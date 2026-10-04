"""Wounded crew at the stations (frigate and every submarine, save ``casualties``).

Hits and the fire, flooding and gas that follow wound people.  Each ship has
three stations with a fixed number of posts: the sonar room, the weapons
(tubes, launchers) and the damage-control parties.  A wound leaves a post
empty; the station then works slower in proportion to its empty posts
(``factor``: 1.0 fully manned, down to ``1 - GAP_WEIGHT`` with every post
empty).  Every third wound is serious: that man is out for the mission.

Two decisions belong to the damage-control officer:

- the **medical team** treats the lightly wounded of one station and sends
  one back to his post every ``MEDIC_TREAT_S``; unless ordered elsewhere it
  goes where most lightly wounded are;
- **re-manning** fills up to ``REASSIGN_MAX`` empty posts of one station at
  once with men from the resting watches.  They lose their rest (fatigue),
  the ship has only ``REASSIGN_POOL`` spare hands, and the order can be
  given again only after ``REASSIGN_COOLDOWN_S``.

How people get hurt is deterministic (no random draws): a jump in the
ship's damage wounds people at the station of the worst-hit compartment,
and the exposure to fire, water and gas in each station's compartments
wounds one more each time it adds up to one (a full fire for
``EXPOSURE_WOUND_S``).  The frigate's model and the submarines' are the
same; only the compartments differ.
"""

from __future__ import annotations

import math
from src.core.limits import finite_number as _number

VERSION = 1
STATIONS = ("sonar", "weapons", "damage")
POSTS = {"sonar": 4, "weapons": 4, "damage": 8}
GAP_WEIGHT = 0.5
SERIOUS_EVERY = 3
HIT_STEP = 15.0               # damage points per wounded in a hit
HIT_MIN = 5.0                 # smaller jumps are not a hit
HIT_MAX_WOUNDED = 4
EXPOSURE_WOUND_S = 60.0
MEDIC_TREAT_S = 90.0
REASSIGN_MAX = 2
REASSIGN_POOL = 6
REASSIGN_COOLDOWN_S = 180.0
REASSIGN_FATIGUE = 0.08       # fatigue per man on every resting watch
MAX_TIME_S = 1e9
MAX_COUNT = 10_000
MAX_DAMAGE = 1e6

# Compartment -> station whose people work there.
FRIGATE_ROOMS = {"sonar": "sonar", "bridge": "sonar", "weapons": "weapons",
                 "opz": "weapons"}                    # everything else: damage
BOAT_ROOMS = {"control": "sonar", "bow": "weapons"}   # everything else: damage

STATE_FIELDS = frozenset({"version", "light", "serious", "exposure", "wounded",
                          "returned", "last_damage", "medic", "medic_order", "medic_s",
                          "reassigned", "reassign_t"})


def station_of(room: str, rooms: dict) -> str:
    return rooms.get(room, "damage")


