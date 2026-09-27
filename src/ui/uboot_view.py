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
from src.core import config, opfor, uboot_local
from src.core.i18n import display_value, localize, message, raw_text
from src.core.station import Station
from src.ui import layout, nato_symbols
from src.ui.feedback import FeedEntry
from src.ui.map_view import draw_chart_frame, draw_chart_geography
from src.ui.sonar_view import draw_sonar_view
from src.ui.stations_view import (_panel, _station_content_top,
                                  draw_station_page_tabs, station_page_tab_at)
from src.ui.uboot_scope import draw_scope_page
from src.ui.viewport import Viewport

UBOOT_PAGES = ("UBOOT_NAV", "UBOOT_WEAPONS", "UBOOT_SCOPE")
# Panel pages of each boat station beside the chart (the sonar room is full screen).
STATION_PAGES = {"uboot": UBOOT_PAGES, "uboot_weapons": ("UBOOT_WEAPONS",),
                 "uboot_engine": ("UBOOT_ENGINE",),
                 "uboot_esm": ("UBOOT_ESM", "UBOOT_SCOPE"),
                 "uboot_nav": ("UBOOT_NAV",)}


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
STATION_TAB_W = 104
CONTACT_ROWS = 10
# Alarms stay on the threat bar this long after the event (s).
ALARM_WINDOW_S = 120.0
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
    pygame.draw.line(s, config.COLOR_SONAR_RING, (0, config.TOP_BAR_H - 1),
                     (config.SCREEN_W, config.TOP_BAR_H - 1), 1)
    sub = boat.sub if boat is not None else None
    # The boat's six stations as tabs (key number and short name); a station a
    # browser crews is marked and not operated from here.
    shown = uboot_local.local_station(game)
    leased = getattr(getattr(game.commander, "server", None), "station_leased", None)
    tabs = station_tab_rects()
    for index, (role, rect) in enumerate(zip(OPFOR_ROLES, tabs)):
        active = role == shown
        remote = bool(leased and leased(role))
        if active:
            pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, rect)
            pygame.draw.line(s, config.COLOR_SONAR_RING, rect.bottomleft,
                             (rect.right - 1, rect.bottom), 2)
        label = message("uboot.tab", number=index + 1, name=message(f"uboot.tab.{role}"))
        layout.blit_line(s, label, rect, config.COLOR_WARN if remote else
                         config.COLOR_TEXT if active else config.COLOR_TEXT_DIM,
                         size=14, align="center")
    text = message("uboot.top.status", scenario=raw_text(game.top_bar_scenario()),
                   time=game.world.format_time(),
                   course=_fmt(sub.course if sub else None, "{:03.0f}"),
                   speed=_fmt(sub.speed if sub else None, "{:.1f}"),
                   depth=_fmt(sub.depth if sub else None))
    left = tabs[-1].right + 12
    layout.blit_line(s, text, (left, 4, config.SCREEN_W - left - 10, config.TOP_BAR_H - 8),
                     config.COLOR_TEXT, size=16, align="right")


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
            pygame.draw.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
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
        pygame.draw.line(s, color, (int(bx), int(by)), (int(ex), int(ey)),
                         2 if is_selected else 1)
        lx, ly = bx + 90 * math.sin(rad), by - 90 * math.cos(rad)
        _label(s, game, label, (int(lx) + 6, int(ly) - 8), color, r)
    # Own torpedoes in the water (commanded own weapons).
    for index, torpedo in enumerate(_own_torpedoes(game, sub), start=1):
        px, py = view.world_to_screen(torpedo.x, torpedo.y)
        ang = math.radians(torpedo.course - 90.0)
        pygame.draw.line(s, config.COLOR_WARN, (int(px), int(py)),
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
            pygame.draw.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
                             (int(bx + 70 * math.cos(ang)), int(by + 70 * math.sin(ang))), 1)
    # The boat: ordered course, heading, NATO subsurface symbol, motion vector.
    target = math.radians(sub.order_course - 90.0)
    pygame.draw.line(s, config.COLOR_TEXT_DIM, (int(bx), int(by)),
                     (int(bx + 42 * math.cos(target)), int(by + 42 * math.sin(target))), 1)
    layout.blit_line(s, message("map.target_course",
                                           course=f"{sub.order_course:03.0f}"),
                     (int(bx) + 12, int(by) + 12, 124, 18), config.COLOR_TEXT_DIM, size=12)
    color = nato_symbols.draw_symbol(s, (bx, by), "FRIEND", "SUBSURFACE", 20)
    heading = math.radians(sub.course - 90.0)
    pygame.draw.line(s, color, (int(bx), int(by)),
                     (int(bx + 16 * math.cos(heading)), int(by + 16 * math.sin(heading))), 2)
    nato_symbols.draw_motion_vector(s, (bx, by), sub.course, sub.speed, view.scale,
                                    config.COLOR_OK, max_px=120)


