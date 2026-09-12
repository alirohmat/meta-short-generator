"""
modules/research.py — Search -> Fakta -> Narasi TTS
Provider: Tavily via 38.45.64.53:20128 (fallback Brave)
Flow: search(query) -> snippets -> synthesize narrative -> SCENE_PROMPTS auto unlimited
TTS: angka ditulis kata (Indonesia) agar Fish TTS tidak baca English
"""
import os
import re
import requests
from pathlib import Path
from .utils import log_info, log_error

SEARCH_ENDPOINT = os.getenv("SEARCH_ENDPOINT", "http://38.45.64.53:20128/v1/search")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY", "sk-5e56e0df71e579e4-4fyc83-d46953a7")
SEARCH_MODEL = os.getenv("SEARCH_MODEL", "tavily")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# --- terbilang Indonesia untuk TTS (hindari angka dibaca English) ---
_SATUAN = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]
def _terbilang_id(n: int) -> str:
    if n < 12:
        return _SATUAN[n]
    if n < 20:
        return _terbilang_id(n - 10) + " belas" if n != 11 else "sebelas"
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

def _numbers_to_words_id(text: str) -> str:
    def repl(m):
        try:
            n = int(m.group(0))
            return _terbilang_id(n)
        except:
            return m.group(0)
    return re.sub(r"\b\d+\b", repl, text)

class ResearchAgent:
    def __init__(self, config):
        self.config = config
        self.search_endpoint = getattr(config, "SEARCH_ENDPOINT", SEARCH_ENDPOINT) or os.getenv("SEARCH_ENDPOINT", SEARCH_ENDPOINT)
        self.search_key = getattr(config, "SEARCH_API_KEY", SEARCH_API_KEY) or os.getenv("SEARCH_API_KEY", SEARCH_API_KEY)
        self.search_model = getattr(config, "SEARCH_MODEL", SEARCH_MODEL)
        self.brave_key = getattr(config, "BRAVE_SEARCH_API_KEY", "") or os.getenv("BRAVE_SEARCH_API_KEY", "")
        self.count = int(getattr(config, "RESEARCH_COUNT", 8))
        self.lang = getattr(config, "RESEARCH_LANG", "id")

    def _tavily_search(self, query: str) -> list[dict]:
        if not self.search_endpoint or not self.search_key:
            return []
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.search_key}"}
        payload = {"model": self.search_model, "query": query, "search_type": "web", "max_results": self.count}
        try:
            r = requests.post(self.search_endpoint, headers=headers, json=payload, timeout=25)
            r.raise_for_status()
            j = r.json()
            results = []
            for item in j.get("results", [])[:self.count]:
                results.append({"title": item.get("title",""), "url": item.get("url",""), "desc": item.get("snippet","") or item.get("description","") or item.get("content","") or "", "score": item.get("score",0)})
            log_info(f"Tavily search '{query}' -> {len(results)} results")
            return results
        except Exception as e:
            log_error(f"Tavily search error {e}")
            return []

    def _brave_search(self, query: str) -> list[dict]:
        if not self.brave_key:
            return []
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": self.brave_key}
        params = {"q": query, "count": self.count, "search_lang": self.lang}
        try:
            r = requests.get(BRAVE_ENDPOINT, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            j = r.json()
            results = []
            for item in j.get("web", {}).get("results", [])[:self.count]:
                results.append({"title": item.get("title",""), "url": item.get("url",""), "desc": item.get("description",""), "score": 0})
            log_info(f"Brave search '{query}' -> {len(results)} results")
            return results
        except Exception as e:
            log_error(f"Brave search error {e}")
            return []

    def _search(self, query: str) -> list[dict]:
        res = self._tavily_search(query)
        if res:
            return res
        res = self._brave_search(query)
        if res:
            return res
        log_error("Semua search kosong — fallback akan pakai template")
        return []

    def _extract_facts(self, results: list[dict]) -> list[str]:
        seen = set()
        facts = []
        for r in results:
            text = f"{r['title']}. {r['desc']}"
            sents = re.split(r'(?<=[.!?])\s+', text.strip())
            for s in sents:
                s = re.sub(r'\s+', ' ', s).strip()
                if len(s) < 30 or len(s) > 240:
                    continue
                key = s.lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                facts.append(s)
        return facts[:24]

    def _synthesize(self, query: str, facts: list[str]) -> dict:
        if not facts:
            return {"title": query.title(), "narrative": _numbers_to_words_id(f"Inilah kisah tentang {query}. Mari kita telusuri fakta menariknya."), "sentences": [_numbers_to_words_id(f"Inilah kisah tentang {query}.")], "facts": []}
        qwords = set(query.lower().split())
        scored = []
        for f in facts:
            score = 0
            fl = f.lower()
            for w in qwords:
                if w in fl:
                    score += 2
            if re.search(r'\b(19\d{2}|20\d{2}|622|1 Hijriah|Rabiul Awwal)\b', f):
                score += 3
            if len(f) > 80:
                score += 1
            if f.count(' ') > 8:
                score += 1
            scored.append((score, f))
        scored.sort(key=lambda x: -x[0])
        picked = [f for _, f in scored[:10]]
        sentences = []
        for p in picked[:7]:
            s = p.strip()
            if not s.endswith('.'):
                s += '.'
            s = s[0].upper() + s[1:] if len(s) > 1 else s
            s = _numbers_to_words_id(s)
            sentences.append(s)
            if len(" ".join(sentences)) > 700:
                break
        if len(sentences) < 4 and len(picked) >= 4:
            sentences = [_numbers_to_words_id(s if s.endswith('.') else s+'.') for s in picked[:5]]
        narrative = " ".join(sentences)
        title = query.title().replace("Sejarah ","").strip()[:40] or query.title()
        return {"title": title, "narrative": narrative, "sentences": sentences, "facts": facts}

    def run(self, query: str) -> dict:
        log_info(f"Research: {query}")
        results = self._search(query)
        facts = self._extract_facts(results) if results else []
        out = self._synthesize(query, facts)
        out["raw_results"] = results
        log_info(f"Research done: {len(out['sentences'])} sentences, {len(out['narrative'])} chars")
        for i, s in enumerate(out['sentences'], 1):
            log_info(f"  {i}. {s[:100]}")
        return out

    def to_config(self, query: str, out: dict) -> tuple[str, str, list[dict]]:
        title = f"sejarah_{re.sub(r'[^a-z0-9]+','_', query.lower()).strip('_')[:30]}" if query else out.get("title","video_short")
        script = "\n".join(out["sentences"])
        prompts = []
        for i, sent in enumerate(out["sentences"]):
            clean = sent[:170].strip().rstrip('.')
            prompt = f"cinematic photo, {clean}, vertical 9:16, ultra detailed, photorealistic"
            prompts.append({"id": f"scene_{i+1:02d}", "prompt": prompt, "type": "auto"})
        return title, script, prompts
