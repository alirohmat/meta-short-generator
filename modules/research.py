"""
modules/research.py — Search -> Fakta -> Narasi TTS + Prompt Ilustrasi
Fleksibel: query apapun -> hook naratif + visual prompt ilustrasi generatif
1 kalimat = 1 footage + 1 TTS sinkron durasi audio
"""
import os
import re
import requests
from pathlib import Path
from .utils import log_info, log_error

SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "http://38.45.64.53:20128/v1/search")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY", "sk-5e5...53a7")
SEARCH_MODEL = os.getenv("SEARCH_MODEL", "tavily")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

_SATUAN = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]
def _terbilang_id(n):
    if n < 12: return _SATUAN[n]
    if n < 20: return _terbilang_id(n - 10) + " belas" if n != 11 else "sebelas"
    if n < 100:
        q, r = divmod(n, 10)
        return _SATUAN[q] + " puluh" + (" " + _terbilang_id(r) if r else "")
    if n < 200:
        return "seratus" + (" " + _terbilang_id(n - 100) if n > 100 else "")
    if n < 1000:
        q, r = divmod(n, 100)
        return _SATUAN[q] + " ratus" + (" " + _terbilang_id(r) if r else "")
    if n < 2000:
        return "seribu" + (" " + _terbilang_id(n - 1000) if n > 1000 else "")
    if n < 1000000:
        q, r = divmod(n, 1000)
        return _terbilang_id(q) + " ribu" + (" " + _terbilang_id(r) if r else "")
    if n < 1000000000:
        q, r = divmod(n, 1000000)
        return _terbilang_id(q) + " juta" + (" " + _terbilang_id(r) if r else "")
    return str(n)

_SINGKATAN = {
    r"\bSAW\b": "Sallallahu Alaihi Wasallam",
    r"\bS\.A\.W\b": "Sallallahu Alaihi Wasallam",
    r"\bSWT\b": "Subhanahu Wa Taala",
    r"\bS\.W\.T\b": "Subhanahu Wa Taala",
    r"\bRA\b": "Radhiyallahu Anhu",
    r"\bR\.A\b": "Radhiyallahu Anhu",
    r"\bAS\b": "Alaihis Salam",
}
def _expand_singkatan(text: str) -> str:
    for pat, repl in _SINGKATAN.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text
def _numbers_to_words_id(text):
    text = _expand_singkatan(text)
    return re.sub(r"\b\d+\b", lambda m: _terbilang_id(int(m.group(0))), text)

