"""W0/W3: Taktische Karte im linken Hauptbereich (640x510, Zoom/Pan).

Zeigt: Land/Inseln, Airbases, Fregatte, Zivile (AIS), Flüge, Torpedos,
ASMs, HSP-5, Peilstrich des ausgewählten Kontakts + Ziel-Kreuz (TMA/Ping).
"""

import copy
import math

import pygame

from src.core import config
from src.core.i18n import display_value, localized, localize, message as structured_message
from src.ui import layout
from src.ui import nato_symbols
from src.ui import observations


def message(key, **values):
    return localize(structured_message(key, **values))


def _near(pos, point, radius=12):
    return (pos[0] - point[0]) ** 2 + (pos[1] - point[1]) ** 2 <= radius ** 2


def observed_position(observation):
    """Read the public displayed position, with legacy field compatibility."""
    return observations.position(observation)


def observed_bearing(observation) -> float:
    """Read the public smoothed bearing, with legacy field compatibility."""
    return observations.bearing(observation)


def contact_position(contact, ship):
    """Prefer a fixed observation datum; derive only for legacy contacts."""
    # Sonar contacts must never fall through to similarly named entity truth.
    x, y = observations.position(contact)
    if x is not None and y is not None:
        return x, y
    distance = getattr(contact, "range_est", None)
    if distance is None:
        return None, None
    angle = math.radians(observations.bearing(contact, ship))
    return (ship.x + float(distance) * math.sin(angle),
            ship.y - float(distance) * math.cos(angle))


def active_fix_markers(game, view):
    """Shared draw/hit geometry for every current detached sonar fix."""
    markers = []
    sonar = getattr(game, "sonar", None)
    contacts = sorted(getattr(sonar, "contacts", {}).values(),
                      key=lambda contact: contact.id)
    for contact in contacts:
        active = getattr(contact, "active_fixes", lambda now: ())(game.sim_t)
        for fix in active:
            px, py = view.world_to_screen(fix["x"], fix["y"])
            markers.append((contact, fix, (int(px), int(py))))
    return markers


def _fix_marker_radius(fix, view):
    return max(3, int(fix["uncertainty_nm"] * view.scale))


