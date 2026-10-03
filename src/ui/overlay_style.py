"""Overlays in the start screen's look: the night hunt behind a console panel.

Every modal overlay of the uConsole (help, options, save/load, quit, nations,
live traffic, Remote Crew administration, mission end) draws the same dimmed
splash scene as the main menu, a translucent console panel with corner
brackets and a phosphor title. It is cosmetic only: the animation phase is
the caller's wall-clock time and nothing here reads or changes the
simulation. With high contrast the panels stay opaque in the theme colors.
"""

from collections import OrderedDict

import pygame

from src.core import config
from src.ui import layout, quality, splash_view

PHOSPHOR = splash_view.PHOSPHOR
PHOSPHOR_DIM = splash_view.PHOSPHOR_DIM
GOLD = splash_view.GOLD
PANEL_FILL = (4, 16, 20, 228)
PANEL_RIM = (40, 96, 90)
HIGHLIGHT = (18, 60, 56)
BRACKET = 22

_PANELS = OrderedDict()
_PANELS_MAX = 12


def high_contrast() -> bool:
    """The high-contrast theme is active."""
    from src.ui import theme
    return theme.high_contrast()


_DIM = {}
BACKDROP_DIM_ALPHA = 110
# The veil over the scene (dark at night, light by day; set by the theme).
BACKDROP_VEIL = (2, 6, 10, BACKDROP_DIM_ALPHA)


_BACKDROP_FRAME = {}


def backdrop(surface: pygame.Surface, t: float) -> None:
    """The start-screen scene over the whole canvas, lightly dimmed.

    At the low graphics level the scene is drawn a few times a second and the
    finished frame is reused in between (src/ui/quality.py)."""
    size = surface.get_size()
    if quality.LEVEL == "low":
        stamp = quality.backdrop_time(t)
        cached = _BACKDROP_FRAME.get(size)
        if cached is not None and cached[0] == stamp:
            surface.blit(cached[1], (0, 0))
            return
        _draw_backdrop(surface, stamp)
        _BACKDROP_FRAME.clear()
        _BACKDROP_FRAME[size] = (stamp, surface.copy())
        return
    _BACKDROP_FRAME.clear()
    _draw_backdrop(surface, t)


def _draw_backdrop(surface: pygame.Surface, t: float) -> None:
    splash_view.draw_scene(surface, t)
    size = surface.get_size()
    key = (size, BACKDROP_VEIL)
    dim = _DIM.get(key)
    if dim is None:
        _DIM.clear()
        dim = pygame.Surface(size, pygame.SRCALPHA)
        dim.fill(BACKDROP_VEIL)
        _DIM[key] = dim
    surface.blit(dim, (0, 0))


def _fill(size) -> pygame.Surface:
    key = (tuple(size), PANEL_FILL)
    surf = _PANELS.get(key)
    if surf is None:
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill(PANEL_FILL)
        _PANELS[key] = surf
        while len(_PANELS) > _PANELS_MAX:
            _PANELS.popitem(last=False)
    else:
        _PANELS.move_to_end(key)
    return surf


def panel(surface: pygame.Surface, rect, accent=None) -> pygame.Rect:
    """Translucent console panel with a thin rim and phosphor corner brackets."""
    rect = pygame.Rect(rect)
    if high_contrast():
        pygame.draw.rect(surface, config.COLOR_PANEL_BG, rect)
        pygame.draw.rect(surface, accent or config.COLOR_TEXT_DIM, rect, 2)
        return rect
    surface.blit(_fill(rect.size), rect)
    pygame.draw.rect(surface, PANEL_RIM, rect, 1)
    color = accent or PHOSPHOR_DIM
    for x, y, dx, dy in ((rect.left, rect.top, 1, 1), (rect.right - 1, rect.top, -1, 1),
                         (rect.left, rect.bottom - 1, 1, -1),
                         (rect.right - 1, rect.bottom - 1, -1, -1)):
        pygame.draw.line(surface, color, (x, y), (x + dx * BRACKET, y), 3)
        pygame.draw.line(surface, color, (x, y), (x, y + dy * BRACKET), 3)
    return rect


def title(surface: pygame.Surface, text, rect, size: int = 30,
          color=None, align: str = "center") -> None:
    """A phosphor heading with the logo's soft glow."""
    rect = pygame.Rect(rect)
    color = color or (config.COLOR_TEXT if high_contrast() else PHOSPHOR)
    if high_contrast():
        layout.blit_line(surface, text, rect, color, size=size, align=align)
        return
    glow = tuple(max(0, int(c * .22)) for c in color)
    with layout.capture_text():  # the glow copies are not separate text
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            layout.blit_line(surface, text, rect.move(dx, dy), glow, size=size, align=align)
    layout.blit_line(surface, text, rect, color, size=size, align=align)


def rule(surface: pygame.Surface, x: int, y: int, width: int) -> None:
    """Thin separator under a title."""
    color = config.COLOR_SONAR_RING if high_contrast() else PANEL_RIM
    pygame.draw.line(surface, color, (x, y), (x + width, y), 1)


def highlight(surface: pygame.Surface, rect) -> None:
    """The main menu's selection band."""
    pygame.draw.rect(surface, config.COLOR_SELECT_BG if high_contrast() else HIGHLIGHT,
                     pygame.Rect(rect))


def text_color(selected: bool):
    """Row text: bright when selected, dim otherwise (as in the main menu)."""
    return config.COLOR_TEXT if selected else config.COLOR_TEXT_DIM


def accent_color():
    """Gold accent for hints and warnings, as the author line on the splash."""
    return config.COLOR_WARN if high_contrast() else GOLD

