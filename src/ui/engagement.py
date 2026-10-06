"""Fire-control engagement sketch shared by the frigate and the crewed boat.

North-up and centred on the own ship: the torpedo's reach ring, the bearing
to the chosen contact and, once a range is known, the estimated target
position with its course, the intercept point and the torpedo run to it.
Every input is an observation (a contact's bearing, estimated position and
TMA course/speed) or own-ship data; the sketch never sees a live target and
changes nothing (display only).
"""

from __future__ import annotations

import math

import pygame

from src.core import config
from src.core.i18n import nm_unit, raw_text
from src.ui import layout, lines, nato_symbols

# The sketch shows at least this much sea around the own ship (NM).
MIN_SPAN_NM = 2.0
# A zoomed sketch reaches this much beyond the target or intercept point.
SPAN_MARGIN = 1.35


def _polar(cx, cy, radius, bearing_deg):
    rad = math.radians(bearing_deg)
    return cx + radius * math.sin(rad), cy - radius * math.cos(rad)


def intercept(dx, dy, course, speed_kn, torpedo_kn):
    """Seconds and relative point where a torpedo from the origin meets a
    target at (dx, dy) NM steering ``course`` at ``speed_kn``; ``None``
    when the torpedo cannot catch it."""
    vx = speed_kn / 3600.0 * math.sin(math.radians(course))
    vy = -speed_kn / 3600.0 * math.cos(math.radians(course))
    s = torpedo_kn / 3600.0
    a = vx * vx + vy * vy - s * s
    b = 2.0 * (dx * vx + dy * vy)
    c = dx * dx + dy * dy
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return None
        roots = [-c / b]
    else:
        disc = b * b - 4.0 * a * c
        if disc < 0.0:
            return None
        root = math.sqrt(disc)
        roots = [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
    times = [t for t in roots if t > 0.0 and math.isfinite(t)]
    if not times:
        return None
    t = min(times)
    return t, (dx + vx * t, dy + vy * t)


def _dashed(screen, color, start, end, dash=5, width=1) -> None:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 1:
        return
    steps = int(length // (dash * 2)) + 1
    for index in range(steps):
        a = index * dash * 2 / length
        b = min(1.0, (index * dash * 2 + dash) / length)
        if a >= 1.0:
            break
        lines.line(screen, color,
                   (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                   (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b),
                   width)


def _ring(screen, color, centre, radius, dashed=False) -> None:
    points = [_polar(centre[0], centre[1], radius, 360.0 * i / 72) for i in range(73)]
    if not dashed:
        lines.lines(screen, color, False, points, 1)
        return
    for index in range(0, 72, 2):
        lines.line(screen, color, points[index], points[index + 1], 1)


def draw_engagement_sketch(screen, rect, *, own_course, torpedo_kn, torpedo_range_nm,
                           bearing=None, target=None, target_course=None,
                           target_speed_kn=None, fresh=True) -> None:
    """Draw the sketch in ``rect``.

    ``bearing`` is the observed bearing to the chosen contact (None: no
    target), ``target`` its estimated position relative to the own ship
    (dx, dy NM; None: bearing only).
    """
    rect = pygame.Rect(rect)
    face = layout.font(11)
    label_h, label_w = face.get_linesize(), face.size("000")[0]
    radius = min(rect.w // 2 - label_w - 6, rect.h // 2 - label_h - 4)
    if radius < 36:
        return
    layout.record_geometry("instrument", rect, "engagement")
    cx, cy = rect.center
    reach = max(0.1, float(torpedo_range_nm))
    point = target
    solved = None
    if target is not None and target_course is not None and target_speed_kn is not None:
        solved = intercept(target[0], target[1], target_course, target_speed_kn, torpedo_kn)
        if solved is not None:
            point = solved[1]
    if target is None:
        # Nothing to measure yet: the whole reach of the torpedo.
        span = max(MIN_SPAN_NM, reach * 1.1)
    else:
        # Zoomed onto the engagement; the reach ring shows when it fits.
        span = max(MIN_SPAN_NM, SPAN_MARGIN * max(math.hypot(*target), math.hypot(*point)))
    scale = radius / span

    def at(dx, dy):
        return cx + dx * scale, cy + dy * scale

    # Frame: the outer ring at the span, cardinal ticks and labels.
    _ring(screen, config.COLOR_SONAR_RING, (cx, cy), radius)
    for bearing_mark in range(0, 360, 30):
        major = bearing_mark % 90 == 0
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_GRID,
                   _polar(cx, cy, radius - (7 if major else 4), bearing_mark),
                   _polar(cx, cy, radius, bearing_mark), 1)
    for bearing_mark in range(0, 360, 90):
        reach_px = radius + 4 + (label_w // 2 if bearing_mark % 180 else label_h // 2)
        tx, ty = _polar(cx, cy, reach_px, bearing_mark)
        layout.blit_line(screen, raw_text(f"{bearing_mark:03d}"),
                         (int(tx) - 18, int(ty) - label_h // 2, 36, label_h),
                         config.COLOR_TEXT_DIM, size=11, align="center")
    # Scale: the frame's radius in NM; torpedo reach: a dashed amber ring.
    fx, fy = _polar(cx, cy, radius, 225.0)
    layout.blit_line(screen, raw_text(f"{span:.1f} {nm_unit()}"),
                     (int(fx) - 66, int(fy), 64, label_h), config.COLOR_TEXT_DIM,
                     size=11, align="right")
    if reach <= span:
        reach_px = reach * scale
        _ring(screen, config.COLOR_WARN, (cx, cy), reach_px, dashed=True)
        lx, ly = _polar(cx, cy, reach_px, 135.0)
        layout.blit_line(screen, raw_text(f"{reach:.0f} {nm_unit()}"),
                         (int(lx) + 2, int(ly), 64, label_h), config.COLOR_WARN, size=11)
    # Own ship: a friendly triangle along its course.
    tip = _polar(cx, cy, 9, own_course)
    left = _polar(cx, cy, 6, own_course + 140)
    right = _polar(cx, cy, 6, own_course - 140)
    friend = nato_symbols.AFFILIATION_COLORS["FRIEND"]
    pygame.draw.polygon(screen, friend, (tip, left, right))
    if bearing is None:
        return
    colour = config.COLOR_DANGER if fresh else config.COLOR_WARN
    edge = _polar(cx, cy, radius, bearing)
    if target is None:
        # Bearing only: the line runs to the frame, no position is claimed.
        _dashed(screen, colour, (cx, cy), edge)
        return
    lines.line(screen, config.COLOR_GRID, (cx, cy), edge, 1)
    tx, ty = at(*target)
    pygame.draw.circle(screen, colour, (int(tx), int(ty)), 6, 1)
    lines.line(screen, colour, (tx - 9, ty), (tx + 9, ty), 1)
    lines.line(screen, colour, (tx, ty - 9), (tx, ty + 9), 1)
    if target_course is not None and target_speed_kn is not None:
        if solved is not None:
            px, py = at(*point)
            _dashed(screen, colour, (tx, ty), (px, py), dash=3)
            pygame.draw.polygon(screen, colour, ((px, py - 5), (px + 5, py),
                                                 (px, py + 5), (px - 5, py)), 1)
        else:
            # Too fast to catch: only its course is shown.
            ex, ey = _polar(tx, ty, 18, target_course)
            lines.line(screen, colour, (tx, ty), (ex, ey), 1)
    run = math.hypot(*point)
    px, py = at(*point)
    lines.line(screen, config.COLOR_OK if run <= reach else config.COLOR_DANGER,
               (cx, cy), (px, py), 2)
