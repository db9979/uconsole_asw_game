"""Radio room view: HFDF bearings and teletype (verbatim from ``stations_view``)."""


import math

import pygame

from src.core import config
from src.core.i18n import localized, message, raw_text
from src.core.station import Station
from src.ui import layout, pointer
from src.ui import observations


from src.ui.stations.radio_chart import CHART_WINDOW_S, chart_half_nm, draw_hfdf_chart
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
        # Current intercepts and the DF rose left; the cross-fix chart with
        # the operator's logged bearings and fixes right.
        regions = hfdf_regions(x, cy, w, box_h)
        left = layout.box(s, regions["left"], "panel.hfdf")
        _draw_chart_and_log(game, s, layout.box(s, regions["right"], "panel.hfdf_chart"))
        lx, ly, lw, _ = left
        reports = game.hfdf_bearings()
        row_h = 34
        # The lower part of the box is the DF rose: live bearings with their
        # error wedge, logged bearings dim.
        rose_h = max(0, left[3] - 34 - 4 * row_h)
        if rose_h >= 150:
            from src.ui import console
            selected_idx = min(game.radio_sel, len(reports) - 1) if reports else -1
            strobes = [(float(row["bearing"]) % 360, config.COLOR_TEXT_DIM, 1, 0, .6)
                       for row in list(game.hfdf_log)[-6:]]
            strobes += [(observations.bearing(report, game.ship), config.COLOR_WARN
                         if i == selected_idx else config.COLOR_HFDF,
                         3 if i == selected_idx else 2, _hfdf_error_deg(report), .25)
                        for i, report in enumerate(reports[:12])]
            rose = pygame.Rect(lx, left[1] + left[3] - 34 - rose_h, lw, rose_h)
            console.bearing_rose(s, rose, strobes, course=game.ship.course, title="radio:rose")
            storm = game.world.thunderstorm()
            if storm > 0.0:
                from src.ui import sferics
                sferics.draw_rose(s, rose.center, min(rose.w, rose.h) // 2 - 20, storm, game._t)
                sferics.draw_label(s, (rose.x, rose.bottom, rose.w, 16), storm)
        if not reports:
            layout.blit_line(s, "panel.no_transmission", (lx, ly, lw, 26),
                             config.COLOR_TEXT_DIM, size=18)
        else:
            capacity = max(1, ((left[3] - 60) if rose_h < 150 else 4 * row_h) // row_h)
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
                # A click on a signal selects it, as ↑/↓ would.
                pointer.add_action((lx - 5, ly - 2, lw + 10, row_h - 4),
                                   lambda _pos, index=i: setattr(game, "radio_sel", index))
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
        # The language model's wording, when there is one, replaces the
        # catalog line (fewer, taller rows; the feed keeps the original).
        worded = getattr(game, "llm_radio_text", None)
        count = 6 if worded is not None and game.llm_radio.styled else 10
        msgs = game.messages[-count:] if game.messages else [("--:--", message("ui.no_traffic"))]
        row_h = max(46, (rh - 40) // max(1, len(msgs)))
        for row, (stamp, txt) in enumerate(msgs):
            styled = worded(stamp, txt) if worded is not None and game.messages else None
            if styled is not None:
                txt = raw_text(styled)
            if row == len(msgs) - 1:
                pygame.draw.rect(s, config.COLOR_SELECT_BG, (rx - 4, ry - 2, rw + 8, row_h - 2))
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


# Page 1: share of the width for the intercepts and the DF rose (the rest is
# the cross-fix chart), and the log rows under the chart.
HFDF_LEFT_SHARE = .4
HFDF_LOG_ROWS = 4


def hfdf_regions(x, cy, w, box_h) -> dict:
    """Page 1 geometry shared by drawing and the station tooltips."""
    split = int(w * HFDF_LEFT_SHARE)
    return {"left": pygame.Rect(x, cy, split - 6, box_h),
            "right": pygame.Rect(x + split + 6, cy, w - split - 6, box_h)}


def _draw_chart_and_log(game, s, inner) -> None:
    """The cross-fix chart, with the newest logged bearings (left) and the
    fixes (right) in two columns below it."""
    gx, gy, gw, gh = inner
    row_h = max(22, layout.font(15).get_linesize() + 2)
    chart = pygame.Rect(gx, gy, gw, max(1, gh - HFDF_LOG_ROWS * row_h - 8))
    reports = game.hfdf_bearings()
    selected = (game.hfdf_display_id(reports[min(game.radio_sel, len(reports) - 1)])
                if reports else None)
    view = draw_hfdf_chart(s, game, chart, selected)
    if view is not None:
        layout.blit_line(s, message("radio.chart.scale", range=f"{chart_half_nm(view):.0f}"),
                         (chart.x + 6, chart.bottom - 24, 180, layout.font(14).get_linesize()),
                         config.COLOR_TEXT_DIM, size=14)
    top = chart.bottom + 8
    column = (gw - 12) // 2
    logged = list(game.hfdf_log)[-HFDF_LOG_ROWS:]
    if not logged:
        layout.blit_line(s, "radio.log_empty", (gx, top, gw, row_h),
                         config.COLOR_TEXT_DIM, size=15)
        pointer.add_token_keys((gx, top, gw, row_h), "radio.log_empty", 15,
                               (("Enter", "Enter"),))
    for index, row in enumerate(reversed(logged)):
        age = max(0.0, game.sim_t - row["t"])
        layout.blit_line(s, message(
            "radio.line.logged", label=raw_text(row["label"]),
            bearing=f"{row['bearing'] % 360:05.1f}",
            x=f"{row['observer_x']:.1f}", y=f"{row['observer_y']:.1f}",
            age=f"{age:.0f}"),
            (gx, top + index * row_h, column, row_h),
            config.COLOR_TEXT if age <= CHART_WINDOW_S else config.COLOR_TEXT_DIM, size=15)
    fixes = list(game.hfdf_fixes.values())[-HFDF_LOG_ROWS:]
    for index, fix in enumerate(reversed(fixes)):
        age = max(0.0, game.sim_t - fix["t"])
        layout.blit_line(s, message(
            "radio.line.fix", label=raw_text(fix["label"]),
            sigma=f"{fix['sigma_nm']:.1f}", age=f"{age:.0f}"),
            (gx + column + 12, top + index * row_h, column, row_h),
            config.COLOR_OK if age <= CHART_WINDOW_S else config.COLOR_TEXT_DIM, size=15)


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
    pointer.add_token_keys(rect, text, 15, (("K", "K"), ("H", "H")))


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
            pointer.add_token_keys((lx, ly + 62, lw, 24), "radio.task.ras_hint", 16,
                                   (("R", "R"),))
        return
    selected_idx = min(max(0, game.task_sel), len(rows) - 1)
    row_h = 34
    for index, row in enumerate(rows[:max(1, (lh - 8) // row_h)]):
        selected = index == selected_idx
        pointer.add_action((lx - 5, ly - 2, lw + 10, row_h - 4),
                           lambda _pos, index=index: setattr(game, "task_sel", index))
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
