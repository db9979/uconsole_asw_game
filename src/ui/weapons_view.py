"""W0/W1: Waffenzentrale – Overlay auf der Seekarte + Panel im STATION_RECT."""

import math

import pygame

from src.core import config
from src.core.i18n import localized, localize
from src.ui import layout


@localized
def weapons_hit_target(game, pos):
    """Hit-test the displayed fire-control panels without consulting targets."""
    station = pygame.Rect(config.STATION_RECT)
    if pos is None or not station.collidepoint(pos):
        return None
    top = station.y + 8 + layout.font(20, bold=True).get_linesize() + 8
    x, w, gap = station.x + 14, station.w - 28, 10
    right_w = min(224, max(200, round(w * .37)))
    left_w = w - right_w - gap
    target = game.target
    readiness = game.torpedo_readiness()[0]
    solution = pygame.Rect(x, top, left_w, 238)
    stages = pygame.Rect(x + left_w + gap, top, right_w, 130)
    inventory = pygame.Rect(x + left_w + gap, top + 140, right_w, 98)
    lower = top + 248
    active = pygame.Rect(x, lower, left_w, station.bottom - lower - 12)
    controls = pygame.Rect(x + left_w + gap, lower, right_w,
                           station.bottom - lower - 12)
    if solution.collidepoint(pos):
        if target is None:
            return layout.tooltip_payload("FEUERLEITLOESUNG", "Kein Ziel zugewiesen",
                                          "M: beobachteten Sonarkontakt uebernehmen",
                                          target_id="weapons:solution")
        distance = (f"{target.range_est:.1f} NM" if target.range_est is not None
                    else "keine Entfernung")
        sigma = (f" +/- {target.range_sigma_nm:.2f} NM"
                 if target.range_sigma_nm is not None else "")
        return layout.tooltip_payload(
            f"LOESUNG K{target.id}",
            f"Peilung {target.bearing:05.1f} deg | {distance}{sigma}",
            f"Klasse {target.player_class or 'UNBEKANNT'} | Konfidenz {target.confidence:.0%}",
            f"Quelle {target.range_source or 'passive Peilung'} | Alter {max(0, game.sim_t - target.last_seen):.0f}s",
            target_id=f"weapons:contact:{target.id}")
    if stages.collidepoint(pos):
        return layout.tooltip_payload("EINSATZSTUFEN / INTERLOCK", readiness,
                                      "T startet nur bei gueltiger Loesung, Freigabe und bereiter Waffe",
                                      target_id="weapons:interlock")
    if inventory.collidepoint(pos):
        return layout.tooltip_payload(
            "BESTAND", f"Schiffstorpedos {game.torpedo_count}/{game.torpedo_total}",
            f"HSP-Torpedos {game.helo.torps} | Bojen {game.helo.buoys_left}",
            "Anzeige; Nachladen waehrend des Einsatzes nicht moeglich",
            target_id="weapons:inventory")
    if active.collidepoint(pos):
        row = max(0, (int(pos[1]) - (active.y + 37)) // 23)
        if row < len(game.torpedoes[:5]):
            weapon = game.torpedoes[row]
            remaining = max(0.0, weapon.RANGE_NM - weapon.travel)
            mode = "SUCHER" if weapon.seeker_acquired else "DRAHT"
            return layout.tooltip_payload(
                f"EIGENE WAFFE T{weapon.idx}", f"Modus {mode} | Restlauf {remaining:.1f} NM",
                "Eigene gestartete Waffe / Feuerleitstatus",
                target_id=f"weapons:torpedo:{weapon.idx}")
        if not game.torpedoes:
            return layout.tooltip_payload("AKTIVE WAFFEN", "Keine Waffen im Wasser",
                                          target_id="weapons:active")
    if controls.collidepoint(pos):
        return layout.tooltip_payload(
            "EINSATZBEDIENUNG", f"Setztiefe {game.torpedo_depth:.0f} m | ROE {game.roe}",
            f"HSP-5 {localize('enum.helo.' + game.helo.state)}",
            "Auf/Ab Tiefe; H Start/RTB; B Boje; D Lufttorpedo",
            target_id="weapons:controls")
    return None


@localized
def draw_weapons_overlay(game, tr=None) -> None:
    """Ziel-/Torpedo-Overlay über der Seekarte (Map-Viewport)."""
    s = game.screen
    view = game.map_view
    r = config.MAP_RECT

    with layout.clip_to(s, r):
        for t in game.torpedoes:
            px, py = view.world_to_screen(t.x, t.y)
            ang = math.radians(t.course - 90.0)
            ex, ey = px + 10 * math.cos(ang), py + 10 * math.sin(ang)
            pygame.draw.line(s, config.COLOR_WARN, (int(px), int(py)),
                             (int(ex), int(ey)), 2)
            pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)

        c = game.target
        if c is not None:
            px, py = view.world_to_screen(game.ship.x, game.ship.y)
            brg = math.radians(c.bearing)
            if c.range_est is not None:
                est_x = game.ship.x + c.range_est * math.sin(brg)
                est_y = game.ship.y - c.range_est * math.cos(brg)
                tx, ty = view.world_to_screen(est_x, est_y)
                src = {"tma": "TMA", "ping": "PING",
                       "buoy": "BOJE"}.get(c.range_source, "FIX")
                pygame.draw.line(s, config.COLOR_DANGER, (int(tx) - 10, int(ty)),
                                 (int(tx) + 10, int(ty)), 2)
                pygame.draw.line(s, config.COLOR_DANGER, (int(tx), int(ty) - 10),
                                 (int(tx), int(ty) + 10), 2)
                pygame.draw.circle(s, config.COLOR_DANGER, (int(tx), int(ty)), 8, 1)
                s.blit(game.font.render(f"K{c.id} ({src})", True, config.COLOR_DANGER),
                       (int(tx) + 12, int(ty) - 22))
            else:
                ex = px + 300 * math.sin(brg)
                ey = py - 300 * math.cos(brg)
                pygame.draw.line(s, config.COLOR_DANGER, (int(px), int(py)),
                                 (int(ex), int(ey)), 1)
                s.blit(game.font.render(localize(
                                         f"K{c.id} (nur Peilung – pingen: A)"),
                                         True, config.COLOR_DANGER),
                       (int(px) + 12, int(py) - 22))


