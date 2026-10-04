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
# Steps a label slides along each axis when no candidate is free.
SLIDE_STEPS = 6

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
        elif best_cost:
            best = self._slide(best, best_cost)
        self.reserve(best)
        return best

    def _slide(self, rect: pygame.Rect, cost: int) -> pygame.Rect:
        """Step a colliding label away from its best spot, a label height
        or width at a time.  Candidates around a point far off the chart all
        clamp to the same spot on its edge; sliding along (and off) that edge
        sets such edge labels beside each other instead of on top."""
        step_y, step_x = rect.h + GAP_PX, rect.w + GAP_PX
        best, best_cost = rect, cost
        for k in range(1, SLIDE_STEPS + 1):
            for dx, dy in ((0, k * step_y), (0, -k * step_y),
                           (-k * step_x, 0), (k * step_x, 0)):
                moved = self._clamp(rect.x + dx, rect.y + dy, rect.w, rect.h)
                moved_cost = self._overlap(moved)
                if moved_cost == 0:
                    return moved
                if moved_cost < best_cost:
                    best, best_cost = moved, moved_cost
        return best


def reserve_segment(start, end, width: int = 6, step: int = 16) -> None:
    """Keep later labels of the active field off a drawn line (a motion
    vector), as a chain of small boxes along it."""
    field = active()
    if field is None:
        return
    length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
    pieces = max(1, int(length // step))
    for index in range(pieces + 1):
        t = index / pieces
        x = start[0] + (end[0] - start[0]) * t
        y = start[1] + (end[1] - start[1]) * t
        field.reserve(pygame.Rect(int(x - width / 2), int(y - width / 2), width, width))


def active() -> LabelField | None:
    return _ACTIVE[-1] if _ACTIVE else None


@contextmanager
def label_scope(bounds, field: LabelField | None = None):
    """Labels drawn inside this block avoid each other within ``bounds``.

    Passing the ``field`` of an earlier scope continues it, so an overlay
    drawn over a finished chart (the weapons station's target marks) steps
    aside from the chart's labels as well."""
    if field is None or pygame.Rect(bounds) != field.bounds:
        field = LabelField(bounds)
    _ACTIVE.append(field)
    try:
        yield field
    finally:
        _ACTIVE.pop()


def free_rect(size, candidates, bounds) -> pygame.Rect:
    """Place a label of ``size``: through the active field when there is
    one, otherwise its first candidate kept inside ``bounds``."""
    field = active()
    if field is not None:
        return field.place(size, candidates)
    return LabelField(bounds).place(size, candidates[:1])


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


def blit_line(surface, text, rect, color, size: int = 12) -> None:
    """``layout.blit_line`` for a chart label: inside a label scope the box
    shrinks to the text and steps aside from labels placed before it."""
    from src.core.i18n import localize
    from src.ui import layout
    x, y, w, h = (int(value) for value in rect)
    field = active()
    if field is not None:
        width = min(w, layout.text_width(layout.font(size), localize(text)) + 2)
        x, y = field.place((width, h), around((x, y), (width, h))).topleft
        w = width
    layout.blit_line(surface, text, (x, y, w, h), color, size=size)
