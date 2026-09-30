"""Chart label placement that keeps labels from covering each other.

A chart opens a :func:`label_scope` while it draws; every label placed in it
takes the first candidate position that neither leaves the chart nor
overlaps a label (or a reserved symbol box) placed before it.  When every
candidate collides, the one with the least overlap wins, so a label is never
dropped.  Placement is pure screen geometry: it depends only on the order of
the calls and the text sizes, never on wall clock or simulation state.
"""

from __future__ import annotations

from contextlib import contextmanager

import pygame

# At most this many rectangles are remembered per chart (bounded work per
# frame on the uConsole; later labels then fall back to their first choice).
MAX_RECTS = 160
# Gap kept between two labels, in pixels.
GAP_PX = 2

_ACTIVE: list["LabelField"] = []


class LabelField:
    """Occupied label rectangles of one chart draw."""

    def __init__(self, bounds) -> None:
        self.bounds = pygame.Rect(bounds)
        self.rects: list[pygame.Rect] = []

    def reserve(self, rect) -> None:
        """Keep later labels off ``rect`` (a symbol or fixed text)."""
        if len(self.rects) < MAX_RECTS:
            self.rects.append(pygame.Rect(rect))

    def _clamp(self, x: float, y: float, width: int, height: int) -> pygame.Rect:
        b = self.bounds
        x = min(max(int(x), b.x + 2), max(b.x + 2, b.right - width - 2))
        y = min(max(int(y), b.y + 2), max(b.y + 2, b.bottom - height - 2))
        return pygame.Rect(x, y, width, height)

    def _overlap(self, rect: pygame.Rect) -> int:
        padded = rect.inflate(GAP_PX * 2, GAP_PX * 2)
        total = 0
        for other in self.rects:
            clip = padded.clip(other)
            total += clip.w * clip.h
        return total

    def place(self, size, candidates) -> pygame.Rect:
        """First free candidate (top-left points) for a label of ``size``."""
        width, height = int(size[0]), int(size[1])
        best, best_cost = None, None
        for x, y in candidates:
            rect = self._clamp(x, y, width, height)
            cost = self._overlap(rect)
            if cost == 0:
                best = rect
                break
            if best_cost is None or cost < best_cost:
                best, best_cost = rect, cost
        if best is None:
            best = self._clamp(self.bounds.x, self.bounds.y, width, height)
        self.reserve(best)
        return best


def active() -> LabelField | None:
    return _ACTIVE[-1] if _ACTIVE else None


@contextmanager
def label_scope(bounds):
    """Labels drawn inside this block avoid each other within ``bounds``."""
    field = LabelField(bounds)
    _ACTIVE.append(field)
    try:
        yield field
    finally:
        _ACTIVE.pop()


def around(pos, size, symbol_gap: int = 14) -> list[tuple[int, int]]:
    """Candidate top-left points around a label's preferred position.

    ``pos`` is the preferred top-left (to the right of and above the symbol);
    the others step down and up, then mirror to the symbol's left side.
    """
    x, y = int(pos[0]), int(pos[1])
    width, height = int(size[0]), int(size[1])
    step = height + GAP_PX
    left = x - width - 2 * symbol_gap
    return [(x, y), (x, y + step), (x, y - step), (left, y), (left, y + step),
            (left, y - step), (x, y + 2 * step), (x, y - 2 * step),
            (left, y + 2 * step), (left, y - 2 * step)]


def along(origin, bearing_unit, distances, size, offset=(6, -8)) -> list[tuple[int, int]]:
    """Candidates sliding outward along a bearing line (bearing-only labels)."""
    ox, oy = origin
    ux, uy = bearing_unit
    points = []
    for distance in distances:
        px, py = ox + ux * distance, oy + uy * distance
        points.append((int(px) + offset[0], int(py) + offset[1]))
        points.append((int(px) - int(size[0]) - offset[0], int(py) + offset[1]))
    return points
