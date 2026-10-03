"""Fault resilience: an error no longer ends a running mission. ``Game`` mixin.

* A **display** error (a station view or the whole frame raising while it is
  drawn) is caught: the view shows a notice box, the simulation keeps running
  and the error goes to ``crash.log`` once per distinct place.  Drawing never
  mutates the simulation, so skipping a broken view changes nothing.
* A **simulation** error (input handling, Remote Crew commands, ``update``)
  restores the newest in-memory recovery snapshot, taken every
  ``RECOVERY_SNAPSHOT_INTERVAL_S`` wall seconds of a running mission.  The
  snapshot is an ordinary save document (``save_state()``), detached with
  ``pickle`` and never written to disk on its own; restoring goes through the
  same strict loader as "Continue", so Remote Crew sessions stay paired and
  are re-leased exactly as after a load.  More than
  ``RECOVERY_MAX_RESTORES`` restores within ``RECOVERY_WINDOW_S`` give up:
  the snapshot becomes the autosave and the main menu opens with "Continue".
* An error that still escapes the main loop writes the snapshot to the
  autosave before the process ends, so the next start resumes it.

Outside a running mission (menus, editors) a simulation-side error ends the
game as before: there is nothing to lose and no state to fall back on.
"""

from __future__ import annotations

import json
import os
import pickle
import traceback

import pygame

from src.core import config, crashlog
from src.core.i18n import message

# Distinct fault places logged per launch; repeats of a logged place are
# counted but not written again (a broken view would fail every frame).
FAULT_LOG_MAX = 32


def fault_signature(exc: BaseException) -> tuple:
    """Where an exception was raised: type and innermost file:line."""
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    last = frames[-1] if frames else None
    return (type(exc).__name__,
            os.path.basename(last.filename) if last else "?",
            last.lineno if last else 0)


def draw_fault_box(surface, rect, tr) -> None:
    """Notice box for a view that failed to draw (display only)."""
    from src.ui import layout
    rect = pygame.Rect(rect)
    box = pygame.Rect(0, 0, min(rect.w - 40, 620), 92)
    box.center = rect.center
    surface.fill(config.COLOR_BG, rect)
    pygame.draw.rect(surface, (40, 18, 18), box)
    pygame.draw.rect(surface, config.COLOR_WARN, box, 2)
    layout.blit_block(surface, tr("resilience.view_fault.title"),
                     box.x + 12, box.y + 10, box.w - 24, 30, config.COLOR_WARN,
                     size=22, align="center", valign="center")
    layout.blit_block(surface, tr("resilience.view_fault.hint"),
                     box.x + 12, box.y + 46, box.w - 24, 36, config.COLOR_TEXT,
                     size=17, align="center", valign="center")