@localized
def draw_weapons_panel(game, tr=None) -> None:
    s = game.screen
    station = pygame.Rect(config.STATION_RECT)
    top = layout.panel(s, station, "Waffenzentrale / Feuerleitung", title_size=20)
    x, w = station.x + 14, station.w - 28
    gap = 10
    right_w = min(224, max(200, round(w * .37)))
    left_w = w - right_w - gap
    c = game.target
    readiness, readiness_color = game.torpedo_readiness()

    solution = layout.box(s, (x, top, left_w, 238), "FEUERLEITLOESUNG",
                          border=config.COLOR_DANGER if c else config.COLOR_WARN)
    sx, sy, sw, _ = solution
    if c is None:
        layout.blit_line(s, "KEIN ZIEL ZUGEWIESEN", (sx, sy, sw, 28),
                         config.COLOR_WARN, size=18)
        layout.blit_block(s, "M: beobachteten Sonarkontakt als Ziel uebernehmen",
                          sx, sy + 38, sw, 48, config.COLOR_TEXT_DIM, size=14)
    else:
        dist = f"{c.range_est:6.1f} NM" if c.range_est is not None else "     --"
        lines = [
            (f"K{c.id}  {c.display_label}", config.COLOR_TEXT, 18),
            (f"PEILUNG {c.bearing:05.1f} deg   DISTANZ {dist}", config.COLOR_TEXT, 15),
            (f"KONFIDENZ {int(c.confidence * 100)}%", config.COLOR_TEXT_DIM, 14),
            ("", config.COLOR_TEXT_DIM, 14),
        ]
        source = ("TMA" if c.range_source == "tma" else
                  "PING" if c.range_est is not None else "NUR PEILUNG")
        age = max(0.0, game.sim_t - c.last_seen)
        sigma = (f"+/- {c.range_sigma_nm:.2f} NM" if c.range_sigma_nm is not None
                 else "KEINE DISTANZLOESUNG")
        lines += [
            (f"LOESUNG  {source} / {sigma}", config.COLOR_OK if c.range_est is not None else config.COLOR_WARN, 14),
            (f"ALTER {age:.0f}s", config.COLOR_TEXT_DIM, 14),
        ]
        if c.tma_course is not None or c.tma_speed is not None:
            course = f"{c.tma_course % 360:05.1f} deg" if c.tma_course is not None else "--"
            speed = f"{c.tma_speed:.1f} kn" if c.tma_speed is not None else "--"
            lines.append((f"TMA KURS {course} | FAHRT {speed} | Q {c.tma_quality:.0%}",
                          config.COLOR_TEXT_DIM, 13))
        if c.depth_est is not None:
            lines.append((f"ZIELTIEFE ~{c.depth_est:.0f} m / SETZWERT {round(c.depth_est / 10) * 10:.0f} m",
                          config.COLOR_TEXT, 14))
        for text, color, size in lines:
            if text:
                layout.blit_line(s, text, (sx, sy, sw, 21), color, size=size)
            sy += 25
        if c.range_est is None:
            layout.blit_block(s, "DISTANZ FEHLT: A-Ping auf Sonar oder TMA-Manoever erforderlich",
                              sx, sy, sw, 42, config.COLOR_WARN, size=13)

    ready = layout.box(s, (x + left_w + gap, top, right_w, 130), "EINSATZSTUFEN",
                        border=readiness_color)
    rx, ry, rw, _ = ready
    has_target = c is not None
    has_solution = has_target and (c.range_est is not None or game.roe == "FREE")
    authorized = (has_target and c.player_class in ("U_BOOT", "KAMPFSCHIFF")
                  and "ZUGEHOERIGKEIT" not in readiness)
    stages = (("ZIEL", "ZUGEWIESEN" if has_target else "KEIN ZIEL", has_target),
              ("LOESUNG", "GUELTIG" if has_solution else "AUSSTEHEND", has_solution),
              ("FREIGABE", "AUTORISIERT" if authorized else "GESPERRT", authorized),
              ("WAFFE", "BEREIT" if readiness == "FEUER FREI" else "BLOCKIERT",
               readiness == "FEUER FREI"))
    for index, (name, value, ok) in enumerate(stages):
        layout.status_line(s, rx, ry + index * 20, rw, name, value,
                           color=config.COLOR_OK if ok else config.COLOR_WARN,
                           label_w=76, size=12)
    layout.blit_line(s, "T: START", (rx, ry + 82, rw, 18), readiness_color, size=12)

    inventory = layout.box(s, (x + left_w + gap, top + 140, right_w, 98),
                           "BESTAND")
    ix, iy, iw, _ = inventory
    layout.status_line(s, ix, iy, iw, "Rohre", f"{game.torpedo_count}/{game.torpedo_total}",
                       label_w=78, size=15)
    layout.status_line(s, ix, iy + 24, iw, "HSP Torp", str(game.helo.torps),
                       label_w=78, size=14)
    layout.status_line(s, ix, iy + 48, iw, "Bojen", str(game.helo.buoys_left),
                       label_w=78, size=14)

    lower = top + 248
    active = layout.box(s, (x, lower, left_w, station.bottom - lower - 12),
                        "AKTIVE WAFFEN")
    ax, ay, aw, ah = active
    if not game.torpedoes:
        layout.blit_line(s, "Keine Waffen im Wasser", (ax, ay, aw, 22),
                         config.COLOR_TEXT_DIM, size=14)
    for t in game.torpedoes[:5]:
        d = t.guidance_distance_nm()
        d_txt = f"{d:.1f} NM" if d != float("inf") else "--"
        mode = "SUCHER" if t.seeker_acquired else "DRAHT"
        remaining = max(0.0, t.RANGE_NM - t.travel)
        run_s = remaining / max(.001, t.speed_nm_per_s)
        layout.blit_line(s, f"T{t.idx}  {mode:<6}  LOESUNG {d_txt:<7}  REST {remaining:.1f}NM / {run_s:.0f}s",
                         (ax, ay, aw, 21), config.COLOR_WARN, size=13)
        ay += 23
    if len(game.torpedoes) > 5:
        layout.blit_line(s, f"+ {len(game.torpedoes) - 5} weitere",
                         (ax, ay, aw, 19), config.COLOR_TEXT_DIM, size=12)

    controls = layout.box(s, (x + left_w + gap, lower, right_w,
                              station.bottom - lower - 12), "EINSATZ")
    cx, cy, cw, _ = controls
    layout.status_line(s, cx, cy, cw, "Tiefe", f"{game.torpedo_depth:.0f} m",
                       label_w=66, size=15)
    layout.status_line(s, cx, cy + 24, cw, "ROE", game.roe,
                       label_w=66, size=14)
    helo = game.helo
    hstate = "AIRBORNE" if helo.airborne else "HANGAR"
    layout.status_line(s, cx, cy + 48, cw, "HSP-5", hstate,
                       color=config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM,
                       label_w=66, size=14)
    for offset, text in enumerate(("Auf/Ab: Torpedotiefe", "H: HSP Start/RTB",
                                   "B: Boje  D: Lufttorpedo")):
        layout.blit_line(s, text, (cx, cy + 78 + offset * 22, cw, 20),
                         config.COLOR_TEXT_DIM, size=12)
