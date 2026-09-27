"""Bridge / navigation station view: weather strip, chart and lookout scope
(verbatim from ``stations_view``)."""

import math

import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize, message as structured_message
from src.core.station import Station
from src.ui import horizon, layout
from src.ui import observations


from src.ui.stations.common import (
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Brücke / Nautik -------------------------------------------------------


def _draw_bridge_weather(surface, rect, weather: dict, hour: float,
                         phase_s: float) -> None:
    """Draw a bounded marine instrument from authoritative weather values."""
    area = pygame.Rect(rect)
    previous_clip = surface.get_clip()
    surface.set_clip(area)
    is_night = hour < 5.5 or hour >= 19.5
    visibility = weather["visibility_nm"]
    haze = 1.0 - config.clamp(visibility / config.WEATHER_VISIBILITY_MAX_NM,
                              0.0, 1.0)
    sky_top = (5, 14, 27) if is_night else (25, 70, 92)
    sky_bottom = (38, 53, 62) if is_night else (111, 151, 157)
    horizon = area.y + int(area.h * 0.54)
    for py in range(area.y, horizon):
        blend = (py - area.y) / max(1, horizon - area.y - 1)
        color = tuple(int(a + (b - a) * blend)
                      for a, b in zip(sky_top, sky_bottom))
        pygame.draw.line(surface, color, (area.x, py), (area.right, py))
    pygame.draw.rect(surface, (7, 35, 48) if is_night else (9, 54, 67),
                     (area.x, horizon, area.w, area.bottom - horizon))

    daylight_start, daylight_end = 5.5, 19.5
    if not is_night:
        progress = config.clamp((hour - daylight_start)
                                / (daylight_end - daylight_start), 0.0, 1.0)
        light = (247, 209, 92)
    else:
        progress = ((hour - daylight_end) % 24.0) / (24.0 - daylight_end
                                                     + daylight_start)
        light = (188, 210, 211)
    light_x = area.x + 12 + int(progress * max(1, area.w - 24))
    light_y = horizon - 7 - int(math.sin(progress * math.pi)
                               * max(5, area.h * 0.28))
    pygame.draw.circle(surface, light, (light_x, light_y), 6)

    sea_state = weather["sea_state"]
    direction_phase = math.radians(weather["wind_from_deg"])
    for band in range(3):
        base = horizon + 8 + band * 10
        amplitude = 1.5 + sea_state * (0.45 + band * 0.12)
        wavelength = max(14.0, 31.0 - sea_state * 2.0 + band * 5.0)
        speed = 0.7 + weather["wind_speed_kn"] / 35.0 + band * 0.18
        points = []
        for px in range(area.x - 2, area.right + 3, 3):
            angle = ((px - area.x) / wavelength * math.tau
                     + phase_s * speed + direction_phase)
            points.append((px, base + int(math.sin(angle) * amplitude)))
        pygame.draw.lines(surface,
                          config.COLOR_WARN if sea_state >= 5 else
                          ((71, 145, 151) if is_night else (91, 181, 181)),
                          False, points, 1)
        if sea_state >= 4.0:
            for crest in range(min(8, int(sea_state * 1.2))):
                px = area.x + int((crest * 43 + phase_s * 7 + band * 17) % area.w)
                pygame.draw.line(surface, (178, 208, 202),
                                 (px, base - int(amplitude)), (px + 5, base - 1), 1)

    rain_count = int(weather["rain_intensity"] * 26)
    for index in range(rain_count):
        px = area.x + int((index * 47 + phase_s * 31) % (area.w + 16)) - 8
        py = area.y + int((index * 23 + phase_s * 53) % area.h)
        pygame.draw.line(surface, (128, 174, 184), (px, py), (px - 3, py + 8), 1)
    if haze > 0.02:
        veil = pygame.Surface(area.size, pygame.SRCALPHA)
        veil.fill((170, 184, 181, int(150 * haze)))
        surface.blit(veil, area.topleft)

    center = (area.x + 17, area.y + 17)
    angle = math.radians(weather["wind_from_deg"])
    source = (center[0] + int(math.sin(angle) * 11),
              center[1] - int(math.cos(angle) * 11))
    pygame.draw.circle(surface, (8, 24, 30), center, 13)
    pygame.draw.circle(surface, config.COLOR_TEXT_DIM, center, 13, 1)
    pygame.draw.line(surface, config.COLOR_WARN, source, center, 2)
    pygame.draw.circle(surface, config.COLOR_WARN, source, 2)
    pygame.draw.rect(surface, config.COLOR_GRID, area, 1)
    surface.set_clip(previous_clip)


@localized
def draw_bridge_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    from src.core.commands import STATION_PAGES
    pages = STATION_PAGES[Station.BRIDGE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.bridge.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    content_h = station_rect.bottom - cy - 30
    x = r[0] + 14
    w = r[2] - 28

    # Build threats list (shared by both pages for alarm bar)
    threats = []
    asm_tracks = game.asm_tracks()
    if asm_tracks:
        ranged = [(t, observations.range_nm(t, game.ship)) for t in asm_tracks]
        nearest, displayed_range = min(
            ((track, distance) for track, distance in ranged
             if distance is not None), key=lambda item: item[1],
            default=(None, None))
        if nearest:
            tti = displayed_range / max(.001, config.kn_to_nm_per_s(
                getattr(game, "asm_speed_kn", 1.0)))
            threats.append(("ASM", localize(message("bridge.line.asm_threat",
                            bearing=observations.format_bearing(nearest, game.ship), range=f"{displayed_range:.1f}",
                            tti=f"{tti:.0f}"))))
        else:
            threats.append(("ASM", message("bridge.line.asm_bearing_only",
                bearing=observations.format_bearing(asm_tracks[0], game.ship))))
    # Torpedo alarms come from intercepts (launch transient, HF seeker
    # pulses) or an operator TORPEDO classification, never the entity type.
    torpedo_warnings = game.torpedo_warnings()
    if torpedo_warnings:
        warning = torpedo_warnings[0]
        threats.append(("TORPEDO", localize(message(
            "bridge.line.torpedo_" + warning["source"],
            bearing=f"{warning['bearing']:05.1f}",
            age=f"{warning['age_s']:.0f}"))))
    if game.damage.avg_flood() >= 25:
        threats.append((localize("station.damage"), localize(message(
            "station.tooltip.mean_flooding", flooding=f"{game.damage.avg_flood():.0f}"))))

    alarm = localize("panel.no_threat") if not threats else localize(message(
        "bridge.line.threat", kind=threats[0][0], detail=threats[0][1]))
    alarm_color = config.COLOR_OK if not threats else config.COLOR_DANGER
    alarm_h = 54 if len(threats) > 1 else 38
    pygame.draw.rect(s, config.COLOR_ALARM_BG, (x, cy, w, alarm_h))
    pygame.draw.rect(s, alarm_color, (x, cy, w, alarm_h), 2)
    layout.blit_line(s, alarm, (x + 10, cy + 5, w - 20, 28), alarm_color,
                     size=20, align="center")
    if len(threats) > 1:
        summary = localize(message("bridge.line.more", threats=" | ".join(
            name for name, _ in threats[1:])))
        layout.blit_line(s, summary, (x + 10, cy + 33, w - 20, 20),
                         config.COLOR_WARN, size=16, align="center")
    y2 = cy + alarm_h + 12

    if page == 0:
        # NAV page: course/rudder + speed/acoustics with larger fonts
        box_h = content_h - alarm_h - 12
        half = (w - 10) // 2
        nav = layout.box(s, (x, y2, half, box_h), "panel.course_rudder",
                         border=config.COLOR_TEXT)
        nx, ny, nw, _ = nav
        layout.blit_line(s, message("bridge.line.course", course=f"{game.ship.course:05.1f}"),
                         (nx, ny, nw, 38), config.COLOR_TEXT, size=32)
        layout.status_line(s, nx, ny + 42, nw, "ui.target_value_short",
                           message("bridge.line.course", course=f"{game.ship.target_course:05.1f}"), size=20, label_w=80)
        layout.status_line(s, nx, ny + 72, nw, "ui.rudder",
                           message("bridge.line.course", course=f"{game.ship.rudder_angle:+4.1f}"), size=20, label_w=80)
        layout.status_line(s, nx, ny + 102, nw, "ui.turn_radius",
                           message("bridge.line.range", range=f"{game.ship.turn_radius_nm:.2f}"), size=18, label_w=130)

        drive = layout.box(s, (x + half + 10, y2, half, box_h), "panel.speed_acoustics",
                           border=config.COLOR_WARN if game.ship.cavitating else config.COLOR_TEXT)
        dx, dy, dw, _ = drive
        layout.blit_line(s, message("bridge.line.speed", speed=f"{game.ship.speed:04.1f}"),
                         (dx, dy, dw, 38), config.COLOR_TEXT, size=32)
        layout.status_line(s, dx, dy + 42, dw, "ui.order", game.ship.telegraph,
                           size=20, label_w=90)
        layout.status_line(s, dx, dy + 72, dw, "ui.target_value_short",
                           message("bridge.line.speed", speed=f"{game.ship.target_speed:.1f}"), size=20, label_w=90)
        noise = "bridge.cavitation" if game.ship.cavitating else message(
            "bridge.line.own_noise", noise=f"{game.ship.noise_level() * 100:.0f}")
        layout.blit_line(s, noise, (dx, dy + 102, dw, 24),
                         config.COLOR_DANGER if game.ship.cavitating else config.COLOR_OK,
                         size=18)
    elif page == 2:
        _draw_bridge_lookout(game, s, pygame.Rect(x, y2, w, content_h - alarm_h - 12))
    else:
        # MISSION page: mission + tactical systems
        half_box = (content_h - alarm_h - 12 - 10) // 2
        mission = layout.box(s, (x, y2, w, half_box), "panel.mission")
        mx, my, mw, _ = mission
        layout.blit_line(s, game.mission_name_display(), (mx, my, mw, 26),
                         config.COLOR_TEXT, size=22)
        layout.blit_line(s, game.mission_objective_display(), (mx, my + 30, mw, 24),
                         config.COLOR_TEXT_DIM, size=18)
        layout.status_line(s, mx, my + 60, mw, "ui.remaining",
                           game.mission.format_remaining(game.mission_time),
                           size=20, label_w=120)

        systems = layout.box(s, (x, y2 + half_box + 10, w, half_box), "panel.tactical")
        sx, sy, sw, _ = systems
        weather_w = min(200, sw // 3)
        text_w = sw - weather_w - 12
        radar = message("station.tooltip.radar_state",
                        surface=structured_message("common.on" if game.surface_radar_on
                                                   else "common.off"),
                        air=structured_message("common.on" if game.air_radar_on
                                               else "common.off"))
        layout.status_line(s, sx, sy, text_w, "panel.sensors",
                           message("bridge.line.sensors", count=len(game.sonar.active_contacts()), radar=radar),
                           size=18, label_w=100)
        layout.status_line(s, sx, sy + 30, text_w, "panel.assets",
                           message("bridge.line.assets", vls=game.vls_cells,
                                   torpedoes=game.torpedo_count,
                                   helo=structured_message('enum.helo.' + game.helo.state)),
                           size=18, label_w=120)
        weather = game.world.weather_values()
        layout.blit_line(s, message("bridge.line.weather",
                                    kind=display_value("weather", game.world.weather_kind()),
                                    sea=f"{weather['sea_state']:.1f}",
                                    light=localize("weather.night" if game.world.is_night()
                                                   else "weather.day")),
                         (sx, sy + 64, text_w, 22), config.COLOR_TEXT_DIM, size=16)
        layout.blit_line(s, message(
            "bridge.line.weather_detail", direction=f"{weather['wind_from_deg']:03.0f}",
            speed=f"{weather['wind_speed_kn']:.0f}",
            rain=f"{weather['rain_intensity']:.0%}",
            visibility=f"{weather['visibility_nm']:.1f}"),
            (sx, sy + 90, text_w, 22), config.COLOR_TEXT_DIM, size=16)
        weather_rect = pygame.Rect(sx + text_w + 12, sy, weather_w, 90)
        _draw_bridge_weather(s, weather_rect, weather, game.world.hour, game.sim_t)

    station_bottom = config.STATION_RECT[1] + config.STATION_RECT[3]
    _shortcut_footer(s, (x, station_bottom - 26, w, 20), (
        ("←/→", "bridge.footer.course"),
        ("↑/↓", "bridge.footer.telegraph"),
        (", / .", "bridge.footer.lookout_range"),
    ) if page == 2 else (
        ("←/→", "bridge.footer.course"),
        ("↑/↓", "bridge.footer.telegraph"),
        ("U", "bridge.footer.set_course"),
        ("V", "bridge.footer.set_speed"),
    ))



_LOOKOUT_KIND_COLORS = {
    "SURFACE": config.COLOR_CONTACT_ZIVIL,
    "SUB": config.COLOR_CONTACT_UBOOT,
    "FLG": config.COLOR_FLIGHT,
    "TORP": config.COLOR_CONTACT_MISSILE,
}


def _lookout_scope_rect(area: pygame.Rect) -> pygame.Rect:
    """Square scope on the left of the lookout page (shared with tooltips)."""
    return pygame.Rect(area.x, area.y, max(40, int(area.w * .58)), max(40, area.h))


LOOKOUT_HORIZON_H = 72
LOOKOUT_HORIZON_FOV_DEG = 90.0
# Assumed lengths (m) of the lookout kinds for the apparent size on the horizon.
_LOOKOUT_KIND_LENGTH_M = {"SURFACE": 120.0, "SUB": 70.0, "FLG": 15.0, "TORP": 40.0}
_LOOKOUT_KIND_CLASS = {"SURFACE": "unknown", "SUB": "unknown", "FLG": "aircraft",
                       "TORP": "torpedo"}


def lookout_outlines(game, sightings) -> list:
    """Detached ``(bearing, span_deg, cls, stale)`` rows of the lookout's own
    tracks: the class from his report, the size from the measured range."""
    from src.sensors import lookout_id
    rows = []
    for track in sightings:
        if track.bearing is None or track.range_nm is None or track.range_nm <= 0.0:
            continue
        cls = _LOOKOUT_KIND_CLASS.get(track.kind, "unknown")
        level, recognized, _identified = lookout_id.decode(track.label)
        if recognized in ("WARSHIP", "CARRIER", "CRUISER", "DESTROYER", "FRIGATE",
                          "CORVETTE", "NAVAL_AUXILIARY", "MINE_WARFARE"):
            cls = "warship"
        elif recognized in ("MERCHANT", "TANKER", "CARGO", "PASSENGER"):
            cls = "merchant"
        span = math.degrees(_LOOKOUT_KIND_LENGTH_M.get(track.kind, 100.0)
                            / max(track.range_nm * 1852.0, 1.0))
        rows.append((track.bearing % 360.0, max(1e-3, min(180.0, span)), cls,
                     game.sim_t - track.last_seen > config.LOOKOUT_EPOCH_S * 2))
    return rows


def _draw_bridge_lookout(game, s, area: pygame.Rect) -> None:
    """Bridge lookout page: north-up scope of the visual sightings.

    Only the lookout's own reports are drawn (measured bearing and range of
    each ``LOOKOUT`` track, what he made out); the same picture as the Remote
    Crew bridge lookout view.
    """
    scope = _lookout_scope_rect(area)
    layout.box(s, scope, "panel.lookout_scope")
    range_nm = float(getattr(game, "lookout_range_nm", 12.0))
    cx, cy = scope.centerx, scope.centery + 10
    radius = max(10, min(scope.w - 70, scope.h - 70) // 2)
    night = game.world.is_night()
    ring = config.COLOR_SONAR_RING
    for fraction in (.25, .5, .75, 1.0):
        pygame.draw.circle(s, ring, (cx, cy), int(radius * fraction), 1)
    layout.blit_line(s, message("bridge.line.lookout_ring", range=f"{range_nm:.0f}"),
                     (scope.x + 10, scope.y + 30, scope.w - 20, 18), config.COLOR_TEXT_DIM,
                     size=14, align="right")
    for bearing in (0, 90, 180, 270):
        angle = math.radians(bearing)
        tx, ty = cx + math.sin(angle) * (radius + 14), cy - math.cos(angle) * (radius + 12)
        layout.blit_line(s, f"{bearing:03d}", (int(tx) - 16, int(ty) - 9, 32, 18),
                         config.COLOR_TEXT_DIM, size=14, align="center")
    sightings = game.lookout_sightings()
    scale = radius / max(.1, range_nm)
    for track in sightings:
        dx, dy = track.x - game.ship.x, track.y - game.ship.y
        if math.hypot(dx, dy) > range_nm:
            angle = math.radians(track.bearing or 0.0)
            px, py = cx + math.sin(angle) * radius, cy - math.cos(angle) * radius
            pygame.draw.circle(s, _LOOKOUT_KIND_COLORS.get(track.kind, config.COLOR_TEXT_DIM),
                               (int(px), int(py)), 3, 1)
            continue
        px, py = int(cx + dx * scale), int(cy + dy * scale)
        color = _LOOKOUT_KIND_COLORS.get(track.kind, config.COLOR_TEXT_DIM)
        pygame.draw.circle(s, color, (px, py), 5)
        what = game.lookout_visual_what(track.label)
        if what is not None and px + 10 < scope.right - 4:
            layout.blit_line(s, what, (px + 8, py - 18, scope.right - px - 12, 16),
                             color, size=13)
    heading = math.radians(game.ship.course)
    tip = (cx + math.sin(heading) * 12, cy - math.cos(heading) * 12)
    left = (cx + math.sin(heading + 2.5) * 8, cy - math.cos(heading + 2.5) * 8)
    right = (cx + math.sin(heading - 2.5) * 8, cy - math.cos(heading - 2.5) * 8)
    pygame.draw.polygon(s, config.COLOR_OK, (tip, left, right), 0)
    pygame.draw.line(s, config.COLOR_OK, tip,
                     (cx + math.sin(heading) * min(40, radius * .5),
                      cy - math.cos(heading) * min(40, radius * .5)), 1)

    info = layout.box(s, (scope.right + 10, area.y, area.right - scope.right - 10, area.h),
                      "panel.lookout_reports")
    ix, iy, iw, ih = info
    weather = game.world.weather_values()
    # The binoculars toward the bow: the same horizon as the boat's periscope,
    # with the outlines of the lookout's own sightings (measured bearing and
    # range; the class from what he made out).
    strip_h = LOOKOUT_HORIZON_H if ih >= 260 else 0
    if strip_h:
        horizon.draw_horizon(
            s, (ix, iy, iw, strip_h), line_of_sight=game.ship.course % 360.0,
            fov_deg=LOOKOUT_HORIZON_FOV_DEG, night=night,
            visibility_nm=weather["visibility_nm"],
            motion=horizon.horizon_motion(0, game.sim_t, weather["sea_state"]),
            outlines=lookout_outlines(game, sightings))
        iy += strip_h + 6
        ih -= strip_h + 6
    layout.blit_line(s, message("bridge.line.lookout_visibility",
                                visibility=f"{weather['visibility_nm']:.1f}"),
                     (ix, iy, iw, 20), config.COLOR_TEXT, size=15)
    layout.blit_line(s, message("bridge.line.lookout_sea_light", sea=f"{weather['sea_state']:.0f}",
                                light=localize("weather.night" if night else "weather.day")),
                     (ix, iy + 21, iw, 20), config.COLOR_TEXT, size=15)
    layout.blit_line(s, message("bridge.line.lookout_count", count=len(sightings)),
                     (ix, iy + 42, iw, 20), config.COLOR_TEXT_DIM, size=15)
    ry = iy + 70
    reports = list(game.lookout_reports)[-8:]
    if not reports:
        layout.blit_block(s, "bridge.line.lookout_none", ix, ry, iw, max(40, iy + ih - ry),
                          color=config.COLOR_TEXT_DIM, size=14)
    for report in reversed(reports):
        if ry + 74 > iy + ih:
            break
        layout.blit_line(s, report["stamp"], (ix, ry, iw, 16), config.COLOR_TEXT_DIM, size=13)
        layout.blit_block(s, game.lookout_report_text(report), ix, ry + 16, iw, 56,
                          color=config.COLOR_TEXT, size=13)
        ry += 76
