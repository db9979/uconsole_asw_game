"""W0: Stations-Views im rechten Hauptpanel (STATION_RECT: 640x510).

Alle Views rendern ausschließlich innerhalb des Rechtecks
(config.STATION_RECT) – die Seekarte bleibt links sichtbar.
"""

import math
import random

import pygame

from src.core import config
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

def draw_bridge_view(game) -> None:
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
    pygame.draw.rect(s, (18, 28, 22), (x, y, w, 34))
    pygame.draw.rect(s, alarm_color, (x, y, w, 34), 2)
    layout.blit_line(s, alarm, (x + 10, y + 5, w - 20, 24), alarm_color,
                     size=17, align="center")
    y += 44

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
                       f"VLS {game.vls_cells} | Torp {game.torpedo_count} | HSP {game.helo.state}",
                       size=14, label_w=110)


# --- OPZ / CIC (M12) -------------------------------------------------------

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


def draw_opz_view(game) -> None:
    s = game.screen
    station = config.STATION_RECT
    scope_w = int(station[2] * 0.66)
    cx = station[0] + scope_w // 2
    cy = station[1] + station[3] // 2
    r = min(scope_w // 2 - 28, station[3] // 2 - 28)
    max_nm = game.opz_range_nm
    pygame.draw.circle(s, (10, 16, 12), (cx, cy), r + 12)
    for ring_index, rr in enumerate((r // 4, r // 2, (3 * r) // 4, r), 1):
        pygame.draw.circle(s, config.COLOR_SONAR_RING, (cx, cy), rr, 1)
        ring_nm = max_nm * ring_index / 4.0
        layout.blit_line(s, f"{ring_nm:g}",
                         (cx + 4, cy - rr + 2, 42, 14),
                         config.COLOR_TEXT_DIM, size=9)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx - r, cy), (cx + r, cy), 1)
    pygame.draw.line(s, config.COLOR_SONAR_RING, (cx, cy - r), (cx, cy + r), 1)
    station_live = not game.damage.station_down("opz")
    radar_live = station_live and (game.surface_radar_on or game.air_radar_on)
    px_per_nm = r / max_nm

    if station_live and game.surface_radar_on:
        coast_range = min(max_nm, game.radar_effective_range("surface"))
        for first, second in game.world.coast.contour_segments_in_circle(
                game.ship.x, game.ship.y, coast_range):
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
                         (int(ex) - 18, int(ey) - 18, 50, 15), col, size=10)

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
                         (int(bx) + 12, int(by) - 10, 118, 18), col, size=11)

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
    layout.status_line(s, x, py, w, "Radar:", radar_state,
                       label_w=70, size=13)
    py += 21
    severity = game.radar_weather_severity()
    weather = ("KLAR" if severity <= 0.0 else
               ("CLUTTER" if severity < 1.0 else "STARKE STOERUNG"))
    weather_color = config.COLOR_TEXT_DIM if severity <= 0.0 else config.COLOR_WARN
    layout.status_line(s, x, py, w, "Scope:",
                       f"{max_nm:.0f} NM | See {game.world.sea_state} | {weather}",
                       label_w=70, size=12, color=weather_color)
    py += 21
    ais_count = sum(1 for t in cic_tracks if t["kind"] == "AIS")
    esm_count = sum(1 for t in cic_tracks if t["source"] in ("ESM", "HOJ"))
    layout.status_line(s, x, py, w, "Lagebild:",
                       f"AIS {ais_count} | ESM {esm_count}",
                       label_w=80, size=13)
    py += 21
    layout.status_line(s, x, py, w, "VLS:",
                       f"{game.vls_cells}/{config.VLS_CELLS}  Chaff {game.chaff_cd:.0f}s",
                       label_w=80, size=14)
    py += 21
    selected = game.selected_opz_track()
    if selected is None:
        layout.blit_block(s, "CIC-Fokus: keiner (Auf/Ab)", x, py, w, 18,
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
        py += 18
        distance = (f"{selected.range_nm:.1f} NM" if selected.range_nm is not None
                    else "nur Peilung")
        layout.blit_line(
            s, f"{nato_symbols.DOMAIN_LABELS[domain]} / {label} | "
               f"{selected.source} {selected.bearing:05.1f} Grad | {distance}",
            (x, py, w, 18), config.COLOR_TEXT_DIM, size=13)
        py += 19
        course = f"{selected.course:03.0f}°" if selected.course is not None else "---"
        layout.blit_line(s, f"Kurs {course} | Alter {selected.age(game.sim_t):.0f}s | "
                         f"Qualität {selected.display_quality(game.sim_t, game.air_picture.stale_s):.0%}",
                         (x, py, w, 18), config.COLOR_TEXT_DIM, size=13)
        py += 21

    layout.blit_block(s, "CIC-TRACKS", x, py, w, 17,
                      color=config.COLOR_TEXT_DIM, size=12)
    py += 17
    max_rows = 5
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
        domains = {"SURFACE": "SEE", "AIR": "LFT", "MISSILE": "FKR"}
        text = (f"{prefix}{track['track_id']:<7} {codes[affiliation]} "
                f"{domains[domain]} {track['bearing']:03.0f} {distance}NM")
        layout.blit_line(s, text, (x, py, w, 19), color, size=13)
        py += 19

    py += 3
    layout.blit_block(s, f"ASM-ABWEHR | CIWS {game.ciws_ammo}", x, py, w, 17,
                      color=config.COLOR_DANGER if asm_tracks else config.COLOR_TEXT_DIM,
                      size=12)
    py += 17
    if not asm_tracks:
        layout.blit_block(s, "Keine ASM-Tracks.", x, py, w, 18,
                          color=config.COLOR_TEXT_DIM, size=11)
        py += 16
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


# --- Funkraum (M13) --------------------------------------------------------

def draw_radio_view(game) -> None:
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
            layout.blit_line(
                s, f"{'>' if selected else ' '}{report.label}  Rtg "
                   f"{report.bearing:5.1f}°  ±{config.HFDF_BEARING_ERR_DEG:.0f}°  "
                   f"Alter {report.age(game.sim_t):.0f}s",
                (lx, ly, lw, 24),
                config.COLOR_WARN if selected else config.COLOR_TEXT_DIM,
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
    row_h = max(38, rh // max(1, min(8, len(msgs))))
    for stamp, txt in msgs:
        layout.blit_line(s, stamp, (rx, ry, 62, 22), config.COLOR_OK, size=14)
        layout.blit_block(s, txt, rx + 66, ry, rw - 66, row_h - 3,
                          color=config.COLOR_TEXT, size=14)
        ry += row_h


# --- Maschinenraum (M10) ---------------------------------------------------

def draw_engine_view(game) -> None:
    s = game.screen
    ship = game.ship
    r, y = _panel(game, title="Maschinenraum")
    x = r[0] + 14
    w = r[2] - 28

    cap = game.damage.engine_speed_cap()
    layout.status_line(s, x, y, w, "Motorenbefehl:", ship.telegraph,
                       color=config.COLOR_TEXT, label_w=170, size=17)
    y += 24
    for i, (name, sp) in enumerate(config.TELEGRAPH_ORDERS):
        mark = ">" if i == ship.order_idx else " "
        col = config.COLOR_OK if i == ship.order_idx else config.COLOR_TEXT_DIM
        layout.status_line(s, x, y, w, f"{mark} {name}", f"{sp:4.1f} kn",
                           color=col, label_w=150, size=14)
        y += 20

    y += 8
    layout.status_line(s, x, y, w, "Welle:",
                       f"{ship.speed:4.1f} kn (gezielt {ship.target_speed:4.1f})",
                       label_w=150, size=15)
    y += 24
    bar_w = int(w * 0.65)
    max_rpm = config.SHIP_RPM_MIN + config.SHIP_SPEED_MAX_KN * config.SHIP_RPM_PER_KN
    frac = min(1.0, ship.rpm() / max_rpm)
    pygame.draw.rect(s, config.COLOR_GRID, (x, y, bar_w, 10))
    pygame.draw.rect(s, config.COLOR_TEXT, (x, y, int(bar_w * frac), 10))
    s.blit(game.font.render(f"{ship.rpm():3.0f} RPM", True, config.COLOR_TEXT_DIM),
           (x + bar_w + 8, y - 2))
    y += 26
    nf = ship.noise_level()
    pygame.draw.rect(s, config.COLOR_GRID, (x, y, bar_w, 10))
    pygame.draw.rect(s, config.COLOR_WARN, (x, y, int(bar_w * nf), 10))
    s.blit(game.font.render(f"Lärm {nf * 100:3.0f} %", True, config.COLOR_TEXT_DIM),
           (x + bar_w + 8, y - 2))
    y += 28
    if ship.cavitating:
        layout.blit_block(s, "!! KAVITATION – Lärm stark erhöht !!", x, y, w, 20,
                          color=config.COLOR_DANGER, size=15)
        y += 22
    layout.status_line(s, x, y, w, "Seegang:",
                       f"{game.world.sea_state}  |  Roll {ship.roll:4.1f}°  "
                       f"Pitch {ship.pitch:4.1f}°", label_w=150, size=14)
    y += 26
    masch = next((c for c in game.damage.compartments.values()
                  if c.name.startswith("Maschinerie")), None)
    if masch is not None:
        col = config.COLOR_DANGER if masch.state == "ZERSTOERT" else (
            config.COLOR_WARN if masch.flood > 20 or masch.fire > 0 else config.COLOR_OK)
        extra = f"  Brand {masch.fire:3.0f}%" if masch.fire > 0 else ""
        layout.blit_block(s, f"Maschinerie: {STATE_LABEL[masch.state]} "
                             f"(Flut {masch.flood:.0f}%){extra}",
                          x, y, w, 20, color=col, size=14)
        y += 22
    layout.status_line(s, x, y, w, "Fahrtgrenze:", f"{cap:4.1f} kn",
                           label_w=150, size=14)
    y += 26
    layout.status_line(s, x, y, w, "Akustikmodus:",
                       "LEISE (max 12 kn)" if ship.quiet_mode else "NORMAL",
                       color=config.COLOR_OK if ship.quiet_mode else config.COLOR_TEXT,
                       label_w=150, size=14)
    y += 24
    sonar_range = game.ship.passive_sonar_range_nm(0.5, game.world.sea_state)
    if game.sonar_mode == "TOWED":
        sonar_range *= max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                           - config.SONAR_TOWED_SPEED_PENALTY * ship.speed)
    layout.status_line(s, x, y, w, "Sonarwirkung:",
                       f"~{sonar_range:4.1f} NM ({game.sonar_mode})",
                       color=config.COLOR_OK if sonar_range > 10 else config.COLOR_WARN,
                       label_w=150, size=14)
    y += 26
    cap_reason = ("Maschinenausfall" if game.damage.station_down("engine") else
                  "Maschinenschaden" if game.damage.station_degraded("engine") else
                  "keine Begrenzung")
    layout.status_line(s, x, y, w, "Begrenzungsgrund:", cap_reason,
                       label_w=170, size=14)
    y += 26
    for hint in ("Auf/Ab oder +/-: Telegraph",
                 "A: Akustikmodus LEISE/NORMAL"):
            layout.blit_block(s, hint, x, y, w, 20, color=config.COLOR_TEXT_DIM, size=13)
            y += 19


# --- Helikopter-Deck --------------------------------------------------------

def draw_helicopter_view(game) -> None:
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
    status = layout.box(s, (x, y, w, 104), "Flugstatus", border=config.COLOR_OK)
    sx, sy, sw, _ = status
    layout.status_line(s, sx, sy, sw, "Zustand:", state_label,
                       color=config.COLOR_OK, label_w=110, size=14)
    layout.status_line(s, sx, sy + 22, sw, "Treibstoff:",
                       f"{helo.fuel_s / 60:4.0f} min", label_w=110, size=14)
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
    layout.blit_line(s, f"RTB-Marge: {margin_s / 60:+.0f} min | Q/E: Kartenzoom",
                     (mx, my + 40, mw, 18), config.COLOR_TEXT_DIM, size=13)
    layout.blit_line(s, "Pfeile: Wegpunkt | B: Boje | D: Lufttorpedo",
                     (mx, my + 62, mw, 18), config.COLOR_WARN, size=12)
    layout.blit_line(s, "Ziel muss geortet und als U-Boot klassifiziert sein.",
                     (mx, my + 82, mw, 18), config.COLOR_WARN, size=12)


# --- Schadensbekämpfung (M5, M14) ------------------------------------------

def draw_damage_view(game) -> None:
    s = game.screen
    rect = config.STATION_RECT
    x0, y0 = rect[0] + 20, rect[1] + 44
    columns = 3 if rect[2] >= 1000 else 2
    bw = (rect[2] - 40 - (columns - 1) * 16) // columns
    rows = (len(game.damage.compartments) + columns - 1) // columns
    gap = 16
    # Reserve the footer before sizing cards, including in the split panel.
    footer_y = rect[1] + rect[3] - 112
    bh = min(112, (footer_y - y0 - 12 - (rows - 1) * gap) // rows)
    for i, (key, c) in enumerate(game.damage.compartments.items()):
        bx = x0 + (i % columns) * (bw + gap)
        by = y0 + (i // columns) * (bh + gap)
        sc = _state_color(c.state)
        pygame.draw.rect(s, (12, 20, 15), (bx, by, bw, bh))
        flood_h = int(bh * min(100.0, c.flood) / 100.0)
        if flood_h > 0:
            pygame.draw.rect(s, (40, 70, 90),
                             (bx + 1, by + bh - flood_h, bw - 2, flood_h - 1))
        pygame.draw.rect(s, sc, (bx, by, bw, bh), 2 if i == game.dmg_cursor else 1)
        layout.blit_line(s, c.name, (bx + 10, by + 6, bw - 20, 18),
                         config.COLOR_TEXT, size=14)
        layout.blit_line(s, STATE_LABEL[c.state], (bx + 10, by + 24, bw - 20, 18),
                         sc, size=14)
        if c.fire > 0:
            layout.blit_line(s, f"FEUER {c.fire:3.0f}%",
                             (bx + 10, by + 42, bw - 20, 18),
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
        layout.blit_line(s, f"{trend}{eta_text}  Flut {c.flood:3.0f}%",
                          (bx + 10, by + bh - 19, bw - 20, 17),
                          config.COLOR_DANGER if severity >= 70 else config.COLOR_TEXT_DIM,
                          size=12)
        if teams:
            layout.blit_line(s, "Team " + ",".join(str(t) for t in teams),
                             (bx + 10, by + bh - 36, bw - 20, 17),
                             config.COLOR_OK, size=13)

    # Die Karten enthalten bereits den vollstaendigen Kompartimentstatus.
    # Unten bleibt deshalb nur eine kompakte, nicht ueberlaufende Einsatzinfo.
    y = footer_y
    x = rect[0] + 20
    w = rect[2] - 40
    selected = list(game.damage.compartments.items())[game.dmg_cursor]
    layout.status_line(s, x, y, w, "Auswahl:", selected[1].name,
                       color=config.COLOR_TEXT, label_w=100, size=14)
    y += 20
    assignment = game.damage.teams[game.dmg_team]
    assignment_text = ("Einsatz: " + game.damage.compartments[assignment].name
                       if assignment is not None else "Frei (nicht zugewiesen)")
    layout.status_line(s, x, y, w, f"Teamwahl: {game.dmg_team}", assignment_text,
                       color=config.COLOR_OK, label_w=150, size=14)
    y += 20
    layout.status_line(
        s, x, y, w, "Flutungs-Summe:",
        f"{game.damage.total:3.0f}/{len(game.damage.compartments) * 100} "
        f"({game.damage.avg_flood():.0f} %)",
        color=config.COLOR_DANGER if game.damage.ship_sunk else config.COLOR_TEXT,
        label_w=150, size=14)
    y += 20
    layout.blit_line(s, "Links/Rechts: Kompartiment | Auf/Ab: Team 1-3",
                     (x, y, w, 18), config.COLOR_TEXT_DIM, size=13)
    y += 20
    layout.blit_line(s, "Enter: Zuweisen | Backspace: Rueckzug | 1-8: Station",
                     (x, y, w, 18), config.COLOR_TEXT_DIM, size=13)


# --- Radar (M4, M12) -------------------------------------------------------

def draw_radar_view(game) -> None:
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
        txt = game.font_big.render("RADAR AUS – EMCON (R)", True, config.COLOR_WARN)
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
