"""uConsole views while the local player commands the hostile submarine.

The screen follows the frigate's station layout: top status bar, the chart
on the left and the station panel on the right (like the Bridge), and the
event band / ticker below.  The sonar room is the ordinary sonar view drawn
inside ``Game.sonar_perspective``.

Everything drawn here is the boat's own: its navigation and systems, its own
torpedoes, the known chart and the boat's own sonar contacts.  The frigate's
position, plot, feed and systems never appear.
"""

import math

import pygame

from src.commander.server import OPFOR_ROLES
from src.core import boat_esm, config, opfor, uboot_local
from src.core.i18n import display_message, display_value, localize, message, raw_text
from src.core.station import Station
from src.ui import console, layout, lines, nato_symbols, overlay_style
from src.ui.feedback import FeedEntry
from src.ui.map_view import chart_background, draw_chart_frame, draw_chart_geography
from src.ui.plot_view import draw_plot
from src.ui.sonar_view import draw_sonar_view
from src.ui.stations_view import (_panel, _shortcut_footer, _station_content_top,
                                  draw_station_page_tabs, station_page_tab_at)
from src.ui.uboot_ballast import draw_ballast_page
from src.ui.uboot_damage import draw_damage_page
from src.ui.uboot_radio import draw_radio_page, draw_report_chart
from src.ui.uboot_threat import draw_intercept_lines, draw_threat_page
from src.enemies.damage_control import COMPARTMENTS
from src.ui.uboot_scope import draw_scope_page
from src.ui.viewport import Viewport
from src.ui.weather_station import draw_weather_station

UBOOT_PAGES = ("UBOOT_NAV", "UBOOT_WEAPONS", "UBOOT_SCOPE", "UBOOT_THREAT")
# Panel pages of each boat station beside the chart (the sonar room is full screen).
STATION_PAGES = {"uboot": UBOOT_PAGES, "uboot_weapons": ("UBOOT_WEAPONS",),
                 "uboot_engine": ("UBOOT_ENGINE", "UBOOT_SUPPLY", "UBOOT_BALLAST",
                                  "UBOOT_DAMAGE"),
                 "uboot_esm": ("UBOOT_ESM", "UBOOT_SCOPE"),
                 "uboot_nav": ("UBOOT_NAV", "UBOOT_THREAT"),
                 "uboot_radio": ("UBOOT_RADIO",)}


def station_pages(station: str) -> tuple:
    """Panel pages of a boat station (the sonar room has none here)."""
    return STATION_PAGES.get(station, UBOOT_PAGES)


def page_name(game, boat) -> str | None:
    """The panel page shown at the boat station the uConsole operates."""
    if boat is None or game.station is Station.SONAR:
        return None
    pages = station_pages(uboot_local.local_station(game))
    return pages[boat.command_page % len(pages)]
# Station tabs in the top bar: (x, width) of each, in station key order.
STATION_TAB_W = 100
CONTACT_ROWS = 10
# Alarms stay on the threat bar this long after the event (s).
ALARM_WINDOW_S = 120.0
# A heard ping or ESM intercept fills the threat box only this long; older
# warnings shrink to the marker in the top bar (details on the threat page).
THREAT_FRESH_S = 30.0
# Contact classification -> NATO frame domain on the chart (annotation only).
_CLASS_DOMAIN = {"U_BOOT": "SUBSURFACE", "KAMPFSCHIFF": "SURFACE",
                 "FAHRZEUG": "SURFACE", "FLUGZEUG": "AIR",
                 "TORPEDO": "UNDERWATER_WEAPON"}
TELEMETRY_TICKER_KEYS = ("uboot.telemetry.course_speed", "uboot.telemetry.depth",
                         "uboot.telemetry.battery", "uboot.telemetry.torpedoes")


def _fmt(value, pattern="{:.0f}"):
    return "--" if value is None or not math.isfinite(value) else pattern.format(value)


# --- chart camera ------------------------------------------------------------

def chart_view(game, boat) -> Viewport:
    """The boat's own chart camera (display only), following it by default."""
    view = boat.chart_view
    if view is None or view.world_size != game.world.size_nm:
        view = Viewport(game.world.size_nm, config.MAP_ZOOM_MIN_PX_PER_NM,
                        config.MAP_ZOOM_MAX_PX_PER_NM)
        view.scale = config.MAP_ZOOM_DEFAULT_PX_PER_NM
        view.cx, view.cy = boat.sub.x, boat.sub.y
        boat.chart_view = view
    view.set_rect(config.MAP_RECT)
    if boat.chart_follow:
        view.cx, view.cy = boat.sub.x, boat.sub.y
        view.clamp_center()
    return view


def chart_pointer(game, pos):
    """Canvas point inside the chart of the command page, else None."""
    if game.station is Station.SONAR:
        return None
    canvas = game._window_to_canvas(pos)
    if canvas is None or not pygame.Rect(config.MAP_RECT).collidepoint(canvas):
        return None
    return canvas


def page_tab_at(game, pos):
    pages = station_pages(uboot_local.local_station(game))
    if game.station is Station.SONAR or len(pages) < 2:
        return None
    canvas = game._window_to_canvas(pos)
    return station_page_tab_at(canvas, pygame.Rect(config.STATION_PANEL_RECT),
                               len(pages))


def station_tab_rects() -> list:
    return [pygame.Rect(4 + index * (STATION_TAB_W + 4), 3, STATION_TAB_W,
                        config.TOP_BAR_H - 6) for index in range(len(OPFOR_ROLES))]


def station_tab_at(game, pos):
    """The boat station whose top-bar tab is at ``pos``, else None."""
    canvas = game._window_to_canvas(pos)
    if canvas is None:
        return None
    return next((role for role, rect in zip(OPFOR_ROLES, station_tab_rects())
                 if rect.collidepoint(canvas)), None)


# --- top bar and bottom band ---------------------------------------------------

