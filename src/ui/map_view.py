"""W0/W3: Taktische Karte im linken Hauptbereich (640x510, Zoom/Pan).

Zeigt: Land/Inseln, Airbases, Fregatte, Zivile (AIS), Flüge, Torpedos,
ASMs, HSP-5, Peilstrich des ausgewählten Kontakts + Ziel-Kreuz (TMA/Ping).
"""

import math

import pygame

from src.core import config
from src.ui import layout
from src.ui import nato_symbols


def _in_rect(px: float, py: float, r: tuple, m: float = 60.0) -> bool:
    return (r[0] - m <= px <= r[0] + r[2] + m and
            r[1] - m <= py <= r[1] + r[3] + m)


def draw_map_view(game) -> None:
    s = game.screen
    r = config.MAP_RECT
    view = game.map_view
    view.set_rect(r)
    # W0: Kamera-Tracking: Fregatte bleibt in der Mitte (K oder Mausrad/
    # Drag schaltet Follow aus, K schaltet wieder ein)
    if getattr(game, "map_follow", True):
        view.cx = game.ship.x
        view.cy = game.ship.y
        view.clamp_center()
    w = game.world
    coast = w.coast

    # See-Hintergrund
    pygame.draw.rect(s, config.COLOR_BG, r)
    with layout.clip_to(s, r):
        # Seedbasierte Bathymetrie: dezente taktische Tiefenfaerbung.
        if coast.has_bathymetry:
            cell_nm = 10.0 if view.scale >= 4.0 else 25.0
            wl, wt = view.screen_to_world(r[0], r[1])
            wr, wb = view.screen_to_world(r[0] + r[2], r[1] + r[3])
            x0 = max(0.0, math.floor(min(wl, wr) / cell_nm) * cell_nm)
            y0 = max(0.0, math.floor(min(wt, wb) / cell_nm) * cell_nm)
            x1 = min(w.size_nm, max(wl, wr) + cell_nm)
            y1 = min(w.size_nm, max(wt, wb) + cell_nm)
            y_nm = y0
            while y_nm < y1:
                x_nm = x0
                while x_nm < x1:
                    depth = w.depth_m(x_nm + cell_nm * .5,
                                      y_nm + cell_nm * .5)
                    if depth > 0.0:
                        deep = max(0.0, min(1.0, depth / 900.0))
                        color = (5, int(24 + 15 * deep), int(34 + 27 * deep))
                        px, py = view.world_to_screen(x_nm, y_nm)
                        px2, py2 = view.world_to_screen(
                            x_nm + cell_nm, y_nm + cell_nm)
                        pygame.draw.rect(s, color,
                                         (int(px), int(py),
                                          max(1, int(px2 - px) + 1),
                                          max(1, int(py2 - py) + 1)))
                    x_nm += cell_nm
                y_nm += cell_nm
        # Gitter (sichtbare 50-NM-Linien)
        step = 10 if view.scale >= 8 else (25 if view.scale >= 3 else 50)
        wl, wt = view.screen_to_world(r[0], r[1])
        wr, wb = view.screen_to_world(r[0] + r[2], r[1] + r[3])
        gx0 = int(max(0.0, min(wl, wr)) // step) * step
        gx1 = int(min(w.size_nm, max(wl, wr)) // step) * step
        gy0 = int(max(0.0, min(wt, wb)) // step) * step
        gy1 = int(min(w.size_nm, max(wt, wb)) // step) * step
        for g in range(gx0, gx1 + 1, step):
            x, _ = view.world_to_screen(g, 0)
            if _in_rect(x, 0, r, 0.0):
                pygame.draw.line(s, config.COLOR_GRID, (int(x), r[1]), (int(x), r[1] + r[3]))
                s.blit(game.font.render(f"{g}", True, config.COLOR_TEXT_DIM),
                       (int(x) + 3, r[1] + r[3] - 18))
        for g in range(gy0, gy1 + 1, step):
            _, y = view.world_to_screen(0, g)
            if _in_rect(0, y, r, 0.0):
                pygame.draw.line(s, config.COLOR_GRID, (r[0], int(y)), (r[0] + r[2], int(y)))
                s.blit(game.font.render(f"{g}", True, config.COLOR_TEXT_DIM),
                       (r[0] + 3, int(y) + 3))

        # Land / Inseln
        for poly in coast.land_points_px(view):
            pygame.draw.polygon(s, config.COLOR_LAND, poly)
            pygame.draw.polygon(s, config.COLOR_LAND_EDGE, poly, 1)
        # Airbases
        for base, px, py in coast.airbase_px(view):
            col = config.COLOR_DANGER if base.get("nation") == "BOREN" \
                else config.COLOR_FLIGHT
            pygame.draw.rect(s, col, (int(px) - 4, int(py) - 4, 8, 8), 2)
            s.blit(game.font.render(base["name"], True, config.COLOR_TEXT_DIM),
                   (int(px) + 7, int(py) - 8))

        tracks = game.radar_tracks()

        # Das Lagebild zeigt nur Sensortracks mit gemessener Position.
        for track in (t for t in tracks if t["kind"] == "AIS"
                      and t["x"] is not None):
            if not _in_rect(*view.world_to_screen(track["x"], track["y"]), r):
                continue
            px, py = view.world_to_screen(track["x"], track["y"])
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(
                s, (px, py), affiliation, "SURFACE", 14)
            s.blit(game.font.render(track["label"], True, col),
                   (int(px) + 7, int(py) - 18))

        for track in (t for t in tracks if t["kind"] == "FLG"
                      and t["x"] is not None):
            px, py = view.world_to_screen(track["x"], track["y"])
            if not _in_rect(px, py, r):
                continue
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(s, (px, py), affiliation, "AIR", 14)
            s.blit(game.font.render(track["label"], True, col),
                   (int(px) + 9, int(py) - 14))

        # Eigene Torpedos
        for t in game.torpedoes:
            px, py = view.world_to_screen(t.x, t.y)
            ang = math.radians(t.course - 90.0)
            pygame.draw.line(s, config.COLOR_WARN, (int(px), int(py)),
                             (int(px + 10 * math.cos(ang)), int(py + 10 * math.sin(ang))), 2)
            pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)
            s.blit(game.font.render(f"T{t.idx}", True, config.COLOR_WARN),
                   (int(px) + 10, int(py) - 24))

        # Sonarbojen
        for b in game.buoys:
            px, py = view.world_to_screen(b.x, b.y)
            pygame.draw.circle(s, config.COLOR_CONTACT_ZIVIL, (int(px), int(py)), 3, 1)

        # ASMs erscheinen nur mit Radarentfernung; HOJ bleibt eine Peilung.
        for track in (t for t in tracks if t["kind"] == "ASM"
                      and t["x"] is not None):
            px, py = view.world_to_screen(track["x"], track["y"])
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(
                s, (px, py), affiliation, "MISSILE", 14)
            s.blit(game.font.render(track["label"], True, col),
                   (int(px) + 10, int(py) - 12))
        fx, fy = view.world_to_screen(game.ship.x, game.ship.y)
        for track in (t for t in tracks if t["kind"] == "ASM"
                      and t["x"] is None):
            rad = math.radians(track["bearing"])
            ex, ey = fx + 300 * math.sin(rad), fy - 300 * math.cos(rad)
            pygame.draw.line(s, config.COLOR_DANGER, (int(fx), int(fy)),
                             (int(ex), int(ey)), 1)
            s.blit(game.font.render(track["source"] + " " + track["label"], True,
                                    config.COLOR_DANGER), (int(fx) + 12, int(fy) + 24))
        for e in game.essms:
            px, py = view.world_to_screen(e.x, e.y)
            pygame.draw.circle(s, (220, 200, 90), (int(px), int(py)), 3)

        # HSP-5
        if game.helo.airborne:
            px, py = view.world_to_screen(game.helo.x, game.helo.y)
            ang = math.radians(game.helo.course - 90.0)
            pygame.draw.line(s, config.COLOR_OK, (int(px), int(py)),
                             (int(px + 9 * math.cos(ang)), int(py + 9 * math.sin(ang))), 2)
            s.blit(game.font.render("HSP-5", True, config.COLOR_OK),
                   (int(px) + 10, int(py) - 12))

        # Peilstrich + Ziel-Kreuz (ausgewählter Kontakt / Ziel)
        contact = game.selected_contact or game.target
        if contact is not None:
            fx, fy = view.world_to_screen(game.ship.x, game.ship.y)
            brg = math.radians(contact.bearing)
            if contact.range_est is not None:
                ex_w = game.ship.x + contact.range_est * math.sin(brg)
                ey_w = game.ship.y - contact.range_est * math.cos(brg)
                tx, ty = view.world_to_screen(ex_w, ey_w)
                line_col = config.COLOR_DANGER if contact is game.target \
                    else config.COLOR_WARN
                pygame.draw.line(s, line_col, (int(fx), int(fy)), (int(tx), int(ty)), 1)
                if contact.range_sigma_nm:
                    sigma_px = max(3, int(contact.range_sigma_nm * view.scale))
                    pygame.draw.circle(s, line_col, (int(tx), int(ty)), sigma_px, 1)
                pygame.draw.line(s, line_col, (int(tx) - 8, int(ty)), (int(tx) + 8, int(ty)), 2)
                pygame.draw.line(s, line_col, (int(tx), int(ty) - 8), (int(tx), int(ty) + 8), 2)
                src = {"tma": "TMA", "ping": "PING",
                       "buoy": "BOJE"}.get(contact.range_source, "FIX")
                s.blit(game.font.render(
                    f"K{contact.id} ~{contact.range_est:4.1f} NM ({src})",
                    True, line_col), (int(tx) + 11, int(ty) - 22))
            else:
                ex = fx + 300 * math.sin(brg)
                ey = fy - 300 * math.cos(brg)
                pygame.draw.line(s, config.COLOR_WARN, (int(fx), int(fy)),
                                 (int(ex), int(ey)), 1)
                s.blit(game.font.render(f"K{contact.id} (nur Peilung)",
                                        True, config.COLOR_WARN),
                       (int(fx) + 14, int(fy) - 20))

        # Manuell protokollierte HFDF-Messungen und daraus berechnete Fixes.
        for report in game.hfdf_log[-6:]:
            ox, oy = view.world_to_screen(report["observer_x"], report["observer_y"])
            brg = math.radians(report["bearing"])
            ex, ey = ox + 260 * math.sin(brg), oy - 260 * math.cos(brg)
            pygame.draw.line(s, (140, 150, 220), (int(ox), int(oy)),
                             (int(ex), int(ey)), 1)
        for fix in game.hfdf_fixes.values():
            px, py = view.world_to_screen(fix["x"], fix["y"])
            radius = max(4, int(fix["sigma_nm"] * view.scale))
            pygame.draw.circle(s, (140, 150, 220), (int(px), int(py)), radius, 1)
            s.blit(game.font.render(fix["label"] + " HFDF", True, (140, 150, 220)),
                   (int(px) + 8, int(py) - 16))

        # Fregatte: Pfeil in Kursrichtung
        px, py = view.world_to_screen(game.ship.x, game.ship.y)
        ang = math.radians(game.ship.course - 90.0)
        target_ang = math.radians(game.ship.target_course - 90.0)
        target_ex = int(px + 42 * math.cos(target_ang))
        target_ey = int(py + 42 * math.sin(target_ang))
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (int(px), int(py)),
                         (target_ex, target_ey), 1)
        layout.blit_line(s, f"Kursziel {game.ship.target_course:03.0f}°",
                         (int(px) + 8, int(py) + 10, 110, 16),
                         config.COLOR_TEXT_DIM, size=10)
        L = 14
        pygame.draw.line(s, config.COLOR_TEXT, (int(px), int(py)),
                         (int(px + L * math.cos(ang)), int(py + L * math.sin(ang))), 3)
        pygame.draw.circle(s, config.COLOR_TEXT, (int(px), int(py)), 4)
        # 30-Minuten-Fahrtvektor macht reale Bewegung auch bei 1x ablesbar.
        vector_nm = game.ship.speed * .5
        vector_px = vector_nm * view.scale
        vx = int(px + vector_px * math.cos(ang))
        vy = int(py + vector_px * math.sin(ang))
        pygame.draw.line(s, config.COLOR_OK, (int(px), int(py)), (vx, vy), 1)
        layout.blit_line(s, "30 min", (vx + 4, vy - 8, 54, 16),
                         config.COLOR_OK, size=11)

    pygame.draw.rect(s, config.COLOR_GRID, r, 1)
    # Zoom-Stufenanzeige
    zoom_nm = r[3] / view.scale
    follow = "K: Follow" if getattr(game, "map_follow", True) else "K: Follow AUS"
    s.blit(game.font.render(
        f"{getattr(game, 'world_mode', 'fixed').upper()} | "
        f"Zoom: {zoom_nm:3.0f} NM | Q/E: Zoom | Drag: Pan | {follow}",
        True, config.COLOR_TEXT_DIM), (r[0] + 4, r[1] + 4))
