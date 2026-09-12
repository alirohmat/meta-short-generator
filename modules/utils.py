"""
modules/utils.py — helpers
"""
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("video-short")
if not logger.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

def log_info(msg): logger.info(msg)
def log_error(msg): logger.error(msg)

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path)

def safe_filename(text, max_len=50):
    s = re.sub(r'[^a-zA-Z0-9_-]+', '_', text).strip('_')
    return s[:max_len] or "scene"

def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass

def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def is_image(path) -> bool:
    return Path(path).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")

def is_video(path) -> bool:
    return Path(path).suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".avi")

def run_command(cmd, verbose=False, timeout=120):
    if verbose:
        log_info(f"$ {' '.join(map(str, cmd))}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        return -1, "", f"timeout: {e}"
    except Exception as e:
        return -1, "", str(e)

def get_media_duration(path) -> float:
    """Prioritas: ffprobe > mutagen > pydub > wave > estimasi"""
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return 0.0
    try:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1", str(p)], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            d = float(r.stdout.strip())
            if d > 0:
                return d
    except Exception:
        pass
    try:
        import mutagen
        m = mutagen.File(str(p))
        if m and hasattr(m, "info") and getattr(m.info, "length", None):
            return float(m.info.length)
    except Exception:
        pass
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(p))
        return len(seg) / 1000.0
    except Exception:
        pass
    try:
        import wave
        if p.suffix.lower() == ".wav":
            with wave.open(str(p), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                if rate:
                    return frames / float(rate)
    except Exception:
        pass
    return 0.0

def estimate_duration_from_text(text: str, chars_per_sec: float = 13.0) -> float:
    if not text:
        return 3.5
    return max(2.0, min(12.0, len(text) / chars_per_sec))
