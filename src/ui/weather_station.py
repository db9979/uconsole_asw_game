"""Weather & sonar analysis panel (key 0), drawn over the station area.

Consumes only ``Game.weather_station_data()`` (an observation-safe DTO):
own-ship atmosphere and flight weather, and - only after a sonar
bathythermograph measurement - the measured ocean profile with its layer,
shadow zone, SOFAR axis and a few sound rays.
"""

from __future__ import annotations

import math

import pygame

from src.core import config
from src.core.i18n import localize, localized, message
from src.ui import layout
from src.ui import profile_cursor

TREND_ARROWS = {"rising": "^", "steady": "=", "falling": "v", "falling_rapidly": "vv"}
# Theme attribute names, resolved at draw time so high contrast applies.
STATUS_COLORS = {"clear": "COLOR_OK", "limited": "COLOR_WARN",
                 "no_go": "COLOR_DANGER"}
SHADOW_COLOR = (70, 30, 30)
RAY_COLOR = (90, 220, 150)
SOFAR_COLOR = (110, 170, 230)
LINE_H = 26
TEXT = 18


def _fmt(value, digits: int = 0) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


def _line(screen, text, x, y, w, color=config.COLOR_TEXT, size=TEXT):
    layout.blit_line(screen, text, (x, y, w, LINE_H), color, size=size)


def _environment(screen, rect, data) -> None:
    x, y, w, h = layout.box(screen, rect, "weather.box.environment")
    a = data["atmosphere"]
    _line(screen, message("weather.line.sky", time=a["time"],
                          daylight=message("weather.daylight." + a["daylight"]),
                          moon=message("weather.moon." + a["moon_phase"]),
                          illumination=f"{a['moon_illumination']:.0%}"), x, y, w)
    _line(screen, message("weather.line.weather",
                          weather=message("weather.kind." + a["weather"]),
                          precipitation=message("weather.precip." + a["precipitation"]),
                          visibility=_fmt(a["visibility_nm"], 1)), x, y + LINE_H, w)
    _line(screen, message("weather.line.wind", direction=f"{a['wind_from_deg']:03.0f}",
                          wind=_fmt(a["wind_kn"]), gust=_fmt(a["gust_kn"]),
                          beaufort=a["beaufort"], sea=a["sea_state"]),
          x, y + 2 * LINE_H, w)
    trend = a["pressure_trend"]
    trend_color = (config.COLOR_DANGER if trend == "falling_rapidly" else
                   config.COLOR_WARN if trend == "falling" else config.COLOR_OK)
    _line(screen, message("weather.line.barometer", pressure=_fmt(a["pressure_hpa"]),
                          arrow=TREND_ARROWS[trend],
                          tendency=f"{a['pressure_tendency_hpa_3h']:+.0f}",
                          trend=message("weather.trend." + trend)),
          x, y + 3 * LINE_H, w, trend_color)
    ceiling = a["ceiling_ft"]
    _line(screen, message("weather.line.temperature", air=_fmt(a["air_temp_c"], 1),
                          sea=_fmt(a["sea_temp_c"], 1),
                          ceiling=(message("weather.ceiling.none") if ceiling is None
                                   else message("weather.ceiling.ft", ceiling=_fmt(ceiling))),
                          icing=message("weather.icing." + a["icing"])),
          x, y + 4 * LINE_H, w,
          config.COLOR_WARN if a["icing"] != "none" else config.COLOR_TEXT)
    if a["storm_warning"]:
        _line(screen, "weather.storm_warning", x, y + 5 * LINE_H, w, config.COLOR_DANGER)


def _effects(screen, rect, data) -> None:
    """Weather influence on sound and sea: active effects amber, others dim."""
    x, y, w, h = rect
    effects = (("solar_heating", "weather.effect.solar"),
               ("wind_mixing", "weather.effect.wind"),
               ("freshwater", "weather.effect.rain"))
    segment = w // len(effects)
    for index, (key, label) in enumerate(effects):
        active = data["effects"][key]
        _line(screen, label, x + index * segment, y, segment - 12,
              config.COLOR_WARN if active else config.COLOR_TEXT_DIM, size=TEXT)


