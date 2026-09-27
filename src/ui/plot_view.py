"""Draw the shared operator plot layer on a chart viewport.

Everything drawn here is crew-made geometry from ``game.plot`` plus own
ship; no contact or hidden state is read. Used by the Bridge/Weapons/Helo
map and the OPZ chart so all stations see the same drawing.
"""

from __future__ import annotations

import math

import pygame

from src.core import config, plot
from src.core.i18n import localize, message, raw_text
from src.ui import layout, lines

MARK_PX = 6
DR_MINUTES = 30.0          # DR line drawn this far ahead of its current point
TOOL_KEYS = {"mark": "plot.tool.mark", "ruler": "plot.tool.ruler",
             "bearing": "plot.tool.bearing", "circle": "plot.tool.circle",
             "dr": "plot.tool.dr"}


def _label(surface, game, text, pos, chart) -> None:
    """Chart label beside a point, kept inside the chart."""
    shown = localize(text)
    face = game.font
    width, height = face.size(shown)
    x = pos[0] + 8
    y = pos[1] - height - 2
    if x + width > chart.right - 2:
        x = max(chart.x + 2, pos[0] - width - 8)
    y = min(max(y, chart.y + 2), chart.bottom - height - 2)
    image = face.render(shown, True, config.COLOR_PLOT)
    rect = image.get_rect(topleft=(int(x), int(y)))
    layout.record_text(shown, rect, chart)
    surface.blit(image, rect)


def _edge_point(view, x, y, bearing, chart):
    """Far end of a ray so it leaves the visible chart."""
    reach = 2.0 * math.hypot(chart.w, chart.h) / max(view.scale, 1e-6)
    rad = math.radians(bearing)
    return view.world_to_screen(x + reach * math.sin(rad), y - reach * math.cos(rad))


def _dashed(surface, color, start, end, dash=8) -> None:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length < 1:
        return
    steps = min(400, int(length // dash))
    for index in range(0, steps, 2):
        a, b = index / max(steps, 1), min(1.0, (index + 1) / max(steps, 1))
        lines.line(surface, color,
                         (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                         (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b))


def object_text(game, item):
    """The chart annotation for one plot object (also used by tests)."""
    label = raw_text(item["label"])
    kind = item["kind"]
    if kind == "ruler":
        brg, dist = plot.bearing_distance(item["x"], item["y"], item["x2"], item["y2"])
        return message("plot.label.ruler", label=item["label"],
                       bearing=f"{brg:03.0f}", range=f"{dist:.1f}")
    if kind == "bearing":
        return message("plot.label.bearing", label=item["label"],
                       bearing=f"{item['bearing']:03.0f}")
    if kind == "circle":
        return message("plot.label.circle", label=item["label"],
                       range=f"{item['radius_nm']:.1f}")
    if kind == "dr":
        dist, seconds = plot.cpa(item, game.sim_t, game.ship.x, game.ship.y,
                                 game.ship.course, game.ship.speed)
        return message("plot.label.dr", label=item["label"],
                       range=f"{dist:.1f}", minutes=f"{seconds / 60.0:.0f}")
    return label


def draw_plot(surface, game, view, chart) -> None:
    """Draw every plot object plus the plot-mode cursor inside ``chart``."""
    layer = getattr(game, "plot", None)
    if layer is None:
        return
    chart = pygame.Rect(chart)
    color = config.COLOR_PLOT
    with layout.clip_to(surface, chart):
        for item in layer.objects:
            px, py = view.world_to_screen(item["x"], item["y"])
            kind = item["kind"]
            anchor = (px, py)
            if kind == "mark":
                lines.line(surface, color, (px - MARK_PX, py - MARK_PX),
                                 (px + MARK_PX, py + MARK_PX), 2)
                lines.line(surface, color, (px - MARK_PX, py + MARK_PX),
                                 (px + MARK_PX, py - MARK_PX), 2)
            elif kind == "ruler":
                end = view.world_to_screen(item["x2"], item["y2"])
                lines.line(surface, color, (px, py), end, 2)
                for point in ((px, py), end):
                    pygame.draw.circle(surface, color, (int(point[0]), int(point[1])), 3)
                anchor = ((px + end[0]) / 2.0, (py + end[1]) / 2.0)
            elif kind == "bearing":
                _dashed(surface, color, (px, py),
                        _edge_point(view, item["x"], item["y"], item["bearing"], chart))
                pygame.draw.circle(surface, color, (int(px), int(py)), 3, 1)
            elif kind == "circle":
                radius = item["radius_nm"] * view.scale
                if radius < 4 * max(chart.w, chart.h):
                    pygame.draw.circle(surface, color, (int(px), int(py)),
                                       max(2, int(radius)), 1)
                pygame.draw.circle(surface, color, (int(px), int(py)), 2)
            elif kind == "dr":
                now = plot.dr_position(item, game.sim_t)
                ahead = plot.dr_position(item, game.sim_t + DR_MINUTES * 60.0)
                cur = view.world_to_screen(*now)
                lines.line(surface, color, (px, py), cur, 1)
                _dashed(surface, color, cur, view.world_to_screen(*ahead))
                pygame.draw.rect(surface, color, (int(cur[0]) - 4, int(cur[1]) - 4, 8, 8), 1)
                pygame.draw.circle(surface, color, (int(px), int(py)), 3, 1)
                anchor = cur
            _label(surface, game, object_text(game, item), anchor, chart)
        if getattr(game, "plot_mode", False):
            _draw_cursor(surface, game, view, chart)


def _draw_cursor(surface, game, view, chart) -> None:
    color = config.COLOR_PLOT
    cx, cy = game.plot_cursor
    px, py = view.world_to_screen(cx, cy)
    lines.line(surface, color, (px - 12, py), (px - 4, py))
    lines.line(surface, color, (px + 4, py), (px + 12, py))
    lines.line(surface, color, (px, py - 12), (px, py - 4))
    lines.line(surface, color, (px, py + 4), (px, py + 12))
    anchor = game.plot_anchor
    if anchor is not None:
        ax, ay = view.world_to_screen(*anchor)
        _dashed(surface, color, (ax, ay), (px, py), dash=4)
        if game.plot_tool == "circle":
            radius = math.hypot(cx - anchor[0], cy - anchor[1]) * view.scale
            if 1 < radius < 4 * max(chart.w, chart.h):
                pygame.draw.circle(surface, color, (int(ax), int(ay)), int(radius), 1)
        ref = anchor
    else:
        ref = (game.ship.x, game.ship.y)
    brg, dist = plot.bearing_distance(ref[0], ref[1], cx, cy)
    # Hint bar at the top of the chart: tool keys left, cursor readout right,
    # so the readout never lands on a chart label.
    hint = pygame.Rect(chart.x + 2, chart.y + 24, chart.w - 4, 20)
    pygame.draw.rect(surface, config.COLOR_PANEL_BG, hint)
    readout = message("plot.cursor", bearing=f"{brg:03.0f}", range=f"{dist:.1f}")
    readout_w = min(hint.w // 3, layout.font(layout.scaled_size(13)).size(localize(readout))[0] + 8)
    layout.blit_line(surface, readout, (hint.right - readout_w - 2, hint.y, readout_w, hint.h),
                     color, size=13, align="right")
    layout.blit_line(surface, message("plot.hint", tool=message(TOOL_KEYS[game.plot_tool])),
                     (hint.x + 2, hint.y, hint.w - readout_w - 8, hint.h), color, size=13)
