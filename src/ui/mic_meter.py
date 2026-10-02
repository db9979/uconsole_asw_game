"""Noise discipline on the uConsole: a small level meter in the top bar.

Shown while the own microphone is switched on (Options, page 2) or a crew
member's browser reports a loud voice: twenty cells, green while the enemy
hears nothing, amber when it hears it close by, red when it hears it far off
(``src/core/noise_discipline.py``).  The outlined cell is the crew's loudest
held level.  The browser shows the same meter (``views/mic.js``).
"""

from __future__ import annotations

import pygame

from src.core import config, noise_discipline as nd

RECT = pygame.Rect(796, 7, 104, 16)
QUIET = (70, 200, 140)
NEAR = (230, 180, 60)
FAR = (235, 70, 60)
DARK = (30, 44, 52)


def _color(level: int):
    return {"quiet": QUIET, "near": NEAR, "far": FAR}[nd.band(level)]


def draw(game, s, side: str) -> None:
    local = int(game.__dict__.get("mic_level", 0)) if game.preferences.microphone else 0
    crew = game.crew_voice_level(side)
    if not game.preferences.microphone and crew <= 0:
        return
    rect = RECT
    pygame.draw.rect(s, config.COLOR_PANEL_BG, rect)
    pygame.draw.rect(s, DARK, rect, 1)
    cells = nd.VOICE_LEVEL_MAX
    width = (rect.w - 4) / cells
    for index in range(cells):
        level = index + 1
        cell = pygame.Rect(round(rect.x + 2 + index * width), rect.y + 3,
                           max(2, round(width) - 1), rect.h - 6)
        color = _color(level)
        if level <= local:
            pygame.draw.rect(s, color, cell)
        else:
            pygame.draw.rect(s, tuple(c // 3 for c in color), cell, 1)
        if level == crew:
            pygame.draw.rect(s, config.COLOR_TEXT, cell.inflate(2, 4), 1)
