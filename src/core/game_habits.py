"""The enemy learns the player's habits (``src/core/habits.py``) in the game.

The tracker watches the local side with the debrief (read-only, never
saved); the logbook files what a mission showed; the habits the enemy knows
are decided once early in each mission from the logbook and saved
(``habits``), so a loaded mission continues with them.
"""

from __future__ import annotations

from src.core import habits
from src.core import logbook as logbook_model


class HabitsMixin:
    """Tracking, the per-mission decision and its save block."""

    def _reset_habits(self) -> None:
        # None until decided early in the mission (saved), then
        # {"side": "frigate"|"boat", "known": [habit, ...]}.
        self.enemy_habits = None
        self.habit_tracker = habits.HabitTracker()

    def habits_allowed(self) -> bool:
        """The enemy may use what it learnt in this mission."""
        if not getattr(self.preferences, "enemy_learns", True):
            return False
        if getattr(self, "training", None) is not None:
            return False
        daily = getattr(self, "_llm_daily_running", None)
        if daily is not None and daily():
            return False
        pvp = getattr(self, "llm_pvp", None)
        return not (pvp is not None and pvp())

    def enemy_known_habits(self, side: str) -> tuple:
        """The habits of ``side`` the enemy adapts to (called in the simulation)."""
        if self.enemy_habits is None:
            if self.mission_time < habits.DECIDE_AFTER_S:
                return ()
            side_now = self._logbook_side()
            known = []
            if self.habits_allowed():
                known = habits.known(logbook_model.load_logbook().entries, side_now)
            self.enemy_habits = {"side": side_now, "known": known}
        decided = self.enemy_habits
        return tuple(decided["known"]) if decided["side"] == side else ()

    def _observe_habits(self) -> None:
        self.habit_tracker.observe(self, self.mission_time, self._logbook_side())

    def mission_habits(self):
        """What this mission showed of the local side (for the logbook)."""
        return self.habit_tracker.result(self._logbook_side(), self.mission_time)

    # -- save (v50) ------------------------------------------------------------

    def habits_serialize(self):
        decided = self.enemy_habits
        return None if decided is None else {"side": decided["side"],
                                             "known": list(decided["known"])}

    def habits_restore(self, value) -> None:
        self.enemy_habits = None if value is None else {"side": value["side"],
                                                        "known": list(value["known"])}
        self.habit_tracker = habits.HabitTracker()