def draw_top_bar(game, boat) -> None:
    s = game.screen
    layout.configure_for(game)
    pygame.draw.rect(s, config.COLOR_PANEL_BG, (0, 0, config.SCREEN_W, config.TOP_BAR_H))
    lines.line(s, config.COLOR_SONAR_RING, (0, config.TOP_BAR_H - 1),
                     (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
    # The boat's seven stations as tabs (key number and short name); a station a
    # browser crews is marked and not operated from here.
    shown = uboot_local.local_station(game)
    leased = getattr(getattr(game.commander, "server", None), "station_leased", None)
    tabs = station_tab_rects()
    for index, (role, rect) in enumerate(zip(OPFOR_ROLES, tabs)):
        active = role == shown
        remote = bool(leased and leased(role))
        if active:
            pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, rect)
            lines.line(s, config.COLOR_SONAR_RING, rect.bottomleft,
                             (rect.right - 1, rect.bottom), 2)
        if index:
            lines.line(s, config.COLOR_GRID, (rect.x - 2, rect.y + 4), (rect.x - 2, rect.bottom - 4), 1)
        label = message("uboot.tab", number=index + 1, name=message(f"uboot.tab.{role}"))
        layout.blit_line(s, label, rect, config.COLOR_WARN if remote else
                         config.COLOR_TEXT if active else config.COLOR_TEXT_DIM,
                         size=14, align="center")
    sub = boat.sub if boat is not None else None
    text = message("uboot.top.status", scenario=raw_text(game.top_bar_scenario()),
                   time=game.world.format_time(),
                   course=_fmt(sub.course % 360.0 if sub else None, "{:03.0f}"),
                   speed=_fmt(sub.speed if sub else None, "{:.1f}"),
                   depth=_fmt(sub.depth if sub else None))
    left = tabs[-1].right + 12
    layout.blit_line(s, text, (left, 4, config.SCREEN_W - left - 10, config.TOP_BAR_H - 8),
                     config.COLOR_TEXT, size=16, align="right")
    rows = threat_rows(game, boat) if boat is not None and boat.sub is not None else []
    if rows and not any(fresh for _text, _level, fresh in rows):
        # Only stale warnings: a small marker left of the clock.
        _draw_threat_marker(s, config.SCREEN_W - 10 - layout.font(16).size(
            localize(text))[0] - 30, config.TOP_BAR_H // 2, len(rows))


def _draw_threat_marker(s, x, cy, count) -> None:
    """Amber warning triangle with the number of standing warnings."""
    pygame.draw.polygon(s, config.COLOR_WARN, ((x - 12, cy + 7), (x - 4, cy - 7), (x + 4, cy + 7)))
    layout.blit_line(s, raw_text(str(count)), (x + 7, cy - 9, 16, 18),
                     config.COLOR_WARN, size=14)


def feed_entries(boat) -> list:
    """The boat log as event-band entries (oldest first)."""
    if boat is None:
        return []
    return [FeedEntry(row.get("stamp") or "--:--", row["category"], row["text"])
            for row in boat.feed]


def telemetry_rows(game, boat) -> list:
    """``(label_key, value, level, compact)`` of the boat, like the frigate's."""
    if boat is None:
        return []
    sub = boat.sub
    course_speed = message("telemetry.value.course_speed",
                           course=f"{sub.course % 360.0:03.0f}", speed=f"{sub.speed:.1f}")
    depth = message("uboot.telemetry.value.depth", depth=_fmt(sub.depth),
                    order=_fmt(sub.order_depth))
    noise = message("telemetry.value.noise_cavitating" if sub.cavitating
                    else "telemetry.value.noise", noise=f"{sub.noise_level() * 100:.0f}")
    battery = _battery_fraction(sub)
    battery_text = (message("telemetry.value.percent", value=f"{battery * 100:.0f}")
                    if battery is not None else message("uboot.telemetry.value.none"))
    stores = sub.weapon_battery
    torpedoes = message("telemetry.value.count", count=int(sub.torpedoes_left),
                        total=int(stores.capacity_total) if stores is not None
                        else int(sub.torpedoes_left))
    damage = message("telemetry.value.percent", value=f"{sub.damage:.0f}")
    return [
        ("uboot.telemetry.course_speed", course_speed, "ok", course_speed),
        ("uboot.telemetry.depth", depth, "ok", message(
            "uboot.telemetry.value.depth_short", depth=_fmt(sub.depth))),
        ("uboot.telemetry.noise", noise, "warn" if sub.cavitating else "ok", noise),
        ("uboot.telemetry.battery", battery_text,
         "danger" if battery is not None and battery < .15 else
         "warn" if battery is not None and battery < .3 else "ok", battery_text),
        ("uboot.telemetry.torpedoes", torpedoes,
         "warn" if sub.torpedoes_left <= 0 else "ok", torpedoes),
        ("uboot.telemetry.damage", damage,
         "danger" if sub.damage >= 50 else "warn" if sub.damage > 0 else "ok", damage),
    ]


def draw_bottom(game, boat) -> None:
    game.draw_bottom_panel(feed_entries(boat), telemetry_rows(game, boat),
                           heading="uboot.local.log", ticker_keys=TELEMETRY_TICKER_KEYS,
                           ticker_hint="")


# --- chart ---------------------------------------------------------------------

def _contacts(boat):
    return sorted(boat.station.sonar.active_contacts(), key=lambda item: item.id)


def _contact_bearing(contact):
    return (contact.passive_bearing if contact.passive_bearing is not None
            else contact.bearing)


def _contact_position(boat, contact, now):
    fresh = (contact.observed_x is not None and contact.observed_y is not None
             and contact.range_source in ("ping", "tma", "visual")
             and 0 <= now - contact.range_seen < config.SONAR_CONTACT_LOST_S)
    return (contact.observed_x, contact.observed_y) if fresh else None


def _label(surface, game, text, pos, color, chart) -> None:
    from src.ui.map_view import _map_label
    _map_label(surface, game, text, pos, color, chart)


def _own_torpedoes(game, sub):
    return sorted((torpedo for torpedo in game.enemy_torpedoes
                   if torpedo.launch_platform_id == sub.id and torpedo.state == "RUN"),
                  key=lambda item: item.id)


def _draw_chart_overlays(game, boat, view, r) -> None:
    s = game.screen
    sub = boat.sub
    bx, by = view.world_to_screen(sub.x, sub.y)
    selected = boat.station.selected_contact
    unknown = nato_symbols.AFFILIATION_COLORS["UNKNOWN"]
    # Own sonar contacts: a fix symbol where a fresh ping/TMA range exists,
    # otherwise the measured bearing from the boat.
    for contact in _contacts(boat):
        is_selected = contact is selected
        color = config.COLOR_WARN if is_selected else unknown
        label = raw_text(f"K{contact.id:02d}")
        position = _contact_position(boat, contact, game.sim_t)
        if position is not None:
            px, py = view.world_to_screen(*position)
            lines.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
                             (int(px), int(py)), 1)
            domain = _CLASS_DOMAIN.get(contact.player_class, "UNKNOWN")
            nato_symbols.draw_symbol(s, (px, py), "UNKNOWN", domain, 16,
                                     selected=is_selected)
            if contact.range_source == "tma":
                nato_symbols.draw_motion_vector(
                    s, (px, py), contact.tma_course, contact.tma_speed, view.scale,
                    color, font=game.font, max_px=120)
            _label(s, game, label, (int(px) + 11, int(py) - 20), color, r)
            continue
        bearing = _contact_bearing(contact)
        if bearing is None:
            continue
        rad = math.radians(bearing)
        length = 320 if is_selected else 260
        ex, ey = bx + length * math.sin(rad), by - length * math.cos(rad)
        lines.line(s, color, (int(bx), int(by)), (int(ex), int(ey)),
                         2 if is_selected else 1)
        lx, ly = bx + 90 * math.sin(rad), by - 90 * math.cos(rad)
        _label(s, game, label, (int(lx) + 6, int(ly) - 8), color, r)
    draw_esm_chart(game, boat, view, r)
    draw_intercept_lines(game, boat, view, bx, by)
    draw_report_chart(game, boat, view)
    _draw_mission_goal(game, view)
    # Own torpedoes in the water (commanded own weapons).
    for index, torpedo in enumerate(_own_torpedoes(game, sub), start=1):
        px, py = view.world_to_screen(torpedo.x, torpedo.y)
        ang = math.radians(torpedo.course - 90.0)
        lines.line(s, config.COLOR_WARN, (int(px), int(py)),
                         (int(px + 10 * math.cos(ang)), int(py + 10 * math.sin(ang))), 2)
        pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)
        _label(s, game, raw_text(f"T{index}"), (int(px) + 10, int(py) - 22),
               config.COLOR_WARN, r)
    # Tube firing arc relative to the bow (own-ship truth).
    launcher = (sub.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
                if sub.weapon_battery is not None else None)
    if launcher is not None and launcher.arc_width_deg < 360.0:
        for edge in (-0.5, 0.5):
            ang = math.radians(sub.course + launcher.arc_center_deg
                               + edge * launcher.arc_width_deg - 90.0)
            lines.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
                             (int(bx + 70 * math.cos(ang)), int(by + 70 * math.sin(ang))), 1)
    # The boat: ordered course, heading, NATO subsurface symbol, motion vector.
    target = math.radians(sub.order_course - 90.0)
    lines.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
                     (int(bx + 42 * math.cos(target)), int(by + 42 * math.sin(target))), 1)
    layout.blit_line(s, message("map.target_course",
                                           course=f"{sub.order_course:03.0f}"),
                     (int(bx) + 12, int(by) + 12, 124, 18), config.COLOR_TEXT_DIM, size=12)
    color = nato_symbols.draw_symbol(s, (bx, by), "FRIEND", "SUBSURFACE", 20)
    heading = math.radians(sub.course - 90.0)
    lines.line(s, color, (int(bx), int(by)),
                     (int(bx + 16 * math.cos(heading)), int(by + 16 * math.sin(heading))), 2)
    nato_symbols.draw_motion_vector(s, (bx, by), sub.course, sub.speed, view.scale,
                                    config.COLOR_OK, max_px=120)


def _draw_mission_goal(game, view) -> None:
    """A boat mission's goal area from the boat's orders (own knowledge)."""
    from src.core import boat_missions
    point = boat_missions.goal(game)
    if point is None:
        return
    s = game.screen
    px, py = view.world_to_screen(point["x"], point["y"])
    radius = max(6, int(point["radius_nm"] * view.scale))
    pygame.draw.circle(s, config.COLOR_OK, (int(px), int(py)), radius, 2)
    layout.blit_line(s, "uboot.chart.goal", (int(px) + radius + 4, int(py) - 9, 80, 18),
                     config.COLOR_OK, size=12)


def _draw_mission_line(game, boat, r) -> None:
    """The boat's orders in one line over the chart's top edge."""
    from src.core import boat_missions
    if boat_missions.mode(game) is None:
        return
    rect = pygame.Rect(r[0] + 8, r[1] + 6, min(560, r[2] - 16), 22)
    pygame.draw.rect(game.screen, config.COLOR_OVERLAY_BG, rect)
    layout.blit_line(game.screen, boat_missions.objective(game, boat), rect.inflate(-8, 0),
                     config.COLOR_OK, size=15)


def draw_chart(game, boat) -> None:
    s = game.screen
    r = config.MAP_RECT
    pygame.draw.rect(s, chart_background(game), r)
    if boat is None:
        layout.blit_block(s, "uboot.local.no_boat", r[0] + 40, r[1] + 40, r[2] - 80, 60,
                          config.COLOR_WARN, size=20)
        pygame.draw.rect(s, config.COLOR_GEO_GRID, r, 1)
        return
    view = chart_view(game, boat)
    with layout.clip_to(s, r):
        draw_chart_geography(game, view, r)
        draw_plot(game.screen, game, view, r, layer=boat.plot, own=boat.sub)
        _draw_chart_overlays(game, boat, view, r)
    draw_chart_frame(game, view, r, boat.chart_follow)
    _draw_mission_line(game, boat, r)


# --- station panel -----------------------------------------------------------

