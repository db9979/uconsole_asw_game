"""Helicopter deck view: waypoint chart, buoys, dipping sonar and the acoustic
pages (verbatim from ``stations_view``)."""

import math

import pygame
import numpy as np

from src.core import config, status_tips
from src.core.i18n import nm_unit, display_value, localized, localize, raw_text
from src.core.station import Station
from src.ui import layout, pointer
from src.ui import hires, theme
from src.ui import observations
from src.air import helicopter as helicopter_physics


from src.ui.stations.common import (_panel, _shortcut_footer, _station_content_top,
                                    draw_station_page_tabs, fire_button, message)
from src.ui.stations.opz import (_helo_dip_contact_line, helo_dip_contacts)


# --- Helikopter-Deck --------------------------------------------------------

# Status page: least height of the console body beside the fuel tank, and
# the least height the deck-motion gauge needs to be drawn at all (px).
STATUS_BODY_MIN_H = 140
DECK_MIN_H = 80
# Text size of the stores counts (torpedoes, buoys) on the status page.
STORE_VALUE_SIZE = 20

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
        # The status console: a state lamp strip and six readout rows beside
        # the fuel tank and the home rose; sized from the fonts so large text
        # grows it.
        title_h = layout.font(16, True).get_linesize() + 16
        lamp_h = layout.line_pitch(14, 0) + 8
        row_h = max(24, layout.font(15).get_linesize() + 4)
        # Stores (two rows of two cells) and the systems lamps (two rows);
        # the cells always keep their room, the lamps and the deck gauge
        # only when the window has it.
        cell_h = layout.font(14).get_linesize() + layout.font(STORE_VALUE_SIZE).get_linesize() + 10
        cells_h = title_h + 2 * cell_h + 6 + 8
        status_h = title_h + lamp_h + 8 + max(STATUS_BODY_MIN_H, row_h * 6) + 8
        status_h = min(status_h, max(int(available * 0.4), available - gap - cells_h))
        # Two lamp rows, else one (flight weather), else none, before the
        # deck-motion gauge gives way.
        for lamp_rows in (2, 1, 0):
            resources_h = cells_h + lamp_rows * (lamp_h + 4) + 4
            deck_h = available - status_h - resources_h - 2 * gap
            if deck_h >= DECK_MIN_H:
                break
        if deck_h < DECK_MIN_H:
            # No room for the deck-motion gauge (small window, large text).
            deck_h = 0
            resources_h = max(1, available - status_h - gap)
        return {
            "station": station,
            "status": pygame.Rect(x, top, width, status_h),
            "resources": pygame.Rect(x, top + status_h + gap, width, resources_h),
            "deck": (pygame.Rect(x, top + status_h + resources_h + 2 * gap, width, deck_h)
                     if deck_h else empty),
            "rules": empty,
        }
    else:
        return {
            "station": station,
            "status": empty,
            "resources": empty,
            "deck": empty,
            "rules": pygame.Rect(x, top, width, available),
        }


_HELICOPTER_WATERFALL_CACHE = {}


def _helicopter_waterfall(screen, rect, rows, *, receiver, amber=False):
    """Render bounded acoustic history in one vectorized surface, in the
    ship sonar's phosphor (newest row on top, fading trail)."""
    from src.ui import sonar_view
    pygame.draw.rect(screen, sonar_view.NAVY, rect)
    if rows and rect.w > 0 and rect.h > 0:
        key = (receiver, receiver.sequence, rect.size, amber, theme.revision(),
               hires.SCALE)
        scaled = _HELICOPTER_WATERFALL_CACHE.get(key)
        if scaled is None:
            values = np.clip(np.asarray(rows[-64:], dtype=np.float32), 0, 1)
            if values.ndim == 2 and values.shape[1] > 0:
                pixels = sonar_view.waterfall_pixels(
                    values, contrast=1.6, palette="amber" if amber else "green")
                surface = pygame.surfarray.make_surface(pixels.transpose(1, 0, 2))
                scaled = hires.scaled_pixels(surface, rect.size)
                if len(_HELICOPTER_WATERFALL_CACHE) >= 4:
                    _HELICOPTER_WATERFALL_CACHE.clear()
                _HELICOPTER_WATERFALL_CACHE[key] = scaled
        if scaled is not None:
            screen.blit(scaled, rect)
    for tick in range(1, 5):
        x = rect.x + tick * rect.w // 5
        y = rect.y + tick * rect.h // 5
        pygame.draw.line(screen, config.COLOR_GRID, (x, rect.y), (x, rect.bottom - 1))
        pygame.draw.line(screen, config.COLOR_GRID, (rect.x, y), (rect.right - 1, y))
    pygame.draw.rect(screen, config.COLOR_SONAR_RING, rect, 1)
    layout.corner_brackets(screen, rect)


