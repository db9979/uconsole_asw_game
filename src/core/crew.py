"""Crew fatigue, watches and morale (frigate and crewed boat).

The ship's company stands in ``WATCHES`` watch sections.  One section is on
duty and tires; the others rest and recover.  A watch is relieved
automatically after ``config.CREW_WATCH_S`` (a game assumption: a real
watch is four hours, the game compresses it so a session sees relief), or
early on the operator's order.  During the turnover the new watch takes
``config.CREW_TURNOVER_S`` to settle in and works less well.

Action stations ("general quarters") put every section on duty: the crew
is alert (a bonus) but nobody rests and everybody tires quickly, so it pays
to stand to for an attack and stand down afterwards.

Morale (0..1) moves with events: tasks done or failed, kills, damage.  It
scales how fast the crew tires and, slightly, how well it works.

``effectiveness()`` is the one number the rest of the game reads.  It is
anchored at 1.0 for a normally rotating, fresh crew at the starting morale,
so gameplay calibration at mission start is unchanged; normal watch
rotation keeps the duty watch below ``CREW_FATIGUE_FREE`` and at 1.0.
Every step is deterministic (no random draws).
"""

from __future__ import annotations

from src.core import config
from src.core.limits import finite_number as _number

WATCHES = 3
VERSION = 1
STATE_FIELDS = frozenset({
    "version", "fatigue", "on_watch", "watch_t", "turnover_t",
    "action_stations", "morale", "kills", "damaged",
})
MAX_TIME_S = 1e9
MAX_COUNT = 10_000

# Morale events (delta), named by what happened.
MORALE_EVENTS = {
    "kill": 0.15,
    "damage": -0.06,
    "repair": 0.02,
    "task_done_sar": 0.12,
    "task_done": 0.06,
    "task_failed": -0.08,
    "task_declined": -0.02,
    "watch_change": 0.0,
}