STOP = set("yang adalah merupakan sebagai untuk dengan secara tersebut pertama kali benar-benar tercatat inilah itulah namun dan atau dari pada ke di sebuah suatu ini itu mereka kita kamu dia kami anda sudah telah akan ada yang itu dalam tempat menjadi simbol sangatlah salah satu dipercaya oleh dibangun tepatnya".split())
# visual concepts English only — jangan campur Indonesia
VISUAL_CONCEPTS = [
    ("berhenti scroll|fakta yang jarang|mengubah sejarah", "dramatic opening reveal, golden sunrise epic light"),
    ("masjid|musholla|surau|quba|tempat ibadah|gereja|kuil|pura", "historic mosque temple interior, stone architecture, warm light"),
    ("hijrah|migrasi|caravan hijrah|wadi ranuna", "hijrah caravan with camels crossing desert valley, travelers arriving"),
    ("rabiul awwal|hijriah|622 m|23 september|tahun hijriah", "ancient stone foundation inscription, historical calendar date"),
    ("batu pertama|peletakan batu|mihrab|baitul maqdis|fondasi", "hands placing first foundation stone, mihrab niche, companions witnessing"),
    ("at.taubah|takwa|ketakwaan|persaudaraan|taqwa", "Quran open to Surah At-Taubah, light rays symbolizing piety"),
    ("khalifah|abbasiyah|umayyah|baghdad|baitul hikmah|kesultanan|kerajaan|dynasty", "Abbasid palace Baghdad golden age, ornate throne hall, scholars"),
    ("harun.*rasyid|khalifah kelima|imam syafi|ulama|scholar debate", "scholar debate in palace library, Abbasid era, scrolls and lamps"),
    ("putra.*enggan|zuhud|prince ascetic|haji jalan kaki|pilgrimage caravan", "humble prince walking pilgrimage caravan to Mecca, desert road"),
    ("perang|pertempuran|battle|jihad|penaklukan|futuhat", "historical battle formation, desert battlefield, banners"),
    ("facebook|mark zuckerberg|harvard|startup|teknologi|AI|internet|media sosial", "modern tech office, servers and screens, startup founders collaborating"),
    ("ekonomi|perdagangan|pasar|dagang|niaga", "historic marketplace bustling, traders and goods, ancient bazaar"),
    ("pendidikan|sekolah|universitas|library|baitul hikmah", "ancient library with scrolls, scholars studying, warm lamp light"),
    ("kota|desa|kampung|pemukiman|negeri", "aerial view ancient village city, mud houses and palm oasis"),
    ("nabi|rasul|sahabat|wali|prophet era", "Prophet era desert village, companions gathering, peaceful devotion"),
]
GENERIC_STYLES = [
    "cinematic lighting, dramatic atmosphere",
    "wide establishing shot, detailed environment",
    "close-up emotional, shallow depth of field",
    "aerial view, epic scale, vibrant colors",
    "interior warm light, historical detail",
    "golden hour, desert atmosphere",
    "wide aerial view, ancient Arabian village",
]
def _translate_visual(text):
    # legacy helper — keep for fallback generic queries
    m={"masjid":"mosque","musholla":"small mosque","jumat":"Friday congregation","sholat":"prayer","hijrah":"migration caravan","rasulullah":"Prophet era","nabi muhammad":"Prophet era","nabi":"prophet","quraisy":"Quraysh","khutbah":"sermon","madinah":"Medina","mekah":"Mecca","quba":"Quba","harun ar-rasyid":"Abbasid caliph Baghdad","abbasiyah":"Abbasid dynasty","baghdad":"Baghdad","khalifah":"caliph","facebook":"Facebook startup","sejarah":"history","kisah":"story","kerajaan":"kingdom","perang":"battle","teknologi":"technology","AI":"artificial intelligence","desa":"village","kota":"city","gunung":"mountain","laut":"sea","hutan":"forest","istana":"palace","perdagangan":"trade","pendidikan":"education"}
    low=text.lower()
    for k,v in sorted(m.items(),key=lambda x:-len(x[0])):
        if k.strip() in low:
            text=re.sub(re.escape(k),v,text,flags=re.I)
    return text
VISUAL_DICT = {"masjid":"mosque","jumat":"Friday"}  # keep compat
VISUAL_STYLES = GENERIC_STYLES
def _to_visual_prompt(sentence, idx, query=""):
    low=sentence.lower()
    # selang-seling foto vs animasi (meta 5s) — idx genap foto, ganjil animasi biar footage variatif
    is_anim = (idx % 3 == 1)  # 1 dari 3 scene jadi animasi, sisanya foto (ubah %2 jika mau 50:50)
    prefix = "cinematic animation" if is_anim else "cinematic photo"
    anim_suffix = ", smooth motion, 5 second clip" if is_anim else ""
    # cek konsep prioritas — match pertama menang (English only)
    for pat, concept in VISUAL_CONCEPTS:
        if re.search(pat, low):
            style=GENERIC_STYLES[idx % len(GENERIC_STYLES)]
            return f"{prefix}, {concept}, {style}{anim_suffix}, ultra detailed, photorealistic, vertical 9:16"[:180]
    # query-aware fallback: translate query jika tidak match konsep
    if query:
        q_vis=_translate_visual(query)[:60]
        style=GENERIC_STYLES[idx % len(GENERIC_STYLES)]
        return f"{prefix}, {q_vis}, {style}{anim_suffix}, ultra detailed, photorealistic, vertical 9:16"[:180]
    style=GENERIC_STYLES[idx % len(GENERIC_STYLES)]
    return f"{prefix}, historical scene, {style}{anim_suffix}, ultra detailed, photorealistic, vertical 9:16"[:180]