class ResilienceMixin:
    """Recovery snapshots, guarded views and the main loop's fault policy."""

    def _init_resilience(self) -> None:
        self._recovery_snapshot = None      # pickled save document (bytes)
        self._recovery_taken_t = 0.0        # self._t when it was taken
        self._recovery_world = None         # the world it belongs to
        self._recovery_elapsed_s = 0.0
        self._recovery_restores = []        # self._t of recent restores
        self._autosave_blocked = False
        self._fault_places = {}             # signature -> count
        self.view_faults = 0

    # --- Snapshots ---------------------------------------------------------

    def recovery_tick(self, wall_dt: float) -> None:
        """Keep a fresh recovery snapshot while a mission runs."""
        if not self._mission_running_for_autosave() or self.game_over:
            self._recovery_snapshot = None
            self._recovery_elapsed_s = 0.0
            self._autosave_blocked = False
            return
        self._recovery_elapsed_s += max(0.0, float(wall_dt))
        # A load or a new mission replaces the world: snapshot the new one now
        # so a fault never falls back into the mission before it.
        if (self._recovery_snapshot is None
                or self._recovery_world is not self.world
                or self._recovery_elapsed_s >= config.RECOVERY_SNAPSHOT_INTERVAL_S):
            self.take_recovery_snapshot()

    def take_recovery_snapshot(self, data: dict | None = None) -> bool:
        """Detach the current save document as the recovery point."""
        try:
            document = self.save_state() if data is None else data
            self._recovery_snapshot = pickle.dumps(document, protocol=4)
        except Exception:  # noqa: BLE001 - a failed snapshot keeps the older one
            return False
        self._recovery_taken_t = self._t
        self._recovery_world = self.world
        self._recovery_elapsed_s = 0.0
        return True

    def recovery_document(self) -> dict | None:
        if self._recovery_snapshot is None:
            return None
        try:
            return pickle.loads(self._recovery_snapshot)
        except Exception:  # noqa: BLE001
            return None

    def write_recovery_autosave(self) -> bool:
        """Write the recovery snapshot as the autosave (crash or give-up)."""
        from src.core.game_autosave import _write_atomically, autosave_path
        from src.core.game_save import save_text_problem
        data = self.recovery_document()
        if data is None:
            return False
        try:
            self.wait_for_autosave()
            text = json.dumps(data, allow_nan=False, separators=(",", ":"))
            # A snapshot the loader would reject keeps the last good autosave.
            if save_text_problem(text) is not None:
                return False
            _write_atomically(autosave_path(), text.encode("utf-8"))
        except Exception:  # noqa: BLE001 - the process is failing already
            return False
        self.autosave_available = True
        return True

    # --- Fault policy --------------------------------------------------------

    def _log_fault(self, exc: BaseException, where: str) -> None:
        signature = fault_signature(exc)
        count = self._fault_places.get(signature, 0)
        if count == 0 and len(self._fault_places) < FAULT_LOG_MAX:
            crashlog.record_fault(type(exc), exc, exc.__traceback__, where=where)
        if count or len(self._fault_places) < FAULT_LOG_MAX:
            self._fault_places[signature] = count + 1

    def view_fault(self, exc: BaseException, name: str, rect) -> None:
        """A view raised while drawing: log it once and show the notice box."""
        self.view_faults += 1
        self._log_fault(exc, f"draw {name}")
        try:
            draw_fault_box(self.screen, rect, self.tr)
        except Exception:  # noqa: BLE001 - the notice must never fail the frame
            self.screen.fill(config.COLOR_BG, pygame.Rect(rect))

    def guarded_view(self, name: str, rect, draw, *args) -> None:
        try:
            draw(*args)
        except Exception as exc:  # noqa: BLE001 - see module docstring
            self.view_fault(exc, name, rect)

    def recover_from_fault(self, exc: BaseException, where: str) -> bool:
        """Simulation-side error: restore the snapshot. False = re-raise."""
        if (not self._mission_running_for_autosave() or self.game_over
                or self._recovery_snapshot is None):
            return False
        self._log_fault(exc, where)
        now = self._t
        self._recovery_restores = [
            t for t in self._recovery_restores
            if 0.0 <= now - t < config.RECOVERY_WINDOW_S]
        lost_s = max(0, int(round(now - self._recovery_taken_t)))
        data = self.recovery_document()
        if len(self._recovery_restores) >= config.RECOVERY_MAX_RESTORES:
            return self._abandon_mission(data)
        self._sonar_ctx = self._frigate_sonar
        try:
            restored = data is not None and self._load_save_data(data)
        except Exception:  # noqa: BLE001
            restored = False
        if not restored:
            return self._abandon_mission(data)
        self._recovery_world = self.world
        self._recovery_restores.append(now)
        self._recovery_restores = self._recovery_restores[-8:]
        self.held.clear()
        self._frame_clock_reset = True
        self._recovery_elapsed_s = 0.0
        self.announce(message("resilience.restored", seconds=lost_s),
                      "mission", 5.0)
        return True

    def _abandon_mission(self, data) -> bool:
        """Repeated faults: keep the snapshot as autosave, open the main menu."""
        if data is None or not self.write_recovery_autosave():
            return False
        self._autosave_blocked = True
        self._sonar_ctx = self._frigate_sonar
        try:
            self._return_to_main_menu()
        except Exception:  # noqa: BLE001 - nothing left to fall back on
            return False
        self._recovery_snapshot = None
        self._recovery_restores = []
        self.autosave_available = True
        self.main_menu_sel = 0
        # Set directly: the frigate's flash never reaches a submarine player,
        # but this note belongs to the menu, not to a side.
        self.msg = message("resilience.abandoned")
        self.msg_until = self._t + 8.0
        return True
