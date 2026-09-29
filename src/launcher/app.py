"""Tk starter window: start/stop the game as Remote Crew server, show the
browser address and join code, and offer published updates.

The game runs as a separate process (the same executable with ``--game``);
the starter never touches simulation state. It learns the address and join
code from the JSON status file the game writes (``--status-file``).
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import webbrowser

from src.core import bugreport
from src.core.i18n import Translator
from src.core.preferences import load_preferences, save_preferences
from src.core.version import APP_VERSION
from src.launcher import update
from src.ui.support import SUPPORT_URL

POLL_MS = 500
DEFAULT_PORT = 8765


def user_dir() -> Path:
    return Path.home() / ".u-jagd"


def log_path() -> Path:
    return user_dir() / "logs" / "server.log"


def game_command(options: dict, status_file: str) -> list[str]:
    """The child command line for the chosen starter options."""
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--game"]
    else:
        command = [sys.executable, str(Path(__file__).resolve().parents[2] / "main.py")]
    command.append("--solo-crew" if options.get("solo") else "--remote-crew")
    if options.get("play_sub"):
        command.append("--play-sub")
    if options.get("windowed"):
        command.append("--windowed")
    if options.get("no_audio"):
        command.append("--no-audio")
    port = int(options.get("port", DEFAULT_PORT))
    if not 1024 <= port <= 65535:
        raise ValueError("port")
    command += ["--web-port", str(port), "--status-file", status_file]
    return command


def read_status(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as handle:
            status = json.load(handle)
    except (OSError, ValueError):
        return None
    return status if isinstance(status, dict) else None


LANGUAGE_NAMES = {"en": "English", "de": "Deutsch"}


class Starter:
    def __init__(self, root, check_updates=True, preferences_path=None):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.preferences_path = preferences_path
        self.tr = Translator(load_preferences(preferences_path).language)
        self.process = None
        self.log = None
        self.status_file = None
        self.release = None
        self.url = None
        self.frame = None
        self.texts = {}
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.solo = tk.BooleanVar(value=False)
        self.play_sub = tk.BooleanVar(value=False)
        self.windowed = tk.BooleanVar(value=True)
        self.no_audio = tk.BooleanVar(value=False)
        self.port = tk.StringVar(value=str(DEFAULT_PORT))
        self.language = tk.StringVar(value=LANGUAGE_NAMES[self.tr.language])
        self.state_text = tk.StringVar()
        self.url_text = tk.StringVar(value="")
        self.code_text = tk.StringVar(value="")
        self.update_text = tk.StringVar()
        self._say(self.state_text, "launcher.state.stopped")
        self._say(self.update_text, "launcher.update.checking")
        self._build()
        if check_updates:
            self.check_updates()
        else:
            self._say(self.update_text, "launcher.update.current", version=APP_VERSION)
        root.after(POLL_MS, self.poll)

    def _build(self):
        """(Re)create every widget in the current language; state survives."""
        tk, ttk, root = self.tk, self.ttk, self.root
        if self.frame is not None:
            self.frame.destroy()
        root.title(self.t("launcher.title", version=APP_VERSION))
        self.frame = frame = ttk.Frame(root, padding=14)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text=self.t("launcher.heading"),
                  font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
        language = ttk.Frame(frame)
        language.grid(row=0, column=1, sticky="e")
        ttk.Label(language, text=self.t("launcher.language")).grid(row=0, column=0,
                                                                   padx=(0, 6))
        chooser = ttk.Combobox(language, textvariable=self.language, state="readonly",
                               width=9, values=list(LANGUAGE_NAMES.values()))
        chooser.grid(row=0, column=1)
        chooser.bind("<<ComboboxSelected>>", lambda _event: self.choose_language(
            next(code for code, name in LANGUAGE_NAMES.items()
                 if name == self.language.get())))
        options = ttk.LabelFrame(frame, text=self.t("launcher.options"), padding=8)
        options.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        ttk.Radiobutton(options, text=self.t("launcher.mode.crew"), variable=self.solo,
                        value=False).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(options, text=self.t("launcher.mode.solo"), variable=self.solo,
                        value=True).grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(options, text=self.t("launcher.play_sub"),
                        variable=self.play_sub).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(options, text=self.t("launcher.windowed"),
                        variable=self.windowed).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(options, text=self.t("launcher.no_audio"),
                        variable=self.no_audio).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(options, text=self.t("launcher.port")).grid(row=5, column=0, sticky="w")
        ttk.Spinbox(options, from_=1024, to=65535, width=7,
                    textvariable=self.port).grid(row=5, column=1, sticky="w")
        self.option_widgets = options.winfo_children()

        server = ttk.LabelFrame(frame, text=self.t("launcher.server"), padding=8)
        server.grid(row=1, column=1, sticky="nsew", pady=(10, 0), padx=(10, 0))
        ttk.Label(server, textvariable=self.state_text).grid(row=0, column=0, columnspan=2,
                                                            sticky="w")
        ttk.Label(server, text=self.t("launcher.address")).grid(row=1, column=0, sticky="w")
        ttk.Entry(server, textvariable=self.url_text, width=28,
                  state="readonly").grid(row=1, column=1, sticky="w")
        ttk.Label(server, text=self.t("launcher.code")).grid(row=2, column=0, sticky="w")
        ttk.Label(server, textvariable=self.code_text,
                  font=("Consolas", 18, "bold")).grid(row=2, column=1, sticky="w")
        self.qr = tk.Canvas(server, width=148, height=148, background="white",
                            highlightthickness=0)
        self.qr.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Label(server, text=self.t("launcher.hint"), wraplength=260,
                  justify="left").grid(row=4, column=0, columnspan=2, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.start_button = ttk.Button(buttons, text=self.t("launcher.start"),
                                       command=self.start)
        self.start_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(buttons, text=self.t("launcher.stop"),
                                      command=self.stop, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=6)
        self.open_button = ttk.Button(buttons, text=self.t("launcher.open"),
                                      command=self.open_browser, state="disabled")
        self.open_button.grid(row=0, column=2)
        ttk.Button(buttons, text=self.t("launcher.log"),
                   command=self.open_log).grid(row=0, column=3, padx=6)
        support = ttk.Label(buttons, text=self.t("launcher.support"), foreground="#1a5fb4",
                            cursor="hand2", font=("Segoe UI", 9, "underline"))
        support.grid(row=0, column=4, padx=(10, 0))
        support.bind("<Button-1>", lambda _event: webbrowser.open(SUPPORT_URL))
        report = ttk.Label(buttons, text=self.t("launcher.bug_report"), foreground="#1a5fb4",
                           cursor="hand2", font=("Segoe UI", 9, "underline"))
        report.grid(row=0, column=5, padx=(10, 0))
        report.bind("<Button-1>", lambda _event: self.report_bug())

        updates = ttk.Frame(frame)
        updates.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(updates, textvariable=self.update_text, wraplength=380,
                  justify="left").grid(row=0, column=0, sticky="w")
        if self.release is not None:
            self.update_button = ttk.Button(updates, text=self.t("launcher.update.install"),
                                            command=self.install_update)
        else:
            self.update_button = ttk.Button(updates, text=self.t("launcher.update.check"),
                                            command=self.check_updates)
        self.update_button.grid(row=0, column=1, padx=(8, 0))
        if self.process is not None:
            self._set_running(True)
            self.open_button.configure(state="normal" if self.url else "disabled")
            self._draw_qr(self.url)

    def choose_language(self, language: str):
        """Switch the starter's language now and keep it for the game too.

        The game reads ``settings.json`` at launch, so a server started
        afterwards (and the game window) uses the same language.
        """
        if language not in LANGUAGE_NAMES or language == self.tr.language:
            return
        preferences = replace(load_preferences(self.preferences_path), language=language)
        try:
            save_preferences(preferences, self.preferences_path)
        except OSError:
            pass
        self.tr = Translator(language)
        self.language.set(LANGUAGE_NAMES[language])
        for variable, key, values in self.texts.values():
            variable.set(self.t(key, **values))
        self._build()

    def _say(self, variable, key: str, **values):
        """Set a status line by key so a language switch can re-translate it."""
        # Tk variables are unhashable: keyed by their Tcl name.
        self.texts[str(variable)] = (variable, key, values)
        variable.set(self.t(key, **values))

    def report_bug(self):
        """Open a prefilled GitHub issue with the crash and server log tails."""
        if self.log is not None:
            try:
                self.log.flush()
            except (OSError, ValueError):
                pass
        log = bugreport.read_log_tail()
        server = bugreport.read_text_tail(str(log_path()), 60)
        if server:
            log = f"{log}\n--- server.log ---\n{server}" if log else server
        context = "Windows starter" if sys.platform == "win32" else "server starter"
        path = bugreport.write_report(bugreport.report_text(context, log))
        webbrowser.open(bugreport.issue_url(context, log))
        if path:
            self._say(self.state_text, "launcher.bug_report.file",
                      path=bugreport.display_path(path))

    def t(self, key: str, **values) -> str:
        return self.tr.translate(key, **values)

    # --- server process -------------------------------------------------

    def start(self):
        if self.process is not None:
            return
        try:
            port = int(self.port.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            self._say(self.state_text, "launcher.error.port")
            return
        handle, self.status_file = tempfile.mkstemp(prefix="u-jagd-", suffix=".json")
        os.close(handle)
        os.remove(self.status_file)
        command = game_command({"solo": self.solo.get(), "play_sub": self.play_sub.get(),
                                "windowed": self.windowed.get(),
                                "no_audio": self.no_audio.get(), "port": port},
                               self.status_file)
        log_path().parent.mkdir(parents=True, exist_ok=True)
        self.log = open(log_path(), "w", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                            stdout=self.log, stderr=subprocess.STDOUT,
                                            creationflags=flags)
        except OSError:
            self.log.close()
            self.log = None
            self._say(self.state_text, "launcher.error.start")
            return
        self._say(self.state_text, "launcher.state.starting")
        self._set_running(True)

    def stop(self):
        from tkinter import messagebox

        if self.process is None:
            return
        if not messagebox.askyesno(self.t("launcher.stop"), self.t("launcher.stop.confirm")):
            return
        self.process.terminate()

    def _set_running(self, running: bool):
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        for widget in self.option_widgets:
            try:
                widget.configure(state="disabled" if running else "normal")
            except self.tk.TclError:
                pass
        if not running:
            self.open_button.configure(state="disabled")
            self.url = None
            self.url_text.set("")
            self.code_text.set("")
            self.qr.delete("all")

    def poll(self):
        if self.process is not None:
            code = self.process.poll()
            if code is not None:
                self.process = None
                if self.log is not None:
                    self.log.close()
                    self.log = None
                self._remove_status_file()
                self._set_running(False)
                if code in (0, 1, -15):
                    self._say(self.state_text, "launcher.state.stopped")
                else:
                    self._say(self.state_text, "launcher.state.crashed", code=code)
            else:
                self._show_status(read_status(self.status_file))
        self.root.after(POLL_MS, self.poll)

    def _show_status(self, status):
        if status is None:
            return
        url = status.get("url") if type(status.get("url")) is str else None
        code = status.get("code") if type(status.get("code")) is str else ""
        state = status.get("state")
        if state == "running" and url:
            self._say(self.state_text, "launcher.state.solo" if status.get("solo")
                      else "launcher.state.crew")
        elif state == "error":
            self._say(self.state_text, "launcher.error.listener")
        else:
            self._say(self.state_text, "launcher.state.off")
        if url != self.url:
            self.url = url
            self.url_text.set(url or "")
            self.open_button.configure(state="normal" if url else "disabled")
            self._draw_qr(url)
        self.code_text.set(code)

    def _draw_qr(self, url):
        self.qr.delete("all")
        if not url:
            return
        from src.ui import qr

        matrix = qr.encode(url)
        size = len(matrix)
        cell = max(1, 140 // (size + 2))
        offset = (148 - cell * size) // 2
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    self.qr.create_rectangle(offset + x * cell, offset + y * cell,
                                             offset + (x + 1) * cell, offset + (y + 1) * cell,
                                             fill="black", width=0)

    def _remove_status_file(self):
        if self.status_file:
            for path in (self.status_file, f"{self.status_file}.tmp"):
                try:
                    os.remove(path)
                except OSError:
                    pass
            self.status_file = None

    def open_browser(self):
        if self.url:
            webbrowser.open(self.url)

    def open_log(self):
        path = log_path()
        if path.exists():
            if os.name == "nt":
                os.startfile(path)  # noqa: S606 - the user's own log file
            else:
                webbrowser.open(path.as_uri())

    def close(self):
        from tkinter import messagebox

        if self.process is not None:
            if not messagebox.askyesno(self.t("launcher.stop"),
                                       self.t("launcher.stop.confirm")):
                return
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            if self.log is not None:
                self.log.close()
            self._remove_status_file()
        self.root.destroy()

    # --- updates ----------------------------------------------------------

    def check_updates(self):
        self.update_button.configure(state="disabled")
        self._say(self.update_text, "launcher.update.checking")

        def work():
            try:
                result = update.check_latest(APP_VERSION)
            except update.UpdateError:
                result = False
            self.root.after(0, lambda: self._update_checked(result))

        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, release):
        self.update_button.configure(state="normal")
        if release is False:
            self._say(self.update_text, "launcher.update.offline", version=APP_VERSION)
            return
        self.release = release
        if release is None:
            self._say(self.update_text, "launcher.update.current", version=APP_VERSION)
            return
        self._say(self.update_text, "launcher.update.available", version=release.version,
                  current=APP_VERSION)
        self.update_button.configure(text=self.t("launcher.update.install"),
                                     command=self.install_update)

    def install_update(self):
        from tkinter import messagebox

        release = self.release
        if release is None:
            return
        if not getattr(sys, "frozen", False):
            webbrowser.open(release.page)
            return
        if self.process is not None:
            messagebox.showinfo(self.t("launcher.update.install"),
                                self.t("launcher.update.stop_first"))
            return
        executable = os.path.abspath(sys.executable)
        target = f"{executable}.new"
        self.update_button.configure(state="disabled")

        def progress(done, total):
            percent = int(done * 100 / total)
            self.root.after(0, lambda: self._say(
                self.update_text, "launcher.update.downloading", percent=percent))

        def work():
            try:
                update.download(release, target, progress=progress)
                script = os.path.join(tempfile.gettempdir(), "u-jagd-update.cmd")
                with open(script, "w", encoding="utf-8", newline="") as handle:
                    handle.write(update.install_script(executable, target, os.getpid()))
            except update.UpdateError:
                self.root.after(0, self._update_failed)
                return
            self.root.after(0, lambda: self._restart_into(script))

        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self):
        self.update_button.configure(state="normal")
        self._say(self.update_text, "launcher.update.failed")

    def _restart_into(self, script):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", script], creationflags=flags,
                         env=update.clean_environment(os.environ),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        self.root.destroy()


def run() -> int:
    import tkinter as tk

    root = tk.Tk()
    Starter(root)
    root.mainloop()
    return 0
