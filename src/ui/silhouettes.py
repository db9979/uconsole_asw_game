"""Procedural side views of the coarse contact classes.

One profile per class the eye can make out (``warship``, ``merchant``,
``unknown``, ``aircraft``) plus the ``submarine`` of the start screen.  A
profile is a set of polygons in hull units: ``u`` runs from the bow (0) to
the stern (1) and ``v`` is the height above the waterline, both as a
fraction of the drawn length.  Everything is display only: the animation
phase comes from the caller's clock and nothing here reads an entity or
changes simulation state.
"""

import math

import pygame

# Bow wave, wake and rotor wash: the colour of broken water.
FOAM = (215, 225, 225)
# Below this drawn length the details merge into the fill.
DETAIL_MIN_PX = 40


def _sub_hull(samples: int = 64) -> list:
    """Round bow, parallel midbody and a tapering stern (Type 212 style)."""
    radius = 0.056
    top, bottom = [], []
    for i in range(samples + 1):
        u = i / samples
        if u < 0.12:
            r = radius * math.sqrt(max(0.0, 1.0 - ((0.12 - u) / 0.12) ** 2))
        elif u > 0.68:
            r = radius * (1.0 - 0.82 * ((u - 0.68) / 0.32) ** 1.5)
        else:
            r = radius
        top.append((u, r))
        bottom.append((u, -r))
    return top + bottom[::-1]


# Frigate F-217 (enclosed mast, raked funnel, hangar and flight deck).
_WARSHIP = {
    "hull": [(0.0, 0.052), (0.035, 0.0), (0.985, 0.0), (1.0, 0.034),
             (0.80, 0.036), (0.45, 0.040), (0.15, 0.046)],
    "blocks": [
        [(0.10, 0.046), (0.115, 0.062), (0.155, 0.062), (0.16, 0.045)],      # gun
        [(0.18, 0.045), (0.18, 0.056), (0.235, 0.056), (0.235, 0.044)],      # VLS
        [(0.245, 0.044), (0.265, 0.090), (0.285, 0.105), (0.42, 0.105),
         (0.42, 0.043)],                                                     # bridge
        [(0.30, 0.105), (0.325, 0.19), (0.355, 0.19), (0.38, 0.105)],        # mast
        [(0.336, 0.19), (0.338, 0.25), (0.342, 0.25), (0.344, 0.19)],        # pole
        [(0.42, 0.043), (0.42, 0.085), (0.60, 0.085), (0.62, 0.043)],        # midship
        [(0.47, 0.085), (0.48, 0.135), (0.545, 0.14), (0.55, 0.085)],        # funnel
        [(0.585, 0.085), (0.595, 0.16), (0.605, 0.16), (0.61, 0.085)],       # aft mast
        [(0.597, 0.16), (0.598, 0.19), (0.602, 0.19), (0.603, 0.16)],
        [(0.62, 0.040), (0.62, 0.082), (0.76, 0.082), (0.78, 0.038)],        # hangar
        [(0.44, 0.041), (0.445, 0.052), (0.49, 0.052), (0.495, 0.041)],      # RHIB
        [(0.69, 0.082), (0.692, 0.094), (0.708, 0.094), (0.71, 0.082)],      # CIWS
    ],
    "lines": [((0.112, 0.056), (0.05, 0.062)),                               # gun barrel
              ((0.005, 0.052), (0.0, 0.074)), ((0.995, 0.034), (1.0, 0.056)),  # staffs
              ((0.322, 0.215), (0.358, 0.215)),                              # yard
              ((0.66, 0.082), (0.655, 0.12)), ((0.75, 0.082), (0.756, 0.115)),  # whips
              ((0.79, 0.037), (0.97, 0.035))],                               # deck edge
    "windows": [(0.275 + i * 0.012, 0.094) for i in range(6)],
    "panels": [[(0.325, 0.150), (0.33, 0.172), (0.35, 0.172), (0.355, 0.150)]],
    "radar": (0.34, 0.24, 0.024),
    "funnel_top": (0.51, 0.14),
    "masthead": (0.34, 0.252),
    # Navigation lights: both masthead lights on the enclosed mast (warships
    # may deviate from the spacing, rule 1e), side lights on the bridge.
    "nav": {"mast": [(0.30, 0.20), (0.34, 0.26)], "side": (0.27, 0.10),
            "stern": (0.995, 0.040), "round": (0.34, 0.215)},
    "pitch_deg": 0.8, "pitch_hz": 0.11, "wake": True,
}

