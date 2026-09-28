"""Procedural start screen: the hunt at night, drawn without external assets.

The frigate F-217 steams on a moonlit sea, its radar turning and its hull
sonar pinging a submarine that creeps below the layer; the helicopter hovers
with its dipping sonar and the towed array trails astern.  The same animated
scene, dimmed, lies behind the main menu.  Everything is cosmetic: the phase
comes from the caller's wall-clock time and nothing here touches the
simulation.
"""

from collections import OrderedDict
import math
import random

import pygame

from src.core.i18n import localize, localized, message
from src.core.version import APP_VERSION
from src.ui import layout, silhouettes

AUTHOR = "Dominik Bornhäußer"

# Hull sonar pulse: travel speed on screen and repetition (one ping sound
# per period, see ``Game.update``).
SPLASH_PING_SPEED_PX_S = 130.0
SPLASH_PING_PERIOD_S = 4.0

HORIZON_Y = 318
LAYER_Y = 452
FRIGATE_CX, FRIGATE_W = 860, 560
HELO_W = 180
SUB_Y, SUB_W = 560, 340
SUB_SPEED_PX_S = 9.0
DIP_PERIOD_S = 3.3

SKY_TOP, SKY_HORIZON = (3, 7, 16), (20, 44, 62)
SEA_TOP, SEA_DEEP = (10, 44, 58), (2, 9, 15)
STEEL = (19, 36, 46)
STEEL_RIM = (84, 150, 158)
HULL_UNDERWATER = (8, 26, 34)
SUB_STEEL = (7, 24, 30)
SUB_RIM = (46, 110, 116)
PHOSPHOR = (150, 255, 205)
PHOSPHOR_DIM = (62, 140, 128)
PING = (70, 190, 190)
GOLD = (236, 204, 128)
WINDOW_LIGHT = (250, 205, 120)
KEEL = [(0.035, 0.0), (0.05, -0.035), (0.13, -0.045), (0.93, -0.033), (0.985, 0.0)]

_LAYERS = {}
_TEXT_CACHE = OrderedDict()
_TEXT_CACHE_MAX = 48


def _gradient(size, top, bottom) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        pygame.draw.line(surf, tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)),
                         (0, y), (w, y))
    return surf


def _static_layers(width: int, height: int) -> dict:
    """Sky, deep water, light shafts and sea floor, built once per size."""
    key = (width, height)
    layers = _LAYERS.get(key)
    if layers is not None:
        return layers
    rng = random.Random(217)  # cosmetic only: fixed star field and sea floor
    sky = _gradient((width, HORIZON_Y), SKY_TOP, SKY_HORIZON)
    stars = [(rng.randrange(width), rng.randrange(int(HORIZON_Y * .85)),
              rng.uniform(0, math.tau), rng.uniform(.6, 2.2), rng.random() < .12)
             for _ in range(140)]
    halo = pygame.Surface((180, 180), pygame.SRCALPHA)
    for r, a in ((96, 5), (80, 7), (66, 9), (54, 12), (44, 16), (35, 22)):
        pygame.draw.circle(halo, (170, 200, 210, a), (90, 90), r)
    water = _gradient((width, height - HORIZON_Y), SEA_TOP, SEA_DEEP)
    shafts = pygame.Surface((width, height - HORIZON_Y), pygame.SRCALPHA)
    for x in (140, 330, 700, 1010, 1180):
        spread = rng.randint(40, 80)
        pygame.draw.polygon(shafts, (120, 190, 200, 8),
                            [(x - 18, 0), (x + 18, 0), (x + spread + 60, 300),
                             (x - spread + 60, 300)])
    water.blit(shafts, (0, 0))
    for x in range(0, width, 18):
        pygame.draw.line(water, (22, 70, 78), (x, LAYER_Y - HORIZON_Y),
                         (x + 8, LAYER_Y - HORIZON_Y), 1)
    floor = [(0, height)]
    y = height - 46
    for x in range(0, width + 40, 40):
        y = min(height - 18, max(height - 90, y + rng.randint(-14, 14)))
        floor.append((x, y))
    floor.append((width, height))
    shifted = [(x, y - HORIZON_Y) for x, y in floor]
    pygame.draw.polygon(water, (4, 15, 19), shifted)
    pygame.draw.lines(water, (18, 48, 50), False, shifted[1:-1], 1)
    dim = pygame.Surface((width, height), pygame.SRCALPHA)
    dim.fill((2, 6, 10, 170))
    layers = dict(sky=sky, stars=stars, halo=halo, water=water, dim=dim)
    _LAYERS.clear()
    _LAYERS[key] = layers
    return layers


