"""Autosave: a running mission is written to ``autosave.json`` every
``AUTOSAVE_INTERVAL_S`` wall seconds and on a normal quit; "Continue" in the
main menu loads it. ``Game`` mixin.

The autosave is an ordinary exact-v53 save document beside the five slots and
goes through the same strict loader. It never touches the simulation: the
document is built on the main thread and detached there with ``pickle`` (the
save dict shares lists with live state; the same bytes are the recovery
point); one background worker (``SaveWorker``) turns them into JSON, checks
the text with the loader's pure validator and then stages, ``fsync``s and
atomically replaces the file (and ``fsync``s its directory). A document the
loader would reject is never written. A save from the save menu takes the
same way (``begin_save_to_slot``) so the frame never waits for it; the menu
shows the save running and closes, or quits, only after it succeeded.

The worker holds at most one pending job per file (a newer autosave replaces
a queued older one); its outcomes come back to the main thread, which records
faults and flashes. A quit waits for the worker; a mission end, a new mission
and a load cancel the pending autosave and wait for the running job first, so
no late write overtakes them. A finished mission (won, lost or sunk) deletes
the autosave, so "Continue" never resumes a debrief. A crash writes the last
recovery point through the same worker and waits. Temporary files a crash
left behind in the save folder are removed at the next start.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import tempfile
import threading
import time
from collections import OrderedDict, deque

from src.core import config, crashlog
from src.core.i18n import message
from src.core.save_validate import opz_chart_size

CONTINUE_ENTRY = "continue"
AUTOSAVE_FILE = "autosave.json"
# Outcomes kept for the main thread (it reads them every frame).
_RESULTS_MAX = 8
# Staged files of an interrupted write (this module, the slot saves and the
# settings), removed from the save folder at start once this old.
_STALE_TEMP = re.compile(r"^(\.autosave-.+|\.save-.+|tmp[a-z0-9_]{8}|\..+\.tmp)$")
STALE_TEMP_AGE_S = 120.0


def autosave_path() -> str:
    return os.path.join(config.SAVE_DIR, AUTOSAVE_FILE)


def _fsync_directory(parent: str) -> None:
    """Make a finished ``os.replace`` durable (POSIX; a no-op elsewhere)."""
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        return
    try:
        handle = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def _write_atomically(path: str, payload: bytes, prefix: str = ".autosave-") -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=parent, delete=False,
                                         prefix=prefix) as f:
            temporary = f.name
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(parent)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def remove_stale_temporaries(directory: str | None = None,
                             max_age_s: float = STALE_TEMP_AGE_S) -> int:
    """Delete staged files an interrupted write left in the save folder (not
    its subfolders, never through a link). Returns how many went."""
    directory = directory or config.SAVE_DIR
    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0
    now = time.time()
    for entry in entries:
        try:
            if (not _STALE_TEMP.match(entry.name)
                    or not entry.is_file(follow_symlinks=False)
                    or now - entry.stat(follow_symlinks=False).st_mtime < max_age_s):
                continue
            os.unlink(entry.path)
            removed += 1
        except OSError:
            continue
    return removed


def document_text(payload, indent: int | None = None) -> str:
    """The save JSON of a job payload: a detached ``pickle`` of the document
    (or, from older callers, the finished text)."""
    if isinstance(payload, str):
        return payload
    document = pickle.loads(payload)
    if indent is None:
        return json.dumps(document, allow_nan=False, separators=(",", ":"))
    return json.dumps(document, allow_nan=False, indent=indent)


class SaveWorker:
    """One daemon thread (alive only while there is work) that turns detached
    save documents into checked files.

    At most one job waits per destination; ``submit`` replaces a queued older
    one for the same file. The thread only runs pure functions (``pickle``,
    ``json``, ``save_text_problem`` with a precomputed OPZ chart size) and
    the file write: no pygame, no live game state. Outcomes ``(sequence, ok,
    problem, check_failed, path)`` are collected for the main thread by
    ``results``."""

    def __init__(self):
        self._cond = threading.Condition()
        self._pending: "OrderedDict[str, tuple]" = OrderedDict()
        self._busy = False
        self._thread = None
        self._sequence = 0
        self._results = deque(maxlen=_RESULTS_MAX)

    def submit(self, path: str, payload, opz_chart, indent: int | None = None,
               cancellable: bool = True) -> int:
        with self._cond:
            self._sequence += 1
            self._pending.pop(path, None)
            self._pending[path] = (self._sequence, path, payload, opz_chart, indent,
                                   cancellable)
            if self._thread is None:
                # Started on demand; it ends itself once nothing is queued.
                self._thread = threading.Thread(target=self._run, name="autosave",
                                                daemon=True)
                self._thread.start()
            self._cond.notify_all()
            return self._sequence

    def cancel(self) -> bool:
        """Drop the queued autosaves (the running job and queued saves of the
        save menu finish). True if one was dropped."""
        with self._cond:
            dropped = [path for path, job in self._pending.items() if job[5]]
            for path in dropped:
                del self._pending[path]
            self._cond.notify_all()
            return bool(dropped)

    def wait(self) -> None:
        """Block until no job is queued or running."""
        with self._cond:
            while self._pending or self._busy:
                self._cond.wait()

    def idle(self) -> bool:
        with self._cond:
            return not self._pending and not self._busy

    def results(self) -> list:
        with self._cond:
            items = list(self._results)
            self._results.clear()
            return items

    def _run(self) -> None:
        from src.core.game_save import save_text_problem
        while True:
            with self._cond:
                if not self._pending:
                    self._thread = None
                    return
                _path, job = self._pending.popitem(last=False)
                sequence, path, payload, opz_chart, indent, cancellable = job
                self._busy = True
            problem, check_failed = None, False
            try:
                text = document_text(payload, indent)
                problem = save_text_problem(text, opz_chart)
                check_failed = problem is not None
                if problem is None and cancellable:
                    _write_atomically(path, text.encode("utf-8"))
                elif problem is None:
                    _write_atomically(path, text.encode("utf-8"), ".save-")
            except OSError as exc:
                problem = str(exc) or repr(exc)
            except Exception as exc:  # noqa: BLE001 - reported to the main thread
                problem, check_failed = f"save check failed: {exc!r}", True
            with self._cond:
                self._results.append((sequence, problem is None, problem, check_failed,
                                      path))
                self._busy = False
                self._cond.notify_all()


# Former name (tests and tools).
AutosaveWorker = SaveWorker


class AutosaveMixin:
    """Periodic autosave of the running mission and the menu's Continue entry."""

    def _init_autosave(self) -> None:
        self._autosave_elapsed_s = 0.0
        self._autosave_worker = SaveWorker()
        self._autosave_failed = False
        # (sequence, slot, quit afterwards) of the save menu's running save.
        self._slot_save_pending = None
        remove_stale_temporaries()
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

        The document is built and detached here (main thread, ``pickle``);
        JSON, the check and the write run on the worker. ``background=False``
        waits for the worker and returns whether this autosave was written; in
        the background it returns True once queued (its outcome arrives
        through ``autosave_tick``). False when there is nothing to save.
        """
        if (not self._mission_running_for_autosave() or self.game_over
                or getattr(self, "_autosave_blocked", False)):
            # Blocked: the recovery snapshot already is the autosave and the
            # live state behind it failed (src/core/game_resilience.py).
            return False
        try:
            blob = pickle.dumps(self.save_state(), protocol=4)
            # The same detached document is a fresh recovery point for free.
            take = getattr(self, "take_recovery_snapshot", None)
            if take is not None:
                take(blob=blob)
        except (TypeError, ValueError, OverflowError, RecursionError,
                pickle.PicklingError):
            self._autosave_failed = True
            return False
        return self._submit_autosave_text(blob, wait=not background)

    def _submit_autosave_text(self, payload, wait: bool) -> bool:
        """Hand a detached document (``pickle`` bytes, or JSON text) to the
        worker; with ``wait`` block until it is checked and written and
        return whether it was."""
        sequence = self._autosave_worker.submit(autosave_path(), payload,
                                                opz_chart_size())
        if not wait:
            return True
        self._autosave_worker.wait()
        outcomes = self._autosave_poll()
        return any(item[0] == sequence and item[1] for item in outcomes)

    def begin_save_to_slot(self, slot: int, quit_after: bool = False) -> int:
        """Save the mission to ``slot`` without holding the frame: the document
        is detached here, JSON, check and write run on the worker. The outcome
        (``_finish_slot_save``) closes the save menu, or quits, only after the
        file was written. Returns the job's sequence."""
        if type(slot) is not int or not 1 <= slot <= 5:
            raise ValueError("slot must be an integer from 1 to 5")
        path = os.path.join(config.SAVE_DIR, f"slot{slot}.json")
        blob = pickle.dumps(self.save_state(), protocol=4)
        sequence = self._autosave_worker.submit(path, blob, opz_chart_size(), indent=1,
                                                cancellable=False)
        self._slot_save_pending = (sequence, slot, bool(quit_after))
        return sequence

    def slot_save_running(self) -> bool:
        return self._slot_save_pending is not None

    def _finish_slot_save(self, sequence: int, ok: bool, problem, check_failed: bool) -> None:
        pending = self._slot_save_pending
        if pending is None or pending[0] != sequence:
            return
        self._slot_save_pending = None
        _sequence, slot, quit_after = pending
        if ok:
            self.announce(message("status.save_feed", slot=slot), "mission", 2.0)
            if self.save_ui == "save":
                self.save_ui = None
                self.save_confirm = False
            self.quit_after_save = False
            if quit_after:
                self.running = False
            return
        if check_failed:
            from src.core.game_save import SaveSelfCheckError
            crashlog.record_fault(SaveSelfCheckError, SaveSelfCheckError(problem),
                                  None, where="save")
            error = message("save.self_check_failed")
        else:
            error = str(problem)
        self.flash(message("runtime.save.error", error=error), 4.0)

    def _autosave_poll(self, flash: bool = True) -> list:
        """Main thread: take the worker's outcomes, record faults, flash."""
        outcomes = self._autosave_worker.results()
        autosave = autosave_path()
        own = []
        for sequence, ok, problem, check_failed, path in outcomes:
            if path != autosave:
                self._finish_slot_save(sequence, ok, problem, check_failed)
                continue
            own.append((sequence, ok, problem, check_failed, path))
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
        if own:
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
