"""Cell index of a landmass's coast edges (pure, built once per landmass).

The finer 1:10m coast has several thousand edges per mainland. Point, line
and circle queries only look at the edges registered in the cells they
touch; an edge is registered in every cell its bounding box overlaps, so a
query sees every edge that can matter and computes exactly what the full
scan computed (candidates are always visited in edge order).
"""

import math

CELL_NM = 4.0
# Queries widen their cells by this margin, so exact touches and the
# geometry epsilon at a cell border still find their edge.
_MARGIN = 1e-6


class EdgeIndex:
    __slots__ = ("cells", "rows", "count", "extent")

    def __init__(self, points):
        self.count = len(points)
        cells = {}
        rows = {}
        for index in range(self.count):
            x1, y1 = points[index]
            x2, y2 = points[(index + 1) % self.count]
            c0, c1 = _cell(min(x1, x2) - _MARGIN), _cell(max(x1, x2) + _MARGIN)
            r0, r1 = _cell(min(y1, y2) - _MARGIN), _cell(max(y1, y2) + _MARGIN)
            for row in range(r0, r1 + 1):
                rows.setdefault(row, []).append(index)
                for column in range(c0, c1 + 1):
                    cells.setdefault((column, row), []).append(index)
        self.cells = {key: tuple(value) for key, value in cells.items()}
        columns = [key[0] for key in cells] or [0]
        row_keys = [key[1] for key in cells] or [0]
        self.extent = (min(columns), min(row_keys), max(columns), max(row_keys))
        self.rows = {key: tuple(value) for key, value in rows.items()}

    def row_edges(self, y):
        """Every edge whose y range can contain ``y`` (the ray-cast row)."""
        return self.rows.get(_cell(y), ())

    def box_edges(self, left, top, right, bottom):
        """Edges whose cells overlap a box, in edge order."""
        c0, c1 = _cell(left - _MARGIN), _cell(right + _MARGIN)
        r0, r1 = _cell(top - _MARGIN), _cell(bottom + _MARGIN)
        if (c1 - c0 + 1) * (r1 - r0 + 1) > 4 * len(self.cells) + 16:
            return range(self.count)
        found = set()
        for row in range(r0, r1 + 1):
            for column in range(c0, c1 + 1):
                found.update(self.cells.get((column, row), ()))
        return sorted(found)

    def segment_edges(self, first, second):
        """Edges whose cells the segment ``first``-``second`` passes, in order."""
        x1, y1 = first
        x2, y2 = second
        dy = y2 - y1
        r0, r1 = _cell(min(y1, y2) - _MARGIN), _cell(max(y1, y2) + _MARGIN)
        found = set()
        for row in range(r0, r1 + 1):
            if abs(dy) <= 1e-12:
                xa, xb = x1, x2
            else:
                low, high = row * CELL_NM - _MARGIN, (row + 1) * CELL_NM + _MARGIN
                ta = max(0.0, min(1.0, (low - y1) / dy))
                tb = max(0.0, min(1.0, (high - y1) / dy))
                xa, xb = x1 + (x2 - x1) * ta, x1 + (x2 - x1) * tb
            for column in range(_cell(min(xa, xb) - _MARGIN), _cell(max(xa, xb) + _MARGIN) + 1):
                found.update(self.cells.get((column, row), ()))
        return sorted(found)


def _cell(value):
    return math.floor(value / CELL_NM)


def nearest_distance(index, points, x, y, best, distance):
    """``min(best, distance to every edge)``, visiting the occupied cells
    nearest first until no unseen edge can be nearer (exact: the same
    arithmetic on a subset that contains the nearest edge)."""
    count = index.count
    bounds = []
    for (column, row) in index.cells:
        left, top = column * CELL_NM, row * CELL_NM
        dx = max(left - x, 0.0, x - left - CELL_NM)
        dy = max(top - y, 0.0, y - top - CELL_NM)
        bound = math.hypot(dx, dy)
        if bound <= best:
            bounds.append((bound, column, row))
    bounds.sort()
    seen = set()
    for bound, column, row in bounds:
        if bound > best:
            break
        for edge in index.cells[(column, row)]:
            if edge not in seen:
                seen.add(edge)
                value = distance(x, y, points[edge], points[(edge + 1) % count])
                if value < best:
                    best = value
    return best
