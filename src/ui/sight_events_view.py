"""Water columns, fireballs, fire and smoke and sinking ships in the
eyepieces (binoculars, lookout strip, periscope).

Draws the detached rows of ``src/core/sight_events.py`` into a
``sight_scene.View``: size from the range, the phase from the event's age
on the display clock.  Plain filled shapes in colours blended toward the
haze (no per-pixel alpha), so a handful of events stays cheap on the
uConsole.  Display only; ``data/commander/js/views/sight-events.js`` draws
the same for the browser.
"""

from __future__ import annotations

import math

import pygame

from src.ui import sight_scene

WHITE_WATER = (236, 244, 246)
FLASH = (255, 236, 170)
FIRE = (255, 150, 44)
FIRE_CORE = (255, 226, 120)
SMOKE_DAY, SMOKE_NIGHT = (58, 60, 62), (16, 18, 22)
HULL_DARK = (28, 34, 40)
SMOKE_PUFFS = 14
COLUMN_PUFFS = 11


def _blend(a, b, t):
    return sight_scene.blend(a, b, max(0.0, min(1.0, t)))


def _px(view, metres: float, range_nm: float) -> float:
    """Screen px of ``metres`` seen at ``range_nm``."""
    return view.px_per_deg * math.degrees(math.atan2(metres, max(30.0, range_nm * 1852.0)))


def _drift(sky: dict, line_of_sight: float) -> float:
    """-1..1: how far smoke drifts to the right of the picture."""
    return math.sin(math.radians(sky["wind_from_deg"] + 180.0 - line_of_sight))


def draw_events(s, view, colors: dict, sky: dict, events, now: float) -> None:
    """Every visible row in ``events`` at display time ``now`` (sim s)."""
    if not events:
        return
    night = sky["light"] < 0.35
    haze = colors["haze_level"]
    # Far events first, so near ones draw over them.
    for row in sorted(events, key=lambda item: -item["range_nm"]):
        age = now - row["at_s"]
        if age < 0.0 or age > row["dur_s"] or not view.visible(row["bearing"], 3.0):
            continue
        x = view.x(row["bearing"])
        base = view.base(x)
        fade = min(1.0, haze * 0.7 + row["range_nm"] / 40.0)
        kind = row["kind"]
        if kind == "column":
            _column(s, view, colors, row, age, x, base, fade, night)
        elif kind == "blast":
            _blast(s, view, colors, sky, row, age, x, base, fade, night)
        elif kind == "fire":
            _fire(s, view, colors, sky, row, age, x, base, fade, night, now)
        elif kind == "sinking":
            _sinking(s, view, colors, row, age, x, base, fade, night)


def _column(s, view, colors, row, age, x, base, fade, night):
    """The white column of an underwater charge: it shoots up in two
    seconds, hangs, collapses and leaves a spreading patch of foam."""
    height = _px(view, row["size_m"], row["range_nm"])
    if height < 1.0:
        return
    rise = min(1.0, age / 2.0)
    fall = max(0.0, (age - 5.0) / 10.0)
    top = height * rise * (1.0 - min(1.0, fall) * 0.95)
    width = max(2.0, height * 0.28)
    water = _blend(WHITE_WATER if not night else (70, 86, 92), colors["haze"], fade)
    spray = _blend(water, colors["sea"][0], min(1.0, age / row["dur_s"] * 1.4))
    if age < 0.6 and night:
        pygame.draw.circle(s, _blend(FLASH, colors["haze"], fade),
                           (int(x), int(base - 1)), max(2, int(width * (1.2 - age))))
    for k in range(COLUMN_PUFFS):
        f = k / (COLUMN_PUFFS - 1)
        y = base - top * f
        wobble = math.sin(k * 1.9 + age * 1.3) * width * 0.15 * f
        radius = max(1, int(width * (0.35 + 0.45 * f) * (1.0 + fall * 0.8)))
        if top > 1.0:
            pygame.draw.circle(s, spray if f < 0.2 else water, (int(x + wobble), int(y)), radius)
    # Foam spreading on the sea round the foot of the column.
    spread = width * (0.8 + min(3.5, age * 0.25))
    pygame.draw.ellipse(s, spray, (x - spread, base - max(1.0, spread * 0.12),
                                   spread * 2, max(2.0, spread * 0.24)))