_MERCHANT = {
    "hull": [(0.0, 0.07), (0.04, 0.0), (0.97, 0.0), (1.0, 0.055),
             (0.30, 0.055), (0.06, 0.065)],
    "blocks": [
        [(0.02, 0.065), (0.02, 0.078), (0.08, 0.078), (0.09, 0.06)],         # forecastle
        [(0.10, 0.055), (0.10, 0.105), (0.20, 0.105), (0.20, 0.055)],        # containers
        [(0.21, 0.055), (0.21, 0.115), (0.33, 0.115), (0.33, 0.055)],
        [(0.34, 0.055), (0.34, 0.110), (0.46, 0.110), (0.46, 0.055)],
        [(0.47, 0.055), (0.47, 0.120), (0.60, 0.120), (0.60, 0.055)],
        [(0.61, 0.055), (0.61, 0.105), (0.74, 0.105), (0.74, 0.055)],
        [(0.78, 0.055), (0.78, 0.170), (0.88, 0.170), (0.89, 0.055)],        # house
        [(0.765, 0.163), (0.765, 0.170), (0.895, 0.170), (0.895, 0.163)],    # wings
        [(0.885, 0.120), (0.89, 0.190), (0.935, 0.190), (0.94, 0.120)],      # funnel
        [(0.058, 0.07), (0.059, 0.14), (0.063, 0.14), (0.064, 0.07)],        # fore mast
    ],
    "lines": [((0.10 + i * 0.043, 0.058), (0.10 + i * 0.043, 0.103)) for i in range(15)],
    "windows": [(0.79 + i * 0.013, 0.155) for i in range(7)],
    "panels": [],
    "funnel_top": (0.91, 0.19),
    "masthead": (0.061, 0.142),
    # Navigation lights: masthead lights (forward, aft and higher), side
    # lights on the bridge wings, stern light.
    "nav": {"mast": [(0.061, 0.150), (0.80, 0.215)], "side": (0.77, 0.166),
            "stern": (0.995, 0.062), "round": (0.84, 0.25)},
    "pitch_deg": 0.5, "pitch_hz": 0.07, "wake": True,
}

# Trawler or small craft: high bow, wheelhouse forward, gantry aft.
_UNKNOWN = {
    "hull": [(0.0, 0.10), (0.06, 0.0), (0.95, 0.0), (1.0, 0.07),
             (0.40, 0.07), (0.10, 0.085)],
    "blocks": [
        [(0.18, 0.083), (0.20, 0.20), (0.38, 0.20), (0.40, 0.076)],          # wheelhouse
        [(0.295, 0.20), (0.297, 0.36), (0.303, 0.36), (0.305, 0.20)],        # mast
        [(0.40, 0.074), (0.40, 0.12), (0.55, 0.12), (0.55, 0.072)],          # casing
    ],
    "lines": [((0.83, 0.07), (0.89, 0.24)), ((0.95, 0.07), (0.89, 0.24)),
              ((0.26, 0.30), (0.34, 0.30))],
    "windows": [(0.22 + i * 0.03, 0.17) for i in range(5)],
    "panels": [],
    "masthead": (0.30, 0.365),
    "nav": {"mast": [(0.30, 0.37), (0.89, 0.45)], "side": (0.20, 0.19),
            "stern": (0.99, 0.075), "round": (0.30, 0.37)},
    "pitch_deg": 1.6, "pitch_hz": 0.19, "wake": True,
}

