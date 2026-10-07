"""The start screen's look for the eyepieces: periscope and binoculars.

``sky_values`` turns the observed atmosphere and the game clock into a small
detached dict (light, dusk glow, cloud, precipitation, sun and moon) that the
uConsole and the browser draw alike.  ``draw_scene`` paints the sky with its
stars, moon or sun and clouds, the sea with moving wave rows and the glitter
under the moon or sun, and ``draw_weather`` the rain, snow or fog in front of
everything.  All of it is cosmetic: positions of stars and clouds are fixed
in bearing space, the animation phase is the caller's clock, and nothing here
reads an entity or changes the simulation.
"""

from collections import OrderedDict
import math
import random

import pygame

from src.core import config
from src.ui import hires

# Sky and sea (top, horizon) per light; night is the start screen's palette.
SKY_NIGHT = ((3, 7, 16), (20, 44, 62))
SKY_DAY = ((34, 88, 118), (138, 176, 182))
SKY_DUSK = ((24, 30, 60), (204, 128, 78))
SEA_NIGHT = ((10, 44, 58), (2, 9, 15))
SEA_DAY = ((24, 78, 92), (6, 34, 46))
SEA_DUSK = ((44, 50, 66), (8, 14, 26))
OVERCAST_DAY, OVERCAST_NIGHT = (108, 120, 126), (18, 24, 30)
HAZE_DAY, HAZE_NIGHT = (150, 160, 165), (34, 44, 50)
WAVE_NIGHT, WAVE_DAY = (22, 70, 80), (58, 112, 122)
CREST_NIGHT, CREST_DAY = (96, 150, 156), (186, 212, 214)
MOON = (214, 222, 206)
MOON_DARK = (26, 34, 42)
SUN_DAY, SUN_DUSK = (255, 244, 210), (255, 178, 96)
# Silhouettes in steel with a lit rim (start screen), windows lit at night.
STEEL_NIGHT, STEEL_DAY = (19, 36, 46), (44, 56, 64)
RIM_NIGHT, RIM_DAY = (84, 150, 158), (170, 196, 200)
WINDOW_LIGHT = (250, 205, 120)
FRAME = (40, 96, 90)
BRACKET = 18
# The weather instrument's wind arrow.
WIND_ARROW = (120, 214, 180)
# Sky field in bearing space (cosmetic, fixed seed like the start screen).
STAR_COUNT = 220
CLOUD_COUNT = 26
RAIN_MAX, SNOW_MAX = 70, 60
# The sun and moon run 45 degrees high at their culmination; on screen the
# altitude is compressed into the sky of the eyepiece.
BODY_MAX_ALT_DEG = 45.0
LUNAR_MONTH_D = 29.530588
_CACHE_MAX = 8
_SKY_CACHE = OrderedDict()
_SHADE_CACHE = OrderedDict()
_MASK_CACHE = OrderedDict()
# The eyepiece's rim: binoculars show two overlapping round fields, the
# periscope a rounded field; the edge falls off over this share of the height.
EYEPIECE_KINDS = ("binoculars", "scope")
EYEPIECE_SOFT = 0.07
EYEPIECE_RIM = (4, 10, 14)
_FIELD = {}


def _clamp(value, low=0.0, high=1.0):
    return config.clamp(value, low, high)


def _smooth(value):
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def blend(a, b, t: float) -> tuple:
    t = _clamp(t)
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _pair(pairs, light, dusk):
    night, day, glow = pairs
    return tuple(blend(blend(n, d, light), g, dusk * 0.7) for n, d, g in zip(night, day, glow))


def daylight(hour: float) -> tuple:
    """(light 0..1, dusk glow 0..1) of the game clock: full day inside the
    daylight window, a one-hour ramp across either edge (``is_night`` flips
    at the edge itself)."""
    hour = hour % 24.0
    ramp = config.DUSK_HALF_WIDTH_H
    morning = (hour - (config.DAYLIGHT_START_H - ramp)) / (2.0 * ramp)
    evening = ((config.DAYLIGHT_END_H + ramp) - hour) / (2.0 * ramp)
    light = _smooth(min(morning, evening))
    dusk = max(0.0, 1.0 - abs(2.0 * light - 1.0) * 1.15)
    return light, dusk


def _body(hour: float) -> tuple:
    """(true bearing, altitude deg) of a body that rises at the start of the
    daylight window in the east and sets at its end in the west."""
    span = config.DAYLIGHT_END_H - config.DAYLIGHT_START_H
    phase = ((hour - config.DAYLIGHT_START_H) % 24.0) / span
    bearing = (90.0 + 180.0 * phase) % 360.0
    altitude = BODY_MAX_ALT_DEG * math.sin(math.pi * phase) if phase <= 1.0 else \
        -BODY_MAX_ALT_DEG * math.sin(math.pi * (phase - 1.0) * span / (24.0 - span))
    return bearing, altitude


