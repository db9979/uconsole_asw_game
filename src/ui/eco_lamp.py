"""Automatic economy: the ECO lamp in the top bar.

Lit while a slow picture made the game draw at the low graphics level by
itself (``src/ui/quality.py``).  It sits left of the microphone meter (or of
the menu button) and the status line gives way to it (``status_right``).
Hovering it says why it is lit and how to switch the automatic economy off.
Display only.
"""

from __future__ import annotations

import pygame

from src.core import config, status_tips
from src.ui import layout, pointer, quality

WIDTH = 40
HEIGHT = 18
GAP = 10


def shown(game) -> bool:
    return bool(quality.AUTO_LOW)


def rect(game) -> pygame.Rect:
    from src.ui import mic_meter
    side = "uboot" if getattr(game, "local_side", "frigate") == "uboot" else "frigate"
    anchor = mic_meter.rect(game).right + mic_meter.GAP      # the menu button
    right = mic_meter.status_right(game, side, anchor - GAP)
    return pygame.Rect(right - WIDTH, (config.TOP_BAR_H - HEIGHT) // 2, WIDTH, HEIGHT)


def status_right(game, right: int) -> int:
    """Right edge of the status line: left of the lamp while it is lit."""
    return min(right, rect(game).x - GAP) if shown(game) else right


def note() -> dict:
    return status_tips.note("eco_lamp.label", "", "eco_lamp.why", "eco_lamp.how",
                            keys=("F10", "Tab"), level="caution")


def draw(game, s) -> None:
    if not shown(game):
        return
    box = rect(game)
    pygame.draw.rect(s, config.COLOR_PANEL_BG, box)
    pygame.draw.rect(s, config.COLOR_WARN, box, 1, border_radius=3)
    layout.blit_line(s, "eco_lamp.tag", box.inflate(-4, -2), config.COLOR_WARN,
                     size=14, align="center")
    pointer.add_tip(box, lambda: status_tips.payload(note()))