def _flight(screen, rect, data) -> None:
    x, y, w, h = layout.box(screen, rect, "weather.box.flight")
    f = data["flight"]
    limits = f["limits"]
    status = f["status"]
    layout.blit_line(screen, "weather.flight." + status, (x, y, w, 30),
                     getattr(config, STATUS_COLORS[status]), size=24)
    rows = (
        message("weather.flight.wind", value=_fmt(f["wind_kn"]), limit=_fmt(limits["wind_kn"])),
        message("weather.flight.gust", value=_fmt(f["gust_kn"]), limit=_fmt(limits["gust_kn"])),
        message("weather.flight.crosswind", value=_fmt(f["crosswind_kn"]),
                limit=_fmt(limits["crosswind_kn"])),
        message("weather.flight.visibility", value=_fmt(f["visibility_nm"], 1),
                limit=_fmt(limits["visibility_nm"], 1)),
        message("weather.flight.ceiling",
                value=(message("weather.ceiling.none") if f["ceiling_ft"] is None
                       else _fmt(f["ceiling_ft"])), limit=_fmt(limits["ceiling_ft"])),
        message("weather.flight.sea", value=f["sea_state"], limit=_fmt(limits["sea_state"])),
        message("weather.flight.deck", roll=_fmt(abs(f["roll_deg"]), 1),
                roll_limit=_fmt(limits["roll_deg"])),
        message("weather.flight.pitch", pitch=_fmt(abs(f["pitch_deg"]), 1),
                pitch_limit=_fmt(limits["pitch_deg"], 1)),
        message("weather.flight.icing", icing=message("weather.icing." + f["icing"])),
        message("weather.flight.dipping",
                dipping=message("weather.flight.dip_ok" if f["dipping_safe"]
                                else "weather.flight.dip_blocked")),
    )
    # Amber: the deck rows while the deck is outside its motion window, the
    # icing/dipping rows while icing restricts operations.
    warn = {6: not f["deck_safe"], 7: not f["deck_safe"],
            8: f["icing"] != "none", 9: not f["dipping_safe"]}
    column = w // 2
    for index, text in enumerate(rows):
        row, col = divmod(index, 2)
        _line(screen, text, x + col * column, y + 32 + row * LINE_H, column - 8,
              config.COLOR_WARN if warn.get(index) else config.COLOR_TEXT, size=TEXT)


