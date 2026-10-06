"""OPZ chart extras and the Display page (``src/core/opz_display.py``).

The bearing scale around the radar ring, track trails, the selected track's
closest point of approach, the layer chips under the chart and the Display
page's settings list.  Display only: everything is drawn from the OPZ's
published tracks, the chart history and own-ship truth.
"""

from __future__ import annotations

import math

import pygame

from src.core import config, opz_display
from src.core.i18n import localize, message
from src.ui import label_layout, layout, lines, pointer
from src.ui.stations.common import _observation_position

# Bearing scale: a tick every 10 degrees, a longer one and a number every 30.
COMPASS_TICK_PX = 5
COMPASS_MAJOR_PX = 9
# Below this ring radius the scale would be a blur: drawn without numbers.
COMPASS_NUMBERS_MIN_PX = 90
# Height of a range ring's distance label.
RANGE_LABEL_H = 18
# A CPA closer than this is drawn in the danger colour.
CPA_DANGER_NM = 2.0
CHIP_SIZE = 11
CHIP_GAP = 4


def _mix(color, background, weight: float):
    weight = max(0.0, min(1.0, weight))
    return tuple(int(round(b + (c - b) * weight)) for c, b in zip(color[:3], background[:3]))


def compass_numbers_shown(radius: float) -> bool:
    """Whether the bearing scale on a ring of ``radius`` carries numbers."""
    return radius >= COMPASS_NUMBERS_MIN_PX


def range_label_stride(radius: float, rings: int = 4) -> int:
    """Every how many range rings carry their distance: rings closer than a
    line of text label only every second (or only the outer) ring, so the
    labels never have to be pushed aside."""
    height = max(RANGE_LABEL_H, layout.font(layout.MIN_OPERATIONAL_FONT).get_linesize())
    stride = 1
    while stride < rings and radius * stride / rings < height + 2:
        stride *= 2
    return stride


def range_label_x(center_x: float, radius: float, ring_index: int, rings: int = 4) -> int:
    """Left edge of a range ring's distance label beside the north axis; the
    outer ring's label moves right of the scale's "000" when that is shown."""
    if ring_index == rings and compass_numbers_shown(radius):
        face = layout.font(layout.MIN_OPERATIONAL_FONT)
        return int(center_x + (layout.text_width(face, "000") + 2) / 2 + 4)
    return int(center_x) + 4


def draw_compass(surface, chart: pygame.Rect, center, radius: float, course: float) -> None:
    """Bearing scale on the outer radar ring and the own course mark."""
    if radius < 24:
        return
    cx, cy = center
    color = config.COLOR_SONAR_RING
    numbers = compass_numbers_shown(radius)
    for bearing in range(0, 360, 10):
        rad = math.radians(bearing)
        ux, uy = math.sin(rad), -math.cos(rad)
        major = bearing % 30 == 0
        inner = radius - (COMPASS_MAJOR_PX if major else COMPASS_TICK_PX)
        outer = (cx + ux * radius, cy + uy * radius)
        if not chart.collidepoint(outer):
            continue
        pygame.draw.line(surface, config.COLOR_TEXT_DIM if major else color,
                         (int(cx + ux * inner), int(cy + uy * inner)),
                         (int(outer[0]), int(outer[1])), 1)
        if major and numbers:
            text = f"{bearing:03d}"
            face = layout.font(layout.MIN_OPERATIONAL_FONT)
            width = layout.text_width(face, text) + 2
            height = face.get_linesize()
            depth = COMPASS_MAJOR_PX + 4 + height * .6
            box = pygame.Rect(int(cx + ux * (radius - depth) - width / 2),
                              int(cy + uy * (radius - depth) - height / 2), width, height)
            if not chart.contains(box):
                continue
            # Scale numbers stay at their bearing: a number pushed aside by
            # another label would read as a different bearing, so one whose
            # place the position line holds is left out.
            label_layout.blit_fixed(surface, text, box, config.COLOR_TEXT_DIM,
                                    size=layout.MIN_OPERATIONAL_FONT, skip_if_taken=True)
    # Own course: a small filled wedge pointing inward from the ring.
    rad = math.radians(course)
    ux, uy = math.sin(rad), -math.cos(rad)
    tip = (cx + ux * (radius - 12), cy + uy * (radius - 12))
    base = (cx + ux * (radius + 1), cy + uy * (radius + 1))
    if chart.collidepoint(base):
        px, py = -uy * 5, ux * 5
        pygame.draw.polygon(surface, config.COLOR_TEXT,
                            [(int(tip[0]), int(tip[1])),
                             (int(base[0] + px), int(base[1] + py)),
                             (int(base[0] - px), int(base[1] - py))])


