"""W0: Stations-Views im rechten Hauptpanel (STATION_RECT: 640x510).

Alle Views rendern ausschließlich innerhalb des Rechtecks
(config.STATION_RECT) – die Seekarte bleibt links sichtbar.
"""

import math
import random
import copy

import pygame
import numpy as np

from src.core import config
from src.core.i18n import (display_value, localized, localize, raw_text,
                            message as structured_message)
from src.core.station import Station
from src.ship.damage import COMPARTMENTS
from src.ship.ship import Ship
from src.sensors.esm import animated_signal_fingerprint, spectrum_band
from src.ui.plot_view import draw_plot
from src.ui import layout
from src.ui import chart_symbols
from src.ui import nato_symbols
from src.ui import observations



def _hfdf_error_deg(report) -> float:
    """Half-width of the HFDF bearing error (uniform sigma x sqrt(3))."""
    sigma = getattr(report, "bearing_uncertainty_deg", None)
    return (sigma * math.sqrt(3.0) if sigma else config.HFDF_BEARING_ERR_DEG)

def message(key, **values):
    """A structured message: localized at draw time so layouts can abbreviate."""
    return structured_message(key, **values)

STATE_LABEL = {
    "OK": "damage.ok",
    "BESCHAEDIGT": "damage.damaged",
    "FLUTEND": "damage.flooding",
    "ZERSTOERT": "damage.destroyed",
}

MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    " ": "/",
}


def _to_morse(text: str) -> str:
    out = []
    for ch in text.upper():
        out.append(MORSE.get(ch, "·"))
    return " ".join(out)


def _srect(x_off: int = 0, w: int = None) -> tuple:
    """Inneres Rechteck innerhalb von STATION_RECT."""
    rect = config.STATION_RECT
    x = rect[0] + x_off
    w = rect[2] - x_off if w is None else w
    return (x, rect[1] + 6, w, rect[3] - 12)


def _panel(game, x_off: int = 0, w: int = None, title: str = "") -> tuple:
    r = _srect(x_off, w)
    y = layout.panel(game.screen, r, title)
    return r, y


def _shortcut_footer(screen, rect, specs) -> None:
    """Draw a persistent, single-row legend of a station's key shortcuts.

    ``specs`` is an ordered iterable of ``(key, description_i18n_key)`` pairs,
    evenly split across ``rect``, matching sonar_view's always-visible
    footer-legend pattern (layout.command_segment) instead of a plain hint.
    """
    rect = pygame.Rect(rect)
    specs = tuple(specs)
    if not specs:
        return
    width = max(1, rect.w // len(specs))
    for index, (key, description) in enumerate(specs):
        segment = pygame.Rect(rect.x + index * width, rect.y, width, rect.h)
        layout.command_segment(screen, segment, key, description, size=11)


PAGE_TAB_H = 26
PAGE_TAB_GAP = 4


def _station_page_tab_rects(station_rect: pygame.Rect, n_pages: int) -> list:
    """Evenly spaced tab rectangles below the station title row."""
    if n_pages <= 1:
        return []
    x0 = station_rect.x + 14
    total_w = station_rect.w - 28
    tab_w = total_w // n_pages
    # Title occupies ~y+8 .. y+8+font_linesize; place tabs below that.
    title_h = layout.font(20, bold=True).get_linesize()
    y = station_rect.y + 8 + int(title_h * 1.15) + 6
    tabs = []
    for i in range(n_pages):
        w = tab_w - 4 if i < n_pages - 1 else tab_w
        tabs.append(pygame.Rect(x0 + i * tab_w, y, w, PAGE_TAB_H))
    return tabs


def draw_station_page_tabs(screen, station_rect, pages, current_page,
                           tr=None) -> list:
    """Render a row of clickable page tabs. Returns the tab rects."""
    from src.core.i18n import display_value
    tabs = _station_page_tab_rects(station_rect, len(pages))
    for i, (name, tab) in enumerate(zip(pages, tabs)):
        active = (i == current_page)
        if active:
            pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE, tab)
            pygame.draw.line(screen, config.COLOR_SONAR_RING,
                              tab.topleft, (tab.right - 1, tab.top), 2)
        label = display_value("station_page", name, tr)
        layout.blit_line(screen, label, tab,
                         config.COLOR_TEXT if active else config.COLOR_TEXT_DIM,
                         size=14, align="center")
    return tabs


def station_page_tab_at(pos, station_rect, n_pages):
    """Return the 0-based page index if *pos* hits a tab, else None."""
    if pos is None or n_pages <= 1:
        return None
    for i, tab in enumerate(_station_page_tab_rects(station_rect, n_pages)):
        if tab.collidepoint(pos):
            return i
    return None


def _station_content_top(station_rect, n_pages) -> int:
    """Y coordinate where paged content starts (below title + tabs)."""
    base = station_rect.y + 8
    title_h = layout.font(20, bold=True).get_linesize()
    base += int(title_h * 1.15) + 6
    if n_pages > 1:
        base += PAGE_TAB_H + PAGE_TAB_GAP
    return base


@localized
def draw_autocrew_overview(game, tr=None) -> None:
    """Render the host-only nine-station automation overview."""
    layout.configure_for(game)
    r, y = _panel(game, title="autocrew.overview.title")
    x = r[0] + 14
    width = r[2] - 28
    gap = 12
    card_w = (width - gap * 2) // 3
    card_h = (r[1] + r[3] - y - gap * 2) // 3
    for index, key in enumerate(game.autocrew.enabled):
        row, column = divmod(index, 3)
        rect = (x + column * (card_w + gap), y + row * (card_h + gap),
                card_w, card_h)
        content = layout.box(game.screen, rect, message(
            "autocrew.station", station=display_value("station", key.upper())))
        cx, cy, cw, _ = content
        status = game.autocrew.status(game, key)
        color = (config.COLOR_OK if status == "active" else
                 config.COLOR_WARN if status in ("suspended_remote", "blocked_damage")
                 else config.COLOR_TEXT_DIM)
        layout.blit_line(game.screen, "autocrew.status." + status,
                         (cx, cy, cw, 24), color, size=16)
        layout.blit_block(game.screen,
                          "autocrew.action." + game.autocrew.last_action[key],
                          cx, cy + 30, cw, max(24, card_h - 72),
                          config.COLOR_TEXT_DIM, size=13)


def _observation_bearing(observation) -> float:
    return observations.bearing(observation)


def _observation_position(observation):
    return observations.position(observation)


def _displayed_bearing(observation, ship) -> float:
    return observations.bearing(observation, ship)


def _state_color(state: str) -> tuple:
    return {
        "OK": config.COLOR_OK,
        "BESCHAEDIGT": config.COLOR_WARN,
        "FLUTEND": config.COLOR_DANGER,
        "ZERSTOERT": config.COLOR_DANGER,
    }[state]


def _compartment_name(key: str, fallback: str) -> str:
    """Localize fixed ship compartments without touching authored content."""
    catalog_key = "compartment." + key
    translated = localize(catalog_key)
    return fallback if translated == catalog_key else translated


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

# --- OPZ / CIC (M12) -------------------------------------------------------

# Three-letter domain codes for the dense OPZ track list (see the manual's
# abbreviation table); catalog keys so EN and DE each use their own codes.
OPZ_DOMAIN_CODES = {
    "UNKNOWN": "domain.code.unknown",
    "SURFACE": "domain.code.surface",
    "SUBSURFACE": "domain.code.subsurface",
    "AIR": "domain.code.air",
    "MISSILE": "domain.code.missile",
    "UNDERWATER_WEAPON": "domain.code.underwater_weapon",
}
OPZ_DOMAIN_COLORS = {
    "UNKNOWN": config.COLOR_TEXT_DIM,
    "SURFACE": config.COLOR_CONTACT_ZIVIL,
    "SUBSURFACE": config.COLOR_CONTACT_UBOOT,
    "AIR": config.COLOR_FLIGHT,
    "MISSILE": config.COLOR_CONTACT_MISSILE,
    "UNDERWATER_WEAPON": config.COLOR_CONTACT_MISSILE,
}


def helo_dip_contacts(game):
    """W2: contacts the helicopter's own dip has plotted - independent of
    (and, since the bug fix, never overwriting) the ship's own sonar picture."""
    sonar = getattr(game, "sonar", None)
    contacts = getattr(sonar, "contacts", None)
    if not contacts:
        return []
    sim_t = getattr(game, "sim_t", 0.0)
    return sorted((c for c in contacts.values()
                   if (c.dip_last_seen is not None
                       and 0 <= sim_t - c.dip_last_seen < config.SONAR_CONTACT_LOST_S)
                   or any(fix["source"] == "DIPPING"
                          for fix in c.active_fixes(sim_t))),
                  key=lambda c: c.id)


def _helo_dip_contact_line(game) -> str:
    contacts = helo_dip_contacts(game)
    if not contacts:
        return localize("helo.dip_contact_none")
    current = getattr(game, "selected_contact", None)
    selected = current if current in contacts else contacts[0]
    dip_fix = next((fix for fix in selected.active_fixes(game.sim_t)
                    if fix["source"] == "DIPPING"), None)
    passive_current = (selected.dip_last_seen is not None
                       and 0 <= game.sim_t - selected.dip_last_seen
                       < config.SONAR_CONTACT_LOST_S)
    bearing = (selected.dip_bearing if passive_current else
               math.degrees(math.atan2(
                   dip_fix["x"] - selected.observer_x,
                   -(dip_fix["y"] - selected.observer_y))) % 360.0)
    seen = (selected.dip_last_seen if selected.dip_last_seen is not None
            and 0 <= game.sim_t - selected.dip_last_seen < config.SONAR_CONTACT_LOST_S
            else dip_fix["measured_at"])
    age = max(0.0, game.sim_t - seen)
    released = localize("common.yes" if selected.dip_released_to_opz else "common.no")
    return message(
        "helo.dip_contact_line",
        contact=observations.contact_display_id(game, selected),
        bearing=f"{bearing:05.1f}", age=f"{age:.0f}",
        count=len(contacts), released=released)


def _lookout_line(game, visual):
    what = game.lookout_visual_what(visual) if visual is not None else None
    return None if what is None else message("lookout.tooltip", what=what)


def _track_tooltip(game, track):
    affiliation = game.opz_affiliation(track.track_id)
    domain = nato_symbols.domain_for_kind(track.kind)
    ship = getattr(game, "ship", None)
    displayed_range = observations.range_nm(track, ship)
    distance = f"{displayed_range:.1f}" if displayed_range is not None else "--"
    quality = track.display_quality(game.sim_t, game.air_picture.stale_s)
    pending = game.live_engagement_pending_for_observation(track.track_id)
    return layout.tooltip_payload(
        message("opz.tooltip.track_title", track=track.label,
                label=display_value("classification",
                                    getattr(track, "classification", None))),
        message("opz.tooltip.domain_affiliation", domain=localize("domain.unknown") if domain == "UNKNOWN" else display_value('domain', domain),
                affiliation=display_value('affiliation', affiliation)),
        observations.format_bearing_pair(track, ship),
        message("opz.tooltip.range", range=distance),
        message("opz.tooltip.altitude", altitude=f"{track.altitude_m:.0f}")
        if getattr(track, "altitude_m", None) is not None else None,
        message("opz.tooltip.quality_age", quality=f"{quality:.0%}", age=f"{track.age(game.sim_t):.1f}"),
        message("observation.fix_age", age=f"{observations.position_age(track, game.sim_t):.1f}")
        if observations.position_age(track, game.sim_t) is not None else None,
        message("opz.tooltip.source", source=track.source),
        _lookout_line(game, getattr(track, "visual", None)),
        message("runtime.cic.hostile_confirm_required", track=track.label) if pending else None,
        target_id=f"opz:track:{track.track_id}")


@localized
def opz_hit_target(game, pos):
    """Hit-test the chart using the same OPZ viewport used for drawing."""
    layout.configure_for(game)
    chart = opz_regions()["chart"]
    if pos is None or not pygame.Rect(config.STATION_RECT).collidepoint(pos):
        return None
    tracks = game.opz_tracks()
    if chart.collidepoint(pos):
        view = _opz_view(game, chart)
        for track in reversed(tracks):
            point = _opz_track_point(game, track, chart, view)
            if point is not None and _near_point(pos, point, 15):
                return _track_tooltip(game, track)
        helo = getattr(game, "helo", None)
        if helo is not None and helo.airborne:
            dx, dy = helo.x - game.ship.x, helo.y - game.ship.y
            point = view.world_to_screen(helo.x, helo.y)
            if chart.collidepoint(point) and _near_point(pos, point, 15):
                bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
                return layout.tooltip_payload(
                    "opz.tooltip.helo_title",
                    message("opz.tooltip.flight_course", course=f"{helo.course:05.1f}"),
                    message("map.tooltip.ship_air_bearing", bearing=layout.format_bearing_pair(
                        bearing, game.ship.course)),
                    message("opz.tooltip.helo_range", range=f"{math.hypot(dx, dy):.1f}"),
                    target_id="opz:helo")
        own = view.world_to_screen(game.ship.x, game.ship.y)
        if chart.collidepoint(own) and _near_point(pos, own, 14):
            return layout.tooltip_payload(
                "opz.tooltip.own_title",
                message("opz.tooltip.own_course_scope", course=f"{game.ship.course:05.1f}", range=f"{_opz_radar_range_nm(game):g}"),
                "tooltip.own_navigation",
                target_id="opz:ownship")
        return None
    if opz_regions()["sidebar"].collidepoint(pos):
        selected = game.selected_opz_track()
        if selected is not None:
            return _track_tooltip(game, selected)
        return layout.tooltip_payload(
            "opz.tooltip.controls_title",
            message("opz.tooltip.track_count_scope", count=len(tracks), range=f"{_opz_radar_range_nm(game):g}"),
            "control.opz",
            target_id="opz:controls")
    return None


