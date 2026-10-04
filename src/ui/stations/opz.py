"""OPZ / CIC station view: track list, PPI with radar clutter and coast
segments, pointer ownership (verbatim from ``stations_view``)."""

import math
import random
import copy

import pygame

from src.core import config
from src.core.i18n import (display_value, localized, localize, raw_text,
                            message as structured_message)
from src.core.station import Station
from src.ui.plot_view import draw_plot
from src.core import map_fx
from src.ui import label_layout, layout, map_fx_view, pointer, quality
from src.ui import theme
from src.ui import chart_symbols
from src.ui import nato_symbols
from src.ui import observations
from src.sensors.fusion import source_groups
from src.core import opz_display
from src.ui.stations import opz_display_view


from src.ui.stations.common import (
    _observation_bearing,
    _observation_position,
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)
from src.ui.stations.eloka import (_near_point)


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
# Correlation suggestions listed above the sidebar buttons (the browser lists
# all of them, at most config.OPZ_SUGGEST_MAX).
OPZ_SUGGESTION_ROWS = 2
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
    for track, rect in opz_track_cards(game):
        if rect.collidepoint(pos):
            return _track_tooltip(game, track)
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


# Track cards in the left column (UI grid, stage 3).
OPZ_TRACKS_W = 250
OPZ_SIDEBAR_W = 300
OPZ_CARD_H = 44
OPZ_CARD_PITCH = 48


