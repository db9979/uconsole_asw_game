"""The frigate's autopilot route: waypoints the helm steers through in turn.

A route is up to ``MAX_WAYPOINTS`` chart points (nautical miles). While it is
active the helm steers the course to the current waypoint and moves on when
the ship comes within ``ARRIVAL_NM`` of it; after the last one the route ends
and the ship holds its course. Search patterns are generated as routes from
the ship's own position and course. Pure and deterministic: no randomness, no
wall clock; the whole state is the saved ``route`` block.
"""

from __future__ import annotations

import heapq
import math
from src.physics.geo import bearing_deg as bearing_to

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
# Chart path search when a stand-off detour finds no way (a channel, a bay,
# a long coast): a bounded grid search on the chart, straightened afterwards.
PATH_GRID_CELLS = 96           # grid cells along the longer side at most
PATH_CELL_MIN_NM = 0.2
PATH_PAD_NM = (4.0, 30.0, 80.0)  # search boxes around the leg, small first


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


def plan_leg(depth_at, x0: float, y0: float, x1: float, y1: float,
             min_depth_m: float, size_nm: float, max_points: int = MAX_ROUTE_POINTS):
    """Points to insert before the leg's end so the whole leg stays in safe
    chart water: a stand-off detour when one works, else a chart path search.
    [] for a clear leg; None when neither finds a way within ``max_points``."""
    detour = plan_detour(depth_at, x0, y0, x1, y1, min_depth_m, size_nm, depth=1)
    if detour is not None and len(detour) <= max_points:
        return detour
    path = find_path(depth_at, x0, y0, x1, y1, min_depth_m, size_nm)
    if path is None or len(path) > max_points:
        return None
    return path


def find_path(depth_at, x0: float, y0: float, x1: float, y1: float,
              min_depth_m: float, size_nm: float):
    """Chart path from (x0, y0) to (x1, y1): A* over a grid of chart
    soundings in a box around the leg, straightened by line of sight. Returns
    the turning points between start and end (every leg checked clear with
    ``leg_hazard``), [] for a clear leg, or None when no path is found.
    Pure and deterministic: fixed grid, integer tie-breaks."""
    if leg_hazard(depth_at, x0, y0, x1, y1, min_depth_m) is None:
        return []
    if depth_at(x1, y1) < min_depth_m:
        return None
    for pad in PATH_PAD_NM:
        pad = max(pad, 0.25 * math.hypot(x1 - x0, y1 - y0))
        path = _grid_path(depth_at, x0, y0, x1, y1, min_depth_m, size_nm, pad)
        if path is not None:
            return path
    return None


def _grid_path(depth_at, x0, y0, x1, y1, min_depth_m, size_nm, pad):
    left = max(0.0, min(x0, x1) - pad)
    top = max(0.0, min(y0, y1) - pad)
    right = min(size_nm, max(x0, x1) + pad)
    bottom = min(size_nm, max(y0, y1) + pad)
    cell = max(PATH_CELL_MIN_NM, max(right - left, bottom - top) / PATH_GRID_CELLS)
    cols = max(1, int(math.ceil((right - left) / cell)))
    rows = max(1, int(math.ceil((bottom - top) / cell)))

    def centre(c, r):
        return left + (c + 0.5) * cell, top + (r + 0.5) * cell

    def index_of(x, y):
        return (min(cols - 1, max(0, int((x - left) / cell))),
                min(rows - 1, max(0, int((y - top) / cell))))

    safe = {}

    def open_cell(c, r):
        key = r * cols + c
        if key not in safe:
            safe[key] = depth_at(*centre(c, r)) >= min_depth_m
        return safe[key]

    start, goal = index_of(x0, y0), index_of(x1, y1)
    moves = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, math.sqrt(2.0)), (1, -1, math.sqrt(2.0)),
             (-1, 1, math.sqrt(2.0)), (-1, -1, math.sqrt(2.0)))

    def estimate(c, r):
        dc, dr = abs(c - goal[0]), abs(r - goal[1])
        return max(dc, dr) + (math.sqrt(2.0) - 1.0) * min(dc, dr)

    best = {start: 0.0}
    came = {}
    heap = [(estimate(*start), 0, start)]
    order = 0
    while heap:
        _, _, node = heapq.heappop(heap)
        if node == goal:
            break
        c, r = node
        base = best[node]
        for dc, dr, cost in moves:
            nc, nr = c + dc, r + dr
            if not (0 <= nc < cols and 0 <= nr < rows):
                continue
            nxt = (nc, nr)
            if nxt != goal and not open_cell(nc, nr):
                continue
            if dc and dr and not (open_cell(c + dc, r) and open_cell(c, r + dr)):
                continue            # no corner cutting past a shoal cell
            value = base + cost
            if value < best.get(nxt, math.inf):
                best[nxt] = value
                came[nxt] = node
                order += 1
                heapq.heappush(heap, (value + estimate(nc, nr), order, nxt))
    else:
        return None
    if goal not in best:
        return None
    cells = [goal]
    while cells[-1] != start:
        cells.append(came[cells[-1]])
    cells.reverse()
    nodes = [(x0, y0)] + [centre(c, r) for c, r in cells[1:-1]] + [(x1, y1)]
    # Line of sight: from each kept point jump as far along the nodes as a
    # clear leg reaches (galloping, then bisection: few leg checks).
    def clear(a, b):
        return leg_hazard(depth_at, *nodes[a], *nodes[b], min_depth_m) is None

    kept, i, last = [], 0, len(nodes) - 1
    while i < last:
        if clear(i, last):
            break
        good, step = i, 1
        while good + step < last and clear(i, good + step):
            good += step
            step *= 2
        low, high = good, min(last, good + step)
        while high - low > 1:
            middle = (low + high) // 2
            if clear(i, middle):
                low = middle
            else:
                high = middle
        if low == i:
            return None
        kept.append(nodes[low])
        i = low
    return kept


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
