"""Draws ``src/core/map_fx.py`` on a chart: the own ping's wavefront running
out at the speed of sound, echoes lighting up where they place their
reflector, rings where own charges went off, the radar's afterglow behind
its beam and the furthest-on circle round a fix that is getting old.

Display only; plain lines in blended colours, a few per frame, so it stays
cheap on the uConsole.  ``data/commander/js/views/map-fx.js`` draws the same
in the browser.
"""

from __future__ import annotations

import math

import pygame

from src.core import map_fx

PING = (110, 190, 255)
ECHO = (255, 236, 150)
SPLASH = (255, 214, 120)
FOC = (240, 190, 90)
GLOW = (70, 190, 130)
# Radar afterglow: the wedge behind the beam (degrees) and its steps.
AFTERGLOW_DEG = 40.0
AFTERGLOW_STEPS = 26


def _fade(color, background, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(b + (c - b) * k) for c, b in zip(color, background))


def _visible(rect, cx, cy, radius) -> bool:
    """Any part of the circle's rim inside ``rect``."""
    near_x = min(max(cx, rect.left), rect.right)
    near_y = min(max(cy, rect.top), rect.bottom)
    if math.hypot(near_x - cx, near_y - cy) > radius:
        return False
    far = max(math.hypot(corner[0] - cx, corner[1] - cy)
              for corner in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright))
    return far >= radius


def draw_fx(s, rows: dict, to_screen, px_per_nm: float, rect, background) -> None:
    """Pings, echoes and splashes (``MapFx.rows``) on a chart ``rect``."""
    rect = pygame.Rect(rect)
    for age, x, y in rows.get("pings", ()):
        cx, cy = to_screen(x, y)
        radius = map_fx.ping_radius_nm(age) * px_per_nm
        if radius < 2 or radius > 4 * max(rect.w, rect.h) or not _visible(rect, cx, cy, radius):
            continue
        fade = 1.0 - age / map_fx.PING_SHOW_S
        pygame.draw.circle(s, _fade(PING, background, 0.85 * fade), (int(cx), int(cy)),
                           int(radius), 2)
        if radius > 8:
            pygame.draw.circle(s, _fade(PING, background, 0.35 * fade), (int(cx), int(cy)),
                               int(radius - 5), 1)
    for age, x, y in rows.get("echoes", ()):
        cx, cy = to_screen(x, y)
        if not rect.collidepoint(cx, cy):
            continue
        k = 1.0 - age / map_fx.ECHO_SHOW_S
        pygame.draw.circle(s, _fade(ECHO, background, k), (int(cx), int(cy)),
                           int(3 + 9 * (1.0 - k)), 2)
        pygame.draw.circle(s, _fade(ECHO, background, k), (int(cx), int(cy)), 2)
    for age, x, y in rows.get("splashes", ()):
        cx, cy = to_screen(x, y)
        if not rect.collidepoint(cx, cy):
            continue
        k = 1.0 - age / map_fx.SPLASH_SHOW_S
        for ring in range(3):
            radius = 3 + (age * 2.0 + ring * 5.0) % 18.0
            pygame.draw.circle(s, _fade(SPLASH, background, k * (1.0 - radius / 22.0)),
                               (int(cx), int(cy)), int(radius), 1)


def draw_furthest_on(s, cx: float, cy: float, radius_px: float, rect, background) -> None:
    """The dashed circle a stale fix's contact can have reached."""
    if radius_px < 4 or not _visible(pygame.Rect(rect), cx, cy, radius_px):
        return
    color = _fade(FOC, background, 0.7)
    steps = max(16, min(72, int(radius_px / 4)))
    for index in range(0, steps, 2):
        a0 = math.tau * index / steps
        a1 = math.tau * (index + 1) / steps
        pygame.draw.line(s, color, (cx + radius_px * math.sin(a0), cy - radius_px * math.cos(a0)),
                         (cx + radius_px * math.sin(a1), cy - radius_px * math.cos(a1)), 1)


def draw_afterglow(s, cx: float, cy: float, radius_px: float, beam_deg: float,
                   background) -> None:
    """The phosphor afterglow behind a turning radar beam (clockwise)."""
    for step in range(1, AFTERGLOW_STEPS + 1):
        k = 1.0 - step / (AFTERGLOW_STEPS + 1)
        angle = math.radians(beam_deg - AFTERGLOW_DEG * step / AFTERGLOW_STEPS)
        pygame.draw.line(s, _fade(GLOW, background, 0.45 * k * k), (cx, cy),
                         (cx + radius_px * math.sin(angle), cy - radius_px * math.cos(angle)), 2)