def draw_chart(game, boat) -> None:
    s = game.screen
    r = config.MAP_RECT
    pygame.draw.rect(s, config.COLOR_GEO_BG, r)
    if boat is None:
        layout.blit_block(s, "uboot.local.no_boat", r[0] + 40, r[1] + 40, r[2] - 80, 60,
                          config.COLOR_WARN, size=20)
        pygame.draw.rect(s, config.COLOR_GEO_GRID, r, 1)
        return
    view = chart_view(game, boat)
    with layout.clip_to(s, r):
        draw_chart_geography(game, view, r)
        _draw_chart_overlays(game, boat, view, r)
    draw_chart_frame(game, view, r, boat.chart_follow)


# --- station panel -----------------------------------------------------------

def _battery_fraction(sub):
    endurance = sub.endurance
    if endurance is None or not endurance.profile.battery_capacity_kwh:
        return None
    return max(0.0, min(1.0, endurance.battery_kwh / endurance.profile.battery_capacity_kwh))


def threats(game, boat) -> list:
    """``(text, level)`` for the threat bar, most urgent first."""
    sub = boat.sub
    rows = []
    alarms = sub.memory
    torpedo_age = alarms["last_torpedo_age"]
    crew = sub.crew
    if math.isfinite(torpedo_age) and torpedo_age < ALARM_WINDOW_S:
        if crew is not None and crew.torpedo_bearing is not None:
            rows.append((message("uboot.threat.torpedo_bearing", age=_fmt(torpedo_age),
                                 bearing=f"{crew.torpedo_bearing:03.0f}"), "danger"))
        else:
            rows.append((message("uboot.threat.torpedo", age=_fmt(torpedo_age)), "danger"))
    if sub.damage >= 50:
        rows.append((message("uboot.threat.damage", value=_fmt(sub.damage)), "danger"))
    ping_age = alarms["last_ping_age"]
    if math.isfinite(ping_age) and ping_age < ALARM_WINDOW_S:
        if crew is not None and crew.ping_bearing is not None:
            rows.append((message("uboot.threat.ping_bearing", age=_fmt(ping_age),
                                 bearing=f"{crew.ping_bearing:03.0f}"), "warn"))
        else:
            rows.append((message("uboot.threat.ping", age=_fmt(ping_age)), "warn"))
    if crew is not None and crew.esm:
        bearing, _quality, _age = crew.esm[0]
        rows.append((message("uboot.threat.esm", bearing=f"{bearing:03.0f}",
                             count=len(crew.esm)), "warn"))
    if sub.cavitating:
        rows.append((message("uboot.threat.cavitation"), "warn"))
    ahead = crew.obstacle_ahead_nm if crew is not None else None
    if ahead is not None and sub.order_speed > 0.0:
        rows.append((message("uboot.threat.obstacle", distance=f"{ahead:.1f}"), "warn"))
    battery = _battery_fraction(sub)
    if battery is not None and battery < .15:
        rows.append((message("uboot.threat.battery", value=_fmt(battery * 100)), "warn"))
    return rows


