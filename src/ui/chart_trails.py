"""Draw the chart history (src/core/chart_history.py) on a tactical chart.

The own track is a dotted line, earlier positions of a track are small dots
that fade with age, and the earlier bearings of the selected contact are
faint lines from where each was taken.  Display only; points outside the
chart are culled before drawing.
"""

from __future__ import annotations

import math

import pygame

from src.core import config
from src.ui import label_layout, lines

# How far a past bearing line reaches on screen (pixels).
BEARING_LINE_PX = 240


def _mix(color, background, weight: float):
    """``color`` faded towards ``background`` (weight 1 = full colour)."""
    weight = max(0.0, min(1.0, weight))
    return tuple(int(round(b + (c - b) * weight)) for c, b in zip(color[:3], background[:3]))


def _inside(rect: pygame.Rect, px: float, py: float, margin: float = 4.0) -> bool:
    return (rect.x - margin <= px <= rect.right + margin
            and rect.y - margin <= py <= rect.bottom + margin)


def draw_own_trail(surface, points, view, rect, color, background, current=None) -> None:
    """The own ship's (or boat's) track: dots joined by a faint line."""
    rect = pygame.Rect(rect)
    points = list(points)
    if current is not None:
        points.append(current)
    if len(points) < 2:
        return
    screen = [view.world_to_screen(x, y) for x, y in points]
    faint = _mix(color, background, 0.35)
    dot = _mix(color, background, 0.7)
    previous = None
    for px, py in screen:
        visible = _inside(rect, px, py)
        if previous is not None and (visible or _inside(rect, *previous)):
            lines.line(surface, faint, (int(previous[0]), int(previous[1])),
                       (int(px), int(py)), 1)
            label_layout.reserve_segment(previous, (px, py), 3)
        previous = (px, py)
    for px, py in screen[:-1]:
        if _inside(rect, px, py):
            pygame.draw.circle(surface, dot, (int(px), int(py)), 1)


def draw_track_history(surface, rows, view, rect, color, background) -> None:
    """Earlier observed positions of one track, oldest faintest."""
    rect = pygame.Rect(rect)
    rows = list(rows)
    count = len(rows)
    previous = None
    for index, row in enumerate(rows[:-1] if count > 1 else ()):
        px, py = view.world_to_screen(row[1], row[2])
        if not _inside(rect, px, py):
            previous = None
            continue
        weight = 0.25 + 0.55 * (index + 1) / count
        pygame.draw.circle(surface, _mix(color, background, weight), (int(px), int(py)), 2)
        # Labels keep off the dotted trail as off a line through its dots.
        if previous is not None:
            label_layout.reserve_segment(previous, (px, py), 4)
        previous = (px, py)


def draw_bearing_history(surface, rows, view, rect, color, background) -> None:
    """Earlier bearings of one contact from where each was taken."""
    rect = pygame.Rect(rect)
    rows = list(rows)
    count = len(rows)
    # The newest bearing is the live line the chart already draws.
    for index, row in enumerate(rows[:-1] if count > 1 else ()):
        ox, oy = view.world_to_screen(row[1], row[2])
        rad = math.radians(row[3])
        ex, ey = ox + BEARING_LINE_PX * math.sin(rad), oy - BEARING_LINE_PX * math.cos(rad)
        if not (_inside(rect, ox, oy, BEARING_LINE_PX) or _inside(rect, ex, ey)):
            continue
        weight = 0.2 + 0.45 * (index + 1) / count
        faded = _mix(color, background, weight)
        # Dashed, so an old bearing never reads as the live one.
        for step in range(0, 24, 2):
            a = (ox + (ex - ox) * step / 24, oy + (ey - oy) * step / 24)
            b = (ox + (ex - ox) * (step + 1) / 24, oy + (ey - oy) * (step + 1) / 24)
            lines.line(surface, faded, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), 1)


def draw_side(surface, side, view, rect, background, own_now=None,
              selected_bearing_key=None, track_color=None,
              hidden_keys=frozenset()) -> None:
    """Everything of one chart's history below the live symbols."""
    if side is None:
        return
    draw_own_trail(surface, side.own, view, rect, config.COLOR_OK, background, own_now)
    color = track_color or config.COLOR_TEXT_DIM
    for key, rows in side.tracks.items():
        if key in hidden_keys:
            continue
        draw_track_history(surface, rows, view, rect, color, background)
    if selected_bearing_key is not None:
        draw_bearing_history(surface, side.bearing_history(selected_bearing_key), view, rect,
                             config.COLOR_WARN, background)
