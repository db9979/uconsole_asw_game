"""W0/W3: Taktische Karte im linken Hauptbereich (640x510, Zoom/Pan).

Zeigt: Land/Inseln, Airbases, Fregatte, Zivile (AIS), Flüge, Torpedos,
ASMs, HSP-5, Peilstrich des ausgewählten Kontakts + Ziel-Kreuz (TMA/Ping).
"""

import copy
import math

import pygame

from src.core import config
from src.core.station import Station
from src.core.i18n import (display_value, localized, localize, raw_text,
                            message as structured_message)
from src.ui.plot_view import draw_plot
from src.ui import chart_symbols, chart_trails, label_layout, layout, lines, map_fx_view, theme
from src.world import atmosphere
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
            message("map.tooltip.fix_title",
                    contact=observations.contact_display_id(game, contact),
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
                (message("lookout.tooltip", what=game.lookout_visual_what(track["visual"]))
                 if track.get("visual") and game.lookout_visual_what(track["visual"]) is not None
                 else None),
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
                message("map.tooltip.sonar_title",
                        contact=observations.contact_display_id(game, contact)),
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
    hazards = getattr(game.world, "charted_hazards", None)
    hazard = (chart_symbols.hazard_at(hazards(), view.world_to_screen, pos)
              if hazards is not None else None)
    if hazard is not None:
        return chart_symbols.hazard_tooltip(hazard)
    return layout.tooltip_payload("map.position", coordinate, terrain,
                                  "tooltip.chart_empty",
                                  target_id=f"chart:{x_nm:.1f}:{y_nm:.1f}")


def _in_rect(px: float, py: float, r: tuple, m: float = 60.0) -> bool:
    return (r[0] - m <= px <= r[0] + r[2] + m and
            r[1] - m <= py <= r[1] + r[3] + m)


GRID_STEPS_NM = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0)
# Clip margin around the chart: far outside lines never reach gfxdraw's
# 16-bit coordinates, and polygon edges stay outside the visible chart.
_CLIP_MARGIN_PX = 64.0


def grid_step_nm(scale_px_per_nm: float) -> float:
    """Grid spacing for a chart scale: the legacy 50/25/10 NM steps up to
    8 px/NM, then the smallest step at least 80 px apart."""
    if scale_px_per_nm < 3.0:
        return 50.0
    if scale_px_per_nm < 8.0:
        return 25.0
    for step in GRID_STEPS_NM:
        if step <= 10.0 and step * scale_px_per_nm >= 80.0:
            return step
    return 10.0


def grid_label(value_nm: float) -> str:
    """Grid coordinate label: whole NM without decimals, else one decimal."""
    rounded = round(value_nm, 1)
    return f"{rounded:.0f}" if abs(rounded - round(rounded)) < 1e-6 else f"{rounded:.1f}"


def scale_label(height_nm: float) -> str:
    """Chart height for the scale line (``0.5``, ``2``, ``51``)."""
    if height_nm < 9.95:
        text = f"{height_nm:.1f}"
        return text[:-2] if text.endswith(".0") else text
    return f"{height_nm:.0f}"


def clip_polygon_to_rect(points, rect, margin: float = _CLIP_MARGIN_PX) -> list:
    """Clip a screen polygon to ``rect`` grown by ``margin`` (Sutherland-Hodgman).

    Polygons already inside the grown rect are returned unchanged, so the
    normal zoom levels keep their exact outline; at strong zoom the huge
    off-screen coordinates are cut away before drawing."""
    left = rect[0] - margin
    top = rect[1] - margin
    right = rect[0] + rect[2] + margin
    bottom = rect[1] + rect[3] + margin
    pts = list(points)
    if all(left <= x <= right and top <= y <= bottom for x, y in pts):
        return pts
    for edge in range(4):
        if not pts:
            break
        out = []
        prev = pts[-1]
        for cur in pts:
            inside_cur = _clip_inside(cur, edge, left, top, right, bottom)
            inside_prev = _clip_inside(prev, edge, left, top, right, bottom)
            if inside_cur:
                if not inside_prev:
                    out.append(_clip_cross(prev, cur, edge, left, top, right, bottom))
                out.append(cur)
            elif inside_prev:
                out.append(_clip_cross(prev, cur, edge, left, top, right, bottom))
            prev = cur
        pts = out
    return pts


