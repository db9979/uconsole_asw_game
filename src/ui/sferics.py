"""Sferics on the ESM and radio displays: the crackle of a thunderstorm.

Lightning discharges are broadband radio noise.  Under a storm
(``src/world/thunder.py``) the ESM roses and the HF/DF page show short
bright ticks at random bearings that come and go, and a line naming the
cause.  Display only: the ticks follow wall time and never become tracks;
what the storm does to HF bearings is modelled in ``thunder.sferics_factor``.
"""

from __future__ import annotations

import math

import pygame

from src.core import detrand
from src.ui import layout

CRACKLE = (170, 176, 230)
TICK_S = 0.12
MAX_TICKS = 10


def ticks(level: float, wall_t: float) -> list:
    """``(bearing, length 0..1)`` of the crackle shown at ``wall_t``."""
    if level <= 0.0:
        return []
    slot = int(wall_t / TICK_S)
    rows = []
    for index in range(MAX_TICKS):
        if detrand.u01(slot, "sferics", index) < 0.35 * level:
            rows.append((360.0 * detrand.u01(slot, "sferics-brg", index),
                         0.3 + 0.7 * detrand.u01(slot, "sferics-len", index)))
    return rows


def draw_rose(s, center, radius: float, level: float, wall_t: float) -> None:
    """Crackle ticks on a bearing rose around ``center``."""
    cx, cy = center
    for bearing, length in ticks(level, wall_t):
        rad = math.radians(bearing)
        inner = radius * (1.0 - 0.35 * length)
        pygame.draw.line(s, CRACKLE, (cx + inner * math.sin(rad), cy - inner * math.cos(rad)),
                         (cx + radius * math.sin(rad), cy - radius * math.cos(rad)), 1)


def draw_label(s, rect, level: float) -> None:
    """The line under a display that names the storm static."""
    if level <= 0.0:
        return
    layout.blit_line(s, "esm.sferics", rect, CRACKLE, size=12)
