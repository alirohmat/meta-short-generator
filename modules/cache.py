"""
modules/cache.py — manifest.json cache
"""
import json
from pathlib import Path
from .utils import log_info, log_error

MANIFEST_NAME = "manifest.json"

def _manifest_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / MANIFEST_NAME

def load_manifest(cache_dir: Path) -> dict:
    p = _manifest_path(cache_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log_error(f"Cache corrupt, reset: {e}")
        return {}

def save_manifest(cache_dir: Path, data: dict):
    p = _manifest_path(cache_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)

def should_regenerate(scene_id: str, new_prompt: str, new_text: str, manifest: dict, cache_dir: Path) -> tuple[bool, bool]:
    entry = manifest.get(scene_id)
    if not entry:
        return True, True
    need_footage = False
    need_audio = False
    if entry.get("prompt") != new_prompt:
        need_footage = True
    footage_path = entry.get("footage_path")
    if not footage_path or not Path(footage_path).exists():
        need_footage = True
    if entry.get("text") != new_text:
        need_audio = True
    audio_path = entry.get("audio_path")
    if not audio_path or not Path(audio_path).exists():
        need_audio = True
    return need_footage, need_audio

def update_entry(cache_dir: Path, scene_id: str, prompt: str, text: str, footage_path: str, audio_path: str, audio_duration: float, footage_status="done", audio_status="done"):
    manifest = load_manifest(cache_dir)
    manifest[scene_id] = {"prompt": prompt, "text": text, "footage_path": footage_path, "audio_path": audio_path, "audio_duration": audio_duration, "footage_status": footage_status, "audio_status": audio_status}
    save_manifest(cache_dir, manifest)
    log_info(f"Cache updated {scene_id}")

def get_entry(cache_dir: Path, scene_id: str):
    return load_manifest(cache_dir).get(scene_id)
