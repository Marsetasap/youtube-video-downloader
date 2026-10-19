import json
import os
import sys
import time
import uuid
from pathlib import Path

APP_NAME = "VideoDownloader"
HISTORY_LIMIT = 500


def data_dir():
    override = os.environ.get("VIDEO_DOWNLOADER_HOME")
    if override:
        folder = Path(override)
    else:
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA") or Path.home())
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class JsonStore:
    def __init__(self, path, default):
        self.path = Path(path)
        self.default = default

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return self.default
        if type(data) is not type(self.default):
            return self.default
        return data

    def save(self, data):
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp, self.path)


class History:
    def __init__(self, folder=None):
        self.store = JsonStore(Path(folder or data_dir()) / "history.json", [])
        self.items = self.store.load()

    def add(self, title, url, path, quality):
        entry = {
            "id": uuid.uuid4().hex,
            "title": title,
            "url": url,
            "path": path,
            "quality": quality,
            "time": time.strftime("%Y-%m-%d %H:%M"),
        }
        self.items.insert(0, entry)
        del self.items[HISTORY_LIMIT:]
        self.store.save(self.items)
        return entry

    def remove(self, entry_id):
        self.items = [entry for entry in self.items if entry["id"] != entry_id]
        self.store.save(self.items)

    def clear(self):
        self.items = []
        self.store.save(self.items)


class Settings:
    def __init__(self, folder=None):
        self.defaults = {
            "output_dir": str(Path.home() / "Downloads"),
            "quality": "Best",
        }
        self.store = JsonStore(Path(folder or data_dir()) / "settings.json", {})
        self.values = {**self.defaults, **self.store.load()}

    def get(self, key):
        return self.values.get(key, self.defaults.get(key))

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.store.save(self.values)