def _text(text: str, size: int, color, bold: bool = False) -> pygame.Surface:
    key = (text, size, bold, color, layout.text_scale())
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        surf = layout.font(size, bold).render(text, True, color)
        _TEXT_CACHE[key] = surf
        while len(_TEXT_CACHE) > _TEXT_CACHE_MAX:
            _TEXT_CACHE.popitem(last=False)
    else:
        _TEXT_CACHE.move_to_end(key)
    return surf


def _blit_text(surface, text: str, pos, size: int, color, *, bold=False, anchor="topleft",
               glow=None) -> pygame.Rect:
    image = _text(text, size, color, bold)
    rect = image.get_rect(**{anchor: pos})
    if glow is not None:
        halo = _text(text, size, glow, bold)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)):
            surface.blit(halo, rect.move(dx, dy))
    surface.blit(image, rect)
    layout.record_text(text, rect, surface.get_rect())
    return rect


def _frigate_frame(t: float):
    return silhouettes.frame_for("warship", FRIGATE_CX, HORIZON_Y, FRIGATE_W, t)


def ping_origin(t: float) -> tuple:
    """The frigate's bow sonar dome on screen at time ``t``."""
    return _frigate_frame(t).point(0.08, -0.05)


def submarine_center(t: float) -> tuple:
    """The submarine's midships on screen at time ``t`` (it wraps around)."""
    x = -200.0 + (580.0 + SUB_SPEED_PX_S * t) % 1680.0
    return (x, SUB_Y + 4.0 * math.sin(t * 0.21))


def _helo_position(t: float) -> tuple:
    return (470.0 + 10.0 * math.sin(t * 0.4), HORIZON_Y + 70.0)


def _draw_sky(surface, layers, t: float) -> None:
    surface.blit(layers["sky"], (0, 0))
    for x, y, phase, speed, bright in layers["stars"]:
        glow = .55 + .45 * math.sin(t * speed + phase)
        level = int((150 if bright else 90) * glow) + 40
        if bright:
            pygame.draw.circle(surface, (level, level, min(255, level + 30)), (x, y), 1)
        else:
            surface.set_at((x, y), (level, level, min(255, level + 25)))
    moon = (1120, 86)
    surface.blit(layers["halo"], (moon[0] - 90, moon[1] - 90))
    pygame.draw.circle(surface, (214, 222, 206), moon, 22)
    pygame.draw.circle(surface, (188, 196, 184), (moon[0] + 7, moon[1] + 4), 5)
    pygame.draw.circle(surface, (194, 202, 190), (moon[0] - 8, moon[1] - 6), 3)


def _draw_smoke(surface, t: float) -> None:
    fx, fy = _frigate_frame(t).point(*silhouettes.PROFILES["warship"]["funnel_top"])
    for i in range(7):
        age = (t * .35 + i / 7.0) % 1.0
        x = fx + 16 + age * 150
        y = fy - 6 - age * 46 - 6 * math.sin(age * 5 + i)
        fade = 1.0 - age
        color = tuple(int(sky + (46 - sky) * fade * .6) for sky in SKY_HORIZON)
        pygame.draw.circle(surface, color, (int(x), int(y)), int(5 + age * 16))


