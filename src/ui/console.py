"""Machinery control console parts in the splash style (display only).

Status lamps with an LED, round dials with coloured zones, tank columns and
a compartment mimic, shared by the frigate's engine room and the
submarine's plant page. They draw values the station already has; nothing
here reads or changes simulation state.
"""

import math

import pygame

from src.core import config
from src.core.i18n import localize, raw_text
from src.ui import layout, lines

LEVELS = ("off", "on", "caution", "alarm")
LED_OFF = (36, 58, 60)
WATER = (40, 110, 160)


def level_color(level: str):
    return {"on": config.COLOR_OK, "caution": config.COLOR_WARN,
            "alarm": config.COLOR_DANGER}.get(level, LED_OFF)


def _mix(color, other, amount: float):
    return tuple(round(a + (b - a) * amount) for a, b in zip(color, other))


def led(screen, center, radius: int, level: str) -> None:
    """A round lamp; lit ones get a soft halo."""
    cx, cy = (int(round(v)) for v in center)
    color = level_color(level)
    if level != "off":
        pygame.draw.circle(screen, _mix(config.COLOR_PANEL_BG, color, .35), (cx, cy), radius + 2)
    pygame.draw.circle(screen, color, (cx, cy), radius)
    if level != "off" and radius >= 4:
        pygame.draw.circle(screen, _mix(color, (255, 255, 255), .45),
                           (cx - radius // 3, cy - radius // 3), max(1, radius // 3))


def master_level(levels) -> str:
    levels = tuple(levels)
    return "alarm" if "alarm" in levels else "caution" if "caution" in levels else "on"


def lamp(screen, rect, label, value, level: str, size: int = 16) -> None:
    """One annunciator tile: LED, label and its value on one row."""
    rect = pygame.Rect(rect)
    layout.record_geometry("lamp", rect, str(label))
    color = level_color(level)
    fill = config.COLOR_PANEL_BG if level in ("off", "on") else _mix(config.COLOR_PANEL_BG, color, .16)
    pygame.draw.rect(screen, fill, rect)
    pygame.draw.rect(screen, color if level != "off" else config.COLOR_SONAR_RING, rect, 1)
    radius = max(3, min(7, rect.h // 4))
    led(screen, (rect.x + 8 + radius, rect.centery), radius, level)
    text_x = rect.x + 16 + 2 * radius
    row = layout.font(size).get_linesize()
    top = rect.y + max(0, (rect.h - row) // 2)
    avail = rect.right - text_x - 6
    face = layout.font(size)
    label_need = face.size(localize(label))[0] + 8
    value_need = face.size(localize(value))[0] + 1 if value else 0
    # The value keeps what the label leaves free, at least three fifths.
    value_w = min(value_need, max(avail - label_need, avail * 3 // 5)) if value else 0
    label_color = config.COLOR_TEXT if level != "off" else config.COLOR_TEXT_DIM
    layout.blit_line(screen, label, (text_x, top, max(1, avail - value_w - 6), row),
                     label_color, size=size)
    if value:
        layout.blit_line(screen, value, (rect.right - 6 - value_w, top, value_w, row),
                         color if level != "off" else config.COLOR_TEXT_DIM, size=size,
                         align="right")


def lamp_grid(screen, rect, rows, columns: int, gap: int = 4, size: int = 16) -> int:
    """Lay ``rows`` of (label, value, level) out as tiles; return the height used."""
    rect = pygame.Rect(rect)
    if not rows:
        return 0
    columns = max(1, columns)
    count = math.ceil(len(rows) / columns)
    tile_h = max(layout.line_pitch(size, 0) + 8, min(40, (rect.h - gap * (count - 1)) // count))
    tile_w = (rect.w - gap * (columns - 1)) // columns
    for index, (label, value, level) in enumerate(rows):
        col, line = index % columns, index // columns
        lamp(screen, (rect.x + col * (tile_w + gap), rect.y + line * (tile_h + gap),
                      tile_w, tile_h), label, value, level, size)
    return count * tile_h + (count - 1) * gap


def _polar(cx, cy, radius, degrees):
    rad = math.radians(degrees)
    return cx + radius * math.sin(rad), cy - radius * math.cos(rad)


def dial(screen, rect, value, lo: float, hi: float, *, text, label,
         zones=(), order=None) -> None:
    """A 240 degree gauge: coloured zones, ticks, needle, the value and label below."""
    rect = pygame.Rect(rect)
    row = layout.font(16).get_linesize()
    radius = min(rect.w // 2 - 6, (rect.h - 2 * row - 8) // 2)
    if radius < 16:
        return
    layout.record_geometry("instrument", rect, str(label))
    used = 4 + radius + radius // 8 + int(radius * .5) + 4 + 2 * row
    cx, cy = rect.centerx, rect.y + max(0, (rect.h - used) // 2) + 4 + radius + radius // 8
    start, sweep = -120.0, 240.0
    span = max(1e-9, float(hi) - float(lo))

    def angle(v):
        return start + sweep * max(0.0, min(1.0, (float(v) - lo) / span))

    def arc(a, b, r, color, width):
        # A filled ring sector: smooth at any band width.
        steps = max(2, int(abs(b - a) / 4) + 1)
        outer = [_polar(cx, cy, r + width / 2, a + (b - a) * i / steps) for i in range(steps + 1)]
        inner = [_polar(cx, cy, r - width / 2, a + (b - a) * i / steps) for i in range(steps, -1, -1)]
        lines.polygon(screen, color, outer + inner)

    band = max(3, radius // 9)
    arc(start, start + sweep, radius - band // 2, layout.METER_TRACK, band)
    for z_lo, z_hi, color in zones:
        arc(angle(z_lo), angle(z_hi), radius - band // 2, color, band)
    for i in range(11):
        a = start + sweep * i / 10
        major = i % 5 == 0
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_SONAR_RING,
                   _polar(cx, cy, radius - band - (7 if major else 3), a),
                   _polar(cx, cy, radius - band, a), 1)
    if order is not None and math.isfinite(order):
        a = angle(order)
        tip = _polar(cx, cy, radius + 1, a)
        pygame.draw.polygon(screen, config.COLOR_WARN,
                            (tip, _polar(cx, cy, radius + 9, a - 5), _polar(cx, cy, radius + 9, a + 5)))
    if value is not None and math.isfinite(value):
        lines.line(screen, config.COLOR_TEXT, (cx, cy), _polar(cx, cy, radius - band - 4, angle(value)), 2)
    pygame.draw.circle(screen, config.COLOR_OK, (cx, cy), 4)
    base = min(rect.bottom - 2 * row, cy + int(radius * .5) + 4)
    layout.blit_line(screen, text if not isinstance(text, str) else raw_text(text),
                     (rect.x, base, rect.w, row), config.COLOR_TEXT, size=16, align="center")
    layout.blit_line(screen, label, (rect.x, base + row, rect.w, row),
                     config.COLOR_TEXT_DIM, size=16, align="center")


def dial_row(screen, rect, specs, gap: int = 6) -> None:
    """Dials across ``rect`` in the rows and columns that make them largest
    (each spec is a dial() keyword dict)."""
    rect = pygame.Rect(rect)
    if not specs:
        return
    row = layout.font(16).get_linesize()
    best = None
    for columns in range(len(specs), 0, -1):
        lines_n = math.ceil(len(specs) / columns)
        cell_w = (rect.w - gap * (columns - 1)) // columns
        cell_h = (rect.h - gap * (lines_n - 1)) // lines_n
        radius = min(cell_w // 2 - 6, (cell_h - 2 * row - 8) // 2)
        if best is None or radius > best[0]:
            best = (radius, columns, cell_w, cell_h)
    _radius, columns, cell_w, cell_h = best
    for index, spec in enumerate(specs):
        col, line = index % columns, index // columns
        dial(screen, (rect.x + col * (cell_w + gap), rect.y + line * (cell_h + gap),
                      cell_w, cell_h), **spec)


def tank(screen, rect, fraction, *, label, text, level: str = "on",
         centred: bool = False) -> None:
    """A vertical tank column with 10 % marks; ``centred`` fills from the middle (-1..1)."""
    rect = pygame.Rect(rect)
    row = layout.font(16).get_linesize()
    tube = pygame.Rect(0, 0, min(34, rect.w - 8), rect.h - 2 * row - 8)
    tube.midtop = (rect.centerx, rect.y + row + 4)
    layout.blit_line(screen, label, (rect.x, rect.y, rect.w, row),
                     config.COLOR_TEXT_DIM, size=16, align="center")
    layout.blit_line(screen, text if not isinstance(text, str) else raw_text(text),
                     (rect.x, tube.bottom + 4, rect.w, row), level_color(level)
                     if level != "on" else config.COLOR_TEXT, size=16, align="center")
    if tube.h < 12 or tube.w < 6:
        return
    layout.record_geometry("tank", rect, str(label))
    pygame.draw.rect(screen, layout.METER_TRACK, tube)
    color = level_color(level)
    if fraction is not None and math.isfinite(fraction):
        if centred:
            value = max(-1.0, min(1.0, float(fraction)))
            half = tube.h // 2
            h = round(half * abs(value))
            fill = pygame.Rect(tube.x + 2, tube.centery - h if value > 0 else tube.centery, tube.w - 4, h)
        else:
            h = round(tube.h * max(0.0, min(1.0, float(fraction))))
            fill = pygame.Rect(tube.x + 2, tube.bottom - h, tube.w - 4, h)
        if fill.h:
            pygame.draw.rect(screen, _mix(config.COLOR_PANEL_BG, color, .55), fill)
            pygame.draw.line(screen, color, fill.topleft, (fill.right - 1, fill.y), 2)
    for i in range(1, 10):
        y = tube.bottom - round(tube.h * i / 10)
        pygame.draw.line(screen, config.COLOR_SONAR_RING, (tube.x, y),
                         (tube.x + (7 if i == 5 else 4), y), 1)
    if centred:
        pygame.draw.line(screen, config.COLOR_TEXT_DIM, (tube.x, tube.centery),
                         (tube.right - 1, tube.centery), 1)
    pygame.draw.rect(screen, layout.BRACKET_COLOR, tube, 1)


def badges(screen, center_x: int, y: int, numbers) -> None:
    """Numbered round badges (repair teams) centred on ``center_x``."""
    radius = 10
    numbers = list(numbers)
    x = center_x - (len(numbers) * (2 * radius + 4) - 4) // 2 + radius
    for number in numbers:
        pygame.draw.circle(screen, config.COLOR_OK, (x, y + radius), radius)
        layout.blit_line(screen, raw_text(str(number)), (x - radius, y + 1, 2 * radius, 2 * radius - 2),
                         config.COLOR_PANEL_BG, size=14, align="center")
        x += 2 * radius + 4


def room(screen, rect, name, *, flood: float, leds, teams=(),
         down: bool = False, bow: bool = False, stern: bool = False) -> None:
    """One compartment of the mimic: water level, name, a row of LEDs and the team."""
    rect = pygame.Rect(rect)
    layout.record_geometry("room", rect, str(name))
    pygame.draw.rect(screen, config.COLOR_PANEL_BG, rect)
    water = round(rect.h * max(0.0, min(100.0, float(flood))) / 100.0)
    if water:
        pygame.draw.rect(screen, _mix(config.COLOR_PANEL_BG, WATER, .6),
                         (rect.x + 1, rect.bottom - water, rect.w - 2, water))
        pygame.draw.line(screen, WATER, (rect.x + 1, rect.bottom - water),
                         (rect.right - 2, rect.bottom - water), 1)
    if bow:
        tip = (rect.x - min(26, rect.w // 3), rect.centery)
        pygame.draw.polygon(screen, config.COLOR_PANEL_BG, (rect.topleft, tip, rect.bottomleft))
        lines.lines(screen, layout.BRACKET_COLOR, False, (rect.topleft, tip, rect.bottomleft), 1)
    border = config.COLOR_DANGER if down else layout.BRACKET_COLOR
    pygame.draw.rect(screen, border, rect, 2 if down else 1)
    row = layout.font(16).get_linesize()
    layout.blit_line(screen, name, (rect.x + 3, rect.y + 4, rect.w - 6, row),
                     config.COLOR_TEXT, size=16, align="center")
    radius = 5
    spacing = 2 * radius + 6
    total = len(leds) * spacing - 6
    lx = rect.centerx - total // 2 + radius
    ly = rect.y + row + 14
    for index, level in enumerate(leds):
        led(screen, (lx + index * spacing, ly), radius, level)
    if teams:
        badges(screen, rect.centerx, rect.bottom - 26, teams)


def bearing_rose(screen, rect, strobes, *, course=None, title="") -> None:
    """A north-up direction-finding rose: dark scope, 10 degree ticks and one
    strobe per observed bearing. ``strobes`` are (bearing, color, width,
    spread_deg, inner) with ``inner`` the strobe's start as a radius fraction
    and ``spread_deg`` a dim wedge for the bearing's error (0: none)."""
    rect = pygame.Rect(rect)
    radius = min(rect.w, rect.h) // 2 - 20
    if radius < 30:
        return
    cx, cy = rect.centerx, rect.centery
    layout.record_geometry("instrument", rect, str(title))
    pygame.draw.circle(screen, (6, 13, 25), (cx, cy), radius)
    for fraction in (.33, .66):
        pygame.draw.circle(screen, config.COLOR_GRID, (cx, cy), round(radius * fraction), 1)
    for bearing, color, _width, spread, _inner in strobes:
        if spread > 0:
            steps = max(2, int(spread))
            wedge = [(cx, cy)] + [_polar(cx, cy, radius, bearing - spread + 2 * spread * i / steps)
                                  for i in range(steps + 1)]
            lines.polygon(screen, _mix((6, 13, 25), color, .22), wedge)
    pygame.draw.circle(screen, config.COLOR_SONAR_RING, (cx, cy), radius, 1)
    for step in range(0, 360, 10):
        major = step % 30 == 0
        lines.line(screen, config.COLOR_TEXT_DIM if major else config.COLOR_SONAR_RING,
                   _polar(cx, cy, radius - (7 if major else 3), step), _polar(cx, cy, radius, step), 1)
    row = layout.font(11).get_linesize()
    for step, label in ((0, "000"), (90, "090"), (180, "180"), (270, "270")):
        x, y = _polar(cx, cy, radius + (10 if step in (0, 180) else 20), step)
        layout.blit_line(screen, raw_text(label), (x - 16, y - row // 2, 32, row),
                         config.COLOR_TEXT_DIM, size=11, align="center")
    if course is not None and math.isfinite(course):
        lines.line(screen, config.COLOR_TEXT, (cx, cy), _polar(cx, cy, radius * .3, course), 2)
    for bearing, color, width, _spread, inner in strobes:
        lines.line(screen, color, _polar(cx, cy, radius * inner, bearing),
                   _polar(cx, cy, radius, bearing), width)
    pygame.draw.circle(screen, config.COLOR_OK, (cx, cy), 3)
