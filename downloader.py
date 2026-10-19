import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import yt_dlp

QUALITIES = ["Best", "1080p", "720p", "Audio (MP3)"]
AUDIO_QUALITY = "Audio (MP3)"
HEIGHT_LIMITS = {"1080p": 1080, "720p": 720}
JS_RUNTIMES = ["deno", "node", "bun", "quickjs"]
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


class CancelledByUser(Exception):
    pass


class SilentLogger:
    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_ffmpeg():
    folders = [app_dir()]
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        folders.append(Path(bundled))
    for folder in folders:
        for name in ("ffmpeg.exe", "ffmpeg"):
            if (folder / name).is_file():
                return str(folder)
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    return None


def find_js_runtime():
    for name in JS_RUNTIMES:
        if shutil.which(name):
            return name
    return None


def build_format(quality, has_ffmpeg):
    if quality == AUDIO_QUALITY:
        return "bestaudio[ext=m4a]/bestaudio/best"
    limit = HEIGHT_LIMITS.get(quality)
    cap = f"[height<={limit}]" if limit else ""
    if has_ffmpeg:
        return (
            f"bestvideo{cap}[ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo{cap}+bestaudio"
            f"/best{cap}/best"
        )
    return f"best{cap}[ext=mp4]/best{cap}/best"


def base_options():
    return {
        "logger": SilentLogger(),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "windowsfilenames": True,
        "js_runtimes": {name: {"path": None} for name in JS_RUNTIMES},
    }


def clean_error(error):
    text = ANSI_PATTERN.sub("", str(error)).strip()
    if text.startswith("ERROR:"):
        text = text[len("ERROR:"):].strip()
    return text or "Unknown error"


def fetch_info(url):
    options = base_options()
    options["skip_download"] = True
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("No video information found for this link")
    if info.get("_type") == "playlist":
        raise RuntimeError("This link is a playlist. Open a single video and paste its link")
    return {
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration") or 0,
        "uploader": info.get("uploader") or info.get("channel") or "",
        "thumbnail": info.get("thumbnail") or "",
        "is_live": bool(info.get("is_live")),
    }


def fetch_thumbnail(url):
    if not url:
        return None
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_speed(bytes_per_second):
    if not bytes_per_second:
        return ""
    return f"{bytes_per_second / 1024 / 1024:.2f} MB/s"


def format_eta(seconds):
    if seconds is None:
        return ""
    return f"ETA {format_duration(seconds)}"


def download(url, output_dir, quality, cancel_event, on_progress, on_status):
    if cancel_event.is_set():
        raise CancelledByUser()

    ffmpeg_dir = find_ffmpeg()
    last_report = {"time": 0.0}

    def progress_hook(data):
        if cancel_event.is_set():
            raise CancelledByUser()
        if data["status"] == "downloading":
            now = time.monotonic()
            if now - last_report["time"] < 0.15:
                return
            last_report["time"] = now
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            fraction = min(done / total, 1.0) if total else 0.0
            on_progress(fraction, data.get("speed"), data.get("eta"))
        elif data["status"] == "finished":
            on_status("Processing")

    def postprocessor_hook(data):
        if data["status"] == "started":
            names = {"Merger": "Merging video and audio", "ExtractAudio": "Converting to MP3"}
            on_status(names.get(data.get("postprocessor"), "Processing"))

    options = base_options()
    options.update({
        "format": build_format(quality, ffmpeg_dir is not None),
        "outtmpl": os.path.join(output_dir, "%(title).150s.%(ext)s"),
        "merge_output_format": "mp4",
        "retries": 5,
        "fragment_retries": 5,
        "match_filter": yt_dlp.utils.match_filter_func("!is_live"),
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
    })
    if ffmpeg_dir:
        options["ffmpeg_location"] = ffmpeg_dir
        if quality == AUDIO_QUALITY:
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except CancelledByUser:
        raise
    except yt_dlp.utils.DownloadError as error:
        if cancel_event.is_set():
            raise CancelledByUser()
        raise RuntimeError(clean_error(error))

    downloads = (info or {}).get("requested_downloads") or []
    path = downloads[0].get("filepath") if downloads else None
    if not path:
        raise RuntimeError("Nothing was downloaded. Live streams are not supported")
    if quality == AUDIO_QUALITY and ffmpeg_dir and not path.lower().endswith(".mp3"):
        path = os.path.splitext(path)[0] + ".mp3"
    return {"path": path, "title": info.get("title") or Path(path).stem}