class CrewState:
    """One ship's watch bill, fatigue and morale."""

    def __init__(self, sim_t: float = 0.0):
        self.fatigue = [0.0] * WATCHES
        self.on_watch = 0
        self.watch_t = float(sim_t)       # when the duty watch took over
        self.turnover_t = None            # turnover ends at this sim time
        self.action_stations = False
        self.morale = config.CREW_MORALE_START
        self.kills = 0                    # event counters already credited
        self.damaged = 0

    # --- the one number the game reads -------------------------------------

    def duty_fatigue(self) -> float:
        if self.action_stations:
            return max(self.fatigue)
        return self.fatigue[self.on_watch]

    def in_turnover(self, sim_t: float) -> bool:
        return self.turnover_t is not None and sim_t < self.turnover_t

    def effectiveness(self, sim_t: float) -> float:
        """Operator performance factor; 1.0 for a fresh crew at start."""
        tired = max(0.0, self.duty_fatigue() - config.CREW_FATIGUE_FREE)
        value = 1.0 - config.CREW_FATIGUE_WEIGHT * tired
        value *= 1.0 + config.CREW_MORALE_WEIGHT * (self.morale - config.CREW_MORALE_START)
        if self.action_stations:
            value *= config.CREW_ACTION_BONUS
        if self.in_turnover(sim_t):
            value *= config.CREW_TURNOVER_FACTOR
        return config.clamp(value, config.CREW_EFFECT_MIN, config.CREW_EFFECT_MAX)

    def watch_left_s(self, sim_t: float) -> float | None:
        if self.action_stations:
            return None
        return max(0.0, self.watch_t + config.CREW_WATCH_S - sim_t)

    # --- orders ------------------------------------------------------------

    def change_watch(self, sim_t: float) -> bool:
        """Relieve the duty watch by the most rested section."""
        if self.action_stations:
            return False
        rested = min((index for index in range(WATCHES) if index != self.on_watch),
                     key=lambda index: (self.fatigue[index], index))
        self.on_watch = rested
        self.watch_t = float(sim_t)
        self.turnover_t = float(sim_t) + config.CREW_TURNOVER_S
        return True

    def set_action_stations(self, enabled: bool, sim_t: float) -> bool:
        enabled = bool(enabled)
        if enabled == self.action_stations:
            return False
        self.action_stations = enabled
        if not enabled:
            # Stand down: the least tired section keeps the watch.
            self.on_watch = min(range(WATCHES), key=lambda index: (self.fatigue[index], index))
            self.watch_t = float(sim_t)
            self.turnover_t = float(sim_t) + config.CREW_TURNOVER_S
        else:
            self.turnover_t = None
        return True

    def event(self, name: str) -> None:
        delta = MORALE_EVENTS.get(name)
        if delta is None:
            prefix = name.rsplit("_", 1)[0]
            delta = MORALE_EVENTS.get(prefix, 0.0)
        self.morale = config.clamp(self.morale + delta, 0.0, 1.0)

    # --- time --------------------------------------------------------------

    def update(self, dt: float, sim_t: float, stress: float = 1.0) -> bool:
        """Advance fatigue; returns True when the watch was relieved."""
        pace = (1.0 + config.CREW_MORALE_FATIGUE * (config.CREW_MORALE_START - self.morale))
        pace = max(0.25, pace) * max(1.0, stress)
        for index in range(WATCHES):
            if self.action_stations:
                rate = pace / config.CREW_TIRE_ACTION_S
            elif index == self.on_watch:
                rate = pace / config.CREW_TIRE_WATCH_S
            else:
                rate = -1.0 / config.CREW_RECOVER_S
            self.fatigue[index] = config.clamp(self.fatigue[index] + rate * dt, 0.0, 1.0)
        if self.turnover_t is not None and sim_t >= self.turnover_t:
            self.turnover_t = None
        if (not self.action_stations
                and sim_t - self.watch_t >= config.CREW_WATCH_S):
            return self.change_watch(sim_t)
        return False

    # --- save --------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, fatigue=[float(value) for value in self.fatigue],
                    on_watch=self.on_watch, watch_t=self.watch_t,
                    turnover_t=self.turnover_t,
                    action_stations=self.action_stations, morale=self.morale,
                    kills=self.kills, damaged=self.damaged)

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        fatigue = state["fatigue"]
        if (not isinstance(fatigue, list) or len(fatigue) != WATCHES
                or not all(_number(value) and 0.0 <= value <= 1.0 for value in fatigue)):
            return False
        if type(state["on_watch"]) is not int or not 0 <= state["on_watch"] < WATCHES:
            return False
        if not (_number(state["watch_t"]) and 0.0 <= state["watch_t"] <= MAX_TIME_S):
            return False
        turnover = state["turnover_t"]
        if turnover is not None and not (_number(turnover) and 0.0 <= turnover <= MAX_TIME_S):
            return False
        if type(state["action_stations"]) is not bool:
            return False
        if state["action_stations"] and turnover is not None:
            return False
        if not (_number(state["morale"]) and 0.0 <= state["morale"] <= 1.0):
            return False
        return all(type(state[key]) is int and 0 <= state[key] <= MAX_COUNT
                   for key in ("kills", "damaged"))

    @classmethod
    def restore(cls, state) -> "CrewState":
        if not cls.valid_state(state):
            raise ValueError("invalid crew watch state")
        crew = cls()
        crew.fatigue = [float(value) for value in state["fatigue"]]
        crew.on_watch = state["on_watch"]
        crew.watch_t = float(state["watch_t"])
        crew.turnover_t = None if state["turnover_t"] is None else float(state["turnover_t"])
        crew.action_stations = state["action_stations"]
        crew.morale = float(state["morale"])
        crew.kills = state["kills"]
        crew.damaged = state["damaged"]
        return crew


BOAT_DAMAGE_STEP = 10.0     # boat damage points per morale "damage" event


def stress(fighting_damage: bool) -> float:
    """Fatigue pace factor: fighting fire and flooding wears a crew out."""
    return config.CREW_DAMAGE_STRESS if fighting_damage else 1.0


def sonar_penalty_db(effectiveness: float) -> float:
    """Extra recognition differential of a tired (or alert) sonar watch."""
    return config.CREW_SONAR_DB * (1.0 - effectiveness)