def _draw_sea(surface, layers, t: float) -> None:
    width, _height = surface.get_size()
    surface.blit(layers["water"], (0, HORIZON_Y))
    points = [(x, HORIZON_Y + 2.2 * math.sin(x * .045 + t * 1.6)
               + 1.4 * math.sin(x * .013 - t * .9)) for x in range(0, width + 16, 16)]
    pygame.draw.polygon(surface, SEA_TOP, points + [(width, HORIZON_Y + 8), (0, HORIZON_Y + 8)])
    pygame.draw.lines(surface, (96, 150, 156), False, points, 1)
    for row in range(1, 6):
        y = HORIZON_Y + row * 9
        offset = (t * (10 + row * 4)) % 56
        for x in range(-56, width, 56):
            if (x // 56 + row) % 2:
                continue
            pygame.draw.line(surface, (20, 64, 74), (x + offset, y), (x + offset + 18, y), 1)
    for i in range(14):
        shimmer = math.sin(t * 2.4 + i * 1.7)
        if shimmer < -.2:
            continue
        y = HORIZON_Y + 5 + i * 5
        half = int(18 + i * 2.5 * (.5 + .5 * shimmer))
        pygame.draw.line(surface, (150, 170, 170), (1120 - half, y), (1120 + half, y), 1)


def _draw_frigate(surface, t: float) -> None:
    frame = silhouettes.draw_profile(surface, "warship", FRIGATE_CX, HORIZON_Y, FRIGATE_W,
                                     STEEL, t=t, rim=STEEL_RIM, lights=WINDOW_LIGHT,
                                     wake=False)
    nx, ny = frame.point(0.085, 0.026)
    _blit_text(surface, "F217", (int(nx), int(ny)), 13, (150, 164, 166), anchor="midleft")
    profile = silhouettes.PROFILES["warship"]
    mast = frame.point(*profile["masthead"])
    pygame.draw.circle(surface, (235, 240, 230), (int(mast[0]), int(mast[1])), 2)
    if (t % 1.4) < .18:
        top = frame.point(0.60, 0.192)
        pygame.draw.circle(surface, (255, 70, 60), (int(top[0]), int(top[1])), 3)
    bow = frame.point(0.02, 0.03)
    stern = frame.point(1.0, 0.03)
    pygame.draw.circle(surface, (60, 220, 90), (int(bow[0] + 2), int(bow[1])), 2)
    pygame.draw.circle(surface, (235, 235, 225), (int(stern[0] - 2), int(stern[1])), 2)


def _draw_keel_and_wake(surface, t: float) -> None:
    frame = _frigate_frame(t)
    pygame.draw.polygon(surface, HULL_UNDERWATER, frame.poly(KEEL))
    dome = frame.point(0.08, -0.05)
    pygame.draw.ellipse(surface, HULL_UNDERWATER, (int(dome[0]) - 12, int(dome[1]) - 5, 26, 10))
    silhouettes.draw_wake(surface, frame, FRIGATE_W, t)


def _draw_towed_array(surface, t: float) -> None:
    sx, sy = _frigate_frame(t).point(0.99, -0.01)
    points = []
    for i in range(12):
        s = i / 11.0
        points.append((sx + s * 240, sy + 120 * s ** 1.3 + 3 * math.sin(t * 1.1 + s * 5)))
    pygame.draw.lines(surface, (40, 96, 100), False, points, 1)
    for x, y in points[7:]:
        pygame.draw.line(surface, (70, 150, 150), (x - 5, y - 2), (x + 5, y + 2), 2)


def _draw_helicopter(surface, t: float) -> None:
    hx, hy = _helo_position(t)
    frame = silhouettes.draw_profile(surface, "aircraft", hx, hy, HELO_W, STEEL, t=t,
                                     rim=STEEL_RIM, lights=WINDOW_LIGHT)
    belly = frame.point(0.30, 0.49)
    dip = (hx - 20, HORIZON_Y + 130)
    pygame.draw.line(surface, (120, 160, 160), belly, dip, 1)
    pygame.draw.rect(surface, (60, 130, 130), (dip[0] - 3, dip[1] - 2, 7, 12))
    for i in range(4):
        phase = (t * 1.8 + i * .25) % 1.0
        half = 10 + phase * 40
        pygame.draw.line(surface, (150, 190, 190), (belly[0] - half, HORIZON_Y + 1),
                         (belly[0] - half + 10, HORIZON_Y + 1), 1)
        pygame.draw.line(surface, (150, 190, 190), (belly[0] + half - 10, HORIZON_Y + 1),
                         (belly[0] + half, HORIZON_Y + 1), 1)


def _arcs(surface, origin, radius: float, color, start: float, stop: float, width=2):
    r = int(radius)
    if r < 3:
        return
    pygame.draw.arc(surface, color, (origin[0] - r, origin[1] - r, 2 * r, 2 * r),
                    start, stop, width)


def _fade(color, k: float) -> tuple:
    k = max(0.0, min(1.0, k))
    return tuple(int(d + (c - d) * k) for c, d in zip(color, SEA_DEEP))


def _draw_pings(surface, t: float) -> float:
    """Hull sonar pulse towards the submarine and its echo; returns the flash."""
    width, height = surface.get_size()
    origin = ping_origin(t)
    radius = (t % SPLASH_PING_PERIOD_S) * SPLASH_PING_SPEED_PX_S
    sub = submarine_center(t)
    distance = math.dist(origin, sub)
    flash = 0.0
    with layout.clip_to(surface, (0, HORIZON_Y + 3, width, height - HORIZON_Y - 3)):
        for lag, strength in ((0, 1.0), (14, .55), (28, .3)):
            r = radius - lag
            if 0 < r < 440:
                _arcs(surface, origin, r, _fade(PING, strength * (1 - r / 460)),
                      math.pi, 2 * math.pi, 2 if lag == 0 else 1)
        hit_age = (radius - distance) / SPLASH_PING_SPEED_PX_S
        if 0 <= hit_age < 2.0:
            flash = max(0.0, 1.0 - hit_age * 1.1)
            toward = math.atan2(sub[1] - origin[1], origin[0] - sub[0])
            _arcs(surface, sub, hit_age * SPLASH_PING_SPEED_PX_S,
                  _fade((200, 255, 220), 1 - hit_age / 2.0), toward - .5, toward + .5, 2)
        dip = (_helo_position(t)[0] - 20, HORIZON_Y + 130)
        dip_r = ((t + 1.1) % DIP_PERIOD_S) * 85.0
        _arcs(surface, dip, dip_r, _fade((90, 170, 150), .7 * (1 - dip_r / 300)),
              0, 2 * math.pi, 1)
    return flash


def _draw_submarine(surface, t: float, flash: float) -> None:
    cx, cy = submarine_center(t)
    rim = tuple(int(a + (b - a) * flash) for a, b in zip(SUB_RIM, (200, 255, 230)))
    frame = silhouettes.draw_profile(surface, "submarine", cx, cy, SUB_W, SUB_STEEL, t=t,
                                     facing=1, rim=rim, wake=False)
    tail = frame.point(1.0, 0.0)
    for i in range(9):
        age = (t * .55 + i / 9.0) % 1.0
        x = tail[0] - 8 - age * 22 + 3 * math.sin(t * 3 + i)
        y = tail[1] - age * 70
        pygame.draw.circle(surface, _fade((120, 190, 200), 1 - age), (int(x), int(y)),
                           max(1, int(1 + age * 3)), 1)


def _draw_snow(surface, t: float) -> None:
    width, height = surface.get_size()
    for i in range(46):
        x = (i * 97 + 13 * math.sin(t * .3 + i)) % width
        y = HORIZON_Y + 20 + (i * 53 + t * (6 + i % 5)) % (height - HORIZON_Y - 40)
        surface.set_at((int(x), int(y)), (40, 88, 96))


def _draw_frame(surface) -> None:
    """Corner brackets of a console display."""
    width, height = surface.get_size()
    color = (40, 96, 90)
    for x, y, dx, dy in ((14, 14, 1, 1), (width - 15, 14, -1, 1),
                         (14, height - 15, 1, -1), (width - 15, height - 15, -1, -1)):
        pygame.draw.line(surface, color, (x, y), (x + dx * 36, y), 2)
        pygame.draw.line(surface, color, (x, y), (x, y + dy * 36), 2)


def draw_scene(surface: pygame.Surface, t: float) -> None:
    """The animated night hunt (sky, frigate, helicopter, sea, submarine)."""
    width, height = surface.get_size()
    layers = _static_layers(width, height)
    _draw_sky(surface, layers, t)
    _draw_smoke(surface, t)
    _draw_frigate(surface, t)
    _draw_sea(surface, layers, t)
    _draw_keel_and_wake(surface, t)
    _draw_towed_array(surface, t)
    _draw_helicopter(surface, t)
    _draw_snow(surface, t)
    flash = _draw_pings(surface, t)
    _draw_submarine(surface, t, flash)
    _draw_frame(surface)


def draw_logo(surface, center_x: int, top: int) -> pygame.Rect:
    """Compact title with author and version, for the menus."""
    title = _blit_text(surface, localize("splash.title"), (center_x, top), 50, PHOSPHOR,
                       bold=True, anchor="midtop", glow=(14, 60, 52))
    byline = localize(message("splash.menu_byline", author=AUTHOR, version=APP_VERSION))
    line = _blit_text(surface, byline, (center_x, title.bottom + 2), 16, GOLD,
                      anchor="midtop")
    return title.union(line)


def draw_menu_panel(surface, rect, highlight) -> None:
    """Translucent console panel behind the main-menu entries."""
    rect = pygame.Rect(rect)
    panel = _LAYERS.get(("panel", rect.size))
    if panel is None:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((4, 16, 20, 150))
        _LAYERS[("panel", rect.size)] = panel
    surface.blit(panel, rect)
    pygame.draw.rect(surface, (40, 96, 90), rect, 1)
    pygame.draw.rect(surface, (18, 60, 56), highlight)


def draw_menu_backdrop(surface: pygame.Surface, t: float) -> None:
    """The start-screen scene, dimmed so menu text stays readable."""
    width, height = surface.get_size()
    draw_scene(surface, t)
    surface.blit(_static_layers(width, height)["dim"], (0, 0))


@localized
def draw_splash(surface: pygame.Surface, elapsed_s: float, tr=None) -> None:
    """Start screen: the scene, the title, the author and the version."""
    width, height = surface.get_size()
    draw_scene(surface, elapsed_s)
    k = max(.15, min(1.0, elapsed_s / .8))

    def tone(color):
        return tuple(int(c * k) for c in color)

    title = _blit_text(surface, localize("splash.title"), (60, 28), 84, tone(PHOSPHOR),
                       bold=True, glow=tone((14, 60, 52)))
    sub = _blit_text(surface, localize("splash.subtitle"), (64, title.bottom), 20,
                     tone(PHOSPHOR_DIM))
    author = _blit_text(surface, localize(message("splash.author", author=AUTHOR)),
                        (64, sub.bottom + 8), 26, tone(GOLD), bold=True)
    version = localize(message("splash.version", version=APP_VERSION))
    badge = _text(version, 16, tone(PHOSPHOR)).get_rect().inflate(20, 10)
    badge.topleft = (64, author.bottom + 8)
    pygame.draw.rect(surface, (6, 22, 24), badge, border_radius=4)
    pygame.draw.rect(surface, tone(PHOSPHOR_DIM), badge, 1, border_radius=4)
    _blit_text(surface, version, badge.center, 16, tone(PHOSPHOR), anchor="center")

    layout.blit_line(surface, "splash.tagline", (40, height - 66, width - 80, 22),
                     tone((110, 180, 170)), size=15, align="center")
    if elapsed_s > .6 and (elapsed_s % 1.6) < 1.1:
        layout.blit_line(surface, "splash.press_key", (40, height - 40, width - 80, 22),
                         tone(PHOSPHOR), size=16, align="center")
