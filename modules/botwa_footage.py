"""
modules/botwa_footage.py — Bot WA Koyeb footage engine
Class: BotWAFootageGenerator
Methods: health_check, get_media_list, send_prompt, poll_new_media, download_media, generate_scene, generate_all
Fallback sync requests jika aiohttp tidak ada. Retry 3 + exponential backoff + 429 handling. Placeholder Pillow.
"""
import asyncio
import time
import random
from pathlib import Path

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

import requests
from .utils import log_info, log_error, ensure_dir

PLACEHOLDER_W = 1080
PLACEHOLDER_H = 1920

def _make_placeholder(save_path: Path, prompt: str):
    """Buat placeholder 1080x1920 dark background + teks. Fallback tanpa Pillow -> tulis txt."""
    save_path = Path(save_path)
    ensure_dir(save_path.parent)
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (PLACEHOLDER_W, PLACEHOLDER_H), (18, 18, 24))
        draw = ImageDraw.Draw(img)
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        except Exception:
            font_title = ImageFont.load_default()
            font_small = ImageFont.load_default()
        title = "Footage unavailable"
        short = prompt[:120] + ("..." if len(prompt) > 120 else "")
        words = short.split()
        lines = []
        cur = ""
        for wd in words:
            test = (cur + " " + wd).strip()
            if len(test) > 42:
                lines.append(cur)
                cur = wd
            else:
                cur = test
        if cur:
            lines.append(cur)
        y = PLACEHOLDER_H // 2 - 80
        bbox = draw.textbbox((0,0), title, font=font_title)
        tw = bbox[2]-bbox[0]
        draw.text(((PLACEHOLDER_W-tw)//2, y), title, fill=(220,220,255), font=font_title)
        y += 70
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font_small)
            tw = bbox[2]-bbox[0]
            draw.text(((PLACEHOLDER_W-tw)//2, y), line, fill=(180,180,190), font=font_small)
            y += 30
        img.save(save_path, "JPEG", quality=88)
        log_info(f"Placeholder saved {save_path.name}")
    except Exception as e:
        try:
            save_path.write_bytes(b"")
            log_error(f"Pillow gagal buat placeholder: {e}, fallback empty file")
        except Exception:
            pass
    return save_path

def _retry_sleep(attempt: int, retry_after: float = None):
    if retry_after:
        time.sleep(retry_after)
    else:
        time.sleep(min(8, (2 ** attempt) + random.uniform(0, 0.6)))

class BotWAFootageGenerator:
    def __init__(self, config):
        self.config = config
        self.base_url = config.BOT_WA_BASE_URL.rstrip("/")
        self.token = getattr(config, "BOT_WA_TOKEN", "")
        self.to_jid = getattr(config, "BOT_WA_TARGET_JID", "867051314767696@bot")
        self.timeout = getattr(config, "BOT_WA_TIMEOUT", 180)
        self.poll_interval = getattr(config, "BOT_WA_POLL_INTERVAL", 3)
    def _headers(self):
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h
    def health_check(self) -> bool:
        url = f"{self.base_url}/api/state"
        for attempt in range(3):
            try:
                r = requests.get(url, headers=self._headers(), timeout=15)
                if r.status_code == 429:
                    ra = float(r.headers.get("Retry-After", "2"))
                    log_error(f"health_check 429 retry {attempt}")
                    _retry_sleep(attempt, ra)
                    continue
                if r.status_code == 200:
                    log_info(f"health_check OK: {r.text[:120]}")
                    return True
                log_error(f"health_check {r.status_code}: {r.text[:150]}")
                _retry_sleep(attempt)
            except requests.Timeout:
                log_error(f"health_check timeout attempt {attempt}")
                _retry_sleep(attempt)
            except requests.ConnectionError as e:
                log_error(f"health_check connection error {e}")
                _retry_sleep(attempt)
            except Exception as e:
                log_error(f"health_check error {e}")
                _retry_sleep(attempt)
        log_error("health_check gagal total, lanjut dengan warning")
        return False
    def get_media_list(self) -> list:
        url = f"{self.base_url}/api/media"
        for attempt in range(3):
            try:
                r = requests.get(url, headers=self._headers(), timeout=20)
                if r.status_code == 429:
                    _retry_sleep(attempt, float(r.headers.get("Retry-After","2")))
                    continue
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict):
                    for k in ("media","data","files","items"):
                        if k in data and isinstance(data[k], list):
                            return data[k]
                    for v in data.values():
                        if isinstance(v, list):
                            return v
                    return []
                if isinstance(data, list):
                    return data
                return []
            except requests.Timeout:
                _retry_sleep(attempt)
            except requests.ConnectionError:
                _retry_sleep(attempt)
            except Exception as e:
                log_error(f"get_media_list error {e}")
                _retry_sleep(attempt)
        return []
    def send_prompt(self, prompt: str) -> bool:
        url = f"{self.base_url}/api/send"
        payload = {"text": prompt, "to": self.to_jid}
        headers = {"Content-Type": "application/json", **self._headers()}
        for attempt in range(3):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=30)
                if r.status_code == 429:
                    _retry_sleep(attempt, float(r.headers.get("Retry-After","2")))
                    continue
                if r.status_code in (200,201,202):
                    log_info(f"send_prompt OK: {prompt[:60]}...")
                    return True
                log_error(f"send_prompt {r.status_code}: {r.text[:200]}")
                _retry_sleep(attempt)
            except requests.Timeout:
                _retry_sleep(attempt)
            except requests.ConnectionError:
                _retry_sleep(attempt)
            except Exception as e:
                log_error(f"send_prompt error {e}")
                _retry_sleep(attempt)
        return False
    def _extract_url(self, item: dict) -> str | None:
        if not isinstance(item, dict):
            return None
        for k in ("url","src","link","path","file","media_url","download_url"):
            if k in item and isinstance(item[k], str):
                v = item[k]
                if v.startswith("http"):
                    return v
                if v.startswith("/"):
                    return self.base_url + v
        for v in item.values():
            if isinstance(v, str) and v.startswith("http") and any(ext in v.lower() for ext in [".mp4",".jpg",".png",".webp",".jpeg",".mov"]):
                return v
        return None
    def poll_new_media(self, old_media_list: list, timeout: int = None) -> dict | None:
        if timeout is None:
            timeout = self.timeout
        old_ids = set()
        for m in old_media_list:
            mid = str(m.get("id", m.get("url", m.get("src","")))) if isinstance(m, dict) else str(m)
            old_ids.add(mid)
        waited = 0
        while waited < timeout:
            time.sleep(self.poll_interval)
            waited += self.poll_interval
            cur = self.get_media_list()
            new_items = []
            for m in cur:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id", m.get("url", m.get("src",""))))
                if mid not in old_ids:
                    new_items.append(m)
            if new_items:
                return new_items[-1]
            if len(cur) > len(old_media_list):
                return cur[-1]
            if waited % 30 == 0:
                log_info(f"poll_new_media menunggu {waited}/{timeout}s")
        return None
    def download_media(self, url_or_path: str, save_path: Path) -> bool:
        save_path = Path(save_path)
        ensure_dir(save_path.parent)
        if not url_or_path.startswith("http"):
            url_or_path = self.base_url + ("/" if not url_or_path.startswith("/") else "") + url_or_path
        for attempt in range(3):
            try:
                with requests.get(url_or_path, headers=self._headers(), stream=True, timeout=60) as r:
                    if r.status_code == 429:
                        _retry_sleep(attempt, float(r.headers.get("Retry-After","2")))
                        continue
                    r.raise_for_status()
                    ctype = r.headers.get("Content-Type","")
                    ext = Path(url_or_path.split("?")[0]).suffix.lower()
                    if not ext or ext not in (".jpg",".jpeg",".png",".webp",".mp4",".mov",".webm"):
                        if "video" in ctype:
                            ext = ".mp4"
                        elif "image" in ctype:
                            ext = ".jpg"
                    if ext and save_path.suffix.lower() != ext and save_path.suffix.lower() in (".jpg",".mp4"):
                        save_path = save_path.with_suffix(ext)
                    with open(save_path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    if save_path.stat().st_size == 0:
                        raise ValueError("download empty")
                    log_info(f"download_media OK {save_path.name} ({save_path.stat().st_size} bytes)")
                    return True
            except requests.Timeout:
                _retry_sleep(attempt)
            except requests.ConnectionError:
                _retry_sleep(attempt)
            except Exception as e:
                log_error(f"download_media error {e}")
                _retry_sleep(attempt)
        return False
    def generate_scene(self, scene: dict) -> Path:
        scene_id = scene["id"]
        prompt = scene["prompt"]
        footage_dir = Path(self.config.FOOTAGE_DIR)
        want_video = "animation" in prompt.lower() or scene.get("type") == "animation"
        save_path = footage_dir / f"{scene_id}.{'mp4' if want_video else 'jpg'}"
        old = self.get_media_list()
        if not self.send_prompt(prompt):
            log_error(f"send_prompt gagal {scene_id}, fallback placeholder")
            ph = _make_placeholder(save_path.with_suffix(".jpg"), prompt)
            return ph
        new_item = self.poll_new_media(old, timeout=self.timeout)
        if new_item:
            url = self._extract_url(new_item)
            if not url:
                try:
                    r = requests.get(f"{self.base_url}/api/logs", params={"level":"bot"}, headers=self._headers(), timeout=15)
                    if r.status_code == 200:
                        txt = r.text
                        import re
                        m = re.findall(r"https?://[^\s\"\']+\.(?:mp4|jpg|jpeg|png|webp)", txt)
                        if m:
                            url = m[-1]
                except Exception:
                    pass
            if url:
                ok = self.download_media(url, save_path)
                if ok:
                    for ext in (".mp4",".jpg",".jpeg",".png",".webp",".mov"):
                        cand = footage_dir / f"{scene_id}{ext}"
                        if cand.exists() and cand.stat().st_size > 0:
                            return cand
                    return save_path if save_path.exists() else save_path.with_suffix(".jpg")
            log_error(f"poll dapat item tanpa URL {scene_id}: {new_item}")
        log_error(f"Timeout/gagal footage {scene_id}, pakai placeholder")
        ph = _make_placeholder(save_path.with_suffix(".jpg"), prompt)
        return ph
    def generate_all(self, scenes: list) -> dict:
        out = {}
        for sc in scenes:
            try:
                p = self.generate_scene(sc)
                out[sc["id"]] = p
            except Exception as e:
                log_error(f"generate_scene {sc['id']} crash {e}, placeholder")
                want = Path(self.config.FOOTAGE_DIR) / f"{sc['id']}.jpg"
                out[sc["id"]] = _make_placeholder(want, sc.get("prompt",""))
        return out
    async def health_check_async(self) -> bool:
        if not HAS_AIOHTTP:
            return self.health_check()
        url = f"{self.base_url}/api/state"
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status == 429:
                            await asyncio.sleep(float(r.headers.get("Retry-After","2")))
                            continue
                        return r.status == 200
            except Exception as e:
                log_error(f"health_check_async {e}")
                await asyncio.sleep(min(8, 2**attempt))
        return False
    async def generate_all_async(self, scenes: list) -> dict:
        import concurrent.futures
        loop = asyncio.get_running_loop()
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {loop.run_in_executor(ex, self.generate_scene, sc): sc["id"] for sc in scenes}
            for fut in asyncio.as_completed(futs):
                sid = futs[fut]
                try:
                    results[sid] = await fut
                except Exception as e:
                    log_error(f"async generate {sid} {e}")
                    want = Path(self.config.FOOTAGE_DIR) / f"{sid}.jpg"
                    results[sid] = _make_placeholder(want, "")
        return results
