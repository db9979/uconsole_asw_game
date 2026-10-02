"""The crewed boat's navigation page: pilot chart and echo sounder.

Shown first at the boat's navigation station (key 6).  Everything here is
own-ship truth or the known chart: the boat's position, course, speed and
depth, its sounding under the keel (the depth it already measures for the
keel warning), the charted depth (bathymetry without tide or hazards), the
charted hazards and the crew's own obstacle check ahead.  No other vessel is
read.  The chart's depth picture is computed once per chart cell crossed and
kept in a one-entry cache; the sounder trace is ``CrewedBoat.sounder``.
"""

import math
from types import SimpleNamespace

import pygame

from src.core import boat_nav, config
from src.core.echo_sounder import WINDOW_S
from src.core.i18n import message, raw_text
from src.ship import route as route_model
from src.ui import chart_symbols, console, layout, lines, nato_symbols, pointer
from src.ui.map_view import _visible_landmasses, clip_polygon_to_rect
from src.ui.viewport import Viewport

# Pilot chart: half its width in NM, pixels per depth cell, depth contours (m).
PILOT_RANGE_NM = 6.0
PILOT_CELL_PX = 8
PILOT_CONTOURS_M = (20.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0)
# Extra depth over the keel limit the chart paints amber (m).
PILOT_CAUTION_M = 2 * config.UBOOT_UNDER_KEEL_WARN_M
# Course line: a tick every this many minutes at the present speed.
PILOT_TICK_MIN = 5.0
# Sounder strip: share of its width for the past trace (the rest looks ahead),
# points of the charted profile ahead, and the shallowest depth scale (m).
SOUNDER_PAST_SHARE = 0.7
SOUNDER_AHEAD_POINTS = 24
SOUNDER_MIN_SCALE_M = 60.0
_CAUTION_TINT = (120, 96, 30)
_DANGER_TINT = (128, 44, 40)
_CONTOUR = (44, 86, 110)
_PILOT_CACHE = {}


def _mix(color, other, amount):
    return console._mix(color, other, amount)


def keel_limit_m(sub) -> float:
    """Deepest keel of the boat's present and ordered depth plus clearance,
    the same limit as the crew's obstacle check ahead."""
    return max(sub.depth, sub.order_depth) + config.UBOOT_BOTTOM_CLEARANCE_M


def clearance_level(clearance) -> str:
    """Lamp level of a keel clearance (m): alarm under the warning depth."""
    if clearance is None or not math.isfinite(clearance):
        return "off"
    if clearance < config.UBOOT_UNDER_KEEL_WARN_M:
        return "alarm"
    if clearance < PILOT_CAUTION_M:
        return "caution"
    return "on"


# Water shades from the shallowest depth band to the deepest (chart style:
# shallow water light, deep water dark), one per band of PILOT_CONTOURS_M.
_BAND_SHADES = tuple(_shade for _shade in (
    (46, 96, 128), (36, 82, 114), (28, 70, 102), (22, 58, 90), (16, 46, 78),
    (11, 36, 66), (8, 28, 56), (5, 21, 46)))
_LAND = (36, 56, 64)


def _cell_color(depth, keel):
    if depth <= 0.0:
        return _LAND
    if depth < keel:
        return _DANGER_TINT
    if depth < keel + PILOT_CAUTION_M:
        return _CAUTION_TINT
    return _BAND_SHADES[_band(depth)]


def _band(depth):
    return sum(1 for level in PILOT_CONTOURS_M if depth >= level)


