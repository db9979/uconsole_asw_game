"""Incidents at sea: unplanned events of a mission (save ``incidents``).

Besides HQ's radio tasks (``tasking.py``) the sea itself brings surprises.
The kinds:

- ``net``: a fishing boat reports a drift net across the frigate's track.
  It hangs from the surface down to ``INCIDENT_NET_DEPTH_M``.  A ship that
  runs over it tears it (the fishermen claim damages) and a streamed towed
  array or variable-depth sonar fouls in it and has to be hauled in; a
  submarine that crosses it shallower than the net's depth fouls it too and
  makes a loud transient while it tears free.
- ``front``: a weather front: HQ warns ahead of it, then rain, a storm or
  fog hold for a while.  Both sides live under the same sky.
- ``dark``: a merchant running without AIS turns up, and HQ asks the frigate
  to identify it (a radio task when the board has room).
- ``whales``: a pod of whales in the area, reported by a fishing boat: real
  biological contacts for every sonar.

Emergencies aboard (1.3.120), one side each so both lose time:

- ``overboard``: a man overboard from the frigate. He drifts with the
  surface current (``x``, ``y``); the ship recovers him by passing within
  ``INCIDENT_OVERBOARD_PICKUP_NM`` at slow speed, or the helicopter by
  hovering over him, before ``end_t`` (his time in the water).
- ``rudder``: the frigate's steering gear fails: the rudder is jammed for
  ``INCIDENT_RUDDER_JAM_S``, then emergency steering turns at half rate
  until ``end_t``.
- ``valve``: the snorkel head valve of a submarine (``target_id``) jams:
  its diesels cannot run until ``end_t``.
- ``gas``: hydrogen from a submarine's battery: it charges at half rate
  until ``end_t``.

HQ also passes the net, the front and the whales on to the submarine's
broadcast, so a crewed boat hears of them when it copies the next one.

This module holds the board (state, schema, bounds) and the pure geometry;
``game_incidents.py`` connects it to the world.  Every draw is
counter-based (``detrand``) so the schedule never moves another random
stream.  Custom missions and lessons have no incidents.
"""

from __future__ import annotations

import math

KINDS = ("net", "front", "dark", "whales", "overboard", "rudder", "valve", "gas")
# Kinds that name an entity in ``target_id``.
TARGET_KINDS = ("dark", "valve", "gas")
WEATHER = ("rain", "storm", "fog")
VERSION = 1
MAX_ITEMS = 6
MAX_FOULED = 16
COORD_LIMIT_NM = 1_000.0
MAX_TIME_S = 1e9

ITEM_FIELDS = frozenset({
    "id", "kind", "announced_t", "start_t", "end_t", "active", "x", "y", "x2", "y2",
    "weather", "target_id", "plot_id", "boat_told", "fouled",
})
BOARD_FIELDS = frozenset({"version", "next_id", "next_t", "count", "items"})


def _number(value) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value))


def _time(value) -> bool:
    return _number(value) and 0.0 <= value <= MAX_TIME_S


def _coord(value) -> bool:
    return _number(value) and -COORD_LIMIT_NM <= value <= COORD_LIMIT_NM


def _entity_id(value) -> bool:
    return type(value) is int and 0 <= value <= 2**31 - 1


