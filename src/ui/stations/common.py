"""Helpers shared by the station views: panels, page tabs, autocrew overview,
observation geometry and state colours (verbatim from ``stations_view``)."""

from contextlib import nullcontext as _no_scope
import math

import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize, message as structured_message
from src.ui import layout, pointer
from src.ui import observations




def _hfdf_error_deg(report) -> float:
    """Half-width of the HFDF bearing error (uniform sigma x sqrt(3))."""
    sigma = getattr(report, "bearing_uncertainty_deg", None)
    return (sigma * math.sqrt(3.0) if sigma else config.HFDF_BEARING_ERR_DEG)

def message(key, **values):
    """A structured message: localized at draw time so layouts can abbreviate."""
    return structured_message(key, **values)

STATE_LABEL = {
    "OK": "damage.ok",
    "BESCHAEDIGT": "damage.damaged",
    "FLUTEND": "damage.flooding",
    "ZERSTOERT": "damage.destroyed",
}

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    " ": "/",
}


def _to_morse(text: str) -> str:
    out = []
    for ch in text.upper():
        out.append(MORSE.get(ch, "·"))
    return " ".join(out)


def _srect(x_off: int = 0, w: int = None) -> tuple:
    """Inneres Rechteck innerhalb von STATION_RECT."""
    rect = config.STATION_RECT
    x = rect[0] + x_off
    w = rect[2] - x_off if w is None else w
    return (x, rect[1] + 6, w, rect[3] - 12)


def _panel(game, x_off: int = 0, w: int = None, title: str = "") -> tuple:
    r = _srect(x_off, w)
    y = layout.panel(game.screen, r, title)
    return r, y


def _shortcut_footer(screen, rect, specs) -> None:
    """Draw a persistent, single-row legend of a station's key shortcuts.

    ``specs`` is an ordered iterable of ``(key, description_i18n_key)`` pairs,
    evenly split across ``rect``, matching sonar_view's always-visible
    footer-legend pattern (layout.command_segment) instead of a plain hint.
    """
    # Two pixels up keep descenders clear of the panel's bottom frame.
    rect = pygame.Rect(rect).move(0, -2)
    specs = tuple(specs)
    if not specs:
        return
    # Segments share the row by the width their text needs, so a long key
    # (Backspace) never gets cut while a short one wastes space.
    face = layout.font(11)
    needs = [layout.text_width(face, f"{localize(key)} {localize(description)}") + 16
             for key, description in specs]
    spare = max(0, rect.w - sum(needs))
    x = rect.x
    for index, ((key, description), need) in enumerate(zip(specs, needs)):
        width = (rect.right - x if index == len(specs) - 1
                 else need + spare // len(specs))
        segment = pygame.Rect(x, rect.y, max(1, width), rect.h)
        layout.command_segment(screen, segment, key, description, size=11)
        # A click on the legend presses its key (full mouse control).
        pointer.add_legend(segment, key)
        x += width


PAGE_TAB_H = 26
PAGE_TAB_GAP = 4


def _station_page_tab_rects(station_rect: pygame.Rect, n_pages: int) -> list:
    """Evenly spaced tab rectangles below the station title row."""
    if n_pages <= 1:
        return []
    x0 = station_rect.x + 14
    total_w = station_rect.w - 28
    tab_w = total_w // n_pages
    # Title occupies ~y+8 .. y+8+font_linesize; place tabs below that.
    title_h = layout.font(20, bold=True).get_linesize()
    y = station_rect.y + 8 + int(title_h * 1.15) + 6
    tabs = []
    for i in range(n_pages):
        w = tab_w - 4 if i < n_pages - 1 else tab_w
        tabs.append(pygame.Rect(x0 + i * tab_w, y, w, PAGE_TAB_H))
    return tabs


def draw_station_page_tabs(screen, station_rect, pages, current_page,
                           tr=None) -> list:
    """Render a row of clickable page tabs. Returns the tab rects."""
    from src.core.i18n import display_message, translation_scope
    tabs = _station_page_tab_rects(station_rect, len(pages))
    for i, (name, tab) in enumerate(zip(pages, tabs)):
        active = (i == current_page)
        # The station's own hit test (station_page_tab_at) takes the click.
        pointer.add_hotspot(tab)
        if active:
            pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE, tab)
            pygame.draw.line(screen, config.COLOR_SONAR_RING,
                              tab.topleft, (tab.right - 1, tab.top), 2)
        # The page's catalog message (its short form fits narrow tabs), never
        # its translated text again: "Navigation" is also a German value.
        with translation_scope(tr) if tr is not None else _no_scope():
            layout.blit_line(screen, display_message("station_page", name), tab,
                             config.COLOR_TEXT if active else config.COLOR_TEXT_DIM,
                             size=14, align="center")
    return tabs


def station_page_tab_at(pos, station_rect, n_pages):
    """Return the 0-based page index if *pos* hits a tab, else None."""
    if pos is None or n_pages <= 1:
        return None
    for i, tab in enumerate(_station_page_tab_rects(station_rect, n_pages)):
        if tab.collidepoint(pos):
            return i
    return None


def _station_content_top(station_rect, n_pages) -> int:
    """Y coordinate where paged content starts (below title + tabs)."""
    base = station_rect.y + 8
    title_h = layout.font(20, bold=True).get_linesize()
    base += int(title_h * 1.15) + 6
    if n_pages > 1:
        base += PAGE_TAB_H + PAGE_TAB_GAP
    return base


@localized
def draw_autocrew_overview(game, tr=None) -> None:
    """Render the host-only nine-station automation overview."""
    layout.configure_for(game)
    r, y = _panel(game, title="autocrew.overview.title")
    x = r[0] + 14
    width = r[2] - 28
    gap = 12
    card_w = (width - gap * 2) // 3
    card_h = (r[1] + r[3] - y - gap * 2) // 3
    for index, key in enumerate(game.autocrew.enabled):
        row, column = divmod(index, 3)
        rect = (x + column * (card_w + gap), y + row * (card_h + gap),
                card_w, card_h)
        content = layout.box(game.screen, rect, message(
            "autocrew.station", station=display_value("station", key.upper())))
        cx, cy, cw, _ = content
        status = game.autocrew.status(game, key)
        color = (config.COLOR_OK if status == "active" else
                 config.COLOR_WARN if status in ("suspended_remote", "blocked_damage")
                 else config.COLOR_TEXT_DIM)
        layout.blit_line(game.screen, "autocrew.status." + status,
                         (cx, cy, cw, 24), color, size=16)
        layout.blit_block(game.screen,
                          "autocrew.action." + game.autocrew.last_action[key],
                          cx, cy + 30, cw, max(24, card_h - 72),
                          config.COLOR_TEXT_DIM, size=13)


def _observation_bearing(observation) -> float:
    return observations.bearing(observation)


def _observation_position(observation):
    return observations.position(observation)


def _displayed_bearing(observation, ship) -> float:
    return observations.bearing(observation, ship)


def _state_color(state: str) -> tuple:
    return {
        "OK": config.COLOR_OK,
        "BESCHAEDIGT": config.COLOR_WARN,
        "FLUTEND": config.COLOR_DANGER,
        "ZERSTOERT": config.COLOR_DANGER,
    }[state]


def _compartment_name(key: str, fallback: str) -> str:
    """Localize fixed ship compartments without touching authored content."""
    catalog_key = "compartment." + key
    translated = localize(catalog_key)
    return fallback if translated == catalog_key else translated
