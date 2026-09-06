"""W0: Stations-Views im rechten Hauptpanel (STATION_RECT: 640x510).

Alle Views rendern ausschließlich innerhalb des Rechtecks
(config.STATION_RECT) – die Seekarte bleibt links sichtbar.
"""

import math
import random

import pygame

from src.core import config
from src.core.i18n import localized, localize
from src.core.station import Station
from src.ui import layout
from src.ui import nato_symbols

STATE_LABEL = {
    "OK": "OK",
    "BESCHAEDIGT": "Beschädigt",
    "FLUTEND": "FLUTEND",
    "ZERSTOERT": "ZERSTÖRT",
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


def _state_color(state: str) -> tuple:
    return {
        "OK": config.COLOR_OK,
        "BESCHAEDIGT": config.COLOR_WARN,
        "FLUTEND": config.COLOR_DANGER,
        "ZERSTOERT": config.COLOR_DANGER,
    }[state]


# --- Brücke / Nautik -------------------------------------------------------

@localized
def draw_bridge_view(game, tr=None) -> None:
    s = game.screen
    r, y = _panel(game, title="Brücke / Nautik")
    x = r[0] + 14
    w = r[2] - 28
    threats = []
    asm_tracks = game.asm_tracks()
    if asm_tracks:
        nearest = min((t for t in asm_tracks if t.range_nm is not None),
                      key=lambda t: t.range_nm, default=None)
        if nearest:
            tti = nearest.range_nm / max(.001, config.kn_to_nm_per_s(
                config.ASM_SPEED_KN))
            threats.append(("ASM", f"{nearest.bearing:03.0f}° / "
                            f"{nearest.range_nm:.1f} NM / TTI {tti:.0f}s"))
    torp_contacts = [c for c in game.sonar.active_contacts()
                     if c.kind == "torpedo"]
    if torp_contacts:
        threats.append(("TORPEDO", f"Peilung {torp_contacts[0].bearing:03.0f}°"))
    if game.damage.avg_flood() >= 25:
        threats.append(("SCHADEN", f"mittlere Flutung {game.damage.avg_flood():.0f}%"))

    alarm = "KEINE AKUTE BEDROHUNG" if not threats else \
        f"{threats[0][0]}: {threats[0][1]}"
    alarm_color = config.COLOR_OK if not threats else config.COLOR_DANGER
    alarm_h = 54 if len(threats) > 1 else 38
    pygame.draw.rect(s, (18, 28, 22), (x, y, w, alarm_h))
    pygame.draw.rect(s, alarm_color, (x, y, w, alarm_h), 2)
    layout.blit_line(s, alarm, (x + 10, y + 5, w - 20, 24), alarm_color,
                     size=17, align="center")
    if len(threats) > 1:
        summary = "WEITERE: " + " | ".join(name for name, _ in threats[1:])
        layout.blit_line(s, summary, (x + 10, y + 29, w - 20, 19),
                         config.COLOR_WARN, size=13, align="center")
    y += alarm_h + 10

    half = (w - 10) // 2
    nav = layout.box(s, (x, y, half, 142), "KURS / RUDER",
                     border=config.COLOR_TEXT)
    nx, ny, nw, _ = nav
    layout.blit_line(s, f"{game.ship.course:05.1f}°",
                     (nx, ny, nw, 34), config.COLOR_TEXT, size=26)
    layout.status_line(s, nx, ny + 36, nw, "Soll",
                       f"{game.ship.target_course:05.1f}°", size=16, label_w=70)
    layout.status_line(s, nx, ny + 62, nw, "Ruder",
                       f"{game.ship.rudder_angle:+4.1f}°", size=16, label_w=70)
    layout.status_line(s, nx, ny + 88, nw, "Wenderadius",
                       f"{game.ship.turn_radius_nm:.2f} NM", size=15, label_w=120)

    drive = layout.box(s, (x + half + 10, y, half, 142), "FAHRT / AKUSTIK",
                       border=config.COLOR_WARN if game.ship.cavitating else config.COLOR_TEXT)
    dx, dy, dw, _ = drive
    layout.blit_line(s, f"{game.ship.speed:04.1f} kn",
                     (dx, dy, dw, 34), config.COLOR_TEXT, size=26)
    layout.status_line(s, dx, dy + 36, dw, "Befehl", game.ship.telegraph,
                       size=16, label_w=82)
    layout.status_line(s, dx, dy + 62, dw, "Soll",
                       f"{game.ship.target_speed:.1f} kn", size=16, label_w=82)
    noise = "KAVITATION" if game.ship.cavitating else \
        f"{game.ship.noise_level() * 100:.0f}% Eigenlärm"
    layout.blit_line(s, noise, (dx, dy + 89, dw, 22),
                     config.COLOR_DANGER if game.ship.cavitating else config.COLOR_OK,
                     size=15)
    y += 154

    mission = layout.box(s, (x, y, w, 100), "AUFTRAG")
    mx, my, mw, _ = mission
    layout.blit_line(s, game.mission.name, (mx, my, mw, 22),
                     config.COLOR_TEXT, size=17)
    layout.blit_line(s, game.mission.objective, (mx, my + 24, mw, 22),
                     config.COLOR_TEXT_DIM, size=14)
    layout.status_line(s, mx, my + 50, mw, "Restzeit",
                       game.mission.format_remaining(game.mission_time),
                       size=15, label_w=100)
    y += 112

    systems = layout.box(s, (x, y, w, 82), "TAKTISCHE LAGE")
    sx, sy, sw, _ = systems
    radar = f"See {'AN' if game.surface_radar_on else 'AUS'} / Luft {'AN' if game.air_radar_on else 'AUS'}"
    layout.status_line(s, sx, sy, sw, "Sensoren",
                       f"Sonar {len(game.sonar.active_contacts())} | {radar}",
                       size=14, label_w=90)
    layout.status_line(s, sx, sy + 25, sw, "Einsatzmittel",
                        f"VLS {game.vls_cells} | Torp {game.torpedo_count} | "
                        f"HSP {localize('enum.helo.' + game.helo.state)}",
                       size=14, label_w=110)


# --- OPZ / CIC (M12) -------------------------------------------------------

OPZ_DOMAIN_CODES = {
    "SURFACE": "SEE",
    "SUBSURFACE": "UBT",
    "AIR": "LFT",
    "MISSILE": "FKR",
    "UNDERWATER_WEAPON": "TOR",
}
OPZ_DOMAIN_COLORS = {
    "SURFACE": config.COLOR_CONTACT_ZIVIL,
    "SUBSURFACE": config.COLOR_CONTACT_UBOOT,
    "AIR": config.COLOR_FLIGHT,
    "MISSILE": config.COLOR_DANGER,
    "UNDERWATER_WEAPON": config.COLOR_DANGER,
}


def _track_tooltip(game, track):
    affiliation = game.opz_affiliation(track.track_id)
    domain = nato_symbols.domain_for_kind(track.kind)
    distance = (f"{track.range_nm:.1f} NM" if track.range_nm is not None
                else "nicht verfuegbar / nur Peilung")
    quality = track.display_quality(game.sim_t, game.air_picture.stale_s)
    return layout.tooltip_payload(
        f"CIC {track.track_id} / {track.label}",
        f"Domaene {domain} | Klassifikation {affiliation}",
        f"Peilung {track.bearing % 360:05.1f} deg | Entfernung {distance}",
        f"Konfidenz {quality:.0%} | Alter {track.age(game.sim_t):.1f}s",
        f"Quelle/Provenienz {track.source} / beobachteter Track",
        target_id=f"opz:track:{track.track_id}")


@localized
def opz_hit_target(game, pos):
    """Hit-test the PPI against the displayed observation picture only."""
    ppi = opz_ppi_rect()
    if pos is None or not pygame.Rect(config.STATION_RECT).collidepoint(pos):
        return None
    tracks = game.opz_tracks()
    if ppi.collidepoint(pos):
        max_nm = _opz_radar_range_nm(game)
        radius = ppi.w // 2
        for track in reversed(tracks):
            if track.range_nm is None:
                radial = radius - 13
            elif track.range_nm <= max_nm:
                radial = track.range_nm / max_nm * radius
            else:
                continue
            angle = math.radians(track.bearing)
            point = (ppi.centerx + radial * math.sin(angle),
                     ppi.centery - radial * math.cos(angle))
            if (pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2 <= 15 ** 2:
                return _track_tooltip(game, track)
        if (pos[0] - ppi.centerx) ** 2 + (pos[1] - ppi.centery) ** 2 <= 14 ** 2:
            return layout.tooltip_payload(
                "EIGENES SCHIFF / PPI-NULLPUNKT",
                f"Kurs {game.ship.course:05.1f} deg | Bereich {max_nm:g} NM",
                "Eigenschiff-Navigationsstatus; keine Sensormessung",
                target_id="opz:ownship")
        return None
    scope_w = int(pygame.Rect(config.STATION_RECT).w * .66)
    if pos[0] >= pygame.Rect(config.STATION_RECT).x + scope_w:
        selected = game.selected_opz_track()
        if selected is not None:
            return _track_tooltip(game, selected)
        return layout.tooltip_payload(
            "OPZ / CIC BEDIENUNG",
            f"{len(tracks)} dargestellte Tracks | Bereich {_opz_radar_range_nm(game):g} NM",
            "Auf/Ab Track; C Zugehoerigkeit; R Radar; PgUp/PgDn Bereich",
            target_id="opz:controls")
    return None


@localized
def station_hit_target(game, pos):
    """Describe meaningful bridge/support-station panels and controls."""
    if game.station is Station.OPZ:
        return opz_hit_target(game, pos)
    rect = pygame.Rect(config.STATION_RECT)
    if pos is None or not rect.collidepoint(pos):
        return None
    x, width = rect.x + 14, rect.w - 28
    top = rect.y + 6 + 8 + layout.font(20).get_linesize() + 8
    if game.station is Station.BRIDGE:
        alarm_h = 54 if len(game.asm_tracks()) + bool(game.damage.avg_flood() >= 25) > 1 else 38
        if pygame.Rect(x, top, width, alarm_h).collidepoint(pos):
            return layout.tooltip_payload(
                "BEDROHUNGSLAGE", f"{len(game.asm_tracks())} beobachtete ASM-Spuren",
                f"Mittlere Flutung {game.damage.avg_flood():.0f}%",
                "Anzeige fasst nur aktuelle Sensor- und Schadensmeldungen zusammen",
                target_id="bridge:alarm")
        y = top + alarm_h + 10
        half = (width - 10) // 2
        if pygame.Rect(x, y, half, 142).collidepoint(pos):
            return layout.tooltip_payload(
                "KURS / RUDER", f"Ist {game.ship.course:05.1f} deg | Soll {game.ship.target_course:05.1f} deg",
                f"Ruder {game.ship.rudder_angle:+.1f} deg | Wenderadius {game.ship.turn_radius_nm:.2f} NM",
                "Links/Rechts aendert Zielkurs; U erlaubt direkte Eingabe",
                target_id="bridge:course")
        if pygame.Rect(x + half + 10, y, half, 142).collidepoint(pos):
            return layout.tooltip_payload(
                "FAHRT / AKUSTIK", f"Ist {game.ship.speed:.1f} kn | Soll {game.ship.target_speed:.1f} kn",
                f"Telegraph {game.ship.telegraph} | Eigenlaerm {game.ship.noise_level():.0%}",
                "Auf/Ab Telegraph; V erlaubt direkte Fahrt-Eingabe",
                target_id="bridge:speed")
        y += 154
        if pygame.Rect(x, y, width, 100).collidepoint(pos):
            return layout.tooltip_payload(
                "AUFTRAG", game.mission.name, game.mission.objective,
                f"Restzeit {game.mission.format_remaining(game.mission_time)}",
                target_id="bridge:mission")
        y += 112
        if pygame.Rect(x, y, width, 82).collidepoint(pos):
            return layout.tooltip_payload(
                "TAKTISCHE LAGE", f"Sonarkontakte {len(game.sonar.active_contacts())}",
                f"Radar See {'AN' if game.surface_radar_on else 'AUS'} / Luft {'AN' if game.air_radar_on else 'AUS'}",
                "Zusammenfassung der dargestellten Bordlage",
                target_id="bridge:tactical")
    elif game.station is Station.ENGINE:
        gap, col_w = 16, (width - 16) // 2
        if pygame.Rect(x, top, col_w, rect.h - 54).collidepoint(pos):
            row = (int(pos[1]) - top - 72) // 27
            action = "Auf/Ab waehlt den Telegraphenbefehl"
            if 0 <= row < len(config.TELEGRAPH_ORDERS):
                name, speed = config.TELEGRAPH_ORDERS[row]
                action = f"{name}: Zielwert {speed:.1f} kn; Auf/Ab waehlt diesen Befehl"
            return layout.tooltip_payload(
                "FAHRTBEFEHL", f"Aktuell {game.ship.telegraph} / Soll {game.ship.target_speed:.1f} kn",
                action, "A schaltet Akustikmodus LEISE/NORMAL",
                target_id="engine:telegraph")
        if pygame.Rect(x + col_w + gap, top, col_w, rect.h - 54).collidepoint(pos):
            return layout.tooltip_payload(
                "ANTRIEB / AKUSTIK", f"Welle {game.ship.rpm():.0f} RPM | Fahrt {game.ship.speed:.1f} kn",
                f"Eigenlaerm {game.ship.noise_level():.0%} | Fahrtgrenze {game.damage.engine_speed_cap():.1f} kn",
                f"Akustikmodus {'LEISE' if game.ship.quiet_mode else 'NORMAL'}; A schaltet um",
                target_id="engine:status")
    elif game.station is Station.RADIO:
        gap, col_w = 18, (width - 18) // 2
        if pygame.Rect(x, top, col_w, rect.h - 52).collidepoint(pos):
            reports = game.hfdf_bearings()
            if reports:
                report = reports[min(game.radio_sel, len(reports) - 1)]
                return layout.tooltip_payload(
                    f"HFDF {report.label}", f"Peilung {report.bearing:05.1f} deg +/-{config.HFDF_BEARING_ERR_DEG:.0f} deg",
                    f"Alter {report.age(game.sim_t):.0f}s | beobachtete Sendung",
                    "Auf/Ab waehlt; Enter protokolliert die Peilung",
                    target_id=f"radio:{report.label}")
            return layout.tooltip_payload("HFDF-PEILUNGEN", "Keine Sendung erfasst",
                                          "Auf/Ab waehlt; Enter protokolliert",
                                          target_id="radio:hfdf")
        if pygame.Rect(x + col_w + gap, top, col_w, rect.h - 52).collidepoint(pos):
            latest = game.messages[-1] if game.messages else ("--:--", "Kein Verkehr")
            return layout.tooltip_payload("HQ / MELDUNGSVERKEHR", f"{latest[0]} {latest[1]}",
                                          "Empfangener Funkverkehr / nur Anzeige",
                                          target_id="radio:messages")
    elif game.station is Station.HELICOPTER:
        helo = game.helo
        distance = math.hypot(helo.x - game.ship.x, helo.y - game.ship.y) if helo.airborne else 0.0
        if pygame.Rect(x, top, width, 104).collidepoint(pos):
            return layout.tooltip_payload(
                "FLUGSTATUS HSP-5",
                f"{localize('enum.helo.' + helo.state)} | Treibstoff {helo.fuel_s / 60:.0f} min",
                f"Abstand {distance:.1f} NM | Kurs {helo.course:05.1f} deg",
                "H startet den HSP oder befiehlt Rueckkehr",
                target_id="helo:status")
        if pygame.Rect(x, top + 116, width, 112).collidepoint(pos):
            return layout.tooltip_payload(
                "HSP-EINSATZMITTEL", f"Lufttorpedos {helo.torps} | Sonarbojen {helo.buoys_left}",
                f"Aktive Bojen {len(game.buoys)} | Datenlink {'AKTIV' if helo.airborne else 'STANDBY'}",
                "B wirft Boje; D startet Lufttorpedo bei gueltiger Loesung",
                target_id="helo:resources")
        if pygame.Rect(x, top + 240, width, 120).collidepoint(pos):
            bearing, distance_nm = game._helo_waypoint_polar()
            return layout.tooltip_payload(
                "HSP-EINSATZREGELN", f"Wegpunkt {bearing:03.0f} deg / {distance_nm:.1f} NM",
                "Pfeile aendern Wegpunkt; H Start/RTB; B Boje; D Torpedo",
                "Waffenabgabe benoetigt beobachtete klassifizierte Loesung",
                target_id="helo:controls")
    elif game.station is Station.DAMAGE:
        margin, gap, detail_w = 16, 14, 356 if rect.w >= 1000 else 250
        grid_w = rect.w - margin * 2 - gap - detail_w
        columns = 3 if grid_w >= 700 else 2
        items = list(game.damage.compartments.items())
        rows = (len(items) + columns - 1) // columns
        grid_h = rect.bottom - (rect.y + 8 + layout.font(20).get_linesize() + 8) - 68
        bw = (grid_w - (columns - 1) * gap) // columns
        bh = (grid_h - (rows - 1) * gap) // rows
        x0 = rect.x + margin
        for index, (key, compartment) in enumerate(items):
            card = pygame.Rect(x0 + index % columns * (bw + gap),
                               top + index // columns * (bh + gap), bw, bh)
            if card.collidepoint(pos):
                teams = game.damage.teams_on(key)
                return layout.tooltip_payload(
                    compartment.name.upper(), f"{STATE_LABEL[compartment.state]} | Flutung {compartment.flood:.0f}% | Feuer {compartment.fire:.0f}%",
                    "Teams " + (", ".join(map(str, teams)) if teams else "keine"),
                    "Links/Rechts waehlt; Enter weist aktuelles Team zu",
                    target_id=f"damage:{key}")
        if pos[0] >= x0 + grid_w + gap:
            selected = items[game.dmg_cursor][1]
            assignment = game.damage.teams[game.dmg_team]
            return layout.tooltip_payload(
                "SCHADENS-MASSNAHMEN", f"Auswahl {selected.name} | Team {game.dmg_team}",
                f"Team-Einsatz {assignment or 'frei'}",
                "Enter zuweisen; Backspace Team zurueckziehen",
                target_id="damage:controls")
    return None


def opz_ppi_rect() -> pygame.Rect:
    """Bounding rectangle of the OPZ PPI in virtual-canvas coordinates."""
    station = pygame.Rect(config.STATION_RECT)
    scope_w = int(station.w * 0.66)
    radius = min(scope_w // 2 - 28, station.h // 2 - 28)
    center = (station.x + scope_w // 2, station.y + station.h // 2)
    return pygame.Rect(center[0] - radius, center[1] - radius,
                       radius * 2, radius * 2)


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


@localized
def draw_opz_view(game, tr=None) -> None:
    s = game.screen
    station = pygame.Rect(config.STATION_RECT)
    scope_w = int(station[2] * 0.66)
    ppi = opz_ppi_rect()
    cx, cy = ppi.center
    r = ppi.w // 2
    max_nm = _opz_radar_range_nm(game)
    scope_bg = config.COLOR_GEO_BG
    pygame.draw.circle(s, scope_bg, (cx, cy), r + 12)
    for ring_index, rr in enumerate((r // 4, r // 2, (3 * r) // 4, r), 1):
        pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), rr, 1)
        ring_nm = max_nm * ring_index / 4.0
        layout.blit_line(s, f"{ring_nm:g}",
                          (cx + 6, cy - rr + 3, 54, 18),
                          config.COLOR_TEXT_DIM, size=13)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx - r, cy), (cx + r, cy), 1)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx, cy - r), (cx, cy + r), 1)
    station_live = not game.damage.station_down("opz")
    radar_live = station_live and (game.surface_radar_on or game.air_radar_on)
    px_per_nm = r / max_nm

    if station_live and game.surface_radar_on:
        coast_range = min(max_nm, game.radar_effective_range("surface"))
        for first, second in _contour_segments_in_circle(
                game.world.coast, game.ship.x, game.ship.y, coast_range):
            mx = (first[0] + second[0]) * .5
            my = (first[1] + second[1]) * .5
            bearing = math.degrees(math.atan2(mx - game.ship.x,
                                              -(my - game.ship.y))) % 360.0
            glow = _radar_glow(game, bearing)
            if glow <= 0.0:
                continue
            p1 = (int(cx + (first[0] - game.ship.x) * px_per_nm),
                  int(cy + (first[1] - game.ship.y) * px_per_nm))
            p2 = (int(cx + (second[0] - game.ship.x) * px_per_nm),
                  int(cy + (second[1] - game.ship.y) * px_per_nm))
            pygame.draw.line(s, _scale_color((75, 180, 105), .25 + .75 * glow),
                             p1, p2, 2)

    if radar_live:
        _draw_radar_clutter(game, s, (cx, cy), r)
        bearing = game.radar_sweep_bearing()
        ang = math.radians(bearing)
        pygame.draw.line(s, (70, 190, 130), (cx, cy),
                         (int(cx + r * math.sin(ang)),
                          int(cy - r * math.cos(ang))), 2)
    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), r, 2)
    # Fregatten-Kurs (nautisch: 0 Grad = Norden/-y).
    hang = math.radians(game.ship.course - 90.0)
    pygame.draw.line(s, config.COLOR_TEXT, (cx, cy),
                     (int(cx + 18 * math.cos(hang)),
                      int(cy + 18 * math.sin(hang))), 3)
    nato_symbols.draw_symbol(s, (cx, cy), "FRIEND", "SURFACE", 18)

    # Own-force aircraft is datalink truth, not a radar/sensor track.
    helo = getattr(game, "helo", None)
    if helo is not None and helo.airborne:
        hdx, hdy = helo.x - game.ship.x, helo.y - game.ship.y
        hdist = math.hypot(hdx, hdy)
        if hdist <= max_nm:
            hx, hy = cx + hdx * px_per_nm, cy + hdy * px_per_nm
            hcol = nato_symbols.draw_symbol(s, (hx, hy), "FRIEND", "AIR", 17)
            layout.blit_line(s, "HSP-5 DL",
                             (int(hx) + 13, int(hy) - 10, 94, 19), hcol, size=12)
    cic_tracks = game.radar_tracks()
    selected_id = game.opz_selected_track_id
    for track in (t for t in cic_tracks if t["dist"] is None):
        rad = math.radians(track["bearing"])
        ex, ey = cx + r * math.sin(rad), cy - r * math.cos(rad)
        affiliation = game.opz_affiliation(track["track_id"])
        domain = nato_symbols.domain_for_kind(track["kind"])
        col = nato_symbols.AFFILIATION_COLORS[affiliation]
        pygame.draw.line(s, col, (cx, cy), (int(ex), int(ey)), 1)
        sx, sy = cx + (r - 13) * math.sin(rad), cy - (r - 13) * math.cos(rad)
        nato_symbols.draw_symbol(s, (sx, sy), affiliation, domain, 14,
                                 track["track_id"] == selected_id)
        layout.blit_line(s, track["source"],
                          (int(ex) - 22, int(ey) - 21, 66, 18), col, size=12)

    # Gemeinsames Lagebild: Oberflaeche, Luft und Flugkoerper im selben Scope.
    for track in (t for t in cic_tracks if t["dist"] is not None):
        if track["dist"] > max_nm:
            continue
        dist = track["dist"]
        rad = math.radians(track["bearing"])
        bx = cx + dist * px_per_nm * math.sin(rad)
        by = cy - dist * px_per_nm * math.cos(rad)
        if track["source"].startswith("RADAR"):
            glow = _radar_glow(game, track["bearing"])
            if glow > 0.0:
                pygame.draw.circle(s, _scale_color((120, 255, 150), glow),
                                   (int(bx), int(by)), 3)
        affiliation = game.opz_affiliation(track["track_id"])
        domain = nato_symbols.domain_for_kind(track["kind"])
        col = nato_symbols.draw_symbol(
            s, (bx, by), affiliation, domain, 16,
            track["track_id"] == selected_id)
        layout.blit_line(s, track["label"],
                          (int(bx) + 12, int(by) - 10, 118, 19), col, size=12)

    # Die ESSM-Auswahl bleibt bewusst von der allgemeinen CIC-Auswahl getrennt.
    asm_tracks = game.asm_tracks()
    for i, track in enumerate(asm_tracks):
        if track.range_nm is None:
            continue
        if track.range_nm > max_nm:
            continue
        dist = track.range_nm
        brg = track.bearing
        rad = math.radians(brg)
        bx, by = (cx + dist * px_per_nm * math.sin(rad),
                  cy - dist * px_per_nm * math.cos(rad))
        if i == min(game.asm_sel, len(asm_tracks) - 1):
            pygame.draw.circle(s, config.COLOR_DANGER, (int(bx), int(by)), 16, 1)

    pr, py = _panel(game, scope_w, None, "OPZ / CIC")
    x = pr[0] + 12
    w = pr[2] - 24
    if game.damage.station_down("opz"):
        radar_state = "AUSFALL"
    else:
        radar_state = (f"SEE {'AN' if game.surface_radar_on else 'AUS'} | "
                       f"LUFT {'AN' if game.air_radar_on else 'AUS'}")
    section_h = 96
    pygame.draw.rect(s, (12, 26, 20), (x - 5, py - 4, w + 10, section_h))
    pygame.draw.rect(s, config.COLOR_GRID, (x - 5, py - 4, w + 10, section_h), 1)
    layout.status_line(s, x, py, w, "RADAR", radar_state,
                       label_w=70, size=14)
    py += 23
    severity = game.radar_weather_severity()
    weather = ("KLAR" if severity <= 0.0 else
               ("CLUTTER" if severity < 1.0 else "STARKE STOERUNG"))
    weather_color = config.COLOR_TEXT_DIM if severity <= 0.0 else config.COLOR_WARN
    layout.status_line(s, x, py, w, "Scope:",
                       f"{max_nm:.0f} NM | See {game.world.sea_state} | {weather}",
                        label_w=70, size=13, color=weather_color)
    py += 23
    ais_count = sum(1 for t in cic_tracks if t["kind"] == "AIS")
    esm_count = sum(1 for t in cic_tracks if t["source"] in ("ESM", "HOJ"))
    layout.status_line(s, x, py, w, "Lagebild:",
                       f"AIS {ais_count} | ESM {esm_count}",
                        label_w=80, size=13)
    py += 23
    layout.status_line(s, x, py, w, "VLS:",
                       f"{game.vls_cells}/{config.VLS_CELLS}  Chaff {game.chaff_cd:.0f}s",
                        label_w=80, size=14)
    py += 28
    selected = game.selected_opz_track()
    if selected is None:
        layout.blit_block(s, "EVIDENZLEDGER: kein Track (Auf/Ab)", x, py, w, 18,
                          color=config.COLOR_TEXT_DIM, size=13)
        py += 22
    else:
        affiliation = game.opz_affiliation(selected.track_id)
        domain = nato_symbols.domain_for_kind(selected.kind)
        color = nato_symbols.AFFILIATION_COLORS[affiliation]
        nato_symbols.draw_symbol(s, (x + 9, py + 9), affiliation, domain, 14)
        label = config.NATO_AFFILIATION_LABELS[affiliation]
        layout.blit_line(s, f"{selected.track_id} {selected.label}",
                         (x + 24, py, w - 24, 18), color, size=13)
        py += 19
        ledger = [
            f"Quelle       {selected.source}",
            f"Peilung      {selected.bearing:05.1f} Grad / vorhanden",
            (f"Entfernung   {selected.range_nm:.1f} NM / vorhanden"
             if selected.range_nm is not None else "Entfernung   nicht verfuegbar"),
            (f"Kurs         {selected.course:03.0f} Grad / vorhanden"
             if selected.course is not None else "Kurs         nicht verfuegbar"),
            f"Alter/Q      {selected.age(game.sim_t):.0f}s / "
            f"{selected.display_quality(game.sim_t, game.air_picture.stale_s):.0%}",
            f"Zuordnung    {label} / Bedienereingabe",
        ]
        for line in ledger:
            layout.blit_line(s, line, (x, py, w, 17), config.COLOR_TEXT_DIM, size=12)
            py += 17

    pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
    py += 7
    layout.blit_block(s, "CIC-TRACKS", x, py, w, 19,
                       color=config.COLOR_TEXT, size=14)
    py += 21
    max_rows = 3
    selected_index = next((i for i, track in enumerate(cic_tracks)
                           if track["track_id"] == selected_id), 0)
    start = max(0, min(selected_index - max_rows // 2,
                       max(0, len(cic_tracks) - max_rows)))
    for track in cic_tracks[start:start + max_rows]:
        affiliation = game.opz_affiliation(track["track_id"])
        domain = nato_symbols.domain_for_kind(track["kind"])
        color = nato_symbols.AFFILIATION_COLORS[affiliation]
        prefix = ">" if track["track_id"] == selected_id else " "
        distance = f"{track['dist']:4.1f}" if track["dist"] is not None else " -- "
        codes = {"UNKNOWN": "UNK", "FRIEND": "FRD",
                 "NEUTRAL": "NEU", "HOSTILE": "FEI"}
        pygame.draw.rect(s, OPZ_DOMAIN_COLORS[domain], (x, py + 4, 3, 11))
        text = (f"{prefix}{track['track_id']:<7} {codes[affiliation]} "
                f"{OPZ_DOMAIN_CODES[domain]} {track['bearing']:03.0f} {distance}NM")
        layout.blit_line(s, text, (x + 6, py, w - 6, 19), color, size=13)
        py += 19

    py += 5
    pygame.draw.line(s, config.COLOR_GRID, (x, py), (x + w, py))
    py += 7
    layout.blit_block(s, f"ASM-ABWEHR | CIWS {game.ciws_ammo}", x, py, w, 19,
                       color=config.COLOR_DANGER if asm_tracks else config.COLOR_TEXT_DIM,
                       size=14)
    py += 21
    if not asm_tracks:
        layout.blit_block(s, "Keine ASM-Tracks.", x, py, w, 18,
                           color=config.COLOR_TEXT_DIM, size=12)
        py += 18
    else:
        n = len(asm_tracks)
        for i, track in enumerate(asm_tracks[:3]):
            sel = i == min(game.asm_sel, n - 1)
            col = config.COLOR_TEXT if sel else config.COLOR_TEXT_DIM
            distance = (f"{track.range_nm:5.1f}NM" if track.range_nm is not None
                        else "  --.-NM")
            jam = "JAMMER" if track.jamming else track.source
            tti = (track.range_nm / max(.001, config.kn_to_nm_per_s(
                config.ASM_SPEED_KN)) if track.range_nm is not None else None)
            tti_text = f" TTI {tti:.0f}s" if tti is not None else ""
            layout.blit_block(
                s, f"{'>' if sel else ' '}{track.label} Rtg "
                   f"{track.bearing:4.0f}° {distance} {jam} "
                   f"Q{track.display_quality(game.sim_t, game.air_picture.stale_s):.0%}{tti_text}",
                 x, py, w, 20, color=col, size=12)
            py += 19
    py += 4
    for hint in ("Auf/Ab: Track | C: Zugehoerigkeit | E: ESSM",
                  "Links/Rechts: ASM | G: Chaff | R/Shift+R: Radar"):
        layout.blit_block(s, hint, x, py, w, 18,
                          color=config.COLOR_TEXT_DIM, size=12)
        py += 18

    scales = " ".join(
        f"[{scale:g}]" if scale == max_nm else f"{scale:g}"
        for scale in config.RADAR_RANGE_SCALES_NM)
    footer = (f"BEREICH {max_nm:g} NM  |  {scales} NM  |  "
              "PgUp/PgDn oder Rad ueber PPI")
    footer_rect = (station.x + 8, station.bottom - 23, scope_w - 16, 19)
    pygame.draw.rect(s, (8, 18, 13), footer_rect)
    layout.blit_line(s, footer, footer_rect, config.COLOR_TEXT, size=12,
                     align="center")