def _battery_color(fraction):
    return (config.COLOR_DANGER if fraction < .15 else
            config.COLOR_WARN if fraction < .3 else config.COLOR_OK)


def _battery_fraction(sub):
    endurance = sub.endurance
    if endurance is None or not endurance.profile.battery_capacity_kwh:
        return None
    return max(0.0, min(1.0, endurance.battery_kwh / endurance.profile.battery_capacity_kwh))


def threats(game, boat) -> list:
    """``(text, level)`` for the threat bar, most urgent first."""
    return [(text, level) for text, level, _fresh in threat_rows(game, boat)]


def threat_rows(game, boat) -> list:
    """``(text, level, fresh)``: stale ping/ESM warnings are not fresh."""
    sub = boat.sub
    rows = []
    alarms = sub.memory
    torpedo_age = alarms["last_torpedo_age"]
    crew = sub.crew
    if math.isfinite(torpedo_age) and torpedo_age < ALARM_WINDOW_S:
        if crew is not None and crew.torpedo_bearing is not None:
            rows.append((message("uboot.threat.torpedo_bearing", age=_fmt(torpedo_age),
                                 bearing=f"{crew.torpedo_bearing:03.0f}"), "danger", True))
        else:
            rows.append((message("uboot.threat.torpedo", age=_fmt(torpedo_age)), "danger", True))
    if sub.damage >= 50:
        rows.append((message("uboot.threat.damage", value=_fmt(sub.damage)), "danger", True))
    control = sub.damage_control
    if not control.power():
        rows.append((message("uboot.threat.power"), "danger", True))
    burning = [name for name, c in zip(COMPARTMENTS, control.compartments) if c.fire > 0.0]
    if burning:
        rows.append((message("uboot.threat.fire",
                             compartment=message(f"uboot.compartment.{burning[0]}")), "danger", True))
    leaking = [name for name, c in zip(COMPARTMENTS, control.compartments) if c.leak > 0.0]
    if leaking:
        rows.append((message("uboot.threat.leak",
                             compartment=message(f"uboot.compartment.{leaking[0]}")), "warn", True))
    ping_age = alarms["last_ping_age"]
    if math.isfinite(ping_age) and ping_age < ALARM_WINDOW_S:
        if crew is not None and crew.ping_bearing is not None:
            rows.append((message("uboot.threat.ping_bearing", age=_fmt(ping_age),
                                 bearing=f"{crew.ping_bearing:03.0f}"), "warn",
                         ping_age < THREAT_FRESH_S))
        else:
            rows.append((message("uboot.threat.ping", age=_fmt(ping_age)), "warn",
                         ping_age < THREAT_FRESH_S))
    if crew is not None and crew.esm:
        bearing, _quality, _age = crew.esm[0]
        newest = min(age for _bearing, _quality, age in crew.esm)
        rows.append((message("uboot.threat.esm", bearing=f"{bearing:03.0f}",
                             count=len(crew.esm)), "warn", newest < THREAT_FRESH_S))
    if sub.cavitating:
        rows.append((message("uboot.threat.cavitation"), "warn", True))
    if sub.beyond_test_depth():
        rows.insert(0, (message("uboot.threat.overdepth", depth=_fmt(sub.depth),
                                test=_fmt(sub.stype.max_depth_m),
                                crush=_fmt(sub.crush_depth_m)), "danger", True))
    ahead = crew.obstacle_ahead_nm if crew is not None else None
    if ahead is not None and sub.order_speed > 0.0:
        rows.append((message("uboot.threat.obstacle", distance=f"{ahead:.1f}"), "warn", True))
    battery = _battery_fraction(sub)
    if battery is not None and battery < .15:
        rows.append((message("uboot.threat.battery", value=_fmt(battery * 100)), "warn", True))
    return rows


def _draw_threat_bar(s, game, boat, x, y, w) -> int:
    """The alarm box, only while a threat is fresh; else nothing (height 0)."""
    rows = [(text, level) for text, level, fresh in threat_rows(game, boat) if fresh]
    if not rows:
        return 0
    text, level = rows[0]
    color = config.COLOR_DANGER if level == "danger" else config.COLOR_WARN
    height = 54 if len(rows) > 1 else 38
    pygame.draw.rect(s, config.COLOR_ALARM_BG, (x, y, w, height))
    pygame.draw.rect(s, color, (x, y, w, height), 2)
    layout.blit_line(s, text, (x + 10, y + 5, w - 20, 28), color, size=20, align="center")
    if len(rows) > 1:
        more = message("bridge.line.more", threats=raw_text(" | ".join(
            str(localize(item)) for item, _level in rows[1:])))
        layout.blit_line(s, more, (x + 10, y + 33, w - 20, 20), config.COLOR_WARN,
                         size=16, align="center")
    return height


def _dashed_hline(s, color, x0, x1, y, dash=6) -> None:
    for x in range(int(x0), int(x1), dash * 2):
        lines.line(s, color, (x, y), (min(x + dash, int(x1)), y), 1)


