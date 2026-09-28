"""The frigate's autopilot route: waypoints the helm steers through in turn.

A route is up to ``MAX_WAYPOINTS`` chart points (nautical miles). While it is
active the helm steers the course to the current waypoint and moves on when
the ship comes within ``ARRIVAL_NM`` of it; after the last one the route ends
and the ship holds its course. Search patterns are generated as routes from
the ship's own position and course. Pure and deterministic: no randomness, no
wall clock; the whole state is the saved ``route`` block.
"""

from __future__ import annotations

import math

MAX_WAYPOINTS = 8
ARRIVAL_NM = 0.3
PATTERNS = ("zigzag", "square")
ZIGZAG_LEG_NM = 3.0
ZIGZAG_ANGLE_DEG = 45.0
SQUARE_STEP_NM = 1.0
ROUTE_KINDS = ("manual",) + PATTERNS


def bearing_to(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def _step(x: float, y: float, course: float, distance: float) -> tuple[float, float]:
    rad = math.radians(course)
    return x + distance * math.sin(rad), y - distance * math.cos(rad)


def pattern_points(kind: str, x: float, y: float, course: float) -> list:
    """Waypoints of a search pattern started at (x, y) on ``course``."""
    points = []
    if kind == "zigzag":
        # Legs alternately 45° right and left of the base course.
        for leg in range(MAX_WAYPOINTS):
            heading = course + (ZIGZAG_ANGLE_DEG if leg % 2 == 0 else -ZIGZAG_ANGLE_DEG)
            x, y = _step(x, y, heading, ZIGZAG_LEG_NM)
            points.append((x, y))
    elif kind == "square":
        # Expanding square: 1, 1, 2, 2, 3, 3 ... steps, turning right.
        heading = course
        for leg in range(MAX_WAYPOINTS):
            x, y = _step(x, y, heading, SQUARE_STEP_NM * (leg // 2 + 1))
            points.append((x, y))
            heading = (heading + 90.0) % 360.0
    else:
        raise ValueError(f"unknown pattern {kind!r}")
    return points


class Route:
    """Ordered waypoints, the current one and how the route was made."""

    __slots__ = ("points", "index", "kind")

    def __init__(self, points=(), index: int = 0, kind: str = "manual"):
        self.points = [(float(x), float(y)) for x, y in points]
        self.index = int(index)
        self.kind = kind

    @property
    def active(self) -> bool:
        return 0 <= self.index < len(self.points)

    def current(self):
        return self.points[self.index] if self.active else None

    def remaining(self) -> list:
        return self.points[self.index:] if self.active else []

    def clear(self) -> None:
        self.points = []
        self.index = 0
        self.kind = "manual"

    def add(self, x: float, y: float) -> bool:
        """Append a manual waypoint; a finished or pattern route starts anew."""
        if not self.active or self.kind != "manual":
            self.clear()
        if len(self.points) >= MAX_WAYPOINTS:
            return False
        self.points.append((float(x), float(y)))
        return True

    def start_pattern(self, kind: str, x: float, y: float, course: float) -> None:
        self.points = pattern_points(kind, x, y, course)
        self.index = 0
        self.kind = kind

    def steer(self, x: float, y: float):
        """Course to the current waypoint, advancing past reached ones.

        Returns ``(course, reached)``: ``course`` is None once the route has
        ended; ``reached`` counts the waypoints passed in this call."""
        reached = 0
        while self.active:
            wx, wy = self.points[self.index]
            if math.hypot(wx - x, wy - y) > ARRIVAL_NM:
                return bearing_to(x, y, wx, wy), reached
            self.index += 1
            reached += 1
        return None, reached

    def serialize(self) -> dict:
        return {"points": [[x, y] for x, y in self.points], "index": self.index,
                "kind": self.kind}

    @staticmethod
    def valid_state(data, world_size_nm: float) -> bool:
        if not isinstance(data, dict) or set(data) != {"points", "index", "kind"}:
            return False
        points, index, kind = data["points"], data["index"], data["kind"]
        if kind not in ROUTE_KINDS or type(index) is not int:
            return False
        if not isinstance(points, list) or len(points) > MAX_WAYPOINTS:
            return False
        if not 0 <= index <= len(points):
            return False
        for point in points:
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(value) not in (int, float) or isinstance(value, bool)
                           or not math.isfinite(value)
                           or not -world_size_nm <= value <= 2.0 * world_size_nm
                           for value in point)):
                return False
        return True

    @classmethod
    def restore(cls, data) -> "Route":
        return cls(((x, y) for x, y in data["points"]), data["index"], data["kind"])