# --- Funkraum (M13) --------------------------------------------------------

@localized
def draw_radio_view(game, tr=None) -> None:
    s = game.screen
    r, y = _panel(game, title="Funkraum / HFDF")
    x = r[0] + 14
    w = r[2] - 28
    gap = 18
    col_w = (w - gap) // 2
    left = layout.box(s, (x, y, col_w, r[3] - 52), "HFDF-PEILUNGEN")
    lx, ly, lw, _ = left
    reports = game.hfdf_bearings()
    if not reports:
        layout.blit_line(s, "Keine Sendung erfasst", (lx, ly, lw, 24),
                         config.COLOR_TEXT_DIM, size=16)
    else:
        selected_idx = min(game.radio_sel, len(reports) - 1)
        start = max(0, min(selected_idx - 3, len(reports) - 7))
        for i, report in enumerate(reports[start:start + 7], start):
            selected = i == selected_idx
            if selected:
                pygame.draw.rect(s, (30, 44, 30), (lx - 5, ly - 2, lw + 10, 26))
                pygame.draw.rect(s, config.COLOR_WARN, (lx - 5, ly - 2, 3, 26))
            age = report.age(game.sim_t)
            layout.blit_line(
                s, f"{'>' if selected else ' '}{report.label}  Rtg "
                   f"{report.bearing:5.1f}°  ±{config.HFDF_BEARING_ERR_DEG:.0f}°  "
                   f"Alter {age:.0f}s",
                (lx, ly, lw, 24),
                config.COLOR_WARN if selected else
                config.COLOR_TEXT if age < 30 else config.COLOR_TEXT_DIM,
                size=15)
            ly += 27
    ly = left[1] + left[3] - 70
    if game.hfdf_log:
        layout.blit_line(s, f"LOG {len(game.hfdf_log)} | FIX {len(game.hfdf_fixes)}",
                         (lx, ly, lw, 22), config.COLOR_OK, size=15)
    layout.blit_line(s, "Auf/Ab: Signal | Enter: protokollieren",
                     (lx, ly + 28, lw, 22), config.COLOR_TEXT_DIM, size=14)

    right = layout.box(s, (x + col_w + gap, y, col_w, r[3] - 52),
                       "HQ / MELDUNGSVERKEHR")
    rx, ry, rw, rh = right
    msgs = game.messages[-8:] if game.messages else [("--:--", "Kein Verkehr")]
    row_h = max(42, rh // max(1, min(8, len(msgs))))
    for row, (stamp, txt) in enumerate(msgs):
        if row == len(msgs) - 1:
            pygame.draw.rect(s, (20, 38, 27), (rx - 4, ry - 2, rw + 8, row_h - 2))
        layout.blit_line(s, stamp, (rx, ry, 72, 22), config.COLOR_OK, size=14)
        pygame.draw.line(s, config.COLOR_GRID, (rx + 76, ry), (rx + 76, ry + row_h - 5))
        layout.blit_block(s, txt, rx + 84, ry, rw - 84, row_h - 3,
                           color=config.COLOR_TEXT, size=14)
        ry += row_h


# --- Maschinenraum (M10) ---------------------------------------------------

@localized
def draw_engine_view(game, tr=None) -> None:
    s = game.screen
    ship = game.ship
    r, y = _panel(game, title="Maschinenraum")
    x, w = r[0] + 14, r[2] - 28
    gap = 16
    col_w = (w - gap) // 2
    cap = game.damage.engine_speed_cap()
    orders = layout.box(s, (x, y, col_w, r[3] - 54), "FAHRTBEFEHL")
    ox, oy, ow, _ = orders
    layout.blit_line(s, ship.telegraph, (ox, oy, ow, 34), config.COLOR_TEXT, size=24)
    oy += 42
    for i, (name, sp) in enumerate(config.TELEGRAPH_ORDERS):
        mark = ">" if i == ship.order_idx else " "
        col = config.COLOR_OK if i == ship.order_idx else config.COLOR_TEXT_DIM
        if i == ship.order_idx:
            pygame.draw.rect(s, (20, 43, 29), (ox - 4, oy - 2, ow + 8, 25))
        layout.status_line(s, ox, oy, ow, f"{mark} {name}", f"{sp:4.1f} kn",
                           color=col, label_w=190, size=15)
        oy += 27
    oy += 14
    layout.blit_line(s, "Auf/Ab oder +/-: Telegraph", (ox, oy, ow, 22),
                     config.COLOR_TEXT_DIM, size=14)
    layout.blit_line(s, "A: Akustikmodus LEISE/NORMAL", (ox, oy + 27, ow, 22),
                     config.COLOR_TEXT_DIM, size=14)

    systems = layout.box(s, (x + col_w + gap, y, col_w, r[3] - 54),
                         "ANTRIEB / AKUSTIK",
                         border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
    px, py, pw, _ = systems
    layout.status_line(s, px, py, pw, "Welle",
                        f"{ship.speed:4.1f} kn (gezielt {ship.target_speed:4.1f})",
                        label_w=125, size=16)
    py += 32
    bar_w = int(pw * 0.72)
    max_rpm = config.SHIP_RPM_MIN + config.SHIP_SPEED_MAX_KN * config.SHIP_RPM_PER_KN
    frac = min(1.0, ship.rpm() / max_rpm)
    pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 14))
    pygame.draw.rect(s, config.COLOR_TEXT, (px, py, int(bar_w * frac), 14))
    layout.blit_line(s, f"{ship.rpm():3.0f} RPM", (px + bar_w + 10, py - 3, pw - bar_w - 10, 22),
                     config.COLOR_TEXT_DIM, size=14)
    py += 34
    nf = ship.noise_level()
    pygame.draw.rect(s, config.COLOR_GRID, (px, py, bar_w, 14))
    pygame.draw.rect(s, config.COLOR_WARN, (px, py, int(bar_w * nf), 14))
    layout.blit_line(s, f"LAERM {nf * 100:3.0f}%", (px + bar_w + 10, py - 3, pw - bar_w - 10, 22),
                     config.COLOR_TEXT_DIM, size=14)
    py += 34
    if ship.cavitating:
        layout.blit_block(s, "KAVITATION / SIGNATUR ERHOEHT", px, py, pw, 24,
                          color=config.COLOR_DANGER, size=16)
        py += 30
    layout.status_line(s, px, py, pw, "Seegang",
                        f"{game.world.sea_state}  |  Roll {ship.roll:4.1f}°  "
                        f"Pitch {ship.pitch:4.1f}°", label_w=125, size=14)
    py += 28
    masch = next((c for c in game.damage.compartments.values()
                  if c.name.startswith("Maschinerie")), None)
    if masch is not None:
        col = config.COLOR_DANGER if masch.state == "ZERSTOERT" else (
            config.COLOR_WARN if masch.flood > 20 or masch.fire > 0 else config.COLOR_OK)
        extra = f"  Brand {masch.fire:3.0f}%" if masch.fire > 0 else ""
        layout.blit_block(s, f"MASCHINERIE  {STATE_LABEL[masch.state]} "
                              f"(Flut {masch.flood:.0f}%){extra}",
                           px, py, pw, 22, color=col, size=14)
        py += 28
    layout.status_line(s, px, py, pw, "Fahrtgrenze", f"{cap:4.1f} kn",
                       label_w=140, size=15)
    py += 28
    layout.status_line(s, px, py, pw, "Akustikmodus",
                        "LEISE (max 12 kn)" if ship.quiet_mode else "NORMAL",
                        color=config.COLOR_OK if ship.quiet_mode else config.COLOR_TEXT,
                        label_w=140, size=15)
    py += 28
    sonar_range = game.ship.passive_sonar_range_nm(0.5, game.world.sea_state)
    if game.sonar_mode == "TOWED":
        sonar_range *= max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                           - config.SONAR_TOWED_SPEED_PENALTY * ship.speed)
    layout.status_line(s, px, py, pw, "Sonarwirkung",
                        f"~{sonar_range:4.1f} NM ({game.sonar_mode})",
                        color=config.COLOR_OK if sonar_range > 10 else config.COLOR_WARN,
                        label_w=140, size=14)
    py += 28
    cap_reason = ("Maschinenausfall" if game.damage.station_down("engine") else
                  "Maschinenschaden" if game.damage.station_degraded("engine") else
                  "keine Begrenzung")
    layout.status_line(s, px, py, pw, "Begrenzung", cap_reason,
                       label_w=140, size=14)


