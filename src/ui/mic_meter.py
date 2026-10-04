"""Noise discipline on the uConsole: a small level meter in the top bar.

Shown while the own microphone is switched on (Options, page 2) or a crew
member's browser reports a loud voice: a microphone sign and twenty LED
segments, green while the enemy hears nothing, amber when it hears it close
by, red when it hears it far off (``src/core/noise_discipline.py``).  Unlit
segments are dimmed, never empty outlines; the tick under a segment is the
crew's loudest held level.  The browser shows the same meter
(``views/mic.js``).

The meter sits right of the status line, left of the menu button, and the
status line gives way to it (``status_right``), so the two never overlap.
"""

from __future__ import annotations

import pygame

from src.core import config, noise_discipline as nd
from src.ui import theme

WIDTH = 100
HEIGHT = 18
GAP = 10                    # to the menu button and to the status line
ICON_W = 12
QUIET = (70, 200, 140)
NEAR = (230, 180, 60)
FAR = (235, 70, 60)
DARK = (30, 44, 52)


def _color(level: int):
    return {"quiet": QUIET, "near": NEAR, "far": FAR}[nd.band(level)]


def shown(game, side: str) -> bool:
    """The meter is up: own microphone on, or a crew voice is held."""
    return bool(game.preferences.microphone) or game.crew_voice_level(side) > 0


def rect(game) -> pygame.Rect:
    """Right of the status line, left of the menu button (or the dark/light
    switch when the menu button is not drawn)."""
    from src.core.game_draw import theme_switch_rect
    from src.ui import game_menu
    anchor = theme_switch_rect() if game.game_over else game_menu.button_rect()
    return pygame.Rect(anchor.x - GAP - WIDTH, (config.TOP_BAR_H - HEIGHT) // 2,
                       WIDTH, HEIGHT)


def status_right(game, side: str, right: int) -> int:
    """Right edge of the top bar's status line: left of the meter if shown."""
    return min(right, rect(game).x - GAP) if shown(game, side) else right


def _icon(s, box, color) -> None:
    """A microphone: capsule, cradle and foot."""
    cx = box.centerx
    capsule = pygame.Rect(cx - 3, box.y + 1, 6, 9)
    pygame.draw.rect(s, color, capsule, border_radius=3)
    pygame.draw.arc(s, color, pygame.Rect(cx - 5, box.y + 3, 10, 10), 3.3, 6.1, 1)
    pygame.draw.line(s, color, (cx, box.y + 13), (cx, box.bottom - 2), 1)
    pygame.draw.line(s, color, (cx - 3, box.bottom - 2), (cx + 3, box.bottom - 2), 1)


def draw(game, s, side: str) -> None:
    if not shown(game, side):
        return
    local = int(game.__dict__.get("mic_level", 0)) if game.preferences.microphone else 0
    crew = game.crew_voice_level(side)
    box = rect(game)
    pygame.draw.rect(s, config.COLOR_PANEL_BG, box)
    _icon(s, pygame.Rect(box.x, box.y, ICON_W, box.h),
          config.COLOR_TEXT if game.preferences.microphone else config.COLOR_TEXT_DIM)
    track = pygame.Rect(box.x + ICON_W + 3, box.y + 1, box.w - ICON_W - 3, box.h - 6)
    pygame.draw.rect(s, theme.c("well"), track, border_radius=2)
    pygame.draw.rect(s, theme.c("line"), track, 1, border_radius=2)
    cells = nd.VOICE_LEVEL_MAX
    pitch = (track.w - 4) / cells
    for index in range(cells):
        level = index + 1
        cell = pygame.Rect(round(track.x + 2 + index * pitch), track.y + 2,
                           max(2, round(pitch) - 1), track.h - 4)
        color = _color(level)
        pygame.draw.rect(s, color if level <= local else theme.mix("well", color, 0.28), cell)
        if level == crew:
            # The crew's loudest voice: a tick under its segment.
            x = cell.centerx
            pygame.draw.polygon(s, config.COLOR_TEXT, ((x, track.bottom + 1),
                                                       (x - 3, box.bottom), (x + 3, box.bottom)))