def _clip_inside(point, edge, left, top, right, bottom) -> bool:
    x, y = point
    return (x >= left, y >= top, x <= right, y <= bottom)[edge]


def _clip_cross(a, b, edge, left, top, right, bottom):
    (x0, y0), (x1, y1) = a, b
    if edge in (0, 2):
        bound = left if edge == 0 else right
        t = (bound - x0) / (x1 - x0)
        return bound, y0 + (y1 - y0) * t
    bound = top if edge == 1 else bottom
    t = (bound - y0) / (y1 - y0)
    return x0 + (x1 - x0) * t, bound


def _visible_landmasses(coast, view, rect):
    """Cull in world space before transforming dense coastline points."""
    left, top = view.screen_to_world(rect[0], rect[1])
    right, bottom = view.screen_to_world(rect[0] + rect[2], rect[1] + rect[3])
    left, right = min(left, right), max(left, right)
    top, bottom = min(top, bottom), max(top, bottom)
    return [land for land in coast.landmasses
            if land.bounds[2] >= left and land.bounds[0] <= right
            and land.bounds[3] >= top and land.bounds[1] <= bottom]


def _map_label(surface, game, text, pos, color, chart, candidates=None,
               size=None) -> None:
    """Label beside a chart symbol, flipped left/down so it is never cut off.

    Inside a :func:`label_layout.label_scope` the label also steps aside
    from labels placed before it (``candidates`` overrides the default
    positions around ``pos``)."""
    shown = localize(text)
    face = layout.font(size) if size else game.font
    width, height = layout.text_size(face, shown)
    chart = pygame.Rect(chart)
    field = label_layout.active()
    if field is not None:
        if callable(candidates):
            candidates = candidates((width, height))
        x, y = field.place((width, height), candidates
                           or label_layout.around(pos, (width, height))).topleft
    else:
        x, y = pos
        if x + width > chart.right - 2:
            x = max(chart.x + 2, pos[0] - width - 24)
        y = min(max(y, chart.y + 2), chart.bottom - height - 2)
    with layout.clip_to(surface, chart):
        image = layout.render_line(face, shown, color)
        rendered = image.get_rect(topleft=(int(x), int(y)))
        layout.record_text(shown, rendered, chart, image)
        surface.blit(image, rendered)