def _profile(screen, rect, data, mouse=None) -> None:
    x, y, w, h = layout.box(screen, rect, "weather.box.profile")
    p = data["profile"]
    if p is None:
        layout.blit_block(screen, "weather.profile.none", x, y + h // 3, w, 60,
                          config.COLOR_WARN, size=20, align="center")
        return
    header = message("weather.profile.header", age=_fmt(p["age_s"] / 60.0),
                     offset=_fmt(p["offset_nm"], 1), layer=_fmt(p["thermocline_m"]),
                     depth=_fmt(p["water_depth_m"]),
                     sofar=(message("weather.sofar.none") if p["sofar_axis_m"] is None
                            else message("weather.sofar.depth", depth=_fmt(p["sofar_axis_m"]))),
                     cz=" / ".join(f"{a:.0f}-{b:.0f}" for a, b in p["cz_bands_nm"]))
    _line(screen, header, x, y, w, config.COLOR_WARN if p["stale"] else config.COLOR_TEXT)
    if p["stale"]:
        _line(screen, "weather.profile.stale", x, y + LINE_H, w, config.COLOR_WARN)
    top = y + 2 * LINE_H + 4
    # Axis labels get their own row under the plot, the hint the last row.
    bottom = y + h - 2 * LINE_H - 6
    depth_max = max(p["depths_m"][-1], 1.0)
    plot_h = max(20, bottom - top)

    def depth_y(depth):
        return top + min(1.0, max(0.0, depth / depth_max)) * plot_h

    # Left: sound-speed profile c(z).
    left_w = int(w * 0.28)
    speeds = p["speeds_m_s"]
    low, high = min(speeds), max(max(speeds), min(speeds) + 1.0)
    pygame.draw.rect(screen, config.COLOR_GRID, (x, top, left_w, plot_h), 1)
    points = [(x + 6 + (speed - low) / (high - low) * (left_w - 12), depth_y(depth))
              for depth, speed in zip(p["depths_m"], speeds)]
    if len(points) > 1:
        pygame.draw.lines(screen, config.COLOR_OK, False, points, 2)
    # Right: range-depth section with shadow zone and rays.
    sx, sw = x + left_w + 12, w - left_w - 12
    pygame.draw.rect(screen, config.COLOR_GRID, (sx, top, sw, plot_h), 1)
    edges = p["depth_edges_m"]
    columns = len(p["shadow"])
    for column, cells in enumerate(p["shadow"]):
        for row, shadowed in enumerate(cells):
            if not shadowed or edges[row] > depth_max:
                continue
            cy0, cy1 = depth_y(edges[row]), depth_y(min(edges[row + 1], depth_max))
            cx0 = sx + column * sw / columns
            pygame.draw.rect(screen, SHADOW_COLOR,
                             (int(cx0) + 1, int(cy0), max(1, int(sw / columns)), max(1, int(cy1 - cy0))))
    for ray in p["rays"]:
        points = [(sx + r / p["range_nm"] * sw, depth_y(z)) for r, z in ray if z <= depth_max]
        if len(points) > 1:
            pygame.draw.lines(screen, RAY_COLOR, False, points, 1)
    for depth, color, label in (
            (p["thermocline_m"], config.COLOR_WARN, "weather.profile.layer"),
            (p["sofar_axis_m"], SOFAR_COLOR, "weather.profile.sofar")):
        if depth is None or depth > depth_max:
            continue
        ly = int(depth_y(depth))
        for dash in range(x, sx + sw, 12):
            pygame.draw.line(screen, color, (dash, ly), (min(dash + 6, sx + sw), ly), 1)
        # Label on its own dark plate so rays never run through the text.
        text = localize(message(label, depth=_fmt(depth)))
        text_w, text_h = layout.font(TEXT).size(text)
        plate = pygame.Rect(sx + 26, ly - text_h - 6, text_w + 12, text_h + 4)
        pygame.draw.rect(screen, config.COLOR_BG, plate)
        pygame.draw.rect(screen, color, plate, 1)
        _line(screen, text, plate.x + 6, plate.y + 1, text_w + 4, color)
    # Ship at the surface and axis labels (depth, range).
    pygame.draw.polygon(screen, config.COLOR_TEXT,
                        [(sx + 2, top - 2), (sx + 16, top - 2), (sx + 9, top + 6)])
    axis_y = bottom + 2
    _line(screen, message("weather.depth_value", depth=_fmt(depth_max)),
          x + 4, axis_y, left_w // 2 - 8, config.COLOR_TEXT_DIM)
    _line(screen, message("weather.speed_range", low=_fmt(low), high=_fmt(high)),
          x + left_w // 2, axis_y, left_w // 2 - 4, config.COLOR_TEXT_DIM)
    _line(screen, message("map.tooltip.range_value", range="0"),
          sx, axis_y, 120, config.COLOR_TEXT_DIM)
    _line(screen, message("map.tooltip.range_value", range=_fmt(p["range_nm"])),
          sx + sw - 120, axis_y, 120, config.COLOR_TEXT_DIM, )
    dip = p["dip_relative_to_layer"]
    footer = ("weather.shadow_hint" if dip is None else "weather.dip." + dip)
    _line(screen, footer, x, y + h - LINE_H, w, config.COLOR_TEXT_DIM)
    _profile_cursor(screen, p, mouse, pygame.Rect(x, top, left_w, plot_h),
                    pygame.Rect(sx, top, sw, plot_h), depth_max)


def _profile_cursor(screen, p, mouse, left, section, depth_max) -> None:
    """Depth (and range) readout under the pointer; display only."""
    if mouse is None:
        return
    inside_left, inside_section = left.collidepoint(mouse), section.collidepoint(mouse)
    if not (inside_left or inside_section):
        return
    depth = (mouse[1] - left.y) / max(1, left.h) * depth_max
    speed = profile_cursor.speed_at(p["depths_m"], p["speeds_m_s"], depth)
    whole = left.union(section)
    if inside_left:
        profile_cursor.draw_crosshair(screen, whole, y=mouse[1])
        profile_cursor.draw_label(screen, message("weather.cursor.depth", depth=_fmt(depth),
                                                  speed=_fmt(speed, 1)), mouse, whole)
        return
    range_nm = (mouse[0] - section.x) / max(1, section.w) * p["range_nm"]
    columns = len(p["shadow"])
    column = min(columns - 1, int(range_nm / p["range_nm"] * columns)) if columns else -1
    edges = p["depth_edges_m"]
    row = next((index for index in range(len(edges) - 1)
                if edges[index] <= depth < edges[index + 1]), -1)
    notes = []
    if column >= 0 and row >= 0 and p["shadow"][column][row]:
        notes.append(message("weather.cursor.shadow"))
    if any(low <= range_nm <= high for low, high in p["cz_bands_nm"]):
        notes.append(message("weather.cursor.cz"))
    text = message("weather.cursor.section", range=_fmt(range_nm, 1), depth=_fmt(depth),
                   speed=_fmt(speed, 1))
    for note in notes:
        text = message("weather.cursor.with_note", text=text, note=note)
    profile_cursor.draw_crosshair(screen, whole, y=mouse[1])
    profile_cursor.draw_crosshair(screen, section, x=mouse[0])
    profile_cursor.draw_label(screen, text, mouse, whole)


@localized
def draw_weather_station(game, tr=None) -> None:
    """Render the panel into ``config.STATION_RECT``."""
    layout.configure_for(game)
    screen = game.screen
    data = game.weather_station_data()
    r = config.STATION_RECT
    y = layout.panel(screen, r, "weather.title")
    x, width = r[0] + 12, r[2] - 24
    top_h = 6 * LINE_H + 52
    left_w = int(width * 0.54)
    _environment(screen, (x, y, left_w, top_h), data)
    _flight(screen, (x + left_w + 10, y, width - left_w - 10, top_h), data)
    _effects(screen, (x + 8, y + top_h + 6, width - 16, LINE_H), data)
    profile_y = y + top_h + LINE_H + 12
    _profile(screen, (x, profile_y, width, r[1] + r[3] - profile_y - 6), data,
             profile_cursor.pointer(game))