def draw_trails(game, surface, chart: pygame.Rect, view, tracks, minutes: float,
                colors: dict) -> None:
    """Earlier OPZ positions of each positioned track, oldest faintest."""
    history = getattr(game, "chart_history", None)
    side = history.sides.get("frigate") if history is not None else None
    if side is None or minutes <= 0.0:
        return
    now = float(game.sim_t)
    for track in tracks:
        rows = side.opz_positions(track.track_id, now, minutes)
        if not rows:
            continue
        color = colors.get(track.track_id, config.COLOR_TEXT_DIM)
        count = len(rows)
        previous = None
        for index, (_t, x, y) in enumerate(rows):
            px, py = view.world_to_screen(x, y)
            weight = .2 + .6 * (index + 1) / count
            shade = _mix(color, config.COLOR_GEO_BG, weight)
            if previous is not None and (chart.collidepoint(px, py)
                                         or chart.collidepoint(previous)):
                lines.line(surface, _mix(color, config.COLOR_GEO_BG, weight * .45),
                           (int(previous[0]), int(previous[1])), (int(px), int(py)), 1)
            if chart.collidepoint(px, py):
                pygame.draw.circle(surface, shade, (int(px), int(py)), 2)
            previous = (px, py)


def selected_cpa(game, track):
    """The CPA of the selected OPZ track from its published motion."""
    if track is None:
        return None
    x, y = _observation_position(track)
    course = getattr(track, "course", None)
    speed = getattr(track, "speed_kn", None)
    ship = game.ship
    return opz_display.cpa(ship.x, ship.y, ship.course, ship.speed,
                           x, y, course, speed)


