"""The crewed boat's threat page: counter-detection picture and evasion.

Draws ``boat_threat.picture`` (the boat's own intercepts, layer, noise and
mast) and the evasion order the I key would give.  No hostile truth.
"""

from __future__ import annotations

import math

import pygame

from src.core import boat_threat, config
from src.core.i18n import message
from src.ui import layout, lines

KIND_COLORS = {"hull": config.COLOR_WARN, "dipping": config.COLOR_WARN,
               "buoy": config.COLOR_TEXT, "splash": config.COLOR_TEXT_DIM,
               "torpedo": config.COLOR_DANGER}
# Intercept bearing lines on the chart stay this long (s).
CHART_LINE_S = 120.0


def _fmt(value, pattern="{:.0f}"):
    return "-" if value is None else pattern.format(value)


def draw_threat_page(s, game, boat, x, y, w, h) -> None:
    view = boat_threat.picture(game, boat)
    counts = view["counts"]
    danger = counts["torpedo"] > 0 or view["echo_likely"]
    # Box heights follow the face: frame and title, then whole text rows.
    row, small = layout.line_pitch(16, 2), layout.line_pitch(15, 1)
    frame = layout.line_pitch(16, 16, bold=True) + 8
    box = layout.box(s, (x, y, w, frame + 3 * row), "uboot.panel.counter_detection",
                     border=config.COLOR_DANGER if danger else config.COLOR_WARN
                     if any(counts.values()) else config.COLOR_TEXT)
    bx, by, bw, _ = box
    layout.blit_line(s, message("uboot.threat_page.pings", hull=str(counts["hull"]),
                                dipping=str(counts["dipping"]), buoy=str(counts["buoy"])),
                     (bx, by, bw, row), config.COLOR_TEXT, size=16)
    if view["loudest_db"] is None:
        loud = message("uboot.threat_page.no_ping")
    else:
        loud = message("uboot.threat_page.loudest", level=_fmt(view["loudest_db"]),
                       assessment=message("uboot.threat_page.echo_likely"
                                          if view["echo_likely"]
                                          else "uboot.threat_page.echo_unlikely"),
                       trend=message("uboot.threat_page.trend." + (view["trend"] or "none")))
    layout.blit_line(s, loud, (bx, by + row, bw, row),
                     config.COLOR_DANGER if view["echo_likely"] else config.COLOR_TEXT, size=16)
    clock = view["clock"]
    other = (message("uboot.threat_page.other", splash=str(counts["splash"]),
                     torpedo=str(counts["torpedo"]), esm=str(view["esm_count"]))
             if clock is None else
             message("uboot.threat_page.clock", bearing=f"{round(clock['bearing']) % 360:03d}",
                     tti=str(clock["tti_s"])))
    layout.blit_line(s, other, (bx, by + 2 * row, bw, row),
                     config.COLOR_DANGER if counts["torpedo"] or clock else config.COLOR_TEXT,
                     size=16)
    own_y = y + frame + 3 * row + 8
    own = layout.box(s, (x, own_y, w, frame + 2 * row), "uboot.panel.own_signature")
    ox, oy, ow, _ = own
    layer = view["layer"]
    layout.blit_line(s, message("uboot.threat_page.layer." + layer,
                                depth=_fmt(view["depth_m"]), layer=_fmt(view["layer_m"])),
                     (ox, oy, ow, row),
                     config.COLOR_OK if layer == "below" else config.COLOR_WARN, size=16)
    noisy = view["noise"] in ("cavitating", "loud", "snorkel")
    layout.blit_line(s, message("uboot.threat_page.noise",
                                noise=message("uboot.threat_page.noise." + view["noise"]),
                                mast=message("uboot.threat_page.mast_up" if view["mast"]
                                             else "uboot.threat_page.mast_down")),
                     (ox, oy + row, ow, row),
                     config.COLOR_WARN if noisy or view["mast"] else config.COLOR_OK, size=16)
    top = own_y + frame + 2 * row + 8
    plan = boat_threat.evasion_plan(game, boat)
    advice_h = frame + 3 * small + row + 4
    advice = layout.box(s, (x, top, w, advice_h), "uboot.panel.advice")
    ax, ay, aw, _ = advice
    rows = [message(key) for key in view["advice"]] or [message("uboot.advice.none")]
    for index, text in enumerate(rows[:3]):
        layout.blit_line(s, text, (ax, ay + index * small, aw, small), config.COLOR_TEXT, size=15)
    if plan is not None:
        layout.blit_line(s, message("uboot.threat_page.plan", course=f"{plan['course']:03.0f}",
                                    speed=_fmt(plan["speed_kn"]), depth=_fmt(plan["depth_m"]),
                                    source=message("uboot.threat_page.source." + plan["kind"])),
                         (ax, ay + 3 * small + 4, aw, row), config.COLOR_WARN, size=16)
    else:
        layout.blit_line(s, "uboot.threat_page.no_plan", (ax, ay + 3 * small + 4, aw, row),
                         config.COLOR_TEXT_DIM, size=16)
    top += advice_h + 8
    listing_h = max(40, h - (top - y))
    listing = layout.box(s, (x, top, w, listing_h), "uboot.panel.intercepts")
    lx, ly, lw, lh = listing
    if not view["intercepts"]:
        layout.blit_line(s, "uboot.threat_page.no_intercepts", (lx, ly, lw, small),
                         config.COLOR_TEXT_DIM, size=15)
    line = layout.line_pitch(14, 0)
    for index, item in enumerate(view["intercepts"][:max(0, lh // line)]):
        values = dict(age=_fmt(item["age_s"]),
                      kind=message("uboot.threat_page.kind." + item["kind"]),
                      bearing=f"{item['bearing']:03.0f}")
        text = (message("uboot.threat_page.row_bearing", **values) if item["level_db"] is None
                else message("uboot.threat_page.row", level=_fmt(item["level_db"]), **values))
        layout.blit_line(s, text,
                         (lx, ly + index * line, lw, line), KIND_COLORS[item["kind"]], size=14)


def draw_intercept_lines(game, boat, view, bx, by) -> None:
    """Fresh intercept bearings as dashed rays from the boat on the chart."""
    s = game.screen
    now = game.sim_t
    for row in boat.intercepts:
        age = now - row["t"]
        if not 0.0 <= age <= CHART_LINE_S:
            continue
        rad = math.radians(row["bearing"])
        color = KIND_COLORS[row["kind"]]
        for start in range(20, 300, 24):
            x0, y0 = bx + start * math.sin(rad), by - start * math.cos(rad)
            x1, y1 = bx + (start + 12) * math.sin(rad), by - (start + 12) * math.cos(rad)
            lines.line(s, color, (int(x0), int(y0)), (int(x1), int(y1)), 1)
        pygame.draw.circle(s, color, (int(bx + 300 * math.sin(rad)),
                                      int(by - 300 * math.cos(rad))), 3, 1)