def sky_values(hour: float, lunar_age_days: float, moon_illumination: float,
               cloud_cover: float, precipitation: str, rain_intensity: float,
               wind_from_deg: float, glow: float = 0.0, storm: float = 0.0,
               lightning=None) -> dict:
    """The sky of the eyepieces from observed values only (detached)."""
    light, dusk = daylight(hour)
    sun_bearing, sun_alt = _body(hour)
    # The moon trails the sun by its age: new moon rises with the sun, full
    # moon at sunset.
    moon_bearing, moon_alt = _body(hour - 24.0 * (lunar_age_days % LUNAR_MONTH_D)
                                   / LUNAR_MONTH_D)
    kind = precipitation if precipitation in ("rain", "snow") else "none"
    return dict(light=round(light, 4), dusk=round(dusk, 4),
                cloud=round(_clamp(cloud_cover), 4), precipitation=kind,
                intensity=round(_clamp(rain_intensity) if kind != "none" else 0.0, 4),
                wind_from_deg=round(wind_from_deg % 360.0, 2),
                sun_bearing=round(sun_bearing, 2), sun_alt_deg=round(sun_alt, 2),
                moon_bearing=round(moon_bearing, 2), moon_alt_deg=round(moon_alt, 2),
                moon_illumination=round(_clamp(moon_illumination), 4),
                moon_waxing=bool((lunar_age_days % LUNAR_MONTH_D) < LUNAR_MONTH_D / 2.0),
                # Bioluminescence at night: stirred water (wakes, torpedo
                # tracks) glows blue-green (``src/physics/bioluminescence.py``).
                glow=round(_clamp(glow), 4),
                # Thunderstorm (``src/world/thunder.py``): activity 0..1 makes
                # the rain heavier; a strike lights the picture at its bearing.
                storm=round(_clamp(storm), 4),
                lightning=round(_clamp(lightning[0]), 4) if lightning else 0.0,
                lightning_bearing=round(lightning[1] % 360.0, 2) if lightning else 0.0)


def sky_state(game) -> dict:
    """``sky_values`` of the game's own atmosphere (observation-safe)."""
    atmosphere = game.atmosphere()
    return sky_values(game.world.hour, game.lunar_age_days(),
                      atmosphere["moon_illumination"], atmosphere["cloud_cover"],
                      atmosphere["precipitation"], atmosphere["rain_intensity"],
                      atmosphere["wind_from_deg"], game.world.glow(),
                      game.world.thunderstorm(), game.world.lightning(game.sim_t))


def plain_sky(night: bool) -> dict:
    """A clear sky at noon or midnight (callers without an atmosphere)."""
    return sky_values(1.0 if night else 12.0, 0.0, 0.0, 0.0, "none", 0.0, 0.0)


def palette(sky: dict, haze: float) -> dict:
    """Colours of one picture: sky, sea, haze and the silhouettes' steel."""
    light, dusk, cloud = sky["light"], sky["dusk"], sky["cloud"]
    haze_color = blend(HAZE_NIGHT, HAZE_DAY, light)
    overcast = blend(OVERCAST_NIGHT, OVERCAST_DAY, light)
    grey = max(0.0, cloud - 0.5) * 1.2
    sky_top, sky_bottom = (blend(blend(c, overcast, grey * 0.8), haze_color, haze * 0.7)
                           for c in _pair((SKY_NIGHT, SKY_DAY, SKY_DUSK), light,
                                          dusk * (1.0 - grey)))
    sea_top, sea_deep = (blend(blend(c, overcast, grey * 0.3), haze_color, haze * 0.35)
                         for c in _pair((SEA_NIGHT, SEA_DAY, SEA_DUSK), light, dusk))
    return dict(sky=(sky_top, sky_bottom), sea=(sea_top, sea_deep), haze=haze_color,
                wave=blend(blend(WAVE_NIGHT, WAVE_DAY, light), haze_color, haze * 0.5),
                crest=blend(blend(CREST_NIGHT, CREST_DAY, light), haze_color, haze * 0.5),
                steel=blend(STEEL_NIGHT, STEEL_DAY, light),
                rim=blend(blend(RIM_NIGHT, RIM_DAY, light), SUN_DUSK, dusk * 0.5),
                cloud=blend(blend((26, 36, 46), (196, 204, 208), light),
                            (196, 130, 96), dusk * 0.6),
                cloud_rim=blend(blend((70, 96, 108), (238, 242, 242), light),
                                (250, 190, 130), dusk * 0.7),
                # Glowing plankton in stirred water (night bloom, 0..1).
                glow=float(sky.get("glow", 0.0)) * (1.0 - haze * 0.6))


def _cached(cache, key, build):
    key = (key, hires.SCALE)
    surf = cache.get(key)
    if surf is None:
        surf = build()
        cache[key] = surf
        while len(cache) > _CACHE_MAX:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    return surf


def _eyepiece_mask(size, kind: str) -> pygame.Surface:
    import numpy as np
    w, h = max(2, int(size[0])), max(2, int(size[1]))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((*EYEPIECE_RIM, 0))
    xs = np.arange(w, dtype=np.float32)[:, None] + 0.5
    ys = np.arange(h, dtype=np.float32)[None, :] + 0.5
    if kind == "binoculars":
        r = h / 2.0
        centers = (min(w / 2.0, r), max(w / 2.0, w - r))
        d = np.minimum(np.hypot(xs - centers[0], ys - h / 2.0),
                       np.hypot(xs - centers[1], ys - h / 2.0)) / r
    else:
        # A rounded field (superellipse) that keeps the whole width.
        u = np.abs(xs - w / 2.0) / (w / 2.0)
        v = np.abs(ys - h / 2.0) / (h / 2.0)
        d = (u ** 6 + v ** 6) ** (1.0 / 6.0)
    soft = EYEPIECE_SOFT * h / (h / 2.0)
    alpha = np.clip((d - (1.0 - soft)) / soft, 0.0, 1.0) * 255.0
    pygame.surfarray.pixels_alpha(surf)[:, :] = alpha.astype(np.uint8)
    return hires.to_factor(surf, hires.SCALE)


def eyepiece_mask(size, kind: str) -> pygame.Surface:
    """The cached rim over an eyepiece picture of ``size``."""
    return _cached(_MASK_CACHE, (tuple(size), kind), lambda: _eyepiece_mask(size, kind))