def valid_item(row) -> bool:
    """Exact keys and bounded, typed values of one saved incident."""
    if not isinstance(row, dict) or set(row) != ITEM_FIELDS:
        return False
    if (type(row["id"]) is not int or not 1 <= row["id"] <= 10_000
            or row["kind"] not in KINDS or type(row["active"]) is not bool
            or type(row["boat_told"]) is not bool):
        return False
    if not (_time(row["announced_t"]) and _time(row["start_t"]) and _time(row["end_t"])
            and row["announced_t"] <= row["start_t"] <= row["end_t"]):
        return False
    if not (_coord(row["x"]) and _coord(row["y"])):
        return False
    net = row["kind"] == "net"
    if net != (row["x2"] is not None) or (row["x2"] is None) != (row["y2"] is None):
        return False
    if net and not (_coord(row["x2"]) and _coord(row["y2"])):
        return False
    if (row["kind"] == "front") != (row["weather"] is not None):
        return False
    if row["weather"] is not None and row["weather"] not in WEATHER:
        return False
    if (row["kind"] in TARGET_KINDS) != (row["target_id"] is not None):
        return False
    if row["target_id"] is not None and not _entity_id(row["target_id"]):
        return False
    if row["plot_id"] is not None and (type(row["plot_id"]) is not int
                                       or not 1 <= row["plot_id"] <= 2**31 - 1):
        return False
    fouled = row["fouled"]
    if (not isinstance(fouled, list) or len(fouled) > MAX_FOULED
            or not all(_entity_id(item) for item in fouled)
            or fouled != sorted(set(fouled))):
        return False
    return not fouled or net


class IncidentBoard:
    """The mission's incidents with their schedule (saved)."""

    def __init__(self, first_t: float | None = None):
        self.next_id = 1
        # None: no incidents in this mission (custom missions, lessons).
        self.next_t = first_t
        self.count = 0
        self.items: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self.next_t is not None

    def active(self, kind: str | None = None) -> list:
        return [item for item in self.items if item["active"]
                and (kind is None or item["kind"] == kind)]

    def add(self, item: dict) -> dict:
        """File a new incident; the oldest finished one makes room."""
        item = dict(item, id=self.next_id)
        self.next_id += 1
        if len(self.items) >= MAX_ITEMS:
            done = [row for row in self.items if not row["active"]]
            self.items.remove(done[0] if done else self.items[0])
        self.items.append(item)
        return item

    def serialize(self) -> dict:
        return dict(version=VERSION, next_id=self.next_id, next_t=self.next_t,
                    count=self.count,
                    items=[dict(item, fouled=list(item["fouled"])) for item in self.items])

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != BOARD_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        if type(state["next_id"]) is not int or not 1 <= state["next_id"] <= 10_001:
            return False
        if type(state["count"]) is not int or not 0 <= state["count"] <= 10_000:
            return False
        if state["next_t"] is not None and not _time(state["next_t"]):
            return False
        items = state["items"]
        if (not isinstance(items, list) or len(items) > MAX_ITEMS
                or not all(valid_item(item) for item in items)):
            return False
        ids = [item["id"] for item in items]
        return (len(set(ids)) == len(ids) and ids == sorted(ids)
                and all(i < state["next_id"] for i in ids)
                and len(items) <= state["next_id"] - 1)

    @classmethod
    def restore(cls, state) -> "IncidentBoard":
        if not cls.valid_state(state):
            raise ValueError("invalid incident state")
        board = cls()
        board.next_id = state["next_id"]
        board.next_t = None if state["next_t"] is None else float(state["next_t"])
        board.count = state["count"]
        board.items = [dict(item, fouled=list(item["fouled"])) for item in state["items"]]
        return board


def segment_distance_nm(px: float, py: float, x1: float, y1: float,
                        x2: float, y2: float) -> float:
    """Distance from a point to the net line."""
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 <= 0.0:
        return math.hypot(px - x1, py - y1)
    along = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length2))
    return math.hypot(px - (x1 + along * dx), py - (y1 + along * dy))


def segments_cross(ax: float, ay: float, bx: float, by: float,
                   cx: float, cy: float, dx: float, dy: float) -> bool:
    """Whether the leg a-b crosses the line c-d (touching counts)."""
    def side(px, py, qx, qy, rx, ry):
        return (qx - px) * (ry - py) - (qy - py) * (rx - px)
    d1, d2 = side(cx, cy, dx, dy, ax, ay), side(cx, cy, dx, dy, bx, by)
    d3, d4 = side(ax, ay, bx, by, cx, cy), side(ax, ay, bx, by, dx, dy)
    return d1 * d2 <= 0.0 and d3 * d4 <= 0.0 and (d1, d2) != (0.0, 0.0)