class ResearchAgent:
    def __init__(self, config):
        self.config=config
        self.search_endpoint=getattr(config,"SEARCH_ENDPOINT",SEARCH_ENDPOINT) or os.getenv("SEARCH_ENDPOINT",SEARCH_ENDPOINT)
        self.search_key=getattr(config,"SEARCH_API_KEY",SEARCH_API_KEY) or os.getenv("SEARCH_API_KEY",SEARCH_API_KEY)
        self.search_model=getattr(config,"SEARCH_MODEL",SEARCH_MODEL)
        self.brave_key=getattr(config,"BRAVE_SEARCH_API_KEY","") or os.getenv("BRAVE_SEARCH_API_KEY","")
        self.count=int(getattr(config,"RESEARCH_COUNT",8))
        self.lang=getattr(config,"RESEARCH_LANG","id")
    def _tavily_search(self, query):
        if not self.search_endpoint or not self.search_key: return []
        # direct Tavily vs proxy (38.45.64.53) auto-detect
        is_direct = "api.tavily.com" in self.search_endpoint or self.search_key.startswith("tvly-")
        endpoint = "https://api.tavily.com/search" if is_direct else self.search_endpoint
        headers={"Content-Type":"application/json","Authorization":f"Bearer {self.search_key}"}
        if is_direct:
            payload={"query":query,"search_depth":"advanced","include_answer":"advanced","max_results":self.count,"include_raw_content":False}
        else:
            payload={"model":self.search_model,"query":query,"search_type":"web","max_results":self.count,"search_depth":"advanced","include_answer":"advanced"}
        try:
            r=requests.post(endpoint, headers=headers, json=payload, timeout=30); r.raise_for_status()
            j=r.json(); res=[]
            # include_answer advanced -> j["answer"] komprehensif, masukkan sebagai fakta utama
            ans=j.get("answer","")
            if ans and len(ans.strip())>40:
                res.append({"title":f"Ringkasan Tavily: {query}","url":"","desc":ans.strip(),"score":10})
            for item in j.get("results",[])[:self.count]:
                res.append({"title":item.get("title",""),"url":item.get("url",""),"desc":item.get("content","") or item.get("snippet","") or item.get("description","") or "","score":item.get("score",0)})
            log_info(f"Tavily {'direct' if is_direct else 'proxy'} search '{query}' -> {len(res)} results (answer={'ya' if ans else 'tidak'})"); return res
        except Exception as e:
            log_error(f"Tavily search error {e}"); return []
    def _brave_search(self, query):
        if not self.brave_key: return []
        headers={"Accept":"application/json","Accept-Encoding":"gzip","X-Subscription-Token":self.brave_key}
        params={"q":query,"count":self.count,"search_lang":self.lang}
        try:
            r=requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=20); r.raise_for_status()
            j=r.json(); res=[]
            for item in j.get("web",{}).get("results",[])[:self.count]:
                res.append({"title":item.get("title",""),"url":item.get("url",""),"desc":item.get("description",""),"score":0})
            log_info(f"Brave search '{query}' -> {len(res)} results"); return res
        except Exception as e:
            log_error(f"Brave search error {e}"); return []
    def _expand_queries(self, query):
        q=query.strip()
        return [q, f"{q} sejarah latar belakang", f"{q} fakta detail kontroversi dampak", f"{q} makna pelajaran"]
    def _search_comprehensive(self, query):
        all_res=[]; seen_url=set()
        for sub in self._expand_queries(query)[:4]:
            chunk=self._tavily_search(sub)
            for r in chunk:
                k=r.get("url","")[:120]
                if k and k in seen_url: continue
                if k: seen_url.add(k)
                all_res.append(r)
            if len(all_res)>=20: break
        if all_res:
            log_info(f"Comprehensive {len(all_res)} results dari 4 varian query")
            return all_res[:24]
        return self._brave_search(query)
    def _search(self, query):
        # komprehensif multi-query Tavily advanced
        r=self._search_comprehensive(query)
        if r: return r
        r=self._tavily_search(query)
        if r: return r
        r=self._brave_search(query)
        if r: return r
        log_error("Semua search kosong — fallback template"); return []
    def _extract_facts(self, results):
        seen=set(); facts=[]
        for r in results:
            text=f"{r['title']}. {r['desc']}"
            for s in re.split(r'(?<=[.!?])\s+', text.strip()):
                s=re.sub(r'\s+',' ',s).strip()
                if len(s)<30 or len(s)>240: continue
                key=s.lower()[:60]
                if key in seen: continue
                seen.add(key); facts.append(s)
        return facts[:24]
    def _synthesize(self, query, facts):
        if not facts:
            hook=_numbers_to_words_id(f"Berhenti scroll — {query} ternyata menyimpan fakta yang jarang diketahui?")
            return {"title":query.title(),"narrative":hook,"sentences":[hook],"facts":[]}
        qwords=set(query.lower().split()); scored=[]
        for f in facts:
            fl=f.lower(); sc=0
            for w in qwords:
                if w in fl: sc+=2
            if re.search(r'\b(19\d{2}|20\d{2}|622|1 Hijriah|Rabiul Awwal)\b',f): sc+=3
            if len(f)>80: sc+=1
            if f.count(' ')>8: sc+=1
            scored.append((sc,f))
        scored.sort(key=lambda x:-x[0])
        picked=[f for _,f in scored[:12]]
        hook=_numbers_to_words_id(f"Berhenti scroll — {query} ternyata menyimpan fakta yang jarang diketahui?")
        sentences=[hook]
        connectors=["Kebanyakan orang mengira ","Saat itu, ","","Menariknya, ","","Hingga akhirnya, ","Bayangkan, ","Dan inilah pelajaran pentingnya, "]
        for idx,p in enumerate(picked[:7]):
            s=re.sub(r'^\[.*?\]\s*','',p).strip(); s=re.sub(r'\s+',' ',s).strip()
            if not s.endswith('.'): s+='.'
            s=s[0].upper()+s[1:] if len(s)>1 else s
            conn=connectors[idx % len(connectors)]
            if conn: s=conn+s[0].lower()+s[1:] if s else s
            s=_numbers_to_words_id(s)
            sentences.append(s)
            if len(" ".join(sentences))>=820: break
        if len(sentences)<7 and len(picked)>=6:
            while len(sentences)<7 and len(picked)>=len(sentences):
                extra=picked[len(sentences)-1]; extra=re.sub(r'^\[.*?\]\s*','',extra).strip()
                if not extra.endswith('.'): extra+='.'
                sentences.append(_numbers_to_words_id(extra[0].upper()+extra[1:]))
        total=len(" ".join(sentences))
        if total>900:
            while len(" ".join(sentences))>850 and len(sentences)>7: sentences.pop()
        if len(" ".join(sentences))<750:
            cta="Setuju atau tidak? Tulis di komentar kita akan makna sebenarnya dari peristiwa tersebut."
            if cta not in sentences: sentences.append(cta)
        narrative=" ".join(sentences)
        title=query.title().replace("Sejarah ","").strip()[:40] or query.title()
        return {"title":title,"narrative":narrative,"sentences":sentences,"facts":facts}
    def run(self, query):
        log_info(f"Research: {query}")
        results=self._search(query); facts=self._extract_facts(results) if results else []
        out=self._synthesize(query,facts); out["raw_results"]=results
        log_info(f"Research done: {len(out['sentences'])} sentences, {len(out['narrative'])} chars")
        for i,s in enumerate(out['sentences'],1): log_info(f"  {i}. {s[:100]}")
        return out
    def to_config(self, query, out):
        title=f"sejarah_{re.sub(r'[^a-z0-9]+','_',query.lower()).strip('_')[:30]}" if query else out.get("title","video_short")
        script="\n".join(out["sentences"])
        prompts=[]
        for i,sent in enumerate(out["sentences"]):
            prompt=_to_visual_prompt(sent,i,query)
            prompts.append({"id":f"scene_{i+1:02d}","prompt":prompt,"type":"auto"})
        return title, script, prompts
