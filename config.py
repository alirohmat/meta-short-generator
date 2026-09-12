"""
config.py — EDITABLE BRAIN
User hanya edit file ini per video.
Semua API key dibaca dari env / .env, jangan hardcode.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

PROJECT_TITLE = "contoh_video_short"

SCRIPT = """
Di sebuah rumah tua yang sudah lama ditinggalkan, angin malam berhembus pelan.
Kabut tebal menyelimuti halaman, lampu temaram berkelip di kejauhan.
Di atas meja kayu, sebuah buku harian terbuka, halamannya bergerak perlahan.
Malam itu, rahasia lama mulai terungkap.
"""

SCENE_PROMPTS = [
    {"id": "scene_01", "prompt": "cinematic photo, abandoned house at night, fog, ultra detailed, vertical 9:16", "type": "auto"},
    {"id": "scene_02", "prompt": "cinematic animation, dark forest, moonlight, mysterious atmosphere, vertical 9:16", "type": "auto"},
    {"id": "scene_03", "prompt": "cinematic photo, old diary on wooden table, candle light, dramatic shadow, vertical 9:16", "type": "auto"},
]

FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
FISH_AUDIO_VOICE_ID = os.getenv("FISH_AUDIO_VOICE_ID", "isi_voice_id")
FISH_AUDIO_FORMAT = os.getenv("FISH_AUDIO_FORMAT", "mp3")
FISH_AUDIO_BASE_URL = os.getenv("FISH_AUDIO_BASE_URL", "https://api.fish.audio")
FISH_AUDIO_MODEL = os.getenv("FISH_AUDIO_MODEL", "s2.1-pro-free")

BOT_WA_BASE_URL = os.getenv("BOT_WA_BASE_URL", "https://bot-wa.koyeb.app")
BOT_WA_TOKEN = os.getenv("BOT_WA_TOKEN", "")
BOT_WA_TARGET_JID = os.getenv("BOT_WA_TARGET_JID", "867051314767696@bot")
BOT_WA_TIMEOUT = int(os.getenv("BOT_WA_TIMEOUT", "180"))
BOT_WA_POLL_INTERVAL = int(os.getenv("BOT_WA_POLL_INTERVAL", "3"))

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
TRANSITION_DURATION = 0.5
TRANSITION_TYPE = "fade"

BGM_PATH = os.getenv("BGM_PATH") or None
BGM_VOLUME = float(os.getenv("BGM_VOLUME", "0.15"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

OUTPUT_FILENAME = "final_output.mp4"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
FOOTAGE_DIR = STORAGE_DIR / "footage"
AUDIO_DIR = STORAGE_DIR / "audio"
CACHE_DIR = STORAGE_DIR / "cache"
SCENES_DIR = STORAGE_DIR / "scenes"
OUTPUT_DIR = STORAGE_DIR / "output"
for p in [FOOTAGE_DIR, AUDIO_DIR, CACHE_DIR, SCENES_DIR, OUTPUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)
