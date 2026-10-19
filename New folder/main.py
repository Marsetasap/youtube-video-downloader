import io
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageOps

import downloader
from storage import History, Settings

THUMB_SIZE = (224, 126)
MUTED = ("gray35", "gray65")
PANEL = ("gray88", "gray17")


def shorten(text, limit=90):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_path(path):
    if sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def placeholder_image():
    image = Image.new("RGB", (THUMB_SIZE[0] * 2, THUMB_SIZE[1] * 2), (55, 55, 60))
    return ctk.CTkImage(light_image=image, dark_image=image, size=THUMB_SIZE)


class DownloadItem:
    def __init__(self, url, title, quality, output_dir):
        self.id = uuid.uuid4().hex
        self.url = url
        self.title = title
        self.quality = quality
        self.output_dir = output_dir
        self.cancel_event = threading.Event()
        self.state = "queued"


class QueueRow(ctk.CTkFrame):
    def __init__(self, master, item, on_cancel, on_remove):
        super().__init__(master, corner_radius=10, fg_color=PANEL)
        self.item = item
        self.on_cancel = on_cancel
        self.on_remove = on_remove
        self.finished = False
        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self, text=shorten(item.title), anchor="w", font=ctk.CTkFont(weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))

        self.meta_label = ctk.CTkLabel(self, text=item.quality, anchor="w", text_color=MUTED)
        self.meta_label.grid(row=1, column=0, sticky="ew", padx=14)

        self.button = ctk.CTkButton(self, text="Cancel", width=84, command=self.handle_button)
        self.button.grid(row=0, column=1, rowspan=2, padx=14, pady=(10, 0))

        self.bar = ctk.CTkProgressBar(self)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 4))

        self.status_label = ctk.CTkLabel(self, text="Queued", anchor="w", text_color=MUTED)
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 10))

    def handle_button(self):
        if self.finished:
            self.on_remove(self)
        else:
            self.button.configure(state="disabled", text="Cancelling")
            self.on_cancel(self.item)

    def set_title(self, title):
        self.title_label.configure(text=shorten(title))

    def set_status(self, text):
        self.status_label.configure(text=text)

    def set_progress(self, fraction, text):
        self.bar.set(fraction)
        self.status_label.configure(text=text)

    def set_finished(self, text, success):
        self.finished = True
        self.bar.set(1.0 if success else 0.0)
        self.status_label.configure(text=text)
        self.button.configure(state="normal", text="Remove")