# --- Helikopter-Deck --------------------------------------------------------

@localized
def draw_helicopter_view(game, tr=None) -> None:
    """Eigene Deckansicht fuer Status, Reichweite und Einsatzfreigaben."""
    s = game.screen
    r, y = _panel(game, title="Helikopter-Deck / HSP-5")
    x = r[0] + 14
    w = r[2] - 28
    helo = game.helo
    state_label = {
        "HANGAR": "HANGAR / bereit",
        "AUF": "IN DER LUFT / Einsatz",
        "ZURUECK": "RUECKKEHR ZUM SCHIFF",
        "VERLOREN": "VERLOREN / NOTGEWASSERT",
    }.get(helo.state, helo.state)
    state_color = (config.COLOR_DANGER if helo.state == "VERLOREN" else
                   config.COLOR_WARN if helo.state == "ZURUECK" else
                   config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM)
    status = layout.box(s, (x, y, w, 104), "FLUGSTATUS", border=state_color)
    sx, sy, sw, _ = status
    layout.status_line(s, sx, sy, sw, "Zustand:", state_label,
                        color=state_color, label_w=110, size=15)
    fuel_color = (config.COLOR_DANGER if helo.airborne and helo.fuel_s <= config.HELO_FUEL_RESERVE_S else
                  config.COLOR_WARN if helo.airborne and helo.fuel_s <= config.HELO_FUEL_RESERVE_S * 1.5 else
                  config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM)
    layout.status_line(s, sx, sy + 22, sw, "Treibstoff:",
                       f"{helo.fuel_s / 60:4.0f} min", color=fuel_color,
                       label_w=110, size=15)
    distance = ((helo.x - game.ship.x) ** 2 +
                (helo.y - game.ship.y) ** 2) ** 0.5 if helo.airborne else 0.0
    layout.status_line(s, sx, sy + 44, sw, "Abstand:",
                       f"{distance:4.1f} NM", label_w=110, size=14)
    layout.status_line(s, sx, sy + 66, sw, "Kurs:", f"{helo.course:5.1f}°",
                       label_w=110, size=14)
    y += 116

    resources = layout.box(s, (x, y, w, 112), "Einsatzmittel")
    rx, ry, rw, _ = resources
    layout.status_line(s, rx, ry, rw, "Lufttorpedos:", str(helo.torps),
                       label_w=140, size=15)
    layout.status_line(s, rx, ry + 24, rw, "Sonarbojen:", str(helo.buoys_left),
                       label_w=140, size=15)
    layout.status_line(s, rx, ry + 48, rw, "Aktive Bojen:", str(len(game.buoys)),
                       label_w=140, size=15)
    layout.status_line(s, rx, ry + 72, rw, "Datenlink:",
                       "AKTIV" if helo.airborne else "STANDBY",
                       color=config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM,
                       label_w=140, size=15)
    y += 124

    mission_box = layout.box(s, (x, y, w, 120), "Einsatzregeln")
    mx, my, mw, _ = mission_box
    layout.blit_line(s, "H: Start / Rueckkehr", (mx, my, mw, 18),
                     config.COLOR_TEXT, size=13)
    wp_brg, wp_dist = game._helo_waypoint_polar()
    return_s = distance / max(.001, config.kn_to_nm_per_s(config.HELO_SPEED_KN))
    margin_s = helo.fuel_s - return_s - config.HELO_FUEL_RESERVE_S
    layout.blit_line(s, f"Wegpunkt: {wp_brg:03.0f}° / {wp_dist:.0f} NM",
                     (mx, my + 20, mw, 18), config.COLOR_TEXT_DIM, size=13)
    margin_color = (config.COLOR_DANGER if margin_s < 0 else
                    config.COLOR_WARN if margin_s < 300 else config.COLOR_OK)
    layout.blit_line(s, f"RTB-Marge: {margin_s / 60:+.0f} min | Q/E: Kartenzoom",
                     (mx, my + 40, mw, 18), margin_color, size=14)
    layout.blit_line(s, "Pfeile: Wegpunkt | B: Boje | D: Lufttorpedo",
                     (mx, my + 62, mw, 18), config.COLOR_WARN, size=12)
    layout.blit_line(s, "Ziel muss geortet und als U-Boot klassifiziert sein.",
                     (mx, my + 82, mw, 18), config.COLOR_WARN, size=12)


