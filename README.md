# Video Downloader

A desktop app around yt-dlp. Paste a link, preview the title and thumbnail, pick a quality, and add it to a queue. Downloads run one after another, and finished ones are kept in a history list.

## Features

- Preview with thumbnail, title, uploader and duration before downloading
- Quality: Best, 1080p, 720p, or Audio (MP3)
- Download queue with live progress, speed, ETA and per-item cancel
- History with Open file and Show in folder buttons
- Remembers your last folder and quality

## Run from source

Needs Python 3.10 or newer with tkinter (included in the python.org installers for Windows and macOS; on Debian/Ubuntu run `sudo apt install python3-tk`).

```
pip install -r requirements.txt
python main.py
```

## Two helper tools you should install

- **ffmpeg**: merges video and audio for 1080p/Best and converts to MP3. Without it the app falls back to single-file formats and MP3 is unavailable. Install it so it is on your PATH, or put `ffmpeg.exe` (Windows) or `ffmpeg` next to `main.py` or next to the built app.
- **A JavaScript runtime (Deno recommended, or Node.js)**: current yt-dlp needs one to read YouTube. Without it, YouTube may return fewer formats or fail. The app shows a warning at the bottom of the window if either tool is missing.

## Build a standalone app

```
pip install pyinstaller
python build.py
```

The result is in `dist/`: a single `VideoDownloader.exe` on Windows, a `VideoDownloader` binary on Linux, and a `.app` bundle on macOS. Build on the operating system you want to ship for. If `ffmpeg.exe` (or `ffmpeg`) sits next to `build.py` when you build, it is bundled inside the app. An optional `icon.ico` (Windows) or `icon.icns` (macOS) next to `build.py` is used as the app icon.

## Keeping it working

Sites change often, so yt-dlp needs regular updates. When downloads start failing, run `pip install -U "yt-dlp[default]"` and rebuild.

## Files

- `main.py`: the window
- `downloader.py`: yt-dlp wrapper (info, download, progress, cancel)
- `storage.py`: history and settings saved as JSON in your user data folder (`%APPDATA%\VideoDownloader` on Windows, `~/Library/Application Support/VideoDownloader` on macOS, `~/.local/share/VideoDownloader` on Linux)
- `build.py`: PyInstaller build script

## Note

Only download videos you own or have permission to save. Downloading from some sites, YouTube included, can go against their terms of service.
