"""Chart label placement that keeps labels from covering each other.

A chart opens a :func:`label_scope` while it draws; every label placed in it
takes the first candidate position that neither leaves the chart nor
overlaps a label, a reserved symbol box or a reserved line (a motion vector,
a trail, a bearing line) placed before it.  When every candidate collides,
the one with the least overlap wins, so a label is never dropped.  A chart
that opens its scope with ``deferred=True`` draws its labels only after all
its symbols and lines, so no label depends on drawing order.  Placement is
screen geometry: it depends on the call order, the text sizes and, for a
label drawn with a ``key``, on the spot that label took last frame (it keeps
that spot while it stays free, so labels do not jump between frames); never
on wall clock or simulation state.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from contextlib import contextmanager

import pygame

# At most this many rectangles are remembered per chart (bounded work per
# frame on the uConsole; later labels then fall back to their first choice).
MAX_RECTS = 160
# Gap kept between two labels, in pixels.
GAP_PX = 2
# Steps a label slides along each axis when no candidate is free.
SLIDE_STEPS = 6
# At most this many reserved lines per chart (vectors, trail pieces, bearing
# lines) and their weight: a pixel of line covered costs like this many
# pixels of covered label.
MAX_LINES = 320
LINE_COST = 6
# Spots remembered for keyed labels (a label keeps its spot next frame).
MEMORY_MAX = 512
# A candidate this close to last frame's spot is the same spot.
NEAR_PX = 8
_MEMORY: OrderedDict = OrderedDict()

_ACTIVE: list["LabelField"] = []


class LabelField:
    """Occupied label rectangles of one chart draw."""

    def __init__(self, bounds) -> None:
        self.bounds = pygame.Rect(bounds)
        self.rects: list[pygame.Rect] = []
        self.line_boxes: list[pygame.Rect] = []
        self.lines: list[tuple] = []
        self.pending: list | None = None

    def reserve_line(self, start, end, width: int = 4) -> None:
        """Keep later labels off a drawn line (a motion vector, a trail
        piece, a bearing line)."""
        if len(self.lines) >= MAX_LINES:
            return
        a = (int(round(start[0])), int(round(start[1])))
        b = (int(round(end[0])), int(round(end[1])))
        box = pygame.Rect(min(a[0], b[0]), min(a[1], b[1]),
                          abs(a[0] - b[0]) + 1, abs(a[1] - b[1]) + 1)
        box = box.inflate(width, width)
        if not box.colliderect(self.bounds):
            return
        self.line_boxes.append(box)
        self.lines.append((a, b, width))

    def reserve(self, rect) -> None:
        """Keep later labels off ``rect`` (a symbol or fixed text)."""
        if len(self.rects) < MAX_RECTS:
            self.rects.append(pygame.Rect(rect))

    def is_free(self, rect) -> bool:
        """Whether ``rect`` keeps clear of every label placed so far."""
        return self._overlap(pygame.Rect(rect)) == 0

    def _clamp(self, x: float, y: float, width: int, height: int) -> pygame.Rect:
        b = self.bounds
        x = min(max(int(x), b.x + 2), max(b.x + 2, b.right - width - 2))
        y = min(max(int(y), b.y + 2), max(b.y + 2, b.bottom - height - 2))
        return pygame.Rect(x, y, width, height)

    def _overlap(self, rect: pygame.Rect) -> int:
        padded = rect.inflate(GAP_PX * 2, GAP_PX * 2)
        total = 0
        for index in padded.collidelistall(self.rects):
            clip = padded.clip(self.rects[index])
            total += clip.w * clip.h
        for index in padded.collidelistall(self.line_boxes):
            a, b, width = self.lines[index]
            hit = padded.inflate(width, width).clipline(a, b)
            if hit:
                (x1, y1), (x2, y2) = hit
                total += int((math.hypot(x2 - x1, y2 - y1) + 1) * LINE_COST)
        return total

    def place(self, size, candidates, key=None) -> pygame.Rect:
        """First free candidate (top-left points) for a label of ``size``.

        With a ``key`` the candidate this label took last time is tried
        first, so a label stays where it was while that spot stays free."""
        width, height = int(size[0]), int(size[1])
        candidates = list(candidates)
        best, best_cost, chosen = None, None, None
        order = list(range(len(candidates)))
        last = _MEMORY.get(key) if key is not None else None
        if last is not None:
            first = _remembered(last, candidates, width, height)
            if first is not None:
                order.remove(first)
                order.insert(0, first)
        for index in order:
            x, y = candidates[index]
            rect = self._clamp(x, y, width, height)
            cost = self._overlap(rect)
            if cost == 0:
                best, best_cost, chosen = rect, 0, index
                break
            if best_cost is None or cost < best_cost:
                best, best_cost, chosen = rect, cost, index
        if key is not None and chosen is not None:
            _MEMORY[key] = (chosen, best.centerx, best.centery)
            _MEMORY.move_to_end(key)
            while len(_MEMORY) > MEMORY_MAX:
                _MEMORY.popitem(last=False)
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


def _remembered(last, candidates, width: int, height: int) -> int | None:
    """The candidate to try first for a keyed label: the one whose box lies
    where the label sat last frame (its symbol moves a few pixels at most),
    else the same candidate as last time.  The spot counts, not the index:
    a contact's course estimate may swing round, which turns the
    course-relative candidates about and would flip the label across its
    symbol (the convoy label jumping from above to below, 2026-10-06)."""
    index, cx, cy = last
    best, best_d = None, NEAR_PX
    for i, (x, y) in enumerate(candidates):
        d = math.hypot(x + width / 2 - cx, y + height / 2 - cy)
        if d <= best_d:
            best, best_d = i, d
    if best is not None:
        return best
    return index if index < len(candidates) else None


def reserve_segment(start, end, width: int = 4) -> None:
    """Keep later labels of the active field off a drawn line (a motion
    vector, a trail piece, a bearing line)."""
    field = active()
    if field is not None:
        field.reserve_line(start, end, width)


def reserve_box(rect) -> None:
    """Keep later labels of the active field off a symbol."""
    field = active()
    if field is not None:
        field.reserve(rect)


def later(draw) -> None:
    """Run ``draw`` (a label) now, or, in a deferred scope, once the chart's
    symbols and lines are all drawn and reserved."""
    field = active()
    if field is not None and field.pending is not None:
        field.pending.append(draw)
    else:
        draw()


def active() -> LabelField | None:
    return _ACTIVE[-1] if _ACTIVE else None


@contextmanager
def label_scope(bounds, field: LabelField | None = None, deferred: bool = False):
    """Labels drawn inside this block avoid each other within ``bounds``.

    Passing the ``field`` of an earlier scope continues it, so an overlay
    drawn over a finished chart (the weapons station's target marks) steps
    aside from the chart's labels as well.  In a ``deferred`` scope the
    labels handed to :func:`later` are placed at its end, after every symbol
    and line of the chart reserved its place."""
    if field is None or pygame.Rect(bounds) != field.bounds:
        field = LabelField(bounds)
    outer = field.pending
    if deferred and outer is None:
        field.pending = []
    _ACTIVE.append(field)
    try:
        yield field
        if deferred and outer is None:
            pending, field.pending = field.pending, None
            for draw in pending:
                draw()
    finally:
        field.pending = outer
        _ACTIVE.pop()


def free_rect(size, candidates, bounds, key=None) -> pygame.Rect:
    """Place a label of ``size``: through the active field when there is
    one, otherwise its first candidate kept inside ``bounds``."""
    field = active()
    if field is not None:
        return field.place(size, candidates, key)
    return LabelField(bounds).place(size, list(candidates)[:1])


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


def beside(center, size, course_deg, gap: int = 10) -> list[tuple[int, int]]:
    """Candidate top-left points for a moving contact's label: first abeam
    of its course (starboard, then port), clear of its motion vector ahead
    and its trail astern; then the quarters and bows, then the usual ring
    around the symbol.  Without a course the label sits right of it."""
    cx, cy = float(center[0]), float(center[1])
    width, height = int(size[0]), int(size[1])
    if course_deg is None:
        return around((cx + gap, cy - height - 2), size, gap)
    points = []
    for offset in (90.0, -90.0, 135.0, -135.0, 45.0, -45.0):
        rad = math.radians(course_deg + offset)
        ux, uy = math.sin(rad), -math.cos(rad)
        # Distance from the symbol to the box centre so the box just clears
        # a circle of ``gap`` pixels around the symbol (its support length).
        reach = gap + abs(ux) * width / 2 + abs(uy) * height / 2
        points.append((int(round(cx + ux * reach - width / 2)),
                       int(round(cy + uy * reach - height / 2))))
    return points + around((cx + gap, cy - height - 2), size, gap)


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


def blit_fixed(surface, text, rect, color, size: int = 12,
               skip_if_taken: bool = False) -> bool:
    """A chart label that belongs to one exact place (a number of the
    bearing scale, a range ring's distance): drawn where asked and never
    moved; inside a label scope later labels keep off it.  With
    ``skip_if_taken`` a label whose place another label already holds is
    left out (a moved label would point at the wrong place); returns
    whether it was drawn."""
    from src.core.i18n import localize
    from src.ui import layout
    x, y, w, h = (int(value) for value in rect)
    field = active()
    if field is not None:
        width = min(w, layout.text_width(layout.font(size), localize(text)) + 2)
        if skip_if_taken and not field.is_free((x, y, width, h)):
            return False
        field.reserve((x, y, width, h))
    layout.blit_line(surface, text, (x, y, w, h), color, size=size)
    return True


def blit_line(surface, text, rect, color, size: int = 12, center=None,
              course=None, key=None) -> None:
    """``layout.blit_line`` for a chart label: inside a label scope the box
    shrinks to the text and steps aside from labels, symbols and lines
    placed before it.  With ``center`` (the symbol) the label is set abeam
    of ``course`` (:func:`beside`); a ``key`` keeps it on last frame's spot
    while that stays free."""
    from src.core.i18n import localize
    from src.ui import layout
    x, y, w, h = (int(value) for value in rect)

    def draw() -> None:
        nonlocal x, y, w
        field = active()
        if field is not None:
            width = min(w, layout.text_width(layout.font(size), localize(text)) + 2)
            candidates = (beside(center, (width, h), course) if center is not None
                          else around((x, y), (width, h)))
            x, y = field.place((width, h), candidates, key).topleft
            w = width
        layout.blit_line(surface, text, (x, y, w, h), color, size=size)

    later(draw)
