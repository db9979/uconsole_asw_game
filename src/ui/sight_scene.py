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
               wind_from_deg: float) -> dict:
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
                moon_waxing=bool((lunar_age_days % LUNAR_MONTH_D) < LUNAR_MONTH_D / 2.0))


def sky_state(game) -> dict:
    """``sky_values`` of the game's own atmosphere (observation-safe)."""
    atmosphere = game.atmosphere()
    return sky_values(game.world.hour, game.lunar_age_days(),
                      atmosphere["moon_illumination"], atmosphere["cloud_cover"],
                      atmosphere["precipitation"], atmosphere["rain_intensity"],
                      atmosphere["wind_from_deg"])


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
                                (250, 190, 130), dusk * 0.7))


def _cached(cache, key, build):
    surf = cache.get(key)
    if surf is None:
        surf = build()
        cache[key] = surf
        while len(cache) > _CACHE_MAX:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    return surf


def _gradient(size, top, bottom) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface((max(1, w), max(1, h)))
    for y in range(max(1, h)):
        pygame.draw.line(surf, blend(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return surf


def _shade(size, color) -> pygame.Surface:
    """Transparent at the top, ``color`` at the bottom (the deep sea)."""
    w, h = size
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
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

    def __init__(self, rect, line_of_sight, fov_deg, horizon, tilt):
        self.rect = pygame.Rect(rect)
        self.los, self.fov = line_of_sight, fov_deg
        self.px_per_deg = self.rect.w / fov_deg
        self.horizon, self.tilt = horizon, tilt
        # The sky (stars, sun, moon, clouds) hangs on the eyepiece's nominal
        # horizon, not on the one rolling with the sea: it stays still.
        self.sky_h = max(8, self.rect.h // 2)

    def x(self, bearing: float) -> float:
        return self.rect.centerx + _wrap(bearing, self.los) * self.px_per_deg

    def base(self, x: float) -> float:
        return self.horizon + math.tan(self.tilt) * (x - self.rect.centerx)

    def visible(self, bearing: float, half_deg: float = 0.0) -> bool:
        return abs(_wrap(bearing, self.los)) <= self.fov / 2.0 + half_deg

    def alt_y(self, fraction: float, x: float) -> float:
        """Height ``fraction`` (0 horizon .. 1 top) of the eyepiece's sky."""
        return self.rect.y + self.rect.h / 2.0 - fraction * self.sky_h


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


def _draw_sea(s, view, sky, colors, sea_state, t, haze):
    rect = view.rect
    dy = math.tan(view.tilt) * rect.w / 2.0
    left, right = view.horizon - dy, view.horizon + dy
    amp = 0.6 + 0.35 * sea_state
    step = max(6, rect.w // 60)
    head, cross = sea_aspect(sky["wind_from_deg"], view.los)
    # The pattern lies on the sea (bearing space), so it slides past as the
    # line of sight turns; along the crests it runs with the swell.
    anchor = view.los * view.px_per_deg
    swell = cross * t * 14.0
    crest = [(x, view.base(x) + amp * math.sin((x + anchor - swell) * 0.045 + t * 1.6 * abs(head))
              + 0.6 * amp * math.sin((x + anchor - swell) * 0.013 - t * 0.9))
             for x in range(rect.x, rect.right + step, step)]
    pygame.draw.polygon(s, colors["sea"][0], crest + [(rect.right, rect.bottom),
                                                       (rect.x, rect.bottom)])
    top = int(min(left, right) + amp + 2)
    depth = rect.bottom - top
    if depth > 4:
        shade = _cached(_SHADE_CACHE, (rect.w, depth, colors["sea"][1]),
                        lambda: _shade((rect.w, depth), colors["sea"][1]))
        s.blit(shade, (rect.x, top))
    # Wave rows, denser toward the horizon.  Looking into or down the sea the
    # crests are long rows that come at the eye or run away from it; across
    # the sea they are short, run sideways and lean with the perspective.
    rows = 9
    below = rect.bottom - view.horizon
    along = abs(head)
    roll = (t * 0.12 * head) % 1.0
    for index in range(rows + 1):
        row = index + roll
        depth_px = below * (row / rows) ** 1.7
        if depth_px < 3 or row > rows:
            continue
        spacing = int(24 + row * 10)
        length = (6 + row * 3) * (0.55 + 1.1 * along)
        lean = cross * (1 + row * 0.7) * (1.0 - along)
        offset = (anchor + t * (6 + row * 3) * cross) % (2 * spacing)
        shade = blend(colors["wave"], colors["sea"][1], row / (rows + 3))
        # Down-sea the eye sees the waves' backs: fainter rows.
        if head < 0:
            shade = blend(shade, colors["sea"][1], 0.35 * -head)
        for x in range(rect.x - 2 * spacing, rect.right, spacing):
            if (x // spacing + index) % 2:
                continue
            x0 = x - offset
            y0 = view.base(x0) + depth_px
            pygame.draw.line(s, shade, (x0, y0), (x0 + length, y0 - lean), 1)
            if sea_state >= 4 and ((x // spacing) * 7 + index) % 5 == 0:
                pygame.draw.line(s, colors["crest"], (x0 + 2, y0 - 1),
                                 (x0 + length - 2, y0 - 1 - lean), 1)
    pygame.draw.lines(s, colors["crest"], False, crest, 1)
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
               t: float) -> dict:
    """Sky, stars, moon or sun, clouds and sea of one picture; returns its
    palette for the land and the silhouettes."""
    haze = 1.0 - _clamp(visibility_nm / config.WEATHER_VISIBILITY_MAX_NM)
    colors = palette(sky, haze)
    rect = view.rect
    sky_img = _cached(_SKY_CACHE, (rect.w, rect.h, colors["sky"]),
                      lambda: _gradient((rect.w, rect.h), *colors["sky"]))
    # The sky stays still: its gradient meets the nominal horizon.
    s.blit(sky_img, rect.topleft, (0, max(0, rect.h - (view.sky_h + 40)), rect.w, rect.h))
    _draw_stars(s, view, sky, colors, t, haze)
    _draw_body(s, view, sky, colors, haze)
    _draw_clouds(s, view, sky, colors, t, haze)
    _draw_sea(s, view, sky, colors, sea_state, t, haze)
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
    kind, intensity = sky["precipitation"], sky["intensity"]
    if kind == "none" or intensity <= 0.0:
        return
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


def _fog(width, height, color) -> pygame.Surface:
    surf = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    for y in range(max(1, height)):
        alpha = int(170 * math.sin(math.pi * y / max(1, height - 1)))
        pygame.draw.line(surf, (*color, alpha), (0, y), (width, y))
    return surf


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
