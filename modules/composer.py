"""
modules/composer.py — VideoComposer
1080x1920 30fps libx264/aac yuv420p
Image: Ken Burns zoompan, Video: scale/crop + loop/trim
Transisi xfade 0.5s fallback concat demuxer, audio acrossfade fallback concat
Anti-AI detect: strip metadata (-map_metadata -1, no encoder/creation_time)
"""
import subprocess
from pathlib import Path
from .utils import log_info, log_error, is_image, is_video, get_media_duration, ensure_dir, run_command

META_STRIP = ["-map_metadata", "-1", "-metadata", "creation_time=", "-metadata", "encoder=", "-metadata", "comment=", "-fflags", "+bitexact"]

class VideoComposer:
    def __init__(self, config):
        self.config = config
        self.w = getattr(config, "VIDEO_WIDTH", 1080)
        self.h = getattr(config, "VIDEO_HEIGHT", 1920)
        self.fps = getattr(config, "VIDEO_FPS", 30)
        self.trans_dur = getattr(config, "TRANSITION_DURATION", 0.5)
        self.trans_type = getattr(config, "TRANSITION_TYPE", "fade")
        self.bgm = getattr(config, "BGM_PATH", None)
        self.bgm_vol = getattr(config, "BGM_VOLUME", 0.15)
    def _scene_video(self, src: Path, duration: float, out: Path):
        src = Path(src)
        out = Path(out)
        ensure_dir(out.parent)
        duration = max(1.0, float(duration))
        total_frames = max(1, round(duration * self.fps))
        if is_image(src):
            vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},setsar=1,zoompan=z='min(zoom+0.0015,1.3)':d={total_frames}:s={self.w}x{self.h}:fps={self.fps}"
            cmd = ["ffmpeg","-y","-threads","1","-loop","1","-t",str(duration),"-i",str(src),"-vf",vf,"-r",str(self.fps),"-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-crf","23","-t",str(duration)] + META_STRIP + [str(out)]
            code,o,e = run_command(cmd, timeout=90)
            if code != 0:
                vf2 = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},setsar=1,fps={self.fps}"
                cmd2 = ["ffmpeg","-y","-threads","1","-loop","1","-t",str(duration),"-i",str(src),"-vf",vf2,"-r",str(self.fps),"-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-crf","23"] + META_STRIP + [str(out)]
                code,o,e = run_command(cmd2, timeout=90)
                if code != 0:
                    log_error(f"scene image gagal {src.name}: {e[:400]}")
                    raise RuntimeError(e[:600])
        elif is_video(src):
            vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},setsar=1,fps={self.fps}"
            sdur = get_media_duration(src)
            if sdur > 0 and sdur < duration:
                cmd = ["ffmpeg","-y","-threads","1","-stream_loop","2","-i",str(src),"-vf",vf,"-t",str(duration),"-r",str(self.fps),"-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-crf","23","-an"] + META_STRIP + [str(out)]
            else:
                cmd = ["ffmpeg","-y","-threads","1","-i",str(src),"-vf",vf,"-t",str(duration),"-r",str(self.fps),"-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-crf","23","-an"] + META_STRIP + [str(out)]
            code,o,e = run_command(cmd, timeout=90)
            if code != 0:
                log_error(f"scene video gagal {src.name}: {e[:400]}")
                raise RuntimeError(e[:600])
        else:
            raise ValueError(f"footage type unknown {src}")
        return out
    def _concat_xfade(self, clips: list[Path], out: Path):
        ensure_dir(out.parent)
        if len(clips) == 1:
            subprocess.run(["ffmpeg","-y","-i",str(clips[0]),"-c","copy"] + META_STRIP + [str(out)], capture_output=True)
            return out
        durs = []
        for c in clips:
            d = get_media_duration(c)
            durs.append(d if d > 0 else 3.0)
        inputs = []
        for c in clips:
            inputs += ["-i", str(c)]
        parts = []
        cur = "[0:v]"
        offset = durs[0] - self.trans_dur
        for i in range(1, len(clips)):
            nxt = f"[{i}:v]"
            nxt_label = f"[v{i}]" if i < len(clips)-1 else "[vout]"
            trans = "fade" if self.trans_type in ("fade","xfade") else "fade"
            parts.append(f"{cur}{nxt}xfade=transition={trans}:duration={self.trans_dur}:offset={offset}{nxt_label}")
            cur = nxt_label
            if i < len(clips)-1:
                offset += durs[i] - self.trans_dur
        fc = ";".join(parts)
        cmd = ["ffmpeg","-y","-threads","1"] + inputs + ["-filter_complex", fc, "-map","[vout]","-r",str(self.fps),"-pix_fmt","yuv420p","-c:v","libx264","-preset","ultrafast","-crf","23"] + META_STRIP + [str(out)]
        code,o,e = run_command(cmd, timeout=180)
        if code != 0:
            log_error(f"xfade gagal fallback concat: {e[:400]}")
            lst = out.parent / "concat_list.txt"
            lst.write_text("\n".join([f"file '{Path(c).resolve()}'" for c in clips]), encoding="utf-8")
            cmd2 = ["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy"] + META_STRIP + [str(out)]
            code,o,e = run_command(cmd2, timeout=60)
            if code != 0:
                raise RuntimeError(e[:600])
        return out
    def _mux_audio(self, video: Path, audios: list[Path], out: Path):
        video = Path(video)
        ensure_dir(out.parent)
        valid = [Path(a) for a in audios if a and Path(a).exists() and Path(a).suffix.lower() in (".mp3",".wav",".m4a",".aac",".ogg")]
        if not valid:
            log_error("Tidak ada audio valid, output silent")
            subprocess.run(["ffmpeg","-y","-i",str(video),"-c","copy"] + META_STRIP + [str(out)], capture_output=True)
            return out
        lst = out.parent / "audio_list.txt"
        lst.write_text("\n".join([f"file '{p.resolve()}'" for p in valid]), encoding="utf-8")
        concat_a = out.parent / "_concat_narr.aac"
        # concat + tail 0.8s silence biar TTS tidak kepotong di -shortest
        code,o,e = run_command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c:a","aac","-b:a","128k"] + META_STRIP + [str(concat_a)], timeout=60)
        if code != 0:
            code,o,e = run_command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c:a","libmp3lame","-q:a","2"] + META_STRIP + [str(concat_a)], timeout=60)
            if code != 0:
                raise RuntimeError(e[:600])
        # pad 0.8s silence tail
        padded_a = out.parent / "_concat_narr_padded.aac"
        code,o,e = run_command(["ffmpeg","-y","-i",str(concat_a),"-af","apad,atrim=start=0:duration="+str(get_media_duration(concat_a)+0.8),"-c:a","aac","-b:a","128k"] + META_STRIP + [str(padded_a)], timeout=60)
        if code == 0 and padded_a.exists() and padded_a.stat().st_size>0:
            concat_a = padded_a
        if self.bgm and Path(self.bgm).exists():
            # bgm mix — pad video jika lebih pendek dari audio
            vdur = get_media_duration(video)
            adur = get_media_duration(concat_a)
            if vdur + 0.05 < adur:
                pad = adur - vdur + 0.5
                cmd = ["ffmpeg","-y","-threads","1","-i",str(video),"-i",str(concat_a),"-stream_loop","-1","-i",str(self.bgm),"-filter_complex",f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.2f}[vpad];[2:a]volume={self.bgm_vol}[bgm];[1:a][bgm]amix=inputs=2:duration=longest:dropout_transition=2[aout]","-map","[vpad]","-map","[aout]","-c:v","libx264","-preset","ultrafast","-crf","23","-c:a","aac","-b:a","128k","-shortest"] + META_STRIP + [str(out)]
            else:
                cmd = ["ffmpeg","-y","-threads","1","-i",str(video),"-i",str(concat_a),"-stream_loop","-1","-i",str(self.bgm),"-filter_complex",f"[2:a]volume={self.bgm_vol}[bgm];[1:a][bgm]amix=inputs=2:duration=shortest:dropout_transition=2[aout]","-map","0:v","-map","[aout]","-c:v","copy","-c:a","aac","-b:a","128k","-shortest"] + META_STRIP + [str(out)]
            code,o,e = run_command(cmd, timeout=120)
            if code == 0:
                return out
            log_error(f"mix BGM gagal fallback tanpa BGM: {e[:300]}")
        # tanpa BGM — pad video jika audio lebih panjang (fix TTS kepotong karena xfade 0.5*6=3s)
        vdur = get_media_duration(video)
        adur = get_media_duration(concat_a)
        if vdur + 0.05 < adur:
            pad = adur - vdur + 0.5
            cmd = ["ffmpeg","-y","-threads","1","-i",str(video),"-i",str(concat_a),"-filter_complex",f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.2f}[vpad]","-map","[vpad]","-map","1:a","-c:v","libx264","-preset","ultrafast","-crf","23","-c:a","aac","-b:a","128k","-shortest"] + META_STRIP + [str(out)]
        else:
            cmd = ["ffmpeg","-y","-threads","1","-i",str(video),"-i",str(concat_a),"-map","0:v","-map","1:a","-c:v","copy","-c:a","aac","-b:a","128k","-shortest"] + META_STRIP + [str(out)]
        code,o,e = run_command(cmd, timeout=90)
        if code != 0:
            raise RuntimeError(e[:600])
        return out
    def render(self, footage_map: dict, audio_map: dict, dry_run=False) -> Path | None:
        output = Path(self.config.OUTPUT_DIR) / self.config.OUTPUT_FILENAME
        if dry_run:
            log_info("[DRY-RUN] compose skip FFmpeg")
            return None
        scenes_dir = Path(self.config.SCENES_DIR)
        ensure_dir(scenes_dir)
        ensure_dir(output.parent)
        clips = []
        audios_ordered = []
        for scene in self.config.SCENE_PROMPTS:
            sid = scene["id"]
            fp = footage_map.get(sid)
            if fp is None or not Path(fp).exists():
                for ext in (".mp4",".jpg",".jpeg",".png",".webp"):
                    cand = Path(self.config.FOOTAGE_DIR) / f"{sid}{ext}"
                    if cand.exists():
                        fp = cand
                        break
            if fp is None or not Path(fp).exists():
                log_error(f"Footage {sid} hilang skip scene")
                continue
            am = audio_map.get(sid)
            dur = 3.5
            audio_path = None
            if isinstance(am, dict):
                dur = float(am.get("duration", 0) or 0)
                audio_path = am.get("audio_path")
            elif isinstance(am, (str, Path)) and am:
                audio_path = Path(am)
                dur = get_media_duration(audio_path)
            if dur <= 0:
                txtp = Path(self.config.AUDIO_DIR) / f"{sid}.txt"
                if txtp.exists():
                    dur = max(2.0, min(8.0, len(txtp.read_text(encoding="utf-8")) * 0.06))
                else:
                    dur = 3.5
            if audio_path is None or not Path(audio_path).exists() or Path(audio_path).suffix.lower() == ".txt":
                silent = scenes_dir / f"{sid}_silent.aac"
                run_command(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo","-t",str(dur),"-c:a","aac","-b:a","128k"] + META_STRIP + [str(silent)], timeout=30)
                audios_ordered.append(silent)
            else:
                audios_ordered.append(Path(audio_path))
            out_clip = scenes_dir / f"{sid}.mp4"
            try:
                self._scene_video(Path(fp), dur, out_clip)
                clips.append(out_clip)
            except Exception as e:
                log_error(f"Gagal clip {sid}: {e}")
                continue
        if not clips:
            log_error("Tidak ada clip berhasil")
            return None
        tmp_v = Path(self.config.OUTPUT_DIR) / "_temp_concat.mp4"
        try:
            if self.trans_type in ("none","cut") or self.trans_dur <= 0:
                lst = tmp_v.parent / "concat_list.txt"
                lst.write_text("\n".join([f"file '{c.resolve()}'" for c in clips]), encoding="utf-8")
                run_command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy"] + META_STRIP + [str(tmp_v)], timeout=60)
            else:
                self._concat_xfade(clips, tmp_v)
        except Exception as e:
            log_error(f"Concat gagal {e}")
            return None
        try:
            self._mux_audio(tmp_v, audios_ordered, output)
        except Exception as e:
            log_error(f"Mux audio gagal {e}")
            return None
        if output.exists():
            log_info(f"FINAL VIDEO: {output} ({output.stat().st_size/1_000_000:.2f} MB)")
            total = sum([get_media_duration(a) if Path(a).exists() else 0 for a in audios_ordered])
            if total == 0:
                total = sum([3.5 for _ in clips])
            est = total - (len(clips)-1)*self.trans_dur if len(clips)>1 else total
            log_info(f"Estimasi durasi: {est:.1f}s (sum {total:.1f}s - trans {(len(clips)-1)*self.trans_dur:.1f}s)")
        return output
