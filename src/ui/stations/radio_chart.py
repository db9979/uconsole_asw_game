"""The radio room's HF/DF cross-fix chart (page 1, beside the intercepts).

It draws only what the radio room has published: the bearings the operator
logged (each from where the ship took it), the live HF intercepts from the
ship, the crossings of logged bearings of one signal and the cross-fixes
with their error ellipse.  Everything fades with age.  Own ship and the
known coastline are the only other things on it; no emitter position that
the radio room did not compute appears here.
"""

import math

import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.ui import console, label_layout, layout, lines, nato_symbols
from src.ui.map_view import _visible_landmasses, clip_polygon_to_rect, grid_step_nm
from src.ui.viewport import Viewport

# Logged bearings and fixes stay on the chart this long (same as the charts
# of Bridge, Weapons and Helicopter); live intercepts fade over the time a
# bearing may still be logged.
CHART_WINDOW_S = 300.0
LIVE_FADE_S = config.RADAR_TRACK_STALE_S
# Half the chart's shorter side in NM: at least, at most.
CHART_MIN_HALF_NM = 20.0
CHART_MAX_HALF_NM = 160.0
# Two logged bearings of one signal cross only from positions this far apart.
CROSS_BASE_MIN_NM = 1.0
_BACKGROUND = (6, 16, 28)
_LAND = (30, 48, 58)


def _fade(color, age, window):
    """Fresh lines in full colour, fading towards the chart ground with age."""
    share = max(0.0, min(1.0, age / window)) if window > 0 else 1.0
    return console._mix(color, _BACKGROUND, 0.75 * share)


def chart_items(game) -> dict:
    """The published HF/DF picture the chart draws (pure, testable)."""
    now = game.sim_t
    logged = [dict(track_id=row["track_id"], label=str(row["label"]),
                   bearing=float(row["bearing"]) % 360.0,
                   observer_x=float(row["observer_x"]), observer_y=float(row["observer_y"]),
                   age=max(0.0, now - float(row["t"])))
              for row in list(game.hfdf_log)[-20:]
              if 0.0 <= now - float(row["t"]) <= CHART_WINDOW_S]
    live = []
    for report in game.hfdf_bearings()[:12]:
        history = report.measurement_history or []
        latest = history[-1] if history else {}
        live.append(dict(label=game.hfdf_display_id(report),
                         bearing=float(latest.get("bearing", report.bearing)) % 360.0,
                         observer_x=float(latest.get("observer_x", game.ship.x)),
                         observer_y=float(latest.get("observer_y", game.ship.y)),
                         error=float(report.bearing_uncertainty_deg
                                     or config.HFDF_BEARING_ERR_DEG / math.sqrt(3.0)),
                         age=report.age(now)))
    crossings = []
    for index, first in enumerate(logged):
        for second in logged[index + 1:]:
            if (first["track_id"] != second["track_id"]
                    or math.hypot(first["observer_x"] - second["observer_x"],
                                  first["observer_y"] - second["observer_y"])
                    < CROSS_BASE_MIN_NM):
                continue
            point = game._bearing_intersection(first, second)
            if point is not None:
                crossings.append(dict(x=point[0], y=point[1],
                                      age=max(first["age"], second["age"])))
    fixes = []
    for _track, fix in sorted(game.hfdf_fixes.items()):
        age = max(0.0, now - float(fix["t"]))
        if age <= CHART_WINDOW_S:
            fixes.append(dict(label=str(fix["label"]), x=float(fix["x"]), y=float(fix["y"]),
                              sigma_nm=float(fix["sigma_nm"]),
                              covariance_nm2=fix.get("covariance_nm2"), age=age))
    return dict(logged=logged, live=live, crossings=crossings, fixes=fixes)


def chart_view(game, items, rect) -> Viewport:
    """North-up camera that holds the ship, every observer position and fix."""
    rect = pygame.Rect(rect)
    xs, ys = [game.ship.x], [game.ship.y]
    for row in items["logged"] + items["live"]:
        xs.append(row["observer_x"])
        ys.append(row["observer_y"])
    for row in items["crossings"]:
        xs.append(row["x"])
        ys.append(row["y"])
    for fix in items["fixes"]:
        xs += [fix["x"] - 2 * fix["sigma_nm"], fix["x"] + 2 * fix["sigma_nm"]]
        ys += [fix["y"] - 2 * fix["sigma_nm"], fix["y"] + 2 * fix["sigma_nm"]]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    half = max(CHART_MIN_HALF_NM,
               min(CHART_MAX_HALF_NM, 0.6 * max(max(xs) - min(xs), max(ys) - min(ys))))
    view = Viewport(game.world.size_nm, 1e-6, 1e6)
    view.set_rect(tuple(rect))
    view.scale = min(rect.w, rect.h) / (2.0 * half)
    view.cx, view.cy = cx, cy
    return view


def chart_half_nm(view) -> float:
    rect = view.rect
    return min(rect[2], rect[3]) / (2.0 * view.scale)


def _ray_end(view, row, rect):
    """The far end of a bearing line: beyond the chart edge."""
    reach = 2.0 * max(rect.w, rect.h) / view.scale
    rad = math.radians(row["bearing"])
    return view.world_to_screen(row["observer_x"] + reach * math.sin(rad),
                                row["observer_y"] - reach * math.cos(rad))


