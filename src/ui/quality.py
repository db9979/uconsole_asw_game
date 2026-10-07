"""Graphics level and canvas scaling (display only, never simulation).

The ``graphics`` preference picks one of three levels:

* ``low`` ("Sparsam"): plain pixel scaling of the canvas, no PPI afterglow,
  the menu and overlay backdrop animates at 4 frames a second;
* ``normal``: sharp smooth scaling (below), every effect; the uConsole default;
* ``full``: like ``normal`` plus anti-aliased chart lines; the default on
  Windows.

With ``graphics_auto`` (default on) a picture that stays below
``AUTO_LOW_FPS`` for a few seconds drops to ``low`` by itself until the
player picks a level again (the ECO lamp in the top bar says so).

Nothing here changes what a station shows as information: tracks, rings,
datums and sight events stay at every level.

Scaling the 1280x720 canvas to another window size: at a whole factor the
pixels are repeated exactly (crisp); otherwise "sharp" scaling first repeats
pixels up to the next whole factor and then smooths down to the window, which
keeps text and thin lines even instead of the uneven rows of plain pixel
scaling at 1.5x, without the blur of smoothing the small canvas directly.
In a clearly larger window the normal and full levels draw the canvas itself
at two or three times its pixels (src/ui/hires.py); the scaling here then
only fits those pixels to the window.
"""

from __future__ import annotations

import math
import sys

import pygame

LEVELS = ("low", "normal", "full")
LEVEL = "normal"            # the level drawn now
CHOSEN = "normal"           # the level of the settings
# Automatic economy: True while a slow picture made the game draw at the low
# level by itself (``FrameWatch``); the ECO lamp in the top bar shows it.
AUTO_LOW = False

# Backdrop frame rate at the low level (frames per second of wall time).
LOW_BACKDROP_FPS = 4.0

# Automatic economy: below this many frames a second for AUTO_LOW_HOLD_S of
# wall time (measured in whole windows of AUTO_LOW_WINDOW_S) the picture
# drops to the low level.  A frame longer than AUTO_LOW_HITCH_S (loading a
# mission or a save) is not counted and starts the measurement again.
AUTO_LOW_FPS = 14.0
AUTO_LOW_HOLD_S = 5.0
AUTO_LOW_WINDOW_S = 1.0
AUTO_LOW_HITCH_S = 1.0


def _apply() -> str:
    from src.ui import lines
    global LEVEL
    LEVEL = "low" if AUTO_LOW else CHOSEN
    lines.ENABLED = LEVEL == "full"
    return LEVEL


def configure(level: str) -> str:
    """Set the chosen level (unknown values fall back to normal); the
    automatic economy keeps the low level drawn until it is reset."""
    global CHOSEN
    CHOSEN = level if level in LEVELS else "normal"
    return _apply()


def set_auto_low(active: bool) -> str:
    """Switch the automatic economy on or off (display only)."""
    global AUTO_LOW
    AUTO_LOW = bool(active)
    return _apply()


class FrameWatch:
    """Wall-time frame-rate watch for the automatic economy.

    ``feed`` takes each frame's wall time and returns True once the frame
    rate stayed below ``AUTO_LOW_FPS`` for ``AUTO_LOW_HOLD_S``.  Display
    only: it never reads or changes the simulation.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._window_s = 0.0
        self._frames = 0
        self._slow_s = 0.0

    def feed(self, wall_dt: float) -> bool:
        try:
            wall_dt = float(wall_dt)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(wall_dt) or wall_dt <= 0.0:
            return False
        if wall_dt > AUTO_LOW_HITCH_S:
            self.reset()
            return False
        self._window_s += wall_dt
        self._frames += 1
        if self._window_s < AUTO_LOW_WINDOW_S:
            return False
        fps = self._frames / self._window_s
        self._slow_s = self._slow_s + self._window_s if fps < AUTO_LOW_FPS else 0.0
        self._window_s = 0.0
        self._frames = 0
        return self._slow_s >= AUTO_LOW_HOLD_S


def afterglow() -> bool:
    return LEVEL != "low"


def backdrop_time(t: float) -> float:
    """The backdrop's animation time: stepped at the low level."""
    if LEVEL == "low":
        return math.floor(t * LOW_BACKDROP_FPS) / LOW_BACKDROP_FPS
    return t


_SCRATCH: dict = {}
_OUTPUT: dict = {}           # plain pixel scaling
_OUTPUT_SMOOTH: dict = {}    # sharp (smooth) scaling


def _scratch(size, like: pygame.Surface, store: dict = _SCRATCH) -> pygame.Surface:
    surface = store.get(size)
    if surface is None or surface.get_bitsize() != like.get_bitsize():
        store.clear()             # one window size at a time
        surface = pygame.Surface(size, 0, like)
        store[size] = surface
    return surface


def scale_canvas(canvas: pygame.Surface, size, level: str | None = None) -> pygame.Surface:
    """The canvas scaled to ``size`` for the window.

    A high-resolution canvas (src/ui/hires.py) is scaled from its physical
    pixels.  The result is a kept surface: valid until the next call that
    scales the same way (the frame blits it at once)."""
    from src.ui import hires
    level = LEVEL if level is None else level
    width, height = int(size[0]), int(size[1])
    cw, ch = pygame.Surface.get_size(canvas)
    if (width, height) == (cw, ch):
        return canvas
    scale, smoothscale = hires.raw("scale"), hires.raw("smoothscale")
    factor = min(width / cw, height / ch)
    whole = round(factor)
    # Scaled into kept surfaces: a desktop window would otherwise allocate
    # (and free) a full-screen surface every frame. Same pixels.
    if (level == "low" or canvas.get_bitsize() not in (24, 32)
            or (abs(factor - whole) < 1e-9 and whole >= 1
                and (width, height) == (cw * whole, ch * whole))):
        return scale(canvas, (width, height),
                     _scratch((width, height), canvas, _OUTPUT))
    output = _scratch((width, height), canvas, _OUTPUT_SMOOTH)
    up = max(1, math.ceil(factor))
    source = canvas
    if up > 1:
        source = _scratch((cw * up, ch * up), canvas)
        scale(canvas, pygame.Surface.get_size(source), source)
    return smoothscale(source, (width, height), output)
