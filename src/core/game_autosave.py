"""Autosave: a running mission is written to ``autosave.json`` every
``AUTOSAVE_INTERVAL_S`` wall seconds and on a normal quit; "Continue" in the
main menu loads it. ``Game`` mixin.

The autosave is an ordinary exact-v45 save document beside the five slots and
goes through the same strict loader. It never touches the simulation: the
document is built and serialized on the main thread (the save dict shares
lists with live state), only the compact bytes go to a background thread that
stages, ``fsync``s and atomically replaces the file. A finished mission (won,
lost or sunk) deletes the autosave, so "Continue" never resumes a debrief.
A crash writes nothing: the last periodic autosave stays.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from src.core import config
from src.core.i18n import message

CONTINUE_ENTRY = "continue"
AUTOSAVE_FILE = "autosave.json"


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


class AutosaveMixin:
    """Periodic autosave of the running mission and the menu's Continue entry."""

    def _init_autosave(self) -> None:
        self._autosave_elapsed_s = 0.0
        self._autosave_thread = None
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

        Returns False when there is nothing to save or the previous background
        write is still running (it is never queued twice).
        """
        if (not self._mission_running_for_autosave() or self.game_over
                or getattr(self, "_autosave_blocked", False)):
            # Blocked: the recovery snapshot already is the autosave and the
            # live state behind it failed (src/core/game_resilience.py).
            return False
        thread = self._autosave_thread
        if thread is not None and thread.is_alive():
            if background:
                return False
            thread.join()
        try:
            document = self.save_state()
            payload = json.dumps(document, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
            # The same document is a fresh recovery point at no extra cost.
            take = getattr(self, "take_recovery_snapshot", None)
            if take is not None:
                take(document)
        except (TypeError, ValueError, OverflowError, RecursionError):
            self._autosave_failed = True
            return False
        path = autosave_path()

        def write() -> None:
            try:
                _write_atomically(path, payload)
                self._autosave_failed = False
            except OSError:
                self._autosave_failed = True

        if background:
            self._autosave_thread = threading.Thread(
                target=write, name="autosave", daemon=True)
            self._autosave_thread.start()
        else:
            write()
        self.autosave_available = not self._autosave_failed or self._autosave_exists()
        return True

    def wait_for_autosave(self) -> None:
        thread = self._autosave_thread
        if thread is not None and thread.is_alive():
            thread.join()

    def discard_autosave(self) -> None:
        """Remove the autosave (the mission ended); a missing file is fine."""
        if not self.autosave_available:
            return
        self.wait_for_autosave()
        try:
            os.unlink(autosave_path())
        except FileNotFoundError:
            pass
        except OSError:
            return
        self.autosave_available = False

    def autosave_on_exit(self) -> None:
        """Normal quit: save the running mission so Continue can resume it."""
        try:
            self.autosave(background=False)
        except Exception:  # noqa: BLE001 - quitting must never fail over it
            self._autosave_failed = True
        finally:
            self.wait_for_autosave()

    def continue_from_autosave(self) -> bool:
        """Load ``autosave.json``; on failure the file stays and a note shows."""
        from src.core.game_save import _read_save_document
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
