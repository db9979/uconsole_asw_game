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


def depth_dial(screen, rect, depth, ordered, test_depth, crush_depth) -> None:
    """A 240 degree depth gauge from the surface to below crush depth.

    The arc beyond test depth is amber, beyond crush depth red; the hollow
    triangle is the ordered depth and the needle the boat's depth.
    """
    rect = pygame.Rect(rect)
    face = layout.font(11)
    label_h = face.get_linesize()
    radius = min(rect.w // 2, rect.h // 2) - label_h // 2 - 4
    if radius < 24:
        return
    layout.record_geometry("instrument", rect, "depth")
    cx, cy = rect.centerx, rect.centery + radius // 5
    step = 100 if crush_depth <= 600 else 200 if crush_depth <= 1200 else 500
    maximum = float(max(step, math.ceil(max(crush_depth * 1.1, depth, ordered) / step) * step))
    start, sweep = -120.0, 240.0

    def angle(value):
        return start + sweep * max(0.0, min(1.0, value / maximum))

    def at(value, r):
        return _polar(cx, cy, r, angle(value))

    points = [at(maximum * i / 48, radius) for i in range(49)]
    lines.lines(screen, config.COLOR_SONAR_RING, False, points, 1)
    for lo, hi, color in ((test_depth, crush_depth, config.COLOR_WARN),
                          (crush_depth, maximum, config.COLOR_DANGER)):
        if hi > lo:
            steps = max(2, int((angle(hi) - angle(lo)) / 4) + 1)
            band = [at(lo + (hi - lo) * i / steps, radius - 3) for i in range(steps + 1)]
            lines.lines(screen, color, False, band, 3)
    for metres in range(0, int(maximum) + 1, step // 2):
        major = metres % step == 0
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_GRID,
                   at(metres, radius - (8 if major else 4)), at(metres, radius), 1)
        if major and metres % (2 * step) == 0:
            tx, ty = at(metres, radius - 10 - label_h)
            layout.blit_line(screen, raw_text(f"{metres}"),
                             (int(tx) - 18, int(ty) - label_h // 2, 36, label_h),
                             config.COLOR_TEXT_DIM, size=11, align="center")
    ox, oy = at(ordered, radius + 1)
    left, right = (_polar(cx, cy, radius + 10, angle(ordered) + d) for d in (-4, 4))
    pygame.draw.polygon(screen, config.COLOR_WARN, ((ox, oy), left, right), 1)
    color = (config.COLOR_DANGER if depth >= crush_depth else config.COLOR_WARN
             if depth > test_depth else config.COLOR_OK)
    lines.line(screen, color, (cx, cy), at(depth, radius - 6), 2)
    pygame.draw.circle(screen, color, (cx, cy), 3)


# --- clicks on the dials (full mouse control) --------------------------------------
# Inverse geometry of the dials above: which value a point on a dial stands
# for.  Pure screen geometry; the caller turns the value into the same order
# a typed entry would give.

def _dial_angle(cx, cy, pos):
    dx, dy = pos[0] - cx, pos[1] - cy
    if math.hypot(dx, dy) < 6:
        return None
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def heading_at(rect, pos):
    """Bearing (whole degrees) under ``pos`` on a heading dial, else None."""
    rect = pygame.Rect(rect)
    if not rect.collidepoint(pos):
        return None
    angle = _dial_angle(*rect.center, pos)
    return None if angle is None else int(round(angle)) % 360


def _arc_value(rect, pos, maximum):
    rect = pygame.Rect(rect)
    if not rect.collidepoint(pos):
        return None
    label_h = layout.font(11).get_linesize()
    radius = min(rect.w // 2, rect.h // 2) - label_h // 2 - 4
    cx, cy = rect.centerx, rect.centery + radius // 5
    angle = _dial_angle(cx, cy, pos)
    if angle is None:
        return None
    signed = angle if angle <= 180.0 else angle - 360.0      # -180..180, 0 up
    if signed < -120.0 or signed > 120.0:
        return None                                           # the open bottom
    return max(0.0, min(1.0, (signed + 120.0) / 240.0)) * maximum


def speed_at(rect, pos, maximum):
    """Speed (whole knots) under ``pos`` on a speed dial, else None."""
    value = _arc_value(rect, pos, max(1.0, float(maximum)))
    return None if value is None else int(round(value))


def depth_at(rect, pos, depth, ordered, crush_depth):
    """Depth (metres, 5 m steps) under ``pos`` on a depth dial, else None."""
    step = 100 if crush_depth <= 600 else 200 if crush_depth <= 1200 else 500
    maximum = float(max(step, math.ceil(max(crush_depth * 1.1, depth, ordered) / step) * step))
    value = _arc_value(rect, pos, maximum)
    return None if value is None else int(round(value / 5.0)) * 5
