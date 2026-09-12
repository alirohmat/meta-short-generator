# Video Short Generator — 9:16 Auto Pipeline

Generate video short vertikal otomatis: **Bot WA (footage) + Fish Audio (TTS) + FFmpeg (compose)**.

Jalan di Python umum: lokal, VPS, Termux, Mac, Linux, Windows. Tanpa Kaggle/Blaxel/Jupyter.
## Struktur
```
video-short-generator/
├── config.py          # EDIT INI PER VIDEO
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── modules/
│   ├── botwa_footage.py  # BotWAFootageGenerator
│   ├── fish_tts.py       # FishTTSGenerator
│   ├── composer.py       # VideoComposer
│   ├── utils.py
│   └── cache.py
├── storage/
│   ├── footage/
│   ├── audio/
│   ├── cache/manifest.json
│   ├── scenes/
│   └── output/final_output.mp4
└── scripts/run.sh|run.ps1
```

## Install
### 1. FFmpeg (wajib, bukan pip)
- Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`
- Mac: `brew install ffmpeg`
- Windows: `winget install ffmpeg` atau `choco install ffmpeg`
- Cek: `ffmpeg -version && ffprobe -version`

### 2. Virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 3. Requirements
```bash
pip install -r requirements.txt
```

### 4. Env
```bash
cp .env.example .env
# isi:
# FISH_AUDIO_API_KEY=...
# FISH_AUDIO_VOICE_ID=...
# BOT_WA_TOKEN= (optional)
nano .env
```

### 5. Config
Edit `config.py`:
- `PROJECT_TITLE`, `SCRIPT`, `SCENE_PROMPTS` (id, prompt, type)
- `VIDEO_WIDTH/HEIGHT/FPS`, `TRANSITION_*`, `BGM_PATH`, `OUTPUT_FILENAME`
## Menjalankan
```bash
python main.py --check        # cek ffmpeg + bot health
python main.py --dry-run      # validasi + estimasi durasi tanpa render/API
python main.py                # full pipeline (footage+tts paralel -> compose)
python main.py --skip-footage # pakai footage existing/placeholder
python main.py --skip-tts     # pakai audio existing/silent
python main.py --force        # regenerate semua (abaikan cache)
python main.py --config custom_config.py
```

Scripts:
```bash
bash scripts/run.sh
bash scripts/run.sh --dry-run
# Windows
powershell -ExecutionPolicy Bypass -File scripts/run.ps1
```

## Cache
`storage/cache/manifest.json`:
```json
{
  "scene_01": {
    "prompt": "...",
    "text": "...",
    "footage_path": "storage/footage/scene_01.jpg",
    "audio_path": "storage/audio/scene_01.mp3",
    "audio_duration": 4.2,
    "footage_status": "done",
    "audio_status": "done"
  }
}
```
- Prompt sama + file ada -> skip regen
- Prompt berubah -> regen footage
- Text berubah -> regen audio
- File hilang -> regen
- JSON corrupt -> reset aman

## Catatan e2b / ephemeral
Sandbox timeout 5 menit -> storage hilang. Persist output ke S3/B2 (`aws s3 cp storage/output/*.mp4 s3://...`) atau mount Volume ke `storage/`.

## Troubleshooting
- `FFmpeg tidak ditemukan` -> install ffmpeg sistem
- `FISH_AUDIO_API_KEY kosong` -> fallback silent audio (estimasi 1s/13chars)
- `Bot WA timeout` -> placeholder 1080x1920 dark + teks prompt
- `xfade gagal` -> fallback concat demuxer tanpa transisi
- `durasi 0` -> estimasi fallback, warning

## Trigger skill
Ucap: "buatkan video short" / "generate video pendek" / "buat video vertikal" / "buat short video" / "generate 9:16 video" -> skill ini.
