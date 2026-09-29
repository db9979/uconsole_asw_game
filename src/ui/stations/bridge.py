"""Bridge / navigation station view: weather strip, chart and lookout scope
(verbatim from ``stations_view``)."""

import math

import pygame

from src.core import config
from src.core.i18n import (display_message, display_value, localized, localize,
                            message as structured_message)
from src.core.station import Station
from src.ui import horizon, instruments, layout, sight_scene
from src.ui import observations


from src.ui.stations.common import (
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Brücke / Nautik -------------------------------------------------------


def _draw_bridge_weather(surface, rect, weather: dict, hour: float,
                         phase_s: float, sky: dict | None = None) -> None:
    """The weather instrument in the start screen's look: a small eyepiece
    picture looking into the wind (sky of the hour, clouds, rain, snow, fog,
    the sea running at the eye) with the wind rose in its corner."""
    if sky is None:
        sky = dict(sight_scene.plain_sky(hour < config.DAYLIGHT_START_H
                                         or hour >= config.DAYLIGHT_END_H),
                   wind_from_deg=weather["wind_from_deg"])
    sight_scene.draw_instrument(surface, rect, sky, visibility_nm=weather["visibility_nm"],
                                sea_state=weather["sea_state"], t=phase_s)


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
        nx, ny, nw, nh = nav
        nav_bottom = ny + nh
        big, row = layout.line_pitch(32, 2), layout.line_pitch(20, 6)
        layout.blit_line(s, message("bridge.line.course", course=f"{game.ship.course % 360:03.0f}"),
                         (nx, ny, nw, big), config.COLOR_TEXT, size=32)
        ny += big
        layout.status_line(s, nx, ny, nw, "ui.target_value_short",
                           message("bridge.line.course", course=f"{game.ship.target_course % 360:03.0f}"), size=20, label_w=80)
        ny += row
        layout.status_line(s, nx, ny, nw, "ui.rudder",
                           message("bridge.line.course", course=f"{game.ship.rudder_angle:+.0f}"), size=20, label_w=80)
        ny += row
        instruments.rudder_scale(s, (nx + 8, ny, nw - 16, 18), game.ship.rudder_angle,
                                 config.SHIP_MAX_RUDDER_DEG)
        ny += 26
        if math.isfinite(game.ship.turn_radius_nm):
            # Straight ahead the radius says nothing; the line appears in a turn.
            layout.status_line(s, nx, ny, nw, "ui.turn_radius",
                               message("bridge.line.range", range=f"{game.ship.turn_radius_nm:.2f}"), size=18, label_w=130)
        ny += row
        route = game.route
        if route.active:
            wx, wy = route.current()
            layout.status_line(s, nx, ny, nw, "ui.autopilot", message(
                "bridge.line.route", number=route.index + 1, total=len(route.points),
                range=f"{math.hypot(wx - game.ship.x, wy - game.ship.y):.1f}"),
                size=18, label_w=130, color=config.COLOR_WARN)
        ny += row
        # The free lower part of the box carries the heading dial.
        instruments.heading_dial(s, (nx, ny, nw, nav_bottom - ny), game.ship.course,
                                 game.ship.target_course)

        drive = layout.box(s, (x + half + 10, y2, half, box_h), "panel.speed_acoustics",
                           border=config.COLOR_WARN if game.ship.cavitating else config.COLOR_TEXT)
        dx, dy, dw, dh = drive
        drive_bottom = dy + dh
        layout.blit_line(s, message("bridge.line.speed", speed=f"{game.ship.speed:04.1f}"),
                         (dx, dy, dw, big), config.COLOR_TEXT, size=32)
        dy += big
        layout.status_line(s, dx, dy, dw, "ui.order", display_message("telegraph", game.ship.telegraph),
                           size=20, label_w=90)
        dy += row
        layout.status_line(s, dx, dy, dw, "ui.target_value_short",
                           message("bridge.line.speed", speed=f"{game.ship.target_speed:.1f}"), size=20, label_w=90)
        dy += row
        noise = "bridge.cavitation" if game.ship.cavitating else message(
            "bridge.line.own_noise", noise=f"{game.ship.noise_level() * 100:.0f}")
        layout.blit_line(s, noise, (dx, dy, dw, layout.line_pitch(18, 0)),
                         config.COLOR_DANGER if game.ship.cavitating else config.COLOR_OK,
                         size=18)
        dy += row + 26
        instruments.speed_dial(s, (dx, dy, dw, drive_bottom - dy), game.ship.speed,
                               game.ship.target_speed, config.TELEGRAPH_ORDERS[-1][1])
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
        _draw_bridge_weather(s, weather_rect, weather, game.world.hour, game.sim_t,
                             sight_scene.sky_state(game))

    station_bottom = config.STATION_RECT[1] + config.STATION_RECT[3]
    _shortcut_footer(s, (x, station_bottom - 26, w, 20), (
        ("←/→", "bridge.footer.course"),
        ("↑/↓", "bridge.footer.glasses_tilt" if game.lookout_glasses
         else "bridge.footer.telegraph"),
        (", / .", "bridge.footer.glasses_train" if game.lookout_glasses
         else "bridge.footer.lookout_range"),
        ("B", "bridge.footer.glasses_close" if game.lookout_glasses
         else "bridge.footer.glasses"),
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


def _lookout_land(game):
    """The charted coast as the bridge lookout sees it (known geography)."""
    from src.sensors.visual import LOOKOUT_EYE_HEIGHT_M
    return horizon.land_view(game.world, game.ship.x, game.ship.y, LOOKOUT_EYE_HEIGHT_M)


def lookout_outlines(game, sightings) -> list:
    """Detached ``(bearing, span_deg, cls, stale, lights, elevation_deg,
    aob_deg)`` rows of the lookout's own tracks: the class from his report,
    the size from the measured range, the navigation lights he makes out
    (``nav_lights`` code), an aircraft's angle above the horizon (``None``
    on the surface) and the angle on the bow he judges of a made-out
    silhouette (``None`` before; it turns the model)."""
    from src.sensors import lookout_id
    lit = getattr(game, "_lookout_lights", {})
    elevation = getattr(game, "_lookout_elevation", {})
    aspects = getattr(game, "_lookout_aspect", {})
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
        stale = game.sim_t - track.last_seen > config.LOOKOUT_EPOCH_S * 2
        lights = lit.get(getattr(track, "track_id", None))
        aloft = elevation.get(getattr(track, "track_id", None)) if track.kind == "FLG" else None
        aspect = aspects.get(getattr(track, "track_id", None))
        rows.append((track.bearing % 360.0, max(1e-3, min(180.0, span)), cls, stale,
                     lights[0] if lights is not None and not stale else None,
                     None if aloft is None else aloft[0],
                     None if aspect is None or stale else aspect[0]))
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
            motion=horizon.horizon_motion(0, game.sim_t, weather["sea_state"],
                                          weather["wind_from_deg"] - game.ship.course),
            outlines=lookout_outlines(game, sightings), land=_lookout_land(game),
            anim_t=game.sim_t, sky=sight_scene.sky_state(game), sea_state=weather["sea_state"])
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


# --- binoculars over the chart (bridge lookout page, display only) ----------

def _glasses_layout():
    """(frame, eyepiece, panorama) rects of the binoculars over the chart."""
    frame = pygame.Rect(config.MAP_RECT)
    inner = frame.inflate(-20, -20)
    eyepiece = pygame.Rect(inner.x, inner.y + 30, inner.w, int(inner.h * 0.52))
    panorama = pygame.Rect(inner.x, eyepiece.bottom + 44, inner.w, 56)
    return frame, eyepiece, panorama


def _panorama_x(panorama: pygame.Rect, bearing: float, course: float) -> int:
    """Panorama position of a true bearing: the bow in the middle, astern at the ends."""
    return panorama.x + int((horizon.relative_offset(bearing, course) + 180.0)
                            / 360.0 * panorama.w)


def lookout_glasses_bearing_at(game, canvas):
    """True bearing under a click on the binoculars' panorama, else None."""
    if canvas is None or not game.lookout_glasses_shown():
        return None
    _frame, _eyepiece, panorama = _glasses_layout()
    if not panorama.collidepoint(canvas):
        return None
    fraction = (canvas[0] - panorama.x) / max(1, panorama.w)
    return (game.ship.course + fraction * 360.0 - 180.0) % 360.0


def draw_lookout_glasses(game) -> None:
    """The lookout's binoculars, large over the chart: a trainable eyepiece
    with the outlines of his own sightings and an all-round panorama of their
    measured bearings (the same reports as the lookout page)."""
    s = game.screen
    frame, eyepiece, panorama = _glasses_layout()
    pygame.draw.rect(s, config.COLOR_PANEL_BG, frame)
    layout.box(s, frame, "panel.lookout_glasses")
    weather = game.world.weather_values()
    night = game.world.is_night()
    sightings = game.lookout_sightings()
    course = game.ship.course % 360.0
    line_of_sight = (course + game.lookout_glasses_rel) % 360.0
    land = _lookout_land(game)
    sight = game.lookout_optics
    fov = sight.fov_deg
    horizon.draw_horizon(
        s, eyepiece, line_of_sight=line_of_sight, fov_deg=fov,
        night=night, visibility_nm=weather["visibility_nm"],
        motion=horizon.horizon_motion(0, game.sim_t, weather["sea_state"],
                                      weather["wind_from_deg"] - course,
                                      game.lookout_glasses_rel),
        outlines=lookout_outlines(game, sightings), land=land, anim_t=game.sim_t,
        sky=sight_scene.sky_state(game), sea_state=weather["sea_state"],
        elevation_deg=sight.elevation_deg, stabilized=sight.stabilized)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, eyepiece, 1)
    layout.blit_line(s, structured_message(
        "bridge.line.glasses_bearing", bearing=f"{line_of_sight:03.0f}",
        relative=f"{game.lookout_glasses_rel:03.0f}",
        elevation=f"{sight.elevation_deg:+.0f}", fov=f"{fov:.0f}"),
        (eyepiece.x, eyepiece.bottom + 8, eyepiece.w, 24), config.COLOR_TEXT, size=18)
    # All-round panorama: the bow in the middle; each sighting as a tick at
    # its measured bearing, the binoculars' field as a frame.
    pygame.draw.rect(s, config.COLOR_GEO_BG, panorama)
    distance = land[0]
    step = 360.0 / len(distance)
    for index, value in enumerate(distance):
        # The coast in sight, as a band along the foot of the panorama.
        if value <= weather["visibility_nm"]:
            px = _panorama_x(panorama, index * step, course)
            pygame.draw.line(s, config.COLOR_LAND_EDGE, (px, panorama.bottom - 10),
                             (px, panorama.bottom - 2), 2)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, panorama, 1)
    for relative in (-180, -90, 0, 90, 180):
        px = panorama.x + int((relative + 180.0) / 360.0 * panorama.w)
        pygame.draw.line(s, config.COLOR_SONAR_RING, (px, panorama.y), (px, panorama.y + 8))
        label_x = min(max(px - 20, panorama.x), panorama.right - 40)
        layout.blit_line(s, f"{(course + relative) % 360.0:03.0f}",
                         (label_x, panorama.bottom + 2, 40, 16), config.COLOR_TEXT_DIM,
                         size=13, align="left" if relative == -180 else
                         "right" if relative == 180 else "center")
    for track in sightings:
        if track.bearing is None:
            continue
        px = _panorama_x(panorama, track.bearing % 360.0, course)
        color = _LOOKOUT_KIND_COLORS.get(track.kind, config.COLOR_TEXT_DIM)
        pygame.draw.line(s, color, (px, panorama.y + 12), (px, panorama.bottom - 12), 3)
    half = fov / 2.0
    left = panorama.x + int((horizon.relative_offset(line_of_sight - half, course) + 180.0)
                            / 360.0 * panorama.w)
    width = max(4, int(fov / 360.0 * panorama.w))
    for start in {left, left - panorama.w, left + panorama.w}:
        window = pygame.Rect(start, panorama.y + 2, width, panorama.h - 4).clip(panorama)
        if window.w > 0:
            pygame.draw.rect(s, config.COLOR_WARN, window, 2)
    layout.blit_line(s, structured_message("bridge.line.glasses_hint"),
                     (frame.x + 10, panorama.bottom + 22, frame.w - 20, 20),
                     config.COLOR_TEXT_DIM, size=14)
    # The lookout's sightings, nearest the line of sight first.
    row_y = panorama.bottom + 48
    rows = sorted((track for track in sightings if track.bearing is not None),
                  key=lambda track: abs(horizon.relative_offset(track.bearing, line_of_sight)))
    for track in rows:
        if row_y + 20 > frame.bottom - 8:
            break
        what = game.lookout_visual_what(track.label) or localize("bridge.line.glasses_unknown")
        in_view = (abs(horizon.relative_offset(track.bearing, line_of_sight))
                   <= fov / 2.0)
        layout.blit_line(s, structured_message(
            "bridge.line.glasses_row", bearing=f"{track.bearing % 360.0:03.0f}", what=what,
            range=f"{track.range_nm:.1f}" if track.range_nm is not None else "--"),
            (frame.x + 10, row_y, frame.w - 20, 20),
            config.COLOR_WARN if in_view else config.COLOR_TEXT, size=15)
        row_y += 21
