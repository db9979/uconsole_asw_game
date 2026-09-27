"""Periscope page of the crewed submarine (uConsole).

Everything drawn here is the boat's own: the line of sight of its scope,
the light and weather its optics see, and the sightings the crew made
(``opfor.update_sightings``).  Silhouettes are procedural by the coarse
class the eye made out and the apparent length it measured; no frigate
truth is read here.
"""

import math

import pygame

from src.core import config, opfor
from src.core.i18n import display_value, localize, message, raw_text
from src.ui import layout

# Silhouette height over apparent length by class (dimensionless).
_HEIGHT_RATIO = {"warship": 0.24, "merchant": 0.17, "unknown": 0.15,
                 "aircraft": 0.45, "torpedo": 0.04}
_SKY_DAY = ((25, 70, 92), (111, 151, 157))
_SKY_NIGHT = ((5, 14, 27), (38, 53, 62))
_SEA_DAY, _SEA_NIGHT = (9, 54, 67), (7, 35, 48)
_HAZE = (150, 160, 165)


def _fmt(value, pattern="{:.0f}"):
    return "--" if value is None or not math.isfinite(value) else pattern.format(value)


def relative_offset(bearing: float, line_of_sight: float) -> float:
    """Signed angle from the crosshair to ``bearing`` (-180..180)."""
    return (bearing - line_of_sight + 180.0) % 360.0 - 180.0


