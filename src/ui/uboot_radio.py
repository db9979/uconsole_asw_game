"""The crewed boat's radio room page and HQ's contact report on the chart.

Draws ``boat_radio`` state: the broadcast schedule, the copy and transmit
progress, HQ's latest contact report (modelled intelligence with its age and
error circle, never the frigate's live position) and the message log.
"""

from __future__ import annotations

import math

import pygame

from src.core import boat_nav, buoy_antenna, config
from src.core.boat_radio import antenna_up, reception
from src.core.i18n import message, raw_text
from src.ui import layout, lines, pointer

REPORT_COLOR = config.COLOR_WARN
# A contact report is drawn on the chart until it is this old (s).
CHART_REPORT_S = 3600.0


def _clock(seconds) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:d}:{seconds % 60:02d}"


def report_lines(game, boat, report) -> list:
    """Text lines of one HQ contact report, seen from the boat's navigated
    position now."""
    bx, by = boat_nav.position(boat)
    dx, dy = report["x"] - bx, report["y"] - by
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    age_min = max(0.0, game.sim_t - report["as_of"]) / 60.0
    return [message("uboot.radio.report_position", bearing=f"{bearing:03.0f}",
                    range=f"{math.hypot(dx, dy):.1f}", radius=f"{report['radius_nm']:.0f}"),
            message("uboot.radio.report_motion", course=f"{report['course']:03.0f}",
                    speed=f"{report['speed_kn']:.0f}", age=f"{age_min:.0f}")]


def order_line(game, boat):
    """The open HQ order as one line (bearing and range from the boat now),
    or the tally of closed ones."""
    radio = boat.radio
    order = radio.active_order()
    if order is None:
        done = sum(1 for row in radio.orders if row["state"] == "done")
        failed = sum(1 for row in radio.orders if row["state"] == "failed")
        if done or failed:
            return message("uboot.radio.order_closed", done=str(done), failed=str(failed))
        return message("uboot.radio.order_none")
    left = _clock(order["deadline_t"] - game.sim_t)
    if order["kind"] not in ("area", "report", "silence"):
        # The free patrol's own kinds (src/core/free_roam.py).
        from src.core import free_roam
        return free_roam.order_text(game, boat, order)
    if order["kind"] == "area":
        bx, by = boat_nav.position(boat)
        dx, dy = order["x"] - bx, order["y"] - by
        return message("uboot.radio.order_area", number=str(order["id"]),
                       bearing=f"{math.degrees(math.atan2(dx, -dy)) % 360.0:03.0f}",
                       range=f"{math.hypot(dx, dy):.1f}",
                       radius=f"{order['radius_nm']:.0f}", left=left)
    return message("uboot.radio.order_" + order["kind"], number=str(order["id"]), left=left)


def buoy_line(boat):
    """The towed buoy antenna's state line (``buoy_antenna.py``)."""
    state = boat.orders.buoy
    return message("uboot.radio.buoy." + buoy_antenna.status(state),
                   percent=f"{state[0] * 100:.0f}",
                   depth=f"{config.UBOOT_BUOY_DEPTH_M:.0f}",
                   speed=f"{config.UBOOT_BUOY_SPEED_KN:.0f}")


def log_text(game, row):
    age = _clock(game.sim_t - row["t"])
    if row["kind"] == "broadcast":
        key = ("uboot.radio.log.broadcast_report" if row["report"] is not None
               else "uboot.radio.log.broadcast")
        text = message(key, age=age, number=str(row["number"]))
        if row["ack"]:
            text = message("uboot.radio.log.with_ack", entry=text)
        if row.get("order") is not None:
            text = message("uboot.radio.log.with_order", entry=text, number=str(row["order"]))
        return text
    if row["kind"] == "sent":
        return message("uboot.radio.log.sent", age=age, number=str(row["number"]))
    return message("uboot.radio.log.aborted", age=age)


def _box_height(inner: int) -> int:
    """Outer height of a titled ``layout.box`` whose inner rect is ``inner`` tall."""
    return 8 + layout.font(16, bold=True).get_linesize() + 8 + inner + 8


