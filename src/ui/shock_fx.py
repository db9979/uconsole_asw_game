"""The uConsole picture shaken by a detonation close to the own ship.

Reads the ``shock_light``/``shock_heavy`` cues (``src/core/shock.py``) from
the sound events of the side shown and plays them on wall time: the canvas
jolts and settles, the light dips towards the dim red emergency lighting,
dust trickles down and, after a heavy one, an instrument glass shows cracks
that fade.  Display only; at the low graphics level only the light dips.
Surfaces are cached, the dust is a few dozen dots.
"""

from __future__ import annotations

import math
import random

import pygame

from src.core import shock
from src.ui import hires

# Seconds the jolt lasts and its first amplitude (canvas pixels).
DURATION_S = {"shock_light": 0.6, "shock_heavy": 1.1}
AMPLITUDE_PX = {"shock_light": 4.0, "shock_heavy": 9.0}
# How far the light dips (0..1) at the jolt.
DIM = {"shock_light": 0.35, "shock_heavy": 0.7}
EMERGENCY_LIGHT = (150, 58, 52)
CRACK_S = 12.0
CRACK_CENTER = (948, 372)
DUST_COUNT = 40
DUST_S = 2.4


class ShockFx:
    """One side's shocks on wall time (never saved, never simulation)."""

    def __init__(self) -> None:
        self.context = None
        self.high = 0
        self.kind = None
        self.started = None
        self.cracked = None
        self.count = 0
        self._tint = None
        self._tint_level = None
        self._cracks = None
        self._dust = ()

    def pump(self, context, events, wall_t: float) -> None:
        """Take new shock cues from ``events`` (dicts with seq and kind); a
        new ``context`` (side, world) only sets the high-water mark."""
        rows = list(events)
        latest = max((int(row["seq"]) for row in rows), default=0)
        if context != self.context or latest < self.high:
            self.context = context
            self.high = latest
            self.started = self.cracked = None
            return
        for row in rows:
            if int(row["seq"]) > self.high and row["kind"] in shock.CUES:
                self.trigger(row["kind"], wall_t)
        self.high = max(self.high, latest)

    def trigger(self, kind: str, wall_t: float) -> None:
        if (self.started is not None and self.kind == "shock_heavy"
                and kind == "shock_light" and wall_t - self.started < DURATION_S[self.kind]):
            return
        self.kind = kind
        self.started = wall_t
        self.count += 1
        if kind == "shock_heavy":
            self.cracked = wall_t
        stream = random.Random(self.count)
        self._dust = tuple((stream.uniform(0, 1280), stream.uniform(30, 520),
                            stream.uniform(60, 160), stream.choice((1, 1, 2)))
                           for _ in range(DUST_COUNT))

    def strength(self, wall_t: float) -> float:
        """1 at the jolt, falling to 0 when it has settled."""
        if self.started is None:
            return 0.0
        age = wall_t - self.started
        duration = DURATION_S[self.kind]
        if not 0.0 <= age < duration:
            return 0.0
        return (1.0 - age / duration) ** 2

    def offset(self, wall_t: float) -> tuple[int, int]:
        level = self.strength(wall_t)
        if level <= 0.0:
            return 0, 0
        age = wall_t - self.started
        amplitude = AMPLITUDE_PX[self.kind] * level
        return (round(amplitude * math.sin(age * 71.0)),
                round(amplitude * 0.6 * math.cos(age * 53.0)))

    def active(self, wall_t: float) -> bool:
        return self.strength(wall_t) > 0.0 or self._crack_alpha(wall_t) > 0 or (
            self.started is not None and 0.0 <= wall_t - self.started < DUST_S)

    def _crack_alpha(self, wall_t: float) -> int:
        if self.cracked is None:
            return 0
        age = wall_t - self.cracked
        if not 0.0 <= age < CRACK_S:
            return 0
        return int(210 * (1.0 - age / CRACK_S))

    def _tint_surface(self, size, level: float):
        level = round(level * 16) / 16.0
        if self._tint is None or self._tint.get_size() != size or hires.stale(self._tint):
            self._tint = hires.surface(size)
            self._tint_level = None
        if level != self._tint_level:
            self._tint.fill(tuple(int(255 + (c - 255) * level) for c in EMERGENCY_LIGHT))
            self._tint_level = level
        return self._tint

    def _crack_surface(self):
        if self._cracks is None or hires.stale(self._cracks):
            surface = hires.surface((300, 300), pygame.SRCALPHA)
            stream = random.Random(7)
            cx = cy = 150
            for _ in range(11):
                angle = stream.uniform(0.0, math.tau)
                x, y = float(cx), float(cy)
                for _ in range(stream.randint(4, 8)):
                    angle += stream.uniform(-0.5, 0.5)
                    step = 140.0 * stream.uniform(0.08, 0.2)
                    nx, ny = x + math.cos(angle) * step, y + math.sin(angle) * step
                    pygame.draw.line(surface, (255, 236, 226, 255), (x, y), (nx, ny))
                    x, y = nx, ny
            pygame.draw.circle(surface, (255, 240, 230, 255), (cx, cy), 4, 1)
            self._cracks = surface
        return self._cracks

    def draw(self, surface, wall_t: float, low: bool = False) -> None:
        """Shake, dim, dust and cracks over the finished canvas."""
        if self.started is None:
            return
        level = self.strength(wall_t)
        if level > 0.0 and not low:
            dx, dy = self.offset(wall_t)
            if dx or dy:
                surface.scroll(dx, dy)
        if level > 0.0:
            surface.blit(self._tint_surface(surface.get_size(), DIM[self.kind] * level),
                         (0, 0), special_flags=pygame.BLEND_MULT)
        if low:
            return
        age = wall_t - self.started
        if 0.0 <= age < DUST_S:
            fade = 1.0 - age / DUST_S
            color = (int(120 + 110 * fade), int(105 + 95 * fade), int(95 + 85 * fade))
            for x, y, speed, size in self._dust:
                py = y + speed * age
                if py < surface.get_height():
                    pygame.draw.rect(surface, color, (int(x), int(py), size, size))
        alpha = self._crack_alpha(wall_t)
        if alpha > 0:
            cracks = self._crack_surface()
            cracks.set_alpha(alpha)
            surface.blit(cracks, (CRACK_CENTER[0] - 150, CRACK_CENTER[1] - 150))
