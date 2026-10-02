"""The enemy learns the player's habits from the service record.

While a mission runs, ``HabitTracker`` watches a few coarse habits of the
side the uConsole plays (read-only, once a second with the debrief, never
saved).  When the mission is filed in the logbook (``src/core/logbook.py``),
the habits it showed go into its entry.  At the start of the next mission
the enemy reads the last missions of that side: a habit shown in more than
half of the last ``WINDOW`` missions (at least ``MIN_MISSIONS``) is known,
and the built-in AI adapts to it a little (``src/core/opfor_plans.py``):

Frigate (the AI submarines adapt):

* ``early_ping``: the first own ping came before (or soon after) the first
  contact; the boats go under the layer as soon as they hear the frigate.
* ``fast_search``: searching at high speed; the frigate is loud, so boats
  that hear it lie in wait under the layer instead of closing.
* ``long_shots``: torpedoes fired from long range; boats that hear the
  frigate keep their distance instead of closing.

Submarine (the AI hunter frigate adapts):

* ``mast_up``: often at periscope depth; the hunter sprints and drifts to
  cover the surface with its radar.
* ``shallow``: mostly above the layer; the hunter pings more often.
* ``fast_transit``: running fast; the hunter searches slowly and listens.

The known habits are decided once per mission (save ``habits``), so a loaded
mission continues with them.  The debrief names them.  Off in the daily
mission (the same for everyone), lessons and two-crew play, and switched
off with the logbook page's ``L`` (``Preferences.enemy_learns``).
"""

from __future__ import annotations

import math

HABITS = {"frigate": ("early_ping", "fast_search", "long_shots"),
          "boat": ("mast_up", "shallow", "fast_transit")}
ALL_HABITS = HABITS["frigate"] + HABITS["boat"]
WINDOW = 5                      # the last missions of a side the enemy reads
MIN_MISSIONS = 3                # fewer filed missions with habits: nothing known
MIN_MISSION_S = 300.0           # shorter missions are not filed with habits
DECIDE_AFTER_S = 1.0            # mission time before the habits are decided
EARLY_PING_S = 120.0            # a first ping this soon after the first contact
FAST_SEARCH_KN = 18.0           # mean speed while searching (no position fix)
LONG_SHOT_NM = 5.0              # mean launch range of own torpedoes
MAST_SHARE = 0.25               # share of time at periscope depth or shallower
SHALLOW_SHARE = 0.5             # share of time above the layer
FAST_TRANSIT_KN = 10.0          # mean speed of the boat
MIN_SAMPLES = 30                # samples (s) before a share or mean counts
SHALLOW_PING_FACTOR = 0.75      # hunter ping interval against a shallow boat


def valid_state(value) -> bool:
    """The save's ``habits`` block: None (not decided yet) or the decision."""
    if value is None:
        return True
    return (isinstance(value, dict) and set(value) == {"side", "known"}
            and value["side"] in HABITS and isinstance(value["known"], list)
            and len(value["known"]) == len(set(value["known"]))
            and all(habit in HABITS[value["side"]] for habit in value["known"]))


def known(entries: list, side: str) -> list:
    """The habits the enemy knows from the logbook entries of one side."""
    rows = [row for row in entries if row.get("side") == side and "habits" in row][-WINDOW:]
    if len(rows) < MIN_MISSIONS:
        return []
    return [habit for habit in HABITS[side]
            if 2 * sum(1 for row in rows if habit in row["habits"]) > len(rows)]


class HabitTracker:
    """Coarse habits of the local side in one mission (read-only, transient)."""

    def __init__(self):
        self.samples = 0
        self.first_contact_t = None
        self.first_ping_t = None
        self._cooldown = 0.0
        self.search_speed_sum = 0.0
        self.search_samples = 0
        self._weapons = set()
        self.shot_ranges = []
        self.mast_samples = 0
        self.shallow_samples = 0
        self.speed_sum = 0.0

    def observe(self, game, t: float, side: str) -> None:
        self.samples += 1
        if side == "boat":
            self._observe_boat(game)
        else:
            self._observe_frigate(game, t)

    def _observe_frigate(self, game, t: float) -> None:
        hostile = [sub for sub in game.subs if sub.side == "hostile" and not sub.sunk]
        ids = {sub.id for sub in hostile}
        contacts = [contact for contact in game.sonar.active_contacts()
                    if contact.target_id in ids]
        if contacts and self.first_contact_t is None:
            self.first_contact_t = float(t)
        cooldown = float(getattr(game.sonar, "ping_cooldown", 0.0) or 0.0)
        if cooldown > self._cooldown + 0.5 and self.first_ping_t is None:
            self.first_ping_t = float(t)
        self._cooldown = cooldown
        fixed = any(contact.observed_x is not None or contact.tma_pos is not None
                    for contact in contacts)
        if not fixed:
            self.search_speed_sum += float(game.ship.speed)
            self.search_samples += 1
        for torpedo in game.torpedoes:
            key = torpedo.idx
            if key in self._weapons:
                continue
            self._weapons.add(key)
            if hostile:
                self.shot_ranges.append(min(math.hypot(sub.x - torpedo.x, sub.y - torpedo.y)
                                            for sub in hostile))

    def _observe_boat(self, game) -> None:
        boat = getattr(game, "_opfor", None)
        if boat is None:
            return
        sub = boat.sub
        from src.sensors.platform import MAST_DEPTH_M
        if sub.depth <= MAST_DEPTH_M:
            self.mast_samples += 1
        try:
            if sub.depth < game.world.thermocline_depth_m(sub.x, sub.y):
                self.shallow_samples += 1
        except (AttributeError, ValueError):
            pass
        self.speed_sum += float(sub.speed)

    def result(self, side: str, mission_s: float) -> list | None:
        """The habits this mission showed, or None when it was too short."""
        if mission_s < MIN_MISSION_S or self.samples < MIN_SAMPLES:
            return None
        shown = []
        if side == "boat":
            if self.mast_samples >= MAST_SHARE * self.samples:
                shown.append("mast_up")
            if self.shallow_samples >= SHALLOW_SHARE * self.samples:
                shown.append("shallow")
            if self.speed_sum >= FAST_TRANSIT_KN * self.samples:
                shown.append("fast_transit")
            return shown
        if self.first_ping_t is not None and (
                self.first_contact_t is None
                or self.first_ping_t <= self.first_contact_t + EARLY_PING_S):
            shown.append("early_ping")
        if (self.search_samples >= MIN_SAMPLES
                and self.search_speed_sum >= FAST_SEARCH_KN * self.search_samples):
            shown.append("fast_search")
        if self.shot_ranges and sum(self.shot_ranges) >= LONG_SHOT_NM * len(self.shot_ranges):
            shown.append("long_shots")
        return shown