def _draw_threat_bar(s, game, boat, x, y, w) -> int:
    rows = threats(game, boat)
    if rows:
        text, level = rows[0]
        color = config.COLOR_DANGER if level == "danger" else config.COLOR_WARN
    else:
        text, color = "panel.no_threat", config.COLOR_OK
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


def _bar(s, rect, fraction, color) -> None:
    rect = pygame.Rect(rect)
    pygame.draw.rect(s, config.COLOR_BG, rect)
    if fraction is not None:
        fill = rect.copy()
        fill.w = max(0, int(rect.w * max(0.0, min(1.0, fraction))))
        pygame.draw.rect(s, color, fill)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)


def _dashed_hline(s, color, x0, x1, y, dash=6) -> None:
    for x in range(int(x0), int(x1), dash * 2):
        pygame.draw.line(s, color, (x, y), (min(x + dash, int(x1)), y), 1)


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
                    sub.stype.max_depth_m, sub.depth, sub.order_depth) * 1.08
    column = pygame.Rect(x + 60, y + 4, max(40, w - 60 - 200), h - 8)

    def depth_y(value):
        return column.y + int(column.h * max(0.0, min(1.0, value / scale_max)))

    for index in range(column.h):
        shade = index / max(1, column.h - 1)
        color = tuple(int(a + (b - a) * shade)
                      for a, b in zip(config.COLOR_SHALLOW, config.COLOR_DEEP))
        pygame.draw.line(s, color, (column.x, column.y + index),
                         (column.right - 1, column.y + index))
    if math.isfinite(bottom) and bottom < scale_max:
        floor = depth_y(bottom)
        pygame.draw.rect(s, config.COLOR_LAND, (column.x, floor, column.w,
                                                column.bottom - floor))
        pygame.draw.line(s, config.COLOR_LAND_EDGE, (column.x, floor),
                         (column.right - 1, floor), 2)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, column, 1)
    step = 100 if scale_max <= 600 else 200 if scale_max <= 1200 else 500
    for value in range(0, int(scale_max) + 1, step):
        ty = depth_y(value)
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (column.x - 5, ty), (column.x, ty), 1)
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
    marks.append((sy, message("uboot.ladder.safe", depth=_fmt(safe)), config.COLOR_DANGER))
    oy = depth_y(sub.order_depth)
    _dashed_hline(s, config.COLOR_TEXT, column.x, column.right, oy, dash=3)
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
    marks.append((cy, message("uboot.ladder.boat", depth=_fmt(sub.depth)), config.COLOR_TEXT))
    # Legend labels, spread so they never overlap.
    placed = []
    for mark_y, text, color in sorted(marks, key=lambda item: item[0]):
        label_y = max(y, mark_y - 8)
        if placed and label_y < placed[-1] + 17:
            label_y = placed[-1] + 17
        label_y = min(label_y, y + h - 16)
        placed.append(label_y)
        pygame.draw.line(s, color, (column.right, mark_y), (legend_x - 2, label_y + 8), 1)
        layout.blit_line(s, text, (legend_x, label_y, x + w - legend_x, 16), color, size=13)


