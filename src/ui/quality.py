"""Graphics level and canvas scaling (display only, never simulation).

The ``graphics`` preference picks one of three levels:

* ``low`` ("Sparsam"): plain pixel scaling of the canvas, no PPI afterglow,
  the menu and overlay backdrop animates at 4 frames a second;
* ``normal``: sharp smooth scaling (below), every effect; the uConsole default;
* ``full``: like ``normal`` plus anti-aliased chart lines; the default on
  Windows.

Nothing here changes what a station shows as information: tracks, rings,
datums and sight events stay at every level.

Scaling the 1280x720 canvas to another window size: at a whole factor the
pixels are repeated exactly (crisp); otherwise "sharp" scaling first repeats
pixels up to the next whole factor and then smooths down to the window, which
keeps text and thin lines even instead of the uneven rows of plain pixel
scaling at 1.5x, without the blur of smoothing the small canvas directly.
"""

from __future__ import annotations

import math
import sys

import pygame

LEVELS = ("low", "normal", "full")
LEVEL = "normal"

# Backdrop frame rate at the low level (frames per second of wall time).
LOW_BACKDROP_FPS = 4.0


def default_level() -> str:
    """Windows PCs get the full level, the uConsole and others normal."""
    return "full" if sys.platform == "win32" else "normal"


def configure(level: str) -> str:
    """Set the active level (unknown values fall back to normal)."""
    from src.ui import lines
    global LEVEL
    LEVEL = level if level in LEVELS else "normal"
    lines.ENABLED = LEVEL == "full"
    return LEVEL


def afterglow() -> bool:
    return LEVEL != "low"


def backdrop_time(t: float) -> float:
    """The backdrop's animation time: stepped at the low level."""
    if LEVEL == "low":
        return math.floor(t * LOW_BACKDROP_FPS) / LOW_BACKDROP_FPS
    return t


_SCRATCH: dict = {}


def _scratch(size, like: pygame.Surface) -> pygame.Surface:
    surface = _SCRATCH.get(size)
    if surface is None or surface.get_bitsize() != like.get_bitsize():
        _SCRATCH.clear()          # one window size at a time
        surface = pygame.Surface(size, 0, like)
        _SCRATCH[size] = surface
    return surface


def scale_canvas(canvas: pygame.Surface, size, level: str | None = None) -> pygame.Surface:
    """The canvas scaled to ``size`` for the window."""
    level = LEVEL if level is None else level
    width, height = int(size[0]), int(size[1])
    cw, ch = canvas.get_size()
    if (width, height) == (cw, ch):
        return canvas
    factor = min(width / cw, height / ch)
    whole = round(factor)
    if level == "low" or (abs(factor - whole) < 1e-9 and whole >= 1
                          and (width, height) == (cw * whole, ch * whole)):
        return pygame.transform.scale(canvas, (width, height))
    if canvas.get_bitsize() not in (24, 32):
        return pygame.transform.scale(canvas, (width, height))
    up = max(1, math.ceil(factor))
    source = canvas
    if up > 1:
        source = _scratch((cw * up, ch * up), canvas)
        pygame.transform.scale(canvas, source.get_size(), source)
    return pygame.transform.smoothscale(source, (width, height))
