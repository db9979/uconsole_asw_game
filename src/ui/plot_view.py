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
from src.ui import label_layout, layout, lines

MARK_PX = 6
EDGE_INSET_PX = 10       # off-chart objects get an edge arrow this far in
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
    if label_layout.active() is not None:
        # Inside a chart's label scope it steps aside from the labels,
        # symbols and vectors drawn before it.
        rect = label_layout.free_rect((width, height),
                                      label_layout.around((x, y), (width, height), 8), chart)
        x, y = rect.topleft
    else:
        if x + width > chart.right - 2:
            x = max(chart.x + 2, pos[0] - width - 8)
        y = min(max(y, chart.y + 2), chart.bottom - height - 2)
    image = face.render(shown, True, config.COLOR_PLOT)
    rect = image.get_rect(topleft=(int(x), int(y)))
    layout.record_text(shown, rect, chart)
    surface.blit(image, rect)


def edge_anchor(chart, point, inset: int = None):
    """Where the ray from the chart's centre to an off-chart ``point``
    crosses the chart edge (pulled ``inset`` pixels in), and its unit
    direction."""
    inset = EDGE_INSET_PX if inset is None else inset
    cx, cy = chart.centerx, chart.centery
    dx, dy = point[0] - cx, point[1] - cy
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (cx, cy), (0.0, -1.0)
    half_w = max(1.0, chart.w / 2.0 - inset)
    half_h = max(1.0, chart.h / 2.0 - inset)
    t = min(half_w / abs(dx) if dx else math.inf, half_h / abs(dy) if dy else math.inf)
    return (cx + dx * t, cy + dy * t), (dx / length, dy / length)


def _edge_mark(surface, chart, point, color):
    """Arrow on the chart edge towards an off-chart plot object; returns the
    arrow's position for its label."""
    (ex, ey), (ux, uy) = edge_anchor(chart, point)
    tip = (ex + ux * 5, ey + uy * 5)
    back = (ex - ux * 5, ey - uy * 5)
    side = (-uy * 5, ux * 5)
    pygame.draw.polygon(surface, color, [tip, (back[0] + side[0], back[1] + side[1]),
                                         (back[0] - side[0], back[1] - side[1])])
    field = label_layout.active()
    if field is not None:
        field.reserve(pygame.Rect(int(ex) - 7, int(ey) - 7, 14, 14))
    return ex, ey


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


def object_text(game, item, own=None):
    """The chart annotation for one plot object (also used by tests); a DR
    line's CPA is to ``own`` (default the frigate)."""
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
        own = game.ship if own is None else own
        dist, seconds = plot.cpa(item, game.sim_t, own.x, own.y, own.course, own.speed)
        return message("plot.label.dr", label=item["label"],
                       range=f"{dist:.1f}", minutes=f"{seconds / 60.0:.0f}")
    return label


def draw_plot(surface, game, view, chart, layer=None, own=None) -> None:
    """Draw every plot object plus the plot-mode cursor inside ``chart``;
    ``layer``/``own`` draw another crew's plot (the crewed boat's)."""
    boat_layer = layer is not None
    layer = getattr(game, "plot", None) if layer is None else layer
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
            if not chart.inflate(-2 * EDGE_INSET_PX, -2 * EDGE_INSET_PX).collidepoint(anchor):
                # Off the chart: an arrow on its edge points the way, and the
                # label sits beside the arrow (stepping aside from others).
                anchor = _edge_mark(surface, chart, anchor, color)
            _label(surface, game, object_text(game, item, own), anchor, chart)
        if getattr(game, "plot_mode", False) and not boat_layer:
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
    _draw_toolbar(surface, game, chart, color,
                  message("plot.cursor", bearing=f"{brg:03.0f}", range=f"{dist:.1f}"))


# The plot toolbar: tools in the first row, actions and the cursor readout in
# the second. Every chip presses its key on a click.
_TOOLS = (("M", "mark"), ("R", "ruler"), ("B", "bearing"), ("C", "circle"), ("D", "dr"))
_ACTIONS = (("Enter", "plot.bar.point"), ("Backspace", "plot.bar.delete"),
            ("Shift+Backspace", "plot.bar.clear"), ("Esc", "plot.bar.end"))
TOOLBAR_ROW_H = 24
TOOLBAR_BOTTOM_GAP = 22     # the longitude labels stay readable below it


def toolbar_rect(chart) -> pygame.Rect:
    """Where the plot toolbar sits: across the foot of ``chart``."""
    chart = pygame.Rect(chart)
    height = 2 * TOOLBAR_ROW_H + 6
    return pygame.Rect(chart.x + 2, chart.bottom - TOOLBAR_BOTTOM_GAP - height,
                       chart.w - 4, height)


def _draw_toolbar(surface, game, chart, color, readout) -> None:
    from src.ui import pointer, theme
    bar = toolbar_rect(chart)
    panel = pygame.Surface(bar.size, pygame.SRCALPHA)
    panel.fill((*config.COLOR_PANEL_BG[:3], 225))
    surface.blit(panel, bar)
    pygame.draw.rect(surface, theme.c("line"), bar, 1)
    pointer.add_blocker(bar)        # a click between the chips plots nothing
    width = (bar.w - 6) // len(_TOOLS)
    for index, (key, tool) in enumerate(_TOOLS):
        segment = pygame.Rect(bar.x + 3 + index * width, bar.y + 2, width, TOOLBAR_ROW_H)
        layout.command_segment(surface, segment, key, TOOL_KEYS[tool], size=12, center=True)
        if game.plot_tool == tool:
            pygame.draw.rect(surface, theme.c("focus"), segment.inflate(-3, -4), 2,
                             border_radius=4)
        pointer.add_legend(segment, key)
    y = bar.y + 4 + TOOLBAR_ROW_H
    readout_w = min(bar.w // 4, layout.text_width(layout.font(13), localize(readout)) + 12)
    # Each action chip is as wide as its key and word need, sharing the rest.
    face = layout.font(12)
    from src.core.i18n import key_label
    needs = [layout.text_width(face, localize(key_label(key)) + " " + localize(description)) + 22
             for key, description in _ACTIONS]
    room = bar.w - 6 - readout_w
    spare = max(0, room - sum(needs)) // len(needs)
    x = bar.x + 3
    for (key, description), need in zip(_ACTIONS, needs):
        width = need + spare if sum(needs) <= room else room * need // sum(needs)
        segment = pygame.Rect(x, y, width, TOOLBAR_ROW_H)
        layout.command_segment(surface, segment, key, description, size=12, center=True)
        pointer.add_legend(segment, key)
        x += width
    layout.blit_line(surface, readout, (bar.right - readout_w - 4, y, readout_w, TOOLBAR_ROW_H),
                     color, size=13, align="right")