def _draw_nav_page(s, game, boat, x, y, w, h) -> None:
    sub = boat.sub
    half = (w - 10) // 2
    box_h = min(176, max(120, h // 2))
    nav = layout.box(s, (x, y, half, box_h), "uboot.panel.course_depth",
                     border=config.COLOR_TEXT)
    nx, ny, nw, _ = nav
    layout.blit_line(s, message("bridge.line.course", course=f"{sub.course:05.1f}"),
                     (nx, ny, nw, 34), config.COLOR_TEXT, size=28)
    layout.status_line(s, nx, ny + 36, nw, "ui.target_value_short",
                       message("bridge.line.course", course=f"{sub.order_course:05.1f}"),
                       size=18, label_w=80)
    layout.blit_line(s, message("uboot.line.depth", depth=_fmt(sub.depth)),
                     (nx, ny + 62, nw, 34), config.COLOR_TEXT, size=28)
    layout.status_line(s, nx, ny + 98, nw, "ui.target_value_short",
                       message("uboot.line.depth", depth=_fmt(sub.order_depth)),
                       size=18, label_w=80)
    bottom = game.world.depth_m(sub.x, sub.y)
    keel = message("uboot.line.under_keel", depth=_fmt(bottom - sub.depth))
    ahead = boat.orders.obstacle_ahead_nm
    if ahead is not None:
        keel = message("uboot.line.keel_obstacle", depth=_fmt(bottom - sub.depth),
                       distance=f"{ahead:.1f}")
    layout.blit_line(s, keel, (nx, ny + 124, nw, 20),
                     config.COLOR_WARN if ahead is not None
                     or bottom - sub.depth < config.UBOOT_UNDER_KEEL_WARN_M
                     else config.COLOR_TEXT_DIM, size=16)
    drive = layout.box(s, (x + half + 10, y, half, box_h), "panel.speed_acoustics",
                       border=config.COLOR_WARN if sub.cavitating else config.COLOR_TEXT)
    dx, dy, dw, _ = drive
    layout.blit_line(s, message("bridge.line.speed", speed=f"{sub.speed:04.1f}"),
                     (dx, dy, dw, 34), config.COLOR_TEXT, size=28)
    layout.status_line(s, dx, dy + 36, dw, "ui.target_value_short",
                       message("bridge.line.speed", speed=f"{sub.order_speed:.1f}"),
                       size=18, label_w=80)
    noise = "bridge.cavitation" if sub.cavitating else message(
        "bridge.line.own_noise", noise=f"{sub.noise_level() * 100:.0f}")
    layout.blit_line(s, noise, (dx, dy + 62, dw, 22),
                     config.COLOR_DANGER if sub.cavitating else config.COLOR_OK, size=18)
    battery = _battery_fraction(sub)
    phase = sub.endurance.phase if sub.endurance is not None else None
    layout.blit_line(s, message("uboot.line.battery",
                                value=_fmt(None if battery is None else battery * 100),
                                phase=raw_text(str(phase or "--"))),
                     (dx, dy + 88, dw, 20), config.COLOR_TEXT_DIM, size=16)
    _bar(s, (dx, dy + 110, dw, 10), battery,
         config.COLOR_DANGER if battery is not None and battery < .15 else
         config.COLOR_WARN if battery is not None and battery < .3 else config.COLOR_OK)
    modes = [key for key, on in (("uboot.mode.silent", boat.orders.silent),
                                 ("uboot.mode.snorkel", sub.snorkeling),
                                 ("uboot.mode.bottom", boat.orders.bottomed),
                                 ("uboot.mode.mast", boat.orders.mast)) if on]
    quiet = boat.orders.quiet_active(sub)
    layout.blit_line(s, message("uboot.line.modes", modes=raw_text(" · ".join(
        str(localize(key)) for key in modes)) if modes else localize("uboot.mode.none")),
                     (dx, dy + 124, dw, 20),
                     config.COLOR_OK if quiet else config.COLOR_TEXT_DIM, size=16)
    ladder_y = y + box_h + 10
    ladder_h = y + h - ladder_y
    if ladder_h >= 70:
        inner = layout.box(s, (x, ladder_y, w, ladder_h), "uboot.panel.depth_ladder")
        draw_depth_ladder(s, game, boat, inner)


def _draw_weapons_page(s, game, boat, x, y, w, h) -> None:
    sub = boat.sub
    battery = sub.weapon_battery
    box_h = min(150, h // 2)
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
                       raw_text(f"{int(battery.ready_count) if battery else 0}"
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
            quality=_fmt(max(contact.quality, contact.confidence), "{:.2f}"),
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
                               ("↑/↓", "uboot.footer.contact"), ("Q/E", "uboot.footer.chart")),
    ("uboot_esm", "UBOOT_SCOPE"): (("←/→", "uboot.footer.scope_turn"),
                                   ("help.key.enter", "uboot.footer.stadimeter"),
                                   ("P", "uboot.footer.mast")),
    ("uboot_nav", "UBOOT_NAV"): (("C", "uboot.footer.course"), ("D", "uboot.footer.depth"),
                                 ("U/J/H", "uboot.footer.presets"),
                                 ("Shift+G", "uboot.footer.bottom")),
    ("uboot_weapons", "UBOOT_WEAPONS"): (("↑/↓", "uboot.footer.contact"),
                                         ("help.key.uboot_fire", "uboot.footer.fire"),
                                         ("F", "uboot.footer.fire_bearing"),
                                         ("W", "uboot.footer.wire"), ("X", "uboot.footer.decoy")),
    ("uboot_engine", "UBOOT_ENGINE"): (("+/-", "uboot.footer.telegraph"),
                                       ("G", "uboot.footer.silent"),
                                       ("N", "uboot.footer.snorkel"),
                                       ("help.key.uboot_blow", "uboot.footer.blow")),
    ("uboot_esm", "UBOOT_ESM"): (("P", "uboot.footer.mast"), ("Q/E", "uboot.footer.chart")),
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
              "UBOOT_ENGINE": _draw_engine_page, "UBOOT_ESM": _draw_esm_page,
              "UBOOT_SCOPE": draw_scope_page}[name]
    drawer(s, game, boat, x, content_y, w, content_h)
    specs = tuple(
        (key, "uboot.footer.mast_down" if text == "uboot.footer.mast" and boat.orders.mast
         else "uboot.footer.snorkel_down" if text == "uboot.footer.snorkel" and boat.sub.snorkeling
         else text) for key, text in _FOOTERS[(station, name)])
    _footer(s, (x, station_rect.bottom - 26, w, 20), specs)


def _draw_engine_page(s, game, boat, x, y, w, h) -> None:
    """Engine room: speed and telegraph, plant modes, battery and own noise."""
    sub = boat.sub
    box_h = min(150, h // 2)
    plant = layout.box(s, (x, y, w, box_h), "uboot.panel.plant",
                       border=config.COLOR_WARN if sub.cavitating else config.COLOR_TEXT)
    px, py, pw, _ = plant
    half = (pw - 10) // 2
    layout.blit_line(s, message("bridge.line.speed", speed=f"{sub.speed:04.1f}"),
                     (px, py, half, 34), config.COLOR_TEXT, size=28)
    layout.status_line(s, px, py + 36, half, "ui.target_value_short",
                       message("bridge.line.speed", speed=f"{sub.order_speed:.1f}"),
                       size=18, label_w=80)
    noise = "bridge.cavitation" if sub.cavitating else message(
        "bridge.line.own_noise", noise=f"{sub.noise_level() * 100:.0f}")
    layout.blit_line(s, noise, (px, py + 64, half, 22),
                     config.COLOR_DANGER if sub.cavitating else config.COLOR_OK, size=18)
    battery = _battery_fraction(sub)
    phase = sub.endurance.phase if sub.endurance is not None else None
    layout.blit_line(s, message("uboot.line.battery",
                                value=_fmt(None if battery is None else battery * 100),
                                phase=raw_text(str(phase or "--"))),
                     (px + half + 10, py, half, 22), config.COLOR_TEXT, size=17)
    _bar(s, (px + half + 10, py + 26, half, 12), battery,
         config.COLOR_DANGER if battery is not None and battery < .15 else
         config.COLOR_WARN if battery is not None and battery < .3 else config.COLOR_OK)
    modes = [key for key, on in (("uboot.mode.silent", boat.orders.silent),
                                 ("uboot.mode.snorkel", sub.snorkeling),
                                 ("uboot.mode.bottom", boat.orders.bottomed)) if on]
    layout.blit_line(s, message("uboot.line.modes", modes=raw_text(" · ".join(
        str(localize(key)) for key in modes)) if modes else localize("uboot.mode.none")),
                     (px + half + 10, py + 46, half, 20),
                     config.COLOR_OK if boat.orders.quiet_active(sub) else config.COLOR_TEXT_DIM,
                     size=16)
    layout.status_line(s, px + half + 10, py + 70, half, "uboot.label.blow",
                       message("common.yes" if sub.blow_available else "common.no"),
                       size=16, label_w=150)
    tele_y = y + box_h + 10
    ladder_y = tele_y + 80
    if y + h - ladder_y >= 90:
        inner = layout.box(s, (x, ladder_y, w, y + h - ladder_y), "uboot.panel.depth_ladder")
        draw_depth_ladder(s, game, boat, inner)
    telegraph = layout.box(s, (x, tele_y, w, min(70, y + h - tele_y)), "uboot.panel.telegraph")
    tx, ty, tw, _ = telegraph
    steps = opfor.speed_steps(sub)
    width = tw // len(steps)
    for index, speed in enumerate(steps):
        current = abs(sub.order_speed - speed) < 0.05
        rect = pygame.Rect(tx + index * width, ty, width - 4, 26)
        if current:
            pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, rect)
        layout.blit_line(s, message("uboot.line.telegraph_step", marker="> " if current else "",
                                    speed=_fmt(speed, "{:.0f}")), rect,
                         config.COLOR_TEXT if current else config.COLOR_TEXT_DIM,
                         size=16, align="center")


def _alarm_value(age, bearing):
    if not math.isfinite(age) or age >= ALARM_WINDOW_S:
        return message("uboot.value.no_alarm")
    return message("uboot.value.alarm", bearing=_fmt(bearing, "{:03.0f}"), age=_fmt(age))


def _draw_esm_rose(s, game, boat, rect) -> None:
    """Bearing rose: own heading, ESM strobes and the alarm bearings (own measurements)."""
    sub, orders = boat.sub, boat.orders
    pygame.draw.rect(s, config.COLOR_GEO_BG, rect)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)
    radius = max(20, min(rect.w, rect.h) // 2 - 18)
    cx, cy = rect.center

    def at(bearing, r):
        rad = math.radians(bearing)
        return int(cx + r * math.sin(rad)), int(cy - r * math.cos(rad))

    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), radius, 1)
    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), radius // 2, 1)
    for bearing in range(0, 360, 30):
        pygame.draw.line(s, config.COLOR_TEXT_DIM, at(bearing, radius), at(bearing, radius - 7), 1)
        tx, ty = at(bearing, radius + 10)
        layout.blit_line(s, raw_text("N" if bearing == 0 else f"{bearing:03d}"),
                         (tx - 16, ty - 7, 32, 14), config.COLOR_TEXT_DIM, size=11, align="center")
    pygame.draw.line(s, nato_symbols.AFFILIATION_COLORS["FRIEND"], (cx, cy),
                     at(sub.course, radius * .35), 2)
    for bearing, _quality, _age in orders.esm:
        pygame.draw.line(s, config.COLOR_WARN, (cx, cy), at(bearing, radius), 2)
    memory = sub.memory
    for age, bearing, color in ((memory["last_ping_age"], orders.ping_bearing, config.COLOR_WARN),
                                (memory["last_torpedo_age"], orders.torpedo_bearing,
                                 config.COLOR_DANGER)):
        if bearing is None or not math.isfinite(age) or age >= ALARM_WINDOW_S:
            continue
        end = at(bearing, radius)
        for step in range(0, 10, 2):
            a = (cx + (end[0] - cx) * step / 10, cy + (end[1] - cy) * step / 10)
            b = (cx + (end[0] - cx) * (step + 1) / 10, cy + (end[1] - cy) * (step + 1) / 10)
            pygame.draw.line(s, color, a, b, 3)


