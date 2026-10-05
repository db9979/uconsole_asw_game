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


# Which slice of an overflowing footer is shown, per footer row (UI state
# only, never saved): the "more" chip steps through the rest.
_FOOTER_OFFSET: dict = {}
_FOOTER_MORE = "panel.more"


def footer_page(specs, needs, width, more_w, offset):
    """Indices of ``specs`` shown from ``offset`` on, and whether a "more"
    chip is needed: as many whole segments as fit the row."""
    if sum(needs) <= width:
        return list(range(len(specs))), False
    shown, used = [], more_w
    for index in range(offset, len(specs)):
        if used + needs[index] > width and shown:
            break
        shown.append(index)
        used += needs[index]
    return shown, True


def footer_needs(specs) -> list:
    """Width each ``(key, description)`` chip of a key bar needs."""
    face = layout.font(11)
    from src.core.i18n import key_label
    return [layout.text_width(face, f"{key_label(key)} {localize(description)}") + 16
            for key, description in specs]


def _shortcut_footer(screen, rect, specs) -> None:
    """Draw a persistent, single-row legend of a station's key shortcuts.

    ``specs`` is an ordered iterable of ``(key, description_i18n_key)`` pairs,
    split across ``rect``, matching sonar_view's always-visible footer-legend
    pattern (layout.command_segment). Every chip presses its key on a click;
    keys that do not fit go behind a "more" chip that pages through them.
    """
    # Two pixels up keep descenders clear of the panel's bottom frame.
    rect = pygame.Rect(rect).move(0, -2)
    specs = tuple(specs)
    if not specs:
        return
    # Segments share the row by the width their text needs, so a long key
    # (Backspace) never gets cut while a short one wastes space.
    needs = footer_needs(specs)
    more_w = footer_needs((("+", _FOOTER_MORE),))[0]
    slot = (rect.x, rect.y, rect.w, len(specs))
    offset = _FOOTER_OFFSET.get(slot, 0)
    if offset >= len(specs):
        offset = 0
    shown, more = footer_page(specs, needs, rect.w, more_w, offset)
    if more and offset and not shown:
        offset, shown = 0, footer_page(specs, needs, rect.w, more_w, 0)[0]
    _FOOTER_OFFSET[slot] = offset
    room = rect.w - (more_w if more else 0)
    spare = max(0, room - sum(needs[i] for i in shown))
    x = rect.x
    for position, index in enumerate(shown):
        key, description = specs[index]
        width = (rect.x + room - x if position == len(shown) - 1
                 else needs[index] + spare // max(1, len(shown)))
        segment = pygame.Rect(x, rect.y, max(1, width), rect.h)
        layout.command_segment(screen, segment, key, description, size=11, center=True)
        # A click on the legend presses its key (full mouse control).
        pointer.add_legend(segment, key)
        x += width
    if more:
        nxt = shown[-1] + 1 if shown else 0
        segment = pygame.Rect(rect.right - more_w, rect.y, more_w, rect.h)
        layout.command_segment(screen, segment, "+", _FOOTER_MORE, size=11, center=True)
        step_to = nxt if nxt < len(specs) else 0

        def page(_pos=None, slot=slot, step_to=step_to):
            _FOOTER_OFFSET[slot] = step_to
        pointer.add_action(segment, page)


def list_window(screen, rect, first: int, shown: int, total: int,
                up="↑", down="↓") -> None:
    """One row under a scrolling list: which part of it is on show, and that
    the arrows (or the wheel over the list) move it. Nothing when it all fits."""
    rect = pygame.Rect(rect)
    pointer.add_scroll(rect.inflate(0, 400).move(0, -200), up, down)
    if shown >= total or shown <= 0 or rect.w <= 0:
        return
    layout.blit_line(screen, message("list.window", first=first + 1,
                                     last=first + shown, total=total),
                     rect, config.COLOR_TEXT_DIM, size=13, align="center")


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
        # The page's catalog message (its short form fits narrow tabs), never
        # its translated text again: "Navigation" is also a German value.
        with translation_scope(tr) if tr is not None else _no_scope():
            layout.tab(screen, tab, display_message("station_page", name), active)
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
    from src.ui import game_menu
    game_menu.close_button(game.screen, r)       # F3 / Esc by mouse
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
