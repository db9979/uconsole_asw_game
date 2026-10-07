"""Display and help constants and pure helpers shared by the ``Game`` mixins.

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 3) so the event,
draw and operator halves import them without a circular import.
"""


import pygame

from src.core import config


# F1 overlay categories: global keys, station, sensors/tactics, manual reader.
HELP_PAGE_COUNT = 4


HELP_MANUAL_PAGE = 3


# Operator TMA: the residuals must show no systematic trend beyond the
# averaged bearing noise before a hypothesis can be accepted as a fix.
TMA_ACCEPT_MIN_FIT = 0.3


# Operator sonar classification -> published track kind (domain symbol).
SONAR_BAND_PRESETS = {
    "FULL": (0.0, 300.0),
    "LOW": (4.0, 80.0),
    "SHAFT": (8.0, 55.0),
    "MID": (20.0, 120.0),
}


def letterbox_layout(win_w: int, win_h: int,
                     base_w: int = config.SCREEN_W,
                     base_h: int = config.SCREEN_H) -> tuple:
    """Aspect-correcte Anordnung des virtuellen Canvas im Fenster."""
    scale = min(win_w / base_w, win_h / base_h)
    sw, sh = int(base_w * scale), int(base_h * scale)
    return scale, (win_w - sw) // 2, (win_h - sh) // 2, sw, sh


def make_canvas(w: int, h: int) -> pygame.Surface:
    """The opaque 1280x720 canvas every frame is drawn on.

    Explicit 32-bit RGB without an alpha channel: a plain
    ``pygame.Surface`` takes the window's format, and on macOS that format
    carries alpha.  Translucent layers (menu veils, panels) then left the
    canvas pixels partly transparent, and the Mac window blinked behind
    every open menu.  Without an alpha channel the frame stays opaque on
    every system."""
    return pygame.Surface((w, h), 0, 32, (0xFF0000, 0xFF00, 0xFF, 0))


def make_scanlines(w: int, h: int, alpha: int = config.SCANLINE_ALPHA):
    """Vorberechnetes CRT-Scanline-Overlay (einmalig, SRCALPHA)."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(0, h, 3):
        s.fill((0, 0, 0, alpha), (0, y, w, 1))
    return s