def _dashed(surface, color, start, end, dash: int = 6) -> None:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    steps = max(1, int(length // dash))
    for index in range(0, steps, 2):
        a = index / steps
        b = min(1.0, (index + 1) / steps)
        lines.line(surface, color,
                   (int(start[0] + (end[0] - start[0]) * a), int(start[1] + (end[1] - start[1]) * a)),
                   (int(start[0] + (end[0] - start[0]) * b), int(start[1] + (end[1] - start[1]) * b)), 1)


def draw_cpa(game, surface, chart: pygame.Rect, view, track) -> None:
    """Both tracks run on to the closest point of approach; a line joins
    the two CPA points and a label gives distance and time."""
    result = selected_cpa(game, track)
    if result is None:
        return
    distance, minutes, own_point, track_point = result
    color = config.COLOR_DANGER if distance < CPA_DANGER_NM else config.COLOR_WARN
    own_now = view.world_to_screen(game.ship.x, game.ship.y)
    x, y = _observation_position(track)
    track_now = view.world_to_screen(x, y)
    own_cpa = view.world_to_screen(*own_point)
    track_cpa = view.world_to_screen(*track_point)
    _dashed(surface, _mix(color, config.COLOR_GEO_BG, .55), own_now, own_cpa)
    _dashed(surface, _mix(color, config.COLOR_GEO_BG, .55), track_now, track_cpa)
    lines.line(surface, color, (int(own_cpa[0]), int(own_cpa[1])),
               (int(track_cpa[0]), int(track_cpa[1])), 1)
    for px, py in (own_cpa, track_cpa):
        pygame.draw.circle(surface, color, (int(px), int(py)), 3, 1)
    text = message("opz.cpa_label", distance=f"{distance:.1f}", minutes=f"{minutes:.0f}")
    mid = ((own_cpa[0] + track_cpa[0]) / 2, (own_cpa[1] + track_cpa[1]) / 2)
    if chart.collidepoint(mid):
        label_layout.blit_line(surface, text, (int(mid[0]) + 8, int(mid[1]) - 8, 150, 18),
                               color, size=12)


def short_label(label) -> str:
    text = str(label)
    return text if len(text) <= 6 else text[:6]


def track_label(values: dict, label):
    """The chart label of a track under the label setting (None: none)."""
    mode = values["labels"]
    if mode == "off":
        return None
    return short_label(label) if mode == "brief" else label


def _chip_text(key: str, value: str) -> str:
    if key in ("trails", "vectors"):
        shown = localize("opz.display.value.off") if value == "off" else value
        return message("opz.chip." + key, value=shown)
    if key == "labels":
        return message("opz.chip.labels", value=localize("opz.display.value." + value))
    return localize("opz.chip." + key)


def chip_rects(game, rect: pygame.Rect) -> list:
    """``(key, rect, text, on)`` of the chips, right-aligned in ``rect``."""
    values = game.opz_display_settings()
    face = layout.font(CHIP_SIZE)
    chips = []
    for key in opz_display.CHIP_KEYS:
        text = _chip_text(key, values[key])
        chips.append((key, text, values[key] != "off",
                      layout.text_width(face, localize(text)) + 10))
    x = rect.right
    placed = []
    for key, text, on, width in reversed(chips):
        x -= width
        if x < rect.x:
            break
        placed.append((key, pygame.Rect(x, rect.y, width, rect.h), text, on))
        x -= CHIP_GAP
    return list(reversed(placed))


def draw_chips(game, surface, rect: pygame.Rect) -> None:
    """Layer chips: lit when the layer is drawn; a click moves it on."""
    for key, chip, text, on in chip_rects(game, rect):
        pygame.draw.rect(surface, config.COLOR_TAB_ACTIVE if on else config.COLOR_PANEL_BG, chip)
        pygame.draw.rect(surface, config.COLOR_SONAR_RING if on else config.COLOR_GRID, chip, 1)
        layout.blit_line(surface, text, chip,
                         config.COLOR_TEXT if on else config.COLOR_TEXT_DIM,
                         size=CHIP_SIZE, align="center")
        pointer.add_action(chip, lambda _pos, key=key: game.step_opz_display(key, 1))
        # The short chip says what it switches, and what it is set to now.
        pointer.add_tip(chip, _chip_tip(game, key))


def _chip_tip(game, key: str):
    """The chip's hover note: its full name, its setting and what a click does."""
    from src.core import status_tips
    values = game.opz_display_settings()
    tip = status_tips.note(f"commander.web.opz_display_{key}",
                           _value_text(key, values[key]),
                           "opz.chip.tip_click")
    return lambda: status_tips.payload(tip)


def _value_text(key: str, value: str) -> str:
    if key in ("trails", "vectors") and value != "off":
        return message("opz.display.value.minutes", minutes=value)
    return localize("opz.display.value." + value)


def draw_display_page(game, surface, x: int, y: int, w: int, bottom: int) -> None:
    """The Display page: one row per setting, the selected one framed."""
    values = game.opz_display_settings()
    count = len(opz_display.KEYS)
    selected = int(getattr(game, "opz_display_sel", 0)) % count
    hint_h = 65
    row_h = max(20, min(28, (bottom - y - hint_h) // count))
    value_w = max(72, int(w * .38))
    for index, key in enumerate(opz_display.KEYS):
        row = pygame.Rect(x, y, w, row_h - 2)
        active = index == selected
        if active:
            pygame.draw.rect(surface, config.COLOR_SELECT_BG, row)
        value = values[key]
        on = value != "off"
        layout.blit_line(surface, "opz.display.option." + key,
                         (x + 6, y, w - value_w - 12, row_h - 2),
                         config.COLOR_TEXT if active else config.COLOR_TEXT_DIM, size=14)
        value_rect = pygame.Rect(x + w - value_w, y, value_w - 4, row_h - 2)
        layout.blit_line(surface, message("opz.display.value_row", value=_value_text(key, value)),
                         value_rect, config.COLOR_OK if on else config.COLOR_TEXT_DIM,
                         size=14, align="right")

        def pick(_pos, index=index, key=key):
            game.opz_display_sel = index
            game.step_opz_display(key, 1)

        pointer.add_action(row, pick)
        y += row_h
    # Three short key lines, every key clickable.
    for index, (key, tokens) in enumerate((
            ("opz.display.hint", (("↑/↓", "↑/↓"), ("←/→", "←/→"))),
            ("opz.display.hint_reset", (("Backspace", "Backspace"),)),
            ("opz.display.hint_reset_all", (("Shift+Backspace", "Shift+Backspace"),)))):
        rect = (x, bottom - hint_h + 2 + index * 21, w, 20)
        layout.blit_line(surface, key, rect, config.COLOR_TEXT_DIM, size=13)
        pointer.add_token_keys(rect, localize(key), 13, tokens, screen=surface)


def radar_switch_rects(chart: pygame.Rect) -> list:
    """``(domain, rect)`` of the two radar switches in the chart's top left."""
    face = layout.font(12)
    rects, x = [], chart.x + 6
    for domain in ("surface", "air"):
        width = max(layout.text_width(face, localize("opz.radar_switch." + domain + "." + state))
                    for state in ("on", "off")) + 14
        rects.append((domain, pygame.Rect(x, chart.y + 6, width, 22)))
        x += width + 4
    return rects


def draw_radar_switches(game, surface, chart: pygame.Rect, live: bool) -> None:
    """Surface and air radar on/off as two lit switches on the chart (R and
    Shift+R; a click presses the same key, with its EMCON report)."""
    for domain, rect in radar_switch_rects(chart):
        on = bool(game.air_radar_on if domain == "air" else game.surface_radar_on)
        lit = on and live
        pygame.draw.rect(surface, config.COLOR_TAB_ACTIVE if lit else config.COLOR_PANEL_BG, rect)
        pygame.draw.rect(surface, config.COLOR_OK if lit else config.COLOR_SONAR_RING, rect, 1)
        pygame.draw.circle(surface, config.COLOR_OK if lit else config.COLOR_TEXT_DIM,
                           (rect.x + 7, rect.centery), 3, 0 if lit else 1)
        layout.blit_line(surface, "opz.radar_switch." + domain + (".on" if on else ".off"),
                         (rect.x + 12, rect.y, rect.w - 14, rect.h),
                         config.COLOR_TEXT if lit else config.COLOR_TEXT_DIM, size=12, align="center")
        pointer.add_key(rect, pygame.K_r, pygame.KMOD_SHIFT if domain == "air" else 0)