def _blend(a, b, t: float) -> tuple:
    t = config.clamp(t, 0.0, 1.0)
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def draw_silhouette(s, cls: str, cx: int, base_y: int, width: int, color) -> None:
    """Procedural silhouette of a coarse class, ``width`` px long, sitting on
    the horizon (aircraft: hovering above it)."""
    width = max(3, int(width))
    height = max(2, int(width * _HEIGHT_RATIO.get(cls, 0.15)))
    left = cx - width // 2
    if cls == "torpedo":
        pygame.draw.line(s, (215, 225, 225), (left, base_y + 1), (left + width, base_y + 1),
                         max(1, min(3, width // 12)))
        return
    if cls == "aircraft":
        body_y = base_y - height * 3
        pygame.draw.ellipse(s, color, (left, body_y, width, max(2, height // 2)))
        pygame.draw.line(s, color, (left - width // 6, body_y - 2),
                         (left + width + width // 6, body_y - 2), 1)
        pygame.draw.line(s, color, (left + width * 3 // 4, body_y),
                         (left + width, body_y - height // 2), 1)
        return
    hull_h = max(1, height // 3)
    bow = width // 10
    pygame.draw.polygon(s, color, [(left + bow, base_y - hull_h), (left + width, base_y - hull_h),
                                   (left + width - bow // 2, base_y), (left, base_y)])
    if cls == "warship":
        block_w, block_h = width // 3, height - hull_h
        block_x = left + width // 3
        pygame.draw.rect(s, color, (block_x, base_y - hull_h - block_h, block_w, block_h))
        pygame.draw.rect(s, color, (block_x + block_w // 3, base_y - height - height // 4,
                                    max(1, block_w // 6), height // 4 + 1))
        pygame.draw.line(s, color, (block_x + block_w // 2, base_y - height),
                         (block_x + block_w // 2, base_y - height - height // 2), 1)
        pygame.draw.rect(s, color, (left + width * 3 // 4, base_y - hull_h - block_h // 2,
                                    max(1, width // 12), block_h // 2))
    elif cls == "merchant":
        block_w, block_h = width // 6, height - hull_h
        block_x = left + width - width // 5
        pygame.draw.rect(s, color, (block_x, base_y - hull_h - block_h, block_w, block_h))
        pygame.draw.rect(s, color, (block_x + block_w // 3, base_y - height - height // 3,
                                    max(1, block_w // 4), height // 3 + 1))
        for post in range(1, 4):
            px = left + bow + post * (width - width // 5 - bow) // 4
            pygame.draw.line(s, color, (px, base_y - hull_h), (px, base_y - height), 1)
    else:
        pygame.draw.rect(s, color, (left + width // 3, base_y - height,
                                    width // 3, height - hull_h))


def draw_eyepiece(s, game, boat, rect) -> None:
    """The picture in the eyepiece: sky, sea, horizon in motion, bearing scale,
    crosshair and the silhouettes of the boat's sightings within the field."""
    rect = pygame.Rect(rect)
    sub, orders = boat.sub, boat.orders
    night = game.world.is_night()
    visibility = getattr(game.world, "visibility_nm", config.WEATHER_VISIBILITY_MAX_NM)
    haze = 1.0 - config.clamp(visibility / config.WEATHER_VISIBILITY_MAX_NM, 0.0, 1.0)
    sky_top, sky_bottom = _SKY_NIGHT if night else _SKY_DAY
    sea = _SEA_NIGHT if night else _SEA_DAY
    haze_color = _blend(_HAZE, (40, 48, 54), 0.8 if night else 0.0)
    offset, tilt = opfor.horizon_motion(game, boat)
    horizon = rect.y + int(rect.h * 0.5 + offset)
    with layout.clip_to(s, rect):
        for py in range(rect.y, rect.bottom):
            blend = (py - rect.y) / max(1, rect.h - 1)
            color = _blend(_blend(sky_top, sky_bottom, blend), haze_color, haze * 0.6)
            pygame.draw.line(s, color, (rect.x, py), (rect.right, py))
        dy = int(math.tan(tilt) * rect.w / 2)
        sea_color = _blend(sea, haze_color, haze * 0.4)
        pygame.draw.polygon(s, sea_color, [(rect.x, horizon - dy), (rect.right, horizon + dy),
                                           (rect.right, rect.bottom), (rect.x, rect.bottom)])
        pygame.draw.line(s, _blend(sea_color, (200, 210, 210), 0.35),
                         (rect.x, horizon - dy), (rect.right, horizon + dy), 1)
        line_of_sight = opfor.scope_bearing(boat)
        fov = config.UBOOT_SCOPE_FOV_DEG
        px_per_deg = rect.w / fov
        silhouette = (60, 66, 72) if night else (28, 34, 40)
        if opfor.scope_available(boat):
            for row in orders.sightings:
                off = relative_offset(row["bearing"], line_of_sight)
                if abs(off) > fov / 2 + row["span_deg"] / 2:
                    continue
                cx = rect.centerx + int(off * px_per_deg)
                base = horizon + int(math.tan(tilt) * (cx - rect.centerx))
                width = max(3, int(row["span_deg"] * px_per_deg))
                width = min(width, rect.w)
                stale = game.sim_t - row["t"] > 1.0
                color = _blend(silhouette, haze_color, 0.5 if stale else haze * 0.5)
                draw_silhouette(s, row["cls"], cx, base, width, color)
        # Bearing scale along the top edge (true bearings).
        first = int(math.floor((line_of_sight - fov / 2) / 5.0)) * 5
        for tick in range(first, first + int(fov) + 10, 5):
            off = relative_offset(tick, line_of_sight)
            if abs(off) > fov / 2:
                continue
            tx = rect.x + int((off + fov / 2) * px_per_deg)
            major = tick % 10 == 0
            pygame.draw.line(s, (220, 225, 225), (tx, rect.y), (tx, rect.y + (10 if major else 5)), 1)
            if major:
                layout.blit_line(s, raw_text(f"{tick % 360:03d}"), (tx - 16, rect.y + 11, 32, 13),
                                 (220, 225, 225), size=11, align="center")
        # Crosshair with the stadimeter window.
        pygame.draw.line(s, (235, 235, 210), (rect.centerx, rect.y + 26),
                         (rect.centerx, rect.bottom), 1)
        window = int(config.UBOOT_STADIMETER_WINDOW_DEG * px_per_deg)
        pygame.draw.line(s, (235, 235, 210), (rect.centerx - window, rect.centery),
                         (rect.centerx + window, rect.centery), 1)
        pygame.draw.rect(s, (235, 235, 210), rect, 1)


def sighting_rows(game, boat) -> list:
    """``(text, color)`` of the boat's sightings, nearest the crosshair first."""
    line_of_sight = opfor.scope_bearing(boat)
    rows = []
    for row in sorted(boat.orders.sightings,
                      key=lambda item: abs(relative_offset(item["bearing"], line_of_sight))):
        cls = display_value("sighting_class", row["cls"])
        if row["range_nm"] is not None:
            distance = message("uboot.value.sighting_range", range=f"{row['range_nm']:.1f}",
                               sigma=f"{row['range_sigma_nm']:.1f}",
                               age=_fmt(game.sim_t - row["range_t"]))
        else:
            distance = localize("uboot.value.no_range")
        text = message("uboot.line.sighting_row", bearing=f"{row['bearing']:03.0f}",
                       cls=cls, span=f"{row['span_deg'] * 60.0:.0f}", distance=distance)
        fresh = game.sim_t - row["t"] <= 1.0
        in_window = (fresh and abs(relative_offset(row["bearing"], line_of_sight))
                     <= config.UBOOT_STADIMETER_WINDOW_DEG)
        rows.append((text, config.COLOR_WARN if in_window
                     else config.COLOR_TEXT if fresh else config.COLOR_TEXT_DIM))
    return rows


def draw_scope_page(s, game, boat, x, y, w, h) -> None:
    """Periscope: eyepiece, line of sight, light and the sightings list."""
    orders = boat.orders
    available = opfor.scope_available(boat)
    view_h = max(120, min(int(h * 0.56), 260))
    box = layout.box(s, (x, y, w, view_h + 24), "uboot.panel.scope",
                     border=config.COLOR_WARN if available else config.COLOR_TEXT)
    bx, by, bw, _ = box
    view = pygame.Rect(bx, by, bw, view_h)
    if available:
        draw_eyepiece(s, game, boat, view)
    else:
        pygame.draw.rect(s, config.COLOR_GEO_BG, view)
        pygame.draw.rect(s, config.COLOR_SONAR_RING, view, 1)
        layout.blit_block(s, "uboot.line.scope_mast_down", view.x + 12, view.y + view.h // 2 - 24,
                          view.w - 24, 48, config.COLOR_TEXT_DIM, size=18, align="center")
    info_y = y + view_h + 34
    line_of_sight = opfor.scope_bearing(boat)
    layout.blit_line(s, message("uboot.line.scope_bearing", bearing=f"{line_of_sight:03.0f}",
                                relative=f"{orders.scope_rel_deg:03.0f}"),
                     (x, info_y, w, 24), config.COLOR_TEXT, size=20)
    night = game.world.is_night()
    visibility = getattr(game.world, "visibility_nm", config.WEATHER_VISIBILITY_MAX_NM)
    sea_state = getattr(game.world, "effective_sea_state", game.world.sea_state)
    layout.blit_line(s, message("uboot.line.scope_light",
                                light=localize("weather.night" if night else "weather.day"),
                                visibility=f"{visibility:.0f}", sea=f"{sea_state:.0f}"),
                     (x, info_y + 26, w, 20), config.COLOR_TEXT_DIM, size=15)
    list_y = info_y + 52
    list_h = y + h - list_y
    if list_h < 40:
        return
    inner = layout.box(s, (x, list_y, w, list_h), "uboot.panel.sightings")
    lx, ly, lw, lh = inner
    rows = sighting_rows(game, boat) if available else []
    if not rows:
        layout.blit_line(s, "uboot.line.no_sighting" if available else "uboot.line.scope_mast_down",
                         (lx, ly, lw, 22), config.COLOR_TEXT_DIM, size=16)
        return
    for index, (text, color) in enumerate(rows):
        row_y = ly + index * 22
        if row_y + 22 > ly + lh:
            break
        layout.blit_line(s, text, (lx, row_y + 2, lw, 20), color, size=15)
