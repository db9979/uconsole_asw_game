"""Helicopter deck view: waypoint chart, buoys, dipping sonar and the acoustic
pages (verbatim from ``stations_view``)."""

import math

import pygame
import numpy as np

from src.core import config
from src.core.i18n import display_value, localized, localize
from src.core.station import Station
from src.ui import layout
from src.ui import observations


from src.ui.stations.common import (_panel, _station_content_top, draw_station_page_tabs, message)
from src.ui.stations.opz import (_helo_dip_contact_line, helo_dip_contacts)


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
                 localize(message(
                     "helo.pattern_rule",
                     pattern=display_value("buoy_pattern",
                                           getattr(helo, "pattern", "single")),
                     remaining=len(getattr(helo, "pattern_queue", ())),
                     mad=localize("ui.active" if getattr(helo, "mad_mode", False)
                                  else "helo.standby"))),
                 localize("view.helo.roe"))
        colors = (config.COLOR_TEXT, margin_color, config.COLOR_TEXT_DIM,
                  config.COLOR_OK, config.COLOR_WARN,
                  config.COLOR_OK if dip_contacts else config.COLOR_TEXT_DIM,
                  config.COLOR_OK if (getattr(helo, "pattern_queue", ())
                                      or getattr(helo, "mad_mode", False))
                  else config.COLOR_TEXT_DIM,
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