def _helicopter_trace(screen, rect, values, color):
    from src.ui import console, sonar_view
    pygame.draw.rect(screen, sonar_view.NAVY, rect)
    for tick in range(1, 5):
        pygame.draw.line(screen, config.COLOR_GRID,
                         (rect.x, rect.y + tick * rect.h // 5),
                         (rect.right - 1, rect.y + tick * rect.h // 5))
    if len(values) > 1:
        points = [(rect.x + int(i * (rect.w - 2) / (len(values) - 1)),
                   rect.bottom - 2 - int(max(0, min(1, value)) * (rect.h - 4)))
                  for i, value in enumerate(values)]
        # A dim fill under the trace, then the bright line (a phosphor A-scope).
        pygame.draw.polygon(screen, console._mix(sonar_view.NAVY, color, .22),
                            [(points[0][0], rect.bottom - 2), *points,
                             (points[-1][0], rect.bottom - 2)])
        pygame.draw.lines(screen, color, False, points, 2)
    pygame.draw.rect(screen, config.COLOR_SONAR_RING, rect, 1)
    layout.corner_brackets(screen, rect)


def _dip_scope(screen, center, radius):
    """The dipping sonar's scope: dark disc, range rings, 10 degree ticks, north."""
    from src.ui import sonar_view
    cx, cy = (int(v) for v in center)
    if radius < 12:
        return
    pygame.draw.circle(screen, sonar_view.NAVY, (cx, cy), radius)
    for fraction in (.25, .5, .75):
        pygame.draw.circle(screen, config.COLOR_GRID, (cx, cy), max(1, int(radius * fraction)), 1)
    pygame.draw.circle(screen, config.COLOR_SONAR_RING, (cx, cy), radius, 1)
    for step in range(0, 360, 10):
        major = step % 90 == 0
        theta = math.radians(step)
        inner = radius - (9 if major else 5 if step % 30 == 0 else 3)
        pygame.draw.line(screen, config.COLOR_TEXT_DIM if step % 30 == 0 else config.COLOR_SONAR_RING,
                         (cx + math.sin(theta) * inner, cy - math.cos(theta) * inner),
                         (cx + math.sin(theta) * radius, cy - math.cos(theta) * radius), 1)
    for step in (0, 90, 180, 270):
        theta = math.radians(step)
        pygame.draw.line(screen, config.COLOR_GRID, (cx, cy),
                         (cx + math.sin(theta) * radius, cy - math.cos(theta) * radius), 1)
    layout.blit_line(screen, "N", (cx - 10, cy - radius - 20, 20, 18),
                     config.COLOR_TEXT_DIM, size=14, align="center")
    pygame.draw.circle(screen, config.COLOR_OK, (cx, cy), 3)


def _dip_lamps(game, helo):
    """Dome, ping and water entry as annunciator lamps (display only)."""
    dome = {"DEPLOYED": "on", "DEPLOYING": "caution", "RETRIEVING": "caution"}.get(
        helo.dip_state, "off")
    ping = ("on" if helo.dip_ping_ready else
            "caution" if helo.dip_available else "off")
    water = ("on" if helo.airborne and helo.water_entry_clear(game.world) else "off")
    # Dome and ping lamps are switches: Y lowers/raises, Shift+A pings.
    return (("helo.lamp.dome", "", dome, "Y"), ("helo.lamp.ping", "", ping, "Shift+A"),
            ("helo.lamp.water", "", water))


_HELO_ACOUSTIC_PAGES = (("helo.acoustic.broadband", "helo.acoustic.broadband_axis"),
                        ("helo.acoustic.lofar", "helo.acoustic.lofar_axis"),
                        ("helo.acoustic.demon", "helo.acoustic.demon_axis"))
_HELO_ACOUSTIC_TABS = ("helo.acoustic.tab_broadband", "helo.acoustic.tab_lofar",
                       "helo.acoustic.tab_demon")


def _select_dip_contact(game, contact):
    if contact.target_id in game.sonar.contacts:
        game.selected_contact = contact


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
        pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE if index == page else theme.c("raised"), tab)
        pygame.draw.rect(screen, config.COLOR_SONAR_RING if index == page
                         else config.COLOR_GRID, tab, 1)
        layout.blit_line(screen, _HELO_ACOUSTIC_TABS[index], tab,
                         config.COLOR_TEXT if index == page else config.COLOR_TEXT_DIM,
                         size=14, align="center")
        pointer.add_hotspot(tab)        # helicopter_acoustic_hit takes the click
    pointer.add_hotspot(geo["back"])
    pygame.draw.rect(screen, theme.c("raised"), geo["back"])
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
    from src.ui import console
    levels = ("on" if ready else "caution",
              "on" if game.helo_listen_bearing is not None else "off",
              "on" if game.helo_audition.audition_mode != "BROADBAND" else "off",
              "on" if audible else "off")
    for item, box, level, key, name in zip(status, geo["statuses"], levels,
                                           (None, None, None, "J"),
                                           ("source", "bearing", "filter", "audio")):
        pointer.add_spec(box, key)      # the sound box switches like J
        pointer.add_tip(box, status_tips.lazy(lambda: status_tips.helicopter_acoustic(game), name))
        pygame.draw.rect(screen, config.COLOR_PANEL_BG, box)
        pygame.draw.rect(screen, console.level_color(level) if level != "off"
                         else config.COLOR_SONAR_RING, box, 1)
        console.led(screen, (box.x + 12, box.centery), 5, level)
        layout.blit_line(screen, item, (box.x + 24, box.y + 3, box.w - 30, box.h - 6),
                         config.COLOR_TEXT, size=13)
    main, rail, plot = geo["main"], geo["rail"], geo["plot"]
    for box in (main, rail):
        pygame.draw.rect(screen, config.COLOR_PANEL_BG, box)
        pygame.draw.rect(screen, config.COLOR_SONAR_RING, box, 1)
        layout.corner_brackets(screen, box)
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
        pygame.draw.rect(screen, config.COLOR_TAB_ACTIVE if selected else theme.c("raised"), row)
        layout.blit_line(screen, message("helo.acoustic.contact",
            contact=contact.id, bearing=f"{observed:05.1f}"),
            (row.x + 7, row.y + 3, row.w - 14, 19), config.COLOR_TEXT, size=14)
        layout.blit_line(screen, "helo.acoustic.qualified" if contact.helo_qualified
                         else "helo.acoustic.unqualified",
                         (row.x + 7, row.y + 22, row.w - 14, 18),
                         config.COLOR_OK if contact.helo_qualified
                         else config.COLOR_TEXT_DIM, size=12)
    footer = geo["footer"]
    # Four main keys in the station footer row; the rest are in F1.
    _shortcut_footer(screen, (footer.x + 2, footer.y + (footer.h - 20) // 2 + 2,
                              footer.w - 4, 20), (
        ("help.key.page_arrows", "helo.footer.view"),
        ("←/→", "helo.footer.bearing"),
        ("I/O", "helo.footer.level"),
        ("J", "helo.footer.sound"),
    ))


DECK_STEEL = (70, 110, 118)
DECK_SEA = (18, 60, 74)


def _draw_deck_gauge(game, s, region) -> None:
    """The flight deck's motion: the stern seen from aft rolling against the
    horizon, the pitch bar with its limit, and the quiet-period bar that
    fills while the deck stays inside its limits (a launch/recovery window)."""
    if region.w < 60 or region.h < 60:
        return
    x, y, w, h = layout.box(s, region, "helo.deck.title")
    ship = game.ship
    roll_deg = float(getattr(ship, "roll", 0.0))
    pitch_deg = float(getattr(ship, "pitch", 0.0))
    quiet = float(getattr(ship, "deck_quiet_s", 0.0))
    open_ = helicopter_physics.deck_window_open(quiet, roll_deg, pitch_deg)
    inside = helicopter_physics.deck_within_limits(roll_deg, pitch_deg)
    label_h = layout.font(14).get_linesize()
    bar_h = 10
    # Left: the picture; right: the values, the quiet-period bar and state.
    picture = pygame.Rect(x, y, min(w // 2, 260), h)
    tx, tw = picture.right + 12, max(1, x + w - picture.right - 12)
    cx, cy = picture.centerx - 10, picture.centery
    # Horizon (fixed) and the stern silhouette tilted by the roll.
    pygame.draw.rect(s, DECK_SEA, (picture.x, cy, picture.w - 22, picture.bottom - cy))
    pygame.draw.line(s, config.COLOR_GRID, (picture.x, cy), (picture.right - 22, cy), 1)
    half = min(picture.w - 22, picture.h * 2) * 0.32
    roll = math.radians(roll_deg)
    ux, uy = math.cos(roll), math.sin(roll)

    def turned(shape):
        return [(cx + px * ux - py * uy, cy + px * uy + py * ux) for px, py in shape]

    color = config.COLOR_OK if open_ else config.COLOR_WARN if inside else config.COLOR_DANGER
    # Hull below the deck, the hangar above it (seen from astern).
    points = turned([(-half, 0), (half, 0), (half * 0.8, half * 0.45), (-half * 0.8, half * 0.45)])
    pygame.draw.polygon(s, DECK_STEEL, points)
    pygame.draw.polygon(s, DECK_STEEL, turned([(-half * 0.55, 0), (half * 0.55, 0),
                                               (half * 0.5, -half * 0.5),
                                               (-half * 0.5, -half * 0.5)]))
    pygame.draw.line(s, color, points[0], points[1], 3)
    for limit in (-helicopter_physics.DECK_ROLL_LIMIT_DEG, helicopter_physics.DECK_ROLL_LIMIT_DEG):
        rad = math.radians(limit)
        tip = (cx + half * 1.1 * math.cos(rad), cy + half * 1.1 * math.sin(rad))
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (cx + half * 0.95 * math.cos(rad),
                                                    cy + half * 0.95 * math.sin(rad)), tip, 1)
    # Pitch bar at the right of the picture: centre is level, ticks the limit.
    bar = pygame.Rect(picture.right - 14, picture.y + 4, 8, picture.h - 8)
    pygame.draw.rect(s, config.COLOR_GRID, bar, 1)
    scale = bar.h / 2 / (helicopter_physics.DECK_PITCH_LIMIT_DEG * 2.0)
    for limit in (-helicopter_physics.DECK_PITCH_LIMIT_DEG, helicopter_physics.DECK_PITCH_LIMIT_DEG):
        ty = bar.centery - limit * scale
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (bar.x - 3, ty), (bar.right + 2, ty), 1)
    py = bar.centery - max(-2 * helicopter_physics.DECK_PITCH_LIMIT_DEG,
                           min(2 * helicopter_physics.DECK_PITCH_LIMIT_DEG, pitch_deg)) * scale
    pygame.draw.rect(s, color, (bar.x + 1, py - 2, bar.w - 2, 4))
    ly = y + max(0, (h - 3 * label_h - bar_h - 6) // 2)
    layout.blit_line(s, message("helo.deck.roll", roll=f"{abs(roll_deg):.1f}",
                                limit=f"{helicopter_physics.DECK_ROLL_LIMIT_DEG:.0f}"),
                     (tx, ly, tw, label_h), config.COLOR_TEXT, size=14)
    layout.blit_line(s, message("helo.deck.pitch", pitch=f"{abs(pitch_deg):.1f}",
                                limit=f"{helicopter_physics.DECK_PITCH_LIMIT_DEG:.1f}"),
                     (tx, ly + label_h, tw, label_h), config.COLOR_TEXT, size=14)
    fill = min(1.0, quiet / helicopter_physics.DECK_WINDOW_S)
    track = pygame.Rect(tx, ly + 2 * label_h + 3, tw, bar_h)
    pygame.draw.rect(s, config.COLOR_GRID, track, 1)
    pygame.draw.rect(s, color, (track.x + 1, track.y + 1, int((track.w - 2) * fill), track.h - 2))
    layout.blit_line(s, "helo.deck.open" if open_ else "helo.deck.wait",
                     (tx, track.bottom + 3, tw, label_h), color, size=14)


def flight_weather(game):
    """The ship's flight-weather decision (own instruments), if available."""
    query = getattr(game, "helicopter_weather", None)
    return query() if callable(query) else None


def _clock(seconds: float) -> str:
    left = int(math.ceil(max(0.0, seconds)))
    return f"{left // 60}:{left % 60:02d}"


def helo_state_text(helo):
    """The helicopter's state for the status rows: in the hangar with a
    launch ordered, the start preparation with its time left (m:ss), then
    the refuelling to the launch minimum, or ready and waiting for the deck
    window; without an order, the refuelling to a full tank."""
    if getattr(helo, "preparing", False):
        if helo.prep_s > 0.0:
            return localize(message("helo.prep.running", time=_clock(helo.prep_s)))
        if not helo.fuel_ready:
            return localize(message("helo.refuel.running", time=_clock(
                helo.refuel_left_s(config.HELO_LAUNCH_MIN_FUEL_S))))
        return localize(message("helo.prep.ready"))
    if getattr(helo, "refuelling", False):
        return localize(message("helo.refuel.running", time=_clock(helo.refuel_left_s())))
    return localize("enum.helo." + helo.state)


def helo_status_reason(helo):
    """Why the helicopter in the hangar is not yet in the air (tooltip line),
    or None."""
    if helo.state != "HANGAR":
        return None
    fuel = f"{helo.fuel_s / 60:.0f}"
    full = f"{config.HELO_FUEL_S / 60:.0f}"
    if getattr(helo, "preparing", False):
        if helo.prep_s > 0.0:
            return message("helo.tooltip.prep_reason", time=_clock(helo.prep_s), fuel=fuel, full=full)
        if not helo.fuel_ready:
            return message("helo.tooltip.fuel_wait_reason", fuel=fuel,
                           minimum=f"{config.HELO_LAUNCH_MIN_FUEL_S / 60:.0f}",
                           time=_clock(helo.refuel_left_s(config.HELO_LAUNCH_MIN_FUEL_S)))
        return "helo.tooltip.window_reason"
    if getattr(helo, "refuelling", False):
        return message("helo.tooltip.refuel_reason", fuel=fuel, full=full,
                       time=_clock(helo.refuel_left_s()))
    return "helo.tooltip.ready_reason"


def _tips(game, *names) -> list:
    """Hover notes of the named lamps (``status_tips.helicopter``), worked
    out only while the pointer is over one."""
    if not callable(getattr(game, "helicopter_weather", None)):
        return [None] * len(names)
    return [status_tips.lazy(lambda: status_tips.helicopter(game), name) for name in names]


def state_lamps(game, helo, weather) -> list:
    """The state strip: hangar, deck (cleared to launch), airborne, dipping,
    returning; exactly one is lit, LOST lights the airborne lamp red."""
    state = helo.state
    dip = getattr(helo, "dip_state", "STOWED")
    damage = getattr(game, "damage", None)
    deck_down = bool(damage is not None and damage.station_down("flightdeck"))
    if state != "HANGAR":
        deck = "off"
    elif deck_down:
        deck = "alarm"
    else:
        deck = "on" if weather is not None and weather["launch_safe"] else "caution"
    airborne = state == "AUF"
    return [
        ("helo.console.state.hangar", "",
         "caution" if getattr(helo, "preparing", False) or getattr(helo, "refuelling", False)
         else "on" if state == "HANGAR" else "off"),
        ("helo.console.state.deck", "", deck),
        ("helo.console.state.airborne", "",
         "alarm" if state == "VERLOREN" else "on" if airborne and dip == "STOWED" else "off"),
        ("helo.console.state.dipping", "",
         "on" if airborne and dip == "DEPLOYED" else
         "caution" if airborne and dip in ("DEPLOYING", "RETRIEVING") else "off"),
        ("helo.console.state.returning", "", "caution" if state == "ZURUECK" else "off"),
    ]


def fuel_level(helo) -> str:
    if not helo.airborne:
        return "alarm" if helo.state == "VERLOREN" else "on"
    if helo.fuel_s <= config.HELO_FUEL_RESERVE_S:
        return "alarm"
    return "caution" if helo.fuel_s <= config.HELO_FUEL_RESERVE_S * 1.5 else "on"


def home_polar(game, helo):
    """(bearing, distance NM, minutes) from the helicopter back to the ship."""
    dx, dy = game.ship.x - helo.x, game.ship.y - helo.y
    distance = math.hypot(dx, dy)
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    minutes = distance / max(1e-6, config.kn_to_nm_per_s(config.HELO_SPEED_KN)) / 60.0
    return bearing, distance, minutes


def _draw_status_console(game, s, regions, helo, state_label, state_color, distance) -> None:
    """Flight status: state lamps, fuel tank, home rose and readouts."""
    from src.ui import console
    region = regions["status"]
    sx, sy, sw, sh = layout.box(s, region, "panel.flight_status", border=state_color)
    weather = flight_weather(game)
    lamp_h = layout.line_pitch(14, 0) + 8
    used = console.lamp_grid(s, (sx, sy, sw, lamp_h), console.with_tips(
        state_lamps(game, helo, weather), _tips(game, "state_hangar", "state_deck",
                                               "state_airborne", "state_dipping",
                                               "state_returning")), 5, size=14)
    top = sy + used + 8
    body_h = sy + sh - top
    if body_h < 60:
        return
    # Fuel tank: the fuel aboard (in the hangar it fills while refuelling).
    tank_w = 84
    hangar = helo.state == "HANGAR"
    fraction = max(0.0, helo.fuel_s / config.HELO_FUEL_S)
    minutes = helo.fuel_s / 60.0
    tank = pygame.Rect(sx, top, tank_w, body_h)
    console.tank(s, tank, fraction, label="helo.console.fuel",
                 text=message("helo.line.fuel", fuel=f"{minutes:.0f}"), level=fuel_level(helo))
    row = layout.font(16).get_linesize()
    tube_h = tank.h - 2 * row - 8
    if tube_h >= 12:
        # The reserve the helicopter turns home on.
        ry = tank.y + row + 4 + tube_h - round(tube_h * config.HELO_FUEL_RESERVE_S
                                                / config.HELO_FUEL_S)
        pygame.draw.line(s, config.COLOR_WARN, (tank.centerx - 22, ry), (tank.centerx + 22, ry), 2)
    # Home rose: the bearing back to the ship, the aircraft's course needle.
    # It gives way first so the readouts beside it keep their full text
    # (large text): labels plus the widest value, the endurance line.
    label_keys = ("ui.condition", "helo.console.endurance", "helo.console.bingo",
                  "helo.console.home", "helo.console.course", "helo.dip_sonar")
    readout_font = layout.font(15)
    readout_need = (max(int(readout_font.size(localize(key))[0]) for key in label_keys) + 10
                    + int(readout_font.size(localize(message(
                        "helo.console.endurance_value", fuel="120", hover="92")))[0]) + 6)
    rose_extra = 2 * (layout.font(11).size("090")[0] - 14)
    rose_size = max(0, min(body_h, 190, sw // 3,
                           sw - tank_w - 6 - rose_extra - 8 - readout_need))
    # Wider than tall: "270" and "090" stand beside the ring inside the rect.
    rose = pygame.Rect(sx + tank_w + 6, top + (body_h - rose_size) // 2,
                       rose_size + rose_extra, rose_size)
    home = home_polar(game, helo) if helo.airborne else None
    strobes = [(home[0], config.COLOR_OK, 3, 0, 0.0)] if home else []
    console.bearing_rose(s, rose, strobes, course=helo.course if helo.airborne else None,
                         title="helo:home")
    # Readouts right of the rose.
    tx = rose.right + 8
    tw = sx + sw - tx
    row_h = max(24, layout.font(15).get_linesize() + 4)
    labels = label_keys
    label_w = min(tw // 2, max(int(layout.font(15).size(localize(key))[0]) for key in labels) + 10)
    dip_state = getattr(helo, "dip_state", "STOWED")
    if helo.airborne:
        return_s = distance / max(.001, config.kn_to_nm_per_s(config.HELO_SPEED_KN))
        margin_s = helo.fuel_s - return_s - config.HELO_FUEL_RESERVE_S
        endurance = message("helo.console.endurance_value", fuel=f"{helo.fuel_s / 60:.0f}",
                            hover=f"{helo.fuel_s / helicopter_physics.HOVER_FUEL_FACTOR / 60:.0f}")
        bingo = message("helo.console.bingo_value", margin=f"{margin_s / 60:+.0f}")
        bingo_color = (config.COLOR_DANGER if margin_s < 0 else
                       config.COLOR_WARN if margin_s < 300 else config.COLOR_OK)
        home_text = message("helo.console.home_value", bearing=f"{home[0]:03.0f}",
                            range=f"{home[1]:.1f}", minutes=f"{home[2]:.0f}")
        course = message("helo.line.course", course=f"{helo.course:05.1f}")
    else:
        endurance = (message("helo.console.endurance_value",
                             fuel=f"{helo.fuel_s / 60:.0f}",
                             hover=f"{helo.fuel_s / helicopter_physics.HOVER_FUEL_FACTOR / 60:.0f}")
                     if hangar else raw_text("--"))
        bingo, bingo_color, home_text, course = raw_text("--"), config.COLOR_TEXT_DIM, \
            localize("enum.helo." + helo.state), raw_text("--")
    dip = message("helo.console.dip_value", state=localize("enum.helo_dip." + dip_state),
                  depth=f"{getattr(helo, 'dip_depth_m', 0.0):.0f}",
                  target=f"{getattr(helo, 'dip_depth_target_m', config.HELO_DIP_DEPTH_DEFAULT_M):.0f}")
    rows = ((labels[0], state_label, state_color), (labels[1], endurance, config.COLOR_TEXT),
            (labels[2], bingo, bingo_color),
            (labels[3], home_text, config.COLOR_TEXT if helo.airborne else config.COLOR_TEXT_DIM),
            (labels[4], course, config.COLOR_TEXT),
            (labels[5], dip, config.COLOR_OK if dip_state == "DEPLOYED" else
             config.COLOR_WARN if dip_state != "STOWED" else config.COLOR_TEXT_DIM))
    y = top + max(0, (body_h - row_h * len(rows)) // 2)
    for label, value, color in rows:
        if y + row_h > sy + sh:
            break
        layout.status_line(s, tx, y, tw, label, value, color=color, label_w=label_w, size=15)
        y += row_h


def _draw_stores_and_systems(game, s, region, helo) -> None:
    """Stores aboard (pips) and the systems lamps: flight weather, deck
    window, dipping weather, dome, ping, water entry and radar."""
    from src.ui import console
    if region.w < 60 or region.h < 40:
        return
    rx, ry, rw, rh = layout.box(s, region, "ui.resources_grid")
    gap = 6
    label_h = layout.font(14).get_linesize()
    cell_h = label_h + layout.font(STORE_VALUE_SIZE).get_linesize() + 10
    cell_w = (rw - gap) // 2
    cells = (
        ("helo.air_torpedoes", str(helo.torps), config.COLOR_WARN, (helo.torps, config.HELO_TORPS)),
        ("helo.sonobuoys_ready", str(helo.buoys_left), config.COLOR_TEXT,
         (helo.buoys_left, config.BUOY_COUNT)),
        ("helo.sonobuoys_active", str(len(game.buoys)), config.COLOR_TEXT, None),
        ("panel.datalink", "ui.active" if helo.airborne else "helo.standby",
         config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM, None),
    )
    for index, (label, value, color, pips) in enumerate(cells):
        cell = pygame.Rect(rx + index % 2 * (cell_w + gap), ry + index // 2 * (cell_h + gap),
                           cell_w, cell_h)
        if cell.bottom > ry + rh:
            break
        pygame.draw.rect(s, config.COLOR_PANEL_BG, cell)
        pygame.draw.rect(s, config.COLOR_GRID, cell, 1)
        layout.corner_brackets(s, cell)
        layout.blit_line(s, label, (cell.x + 8, cell.y + 4, cell.w - 16, label_h),
                         config.COLOR_TEXT_DIM, size=14)
        value_h = layout.font(STORE_VALUE_SIZE).get_linesize()
        value_w = min(cell.w // 2, max(40, layout.font(STORE_VALUE_SIZE).size(localize(value))[0] + 4))
        layout.blit_line(s, value, (cell.x + 8, cell.y + 4 + label_h, value_w, value_h),
                         color, size=STORE_VALUE_SIZE)
        if pips is not None:
            count, capacity = pips
            size, pip_gap = 10, 6
            px = cell.x + 16 + value_w
            py = cell.y + 4 + label_h + (value_h - size) // 2
            for pip in range(max(1, capacity)):
                rect = pygame.Rect(px + pip * (size + pip_gap), py, size, size)
                if rect.right > cell.right - 6:
                    break
                if pip < count:
                    pygame.draw.rect(s, color, rect)
                else:
                    pygame.draw.rect(s, config.COLOR_GRID, rect, 1)
    lamp_h = layout.line_pitch(14, 0) + 8
    top = ry + 2 * (cell_h + gap) + 2
    if top + lamp_h > ry + rh:
        return
    weather = flight_weather(game)
    if weather is None:
        launch = deck = dipping = ("", "off")
    else:
        status = weather["status"]
        launch = (message("weather.flight." + status),
                  "on" if status == "clear" else "caution" if status == "limited" else "alarm")
        deck = (message("helo.console.deck_open" if weather["deck_safe"]
                        else "helo.console.deck_wait"),
                "on" if weather["deck_safe"] else "caution")
        dipping = (message("weather.flight.dip_ok" if weather["dipping_safe"]
                           else "weather.flight.dip_blocked"),
                   "on" if weather["dipping_safe"] else "alarm")
    console.lamp_grid(s, (rx, top, rw, lamp_h), console.with_tips((
        ("helo.console.launch_weather", launch[0], launch[1], "H"),
        ("helo.console.deck_window", deck[0], deck[1]),
        ("helo.console.dip_weather", dipping[0], dipping[1])),
        _tips(game, "launch", "deck", "dip")), 3, size=14)
    if top + 2 * lamp_h + 4 > ry + rh:
        return
    radar = getattr(game, "helo_radar_active", None)
    console.lamp_grid(s, (rx, top + lamp_h + 4, rw, lamp_h), console.with_tips((
        *_dip_lamps(game, helo),
        ("helo.console.radar", "", "on" if callable(radar) and radar() else "off", "Ctrl+R")),
        _tips(game, "dome", "ping", "water", "radar")), 4, size=14)


def _draw_dip_column(s, column, helo, gauge_max, thermocline) -> None:
    """The dipping sonar's side view: the air with the helicopter on top,
    the waterline, then the water column (darker with depth) with the layer
    and the dome on its cable from the helicopter."""
    from src.ui import console
    air_h = max(16, column.h // 5)
    air = pygame.Rect(column.x, column.y, column.w, air_h)
    water = pygame.Rect(column.x, air.bottom, column.w, column.bottom - air.bottom)
    pygame.draw.rect(s, console.AIR, air)
    for band in range(4):
        top = water.y + water.h * band // 4
        pygame.draw.rect(s, console._mix(config.COLOR_PANEL_BG, console.WATER, .45 + band * .14),
                         (water.x, top, water.w, water.h * (band + 1) // 4 - water.h * band // 4))
    pygame.draw.rect(s, layout.BRACKET_COLOR, column, 1)
    # The waterline: a bold line with a wave crest either side of the column.
    pygame.draw.line(s, console.WATER, (column.x - 4, water.y), (column.right + 3, water.y), 3)
    cx = column.centerx
    airborne = helo.airborne
    if airborne:
        # The helicopter in the hover (or passing) at the top of the air.
        hy = air.y + 5
        pygame.draw.polygon(s, config.COLOR_TEXT, [(cx - 7, hy), (cx + 7, hy), (cx, hy + 6)])
        pygame.draw.line(s, config.COLOR_TEXT, (cx - 10, air.y + 2), (cx + 10, air.y + 2), 1)
    if thermocline is not None and thermocline <= gauge_max:
        layer_y = water.y + int(water.h * thermocline / gauge_max)
        pygame.draw.line(s, config.COLOR_WARN, (column.x - 5, layer_y), (column.x + 27, layer_y), 2)
    if airborne and helo.dip_state != "STOWED":
        dome_y = water.y + int(water.h * min(1.0, helo.dip_depth_m / gauge_max))
        # The cable from the helicopter through the air down to the dome.
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (cx, air.y + 11), (cx, dome_y), 1)
        pygame.draw.circle(s, config.COLOR_OK, (cx, dome_y), 5)


# Rescue panel phases and their lamp level (``game.helo_rescue_status``).
RESCUE_LEVELS = {"search": "off", "ready": "caution", "approach": "caution",
                 "lifting": "on", "weather": "alarm", "return": "caution", "deck": "off"}


def rescue_hint(status):
    """The rescue panel's line under the lamps: what to do next."""
    phase = status["phase"]
    params = dict(task=raw_text(status["raft"] or "-"),
                  left=status["left"] if status["left"] is not None else 0,
                  bearing=(f"{status['bearing']:03.0f}" if status["bearing"] is not None
                           else "---"),
                  range=(f"{status['range_nm']:.2f}" if status["range_nm"] is not None
                         else "--"),
                  lift=f"{100 * status['lift']:.0f}")
    return message("helo.rescue.hint." + phase, **params)


def _draw_rescue_panel(game, s, region, status) -> None:
    """The rescue hoist: the winch switch (Z), the cabin and the next step,
    with the current lift as a bar."""
    from src.ui import console
    if region.w < 60 or region.h < 60:
        return
    rx, ry, rw, rh = layout.box(s, region, "helo.rescue.title")
    lamp_h = layout.line_pitch(14, 0) + 8
    level = RESCUE_LEVELS[status["phase"]]
    tips = status_tips.helicopter_rescue(status)
    console.lamp_grid(s, (rx, ry, rw, lamp_h), (
        ("helo.rescue.winch", message("helo.rescue.phase." + status["phase"]), level, "Z",
         status_tips.payload(tips["winch"])),
        ("helo.rescue.cabin", message("helo.rescue.cabin_value", aboard=status["aboard"],
                                      capacity=status["capacity"]),
         "caution" if status["aboard"] >= status["capacity"] else
         "on" if status["aboard"] else "off", None, status_tips.payload(tips["cabin"]))),
        2, size=14)
    top = ry + lamp_h + 6
    row = layout.font(14).get_linesize()
    if top + row > ry + rh:
        return
    if status["phase"] == "lifting":
        bar = pygame.Rect(rx, top + row // 2 - 3, max(1, rw // 4), 6)
        pygame.draw.rect(s, config.COLOR_GRID, bar, 1)
        pygame.draw.rect(s, config.COLOR_OK, (bar.x, bar.y, round(bar.w * status["lift"]), bar.h))
        text_x = bar.right + 8
    else:
        text_x = rx
    layout.blit_line(s, rescue_hint(status), (text_x, top, rx + rw - text_x, row),
                     config.COLOR_WARN if level in ("caution", "alarm") else config.COLOR_TEXT,
                     size=14)


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
    state_label = helo_state_text(helo)
    state_color = (config.COLOR_DANGER if helo.state == "VERLOREN" else
                   config.COLOR_WARN if helo.state == "ZURUECK" or getattr(helo, "preparing", False)
                   or getattr(helo, "refuelling", False) else
                   config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM)
    distance = ((helo.x - game.ship.x) ** 2 +
                (helo.y - game.ship.y) ** 2) ** 0.5 if helo.airborne else 0.0

    if page == 0:
        _draw_status_console(game, s, regions, helo, state_label, state_color, distance)
        rescue = game.helo_rescue_status() if helo.airborne else None
        if rescue is None:
            _draw_deck_gauge(game, s, regions["deck"])
            _draw_stores_and_systems(game, s, regions["resources"], helo)
        elif regions["deck"].h:
            # Airborne on a rescue: the hoist takes the deck gauge's place.
            _draw_rescue_panel(game, s, regions["deck"], rescue)
            _draw_stores_and_systems(game, s, regions["resources"], helo)
        else:
            _draw_rescue_panel(game, s, regions["resources"], rescue)
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
                 localize("helo.radar_on" if game.helo_radar_active()
                          else "helo.radar_off"),
                 localize("view.helo.roe"))
        colors = (config.COLOR_TEXT, margin_color, config.COLOR_TEXT_DIM,
                  config.COLOR_OK, config.COLOR_WARN,
                  config.COLOR_OK if dip_contacts else config.COLOR_TEXT_DIM,
                  config.COLOR_OK if (getattr(helo, "pattern_queue", ())
                                      or getattr(helo, "mad_mode", False))
                  else config.COLOR_TEXT_DIM,
                  config.COLOR_OK if game.helo_radar_active() else config.COLOR_TEXT_DIM,
                  config.COLOR_WARN)
        # The keys named in the rules are switches (full mouse control).
        tokens = ((), (("Q/E", "Q/E"),),
                  (("H:", "H"), ("←/→", "←/→"), ("↑/↓", "↑/↓")),
                  (("Y", "Y"), ("U/V", "U/V"), ("Shift+A", "Shift+A")),
                  (("B:", "B"),),
                  (("Shift+↑/↓", None), ("G", "G")),
                  (("Buoys:", "Shift+B"), ("Bojen:", "Shift+B"), ("MAD", "Shift+M")),
                  (("Radar", "Ctrl+R"),), ())
        line_y = my
        line_h = max(30, layout.font(18).get_linesize() + 4)
        for text, color, keys in zip(rules, colors, tokens):
            remaining = max(0, regions["rules"].bottom - 8 - line_y)
            if remaining <= 0:
                break
            block_h = min(remaining, line_h * (2 if text == rules[-1] else 1))
            layout.blit_block(s, text, mx, line_y, mw, block_h, color,
                              size=18, min_size=16)
            pointer.add_token_keys((mx, line_y, mw, block_h), text, 18, keys, min_size=16,
                                   screen=s)
            line_y += block_h + 4
        if line_y + 28 <= regions["rules"].bottom - 6:
            # The air torpedo fires by this button on a confirming second click.
            fire_button(game, s, (mx, line_y + 2, min(mw, 420), 26),
                        "fire.helo_torpedo", "helo_torpedo")
    elif page == 2:
        plot = layout.box(s, regions["rules"], "helo.dip_sonar")
        px, py, pw, ph = plot
        from src.ui import console
        lamp_h = layout.line_pitch(14, 0) + 8
        lamps = pygame.Rect(int(px + 8), py + 30, max(1, int(pw * .56)), lamp_h)
        console.lamp_grid(s, lamps, console.with_tips(
            _dip_lamps(game, helo), _tips(game, "dome", "ping", "water")), 3, size=14)
        center_x = px + min(pw * .34, ph * .42)
        radius = int(min(pw * .28, ph * .42, (py + ph - 90 - lamps.bottom - 24) / 2))
        center_y = lamps.bottom + 24 + radius
        _dip_scope(s, (center_x, center_y), radius)
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
        _draw_dip_column(s, pygame.Rect(gauge_x, gauge_y, 22, gauge_h), helo,
                         gauge_max, thermocline)
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
        owners = []                     # the contact of each line, for a click
        source_label = localize("helo.source.buoy" if getattr(game, "helo_sensor_source", "DIP") == "BUOY"
                                else "helo.source.dip")
        layout.blit_line(s, source_label, (px + 8, py + 4, int(pw * .55), 22),
                         config.COLOR_OK, size=16)
        pointer.add_token_keys((px + 8, py + 4, int(pw * .55), 22), source_label, 16,
                               (("(T/F/G)", "T/F/G"),), screen=s)
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
                    # The bearing's uncertainty as a dim wedge (at least 1 degree wide).
                    spread = max(1.0, float(contact.dip_bearing_uncertainty_deg))
                    wedge = [(center_x, center_y)] + [
                        (center_x + math.sin(math.radians(contact.dip_bearing + a)) * radius,
                         center_y - math.cos(math.radians(contact.dip_bearing + a)) * radius)
                        for a in np.linspace(-spread, spread, 7)]
                    pygame.draw.polygon(s, console._mix(config.COLOR_PANEL_BG, config.COLOR_OK, .25),
                                        wedge)
                end = (int(center_x + math.sin(theta) * radius),
                       int(center_y - math.cos(theta) * radius))
                pygame.draw.line(s, config.COLOR_OK,
                                 (int(center_x), int(center_y)), end, 2)
                owners.append(contact)
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
                owners.append(contact)
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
                owners.append(contact)
                lines.append(message("helo.buoy_report_line", buoy=f"SB{seq:02d}",
                                     contact=label, bearing=f"{row['bearing']:05.1f}",
                                     range=(f"{row['range_nm']:.1f} {nm_unit()}"
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
        _helicopter_trace(s, graph, spectrum, config.COLOR_OK)
        layout.blit_line(s, "helo.dip_scale", (int(center_x - radius),
                         int(center_y + radius + 4), radius * 2, 20),
                         config.COLOR_TEXT_DIM, size=14, align="center")
        line_h = max(22, layout.font(15).get_linesize() + 2)
        list_y = gauge_y + gauge_h + 18
        for index, line in enumerate(lines[:max(1, int((py + ph - list_y) / line_h))]):
            row = pygame.Rect(int(px + pw * .62), list_y + index * line_h,
                              int(pw * .38), line_h)
            owner = owners[index] if index < len(owners) else None
            if owner is not None:
                # A click selects the line's contact, like Shift+Up/Down.
                if owner is game.selected_contact:
                    pygame.draw.rect(s, config.COLOR_TAB_ACTIVE, row)
                pointer.add_action(row, lambda _pos, c=owner: _select_dip_contact(game, c))
            layout.blit_line(s, line, row, config.COLOR_TEXT, size=15)
    else:
        _draw_helicopter_acoustic_view(game, regions["rules"])
    if page < len(HELICOPTER_FOOTER):
        # The page's keys as chips under the panels (a click presses the key).
        _shortcut_footer(s, (station.x + 14, station.bottom - 26, station.w - 28, 20),
                         HELICOPTER_FOOTER[page])


# Per page; the air torpedo fires by its button on the rules page.
HELICOPTER_FOOTER = (
    (("H", "helo.footer.launch"), ("Z", "helo.footer.hoist"),
     ("Ctrl+R", "helo.footer.radar"), ("Q/E", "footer.zoom"), ("K", "footer.follow")),
    (("W", "helo.footer.wp_contact"), ("M", "helo.footer.target"),
     ("X", "helo.footer.pattern"), ("Shift+B", "helo.footer.buoy_mode"),
     ("Shift+M", "helo.footer.mad"), ("Ctrl+R", "helo.footer.radar")),
    (("Y", "helo.footer.dip"), ("U/V", "helo.footer.dip_depth"),
     ("Shift+A", "helo.footer.ping"), ("Shift+↓", "helo.footer.dip_contact"),
     ("C", "helo.footer.classify"), ("G", "helo.footer.release")),
)
