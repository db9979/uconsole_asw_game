"""W0: Stations-Views im rechten Hauptpanel (STATION_RECT: 640x510).

Alle Views rendern ausschließlich innerhalb des Rechtecks
(config.STATION_RECT) – die Seekarte bleibt links sichtbar.

Since plan 1.3 (phase 2, step 5) the views live in ``src.ui.stations``; this
module re-exports them and keeps the station-wide hit test."""

import math

import pygame

from src.core import config
from src.core.i18n import localize, localized
from src.core.station import Station
from src.ui import layout
from src.ui import observations
from src.ui import chart_symbols, nato_symbols  # noqa: F401  (patched by tests)



from src.ui.stations.common import (  # noqa: F401
    _hfdf_error_deg,
    message,
    STATE_LABEL,
    MORSE,
    _to_morse,
    _srect,
    _panel,
    _shortcut_footer,
    PAGE_TAB_H,
    PAGE_TAB_GAP,
    _station_page_tab_rects,
    draw_station_page_tabs,
    station_page_tab_at,
    _station_content_top,
    draw_autocrew_overview,
    _observation_bearing,
    _observation_position,
    _displayed_bearing,
    _state_color,
    _compartment_name)
from src.ui.stations.bridge import (  # noqa: F401
    _draw_bridge_weather,
    draw_bridge_view,
    _LOOKOUT_KIND_COLORS,
    _lookout_scope_rect,
    _draw_bridge_lookout)
from src.ui.stations.opz import (  # noqa: F401
    OPZ_DOMAIN_CODES,
    OPZ_DOMAIN_COLORS,
    helo_dip_contacts,
    _helo_dip_contact_line,
    _lookout_line,
    _track_tooltip,
    opz_hit_target,
    opz_regions,
    opz_ppi_rect,
    _opz_view,
    _opz_bearing_ray,
    _opz_track_point,
    opz_action_at,
    _opz_radar_range_nm,
    _radar_sweep_age,
    _radar_glow,
    _scale_color,
    _draw_radar_clutter,
    _bounds_intersect_circle,
    _contour_segments_in_circle,
    _opz_basemap_surface,
    draw_opz_view)
from src.ui.stations.eloka import (  # noqa: F401
    _near_point,
    eloka_regions,
    _eloka_visible_tracks,
    _draw_eloka_signal,
    eloka_track_at,
    draw_eloka_view)
from src.ui.stations.radio import (  # noqa: F401
    draw_radio_view)
from src.ui.stations.engine import (  # noqa: F401
    draw_engine_view)
from src.ui.stations.helicopter import (  # noqa: F401
    helicopter_regions,
    _HELICOPTER_WATERFALL_CACHE,
    _helicopter_waterfall,
    _helicopter_trace,
    _HELO_ACOUSTIC_PAGES,
    _HELO_ACOUSTIC_TABS,
    _helicopter_acoustic_observations,
    helicopter_acoustic_geometry,
    helicopter_acoustic_hit,
    _draw_helicopter_acoustic_view,
    draw_helicopter_view)
from src.ui.stations.damage import (  # noqa: F401
    damage_regions,
    damage_compartment_at,
    draw_damage_view)

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
