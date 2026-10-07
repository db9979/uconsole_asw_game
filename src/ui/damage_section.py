"""Damage-control pictures drawn like a ship's damage-control board.

The frigate as a side profile (bow right) with its decks, superstructure and
compartments at their real length and height, the sea and waterline outside
with draft marks, the floodwater at its true level tilted by the trim, open
holes with the water rushing in, fitted patches and pumps discharging over
the side; beside it a cross-section that lists with the ship and shows the
two hull voids. The submarine as a longitudinal section of the pressure hull
with sail, casing and fittings, water tilted by the trim, fire and smoke,
chlorine haze, leaks and the round bulkhead doors.

Display only: everything comes from the own ship's damage model and is never
written back. Geometry is fictional and shared with the browser
(``data/commander/js/stations/damage-section.js``, kept equal by
``tests/test_damage_section.py``). Animation runs on wall-clock time like the
other cosmetic timers.
"""

import math

import pygame

from src.core import config
from src.core.i18n import raw_text
from src.ui import console, layout, lines
from src.ui import theme
from src.ui import hires

# Metres: x forward of midships, z above the keel (frigate); y to starboard in
# the cross-section looking forward. Rooms are convex polygons.
FRIGATE = {
    "x_range": [-76.0, 77.0],
    "z_range": [-2.5, 41.0],
    # A cutaway of a modern German frigate: flush hull with a high bow and a
    # bulb, two superstructure islands (hangar aft, bridge and tower mast
    # forward), the boat bay between them, gun on the forecastle; rudder
    # and propeller aft. Outlines only, fictional detail.
    "hull": [[-74.0, 4.0], [-74.0, 10.0], [-20.0, 10.0], [40.0, 10.5], [62.0, 12.0],
             [75.0, 14.5], [73.0, 9.0], [70.0, 4.0], [66.0, 0.8], [60.0, 0.0],
             [-55.0, 0.0], [-66.0, 2.0], [-72.0, 3.0]],
    "dome": [[62.0, 0.5], [66.0, -1.0], [72.0, -0.2], [74.0, 2.5], [70.0, 3.5]],
    "blocks": [
        [[-50.0, 10.0], [-50.0, 17.0], [-30.0, 17.0], [-28.0, 22.0], [-14.0, 22.0],
         [-12.0, 17.0], [-4.0, 17.0], [-4.0, 10.0]],
        [[-26.0, 22.0], [-24.0, 27.0], [-17.0, 27.0], [-16.0, 22.0]],
        [[-22.7, 27.0], [-23.0, 28.8], [-21.8, 30.6], [-19.2, 30.6], [-18.0, 28.8],
         [-18.3, 27.0]],
        [[10.0, 10.3], [10.0, 19.0], [14.0, 19.0], [14.0, 23.0], [33.0, 23.0],
         [36.0, 19.0], [40.0, 16.0], [41.0, 10.5]],
        [[14.0, 23.0], [16.0, 33.0], [20.0, 36.0], [23.0, 33.0], [24.0, 23.0]],
        [[46.0, 11.1], [47.0, 13.2], [53.0, 13.2], [54.0, 11.4]],
        [[36.5, 17.6], [36.5, 19.4], [39.0, 19.4], [39.0, 17.6]],
        [[-44.0, 17.0], [-44.0, 18.8], [-40.0, 18.8], [-40.0, 17.0]],
        [[-2.0, 12.4], [-1.0, 11.2], [8.0, 11.2], [9.0, 12.4]],
        [[-68.0, 1.5], [-68.0, -1.8], [-63.0, -1.8], [-63.0, 1.2]],
    ],
    "lines": [[[19.5, 36.0], [19.5, 40.5]], [[53.0, 12.6], [61.0, 13.2]],
              [[4.0, 10.3], [4.0, 30.0]], [[1.5, 26.0], [6.5, 26.0]],
              [[-60.0, 0.0], [-60.0, -1.6]], [[-61.2, -0.8], [-58.8, -0.8]],
              [[25.0, 22.0], [32.5, 22.0]]],
    "draft_marks": [[-74.6, 4.0], [-74.6, 6.0], [-74.6, 8.0], [-74.6, 10.0],
                    [70.4, 4.0], [71.6, 6.0], [72.8, 8.0], [73.8, 10.0]],
    "decks": [[[-72.0, 6.0], [70.0, 6.0]], [[-64.0, 2.5], [66.0, 2.5]],
              [[-50.0, 13.5], [-4.0, 13.5]], [[10.0, 13.5], [41.0, 13.5]],
              [[10.0, 16.5], [38.0, 16.5]], [[14.0, 19.5], [34.0, 19.5]],
              [[-30.0, 0.5], [-30.0, 10.0]], [[-14.0, 0.5], [-14.0, 10.0]],
              [[-56.0, 0.5], [-56.0, 10.0]], [[-6.0, 0.5], [-6.0, 10.0]],
              [[40.0, 0.5], [40.0, 10.5]], [[56.0, 0.5], [56.0, 11.5]]],
    "rooms": {
        "sonar": [[56.0, 0.5], [64.0, 0.5], [68.0, 3.0], [68.0, 6.0], [56.0, 6.0]],
        "bridge": [[24.0, 19.6], [32.0, 19.6], [32.0, 22.6], [24.0, 22.6]],
        "weapons": [[40.0, 1.0], [56.0, 1.0], [56.0, 7.5], [40.0, 7.5]],
        "opz": [[16.0, 4.0], [40.0, 4.0], [40.0, 8.0], [16.0, 8.0]],
        "radio": [[12.0, 10.8], [24.0, 10.8], [24.0, 16.2], [12.0, 16.2]],
        "engine": [[-38.0, 0.5], [-6.0, 0.5], [-6.0, 7.5], [-38.0, 7.5]],
        "flightdeck": [[-48.0, 10.2], [-32.0, 10.2], [-32.0, 16.6], [-48.0, 16.6]],
    },
    "section": {
        "y_range": [-10.5, 10.5],
        "z_range": [-1.0, 13.0],
        "shell": [[-8.3, 10.4], [-8.3, 3.2], [-6.6, 0.9], [-3.6, 0.0], [3.6, 0.0],
                  [6.6, 0.9], [8.3, 3.2], [8.3, 10.4]],
        "rooms": {
            "hull_left": [[-8.3, 3.4], [-8.3, 6.5], [-5.0, 6.5], [-5.0, 0.4], [-6.4, 1.0]],
            "hull_right": [[8.3, 3.4], [6.4, 1.0], [5.0, 0.4], [5.0, 6.5], [8.3, 6.5]],
        },
    },
}

