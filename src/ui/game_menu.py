"""The top bar's game menu and the close buttons of overlays (full mouse
control on the uConsole).

A small menu icon beside the dark/light switch opens a compact list of the
global functions that otherwise only have a key (help, options, save/load,
weather, plot, autocrew, quit ...).  Each row calls exactly what its key
calls, so the same checks and feedback apply.  The open list owns the
pointer (layer "popup"): a click beside it or any key closes it.  Overlays
get a visible close button that presses ``Esc``.  Display state only: the
open flag is never saved and nothing here touches the simulation.
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.station import Station
from src.ui import layout, pointer, theme

BUTTON_W = 30
ROW_H = 28
MENU_W = 330
CLOSE_SIZE = 28


def button_rect() -> pygame.Rect:
    """The menu icon, left of the top bar's dark/light switch."""
    from src.core.game_draw import theme_switch_rect
    switch = theme_switch_rect()
    return pygame.Rect(switch.x - 8 - BUTTON_W, switch.y - 1, BUTTON_W, switch.h + 2)


def _bars(screen, rect, color) -> None:
    """Three short bars (the usual menu glyph), centred in ``rect``."""
    width = max(8, rect.w - 14)
    left = rect.centerx - width // 2
    for dy in (-5, 0, 5):
        pygame.draw.line(screen, color, (left, rect.centery + dy),
                         (left + width - 1, rect.centery + dy), 2)


def draw_button(game) -> pygame.Rect | None:
    """Draw the menu icon (both sides); a click opens or closes the menu."""
    if game.game_over:
        return None
    rect = button_rect()
    layout.record_geometry("switch", rect, "game_menu")
    opened = bool(getattr(game, "game_menu_open", False))
    pygame.draw.rect(game.screen, theme.c("accent") if opened else theme.c("raised"),
                     rect, border_radius=4)
    pygame.draw.rect(game.screen, theme.c("line"), rect, 1, border_radius=4)
    _bars(game.screen, rect, theme.c("on_accent") if opened else config.COLOR_TEXT)
    pointer.add_action(rect.inflate(4, 6), lambda _pos: toggle(game))
    return rect


def toggle(game) -> None:
    game.game_menu_open = not getattr(game, "game_menu_open", False)


def _frigate_entries(game) -> list:
    rows = [("F1", "gamemenu.help", lambda: game._open_administration("help")),
            ("F10", "gamemenu.options", lambda: game._open_administration("options")),
            ("S", "gamemenu.save", lambda: game._open_administration("save")),
            ("L", "gamemenu.load", lambda: game._open_administration("load")),
            ("0", "gamemenu.weather", game.open_weather_station)]
    if game.station is Station.OPZ or game._map_station_visible():   # a chart to plot on
        rows.append(("P", "gamemenu.plot", game.menu_toggle_plot))
    rows += [("F2", "gamemenu.autocrew", game.toggle_station_autocrew),
             ("Shift+F2", "gamemenu.crew_assist", game.toggle_crew_assist),
             ("F3", "gamemenu.autocrew_overview", game.open_autocrew_overview),
             ("F4", "gamemenu.simlog", game._open_simlog_view),
             ("F7", "gamemenu.advisor", lambda: game._open_administration("advisor")),
             ("F8", "gamemenu.analyzer", game._open_analyzer_in_game),
             ("F9", "gamemenu.commander", lambda: game._open_administration("commander")),
             ("N", "gamemenu.nations", lambda: game._open_administration("nations")),
             ("Esc", "gamemenu.quit", lambda: game._open_administration("quit"))]
    return rows


def _boat_entries(game) -> list:
    from src.core import uboot_local
    rows = [("F1", "gamemenu.help", lambda: game._open_administration("help")),
            ("F10", "gamemenu.options", lambda: game._open_administration("options")),
            ("S", "gamemenu.save", lambda: game._open_administration("save")),
            ("L", "gamemenu.load", lambda: game._open_administration("load"))]
    if uboot_local.boat(game) is not None:      # the boat's own instruments
        rows.append(("0", "gamemenu.weather", game.open_weather_station))
    return rows + [
        ("Shift+F2", "gamemenu.crew_assist", game.toggle_crew_assist),
        ("F7", "gamemenu.advisor", lambda: game._open_administration("advisor")),
        ("F9", "gamemenu.commander", lambda: game._open_administration("commander")),
        ("Esc", "gamemenu.quit", lambda: game._open_administration("quit"))]


def entries(game) -> list:
    """``(key label, catalog key, call)`` of the side shown."""
    return _boat_entries(game) if game.local_side == "uboot" else _frigate_entries(game)


def menu_rect(count: int) -> pygame.Rect:
    button = button_rect()
    return pygame.Rect(config.SCREEN_W - 6 - MENU_W, button.bottom + 6, MENU_W,
                       count * ROW_H + 12)


def row_rects(count: int) -> list:
    panel = menu_rect(count)
    return [pygame.Rect(panel.x + 6, panel.y + 6 + index * ROW_H, panel.w - 12, ROW_H - 2)
            for index in range(count)]


def can_show(game) -> bool:
    """The menu belongs to a running mission's station screen."""
    return (game._mission_shown() and not game.administration_open
            and game.input_mode is None and not game.umpire_view_active())


def draw_menu(game) -> None:
    """The open menu over the station (pointer layer "popup")."""
    if not getattr(game, "game_menu_open", False):
        return
    if not can_show(game):
        game.game_menu_open = False
        return
    rows = entries(game)
    panel = menu_rect(len(rows))
    layout.record_geometry("panel", panel, "game_menu")
    layout.panel_frame(game.screen, panel)
    for (key, label, call), rect in zip(rows, row_rects(len(rows))):
        layout.command_segment(game.screen, rect, key, label, size=14)
        pointer.add_action(rect, lambda _pos, call=call: choose(game, call))


def choose(game, call) -> None:
    """Close the menu, then do what the row's key does."""
    game.game_menu_open = False
    call()


def close_button(screen, panel_rect, key: int = pygame.K_ESCAPE) -> pygame.Rect:
    """A visible close box in the top right corner of an overlay panel; a
    click presses ``key`` (``Esc``) in the current pointer layer."""
    rect = draw_close_box(screen, panel_rect)
    pointer.add_key(rect, key)
    return rect


def close_rect(panel_rect) -> pygame.Rect:
    """Where :func:`close_button` sits in ``panel_rect`` (top right)."""
    panel_rect = pygame.Rect(panel_rect)
    return pygame.Rect(panel_rect.right - CLOSE_SIZE - 8, panel_rect.y + 8,
                       CLOSE_SIZE, CLOSE_SIZE)


def draw_close_box(screen, panel_rect) -> pygame.Rect:
    """Draw the close box only (views with their own mouse handling, such
    as the editors, take its click themselves); returns its rectangle."""
    rect = close_rect(panel_rect)
    layout.record_geometry("switch", rect, "close")
    pygame.draw.rect(screen, theme.c("raised"), rect, border_radius=4)
    pygame.draw.rect(screen, theme.c("line_strong"), rect, 1, border_radius=4)
    inset = rect.inflate(-14, -14)
    color = config.COLOR_TEXT
    pygame.draw.line(screen, color, inset.topleft, (inset.right - 1, inset.bottom - 1), 2)
    pygame.draw.line(screen, color, (inset.x, inset.bottom - 1), (inset.right - 1, inset.y), 2)
    return rect
