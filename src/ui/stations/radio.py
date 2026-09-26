"""Radio room view: HFDF bearings and teletype (verbatim from ``stations_view``)."""


import pygame

from src.core import config
from src.core.i18n import localized, raw_text
from src.core.station import Station
from src.ui import layout
from src.ui import observations


from src.ui.stations.common import (
    _hfdf_error_deg,
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Funkraum (M13) --------------------------------------------------------

@localized
def draw_radio_view(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.RADIO]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.radio.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    x = r[0] + 14
    w = r[2] - 28
    box_h = station_rect.bottom - cy - 34

    if page == 0:
        # Current intercepts left; the operator's logged bearings and the
        # resulting cross-fixes right (same data as the Remote Crew radio).
        split = int(w * .56)
        left = layout.box(s, (x, cy, split - 6, box_h), "panel.hfdf")
        log_box = layout.box(s, (x + split + 6, cy, w - split - 6, box_h), "panel.hfdf_log")
        gx, gy, gw, gh = log_box
        logged = list(game.hfdf_log)[-6:]
        if not logged:
            layout.blit_line(s, "radio.log_empty", (gx, gy, gw, 24),
                             config.COLOR_TEXT_DIM, size=16)
        for row in reversed(logged):
            layout.blit_line(s, message(
                "radio.line.logged", label=raw_text(row["label"]),
                bearing=f"{row['bearing'] % 360:05.1f}",
                x=f"{row['observer_x']:.1f}", y=f"{row['observer_y']:.1f}",
                age=f"{max(0.0, game.sim_t - row['t']):.0f}"),
                (gx, gy, gw, 24), config.COLOR_TEXT, size=16)
            gy += 26
        gy += 8
        for fix in list(game.hfdf_fixes.values())[-4:]:
            if gy + 24 > log_box[1] + gh:
                break
            layout.blit_line(s, message(
                "radio.line.fix", label=raw_text(fix["label"]),
                sigma=f"{fix['sigma_nm']:.1f}",
                age=f"{max(0.0, game.sim_t - fix['t']):.0f}"),
                (gx, gy, gw, 24), config.COLOR_OK, size=16)
            gy += 26
        lx, ly, lw, _ = left
        reports = game.hfdf_bearings()
        row_h = 34
        if not reports:
            layout.blit_line(s, "panel.no_transmission", (lx, ly, lw, 26),
                             config.COLOR_TEXT_DIM, size=18)
        else:
            capacity = max(1, (left[3] - 60) // row_h)
            selected_idx = min(game.radio_sel, len(reports) - 1)
            start = max(0, min(selected_idx - capacity // 2,
                               len(reports) - capacity))
            for i, report in enumerate(reports[start:start + capacity], start):
                selected = i == selected_idx
                if selected:
                    pygame.draw.rect(s, config.COLOR_SELECT_BG,
                                     (lx - 5, ly - 2, lw + 10, row_h - 4))
                    pygame.draw.rect(s, config.COLOR_WARN,
                                     (lx - 5, ly - 2, 3, row_h - 4))
                age = report.age(game.sim_t)
                layout.blit_line(
                    s, message("radio.line.signal", prefix='>' if selected else ' ',
                                label=game.hfdf_display_id(report),
                                bearing=observations.format_bearing(report, game.ship),
                               error=f"{_hfdf_error_deg(report):.0f}", age=f"{age:.0f}"),
                    (lx, ly, lw, row_h - 8),
                    config.COLOR_WARN if selected else
                    config.COLOR_TEXT if age < 30 else config.COLOR_TEXT_DIM,
                    size=17)
                ly += row_h
        ly = left[1] + left[3] - 34
        if game.hfdf_log:
            layout.blit_line(s, message("radio.line.log_fix", log=len(game.hfdf_log), fixes=len(game.hfdf_fixes)),
                             (lx, ly, lw, 24), config.COLOR_OK, size=16)
    else:
        right = layout.box(s, (x, cy, w, box_h), "panel.messages")
        rx, ry, rw, rh = right
        msgs = game.messages[-10:] if game.messages else [("--:--", message("ui.no_traffic"))]
        row_h = max(46, (rh - 40) // max(1, len(msgs)))
        for row, (stamp, txt) in enumerate(msgs):
            if row == len(msgs) - 1:
                pygame.draw.rect(s, (20, 38, 27), (rx - 4, ry - 2, rw + 8, row_h - 2))
            layout.blit_line(s, stamp, (rx, ry, 90, 26), config.COLOR_OK, size=17)
            pygame.draw.line(s, config.COLOR_GRID, (rx + 94, ry), (rx + 94, ry + row_h - 5))
            layout.blit_block(s, txt, rx + 104, ry, rw - 104, row_h - 3,
                               color=config.COLOR_TEXT, size=16)
            ry += row_h

    _shortcut_footer(s, (x, station_rect.bottom - 26, w, 20), (
        ("↑/↓", "radio.footer.select"),
        ("Enter", "radio.footer.log"),
    ))