# The submarine: share of the pressure hull per compartment, stern to bow.
BOAT = {
    "order": ["stern", "engine", "battery", "quarters", "control", "bow"],
    "share": [0.14, 0.2, 0.17, 0.15, 0.18, 0.16],
}

HULL_FILL = (40, 50, 56)
ROOM_FILL = (22, 44, 48)
STEEL = (150, 168, 172)
STEEL_DIM = (84, 100, 106)
SEA = (6, 30, 52)
SEA_LINE = (90, 160, 200)
WATER_TOP = (132, 194, 223)
SPRAY = (160, 214, 240)
GAS = (150, 190, 60)
SMOKE = (70, 72, 76)
MARK = (210, 222, 220)
KEEL = (22, 40, 48)
INK = (170, 186, 186)
DOOR_FILL = (10, 20, 24)
_CACHE: dict = {}
_CACHE_MAX = 6


def _phase() -> float:
    """Wall-clock seconds for cosmetic motion (never simulation time)."""
    return pygame.time.get_ticks() / 1000.0


def _cached(key, build):
    key = (key, theme.revision(), hires.SCALE)
    surface = _CACHE.get(key)
    if surface is None:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        surface = _CACHE[key] = build()
    return surface


def masked(s, polygon, paint) -> None:
    """Let ``paint`` draw on a scratch layer and keep only the polygon."""
    bounds = pygame.Rect(min(p[0] for p in polygon), min(p[1] for p in polygon), 1, 1)
    bounds.width = max(p[0] for p in polygon) - bounds.x + 1
    bounds.height = max(p[1] for p in polygon) - bounds.y + 1
    layer = hires.surface(bounds.size, pygame.SRCALPHA)
    paint(layer, bounds)
    mask = hires.surface(bounds.size, pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255),
                        [(x - bounds.x, y - bounds.y) for x, y in polygon])
    layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(layer, bounds.topleft)


# --- frigate profile ---------------------------------------------------------

class Profile:
    """Metres to screen for the frigate's side profile inside ``rect``."""

    def __init__(self, rect):
        rect = pygame.Rect(rect)
        (x0, x1), (z0, z1) = FRIGATE["x_range"], FRIGATE["z_range"]
        self.scale = max(.5, min(rect.w / (x1 - x0), rect.h / (z1 - z0)))
        self.ox = rect.centerx - (x0 + x1) / 2 * self.scale
        self.oy = rect.centery + (z0 + z1) / 2 * self.scale
        self.rect = rect

    def point(self, x, z):
        return (round(self.ox + x * self.scale), round(self.oy - z * self.scale))

    def points(self, coords):
        return tuple(self.point(x, z) for x, z in coords)