def _ellipse(view, fix, steps=32):
    px, py = view.world_to_screen(fix["x"], fix["y"])
    covariance = fix.get("covariance_nm2")
    if covariance is None or len(covariance) != 3:
        radius = max(3.0, fix["sigma_nm"] * view.scale)
        major = minor = radius
        angle = 0.0
    else:
        xx, xy, yy = (float(value) for value in covariance)
        spread = math.hypot(xx - yy, 2 * xy)
        major = max(3.0, math.sqrt(max(0.0, (xx + yy + spread) / 2)) * view.scale)
        minor = max(2.0, math.sqrt(max(0.0, (xx + yy - spread) / 2)) * view.scale)
        angle = .5 * math.atan2(2 * xy, xx - yy)
    ca, sa = math.cos(angle), math.sin(angle)
    return [(px + major * math.cos(phase) * ca - minor * math.sin(phase) * sa,
             py + major * math.cos(phase) * sa + minor * math.sin(phase) * ca)
            for phase in (index * math.tau / steps for index in range(steps))]


def _geography(s, game, view, rect) -> None:
    """Grid and coastline only: the radio room's plotting sheet."""
    step = grid_step_nm(view.scale)
    left, top = view.screen_to_world(rect.x, rect.y)
    right, bottom = view.screen_to_world(rect.right, rect.bottom)
    k = math.ceil(left / step)
    while k * step <= right:
        x, _ = view.world_to_screen(k * step, 0.0)
        lines.line(s, config.COLOR_GEO_GRID, (x, rect.y), (x, rect.bottom - 1), 1)
        k += 1
    k = math.ceil(top / step)
    while k * step <= bottom:
        _, y = view.world_to_screen(0.0, k * step)
        lines.line(s, config.COLOR_GEO_GRID, (rect.x, y), (rect.right - 1, y), 1)
        k += 1
    coast = game.world.coast
    if getattr(coast, "landmasses", None) is None:
        return
    for land in _visible_landmasses(coast, view, tuple(rect)):
        poly = clip_polygon_to_rect([view.world_to_screen(px, py) for px, py in land.points],
                                    tuple(rect))
        if len(poly) >= 3:
            lines.polygon(s, _LAND, poly)
            lines.polygon(s, config.COLOR_LAND_EDGE, poly, 1)


def draw_hfdf_chart(s, game, rect, selected_label=None) -> Viewport | None:
    """The cross-fix chart inside ``rect``; returns its camera."""
    rect = pygame.Rect(rect)
    if rect.w < 120 or rect.h < 90:
        return None
    items = chart_items(game)
    view = chart_view(game, items, rect)
    pygame.draw.rect(s, _BACKGROUND, rect)
    north = (rect.right - 24, rect.y + 4, 20, layout.font(14).get_linesize())
    with layout.clip_to(s, rect), label_layout.label_scope(rect) as labels:
        labels.reserve(north)
        _geography(s, game, view, rect)
        # Live intercepts from the ship: an error wedge and a thin line.
        for row in items["live"]:
            selected = row["label"] == selected_label
            color = _fade(config.COLOR_WARN if selected else config.COLOR_HFDF,
                          row["age"], LIVE_FADE_S)
            ox, oy = view.world_to_screen(row["observer_x"], row["observer_y"])
            for edge in (-row["error"], row["error"]):
                end = _ray_end(view, dict(row, bearing=row["bearing"] + edge), rect)
                lines.line(s, console._mix(_BACKGROUND, color, .45), (ox, oy), end, 1)
            lines.line(s, color, (ox, oy), _ray_end(view, row, rect), 2 if selected else 1)
        # Logged bearings, each from where it was taken.
        for row in items["logged"]:
            color = _fade(config.COLOR_HFDF, row["age"], CHART_WINDOW_S)
            ox, oy = view.world_to_screen(row["observer_x"], row["observer_y"])
            lines.line(s, color, (ox, oy), _ray_end(view, row, rect), 2)
            pygame.draw.circle(s, color, (int(ox), int(oy)), 4, 1)
        for row in items["crossings"]:
            color = _fade(config.COLOR_WARN, row["age"], CHART_WINDOW_S)
            px, py = view.world_to_screen(row["x"], row["y"])
            pygame.draw.polygon(s, color, ((px, py - 5), (px + 5, py), (px, py + 5), (px - 5, py)), 1)
        for fix in items["fixes"]:
            color = _fade(config.COLOR_OK, fix["age"], CHART_WINDOW_S)
            lines.lines(s, color, True, _ellipse(view, fix), 2)
            px, py = view.world_to_screen(fix["x"], fix["y"])
            pygame.draw.circle(s, color, (int(px), int(py)), 3)
            label_layout.blit_line(s, message("radio.chart.fix_label", label=raw_text(fix["label"]),
                                        sigma=f"{fix['sigma_nm']:.1f}"),
                             (int(px) + 8, int(py) - 20, 190, layout.font(14).get_linesize()), color, size=14)
        # Own ship last, on top.
        sx, sy = view.world_to_screen(game.ship.x, game.ship.y)
        heading = math.radians(game.ship.course)
        lines.line(s, config.COLOR_OK, (sx, sy),
                   (sx + 18 * math.sin(heading), sy - 18 * math.cos(heading)), 2)
        nato_symbols.draw_symbol(s, (sx, sy), "FRIEND", "SURFACE", 16)
        layout.blit_line(s, "uboot.pilot.north", north,
                         config.COLOR_TEXT_DIM, size=14, align="center")
        if not (items["logged"] or items["live"] or items["fixes"]):
            layout.blit_line(s, "radio.chart.empty",
                             (rect.x + 10, rect.y + 6, rect.w - 40, 22),
                             config.COLOR_TEXT_DIM, size=15)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)
    return view