@localized
def station_hit_target(game, pos):
    """Describe meaningful bridge/support-station panels and controls."""
    layout.configure_for(game)
    if game.station is Station.OPZ:
        return opz_hit_target(game, pos)
    rect = pygame.Rect(config.STATION_RECT)
    if pos is None or not rect.collidepoint(pos):
        return None
    x, width = rect.x + 14, rect.w - 28
    if game.station is Station.ELOKA:
        if game.damage.station_down("opz"):
            return layout.tooltip_payload(
                "eloka.tooltip.picture_title", "eloka.state.disabled",
                target_id="eloka:disabled")
        hovered = eloka_track_at(game, pos)
        selected = game.selected_eloka_track()
        eloka_page = int(getattr(game, "station_page", 0))
        inspected = (hovered if hovered is not None else selected
                     if selected is not None
                     and eloka_regions(page=eloka_page)["evidence"].collidepoint(pos)
                     else None)
        if inspected is not None:
            annotation = game.eloka_annotation_name(inspected.track_key)
            return layout.tooltip_payload(
                message("eloka.tooltip.track_title", track=inspected.track_key),
                message("eloka.tooltip.bearing", bearing=f"{inspected.bearing:05.1f}",
                        error=f"{inspected.bearing_uncertainty_deg:.1f}"),
                message("eloka.tooltip.fingerprint",
                        frequency=f"{inspected.frequency_hz / 1e9:.3f}",
                        prf=(f"{inspected.prf_hz:.0f}" if inspected.prf_hz is not None else "--"),
                        modulation=localize("eloka.modulation." + inspected.modulation_code)),
                message("eloka.tooltip.annotation",
                        assignment=annotation or localize("common.unknown")),
                message("control.eloka", audio=localize(
                    "ui.on" if getattr(game, "eloka_audio_enabled", True)
                    else "ui.off")),
                target_id=f"eloka:{inspected.track_key}")
        return layout.tooltip_payload(
            "eloka.tooltip.picture_title",
            message("eloka.tooltip.track_count", count=len(game.eloka_tracks())),
            "eloka.tooltip.observation_limit",
            message("control.eloka", audio=localize(
                "ui.on" if getattr(game, "eloka_audio_enabled", True)
                else "ui.off")),
            target_id="eloka:picture")
    if game.station is Station.BRIDGE:
        from src.core.commands import STATION_PAGES
        page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.BRIDGE])
        cy = _station_content_top(rect, len(STATION_PAGES[Station.BRIDGE]))
        alarm_h = 54 if len(game.asm_tracks()) + bool(game.damage.avg_flood() >= 25) > 1 else 38
        if pygame.Rect(x, cy, width, alarm_h).collidepoint(pos):
            return layout.tooltip_payload(
                "station.tooltip.threat_title", message("station.tooltip.asm_count", count=len(game.asm_tracks())),
                message("station.tooltip.mean_flooding", flooding=f"{game.damage.avg_flood():.0f}"),
                "tooltip.threat_summary",
                target_id="bridge:alarm")
        y2 = cy + alarm_h + 12
        if page == 0:
            box_h = rect.bottom - y2 - 30
            half = (width - 10) // 2
            if pygame.Rect(x, y2, half, box_h).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.course_rudder", message("station.tooltip.actual_target_course", actual=f"{game.ship.course:05.1f}", target=f"{game.ship.target_course:05.1f}"),
                    message("station.tooltip.rudder_radius", rudder=f"{game.ship.rudder_angle:+.1f}", radius=f"{game.ship.turn_radius_nm:.2f}"),
                    "control.bridge_course",
                    target_id="bridge:course")
            if pygame.Rect(x + half + 10, y2, half, box_h).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.speed_acoustics", message("station.tooltip.actual_target_speed", actual=f"{game.ship.speed:.1f}", target=f"{game.ship.target_speed:.1f}"),
                    message("station.tooltip.telegraph_noise", telegraph=game.ship.telegraph, noise=f"{game.ship.noise_level():.0%}"),
                    "control.bridge_speed",
                    target_id="bridge:speed")
        elif page == 2:
            content_h = rect.bottom - cy - 30
            area = pygame.Rect(x, y2, width, content_h - alarm_h - 12)
            if _lookout_scope_rect(area).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.lookout_scope",
                    message("bridge.line.lookout_count", count=len(game.lookout_sightings())),
                    message("bridge.line.lookout_ring", range=f"{game.lookout_range_nm:.0f}"),
                    "control.bridge_lookout",
                    target_id="bridge:lookout")
        else:
            half_box = (rect.bottom - y2 - 30 - 10) // 2
            if pygame.Rect(x, y2, width, half_box).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.mission", game.mission_name_display(),
                    game.mission_description_display(), game.mission_objective_display(),
                    message("station.tooltip.remaining", remaining=game.mission.format_remaining(game.mission_time)),
                    target_id="bridge:mission")
            if pygame.Rect(x, y2 + half_box + 10, width, half_box).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.tactical", message("station.tooltip.sonar_count", count=len(game.sonar.active_contacts())),
                    message("station.tooltip.radar_state", surface=localize("common.on" if game.surface_radar_on else "common.off"), air=localize("common.on" if game.air_radar_on else "common.off")),
                    "tooltip.ship_summary",
                    target_id="bridge:tactical")
    elif game.station is Station.ENGINE:
        from src.core.commands import STATION_PAGES
        page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.ENGINE])
        cy = _station_content_top(rect, len(STATION_PAGES[Station.ENGINE]))
        content_h = rect.bottom - cy - 34
        gap, col_w = 16, (width - 16) // 2
        if page == 0:
            if pygame.Rect(x, cy, col_w, content_h).collidepoint(pos):
                row = (int(pos[1]) - cy - 48) // 34
                action = message("station.tooltip.select_telegraph")
                displayed_orders = (("ASTERN", config.ASTERN_SPEED_KN),
                                    *config.TELEGRAPH_ORDERS)
                if 0 <= row < len(displayed_orders):
                    name, speed = displayed_orders[row]
                    action = message("station.tooltip.telegraph_order", order=name, speed=f"{speed:.1f}")
                return layout.tooltip_payload(
                    "panel.engine_order", message("station.tooltip.current_target_speed", current=game.ship.telegraph, target=f"{game.ship.target_speed:.1f}"),
                    action, "tooltip.quiet_toggle",
                    target_id="engine:telegraph")
            if pygame.Rect(x + col_w + gap, cy, col_w, content_h).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.propulsion", message("station.tooltip.shaft_speed", rpm=f"{game.ship.rpm():.0f}", speed=f"{game.ship.speed:.1f}"),
                    message("station.tooltip.noise_limit", noise=f"{game.ship.noise_level():.0%}", limit=f"{game.damage.engine_speed_cap():.1f}"),
                    message("station.tooltip.quiet_state", state=localize("station.quiet" if game.ship.quiet_mode else "station.normal")),
                    target_id="engine:status")
        else:
            if pygame.Rect(x, cy, width, content_h).collidepoint(pos):
                return layout.tooltip_payload(
                    "panel.propulsion", message("station.tooltip.shaft_speed", rpm=f"{game.ship.rpm():.0f}", speed=f"{game.ship.speed:.1f}"),
                    message("station.tooltip.noise_limit", noise=f"{game.ship.noise_level():.0%}", limit=f"{game.damage.engine_speed_cap():.1f}"),
                    message("station.tooltip.quiet_state", state=localize("station.quiet" if game.ship.quiet_mode else "station.normal")),
                    target_id="engine:systems")
    elif game.station is Station.RADIO:
        from src.core.commands import STATION_PAGES
        page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.RADIO])
        cy = _station_content_top(rect, len(STATION_PAGES[Station.RADIO]))
        content_h = rect.bottom - cy - 34
        if page == 0:
            if pygame.Rect(x, cy, width, content_h).collidepoint(pos):
                reports = game.hfdf_bearings()
                if reports:
                    report = reports[min(game.radio_sel, len(reports) - 1)]
                    return layout.tooltip_payload(
                        message("radio.tooltip.hfdf_title",
                                label=game.hfdf_display_id(report)),
                        observations.format_bearing_pair(report, game.ship),
                        message("radio.tooltip.error", error=f"{_hfdf_error_deg(report):.0f}"),
                        message("radio.hfdf.frequency",
                                frequency=(f"{report.frequency_hz / 1e3:.0f}"
                                           if report.frequency_hz else "--"),
                                mode=localize("radio.hfdf.mode." + report.propagation)
                                if report.propagation in ("GROUND", "SKY") else ""),
                        message("radio.tooltip.age", age=f"{report.age(game.sim_t):.0f}"),
                        "control.radio_tooltip",
                        target_id=f"radio:{game.hfdf_display_id(report)}")
                return layout.tooltip_payload("panel.hfdf", "tooltip.radio_none",
                                              "tooltip.log_select",
                                              target_id="radio:hfdf")
        elif pygame.Rect(x, cy, width, content_h).collidepoint(pos):
            latest = game.messages[-1] if game.messages else ("--:--", message("ui.no_traffic"))
            return layout.tooltip_payload("panel.messages",
                                          message("radio.tooltip.message", time=latest[0], text=localize(latest[1])),
                                          "tooltip.radio_received",
                                          target_id="radio:messages")
    elif game.station is Station.HELICOPTER:
        from src.core.commands import STATION_PAGES
        page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.HELICOPTER])
        helo = game.helo
        distance = math.hypot(helo.x - game.ship.x, helo.y - game.ship.y) if helo.airborne else 0.0
        regions = helicopter_regions(game, page=page)
        if page == 0:
            if regions["status"].collidepoint(pos):
                bearing = math.degrees(math.atan2(
                    helo.x - game.ship.x, -(helo.y - game.ship.y))) % 360.0
                return layout.tooltip_payload(
                    "helo.tooltip.status_title",
                    message("helo.tooltip.state_fuel", state=localize('enum.helo.' + helo.state), fuel=f"{helo.fuel_s / 60:.0f}"),
                    message("helo.tooltip.course_range", course=f"{helo.course:05.1f}", range=f"{distance:.1f}") if helo.airborne else "helo.navigation_unavailable",
                    message("map.tooltip.ship_air_bearing", bearing=layout.format_bearing_pair(
                        bearing, game.ship.course)) if helo.airborne else None,
                    "tooltip.helo_return",
                    target_id="helo:status")
            if regions["resources"].collidepoint(pos):
                return layout.tooltip_payload(
                    "helo.tooltip.resources_title", message("helo.tooltip.resources", torpedoes=helo.torps, buoys=helo.buoys_left),
                    message("helo.tooltip.active_datalink", active=len(game.buoys), state=localize("ui.active" if helo.airborne else "helo.standby")),
                    "control.helo_weapons",
                    target_id="helo:resources")
        elif page == 1:
            if regions["rules"].collidepoint(pos):
                bearing, distance_nm = game._helo_waypoint_polar()
                return layout.tooltip_payload(
                    "helo.tooltip.rules_title",
                    message("helo.tooltip.waypoint_bearing", bearing=layout.format_bearing_pair(
                        bearing, game.ship.course)),
                    message("helo.tooltip.waypoint_range", range=f"{distance_nm:.1f}"),
                    "control.helo_rules",
                    "tooltip.helo_release",
                    target_id="helo:controls")
    elif game.station is Station.DAMAGE:
        from src.core.commands import STATION_PAGES
        page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.DAMAGE])
        regions = damage_regions(game, page=page)
        items = list(game.damage.compartments.items())
        if page == 0:
            key = damage_compartment_at(game, pos, page=0)
            if key is not None:
                compartment = game.damage.compartments[key]
                teams = game.damage.teams_on(key)
                return layout.tooltip_payload(
                    _compartment_name(key, compartment.name),
                    message("damage.tooltip.condition", state=localize(STATE_LABEL[compartment.state]), flooding=f"{compartment.flood:.0f}", fire=f"{compartment.fire:.0f}"),
                    message("damage.tooltip.teams", teams=", ".join(map(str, teams)) if teams else localize("common.none")),
                    "tooltip.compartment_controls", target_id=f"damage:{key}")
            if regions["schematic"].collidepoint(pos):
                return layout.tooltip_payload(
                    "damage.schematic.title",
                    message("damage.tooltip.schematic_hint", total=f"{game.damage.total:.0f}",
                            max_total=str(len(game.damage.compartments) * 100)),
                    "tooltip.compartment_controls",
                    target_id="damage:schematic")
        elif regions["detail"].collidepoint(pos):
            selected = items[game.dmg_cursor][1]
            assignment = game.damage.teams[game.dmg_team]
            return layout.tooltip_payload(
                "tooltip.damage_actions", message("damage.tooltip.selection_team",
                    selection=_compartment_name(items[game.dmg_cursor][0], selected.name),
                    team=game.dmg_team),
                message("damage.tooltip.assignment", assignment=_compartment_name(
                    assignment, game.damage.compartments[assignment].name)
                    if assignment else localize("damage.free")),
                "tooltip.team_controls",
                target_id="damage:controls")
    return None


