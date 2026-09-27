"""Optional spoken crew reports on the uConsole through espeak-ng.

No audio assets: the text comes from the catalogs and an installed
``espeak-ng`` (or ``espeak``) says it.  When neither is installed the
speaker stays silent.  Speaking never blocks the frame: one process runs at
a time, further sentences wait in a short queue (the oldest is dropped when
it is full), and ``pump`` only polls.  Wall clock only; the simulation
never sees any of this.
"""

from __future__ import annotations

import shutil
import subprocess

QUEUE_MAX = 3
VOICES = {"de": "de", "en": "en-gb"}
RATE_WPM = 170


def find_engine() -> str | None:
    for name in ("espeak-ng", "espeak"):
        path = shutil.which(name)
        if path:
            return path
    return None


class Speaker:
    """One espeak process at a time with a bounded queue."""

    def __init__(self, engine: str | None = None, popen=subprocess.Popen):
        self.engine = engine
        self._popen = popen
        self._process = None
        self.queue: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self.engine is not None

    def say(self, text: str, language: str) -> None:
        if not self.available or not text:
            return
        self.queue.append((str(text)[:200], language))
        del self.queue[:-QUEUE_MAX]
        self.pump()

    def busy(self) -> bool:
        if self._process is None:
            return False
        try:
            if self._process.poll() is None:
                return True
        except OSError:
            pass
        self._process = None
        return False

    def pump(self) -> None:
        if not self.queue or self.busy():
            return
        text, language = self.queue.pop(0)
        try:
            self._process = self._popen(
                [self.engine, "-v", VOICES.get(language, "en-gb"), "-s", str(RATE_WPM),
                 "--", text],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, close_fds=True)
        except (OSError, ValueError, subprocess.SubprocessError):
            # A broken installation silences the speaker for this launch.
            self.engine = None
            self.queue.clear()
            self._process = None

    def stop(self) -> None:
        self.queue.clear()
        process, self._process = self._process, None
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
            except OSError:
                pass
