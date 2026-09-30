"""Alarm lamps on the uConsole's station tabs and the red light.

The lamp is a small filled dot in a tab's top right corner; the red light
is the existing multiply blend (``config.NIGHT_MODE_COLOR``), faded in and
out on wall time.  Levels come from ``src/core/station_alarms.py``.
"""

from __future__ import annotations

import pygame

from src.core import config, station_alarms

LAMP_DANGER = (255, 70, 60)
LAMP_WARN = (255, 190, 60)
LAMP_R = 4


def draw_lamp(s, rect, level, wall_t: float) -> None:
    """The alarm lamp of one tab (nothing without an alarm)."""
    if level is None:
        return
    center = (rect.right - LAMP_R - 3, rect.top + LAMP_R + 3)
    if station_alarms.lamp_on(level, wall_t):
        color = LAMP_DANGER if level == "danger" else LAMP_WARN
        pygame.draw.circle(s, color, center, LAMP_R)
    else:
        pygame.draw.circle(s, (90, 40, 36), center, LAMP_R, 1)


class RedLight:
    """The red light's current strength (0..1), fading on wall time."""

    def __init__(self) -> None:
        self.level = 0.0
        self._t = None
        self._surface = None
        self._surface_level = None

    def step(self, target: float, wall_t: float) -> float:
        if self._t is None:
            self.level = target
        else:
            rate = max(0.0, wall_t - self._t) / station_alarms.FADE_S
            if target > self.level:
                self.level = min(target, self.level + rate)
            else:
                self.level = max(target, self.level - rate)
        self._t = wall_t
        return self.level

    def overlay(self, size):
        """The multiply surface for the current level (rebuilt in steps)."""
        level = round(self.level * 16) / 16.0
        if self._surface is None or self._surface.get_size() != size:
            self._surface = pygame.Surface(size)
            self._surface_level = None
        if level != self._surface_level:
            color = tuple(int(255 + (c - 255) * level) for c in config.NIGHT_MODE_COLOR)
            self._surface.fill(color)
            self._surface_level = level
        return self._surface