class Casualties:
    """One ship's wounded, medical team and re-manning."""

    def __init__(self, damage_now: float = 0.0):
        self.light = {station: 0 for station in STATIONS}
        self.serious = {station: 0 for station in STATIONS}
        self.exposure = {station: 0.0 for station in STATIONS}
        self.wounded = 0
        self.returned = 0
        self.last_damage = float(damage_now)
        self.medic = None             # where the medical team works
        self.medic_order = None       # the officer's choice (None: automatic)
        self.medic_s = 0.0
        self.reassigned = 0
        self.reassign_t = 0.0         # next re-manning allowed at this time

    # --- derived -------------------------------------------------------------

    def gaps(self, station: str) -> int:
        return self.light[station] + self.serious[station]

    def factor(self, station: str) -> float:
        return 1.0 - GAP_WEIGHT * self.gaps(station) / POSTS[station]

    def spare(self) -> int:
        return REASSIGN_POOL - self.reassigned

    def worst(self):
        """The station with the most empty posts (relative), or None."""
        rows = [(-self.gaps(station) / POSTS[station], index, station)
                for index, station in enumerate(STATIONS) if self.gaps(station) > 0]
        return min(rows)[2] if rows else None

    # --- events --------------------------------------------------------------

    def wound(self, station: str) -> bool:
        """One man hurt at ``station``; False when nobody is left there."""
        if self.gaps(station) >= POSTS[station] or self.wounded >= MAX_COUNT:
            return False
        if self.wounded % SERIOUS_EVERY == SERIOUS_EVERY - 1:
            self.serious[station] += 1
        else:
            self.light[station] += 1
        self.wounded += 1
        return True

    def update(self, dt: float, damage_now: float, levels: dict, worst_room_station) -> int:
        """Advance; ``levels`` is each station's exposure (0..1) and
        ``worst_room_station`` the station of the worst-hit compartment.
        Returns how many were wounded in this step."""
        hurt = 0
        jump = float(damage_now) - self.last_damage
        self.last_damage = min(MAX_DAMAGE, max(0.0, float(damage_now)))
        if jump >= HIT_MIN:
            count = min(HIT_MAX_WOUNDED, max(1, math.ceil(jump / HIT_STEP)))
            station = worst_room_station or "damage"
            hurt += sum(1 for _ in range(count) if self.wound(station))
        for station in STATIONS:
            level = min(1.0, max(0.0, float(levels.get(station, 0.0))))
            self.exposure[station] += level * max(0.0, dt) / EXPOSURE_WOUND_S
            while self.exposure[station] >= 1.0:
                self.exposure[station] -= 1.0
                hurt += int(self.wound(station))
        self._treat(dt)
        return hurt

    def _treat(self, dt: float) -> None:
        wanted = self.medic_order
        if wanted is None or self.light[wanted] == 0:
            rows = [(-self.light[station], index, station)
                    for index, station in enumerate(STATIONS) if self.light[station] > 0]
            wanted = min(rows)[2] if rows else None
        if wanted != self.medic:
            self.medic, self.medic_s = wanted, 0.0
        if self.medic is None:
            return
        self.medic_s += max(0.0, dt)
        if self.medic_s >= MEDIC_TREAT_S:
            self.medic_s = 0.0
            self.light[self.medic] -= 1
            self.returned = min(MAX_COUNT, self.returned + 1)

    # --- orders --------------------------------------------------------------

    def cycle_medic(self):
        """Send the medical team to the next station with lightly wounded
        (after the last: automatic).  Returns the new order."""
        choices = [station for station in STATIONS if self.light[station] > 0]
        if not choices:
            self.medic_order = None
            return None
        if self.medic_order in choices and self.medic_order != choices[-1]:
            self.medic_order = choices[choices.index(self.medic_order) + 1]
        elif self.medic_order is None:
            self.medic_order = choices[0]
        else:
            self.medic_order = None
        return self.medic_order

    def reassign(self, now: float, station=None):
        """Fill empty posts of ``station`` (default: the worst) from the
        resting watches.  Returns ``(station, men)`` or a refusal code."""
        station = self.worst() if station is None else station
        if station not in STATIONS or self.gaps(station) == 0:
            return "no_gaps"
        if now < self.reassign_t:
            return "reassign_wait"
        men = min(REASSIGN_MAX, self.gaps(station), self.spare())
        if men <= 0:
            return "no_hands"
        for _ in range(men):
            if self.serious[station] > 0:
                self.serious[station] -= 1
            else:
                self.light[station] -= 1
        self.reassigned += men
        self.reassign_t = float(now) + REASSIGN_COOLDOWN_S
        return station, men

    # --- save ----------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, light=dict(self.light), serious=dict(self.serious),
                    exposure={key: float(value) for key, value in self.exposure.items()},
                    wounded=self.wounded, returned=self.returned,
                    last_damage=self.last_damage, medic=self.medic,
                    medic_order=self.medic_order, medic_s=self.medic_s,
                    reassigned=self.reassigned, reassign_t=self.reassign_t)

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        for key in ("light", "serious", "exposure"):
            if not isinstance(state[key], dict) or set(state[key]) != set(STATIONS):
                return False
        for station in STATIONS:
            light, serious = state["light"][station], state["serious"][station]
            if (type(light) is not int or type(serious) is not int
                    or light < 0 or serious < 0 or light + serious > POSTS[station]):
                return False
            exposure = state["exposure"][station]
            if not (_number(exposure) and 0.0 <= exposure < 1.0):
                return False
        for key in ("wounded", "returned", "reassigned"):
            if type(state[key]) is not int or not 0 <= state[key] <= MAX_COUNT:
                return False
        if state["reassigned"] > REASSIGN_POOL:
            return False
        if not (_number(state["last_damage"]) and 0.0 <= state["last_damage"] <= MAX_DAMAGE):
            return False
        for key in ("medic", "medic_order"):
            if state[key] is not None and state[key] not in STATIONS:
                return False
        if not (_number(state["medic_s"]) and 0.0 <= state["medic_s"] < MEDIC_TREAT_S):
            return False
        return _number(state["reassign_t"]) and 0.0 <= state["reassign_t"] <= MAX_TIME_S

    @classmethod
    def restore(cls, state) -> "Casualties":
        if not cls.valid_state(state):
            raise ValueError("invalid casualties state")
        roster = cls()
        roster.light = dict(state["light"])
        roster.serious = dict(state["serious"])
        roster.exposure = {key: float(value) for key, value in state["exposure"].items()}
        roster.wounded = state["wounded"]
        roster.returned = state["returned"]
        roster.last_damage = float(state["last_damage"])
        roster.medic = state["medic"]
        roster.medic_order = state["medic_order"]
        roster.medic_s = float(state["medic_s"])
        roster.reassigned = state["reassigned"]
        roster.reassign_t = float(state["reassign_t"])
        return roster