def _depth_picture(world, gx0, gy0, cols, rows, cell_nm, keel):
    """The chart's depth cells as one surface (cached per cell crossed)."""
    key = (id(world), world.size_nm, gx0, gy0, cols, rows, round(cell_nm, 6),
           round(keel / 5.0))
    surface = _PILOT_CACHE.get(key)
    if surface is not None:
        return surface
    depths = [[world.charted_depth_m((gx0 + col + .5) * cell_nm, (gy0 + row + .5) * cell_nm)
               for col in range(cols)] for row in range(rows)]
    size = PILOT_CELL_PX
    surface = pygame.Surface((cols * size, rows * size))
    for row in range(rows):
        for col in range(cols):
            surface.fill(_cell_color(depths[row][col], keel),
                         (col * size, row * size, size, size))
    # Depth contours along the cell edges where the depth band changes.
    for row in range(rows):
        for col in range(cols):
            band = _band(depths[row][col])
            if col + 1 < cols and _band(depths[row][col + 1]) != band:
                x = (col + 1) * size
                pygame.draw.line(surface, _CONTOUR, (x, row * size), (x, (row + 1) * size - 1))
            if row + 1 < rows and _band(depths[row + 1][col]) != band:
                y = (row + 1) * size
                pygame.draw.line(surface, _CONTOUR, (col * size, y), ((col + 1) * size - 1, y))
    _PILOT_CACHE.clear()
    _PILOT_CACHE[key] = surface
    return surface


def _own(game, sub):
    """Where the crew believes the boat is: its dead-reckoned position for
    the crewed boat (``boat_nav``), the true one otherwise."""
    boat = getattr(game, "opfor", None)
    if boat is not None and boat.sub is sub:
        x, y = boat_nav.position(boat)
        return SimpleNamespace(x=x, y=y)
    return sub


def pilot_view(game, sub, rect) -> Viewport:
    """North-up chart camera centred on the boat's navigated position,
    PILOT_RANGE_NM to each side."""
    rect = pygame.Rect(rect)
    view = Viewport(game.world.size_nm, 1e-6, 1e6)
    view.set_rect(tuple(rect))
    view.scale = rect.w / (2.0 * PILOT_RANGE_NM)
    own = _own(game, sub)
    view.cx, view.cy = own.x, own.y
    return view


def bearing_at(game, sub, rect, pos):
    """True bearing from the boat to a point of the pilot chart, else None."""
    if pos is None or not pygame.Rect(rect).collidepoint(pos):
        return None
    wx, wy = pilot_view(game, sub, rect).screen_to_world(*pos)
    own = _own(game, sub)
    dx, dy = wx - own.x, wy - own.y
    if math.hypot(dx, dy) < 1e-6:
        return None
    return round(math.degrees(math.atan2(dx, -dy))) % 360


def _ray(sub, course, distance):
    rad = math.radians(course)
    return sub.x + distance * math.sin(rad), sub.y - distance * math.cos(rad)