@localized
def map_hit_target(game, pos):
    """Describe the chart item under *pos* using chart and displayed data only."""
    layout.configure_for(game)
    if pos is None or not pygame.Rect(config.MAP_RECT).collidepoint(pos):
        return None
    view = copy.copy(game.map_view)
    view.set_rect(config.MAP_RECT)
    x_nm, y_nm = view.screen_to_world(*pos)
    if not (0.0 <= x_nm <= game.world.size_nm and
            0.0 <= y_nm <= game.world.size_nm):
        return None
    metadata = getattr(game.world.coast, "metadata", None) or {}
    center = metadata.get("center")
    if isinstance(center, (list, tuple)) and len(center) == 2:
        from src.world.projection import nm_to_lonlat
        lon, lat = nm_to_lonlat(x_nm, y_nm, center[0], center[1],
                                game.world.size_nm)
        coordinate = message("map.tooltip.coordinate_geo", latitude=f"{abs(lat):.4f}",
                             ns="N" if lat >= 0 else "S", longitude=f"{abs(lon):.4f}",
                             ew="E" if lon >= 0 else "W")
    else:
        coordinate = message("map.tooltip.coordinate_local", x=f"{x_nm:.2f}", y=f"{y_nm:.2f}")
    depth = float(game.world.depth_m(x_nm, y_nm))
    terrain = "map.land" if depth <= 0.0 else message(
        "map.tooltip.water_depth", depth=f"{depth:.0f}")
    chart_lines = (coordinate, terrain)
    for contact, fix, point in reversed(active_fix_markers(game, view)):
        if not _near(pos, point, max(15, _fix_marker_radius(fix, view) + 3)):
            continue
        measurement_age = max(0.0, game.sim_t - fix["measured_at"])
        fix_age = max(0.0, game.sim_t - fix["fixed_at"])
        depth = (message("map.tooltip.fix_depth", depth=f"{fix['depth_m']:.0f}",
                         uncertainty=f"{fix['depth_uncertainty_m']:.0f}")
                 if fix["depth_m"] is not None else None)
        return layout.tooltip_payload(
            message("map.tooltip.fix_title", contact=contact.id,
                    source=fix["source"]),
            message("map.tooltip.fix_ages", measurement_age=f"{measurement_age:.0f}",
                    fix_age=f"{fix_age:.0f}"),
            message("map.tooltip.fix_uncertainty",
                    uncertainty=f"{fix['uncertainty_nm']:.2f}"), depth,
            *chart_lines,
            target_id=f"map:sonar:{contact.id}:fix:{fix['source'].lower()}")
    tracks = game.radar_tracks()
    for track in reversed(tracks):
        observed_x, observed_y = observed_position(track)
        if observed_x is None or observed_y is None:
            continue
        if _near(pos, view.world_to_screen(observed_x, observed_y), 14):
            affiliation = game.opz_affiliation(track["track_id"])
            domain = nato_symbols.domain_for_kind(track["kind"])
            distance = observations.range_nm(track, game.ship)
            return layout.tooltip_payload(
                message("map.tooltip.track_title", track=track["track_id"], label=track["label"]),
                message("map.tooltip.observed", domain=display_value('domain', domain),
                        affiliation=display_value('affiliation', affiliation)),
                observations.format_bearing_pair(track, game.ship),
                message("map.tooltip.range", range=f"{distance:.1f}"),
                message("map.tooltip.source_quality_age", source=track["source"],
                        quality=f"{track.get('quality', 0):.0%}", age=f"{track.get('age', 0):.0f}"),
                *chart_lines,
                target_id=f"map-track:{track['track_id']}")
    ship_point = view.world_to_screen(game.ship.x, game.ship.y)
    if _near(pos, ship_point, 14):
        return layout.tooltip_payload(
            "map.own_ship",
            message("map.tooltip.own_course_speed", course=f"{game.ship.course:05.1f}", speed=f"{game.ship.speed:.1f}"),
            message("map.tooltip.own_targets", course=f"{game.ship.target_course:05.1f}", speed=f"{game.ship.target_speed:.1f}"),
            "tooltip.own_position",
            *chart_lines,
            target_id="map:ownship")
    helo = getattr(game, "helo", None)
    if helo is not None and helo.airborne and _near(
            pos, view.world_to_screen(helo.x, helo.y), 15):
        aircraft_bearing = math.degrees(math.atan2(
            helo.x - game.ship.x, -(helo.y - game.ship.y))) % 360.0
        return layout.tooltip_payload(
            "tooltip.own_air",
            message("map.tooltip.helo_state_course", state=localize('enum.helo.' + helo.state), course=f"{helo.course:05.1f}"),
            message("map.tooltip.ship_air_bearing", bearing=layout.format_bearing_pair(
                aircraft_bearing, game.ship.course)),
            message("map.tooltip.helo_fuel", fuel=f"{helo.fuel_s / 60:.0f}"),
            *chart_lines,
            target_id="map:helo")
    contact = getattr(game, "selected_contact", None) or getattr(game, "target", None)
    if contact is not None:
        bearing = observations.bearing(contact, game.ship)
        estimated_range = getattr(contact, "range_est", None)
        observed_x, observed_y = contact_position(contact, game.ship)
        if observed_x is not None and observed_y is not None:
            point = view.world_to_screen(observed_x, observed_y)
            hit = _near(pos, point, 15)
        else:
            start = view.world_to_screen(game.ship.x, game.ship.y)
            angle = math.radians(bearing)
            direction = (math.sin(angle), -math.cos(angle))
            along = ((pos[0] - start[0]) * direction[0]
                     + (pos[1] - start[1]) * direction[1])
            perpendicular = abs((pos[0] - start[0]) * direction[1]
                                - (pos[1] - start[1]) * direction[0])
            hit = 15 <= along <= 300 and perpendicular <= 7
        if hit:
            if observed_x is not None and observed_y is not None:
                bearing = observations.bearing(contact, game.ship)
            displayed_range = observations.range_nm(contact, game.ship)
            distance = (message("map.tooltip.range_value", range=f"{float(displayed_range):.1f}")
                        if displayed_range is not None else "ui.bearing_only")
            sigma = getattr(contact, "range_sigma_nm", None)
            uncertainty = (f"+/-{float(sigma):.2f} NM" if sigma is not None else "--")
            return layout.tooltip_payload(
                message("map.tooltip.sonar_title", contact=contact.id),
                observations.format_bearing_pair(contact, game.ship),
                message("map.tooltip.contact_range", range=localize(distance), uncertainty=uncertainty),
                message("map.tooltip.class_confidence", classification=display_value('classification', getattr(contact, 'player_class', None)), confidence=f"{getattr(contact, 'confidence', 0):.0%}"),
                message("map.tooltip.contact_source", source=getattr(contact, 'range_source', None) or localize("map.tooltip.passive_bearing")),
                message("observation.bearing_uncertainty", uncertainty=f"{observations.bearing_uncertainty(contact):.1f}")
                if observations.bearing_uncertainty(contact) is not None else None,
                message("observation.ages", observation_age=f"{observations.observation_age(contact, game.sim_t):.0f}",
                        fix_age=f"{observations.position_age(contact, game.sim_t):.0f}")
                if observations.position_age(contact, game.sim_t) is not None else None,
                *chart_lines,
                target_id=f"map:sonar:{contact.id}")
    return layout.tooltip_payload("map.position", coordinate, terrain,
                                  "tooltip.chart_empty",
                                  target_id=f"chart:{x_nm:.1f}:{y_nm:.1f}")