def draw_depth_ladder(s, game, boat, rect) -> None:
    """Water column under the boat: depth, order, safe depth, layer, seabed."""
    sub = boat.sub
    x, y, w, h = rect
    if h < 40:
        return
    bottom = game.world.depth_m(sub.x, sub.y)
    safe = sub.safe_depth_m(game.world)
    profile = boat.station.sonar.bt_profile
    layer = profile["thermocline_m"] if profile else None
    scale_max = max(100.0, bottom if math.isfinite(bottom) else 0.0,
                    sub.crush_depth_m, sub.depth, sub.order_depth) * 1.08
    column = pygame.Rect(x + 60, y + 4, max(40, w - 60 - 200), h - 8)

    def depth_y(value):
        return column.y + int(column.h * max(0.0, min(1.0, value / scale_max)))

    for index in range(column.h):
        shade = index / max(1, column.h - 1)
        color = tuple(int(a + (b - a) * shade)
                      for a, b in zip(config.COLOR_SHALLOW, config.COLOR_DEEP))
        lines.line(s, color, (column.x, column.y + index),
                         (column.right - 1, column.y + index))
    if math.isfinite(bottom) and bottom < scale_max:
        floor = depth_y(bottom)
        pygame.draw.rect(s, config.COLOR_LAND, (column.x, floor, column.w,
                                                column.bottom - floor))
        lines.line(s, config.COLOR_LAND_EDGE, (column.x, floor),
                         (column.right - 1, floor), 2)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, column, 1)
    step = 100 if scale_max <= 600 else 200 if scale_max <= 1200 else 500
    for value in range(0, int(scale_max) + 1, step):
        ty = depth_y(value)
        lines.line(s, config.COLOR_TEXT_DIM, (column.x - 5, ty), (column.x, ty), 1)
        layout.blit_line(s, raw_text(f"{value}"), (x, ty - 8, 52, 16),
                         config.COLOR_TEXT_DIM, size=12, align="right")
    legend_x = column.right + 12
    marks = []
    if layer is not None:
        ly = depth_y(layer)
        _dashed_hline(s, (110, 200, 220), column.x, column.right, ly)
        marks.append((ly, message("uboot.ladder.layer", depth=_fmt(layer)), (110, 200, 220)))
    sy = depth_y(safe)
    _dashed_hline(s, config.COLOR_DANGER, column.x, column.right, sy)
    _dashed_hline(s, config.COLOR_DANGER, column.x, column.right, sy + 1)
    marks.append((sy, message("uboot.ladder.safe", depth=_fmt(safe)), config.COLOR_DANGER))
    cy = depth_y(sub.crush_depth_m)
    lines.line(s, config.COLOR_DANGER, (column.x, cy), (column.right - 1, cy), 2)
    marks.append((cy, message("uboot.ladder.crush", depth=_fmt(sub.crush_depth_m)),
                  config.COLOR_DANGER))
    oy = depth_y(sub.order_depth)
    _dashed_hline(s, config.COLOR_TEXT, column.x, column.right, oy, dash=3)
    # Holding the ordered depth: one label for boat and order, not two.
    on_order = abs(sub.order_depth - sub.depth) < 1.0
    if not on_order:
        marks.append((oy, message("uboot.ladder.order", depth=_fmt(sub.order_depth)),
                      config.COLOR_TEXT_DIM))
    if math.isfinite(bottom):
        marks.append((depth_y(min(bottom, scale_max)),
                      message("uboot.ladder.bottom", depth=_fmt(bottom)), config.COLOR_LAND_EDGE))
    # The boat itself: a hull marker at its depth.
    cy = depth_y(sub.depth)
    hull = pygame.Rect(0, 0, 34, 10)
    hull.center = (column.centerx, cy)
    pygame.draw.ellipse(s, nato_symbols.AFFILIATION_COLORS["FRIEND"], hull)
    pygame.draw.rect(s, nato_symbols.AFFILIATION_COLORS["FRIEND"],
                     (hull.centerx - 3, hull.y - 5, 7, 6))
    marks.append((cy, message("uboot.ladder.boat_on_order" if on_order else "uboot.ladder.boat",
                              depth=_fmt(sub.depth)), config.COLOR_TEXT))
    # Legend labels, spread so they never overlap: push down from the top,
    # then back up from the bottom edge so the deepest ones stay inside too.
    pitch = layout.line_pitch(13, 1)
    ordered = sorted(marks, key=lambda item: item[0])
    placed = []
    for mark_y, _text, _color in ordered:
        label_y = max(y, mark_y - pitch // 2)
        if placed and label_y < placed[-1] + pitch:
            label_y = placed[-1] + pitch
        placed.append(label_y)
    limit = y + h - pitch
    for index in range(len(placed) - 1, -1, -1):
        placed[index] = min(placed[index], limit)
        limit = placed[index] - pitch
    for (mark_y, text, color), label_y in zip(ordered, placed):
        lines.line(s, color, (column.right, mark_y), (legend_x - 2, label_y + pitch // 2), 1)
        layout.blit_line(s, text, (legend_x, label_y, x + w - legend_x, pitch), color, size=13)


def _draw_nav_page(s, game, boat, x, y, w, h) -> None:
    sub = boat.sub
    half = (w - 10) // 2
    big, row, small = (layout.line_pitch(28, gap=0), layout.line_pitch(18, gap=0),
                       layout.line_pitch(16, gap=0))
    # Tall enough for every row at the current text size (large text too).
    needed = layout.line_pitch(16, 16, bold=True) + 2 * big + 2 * row + small + 10
    box_h = max(min(176, max(120, h // 2)), min(needed, h - 80))
    nav = layout.box(s, (x, y, half, box_h), "uboot.panel.course_depth",
                     border=config.COLOR_TEXT)
    nx, ny, nw, _ = nav
    layout.blit_line(s, message("bridge.line.course", course=f"{sub.course % 360:03.0f}"),
                     (nx, ny, nw, big), config.COLOR_TEXT, size=28)
    ny += big
    layout.status_line(s, nx, ny, nw, "ui.target_value_short",
                       message("bridge.line.course", course=f"{sub.order_course % 360:03.0f}"),
                       size=18, label_w=80)
    ny += row
    layout.blit_line(s, message("uboot.line.depth", depth=_fmt(sub.depth)),
                     (nx, ny, nw, big), config.COLOR_TEXT, size=28)
    ny += big
    layout.status_line(s, nx, ny, nw, "ui.target_value_short",
                       message("uboot.line.depth", depth=_fmt(sub.order_depth)),
                       size=18, label_w=80)
    ny += row
    bottom = game.world.depth_m(sub.x, sub.y)
    keel = message("uboot.line.under_keel", depth=_fmt(bottom - sub.depth))
    ahead = boat.orders.obstacle_ahead_nm
    if ahead is not None:
        keel = message("uboot.line.keel_obstacle", depth=_fmt(bottom - sub.depth),
                       distance=f"{ahead:.1f}")
    layout.blit_line(s, keel, (nx, ny, nw, small),
                     config.COLOR_WARN if ahead is not None
                     or bottom - sub.depth < config.UBOOT_UNDER_KEEL_WARN_M
                     else config.COLOR_TEXT_DIM, size=16)
    drive = layout.box(s, (x + half + 10, y, half, box_h), "panel.speed_acoustics",
                       border=config.COLOR_WARN if sub.cavitating else config.COLOR_TEXT)
    dx, dy, dw, _ = drive
    layout.blit_line(s, message("bridge.line.speed", speed=f"{sub.speed:.1f}"),
                     (dx, dy, dw, big), config.COLOR_TEXT, size=28)
    dy += big
    layout.status_line(s, dx, dy, dw, "ui.target_value_short",
                       message("bridge.line.speed", speed=f"{sub.order_speed:.1f}"),
                       size=18, label_w=80)
    dy += row
    noise = "bridge.cavitation" if sub.cavitating else message(
        "bridge.line.own_noise", noise=f"{sub.noise_level() * 100:.0f}")
    layout.blit_line(s, noise, (dx, dy, dw, row),
                     config.COLOR_DANGER if sub.cavitating else config.COLOR_OK, size=18)
    dy += row
    battery = _battery_fraction(sub)
    phase = sub.endurance.phase if sub.endurance is not None else None
    if battery is not None:
        layout.gauge(s, (dx, dy, dw, small + 8), battery, label="uboot.label.battery",
                     value=message("uboot.line.battery_value", value=_fmt(battery * 100),
                                   phase=(display_message("endurance_phase", phase)
                                          if phase else raw_text("--"))),
                     color=_battery_color(battery))
        dy += small + 10
    modes = [key for key, on in (("uboot.mode.silent", boat.orders.silent),
                                 ("uboot.mode.snorkel", sub.snorkeling),
                                 ("uboot.mode.bottom", boat.orders.bottomed),
                                 ("uboot.mode.mast", boat.orders.mast)) if on]
    quiet = boat.orders.quiet_active(sub)
    layout.blit_line(s, message("uboot.line.modes", modes=raw_text(" · ".join(
        str(localize(key)) for key in modes)) if modes else localize("uboot.mode.none")),
                     (dx, dy, dw, small),
                     config.COLOR_OK if quiet else config.COLOR_TEXT_DIM, size=16)
    ladder_y = y + box_h + 10
    ladder_h = y + h - ladder_y
    if ladder_h >= 70:
        inner = layout.box(s, (x, ladder_y, w, ladder_h), "uboot.panel.depth_ladder")
        draw_depth_ladder(s, game, boat, inner)


def tube_line(sub, busy_only=False):
    """``1 ready · 2 dry · 3 loading 40 s · 4 empty`` (localized); with
    ``busy_only`` the ready tubes are left out (``None`` when all are ready)."""
    parts = []
    for index, (state, left) in enumerate(opfor.tube_states(sub), start=1):
        if busy_only and state == "flooded":
            continue
        parts.append(message(f"uboot.tube.{state}", tube=index,
                             seconds=_fmt(left, "{:.0f}")))
    if busy_only and not parts:
        return None
    return raw_text(" · ".join(str(localize(part)) for part in parts)) if parts \
        else raw_text("--")


def _draw_weapons_page(s, game, boat, x, y, w, h) -> None:
    sub = boat.sub
    battery = sub.weapon_battery
    box_h = min(172, h // 2)
    fire = layout.box(s, (x, y, w, box_h), "uboot.panel.fire_control",
                      border=config.COLOR_TEXT)
    fx, fy, fw, _ = fire
    reason = sub.fire_readiness()
    layout.blit_line(s, message("uboot.local.row.fire", state=message(
        "uboot.local.fire_ready" if reason is None else f"uboot.reason.{reason}")),
        (fx, fy, fw, 30), config.COLOR_OK if reason is None else config.COLOR_WARN, size=24)
    half = (fw - 10) // 2
    layout.status_line(s, fx, fy + 36, half, "uboot.label.torpedoes",
                       raw_text(f"{int(sub.torpedoes_left)}"), size=17, label_w=150)
    layout.status_line(s, fx, fy + 62, half, "uboot.label.tubes_ready",
                       raw_text(f"{opfor.tubes_flooded(sub)}"
                                f"/{int(battery.mount_count) if battery else 0}"),
                       size=17, label_w=150)
    reload_s = battery.next_reload_s if battery is not None and battery.loading_count else None
    layout.status_line(s, fx + half + 10, fy + 36, half, "uboot.label.reload",
                       message("uboot.value.seconds", value=_fmt(reload_s))
                       if reload_s else raw_text("--"), size=17, label_w=150)
    decoys = (int(sub.countermeasure_store.remaining_total)
              if sub.countermeasure_store is not None else 0)
    layout.status_line(s, fx + half + 10, fy + 62, half, "uboot.label.decoys",
                       raw_text(f"{decoys}"), size=17, label_w=150)
    layout.status_line(s, fx, fy + 88, half, "uboot.label.blow",
                       message("common.yes" if sub.blow_available else "common.no"),
                       size=17, label_w=150)
    orders = boat.orders
    wired = sum(1 for wire in orders.wires.values() if wire.active)
    layout.blit_line(s, message(
        "uboot.line.fire_presets",
        depth=_fmt(orders.torpedo_depth) if orders.torpedo_depth else message("uboot.value.auto_depth"),
        salvo=orders.salvo, wires=wired),
        (fx + half + 10, fy + 88, half, 20), config.COLOR_TEXT_DIM, size=15)
    busy = tube_line(sub, busy_only=True)
    if busy is not None:
        # Only tubes that are not ready; "tubes ready n/m" covers the rest.
        layout.blit_line(s, message("uboot.line.tubes", tubes=busy),
                         (fx, fy + 112, fw, 20), config.COLOR_WARN, size=15)
    contacts_y = y + box_h + 10
    listing = layout.box(s, (x, contacts_y, w, y + h - contacts_y), "uboot.local.contacts")
    lx, ly, lw, lh = listing
    selected = boat.station.selected_contact
    rows = []
    for contact in _contacts(boat)[:CONTACT_ROWS]:
        position = _contact_position(boat, contact, game.sim_t)
        distance = (math.hypot(position[0] - sub.x, position[1] - sub.y)
                    if position is not None else None)
        rows.append((contact is selected, message(
            "uboot.local.contact_row", marker=">" if contact is selected else " ",
            label=raw_text(f"K{contact.id:02d}"),
            bearing=_fmt(_contact_bearing(contact), "{:03.0f}"),
            range=_fmt(distance, "{:.1f}"),
            quality=_fmt(max(contact.quality, contact.confidence) * 100.0, "{:.0f}"),
            classification=display_value("classification", contact.player_class)
            if contact.player_class in config.PLAYER_CLASSES
            else message("uboot.local.unclassified"))))
    if not rows:
        layout.blit_line(s, "uboot.local.no_contacts", (lx, ly, lw, 22),
                         config.COLOR_TEXT_DIM, size=16)
        return
    pitch = 24
    for index, (is_selected, text) in enumerate(rows):
        row_y = ly + index * pitch
        if row_y + pitch > ly + lh:
            break
        if is_selected:
            pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, (lx - 4, row_y, lw + 8, pitch - 2))
        layout.blit_line(s, text, (lx, row_y + 2, lw, pitch - 4),
                         config.COLOR_WARN if is_selected else config.COLOR_TEXT, size=16)


# Key legend of each station page (only keys that station may use).
_FOOTERS = {
    ("uboot", "UBOOT_NAV"): (("C", "uboot.footer.course"), ("V", "uboot.footer.speed"),
                             ("D", "uboot.footer.depth"), ("U/J/H", "uboot.footer.presets")),
    ("uboot", "UBOOT_WEAPONS"): (("↑/↓", "uboot.footer.contact"), ("G", "uboot.footer.silent"),
                                 ("Shift+G", "uboot.footer.bottom"),
                                 ("Q/E", "uboot.footer.chart")),
    ("uboot", "UBOOT_SCOPE"): (("←/→", "uboot.footer.scope_turn"),
                               ("help.key.enter", "uboot.footer.stadimeter"),
                               ("P", "uboot.footer.mast"), ("Q/E", "uboot.footer.chart")),
    ("uboot_esm", "UBOOT_SCOPE"): (("←/→", "uboot.footer.scope_turn"),
                                   ("help.key.enter", "uboot.footer.stadimeter"),
                                   ("P", "uboot.footer.mast")),
    ("uboot", "UBOOT_THREAT"): (("I", "uboot.footer.evade"), ("J", "uboot.footer.below_layer"),
                                ("G", "uboot.footer.silent"), ("P", "uboot.footer.mast")),
    ("uboot_nav", "UBOOT_THREAT"): (("I", "uboot.footer.evade"),
                                    ("J", "uboot.footer.below_layer"),
                                    ("Shift+G", "uboot.footer.bottom")),
    ("uboot_nav", "UBOOT_NAV"): (("C", "uboot.footer.course"), ("D", "uboot.footer.depth"),
                                 ("U/J/H", "uboot.footer.presets"),
                                 ("Shift+G", "uboot.footer.bottom")),
    # At most four main keys per page; fire bearing, decoy and flooding are in F1.
    ("uboot_weapons", "UBOOT_WEAPONS"): (("↑/↓", "uboot.footer.contact"),
                                         ("help.key.uboot_fire", "uboot.footer.fire"),
                                         ("W", "uboot.footer.wire"),
                                         ("M", "uboot.footer.tube_load")),
    ("uboot_radio", "UBOOT_RADIO"): (("help.key.enter", "uboot.footer.radio_send"),
                                     ("P", "uboot.footer.mast"), ("Q/E", "uboot.footer.chart")),
    ("uboot_engine", "UBOOT_ENGINE"): (("+/-", "uboot.footer.telegraph"),
                                       ("G", "uboot.footer.silent"),
                                       ("N", "uboot.footer.snorkel"),
                                       ("help.key.uboot_blow", "uboot.footer.blow")),
    ("uboot_esm", "UBOOT_ESM"): (("P", "uboot.footer.mast"), ("↑/↓", "uboot.footer.esm_select"),
                                 ("←/→", "uboot.footer.esm_classify"),
                                 ("help.key.enter", "uboot.footer.esm_plot")),
    ("uboot_engine", "UBOOT_SUPPLY"): (("R", "uboot.footer.charge_rate"),
                                       ("A", "uboot.footer.absorber"),
                                       ("O", "uboot.footer.o2_candle"),
                                       ("N", "uboot.footer.snorkel")),
    ("uboot_engine", "UBOOT_BALLAST"): (("↑/↓", "uboot.footer.regulating"),
                                        ("←/→", "uboot.footer.trim"),
                                        ("Z", "uboot.footer.trim_auto")),
    ("uboot_engine", "UBOOT_DAMAGE"): (("↑/↓ ←/→", "uboot.footer.dc_pick"),
                                       ("help.key.enter", "uboot.footer.dc_team"),
                                       ("I", "uboot.footer.dc_bulkhead"),
                                       ("M", "uboot.footer.watch")),
}


def draw_command_panel(game, boat) -> None:
    s = game.screen
    station = uboot_local.local_station(game)
    pages = station_pages(station)
    page = boat.command_page % len(pages) if boat is not None else 0
    r, _y = _panel(game, title=f"uboot.panel.station.{station}")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page)
    top = _station_content_top(station_rect, len(pages))
    x, w = r[0] + 14, r[2] - 28
    if boat is None:
        layout.blit_block(s, "uboot.local.no_boat", x, top + 10, w, 60,
                          config.COLOR_WARN, size=20)
        return
    alarm_h = _draw_threat_bar(s, game, boat, x, top, w)
    content_y = top + alarm_h + 12
    content_h = station_rect.bottom - 30 - content_y
    if uboot_local.station_remote(game):
        layout.blit_block(s, message("uboot.local.station_remote",
                                     station=message(f"station.{station}")),
                          x, content_y, w, 50, config.COLOR_WARN, size=18)
        content_y += 54
        content_h -= 54
    name = pages[page]
    drawer = {"UBOOT_NAV": _draw_nav_page, "UBOOT_WEAPONS": _draw_weapons_page,
              "UBOOT_ENGINE": _draw_engine_page, "UBOOT_SUPPLY": _draw_supply_page,
              "UBOOT_ESM": _draw_esm_page, "UBOOT_BALLAST": draw_ballast_page,
              "UBOOT_DAMAGE": draw_damage_page,
              "UBOOT_SCOPE": draw_scope_page, "UBOOT_THREAT": draw_threat_page,
              "UBOOT_RADIO": draw_radio_page}[name]
    drawer(s, game, boat, x, content_y, w, content_h)
    specs = tuple(
        (key, "uboot.footer.mast_down" if text == "uboot.footer.mast" and boat.orders.mast
         else "uboot.footer.snorkel_down" if text == "uboot.footer.snorkel" and boat.sub.snorkeling
         else text) for key, text in _FOOTERS[(station, name)])
    _footer(s, (x, station_rect.bottom - 26, w, 20), specs)


def _draw_engine_page(s, game, boat, x, y, w, h) -> None:
    """Engine room: plant console (dials and lamps), telegraph and water column."""
    sub = boat.sub
    box_h = max(150, min(270, h - 80 - 100))
    px, py, pw, ph = layout.box(s, (x, y, w, box_h), "uboot.panel.plant",
                                border=config.COLOR_WARN if sub.cavitating else config.COLOR_TEXT)
    battery = _battery_fraction(sub)
    phase = sub.endurance.phase if sub.endurance is not None else None
    maximum = max(1.0, sub.motion.maximum_speed_kn)
    noise = sub.noise_level()
    specs = [dict(value=abs(sub.speed), lo=0.0, hi=maximum, order=abs(sub.order_speed),
                  text=message("bridge.line.speed", speed=f"{sub.speed:.1f}"),
                  label="uboot.dial.speed")]
    if battery is not None:
        specs.append(dict(value=battery * 100, lo=0.0, hi=100.0,
                          zones=((0.0, 15.0, config.COLOR_DANGER), (15.0, 30.0, config.COLOR_WARN)),
                          text=raw_text(f"{battery * 100:.0f} %"), label="uboot.label.battery"))
    else:
        specs.append(dict(value=sub.depth, lo=0.0, hi=max(1.0, sub.crush_depth_m),
                          order=sub.order_depth,
                          zones=((sub.stype.max_depth_m, sub.crush_depth_m, config.COLOR_DANGER),),
                          text=raw_text(f"{sub.depth:.0f} m"), label="uboot.dial.depth"))
    specs.append(dict(value=noise, lo=0.0, hi=1.0, zones=((0.85, 1.0, config.COLOR_DANGER),),
                      text=raw_text(f"{noise * 100:.0f} %"), label="uboot.dial.noise"))
    snorkel = bool(sub.snorkeling)
    lamps = [
        ("uboot.mode.silent", "", "on" if boat.orders.silent else "off"),
        ("uboot.mode.snorkel", "", "caution" if snorkel else "off"),
        ("uboot.mode.bottom", "", "caution" if boat.orders.bottomed else "off"),
        ("engine.lamp.cavitation", "", "alarm" if sub.cavitating else "off"),
        ("uboot.label.blow", "common.yes" if sub.blow_available else "common.no",
         "on" if sub.blow_available else "alarm"),
        (display_message("endurance_phase", phase), "", "on")
        if phase else ("uboot.lamp.reactor", "common.on", "on"),
    ]
    lamp_h = 2 * 32 + 4
    console.dial_row(s, (px, py, pw, max(60, ph - lamp_h - 8)), specs)
    console.lamp_grid(s, (px, py + ph - lamp_h, pw, lamp_h), lamps, 3)
    tele_y = y + box_h + 10
    ladder_y = tele_y + 80
    if y + h - ladder_y >= 90:
        inner = layout.box(s, (x, ladder_y, w, y + h - ladder_y), "uboot.panel.depth_ladder")
        draw_depth_ladder(s, game, boat, inner)
    telegraph = layout.box(s, (x, tele_y, w, min(70, y + h - tele_y)), "uboot.panel.telegraph")
    tx, ty, tw, _ = telegraph
    steps = opfor.speed_steps(sub)
    width = tw // len(steps)
    # An order between two steps (set directly) outlines the nearest step.
    nearest = min(range(len(steps)), key=lambda i: abs(sub.order_speed - steps[i]))
    exact = abs(sub.order_speed - steps[nearest]) < 0.05
    for index, speed in enumerate(steps):
        current = index == nearest
        rect = pygame.Rect(tx + index * width, ty, width - 4, 26)
        if current and exact:
            pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, rect)
        elif current:
            pygame.draw.rect(s, layout.BRACKET_COLOR, rect, 1)
        layout.blit_line(s, message("uboot.line.telegraph_step",
                                    marker="> " if current and exact else "",
                                    speed=_fmt(speed, "{:.0f}")), rect,
                         config.COLOR_TEXT if current else config.COLOR_TEXT_DIM,
                         size=16, align="center")


def _hours_text(seconds):
    """A forecast time as h:mm (``--`` when none)."""
    if seconds is None or not math.isfinite(seconds):
        return "--"
    minutes = int(round(seconds / 60.0))
    return f"{minutes // 60}:{minutes % 60:02d}"


def _supply_bar(s, x, y, w, label, text, fraction, low, empty) -> None:
    color = (config.COLOR_DANGER if fraction is not None and fraction <= empty else
             config.COLOR_WARN if fraction is not None and fraction <= low else config.COLOR_OK)
    layout.gauge(s, (x, y, w, 30), fraction, label=label, value=text, color=color, size=15)


def _draw_supply_page(s, game, boat, x, y, w, h) -> None:
    """Engine room stores: energy balance, endurance dived by speed, diesel and air."""
    sub = boat.sub
    endurance = sub.endurance
    if endurance is None:
        inner = layout.box(s, (x, y, w, 80), "uboot.panel.energy")
        layout.blit_block(s, "uboot.line.nuclear_plant", inner[0], inner[1], inner[2], inner[3],
                          config.COLOR_TEXT_DIM, size=16)
        return
    profile = endurance.profile
    maximum = sub.motion.maximum_speed_kn
    balance = endurance.forecast(sub.speed, maximum)
    litres = config.UBOOT_DIESEL_L_PER_KWH
    energy_h = max(150, min(250, h // 2))
    ex, ey, ew, eh = layout.box(s, (x, y, w, energy_h), "uboot.panel.energy")
    battery = endurance.battery_kwh / profile.battery_capacity_kwh
    fuel = endurance.fuel_kwh / max(1e-9, endurance.fuel_capacity_kwh)

    def store_level(fraction, low, empty):
        return "alarm" if fraction <= empty else "caution" if fraction <= low else "on"

    columns = [("uboot.label.battery", battery, raw_text(f"{battery * 100:.0f} %"),
                store_level(battery, .2, .03))]
    if profile.aip_power_kw is not None:
        aip = endurance.aip_energy_kwh / max(1e-9, profile.aip_energy_kwh)
        columns.append(("uboot.label.aip", aip, raw_text(f"{aip * 100:.0f} %"),
                        store_level(aip, .1, 0.0)))
    columns.append(("uboot.label.fuel", fuel,
                    message("uboot.value.diesel_m3", value=_fmt(endurance.fuel_kwh * litres / 1000.0, "{:.1f}")),
                    store_level(fuel, config.UBOOT_FUEL_LOW_FRACTION, 0.0)))
    absorber = endurance.air.absorber_left
    columns.append(("uboot.label.absorber", absorber, raw_text(f"{absorber * 100:.0f} %"),
                    store_level(absorber, .25, 0.0)))
    tank_w = 84
    for index, (label, fraction, text, level) in enumerate(columns):
        console.tank(s, (ex + index * tank_w, ey, tank_w - 6, eh), fraction,
                     label=label, text=text, level=level)
    rx = ex + len(columns) * tank_w + 8
    rw = ex + ew - rx
    net = balance["net_kw"]
    full = balance["full_s"] is not None
    readouts = (
        ("uboot.label.balance", message("uboot.value.balance", load=_fmt(balance["load_kw"]),
                                        supply=_fmt(balance["supply_kw"]), net=f"{net:+.0f}"),
         config.COLOR_OK if net >= 0 else config.COLOR_TEXT),
        ("uboot.label.full_in" if full else "uboot.label.empty_in",
         _hours_text(balance["full_s"] if full else balance["empty_s"]), config.COLOR_TEXT),
        ("uboot.label.charge_rate", message(
            "uboot.value.charge", rate=message(f"uboot.charge.{endurance.charge_rate}"),
            kw=_fmt(profile.generator_power_kw * config.UBOOT_CHARGE_POWER[endurance.charge_rate])),
         config.COLOR_TEXT),
        ("uboot.label.battery", message("uboot.value.kwh", value=_fmt(endurance.battery_kwh),
                                        capacity=_fmt(profile.battery_capacity_kwh)), config.COLOR_TEXT),
    )
    row = layout.font(16).get_linesize()
    pitch = max(2 * row + 2, min(eh // len(readouts), 2 * row + 12))
    for index, (label, value, color) in enumerate(readouts):
        ry = ey + index * pitch
        if ry + 2 * row > ey + eh:
            break
        layout.blit_line(s, label, (rx, ry, rw, row), config.COLOR_TEXT_DIM, size=16)
        layout.blit_line(s, value, (rx, ry + row, rw, row), color, size=16)
    air = endurance.air
    air_y = y + energy_h + 8
    half = (w - 8) // 2
    table_h = y + h - air_y
    tx, ty, tw, th = layout.box(s, (x, air_y, half, table_h), "uboot.panel.endurance")
    speeds = sorted({*(step for step in config.UBOOT_SPEED_STEPS_KN if 0.0 < step < maximum),
                     maximum})
    # Hours dived at each speed as bars against the slowest (longest) one.
    hours_by_speed = [(speed, min(endurance.submerged_hours(speed, maximum), 9999.0))
                      for speed in speeds]
    longest = max((hours for _speed, hours in hours_by_speed), default=1.0) or 1.0
    pitch = layout.line_pitch(16, 0) + 14
    for index, (speed, hours) in enumerate(hours_by_speed):
        if (index + 1) * pitch > th:
            break
        ordered = abs(speed - sub.order_speed) < .05
        layout.gauge(s, (tx, ty + index * pitch, tw, pitch - 4), hours / longest,
                     label=message("bridge.line.speed", speed=_fmt(speed)),
                     value=message("uboot.value.endurance_bar", hours=_fmt(hours, "{:.1f}"),
                                   range=_fmt(min(hours * speed, 99999.0))),
                     color=config.COLOR_WARN if ordered else config.COLOR_OK, size=16)
    level = air.level()
    ax, ay, aw, ah = layout.box(s, (x + half + 8, air_y, w - half - 8, table_h), "uboot.panel.air",
                                border={"ok": None, "caution": config.COLOR_WARN,
                                        "danger": config.COLOR_DANGER}[level])
    color = {"ok": config.COLOR_TEXT, "caution": config.COLOR_WARN,
             "danger": config.COLOR_DANGER}[level]
    rows = (("uboot.label.o2", _fmt(air.o2_pct, "{:.1f} %")),
            ("uboot.label.co2", _fmt(air.co2_pct, "{:.2f} %")),
            ("uboot.label.air_level", message(f"uboot.air.{level}")),
            ("uboot.label.crew_efficiency", _fmt(air.efficiency() * 100, "{:.0f} %")),
            ("uboot.label.absorber", message("uboot.value.absorber", pct=_fmt(air.absorber_left * 100),
                                             sets=str(air.absorber_sets))),
            ("uboot.label.candles", message("uboot.value.candles", count=str(air.candles),
                                            burning=_hours_text(air.candle_left_s)
                                            if air.candle_left_s > 0 else "--")))
    for index, (label, value) in enumerate(rows):
        if (index + 1) * 20 > ah:
            break
        layout.status_line(s, ax, ay + index * 20, aw, label, value,
                           color=color if index < 3 else None, size=15, label_w=100)


def _alarm_value(age, bearing):
    if not math.isfinite(age) or age >= ALARM_WINDOW_S:
        return message("uboot.value.no_alarm")
    return message("uboot.value.alarm", bearing=_fmt(bearing, "{:03.0f}"), age=_fmt(age))


def esm_selection(boat):
    """The emitter selected on the ESM page (display only), else the newest."""
    emitters = boat.esm.ordered()
    chosen = boat.esm.by_number(boat.esm_selected)
    if chosen is None and emitters:
        chosen = emitters[0]
    return emitters, chosen


def step_esm_selection(boat, delta: int) -> None:
    emitters, chosen = esm_selection(boat)
    if not emitters:
        boat.esm_selected = None
        return
    index = emitters.index(chosen) if chosen in emitters else 0
    chosen = emitters[(index + delta) % len(emitters)]
    boat.esm_selected = boat_esm.emitter_number(chosen.track.track_key)


def _esm_weather(game):
    sea = float(getattr(game.world, "effective_sea_state", game.world.sea_state))
    rain = config.clamp(float(getattr(game.world, "rain_intensity", 0.0)), 0.0, 1.0)
    return sea, rain


def _draw_esm_rose(s, game, boat, rect, threats) -> None:
    """Bearing rose: own heading, each emitter's strobe (live bright, remembered
    faint, a mast threat red) and the alarm bearings (own measurements)."""
    sub = boat.sub
    pygame.draw.rect(s, config.COLOR_GEO_BG, rect)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)
    label_face = layout.font(11)
    label_w, label_h = label_face.size("000")[0], label_face.get_linesize()
    radius = max(20, min(rect.w - 2 * label_w, rect.h - 2 * label_h) // 2 - 6)
    cx, cy = rect.center

    def at(bearing, r):
        rad = math.radians(bearing)
        return int(cx + r * math.sin(rad)), int(cy - r * math.cos(rad))

    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), radius, 1)
    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), radius // 2, 1)
    for bearing in range(0, 360, 30):
        lines.line(s, config.COLOR_TEXT_DIM, at(bearing, radius), at(bearing, radius - 7), 1)
        # Push each label out by its own half extent so none sits on the ring.
        rad = math.radians(bearing)
        reach = radius + 4 + abs(math.sin(rad)) * label_w / 2 + abs(math.cos(rad)) * label_h / 2
        tx, ty = at(bearing, reach)
        layout.blit_line(s, raw_text("N" if bearing == 0 else f"{bearing:03d}"),
                         (tx - label_w // 2 - 2, ty - label_h // 2, label_w + 4, label_h),
                         config.COLOR_TEXT_DIM, size=11, align="center")
    lines.line(s, nato_symbols.AFFILIATION_COLORS["FRIEND"], (cx, cy),
               at(sub.course, radius * .35), 2)
    _, chosen = esm_selection(boat)
    # Emitters on nearly the same bearing get their labels stepped inwards.
    steps, previous, step = {}, None, 0
    for emitter in sorted(boat.esm.ordered(), key=lambda item: item.track.bearing % 360.0):
        bearing = emitter.track.bearing % 360.0
        step = step + 1 if previous is not None and bearing - previous < 8.0 else 0
        steps[id(emitter)], previous = step, bearing
    for emitter in boat.esm.ordered():
        track = emitter.track
        live = boat.esm.live(emitter, game.sim_t)
        color = (config.COLOR_DANGER if emitter in threats else config.COLOR_WARN if live
                 else config.COLOR_TEXT_DIM)
        lines.line(s, color, (cx, cy), at(track.bearing, radius),
                   3 if emitter is chosen else 2 if live else 1)
        lx, ly = at(track.bearing, max(radius * .3, radius * .78 - steps[id(emitter)] * 14))
        layout.blit_line(s, raw_text(boat_esm.emitter_label(track.track_key)),
                         (lx - 18, ly - 8, 36, 16), color, size=12, align="center")
    memory = sub.memory
    for age, bearing, color in ((memory["last_ping_age"], boat.orders.ping_bearing,
                                 config.COLOR_WARN),
                                (memory["last_torpedo_age"], boat.orders.torpedo_bearing,
                                 config.COLOR_DANGER)):
        if bearing is None or not math.isfinite(age) or age >= ALARM_WINDOW_S:
            continue
        end = at(bearing, radius)
        for step in range(0, 10, 2):
            a = (cx + (end[0] - cx) * step / 10, cy + (end[1] - cy) * step / 10)
            b = (cx + (end[0] - cx) * (step + 1) / 10, cy + (end[1] - cy) * (step + 1) / 10)
            lines.line(s, color, a, b, 3)


def _esm_trend_text(emitter, now):
    slope, trend = boat_esm.level_trend(emitter.history, now)
    return "--" if trend is None else f"{localize(message(f'uboot.esm.trend.{trend}'))} {slope:+.1f}"


def _esm_scan_text(emitter):
    reading = boat_esm.scan_reading(emitter.track)
    if reading is None:
        return message("uboot.esm.scan.measuring")
    return message(f"uboot.esm.scan.{reading}", period=f"{emitter.track.revisit_s:.1f}")


def _esm_class_text(game, boat, emitter):
    profile = boat.esm.classified(game, emitter)
    if profile is None:
        return message("uboot.esm.unclassified")
    name = str(game.eloka_emitter_name(emitter.label) or emitter.label.rsplit(".", 1)[-1])[:32]
    return message("uboot.esm.class_fit", name=raw_text(name),
                   fit=message(f"uboot.esm.fit.{boat.esm.fit(game, emitter, emitter.label)}"))


def _draw_esm_page(s, game, boat, x, y, w, h) -> None:
    """Mast & ESM: mast time, the crew's emitter list and the selected
    emitter's evaluation (its own measurements and the crew's cross-fix)."""
    from src.sensors.platform import MAST_DEPTH_M
    esm, orders, now = boat.esm, boat.orders, game.sim_t
    sea, rain = _esm_weather(game)
    mast_range = boat_esm.mast_radar_nm(sea, rain)
    threats = [item for item in esm.ordered() if esm.mast_threat(game, item, now, mast_range)]
    limit = boat_esm.recommended_mast_time_s(sea, rain, bool(threats))
    elapsed = esm.mast_time_s(now)
    over = elapsed is not None and elapsed > limit
    border = (config.COLOR_DANGER if threats else config.COLOR_WARN if orders.mast or over
              else config.COLOR_TEXT)
    first, row = layout.line_pitch(17, 1), layout.line_pitch(15, 1)
    mast_h = layout.line_pitch(16, 16, bold=True) + first + 2 * row + 8
    mast = layout.box(s, (x, y, w, mast_h), "uboot.panel.mast", border=border)
    mx, my, mw, _ = mast
    layout.blit_line(s, message("uboot.line.mast_up" if orders.mast else "uboot.line.mast_down",
                                depth=_fmt(MAST_DEPTH_M)), (mx, my, mw, first),
                     config.COLOR_WARN if orders.mast else config.COLOR_TEXT, size=17)
    layout.blit_line(s, message("uboot.esm.mast_time", elapsed=_fmt(elapsed), limit=_fmt(limit))
                     if elapsed is not None else message("uboot.esm.mast_time_limit",
                                                        limit=_fmt(limit)),
                     (mx, my + first, mw, row),
                     config.COLOR_WARN if over else config.COLOR_TEXT, size=15)
    warning = ("uboot.esm.threat" if threats else "uboot.esm.overtime" if over else None)
    layout.blit_line(s, warning or message("uboot.esm.mast_radar", range=_fmt(mast_range, "{:.1f}"),
                                           wash=_fmt(boat_esm.wash_fraction(sea) * 100)),
                     (mx, my + first + row, mw, row),
                     config.COLOR_DANGER if threats else config.COLOR_WARN if over
                     else config.COLOR_TEXT_DIM, size=15)
    top = y + mast_h + 8
    rose_w = min(w * 2 // 5, 220)
    rose_h = min(rose_w, max(100, h - (top - y) - 170))
    _draw_esm_rose(s, game, boat, pygame.Rect(x, top, rose_w, rose_h), threats)
    memory = boat.sub.memory
    layout.blit_line(s, message("uboot.line.alarm_ping", value=_alarm_value(
        memory["last_ping_age"], orders.ping_bearing)), (x, top + rose_h + 4, rose_w, 18),
        config.COLOR_TEXT, size=13)
    layout.blit_line(s, message("uboot.line.alarm_torpedo", value=_alarm_value(
        memory["last_torpedo_age"], orders.torpedo_bearing)), (x, top + rose_h + 22, rose_w, 18),
        config.COLOR_TEXT, size=13)
    listing = layout.box(s, (x + rose_w + 10, top, w - rose_w - 10, rose_h + 40),
                         "uboot.panel.esm")
    lx, ly, lw, lh = listing
    emitters, chosen = esm_selection(boat)
    if not emitters:
        layout.blit_line(s, "uboot.line.no_esm" if orders.mast else "uboot.line.esm_mast_down",
                         (lx, ly, lw, 22), config.COLOR_TEXT_DIM, size=16)
    for index, emitter in enumerate(emitters):
        row_y = ly + index * 20
        if row_y + 20 > ly + lh:
            break
        track = emitter.track
        live = esm.live(emitter, now)
        color = (config.COLOR_DANGER if emitter in threats else config.COLOR_WARN if live
                 else config.COLOR_TEXT_DIM)
        if emitter is chosen:
            pygame.draw.rect(s, config.COLOR_SONAR_RING, (lx - 2, row_y, lw + 4, 20), 1)
        layout.blit_line(s, message(
            "uboot.esm.row", label=boat_esm.emitter_label(track.track_key),
            bearing=_fmt(track.bearing % 360.0, "{:03.0f}"),
            band=boat_esm.band(track.frequency_hz).upper().replace("_", "/"),
            level=_fmt(track.signal_db), fix="+" if emitter.fix(now) is not None else " "),
            (lx, row_y + 2, lw, 18), color, size=14)
    detail_y = top + rose_h + 48
    detail = layout.box(s, (x, detail_y, w, y + h - detail_y), "uboot.panel.esm_detail")
    dx, dy, dw, dh = detail
    if chosen is None:
        return
    track = chosen.track
    fix = chosen.fix(now)
    rows = [
        (message("uboot.esm.label.signal"), message(
            "uboot.esm.signal", frequency=f"{track.frequency_hz / 1e9:.2f}",
            prf=_fmt(track.prf_hz) if track.prf_hz is not None else "--",
            modulation=display_value("esm_modulation", track.modulation_code))),
        (message("uboot.esm.label.level"), message(
            "uboot.esm.level", level=_fmt(track.signal_db), trend=_esm_trend_text(chosen, now),
            range=_fmt(esm.range_estimate_nm(game, chosen), "{:.1f}"))),
        (message("uboot.esm.label.fix"), message(
            "uboot.esm.fix", x=f"{fix['x']:.1f}", y=f"{fix['y']:.1f}",
            major=f"{fix['major_nm']:.1f}", minor=f"{fix['minor_nm']:.1f}",
            lines=fix["lines"]) if fix is not None else message("uboot.esm.no_fix")),
        (message("uboot.esm.label.class"), _esm_class_text(game, boat, chosen)),
        (message("uboot.esm.label.scan"), _esm_scan_text(chosen)),
    ]
    # One column when every row fits, else the measurements on the left
    # and the crew's reading (class, scan) in a narrower right column.
    split = len(rows) * 20 > dh
    for index, (label, value) in enumerate(rows):
        column, line = (divmod(index, 3) if split else (0, index))
        if (line + 1) * 20 > dh:
            continue
        left_w = dw * 3 // 5 if split else dw
        column_x = dx if column == 0 else dx + left_w + 12
        layout.status_line(s, column_x, dy + line * 20,
                           left_w if column == 0 else dw - left_w - 12, label, value,
                           color=(config.COLOR_WARN if index == 2 and fix is not None
                                  and not fix["consistent"] else None),
                           size=14, label_w=104 if not split else 84 if column == 0 else 72)


def draw_esm_chart(game, boat, view, r) -> None:
    """ESM mapping on the boat's chart: each emitter's latest bearing line
    from where the boat took it and the crew's cross-fix with its ellipse."""
    s = game.screen
    now = game.sim_t
    _, chosen = esm_selection(boat)
    for emitter in boat.esm.ordered():
        if not emitter.history:
            continue
        live = boat.esm.live(emitter, now)
        color = config.COLOR_WARN if live else config.COLOR_TEXT_DIM
        label = raw_text(boat_esm.emitter_label(emitter.track.track_key))
        for row in emitter.history[-(3 if emitter is chosen else 1):]:
            ox, oy = view.world_to_screen(row[1], row[2])
            rad = math.radians(row[3])
            length = 360 if emitter is chosen else 220
            end = (ox + length * math.sin(rad), oy - length * math.cos(rad))
            for step in range(0, 20, 2):
                a = (ox + (end[0] - ox) * step / 20, oy + (end[1] - oy) * step / 20)
                b = (ox + (end[0] - ox) * (step + 1) / 20, oy + (end[1] - oy) * (step + 1) / 20)
                lines.line(s, color, a, b, 2 if emitter is chosen else 1)
        fix = emitter.fix(now)
        if fix is None:
            continue
        px, py = view.world_to_screen(fix["x"], fix["y"])
        major = max(2.0, fix["major_nm"] * view.scale)
        minor = max(2.0, fix["minor_nm"] * view.scale)
        axis = math.radians(fix["axis_deg"])
        points = []
        for step in range(24):
            angle = 2.0 * math.pi * step / 24
            u, v = major * math.cos(angle), minor * math.sin(angle)
            points.append((px + u * math.sin(axis) + v * math.cos(axis),
                           py - u * math.cos(axis) + v * math.sin(axis)))
        pygame.draw.lines(s, config.COLOR_WARN, True, points, 1)
        pygame.draw.rect(s, config.COLOR_WARN, (int(px) - 3, int(py) - 3, 7, 7), 1)
        _label(s, game, label, (int(px) + 8, int(py) - 18), config.COLOR_WARN, r)


def _footer(s, rect, specs) -> None:
    """Key legend like the frigate's, each segment as wide as its text."""
    _shortcut_footer(s, rect, specs)


# --- end of mission and the whole screen ---------------------------------------

def end_text(game, boat) -> str:
    from src.core import boat_debrief
    return "uboot.end." + boat_debrief.outcome(game, boat)


_END_WINS = ("uboot.end.won", "uboot.end.escaped", "uboot.end.survived",
             "uboot.end.trained", "uboot.end.broke_through", "uboot.end.reported",
             "uboot.end.convoy_sunk")


def draw_end_panel(game, boat) -> None:
    s = game.screen
    campaign = game.campaign_end_line()
    extra = 36 if campaign is not None else 0
    rect = pygame.Rect(340, 250, 600, 150 + extra)
    overlay_style.panel(s, rect)
    key = end_text(game, boat)
    layout.blit_line(s, key, (rect.x + 16, rect.y + 20, rect.w - 32, 40),
                     config.COLOR_OK if key in _END_WINS else config.COLOR_WARN,
                     size=28, align="center")
    if campaign is not None:
        # A boat campaign leg: the standing and what comes next.
        layout.blit_line(s, campaign, (rect.x + 16, rect.y + 72, rect.w - 32, 28),
                         config.COLOR_WARN, size=16, align="center")
    layout.blit_block(s, "uboot.end.hint", rect.x + 16, rect.y + 80 + extra, rect.w - 32,
                      56, config.COLOR_TEXT_DIM, size=16, align="center")


def silent_light(s, boat) -> bool:
    """Silent running: the boat rigs for red, dimmed light (display only)."""
    if boat is None or not boat.orders.silent or boat.sub.sunk:
        return False
    s.fill(config.UBOOT_SILENT_LIGHT, special_flags=pygame.BLEND_MULT)
    s.fill(config.UBOOT_SILENT_LIGHT_FLOOR, special_flags=pygame.BLEND_ADD)
    return True


def draw(game) -> None:
    """The whole mission screen while the uConsole plays the submarine."""
    boat = game.opfor
    draw_top_bar(game, boat)
    previous = config.STATION_RECT
    try:
        if game.weather_station_open and boat is not None:
            # Key 0: the weather panel over the whole station area, read
            # from the boat's own instruments and bathythermograph.
            config.STATION_RECT = config.OPZ_STATION_RECT
            with layout.clip_to(game.screen, config.STATION_RECT):
                with game.sonar_perspective(boat.station):
                    draw_weather_station(game)
            game.draw_navigation_input()
            return
        if game.station is Station.SONAR and boat is not None:
            config.STATION_RECT = config.FULL_STATION_RECT
            with layout.clip_to(game.screen, config.STATION_RECT):
                with game.sonar_perspective(boat.station):
                    draw_sonar_view(game)
        else:
            draw_chart(game, boat)
            config.STATION_RECT = config.STATION_PANEL_RECT
            with layout.clip_to(game.screen, config.STATION_RECT):
                draw_command_panel(game, boat)
        draw_bottom(game, boat)
        game.draw_navigation_input()
        silent_light(game.screen, boat)
        if game.game_over and getattr(game, "debrief_open", False):
            from src.ui.debrief_view import draw_debrief
            draw_debrief(game)
        elif game.game_over:
            draw_end_panel(game, boat)
        else:
            # Over the chart's foot, clear of the station panel.
            game.draw_training_hint((10, config.SCREEN_H - 118, 620, 46))
    finally:
        config.STATION_RECT = previous
