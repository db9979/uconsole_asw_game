"""Shared operator plot layer: marks, rulers, bearing lines, circles and
dead-reckoning lines on the chart (pure, bounded, strictly validated).

Every object is the crew's own drawing. The helpers only do chart geometry
(bearing/distance, a point moved along a course, closest point of approach
to own ship); nothing reads a contact or any hidden state, and the layer
never feeds the simulation. It is saved (save v14) and shared by all
stations and Remote Crew clients.
"""

from __future__ import annotations

import math

from src.core import config

KINDS = ("mark", "ruler", "bearing", "circle", "dr")
MAX_OBJECTS = 64
MAX_LABEL = 24
COORD_LIMIT_NM = 1_000.0
MAX_RADIUS_NM = 200.0
MAX_SPEED_KN = 60.0
MAX_ID = 2 ** 31 - 1

_FIELDS = {
    "mark": {"id", "kind", "label", "t", "x", "y"},
    "ruler": {"id", "kind", "label", "t", "x", "y", "x2", "y2"},
    "bearing": {"id", "kind", "label", "t", "x", "y", "bearing"},
    "circle": {"id", "kind", "label", "t", "x", "y", "radius_nm"},
    "dr": {"id", "kind", "label", "t", "x", "y", "course", "speed_kn"},
}


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _coord(value) -> bool:
    return _finite(value) and -COORD_LIMIT_NM <= value <= COORD_LIMIT_NM


def command_fields(kind) -> frozenset:
    """Exact parameter keys of an add command (no id/time: the host sets them)."""
    return frozenset(_FIELDS[kind] - {"id", "t"})


def valid_label(label) -> bool:
    return type(label) is str and len(label) <= MAX_LABEL and label.isprintable()


def default_label(kind: str, object_id: int) -> str:
    """Language-neutral chart label: kind letter plus the object number."""
    return f"{'MRBCD'[KINDS.index(kind)]}{object_id}"


def valid_object(item) -> bool:
    """Strict schema: exact keys per kind, finite bounded values."""
    if not isinstance(item, dict) or item.get("kind") not in KINDS:
        return False
    kind = item["kind"]
    if set(item) != _FIELDS[kind]:
        return False
    if type(item["id"]) is not int or not 1 <= item["id"] <= MAX_ID:
        return False
    if not valid_label(item["label"]):
        return False
    if not _finite(item["t"]) or item["t"] < 0:
        return False
    if not (_coord(item["x"]) and _coord(item["y"])):
        return False
    if kind == "ruler":
        return _coord(item["x2"]) and _coord(item["y2"])
    if kind == "bearing":
        return _finite(item["bearing"]) and 0.0 <= item["bearing"] < 360.0
    if kind == "circle":
        return _finite(item["radius_nm"]) and 0.0 < item["radius_nm"] <= MAX_RADIUS_NM
    if kind == "dr":
        return (_finite(item["course"]) and 0.0 <= item["course"] < 360.0
                and _finite(item["speed_kn"]) and 0.0 <= item["speed_kn"] <= MAX_SPEED_KN)
    return True


def bearing_distance(x1, y1, x2, y2):
    """True bearing (deg) and distance (NM) from point 1 to point 2."""
    dx, dy = x2 - x1, y2 - y1
    return math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy)


def dr_position(item, t: float):
    """Where a dead-reckoning line puts its point at time ``t``."""
    step = config.kn_to_nm_per_s(item["speed_kn"]) * (t - item["t"])
    course = math.radians(item["course"])
    return item["x"] + step * math.sin(course), item["y"] - step * math.cos(course)


def cpa(item, t: float, own_x, own_y, own_course, own_speed_kn):
    """Closest point of approach between a DR line and own ship.

    Both move straight on from time ``t``. Returns ``(distance_nm,
    seconds_from_now)``; a CPA already passed gives time 0.
    """
    px, py = dr_position(item, t)
    vx = config.kn_to_nm_per_s(item["speed_kn"]) * math.sin(math.radians(item["course"]))
    vy = -config.kn_to_nm_per_s(item["speed_kn"]) * math.cos(math.radians(item["course"]))
    ox = config.kn_to_nm_per_s(own_speed_kn) * math.sin(math.radians(own_course))
    oy = -config.kn_to_nm_per_s(own_speed_kn) * math.cos(math.radians(own_course))
    rx, ry = px - own_x, py - own_y
    wx, wy = vx - ox, vy - oy
    speed2 = wx * wx + wy * wy
    seconds = 0.0 if speed2 <= 1e-12 else max(0.0, -(rx * wx + ry * wy) / speed2)
    return math.hypot(rx + wx * seconds, ry + wy * seconds), seconds


class PlotLayer:
    """Bounded list of plot objects with a monotonic id counter."""

    def __init__(self):
        self.objects: list[dict] = []
        self.next_id = 1

    def add(self, item: dict):
        item = dict(item, id=self.next_id)
        if item.get("kind") in KINDS and not item.get("label"):
            item["label"] = default_label(item["kind"], self.next_id)
        if not valid_object(item):
            return "invalid_value"
        if len(self.objects) >= MAX_OBJECTS:
            return "full"
        item = {key: (float(value) if type(value) is int and key != "id" else value)
                for key, value in item.items()}
        self.objects.append(item)
        self.next_id = min(MAX_ID, self.next_id + 1)
        return item["id"]

    def remove(self, object_id) -> bool:
        before = len(self.objects)
        self.objects = [item for item in self.objects if item["id"] != object_id]
        return len(self.objects) != before

    def relabel(self, object_id, label: str) -> bool:
        if not valid_label(label):
            return False
        for item in self.objects:
            if item["id"] == object_id:
                item["label"] = label or default_label(item["kind"], item["id"])
                return True
        return False

    def clear(self) -> None:
        self.objects = []

    def nearest(self, x: float, y: float, within_nm: float):
        """The object whose anchor point lies closest to (x, y)."""
        best, best_d = None, within_nm
        for item in self.objects:
            points = [(item["x"], item["y"])]
            if item["kind"] == "ruler":
                points.append((item["x2"], item["y2"]))
            for px, py in points:
                d = math.hypot(px - x, py - y)
                if d <= best_d:
                    best, best_d = item, d
        return best

    def to_save(self) -> dict:
        return {"next_id": self.next_id, "objects": [dict(item) for item in self.objects]}

    @staticmethod
    def valid_save(data) -> bool:
        if not isinstance(data, dict) or set(data) != {"next_id", "objects"}:
            return False
        objects = data["objects"]
        if (type(data["next_id"]) is not int or not 1 <= data["next_id"] <= MAX_ID
                or not isinstance(objects, list) or len(objects) > MAX_OBJECTS
                or not all(valid_object(item) for item in objects)):
            return False
        ids = [item["id"] for item in objects]
        below = all(i < data["next_id"] for i in ids) or data["next_id"] == MAX_ID
        return len(set(ids)) == len(ids) and below

    @classmethod
    def from_save(cls, data) -> "PlotLayer":
        layer = cls()
        layer.next_id = data["next_id"]
        layer.objects = [dict(item) for item in data["objects"]]
        return layer