# --- Schadensbekämpfung (M5, M14) ------------------------------------------

@localized
def draw_damage_view(game, tr=None) -> None:
    s = game.screen
    rect = pygame.Rect(config.STATION_RECT)
    top = layout.panel(s, rect, "Schadensabwehr / Einsatzleitung")
    margin, gap = 16, 14
    detail_w = 356 if rect.w >= 1000 else 250
    grid_w = rect.w - margin * 2 - gap - detail_w
    columns = 3 if grid_w >= 700 else 2
    items = list(game.damage.compartments.items())
    rows = (len(items) + columns - 1) // columns
    grid_h = rect.bottom - top - 68
    bw = (grid_w - (columns - 1) * gap) // columns
    bh = (grid_h - (rows - 1) * gap) // rows
    x0 = rect.x + margin
    for i, (key, c) in enumerate(items):
        bx = x0 + (i % columns) * (bw + gap)
        by = top + (i // columns) * (bh + gap)
        sc = _state_color(c.state)
        pygame.draw.rect(s, (12, 20, 15), (bx, by, bw, bh))
        flood_h = int(bh * min(100.0, c.flood) / 100.0)
        if flood_h > 0:
            pygame.draw.rect(s, (40, 70, 90),
                             (bx + 1, by + bh - flood_h, bw - 2, flood_h - 1))
        selected_card = i == game.dmg_cursor
        pygame.draw.rect(s, config.COLOR_TEXT if selected_card else sc,
                         (bx, by, bw, bh), 3 if selected_card else 1)
        if selected_card:
            pygame.draw.rect(s, sc, (bx + 5, by + 5, 4, bh - 10))
        layout.blit_line(s, c.name, (bx + 14, by + 8, bw - 26, 20),
                         config.COLOR_TEXT, size=15)
        layout.blit_line(s, STATE_LABEL[c.state], (bx + 14, by + 31, bw - 26, 20),
                         sc, size=15)
        if c.fire > 0:
            layout.blit_line(s, f"FEUER {c.fire:3.0f}%",
                              (bx + 14, by + 53, bw - 26, 19),
                              (255, 120, 60), size=14)
        severity = max(c.flood, c.fire)
        teams = game.damage.teams_on(key)
        flood_rate = (config.DMG_FLOOD_RATE if c.state == "FLUTEND" else
                      config.DMG_LEAK_RATE if c.state == "BESCHAEDIGT" else 0.0)
        net_rate = flood_rate - config.DMG_REPAIR_RATE * len(teams)
        trend = "STEIGT" if net_rate > .001 else ("FAELLT" if net_rate < -.001 else "STABIL")
        eta = ((config.DMG_DESTROY_FLOOD - c.flood) / net_rate
               if net_rate > .001 else None)
        eta_text = f" / {eta / 60:.0f}min" if eta is not None else ""
        layout.blit_line(s, f"{trend}{eta_text}  FLUT {c.flood:3.0f}%",
                           (bx + 14, by + bh - 22, bw - 26, 19),
                           config.COLOR_DANGER if severity >= 70 else config.COLOR_TEXT_DIM,
                           size=13)
        if teams:
            layout.blit_line(s, "Team " + ",".join(str(t) for t in teams),
                              (bx + 14, by + bh - 43, bw - 26, 19),
                              config.COLOR_OK, size=13)

    selected_key, selected = items[game.dmg_cursor]
    detail_x = x0 + grid_w + gap
    detail = layout.box(s, (detail_x, top, detail_w, grid_h),
                        "AUSWAHL / MASSNAHMEN", border=_state_color(selected.state))
    dx, dy, dw, _ = detail
    layout.blit_line(s, selected.name, (dx, dy, dw, 28), config.COLOR_TEXT, size=19)
    dy += 34
    layout.status_line(s, dx, dy, dw, "Zustand", STATE_LABEL[selected.state],
                       color=_state_color(selected.state), label_w=118, size=15)
    dy += 28
    layout.status_line(s, dx, dy, dw, "Flutung", f"{selected.flood:.0f}%",
                       color=config.COLOR_DANGER if selected.flood >= 50 else config.COLOR_TEXT,
                       label_w=118, size=15)
    dy += 28
    layout.status_line(s, dx, dy, dw, "Feuer", f"{selected.fire:.0f}%",
                       color=config.COLOR_DANGER if selected.fire else config.COLOR_TEXT_DIM,
                       label_w=118, size=15)
    dy += 38
    pygame.draw.line(s, config.COLOR_GRID, (dx, dy), (dx + dw, dy))
    dy += 12
    assignment = game.damage.teams[game.dmg_team]
    assignment_text = ("Einsatz: " + game.damage.compartments[assignment].name
                        if assignment is not None else "Frei (nicht zugewiesen)")
    layout.status_line(s, dx, dy, dw, f"Team {game.dmg_team}", assignment_text,
                       color=config.COLOR_OK, label_w=96, size=14)
    dy += 34
    assigned = game.damage.teams_on(selected_key)
    layout.status_line(s, dx, dy, dw, "Vor Ort",
                       ", ".join(f"Team {team}" for team in assigned) or "kein Team",
                       color=config.COLOR_OK if assigned else config.COLOR_WARN,
                       label_w=96, size=14)
    dy += 40
    layout.blit_block(s, "Enter: Team zuweisen\nBackspace: Team rueckziehen",
                      dx, dy, dw, 58, config.COLOR_TEXT, size=14)

    footer_y = rect.bottom - 52
    layout.status_line(
        s, x0, footer_y, rect.w - margin * 2, "GESAMTFLUTUNG",
        f"{game.damage.total:3.0f}/{len(game.damage.compartments) * 100} "
        f"({game.damage.avg_flood():.0f} %)",
        color=config.COLOR_DANGER if game.damage.ship_sunk else config.COLOR_TEXT,
        label_w=170, size=15)
    layout.blit_line(s, "Links/Rechts: Kompartiment   Auf/Ab: Team 1-3",
                     (rect.centerx, footer_y, rect.w // 2 - margin, 21),
                     config.COLOR_TEXT_DIM, size=14, align="right")


# --- Radar (M4, M12) -------------------------------------------------------

@localized
def draw_radar_view(game, tr=None) -> None:
    s = game.screen
    cx, cy, r = 840, 300, 200
    pygame.draw.rect(s, (14, 24, 18), (655, 44, 370, 470))
    pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), r, 2)
    for rr in (r // 3, (2 * r) // 3):
        pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), rr, 1)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx - r, cy), (cx + r, cy), 1)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx, cy - r), (cx, cy + r), 1)

    ang = math.radians((game._t * 120.0) % 360.0)
    if game.radar_on:
        pygame.draw.line(s, config.COLOR_TEXT, (cx, cy),
                         (int(cx + r * math.cos(ang)), int(cy - r * math.sin(ang))), 2)

    # Fregatten-Kurs (nautisch: 0°=Norden/-y – wie Karte & Sonar-PPI)
    hang = math.radians(game.ship.course - 90.0)
    pygame.draw.line(s, config.COLOR_TEXT, (cx, cy),
                     (int(cx + 18 * math.cos(hang)),
                      int(cy + 18 * math.sin(hang))), 3)
    pygame.draw.circle(s, config.COLOR_TEXT, (cx, cy), 4)

    px_per_nm = r / config.RADAR_RANGE_NM
    for tr in game.radar_tracks():
        kind, dist, brg = tr["kind"], tr["dist"], tr["bearing"]
        rad = math.radians(brg)
        if kind == "HOJ":
            ex, ey = cx + r * math.sin(rad), cy - r * math.cos(rad)
            pygame.draw.line(s, config.COLOR_DANGER, (cx, cy), (int(ex), int(ey)), 2)
            s.blit(game.font.render("HOJ", True, config.COLOR_DANGER),
                   (int(ex) - 10, int(ey) - 18))
        else:
            d = min(dist, config.RADAR_RANGE_NM)
            bx, by = (cx + d * px_per_nm * math.sin(rad),
                      cy - d * px_per_nm * math.cos(rad))
            if kind == "AIS":
                if tr["hostile"]:
                    col = config.COLOR_CONTACT_WARSHIP
                else:
                    col = config.COLOR_CONTACT_ZIVIL
                pygame.draw.rect(s, col, (int(bx) - 3, int(by) - 3, 6, 6))
                s.blit(game.font.render(tr["label"], True, col),
                       (int(bx) + 6, int(by) - 8))
            else:  # ASM
                pygame.draw.rect(s, config.COLOR_DANGER,
                                 (int(bx) - 4, int(by) - 4, 8, 8), 2)
                s.blit(game.font.render("ASM", True, config.COLOR_DANGER),
                       (int(bx) + 6, int(by) - 8))

    if not game.radar_on:
        txt = game.font_big.render(localize("RADAR AUS – EMCON (R)"),
                                   True, config.COLOR_WARN)
        s.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

    for civ, brg in game.esm_contacts():
        rad = math.radians(brg)
        ex = cx + r * math.sin(rad)
        ey = cy - r * math.cos(rad)
        pygame.draw.line(s, (140, 150, 220), (cx, cy), (int(ex), int(ey)), 1)
        s.blit(game.font.render("ESM", True, (140, 150, 220)),
               (int(ex) + 4, int(ey) - 14))

    pr, py = _panel(game, 385, None, "Radar / Oberfläche")
    x = pr[0] + 12
    w = pr[2] - 24
    tracks = game.radar_tracks()
    n_aism = sum(1 for t in tracks if t["kind"] in ("ASM", "HOJ"))
    n_ais = sum(1 for t in tracks if t["kind"] == "AIS")
    layout.status_line(s, x, py, w, "Radar:",
                       "AN" if game.radar_on else "AUS", label_w=80, size=14)
    py += 21
    layout.status_line(s, x, py, w, "ESM:", str(len(game.esm_contacts())),
                       label_w=80, size=14)
    py += 21
    layout.status_line(s, x, py, w, "Tracks:", f"ASM {n_aism} | AIS {n_ais}",
                       label_w=80, size=14)
    py += 21
    layout.status_line(s, x, py, w, "VLS:",
                       f"{game.vls_cells}/{config.VLS_CELLS}  Chaff {game.chaff_cd:.0f}s",
                       label_w=80, size=14)
    py += 26
    layout.blit_block(s, "E: ESSM   G: Chaff   ←/→: Track", x, py, w, 18,
                      color=config.COLOR_TEXT_DIM, size=13)
    py += 20
    layout.blit_block(s, "CIWS: automatisch < 1.5 NM", x, py, w, 18,
                      color=config.COLOR_OK, size=13)
    py += 20
    if game.incident:
        layout.blit_block(s, "!! POLITISCHER VORFALL !!", x, py, w, 20,
                          color=config.COLOR_DANGER, size=14)