def draw_chart_geography(game, view, r, top_band=None) -> None:
    """Known geography of a chart: bathymetry, grid, land, airbases, hazards.

    Shared by the frigate map and the crewed submarine's chart; it reads only
    the world's public chart data.  The caller clips to ``r``; ``top_band``
    is an extra box along the top edge (a mission line) that the axis
    numbers and labels keep clear of, like the scale line.
    """
    s = game.screen
    w = game.world
    coast = w.coast
    stage = daylight_stage(w)
    shallow_color = theme.water_color(config.COLOR_SHALLOW, stage)
    deep_color = theme.water_color(config.COLOR_DEEP, stage)
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
                   shallow_color, deep_color)
            cached = getattr(draw_map_view, "_bathymetry_cache", None)
            if (cached is None or cached[0] is not w
                    or cached[1] is not coast or cached[2] != key):
                cached = (w, coast, key, colors)
                draw_map_view._bathymetry_cache = cached
            colors = cached[3]
        cell_nm = (2.0 if view.scale >= 40.0 else
                   10.0 if view.scale >= 4.0 else 25.0)
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
                            int(near + (far - near) * deep)
                            for near, far in zip(shallow_color, deep_color))
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
    # Gitter: Linienabstand waechst mit dem Zoom (50 NM bis 0.1 NM).
    step = grid_step_nm(view.scale)
    wl, wt = view.screen_to_world(r[0], r[1])
    wr, wb = view.screen_to_world(r[0] + r[2], r[1] + r[3])
    gx0 = math.ceil(max(0.0, min(wl, wr)) / step - 1e-9)
    gx1 = math.floor(min(w.size_nm, max(wl, wr)) / step + 1e-9)
    gy0 = math.ceil(max(0.0, min(wt, wb)) / step - 1e-9)
    gy1 = math.floor(min(w.size_nm, max(wt, wb)) / step + 1e-9)
    # Axis numbers: x along the bottom edge, y along the left edge. A number
    # that would run off the chart or into the other axis' corner is left out.
    # The top band belongs to the scale line (:func:`draw_chart_frame`).
    face = game.font
    label_h = face.get_linesize()
    left_w = layout.text_width(face, "0000") + 6
    bottom_band = r[1] + r[3] - label_h - 2
    reserved = [scale_rect(r)] + ([pygame.Rect(top_band)] if top_band is not None else [])
    top_band = max(rect.bottom for rect in reserved) + 1
    field = label_layout.active()
    for rect in reserved if field is not None else ():
        field.reserve(rect)
    axis_labels = []
    with layout.clip_to(s, r):
        for k in range(gx0, gx1 + 1):
            g = k * step
            x, _ = view.world_to_screen(g, 0)
            if r[0] <= x <= r[0] + r[2]:
                lines.line(s, config.COLOR_GEO_GRID, (int(x), r[1]), (int(x), r[1] + r[3]))
                image = layout.render_line(face, grid_label(g), config.COLOR_TEXT_DIM)
                if int(x) + 3 >= r[0] + left_w and int(x) + 3 + image.get_width() <= r[0] + r[2] - 2:
                    axis_labels.append((grid_label(g), image, (int(x) + 3, bottom_band)))
        for k in range(gy0, gy1 + 1):
            g = k * step
            _, y = view.world_to_screen(0, g)
            if r[1] <= y <= r[1] + r[3]:
                lines.line(s, config.COLOR_GEO_GRID, (r[0], int(y)), (r[0] + r[2], int(y)))
                if top_band <= int(y) + 3 and int(y) + 3 + label_h <= bottom_band:
                    axis_labels.append((grid_label(g), layout.render_line(
                        face, grid_label(g), config.COLOR_TEXT_DIM), (r[0] + 3, int(y) + 3)))
        for text, image, pos in axis_labels:
            rect = image.get_rect(topleft=pos)
            layout.record_text(text, rect, r, image)
            s.blit(image, rect)
            if field is not None:
                # Contact labels step aside from the axis numbers.
                field.reserve(image.get_bounding_rect().move(rect.topleft))

    # Land / Inseln. Legacy/fake coast providers retain their old API.
    landmasses = getattr(coast, "landmasses", None)
    visible_land = (_visible_landmasses(coast, view, r)
                    if landmasses is not None else None)
    polygons = ([[view.world_to_screen(px, py) for px, py in land.points]
                 for land in visible_land]
                if visible_land is not None else coast.land_points_px(view))
    for poly in polygons:
        poly = clip_polygon_to_rect(poly, r)
        if len(poly) < 3:
            continue
        lines.polygon(s, config.COLOR_LAND, poly)
        lines.polygon(s, config.COLOR_LAND_EDGE, poly, 1)
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
        if not _in_rect(px, py, r, 0.0):
            # Off-chart bases would have their labels pinned to the edge.
            continue
        col = config.COLOR_DANGER if base.get("gameplay_role") == "hostile" \
            else config.COLOR_FLIGHT
        pygame.draw.rect(s, col, (int(px) - 4, int(py) - 4, 8, 8), 2)
        _map_label(s, game, raw_text(base["name"]), (int(px) + 7, int(py) - 8),
                   config.COLOR_TEXT_DIM, r)
    # Charted wrecks and underwater rocks (public chart information).
    hazards = getattr(w, "charted_hazards", None)
    if hazards is not None:
        chart_symbols.draw_hazards(s, hazards(), view.world_to_screen, r, view.scale)
    draw_weather_band(game, r)