def opz_regions(station_rect=None) -> dict[str, pygame.Rect]:
    """Single OPZ geometry source for drawing and pointer ownership.

    Three columns on every page: track cards on the left, the chart in the
    middle, the page's sidebar on the right.
    """
    station = pygame.Rect(station_rect or config.STATION_RECT)
    top = _station_content_top(station, 2)
    height = station.bottom - top - 42
    if station.w >= 1000:
        tracks = pygame.Rect(station.x + 8, top, OPZ_TRACKS_W, height)
        sidebar = pygame.Rect(station.right - 8 - OPZ_SIDEBAR_W, top,
                              OPZ_SIDEBAR_W, height)
        map_rect = pygame.Rect(tracks.right + 10, top,
                               sidebar.x - 10 - tracks.right - 10, height)
    else:
        # A narrow panel (never the uConsole's OPZ): chart and sidebar only.
        scope_w = int(station.w * .75)
        tracks = pygame.Rect(station.x, top, 0, height)
        map_rect = pygame.Rect(station.x + 8, top, scope_w - 16, height)
        sidebar = pygame.Rect(station.x + scope_w, top, station.w - scope_w, height)
    chart = map_rect.copy()
    button_y = sidebar.bottom - 80
    button_w = max(1, (sidebar.w - 24) // 2)
    return {"map": map_rect, "chart": chart, "sidebar": sidebar, "tracks": tracks,
            "classify": pygame.Rect(sidebar.x + 8, button_y, button_w, 28),
            "affiliate": pygame.Rect(sidebar.x + 16 + button_w, button_y,
                                     button_w, 28),
            "mark": pygame.Rect(sidebar.x + 8, button_y + 34, button_w, 28),
            "fusion": pygame.Rect(sidebar.x + 16 + button_w, button_y + 34,
                                  button_w, 28)}


def opz_track_cards(game, station_rect=None) -> list:
    """The visible track cards as (track, rect), the selected one in view."""
    box = opz_regions(station_rect)["tracks"]
    if box.w <= 0:
        return []
    tracks = (game.filtered_opz_tracks() if hasattr(game, "filtered_opz_tracks")
              else game.opz_tracks())
    top = box.y + 34
    capacity = max(0, (box.bottom - 6 - top) // OPZ_CARD_PITCH)
    selected_id = getattr(game, "opz_selected_track_id", None)
    index = next((i for i, track in enumerate(tracks)
                  if track.track_id == selected_id), 0)
    start = max(0, min(index - capacity // 2, max(0, len(tracks) - capacity)))
    return [(track, pygame.Rect(box.x + 6, top + row * OPZ_CARD_PITCH,
                                box.w - 12, OPZ_CARD_H))
            for row, track in enumerate(tracks[start:start + capacity])]


def _draw_track_cards(game, s, box, selected_id) -> None:
    """Left column: one card per CIC track (affiliation stripe, label,
    bearing, range and the sensors behind it); a click selects it."""
    if box.w <= 0:
        return
    layout.box(s, box, "")
    contact_filter = getattr(game, "opz_contact_filter", "ALL")
    heading = message("opz.tracks_heading_filtered",
                      filter=display_value("contact_filter", contact_filter))
    head = pygame.Rect(box.x + 10, box.y + 8, box.w - 20, 22)
    layout.blit_line(s, heading, head, config.COLOR_TEXT, size=14)
    pointer.add_token_keys(head, heading, 14, (("(Shift+F)", "Shift+F"),),
                           min_size=layout.MIN_OPERATIONAL_FONT)
    cards = opz_track_cards(game)
    if not cards:
        layout.blit_line(s, "opz.no_tracks", (box.x + 10, box.y + 36, box.w - 20, 22),
                         config.COLOR_TEXT_DIM, size=14)
    for track, rect in cards:
        chosen = track.track_id == selected_id
        affiliation = game.opz_affiliation(track.track_id)
        domain = nato_symbols.domain_for_kind(track.kind)
        color = nato_symbols.AFFILIATION_COLORS[affiliation]
        pygame.draw.rect(s, config.COLOR_TAB_ACTIVE if chosen else theme.c("raised"),
                         rect, border_radius=4)
        pygame.draw.rect(s, theme.c("focus") if chosen else theme.c("line"),
                         rect, 2 if chosen else 1, border_radius=4)
        pygame.draw.rect(s, color, (rect.x + 3, rect.y + 5, 3, rect.h - 10))
        mark = "*" if track.track_id in game.opz_fusion.marked else ""
        layout.blit_line(s, f"{mark}{track.label}", (rect.x + 12, rect.y + 3, 92, 20),
                         config.COLOR_TEXT, size=15)
        layout.blit_line(s, message("opz.card.kind",
                                    affiliation=structured_message(
                                        "affil.code." + affiliation.lower()),
                                    domain=structured_message(OPZ_DOMAIN_CODES[domain])),
                         (rect.x + 104, rect.y + 4, 60, 19), color, size=13)
        layout.blit_line(s, observations.format_bearing(track, game.ship) + "\u00b0",
                         (rect.right - 76, rect.y + 2, 68, 21), config.COLOR_TEXT,
                         size=17, align="right")
        displayed_range = observations.range_nm(track, game.ship)
        distance = (f"{displayed_range:.1f} NM" if displayed_range is not None else "-- NM")
        tags = "".join(localize("opz.source_code." + group)
                       for group in source_groups(track))
        layout.blit_line(s, f"{distance} \u00b7 {tags}",
                         (rect.x + 12, rect.y + 24, rect.w - 20, 19),
                         config.COLOR_TEXT_DIM, size=13)
        pointer.add_hotspot(rect)       # opz_action_at takes the click


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
    for track, rect in opz_track_cards(game, station_rect):
        if rect.collidepoint(pos):
            return ("select", track.observation_id)
    chart = regions["chart"]
    if not chart.collidepoint(pos):
        return None
    view = _opz_view(game, chart)
    for track in reversed(game.opz_tracks()):
        point = _opz_track_point(game, track, chart, view)
        if point is not None and _near_point(pos, point, 15):
            return ("select", track.observation_id)
    # A bare radar blip: clicking it marks it into a track.
    for blip in reversed(game.radar_blip_view() if hasattr(game, "radar_blip_view") else []):
        if _near_point(pos, view.world_to_screen(blip["x"], blip["y"]), 12):
            return ("blip", blip["seq"])
    return None


def opz_world_at(game, pos, station_rect=None):
    """World position (nm) under a chart point, or ``None`` off the chart."""
    if pos is None:
        return None
    chart = opz_regions(station_rect)["chart"]
    if not chart.collidepoint(pos):
        return None
    x, y = _opz_view(game, chart).screen_to_world(*pos)
    size = float(getattr(getattr(game, "world", None), "size_nm", config.WORLD_SIZE_NM))
    return config.clamp(float(x), 0.0, size), config.clamp(float(y), 0.0, size)


def _draw_mpa(game, s, chart, view, px_per_nm, page) -> None:
    """The patrol aircraft is own-force datalink truth, like the helicopter;
    its waypoint and planned buoy points are shown on the MPA page."""
    mpa = getattr(game, "mpa", None)
    if mpa is None or not mpa.airborne:
        return
    color = config.COLOR_FLIGHT
    if page == 2:
        wx, wy = view.world_to_screen(mpa.waypoint_x, mpa.waypoint_y)
        if chart.collidepoint(wx, wy):
            pygame.draw.line(s, color, (wx - 7, wy), (wx + 7, wy), 1)
            pygame.draw.line(s, color, (wx, wy - 7), (wx, wy + 7), 1)
            radius = int(config.MPA_ORBIT_NM * px_per_nm)
            if radius >= 4:
                pygame.draw.circle(s, config.COLOR_TEXT_DIM, (int(wx), int(wy)), radius, 1)
        for px, py in mpa.pattern_queue:
            bx, by = view.world_to_screen(px, py)
            if chart.collidepoint(bx, by):
                pygame.draw.circle(s, color, (int(bx), int(by)), 4, 1)
    mx, my = view.world_to_screen(mpa.x, mpa.y)
    if not chart.collidepoint(mx, my):
        return
    col = nato_symbols.draw_symbol(s, (mx, my), "FRIEND", "AIR", 17)
    nato_symbols.draw_motion_vector(s, (mx, my), mpa.course, mpa.speed_kn,
                                    px_per_nm, col, max_px=min(chart.size) * .3)
    label_layout.blit_line(s, "MPA DL", (int(mx) + 13, int(my) - 10, 94, 19), col, size=12)


def _draw_mpa_sidebar(game, s, x, py, w, bottom) -> int:
    """OPZ page 3: the patrol aircraft's state, stores and order keys."""
    view = game.mpa_view()
    state = display_value("mpa_state", view["state"])
    lines = [(message("opz.mpa.state", state=state), config.COLOR_TEXT)]
    if view["airborne"]:
        lines.append((message("opz.mpa.position", bearing=f"{view['bearing']:03.0f}",
                              range=f"{view['range_nm']:.0f}"), config.COLOR_TEXT_DIM))
        reserve = view["fuel_s"] - view["bingo_s"]
        lines.append((message("opz.mpa.fuel", minutes=f"{max(0.0, reserve) / 60.0:.0f}"),
                      config.COLOR_WARN if reserve < 1800.0 else config.COLOR_TEXT_DIM))
        lines.append((localize("opz.mpa.datalink_on" if view["datalink"]
                               else "opz.mpa.datalink_off"),
                      config.COLOR_OK if view["datalink"] else config.COLOR_WARN))
    elif view["ready_in_s"] is None:
        lines.append((localize("opz.mpa.no_sorties"), config.COLOR_WARN))
    elif view["ready_in_s"] > 0.0:
        lines.append((message("opz.mpa.ready_in", minutes=f"{view['ready_in_s'] / 60.0:.0f}"),
                      config.COLOR_TEXT_DIM))
    else:
        lines.append((localize("opz.mpa.ready"), config.COLOR_OK))
    lines.append((message("opz.mpa.stores", buoys=view["buoys"], torpedoes=view["torpedoes"]),
                  config.COLOR_TEXT_DIM))
    lines.append((message("opz.mpa.sorties", sorties=view["sorties_left"]),
                  config.COLOR_TEXT_DIM))
    lines.append((message("opz.mpa.sensors",
                          radar=localize("common.on" if view["radar"] else "common.off"),
                          mode=display_value("buoy_mode", view["buoy_mode"])),
                  config.COLOR_TEXT_DIM))
    if view["mad"]:
        lines.append((localize("opz.mpa.mad_run"), config.COLOR_OK))
    lines.append((message("opz.mpa.relayed", relayed=view["relayed"]), config.COLOR_TEXT_DIM))
    if view["pattern"] != "single":
        lines.append((message("opz.mpa.pattern",
                              pattern=display_value("buoy_pattern", view["pattern"]),
                              count=len(view["pattern_points"])), config.COLOR_TEXT_DIM))
    for text, color in lines:
        if py + 24 > bottom:
            return py
        layout.blit_line(s, text, (x, py, w, 24), color, size=15)
        py += 26
    py += 4
    pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
    py += 6
    for key, tokens in (
            ("opz.mpa.keys_orders", (("H", "H"),)),
            ("opz.mpa.keys_area", (("W", "W"),)),
            ("opz.mpa.keys_buoys", (("X", "X"), ("B", "B"), ("Shift+B", "Shift+B"))),
            ("opz.mpa.keys_weapons", (("Ctrl+R", "Ctrl+R"), ("Strg+R", "Ctrl+R"),
                                      ("Shift+M", "Shift+M"), ("D", "D")))):
        if py + 22 > bottom:
            break
        layout.blit_line(s, key, (x, py, w, 22), config.COLOR_TEXT_DIM, size=14)
        # Each key in the hint is a switch (full mouse control).
        pointer.add_token_keys((x, py, w, 22), key, 14, tokens)
        py += 24
    return py


OPZ_TARGET_KEYS = ((("M", "opz.keys.designate"), ("G", "opz.keys.chaff")),
                   (("←/→", "opz.keys.asm_track"),))

# The consort's order hints: each key in them is a switch.  Ctrl+Enter (its
# ASROC) is not: fire by click only at the weapons station.
CONSORT_KEY_TOKENS = {
    "opz.group.keys_orders": (("Y", "Y"), ("F", "F"), ("H", "H")),
    "opz.group.keys_point": (("X", "X"), ("W", "W")),
    "opz.group.keys_sensors": (("Shift+A", "Shift+A"),),
    "opz.group.keys_weapons": (("Shift+W", "Shift+W"),),
}


def _draw_consort(game, s, chart, view, px_per_nm, page) -> None:
    """The consort destroyer is own-force datalink truth; on the group page
    also its search point and its sonar's bearing lines (measurements)."""
    consort_view = game.consort_view() if hasattr(game, "consort_view") else None
    if consort_view is None or consort_view["sunk"]:
        return
    color = config.COLOR_FLIGHT
    if page == 3 and consort_view["datalink"]:
        for row in consort_view["bearings"]:
            ox, oy = view.world_to_screen(row["x"], row["y"])
            rad = math.radians(row["bearing"])
            reach = config.CONSORT_XFIX_MAX_NM * px_per_nm
            pygame.draw.line(s, _scale_color(color, .7), (int(ox), int(oy)),
                             (int(ox + reach * math.sin(rad)), int(oy - reach * math.cos(rad))), 1)
        point = consort_view["point"]
        if point is not None and consort_view["working"] in ("search", "prosecute"):
            wx, wy = view.world_to_screen(*point)
            if chart.collidepoint(wx, wy):
                pygame.draw.line(s, color, (wx - 7, wy), (wx + 7, wy), 1)
                pygame.draw.line(s, color, (wx, wy - 7), (wx, wy + 7), 1)
                orbit = (config.CONSORT_PROSECUTE_ORBIT_NM
                         if consort_view["working"] == "prosecute"
                         else config.CONSORT_SEARCH_ORBIT_NM)
                radius = int(orbit * px_per_nm)
                if radius >= 4:
                    pygame.draw.circle(s, config.COLOR_TEXT_DIM, (int(wx), int(wy)), radius, 1)
    cx, cy = view.world_to_screen(consort_view["x"], consort_view["y"])
    if not chart.collidepoint(cx, cy):
        return
    col = nato_symbols.draw_symbol(s, (cx, cy), "FRIEND", "SURFACE", 17)
    nato_symbols.draw_motion_vector(s, (cx, cy), consort_view["course"],
                                    consort_view["speed_kn"], px_per_nm, col,
                                    max_px=min(chart.size) * .3)
    label_layout.blit_line(s, raw_text(consort_view["callsign"] + " DL"),
                     (int(cx) + 13, int(cy) + 8, 110, 19), col, size=12)


def _draw_consort_sidebar(game, s, x, py, w, bottom) -> int:
    """OPZ page 4: the consort destroyer's orders, state and order keys."""
    consort_view = game.consort_view() if hasattr(game, "consort_view") else None
    if consort_view is None:
        layout.blit_block(s, "opz.group.none", x, py, w, 44,
                          color=config.COLOR_TEXT_DIM, size=15)
        return py + 48
    lines = [(message("opz.group.ship", callsign=raw_text(consort_view["callsign"])),
              config.COLOR_TEXT)]
    if consort_view["sunk"]:
        lines.append((localize("opz.group.lost"), config.COLOR_DANGER))
    else:
        lines.append((message("opz.group.position", bearing=f"{consort_view['bearing']:03.0f}",
                              range=f"{consort_view['range_nm']:.1f}",
                              course=f"{consort_view['course']:03.0f}",
                              speed=f"{consort_view['speed_kn']:.0f}"), config.COLOR_TEXT_DIM))
        lines.append((localize("opz.group.datalink_on" if consort_view["datalink"]
                               else "opz.group.datalink_off"),
                      config.COLOR_OK if consort_view["datalink"] else config.COLOR_WARN))
        mode = display_value("consort_mode", consort_view["mode"])
        working = display_value("consort_mode", consort_view["working"])
        lines.append((message("opz.group.mode", mode=mode, working=working), config.COLOR_TEXT))
        lines.append((message("opz.group.station",
                              station=display_value("consort_station",
                                                    consort_view["station"])),
                      config.COLOR_TEXT_DIM))
        lines.append((message("opz.group.sensors",
                              sonar=localize("opz.group.active" if consort_view["active"]
                                             else "opz.group.passive"),
                              bearings=len(consort_view["bearings"])),
                      config.COLOR_WARN if consort_view["active"] else config.COLOR_TEXT_DIM))
        lines.append((message("opz.group.weapons",
                              state=localize("opz.group.free" if consort_view["weapons_free"]
                                             else "opz.group.tight"),
                              asroc=consort_view["asroc"]),
                      config.COLOR_WARN if consort_view["weapons_free"] else config.COLOR_TEXT_DIM))
    for text, color in lines:
        if py + 24 > bottom:
            return py
        layout.blit_line(s, text, (x, py, w, 24), color, size=15)
        py += 26
    py += 4
    pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
    py += 6
    for key in ("opz.group.keys_orders", "opz.group.keys_point", "opz.group.keys_sensors",
                "opz.group.keys_weapons"):
        if py + 22 > bottom:
            break
        layout.blit_line(s, key, (x, py, w, 22), config.COLOR_TEXT_DIM, size=14)
        pointer.add_token_keys((x, py, w, 22), key, 14, CONSORT_KEY_TOKENS[key])
        py += 24
    return py


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
            base = theme.pick((70, 145, 95), (4, 120, 87))
        else:
            distance = radius * math.sqrt(rng.random())
            base = theme.pick((90, 115, 105), (100, 116, 139))
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


# (largest visible radius NM, grid step NM) for the OPZ chart.
_OPZ_GRID_STEPS = ((0.5, 0.1), (1.0, 0.2), (2.5, 0.5), (5.0, 1.0), (10.0, 2.0),
                   (20.0, 5.0), (40.0, 10.0), (80.0, 20.0))


def _ring_visible(center, radius, rect) -> bool:
    """True when a circle outline crosses ``rect``: it is neither wholly
    outside the rect nor so large that the whole rect lies inside it."""
    cx, cy = center
    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
    near_x = min(max(cx, left), right)
    near_y = min(max(cy, top), bottom)
    if math.hypot(near_x - cx, near_y - cy) > radius + 2:
        return False
    far = max(math.hypot(x - cx, y - cy)
              for x in (left, right) for y in (top, bottom))
    return far >= radius - 2


def _opz_basemap_surface(game, map_rect: pygame.Rect, view,
                         chart_layer: bool = True) -> pygame.Surface:
    """Build a bounded cached chart layer beneath the live OPZ radar picture
    (``chart_layer`` False leaves out the depth shading and the grid)."""
    world = game.world
    coast = getattr(world, "coast", None)
    world_size_nm = float(getattr(world, "size_nm", config.WORLD_SIZE_NM))
    scale = view.scale
    # Re-render when the camera moved about a pixel (0.1 NM at normal zoom).
    quantum = min(0.1, 1.0 / max(scale, 1e-6))
    bucket_x = round(view.cx / quantum) * quantum
    bucket_y = round(view.cy / quantum) * quantum
    key = (world, coast, map_rect.size, round(scale, 6), bucket_x, bucket_y,
           config.COLOR_GEO_BG, config.COLOR_GEO_GRID,
           config.COLOR_LAND, config.COLOR_LAND_EDGE,
           config.COLOR_SHALLOW, config.COLOR_DEEP, chart_layer)
    cached = getattr(_opz_basemap_surface, "_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]

    layer = pygame.Surface(map_rect.size)
    layer.fill(config.COLOR_GEO_BG)
    center_x = map_rect.w / 2.0
    center_y = map_rect.h / 2.0

    depth_query = getattr(world, "depth_m", None)
    if (chart_layer and coast is not None and getattr(coast, "has_bathymetry", False)
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
    step = next((value for limit, value in _OPZ_GRID_STEPS if visible_radius <= limit), 40)
    half_w_nm = map_rect.w / (2.0 * scale)
    half_h_nm = map_rect.h / (2.0 * scale)
    first_x = math.ceil((bucket_x - half_w_nm) / step) * step
    first_y = math.ceil((bucket_y - half_h_nm) / step) * step
    value = first_x if chart_layer else bucket_x + half_w_nm + step
    while value <= bucket_x + half_w_nm:
        px = int(center_x + (value - bucket_x) * scale)
        pygame.draw.line(layer, config.COLOR_GEO_GRID,
                         (px, 0), (px, map_rect.h), 1)
        value += step
    value = first_y if chart_layer else bucket_y + half_h_nm + step
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
    _panel(game, title="station.opz.panel_title")
    draw_station_page_tabs(s, station, pages, page, tr)
    regions = opz_regions()
    scope_w = regions["sidebar"].x - station.x
    map_rect = regions["map"]
    chart = regions["chart"]
    view = _opz_view(game, chart)
    max_nm = _opz_radar_range_nm(game)
    shown = game.opz_display_settings()
    layer = lambda key: opz_display.enabled(shown, key)  # noqa: E731
    vector_min = opz_display.vector_minutes(shown)
    vector_max_px = min(chart.size) * .45
    s.blit(_opz_basemap_surface(game, map_rect, view, layer("chart")), map_rect)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, map_rect, 1)
    layout.corner_brackets(s, map_rect)
    previous_clip = s.get_clip()
    s.set_clip(chart)
    # Chart labels step aside from each other (and from the speed labels).
    with label_layout.label_scope(chart) as chart_labels:
        # The radar switches sit in the chart's top left; labels keep off.
        for _domain, switch in opz_display_view.radar_switch_rects(chart):
            chart_labels.reserve(switch)
        station_live = not game.damage.station_down("opz")
        radar_live = station_live and (game.surface_radar_on or game.air_radar_on)
        px_per_nm = view.scale
        own_x, own_y = view.world_to_screen(game.ship.x, game.ship.y)
        radar_radius = max_nm * px_per_nm

        coast = getattr(game.world, "coast", None)
        coast_segments = (_contour_segments_in_circle(
            coast, game.ship.x, game.ship.y, max_nm) if coast is not None else [])
        with layout.clip_to(s, chart):
            if radar_live and quality.afterglow() and layer("afterglow"):
                # Phosphor afterglow behind the beam, under everything else.
                map_fx_view.draw_afterglow(s, own_x, own_y, radar_radius,
                                           game.radar_sweep_bearing(), config.COLOR_GEO_BG)
            # Radar presentation remains ship-centred and independent of the camera.
            for ring_index in range(1, 5) if layer("rings") else ():
                rr = radar_radius * ring_index / 4.0
                if not _ring_visible((own_x, own_y), rr, chart):
                    continue
                pygame.draw.circle(s, config.COLOR_SONAR_RING,
                                   (int(own_x), int(own_y)), max(1, int(rr)), 1)
            # Axis lines clipped to the chart (strong zoom gives huge radii).
            x0 = max(chart.left, own_x - radar_radius)
            x1 = min(chart.right, own_x + radar_radius)
            if layer("rings") and chart.top <= own_y <= chart.bottom and x0 < x1:
                pygame.draw.line(s, config.COLOR_SONAR_RING,
                                 (int(x0), int(own_y)), (int(x1), int(own_y)), 1)
            y0 = max(chart.top, own_y - radar_radius)
            y1 = min(chart.bottom, own_y + radar_radius)
            if layer("rings") and chart.left <= own_x <= chart.right and y0 < y1:
                pygame.draw.line(s, config.COLOR_SONAR_RING,
                                 (int(own_x), int(y0)), (int(own_x), int(y1)), 1)
            # Range labels at the top of each ring, beside the north axis.
            for ring_index in range(1, 5) if layer("rings") else ():
                rr = radar_radius * ring_index / 4.0
                if not chart.top - 18 <= own_y - rr <= chart.bottom:
                    continue
                label_layout.blit_line(
                    s, message("map.tooltip.range_value",
                               range=f"{max_nm * ring_index / 4.0:g}"),
                    (int(own_x) + 4, int(own_y - rr) + 1, 80, 18),
                    config.COLOR_TEXT_DIM, size=layout.MIN_OPERATIONAL_FONT)
            if layer("compass") and _ring_visible((own_x, own_y), radar_radius, chart):
                # Bearing scale on the outer ring with the own course mark.
                opz_display_view.draw_compass(s, chart, (own_x, own_y), radar_radius,
                                              game.ship.course)

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
                            s, _scale_color(theme.pick((75, 180, 105), (4, 120, 87)), .25 + .75 * glow),
                            view.world_to_screen(*first), view.world_to_screen(*second), 2)

            if radar_live:
                _draw_radar_clutter(game, s, (own_x, own_y), int(radar_radius))
                ang = math.radians(game.radar_sweep_bearing())
                pygame.draw.line(s, theme.pick((70, 190, 130), (4, 120, 87)), (own_x, own_y),
                                 (own_x + radar_radius * math.sin(ang),
                                  own_y - radar_radius * math.cos(ang)), 2)
            fx = getattr(game, "map_fx", None)
            if fx is not None:
                map_fx_view.draw_fx(s, fx.rows("frigate", game.sim_t), view.world_to_screen,
                                    px_per_nm, chart, config.COLOR_GEO_BG)
            nato_symbols.draw_symbol(s, (own_x, own_y), "FRIEND", "SURFACE", 18)
            nato_symbols.draw_motion_vector(
                s, (own_x, own_y), game.ship.course, game.ship.speed,
                px_per_nm, config.COLOR_TEXT, minutes=vector_min, max_px=vector_max_px)

        # Own-force aircraft is datalink truth, not a radar/sensor track.
        helo = getattr(game, "helo", None)
        if helo is not None and helo.airborne:
            hx, hy = view.world_to_screen(helo.x, helo.y)
            if chart.collidepoint(hx, hy):
                hcol = nato_symbols.draw_symbol(s, (hx, hy), "FRIEND", "ROTARY", 17)
                # Speed over ground on the own ship's time base (none in the hover).
                end = nato_symbols.draw_motion_vector(
                    s, (hx, hy), helo.course, getattr(helo, "ground_speed_kn", 0.0),
                    px_per_nm, hcol, minutes=vector_min, max_px=min(chart.size) * .3)
                if end is not None:
                    label_layout.reserve_segment((hx, hy), end)
                label_layout.blit_line(s, "HSP-5 DL",
                                 (int(hx) + 13, int(hy) - 10, 94, 19), hcol, size=12)
        _draw_mpa(game, s, chart, view, px_per_nm, page)
        _draw_consort(game, s, chart, view, px_per_nm, page)
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
            label_layout.blit_line(s, raw_text(label),
                             (int(wx) + 10, int(wy) - 9, 80, 17), wcol, size=12)
        cic_tracks = (game.opz_tracks() if hasattr(game, "opz_tracks")
                      else game.radar_tracks())
        selected_id = game.opz_selected_track_id
        plotted = {}
        # Track trails under the live symbols, in each track's colour.
        trail_minutes = opz_display.trail_minutes(shown)
        if trail_minutes > 0.0 and hasattr(game, "opz_tracks"):
            opz_display_view.draw_trails(
                game, s, chart, view,
                [t for t in cic_tracks if _observation_position(t)[0] is not None],
                trail_minutes,
                {t.track_id: nato_symbols.AFFILIATION_COLORS[game.opz_affiliation(t.track_id)]
                 for t in cic_tracks})
        for track in (t for t in cic_tracks if layer("bearings")
                      and _observation_position(t)[0] is None):
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
                                            px_per_nm, col, minutes=vector_min,
                                            max_px=vector_max_px)
            text = opz_display_view.track_label(shown, track["source"])
            if text is not None:
                label_layout.blit_line(s, text, (int(sx) - 22, int(sy) - 21, 66, 18),
                                       col, size=12)

        # Unmarked mast/snorkel echoes: a bare afterglow dot, no symbol or label,
        # dimming with the time since the sweep painted it.
        for blip in (game.radar_blip_view() if hasattr(game, "radar_blip_view") else []):
            px, py = view.world_to_screen(blip["x"], blip["y"])
            if not chart.collidepoint(px, py):
                continue
            fade = 1.0 - (game.sim_t - blip["t"]) / config.RADAR_BLIP_LIFE_S
            pygame.draw.circle(s, _scale_color(theme.pick((120, 255, 150), (5, 150, 105)), max(.2, fade)),
                               (int(px), int(py)), 3)

        # Gemeinsames Lagebild: Oberflaeche, Luft und Flugkoerper im selben Scope.
        for track in (t for t in cic_tracks if _observation_position(t)[0] is not None):
            observed_x, observed_y = _observation_position(track)
            bx, by = view.world_to_screen(observed_x, observed_y)
            if not chart.collidepoint(bx, by):
                continue
            plotted[track.track_id] = (bx, by)
            # Furthest-on circle: how far the contact can have gone since its fix.
            reach = map_fx.furthest_on_nm(track["kind"], game.sim_t - track.last_seen)
            if reach is not None and layer("uncertainty"):
                map_fx_view.draw_furthest_on(s, bx, by, reach * px_per_nm, chart, config.COLOR_GEO_BG)
            if track["source"].startswith("RADAR"):
                glow = _radar_glow(game, observations.bearing(track, game.ship))
                if glow > 0.0:
                    pygame.draw.circle(s, _scale_color(theme.pick((120, 255, 150), (5, 150, 105)), glow),
                                       (int(bx), int(by)), 3)
            affiliation = game.opz_affiliation(track["track_id"])
            domain = nato_symbols.domain_for_kind(track["kind"])
            col = nato_symbols.draw_symbol(
                s, (bx, by), affiliation, domain, 16,
                track["track_id"] == selected_id)
            nato_symbols.draw_motion_vector(s, (bx, by), track.course, track.speed_kn,
                                            px_per_nm, col, minutes=vector_min,
                                            max_px=vector_max_px)
            text = opz_display_view.track_label(shown, track["label"])
            if text is not None:
                label_layout.blit_line(s, text, (int(bx) + 12, int(by) - 10, 118, 19),
                                       col, size=12)

        for fusion in (track for track in cic_tracks if track.source == "FUSION"):
            if fusion.track_id not in plotted:
                continue
            for member in fusion.members:
                if member in plotted:
                    pygame.draw.line(s, config.COLOR_WARN, plotted[fusion.track_id],
                                     plotted[member], 1)

        if layer("cpa") and hasattr(game, "selected_opz_track"):
            # The selected track's closest point of approach (its own report).
            selected_track = game.selected_opz_track()
            if (selected_track is not None and selected_track.track_id in plotted
                    and _observation_position(selected_track)[0] is not None):
                opz_display_view.draw_cpa(game, s, chart, view, selected_track)

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
    opz_display_view.draw_radar_switches(game, s, chart, not game.damage.station_down("opz"))
    side_top = regions["sidebar"].y
    side_h = regions["sidebar"].h
    sb_box = layout.box(s, (regions["sidebar"].x + 4, side_top,
                            regions["sidebar"].w - 8, side_h - 8),
                        "opz.display.heading" if page == 4 else "panel.opz_status")
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
        # One label column for the five status rows.
        label_face = layout.font(15)
        label_w = max(label_face.size(localize(key))[0] for key in
                      ("opz.label.radar", "opz.label.scope", "opz.label.picture",
                       "opz.label.vls", "opz.label.ciws")) + 12
        row = layout.line_pitch(15, 6)
        layout.status_line(s, x, py, w, "opz.label.radar", radar_state,
                           label_w=label_w, size=15)
        # Surface and air radar switch with a click on their state (R, Shift+R).
        pointer.add_line_keys((x + label_w + 4, py, w - label_w - 4,
                               layout.font(15).get_linesize()), radar_state, 15,
                              ("R", "Shift+R"), separator=" | ")
        py += row
        severity = game.radar_weather_severity()
        weather_key = ("opz.weather.clear" if severity <= 0.0 else
                       ("opz.weather.clutter" if severity < 1.0 else "opz.weather.heavy"))
        weather_color = config.COLOR_TEXT_DIM if severity <= 0.0 else config.COLOR_WARN
        layout.status_line(s, x, py, w, "opz.label.scope",
                            message("opz.line.scope", range=f"{max_nm:.0f}", sea=game.world.sea_state,
                                    weather=localize(weather_key)),
                            label_w=label_w, size=15, color=weather_color)
        py += row
        surface_count = sum(1 for t in cic_tracks
                            if t["kind"] in ("SURFACE", "AIS"))
        hoj_count = sum(1 for t in cic_tracks if t["source"] == "HOJ")
        layout.status_line(s, x, py, w, "opz.label.picture",
                            message("opz.line.picture", surface=surface_count,
                                    hoj=hoj_count),
                            label_w=label_w, size=15)
        py += row
        layout.status_line(s, x, py, w, "opz.label.vls",
                            message("opz.line.vls_chaff", count=game.vls_cells,
                                    total=getattr(game, "vls_loadout_total",
                                                  game.vls_cells),
                                    chaff=f"{game.chaff_cd:.0f}"),
                            label_w=label_w, size=15)
        py += row
        pointer.add_key((x, py, w, layout.font(15).get_linesize()), pygame.K_i)
        layout.status_line(s, x, py, w, "opz.label.ciws",
                            localize("opz.ciws.authorized" if game.ciws_authorized
                                     else "opz.ciws.withheld"),
                            label_w=label_w, size=15,
                            color=(config.COLOR_OK if game.ciws_authorized
                                   else config.COLOR_WARN))
        py += 30
        pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
        py += 8
        content_bottom = regions["classify"].top - 7
        suggestions = (game.opz_suggestions()[:OPZ_SUGGESTION_ROWS]
                       if hasattr(game, "opz_suggestions") else ())
        if suggestions:
            content_bottom -= 24 * (len(suggestions) + 1)
        if suggestions:
            # Correlation suggestions: U confirms the top one, Shift+U drops it.
            py = content_bottom + 2
            layout.blit_line(s, "opz.suggestions_heading", (x, py, w, 22),
                             config.COLOR_TEXT_DIM, size=14)
            py += 24
            for index, suggestion in enumerate(suggestions):
                first, second = game.opz_suggestion_labels(suggestion)
                layout.blit_line(s, message(
                    "opz.line.suggestion", prefix=">" if index == 0 else " ",
                    first=first, second=second,
                    bearing=f"{suggestion.bearing:03.0f}"),
                    (x, py, w, 22),
                    config.COLOR_WARN if index == 0 else config.COLOR_TEXT_DIM,
                    size=14)
                py += 24
    elif page == 2:
        _draw_mpa_sidebar(game, s, x, py, w, regions["classify"].top - 7)
    elif page == 3:
        _draw_consort_sidebar(game, s, x, py, w, regions["classify"].top - 7)
    elif page == 4:
        opz_display_view.draw_display_page(game, s, x, py, w, regions["classify"].top - 7)
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
                (message("opz.line.sources", sources=" · ".join(
                    localize("opz.source." + group) for group in source_groups(selected)))
                 if selected.source == "FUSION"
                 else message("opz.line.source", source=selected.source)),
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
        # The target page's orders as key chips (full mouse control); the
        # ESSM fire key stays a key: fire by click only at the weapons station.
        keys_top = content_bottom - len(OPZ_TARGET_KEYS) * 24
        for index, specs in enumerate(OPZ_TARGET_KEYS):
            _shortcut_footer(s, (x, keys_top + index * 24 + 2, w, 22), specs)
        content_bottom = keys_top - 4
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
        pygame.draw.rect(s, theme.c("raised"), rect, border_radius=4)
        pygame.draw.rect(s, theme.c("line_strong"), rect, 1, border_radius=4)
        layout.blit_line(s, key, rect, config.COLOR_TEXT, size=14,
                         align="center")
        pointer.add_hotspot(rect)       # opz_action_at takes the click

    scales = " ".join(
        f"[{scale:g}]" if scale == max_nm else f"{scale:g}"
        for scale in config.RADAR_RANGE_SCALES_NM)
    # The station footer row, like every other station's key legend.
    _draw_track_cards(game, s, regions["tracks"], selected_id)
    footer_rect = pygame.Rect(station.x + 8, station.bottom - 28, station.w - 16, 20)
    range_text_w = layout.text_width(
        layout.font(11), "Q/E " + localize("opz.footer.range") + f" {max_nm:g} NM  {scales}") + 24
    range_rect = pygame.Rect(footer_rect.x, footer_rect.y, range_text_w, footer_rect.h)
    layout.command_segment(s, range_rect, "Q/E", "opz.footer.range", "",
                           f"{max_nm:g} NM  {scales}", size=11)
    pointer.add_legend(range_rect, "Q/E")
    # Layer chips: what the chart draws now; a click moves one on.
    opz_display_view.draw_chips(game, s, pygame.Rect(
        range_rect.right + 8, footer_rect.y + 1,
        footer_rect.right - range_rect.right - 8, footer_rect.h - 2))