class Section:
    """Metres to screen for the cross-section, listed by ``heel`` degrees
    (positive: starboard down) about the waterline ``pivot_z``."""

    def __init__(self, rect, heel_deg=0.0, pivot_z=7.5):
        rect = pygame.Rect(rect)
        geo = FRIGATE["section"]
        (y0, y1), (z0, z1) = geo["y_range"], geo["z_range"]
        self.scale = max(.5, min(rect.w / (y1 - y0), rect.h / (z1 - z0)))
        self.cx = rect.centerx
        self.pz = pivot_z
        self.py = rect.centery + ((z0 + z1) / 2 - pivot_z) * self.scale
        self.heel = math.radians(max(-40.0, min(40.0, float(heel_deg))))
        self.rect = rect

    def world(self, y, z):
        """Ship frame to world frame (y right, z up) about the pivot."""
        c, s = math.cos(self.heel), math.sin(self.heel)
        dz = z - self.pz
        return y * c + dz * s, dz * c - y * s

    def point(self, y, z):
        wy, wz = self.world(y, z)
        return (round(self.cx + wy * self.scale), round(self.py - wz * self.scale))

    def points(self, coords):
        return tuple(self.point(y, z) for y, z in coords)


def frigate_room_polygons(profile_rect, section_rect, heel_deg=0.0, draft_m=7.5) -> dict:
    """Screen polygons of every compartment (profile rooms and hull voids)."""
    profile = Profile(profile_rect)
    section = Section(section_rect, heel_deg, draft_m)
    rooms = {key: profile.points(coords) for key, coords in FRIGATE["rooms"].items()}
    rooms.update({key: section.points(coords)
                  for key, coords in FRIGATE["section"]["rooms"].items()})
    return rooms


def _static_profile(rect) -> pygame.Surface:
    profile = Profile(pygame.Rect(0, 0, rect.w, rect.h))
    surface = hires.surface(rect.size, pygame.SRCALPHA)
    hull = profile.points(FRIGATE["hull"])
    for coords in FRIGATE["blocks"]:
        pts = profile.points(coords)
        pygame.draw.polygon(surface, HULL_FILL, pts)
        lines.lines(surface, STEEL, True, pts, 1)
    pygame.draw.polygon(surface, HULL_FILL, hull)
    dome = profile.points(FRIGATE["dome"])
    pygame.draw.polygon(surface, HULL_FILL, dome)
    lines.lines(surface, STEEL_DIM, True, dome, 1)
    for start, end in FRIGATE["decks"]:
        lines.line(surface, STEEL_DIM, profile.point(*start), profile.point(*end), 1)
    for start, end in FRIGATE["lines"]:
        lines.line(surface, STEEL, profile.point(*start), profile.point(*end), 2)
    # Frame ticks under the keel every ten metres.
    for x in range(-70, 71, 10):
        top, bottom = profile.point(x, -0.4), profile.point(x, -1.2)
        lines.line(surface, STEEL_DIM, top, bottom, 1)
    # Draft marks on stem and stern every two metres.
    for x, z in FRIGATE["draft_marks"]:
        mx, my = profile.point(x, z)
        lines.line(surface, MARK, (mx - 3, my), (mx + 3, my), 1)
    lines.lines(surface, STEEL, True, hull, 2)
    return surface


def _waterline_z(x, draft_m, trim_deg) -> float:
    """Outside water on the hull: deeper at the bow when trimmed bow down."""
    return draft_m + x * math.tan(math.radians(trim_deg))


def _jet(s, start, toward, strength, color=SPRAY) -> None:
    """Three spray arcs from ``start`` bending toward ``toward``."""
    sx, sy = start
    tx, ty = toward
    length = max(4.0, strength)
    angle = math.atan2(ty - sy, tx - sx)
    wobble = math.sin(_phase() * 9.0) * .12
    for spread in (-.35, 0.0, .35):
        a = angle + spread + wobble
        pts = []
        for step in range(6):
            t = step / 5
            pts.append((sx + math.cos(a) * length * t,
                        sy + math.sin(a) * length * t + length * .35 * t * t))
        lines.lines(s, color, False, pts, 2 if spread == 0.0 else 1)


