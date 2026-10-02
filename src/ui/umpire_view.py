"""Umpire screen of a host-only uConsole in a crew-versus-crew round.

Both crews may see the uConsole's screen, so it shows no tactical picture of
either unit: only the mission, the time left and who crews which station
(a person or the AI). Nothing here reads hidden state; the roster comes from
the Remote Crew server and the clock from the mission.
"""

from __future__ import annotations

import pygame

from src.commander.server import OPFOR_ROLES, STATIONS
from src.core import config
from src.core.i18n import message, raw_text
from src.ui import layout
from src.ui.splash_view import draw_menu_panel

_TEAM_COLORS = {"frigate": (40, 110, 160), "uboot": (170, 70, 50)}


def _holders(game) -> dict:
    """Station -> name of the browser holding it (observers aside)."""
    server = getattr(game.commander, "server", None)
    if server is None or getattr(game.commander, "address", None) is None:
        return {}
    holders = {}
    for player in server.lobby_players():
        if player["observer"]:
            continue
        for station in player["stations"]:
            holders.setdefault(station, player["name"])
    return holders


def draw(game) -> None:
    s = game.screen
    overlay_rect = pygame.Rect(40, 60, config.SCREEN_W - 80, config.SCREEN_H - 120)
    draw_menu_panel(s, overlay_rect, pygame.Rect(0, 0, 0, 0))
    layout.blit_line(s, "umpire.title", (overlay_rect.x + 20, overlay_rect.y + 12,
                                         overlay_rect.w - 40, 34),
                     config.COLOR_WARN, size=26, align="center")
    layout.blit_line(s, message("umpire.mission", mission=game.mission_name_display()),
                     (overlay_rect.x + 20, overlay_rect.y + 52, overlay_rect.w - 40, 26),
                     config.COLOR_TEXT, size=20, align="center")
    layout.blit_line(s, message("umpire.time",
                                remaining=game.mission.format_remaining(game.mission_time)),
                     (overlay_rect.x + 20, overlay_rect.y + 82, overlay_rect.w - 40, 26),
                     config.COLOR_TEXT, size=20, align="center")
    holders = _holders(game)
    column_w = (overlay_rect.w - 60) // 2
    for index, (unit, stations) in enumerate((("frigate", STATIONS),
                                              ("uboot", OPFOR_ROLES))):
        x = overlay_rect.x + 20 + index * (column_w + 20)
        y = overlay_rect.y + 126
        pygame.draw.rect(s, _TEAM_COLORS[unit], (x, y, column_w, 4))
        layout.blit_line(s, f"umpire.team.{unit}", (x, y + 8, column_w, 28),
                         config.COLOR_TEXT, size=21)
        humans = 0
        for row, station in enumerate(stations):
            name = holders.get(station)
            humans += name is not None
            line_y = y + 42 + row * 28
            layout.blit_line(s, f"station.{station}", (x, line_y, column_w // 2, 24),
                             config.COLOR_TEXT_DIM, size=17)
            layout.blit_line(s, raw_text(name) if name is not None else "umpire.ai",
                             (x + column_w // 2, line_y, column_w // 2, 24),
                             config.COLOR_TEXT if name is not None else config.COLOR_TEXT_DIM,
                             size=17)
        layout.blit_line(s, message("umpire.humans", count=str(humans)),
                         (x, y + 46 + len(STATIONS) * 28, column_w, 24),
                         config.COLOR_OK if humans else config.COLOR_WARN, size=16)
    layout.blit_line(s, "umpire.hint", (overlay_rect.x + 20, overlay_rect.bottom - 30,
                                        overlay_rect.w - 40, 22),
                     config.COLOR_TEXT_DIM, size=15, align="center")