# Helicopter, nose to the left; ``v`` includes its hover height.
_AIRCRAFT = {
    "hull": [(0.0, 0.52), (0.05, 0.57), (0.18, 0.61), (0.45, 0.61), (0.55, 0.57),
             (0.95, 0.565), (1.0, 0.60), (1.0, 0.55), (0.55, 0.535), (0.42, 0.50),
             (0.10, 0.495)],
    "blocks": [[(0.28, 0.61), (0.29, 0.635), (0.33, 0.635), (0.34, 0.61)]],  # rotor head
    "lines": [((0.12, 0.47), (0.42, 0.47)), ((0.18, 0.47), (0.18, 0.50)),
              ((0.36, 0.47), (0.36, 0.50))],
    "windows": [(0.05 + i * 0.035, 0.56) for i in range(3)],
    "panels": [],
    "rotor": (0.31, 0.64, 0.48),
    "tail_rotor": (0.985, 0.58, 0.06),
    "masthead": (0.30, 0.47),
    # Position lights on the cabin sides, tail light, anti-collision beacons
    # on top and underneath, strobe on the tail fin.
    "nav": {"mast": [], "side": (0.20, 0.555), "stern": (0.995, 0.585),
            "beacon": [(0.36, 0.615), (0.30, 0.49)], "strobe": (0.975, 0.60)},
    "hover": True, "pitch_deg": 2.0, "pitch_hz": 0.23, "wake": False,
}

_SUBMARINE = {
    "hull": _sub_hull(),
    "blocks": [[(0.215, 0.05), (0.222, 0.118), (0.236, 0.132), (0.33, 0.132),
                (0.335, 0.05)]],                                             # sail
    "lines": [((0.205, 0.100), (0.262, 0.100)),                              # sail planes
              ((0.92, 0.012), (0.985, 0.075)), ((0.92, -0.012), (0.985, -0.075)),
              ((0.27, 0.132), (0.27, 0.16))],                                # retracted mast
    "windows": [],
    "panels": [],
    "propeller": (1.0, 0.0, 0.05),
    "pitch_deg": 0.3, "pitch_hz": 0.05, "wake": False,
}

PROFILES = {"warship": _WARSHIP, "merchant": _MERCHANT, "unknown": _UNKNOWN,
            "aircraft": _AIRCRAFT, "submarine": _SUBMARINE}
# Height of the aircraft's body in its profile (centred on its elevation).
AIRCRAFT_CENTRE_V = 0.555
# Silhouette height over apparent length (highest point), per class.
HEIGHT_RATIO = {name: max(v for poly in [p["hull"], *p["blocks"]] for _u, v in poly)
                for name, p in PROFILES.items()}


class _Frame:
    """Maps hull units to pixels: length, facing, pitch and heave."""

    def __init__(self, left: float, base_y: float, width: float, facing: int,
                 pitch_rad: float, lift: float = 0.0):
        self.left, self.base_y, self.width = left, base_y - lift, width
        self.facing = -1 if facing < 0 else 1
        self.cos, self.sin = math.cos(pitch_rad), math.sin(pitch_rad)

    def point(self, u: float, v: float) -> tuple:
        # Rotate about midships on the waterline; bow down for positive pitch.
        du, dv = u - 0.5, v
        ru = du * self.cos - dv * self.sin
        rv = du * self.sin + dv * self.cos
        if self.facing > 0:
            ru = -ru
        return (self.left + (0.5 + ru) * self.width, self.base_y - rv * self.width)

    def poly(self, points) -> list:
        return [self.point(u, v) for u, v in points]


def _pitch(profile: dict, t: float) -> float:
    return math.radians(profile["pitch_deg"]) * math.sin(
        2.0 * math.pi * profile["pitch_hz"] * t)


def frame_for(cls: str, cx: float, base_y: float, width: float, t: float = 0.0,
              facing: int = -1, aloft: bool = False) -> _Frame:
    """The pixel frame a profile is drawn in (also for anchoring effects);
    ``aloft`` centres an aircraft's body on ``base_y`` instead of hovering
    it over the horizon."""
    profile = PROFILES.get(cls, _UNKNOWN)
    lift = 0.0
    if aloft:
        lift = -AIRCRAFT_CENTRE_V * width
    elif profile.get("hover"):
        lift = width * (0.25 + 0.02 * math.sin(t * 1.3))
    return _Frame(cx - width / 2.0, base_y, width, facing, _pitch(profile, t), lift)