def _blast(s, view, colors, sky, row, age, x, base, fade, night):
    """A missile hit: a fireball on the hull, then a black cloud rising."""
    size = max(2.0, _px(view, row["size_m"], row["range_nm"]))
    if age < 3.0:
        k = age / 3.0
        pygame.draw.circle(s, _blend(FIRE, colors["haze"], fade * 0.6 + k * 0.4),
                           (int(x), int(base - size * 0.5)), max(2, int(size * (0.6 + k))))
        pygame.draw.circle(s, _blend(FIRE_CORE, FIRE, k), (int(x), int(base - size * 0.5)),
                           max(1, int(size * 0.45 * (1.0 - k))))
    smoke = _blend(SMOKE_NIGHT if night else SMOKE_DAY, colors["haze"], fade)
    drift = _drift(sky, view.los)
    for k in range(6):
        f = min(1.0, age / 14.0) * (0.3 + k / 8.0)
        cx = x + drift * size * 2.0 * f
        pygame.draw.circle(s, smoke, (int(cx), int(base - size * (0.6 + 3.0 * f))),
                           max(1, int(size * (0.5 + 0.9 * f))))


def _fire(s, view, colors, sky, row, age, x, base, fade, night, now):
    """A burning ship: flames on deck and a smoke plume that drifts with
    the wind (at night the glow alone)."""
    level = row["level"]
    if level <= 0.02:
        return
    hull = _px(view, row["size_m"], row["range_nm"])
    plume = _px(view, 180.0, row["range_nm"]) * (0.4 + 0.6 * level)
    drift = _drift(sky, view.los)
    if not night and plume >= 2.0:
        smoke = _blend(SMOKE_DAY, colors["haze"], fade)
        for k in range(SMOKE_PUFFS):
            f = ((now * 0.03) + k / SMOKE_PUFFS) % 1.0
            cx = x + drift * plume * 1.4 * f ** 1.3 + math.sin(k * 2.3) * hull * 0.05
            radius = max(1, int(plume * (0.06 + 0.22 * f)))
            color = _blend(smoke, colors["haze"], f * 0.7)
            pygame.draw.circle(s, color, (int(cx), int(base - plume * f - hull * 0.05)), radius)
    flame = max(1.0, hull * 0.06 * (0.5 + level))
    glow = _blend(FIRE, colors["haze"], fade * (0.3 if night else 0.6))
    for k in range(3):
        flicker = 0.7 + 0.3 * math.sin(now * (7.0 + k * 2.3) + k * 1.7)
        fx = x + (k - 1) * hull * 0.08
        pygame.draw.circle(s, glow, (int(fx), int(base - flame * 0.6)), max(1, int(flame * flicker)))
    if night:
        pygame.draw.circle(s, _blend(FIRE_CORE, colors["haze"], fade * 0.3),
                           (int(x), int(base - flame * 0.6)), max(1, int(flame * 0.5)))


def _sinking(s, view, colors, row, age, x, base, fade, night):
    """A sinking ship: she settles by the stern, the bow rises and she
    slides under; foam and bubbles stay a little longer."""
    length = _px(view, row["size_m"], row["range_nm"])
    if length < 2.0:
        return
    p = min(1.0, age / (row["dur_s"] * 0.8))
    tilt = math.radians(8.0 + 32.0 * min(1.0, p * 1.5))
    height = length * 0.12
    drop = (length * math.sin(tilt) * 0.5 + height) * p * 1.3
    hull = _blend(HULL_DARK if not night else (10, 14, 18), colors["haze"], fade)
    # Bow on the left rises, the stern goes down first; the whole hull
    # slides under (``u`` along the hull bow -0.5 .. stern 0.5, ``v`` up).
    points = []
    for u, v in ((-0.5, 0.0), (-0.46, 1.5), (-0.1, 1.0), (0.3, 1.0), (0.32, 1.8),
                 (0.42, 1.8), (0.44, 1.0), (0.5, 1.0), (0.5, 0.0)):
        points.append((x + u * length * math.cos(tilt) - v * height * math.sin(tilt),
                       base + drop - v * height + u * length * math.sin(tilt)))
    previous = s.get_clip()
    above = pygame.Rect(view.rect.x, view.rect.y, view.rect.w, max(0, int(base) - view.rect.y))
    s.set_clip(above.clip(previous) if previous else above)
    try:
        if p < 1.0:
            pygame.draw.polygon(s, hull, points)
    finally:
        s.set_clip(previous)
    foam = _blend(WHITE_WATER if not night else (60, 76, 82), colors["sea"][0], 0.3 + p * 0.5)
    spread = length * (0.3 + 0.5 * p)
    pygame.draw.ellipse(s, foam, (x - spread, base - max(1.0, spread * 0.05),
                                  spread * 2, max(2.0, spread * 0.1)))
