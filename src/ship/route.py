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

# --- chart safety -----------------------------------------------------------
# The autopilot plans on the chart (known geography): charted depth shoaled
# by charted rocks and wrecks, never on the live tide or hidden entities.
MAX_ROUTE_POINTS = 16          # stored points: waypoints plus inserted detours
HAZARD_STEP_NM = 0.1
HAZARD_BEAM_NM = 0.1           # samples either side of the track line
ROUTE_DEPTH_MARGIN_M = 2.0     # under-keel margin on top of the hull minimum
DETOUR_OFFSETS_NM = (0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0)
DETOUR_DEPTH = 2               # nested detours per leg at most
WATCH_PERIOD_S = 1.0           # look-ahead cadence while a route runs
WATCH_AHEAD_S = 120.0          # look-ahead distance in time at current speed
WATCH_MIN_NM = 0.5


def leg_hazard(depth_at, x0: float, y0: float, x1: float, y1: float,
               min_depth_m: float):
    """Fraction (0..1) along the leg of the first sample whose chart depth is
    below ``min_depth_m`` (centre line or either beam line), else None."""
    length = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(math.ceil(length / HAZARD_STEP_NM)))
    if length > 0.0:
        px, py = -(y1 - y0) / length, (x1 - x0) / length
    else:
        px = py = 0.0
    for index in range(1, steps + 1):
        t = index / steps
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        for side in (0.0, HAZARD_BEAM_NM, -HAZARD_BEAM_NM):
            if depth_at(x + px * side, y + py * side) < min_depth_m:
                return t
    return None


def plan_detour(depth_at, x0: float, y0: float, x1: float, y1: float,
                min_depth_m: float, size_nm: float, depth: int = DETOUR_DEPTH):
    """Detour points that take a leg around the charted hazard on it.

    Candidates stand off the first unsafe point, square to the leg, nearest
    first and port before starboard; a candidate counts when both new legs
    are clear (or clear after one more nested detour). Returns the inserted
    points in order, [] for a clear leg, or None when no detour is found."""
    t = leg_hazard(depth_at, x0, y0, x1, y1, min_depth_m)
    if t is None:
        return []
    if depth <= 0:
        return None
    length = math.hypot(x1 - x0, y1 - y0)
    if length <= 0.0:
        return None
    hx, hy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
    px, py = -(y1 - y0) / length, (x1 - x0) / length
    for offset in DETOUR_OFFSETS_NM:
        for side in (-1.0, 1.0):
            cx, cy = hx + px * offset * side, hy + py * offset * side
            if not (0.0 <= cx <= size_nm and 0.0 <= cy <= size_nm):
                continue
            if depth_at(cx, cy) < min_depth_m:
                continue
            first = plan_detour(depth_at, x0, y0, cx, cy, min_depth_m, size_nm, depth - 1)
            if first is None:
                continue
            second = plan_detour(depth_at, cx, cy, x1, y1, min_depth_m, size_nm, depth - 1)
            if second is None:
                continue
            return first + [(cx, cy)] + second
    return None


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

    def add(self, x: float, y: float, detour=()) -> bool:
        """Append a manual waypoint (after its ``detour`` points); a finished
        or pattern route starts anew. A waypoint is taken while the route
        holds fewer than ``MAX_WAYPOINTS`` points; detours may stretch it to
        ``MAX_ROUTE_POINTS``."""
        if not self.active or self.kind != "manual":
            self.clear()
        if (len(self.points) >= MAX_WAYPOINTS
                or len(self.points) + len(detour) + 1 > MAX_ROUTE_POINTS):
            return False
        self.points.extend((float(px), float(py)) for px, py in detour)
        self.points.append((float(x), float(y)))
        return True

    def insert_detour(self, points) -> bool:
        """Put detour points before the current waypoint."""
        if not self.active or len(self.points) + len(points) > MAX_ROUTE_POINTS:
            return False
        self.points[self.index:self.index] = [(float(x), float(y)) for x, y in points]
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
        if not isinstance(points, list) or len(points) > MAX_ROUTE_POINTS:
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