def _near_point(pos, point, radius):
    return ((pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2
            <= radius ** 2)


def eloka_regions(station_rect=None, page=0) -> dict[str, pygame.Rect]:
    """Shared full-station geometry for ELOKA drawing and hit testing."""
    station = pygame.Rect(station_rect or config.STATION_RECT)
    inner_x = station.x + 14
    inner_w = station.w - 28
    top = _station_content_top(station, 2)
    bottom = station.bottom - 14
    height = max(1, bottom - top)
    return {
        "picture": pygame.Rect(inner_x, top, inner_w, height) if page == 0
                   else pygame.Rect(0, 0, 0, 0),
        "evidence": pygame.Rect(inner_x, top, inner_w, height) if page == 1
                    else pygame.Rect(0, 0, 0, 0),
    }


def _eloka_visible_tracks(game) -> tuple:
    tracks = game.eloka_visible_tracks()
    selected = next((index for index, track in enumerate(tracks)
                     if track.track_key == game.eloka_selected_track_key), 0)
    start = max(0, min(selected - 5, max(0, len(tracks) - 11)))
    return tracks[start:start + 11]


def _draw_eloka_signal(surface, rect, track, now: float, channel=None) -> None:
    """Draw normalized RF spectrum and modulation samples from observations."""
    rect = pygame.Rect(rect)
    if rect.w < 80 or rect.h < 70:
        return
    pygame.draw.rect(surface, (8, 18, 16), rect)
    pygame.draw.rect(surface, config.COLOR_SONAR_RING, rect, 1)
    title_h = 24
    layout.blit_line(surface, "eloka.heading.signal_fingerprint",
                     (rect.x + 7, rect.y + 3, rect.w - 14, title_h),
                     config.COLOR_TEXT, size=16)
    graph = pygame.Rect(rect.x + 7, rect.y + title_h + 3,
                        rect.w - 14, rect.h - title_h - 9)
    split = graph.y + graph.h // 2
    for fraction in (.25, .5, .75):
        x = graph.x + round(graph.w * fraction)
        pygame.draw.line(surface, (24, 50, 44), (x, graph.y),
                         (x, graph.bottom), 1)
    pygame.draw.line(surface, (36, 72, 62), (graph.x, split),
                     (graph.right, split), 1)
    fingerprint = animated_signal_fingerprint(
        track, now,
        technique=None if channel is None else channel.technique,
        effectiveness=0.0 if channel is None else channel.effectiveness,
        samples=48, bins=40)
    status = (message("eloka.signal.memory", age=f"{track.age(now):.0f}")
              if fingerprint.memory_hold else localize("eloka.signal.live"))
    layout.blit_line(surface, status,
                     (rect.x + rect.w // 2, rect.y + 3,
                      rect.w // 2 - 7, title_h),
                     config.COLOR_TEXT_DIM if fingerprint.memory_hold
                     else config.COLOR_OK, size=14, align="right")
    def faded(color):
        scale = .35 + .65 * fingerprint.intensity
        return tuple(round(component * scale) for component in color)

    spectrum_h = max(8, split - graph.y - 4)
    spectrum_points = [(
        graph.x + round(index * (graph.w - 1)
                        / max(1, len(fingerprint.spectrum) - 1)),
        split - 3 - round(value * spectrum_h))
        for index, value in enumerate(fingerprint.spectrum)]
    if len(spectrum_points) > 1:
        pygame.draw.lines(surface, faded(config.COLOR_WARN), False,
                          spectrum_points, 2)
    wave_mid = split + max(4, (graph.bottom - split) // 2)
    wave_amp = max(3, (graph.bottom - split) // 2 - 4)
    wave_points = [(
        graph.x + round(index * (graph.w - 1)
                        / max(1, len(fingerprint.waveform) - 1)),
        wave_mid - round(value * wave_amp))
        for index, value in enumerate(fingerprint.waveform)]
    if len(wave_points) > 1:
        pygame.draw.lines(surface, faded(config.COLOR_OK), False, wave_points, 2)


def eloka_track_at(game, pos, station_rect=None):
    """Return the displayed passive intercept at a canvas position."""
    if pos is None or game.damage.station_down("opz"):
        return None
    from src.core.commands import STATION_PAGES
    page = int(getattr(game, "station_page", 0)) % len(STATION_PAGES[Station.ELOKA])
    regions = eloka_regions(station_rect, page=page)
    if not regions["picture"].collidepoint(pos):
        return None
    row_y = regions["picture"].y + layout.font(18).get_linesize() + 58
    row_height = 40
    tracks = _eloka_visible_tracks(game)
    for index, track in enumerate(tracks):
        if pygame.Rect(regions["picture"].x, row_y + index * row_height,
                       regions["picture"].w, 36).collidepoint(pos):
            return track
    return None


@localized
def draw_eloka_view(game, tr=None) -> None:
    """Render only the detached passive ESM picture and operator annotations."""
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    surface = game.screen
    pages = STATION_PAGES[Station.ELOKA]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    layout.panel(surface, _srect(), "station.eloka.title")
    draw_station_page_tabs(surface, station, pages, page, tr)
    regions = eloka_regions(page=page)
    if page == 0:
        box = layout.box(surface, regions["picture"], "eloka.panel.intercepts")
        bx, by, bw, _ = box
        if game.damage.station_down("opz"):
            layout.blit_block(surface, "eloka.state.disabled", bx, by, bw, 48,
                              color=config.COLOR_DANGER, size=18)
        else:
            row_h = max(42, layout.font(18).get_linesize() + 14)
            capacity = max(1, (box[3] - row_h - 76) // row_h)
            tracks = _eloka_visible_tracks(game)[:capacity]
            total = len(game.eloka_tracks())
            visible = len(game.eloka_visible_tracks())
            layout.blit_line(surface, message(
                "eloka.filter.summary", status=localize(
                    "eloka.filter.status." + game.eloka_status_filter.lower()),
                threat=localize(
                    "eloka.filter.threat." + game.eloka_threat_filter.lower()),
                band=localize("eloka.filter.band." + game.eloka_band_filter.lower())),
                (bx, by, bw, 22), config.COLOR_TEXT_DIM, size=15)
            by += 23
            layout.blit_line(surface, message(
                "eloka.filter.count", visible=visible, total=total),
                (bx, by, bw, 20), config.COLOR_TEXT_DIM, size=14)
            by += 23
            if not tracks:
                layout.blit_block(surface, "eloka.state.empty", bx, by, bw, 48,
                                  color=config.COLOR_TEXT_DIM, size=17)
            for track in tracks:
                selected = track.track_key == game.eloka_selected_track_key
                if selected:
                    pygame.draw.rect(surface, config.COLOR_SELECT_BG,
                                     (bx - 5, by - 2, bw + 10, row_h - 4))
                    pygame.draw.rect(surface, config.COLOR_WARN,
                                     (bx - 5, by - 2, 3, row_h - 4))
                age = track.age(game.sim_t)
                layout.blit_line(
                    surface,
                    message("eloka.line.intercept",
                            prefix=">" if selected else " ",
                            track=track.track_key,
                            bearing=f"{track.bearing:05.1f}",
                            frequency=f"{track.frequency_hz / 1e9:.3f}",
                            quality=f"{track.display_quality(game.sim_t):.0%}",
                            age=f"{age:.0f}"),
                    (bx, by, bw, row_h - 8),
                    config.COLOR_WARN if selected else
                    config.COLOR_TEXT if age < game.esm_picture.stale_s / 2
                    else config.COLOR_TEXT_DIM,
                    size=18)
                by += row_h
            footer_y = box[1] + box[3] - 26
            layout.blit_line(surface, message(
                                 "control.eloka",
                                 audio=localize("ui.on" if getattr(
                                     game, "eloka_audio_enabled", True)
                                     else "ui.off")),
                             (bx, footer_y, bw, 22),
                             config.COLOR_TEXT_DIM, size=15)
    else:
        box = layout.box(surface, regions["evidence"], "eloka.panel.evidence")
        rx, ry, rw, rh = box
        selected = (None if game.damage.station_down("opz")
                    else game.selected_eloka_track())
        if selected is None:
            layout.blit_block(surface, "eloka.state.no_selection", rx, ry, rw, 42,
                              color=config.COLOR_TEXT_DIM, size=18)
        else:
            modulation = localize("eloka.modulation." + selected.modulation_code)
            prf = f"{selected.prf_hz:.0f} Hz" if selected.prf_hz is not None else "--"
            analysis = game.eloka_display_analysis(selected)
            channel = next((item for item in game.ecm_jammer.channels
                            if item.track_key == selected.track_key), None)
            values = (
                ("eloka.field.intercept", selected.track_key),
                ("eloka.field.release", localize(
                    "eloka.release.active" if game.eloka_annotation(selected.track_key)
                    else "eloka.release.private")),
                ("eloka.field.bearing", message("eloka.value.bearing",
                                                 bearing=f"{selected.bearing:05.1f}",
                                                 error=f"{selected.bearing_uncertainty_deg:.1f}")),
                ("eloka.field.frequency", localize(message(
                    "eloka.value.frequency",
                    frequency=f"{selected.frequency_hz / 1e9:.3f}"))
                 + " / " + localize("eloka.band." + spectrum_band(
                     selected.frequency_hz).value)),
                ("eloka.field.prf", prf),
                ("eloka.field.modulation", modulation),
                ("eloka.field.quality_age", message(
                    "eloka.value.quality_age",
                    quality=f"{selected.display_quality(game.sim_t):.0%}",
                    age=f"{selected.age(game.sim_t):.1f}")),
                ("eloka.field.signal", message(
                    "eloka.value.signal", level=f"{selected.signal_db:.0f}",
                    range=(f"{estimate:.0f}" if (estimate := game.eloka_display_range(
                        selected)) is not None else "--"),
                    scan=(f"{selected.revisit_s:.1f}" if selected.revisit_s > 0.0
                          else "--"))),
                ("eloka.field.radar_type", localize(
                    "eloka.radar_type." + (analysis.radar_type.value
                    if analysis is not None and analysis.radar_type is not None
                    else "unassessed"))),
                ("eloka.field.threat", localize(
                    "eloka.threat." + (analysis.threat_level
                    if analysis is not None else "unknown"))),
                ("eloka.field.synthetic", localize(
                    "eloka.value.synthetic" if selected.synthetic_assumption
                    else "eloka.value.observed")),
                ("eloka.field.ecm", localize("eloka.value.ecm_off") if channel is None
                 else message("eloka.value.ecm_detail",
                              technique=localize("eloka.technique." + channel.technique),
                              effectiveness=f"{channel.effectiveness:.0%}",
                              power=f"{channel.power_draw:.0%}",
                              lock=localize("ui.on" if channel.is_locked_on else "ui.off"))),
                ("eloka.field.annotation",
                 game.eloka_annotation_name(selected.track_key) or localize("common.unknown")),
            )
            # Details and analysis used to be stacked into one column.  With
            # radar type/threat/ECM added that exceeded the 510 px uConsole
            # station height and painted over the footer.  Keep both columns
            # inside one explicitly clipped content area instead.
            footer_y = box[1] + box[3] - 26
            content = pygame.Rect(rx, ry, rw, max(1, footer_y - ry - 8))
            gap = 14
            details_w = max(270, int(rw * .54))
            analysis_x = rx + details_w + gap
            analysis_w = max(1, rw - details_w - gap)
            detail_step = max(27, layout.font(16).get_linesize() + 5)
            with layout.clip_to(surface, content):
                detail_y = ry
                for label, value in values:
                    if detail_y + detail_step > content.bottom:
                        break
                    layout.status_line(surface, rx, detail_y, details_w,
                                       label, value, label_w=138, size=16)
                    detail_y += detail_step

                analysis_y = ry
                signal_h = min(128, max(96, content.h // 3))
                _draw_eloka_signal(
                    surface, (analysis_x, analysis_y, analysis_w, signal_h),
                    selected, game.sim_t, channel)
                analysis_y += signal_h + 10
                assist = game.operator_assist()
                layout.blit_line(surface, "eloka.heading.candidates" if assist
                                 else "eloka.heading.library",
                                 (analysis_x, analysis_y, analysis_w, 24),
                                 config.COLOR_TEXT, size=17)
                analysis_y += 28
                shown = game.eloka_display_candidates(selected)
                for candidate in shown[:3]:
                    name = (game.eloka_emitter_name(candidate.emitter_key)
                            or candidate.emitter_key)
                    layout.blit_line(surface, message(
                        "eloka.line.candidate", emitter=name,
                        score=f"{candidate.score:.0%}") if candidate.score is not None
                        else raw_text(name),
                        (analysis_x, analysis_y, analysis_w, 25),
                        config.COLOR_TEXT_DIM, size=16)
                    analysis_y += 28
                if not assist:
                    layout.blit_line(surface, message(
                        "eloka.library_hint", count=len(shown)),
                        (analysis_x, analysis_y, analysis_w, 25),
                        config.COLOR_TEXT_DIM, size=16)
                    analysis_y += 28
                analysis_y += 8
                layout.blit_line(surface, "eloka.heading.correlations",
                                 (analysis_x, analysis_y, analysis_w, 24),
                                 config.COLOR_TEXT, size=17)
                analysis_y += 28
                correlations = game.eloka_correlations(selected)
                if not correlations:
                    layout.blit_line(surface, "eloka.correlation.none",
                                     (analysis_x, analysis_y, analysis_w, 25),
                                     config.COLOR_TEXT_DIM, size=16)
                else:
                    for correlation in correlations[:2]:
                        layout.blit_line(surface, message(
                            "eloka.line.correlation", source=correlation.source,
                            track=correlation.track_id,
                            score=f"{correlation.score:.0%}",
                            ambiguity=localize("eloka.correlation.ambiguous")
                            if correlation.ambiguous else ""),
                            (analysis_x, analysis_y, analysis_w, 25),
                            config.COLOR_OK, size=16)
                        analysis_y += 28
        footer_y = box[1] + box[3] - 26
        layout.blit_line(surface, message(
                             "control.eloka",
                             audio=localize("ui.on" if getattr(
                                 game, "eloka_audio_enabled", True)
                                 else "ui.off")),
                         (rx, footer_y, rw, 22),
                         config.COLOR_TEXT_DIM, size=15)


def opz_regions(station_rect=None) -> dict[str, pygame.Rect]:
    """Single OPZ geometry source for drawing and pointer ownership.

    Both pages share the same rectangular chart; only the sidebar differs.
    """
    station = pygame.Rect(station_rect or config.STATION_RECT)
    scope_w = int(station.w * .75)
    top = _station_content_top(station, 2)
    map_rect = pygame.Rect(station.x + 8, top,
                           scope_w - 16, station.bottom - top - 42)
    chart = map_rect.copy()
    sidebar = pygame.Rect(station.x + scope_w, top,
                          station.right - station.x - scope_w,
                          map_rect.h)
    button_y = sidebar.bottom - 80
    button_w = max(1, (sidebar.w - 24) // 2)
    return {"map": map_rect, "chart": chart, "sidebar": sidebar,
            "classify": pygame.Rect(sidebar.x + 8, button_y, button_w, 28),
            "affiliate": pygame.Rect(sidebar.x + 16 + button_w, button_y,
                                     button_w, 28),
            "mark": pygame.Rect(sidebar.x + 8, button_y + 34, button_w, 28),
            "fusion": pygame.Rect(sidebar.x + 16 + button_w, button_y + 34,
                                  button_w, 28)}


def opz_ppi_rect(station_rect=None) -> pygame.Rect:
    return opz_regions(station_rect)["chart"]


def _opz_view(game, chart):
    """Return the OPZ camera configured for this frame's chart geometry."""
    source = getattr(game, "opz_map_view", None)
    if source is None:
        from src.ui.viewport import Viewport
        world_size = float(getattr(getattr(game, "world", None), "size_nm",
                                   config.WORLD_SIZE_NM))
        source = Viewport(world_size, 1.0, 100.0)
        source.cx, source.cy = game.ship.x, game.ship.y
        source.scale = min(chart.w, chart.h) / (
            2.0 * config.OPZ_MAP_DEFAULT_RADIUS_NM)
    view = copy.copy(source)
    view.set_rect(tuple(chart))
    view.min_scale = min(chart.w, chart.h) / float(view.world_size)
    view.max_scale = max(view.min_scale, min(chart.w, chart.h) / (
        2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM))
    view.scale = config.clamp(view.scale, view.min_scale, view.max_scale)
    view.clamp_center()
    return view


def _opz_bearing_ray(game, track, chart, view):
    """Return a public bearing ray clipped to the rectangular chart."""
    # Compatibility for focused geometry callers from the former PPI API.
    if isinstance(view, (int, float)) and not isinstance(view, bool):
        from src.ui.viewport import Viewport
        radius_nm = max(float(view), 1e-6)
        legacy = Viewport(float(getattr(getattr(game, "world", None),
                                        "size_nm", config.WORLD_SIZE_NM)),
                          1e-6, 1e6)
        legacy.set_rect(tuple(chart))
        legacy.cx, legacy.cy = game.ship.x, game.ship.y
        legacy.scale = min(chart.w, chart.h) / (2.0 * radius_nm)
        view = legacy
    if (getattr(track, "observer_x", None) is not None
            and getattr(track, "observer_y", None) is not None):
        origin = view.world_to_screen(track.observer_x, track.observer_y)
    else:
        origin = view.world_to_screen(game.ship.x, game.ship.y)
    angle = math.radians(_observation_bearing(track))
    dx, dy = math.sin(angle), -math.cos(angle)
    near, far = 0.0, float("inf")
    for value, direction, low, high in (
            (origin[0], dx, chart.left, chart.right - 1),
            (origin[1], dy, chart.top, chart.bottom - 1)):
        if abs(direction) < 1e-12:
            if not low <= value <= high:
                return None
            continue
        first, second = (low - value) / direction, (high - value) / direction
        near, far = max(near, min(first, second)), min(far, max(first, second))
        if near > far:
            return None
    if far < 0.0:
        return None
    return ((origin[0] + dx * near, origin[1] + dy * near),
            (origin[0] + dx * far, origin[1] + dy * far))


def _opz_track_point(game, track, chart, view):
    observed_x, observed_y = _observation_position(track)
    if observed_x is not None and observed_y is not None:
        point = view.world_to_screen(observed_x, observed_y)
        return point if chart.collidepoint(point) else None
    ray = _opz_bearing_ray(game, track, chart, view)
    return ray[1] if ray is not None else None


def opz_action_at(game, pos, station_rect=None):
    """Return a closed native OPZ action from the same geometry used to draw."""
    if pos is None:
        return None
    regions = opz_regions(station_rect)
    for action in ("classify", "affiliate", "mark", "fusion"):
        if regions[action].collidepoint(pos):
            return action
    chart = regions["chart"]
    if not chart.collidepoint(pos):
        return None
    view = _opz_view(game, chart)
    for track in reversed(game.opz_tracks()):
        point = _opz_track_point(game, track, chart, view)
        if point is not None and _near_point(pos, point, 15):
            return ("select", track.observation_id)
    return None


def _opz_radar_range_nm(game) -> float:
    value = getattr(game, "radar_range_nm", None)
    if value is None:
        value = game.opz_range_nm
    return float(value)


def _radar_sweep_age(game, bearing: float) -> float:
    passed = (game.radar_sweep_bearing() - bearing) % 360.0
    return passed / config.RADAR_SWEEP_DEG_PER_S


def _radar_glow(game, bearing: float) -> float:
    age = _radar_sweep_age(game, bearing)
    if age > config.RADAR_AFTERGLOW_S:
        return 0.0
    return max(0.08, 1.0 - age / config.RADAR_AFTERGLOW_S)


def _scale_color(color: tuple, factor: float) -> tuple:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _draw_radar_clutter(game, surface, center, radius: int) -> None:
    severity = game.radar_weather_severity()
    if severity <= 0.0:
        return
    cx, cy = center
    turn = int(game._t * config.RADAR_SWEEP_DEG_PER_S // 360.0)
    rng = random.Random(game.seed * 1009 + turn * 9176)
    count = int(45 + 95 * severity)
    for _ in range(count):
        bearing = rng.uniform(0.0, 360.0)
        glow = _radar_glow(game, bearing)
        if glow <= 0.0:
            continue
        # Seegang: Nahbereichs-Clutter; Wetterzellen: Flaechenstoerung im Luftbild.
        if game.surface_radar_on and (not game.air_radar_on or rng.random() < .65):
            distance = radius * rng.random() ** 1.8
            base = (70, 145, 95)
        else:
            distance = radius * math.sqrt(rng.random())
            base = (90, 115, 105)
        rad = math.radians(bearing)
        px = int(cx + distance * math.sin(rad))
        py = int(cy - distance * math.cos(rad))
        color = _scale_color(base, (0.25 + 0.55 * severity) * glow)
        pygame.draw.circle(surface, color, (px, py), 1 if rng.random() < .85 else 2)


def _bounds_intersect_circle(bounds, cx: float, cy: float, radius: float) -> bool:
    left, top, right, bottom = bounds
    nearest_x = min(max(cx, left), right)
    nearest_y = min(max(cy, top), bottom)
    return (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 <= radius ** 2


def _contour_segments_in_circle(coast, cx: float, cy: float,
                                radius_nm: float) -> list:
    """Clip visible coastline edges after a cheap landmass-bounds cull."""
    if not hasattr(coast, "landmasses") or "contour_segments_in_circle" in vars(coast):
        return coast.contour_segments_in_circle(cx, cy, radius_nm)
    radius = max(0.0, float(radius_nm))
    if radius <= 0.0:
        return []
    radius2 = radius * radius
    out = []
    for landmass in coast.landmasses:
        if not _bounds_intersect_circle(landmass.bounds, cx, cy, radius):
            continue
        points = landmass.points
        if len(points) < 2:
            continue
        for index, first in enumerate(points):
            second = points[(index + 1) % len(points)]
            x1, y1 = float(first[0]), float(first[1])
            x2, y2 = float(second[0]), float(second[1])
            dx, dy = x2 - x1, y2 - y1
            a = dx * dx + dy * dy
            if a <= 1e-12:
                continue
            ox, oy = x1 - cx, y1 - cy
            b = 2.0 * (ox * dx + oy * dy)
            c = ox * ox + oy * oy - radius2
            disc = b * b - 4.0 * a * c
            cuts = [0.0, 1.0]
            if disc >= 0.0:
                root = math.sqrt(max(0.0, disc))
                for value in ((-b - root) / (2.0 * a),
                              (-b + root) / (2.0 * a)):
                    if 0.0 < value < 1.0:
                        cuts.append(value)
            cuts = sorted(set(cuts))
            for lo, hi in zip(cuts, cuts[1:]):
                middle = (lo + hi) * 0.5
                mx, my = x1 + dx * middle, y1 + dy * middle
                if (mx - cx) ** 2 + (my - cy) ** 2 > radius2 + 1e-9:
                    continue
                start = (x1 + dx * lo, y1 + dy * lo)
                end = (x1 + dx * hi, y1 + dy * hi)
                if math.hypot(end[0] - start[0], end[1] - start[1]) > 1e-9:
                    out.append((start, end))
    return out


def _opz_basemap_surface(game, map_rect: pygame.Rect, view) -> pygame.Surface:
    """Build a bounded cached chart layer beneath the live OPZ radar picture."""
    world = game.world
    coast = getattr(world, "coast", None)
    world_size_nm = float(getattr(world, "size_nm", config.WORLD_SIZE_NM))
    bucket_x = round(view.cx * 10.0) / 10.0
    bucket_y = round(view.cy * 10.0) / 10.0
    scale = view.scale
    key = (world, coast, map_rect.size, round(scale, 6), bucket_x, bucket_y,
           config.COLOR_GEO_BG, config.COLOR_GEO_GRID,
           config.COLOR_LAND, config.COLOR_LAND_EDGE,
           config.COLOR_SHALLOW, config.COLOR_DEEP)
    cached = getattr(_opz_basemap_surface, "_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]

    layer = pygame.Surface(map_rect.size)
    layer.fill(config.COLOR_GEO_BG)
    center_x = map_rect.w / 2.0
    center_y = map_rect.h / 2.0

    depth_query = getattr(world, "depth_m", None)
    if (coast is not None and getattr(coast, "has_bathymetry", False)
            and callable(depth_query)):
        cell_px = 20
        for py in range(0, map_rect.h, cell_px):
            for px in range(0, map_rect.w, cell_px):
                wx = bucket_x + (px + cell_px * .5 - center_x) / scale
                wy = bucket_y + (py + cell_px * .5 - center_y) / scale
                if not (0.0 <= wx <= world_size_nm and 0.0 <= wy <= world_size_nm):
                    continue
                depth = depth_query(wx, wy)
                if depth <= 0.0:
                    continue
                deep = max(0.0, min(1.0, depth / 900.0))
                color = tuple(int(shallow + (deep_color - shallow) * deep)
                              for shallow, deep_color in zip(
                                  config.COLOR_SHALLOW, config.COLOR_DEEP))
                pygame.draw.rect(layer, color, (px, py, cell_px + 1, cell_px + 1))

    visible_radius = min(map_rect.w, map_rect.h) / (2.0 * scale)
    step = 5 if visible_radius <= 20 else (10 if visible_radius <= 40 else
                                          (20 if visible_radius <= 80 else 40))
    half_w_nm = map_rect.w / (2.0 * scale)
    half_h_nm = map_rect.h / (2.0 * scale)
    first_x = math.ceil((bucket_x - half_w_nm) / step) * step
    first_y = math.ceil((bucket_y - half_h_nm) / step) * step
    value = first_x
    while value <= bucket_x + half_w_nm:
        px = int(center_x + (value - bucket_x) * scale)
        pygame.draw.line(layer, config.COLOR_GEO_GRID,
                         (px, 0), (px, map_rect.h), 1)
        value += step
    value = first_y
    while value <= bucket_y + half_h_nm:
        py = int(center_y + (value - bucket_y) * scale)
        pygame.draw.line(layer, config.COLOR_GEO_GRID,
                         (0, py), (map_rect.w, py), 1)
        value += step

    if coast is not None and hasattr(coast, "landmasses"):
        visible_bounds = (bucket_x - half_w_nm, bucket_y - half_h_nm,
                          bucket_x + half_w_nm, bucket_y + half_h_nm)
        for landmass in coast.landmasses[:1024]:
            left, top, right, bottom = landmass.bounds
            if (right < visible_bounds[0] or left > visible_bounds[2]
                    or bottom < visible_bounds[1] or top > visible_bounds[3]):
                continue
            polygon = [
                (int(center_x + (x - bucket_x) * scale),
                 int(center_y + (y - bucket_y) * scale))
                for x, y in landmass.points[:20000]
            ]
            if len(polygon) >= 3:
                pygame.draw.polygon(layer, config.COLOR_LAND, polygon)
                pygame.draw.polygon(layer, config.COLOR_LAND_EDGE, polygon, 2)

        for base in getattr(coast, "airbases", ())[:128]:
            bx, by = base.get("x"), base.get("y")
            if not isinstance(bx, (int, float)) or not isinstance(by, (int, float)):
                continue
            px = int(center_x + (bx - bucket_x) * scale)
            py = int(center_y + (by - bucket_y) * scale)
            if 0 <= px < map_rect.w and 0 <= py < map_rect.h:
                color = (config.COLOR_DANGER
                         if base.get("gameplay_role") == "hostile"
                         else config.COLOR_FLIGHT)
                pygame.draw.rect(layer, color, (px - 3, py - 3, 7, 7), 1)

    hazards = getattr(world, "charted_hazards", None)
    if hazards is not None:
        chart_symbols.draw_hazards(
            layer, hazards(),
            lambda x, y: (center_x + (x - bucket_x) * scale, center_y + (y - bucket_y) * scale),
            (0, 0, map_rect.w, map_rect.h), scale)

    world_left = int(center_x - bucket_x * scale)
    world_top = int(center_y - bucket_y * scale)
    world_size_px = int(world_size_nm * scale)
    pygame.draw.rect(layer, config.COLOR_LAND_EDGE,
                     (world_left, world_top, world_size_px, world_size_px), 1)
    _opz_basemap_surface._cache = (key, layer)
    return layer


@localized
def draw_opz_view(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.OPZ]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station, pages, page, tr)
    regions = opz_regions()
    scope_w = regions["sidebar"].x - station.x
    map_rect = regions["map"]
    chart = regions["chart"]
    view = _opz_view(game, chart)
    max_nm = _opz_radar_range_nm(game)
    s.blit(_opz_basemap_surface(game, map_rect, view), map_rect)
    pygame.draw.rect(s, config.COLOR_LAND_EDGE, map_rect, 1)
    previous_clip = s.get_clip()
    s.set_clip(chart)
    station_live = not game.damage.station_down("opz")
    radar_live = station_live and (game.surface_radar_on or game.air_radar_on)
    px_per_nm = view.scale
    own_x, own_y = view.world_to_screen(game.ship.x, game.ship.y)
    radar_radius = max_nm * px_per_nm

    coast = getattr(game.world, "coast", None)
    coast_segments = (_contour_segments_in_circle(
        coast, game.ship.x, game.ship.y, max_nm) if coast is not None else [])
    with layout.clip_to(s, chart):
        # Radar presentation remains ship-centred and independent of the camera.
        for ring_index in range(1, 5):
            rr = radar_radius * ring_index / 4.0
            pygame.draw.circle(s, config.COLOR_SONAR_RING,
                               (int(own_x), int(own_y)), max(1, int(rr)), 1)
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (int(own_x - radar_radius), int(own_y)),
                         (int(own_x + radar_radius), int(own_y)), 1)
        pygame.draw.line(s, config.COLOR_SONAR_RING,
                         (int(own_x), int(own_y - radar_radius)),
                         (int(own_x), int(own_y + radar_radius)), 1)
        # Range labels at the top of each ring, beside the north axis.
        for ring_index in range(1, 5):
            rr = radar_radius * ring_index / 4.0
            layout.blit_line(
                s, message("map.tooltip.range_value",
                           range=f"{max_nm * ring_index / 4.0:g}"),
                (int(own_x) + 4, int(own_y - rr) + 1, 80, 18),
                config.COLOR_TEXT_DIM, size=layout.MIN_OPERATIONAL_FONT)

        if station_live and game.surface_radar_on:
            coast_range = min(max_nm, game.radar_effective_range("surface"))
            for first, second in coast_segments:
                if max(math.hypot(first[0] - game.ship.x, first[1] - game.ship.y),
                       math.hypot(second[0] - game.ship.x, second[1] - game.ship.y)) > coast_range:
                    continue
                mx = (first[0] + second[0]) * .5
                my = (first[1] + second[1]) * .5
                bearing = math.degrees(math.atan2(mx - game.ship.x,
                                                  -(my - game.ship.y))) % 360.0
                glow = _radar_glow(game, bearing)
                if glow > 0.0:
                    pygame.draw.line(
                        s, _scale_color((75, 180, 105), .25 + .75 * glow),
                        view.world_to_screen(*first), view.world_to_screen(*second), 2)

        if radar_live:
            _draw_radar_clutter(game, s, (own_x, own_y), int(radar_radius))
            ang = math.radians(game.radar_sweep_bearing())
            pygame.draw.line(s, (70, 190, 130), (own_x, own_y),
                             (own_x + radar_radius * math.sin(ang),
                              own_y - radar_radius * math.cos(ang)), 2)
        nato_symbols.draw_symbol(s, (own_x, own_y), "FRIEND", "SURFACE", 18)
        nato_symbols.draw_motion_vector(
            s, (own_x, own_y), game.ship.course, game.ship.speed,
            px_per_nm, config.COLOR_TEXT, max_px=min(chart.size) * .3)

    # Own-force aircraft is datalink truth, not a radar/sensor track.
    helo = getattr(game, "helo", None)
    if helo is not None and helo.airborne:
        hx, hy = view.world_to_screen(helo.x, helo.y)
        if chart.collidepoint(hx, hy):
            hcol = nato_symbols.draw_symbol(s, (hx, hy), "FRIEND", "AIR", 17)
            nato_symbols.draw_motion_vector(s, (hx, hy), helo.course, helo.SPEED_KN,
                                            px_per_nm, hcol, max_px=min(chart.size) * .3)
            layout.blit_line(s, "HSP-5 DL",
                             (int(hx) + 13, int(hy) - 10, 94, 19), hcol, size=12)
    # Own weapons are commanded own assets (wire/datalink), not sensor tracks:
    # torpedoes from ship, helicopter or ASROC payload, ASROC and ESSM flights.
    own_weapons = (
        [(item, "UNDERWATER_WEAPON", f"T{item.idx}")
         for item in getattr(game, "torpedoes", ())]
        + [(item, "MISSILE", f"ASROC {item.seq}")
           for item in getattr(game, "asrocs", ())]
        + [(item, "MISSILE", "ESSM") for item in getattr(game, "essms", ())])
    for item, domain, label in own_weapons:
        wx, wy = view.world_to_screen(item.x, item.y)
        if not chart.collidepoint(wx, wy):
            continue
        wcol = nato_symbols.draw_symbol(s, (wx, wy), "FRIEND", domain, 12)
        course = getattr(item, "course", None)
        if course is not None:
            rad = math.radians(course)
            pygame.draw.line(s, wcol, (int(wx), int(wy)),
                             (int(wx + 12 * math.sin(rad)), int(wy - 12 * math.cos(rad))), 1)
        layout.blit_line(s, raw_text(label),
                         (int(wx) + 10, int(wy) - 9, 80, 17), wcol, size=12)
    cic_tracks = (game.opz_tracks() if hasattr(game, "opz_tracks")
                  else game.radar_tracks())
    selected_id = game.opz_selected_track_id
    plotted = {}
    for track in (t for t in cic_tracks if _observation_position(t)[0] is None):
        ray = _opz_bearing_ray(game, track, chart, view)
        if ray is None:
            continue
        start, (sx, sy) = ray
        affiliation = game.opz_affiliation(track["track_id"])
        domain = nato_symbols.domain_for_kind(track["kind"])
        col = nato_symbols.AFFILIATION_COLORS[affiliation]
        pygame.draw.line(s, col, start, (sx, sy), 1)
        plotted[track.track_id] = (sx, sy)
        nato_symbols.draw_symbol(s, (sx, sy), affiliation, domain, 14,
                                 track["track_id"] == selected_id)
        nato_symbols.draw_motion_vector(s, (sx, sy), track.course, track.speed_kn,
                                        px_per_nm, col, max_px=min(chart.size) * .3)
        layout.blit_line(s, track["source"],
                         (int(sx) - 22, int(sy) - 21, 66, 18), col, size=12)

    # Gemeinsames Lagebild: Oberflaeche, Luft und Flugkoerper im selben Scope.
    for track in (t for t in cic_tracks if _observation_position(t)[0] is not None):
        observed_x, observed_y = _observation_position(track)
        bx, by = view.world_to_screen(observed_x, observed_y)
        if not chart.collidepoint(bx, by):
            continue
        plotted[track.track_id] = (bx, by)
        if track["source"].startswith("RADAR"):
            glow = _radar_glow(game, observations.bearing(track, game.ship))
            if glow > 0.0:
                pygame.draw.circle(s, _scale_color((120, 255, 150), glow),
                                   (int(bx), int(by)), 3)
        affiliation = game.opz_affiliation(track["track_id"])
        domain = nato_symbols.domain_for_kind(track["kind"])
        col = nato_symbols.draw_symbol(
            s, (bx, by), affiliation, domain, 16,
            track["track_id"] == selected_id)
        nato_symbols.draw_motion_vector(s, (bx, by), track.course, track.speed_kn,
                                        px_per_nm, col, max_px=min(chart.size) * .3)
        layout.blit_line(s, track["label"],
                          (int(bx) + 12, int(by) - 10, 118, 19), col, size=12)

    for fusion in (track for track in cic_tracks if track.source == "FUSION"):
        if fusion.track_id not in plotted:
            continue
        for member in fusion.members:
            if member in plotted:
                pygame.draw.line(s, config.COLOR_WARN, plotted[fusion.track_id],
                                 plotted[member], 1)

    # Die ESSM-Auswahl bleibt bewusst von der allgemeinen CIC-Auswahl getrennt.
    asm_tracks = game.asm_tracks()
    for i, track in enumerate(asm_tracks):
        observed_x, observed_y = _observation_position(track)
        if observed_x is not None and observed_y is not None:
            dx, dy = observed_x - game.ship.x, observed_y - game.ship.y
            dist = math.hypot(dx, dy)
            brg = math.degrees(math.atan2(dx, -dy)) % 360.0
        elif observations.range_nm(track, game.ship) is not None:
            dist = observations.range_nm(track, game.ship)
            brg = observations.bearing(track, game.ship)
        else:
            continue
        rad = math.radians(brg)
        bx, by = view.world_to_screen(
            game.ship.x + dist * math.sin(rad),
            game.ship.y - dist * math.cos(rad))
        if not chart.collidepoint(bx, by):
            continue
        if i == min(game.asm_sel, len(asm_tracks) - 1):
            pygame.draw.circle(s, config.COLOR_DANGER, (int(bx), int(by)), 16, 1)
    draw_plot(s, game, view, chart)

    s.set_clip(previous_clip)
    side_top = regions["sidebar"].y
    side_h = regions["sidebar"].h
    sb_box = layout.box(s, (regions["sidebar"].x + 4, side_top,
                            regions["sidebar"].w - 8, side_h - 8),
                        "station.opz.title")
    x = sb_box[0]
    py = sb_box[1]
    w = sb_box[2]

    if game.damage.station_down("opz"):
        radar_state = localize("common.disabled")
    else:
        radar_state = localize(message("opz.line.radar_state",
            surface=localize("common.on" if game.surface_radar_on else "common.off"),
            air=localize("common.on" if game.air_radar_on else "common.off")))

    if page == 0:
        layout.status_line(s, x, py, w, "RADAR", radar_state,
                           label_w=70, size=16)
        py += 28
        severity = game.radar_weather_severity()
        weather_key = ("opz.weather.clear" if severity <= 0.0 else
                       ("opz.weather.clutter" if severity < 1.0 else "opz.weather.heavy"))
        weather_color = config.COLOR_TEXT_DIM if severity <= 0.0 else config.COLOR_WARN
        layout.status_line(s, x, py, w, "ui.scope",
                            message("opz.line.scope", range=f"{max_nm:.0f}", sea=game.world.sea_state,
                                    weather=localize(weather_key)),
                            label_w=66, size=14, color=weather_color)
        py += 26
        surface_count = sum(1 for t in cic_tracks
                            if t["kind"] in ("SURFACE", "AIS"))
        hoj_count = sum(1 for t in cic_tracks if t["source"] == "HOJ")
        layout.status_line(s, x, py, w, "ui.picture",
                            message("opz.line.picture", surface=surface_count,
                                    hoj=hoj_count),
                            label_w=80, size=15)
        py += 26
        layout.status_line(s, x, py, w, "VLS:",
                            message("opz.line.vls_chaff", count=game.vls_cells,
                                    total=getattr(game, "vls_loadout_total",
                                                  game.vls_cells),
                                    chaff=f"{game.chaff_cd:.0f}"),
                            label_w=80, size=15)
        py += 26
        layout.status_line(s, x, py, w, "CIWS:",
                            localize("opz.ciws.authorized" if game.ciws_authorized
                                     else "opz.ciws.withheld"),
                            label_w=80, size=15,
                            color=(config.COLOR_OK if game.ciws_authorized
                                   else config.COLOR_WARN))
        py += 30
        pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
        py += 8
        contact_filter = getattr(game, "opz_contact_filter", "ALL")
        layout.blit_block(s, message(
            "opz.tracks_heading_filtered",
            filter=display_value("contact_filter", contact_filter)),
            x, py, w, 22, color=config.COLOR_TEXT, size=16)
        py += 24
        content_bottom = regions["classify"].top - 7
        max_rows = max(0, (content_bottom - py) // 28)
        register_tracks = (game.filtered_opz_tracks()
                           if hasattr(game, "filtered_opz_tracks")
                           else cic_tracks)
        selected_index = next((i for i, track in enumerate(register_tracks)
                               if track["track_id"] == selected_id), 0)
        start = max(0, min(selected_index - max_rows // 2,
                           max(0, len(register_tracks) - max_rows)))
        for track in register_tracks[start:start + max_rows]:
            affiliation = game.opz_affiliation(track["track_id"])
            domain = nato_symbols.domain_for_kind(track["kind"])
            color = nato_symbols.AFFILIATION_COLORS[affiliation]
            prefix = ">" if track["track_id"] == selected_id else " "
            if track["track_id"] in game.opz_fusion.marked:
                prefix = "*"
            displayed_range = observations.range_nm(track, game.ship)
            distance = f"{displayed_range:4.1f}" if displayed_range is not None else " -- "
            pygame.draw.rect(s, OPZ_DOMAIN_COLORS[domain], (x, py + 5, 3, 14))
            text = message("opz.line.track", prefix=prefix, track=f"{track['label']:<7}",
                           affiliation=structured_message(
                               "affil.code." + affiliation.lower()),
                           domain=structured_message(OPZ_DOMAIN_CODES[domain]),
                            bearing=observations.format_bearing(track, game.ship), distance=distance)
            layout.blit_line(s, text, (x + 6, py, w - 6, 24), color, size=15)
            py += 28
    else:
        selected = game.selected_opz_track()
        if selected is None:
            layout.blit_block(s, "panel.no_track", x, py, w, 22,
                              color=config.COLOR_TEXT_DIM, size=16)
            py += 26
        else:
            affiliation = game.opz_affiliation(selected.track_id)
            domain = nato_symbols.domain_for_kind(selected.kind)
            color = nato_symbols.AFFILIATION_COLORS[affiliation]
            nato_symbols.draw_symbol(s, (x + 10, py + 10), affiliation, domain, 16)
            layout.blit_line(s, selected.label,
                             (x + 28, py, w - 28, 22), color, size=18)
            py += 26
            ledger = [
                message("opz.line.source", source=selected.source),
                message("opz.line.bearing", bearing=observations.format_bearing(selected, game.ship)),
                (message("opz.line.range_available", range=f"{observations.range_nm(selected, game.ship):.1f}")
                 if observations.range_nm(selected, game.ship) is not None else "opz.line.range_unavailable"),
                (message("opz.line.course_available", course=f"{selected.course:03.0f}")
                 if selected.course is not None else "opz.line.course_unavailable"),
                ((message("opz.line.altitude_available",
                          altitude=f"{selected.altitude_m:.0f}")
                  if getattr(selected, "altitude_m", None) is not None
                  else "opz.line.altitude_unavailable")
                 if domain == "AIR" else
                 (message("opz.line.depth_available", depth=f"{selected.depth_m:.0f}")
                  if selected.depth_m is not None else "opz.line.depth_unavailable")),
                (message("opz.line.speed_available", speed=f"{selected.speed_kn:.1f}")
                 if selected.speed_kn is not None else "opz.line.speed_unavailable"),
                (message("opz.line.ages_quality", observation_age=f"{selected.age(game.sim_t):.0f}",
                         fix_age=f"{observations.position_age(selected, game.sim_t):.0f}",
                         quality=f"{selected.display_quality(game.sim_t, game.air_picture.stale_s):.0%}")
                 if observations.position_age(selected, game.sim_t) is not None
                 else message("opz.line.age_quality", age=f"{selected.age(game.sim_t):.0f}",
                              quality=f"{selected.display_quality(game.sim_t, game.air_picture.stale_s):.0%}")),
                message("opz.line.assignment", affiliation=display_value("affiliation", affiliation)),
                message("opz.line.classification", classification=display_value(
                    "classification", getattr(selected, "classification", None))),
            ]
            for line in ledger:
                layout.blit_line(s, line, (x, py, w, 24), config.COLOR_TEXT_DIM, size=15)
                py += 26
            py += 6
            pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
            py += 8
        layout.blit_block(s, message("opz.line.asm_defense", ammo=game.ciws_ammo,
                                      aa_ammo=getattr(game, "aa_ammo", 0)),
                           x, py, w, 22,
                           color=(config.COLOR_DANGER
                                  if asm_tracks or getattr(game, "raiders", None)
                                  else config.COLOR_TEXT_DIM),
                           size=16)
        py += 26
        content_bottom = regions["classify"].top - 7
        if asm_tracks:
            n = len(asm_tracks)
            visible_rows = max(0, min(3, (content_bottom - py) // 26))
            start = max(0, min(game.asm_sel - 1, n - visible_rows))
            for i, track in enumerate(asm_tracks[start:start + visible_rows], start):
                sel = i == min(game.asm_sel, n - 1)
                col = config.COLOR_TEXT if sel else config.COLOR_TEXT_DIM
                displayed_range = observations.range_nm(track, game.ship)
                distance = (f"{displayed_range:5.1f}NM" if displayed_range is not None
                            else "  --.-NM")
                jam = "JAMMER" if track.jamming else track.source
                tti = (displayed_range / max(.001, config.kn_to_nm_per_s(
                    getattr(game, "asm_speed_kn", 1.0)))
                    if displayed_range is not None else None)
                tti_text = f" TTI {tti:.0f}s" if tti is not None else ""
                layout.blit_block(
                    s, message("opz.line.asm_track", prefix='>' if sel else ' ',
                                label=track.label, bearing=observations.format_bearing(track, game.ship),
                               distance=distance, source=jam,
                               quality=f"{track.display_quality(game.sim_t, game.air_picture.stale_s):.0%}",
                               tti=tti_text),
                      x, py, w, 24, color=col, size=15)
                py += 26

    for action, key in (("classify", "opz.button.classify"),
                        ("affiliate", "opz.button.affiliation"),
                        ("mark", "opz.button.mark"),
                        ("fusion", "opz.button.fusion")):
        rect = regions[action]
        pygame.draw.rect(s, config.COLOR_GRID, rect, 1)
        layout.blit_line(s, key, rect, config.COLOR_TEXT_DIM, size=14,
                         align="center")

    scales = " ".join(
        f"[{scale:g}]" if scale == max_nm else f"{scale:g}"
        for scale in config.RADAR_RANGE_SCALES_NM)
    footer_rect = pygame.Rect(station.x + 8, station.bottom - 23, scope_w - 16, 19)
    pygame.draw.rect(s, (8, 18, 13), footer_rect)
    layout.command_segment(s, footer_rect, "PGUP/DN", "opz.footer.range", "",
                           f"{max_nm:g} NM  {scales}", size=14)


# --- Funkraum (M13) --------------------------------------------------------

@localized
def draw_radio_view(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.RADIO]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.radio.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    x = r[0] + 14
    w = r[2] - 28
    box_h = station_rect.bottom - cy - 34

    if page == 0:
        # Current intercepts left; the operator's logged bearings and the
        # resulting cross-fixes right (same data as the Remote Crew radio).
        split = int(w * .56)
        left = layout.box(s, (x, cy, split - 6, box_h), "panel.hfdf")
        log_box = layout.box(s, (x + split + 6, cy, w - split - 6, box_h), "panel.hfdf_log")
        gx, gy, gw, gh = log_box
        logged = list(game.hfdf_log)[-6:]
        if not logged:
            layout.blit_line(s, "radio.log_empty", (gx, gy, gw, 24),
                             config.COLOR_TEXT_DIM, size=16)
        for row in reversed(logged):
            layout.blit_line(s, message(
                "radio.line.logged", label=raw_text(row["label"]),
                bearing=f"{row['bearing'] % 360:05.1f}",
                x=f"{row['observer_x']:.1f}", y=f"{row['observer_y']:.1f}",
                age=f"{max(0.0, game.sim_t - row['t']):.0f}"),
                (gx, gy, gw, 24), config.COLOR_TEXT, size=16)
            gy += 26
        gy += 8
        for fix in list(game.hfdf_fixes.values())[-4:]:
            if gy + 24 > log_box[1] + gh:
                break
            layout.blit_line(s, message(
                "radio.line.fix", label=raw_text(fix["label"]),
                sigma=f"{fix['sigma_nm']:.1f}",
                age=f"{max(0.0, game.sim_t - fix['t']):.0f}"),
                (gx, gy, gw, 24), config.COLOR_OK, size=16)
            gy += 26
        lx, ly, lw, _ = left
        reports = game.hfdf_bearings()
        row_h = 34
        if not reports:
            layout.blit_line(s, "panel.no_transmission", (lx, ly, lw, 26),
                             config.COLOR_TEXT_DIM, size=18)
        else:
            capacity = max(1, (left[3] - 60) // row_h)
            selected_idx = min(game.radio_sel, len(reports) - 1)
            start = max(0, min(selected_idx - capacity // 2,
                               len(reports) - capacity))
            for i, report in enumerate(reports[start:start + capacity], start):
                selected = i == selected_idx
                if selected:
                    pygame.draw.rect(s, config.COLOR_SELECT_BG,
                                     (lx - 5, ly - 2, lw + 10, row_h - 4))
                    pygame.draw.rect(s, config.COLOR_WARN,
                                     (lx - 5, ly - 2, 3, row_h - 4))
                age = report.age(game.sim_t)
                layout.blit_line(
                    s, message("radio.line.signal", prefix='>' if selected else ' ',
                                label=game.hfdf_display_id(report),
                                bearing=observations.format_bearing(report, game.ship),
                               error=f"{_hfdf_error_deg(report):.0f}", age=f"{age:.0f}"),
                    (lx, ly, lw, row_h - 8),
                    config.COLOR_WARN if selected else
                    config.COLOR_TEXT if age < 30 else config.COLOR_TEXT_DIM,
                    size=17)
                ly += row_h
        ly = left[1] + left[3] - 34
        if game.hfdf_log:
            layout.blit_line(s, message("radio.line.log_fix", log=len(game.hfdf_log), fixes=len(game.hfdf_fixes)),
                             (lx, ly, lw, 24), config.COLOR_OK, size=16)
    else:
        right = layout.box(s, (x, cy, w, box_h), "panel.messages")
        rx, ry, rw, rh = right
        msgs = game.messages[-10:] if game.messages else [("--:--", message("ui.no_traffic"))]
        row_h = max(46, (rh - 40) // max(1, len(msgs)))
        for row, (stamp, txt) in enumerate(msgs):
            if row == len(msgs) - 1:
                pygame.draw.rect(s, (20, 38, 27), (rx - 4, ry - 2, rw + 8, row_h - 2))
            layout.blit_line(s, stamp, (rx, ry, 90, 26), config.COLOR_OK, size=17)
            pygame.draw.line(s, config.COLOR_GRID, (rx + 94, ry), (rx + 94, ry + row_h - 5))
            layout.blit_block(s, txt, rx + 104, ry, rw - 104, row_h - 3,
                               color=config.COLOR_TEXT, size=16)
            ry += row_h

    _shortcut_footer(s, (x, station_rect.bottom - 26, w, 20), (
        ("↑/↓", "radio.footer.select"),
        ("Enter", "radio.footer.log"),
    ))


# --- Maschinenraum (M10) ---------------------------------------------------

@localized
def draw_engine_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    ship = game.ship
    from src.core.commands import STATION_PAGES
    pages = STATION_PAGES[Station.ENGINE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.engine.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    content_h = station_rect.bottom - cy - 34
    x, w = r[0] + 14, r[2] - 28

    if page == 0:
        gap = 16
        col_w = (w - gap) // 2
        orders = layout.box(s, (x, cy, col_w, content_h), "panel.engine_order")
        ox, oy, ow, _ = orders
        layout.blit_line(s, ship.telegraph, (ox, oy, ow, 40), config.COLOR_TEXT, size=28)
        oy += 48
        displayed_orders = (("ASTERN", config.ASTERN_SPEED_KN),
                            *config.TELEGRAPH_ORDERS)
        for i, (name, sp) in enumerate(displayed_orders):
            astern = getattr(ship, "astern", False)
            selected = astern if i == 0 else not astern and i - 1 == ship.order_idx
            mark = ">" if selected else " "
            col = config.COLOR_OK if selected else config.COLOR_TEXT_DIM
            if selected:
                pygame.draw.rect(s, (20, 43, 29), (ox - 4, oy - 2, ow + 8, 28))
            layout.status_line(s, ox, oy, ow,
                               message("engine.line.order", mark=mark, order=name),
                               message("bridge.line.speed", speed=f"{sp:4.1f}"),
                               color=col, label_w=200, size=18)
            oy += 32
        systems = layout.box(s, (x + col_w + gap, cy, col_w, content_h),
                              "panel.propulsion",
                             border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
        px, py, pw, _ = systems
        layout.status_line(s, px, py, pw, "panel.shaft",
                            message("engine.line.speed_target", speed=f"{ship.speed:4.1f}", target=f"{ship.target_speed:4.1f}"),
                           label_w=140, size=20)
        py += 40
        layout.status_line(s, px, py, pw, "engine.course",
                           message("engine.line.course_target",
                                   course=f"{ship.course:03.0f}",
                                   target=f"{ship.target_course:03.0f}"),
                           label_w=140, size=20)
        py += 40
        bar_w = int(pw * 0.72)
        max_rpm = Ship.max_rpm()
        frac = min(1.0, ship.rpm() / max_rpm)
        pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 16))
        pygame.draw.rect(s, config.COLOR_TEXT, (px, py, int(bar_w * frac), 16))
        layout.blit_line(s, message("engine.line.rpm", rpm=f"{ship.rpm():3.0f}"),
                         (px + bar_w + 10, py - 2, pw - bar_w - 10, 24),
                         config.COLOR_TEXT_DIM, size=18)
        py += 42
        nf = ship.noise_level()
        pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 16))
        pygame.draw.rect(s, config.COLOR_WARN, (px, py, int(bar_w * nf), 16))
        layout.blit_line(s, message("engine.line.noise", noise=f"{nf * 100:3.0f}"),
                         (px + bar_w + 10, py - 2, pw - bar_w - 10, 24),
                         config.COLOR_TEXT_DIM, size=18)
        py += 42
        if ship.cavitating:
            layout.blit_block(s, "engine.cavitation_warning", px, py, pw, 28,
                              color=config.COLOR_DANGER, size=20)
    else:
        cap = game.damage.engine_speed_cap()
        systems = layout.box(s, (x, cy, w, content_h), "panel.propulsion",
                             border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
        px, py, pw, _ = systems
        layout.status_line(s, px, py, pw, "panel.shaft",
                           message("engine.line.speed_target", speed=f"{ship.speed:4.1f}", target=f"{ship.target_speed:4.1f}"),
                           label_w=160, size=20)
        py += 38
        layout.status_line(s, px, py, pw, "panel.sea_state",
                           message("engine.line.sea_motion",
                                   sea=f"{getattr(game.world, 'effective_sea_state', game.world.sea_state):.1f}",
                                   roll=f"{ship.roll:4.1f}", pitch=f"{ship.pitch:4.1f}"),
                           label_w=160, size=18)
        py += 34
        list_deg = game.damage.list_deg()
        if abs(list_deg) > 0.05:
            layout.status_line(s, px, py, pw, "panel.hull_list",
                               message("engine.line.hull_list",
                                       side=localize("engine.list_starboard" if list_deg > 0
                                                     else "engine.list_port"),
                                       degrees=f"{abs(list_deg):3.1f}"),
                               label_w=160, size=18, color=config.COLOR_WARN)
            py += 34
        masch = game.damage.compartments.get("engine")
        if masch is not None:
            col = config.COLOR_DANGER if masch.state == "ZERSTOERT" else (
                config.COLOR_WARN if masch.flood > 20 or masch.fire > 0 else config.COLOR_OK)
            extra = (localize(message("engine.line.fire", fire=f"{masch.fire:3.0f}"))
                     if masch.fire > 0 else "")
            layout.blit_block(s, localize(message(
                                  "engine.machinery", state=localize(STATE_LABEL[masch.state]),
                                  flooding=f"{masch.flood:.0f}", extra=extra)),
                               px, py, pw, 26, color=col, size=18)
            py += 34
        fuel_fraction = (ship.fuel_kg / ship.fuel_capacity_kg
                         if ship.fuel_capacity_kg > 0.0 else 0.0)
        endurance = ship.fuel_endurance_h()
        distance = ship.fuel_range_nm()
        layout.status_line(s, px, py, pw, "engine.fuel",
                           message("engine.line.fuel", fuel=f"{ship.fuel_kg / 1000.0:.1f}",
                                   percent=f"{fuel_fraction:.0%}"),
                           color=(config.COLOR_DANGER if fuel_fraction <= 0.1
                                  else config.COLOR_WARN if fuel_fraction <= 0.25
                                  else config.COLOR_TEXT),
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "engine.consumption",
                           message("engine.line.endurance",
                                   burn=f"{ship.fuel_burn_kg_h():.0f}",
                                   hours=(f"{endurance:.0f}" if endurance is not None else "--"),
                                   range=(f"{distance:.0f}" if distance is not None else "--")),
                           label_w=160, size=18)
        py += 34
        teams = game.damage.teams_on("engine")
        trend = game.damage.compartment_trend("engine")
        layout.status_line(s, px, py, pw, "engine.repairs",
                           message("engine.line.repairs",
                                   teams=", ".join(str(team) for team in teams) or "--",
                                   flood=f"{trend['flood_rate']:+.2f}",
                                   fire=f"{trend['fire_rate']:+.2f}"),
                           color=config.COLOR_OK if teams else config.COLOR_TEXT_DIM,
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "view.engine.speed_limit",
                           message("bridge.line.speed", speed=f"{cap:4.1f}"),
                           label_w=160, size=18)
        py += 34
        layout.status_line(s, px, py, pw, "ui.acoustic_mode",
                            "engine.quiet_limit" if ship.quiet_mode else "station.normal",
                           color=config.COLOR_OK if ship.quiet_mode else config.COLOR_TEXT,
                           label_w=160, size=18)
        py += 34
        sonar_range = game.ship.passive_sonar_range_nm(
            0.5, getattr(game.world, "effective_sea_state", game.world.sea_state))
        if game.sonar_mode == "TOWED":
            sonar_range *= max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                               - config.SONAR_TOWED_SPEED_PENALTY * ship.speed)
        available = game.sonar_mode != "TOWED" or game.sonar._tow_available()
        layout.status_line(s, px, py, pw, "ui.sonar_effect",
                            message("engine.line.sonar_effect", range=f"{sonar_range:4.1f}",
                                    array=display_value("array", game.sonar_mode))
                            if available else "engine.tas_unavailable",
                           color=config.COLOR_OK if available and sonar_range > 10 else config.COLOR_WARN,
                           label_w=160, size=18)
        py += 34
        cap_reason = ("engine.limit.down" if game.damage.station_down("engine") else
                      "engine.limit.damaged" if game.damage.station_degraded("engine") else
                      "engine.limit.none")
        layout.status_line(s, px, py, pw, "panel.limit", cap_reason,
                           label_w=160, size=18)

    station_bottom = config.STATION_RECT[1] + config.STATION_RECT[3]
    _shortcut_footer(s, (x, station_bottom - 26, w, 20), (
        ("↑/↓", "engine.footer.telegraph"),
        ("A", "engine.footer.quiet"),
        ("U", "engine.footer.set_course"),
        ("V", "engine.footer.set_speed"),
    ))


# --- Helikopter-Deck --------------------------------------------------------


def helicopter_regions(game=None, station_rect=None, page=0) -> dict[str, pygame.Rect]:
    """Authoritative adaptive geometry shared by flight-deck draw and hit-test."""
    if game is not None:
        layout.configure_for(game)
    station = pygame.Rect(station_rect or config.STATION_RECT)
    top = _station_content_top(station, 2)
    x, width = station.x + 14, station.w - 28
    gap = 10
    bottom = station.bottom - 30
    available = max(1, bottom - top)
    empty = pygame.Rect(0, 0, 0, 0)
    if page == 0:
        # Size the status card from its six real rows so large text grows it.
        row_h = max(28, layout.font(16).get_linesize() + 6)
        status_h = layout.font(16, True).get_linesize() + 16 + row_h * 6
        status_h = min(status_h + 10, max(int(available * 0.45),
                                          available - gap - 110))
        resources_h = max(1, available - status_h - gap)
        return {
            "station": station,
            "status": pygame.Rect(x, top, width, status_h),
            "resources": pygame.Rect(x, top + status_h + gap, width, resources_h),
            "rules": empty,
        }
    else:
        return {
            "station": station,
            "status": empty,
            "resources": empty,
            "rules": pygame.Rect(x, top, width, available),
        }


_HELICOPTER_WATERFALL_CACHE = {}


def _helicopter_waterfall(screen, rect, rows, *, receiver, amber=False):
    """Render bounded acoustic history in one vectorized surface."""
    pygame.draw.rect(screen, (7, 21, 28), rect)
    if rows and rect.w > 0 and rect.h > 0:
        key = (receiver, receiver.sequence, rect.size, amber)
        scaled = _HELICOPTER_WATERFALL_CACHE.get(key)
        if scaled is None:
            values = np.clip(np.asarray(rows[-64:], dtype=np.float32), 0, 1)
            if values.ndim == 2 and values.shape[1] > 0:
                levels = (values[::-1].T * 255).astype(np.uint16)
                pixels = np.zeros((*levels.shape, 3), dtype=np.uint8)
                if amber:
                    pixels[..., 0] = levels
                    pixels[..., 1] = levels * 3 // 4
                    pixels[..., 2] = levels // 5
                else:
                    pixels[..., 0] = levels // 4
                    pixels[..., 1] = levels
                    pixels[..., 2] = levels * 3 // 4
                surface = pygame.surfarray.make_surface(pixels)
                scaled = pygame.transform.scale(surface, rect.size)
                if len(_HELICOPTER_WATERFALL_CACHE) >= 4:
                    _HELICOPTER_WATERFALL_CACHE.clear()
                _HELICOPTER_WATERFALL_CACHE[key] = scaled
        if scaled is not None:
            screen.blit(scaled, rect)
    for tick in range(1, 5):
        x = rect.x + tick * rect.w // 5
        y = rect.y + tick * rect.h // 5
        pygame.draw.line(screen, (24, 55, 61), (x, rect.y), (x, rect.bottom - 1))
        pygame.draw.line(screen, (24, 55, 61), (rect.x, y), (rect.right - 1, y))
    pygame.draw.rect(screen, config.COLOR_GRID, rect, 1)


def _helicopter_trace(screen, rect, values, color):
    pygame.draw.rect(screen, (7, 21, 28), rect)
    for tick in range(1, 5):
        pygame.draw.line(screen, (24, 55, 61),
                         (rect.x, rect.y + tick * rect.h // 5),
                         (rect.right - 1, rect.y + tick * rect.h // 5))
    if len(values) > 1:
        points = [(rect.x + int(i * (rect.w - 2) / (len(values) - 1)),
                   rect.bottom - 2 - int(max(0, min(1, value)) * (rect.h - 4)))
                  for i, value in enumerate(values)]
        pygame.draw.lines(screen, color, False, points, 1)
    pygame.draw.rect(screen, config.COLOR_GRID, rect, 1)


_HELO_ACOUSTIC_PAGES = (("helo.acoustic.broadband", "helo.acoustic.broadband_axis"),
                        ("helo.acoustic.lofar", "helo.acoustic.lofar_axis"),
                        ("helo.acoustic.demon", "helo.acoustic.demon_axis"))
_HELO_ACOUSTIC_TABS = ("helo.acoustic.tab_broadband", "helo.acoustic.tab_lofar",
                       "helo.acoustic.tab_demon")


def _helicopter_acoustic_observations(game):
    source = game.helo_listen_source
    observations = []
    for contact in sorted(game.sonar.active_contacts(), key=lambda item: item.id):
        if source == "DIP":
            if contact.dip_last_seen is None or game.sim_t - contact.dip_last_seen >= 2:
                continue
            observed = contact.dip_bearing
        else:
            report = contact.buoy_reports.get(int(source[2:]))
            if not report or game.sim_t - report["measured_at"] >= 2:
                continue
            observed = report["bearing"]
        if observed is not None:
            observations.append((contact, observed))
    return observations


def helicopter_acoustic_geometry(rect):
    """One large analysis plot, observation rail and controls, as on ship sonar."""
    rect = pygame.Rect(rect)
    inner = rect.inflate(-12, -10)
    gap = 8
    tab_w = min(205, max(100, (inner.w - 2 * gap) // 3))
    tabs = [pygame.Rect(inner.x + 260 + i * (tab_w + gap), inner.y + 3,
                        tab_w, 28) for i in range(3)]
    back = pygame.Rect(inner.right - 155, inner.y + 3, 155, 28)
    status_y = inner.y + 37
    status_w = (inner.w - 3 * gap) // 4
    statuses = [pygame.Rect(inner.x + i * (status_w + gap), status_y,
                            status_w, 40) for i in range(4)]
    body_y = status_y + 48
    body_h = max(80, inner.bottom - body_y - 50)
    rail_w = max(245, min(340, int(inner.w * .27)))
    main = pygame.Rect(inner.x, body_y, inner.w - rail_w - gap, body_h)
    rail = pygame.Rect(main.right + gap, body_y, rail_w, body_h)
    footer = pygame.Rect(inner.x, inner.bottom - 43, inner.w, 38)
    return dict(tabs=tabs, back=back, statuses=statuses, main=main, rail=rail,
                footer=footer, plot=main.inflate(-16, -48).move(0, 12))


def helicopter_acoustic_hit(game, pos):
    if pos is None or game.station_page != 3:
        return None
    rect = pygame.Rect(config.FULL_STATION_RECT)
    geo = helicopter_acoustic_geometry(rect)
    if geo["back"].collidepoint(pos):
        return ("deck", 2)
    for index, tab in enumerate(geo["tabs"]):
        if tab.collidepoint(pos):
            return ("page", index)
    for index, (contact, _) in enumerate(_helicopter_acoustic_observations(game)[:3]):
        row = pygame.Rect(geo["rail"].x + 8,
                          geo["rail"].y + 132 + index * 48,
                          geo["rail"].w - 16, 43)
        if row.collidepoint(pos):
            return ("contact", contact.id)
    if game.helo_acoustic_page == 0 and geo["plot"].collidepoint(pos):
        return ("bearing", (pos[0] - geo["plot"].x) /
                max(1, geo["plot"].w - 1) * 360.0 % 360.0)
    return None


def _draw_helicopter_acoustic_view(game, rect):
    screen = game.screen
    layout.box(screen, rect)
    geo = helicopter_acoustic_geometry(rect)
    page = game.helo_acoustic_page % 3
    layout.blit_line(screen, "helo.acoustic.title",
                     (rect.x + 14, rect.y + 10, 245, 27),
                     config.COLOR_TEXT, size=19)
    for index, tab in enumerate(geo["tabs"]):
        pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE if index == page else (9, 30, 39), tab)
        pygame.draw.rect(screen, config.COLOR_SONAR_RING if index == page
                         else config.COLOR_GRID, tab, 1)
        layout.blit_line(screen, _HELO_ACOUSTIC_TABS[index], tab,
                         config.COLOR_TEXT if index == page else config.COLOR_TEXT_DIM,
                         size=14, align="center")
    pygame.draw.rect(screen, (9, 30, 39), geo["back"])
    pygame.draw.rect(screen, config.COLOR_GRID, geo["back"], 1)
    layout.blit_line(screen, "helo.acoustic.deck", geo["back"],
                     config.COLOR_TEXT_DIM, size=14, align="center")
    ready = game.helicopter_audio_ready()
    audio = game.audio.availability_status()
    audible = bool(ready and game.helo_audio_enabled and audio["global_enabled"]
                   and audio["device_available"])
    source = game.helo_listen_source
    source_label = localize("helo.dip_sonar") if source == "DIP" else source
    bearing = (f"{game.helo_listen_bearing:05.1f}°" if game.helo_listen_bearing
               is not None else localize("helo.acoustic.auto"))
    status = (
        message("helo.acoustic.status_source", source=source_label,
                state=localize("ui.ready" if ready else "helo.acoustic.dry")),
        message("helo.acoustic.status_bearing", bearing=bearing,
                gain=f"{game.helo_audition.gain_db:+.0f}"),
        message("helo.acoustic.status_filter", mode=display_value(
                    "audition_mode", game.helo_audition.audition_mode),
                band=f"{game.helo_audition.band_low_hz:.0f}–{game.helo_audition.band_high_hz:.0f} Hz"),
        message("helo.acoustic.status_audio",
                state=localize("ui.on" if audible else "ui.off"),
                volume=f"{game.sonar_volume:.0%}"),
    )
    for item, box in zip(status, geo["statuses"]):
        pygame.draw.rect(screen, (13, 35, 43), box)
        pygame.draw.rect(screen, config.COLOR_GRID, box, 1)
        layout.blit_line(screen, item, box.inflate(-10, -6), config.COLOR_TEXT,
                         size=13)
    main, rail, plot = geo["main"], geo["rail"], geo["plot"]
    for box in (main, rail):
        pygame.draw.rect(screen, (9, 29, 38), box)
        pygame.draw.rect(screen, config.COLOR_GRID, box, 1)
    layout.blit_line(screen, _HELO_ACOUSTIC_PAGES[page][0],
                     (main.x + 10, main.y + 6, main.w - 130, 23),
                     config.COLOR_TEXT, size=17)
    layout.blit_line(screen, _HELO_ACOUSTIC_PAGES[page][1],
                     (main.right - 115, main.y + 8, 105, 20),
                     config.COLOR_TEXT_DIM, size=13, align="right")
    if page == 0:
        _helicopter_waterfall(screen, plot, game.helo_broadband_history,
                              receiver=game.helo_receiver)
        if game.helo_listen_bearing is not None:
            marker_x = plot.x + round(game.helo_listen_bearing / 360 * plot.w)
            pygame.draw.line(screen, config.COLOR_WARN,
                             (marker_x, plot.y), (marker_x, plot.bottom - 1), 2)
    elif page == 1:
        upper = pygame.Rect(plot.x, plot.y, plot.w, max(1, int(plot.h * .28)))
        lower = pygame.Rect(plot.x, upper.bottom + 6, plot.w,
                            max(1, plot.bottom - upper.bottom - 6))
        _helicopter_trace(screen, upper, game.helo_receiver.spectrum,
                          config.COLOR_OK)
        _helicopter_waterfall(screen, lower, game.helo_spectra,
                              receiver=game.helo_receiver, amber=True)
    else:
        upper = pygame.Rect(plot.x, plot.y, plot.w, max(1, int(plot.h * .64)))
        lower = pygame.Rect(plot.x, upper.bottom + 6, plot.w,
                            max(1, plot.bottom - upper.bottom - 6))
        _helicopter_waterfall(screen, upper, game.helo_demon_history,
                              receiver=game.helo_receiver, amber=True)
        _helicopter_trace(screen, lower, game.helo_receiver.demon_spectrum,
                          config.COLOR_WARN)
    axis_max = (360, 300, 80)[page]
    for tick in range(5):
        value = axis_max * tick // 4
        x = plot.x + round(tick * (plot.w - 1) / 4)
        label_w = 42
        layout.blit_line(screen, str(value),
                         (max(plot.x + 2, min(x - label_w // 2,
                                               plot.right - label_w - 2)),
                          plot.bottom - 20, label_w, 17),
                         config.COLOR_TEXT_DIM, size=11, align="center")
    layout.blit_line(screen, "helo.acoustic.receiver",
                     (rail.x + 10, rail.y + 7, rail.w - 20, 23),
                     config.COLOR_TEXT, size=16)
    layout.blit_line(screen, message("helo.acoustic.receiver_source",
                     source=source_label),
                     (rail.x + 10, rail.y + 33, rail.w - 20, 20),
                     config.COLOR_TEXT_DIM, size=13)
    if source == "DIP":
        layout.blit_line(screen, message("helo.acoustic.receiver_depth",
            depth=f"{game.helo.dip_depth_m:.0f}"),
            (rail.x + 10, rail.y + 55, rail.w - 20, 20),
            config.COLOR_TEXT_DIM, size=13)
    layout.blit_line(screen, message("helo.acoustic.device",
        global_state=localize("ui.on" if audio["global_enabled"] else "ui.off"),
        device=localize("ui.on" if audio["device_available"] else "ui.off")),
        (rail.x + 10, rail.y + 76, rail.w - 20, 20),
        config.COLOR_TEXT_DIM, size=13)
    pygame.draw.line(screen, config.COLOR_GRID,
                     (rail.x + 8, rail.y + 102), (rail.right - 8, rail.y + 102))
    layout.blit_line(screen, "helo.acoustic.observations",
                     (rail.x + 10, rail.y + 106, rail.w - 20, 23),
                     config.COLOR_TEXT, size=15)
    observations = _helicopter_acoustic_observations(game)
    if not observations:
        layout.blit_line(screen, "helo.dip_contact_none",
                         (rail.x + 10, rail.y + 132, rail.w - 20, 24),
                         config.COLOR_TEXT_DIM, size=14)
    for index, (contact, observed) in enumerate(observations[:3]):
        y = rail.y + 132 + index * 48
        if y + 44 > rail.bottom:
            break
        selected = contact is game.selected_contact
        row = pygame.Rect(rail.x + 8, y, rail.w - 16, 43)
        pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE if selected else (12, 32, 40), row)
        layout.blit_line(screen, message("helo.acoustic.contact",
            contact=contact.id, bearing=f"{observed:05.1f}"),
            (row.x + 7, row.y + 3, row.w - 14, 19), config.COLOR_TEXT, size=14)
        layout.blit_line(screen, "helo.acoustic.qualified" if contact.helo_qualified
                         else "helo.acoustic.unqualified",
                         (row.x + 7, row.y + 22, row.w - 14, 18),
                         config.COLOR_OK if contact.helo_qualified
                         else config.COLOR_TEXT_DIM, size=12)
    footer = geo["footer"]
    pygame.draw.rect(screen, (13, 35, 43), footer)
    pygame.draw.rect(screen, config.COLOR_GRID, footer, 1)
    layout.blit_line(screen, "helo.acoustic.keys_view",
                     (footer.x + 9, footer.y + 2, footer.w - 18, 17),
                     config.COLOR_TEXT_DIM, size=12)
    layout.blit_line(screen, "helo.acoustic.keys_audio",
                     (footer.x + 9, footer.y + 20, footer.w - 18, 17),
                     config.COLOR_TEXT_DIM, size=12)


@localized
def draw_helicopter_view(game, tr=None) -> None:
    """Eigene Deckansicht fuer Status, Reichweite und Einsatzfreigaben."""
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.HELICOPTER]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    station = pygame.Rect(config.STATION_RECT)
    if page == 3:
        _draw_helicopter_acoustic_view(game, station)
        return
    _panel(game, title="station.helicopter.title")
    draw_station_page_tabs(s, station, pages, page, tr)
    regions = helicopter_regions(game, station_rect=station, page=page)
    helo = game.helo
    state_label = localize("enum.helo." + helo.state)
    state_color = (config.COLOR_DANGER if helo.state == "VERLOREN" else
                   config.COLOR_WARN if helo.state == "ZURUECK" else
                   config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM)
    distance = ((helo.x - game.ship.x) ** 2 +
                (helo.y - game.ship.y) ** 2) ** 0.5 if helo.airborne else 0.0

    if page == 0:
        status = layout.box(s, regions["status"], "panel.flight_status", border=state_color)
        sx, sy, sw, _ = status

        def _label_w(key: str, size: int, min_w: int) -> int:
            face = layout.font(size)
            return max(min_w, int(face.size(localize(key))[0]) + 12)

        row_h = max(28, layout.font(16).get_linesize() + 6)
        layout.status_line(s, sx, sy, sw, "ui.condition", state_label,
                           color=state_color, label_w=_label_w("ui.condition", 16, 120), size=16)
        fuel_color = (config.COLOR_DANGER if helo.airborne and helo.fuel_s <= config.HELO_FUEL_RESERVE_S else
                      config.COLOR_WARN if helo.airborne and helo.fuel_s <= config.HELO_FUEL_RESERVE_S * 1.5 else
                      config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM)
        layout.status_line(s, sx, sy + row_h, sw, "ui.fuel_colon",
                           message("helo.line.fuel", fuel=f"{helo.fuel_s / 60:4.0f}"),
                           color=fuel_color, label_w=_label_w("ui.fuel_colon", 16, 90), size=16)
        aircraft_bearing = math.degrees(math.atan2(
            helo.x - game.ship.x, -(helo.y - game.ship.y))) % 360.0
        true_bearing, relative_bearing = layout.bearing_pair(
            aircraft_bearing, game.ship.course)
        layout.status_line(s, sx, sy + row_h * 2, sw, "ui.ship_helo_range",
                           message("bridge.line.range", range=f"{distance:4.1f}") if helo.airborne else state_label,
                           label_w=_label_w("ui.ship_helo_range", 15, 150), size=15)
        layout.status_line(s, sx, sy + row_h * 3, sw, "ui.ship_helo_bearing",
                           message("helo.line.bearing_pair", true=f"{true_bearing:05.1f}", relative=f"{relative_bearing:05.1f}") if helo.airborne else "--",
                           label_w=_label_w("ui.ship_helo_bearing", 15, 150), size=15)
        layout.status_line(s, sx, sy + row_h * 4, sw, "ui.flight_course_true",
                           message("helo.line.course", course=f"{helo.course:05.1f}") if helo.airborne else "--",
                           label_w=_label_w("ui.flight_course_true", 15, 160), size=15)
        dip_state = getattr(helo, "dip_state", "STOWED")
        dip_depth = getattr(helo, "dip_depth_m", 0.0)
        dip_target = getattr(helo, "dip_depth_target_m",
                             config.HELO_DIP_DEPTH_DEFAULT_M)
        dip_water = getattr(helo, "dip_water_depth_m", 0.0)
        dip_cooldown = getattr(helo, "dip_ping_cooldown", 0.0)
        layout.status_line(
            s, sx, sy + row_h * 5, sw, "helo.dip_sonar",
            message("helo.line.dip_status",
                    state=localize("enum.helo_dip." + dip_state),
                    depth=f"{dip_depth:.0f}/{dip_target:.0f}",
                    water=f"{dip_water:.0f}", cooldown=f"{dip_cooldown:.0f}"),
            color=(config.COLOR_OK if dip_state == "DEPLOYED" else
                   config.COLOR_WARN if dip_state != "STOWED" else
                   config.COLOR_TEXT_DIM), label_w=_label_w("helo.dip_sonar", 15, 120), size=15)

        resources = layout.box(s, regions["resources"], "ui.resources_grid")
        rx, ry, rw, rh = resources
        cell_gap = 8
        cell_w = (rw - cell_gap) // 2
        cell_h = max(1, (rh - cell_gap) // 2)
        resource_values = (
            ("helo.air_torpedoes", str(helo.torps), config.COLOR_WARN),
            ("helo.sonobuoys_ready", str(helo.buoys_left), config.COLOR_TEXT),
            ("helo.sonobuoys_active", str(len(game.buoys)), config.COLOR_TEXT),
            ("panel.datalink", "ui.active" if helo.airborne else "helo.standby",
             config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM),
        )
        for index, (label, value, color) in enumerate(resource_values):
            cell = pygame.Rect(rx + index % 2 * (cell_w + cell_gap),
                               ry + index // 2 * (cell_h + cell_gap),
                               cell_w, cell_h)
            pygame.draw.rect(s, (10, 21, 17), cell)
            pygame.draw.rect(s, config.COLOR_GRID, cell, 1)
            label_h = layout.font(14).get_linesize()
            value_h = layout.font(16).get_linesize()
            layout.blit_line(s, label,
                             (cell.x + 8, cell.y + 4, cell.w - 16, label_h),
                             config.COLOR_TEXT_DIM, size=14)
            layout.blit_line(s, value,
                             (cell.x + 8, cell.bottom - value_h - 4,
                              cell.w - 16, value_h), color, size=16,
                             align="right")
    elif page == 1:
        mission_box = layout.box(s, regions["rules"], "panel.rules")
        mx, my, mw, _ = mission_box
        wp_brg, wp_dist = game._helo_waypoint_polar()
        return_s = distance / max(.001, config.kn_to_nm_per_s(config.HELO_SPEED_KN))
        margin_s = helo.fuel_s - return_s - config.HELO_FUEL_RESERVE_S
        margin_color = (config.COLOR_TEXT_DIM if not helo.airborne else
                        config.COLOR_DANGER if margin_s < 0 else
                        config.COLOR_WARN if margin_s < 300 else config.COLOR_OK)
        dip_contacts = helo_dip_contacts(game)
        rules = (localize(message("helo.waypoint_rule", bearing=f"{wp_brg:03.0f}",
                                  range=f"{wp_dist:.0f}")),
                 localize(message("helo.rtb_margin", margin=f"{margin_s / 60:+.0f}"))
                 if helo.airborne else localize("helo.rtb_unavailable"),
                 localize("helo.launch_rule"), localize("helo.dip_controls"),
                 localize("helo.weapon_controls"),
                 _helo_dip_contact_line(game),
                 localize("view.helo.roe"))
        colors = (config.COLOR_TEXT, margin_color, config.COLOR_TEXT_DIM,
                  config.COLOR_OK, config.COLOR_WARN,
                  config.COLOR_OK if dip_contacts else config.COLOR_TEXT_DIM,
                  config.COLOR_WARN)
        line_y = my
        line_h = max(30, layout.font(18).get_linesize() + 4)
        for text, color in zip(rules, colors):
            remaining = max(0, regions["rules"].bottom - 8 - line_y)
            if remaining <= 0:
                break
            block_h = min(remaining, line_h * (2 if text == rules[-1] else 1))
            layout.blit_block(s, text, mx, line_y, mw, block_h, color,
                              size=18, min_size=16)
            line_y += block_h + 4
    elif page == 2:
        plot = layout.box(s, regions["rules"], "helo.dip_sonar")
        px, py, pw, ph = plot
        center_x, center_y = px + min(pw * .34, ph * .42), py + ph * .48
        radius = int(min(pw * .28, ph * .42))
        for fraction in (.5, 1.0):
            pygame.draw.circle(s, config.COLOR_GRID,
                               (int(center_x), int(center_y)),
                               max(1, int(radius * fraction)), 1)
        for bearing in (0, 90, 180, 270):
            theta = math.radians(bearing)
            end = (int(center_x + math.sin(theta) * radius),
                   int(center_y - math.cos(theta) * radius))
            pygame.draw.line(s, config.COLOR_GRID,
                             (int(center_x), int(center_y)), end, 1)
        gauge_x, gauge_y = int(px + pw * .62), py + 12
        gauge_h = min(160, max(80, ph // 3))
        depth_limit = (helo.dip_depth_limit(game.world) if helo.airborne else 0.0)
        # The layer is known only once the lowered dome has passed through
        # it (the dome's own temperature/sound-speed trace), never before.
        layer = (game.world.thermocline_depth_m(helo.x, helo.y)
                 if depth_limit > 0 and helo.dip_state != "STOWED" else None)
        thermocline = (layer if layer is not None and helo.dip_depth_m >= layer
                       else None)
        gauge_max = max(50.0, depth_limit)
        pygame.draw.rect(s, config.COLOR_GRID,
                         pygame.Rect(gauge_x, gauge_y, 22, gauge_h), 1)
        if thermocline is not None and thermocline <= gauge_max:
            layer_y = gauge_y + int(gauge_h * thermocline / gauge_max)
            pygame.draw.line(s, config.COLOR_WARN,
                             (gauge_x - 5, layer_y), (gauge_x + 27, layer_y), 2)
        if helo.dip_state != "STOWED":
            dome_y = gauge_y + int(gauge_h * min(1.0, helo.dip_depth_m / gauge_max))
            pygame.draw.circle(s, config.COLOR_OK, (gauge_x + 11, dome_y), 5)
        gauge_text_x = gauge_x + 34
        gauge_text_w = max(1, int(px + pw - gauge_text_x))
        for index, label in enumerate((
                message("helo.dip_gauge_depth", depth=f"{helo.dip_depth_m:.0f}",
                        target=f"{helo.dip_depth_target_m:.0f}"),
                message("helo.dip_gauge_layer", depth=(
                    "--" if thermocline is None else f"{thermocline:.0f}")),
                message("helo.dip_gauge_limit", depth=f"{depth_limit:.0f}"),
                message("helo.dip_gauge_rate", rate=f"{config.HELO_DIP_DEPTH_RATE_M_S:.1f}"))):
            layout.blit_line(s, label, (gauge_text_x, gauge_y + index * 29,
                                        gauge_text_w, 26),
                             config.COLOR_TEXT, size=15)
        lines = []
        source_label = localize("helo.source.buoy" if getattr(game, "helo_sensor_source", "DIP") == "BUOY"
                                else "helo.source.dip")
        layout.blit_line(s, source_label, (px + 8, py + 4, int(pw * .55), 22),
                         config.COLOR_OK, size=16)
        for contact in sorted(game.sonar.contacts.values(), key=lambda c: c.id):
            fixes = [fix for fix in contact.active_fixes(game.sim_t)
                     if fix["source"] == "DIPPING"]
            fix = max(fixes, key=lambda item: item["fixed_at"]) if fixes else None
            passive = (contact.dip_bearing is not None
                       and contact.dip_last_seen is not None
                       and 0 <= game.sim_t - contact.dip_last_seen
                       < config.SONAR_CONTACT_LOST_S)
            if not passive and fix is None and not contact.buoy_reports:
                continue
            label = observations.contact_display_id(game, contact)
            if passive:
                theta = math.radians(contact.dip_bearing)
                if contact.dip_bearing_uncertainty_deg is not None:
                    for edge in (-1, 1):
                        bound = math.radians(contact.dip_bearing + edge *
                                             contact.dip_bearing_uncertainty_deg)
                        bound_end = (int(center_x + math.sin(bound) * radius),
                                     int(center_y - math.cos(bound) * radius))
                        pygame.draw.line(s, config.COLOR_GRID,
                                         (int(center_x), int(center_y)), bound_end, 1)
                end = (int(center_x + math.sin(theta) * radius),
                       int(center_y - math.cos(theta) * radius))
                pygame.draw.line(s, config.COLOR_OK,
                                 (int(center_x), int(center_y)), end, 2)
                lines.append(message("helo.dip_passive_line", contact=label,
                                     bearing=f"{contact.dip_bearing:05.1f}",
                                     error=f"{contact.dip_bearing_uncertainty_deg:.1f}",
                                     age=f"{game.sim_t - contact.dip_last_seen:.0f}"))
            if fix is not None:
                origin_x, origin_y = contact.observer_x, contact.observer_y
                distance = math.hypot(fix["x"] - origin_x, fix["y"] - origin_y)
                theta = math.atan2(fix["x"] - origin_x, -(fix["y"] - origin_y))
                marker_r = radius * min(1.0, distance / 20.0)
                marker = (int(center_x + math.sin(theta) * marker_r),
                          int(center_y - math.cos(theta) * marker_r))
                pygame.draw.circle(s, config.COLOR_WARN, marker,
                                   max(3, min(radius, int(radius * fix["uncertainty_nm"] / 20.0))), 1)
                pygame.draw.circle(s, config.COLOR_WARN,
                                   marker, 5)
                lines.append(message("helo.dip_active_line", contact=label,
                                     range=f"{distance:.1f}",
                                     range_error=f"{fix['uncertainty_nm']:.1f}",
                                     depth=f"{fix['depth_m']:.0f}" if fix["depth_m"] is not None else "--",
                                     depth_error=(f"{fix['depth_uncertainty_m']:.0f}"
                                                  if fix["depth_uncertainty_m"] is not None else "--"),
                                     age=f"{game.sim_t - fix['measured_at']:.0f}"))
            for seq, row in sorted(contact.buoy_reports.items()):
                if not 0 <= game.sim_t - row["measured_at"] < config.SONAR_CONTACT_LOST_S:
                    continue
                lines.append(message("helo.buoy_report_line", buoy=f"SB{seq:02d}",
                                     contact=label, bearing=f"{row['bearing']:05.1f}",
                                     range=(f"{row['range_nm']:.1f} NM"
                                            if row["range_nm"] is not None else "--"),
                                     age=f"{game.sim_t - row['measured_at']:.0f}"))
                if (getattr(game, "helo_sensor_source", "DIP") == "BUOY"
                        and contact is game.selected_contact):
                    theta = math.radians(row["bearing"])
                    end = (int(center_x + math.sin(theta) * radius),
                           int(center_y - math.cos(theta) * radius))
                    pygame.draw.line(s, config.COLOR_WARN,
                                     (int(center_x), int(center_y)), end, 2)
        if not lines:
            lines.append(localize("helo.dip_contact_none"))
        spectrum = game.helo_receiver.spectrum
        graph = pygame.Rect(int(px + 6), int(py + ph - 66),
                            max(1, int(pw * .56)), 55)
        pygame.draw.rect(s, config.COLOR_GRID, graph, 1)
        if len(spectrum) > 1:
            points = [(graph.x + int(i * (graph.w - 2) / (len(spectrum) - 1)),
                       graph.bottom - 2 - int(max(0, min(1, value)) * (graph.h - 4)))
                      for i, value in enumerate(spectrum)]
            pygame.draw.lines(s, config.COLOR_OK, False, points, 1)
        layout.blit_line(s, "helo.dip_scale", (int(center_x - radius),
                         int(center_y + radius + 4), radius * 2, 20),
                         config.COLOR_TEXT_DIM, size=14, align="center")
        line_h = max(22, layout.font(15).get_linesize() + 2)
        list_y = gauge_y + gauge_h + 18
        for index, line in enumerate(lines[:max(1, int((py + ph - list_y) / line_h))]):
            layout.blit_line(s, line, (int(px + pw * .62), list_y + index * line_h,
                                       int(pw * .38), line_h),
                             config.COLOR_TEXT, size=15)
    else:
        _draw_helicopter_acoustic_view(game, regions["rules"])


# --- Schadensbekämpfung (M5, M14) ------------------------------------------

def damage_regions(game=None, station_rect=None, page=0) -> dict:
    """Shared fictional deck-plan geometry in virtual-canvas coordinates.

    ``compartments`` preserves COMPARTMENTS/save ordering. Each entry contains
    a convex ``polygon``, a ``callout`` Rect and an interior ``anchor`` point.
    Callers must reject letterbox coordinates before using this API. Page 0
    shows the full-width plan; page 1 shows the selected-compartment detail.
    """
    if game is not None:
        layout.configure_for(game)
    station = pygame.Rect(station_rect or config.STATION_RECT)
    top = _station_content_top(station, 2)
    bottom = station.bottom - 58
    x0 = station.x + 16
    full_w = station.w - 32
    if page == 0:
        schematic = pygame.Rect(x0, top, full_w, max(1, bottom - top))
        detail = pygame.Rect(0, 0, 0, 0)
    else:
        detail_w = 760
        detail = pygame.Rect(station.centerx - detail_w // 2, top,
                             detail_w, max(1, bottom - top))
        schematic = pygame.Rect(0, 0, 0, 0)
    hull_w = min(200, int(max(schematic.w, detail.w) * .30))
    hull_center_x = (schematic.centerx if page == 0 else detail.centerx)
    hull_rect = pygame.Rect(hull_center_x - hull_w // 2, top + 40,
                            hull_w, max(1, bottom - top - 90))

    def points(coords):
        return tuple((round(hull_rect.x + x * hull_rect.w),
                      round(hull_rect.y + y * hull_rect.h)) for x, y in coords)

    hull = points(((.5, 0), (.82, .12), (1, .28), (1, .87),
                   (.87, 1), (.13, 1), (0, .87), (0, .28), (.18, .12)))
    polygons = {
        "bridge": ((.2, .27), (.8, .27), (.8, .37), (.2, .37)),
        "sonar": ((.35, .07), (.65, .07), (.82, .15), (.18, .15)),
        "weapons": ((.18, .16), (.82, .16), (.8, .26), (.2, .26)),
        "opz": ((.2, .38), (.8, .38), (.8, .49), (.2, .49)),
        "radio": ((.2, .5), (.8, .5), (.8, .6), (.2, .6)),
        "engine": ((.2, .61), (.8, .61), (.8, .73), (.2, .73)),
        "flightdeck": ((.2, .74), (.8, .74), (.86, .98), (.14, .98)),
        "hull_left": ((.02, .29), (.17, .29), (.17, .88), (.12, .96), (.02, .86)),
        "hull_right": ((.83, .29), (.98, .29), (.98, .86), (.88, .96), (.83, .88)),
    }
    # Callout order is spatial; the public mapping and keyboard order are not.
    left = ("sonar", "bridge", "opz", "engine", "hull_left")
    right = ("weapons", "radio", "flightdeck", "hull_right")
    ref_width = schematic.w if page == 0 else full_w
    compartments = {}
    if page == 0:
        for key, _ in COMPARTMENTS:
            side = left if key in left else right
            row = side.index(key)
            row_h = hull_rect.h // len(side)
            callout_w = int(ref_width * .28)
            callout_h = min(row_h - 5, max(48, layout.font(16).get_linesize() * 2 + 10))
            callout = pygame.Rect(schematic.x if side is left else schematic.right - callout_w,
                                  hull_rect.y + row * row_h, callout_w, callout_h)
            polygon = points(polygons[key])
            anchor = (sum(p[0] for p in polygon) // len(polygon),
                      sum(p[1] for p in polygon) // len(polygon))
            compartments[key] = {"polygon": polygon, "callout": callout, "anchor": anchor}
    features = {
        "gun": points(((.43, .085), (.57, .085), (.59, .13), (.41, .13))),
        "barrel": points(((.5, .085), (.5, .035))),
        "vls": points(((.32, .18), (.68, .18), (.68, .24), (.32, .24))),
        "mast": points(((.5, .4), (.5, .47), (.28, .435), (.72, .435))),
        "funnel": points(((.37, .63), (.63, .63), (.63, .7), (.37, .7))),
        "hangar": points(((.3, .76), (.7, .76), (.7, .83), (.3, .83))),
        "helipad": points(((.28, .86), (.72, .86), (.72, .95), (.28, .95))),
    }
    return {"station": station, "schematic": schematic, "detail": detail,
            "hull": hull, "features": features, "compartments": compartments,
            "footer": pygame.Rect(station.x + 16, station.bottom - 56, station.w - 32, 48)}


def damage_compartment_at(game, pos, page=0):
    """Return compartment ID for polygon OR callout, otherwise None; no mutation."""
    regions = damage_regions(game, page=page)
    if pos is None or not regions["station"].collidepoint(pos):
        return None
    for key, region in regions["compartments"].items():
        if region["callout"].collidepoint(pos):
            return key
        polygon = region["polygon"]
        crosses = [(b[0] - a[0]) * (pos[1] - a[1]) -
                   (b[1] - a[1]) * (pos[0] - a[0])
                   for a, b in zip(polygon, polygon[1:] + polygon[:1])]
        if all(v >= 0 for v in crosses) or all(v <= 0 for v in crosses):
            return key
    return None


@localized
def draw_damage_view(game, tr=None) -> None:
    layout.configure_for(game)
    from src.core.commands import STATION_PAGES
    s = game.screen
    pages = STATION_PAGES[Station.DAMAGE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    rect = pygame.Rect(config.STATION_RECT)
    layout.panel(s, rect, "station.damage.title")
    draw_station_page_tabs(s, rect, pages, page, tr)
    regions = damage_regions(game, page=page)
    items = list(game.damage.compartments.items())
    selected_key, selected = items[game.dmg_cursor]

    if page == 0:
        plan = regions["schematic"]
        layout.record_geometry("schematic", plan, "damage.schematic.title")
        layout.blit_line(s, "damage.schematic.title", (plan.x, plan.y, plan.w, 26),
                         config.COLOR_TEXT_DIM, size=16)
        pygame.draw.polygon(s, (12, 32, 34), regions["hull"])
        pygame.draw.polygon(s, (115, 161, 163), regions["hull"], 2)
        for i, (key, c) in enumerate(items):
            region = regions["compartments"][key]
            polygon, card, anchor = region["polygon"], region["callout"], region["anchor"]
            sc = _state_color(c.state)
            is_sel = i == game.dmg_cursor
            fill = ((57, 27, 26) if c.state == "ZERSTOERT" else
                    (34, 66, 83) if c.flood > 0 else (18, 42, 39))
            pygame.draw.polygon(s, fill, polygon)
            pygame.draw.polygon(s, config.COLOR_TEXT if is_sel else sc,
                                polygon, 3 if is_sel else 1)
            left_side = card.centerx < anchor[0]
            edge = card.midright if left_side else card.midleft
            endpoint = (min(p[0] for p in polygon) if left_side else max(p[0] for p in polygon),
                        anchor[1])
            pygame.draw.lines(s, sc, False,
                              (edge, (edge[0] + (10 if left_side else -10), edge[1]), endpoint), 1)
            pygame.draw.rect(s, (10, 22, 23), card)
            pygame.draw.rect(s, config.COLOR_TEXT if is_sel else sc, card,
                             2 if is_sel else 1)
            label = message("damage.schematic.callout", number=f"{i + 1:02}",
                            name=localize("damage.short." + key))
            line_h = layout.font(16).get_linesize() + 2
            layout.blit_line(s, label, (card.x + 6, card.y + 3, card.w - 12, line_h),
                             config.COLOR_TEXT, size=16)
            teams = game.damage.teams_on(key)
            markers = ("X" if c.state == "ZERSTOERT" else
                       "!" if c.state != "OK" else "OK")
            markers += (" ~" if c.flood > 0 else "") + (" ^" if c.fire > 0 else "")
            if teams:
                markers += " T" + ",".join(map(str, teams))
            layout.blit_line(s, markers, (card.x + 6, card.y + line_h + 3,
                                          card.w - 12, line_h), sc, size=15)
            ax, ay = anchor
            if c.state == "ZERSTOERT":
                pygame.draw.line(s, sc, (ax - 7, ay - 7), (ax + 7, ay + 7), 2)
                pygame.draw.line(s, sc, (ax - 7, ay + 7), (ax + 7, ay - 7), 2)
            if c.fire > 0:
                pygame.draw.polygon(s, (255, 155, 83),
                                    ((ax - 7, ay + 6), (ax, ay - 8), (ax + 7, ay + 6)), 2)
            if c.flood > 0:
                pygame.draw.lines(s, (132, 194, 223), False,
                                  ((ax - 9, ay + 9), (ax - 3, ay + 6),
                                   (ax + 3, ay + 9), (ax + 9, ay + 6)), 2)
        for name, pts in regions["features"].items():
            if name in ("barrel", "mast"):
                pygame.draw.lines(s, (124, 161, 163), False, pts, 2)
            else:
                pygame.draw.polygon(s, (124, 161, 163), pts, 1)
            if name in ("vls", "funnel", "hangar"):
                for step in range(1, 4):
                    fx = round(pts[0][0] + (pts[1][0] - pts[0][0]) * step / 4)
                    pygame.draw.line(s, (90, 125, 129), (fx, pts[0][1]),
                                     (fx, pts[2][1]), 1)
            if name == "helipad":
                bounds = pygame.Rect(pts[0], (pts[2][0] - pts[0][0],
                                              pts[2][1] - pts[0][1]))
                inset = bounds.inflate(-bounds.w // 2, -bounds.h // 3)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.topleft, inset.bottomleft, 1)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.topright, inset.bottomright, 1)
                pygame.draw.line(s, config.COLOR_TEXT_DIM, inset.midleft, inset.midright, 1)
        layout.blit_line(s, "damage.schematic.legend",
                         (plan.x, plan.bottom - 36, plan.w, 30),
                         config.COLOR_TEXT_DIM, size=16)
    else:
        detail = layout.box(s, regions["detail"],
                            "panel.selection_actions", border=_state_color(selected.state))
        dx, dy, dw, _ = detail
        layout.blit_line(s, _compartment_name(selected_key, selected.name),
                         (dx, dy, dw, 32), config.COLOR_TEXT, size=22)
        dy += 36
        for label, value, color in (
                ("ui.state", localize(STATE_LABEL[selected.state]), _state_color(selected.state)),
                ("ui.flooding", f"{selected.flood:.0f}%", config.COLOR_TEXT),
                ("ui.fire", f"{selected.fire:.0f}%", config.COLOR_DANGER if selected.fire else config.COLOR_TEXT_DIM)):
            layout.blit_line(s, localize(label), (dx, dy, 140, 26), config.COLOR_TEXT_DIM, size=18)
            layout.blit_line(s, value, (dx + 144, dy, dw - 144, 26), color, size=18)
            dy += 30
        trend = game.damage.compartment_trend(selected_key)
        for hazard in ("flood", "fire"):
            rate = trend[hazard + "_rate"]
            trend_key = ("damage.unrepairable" if not trend["repairable"] else
                         "damage.rising" if rate > .001 else
                         "damage.falling" if rate < -.001 else "damage.stable")
            layout.blit_line(s, message("damage.net." + hazard,
                trend=localize(trend_key), rate=f"{rate * 60:+.1f}"),
                (dx, dy, dw, 26), config.COLOR_WARN if rate > 0 else config.COLOR_TEXT_DIM, size=18)
            dy += 30
        pygame.draw.line(s, config.COLOR_GRID, (dx, dy), (dx + dw, dy))
        dy += 14
        assignment = game.damage.teams[game.dmg_team]
        assignment_text = (_compartment_name(assignment, game.damage.compartments[assignment].name)
                           if assignment is not None else localize("damage.free"))
        layout.blit_line(s, message("damage.team_destination", team=game.dmg_team,
                                    destination=assignment_text),
                         (dx, dy, dw, 32), config.COLOR_OK, size=18)
        dy += 36
        assigned = game.damage.teams_on(selected_key)
        layout.blit_line(s, "ui.on_scene", (dx, dy, 120, 26), config.COLOR_TEXT_DIM, size=18)
        layout.blit_line(s, message("damage.line.teams_on_scene", teams=", ".join(map(str, assigned)))
                         if assigned else "damage.line.no_team", (dx + 124, dy, dw - 124, 26),
                         config.COLOR_OK if assigned else config.COLOR_WARN, size=18)
        dy += 30
        layout.blit_block(s, "control.damage_team",
                          dx, dy, dw, max(1, regions["detail"].bottom - dy - 8), config.COLOR_TEXT, size=18)

    footer_y = rect.bottom - 52
    layout.status_line(
        s, rect.x + 16, footer_y, rect.w - 32, "panel.total_flooding",
         message("damage.line.total", total=f"{game.damage.total:3.0f}",
                 maximum=len(game.damage.compartments) * 100,
                 average=f"{game.damage.avg_flood():.0f}"),
        color=config.COLOR_DANGER if game.damage.ship_sunk else config.COLOR_TEXT,
        label_w=190, size=17)
    _shortcut_footer(s, (rect.x + 16, footer_y + 26, rect.w - 32, 19), (
        ("←/→", "damage.footer.department"),
        ("↑/↓", "damage.footer.team"),
        ("Enter", "damage.footer.assign"),
        ("Backspace", "damage.footer.withdraw"),
    ))