@localized
def _draw_guard_area(game, view, r) -> None:
    """What the frigate's orders tell it to guard (authored mission data):
    the strait's gate or the coast section of the swimmers' mission."""
    from src.core import boat_missions
    area = boat_missions.guard_area(game)
    if area is None:
        return
    s = game.screen
    color = config.COLOR_WARN
    if area["kind"] == "gate":
        (ax, ay), (bx, by) = area["ends"]
        p1 = view.world_to_screen(ax, ay)
        p2 = view.world_to_screen(bx, by)
        lines.line(s, color, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 2)
        label_at = (int(max(p1[0], p2[0])) + 6, int(min(p1[1], p2[1])) - 16)
        key = "map.guard.gate"
    else:
        px, py = view.world_to_screen(area["x"], area["y"])
        radius = max(8, int(area["radius_nm"] * view.scale))
        pygame.draw.circle(s, color, (int(px), int(py)), radius, 1)
        label_at = (int(px) + 6, int(py) - radius - 16)
        key = area.get("label", "map.guard.coast")
    _map_label(s, game, key, label_at, color, r, size=12)


def draw_map_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    r = config.MAP_RECT
    view = copy.copy(game.map_view)
    view.set_rect(r)

    # See-Hintergrund; bleibt auch ausserhalb der Weltgrenzen sichtbar.
    pygame.draw.rect(s, chart_background(game), r)
    with layout.clip_to(s, r), label_layout.label_scope(r) as labels:
        # Own ship first: no label may cover it.
        ox, oy = view.world_to_screen(game.ship.x, game.ship.y)
        labels.reserve((int(ox) - 10, int(oy) - 10, 20, 20))
        draw_chart_geography(game, view, r)
        _draw_guard_area(game, view, r)
        history = getattr(game, "chart_history", None)
        if history is not None:
            chosen = game.selected_contact or game.target
            chart_trails.draw_side(
                s, history.sides.get("frigate"), view, r, chart_background(game),
                own_now=(game.ship.x, game.ship.y),
                selected_bearing_key=getattr(chosen, "id", None))
        fx = getattr(game, "map_fx", None)
        if fx is not None:
            map_fx_view.draw_fx(s, fx.rows("frigate", game.sim_t), view.world_to_screen,
                                view.scale, r, chart_background(game))

        tracks = game.radar_tracks()

        # Das Lagebild zeigt nur Sensortracks mit gemessener Position.
        for track in (t for t in tracks if t["kind"] in ("SURFACE", "AIS")
                      and observed_position(t)[0] is not None):
            tx, ty = observed_position(track)
            if not _in_rect(*view.world_to_screen(tx, ty), r):
                continue
            px, py = view.world_to_screen(tx, ty)
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(
                s, (px, py), affiliation, "SURFACE", 14)
            _map_label(s, game, raw_text(track["label"]), (int(px) + 7, int(py) - 18),
                       col, r)
            nato_symbols.draw_motion_vector(s, (px, py), track["course"], track["speed_kn"],
                                            view.scale, col, font=game.font, max_px=120)

        for track in (t for t in tracks if t["kind"] == "FLG"
                      and observed_position(t)[0] is not None):
            px, py = view.world_to_screen(*observed_position(track))
            if not _in_rect(px, py, r):
                continue
            affiliation = game.opz_affiliation(track["track_id"])
            col = nato_symbols.draw_symbol(s, (px, py), affiliation, "AIR", 14)
            _map_label(s, game, raw_text(track["label"]), (int(px) + 9, int(py) - 14),
                       col, r)
            nato_symbols.draw_motion_vector(s, (px, py), track["course"], track["speed_kn"],
                                            view.scale, col, font=game.font, max_px=120)

        # Eigene Torpedos
        for t in game.torpedoes:
            px, py = view.world_to_screen(t.x, t.y)
            ang = math.radians(t.course - 90.0)
            lines.line(s, config.COLOR_WARN, (int(px), int(py)),
                             (int(px + 10 * math.cos(ang)), int(py + 10 * math.sin(ang))), 2)
            pygame.draw.circle(s, config.COLOR_WARN, (int(px), int(py)), 3)
            _map_label(s, game, raw_text(f"T{t.idx}"), (int(px) + 10, int(py) - 24),
                       config.COLOR_WARN, r)

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
            _map_label(s, game, raw_text(track["label"]), (int(px) + 10, int(py) - 12),
                       col, r)
            nato_symbols.draw_motion_vector(s, (px, py), track["course"], track["speed_kn"],
                                            view.scale, col, font=game.font, max_px=120)
        fx, fy = view.world_to_screen(game.ship.x, game.ship.y)
        for track in (t for t in tracks if t["kind"] == "ASM"
                      and observed_position(t)[0] is None):
            rad = math.radians(observed_bearing(track))
            ex, ey = fx + 300 * math.sin(rad), fy - 300 * math.cos(rad)
            lines.line(s, config.COLOR_DANGER, (int(fx), int(fy)),
                             (int(ex), int(ey)), 1)
            _map_label(s, game, raw_text(track["source"] + " " + track["label"]),
                       (int(fx) + 12, int(fy) + 24), config.COLOR_DANGER, r)
        for e in game.essms:
            px, py = view.world_to_screen(e.x, e.y)
            pygame.draw.circle(s, theme.pick((220, 200, 90), (161, 98, 7)), (int(px), int(py)), 3)

        # Peilstrich + Ziel-Kreuz (ausgewählter Kontakt / Ziel)
        for contact, fix, (px, py) in active_fix_markers(game, view):
            color = {"PING": theme.pick((90, 220, 220), (14, 116, 144)),
                     "DIPPING": theme.pick((120, 220, 190), (4, 120, 87)),
                     "TMA": config.COLOR_WARN, "MAD": theme.pick((200, 160, 240), (126, 34, 206)),
                     "VISUAL": theme.pick((230, 230, 200), (55, 65, 81)),
                     "CONSORT": config.COLOR_FLIGHT,
                     "SONOBUOY": config.COLOR_CONTACT_ZIVIL}[fix["source"]]
            radius = _fix_marker_radius(fix, view)
            pygame.draw.circle(s, color, (px, py), radius, 1)
            lines.line(s, color, (px - 6, py), (px + 6, py), 1)
            lines.line(s, color, (px, py - 6), (px, py + 6), 1)
            _map_label(s, game, message(
                "map.line.sonar_fix",
                contact=observations.contact_display_id(game, contact),
                source=fix["source"]), (px + 9, py - 19), color, r, size=12)

        contact = game.selected_contact or game.target
        if contact is not None:
            observer_x = getattr(contact, "observer_x", game.ship.x)
            observer_y = getattr(contact, "observer_y", game.ship.y)
            fx, fy = view.world_to_screen(observer_x, observer_y)
            brg = math.radians(observed_bearing(contact))
            ex_w, ey_w = contact_position(contact, game.ship)
            if ex_w is not None and ey_w is not None:
                tx, ty = view.world_to_screen(ex_w, ey_w)
                line_col = config.COLOR_DANGER if contact is game.target \
                    else config.COLOR_WARN
                lines.line(s, line_col, (int(fx), int(fy)), (int(tx), int(ty)), 1)
                if contact.range_sigma_nm:
                    sigma_px = max(3, int(contact.range_sigma_nm * view.scale))
                    pygame.draw.circle(s, line_col, (int(tx), int(ty)), sigma_px, 1)
                lines.line(s, line_col, (int(tx) - 8, int(ty)), (int(tx) + 8, int(ty)), 2)
                lines.line(s, line_col, (int(tx), int(ty) - 8), (int(tx), int(ty) + 8), 2)
                src = ({"tma": "TMA", "ping": "PING",
                        "buoy": localize("map.source.buoy")}
                       .get(contact.range_source, "FIX"))
                _map_label(s, game, structured_message(
                    "map.line.contact_fix",
                    contact=observations.contact_display_id(game, contact),
                    range=f"{observations.range_nm(contact, game.ship):4.1f}", source=src),
                    (int(tx) + 11, int(ty) - 22), line_col, r)
                nato_symbols.draw_motion_vector(
                    s, (tx, ty), getattr(contact, "tma_course", None),
                    getattr(contact, "tma_speed", None),
                    view.scale, line_col, font=game.font, max_px=120)
            else:
                # The weapons station's target carries the ping hint in one
                # label (the overlay adds no second one at the same spot).
                aimed = contact is game.target
                hint = aimed and getattr(game, "station", None) is Station.WEAPONS
                line_col = config.COLOR_DANGER if aimed else config.COLOR_WARN
                ex = fx + 300 * math.sin(brg)
                ey = fy - 300 * math.cos(brg)
                lines.line(s, line_col, (int(fx), int(fy)),
                                 (int(ex), int(ey)), 1)
                _map_label(s, game, structured_message(
                    "weapons.line.bearing_only.short" if hint else "map.line.bearing_only",
                    contact=observations.contact_display_id(game, contact)),
                    (int(fx) + 14, int(fy) - 20), line_col, r)

        # Manuell protokollierte HFDF-Messungen und daraus berechnete Fixes.
        for report in game.hfdf_log[-6:]:
            if game.sim_t - report["t"] > 300.0:
                continue
            ox, oy = view.world_to_screen(report["observer_x"], report["observer_y"])
            brg = math.radians(report["bearing"])
            ex, ey = ox + 260 * math.sin(brg), oy - 260 * math.cos(brg)
            lines.line(s, config.COLOR_ESM, (int(ox), int(oy)),
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
                lines.lines(s, config.COLOR_ESM, True, points, 1)
            else:
                radius = max(4, int(fix["sigma_nm"] * view.scale))
                pygame.draw.circle(s, config.COLOR_ESM, (int(px), int(py)), radius, 1)
            _map_label(s, game, message("map.hfdf_fix", label=fix["label"], age=f"{age:.0f}"),
                       (int(px) + 8, int(py) - 20), config.COLOR_ESM, r, size=14)

        # Autopilot route: from the ship through the waypoints still ahead.
        route = getattr(game, "route", None)
        if route is not None and route.active:
            previous = view.world_to_screen(game.ship.x, game.ship.y)
            for number, (wx, wy) in enumerate(route.remaining(), start=route.index + 1):
                point = view.world_to_screen(wx, wy)
                lines.line(s, config.COLOR_WARN, (int(previous[0]), int(previous[1])),
                           (int(point[0]), int(point[1])), 1)
                pygame.draw.circle(s, config.COLOR_WARN, (int(point[0]), int(point[1])), 5, 1)
                _map_label(s, game, message("map.route_waypoint", number=number),
                           (int(point[0]) + 7, int(point[1]) - 18),
                           config.COLOR_WARN, r, size=12)
                previous = point

        # Fregatte: Pfeil in Kursrichtung
        px, py = view.world_to_screen(game.ship.x, game.ship.y)
        ang = math.radians(game.ship.course - 90.0)
        target_ang = math.radians(game.ship.target_course - 90.0)
        target_ex = int(px + 42 * math.cos(target_ang))
        target_ey = int(py + 42 * math.sin(target_ang))
        lines.line(s, config.COLOR_TEXT_DIM, (int(px), int(py)),
                         (target_ex, target_ey), 1)
        _map_label(s, game, structured_message("map.target_course",
                                               course=f"{game.ship.target_course:03.0f}"),
                   (int(px) + 8, int(py) + 10), config.COLOR_TEXT_DIM, r, size=12)
        L = 14
        lines.line(s, config.COLOR_TEXT, (int(px), int(py)),
                         (int(px + L * math.cos(ang)), int(py + L * math.sin(ang))), 3)
        pygame.draw.circle(s, config.COLOR_TEXT, (int(px), int(py)), 4)
        nato_symbols.draw_motion_vector(s, (px, py), game.ship.course, game.ship.speed,
                                        view.scale, config.COLOR_OK, max_px=120)

        # HSP-5 zuletzt: beim Start an gleicher Position bleibt es ueber dem Schiff.
        if game.helo.airborne:
            px, py = view.world_to_screen(game.helo.x, game.helo.y)
            col = nato_symbols.draw_symbol(
                s, (px, py), "FRIEND", "AIR", size=22)
            nato_symbols.draw_motion_vector(
                s, (px, py), game.helo.course, game.helo.SPEED_KN,
                view.scale, col, max_px=120)
            _map_label(s, game, raw_text("HSP-5"), (int(px) + 15, int(py) - 14),
                       col, r)
        draw_plot(s, game, view, r)
    global _LAST_LABELS
    _LAST_LABELS = labels

    draw_chart_frame(game, view, r, getattr(game, "map_follow", True))


# Label field of the last frigate chart drawn: the weapons overlay continues
# it so its target marks step aside from the chart's labels.
_LAST_LABELS = None


def last_label_field():
    return _LAST_LABELS


def daylight_stage(world) -> str:
    """The chart's light stage; fake/legacy worlds without a clock draw by day."""
    stage = getattr(world, "daylight_stage", None)
    if callable(stage):
        return stage()
    hour = getattr(world, "hour", None)
    return atmosphere.daylight_stage(hour) if isinstance(hour, (int, float)) else "day"


def chart_background(game):
    """The sea background in the light of the hour (display only)."""
    return theme.water_color(config.COLOR_GEO_BG, daylight_stage(game.world))


# Rain hatch: line spacing (px) at light and at heavy rain, and its alpha.
WEATHER_HATCH_SPACING_PX = (46, 18)
WEATHER_HATCH_ALPHA = (28, 70)
WEATHER_BAND_MIN_RAIN = 0.25


def draw_weather_band(game, r) -> None:
    """Rain and storm over the chart as a dashed diagonal hatch (display
    only, from the world's public weather values; a storm adds a warning
    border).  Nothing here depends on entities."""
    values = getattr(game.world, "weather_values", None)
    kind = getattr(game.world, "weather_kind", None)
    if not callable(values) or not callable(kind):
        return                       # fake/legacy worlds without weather
    weather = values()
    rain = config.clamp(weather["rain_intensity"], 0.0, 1.0)
    storm = kind() == "storm"
    if rain < WEATHER_BAND_MIN_RAIN and not storm:
        return
    rect = pygame.Rect(r)
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    strength = config.clamp((rain - WEATHER_BAND_MIN_RAIN) / (1.0 - WEATHER_BAND_MIN_RAIN),
                            0.0, 1.0)
    spacing = int(WEATHER_HATCH_SPACING_PX[0]
                  + (WEATHER_HATCH_SPACING_PX[1] - WEATHER_HATCH_SPACING_PX[0]) * strength)
    alpha = int(WEATHER_HATCH_ALPHA[0] + (WEATHER_HATCH_ALPHA[1] - WEATHER_HATCH_ALPHA[0]) * strength)
    color = (*config.COLOR_WARN, alpha) if storm else (170, 190, 200, alpha)
    dash, gap = 9, 7
    for start in range(-rect.h, rect.w, max(6, spacing)):
        # Diagonal from the bottom-left, dashed.
        length = int(math.hypot(rect.h, rect.h))
        for offset in range(0, length, dash + gap):
            x0 = start + offset * 0.7071
            y0 = rect.h - offset * 0.7071
            x1 = start + (offset + dash) * 0.7071
            y1 = rect.h - (offset + dash) * 0.7071
            pygame.draw.line(layer, color, (x0, y0), (x1, y1), 1)
    game.screen.blit(layer, rect.topleft)
    if storm:
        pygame.draw.rect(game.screen, config.COLOR_WARN, rect, 2)


# The scale line's text size; the grid keeps its numbers out of its band.
SCALE_TEXT_SIZE = 13


def scale_rect(r) -> pygame.Rect:
    """Box of the scale / follow line in the chart's top-left corner (the
    longest German follow text fits; axis numbers and labels keep off it)."""
    face = layout.font(SCALE_TEXT_SIZE)
    width, height = layout.text_size(face, localize(structured_message(
        "map.line.scale_follow", zoom="00.0")))
    return pygame.Rect(r[0] + 4, r[1] + 4, min(r[2] - 8, width + 4), height + 2)


def draw_chart_frame(game, view, r, following: bool) -> None:
    """Chart border and the scale / follow line."""
    s = game.screen
    pygame.draw.rect(s, config.COLOR_GEO_GRID, r, 1)
    # Only the scale (and follow while on); the sector name is in the briefing.
    zoom_nm = r[3] / view.scale
    layout.blit_line(
        s, structured_message("map.line.scale_follow" if following else "map.line.scale",
                              zoom=scale_label(zoom_nm)),
        (r[0] + 4, r[1] + 4, r[2] - 8, 20), config.COLOR_TEXT_DIM,
        size=SCALE_TEXT_SIZE)
