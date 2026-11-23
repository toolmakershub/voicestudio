"""
Offline Voiceover Studio — a desktop text-to-audio generator that runs fully offline.

Run:   python app.py
Needs: pip install piper-tts lameenc
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tts_engine as eng

APP_NAME = "ToolMakersHub Voice Studio Lite"
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
VOICES_DIR = APP_DIR / "voices"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_VOICE = "en_US-lessac-medium"

SAMPLE_TEXT = """Welcome to the channel! In today's video, we're building a complete login screen in just ten minutes.

First, let's open the project and create a new screen. [pause 1] Make sure you're on the latest version before you start.

If this helped you, hit subscribe, and I'll see you in the next one."""

TIP = ("Blank line = new paragraph · [pause 1.5] = exact pause.\n"
       "Select text, then Preview to hear just that part.")


class Player:
    """Plays a WAV file with whatever the OS provides — no extra packages needed."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None

    def play(self, path: Path):
        self.stop()
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        for cmd in (["afplay"], ["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
            try:
                self.proc = subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
        raise RuntimeError("No audio player found (tried afplay, paplay, aplay, ffplay).")

    def stop(self):
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(None, 0)
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1120x800")
        self.minsize(940, 740)

        self.vm = eng.VoiceManager(VOICES_DIR)
        self.player = Player()
        self.events: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.busy = False
        self.preview_path = Path(tempfile.gettempdir()) / "voiceover_preview.wav"

        saved = self._load_settings()
        self.v_voice = tk.StringVar(value=saved.get("voice", DEFAULT_VOICE))
        self.v_speaker = tk.IntVar(value=saved.get("speaker", 0))
        self.v_speed = tk.DoubleVar(value=saved.get("speed", 1.0))
        self.v_expr = tk.DoubleVar(value=saved.get("expressiveness", 0.667))
        self.v_volume = tk.DoubleVar(value=saved.get("volume", 1.0))
        self.v_spause = tk.DoubleVar(value=saved.get("sentence_pause", 0.35))
        self.v_ppause = tk.DoubleVar(value=saved.get("paragraph_pause", 0.9))
        self.v_format = tk.StringVar(value=saved.get("format", "mp3"))
        self.v_split = tk.BooleanVar(value=saved.get("split", False))
        self.v_srt = tk.BooleanVar(value=saved.get("subtitles", True))
        self.v_status = tk.StringVar(value="Ready — everything runs on this computer.")
        self.v_stats = tk.StringVar()
        self.v_voice_info = tk.StringVar()

        self._style()
        self._build()
        self.text.insert("1.0", saved.get("text", SAMPLE_TEXT))
        self._refresh_voices()
        self._update_stats()
        self.after(100, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _style(self):
        s = ttk.Style(self)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        bg = "#f4f5f7"
        self.configure(bg=bg)
        s.configure(".", background=bg, font=("Segoe UI", 10))
        s.configure("Side.TFrame", background="#ffffff")
        s.configure("Side.TLabel", background="#ffffff")
        s.configure("Side.TCheckbutton", background="#ffffff")
        s.configure("Side.TRadiobutton", background="#ffffff")
        s.configure("Head.TLabel", background="#ffffff", font=("Segoe UI", 10, "bold"), foreground="#1f2937")
        s.configure("Muted.TLabel", background="#ffffff", foreground="#6b7280", font=("Segoe UI", 9))
        s.configure("Bar.TLabel", foreground="#4b5563")
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), foreground="#ffffff",
                    background="#2563eb", padding=(14, 6))
        s.map("Accent.TButton", background=[("disabled", "#93c5fd"), ("active", "#1d4ed8")])
        s.configure("TButton", padding=(10, 5))

    def _build(self):
        # Top toolbar
        top = ttk.Frame(self, padding=(12, 10, 12, 6))
        top.pack(fill="x")
        ttk.Button(top, text="Open text…", command=self._open_text).pack(side="left")
        ttk.Button(top, text="Save text…", command=self._save_text).pack(side="left", padx=6)
        ttk.Button(top, text="Clear", command=lambda: (self.text.delete("1.0", "end"), self._update_stats())).pack(side="left")
        ttk.Label(top, textvariable=self.v_stats, style="Bar.TLabel").pack(side="right")

        body = ttk.Frame(self, padding=(12, 0, 12, 0))
        body.pack(fill="both", expand=True)

        # Script editor
        edit = ttk.Frame(body)
        edit.pack(side="left", fill="both", expand=True)
        self.text = tk.Text(edit, wrap="word", undo=True, font=("Segoe UI", 12), padx=14, pady=12,
                            relief="flat", highlightthickness=1, highlightbackground="#d1d5db",
                            highlightcolor="#2563eb", spacing2=3, spacing3=6)
        sb = ttk.Scrollbar(edit, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.text.bind("<<Modified>>", self._on_text_modified)

        # Settings sidebar
        side = ttk.Frame(body, style="Side.TFrame", padding=14, width=330)
        side.pack(side="right", fill="y", padx=(12, 0), before=edit)
        side.pack_propagate(False)

        ttk.Label(side, text="Voice", style="Head.TLabel").pack(anchor="w")
        self.cb_voice = ttk.Combobox(side, textvariable=self.v_voice)
        self.cb_voice.pack(fill="x", pady=(4, 2))
        self.cb_voice.bind("<<ComboboxSelected>>", lambda e: self._on_voice_change())
        self.cb_voice.bind("<FocusOut>", lambda e: self._on_voice_change())
        self.cb_voice.bind("<Return>", lambda e: self._on_voice_change())
        ttk.Label(side, textvariable=self.v_voice_info, style="Muted.TLabel", wraplength=295,
                  justify="left").pack(anchor="w")
        row = ttk.Frame(side, style="Side.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.btn_download = ttk.Button(row, text="Download voice", command=self._download_voice)
        self.btn_download.pack(side="left")
        ttk.Button(row, text="Import .onnx…", command=self._import_voice).pack(side="left", padx=6)
        row = ttk.Frame(side, style="Side.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Speaker #", style="Side.TLabel").pack(side="left")
        self.sp_speaker = ttk.Spinbox(row, from_=0, to=0, width=6, textvariable=self.v_speaker)
        self.sp_speaker.pack(side="left", padx=6)

        ttk.Separator(side).pack(fill="x", pady=12)
        ttk.Label(side, text="Delivery", style="Head.TLabel").pack(anchor="w")
        self._slider(side, "Speed", self.v_speed, 0.5, 2.0, "{:.2f}×")
        self._slider(side, "Expressiveness", self.v_expr, 0.0, 1.2, "{:.2f}")
        self._slider(side, "Volume", self.v_volume, 0.3, 2.0, "{:.2f}×")
        self._slider(side, "Pause between sentences", self.v_spause, 0.0, 2.0, "{:.2f} s")
        self._slider(side, "Pause between paragraphs", self.v_ppause, 0.0, 4.0, "{:.2f} s")

        ttk.Separator(side).pack(fill="x", pady=12)
        ttk.Label(side, text="Output", style="Head.TLabel").pack(anchor="w")
        row = ttk.Frame(side, style="Side.TFrame")
        row.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(row, text="MP3", value="mp3", variable=self.v_format, style="Side.TRadiobutton").pack(side="left")
        ttk.Radiobutton(row, text="WAV (lossless)", value="wav", variable=self.v_format, style="Side.TRadiobutton").pack(side="left", padx=10)
        ttk.Checkbutton(side, text="One file per paragraph (scenes)", variable=self.v_split,
                        style="Side.TCheckbutton").pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(side, text="Subtitles file (.srt) for video editors", variable=self.v_srt,
                        style="Side.TCheckbutton").pack(anchor="w", pady=(2, 0))
        ttk.Label(side, text=TIP, style="Muted.TLabel", wraplength=295, justify="left").pack(anchor="w", side="bottom")

        # Bottom bar
        bar = ttk.Frame(self, padding=12)
        bar.pack(fill="x", side="bottom", before=body)
        self.btn_preview = ttk.Button(bar, text="▶  Preview", command=self._preview)
        self.btn_preview.pack(side="left")
        ttk.Button(bar, text="■  Stop", command=self._stop).pack(side="left", padx=6)
        self.btn_generate = ttk.Button(bar, text="Generate & Save…", style="Accent.TButton", command=self._generate)
        self.btn_generate.pack(side="right")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=220)
        self.progress.pack(side="right", padx=12)
        ttk.Label(bar, textvariable=self.v_status, style="Bar.TLabel").pack(side="left", padx=12)

    def _slider(self, parent, label, var, lo, hi, fmt):
        row = ttk.Frame(parent, style="Side.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=label, style="Side.TLabel").pack(side="left")
        val = ttk.Label(row, style="Muted.TLabel")
        val.pack(side="right")
        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var,
                          command=lambda _=None: (val.config(text=fmt.format(var.get())), self._update_stats()))
        scale.pack(fill="x")
        val.config(text=fmt.format(var.get()))

    # ------------------------------------------------------------- voices
    def _refresh_voices(self):
        installed = self.vm.installed()
        names = installed + [n for n in eng.VOICE_CATALOG if n not in installed]
        self.cb_voice["values"] = names
        self._on_voice_change()

    def _on_voice_change(self):
        name = self.v_voice.get().strip()
        desc = eng.VOICE_CATALOG.get(name, "Custom Piper voice")
        if self.vm.is_installed(name):
            self.v_voice_info.set(f"✓ Installed · {desc}")
            self.btn_download.state(["disabled"])
            n = self.vm.speaker_count(name)
            self.sp_speaker.configure(to=max(0, n - 1))
            self.sp_speaker.state(["!disabled"] if n > 1 else ["disabled"])
            if n <= 1:
                self.v_speaker.set(0)
        else:
            self.v_voice_info.set(f"Not downloaded yet · {desc}\nOne-time download (~60–110 MB), then works offline.")
            if not self.busy:
                self.btn_download.state(["!disabled"])
            self.sp_speaker.state(["disabled"])

    def _download_voice(self):
        name = self.v_voice.get().strip()
        if not name:
            return

        def work():
            self._emit("status", f"Downloading {name}… (one time only)")
            self.vm.download(name)
            self._emit("downloaded", name)

        self._run(work, indeterminate=True)

    def _import_voice(self):
        path = filedialog.askopenfilename(title="Choose a Piper voice model",
                                          filetypes=[("Piper voice", "*.onnx")])
        if not path:
            return
        try:
            name = self.vm.import_model(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        self.v_voice.set(name)
        self._refresh_voices()
        self.v_status.set(f"Imported voice {name}.")

    # ------------------------------------------------------------ actions
    def _settings(self) -> eng.RenderSettings:
        name = self.v_voice.get().strip()
        multi = self.vm.speaker_count(name) > 1
        return eng.RenderSettings(
            speed=round(self.v_speed.get(), 2),
            expressiveness=round(self.v_expr.get(), 3),
            volume=round(self.v_volume.get(), 2),
            speaker_id=int(self.v_speaker.get()) if multi else None,
            sentence_pause=round(self.v_spause.get(), 2),
            paragraph_pause=round(self.v_ppause.get(), 2),
        )

    def _require_voice(self):
        name = self.v_voice.get().strip()
        if self.vm.is_installed(name):
            return name
        if messagebox.askyesno(APP_NAME, f"The voice '{name}' isn't downloaded yet.\n\n"
                                         "Download it now? This is the only step that needs internet."):
            self._download_voice()
        return None

    def _preview(self):
        try:
            text = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            paras = eng.split_paragraphs(self.text.get("1.0", "end"))
            text = paras[0] if paras else ""
        if not text.strip():
            self.v_status.set("Nothing to preview — type some text first.")
            return
        name = self._require_voice()
        if not name:
            return
        settings = self._settings()

        def work():
            self._emit("status", "Loading voice…")
            voice = self.vm.load(name)
            self._emit("status", "Rendering preview…")
            result = eng.render(voice, text, settings, self._progress_cb, self.stop_flag.is_set)
            eng.save_audio(result.joined().audio, result.sample_rate, self.preview_path)
            self._emit("play", self.preview_path)

        self._run(work)

    def _generate(self):
        text = self.text.get("1.0", "end")
        if not text.strip():
            self.v_status.set("Nothing to generate — type some text first.")
            return
        name = self._require_voice()
        if not name:
            return
        ext = self.v_format.get()
        if ext == "mp3" and not eng.mp3_backend():
            if not messagebox.askyesno(APP_NAME, "No MP3 encoder found (install with: pip install lameenc).\n\nSave as WAV instead?"):
                return
            ext = "wav"
        path = filedialog.asksaveasfilename(
            title="Save voiceover", defaultextension=f".{ext}", initialfile=f"voiceover.{ext}",
            filetypes=[(ext.upper(), f"*.{ext}")])
        if not path:
            return
        settings, split, srt = self._settings(), self.v_split.get(), self.v_srt.get()
        self._save_settings()

        def work():
            self._emit("status", "Loading voice…")
            voice = self.vm.load(name)
            self._emit("status", "Generating voiceover…")
            result = eng.render(voice, text, settings, self._progress_cb, self.stop_flag.is_set)
            self._emit("status", "Saving…")
            files = eng.export(result, path, split=split, subtitles=srt)
            self._emit("saved", (files, result.duration))

        self._run(work)

    def _stop(self):
        self.stop_flag.set()
        self.player.stop()
        if not self.busy:
            self.v_status.set("Stopped.")

    # ------------------------------------------------------- threading
    def _run(self, fn, indeterminate=False):
        if self.busy:
            return
        self.busy = True
        self.stop_flag.clear()
        self.player.stop()
        for b in (self.btn_preview, self.btn_generate, self.btn_download):
            b.state(["disabled"])
        if indeterminate:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.configure(mode="determinate", value=0)

        def wrapper():
            try:
                fn()
            except eng.Cancelled:
                self._emit("status", "Stopped.")
            except Exception as e:  # surface every failure to the user
                self._emit("error", f"{type(e).__name__}: {e}")
            finally:
                self._emit("idle", None)

        threading.Thread(target=wrapper, daemon=True).start()

    def _emit(self, kind, payload):
        self.events.put((kind, payload))

    def _progress_cb(self, done, total):
        self._emit("progress", (done, total))

    def _pump(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.v_status.set(payload)
                elif kind == "progress":
                    done, total = payload
                    self.progress.configure(value=100 * done / total)
                    self.v_status.set(f"Rendering sentence {done} of {total}…")
                elif kind == "play":
                    try:
                        self.player.play(payload)
                        self.v_status.set("Playing preview…")
                    except Exception as e:
                        self.v_status.set(str(e))
                elif kind == "saved":
                    files, dur = payload
                    audio = [f for f in files if f.suffix != ".srt"]
                    m, s = divmod(int(round(dur)), 60)
                    self.v_status.set(f"Saved {len(audio)} audio file(s) · {m}:{s:02} total · {files[0].parent}")
                    if messagebox.askyesno(APP_NAME, f"Done! Saved {len(files)} file(s) to:\n{files[0].parent}\n\nOpen the folder?"):
                        self._open_folder(files[0].parent)
                elif kind == "downloaded":
                    self._refresh_voices()
                    self.v_status.set(f"Voice {payload} is ready — fully offline from now on.")
                elif kind == "error":
                    self.v_status.set("Something went wrong — see message.")
                    messagebox.showerror(APP_NAME, payload)
                elif kind == "idle":
                    self.busy = False
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    for b in (self.btn_preview, self.btn_generate):
                        b.state(["!disabled"])
                    self._on_voice_change()
        except queue.Empty:
            pass
        self.after(100, self._pump)

    # ----------------------------------------------------------- helpers
    def _on_text_modified(self, _):
        if self.text.edit_modified():
            self._update_stats()
            self.text.edit_modified(False)

    def _update_stats(self):
        if not hasattr(self, "text"):
            return
        text = self.text.get("1.0", "end")
        words = len(eng.PAUSE_RE.sub(" ", text).split())
        secs = int(eng.estimate_seconds(text, self.v_speed.get()))
        paras = len(eng.split_paragraphs(text))
        self.v_stats.set(f"{words} words · {paras} paragraph(s) · ≈ {secs // 60}:{secs % 60:02} of audio")

    def _open_text(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")])
        if path:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", Path(path).read_text(encoding="utf-8", errors="replace"))
            self._update_stats()

    def _save_text(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            Path(path).write_text(self.text.get("1.0", "end-1c"), encoding="utf-8")

    @staticmethod
    def _open_folder(folder: Path):
        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])

    def _load_settings(self) -> dict:
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_settings(self):
        data = {
            "voice": self.v_voice.get().strip(), "speaker": int(self.v_speaker.get() or 0),
            "speed": self.v_speed.get(), "expressiveness": self.v_expr.get(),
            "volume": self.v_volume.get(), "sentence_pause": self.v_spause.get(),
            "paragraph_pause": self.v_ppause.get(), "format": self.v_format.get(),
            "split": self.v_split.get(), "subtitles": self.v_srt.get(),
            "text": self.text.get("1.0", "end-1c"),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _on_close(self):
        self.stop_flag.set()
        self.player.stop()
        self._save_settings()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