class HistoryRow(ctk.CTkFrame):
    def __init__(self, master, entry, on_open, on_reveal, on_remove):
        super().__init__(master, corner_radius=10, fg_color=PANEL)
        self.grid_columnconfigure(0, weight=1)
        exists = os.path.exists(entry["path"])

        title = ctk.CTkLabel(self, text=shorten(entry["title"]), anchor="w", font=ctk.CTkFont(weight="bold"))
        title.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))

        note = "" if exists else "  •  file not found"
        meta = ctk.CTkLabel(
            self, text=f'{entry["time"]}  •  {entry["quality"]}{note}', anchor="w", text_color=MUTED
        )
        meta.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=2, padx=10)
        open_button = ctk.CTkButton(
            actions, text="Open", width=64, command=lambda: on_open(entry),
            state="normal" if exists else "disabled",
        )
        open_button.pack(side="left", padx=3)
        folder_button = ctk.CTkButton(
            actions, text="Folder", width=64, command=lambda: on_reveal(entry),
            state="normal" if exists else "disabled",
        )
        folder_button.pack(side="left", padx=3)
        remove_button = ctk.CTkButton(
            actions, text="Remove", width=72, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=lambda: on_remove(entry),
        )
        remove_button.pack(side="left", padx=3)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Video Downloader")
        self.geometry("940x740")
        self.minsize(800, 620)

        self.settings = Settings()
        self.history = History()
        self.events = queue.Queue()
        self.jobs = queue.Queue()
        self.rows = {}
        self.items = {}
        self.fetch_token = 0
        self.preview = None
        self.thumb_image = placeholder_image()
        self.ffmpeg_found = downloader.find_ffmpeg() is not None
        self.js_found = downloader.find_js_runtime() is not None

        self.build_ui()
        self.refresh_history()
        self.update_empty_states()

        threading.Thread(target=self.worker_loop, daemon=True).start()
        self.after(100, self.pump_events)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        bar.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(bar, height=40, placeholder_text="Paste a video link here")
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda event: self.start_preview())
        ctk.CTkButton(bar, text="Paste", width=72, height=40, command=self.paste_url).grid(
            row=0, column=1, padx=(8, 0)
        )
        self.preview_button = ctk.CTkButton(bar, text="Preview", width=88, height=40, command=self.start_preview)
        self.preview_button.grid(row=0, column=2, padx=(8, 0))

        card = ctk.CTkFrame(self, corner_radius=12, fg_color=PANEL)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        card.grid_columnconfigure(1, weight=1)
        self.thumb_label = ctk.CTkLabel(card, text="", image=self.thumb_image, width=THUMB_SIZE[0], height=THUMB_SIZE[1])
        self.thumb_label.grid(row=0, column=0, rowspan=3, padx=14, pady=14)
        self.preview_title = ctk.CTkLabel(
            card, text="No video selected", anchor="w", justify="left",
            font=ctk.CTkFont(size=16, weight="bold"), wraplength=560,
        )
        self.preview_title.grid(row=0, column=1, sticky="sw", padx=(0, 14), pady=(14, 0))
        self.preview_meta = ctk.CTkLabel(card, text="Paste a link and press Preview", anchor="w", text_color=MUTED)
        self.preview_meta.grid(row=1, column=1, sticky="nw", padx=(0, 14))

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        options.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(options, text="Quality").grid(row=0, column=0, padx=(0, 8))
        self.quality_menu = ctk.CTkOptionMenu(options, values=downloader.QUALITIES, width=140, command=self.on_option_change)
        saved_quality = self.settings.get("quality")
        self.quality_menu.set(saved_quality if saved_quality in downloader.QUALITIES else "Best")
        self.quality_menu.grid(row=0, column=1, padx=(0, 16))
        self.folder_var = tk.StringVar(value=self.settings.get("output_dir"))
        self.folder_entry = ctk.CTkEntry(options, textvariable=self.folder_var)
        self.folder_entry.grid(row=0, column=2, sticky="ew")
        ctk.CTkButton(options, text="Browse", width=80, command=self.choose_folder).grid(row=0, column=3, padx=(8, 0))
        self.add_button = ctk.CTkButton(options, text="Add to queue", width=120, command=self.add_to_queue)
        self.add_button.grid(row=0, column=4, padx=(16, 0))

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 6))
        queue_tab = self.tabs.add("Queue")
        history_tab = self.tabs.add("History")
        for tab in (queue_tab, history_tab):
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(1, weight=1)

        queue_tools = ctk.CTkFrame(queue_tab, fg_color="transparent")
        queue_tools.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            queue_tools, text="Clear finished", width=120, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.clear_finished,
        ).pack(side="right")
        self.queue_frame = ctk.CTkScrollableFrame(queue_tab, fg_color="transparent")
        self.queue_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.queue_empty = ctk.CTkLabel(self.queue_frame, text="Nothing in the queue yet", text_color=MUTED)

        history_tools = ctk.CTkFrame(history_tab, fg_color="transparent")
        history_tools.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            history_tools, text="Clear history", width=120, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), command=self.clear_history,
        ).pack(side="right")
        self.history_frame = ctk.CTkScrollableFrame(history_tab, fg_color="transparent")
        self.history_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.history_empty = ctk.CTkLabel(self.history_frame, text="No downloads yet", text_color=MUTED)

        warnings = []
        if not self.ffmpeg_found:
            warnings.append("ffmpeg not found: downloads use single-file formats and MP3 conversion is off.")
        if not self.js_found:
            warnings.append("No JavaScript runtime (Deno or Node.js) found: YouTube may return fewer formats or fail.")
        footer_text = "  ".join(warnings) if warnings else "Only download videos you have the right to save."
        self.footer = ctk.CTkLabel(
            self, text=footer_text, anchor="w", justify="left", wraplength=880,
            text_color=("#a15c00", "#e0a040") if warnings else MUTED,
        )
        self.footer.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 12))

    def valid_url(self, url):
        return url.lower().startswith(("http://", "https://"))

    def paste_url(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        if text:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, text)
            self.start_preview()

    def choose_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get() or None)
        if chosen:
            self.folder_var.set(chosen)
            self.save_settings()

    def on_option_change(self, value=None):
        self.save_settings()

    def save_settings(self):
        self.settings.set("quality", self.quality_menu.get())
        self.settings.set("output_dir", self.folder_var.get().strip())
        try:
            self.settings.save()
        except OSError:
            pass

    def set_preview_loading(self):
        self.preview = None
        self.preview_title.configure(text="Fetching video details…")
        self.preview_meta.configure(text="")
        self.preview_button.configure(state="disabled")

    def clear_preview(self):
        self.fetch_token += 1
        self.preview = None
        self.thumb_image = placeholder_image()
        self.thumb_label.configure(image=self.thumb_image)
        self.preview_title.configure(text="No video selected")
        self.preview_meta.configure(text="Paste a link and press Preview")
        self.preview_button.configure(state="normal")

    def start_preview(self):
        url = self.url_entry.get().strip()
        if not self.valid_url(url):
            messagebox.showwarning("Invalid link", "Enter a link that starts with http:// or https://")
            return
        self.fetch_token += 1
        token = self.fetch_token
        self.set_preview_loading()
        threading.Thread(target=self.preview_worker, args=(url, token), daemon=True).start()

    def preview_worker(self, url, token):
        try:
            info = downloader.fetch_info(url)
        except Exception as error:
            self.events.put(("preview_failed", token, downloader.clean_error(error)))
            return
        try:
            thumb_bytes = downloader.fetch_thumbnail(info["thumbnail"])
        except Exception:
            thumb_bytes = None
        self.events.put(("preview_ready", token, url, info, thumb_bytes))

    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if not self.valid_url(url):
            messagebox.showwarning("Invalid link", "Enter a link that starts with http:// or https://")
            return
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No folder", "Choose a folder to save the video in.")
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as error:
            messagebox.showerror("Folder problem", f"Cannot use this folder:\n{error}")
            return

        title = url
        if self.preview and self.preview["url"] == url:
            title = self.preview["info"]["title"]
        item = DownloadItem(url, title, self.quality_menu.get(), folder)
        row = QueueRow(self.queue_frame, item, self.cancel_item, self.remove_row)
        row.pack(fill="x", pady=4)
        self.rows[item.id] = row
        self.items[item.id] = item
        self.jobs.put(item)

        self.url_entry.delete(0, "end")
        self.clear_preview()
        self.tabs.set("Queue")
        self.update_empty_states()
        self.save_settings()

    def cancel_item(self, item):
        item.cancel_event.set()
        if item.state == "queued":
            item.state = "cancelled"
            row = self.rows.get(item.id)
            if row:
                row.set_finished("Cancelled", False)

    def remove_row(self, row):
        row.destroy()
        self.rows.pop(row.item.id, None)
        self.items.pop(row.item.id, None)
        self.update_empty_states()

    def clear_finished(self):
        for row in [row for row in self.rows.values() if row.finished]:
            self.remove_row(row)

    def update_empty_states(self):
        if self.rows:
            self.queue_empty.pack_forget()
        elif not self.queue_empty.winfo_ismapped():
            self.queue_empty.pack(pady=40)
        if self.history.items:
            self.history_empty.pack_forget()
        elif not self.history_empty.winfo_ismapped():
            self.history_empty.pack(pady=40)

    def refresh_history(self):
        for child in self.history_frame.winfo_children():
            if child is not self.history_empty:
                child.destroy()
        for entry in self.history.items[:150]:
            row = HistoryRow(
                self.history_frame, entry, self.open_entry, self.reveal_entry, self.remove_entry
            )
            row.pack(fill="x", pady=4)
        self.update_empty_states()

    def open_entry(self, entry):
        try:
            open_path(entry["path"])
        except OSError as error:
            messagebox.showerror("Cannot open file", str(error))

    def reveal_entry(self, entry):
        try:
            reveal_path(entry["path"])
        except OSError as error:
            messagebox.showerror("Cannot open folder", str(error))

    def remove_entry(self, entry):
        self.history.remove(entry["id"])
        self.refresh_history()

    def clear_history(self):
        if not self.history.items:
            return
        if messagebox.askyesno("Clear history", "Remove all entries from the history list?\nYour video files are not deleted."):
            self.history.clear()
            self.refresh_history()

    def worker_loop(self):
        while True:
            item = self.jobs.get()
            if item.cancel_event.is_set():
                self.events.put(("cancelled", item))
                continue
            self.events.put(("status", item, "Starting"))
            try:
                result = downloader.download(
                    item.url,
                    item.output_dir,
                    item.quality,
                    item.cancel_event,
                    lambda fraction, speed, eta, item=item: self.events.put(("progress", item, fraction, speed, eta)),
                    lambda text, item=item: self.events.put(("status", item, text)),
                )
            except downloader.CancelledByUser:
                self.events.put(("cancelled", item))
            except Exception as error:
                self.events.put(("failed", item, downloader.clean_error(error)))
            else:
                self.events.put(("done", item, result))

    def pump_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                handler = getattr(self, f"event_{event[0]}")
                handler(*event[1:])
        except queue.Empty:
            pass
        self.after(100, self.pump_events)

    def event_preview_ready(self, token, url, info, thumb_bytes):
        if token != self.fetch_token:
            return
        self.preview = {"url": url, "info": info}
        self.preview_button.configure(state="normal")
        self.preview_title.configure(text=shorten(info["title"], 120))
        parts = [part for part in (info["uploader"], downloader.format_duration(info["duration"]) if info["duration"] else "") if part]
        meta = "  •  ".join(parts)
        if info["is_live"]:
            meta = (meta + "  •  " if meta else "") + "Live stream (not supported)"
        self.preview_meta.configure(text=meta or "Ready to download")
        if thumb_bytes:
            try:
                image = Image.open(io.BytesIO(thumb_bytes)).convert("RGB")
                image = ImageOps.fit(image, (THUMB_SIZE[0] * 2, THUMB_SIZE[1] * 2))
                self.thumb_image = ctk.CTkImage(light_image=image, dark_image=image, size=THUMB_SIZE)
                self.thumb_label.configure(image=self.thumb_image)
            except Exception:
                pass

    def event_preview_failed(self, token, message):
        if token != self.fetch_token:
            return
        self.preview = None
        self.preview_button.configure(state="normal")
        self.preview_title.configure(text="Could not load this video")
        self.preview_meta.configure(text=shorten(message, 160))

    def event_status(self, item, text):
        row = self.rows.get(item.id)
        if row is None or row.finished:
            return
        if item.state == "queued":
            item.state = "running"
        row.set_status(text)

    def event_progress(self, item, fraction, speed, eta):
        row = self.rows.get(item.id)
        if row is None or row.finished:
            return
        parts = [f"Downloading {fraction * 100:.1f}%", downloader.format_speed(speed), downloader.format_eta(eta)]
        row.set_progress(fraction, "  •  ".join(part for part in parts if part))

    def event_done(self, item, result):
        item.state = "done"
        self.history.add(result["title"], item.url, result["path"], item.quality)
        self.refresh_history()
        row = self.rows.get(item.id)
        if row is not None:
            row.set_title(result["title"])
            row.set_finished(f'Saved to {result["path"]}', True)

    def event_failed(self, item, message):
        item.state = "failed"
        row = self.rows.get(item.id)
        if row is not None:
            row.set_finished(f"Failed: {shorten(message, 200)}", False)

    def event_cancelled(self, item):
        item.state = "cancelled"
        row = self.rows.get(item.id)
        if row is not None and not row.finished:
            row.set_finished("Cancelled", False)

    def on_close(self):
        for item in self.items.values():
            item.cancel_event.set()
        self.save_settings()
        self.destroy()


def main():
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