def _in_rect(px: float, py: float, r: tuple, m: float = 60.0) -> bool:
    return (r[0] - m <= px <= r[0] + r[2] + m and
            r[1] - m <= py <= r[1] + r[3] + m)


def _visible_landmasses(coast, view, rect):
    """Cull in world space before transforming dense coastline points."""
    left, top = view.screen_to_world(rect[0], rect[1])
    right, bottom = view.screen_to_world(rect[0] + rect[2], rect[1] + rect[3])
    left, right = min(left, right), max(left, right)
    top, bottom = min(top, bottom), max(top, bottom)
    return [land for land in coast.landmasses
            if land.bounds[2] >= left and land.bounds[0] <= right
            and land.bounds[3] >= top and land.bounds[1] <= bottom]


@localized
def draw_map_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    r = config.MAP_RECT
    view = copy.copy(game.map_view)
    view.set_rect(r)
    w = game.world
    coast = w.coast

    # See-Hintergrund; bleibt auch ausserhalb der Weltgrenzen sichtbar.
    pygame.draw.rect(s, config.COLOR_GEO_BG, r)
    with layout.clip_to(s, r):
        # Seedbasierte Bathymetrie: dezente taktische Tiefenfaerbung.
        if coast.has_bathymetry:
            # UI-only, one world/snapshot and at most 4096 chart cells. Compare
            # the small depth grid too, so in-place snapshot edits invalidate.
            bathymetry = getattr(coast, "_bathymetry", None)
            colors = {}
            if bathymetry is not None:
                key = (w.size_nm, coast.world_size_nm,
                       bathymetry["size"],
                       tuple(tuple(row) for row in bathymetry["values"]),
                       tuple(coast.landmasses),
                       config.COLOR_SHALLOW, config.COLOR_DEEP)
                cached = getattr(draw_map_view, "_bathymetry_cache", None)
                if (cached is None or cached[0] is not w
                        or cached[1] is not coast or cached[2] != key):
                    cached = (w, coast, key, colors)
                    draw_map_view._bathymetry_cache = cached
                colors = cached[3]
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
                    cell = (cell_nm, x_nm, y_nm)
                    if cell not in colors:
                        depth = w.depth_m(x_nm + cell_nm * .5,
                                          y_nm + cell_nm * .5)
                        color = None
                        if depth > 0.0:
                            deep = max(0.0, min(1.0, depth / 900.0))
                            color = tuple(
                                int(shallow + (deep_color - shallow) * deep)
                                for shallow, deep_color in zip(
                                    config.COLOR_SHALLOW, config.COLOR_DEEP))
                        if len(colors) >= 4096:
                            colors.clear()
                        colors[cell] = color
                    color = colors[cell]
                    if color is not None:
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
            if r[0] <= x <= r[0] + r[2]:
                pygame.draw.line(s, config.COLOR_GEO_GRID, (int(x), r[1]), (int(x), r[1] + r[3]))
                s.blit(game.font.render(f"{g}", True, config.COLOR_TEXT_DIM),
                       (int(x) + 3, r[1] + r[3] - 18))
        for g in range(gy0, gy1 + 1, step):
            _, y = view.world_to_screen(0, g)
            if r[1] <= y <= r[1] + r[3]:
                pygame.draw.line(s, config.COLOR_GEO_GRID, (r[0], int(y)), (r[0] + r[2], int(y)))
                s.blit(game.font.render(f"{g}", True, config.COLOR_TEXT_DIM),
                       (r[0] + 3, int(y) + 3))

        # Land / Inseln. Legacy/fake coast providers retain their old API.
        landmasses = getattr(coast, "landmasses", None)
        visible_land = (_visible_landmasses(coast, view, r)
                        if landmasses is not None else None)
        polygons = ([[view.world_to_screen(px, py) for px, py in land.points]
                     for land in visible_land]
                    if visible_land is not None else coast.land_points_px(view))
        for poly in polygons:
            pygame.draw.polygon(s, config.COLOR_LAND, poly)
            pygame.draw.polygon(s, config.COLOR_LAND_EDGE, poly, 1)
        shown_countries = set()
        for land in visible_land or ():
            if land.name in shown_countries:
                continue
            px, py = view.world_to_screen(*land.centroid)
            if _in_rect(px, py, r, 18.0):
                shown_countries.add(land.name)
                layout.blit_line(s, land.name.upper(),
                                 (int(px) - 70, int(py) - 9, 140, 18),
                                 config.COLOR_LAND_EDGE, size=12,
                                 align="center")
        # Airbases
        for base, px, py in coast.airbase_px(view):
            col = config.COLOR_DANGER if base.get("gameplay_role") == "hostile" \
                else config.COLOR_FLIGHT
            pygame.draw.rect(s, col, (int(px) - 4, int(py) - 4, 8, 8), 2)
            s.blit(game.font.render(base["name"], True, config.COLOR_TEXT_DIM),
                   (int(px) + 7, int(py) - 8))

        tracks = game.radar_tracks()

        # Das Lagebild zeigt nur Sensortracks mit gemessener Position.
        for track in (t for t in tracks if t["kind"] == "AIS"
                      and observed_position(t)[0] is not None):
            tx, ty = observed_position(track)
            if not _in_rect(*view.world_to_screen(tx, ty), r):
                continue
            px, py = view.world_to_screen(tx, ty)
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(
                s, (px, py), affiliation, "SURFACE", 14)
            s.blit(game.font.render(track["label"], True, col),
                   (int(px) + 7, int(py) - 18))

        for track in (t for t in tracks if t["kind"] == "FLG"
                      and observed_position(t)[0] is not None):
            px, py = view.world_to_screen(*observed_position(track))
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
                      and observed_position(t)[0] is not None):
            px, py = view.world_to_screen(*observed_position(track))
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(
                s, (px, py), affiliation, "MISSILE", 14)
            s.blit(game.font.render(track["label"], True, col),
                   (int(px) + 10, int(py) - 12))
        fx, fy = view.world_to_screen(game.ship.x, game.ship.y)
        for track in (t for t in tracks if t["kind"] == "ASM"
                      and observed_position(t)[0] is None):
            rad = math.radians(observed_bearing(track))
            ex, ey = fx + 300 * math.sin(rad), fy - 300 * math.cos(rad)
            pygame.draw.line(s, config.COLOR_DANGER, (int(fx), int(fy)),
                             (int(ex), int(ey)), 1)
            s.blit(game.font.render(track["source"] + " " + track["label"], True,
                                    config.COLOR_DANGER), (int(fx) + 12, int(fy) + 24))
        for e in game.essms:
            px, py = view.world_to_screen(e.x, e.y)
            pygame.draw.circle(s, (220, 200, 90), (int(px), int(py)), 3)

        # Peilstrich + Ziel-Kreuz (ausgewählter Kontakt / Ziel)
        for contact, fix, (px, py) in active_fix_markers(game, view):
            color = {"PING": (90, 220, 220), "TMA": config.COLOR_WARN,
                     "SONOBUOY": config.COLOR_CONTACT_ZIVIL}[fix["source"]]
            radius = _fix_marker_radius(fix, view)
            pygame.draw.circle(s, color, (px, py), radius, 1)
            pygame.draw.line(s, color, (px - 6, py), (px + 6, py), 1)
            pygame.draw.line(s, color, (px, py - 6), (px, py + 6), 1)
            layout.blit_line(
                s, message("map.line.sonar_fix", contact=contact.id,
                           source=fix["source"]),
                (px + 9, py - 19, 180, 18), color, size=12)

        contact = game.selected_contact or game.target
        if contact is not None:
            fx, fy = view.world_to_screen(game.ship.x, game.ship.y)
            brg = math.radians(observed_bearing(contact))
            ex_w, ey_w = contact_position(contact, game.ship)
            if ex_w is not None and ey_w is not None:
                tx, ty = view.world_to_screen(ex_w, ey_w)
                line_col = config.COLOR_DANGER if contact is game.target \
                    else config.COLOR_WARN
                pygame.draw.line(s, line_col, (int(fx), int(fy)), (int(tx), int(ty)), 1)
                if contact.range_sigma_nm:
                    sigma_px = max(3, int(contact.range_sigma_nm * view.scale))
                    pygame.draw.circle(s, line_col, (int(tx), int(ty)), sigma_px, 1)
                pygame.draw.line(s, line_col, (int(tx) - 8, int(ty)), (int(tx) + 8, int(ty)), 2)
                pygame.draw.line(s, line_col, (int(tx), int(ty) - 8), (int(tx), int(ty) + 8), 2)
                src = ({"tma": "TMA", "ping": "PING",
                        "buoy": localize("map.source.buoy")}
                       .get(contact.range_source, "FIX"))
                s.blit(game.font.render(localize(message(
                    "map.line.contact_fix", contact=contact.id,
                    range=f"{observations.range_nm(contact, game.ship):4.1f}", source=src)),
                    True, line_col), (int(tx) + 11, int(ty) - 22))
            else:
                ex = fx + 300 * math.sin(brg)
                ey = fy - 300 * math.cos(brg)
                pygame.draw.line(s, config.COLOR_WARN, (int(fx), int(fy)),
                                 (int(ex), int(ey)), 1)
                s.blit(game.font.render(message("map.line.bearing_only", contact=contact.id),
                                         True, config.COLOR_WARN),
                       (int(fx) + 14, int(fy) - 20))

        # Manuell protokollierte HFDF-Messungen und daraus berechnete Fixes.
        for report in game.hfdf_log[-6:]:
            if game.sim_t - report["t"] > 300.0:
                continue
            ox, oy = view.world_to_screen(report["observer_x"], report["observer_y"])
            brg = math.radians(report["bearing"])
            ex, ey = ox + 260 * math.sin(brg), oy - 260 * math.cos(brg)
            pygame.draw.line(s, (140, 150, 220), (int(ox), int(oy)),
                             (int(ex), int(ey)), 1)
        for fix in game.hfdf_fixes.values():
            age = max(0.0, game.sim_t - fix["t"])
            if age > 300.0:
                continue
            px, py = view.world_to_screen(fix["x"], fix["y"])
            covariance = fix.get("covariance_nm2")
            if covariance is not None:
                xx, xy, yy = covariance
                spread = math.hypot(xx - yy, 2 * xy)
                major = math.sqrt(max(0.0, (xx + yy + spread) / 2)) * view.scale
                minor = math.sqrt(max(0.0, (xx + yy - spread) / 2)) * view.scale
                angle = .5 * math.atan2(2 * xy, xx - yy)
                ca, sa = math.cos(angle), math.sin(angle)
                points = []
                for index in range(32):
                    phase = index * math.tau / 32
                    a, b = major * math.cos(phase), minor * math.sin(phase)
                    points.append((px + a * ca - b * sa, py + a * sa + b * ca))
                pygame.draw.lines(s, (140, 150, 220), True, points, 1)
            else:
                radius = max(4, int(fix["sigma_nm"] * view.scale))
                pygame.draw.circle(s, (140, 150, 220), (int(px), int(py)), radius, 1)
            layout.blit_line(s, message("map.hfdf_fix", label=fix["label"], age=f"{age:.0f}"),
                             (int(px) + 8, int(py) - 20, 350, 20),
                             (140, 150, 220), size=14)

        # Fregatte: Pfeil in Kursrichtung
        px, py = view.world_to_screen(game.ship.x, game.ship.y)
        ang = math.radians(game.ship.course - 90.0)
        target_ang = math.radians(game.ship.target_course - 90.0)
        target_ex = int(px + 42 * math.cos(target_ang))
        target_ey = int(py + 42 * math.sin(target_ang))
        pygame.draw.line(s, config.COLOR_TEXT_DIM, (int(px), int(py)),
                         (target_ex, target_ey), 1)
        layout.blit_line(s, localize(message("map.target_course",
                                             course=f"{game.ship.target_course:03.0f}")),
                         (int(px) + 8, int(py) + 10, 124, 18),
                         config.COLOR_TEXT_DIM, size=12)
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
        layout.blit_line(s, "30 min", (vx + 4, vy - 8, 60, 18),
                         config.COLOR_OK, size=12)

        # HSP-5 zuletzt: beim Start an gleicher Position bleibt es ueber dem Schiff.
        if game.helo.airborne:
            px, py = view.world_to_screen(game.helo.x, game.helo.y)
            ang = math.radians(game.helo.course - 90.0)
            pygame.draw.line(
                s, nato_symbols.AFFILIATION_COLORS["FRIEND"],
                (int(px), int(py)),
                (int(px + 20 * math.cos(ang)), int(py + 20 * math.sin(ang))), 2)
            col = nato_symbols.draw_symbol(
                s, (px, py), "FRIEND", "AIR", size=22)
            s.blit(game.font.render("HSP-5", True, col),
                   (int(px) + 15, int(py) - 14))

    pygame.draw.rect(s, config.COLOR_GEO_GRID, r, 1)
    # Zoom-Stufenanzeige
    zoom_nm = r[3] / view.scale
    follow = localize("common.on" if getattr(game, "map_follow", True)
                      else "common.off")
    metadata = getattr(coast, "metadata", None) or {}
    region = metadata.get("name")
    prefix = region if region else getattr(game, "world_mode", "fixed").upper()
    layout.blit_line(
        s, message("map.line.footer", region=prefix, zoom=f"{zoom_nm:3.0f}",
                   follow=follow),
        (r[0] + 4, r[1] + 4, r[2] - 8, 20), config.COLOR_TEXT_DIM,
        size=13)
