"""
modules/fish_tts.py — Fish Audio TTS Engine
Class: FishTTSGenerator
Methods: split_text, generate_audio, get_duration, generate_scene_audio, generate_all
Fallback silent audio via ffmpeg anullsrc. Chunk >550 chars.
"""
import re
import time
import random
import subprocess
import tempfile
from pathlib import Path
import requests
try:
    import aiohttp
    HAS_AIO = True
except ImportError:
    HAS_AIO = False
from .utils import log_info, log_error, get_media_duration, estimate_duration_from_text, ensure_dir, run_command

class FishTTSGenerator:
    def __init__(self, config):
        self.config = config
        self.api_key = getattr(config, "FISH_AUDIO_API_KEY", "")
        self.voice_id = getattr(config, "FISH_AUDIO_VOICE_ID", "isi_voice_id")
        self.fmt = getattr(config, "FISH_AUDIO_FORMAT", "mp3")
        self.base_url = getattr(config, "FISH_AUDIO_BASE_URL", "https://api.fish.audio").rstrip("/")
        self.model = getattr(config, "FISH_AUDIO_MODEL", "s2.1-pro-free")
    def split_text(self, text: str, max_chars=550) -> list[str]:
        if not text:
            return []
        if len(text) <= max_chars:
            return [text]
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        chunks = []
        cur = ""
        for s in sentences:
            if len(s) <= max_chars and len(cur) + len(s) + 1 <= max_chars:
                cur = (cur + " " + s).strip()
            elif len(s) > max_chars:
                if cur:
                    chunks.append(cur)
                    cur = ""
                for i in range(0, len(s), max_chars):
                    chunks.append(s[i:i+max_chars])
            else:
                if cur:
                    chunks.append(cur)
                cur = s
        if cur:
            chunks.append(cur)
        return [c for c in chunks if c.strip()]
    def get_duration(self, file_path) -> float:
        d = get_media_duration(file_path)
        return d if d > 0 else 0.0
    def _tts_request_once(self, text: str) -> bytes | None:
        if not self.api_key or self.api_key in ("", "isi_voice_id"):
            return None
        endpoints = [f"{self.base_url}/v1/tts", f"{self.base_url}/api/v1/tts"]
        headers_base = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "model": self.model}
        payloads = [{"text": text, "reference_id": self.voice_id, "format": self.fmt}, {"text": text, "voice_id": self.voice_id, "format": self.fmt}]
        for url in endpoints:
            for payload in payloads:
                for attempt in range(3):
                    try:
                        r = requests.post(url, json=payload, headers=headers_base, timeout=60)
                        if r.status_code == 429:
                            time.sleep(float(r.headers.get("Retry-After","2")) + random.uniform(0,0.5))
                            continue
                        if r.status_code in (400,401,403,404):
                            break
                        if r.status_code == 200 and r.content:
                            ctype = r.headers.get("Content-Type","")
                            if "application/json" in ctype:
                                try:
                                    j = r.json()
                                    for k in ("url","audio","data","result"):
                                        if k in j and isinstance(j[k], str) and j[k].startswith("http"):
                                            ar = requests.get(j[k], timeout=60)
                                            ar.raise_for_status()
                                            return ar.content
                                    for k in ("audio_base64","data_base64","content"):
                                        if k in j and isinstance(j[k], str) and len(j[k]) > 100:
                                            import base64
                                            return base64.b64decode(j[k])
                                except Exception:
                                    pass
                            else:
                                return r.content
                        time.sleep(min(6, 2**attempt + random.uniform(0,0.4)))
                        break
                    except requests.Timeout:
                        time.sleep(min(6, 2**attempt))
                    except requests.ConnectionError:
                        time.sleep(min(6, 2**attempt))
                    except Exception as e:
                        log_error(f"tts request error {e}")
                        time.sleep(1)
        return None
    def _make_silent(self, save_path: Path, duration: float):
        save_path = Path(save_path)
        ensure_dir(save_path.parent)
        duration = max(1.0, duration)
        cmd = ["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r=44100:cl=stereo","-t",str(duration),"-c:a","aac" if save_path.suffix==".m4a" else "libmp3lame","-q:a","2",str(save_path)]
        if save_path.suffix.lower() not in (".mp3",".wav",".m4a",".aac"):
            save_path = save_path.with_suffix(".mp3")
            cmd[-1] = str(save_path)
        code, out, err = run_command(cmd, timeout=30)
        if code != 0:
            run_command(["ffmpeg","-y","-f","lavfi","-i",f"anullsrc=r=44100:cl=stereo","-t",str(duration),"-c:a","libmp3lame",str(save_path)], timeout=30)
        log_info(f"Silent audio {save_path.name} {duration:.1f}s")
        return save_path
    def generate_audio(self, text: str, save_path: Path) -> dict:
        save_path = Path(save_path)
        ensure_dir(save_path.parent)
        chunks = self.split_text(text, 550)
        if not chunks:
            chunks = [text]
        if len(chunks) == 1:
            data = self._tts_request_once(chunks[0])
            if data:
                save_path.write_bytes(data)
                dur = self.get_duration(save_path) or estimate_duration_from_text(text)
                return {"audio_path": save_path, "duration": dur, "text": text, "placeholder": False}
            else:
                dur = estimate_duration_from_text(text)
                p = self._make_silent(save_path.with_suffix(".mp3"), dur)
                return {"audio_path": p, "duration": dur, "text": text, "placeholder": True}
        tmpdir = Path(tempfile.mkdtemp())
        chunk_files = []
        total_placeholder = False
        for i, ch in enumerate(chunks):
            tmpf = tmpdir / f"chunk_{i}.mp3"
            data = self._tts_request_once(ch)
            if data:
                tmpf.write_bytes(data)
                chunk_files.append(tmpf)
            else:
                total_placeholder = True
                silent = tmpdir / f"chunk_{i}_silent.mp3"
                self._make_silent(silent, estimate_duration_from_text(ch))
                chunk_files.append(silent)
        if not chunk_files:
            dur = estimate_duration_from_text(text)
            p = self._make_silent(save_path.with_suffix(".mp3"), dur)
            return {"audio_path": p, "duration": dur, "text": text, "placeholder": True}
        if len(chunk_files) == 1:
            import shutil
            shutil.copy(str(chunk_files[0]), str(save_path.with_suffix(".mp3")))
            save_path = save_path.with_suffix(".mp3")
        else:
            lst = tmpdir / "list.txt"
            lst.write_text("\n".join([f"file '{c.resolve()}'" for c in chunk_files]), encoding="utf-8")
            out = save_path.with_suffix(".mp3")
            code, o, e = run_command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(out)], timeout=60)
            if code != 0:
                run_command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c:a","libmp3lame","-q:a","2",str(out)], timeout=60)
            save_path = out
        dur = self.get_duration(save_path) or estimate_duration_from_text(text)
        return {"audio_path": save_path, "duration": dur, "text": text, "placeholder": total_placeholder}
    def generate_scene_audio(self, scene: dict, script_segment: str) -> dict:
        scene_id = scene["id"]
        save_path = Path(self.config.AUDIO_DIR) / f"{scene_id}.mp3"
        log_info(f"Scene {scene_id}: generating audio ({len(script_segment)} chars)")
        res = self.generate_audio(script_segment, save_path)
        res["scene_id"] = scene_id
        log_info(f"Audio {scene_id}: {res['audio_path'].name} {res['duration']:.1f}s placeholder={res['placeholder']}")
        return res
    def generate_all(self, script: str, scenes: list) -> dict:
        import re as _re
        texts = [p.strip() for p in _re.split(r'\n+', script.strip()) if p.strip()]
        if len(texts) == 1:
            sents = _re.split(r'(?<=[.!?])\s+', texts[0])
            sents = [s.strip() for s in sents if s.strip()]
            if len(sents) > 1:
                texts = sents
        segments = []
        if len(texts) == len(scenes):
            segments = texts
        elif len(texts) > len(scenes):
            per = len(texts)//len(scenes)
            rem = len(texts)%len(scenes)
            idx=0
            for i in range(len(scenes)):
                take = per + (1 if i<rem else 0)
                segments.append(" ".join(texts[idx:idx+take]))
                idx+=take
        else:
            for i in range(len(scenes)):
                segments.append(texts[i] if i < len(texts) else texts[-1] if texts else scenes[i].get("prompt",""))
        out = {}
        for sc, seg in zip(scenes, segments):
            try:
                out[sc["id"]] = self.generate_scene_audio(sc, seg)
            except Exception as e:
                log_error(f"generate_scene_audio {sc['id']} crash {e}")
                dur = estimate_duration_from_text(seg)
                p = self._make_silent(Path(self.config.AUDIO_DIR)/f"{sc['id']}.mp3", dur)
                out[sc["id"]] = {"scene_id": sc["id"], "audio_path": p, "duration": dur, "text": seg, "placeholder": True}
        return out
