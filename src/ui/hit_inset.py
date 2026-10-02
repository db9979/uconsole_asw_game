"""The hit picture on the uConsole (``src/core/hit_view.py``).

A small window over the station: in sight, the side's own eyepiece picture
trained on the hit (the lookout's or the periscope's outlines and the sight
events); only heard, the bearing with the noise as the sonar hears it.
Display only; the browser draws the same (``views/hit-view.js``).
"""

from __future__ import annotations

import math

import pygame

from src.core import config, hit_view, opfor, sight_events
from src.core.i18n import message
from src.ui import horizon, layout, sight_scene

RECT = pygame.Rect(944, 92, 324, 196)
TITLE_H = 22
SONAR_SPAN_DEG = 60.0
SONAR_ROWS = 28
BACK = (6, 18, 26)
TRACE = (110, 232, 200)


def title(view: dict):
    bearing = f"{round(view['bearing']) % 360:03d}"
    if view["mode"] == "sight":
        return message("hitview.sight", bearing=bearing)
    return message("hitview.heard_" + ("breakup" if view["kind"] == "breakup" else "hit"),
                   bearing=bearing)


def _noise(i: int, k: int) -> float:
    """A fixed pseudo-random value 0..1 (display only)."""
    value = math.sin(i * 12.9898 + k * 78.233) * 43758.5453
    return value - math.floor(value)


def draw_sonar(s, rect, bearing: float, age_s: float) -> None:
    """The heard hit: rows of broadband noise around the bearing, newest on
    top, with a bright, wavering trace where the hull breaks up."""
    pygame.draw.rect(s, BACK, rect)
    rows = SONAR_ROWS
    row_h = max(1, rect.h // rows)
    step = int(age_s * 6.0)
    for r in range(rows):
        y = rect.y + r * row_h
        k = step - r
        if k < 0:
            continue
        fade = 1.0 - 0.6 * r / rows
        for c in range(0, rect.w, 4):
            level = 0.18 * _noise(c, k)
            centre = rect.centerx + (_noise(7, k) - 0.5) * 6.0
            distance = abs(rect.x + c - centre) / (rect.w / SONAR_SPAN_DEG)
            if distance < 3.0:
                level += (0.9 - 0.25 * distance) * (0.6 + 0.4 * _noise(c + 3, k))
            shade = max(0.0, min(1.0, level * fade))
            if shade > 0.08:
                color = tuple(int(BACK[i] + (TRACE[i] - BACK[i]) * shade) for i in range(3))
                pygame.draw.rect(s, color, (rect.x + c, y, 4, row_h))
    for off in (-30, -20, -10, 0, 10, 20, 30):
        x = rect.centerx + int(off * rect.w / SONAR_SPAN_DEG)
        pygame.draw.line(s, (60, 120, 112), (x, rect.bottom - (8 if off else 14)), (x, rect.bottom), 1)
        if off % 20 == 0 or off == 0:
            label = f"{round(bearing + off) % 360:03d}"
            layout.blit_line(s, label, (x - 16, rect.bottom - 26, 32, 12), (120, 180, 170),
                             size=11, align="center")


def draw(game, s, side: str) -> None:
    view = hit_view.current(game, side)
    if view is None:
        return
    rect = RECT
    pygame.draw.rect(s, config.COLOR_PANEL_BG, rect)
    pygame.draw.rect(s, config.COLOR_DANGER, rect, 1)
    layout.blit_line(s, title(view), (rect.x + 8, rect.y + 3, rect.w - 16, TITLE_H - 4),
                     config.COLOR_WARN, size=15)
    picture = pygame.Rect(rect.x + 2, rect.y + TITLE_H, rect.w - 4, rect.h - TITLE_H - 2)
    if view["mode"] != "sight":
        draw_sonar(s, picture, view["bearing"], view["age_s"])
        return
    weather = game.world.weather_values()
    if side == "uboot":
        from src.ui.uboot_scope import scope_outlines
        boat = game.opfor
        outlines = scope_outlines(game, boat) if opfor.scope_available(boat) else []
        rows = sight_events.boat_rows(game, boat)
    else:
        from src.ui.stations.bridge import lookout_outlines
        outlines = lookout_outlines(game, game.lookout_sightings())
        rows = sight_events.frigate_rows(game)
    horizon.draw_horizon(s, picture, line_of_sight=view["bearing"], fov_deg=hit_view.FOV_DEG,
                         night=game.world.is_night(), visibility_nm=weather["visibility_nm"],
                         motion=(0.0, 0.0), outlines=outlines, anim_t=game.sim_t,
                         sky=sight_scene.sky_state(game), sea_state=weather["sea_state"],
                         events=rows)
