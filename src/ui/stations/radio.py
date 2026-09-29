"""Radio room view: HFDF bearings and teletype (verbatim from ``stations_view``)."""


import math

import pygame

from src.core import config
from src.core.i18n import localized, message, raw_text
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
    elif page == 2:
        _draw_tasks(game, s, x, cy, w, box_h)
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
        ("↑/↓", "radio.footer.task_select"),
        ("A", "radio.footer.accept"),
        ("D", "radio.footer.decline"),
        ("R", "radio.footer.ras"),
    ) if page == 2 else (
        ("↑/↓", "radio.footer.select"),
        ("Enter", "radio.footer.log"),
    ))


def task_line(game, row) -> object:
    """One task in the list: label, kind, state and its clock."""
    if row["state"] == "offered":
        clock = message("radio.task.clock.respond", seconds=f"{row['respond_s']:.0f}")
    elif row["remaining_s"] is not None:
        clock = message("radio.task.clock.remaining",
                        minutes=f"{row['remaining_s'] / 60.0:.0f}")
    else:
        clock = message("radio.task.clock.points", points=f"{row['points']:+d}")
    return message("radio.task.line", task=f"{row['kind'].upper()} {row['id']}",
                   kind=message("radio.task.kind." + row["kind"]),
                   state=message("radio.task.state." + row["state"]), clock=clock)


def task_detail_lines(game, row) -> list:
    """The selected task's order and its state, one line each."""
    lines = [message("radio.task.brief." + row["kind"],
                     name=raw_text(row["name"] or "-"), persons=row["persons"])]
    lines.append(message("radio.task.position", x=f"{row['x']:.1f}", y=f"{row['y']:.1f}",
                         bearing=f"{row['bearing']:03.0f}", range=f"{row['range_nm']:.1f}",
                         radius=f"{row['radius_nm']:.1f}"))
    if row["course"] is not None:
        lines.append(message("radio.task.motion", course=f"{row['course']:03.0f}",
                             speed=f"{row['speed_kn']:.0f}"))
    if row["kind"] == "sar":
        lines.append(message("radio.task.sighted" if row["sighted"]
                             else "radio.task.not_sighted"))
    if row["state"] in ("active", "done") and row["kind"] != "identify":
        lines.append(message("radio.task.progress", progress=f"{row['progress']:.0%}"))
    if row["kind"] == "ras" and row["state"] in ("offered", "active"):
        lines.append(game.ras_stores_line())
    if row["verdict"] is not None:
        lines.append(message("radio.task.verdict." + row["verdict"]))
    if row["state"] == "offered":
        lines.append(message("radio.task.answer_hint"))
    return lines


def _draw_report_status(game, s, rect) -> None:
    """The radio room's own calls: on the air, waiting, or ready (K / H)."""
    view = game.report_view()
    if view["transmitting"]:
        text, color = message("radio.report.status_on_air",
                              seconds=f"{view['tx_left_s']:.0f}"), config.COLOR_WARN
    elif view["ready_in_s"] > 0.0:
        text, color = message("radio.report.status_wait",
                              minutes=f"{math.ceil(view['ready_in_s'] / 60.0):.0f}"), \
            config.COLOR_TEXT_DIM
    else:
        text, color = message("radio.report.status_ready"), config.COLOR_TEXT
    layout.blit_line(s, text, rect, color, size=15)


def _draw_tasks(game, s, x, cy, w, box_h) -> None:
    split = int(w * .5)
    left = layout.box(s, (x, cy, split - 6, box_h), "panel.tasks")
    right = layout.box(s, (x + split + 6, cy, w - split - 6, box_h), "panel.task_detail")
    rows = game.task_view()
    lx, ly, lw, lh = left
    _draw_report_status(game, s, (lx, ly + lh - 24, lw, 22))
    lh -= 30
    if not rows:
        layout.blit_line(s, "radio.task.none" if game.tasking.enabled
                         else "radio.task.disabled",
                         (lx, ly, lw, 26), config.COLOR_TEXT_DIM, size=18)
        if game.tasking.enabled:
            layout.blit_line(s, game.ras_stores_line(), (lx, ly + 34, lw, 24),
                             config.COLOR_TEXT_DIM, size=16)
            layout.blit_line(s, "radio.task.ras_hint", (lx, ly + 62, lw, 24),
                             config.COLOR_TEXT_DIM, size=16)
        return
    selected_idx = min(max(0, game.task_sel), len(rows) - 1)
    row_h = 34
    for index, row in enumerate(rows[:max(1, (lh - 8) // row_h)]):
        selected = index == selected_idx
        if selected:
            pygame.draw.rect(s, config.COLOR_SELECT_BG, (lx - 5, ly - 2, lw + 10, row_h - 4))
            pygame.draw.rect(s, config.COLOR_WARN, (lx - 5, ly - 2, 3, row_h - 4))
        color = (config.COLOR_WARN if row["state"] == "offered"
                 else config.COLOR_TEXT if row["state"] == "active"
                 else config.COLOR_OK if row["state"] == "done"
                 else config.COLOR_TEXT_DIM)
        layout.blit_line(s, task_line(game, row), (lx, ly, lw, row_h - 8), color, size=17)
        ly += row_h
    rx, ry, rw, rh = right
    lines = task_detail_lines(game, rows[selected_idx])
    # The order itself wraps over three lines; the facts are one line each.
    layout.blit_block(s, lines[0], rx, ry, rw, 72, color=config.COLOR_TEXT, size=16)
    ry += 80
    for text in lines[1:]:
        if ry + 24 > right[1] + rh:
            break
        layout.blit_line(s, text, (rx, ry, rw, 24), config.COLOR_TEXT, size=16)
        ry += 28
