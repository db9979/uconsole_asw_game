"""Autosave: a running mission is written to ``autosave.json`` every
``AUTOSAVE_INTERVAL_S`` wall seconds and on a normal quit; "Continue" in the
main menu loads it. ``Game`` mixin.

The autosave is an ordinary exact-v51 save document beside the five slots and
goes through the same strict loader. It never touches the simulation: the
document is built and serialized on the main thread (the save dict shares
lists with live state); only the text goes to one background worker
(``AutosaveWorker``) that checks it with the loader's pure validator and then
stages, ``fsync``s and atomically replaces the file. A document the loader
would reject is never written. The worker holds at most one pending job (a
newer autosave replaces a queued older one); its outcomes come back to the
main thread, which records faults and flashes. A quit waits for the worker; a
mission end, a new mission and a load cancel the pending job and wait for the
running one first, so no late write overtakes them. A finished mission (won,
lost or sunk) deletes the autosave, so "Continue" never resumes a debrief.
A crash writes the last recovery point through the same worker and waits.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import deque

from src.core import config, crashlog
from src.core.i18n import message
from src.core.save_validate import opz_chart_size

CONTINUE_ENTRY = "continue"
AUTOSAVE_FILE = "autosave.json"
# Outcomes kept for the main thread (it reads them every frame).
_RESULTS_MAX = 8


def autosave_path() -> str:
    return os.path.join(config.SAVE_DIR, AUTOSAVE_FILE)


def _write_atomically(path: str, payload: bytes) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=parent, delete=False,
                                         prefix=".autosave-") as f:
            temporary = f.name
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


class AutosaveWorker:
    """One daemon thread (alive only while there is work) that checks and
    writes autosave texts.

    At most one job waits; ``submit`` replaces a queued older one. The thread
    only runs pure functions (``save_text_problem`` with a precomputed OPZ
    chart size) and the file write: no pygame, no live game state. Outcomes
    ``(sequence, ok, problem, check_failed)`` are collected for the main
    thread by ``results``."""

    def __init__(self):
        self._cond = threading.Condition()
        self._pending = None
        self._busy = False
        self._thread = None
        self._sequence = 0
        self._results = deque(maxlen=_RESULTS_MAX)

    def submit(self, path: str, text: str, opz_chart) -> int:
        with self._cond:
            self._sequence += 1
            self._pending = (self._sequence, path, text, opz_chart)
            if self._thread is None:
                # Started on demand; it ends itself once nothing is queued.
                self._thread = threading.Thread(target=self._run, name="autosave",
                                                daemon=True)
                self._thread.start()
            self._cond.notify_all()
            return self._sequence

    def cancel(self) -> bool:
        """Drop the queued job (the running one finishes). True if one was."""
        with self._cond:
            dropped = self._pending is not None
            self._pending = None
            self._cond.notify_all()
            return dropped

    def wait(self) -> None:
        """Block until no job is queued or running."""
        with self._cond:
            while self._pending is not None or self._busy:
                self._cond.wait()

    def idle(self) -> bool:
        with self._cond:
            return self._pending is None and not self._busy

    def results(self) -> list:
        with self._cond:
            items = list(self._results)
            self._results.clear()
            return items

    def _run(self) -> None:
        from src.core.game_save import save_text_problem
        while True:
            with self._cond:
                if self._pending is None:
                    self._thread = None
                    return
                sequence, path, text, opz_chart = self._pending
                self._pending = None
                self._busy = True
            problem, check_failed = None, False
            try:
                problem = save_text_problem(text, opz_chart)
                check_failed = problem is not None
                if problem is None:
                    _write_atomically(path, text.encode("utf-8"))
            except OSError as exc:
                problem = f"autosave write failed: {exc!r}"
            except Exception as exc:  # noqa: BLE001 - reported to the main thread
                problem, check_failed = f"autosave check failed: {exc!r}", True
            with self._cond:
                self._results.append((sequence, problem is None, problem, check_failed))
                self._busy = False
                self._cond.notify_all()


class AutosaveMixin:
    """Periodic autosave of the running mission and the menu's Continue entry."""

    def _init_autosave(self) -> None:
        self._autosave_elapsed_s = 0.0
        self._autosave_worker = AutosaveWorker()
        self._autosave_failed = False
        self.autosave_available = self._autosave_exists()

    @staticmethod
    def _autosave_exists() -> bool:
        path = autosave_path()
        return os.path.isfile(path) and not os.path.islink(path)

    def main_menu_entries(self) -> tuple:
        """Main-menu entries; "Continue" leads while an autosave exists."""
        from src.core.game_bugreport import MAIN_MENU_ENTRIES
        if self.autosave_available:
            return (CONTINUE_ENTRY,) + MAIN_MENU_ENTRIES
        return MAIN_MENU_ENTRIES

    def main_menu_index(self, entry: str) -> int:
        return self.main_menu_entries().index(entry)

    def _mission_running_for_autosave(self) -> bool:
        return not (self.main_menu or self.in_menu or self.editor is not None
                    or self.splash_active or self.web_mode)

    def autosave_tick(self, wall_dt: float) -> None:
        """Count wall time of a running mission; save when the interval is up."""
        self._autosave_poll()
        if not self._mission_running_for_autosave():
            self._autosave_elapsed_s = 0.0
            return
        if self.game_over:
            self._autosave_elapsed_s = 0.0
            self.discard_autosave()
            return
        self._autosave_elapsed_s += max(0.0, float(wall_dt))
        if self._autosave_elapsed_s >= config.AUTOSAVE_INTERVAL_S:
            self._autosave_elapsed_s = 0.0
            self.autosave(background=True)

    def autosave(self, background: bool = False) -> bool:
        """Write the running mission to ``autosave.json``.

        The document is built and serialized here (main thread); the check and
        the write run on the worker. ``background=False`` waits for the worker
        and returns whether this autosave was written; in the background it
        returns True once queued (its outcome arrives through
        ``autosave_tick``). False when there is nothing to save.
        """
        if (not self._mission_running_for_autosave() or self.game_over
                or getattr(self, "_autosave_blocked", False)):
            # Blocked: the recovery snapshot already is the autosave and the
            # live state behind it failed (src/core/game_resilience.py).
            return False
        try:
            document = self.save_state()
            text = json.dumps(document, allow_nan=False, separators=(",", ":"))
            # The same document is a fresh recovery point at no extra cost.
            take = getattr(self, "take_recovery_snapshot", None)
            if take is not None:
                take(document)
        except (TypeError, ValueError, OverflowError, RecursionError):
            self._autosave_failed = True
            return False
        return self._submit_autosave_text(text, wait=not background)

    def _submit_autosave_text(self, text: str, wait: bool) -> bool:
        """Hand a serialized document to the worker; with ``wait`` block until
        it is checked and written and return whether it was."""
        sequence = self._autosave_worker.submit(autosave_path(), text, opz_chart_size())
        if not wait:
            return True
        self._autosave_worker.wait()
        outcomes = self._autosave_poll()
        return any(item[0] == sequence and item[1] for item in outcomes)

    def _autosave_poll(self, flash: bool = True) -> list:
        """Main thread: take the worker's outcomes, record faults, flash."""
        outcomes = self._autosave_worker.results()
        for _sequence, ok, problem, check_failed in outcomes:
            if ok:
                self._autosave_failed = False
                self.autosave_available = True
                continue
            self._autosave_failed = True
            if check_failed:
                from src.core.game_save import SaveSelfCheckError
                crashlog.record_fault(SaveSelfCheckError, SaveSelfCheckError(problem),
                                      None, where="autosave")
            if flash:
                self.flash(message("autosave.failed"), 4.0)
        if outcomes:
            self.autosave_available = self.autosave_available or self._autosave_exists()
        return outcomes

    def _settle_autosave(self) -> None:
        """Before a mission end, a new mission or a load: drop the queued
        autosave and wait for the running write, so none lands afterwards."""
        self._autosave_worker.cancel()
        self._autosave_worker.wait()
        self._autosave_poll(flash=False)

    def wait_for_autosave(self) -> None:
        self._autosave_worker.wait()
        self._autosave_poll()

    def discard_autosave(self) -> None:
        """Remove the autosave (the mission ended); a missing file is fine."""
        self._settle_autosave()
        if not self.autosave_available:
            return
        try:
            os.unlink(autosave_path())
        except FileNotFoundError:
            pass
        except OSError:
            return
        self.autosave_available = False

    def autosave_on_exit(self) -> None:
        """Normal quit: save the running mission so Continue can resume it.
        Returns only after the worker has finished (written or refused)."""
        try:
            self.autosave(background=False)
        except Exception:  # noqa: BLE001 - quitting must never fail over it
            self._autosave_failed = True
        finally:
            self.wait_for_autosave()

    def continue_from_autosave(self) -> bool:
        """Load ``autosave.json``; on failure the file stays and a note shows."""
        from src.core.game_save import _read_save_document
        self._settle_autosave()
        path = autosave_path()
        if not self._autosave_exists():
            self.autosave_available = False
            return False
        try:
            data = _read_save_document(path)
        except (OSError, ValueError, RecursionError):
            data = None
        if data is None or not self._load_save_data(data):
            self.flash(message("autosave.invalid"), 4.0)
            return False
        self._autosave_elapsed_s = 0.0
        self.announce(message("autosave.loaded"), "mission", 2.0)
        return True