def _gradient(size, top, bottom) -> pygame.Surface:
    w, h = size
    surf = hires.surface((max(1, w), max(1, h)))
    for y in range(max(1, h)):
        pygame.draw.line(surf, blend(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return surf


def _shade(size, color) -> pygame.Surface:
    """Transparent at the top, ``color`` at the bottom (the deep sea)."""
    w, h = size
    surf = hires.surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    for y in range(max(1, h)):
        alpha = int(235 * (y / max(1, h - 1)) ** 0.8)
        pygame.draw.line(surf, (*color, alpha), (0, y), (w, y))
    return surf


def _field() -> dict:
    """Stars and clouds in bearing space, built once (fixed seed)."""
    if not _FIELD:
        rng = random.Random(217)
        _FIELD["stars"] = [(rng.uniform(0, 360), rng.random() ** 0.8, rng.uniform(0, math.tau),
                            rng.uniform(0.6, 2.2), rng.random() < 0.12)
                           for _ in range(STAR_COUNT)]
        _FIELD["clouds"] = [(rng.uniform(0, 360), rng.uniform(0.25, 0.95),
                             rng.uniform(6, 22), rng.uniform(0.05, 0.12), rng.random())
                            for _ in range(CLOUD_COUNT)]
    return _FIELD


def _wrap(bearing: float, line_of_sight: float) -> float:
    return (bearing - line_of_sight + 180.0) % 360.0 - 180.0


class View:
    """Geometry of one eyepiece picture (screen px per degree, horizon)."""

    def __init__(self, rect, line_of_sight, fov_deg, horizon, tilt, lift=0.0):
        self.rect = pygame.Rect(rect)
        self.los, self.fov = line_of_sight, fov_deg
        self.px_per_deg = self.rect.w / fov_deg
        self.horizon, self.tilt = horizon, tilt
        # The sky (stars, sun, moon, clouds) hangs on the eyepiece's nominal
        # horizon, not on the one rolling with the sea: it stays still.
        self.sky_h = max(8, self.rect.h // 2)
        # Tilting the optics up moves the sky and the horizon down.
        self.lift = float(lift)

    def x(self, bearing: float) -> float:
        return self.rect.centerx + _wrap(bearing, self.los) * self.px_per_deg

    def base(self, x: float) -> float:
        return self.horizon + math.tan(self.tilt) * (x - self.rect.centerx)

    def visible(self, bearing: float, half_deg: float = 0.0) -> bool:
        return abs(_wrap(bearing, self.los)) <= self.fov / 2.0 + half_deg

    def alt_y(self, fraction: float, x: float) -> float:
        """Height ``fraction`` (0 horizon .. 1 top) of the eyepiece's sky."""
        return self.rect.y + self.rect.h / 2.0 + self.lift - fraction * self.sky_h


def _body_fraction(alt_deg: float) -> float:
    return 0.12 + 0.7 * _clamp(alt_deg / BODY_MAX_ALT_DEG)


def _draw_stars(s, view, sky, colors, t, haze):
    strength = (1.0 - sky["light"] * 1.8) * (1.0 - sky["cloud"]) * (1.0 - haze)
    if strength <= 0.05:
        return
    for bearing, alt, phase, speed, bright in _field()["stars"]:
        if not view.visible(bearing):
            continue
        x = view.x(bearing)
        y = view.alt_y(0.08 + 0.92 * alt, x)
        if y < view.rect.y + 2:
            continue
        glow = (0.55 + 0.45 * math.sin(t * speed + phase)) * strength
        level = int(((150 if bright else 90) * glow) + 30 * strength)
        color = blend(colors["sky"][0], (level + 40, level + 40, min(255, level + 70)), strength)
        if bright:
            pygame.draw.circle(s, color, (int(x), int(y)), 1)
        else:
            s.set_at((int(x), int(y)), color)


def _draw_body(s, view, sky, colors, haze):
    """The moon (night) or the sun (day and dusk) where the eye looks."""
    light = sky["light"]
    moon = light < 0.6 and sky["moon_alt_deg"] > 0.0 and sky["moon_illumination"] > 0.03
    sun = light > 0.05 and sky["sun_alt_deg"] > -1.0
    cover = 1.0 - _clamp((sky["cloud"] - 0.6) * 2.5)
    radius = max(4, int(0.55 * view.px_per_deg))
    if sun and view.visible(sky["sun_bearing"], 2.0) and cover > 0.05:
        x = view.x(sky["sun_bearing"])
        y = view.alt_y(_body_fraction(sky["sun_alt_deg"]), x)
        color = blend(blend(SUN_DAY, SUN_DUSK, sky["dusk"]), colors["sky"][1], 1.0 - cover)
        for r, k in ((radius * 3, 0.85), (radius * 2, 0.7)):
            pygame.draw.circle(s, blend(color, colors["sky"][1], k), (int(x), int(y)), r)
        pygame.draw.circle(s, color, (int(x), int(y)), radius)
    if moon and view.visible(sky["moon_bearing"], 2.0) and cover > 0.05:
        x = view.x(sky["moon_bearing"])
        y = view.alt_y(_body_fraction(sky["moon_alt_deg"]), x)
        lit = blend(MOON, colors["sky"][1], (1.0 - cover) + haze * 0.5)
        dark = blend(MOON_DARK, colors["sky"][1], 0.3)
        for r, k in ((radius * 4, 0.9), (radius * 3, 0.82), (radius * 2, 0.7)):
            pygame.draw.circle(s, blend(lit, colors["sky"][1], k), (int(x), int(y)), r)
        pygame.draw.circle(s, lit, (int(x), int(y)), radius)
        # Phase: the terminator as a shifted dark disc.
        illumination = sky["moon_illumination"]
        if illumination < 0.97:
            side = -1 if sky["moon_waxing"] else 1
            shift = int(side * 2 * radius * illumination)
            with_clip = s.get_clip()
            s.set_clip(with_clip.clip((x - radius, y - radius, 2 * radius + 1, 2 * radius + 1)))
            pygame.draw.circle(s, dark, (int(x) + shift, int(y)), radius)
            s.set_clip(with_clip)
        if radius >= 6 and illumination > 0.3:
            pygame.draw.circle(s, blend(lit, dark, 0.2), (int(x) + radius // 3, int(y) + radius // 5),
                               max(1, radius // 4))


def _draw_clouds(s, view, sky, colors, t, haze):
    cover = sky["cloud"]
    if cover <= 0.2 or haze > 0.85:
        return
    count = int(CLOUD_COUNT * _clamp((cover - 0.15) / 0.85))
    drift = t * 0.05 * (1.0 if math.sin(math.radians(sky["wind_from_deg"] - view.los)) > 0 else -1.0)
    base = blend(colors["cloud"], colors["haze"], haze * 0.6)
    rim = blend(colors["cloud_rim"], colors["haze"], haze * 0.6)
    moonlit = sky["light"] > 0.3 or (sky["moon_alt_deg"] > 0 and sky["moon_illumination"] > 0.3)
    for index, (bearing, alt, width_deg, height, shade) in enumerate(_field()["clouds"][:count]):
        bearing = bearing + drift
        if not view.visible(bearing, width_deg):
            continue
        x = view.x(bearing)
        y = view.alt_y(alt, x)
        w = width_deg * view.px_per_deg
        h = max(4, height * view.sky_h * 1.6)
        color = blend(base, colors["sky"][0], 0.25 * shade)
        for k, (dx, dy, fw, fh) in enumerate(((0, 0, 1.0, 0.6), (-0.25, -0.25, 0.5, 0.6),
                                              (0.2, -0.3, 0.45, 0.7), (0.3, 0.05, 0.5, 0.5))):
            ex, ey = x + dx * w, y + dy * h
            rect = pygame.Rect(int(ex - fw * w / 2), int(ey - fh * h / 2),
                               max(2, int(fw * w)), max(2, int(fh * h)))
            if moonlit and k:
                pygame.draw.ellipse(s, rim, rect.move(0, -1))
            pygame.draw.ellipse(s, color, rect)


def sea_aspect(wind_from_deg: float, line_of_sight: float) -> tuple:
    """(head, cross) of the sea as seen: the waves run from where the wind
    blows.  ``head`` is 1 looking into the sea (crests come at the eye), -1
    looking down-sea (their backs run away), ``cross`` is +1 when they run
    from left to right across the picture."""
    angle = math.radians(wind_from_deg - line_of_sight)
    return math.cos(angle), -math.sin(angle)


# Rows of waves between the horizon and the bottom of a picture.
SEA_ROWS = 18
# Own way through the water: rows per second and knot coming at the eye when
# looking ahead, and the sideways stream (per knot) when looking abeam.
WAY_ROWS_PER_KN = 0.04
WAY_SIDE_PER_KN = 0.15
# Where the frigate's bow and stern lie from the bridge lookout (m), her
# beam, and the half angle of her Kelvin wake.
OWN_BOW_M = 40.0
OWN_STERN_M = 100.0
OWN_BEAM_M = 17.0
KELVIN_DEG = 19.47
WAKE_FOAM = 48
# The blue-green light of stirred plankton (bioluminescence).
GLOW = (70, 235, 205)
BOW_SPRAY = 28
_FLOW = OrderedDict()


def flow(key, t: float, rates: tuple) -> tuple:
    """Display-only integral of ``rates`` over the display clock ``t``, so a
    change of speed or line of sight bends the motion instead of making the
    pattern jump; after a gap (or at first sight) ``rate * t``."""
    state = _FLOW.get(key)
    if state is None or not 0.0 <= t - state[0] <= 2.0:
        values = tuple(rate * t for rate in rates)
    else:
        values = tuple(value + rate * (t - state[0]) for value, rate in zip(state[1], rates))
    _FLOW[key] = (t, values)
    _FLOW.move_to_end(key)
    while len(_FLOW) > _CACHE_MAX:
        _FLOW.popitem(last=False)
    return values


def waterline_drop_deg(distance_m: float, eye_m: float) -> float:
    """How far below the sea horizon the eye sees a point on the water
    ``distance_m`` away, degrees (0 at and beyond the horizon): close
    aboard the water lies well below the horizon line."""
    below = math.degrees(math.atan2(eye_m, max(1.0, distance_m))
                         - math.sqrt(2.0 * eye_m / 7.3e6))
    return max(0.0, below)


def _sea_y(view, bearing: float, distance_m: float, eye_m: float) -> float:
    """Picture row of a point on the sea ``distance_m`` from the eye."""
    return view.base(view.x(bearing)) + waterline_drop_deg(distance_m, eye_m) * view.px_per_deg


def _sea_point(view, bearing: float, distance_m: float, eye_m: float) -> tuple:
    return (view.x(bearing), _sea_y(view, bearing, distance_m, eye_m))


def _offset_point(view, course: float, ahead_m: float, side_m: float, eye_m: float) -> tuple:
    """A point ``ahead_m`` forward and ``side_m`` to starboard of the eye."""
    bearing = course + math.degrees(math.atan2(side_m, ahead_m))
    return _sea_point(view, bearing, math.hypot(ahead_m, side_m), eye_m)


def _draw_way(s, view, colors, way, t, haze):
    """Bow wave and wake of the own ship, in true perspective from the eye:
    the bow wave curls out from the bow (tilt down to see it), the wake runs
    astern as a band of churned water to the horizon between the two arms of
    the Kelvin wave."""
    speed = float(way.get("speed_kn") or 0.0)
    if speed < 1.0 or not way.get("hull", True):
        return
    course = float(way["course_deg"])
    eye = float(way.get("eye_m", 18.0))
    strength = _clamp(speed / 20.0) * (1.0 - haze * 0.7)
    foam = blend(colors["sea"][0], colors["crest"], 0.35 + 0.55 * strength)
    glow = colors.get("glow", 0.0) * strength
    if glow > 0.0:
        foam = blend(foam, GLOW, 0.85 * glow)
    rect = view.rect
    stern = (course + 180.0) % 360.0
    # The wake: a band of smoother, lighter churned water behind the stern,
    # ragged at its edges, with foam drifting away astern; it fades out
    # toward the horizon.
    if view.visible(stern, 40.0):
        length = 150.0 + speed * 120.0
        steps = 16
        previous = None
        edges = ([], [])
        for i in range(steps + 1):
            along = length * (i / steps) ** 1.6
            d = OWN_STERN_M + along
            rag = 1.0 + 0.05 * math.sin(along * 0.03 + t * 1.3)
            half = (OWN_BEAM_M / 2.0 + along * 0.02) * rag
            edge = math.degrees(math.atan2(half, d))
            left = _sea_point(view, stern - edge, d, eye)
            right = _sea_point(view, stern + edge, d, eye)
            edges[0].append(left)
            edges[1].append(right)
            if previous is not None:
                calm = blend(colors["sea"][0], colors["wave"],
                             (0.04 + 0.1 * strength) * (1.0 - i / steps))
                pygame.draw.polygon(s, calm, [previous[0], previous[1], right, left])
            previous = (left, right)
        rim = blend(colors["sea"][0], colors["crest"], 0.15 + 0.3 * strength)
        if glow > 0.0:
            rim = blend(rim, GLOW, 0.6 * glow)
        for line in edges:
            pygame.draw.lines(s, rim, False, line, 1)
        for k in range(WAKE_FOAM):
            phase = (t * (0.05 + speed * 0.006) + k * 0.382) % 1.0
            along = length * phase ** 1.6
            d = OWN_STERN_M + along
            lateral = (((k * k * 0.618 + k * 0.29) % 1.0) - 0.5) * (OWN_BEAM_M + along * 0.04)
            bearing = stern + math.degrees(math.atan2(lateral, d))
            x, y = _sea_point(view, bearing, d, eye)
            half = max(1.0, view.px_per_deg * math.degrees(math.atan2(3.0, d)))
            pygame.draw.line(s, blend(foam, colors["sea"][0], 0.2 + 0.8 * phase),
                             (x - half, y), (x + half, y), 1)
    # The Kelvin arms from the stern out to the horizon.
    for side in (-1.0, 1.0):
        points = []
        for i in range(1, 16):
            run = 20.0 * 1.45 ** i
            ahead = -(OWN_STERN_M + run * math.cos(math.radians(KELVIN_DEG)))
            lateral = side * (OWN_BEAM_M / 2.0 + run * math.sin(math.radians(KELVIN_DEG)))
            bearing = course + math.degrees(math.atan2(lateral, ahead))
            if view.visible(bearing, 2.0):
                points.append(_sea_point(view, bearing, math.hypot(ahead, lateral), eye))
        if len(points) >= 2:
            pygame.draw.lines(s, blend(colors["crest"], colors["sea"][0], 0.5 - 0.3 * strength),
                              False, points, 1)
    # Below the picture's lower edge the bow wave still throws its spray up
    # into it: white water running out to both sides from the stem.
    if _sea_y(view, course, OWN_BOW_M, eye) > rect.bottom and view.visible(course, 30.0):
        band = rect.h * (0.08 + 0.14 * strength)
        grow = rect.w / 400.0
        spread = min(26.0, 0.45 * view.fov)
        for k in range(BOW_SPRAY):
            side = -1.0 if k % 2 else 1.0
            phase = (t * (0.3 + speed * 0.025) + k * 0.382) % 1.0
            lift = math.sin(math.pi * phase) * (0.4 + 0.6 * ((k * k * 0.618) % 1.0))
            x = view.x(course + side * (0.5 + spread * phase))
            y = rect.bottom - band * lift
            half = (3.0 + 8.0 * strength * (1.0 - phase)) * grow
            pygame.draw.line(s, blend(colors["crest"], colors["sea"][0], 0.15 + 0.7 * phase),
                             (x - half, y), (x + half, y), 2 if strength > 0.5 else 1)
    # The bow wave: white water curling out from both sides of the bow and
    # running aft along the hull.
    for side in (-1.0, 1.0):
        points = []
        for i in range(12):
            run = OWN_BOW_M * 1.6 * i / 11
            ahead = OWN_BOW_M - run * math.cos(math.radians(28.0))
            lateral = side * (1.0 + run * math.sin(math.radians(28.0)))
            curl = 0.6 * speed / 10.0 * math.sin(t * 3.1 + i * 0.9 + side)
            if not view.visible(course + math.degrees(math.atan2(lateral, ahead)), 4.0):
                continue
            x, y = _offset_point(view, course, ahead, lateral + curl, eye)
            if y <= rect.bottom + 40:
                points.append((x, y))
        if len(points) >= 2:
            width = max(1, min(4, int(1 + strength * rect.h / 160.0)))
            pygame.draw.lines(s, blend(foam, colors["crest"], strength), False, points, width)


def _draw_sea(s, view, sky, colors, sea_state, t, haze, way=None):
    """The sea as a field of wave rows in perspective: at the horizon a
    fine, nearly flat line of small crests, toward the eye ever longer and
    higher waves, all moving with the swell (bearing space, so the field
    slides past as the line of sight turns)."""
    rect = view.rect
    dy = math.tan(view.tilt) * rect.w / 2.0
    left, right = view.horizon - dy, view.horizon + dy
    step = max(4, rect.w // 90)
    head, cross = sea_aspect(sky["wind_from_deg"], view.los)
    along = abs(head)
    anchor = view.los * view.px_per_deg
    # Far off the waves are too small to break the horizon: a clean line.
    crest = [(x, view.base(x)) for x in range(rect.x, rect.right + step, step)]
    pygame.draw.polygon(s, colors["sea"][0], crest + [(rect.right, rect.bottom),
                                                       (rect.x, rect.bottom)])
    top = int(min(left, right) + 2)
    depth = rect.bottom - top
    if depth > 4:
        shade = _cached(_SHADE_CACHE, (rect.w, depth, colors["sea"][1]),
                        lambda: _shade((rect.w, depth), colors["sea"][1]))
        s.blit(shade, (rect.x, top))
    below = max(1.0, rect.bottom - view.horizon)
    # Near waves: height and length grow with the sea state and the picture.
    near_amp = (1.2 + 0.9 * sea_state) * rect.h / 280.0
    # Into or down the sea the rows come at the eye or run away from it
    # (new rows are born at the horizon); across it they run sideways.  The
    # own way adds the water streaming past: toward the eye looking ahead,
    # away looking astern, from bow to stern looking abeam.
    speed = float(way.get("speed_kn") or 0.0) if way else 0.0
    rel = math.radians(view.los - float(way["course_deg"])) if way else 0.0
    cycles, side = flow(("sea", tuple(rect)), t, (
        0.35 * head + WAY_ROWS_PER_KN * speed * math.cos(rel),
        cross + WAY_SIDE_PER_KN * speed * math.sin(rel)))
    roll = cycles % 1.0
    born = math.floor(cycles)
    trough = blend(colors["sea"][0], colors["sea"][1], 0.45)
    for index in range(SEA_ROWS + 1):
        f = (index + roll) / SEA_ROWS
        if f > 1.0:
            continue
        depth_px = below * f ** 1.9
        if depth_px < 1.0:
            continue
        near = depth_px / below
        n = index - born                      # the row's own identity
        amp = max(0.35, near_amp * near)
        wavelength = (10.0 + 150.0 * near) * (0.45 + 0.9 * along)
        k = math.tau / wavelength
        drift = side * (4.0 + 40.0 * near)
        phase = n * 1.7 + t * 1.4 * (1.0 - along)
        points = []
        for x in range(rect.x - step, rect.right + step, step):
            u = (x + anchor - drift) * k + phase
            points.append((x, view.base(x) + depth_px
                           - amp * (math.sin(u) + 0.35 * math.sin(2.1 * u + n))))
        fade = f * 0.9
        light = blend(blend(colors["sea"][0], colors["wave"], 0.35 + 0.65 * near),
                      colors["haze"], haze * (1.0 - near) * 0.6)
        # Down-sea the eye sees the waves' backs: fainter rows.
        if head < 0:
            light = blend(light, colors["sea"][1], 0.35 * -head)
        width = 2 if near > 0.55 and rect.h >= 200 else 1
        if near > 0.12:
            pygame.draw.lines(s, blend(trough, colors["sea"][1], fade),
                              False, [(x, y + max(1.0, amp * 0.8)) for x, y in points], width)
        pygame.draw.lines(s, light, False, points, width)
        if sea_state >= 4 and near > 0.08:
            # White caps on the highest crests.
            cap = colors["crest"]
            for i in range(1, len(points) - 1):
                if (points[i][1] < points[i - 1][1] and points[i][1] <= points[i + 1][1]
                        and (i * 7 + n * 3) % max(2, 9 - int(sea_state)) == 0):
                    x, y = points[i]
                    half = max(1.0, wavelength * 0.08)
                    pygame.draw.line(s, cap, (x - half, y), (x + half, y), width)
    pygame.draw.lines(s, blend(colors["crest"], colors["haze"], 0.4), False, crest, 1)
    if way:
        _draw_way(s, view, colors, way, t, haze)
    # Glitter under the moon or the sun.
    light = sky["light"]
    if light < 0.5 and sky["moon_alt_deg"] > 0:
        strength, bearing = sky["moon_illumination"] * (1 - light * 2), sky["moon_bearing"]
        glint = (150, 170, 170)
    elif light >= 0.5 and sky["sun_alt_deg"] > -1:
        strength, bearing = 0.8, sky["sun_bearing"]
        glint = blend((226, 236, 236), SUN_DUSK, sky["dusk"])
    else:
        strength = 0.0
    strength *= (1.0 - _clamp((sky["cloud"] - 0.5) * 2.0)) * (1.0 - haze)
    if strength > 0.1 and view.visible(bearing, 6.0):
        cx = view.x(bearing)
        for i in range(14):
            shimmer = math.sin(t * 2.4 + i * 1.7)
            if shimmer < -0.2:
                continue
            y = view.base(cx) + 4 + i * i * 0.9
            if y > rect.bottom:
                break
            half = (4 + i * 2.5 * (0.5 + 0.5 * shimmer)) * (rect.w / 600.0 + 0.4)
            pygame.draw.line(s, blend(colors["sea"][0], glint, strength),
                             (cx - half, y), (cx + half, y), 1)


def draw_scene(s, view: View, sky: dict, *, visibility_nm: float, sea_state: float,
               t: float, aloft=None, way=None) -> dict:
    """Sky, stars, moon or sun, clouds and sea of one picture; returns its
    palette for the land and the silhouettes.  ``aloft(colors)`` draws what
    flies behind the clouds (aircraft); ``way`` (``speed_kn``, ``course_deg``,
    optional ``eye_m`` and ``hull``) is the own way through the water."""
    haze = 1.0 - _clamp(visibility_nm / config.WEATHER_VISIBILITY_MAX_NM)
    colors = palette(sky, haze)
    colors["haze_level"] = haze
    rect = view.rect
    sky_img = _cached(_SKY_CACHE, (rect.w, rect.h, colors["sky"]),
                      lambda: _gradient((rect.w, rect.h), *colors["sky"]))
    # The sky stays still: its gradient meets the nominal horizon (moved by
    # the optics' elevation); above it the zenith colour.
    top = int(rect.y + view.sky_h + 40 + view.lift - rect.h)
    if top > rect.y:
        s.fill(colors["sky"][0], (rect.x, rect.y, rect.w, top - rect.y))
    s.blit(sky_img, (rect.x, top))
    _draw_stars(s, view, sky, colors, t, haze)
    _draw_body(s, view, sky, colors, haze)
    if aloft is not None:
        aloft(colors)
    _draw_clouds(s, view, sky, colors, t, haze)
    _draw_sea(s, view, sky, colors, sea_state, t, haze, way)
    colors["haze_level"] = haze
    return colors


def draw_weather(s, view: View, sky: dict, colors: dict, *, visibility_nm: float,
                 t: float) -> None:
    """Rain streaks, snow flakes and a fog bank in front of the picture."""
    rect = view.rect
    haze = colors["haze_level"]
    if visibility_nm < 3.0:
        band = int(rect.h * (0.1 + 0.25 * (1.0 - visibility_nm / 3.0)))
        fog = _cached(_SHADE_CACHE, ("fog", rect.w, band, colors["haze"]),
                      lambda: _fog(rect.w, band, colors["haze"]))
        s.blit(fog, (rect.x, int(view.horizon - band / 2)))
    draw_lightning(s, view, sky)
    kind, intensity = sky["precipitation"], sky["intensity"]
    if kind == "none" or intensity <= 0.0:
        return
    # A thunderstorm pours: up to 60 % more streaks.
    intensity = intensity * (1.0 + 0.6 * sky.get("storm", 0.0))
    lateral = math.sin(math.radians(sky["wind_from_deg"] - view.los + 180.0))
    color = blend(blend((70, 96, 104), (196, 208, 212), sky["light"]), colors["haze"], haze * 0.3)
    if kind == "rain":
        count = int(RAIN_MAX * intensity)
        length = 10 + 10 * intensity
        for i in range(count):
            x = rect.x + (i * 97 + t * 40 * lateral) % rect.w
            y = rect.y + (i * 53 + t * 420) % rect.h
            pygame.draw.line(s, color, (x, y), (x + lateral * length * 0.4, y + length), 1)
    else:
        count = int(SNOW_MAX * intensity)
        for i in range(count):
            x = rect.x + (i * 97 + 13 * math.sin(t * 0.7 + i) + t * 22 * lateral) % rect.w
            y = rect.y + (i * 53 + t * (26 + i % 5 * 6)) % rect.h
            pygame.draw.circle(s, color, (int(x), int(y)), 1 + (i % 3 == 0))


LIGHTNING = (200, 196, 255)
BOLT = (238, 236, 255)


def draw_lightning(s, view: View, sky: dict) -> None:
    """A strike: the picture flashes pale violet, and a bolt forks down to
    the horizon when its bearing lies in the field of view."""
    level = sky.get("lightning", 0.0)
    if level <= 0.02:
        return
    rect = view.rect
    lift = int(70 * level)
    s.fill((lift, lift, int(lift * 1.15)), rect, special_flags=pygame.BLEND_RGB_ADD)
    bearing = sky.get("lightning_bearing", 0.0)
    if not view.visible(bearing):
        return
    x = view.x(bearing)
    y, bottom = float(rect.y), view.base(x)
    seed = int(bearing * 100.0)
    points = [(x, y)]
    step = max(6.0, (bottom - y) / 9.0)
    index = 0
    while y < bottom:
        index += 1
        y = min(bottom, y + step)
        x += ((seed * (index * 7 + 3)) % 23 - 11) * rect.w / 1200.0
        points.append((x, y))
    width = 2 if level > 0.5 else 1
    pygame.draw.lines(s, blend(LIGHTNING, BOLT, level), False, points, width)
    if len(points) > 4:
        fork = points[3]
        pygame.draw.line(s, LIGHTNING, fork, (fork[0] + (seed % 2 * 2 - 1) * step,
                                              fork[1] + step * 1.4), 1)


# Water on the periscope's head glass: how long the water takes to run off a
# raised scope, the sea state from which waves wash over it, and how long
# drops stay on the glass after a wave.
RAISE_DRAIN_S = 1.4
WASH_SEA_MIN = 3.5
DROPS_S = 2.5
DROP_COUNT = 18
WATER_COLOR = (12, 58, 66)
WATER_FOAM = (150, 214, 208)


def lens_water(t: float, sea_state: float, raised_s: float | None = None) -> tuple:
    """(cover 0..1, drops 0..1) on the periscope's glass at display time
    ``t``: the share of the picture under water (from below) and how wet
    the glass still is.  A scope raised ``raised_s`` ago is still draining;
    in a rough sea the bigger waves wash over the head now and then.
    Cosmetic only; the browser uses the same formula (sight-scene.js)."""
    cover = drops = 0.0
    if raised_s is not None and raised_s >= 0.0:
        cover = _clamp(1.0 - raised_s / RAISE_DRAIN_S)
        drops = _clamp(1.0 - (raised_s - RAISE_DRAIN_S) / DROPS_S) if raised_s < RAISE_DRAIN_S + DROPS_S else 0.0
    if sea_state >= WASH_SEA_MIN:
        period = 5.0 + sea_state
        phase = t / period
        wave = math.floor(phase)
        amp = 0.75 + 0.25 * math.sin(wave * 1.7)
        crest = amp * math.sin(math.tau * phase)
        threshold = 1.1 - 0.12 * sea_state
        cover = max(cover, _clamp((crest - threshold) / max(0.05, 1.0 - threshold)) * 0.9)
        # Drops after this wave's crest (a quarter period in) if it washed over.
        since = (phase - wave - 0.25) * period
        if amp > threshold and 0.0 <= since <= DROPS_S + period * 0.25:
            drops = max(drops, _clamp(1.0 - max(0.0, since - period * 0.25) / DROPS_S))
    return cover, drops


def draw_lens_water(s, rect, cover: float, drops: float, t: float) -> None:
    """Water over the lower ``cover`` of the picture with a moving wavy
    line and foam, and drops running down the glass."""
    rect = pygame.Rect(rect)
    if cover > 0.01:
        top = rect.bottom - cover * rect.h
        step = max(6, rect.w // 60)
        points = [(rect.x, rect.bottom)]
        for x in range(rect.x, rect.right + step, step):
            points.append((min(x, rect.right), top + 5.0 * math.sin(x / 37.0 + t * 3.1)
                           + 3.0 * math.sin(x / 11.0 - t * 5.3)))
        points.append((rect.right, rect.bottom))
        pygame.draw.polygon(s, WATER_COLOR, points)
        pygame.draw.lines(s, WATER_FOAM, False, points[1:-1], 2)
    if drops > 0.02:
        count = int(DROP_COUNT * drops)
        for index in range(count):
            fx = (index * 0.5698 + 0.13) % 1.0
            fy = (index * 0.7549 + 0.29) % 1.0
            x = rect.x + fx * rect.w
            y = rect.y + (fy * 0.85 + 0.06 * (1.0 - drops)) * rect.h
            radius = max(2, int((3 + (index % 4) * 2) * rect.w / 600.0 + 1))
            pygame.draw.circle(s, WATER_FOAM, (int(x), int(y)), radius, 1)
            pygame.draw.circle(s, (230, 250, 250), (int(x - radius * 0.4), int(y - radius * 0.4)),
                               max(1, radius // 3))


def _fog(width, height, color) -> pygame.Surface:
    surf = hires.surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    for y in range(max(1, height)):
        alpha = int(170 * math.sin(math.pi * y / max(1, height - 1)))
        pygame.draw.line(surf, (*color, alpha), (0, y), (width, y))
    return surf


# The weather instrument looks into the wind over this field.
INSTRUMENT_FOV_DEG = 120.0


def draw_instrument(s, rect, sky: dict, *, visibility_nm: float, sea_state: float,
                    t: float) -> None:
    """The bridge's small weather picture: sky, clouds, sea and weather seen
    into the wind, the wind rose in the top left corner and the brackets."""
    rect = pygame.Rect(rect)
    view = View(rect, sky["wind_from_deg"], INSTRUMENT_FOV_DEG, rect.y + int(rect.h * 0.56), 0.0)
    previous = s.get_clip()
    s.set_clip(rect.clip(previous) if previous else rect)
    try:
        colors = draw_scene(s, view, sky, visibility_nm=visibility_nm, sea_state=sea_state, t=t)
        draw_weather(s, view, sky, colors, visibility_nm=visibility_nm, t=t)
        # Wind rose: north up, the arrow blows from where the wind comes.
        radius = max(8, min(14, rect.h // 5))
        cx, cy = rect.x + radius + 6, rect.y + radius + 6
        angle = math.radians(sky["wind_from_deg"])
        dx, dy = math.sin(angle), -math.cos(angle)
        pygame.draw.circle(s, blend(colors["sky"][0], (0, 0, 0), 0.5), (cx, cy), radius)
        pygame.draw.circle(s, FRAME, (cx, cy), radius, 1)
        tail = (cx + dx * (radius - 2), cy + dy * (radius - 2))
        head = (cx - dx * (radius - 3), cy - dy * (radius - 3))
        pygame.draw.line(s, WIND_ARROW, tail, head, 2)
        side = (-dy * 3, dx * 3)
        pygame.draw.polygon(s, WIND_ARROW, [head, (head[0] + dx * 5 + side[0], head[1] + dy * 5 + side[1]),
                                            (head[0] + dx * 5 - side[0], head[1] + dy * 5 - side[1])])
    finally:
        s.set_clip(previous)
    draw_frame(s, rect)


def draw_frame(s, rect) -> None:
    """Thin rim and the start screen's corner brackets around a picture."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(s, blend(FRAME, (0, 0, 0), 0.4), rect, 1)
    size = max(6, min(BRACKET, rect.w // 6, rect.h // 4))
    for x, y, dx, dy in ((rect.x + 3, rect.y + 3, 1, 1), (rect.right - 4, rect.y + 3, -1, 1),
                         (rect.x + 3, rect.bottom - 4, 1, -1),
                         (rect.right - 4, rect.bottom - 4, -1, -1)):
        pygame.draw.line(s, FRAME, (x, y), (x + dx * size, y), 2)
        pygame.draw.line(s, FRAME, (x, y), (x, y + dy * size), 2)