def draw_wake(s, frame: _Frame, width: float, t: float) -> None:
    """Bow wave and a dashed wake along the waterline, moving aft."""
    fwd = frame.facing  # +1: bow to the right
    bx, by = frame.point(0.03, 0.0)
    for i in range(3):
        phase = (t * 1.7 + i * 0.33) % 1.0
        reach = width * (0.01 + 0.035 * phase)
        rise = width * 0.018 * (1.0 - phase)
        pygame.draw.line(s, FOAM, (bx + fwd * reach * 0.3, by),
                         (bx + fwd * reach, by - rise), 1)
    sx, sy = frame.point(1.0, 0.0)
    step = max(3.0, width * 0.04)
    offset = (t * 18.0) % (2 * step)
    for k in range(6):
        start = offset + k * 2 * step
        if start > width * 0.35:
            break
        x0 = sx - fwd * start
        pygame.draw.line(s, FOAM, (x0, sy), (x0 - fwd * step * 0.8, sy), 1)


def _draw_rotor(s, frame: _Frame, profile: dict, color, t: float) -> None:
    hu, hv, half = profile["rotor"]
    blade = abs(math.cos(t * 23.0))
    left = frame.point(hu - half * blade, hv)
    right = frame.point(hu + half * blade, hv)
    pygame.draw.line(s, color, left, right, 2)
    disc_l, disc_r = frame.point(hu - half, hv), frame.point(hu + half, hv)
    pygame.draw.line(s, color, disc_l, disc_r, 1)
    tu, tv, tr = profile["tail_rotor"]
    angle = t * 31.0
    c = frame.point(tu, tv)
    r = tr * frame.width
    pygame.draw.line(s, color, (c[0] - r * math.cos(angle), c[1] - r * math.sin(angle)),
                     (c[0] + r * math.cos(angle), c[1] + r * math.sin(angle)), 1)


# Navigation light colours: white masthead/stern, red port, green starboard.
NAV_LIGHT = {"white": (255, 246, 222), "red": (255, 74, 58), "green": (96, 255, 150)}


def anti_collision(t: float) -> tuple:
    """(beacon on, strobe on) at display time ``t``: a red beacon flash
    every second, a white strobe double flash every 1.2 seconds."""
    beacon = (t % 1.0) < 0.12
    phase = t % 1.2
    return beacon, phase < 0.06 or 0.18 <= phase < 0.24


def draw_nav_lights(s, cls: str, frame: _Frame, width: float, code: str,
                    t: float = 0.0, nav_points: dict | None = None) -> None:
    """The ``nav_lights`` code as points of light with a soft glow; drawn at
    any size, since at night the lights are what the eye picks up first.
    ``nav_points``: the light positions of a type's own model instead of the
    class profile's."""
    nav = nav_points or PROFILES.get(cls, _MERCHANT).get("nav") or _MERCHANT["nav"]
    masts, red, green, stern = int(code[1]), code[2] == "r", code[3] == "g", code[4] == "s"
    round_lights = code[5:]
    nav = nav if round_lights != "AC" else PROFILES["aircraft"]["nav"]
    core = max(1, min(3, int(width / 150)))
    # A trawler's single masthead light stands abaft and above her green.
    mast = nav["mast"][1:] if round_lights == "GW" else nav["mast"]
    points = [(mast[i], "white") for i in range(masts)]
    su, sv = nav["side"]
    if red and green:           # head on: both side lights, just apart
        points += [((su - 0.004, sv), "red"), ((su + 0.004, sv), "green")]
    elif red:
        points.append(((su, sv), "red"))
    elif green:
        points.append(((su, sv), "green"))
    if stern:
        points.append((nav["stern"], "white"))
    spots = [(frame.point(u, v), name) for (u, v), name in points]
    if round_lights == "AC":
        beacon, strobe = anti_collision(t)
        if beacon:
            spots += [(frame.point(u, v), "red") for u, v in nav["beacon"]]
        if strobe:
            spots.append((frame.point(*nav["strobe"]), "white"))
    elif round_lights:
        # All-round lights in a vertical line down the mast, at least a
        # glow apart (mine clearance: one at the masthead, one each yardarm).
        x, y = frame.point(*nav["round"])
        step = max(core * 2 + 3, width * 0.02)
        names = {"W": "white", "R": "red", "G": "green"}
        if round_lights == "GGG":
            spots += [((x, y - step), "green"), ((x - step, y), "green"),
                      ((x + step, y), "green")]
        else:
            spots += [((x, y - step * (len(round_lights) - i)), names[letter])
                      for i, letter in enumerate(round_lights)]
    for (x, y), name in spots:
        color = NAV_LIGHT[name]
        glow = tuple(int(c * 0.45) for c in color)
        pygame.draw.circle(s, glow, (int(x), int(y)), core + 2)
        pygame.draw.circle(s, color, (int(x), int(y)), core)