def draw_pilot_chart(s, game, boat, rect) -> None:
    """Own-centred chart: depth cells and contours, hazards, the wake, rings,
    the ordered course ahead with time ticks and the obstacle the crew found."""
    rect = pygame.Rect(rect)
    if rect.w < 80 or rect.h < 60:
        return
    sub = boat.sub
    own = _own(game, sub)
    shift_x, shift_y = boat_nav.error(boat)
    world = game.world
    view = pilot_view(game, sub, rect)
    cell_nm = PILOT_CELL_PX / view.scale
    left, top = view.screen_to_world(rect.x, rect.y)
    gx0, gy0 = math.floor(left / cell_nm), math.floor(top / cell_nm)
    cols = rect.w // PILOT_CELL_PX + 2
    rows = rect.h // PILOT_CELL_PX + 2
    with layout.clip_to(s, rect):
        picture = _depth_picture(world, gx0, gy0, cols, rows, cell_nm, keel_limit_m(sub))
        px, py = view.world_to_screen(gx0 * cell_nm, gy0 * cell_nm)
        s.blit(picture, (round(px), round(py)))
        coast = world.coast
        if getattr(coast, "landmasses", None) is not None:
            for land in _visible_landmasses(coast, view, tuple(rect)):
                poly = clip_polygon_to_rect([view.world_to_screen(px, py)
                                             for px, py in land.points], tuple(rect))
                if len(poly) >= 3:
                    lines.polygon(s, _LAND, poly)
                    lines.polygon(s, config.COLOR_LAND_EDGE, poly, 1)
        hazards = getattr(world, "charted_hazards", None)
        if hazards is not None:
            chart_symbols.draw_hazards(s, hazards(), view.world_to_screen, tuple(rect), view.scale)
        bx, by = view.world_to_screen(own.x, own.y)
        # Range rings every 2 NM with their distance.
        ring_row = layout.font(12).get_linesize()
        for ring_nm in range(2, int(PILOT_RANGE_NM * 2) + 1, 2):
            radius = int(ring_nm * view.scale)
            pygame.draw.circle(s, config.COLOR_SONAR_RING, (int(bx), int(by)), radius, 1)
            if by - radius >= rect.y:
                layout.blit_line(s, raw_text(f"{ring_nm}"),
                                 (int(bx) + 3, int(by) - radius, 28, ring_row),
                                 config.COLOR_TEXT_DIM, size=12)
        # The wake: where the boat was over the sounder's window.
        trail = [view.world_to_screen(x + shift_x, y + shift_y)
                 for _t, x, y, _b, _d in boat.sounder.window(game.sim_t)]
        if len(trail) >= 2:
            lines.lines(s, config.COLOR_TEXT_DIM, False, trail + [(bx, by)], 1)
        # Ordered course ahead to the look-ahead, ticks every PILOT_TICK_MIN.
        ahead = config.UBOOT_OBSTACLE_LOOKAHEAD_NM
        ex, ey = view.world_to_screen(*_ray(own, sub.order_course, ahead))
        lines.line(s, config.COLOR_TEXT, (bx, by), (ex, ey), 2)
        far = view.world_to_screen(*_ray(own, sub.order_course, PILOT_RANGE_NM * 2))
        lines.line(s, config.COLOR_TEXT_DIM, (ex, ey), far, 1)
        step = max(0.0, sub.speed) * PILOT_TICK_MIN / 60.0
        if step >= 0.2:
            rad = math.radians(sub.order_course)
            nx, ny = math.cos(rad), math.sin(rad)
            distance = step
            while distance <= ahead + 1e-9:
                tx, ty = view.world_to_screen(*_ray(own, sub.order_course, distance))
                lines.line(s, config.COLOR_TEXT, (tx - 6 * nx, ty - 6 * ny),
                           (tx + 6 * nx, ty + 6 * ny), 2)
                distance += step
        obstacle = boat.orders.obstacle_ahead_nm
        if obstacle is not None:
            ox, oy = view.world_to_screen(*_ray(own, sub.order_course, obstacle))
            for sx, sy in ((1, 1), (1, -1)):
                lines.line(s, config.COLOR_DANGER, (ox - 7 * sx, oy - 7 * sy),
                           (ox + 7 * sx, oy + 7 * sy), 3)
            label_w = 150
            lx = int(ox) + 10 if ox + 10 + label_w <= rect.right else int(ox) - 10 - label_w
            layout.blit_line(s, message("uboot.pilot.value.shoal", range=f"{obstacle:.1f}"),
                             (lx, int(oy) + 8, label_w, layout.font(14).get_linesize()), config.COLOR_DANGER, size=14,
                             align="left" if lx > ox else "right")
        # The boat and its heading.
        heading = math.radians(sub.course)
        lines.line(s, config.COLOR_OK, (bx, by),
                   (bx + 22 * math.sin(heading), by - 22 * math.cos(heading)), 2)
        nato_symbols.draw_symbol(s, (bx, by), "FRIEND", "SUBSURFACE", 18)
        layout.blit_line(s, "uboot.pilot.north",
                         (rect.right - 26, rect.y + 4, 20, layout.font(14).get_linesize()),
                         config.COLOR_TEXT_DIM, size=14, align="center")
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)
    # A click on the chart orders the course to that point (as typed with C).
    from src.core import pointer_input
    pointer.add_action(rect, lambda pos, r=tuple(rect): pointer_input.enter_value(
        game, "uboot_course", bearing_at(game, boat.sub, r, pos)))


