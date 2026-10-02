"""Bow wave and wake of a made-out ship in the eyepiece (display only).

``level`` (0..1, ``lookout_id.way_level``) is the white water the eye sees:
a fast ship pushes a high, white bow wave and leaves a long wake, a slow one
hardly any.  The ship's angle on the bow (``aob_deg``, positive when the eye
sees her starboard side, so her bow points right) places the bow and stern on
the waterline.  A few lines per ship; the browser draws the same
(``sight-scene.js`` ``drawShipWay``).
"""

from __future__ import annotations

import math

import pygame

MIN_LEVEL = 0.05
# Broken white water (the browser uses the same colour).
FOAM = (236, 246, 246)
MIN_WIDTH_PX = 8


def _blend(a, b, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def ends(cx: float, width: float, aob_deg: float) -> tuple:
    """Screen x of the bow and the stern, and which way the bow points."""
    side = math.sin(math.radians(aob_deg))
    face = 1.0 if side >= 0.0 else -1.0
    half = width / 2.0 * max(0.12, abs(side))
    return cx + face * half, cx - face * half, face


def draw(s, cx: float, base_y: float, width: float, aob_deg: float, level: float,
         t: float, foam, sea) -> None:
    """White water at the bow, along the hull and astern of one ship."""
    if level is None or level < MIN_LEVEL or width < MIN_WIDTH_PX:
        return
    bow_x, stern_x, face = ends(cx, width, aob_deg)
    toward = math.cos(math.radians(aob_deg))      # > 0: bow toward the eye
    white = _blend(sea, foam, 0.55 + 0.45 * level)
    # The bow wave: a mound of white water pushed ahead and to the sides.
    rise = max(1.5, width * 0.07 * level)
    spread = width * (0.05 + 0.1 * level) * (0.5 + 0.5 * abs(toward))
    for k in range(3):
        phase = (t * (0.8 + 1.4 * level) + k * 0.33) % 1.0
        reach = spread * (0.4 + 0.6 * phase)
        lift = rise * (1.0 - phase)
        for side in (-1.0, 1.0):
            pygame.draw.line(s, white, (bow_x, base_y - lift * 0.3),
                             (bow_x + side * reach, base_y - lift * (0.2 + 0.8 * (1.0 - phase))), 1)
    pygame.draw.line(s, white, (bow_x - face * width * 0.03, base_y),
                     (bow_x + face * spread * 0.5, base_y), 2 if level > 0.5 else 1)
    # White water running aft along the waterline.
    pygame.draw.line(s, _blend(sea, foam, 0.3 + 0.5 * level), (bow_x, base_y),
                     (bow_x + (stern_x - bow_x) * (0.3 + 0.4 * level), base_y), 1)
    # The wake: a widening band of churned water astern, longer the faster.
    length = width * (0.3 + 1.4 * level)
    steps = 7
    for i in range(steps):
        f = i / steps
        g = (i + 1) / steps
        x0 = stern_x - face * length * f * max(0.15, abs(math.sin(math.radians(aob_deg))))
        x1 = stern_x - face * length * g * max(0.15, abs(math.sin(math.radians(aob_deg))))
        band = 1.0 + 4.0 * level * f
        color = _blend(white, sea, 0.1 + 0.8 * f)
        if toward < 0.0:
            # Stern toward the eye: the wake runs down toward the viewer.
            pygame.draw.line(s, color, (x0, base_y + band * 0.3),
                             (x1, base_y + band + 2.0 * level * -toward * (i + 1)), 1)
        else:
            pygame.draw.line(s, color, (x0, base_y + 1.0 + band / 2.0),
                             (x1, base_y + 1.0 + band / 2.0), max(1, int(band)))
        drift = (t * (0.6 + level) + i * 0.37) % 1.0
        if drift < 0.5:
            fx = x0 + (x1 - x0) * drift * 2.0
            pygame.draw.line(s, color, (fx, base_y + band), (fx - face * 3.0, base_y + band), 1)