def draw_bubble_track(s, cx: float, base_y: float, width: float, t: float = 0.0) -> None:
    """The bubble track of a running torpedo on the sea: a pale streak with
    bubbles breaking along it (display clock ``t``)."""
    width = max(3.0, float(width))
    left = cx - width / 2.0
    pygame.draw.line(s, FOAM, (left, base_y + 1), (left + width, base_y + 1),
                     max(1, min(3, int(width // 40) + 1)))
    count = max(3, min(18, int(width / 8)))
    for k in range(count):
        phase = (t * 0.7 + k * 0.618) % 1.0
        x = left + width * ((k + 0.5) / count)
        radius = max(1, int(1 + 2 * math.sin(math.pi * phase)))
        pygame.draw.circle(s, FOAM, (int(x), int(base_y + 1)), radius, 1)


def draw_profile(s, cls: str, cx: float, base_y: float, width: float, color, *,
                 t: float = 0.0, facing: int = -1, rim=None, lights=None,
                 wake: bool = True, nav: str | None = None, aloft: bool = False) -> _Frame:
    """Draw ``cls`` ``width`` px long on the waterline ``base_y`` (``aloft``:
    an aircraft centred on ``base_y``).

    ``t`` animates pitch, radar, rotors and the wake; ``rim`` outlines the
    polygons (moonlit edges) and ``lights`` colours bridge windows, both only
    when the silhouette is large enough to show them; ``nav`` is a
    ``nav_lights`` code of the navigation lights shown.  Returns the frame.
    """
    profile = PROFILES.get(cls, _UNKNOWN)
    width = max(3.0, float(width))
    frame = frame_for(cls, cx, base_y, width, t, facing, aloft)
    detail = width >= DETAIL_MIN_PX
    polys = [frame.poly(profile["hull"])]
    polys += [frame.poly(block) for block in profile["blocks"]]
    for poly in polys:
        pygame.draw.polygon(s, color, poly)
    line_w = max(1, int(width / 260))
    for a, b in profile["lines"]:
        pygame.draw.line(s, color if rim is None or not detail else rim,
                         frame.point(*a), frame.point(*b), line_w)
    if "rotor" in profile:
        _draw_rotor(s, frame, profile, color if rim is None else rim, t)
    if "radar" in profile and detail:
        ru, rv, half = profile["radar"]
        span = half * abs(math.cos(t * 2.6))
        pygame.draw.line(s, color if rim is None else rim, frame.point(ru - span, rv),
                         frame.point(ru + span, rv), max(1, int(width / 200)))
    if "propeller" in profile:
        pu, pv, half = profile["propeller"]
        blade = half * abs(math.sin(t * 9.0))
        pygame.draw.line(s, color if rim is None else rim, frame.point(pu, pv - blade),
                         frame.point(pu, pv + blade), max(1, int(width / 150)))
    if detail and rim is not None:
        for poly in polys:
            pygame.draw.lines(s, rim, True, poly, 1)
        for poly in profile["panels"]:
            pygame.draw.polygon(s, rim, frame.poly(poly))
    if detail and lights is not None:
        size = max(1, int(width / 180))
        for u, v in profile["windows"]:
            x, y = frame.point(u, v)
            pygame.draw.rect(s, lights, (int(x), int(y), size + 1, size))
    if wake and profile.get("wake") and detail:
        draw_wake(s, frame, width, t)
    if nav is not None:
        draw_nav_lights(s, cls, frame, width, nav, t)
    return frame
