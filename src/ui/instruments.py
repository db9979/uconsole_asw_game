"""Own-ship bridge instruments in the start screen's style (display only).

A heading dial with the ordered course, a rudder-angle scale and a speed
dial. They show only own-ship values the bridge already prints as numbers;
nothing here reads or changes simulation state.
"""

import math

import pygame

from src.core import config
from src.core.i18n import raw_text
from src.ui import layout, lines


def _polar(cx, cy, radius, bearing_deg):
    rad = math.radians(bearing_deg)
    return cx + radius * math.sin(rad), cy - radius * math.cos(rad)


def heading_dial(screen, rect, course, ordered) -> None:
    """Compass ring with the heading needle and an ordered-course mark."""
    rect = pygame.Rect(rect)
    face = layout.font(11)
    label_h, label_w = face.get_linesize(), face.size("000")[0]
    radius = min(rect.w // 2 - label_w - 6, rect.h // 2 - label_h - 4)
    if radius < 24:
        return
    layout.record_geometry("instrument", rect, "heading")
    cx, cy = rect.center
    pygame.draw.circle(screen, config.COLOR_SONAR_RING, (cx, cy), radius, 1)
    for bearing in range(0, 360, 10):
        major = bearing % 30 == 0
        inner = radius - (8 if major else 4)
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_GRID,
                   _polar(cx, cy, inner, bearing), _polar(cx, cy, radius, bearing), 1)
    for bearing in range(0, 360, 90):
        reach = radius + 4 + (label_w // 2 if bearing % 180 else label_h // 2)
        tx, ty = _polar(cx, cy, reach, bearing)
        layout.blit_line(screen, raw_text(f"{bearing:03d}"),
                         (int(tx) - 18, int(ty) - label_h // 2, 36, label_h),
                         config.COLOR_TEXT_DIM, size=11, align="center")
    # Ordered course: a hollow triangle on the ring.
    ox, oy = _polar(cx, cy, radius - 2, ordered)
    left = _polar(cx, cy, radius - 12, ordered - 5)
    right = _polar(cx, cy, radius - 12, ordered + 5)
    pygame.draw.polygon(screen, config.COLOR_WARN, ((ox, oy), left, right), 1)
    # Heading needle.
    lines.line(screen, config.COLOR_OK, (cx, cy), _polar(cx, cy, radius - 6, course), 2)
    pygame.draw.circle(screen, config.COLOR_OK, (cx, cy), 3)


def rudder_scale(screen, rect, angle, maximum) -> None:
    """Port (left) to starboard (right) rudder angle with a centre mark."""
    rect = pygame.Rect(rect)
    if rect.w < 60 or rect.h < 14:
        return
    layout.record_geometry("instrument", rect, "rudder")
    maximum = max(1.0, float(maximum))
    mid = rect.centerx
    base = rect.bottom - 3
    lines.line(screen, config.COLOR_SONAR_RING, (rect.x, base), (rect.right - 1, base), 1)
    for step in range(-int(maximum), int(maximum) + 1, 10):
        x = mid + round(step / maximum * (rect.w // 2 - 1))
        lines.line(screen, config.COLOR_TEXT_DIM if step else config.COLOR_TEXT,
                   (x, base - (8 if step == 0 else 5)), (x, base), 1)
    value = max(-maximum, min(maximum, float(angle)))
    x = mid + round(value / maximum * (rect.w // 2 - 1))
    band = pygame.Rect(min(mid, x), base - 4, abs(x - mid), 3)
    if band.w:
        pygame.draw.rect(screen, config.COLOR_OK, band)
    pygame.draw.polygon(screen, config.COLOR_OK,
                        ((x, base - 5), (x - 5, rect.y + 1), (x + 5, rect.y + 1)))


def speed_dial(screen, rect, speed, ordered, maximum) -> None:
    """A 240 degree speed arc from 0 to ``maximum`` knots with its needle."""
    rect = pygame.Rect(rect)
    face = layout.font(11)
    label_h = face.get_linesize()
    radius = min(rect.w // 2, rect.h // 2) - label_h // 2 - 4
    if radius < 24:
        return
    layout.record_geometry("instrument", rect, "speed")
    cx, cy = rect.centerx, rect.centery + radius // 5
    maximum = max(1.0, float(maximum))
    start, sweep = -120.0, 240.0

    def at(value, r):
        return _polar(cx, cy, r, start + sweep * max(0.0, min(1.0, value / maximum)))

    points = [at(maximum * i / 48, radius) for i in range(49)]
    lines.lines(screen, config.COLOR_SONAR_RING, False, points, 1)
    for knots in range(0, int(maximum) + 1, 5):
        major = knots % 10 == 0
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_GRID,
                   at(knots, radius - (8 if major else 4)), at(knots, radius), 1)
        if major:
            tx, ty = at(knots, radius - 8 - label_h)
            layout.blit_line(screen, raw_text(f"{knots}"),
                             (int(tx) - 14, int(ty) - label_h // 2, 28, label_h),
                             config.COLOR_TEXT_DIM, size=11, align="center")
    ox, oy = at(abs(ordered), radius + 1)
    left, right = (_polar(cx, cy, radius + 10, start + sweep * min(1.0, abs(ordered) / maximum) + d)
                   for d in (-4, 4))
    pygame.draw.polygon(screen, config.COLOR_WARN, ((ox, oy), left, right), 1)
    lines.line(screen, config.COLOR_OK, (cx, cy), at(abs(speed), radius - 6), 2)
    pygame.draw.circle(screen, config.COLOR_OK, (cx, cy), 3)