def ahead_profile(game, sub) -> list:
    """Charted depth along the ordered course out to the look-ahead:
    ``(distance_nm, depth_m)`` from the boat's navigated position outwards."""
    ahead = config.UBOOT_OBSTACLE_LOOKAHEAD_NM
    own = _own(game, sub)
    rows = []
    for index in range(SOUNDER_AHEAD_POINTS + 1):
        distance = ahead * index / SOUNDER_AHEAD_POINTS
        rows.append((distance, max(0.0, game.world.charted_depth_m(
            *_ray(own, sub.order_course, distance)))))
    return rows


def sounder_scale_m(sub, bottoms) -> float:
    """Depth at the foot of the strip: the deepest sounding, but never so
    deep that the boat's own depth band shrinks to a line."""
    deepest = max([b for b in bottoms if math.isfinite(b)] or [0.0])
    cap = max(sub.crush_depth_m * 1.25, sub.depth * 2.0 + 100.0, sub.order_depth * 1.5)
    return max(SOUNDER_MIN_SCALE_M, min(deepest * 1.1, cap), sub.depth * 1.2,
               sub.order_depth * 1.2)


def draw_sounder(s, game, boat, rect) -> None:
    """Echo-sounder strip: seabed and own depth over the last minutes, the
    charted profile ahead on the ordered course, keel clearance in colour."""
    rect = pygame.Rect(rect)
    if rect.w < 120 or rect.h < 50:
        return
    sub = boat.sub
    now = game.sim_t
    row_h = layout.font(12).get_linesize()
    axis_w = layout.font(12).size("0000")[0] + 8
    plot = pygame.Rect(rect.x + axis_w, rect.y + 2, rect.w - axis_w, rect.h - row_h - 6)
    if plot.h < 30:
        return
    samples = boat.sounder.window(now)
    bottom_now = sub.last_bottom_m
    past = [(t, b, d) for t, _x, _y, b, d in samples]
    if bottom_now is not None and math.isfinite(bottom_now):
        past.append((now, max(0.0, bottom_now), sub.depth))
    ahead = ahead_profile(game, sub)
    scale = sounder_scale_m(sub, [b for _t, b, _d in past] + [d for _x, d in ahead])
    split = plot.x + int(plot.w * SOUNDER_PAST_SHARE)

    def dy(depth):
        return plot.y + int(plot.h * max(0.0, min(1.0, depth / scale)))

    def tx(t):
        return plot.x + int((split - plot.x) * max(0.0, min(1.0, 1.0 - (now - t) / WINDOW_S)))

    def ax(distance):
        return split + int((plot.right - 1 - split) * distance / config.UBOOT_OBSTACLE_LOOKAHEAD_NM)

    pygame.draw.rect(s, config.COLOR_DEEP, plot)
    # Depth grid with its numbers.
    step = next((value for value in (10, 20, 50, 100, 200, 500, 1000, 2000)
                 if scale / value <= 5), 5000)
    for value in range(0, int(scale) + 1, step):
        y = dy(value)
        lines.line(s, config.COLOR_GRID, (plot.x, y), (plot.right - 1, y), 1)
        layout.blit_line(s, raw_text(f"{value}"), (rect.x, y - row_h // 2, axis_w - 6, row_h),
                         config.COLOR_TEXT_DIM, size=12, align="right")
    # Seabed: the trace taken (solid) and the chart ahead (dim).
    if len(past) >= 2:
        points = [(tx(t), dy(b)) for t, b, _d in past]
        lines.polygon(s, config.COLOR_LAND, [(points[0][0], plot.bottom)] + points
                      + [(points[-1][0], plot.bottom)])
        lines.lines(s, config.COLOR_LAND_EDGE, False, points, 2)
        # Thin keel clearance: the water between keel and seabed glows.
        for t, b, d in past:
            level = clearance_level(b - d)
            if level in ("caution", "alarm"):
                color = config.COLOR_DANGER if level == "alarm" else config.COLOR_WARN
                lines.line(s, color, (tx(t), dy(d)), (tx(t), dy(b)), 2)
        lines.lines(s, config.COLOR_OK, False, [(tx(t), dy(d)) for t, _b, d in past], 2)
    profile = [(ax(distance), dy(depth)) for distance, depth in ahead]
    lines.polygon(s, _mix(config.COLOR_LAND, config.COLOR_DEEP, .4),
                  [(profile[0][0], plot.bottom)] + profile + [(profile[-1][0], plot.bottom)])
    for index in range(0, len(profile) - 1, 2):
        lines.line(s, config.COLOR_LAND_EDGE, profile[index], profile[index + 1], 1)
    # Ordered depth ahead, and the crush depth when it is on the scale.
    order_y = dy(sub.order_depth)
    for x in range(split, plot.right - 1, 10):
        lines.line(s, config.COLOR_TEXT, (x, order_y), (min(x + 5, plot.right - 1), order_y), 1)
    if sub.crush_depth_m <= scale:
        crush_y = dy(sub.crush_depth_m)
        lines.line(s, config.COLOR_DANGER, (plot.x, crush_y), (plot.right - 1, crush_y), 1)
    obstacle = boat.orders.obstacle_ahead_nm
    if obstacle is not None:
        x = ax(obstacle)
        lines.line(s, config.COLOR_DANGER, (x, plot.y), (x, plot.bottom - 1), 2)
    # Now: the boat at its depth.
    lines.line(s, config.COLOR_TEXT_DIM, (split, plot.y), (split, plot.bottom - 1), 1)
    hull = pygame.Rect(0, 0, 18, 7)
    hull.center = (split, dy(sub.depth))
    pygame.draw.ellipse(s, nato_symbols.AFFILIATION_COLORS["FRIEND"], hull)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, plot, 1)
    if len(past) < 2:
        layout.blit_line(s, "uboot.pilot.no_trace",
                         (plot.x + 8, plot.y + 4, split - plot.x - 16, row_h + 4),
                         config.COLOR_TEXT_DIM, size=14)
    if bottom_now is not None and math.isfinite(bottom_now) and bottom_now > scale:
        layout.blit_line(s, message("uboot.pilot.off_scale", depth=f"{bottom_now:.0f}"),
                         (plot.x + 8, plot.bottom - row_h - 6, split - plot.x - 16, row_h + 4),
                         config.COLOR_LAND_EDGE, size=14)
    # Time and distance along the foot.
    foot = plot.bottom + 3
    third = (split - plot.x) // 3
    layout.blit_line(s, message("uboot.pilot.axis.past", minutes=f"{WINDOW_S / 60:.0f}"),
                     (plot.x, foot, third, row_h), config.COLOR_TEXT_DIM, size=12)
    layout.blit_line(s, "uboot.pilot.axis.now", (split - third // 2, foot, third, row_h),
                     config.COLOR_TEXT_DIM, size=12, align="center")
    layout.blit_line(s, message("uboot.pilot.axis.ahead",
                                range=f"{config.UBOOT_OBSTACLE_LOOKAHEAD_NM:.0f}"),
                     (split + 4, foot, plot.right - split - 4, row_h),
                     config.COLOR_TEXT_DIM, size=12, align="right")


def pilot_lamps(game, boat) -> list:
    """The four readouts over the chart: depth, sounding, keel, ahead."""
    sub = boat.sub
    bottom = sub.last_bottom_m
    sounded = bottom is not None and math.isfinite(bottom)
    keel = bottom - sub.depth if sounded else None
    obstacle = boat.orders.obstacle_ahead_nm
    on_order = abs(sub.order_depth - sub.depth) < 1.0
    return [
        ("uboot.pilot.lamp.depth",
         message("uboot.pilot.value.depth", depth=f"{sub.depth:.0f}") if on_order else
         message("uboot.pilot.value.depth_order", depth=f"{sub.depth:.0f}",
                 order=f"{sub.order_depth:.0f}"), "on"),
        ("uboot.pilot.lamp.sounding",
         message("uboot.pilot.value.depth", depth=f"{bottom:.0f}") if sounded
         else raw_text("--"), "on" if sounded else "off"),
        ("uboot.pilot.lamp.keel",
         message("uboot.pilot.value.depth", depth=f"{keel:.0f}") if sounded
         else raw_text("--"), clearance_level(keel)),
        ("uboot.pilot.lamp.ahead",
         message("uboot.pilot.value.shoal", range=f"{obstacle:.1f}") if obstacle is not None
         else message("uboot.pilot.value.clear",
                      range=f"{config.UBOOT_OBSTACLE_LOOKAHEAD_NM:.0f}"),
         "alarm" if obstacle is not None and obstacle < 2.0 else
         "caution" if obstacle is not None else "on"),
        dr_lamp(game, boat),
        route_lamp(boat),
    ]


def dr_lamp(game, boat):
    """The dead-reckoning readout: the navigator's error estimate and the
    age of the last fix, or the GPS fix being taken."""
    progress = boat_nav.fix_progress(boat)
    if progress > 0.0:
        return ("uboot.pilot.lamp.position",
                message("uboot.pilot.value.fixing", percent=f"{progress * 100:.0f}"), "on")
    error = boat_nav.uncertainty_nm(boat)
    return ("uboot.pilot.lamp.position",
            message("uboot.pilot.value.dr", error=f"{error:.1f}",
                    age=f"{boat.orders.nav[2] / 60.0:.0f}"),
            "alarm" if error >= 2.0 else "caution" if error >= 0.5 else "on")


def route_lamp(boat):
    """The route: next waypoint and its bearing from the navigated position."""
    route = boat.orders.route
    if not route.active:
        return ("uboot.pilot.lamp.route", "uboot.pilot.value.route_off", "off")
    bx, by = boat_nav.position(boat)
    x, y = route.points[route.index]
    return ("uboot.pilot.lamp.route",
            message("uboot.pilot.value.route", number=f"{route.index + 1}",
                    count=f"{len(route.points)}",
                    bearing=f"{route_model.bearing_to(bx, by, x, y):03.0f}"), "on")


def draw_pilot_page(s, game, boat, x, y, w, h) -> None:
    """Navigation station, first page: readouts, pilot chart, echo sounder."""
    lamp_h = console.lamp_grid(s, (x, y, w, 3 * (layout.line_pitch(14, 0) + 8) + 8),
                               pilot_lamps(game, boat), 2, size=14)
    top = y + lamp_h + 8
    rest = y + h - top
    if rest < 120:
        return
    chart_h = max(60, int(rest * .56))
    chart = layout.box(s, (x, top, w, chart_h), message(
        "uboot.pilot.chart", range=f"{PILOT_RANGE_NM:.0f}"))
    draw_pilot_chart(s, game, boat, chart)
    sounder_y = top + chart_h + 8
    sounder = layout.box(s, (x, sounder_y, w, y + h - sounder_y), "uboot.pilot.sounder")
    least = boat.sounder.least_clearance(game.sim_t)
    if least is not None:
        level = clearance_level(least)
        row = layout.font(14).get_linesize()
        layout.blit_line(s, message("uboot.pilot.least", depth=f"{least:.0f}",
                                    minutes=f"{WINDOW_S / 60:.0f}"),
                         (x + w // 2, sounder_y + 8, w // 2 - 12, row),
                         console.level_color(level) if level != "on" else config.COLOR_TEXT_DIM,
                         size=14, align="right")
    draw_sounder(s, game, boat, sounder)
