"""Radio tasking: HQ orders and incidents during a mission.

HQ offers a task by teletype; the radio room accepts or declines it within
a response window, and an offer left unanswered counts as declined.  An
accepted task runs to its deadline and ends done or failed.  The kinds:

- ``sar``: a distress call.  A life raft drifts with the current and the
  wind; the ship alongside at slow speed or the helicopter overhead
  recovers the survivors before the survival time runs out.
- ``identify``: a named merchant to identify, by the lookout (visual
  identification) or the helicopter crew close aboard.
- ``datum``: a reported submarine datum to investigate (reach and search).
- ``ras``: replenishment at sea with a friendly supply ship (fuel and
  torpedoes back to the mission load).
- ``emcon``: radar silence for a period.
- ``patrol``: hold a sector for a while (a free patrol only,
  ``free_roam.py``).

This module holds the board (state, schema, bounds) and the pure geometry;
``game_tasking.py`` connects it to the world.  Every draw is counter-based
(``detrand``) so the schedule never moves another random stream.
"""

from __future__ import annotations

import math

KINDS = ("sar", "identify", "datum", "ras", "emcon", "patrol")
STATES = ("offered", "active", "done", "failed", "declined")
OPEN_STATES = ("offered", "active")
VERDICTS = ("clear", "suspect")
VERSION = 1
MAX_TASKS = 8
MAX_NAME = 24
COORD_LIMIT_NM = 1_000.0
MAX_TIME_S = 1e9
MAX_POINTS = 10_000

# Names of the fishing boats in distress (proper names, not prose).
DISTRESS_NAMES = ("FV MOEWE", "FV GRETE", "FV NORDLICHT", "FV HELGA",
                  "FV SEESTERN", "FV ALBATROS", "FV KORMORAN", "FV LOTTE")

TASK_FIELDS = frozenset({
    "id", "kind", "state", "offered_t", "respond_by_t", "deadline_t", "ended_t",
    "x", "y", "radius_nm", "course", "speed_kn", "report_t", "name", "persons",
    "target_id", "true_x", "true_y", "progress", "sighted", "plot_id", "verdict",
    "points",
})
BOARD_FIELDS = frozenset({"version", "next_id", "next_offer_t", "offers", "tasks"})


def _number(value) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value))


def _time(value) -> bool:
    return _number(value) and 0.0 <= value <= MAX_TIME_S


def _coord(value) -> bool:
    return _number(value) and -COORD_LIMIT_NM <= value <= COORD_LIMIT_NM


def valid_task(row) -> bool:
    """Exact keys and bounded, typed values of one saved task."""
    if not isinstance(row, dict) or set(row) != TASK_FIELDS:
        return False
    if (type(row["id"]) is not int or not 1 <= row["id"] <= 10_000
            or row["kind"] not in KINDS or row["state"] not in STATES):
        return False
    if not (_time(row["offered_t"]) and _time(row["respond_by_t"])
            and row["offered_t"] <= row["respond_by_t"]):
        return False
    for key in ("deadline_t", "ended_t", "report_t"):
        if row[key] is not None and not _time(row[key]):
            return False
    if not (_coord(row["x"]) and _coord(row["y"])
            and _number(row["radius_nm"]) and 0.0 < row["radius_nm"] <= 50.0):
        return False
    if (row["course"] is None) != (row["speed_kn"] is None):
        return False
    if row["course"] is not None and not (
            _number(row["course"]) and 0.0 <= row["course"] < 360.0
            and _number(row["speed_kn"]) and 0.0 <= row["speed_kn"] <= 40.0):
        return False
    if row["name"] is not None and (type(row["name"]) is not str
                                    or not row["name"].isprintable()
                                    or not 1 <= len(row["name"]) <= MAX_NAME):
        return False
    if type(row["persons"]) is not int or not 0 <= row["persons"] <= 20:
        return False
    if row["target_id"] is not None and (type(row["target_id"]) is not int
                                         or not 0 <= row["target_id"] <= 2**31 - 1):
        return False
    if (row["true_x"] is None) != (row["true_y"] is None):
        return False
    if row["true_x"] is not None and not (_coord(row["true_x"]) and _coord(row["true_y"])):
        return False
    if not (_number(row["progress"]) and 0.0 <= row["progress"] <= 1.0):
        return False
    if type(row["sighted"]) is not bool:
        return False
    if row["plot_id"] is not None and (type(row["plot_id"]) is not int
                                       or not 1 <= row["plot_id"] <= 2**31 - 1):
        return False
    if row["verdict"] is not None and row["verdict"] not in VERDICTS:
        return False
    if type(row["points"]) is not int or not -MAX_POINTS <= row["points"] <= MAX_POINTS:
        return False
    # State-dependent shape: an open task has not ended, a closed one has.
    if (row["state"] in OPEN_STATES) != (row["ended_t"] is None):
        return False
    if row["state"] == "active" and row["deadline_t"] is None:
        return False
    # Kind-dependent shape.
    kind = row["kind"]
    if (kind == "sar") != (row["true_x"] is not None):
        return False
    if kind == "sar" and row["persons"] < 1:
        return False
    if kind in ("identify", "ras") and row["target_id"] is None:
        return False
    if kind == "ras" and row["course"] is None:
        return False
    if row["verdict"] is not None and kind != "identify":
        return False
    return True