def _hole(s, center, radius, patched) -> None:
    cx, cy = center
    r = max(3, int(radius))
    if patched:
        plate = pygame.Rect(cx - r - 2, cy - r - 2, 2 * r + 4, 2 * r + 4)
        pygame.draw.rect(s, STEEL_DIM, plate)
        pygame.draw.rect(s, STEEL, plate, 1)
        for bx, by in (plate.topleft, plate.topright, plate.bottomleft, plate.bottomright):
            pygame.draw.circle(s, MARK, (bx + (2 if bx == plate.x else -3),
                                                    by + (2 if by == plate.y else -3)), 1)
        return
    jag = [(cx + r * math.cos(k * math.pi / 4) * (1.0 if k % 2 else .55),
            cy + r * math.sin(k * math.pi / 4) * (1.0 if k % 2 else .55)) for k in range(8)]
    pygame.draw.polygon(s, KEEL, jag)
    pygame.draw.polygon(s, config.COLOR_DANGER, jag, 1)


def _flames(layer, bounds, fire, seed) -> None:
    """Glow, a few flickering flame tongues and smoke under the deckhead."""
    w, h = bounds.size
    fire = max(0.0, min(1.0, fire))
    cx, base = w // 2, h - 2
    for step in range(4, 0, -1):
        alpha = min(220, round(40 + 150 * fire * (5 - step) / 4))
        pygame.draw.ellipse(layer, (255, 110 + 20 * step, 50, alpha),
                            (cx - w * step // 8, h // 2 - h * step // 8,
                             w * step // 4, h * step // 4))
    t = _phase()
    count = 2 + round(5 * fire)
    for k in range(count):
        fx = w * (k + .5) / count
        flicker = .65 + .35 * math.sin(t * 7.0 + seed * 1.7 + k * 2.3)
        fh = h * (.25 + .45 * fire) * flicker
        fw = max(3.0, w / count * .4)
        pygame.draw.polygon(layer, (255, 140 + (k * 37) % 60, 40, 170),
                            [(fx - fw, base), (fx, base - fh), (fx + fw, base)])
    smoke_h = max(2, round(h * (.15 + .25 * fire)))
    layer.fill((*SMOKE, round(90 + 80 * fire)), (0, 0, w, smoke_h),
               special_flags=pygame.BLEND_RGBA_MAX)


def _water(layer, bounds, level_left, level_right) -> None:
    """Floodwater below a line from ``level_left`` to ``level_right`` (screen y)."""
    w, h = bounds.size
    t = _phase()
    top = []
    for step in range(9):
        x = w * step / 8
        y = (level_left + (level_right - level_left) * step / 8 - bounds.y
             + 1.2 * math.sin(t * 2.2 + step * .9))
        top.append((x, y))
    pygame.draw.polygon(layer, (*console.WATER, 175), top + [(w, h + 2), (0, h + 2)])
    pygame.draw.lines(layer, (*WATER_TOP, 255), False, top, 2)


def _hatching(layer, bounds) -> None:
    w, h = bounds.size
    for x in range(-h, w, 9):
        pygame.draw.line(layer, (*config.COLOR_DANGER, 200), (x, h), (x + h, 0), 1)


def _inflow(damage, key) -> float:
    rate = getattr(damage, "inflow_pct_s", None)
    return float(rate(key)) if rate is not None else 0.0


def draw_frigate_profile(s, rect, damage, selected=None) -> dict:
    """The side profile with sea, rooms, water, fire, holes, pumps and teams.

    Returns the screen polygons of the profile rooms.
    """
    rect = pygame.Rect(rect)
    profile = Profile(rect)
    draft = float(getattr(damage, "draft_m", 7.5))
    trim = float(damage.trim_deg())
    tan_trim = math.tan(math.radians(trim))
    # Sea under the waterline, then the ship over it.
    left, right = FRIGATE["x_range"]
    sea = [profile.point(left, _waterline_z(left, draft, trim)),
           profile.point(right, _waterline_z(right, draft, trim))]
    old_clip = s.get_clip()
    s.set_clip(rect.clip(old_clip) if old_clip else rect)
    pygame.draw.polygon(s, SEA, sea + [(rect.right, rect.bottom), (rect.x, rect.bottom)])
    s.blit(_cached(("profile", rect.size), lambda: _static_profile(rect)), rect.topleft)
    lines.line(s, SEA_LINE, sea[0], sea[1], 1)
    s.set_clip(old_clip)
    polygons = {}
    rooms = damage.compartments
    for index, (key, coords) in enumerate(FRIGATE["rooms"].items()):
        c = rooms.get(key)
        if c is None:
            continue
        polygon = profile.points(coords)
        polygons[key] = polygon
        pygame.draw.polygon(s, ROOM_FILL, polygon)
        xs = [x for x, _ in coords]
        x_lo, x_hi, xc = min(xs), max(xs), sum(xs) / len(xs)
        flood = max(0.0, min(100.0, float(c.flood))) / 100.0
        fire = max(0.0, min(100.0, float(c.fire))) / 100.0
        lost = c.state == "ZERSTOERT"
        if flood or fire or lost:
            floor, top = min(z for _, z in coords), max(z for _, z in coords)
            level = floor + flood * (top - floor)

            def paint(layer, bounds, flood=flood, fire=fire, lost=lost, level=level,
                      x_lo=x_lo, x_hi=x_hi, xc=xc, seed=index):
                if fire:
                    _flames(layer, bounds, fire, seed)
                if flood:
                    _water(layer, bounds,
                           profile.point(x_lo, level + (x_lo - xc) * tan_trim)[1],
                           profile.point(x_hi, level + (x_hi - xc) * tan_trim)[1])
                if lost:
                    _hatching(layer, bounds)

            masked(s, polygon, paint)
        border = (config.COLOR_TEXT if key == selected else
                  config.COLOR_DANGER if (fire or lost) else
                  config.COLOR_WARN if flood else (40, 110, 100))
        lines.lines(s, border, True, polygon, 3 if key == selected else 1)
        number = list(rooms).index(key) + 1
        box = pygame.Rect(min(p[0] for p in polygon) + 3, min(p[1] for p in polygon) + 1,
                          max(8, max(p[0] for p in polygon) - min(p[0] for p in polygon) - 6),
                          layout.line_pitch(13, 0))
        layout.blit_line(s, raw_text(f"{number:02}"), box,
                         border if border != (40, 110, 100) else config.COLOR_TEXT_DIM, size=13)
        _draw_leak(s, profile, damage, key, c, coords, draft)
        teams = damage.teams_on(key)
        if teams:
            floor = min(z for _, z in coords)
            fx, fy = profile.point(xc, floor)
            console.badges(s, fx, fy - 24, teams)
            if flood:
                deck = max(z for _, z in coords)
                sx, sy = profile.point(xc, max(deck, 10.0))
                _jet(s, (sx, sy - 2), (sx + 3 * profile.scale, sy - profile.scale),
                     2.5 * profile.scale)
    return polygons


def _draw_leak(s, view, damage, key, c, coords, draft) -> None:
    hole = float(getattr(c, "hole_m2", 0.0))
    if hole <= 0.0 or c.state == "ZERSTOERT":
        return
    ys = [z for _, z in coords]
    xs = [x for x, _ in coords]
    floor, top = min(ys), max(ys)
    z = floor + .3 * max(.6, min(top, draft) - floor)
    x = sum(xs) / len(xs)
    reference = math.sqrt(hole / max(1e-6, _reference_hole()))
    radius = max(3.0, min(1.6, .6 * reference) * view.scale)
    centre = view.point(x, z) if isinstance(view, Profile) else view.point(x, z)
    _hole(s, centre, radius, c.state != "FLUTEND")
    inflow = _inflow(damage, key)
    if inflow > 0.0:
        strength = view.scale * min(5.0, 1.5 + 6.0 * math.sqrt(inflow / max(1e-6, config.DMG_FLOOD_RATE)))
        _jet(s, centre, (centre[0] + strength, centre[1] - strength * .4), strength)


def _reference_hole() -> float:
    from src.ship.damage import HIT_HOLE_M2
    return HIT_HOLE_M2


def draw_frigate_section(s, rect, damage, selected=None) -> dict:
    """The listing cross-section with both hull voids; returns their polygons."""
    rect = pygame.Rect(rect)
    draft = float(getattr(damage, "draft_m", 7.5))
    heel = float(damage.list_deg())
    view = Section(rect, heel, draft)
    old_clip = s.get_clip()
    s.set_clip(rect.clip(old_clip) if old_clip else rect)
    pygame.draw.rect(s, SEA, (rect.x, view.py, rect.w, rect.bottom - view.py))
    shell = view.points(FRIGATE["section"]["shell"])
    pygame.draw.polygon(s, HULL_FILL, shell)
    lines.line(s, SEA_LINE, (rect.x, view.py), (rect.right, view.py), 1)
    for z in (2.5, 6.0):
        lines.line(s, STEEL_DIM, view.point(-8.3, z), view.point(8.3, z), 1)
    polygons = {}
    for key, coords in FRIGATE["section"]["rooms"].items():
        c = damage.compartments.get(key)
        if c is None:
            continue
        polygon = view.points(coords)
        polygons[key] = polygon
        pygame.draw.polygon(s, ROOM_FILL, polygon)
        flood = max(0.0, min(100.0, float(c.flood))) / 100.0
        lost = c.state == "ZERSTOERT"
        if flood or lost:
            yc = sum(y for y, _ in coords) / len(coords)
            floor, top = min(z for _, z in coords), max(z for _, z in coords)
            level_y = view.point(yc, floor + flood * (top - floor))[1]

            def paint(layer, bounds, flood=flood, lost=lost, level_y=level_y):
                if flood:
                    _water(layer, bounds, level_y, level_y)
                if lost:
                    _hatching(layer, bounds)

            masked(s, polygon, paint)
        border = (config.COLOR_TEXT if key == selected else
                  config.COLOR_DANGER if lost else
                  config.COLOR_WARN if flood else (40, 110, 100))
        lines.lines(s, border, True, polygon, 3 if key == selected else 1)
        hole = float(getattr(c, "hole_m2", 0.0))
        if hole > 0.0 and not lost:
            side = -1.0 if key == "hull_left" else 1.0
            centre = view.point(8.3 * side, 2.4)
            _hole(s, centre, max(3.0, .5 * view.scale), c.state != "FLUTEND")
            if _inflow(damage, key) > 0.0:
                inner = view.point(5.8 * side, 2.8)
                _jet(s, centre, inner, abs(inner[0] - centre[0]))
        teams = damage.teams_on(key)
        if teams:
            tx, ty = view.point(sum(y for y, _ in coords) / len(coords), 6.5)
            console.badges(s, tx, ty - 22, teams)
    lines.lines(s, STEEL, False, shell, 2)
    lines.line(s, STEEL, view.point(-8.3, 10.4), view.point(8.3, 10.4), 2)
    # Plumb line against the ship's centre line shows the list.
    top = (view.cx, rect.y + 4)
    lines.line(s, STEEL_DIM, top, (view.cx, view.py), 1)
    lines.line(s, config.COLOR_WARN if abs(heel) >= 5.0 else STEEL,
               view.point(0.0, 12.5), view.point(0.0, 0.0), 1)
    s.set_clip(old_clip)
    return polygons


# --- submarine section -------------------------------------------------------

def boat_cells(rect) -> tuple:
    """Outer hull, pressure hull, conning tower and the six cells (stern left).

    Proportions follow a classic cutaway drawing: a long free-flooding casing
    with a flat deck, the pressure hull tapering to both ends inside it, the
    tower amidships with periscopes and snorkel, keel tanks below.
    """
    rect = pygame.Rect(rect)
    if rect.h > rect.w * .3:                       # keep the boat's proportions
        height = max(1, round(rect.w * .3))
        rect = pygame.Rect(rect.x, rect.y + (rect.h - height) // 2, rect.w, height)
    tower_h = max(12, rect.h // 4)
    body = pygame.Rect(rect.x + 2, rect.y + tower_h, rect.w - 4, rect.h - tower_h)
    deck_y = body.y + max(3, body.h // 9)
    keel_y = body.bottom - max(3, body.h // 10)
    outer = ((body.x, deck_y + (keel_y - deck_y) * 2 // 5),          # stern tip
             (body.x + body.w * .05, deck_y), (body.x + body.w * .84, deck_y),
             (body.right - body.w * .03, body.y + 1), (body.right, body.y + 2),
             (body.right - body.w * .02, deck_y + (keel_y - deck_y) // 2),
             (body.right - body.w * .07, keel_y), (body.x + body.w * .12, keel_y),
             (body.x + body.w * .04, deck_y + (keel_y - deck_y) * 3 // 4))
    hull = pygame.Rect(round(body.x + body.w * .07), deck_y + max(3, body.h // 12),
                       round(body.w * .82), 0)
    hull.h = keel_y - max(4, body.h // 7) - hull.y
    taper = max(6, hull.w // 14)
    pressure = ((hull.x, hull.y + hull.h * .3), (hull.x + taper, hull.y),
                (hull.right - taper, hull.y), (hull.right, hull.y + hull.h * .3),
                (hull.right, hull.bottom - hull.h * .3), (hull.right - taper, hull.bottom),
                (hull.x + taper, hull.bottom), (hull.x, hull.bottom - hull.h * .3))
    tower_x = hull.x + round(hull.w * .5)
    tower = ((tower_x - tower_h * 1.6, deck_y), (tower_x - tower_h * 1.2, rect.y + tower_h * .35),
             (tower_x + tower_h * 1.0, rect.y + tower_h * .35), (tower_x + tower_h * 1.5, deck_y))
    cells = []
    x = float(hull.x)
    for share in BOAT["share"]:
        right = x + hull.w * share
        cells.append(pygame.Rect(round(x), hull.y, round(right) - round(x), hull.h))
        x = right
    return hull, outer, tower, cells, pressure


# Muted tints per compartment, after the coloured cutaway drawings.
BOAT_TINTS = {"stern": (92, 86, 40), "engine": (96, 70, 36), "battery": (90, 46, 44),
              "quarters": (46, 84, 52), "control": (64, 66, 104), "bow": (96, 54, 48)}


def _static_boat(size) -> pygame.Surface:
    rect = pygame.Rect((0, 0), size)
    hull, outer, tower, cells, pressure = boat_cells(rect)
    surface = hires.surface(size, pygame.SRCALPHA)
    pygame.draw.polygon(surface, HULL_FILL, outer)
    pygame.draw.polygon(surface, HULL_FILL, tower)
    lines.lines(surface, STEEL, True, outer, 1)
    lines.lines(surface, STEEL, False, tower, 1)
    deck_y = outer[1][1]
    # Deck rail, keel tank and the masts on the tower: two periscopes,
    # snorkel and the direction-finder loop.
    lines.line(surface, STEEL_DIM, (outer[1][0], deck_y + 2), (outer[2][0], deck_y + 2), 1)
    keel = pygame.Rect(cells[2].x, hull.bottom + 2, cells[3].right - cells[2].x,
                       max(2, outer[6][1] - hull.bottom - 3))
    pygame.draw.rect(surface, KEEL, keel)
    lines.lines(surface, STEEL_DIM, True, (keel.topleft, keel.topright,
                                           keel.bottomright, keel.bottomleft), 1)
    top = tower[1][1]
    span = tower[2][0] - tower[1][0]
    for share, height in ((.25, 1.0), (.45, .8), (.7, .6)):
        mx = round(tower[1][0] + span * share)
        lines.line(surface, STEEL, (mx, top), (mx, rect.y + round((top - rect.y) * (1 - height))), 2)
    loop = (round(tower[1][0] + span * .9), max(rect.y + 3, top - 4))
    pygame.draw.circle(surface, STEEL_DIM, loop, 3, 1)
    # Rudder, propeller and bow planes.
    stern = outer[0]
    lines.line(surface, STEEL, (stern[0] + 2, stern[1] - 6), (stern[0] + 2, stern[1] + 6), 2)
    pygame.draw.circle(surface, STEEL_DIM, (stern[0] + 7, stern[1] + 3), 3, 1)
    bow_plane = (outer[5][0] - 10, outer[5][1] + 2)
    lines.line(surface, STEEL, bow_plane, (bow_plane[0] + 8, bow_plane[1] + 3), 2)
    # The pressure hull with its compartments and their fittings.
    pygame.draw.polygon(surface, ROOM_FILL, pressure)
    tint = hires.surface(size, pygame.SRCALPHA)
    for name, cell in zip(BOAT["order"], cells):
        tint.fill((*BOAT_TINTS[name], 150), cell)
    mask = hires.surface(size, pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), pressure)
    tint.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(tint, (0, 0))
    stern_room, engine, battery, quarters, control, bow = cells
    floor = hull.bottom - hull.h // 3              # deck plates over the bilge
    lines.line(surface, STEEL_DIM, (hull.x + 4, floor), (hull.right - 4, floor), 1)
    ink = INK
    for room in (stern_room, bow):                  # torpedo tubes
        tube_h = max(2, hull.h // 9)
        for k in (0, 1):
            y = hull.centery - tube_h - 1 + k * (tube_h + 2)
            x0 = room.x + (4 if room is bow else 0)
            pygame.draw.rect(surface, (60, 96, 140), (x0 + (room.w // 3 if room is bow else 2), y,
                                                     room.w * 2 // 3 - 4, tube_h))
    lines.line(surface, ink, (stern_room.x + stern_room.w // 2, floor),
               (stern_room.x + stern_room.w // 2, hull.y + 2), 1)
    for k in range(2):                              # diesels
        block = pygame.Rect(engine.x + 4 + k * engine.w // 2, floor - engine.h // 3,
                            engine.w // 2 - 8, engine.h // 3)
        pygame.draw.rect(surface, (120, 94, 52), block, 0, 2)
        pygame.draw.rect(surface, ink, block, 1, 2)
        for c in range(3):
            cx = block.x + (c + 1) * block.w // 4
            lines.line(surface, ink, (cx, block.y - 2), (cx, block.y + 2), 1)
    for room in (battery, quarters):                # battery cells under the deck
        cell_w = max(3, (room.w - 6) // 7)
        for k in range(7):
            pygame.draw.rect(surface, (110, 96, 70), (room.x + 3 + k * cell_w, floor + 2,
                                                      cell_w - 1, max(2, hull.bottom - floor - 5)), 1)
    for k in range(1, 3):                           # bunks
        y = quarters.y + (floor - quarters.y) * k // 3
        lines.line(surface, ink, (quarters.x + 4, y), (quarters.right - 4, y), 1)
    for share in (.35, .6):                         # periscope wells, chart table
        x = control.x + round(control.w * share)
        lines.line(surface, ink, (x, hull.y + 1), (x, floor), 1)
    pygame.draw.rect(surface, ink, (control.x + 3, floor - control.h // 5, control.w // 4, control.h // 5), 1)
    lines.lines(surface, STEEL, True, pressure, 2)
    return surface


def boat_mask(size) -> pygame.Surface:
    rect = pygame.Rect((0, 0), size)
    pressure = boat_cells(rect)[4]
    mask = hires.surface(size, pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), pressure)
    return mask


def draw_boat_section(s, rect, control, capacity, trim_deg=0.0, selected=None) -> list:
    """The boat in section; returns the six cell rects in the damage model's
    order (``COMPARTMENTS``: bow first)."""
    rect = pygame.Rect(rect)
    hull, _outer, _tower, cells, pressure = boat_cells(rect)
    s.blit(_cached(("boat", rect.size), lambda: _static_boat(rect.size)), rect.topleft)
    order = BOAT["order"]
    model_order = ["bow", "control", "quarters", "battery", "engine", "stern"]
    tan_trim = math.tan(math.radians(max(-20.0, min(20.0, float(trim_deg))))) * 1.5
    layer = hires.surface(rect.size, pygame.SRCALPHA)
    t = _phase()
    for name, cell in zip(order, cells):
        index = model_order.index(name)
        c = control.compartments[index]
        box = cell.move(-rect.x, -rect.y)
        fraction = max(0.0, min(1.0, c.water_kg / max(1.0, capacity(index))))
        if c.fire > 0.0:
            _flames(layer.subsurface(box), box, min(1.0, c.fire), index)
        if c.chlorine > 0.0:
            haze = min(1.0, c.chlorine)
            for k in range(6):
                px = box.x + box.w * ((k * .37 + t * .03) % 1.0)
                py = box.y + box.h * (.2 + .25 * ((k * .61) % 1.0))
                pygame.draw.circle(layer, (*GAS, round(40 + 50 * haze)), (round(px), round(py)),
                                   max(4, box.h // 5))
        if fraction > 0.0:
            level = box.bottom - box.h * fraction
            top = []
            for step in range(7):
                x = box.x + box.w * step / 6
                y = (level - (x - box.centerx) * tan_trim
                     + 1.0 * math.sin(t * 2.0 + step + index))
                top.append((x, y))
            pygame.draw.polygon(layer, (*console.WATER, 190),
                                top + [(box.right, box.bottom + 2), (box.x, box.bottom + 2)])
            pygame.draw.lines(layer, (*WATER_TOP, 255), False, top, 2)
        if control.down(name):
            _hatching(layer.subsurface(box), box)
    layer.blit(_cached(("boat_mask", rect.size), lambda: boat_mask(rect.size)), (0, 0),
               special_flags=pygame.BLEND_RGBA_MIN)
    s.blit(layer, rect.topleft)
    rects = [None] * len(model_order)
    for position, (name, cell) in enumerate(zip(order, cells)):
        index = model_order.index(name)
        c = control.compartments[index]
        rects[index] = cell
        if position:
            lines.line(s, STEEL, (cell.x, cell.y + 1), (cell.x, cell.bottom - 1), 2)
        if c.leak > 0.0:
            centre = (cell.centerx, cell.bottom - 2)
            _hole(s, centre, 3 + 3 * min(1.0, c.leak), False)
            _jet(s, centre, (centre[0] + cell.w // 5, centre[1] - cell.h // 2),
                 max(6.0, cell.h * .4 * min(1.5, .5 + c.leak)))
        if selected == index:
            pygame.draw.rect(s, config.COLOR_TEXT, cell, 2)
    # Round bulkhead doors: shut when either side has closed its bulkheads.
    radius = max(4, hull.h // 8)
    for position in range(1, len(cells)):
        a = control.compartments[model_order.index(order[position - 1])]
        b = control.compartments[model_order.index(order[position])]
        x, y = cells[position].x, hull.centery - hull.h // 8
        shut = a.closed or b.closed
        pygame.draw.circle(s, DOOR_FILL, (x, y), radius)
        pygame.draw.circle(s, config.COLOR_OK if shut else STEEL_DIM, (x, y), radius, 2)
        if shut:
            lines.line(s, config.COLOR_OK, (x - radius + 2, y), (x + radius - 2, y), 2)
            lines.line(s, config.COLOR_OK, (x, y - radius + 2), (x, y + radius - 2), 2)
    return rects