def _draw_esm_page(s, game, boat, x, y, w, h) -> None:
    """Mast & ESM: mast state, the boat's own radar intercepts and alarm bearings."""
    from src.sensors.platform import MAST_DEPTH_M
    sub, orders = boat.sub, boat.orders
    mast = layout.box(s, (x, y, w, 64), "uboot.panel.mast",
                      border=config.COLOR_WARN if orders.mast else config.COLOR_TEXT)
    mx, my, mw, _ = mast
    layout.blit_line(s, message("uboot.line.mast_up" if orders.mast else "uboot.line.mast_down",
                                depth=_fmt(MAST_DEPTH_M)), (mx, my, mw, 26),
                     config.COLOR_WARN if orders.mast else config.COLOR_TEXT, size=20)
    alarm_y = y + 74
    alarms = layout.box(s, (x, alarm_y, w, 84), "uboot.panel.alarms")
    ax, ay, aw, _ = alarms
    memory = sub.memory
    layout.blit_line(s, message("uboot.line.alarm_ping", value=_alarm_value(
        memory["last_ping_age"], orders.ping_bearing)), (ax, ay, aw, 22),
        config.COLOR_TEXT, size=17)
    layout.blit_line(s, message("uboot.line.alarm_torpedo", value=_alarm_value(
        memory["last_torpedo_age"], orders.torpedo_bearing)), (ax, ay + 24, aw, 22),
        config.COLOR_TEXT, size=17)
    esm_y = alarm_y + 94
    rose_w = min(w // 2, y + h - esm_y)
    _draw_esm_rose(s, game, boat, pygame.Rect(x, esm_y, rose_w, y + h - esm_y))
    listing = layout.box(s, (x + rose_w + 10, esm_y, w - rose_w - 10, y + h - esm_y),
                         "uboot.panel.esm")
    lx, ly, lw, lh = listing
    if not orders.mast or not orders.esm:
        layout.blit_line(s, "uboot.line.no_esm" if orders.mast else "uboot.line.esm_mast_down",
                         (lx, ly, lw, 22), config.COLOR_TEXT_DIM, size=16)
        return
    for index, (bearing, quality, age) in enumerate(orders.esm):
        row_y = ly + index * 24
        if row_y + 24 > ly + lh:
            break
        layout.blit_line(s, message("uboot.line.esm_row", bearing=_fmt(bearing, "{:03.0f}"),
                                    quality=_fmt(quality * 100), age=_fmt(age)),
                         (lx, row_y + 2, lw, 20), config.COLOR_WARN, size=16)


def _footer(s, rect, specs) -> None:
    """Key legend like the frigate's, each segment as wide as its text."""
    rect = pygame.Rect(rect)
    weights = [len(localize(key)) + len(localize(text)) + 2 for key, text in specs]
    x = rect.x
    for index, ((key, text), weight) in enumerate(zip(specs, weights)):
        width = (rect.right - x if index == len(specs) - 1
                 else int(rect.w * weight / sum(weights)))
        layout.command_segment(s, (x, rect.y, width, rect.h), key, text, size=11)
        x += width


# --- end of mission and the whole screen ---------------------------------------

def end_text(game, boat) -> str:
    if boat is not None and boat.sub.sunk:
        return "uboot.end.lost"
    if game.damage.ship_sunk:
        return "uboot.end.won"
    return "uboot.end.over"


def draw_end_panel(game, boat) -> None:
    s = game.screen
    rect = pygame.Rect(340, 250, 600, 150)
    pygame.draw.rect(s, config.COLOR_OVERLAY_BG, rect)
    pygame.draw.rect(s, config.COLOR_WARN, rect, 2)
    key = end_text(game, boat)
    layout.blit_line(s, key, (rect.x + 16, rect.y + 20, rect.w - 32, 40),
                     config.COLOR_OK if key == "uboot.end.won" else config.COLOR_WARN,
                     size=28, align="center")
    layout.blit_block(s, "uboot.end.hint", rect.x + 16, rect.y + 80, rect.w - 32, 56,
                      config.COLOR_TEXT_DIM, size=16, align="center")


def draw(game) -> None:
    """The whole mission screen while the uConsole plays the submarine."""
    boat = game.opfor
    draw_top_bar(game, boat)
    previous = config.STATION_RECT
    try:
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
        if game.game_over:
            draw_end_panel(game, boat)
    finally:
        config.STATION_RECT = previous
