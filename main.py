"""
main.py — orchestrator video-short-generator
Usage:
  python main.py
  python main.py --dry-run
  python main.py --skip-footage
  python main.py --skip-tts
  python main.py --force
  python main.py --config custom_config.py
"""
import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.utils import log_info, log_error, check_ffmpeg, get_media_duration, load_env, ensure_dir, estimate_duration_from_text
from modules.cache import load_manifest, update_entry, should_regenerate
from modules.botwa_footage import BotWAFootageGenerator
from modules.fish_tts import FishTTSGenerator
from modules.composer import VideoComposer
from modules.telegram_notify import TelegramNotifier

def load_config(path: str):
    p = Path(path)
    if not p.exists():
        p = Path("config.py")
    spec = importlib.util.spec_from_file_location("config", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    parser = argparse.ArgumentParser(description="video-short-generator")
    parser.add_argument("--dry-run", action="store_true", help="validasi tanpa render berat")
    parser.add_argument("--skip-footage", action="store_true", help="skip footage, pakai yang ada/placeholder")
    parser.add_argument("--skip-tts", action="store_true", help="skip TTS, pakai yang ada/silent")
    parser.add_argument("--force", action="store_true", help="abaikan cache, regenerate semua")
    parser.add_argument("--config", default="config.py", help="path config custom")
    parser.add_argument("--check", action="store_true", help="alias dry-run + health check")
    args = parser.parse_args()
    load_env()
    config = load_config(args.config)
    for d in [config.FOOTAGE_DIR, config.AUDIO_DIR, config.CACHE_DIR, config.SCENES_DIR, config.OUTPUT_DIR]:
        ensure_dir(d)
    notifier = TelegramNotifier(config)
    dry_run = args.dry_run or args.check or getattr(config, "DRY_RUN", False)
    log_info(f"Starting video generation: {config.PROJECT_TITLE}")
    if notifier.enabled:
        notifier.send_message(f"🎬 <b>{config.PROJECT_TITLE}</b> mulai — {len(config.SCENE_PROMPTS)} scenes | dry_run={dry_run}")
    log_info(f"Config: {args.config} | dry_run={dry_run} force={args.force} skip_footage={args.skip_footage} skip_tts={args.skip_tts}")
    log_info(f"Scenes: {len(config.SCENE_PROMPTS)}")
    if not config.SCENE_PROMPTS:
        log_error("SCENE_PROMPTS kosong")
        sys.exit(1)
    if not check_ffmpeg():
        msg = "FFmpeg/ffprobe tidak ditemukan. Install ffmpeg dulu."
        if dry_run:
            log_error(msg + " (dry-run lanjut)")
        else:
            log_error(msg)
            sys.exit(1)
    else:
        log_info("FFmpeg: OK")
    if not args.skip_footage:
        try:
            bot = BotWAFootageGenerator(config)
            ok = bot.health_check()
            log_info("Bot WA: OK" if ok else "Bot WA: tidak reachable (akan fallback placeholder)")
        except Exception as e:
            log_error(f"Bot WA health error {e}")
    if not config.FISH_AUDIO_API_KEY and not args.skip_tts:
        log_error("FISH_AUDIO_API_KEY kosong -> TTS akan fallback silent audio")
    if dry_run:
        import re
        log_info("=== DRY-RUN SUMMARY ===")
        texts = [p.strip() for p in re.split(r'\n+', config.SCRIPT.strip()) if p.strip()]
        if len(texts)==1 and texts and len(texts[0]):
            sents = re.split(r'(?<=[.!?])\s+', texts[0])
            sents=[s.strip() for s in sents if s.strip()]
            if len(sents)>1:
                texts=sents
        if len(texts)==len(config.SCENE_PROMPTS):
            segs=texts
        elif len(texts)>len(config.SCENE_PROMPTS):
            per=len(texts)//len(config.SCENE_PROMPTS)
            rem=len(texts)%len(config.SCENE_PROMPTS)
            idx=0
            segs=[]
            for i in range(len(config.SCENE_PROMPTS)):
                take=per+(1 if i<rem else 0)
                segs.append(" ".join(texts[idx:idx+take]))
                idx+=take
        else:
            segs=[]
            for i in range(len(config.SCENE_PROMPTS)):
                segs.append(texts[i] if i<len(texts) else texts[-1] if texts else config.SCENE_PROMPTS[i].get("prompt",""))
        id2text = {config.SCENE_PROMPTS[i]["id"]: segs[i] for i in range(len(config.SCENE_PROMPTS))}
        total_est=0
        for sc in config.SCENE_PROMPTS:
            sid=sc["id"]
            txt=id2text.get(sid,"")
            est=estimate_duration_from_text(txt)
            total_est+=est
            sf="exists" if (config.FOOTAGE_DIR/f"{sid}.jpg").exists() or (config.FOOTAGE_DIR/f"{sid}.mp4").exists() else "missing"
            sa="exists" if (config.AUDIO_DIR/f"{sid}.mp3").exists() else "missing"
            log_info(f"  {sid}: prompt={sc['prompt'][:45]}... | text={txt[:40]}... | est {est:.1f}s | footage:{sf} audio:{sa}")
        trans=getattr(config,"TRANSITION_DURATION",0.5) if len(config.SCENE_PROMPTS)>1 else 0
        log_info(f"Estimasi durasi total: {total_est - (len(config.SCENE_PROMPTS)-1)*trans:.1f}s (sum {total_est:.1f}s - trans {(len(config.SCENE_PROMPTS)-1)*trans:.1f}s)")
        log_info(f"Output: {config.OUTPUT_DIR/config.OUTPUT_FILENAME}")
        log_info("DRY-RUN selesai (tidak ada API call / render)")
        return
    manifest = load_manifest(config.CACHE_DIR)
    import re
    texts = [p.strip() for p in re.split(r'\n+', config.SCRIPT.strip()) if p.strip()]
    if len(texts)==1 and texts and len(texts[0]):
        sents=re.split(r'(?<=[.!?])\s+', texts[0])
        sents=[s.strip() for s in sents if s.strip()]
        if len(sents)>1:
            texts=sents
    if len(texts)==len(config.SCENE_PROMPTS):
        segments=texts
    elif len(texts)>len(config.SCENE_PROMPTS):
        per=len(texts)//len(config.SCENE_PROMPTS)
        rem=len(texts)%len(config.SCENE_PROMPTS)
        idx=0
        segments=[]
        for i in range(len(config.SCENE_PROMPTS)):
            take=per+(1 if i<rem else 0)
            segments.append(" ".join(texts[idx:idx+take]))
            idx+=take
    else:
        segments=[]
        for i in range(len(config.SCENE_PROMPTS)):
            segments.append(texts[i] if i<len(texts) else texts[-1] if texts else config.SCENE_PROMPTS[i].get("prompt",""))
    id2text={config.SCENE_PROMPTS[i]["id"]: segments[i] for i in range(len(config.SCENE_PROMPTS))}
    import concurrent.futures
    def run_footage():
        if args.skip_footage:
            log_info("Skip footage -> pakai existing / placeholder")
            out={}
            for sc in config.SCENE_PROMPTS:
                sid=sc["id"]
                found=None
                for ext in (".mp4",".jpg",".jpeg",".png",".webp"):
                    cand=config.FOOTAGE_DIR/f"{sid}{ext}"
                    if cand.exists() and cand.stat().st_size>0:
                        found=cand
                        break
                if found and not args.force:
                    log_info(f"[CACHE] footage {sid} pakai existing {found.name}")
                    out[sid]=found
                else:
                    from modules.botwa_footage import _make_placeholder
                    out[sid]=_make_placeholder(config.FOOTAGE_DIR/f"{sid}.jpg", sc["prompt"])
            return out
        bot = BotWAFootageGenerator(config)
        out={}
        for sc in config.SCENE_PROMPTS:
            sid=sc["id"]
            if not args.force:
                ent=manifest.get(sid)
                if ent and ent.get("prompt")==sc["prompt"] and ent.get("footage_path") and Path(ent["footage_path"]).exists():
                    log_info(f"[CACHE] skip footage {sid}")
                    out[sid]=Path(ent["footage_path"])
                    continue
                for ext in (".mp4",".jpg",".jpeg",".png",".webp"):
                    cand=config.FOOTAGE_DIR/f"{sid}{ext}"
                    if cand.exists() and cand.stat().st_size>0 and ent and ent.get("prompt")==sc["prompt"]:
                        log_info(f"[CACHE] footage {sid} existing {cand.name}")
                        out[sid]=cand
                        break
                if sid in out:
                    continue
            log_info(f"Scene {sid}: generating footage")
            try:
                out[sid]=bot.generate_scene(sc)
            except Exception as e:
                log_error(f"Footage {sid} gagal {e}")
                from modules.botwa_footage import _make_placeholder
                out[sid]=_make_placeholder(config.FOOTAGE_DIR/f"{sid}.jpg", sc["prompt"])
        return out
    def run_tts():
        tts = FishTTSGenerator(config)
        if args.skip_tts:
            log_info("Skip TTS -> pakai existing / silent")
            out={}
            for sc in config.SCENE_PROMPTS:
                sid=sc["id"]
                found=None
                for ext in (".mp3",".wav",".m4a"):
                    cand=config.AUDIO_DIR/f"{sid}{ext}"
                    if cand.exists() and cand.stat().st_size>0:
                        found=cand
                        break
                if found and not args.force:
                    d=get_media_duration(found) or estimate_duration_from_text(id2text[sid])
                    out[sid]={"audio_path":found,"duration":d,"text":id2text[sid],"placeholder":False}
                    log_info(f"[CACHE] audio {sid} pakai existing")
                else:
                    d=estimate_duration_from_text(id2text[sid])
                    out[sid]={"audio_path":tts._make_silent(config.AUDIO_DIR/f"{sid}.mp3", d),"duration":d,"text":id2text[sid],"placeholder":True}
            return out
        out={}
        for sc in config.SCENE_PROMPTS:
            sid=sc["id"]
            if not args.force:
                ent=manifest.get(sid)
                if ent and ent.get("text")==id2text[sid] and ent.get("audio_path") and Path(ent["audio_path"]).exists():
                    log_info(f"[CACHE] skip audio {sid}")
                    out[sid]={"audio_path":Path(ent["audio_path"]),"duration":float(ent.get("audio_duration",0) or estimate_duration_from_text(id2text[sid])),"text":id2text[sid],"placeholder":ent.get("audio_status")=="placeholder"}
                    continue
            out[sid]=tts.generate_scene_audio(sc, id2text[sid])
        return out
    log_info("Generate footage + audio (concurrent)")
    if notifier.enabled:
        notifier.send_message(f"⏳ <b>{config.PROJECT_TITLE}</b> — generate footage + audio …")
    footage_map={}
    audio_map={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f1=ex.submit(run_footage)
        f2=ex.submit(run_tts)
        try:
            footage_map=f1.result()
        except Exception as e:
            log_error(f"Footage thread error {e}")
        try:
            audio_map=f2.result()
        except Exception as e:
            log_error(f"TTS thread error {e}")
    for sc in config.SCENE_PROMPTS:
        sid=sc["id"]
        fp=footage_map.get(sid)
        am=audio_map.get(sid)
        fp_str=str(fp) if fp and Path(fp).exists() else ""
        if isinstance(am, dict):
            ap_str=str(am.get("audio_path","")) if am.get("audio_path") and Path(am.get("audio_path")).exists() else ""
            dur=float(am.get("duration",0) or 0)
            a_status="placeholder" if am.get("placeholder") else "done"
        elif isinstance(am, (str,Path)) and am and Path(am).exists():
            ap_str=str(Path(am))
            dur=get_media_duration(Path(am)) or estimate_duration_from_text(id2text[sid])
            a_status="done"
        else:
            ap_str=""
            dur=estimate_duration_from_text(id2text[sid])
            a_status="placeholder"
        f_status="done" if fp_str and Path(fp_str).exists() else "missing"
        update_entry(config.CACHE_DIR, sid, sc["prompt"], id2text[sid], fp_str, ap_str, dur, f_status, a_status)
    if notifier.enabled:
        ok_f = len([v for v in footage_map.values() if v and Path(v).exists()])
        ok_a = len([v for v in audio_map.values() if isinstance(v, dict) and v.get("audio_path") and Path(v.get("audio_path")).exists()])
        notifier.send_message(f"🎞 Footage {ok_f}/{len(config.SCENE_PROMPTS)} | Audio {ok_a}/{len(config.SCENE_PROMPTS)} — composing …")
    log_info("Composing final video")
    composer=VideoComposer(config)
    try:
        out = composer.render(footage_map, audio_map, dry_run=False)
        if out and Path(out).exists():
            log_info(f"Output saved to {out}")
            audios=[]
            for v in audio_map.values():
                if isinstance(v, dict) and v.get("audio_path") and Path(v.get("audio_path")).exists():
                    audios.append(Path(v["audio_path"]))
                elif isinstance(v, (str,Path)) and Path(v).exists():
                    audios.append(Path(v))
            total=sum([get_media_duration(a) for a in audios]) if audios else sum([estimate_duration_from_text(id2text[s["id"]]) for s in config.SCENE_PROMPTS])
            trans=(len(config.SCENE_PROMPTS)-1)*config.TRANSITION_DURATION if len(config.SCENE_PROMPTS)>1 else 0
            log_info(f"Estimasi durasi: {total - trans:.1f}s")
            if notifier.enabled:
                notifier.send_message(f"✅ <b>{config.PROJECT_TITLE}</b> selesai — {total - trans:.1f}s — kirim video …")
                notifier.send_video(out, caption=f"{config.PROJECT_TITLE} — {total - trans:.1f}s")
        else:
            log_error("Compose gagal, output tidak ada")
            if notifier.enabled:
                notifier.send_message(f"❌ <b>{config.PROJECT_TITLE}</b> gagal — output tidak ada")
            sys.exit(1)
    except Exception as e:
        log_error(f"Compose error {e}")
        if 'notifier' in locals() and notifier.enabled:
            notifier.send_message(f"❌ <b>{config.PROJECT_TITLE if 'config' in locals() else 'video'}</b> error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
