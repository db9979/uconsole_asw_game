"""Pointer readout for the measured sound-speed profile and sound-path section.

Display only: it reads the mouse and the operator's own BT measurement and
never touches the simulation. Shared by the Sonar environment page and the
weather/sonar analysis panel (key 0).
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import localize
from src.ui import layout

CURSOR_COLOR = (150, 235, 255)


def speed_at(depths, speeds, depth: float):
    """Sound speed at ``depth``, linearly interpolated from a measured profile."""
    if not len(depths):
        return None
    if depth <= depths[0]:
        return float(speeds[0])
    for index in range(1, len(depths)):
        if depth <= depths[index]:
            upper, lower = float(depths[index - 1]), float(depths[index])
            share = (depth - upper) / (lower - upper) if lower > upper else 0.0
            return float(speeds[index - 1]) + share * (float(speeds[index]) - float(speeds[index - 1]))
    return float(speeds[-1])


def pointer(game):
    """Canvas position of the mouse, or None outside the canvas/window."""
    try:
        if not pygame.mouse.get_focused():
            return None
        return game._window_to_canvas(pygame.mouse.get_pos())
    except (pygame.error, AttributeError):
        return None


def draw_crosshair(screen, rect: pygame.Rect, x=None, y=None) -> None:
    """Dotted guide lines inside ``rect`` (horizontal at y, vertical at x)."""
    if y is not None:
        for dash in range(rect.x, rect.right, 6):
            pygame.draw.line(screen, CURSOR_COLOR, (dash, y), (min(dash + 2, rect.right - 1), y))
    if x is not None:
        for dash in range(rect.y, rect.bottom, 6):
            pygame.draw.line(screen, CURSOR_COLOR, (x, dash), (x, min(dash + 2, rect.bottom - 1)))


def draw_label(screen, text, anchor, bounds: pygame.Rect, size: int = 13) -> None:
    """Readout on its own dark plate beside the cursor, kept inside bounds."""
    label = localize(text)
    face = layout.font(layout.scaled_size(size))
    width, height = face.size(label)
    plate = pygame.Rect(0, 0, width + 12, height + 4)
    plate.x = min(bounds.right - plate.w - 2, max(bounds.x + 2, anchor[0] + 10))
    plate.y = anchor[1] - plate.h - 4
    if plate.y < bounds.y + 2:
        plate.y = anchor[1] + 6
    pygame.draw.rect(screen, config.COLOR_BG, plate)
    pygame.draw.rect(screen, CURSOR_COLOR, plate, 1)
    layout.blit_line(screen, text, (plate.x + 6, plate.y + 2, width + 4, height),
                     CURSOR_COLOR, size=size)