def draw_radio_page(s, game, boat, x, y, w, h) -> None:
    radio = boat.radio
    progress = radio.progress(game, boat)
    up = antenna_up(boat)
    mode = reception(boat)
    row = layout.line_pitch(16, 2)
    box = layout.box(s, (x, y, w, _box_height(4 * row + 24)), "uboot.panel.radio",
                     border=config.COLOR_WARN if radio.transmitting else config.COLOR_TEXT)
    bx, by, bw, _ = box
    antenna = ("uboot.radio.antenna_up" if up else "uboot.radio.antenna_buoy"
               if mode == "buoy" else "uboot.radio.antenna_vlf"
               if mode == "vlf" else "uboot.radio.antenna_down")
    layout.blit_line(s, antenna, (bx, by, bw, row), config.COLOR_OK if up else config.COLOR_TEXT
                     if mode in ("vlf", "buoy") else config.COLOR_TEXT_DIM, size=16)
    pointer.add_token_keys((bx, by, bw, row), antenna, 16, (("(P)", "P"),), screen=s)
    number = str(progress["broadcast"])
    if progress["copied"]:
        state = message("uboot.radio.broadcast_copied", number=number)
    elif progress["copy"] is not None:
        state = message("uboot.radio.broadcast_copying", number=number,
                        percent=f"{progress['copy'] * 100:.0f}")
    else:
        state = message("uboot.radio.broadcast_missed", number=number)
    layout.blit_line(s, message("uboot.radio.schedule", state=state,
                                next=_clock(progress["next_s"])),
                     (bx, by + row, bw, row), config.COLOR_TEXT, size=16)
    layout.meter(s, (bx + 2, by + 2 * row + 3, bw - 4, 6),
                 progress["copy"] if not progress["copied"] else 1.0, config.COLOR_OK)
    if progress["send"] is not None:
        send = message("uboot.radio.sending", percent=f"{progress['send'] * 100:.0f}")
        color = config.COLOR_WARN
    else:
        send = message("uboot.radio.sitreps_ack" if progress["ack_due"]
                       else "uboot.radio.sitreps", count=str(progress["sitreps"]))
        color = config.COLOR_TEXT
    layout.blit_line(s, send, (bx, by + 2 * row + 12, bw, row), color, size=16)
    layout.meter(s, (bx + 2, by + 3 * row + 15, bw - 4, 6), progress["send"],
                 config.COLOR_WARN)
    layout.blit_line(s, buoy_line(boat), (bx, by + 3 * row + 24, bw, row),
                     config.COLOR_WARN if boat.orders.buoy[2] else config.COLOR_TEXT, size=16)
    pointer.add_token_keys((bx, by + 3 * row + 24, bw, row), buoy_line(boat), 16,
                           (("(B)", "B"),), screen=s)
    top = box[1] + box[3] + 8 + 8
    latest = radio.latest_report()
    report = layout.box(s, (x, top, w, _box_height(2 * row)), "uboot.panel.hq_report")
    rx, ry, rw, _ = report
    if latest is None:
        layout.blit_line(s, "uboot.radio.no_report", (rx, ry, rw, row),
                         config.COLOR_TEXT_DIM, size=16)
    else:
        for index, text in enumerate(report_lines(game, boat, latest["report"])):
            layout.blit_line(s, text, (rx, ry + index * row, rw, row), REPORT_COLOR, size=16)
    top = report[1] + report[3] + 8 + 8
    orders = layout.box(s, (x, top, w, _box_height(row)), "uboot.panel.hq_order")
    ox, oy, ow, _ = orders
    layout.blit_line(s, order_line(game, boat), (ox, oy, ow, row),
                     config.COLOR_WARN if radio.active_order() is not None
                     else config.COLOR_TEXT_DIM, size=16)
    top = orders[1] + orders[3] + 8 + 8
    listing = layout.box(s, (x, top, w, max(40, h - (top - y))), "uboot.panel.radio_log")
    lx, ly, lw, lh = listing
    log_row = layout.line_pitch(14, 2)
    # The open order worded as radio traffic by the optional language model.
    worded = getattr(game, "llm_boat_order_text", None)
    worded = worded(radio.active_order()) if worded is not None else None
    if worded:
        block_h = min(lh // 2, 3 * log_row + 6)
        layout.blit_block(s, raw_text(worded), lx, ly, lw, block_h,
                          color=config.COLOR_WARN, size=14)
        ly += block_h
        lh -= block_h
    if not radio.log:
        layout.blit_line(s, "uboot.radio.log.empty", (lx, ly, lw, log_row),
                         config.COLOR_TEXT_DIM, size=15)
    for index, row_data in enumerate(list(reversed(radio.log))[:max(0, lh // log_row)]):
        layout.blit_line(s, log_text(game, row_data), (lx, ly + index * log_row, lw, log_row),
                         config.COLOR_WARN if row_data["kind"] != "broadcast"
                         else config.COLOR_TEXT, size=14)


def draw_report_chart(game, boat, view) -> None:
    from src.ui.map_view import _map_label
    """HQ's latest contact report: error circle, reported course and its age;
    and the area of an open HQ order."""
    order = boat.radio.active_order()
    if order is not None and order["x"] is not None:
        x, y = order["x"], order["y"]
        if order["kind"] == "attack":
            # The ordered merchant's reported position, dead-reckoned.
            from src.core import free_roam
            x, y = free_roam.target_position(order, game.sim_t)
        ox, oy = view.world_to_screen(x, y)
        radius = max(6, int(order["radius_nm"] * view.scale))
        pygame.draw.circle(game.screen, config.COLOR_OK, (int(ox), int(oy)), radius, 1)
        _map_label(game.screen, game, message("uboot.radio.chart_order", number=str(order["id"])),
                   (int(ox) + 8, int(oy) - radius - 20), config.COLOR_OK, config.MAP_RECT,
                   size=12)
    latest = boat.radio.latest_report()
    if latest is None:
        return
    report = latest["report"]
    age = game.sim_t - report["as_of"]
    if not 0.0 <= age <= CHART_REPORT_S:
        return
    s = game.screen
    px, py = view.world_to_screen(report["x"], report["y"])
    radius = max(6, int(report["radius_nm"] * view.scale))
    pygame.draw.circle(s, REPORT_COLOR, (int(px), int(py)), radius, 1)
    rad = math.radians(report["course"])
    lines.line(s, REPORT_COLOR, (int(px), int(py)),
               (int(px + 24 * math.sin(rad)), int(py - 24 * math.cos(rad))), 2)
    _map_label(s, game, message("uboot.radio.chart_label", age=f"{age / 60.0:.0f}"),
               (int(px) + 8, int(py) - radius - 20), REPORT_COLOR, config.MAP_RECT, size=12)
