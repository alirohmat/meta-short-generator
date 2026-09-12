"""
modules/telegram_notify.py — Telegram progress + result
Bot API: sendMessage / sendVideo (fallback sendDocument)
Dep: requests only. Enabled if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set.
"""
import requests
from pathlib import Path
from .utils import log_info, log_error

class TelegramNotifier:
    def __init__(self, config=None, token=None, chat_id=None):
        if config is not None:
            token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or token or ""
            chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or chat_id or ""
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.enabled = bool(self.token and self.chat_id)
        self.base = f"https://api.telegram.org/bot{self.token}" if self.enabled else ""
        if self.enabled:
            log_info(f"Telegram: enabled chat {self.chat_id}")
        else:
            log_info("Telegram: disabled (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to enable)")

    def send_message(self, text: str, parse_mode="HTML"):
        if not self.enabled:
            return None
        try:
            r = requests.post(f"{self.base}/sendMessage", data={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode}, timeout=20)
            if r.status_code != 200:
                log_error(f"Telegram sendMessage {r.status_code}: {r.text[:300]}")
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            log_error(f"Telegram sendMessage error {e}")
            return None

    def send_video(self, video_path, caption: str = ""):
        if not self.enabled:
            return None
        p = Path(video_path)
        if not p.exists() or p.stat().st_size == 0:
            return self.send_message(f"❌ Video not found: {p.name}")
        # try sendVideo (50MB limit), fallback sendDocument (2GB)
        for method in ("sendVideo", "sendDocument"):
            try:
                key = "video" if method == "sendVideo" else "document"
                url = f"{self.base}/{method}"
                with open(p, "rb") as f:
                    r = requests.post(url, data={"chat_id": self.chat_id, "caption": caption[:1024]}, files={key: (p.name, f, "video/mp4")}, timeout=180)
                if r.status_code == 200:
                    log_info(f"Telegram {method} OK {p.name} {p.stat().st_size/1_000_000:.1f}MB")
                    return r.json()
                log_error(f"Telegram {method} {r.status_code}: {r.text[:400]}")
                if method == "sendDocument":
                    return None
            except Exception as e:
                log_error(f"Telegram {method} error {e}")
        return None
