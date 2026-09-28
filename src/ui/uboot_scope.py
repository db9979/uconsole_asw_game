"""Periscope page of the crewed submarine (uConsole).

Everything drawn here is the boat's own: the line of sight of its scope,
the light and weather its optics see, and the sightings the crew made
(``opfor.update_sightings``).  Silhouettes are procedural by the coarse
class the eye made out and the apparent length it measured; no frigate
truth is read here.
"""

import math

import pygame

from src.core import attack_computer, config, opfor
from src.core.i18n import display_value, localize, message
from src.ui import layout

from src.ui import sight_scene  # noqa: E402
from src.ui.horizon import (draw_horizon, draw_outline, land_view,  # noqa: E402,F401
                            relative_offset)


def _fmt(value, pattern="{:.0f}"):
    return "--" if value is None or not math.isfinite(value) else pattern.format(value)


def draw_silhouette(s, cls: str, cx: int, base_y: int, width: int, color) -> None:
    """Kept for callers: the shared outline renderer."""
    draw_outline(s, cls, cx, base_y, width, color)


def scope_outlines(game, boat) -> list:
    """Detached ``(bearing, span_deg, cls, stale)`` rows of the sightings."""
    return [(row["bearing"], row["span_deg"], row["cls"], game.sim_t - row["t"] > 1.0)
            for row in boat.orders.sightings]


def draw_eyepiece(s, game, boat, rect) -> None:
    """The picture in the eyepiece: sky, sea, horizon in motion, bearing scale,
    crosshair and the outlines of the boat's sightings within the field."""
    draw_horizon(s, rect, line_of_sight=opfor.scope_bearing(boat),
                 fov_deg=config.UBOOT_SCOPE_FOV_DEG, night=game.world.is_night(),
                 visibility_nm=getattr(game.world, "visibility_nm",
                                       config.WEATHER_VISIBILITY_MAX_NM),
                 motion=opfor.horizon_motion(game, boat),
                 outlines=scope_outlines(game, boat) if opfor.scope_available(boat) else [],
                 crosshair_deg=config.UBOOT_STADIMETER_WINDOW_DEG,
                 land=land_view(game.world, boat.sub.x, boat.sub.y,
                                config.UBOOT_SCOPE_EYE_HEIGHT_M),
                 anim_t=game.sim_t, sky=sight_scene.sky_state(game),
                 sea_state=getattr(game.world, "effective_sea_state", game.world.sea_state))


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
    box_h = view_h + 44
    box = layout.box(s, (x, y, w, box_h), "uboot.panel.scope",
                     border=config.COLOR_WARN if available else config.COLOR_TEXT)
    bx, by, bw, bh = box
    # The eyepiece fills the box's inner area, never its frame.
    view = pygame.Rect(bx, by, bw, bh)
    if available:
        draw_eyepiece(s, game, boat, view)
    else:
        pygame.draw.rect(s, config.COLOR_GEO_BG, view)
        pygame.draw.rect(s, config.COLOR_SONAR_RING, view, 1)
        layout.blit_block(s, "uboot.line.scope_mast_down", view.x + 12, view.y + view.h // 2 - 24,
                          view.w - 24, 48, config.COLOR_TEXT_DIM, size=18, align="center")
    info_y = y + box_h + 8
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
    text, color = tdc_line(game, boat)
    layout.blit_line(s, text, (x, info_y + 48, w, 20), color, size=15)
    list_y = info_y + 72
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


def _signed_lead(lead):
    side = "uboot.value.lead_right" if lead >= 0.0 else "uboot.value.lead_left"
    return message(side, angle=f"{abs(lead):.0f}")


def tdc_line(game, boat):
    """``(text, color)`` of the attack computer on the crosshair sighting."""
    row = opfor.sighting_in_crosshair(boat, game.sim_t) if opfor.scope_available(boat) else None
    if row is None:
        return "uboot.line.tdc_idle", config.COLOR_TEXT_DIM
    values = attack_computer.summary(boat, row["ref"], game.sim_t)
    if values is None:
        return "uboot.line.tdc_idle", config.COLOR_TEXT_DIM
    if values["course"] is None:
        return (message("uboot.line.tdc_marking", marks=values["marks"]),
                config.COLOR_TEXT)
    if values["lead_deg"] is None:
        return (message("uboot.line.tdc_no_intercept", course=f"{values['course']:03.0f}",
                        speed=f"{values['speed_kn']:.0f}"), config.COLOR_WARN)
    minutes, seconds = divmod(int(round(values["run_s"])), 60)
    return (message("uboot.line.tdc_solution", course=f"{values['course']:03.0f}",
                    speed=f"{values['speed_kn']:.0f}", lead=_signed_lead(values["lead_deg"]),
                    run=f"{minutes}:{seconds:02d}", marks=values["marks"],
                    quality=f"{values['quality'] * 100:.0f}"), config.COLOR_OK)
