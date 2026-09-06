"""W0/W1: Waffenzentrale – Overlay auf der Seekarte + Panel im STATION_RECT."""

import math

import pygame

from src.core import config
from src.ui import layout


def draw_weapons_overlay(game) -> None:
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
                s.blit(game.font.render(f"K{c.id} (nur Peilung – pingen: A)",
                                        True, config.COLOR_DANGER),
                       (int(px) + 12, int(py) - 22))


def draw_weapons_panel(game) -> None:
    s = game.screen
    y = layout.panel(s, config.STATION_RECT, "Waffenzentrale")
    x = config.STATION_RECT[0] + 14
    w = config.STATION_RECT[2] - 28

    layout.status_line(s, x, y, w, "Torpedorohre:",
                       f"{game.torpedo_count}/{game.torpedo_total}",
                       label_w=130, size=15)
    y += 26

    c = game.target
    readiness, readiness_color = game.torpedo_readiness()
    layout.blit_line(s, readiness, (x, y, w, 20), readiness_color, size=14)
    y += 25
    if c is None:
        layout.blit_block(s, "Ziel: -- (M = Ziel setzen)", x, y, w, 20,
                          color=config.COLOR_WARN, size=14)
        y += 26
    else:
        dist = f"{c.range_est:6.1f} NM" if c.range_est is not None else "     --"
        lines = [
            f"Ziel K{c.id}: {c.display_label}  Konf {int(c.confidence * 100)}%",
            f"    Rtg {c.bearing:5.1f}°  Dst {dist}"
            + (" (TMA)" if c.range_source == "tma" else
               (" (Ping)" if c.range_est is not None else "")),
        ]
        age = max(0.0, game.sim_t - c.last_seen)
        sigma = (f"±{c.range_sigma_nm:.2f} NM" if c.range_sigma_nm is not None
                 else "nur Peilung")
        lines.append(f"    Lösung: {sigma} | Alter {age:.0f}s | Quelle {c.range_source or '--'}")
        if c.depth_est is not None:
            lines.append(f"    Zieltiefe ~{c.depth_est:4.0f} m  "
                         f"Empf. {int(round(c.depth_est / 10.0)) * 10:4d} m")
        if c.range_est is None:
            lines.append("    Dst fehlt – erst pingen (A, St.2) oder TMA manövrieren")
        if c.player_class not in ("U_BOOT", "KAMPFSCHIFF"):
            lines.append("    Klassifizieren: C (St.2) -> U-Boot/Kampfschiff")
        for line in lines:
            layout.blit_block(s, line, x, y, w, 20, color=config.COLOR_TEXT, size=14)
            y += 20
        y += 10

    layout.status_line(s, x, y, w, "Torpedotiefe:",
                       f"{game.torpedo_depth:4.0f} m (Auf/Ab einstellen)",
                       label_w=130, size=15)
    y += 26
    layout.blit_block(s, "T = Torpedo abfeuern", x, y, w, 20,
                      color=config.COLOR_OK if game.torpedo_count > 0
                      else config.COLOR_DANGER, size=15)
    y += 26

    helo = game.helo
    hcol = config.COLOR_OK if helo.airborne else config.COLOR_TEXT_DIM
    layout.blit_block(
        s, f"HSP-5: {'AN (' + str(helo.torps) + ' Torp, ' + str(helo.buoys_left)
            + ' Bojen)' if helo.airborne else 'Hangar (H = Start)'}",
        x, y, w, 20, color=hcol, size=14)
    y += 22
    layout.blit_block(s, "B: einzelne Sonarboje   D: Leichttorpedo vom HSP-5",
                      x, y, w, 20, color=config.COLOR_TEXT_DIM, size=13)
    y += 24
    layout.blit_block(s, f"ROE: {game.roe}   Salven: max "
                         f"{config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]} in der Luft",
                      x, y, w, 20, color=config.COLOR_TEXT_DIM, size=13)
    y += 26

    if game.torpedoes:
        layout.blit_block(s, "In der Luft:", x, y, w, 18,
                          color=config.COLOR_TEXT_DIM, size=13)
        y += 20
        for t in game.torpedoes[:4]:
            d = t.guidance_distance_nm()
            d_txt = f"{d:5.1f} NM" if d != float("inf") else "   --"
            mode = "SUCHER" if t.seeker_acquired else "DRAHT"
            remaining = max(0.0, t.RANGE_NM - t.travel)
            run_s = remaining / max(.001, t.speed_nm_per_s)
            layout.blit_line(s, f"  T{t.idx}: {d_txt} {mode} | Lauf {remaining:.1f}NM/{run_s:.0f}s",
                              (x, y, w, 20), config.COLOR_WARN, size=13)
            y += 20
        if len(game.torpedoes) > 4:
            layout.blit_line(s, f"+{len(game.torpedoes) - 4} weitere Torpedos",
                             (x, y, w, 18), config.COLOR_TEXT_DIM, size=12)
            y += 18
    layout.blit_block(s, "Torpedostart erzeugt ein akustisches Transient; "
                         "der Gegner kann ausweichen oder täuschen.",
                       x, y, w, 34, color=config.COLOR_TEXT_DIM, size=13)
