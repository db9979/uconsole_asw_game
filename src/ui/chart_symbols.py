"""Nautical chart symbols for charted wrecks and underwater rocks.

Charted hazards are public chart information (not hidden truth), drawn in
the style of paper charts: a wreck as a hull line with masts, an underwater
rock as an asterisk.  Depth labels appear once the chart is zoomed in.
"""

from __future__ import annotations

import pygame

from src.core.i18n import message
from src.ui import layout

WRECK_COLOR = (150, 180, 200)
ROCK_COLOR = (220, 190, 120)
LABEL_MIN_SCALE_PX_PER_NM = 12.0
SYMBOL_MIN_SCALE_PX_PER_NM = 0.8


def draw_symbol(surface, kind: str, px: float, py: float) -> None:
    x, y = int(px), int(py)
    if kind == "wreck":
        pygame.draw.line(surface, WRECK_COLOR, (x - 8, y), (x + 8, y), 2)
        for dx in (-4, 0, 4):
            pygame.draw.line(surface, WRECK_COLOR, (x + dx, y - 5), (x + dx, y + 5), 1)
    else:
        pygame.draw.line(surface, ROCK_COLOR, (x - 5, y), (x + 5, y), 2)
        pygame.draw.line(surface, ROCK_COLOR, (x, y - 5), (x, y + 5), 2)
        pygame.draw.line(surface, ROCK_COLOR, (x - 4, y - 4), (x + 4, y + 4), 1)
        pygame.draw.line(surface, ROCK_COLOR, (x - 4, y + 4), (x + 4, y - 4), 1)


def draw_hazards(surface, hazards, to_screen, rect, scale_px_per_nm: float) -> None:
    """Draw every charted hazard inside ``rect`` (screen/layer coordinates).

    ``to_screen(x_nm, y_nm)`` maps world to the target surface; hazards are
    culled by bounds before drawing (at most 64 per world)."""
    if scale_px_per_nm < SYMBOL_MIN_SCALE_PX_PER_NM:
        return
    left, top, width, height = rect
    labels = scale_px_per_nm >= LABEL_MIN_SCALE_PX_PER_NM
    for hazard in hazards:
        px, py = to_screen(hazard.x_nm, hazard.y_nm)
        if not (left - 8 <= px <= left + width + 8 and top - 8 <= py <= top + height + 8):
            continue
        draw_symbol(surface, hazard.kind, px, py)
        if labels:
            layout.blit_line(
                surface, message("chart.hazard_depth", depth=f"{hazard.top_depth_m:.0f}"),
                (int(px) + 12, int(py) - 9, 80, 18),
                WRECK_COLOR if hazard.kind == "wreck" else ROCK_COLOR, size=14)


def hazard_at(hazards, to_screen, pos, radius_px: float = 10.0):
    """Charted hazard under the cursor, for chart tooltips."""
    best = None
    for hazard in hazards:
        px, py = to_screen(hazard.x_nm, hazard.y_nm)
        distance = ((px - pos[0]) ** 2 + (py - pos[1]) ** 2) ** 0.5
        if distance <= radius_px and (best is None or distance < best[0]):
            best = (distance, hazard)
    return None if best is None else best[1]


def hazard_tooltip(hazard):
    """Tooltip lines for a charted hazard."""
    if hazard.kind == "wreck":
        return layout.tooltip_payload(
            "chart.wreck_title",
            message("chart.wreck_detail", depth=f"{hazard.top_depth_m:.0f}",
                    length=f"{hazard.length_m:.0f}"),
            "chart.hazard_note",
            target_id=f"chart:wreck:{hazard.x_nm:.3f}:{hazard.y_nm:.3f}")
    return layout.tooltip_payload(
        "chart.rock_title",
        message("chart.rock_detail", depth=f"{hazard.top_depth_m:.0f}"),
        "chart.hazard_note",
        target_id=f"chart:rock:{hazard.x_nm:.3f}:{hazard.y_nm:.3f}")


__all__ = ["draw_hazards", "draw_symbol", "hazard_at", "hazard_tooltip",
           "WRECK_COLOR", "ROCK_COLOR"]