class TaskBoard:
    """The mission's task list with the offer schedule (saved)."""

    def __init__(self, first_offer_t: float | None = None):
        self.next_id = 1
        # None: no tasking in this mission (custom missions).
        self.next_offer_t = first_offer_t
        self.offers = 0
        self.tasks: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self.next_offer_t is not None

    def get(self, task_id):
        return next((task for task in self.tasks if task["id"] == task_id), None)

    def open_tasks(self) -> list:
        return [task for task in self.tasks if task["state"] in OPEN_STATES]

    def active(self, kind: str | None = None) -> list:
        return [task for task in self.tasks if task["state"] == "active"
                and (kind is None or task["kind"] == kind)]

    def counts(self) -> dict:
        result = {state: 0 for state in STATES}
        for task in self.tasks:
            result[task["state"]] += 1
        return result

    def add(self, task: dict) -> dict:
        """File a new offer; the oldest closed task makes room if needed."""
        task = dict(task, id=self.next_id)
        self.next_id += 1
        self.offers += 1
        if len(self.tasks) >= MAX_TASKS:
            closed = [item for item in self.tasks if item["state"] not in OPEN_STATES]
            if closed:
                self.tasks.remove(closed[0])
            else:
                self.tasks.pop(0)
        self.tasks.append(task)
        return task

    # --- persistence --------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, next_id=self.next_id,
                    next_offer_t=self.next_offer_t, offers=self.offers,
                    tasks=[dict(task) for task in self.tasks])

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != BOARD_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        if type(state["next_id"]) is not int or not 1 <= state["next_id"] <= 10_001:
            return False
        if type(state["offers"]) is not int or not 0 <= state["offers"] <= 10_000:
            return False
        if state["next_offer_t"] is not None and not _time(state["next_offer_t"]):
            return False
        tasks = state["tasks"]
        if (not isinstance(tasks, list) or len(tasks) > MAX_TASKS
                or not all(valid_task(task) for task in tasks)):
            return False
        ids = [task["id"] for task in tasks]
        return (len(set(ids)) == len(ids) and ids == sorted(ids)
                and all(i < state["next_id"] for i in ids)
                and len(tasks) <= state["offers"])

    @classmethod
    def restore(cls, state) -> "TaskBoard":
        if not cls.valid_state(state):
            raise ValueError("invalid tasking state")
        board = cls()
        board.next_id = state["next_id"]
        board.next_offer_t = (None if state["next_offer_t"] is None
                              else float(state["next_offer_t"]))
        board.offers = state["offers"]
        board.tasks = [dict(task) for task in state["tasks"]]
        return board


def survival_s(sea_temperature_c: float) -> float:
    """How long the survivors of a sinking last (a game assumption, shorter
    in cold water); the recovery must come inside it."""
    if sea_temperature_c < 8.0:
        return 2400.0
    if sea_temperature_c < 14.0:
        return 3600.0
    if sea_temperature_c < 20.0:
        return 4800.0
    return 6000.0


def dead_reckon(x: float, y: float, course: float, speed_kn: float,
                seconds: float) -> tuple[float, float]:
    step = speed_kn / 3600.0 * seconds
    return (x + step * math.sin(math.radians(course)),
            y - step * math.cos(math.radians(course)))
