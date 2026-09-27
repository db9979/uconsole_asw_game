"""Horizon view shared by the periscope and the bridge lookout page.

Sky and sea in the light of the hour, haze from the visibility, the
horizon in motion from the wave slope, a true-bearing scale, an optional
crosshair and procedural outlines of what the eye made out.  Callers pass
detached ``(bearing, span_deg, cls, stale)`` rows; nothing here reads an
entity.
"""

import math

import pygame

from src.core import config
from src.core.i18n import raw_text
from src.physics import ship_dynamics
from src.ui import layout

# Outline height over apparent length by class (dimensionless).
HEIGHT_RATIO = {"warship": 0.24, "merchant": 0.17, "unknown": 0.15,
                "aircraft": 0.45, "torpedo": 0.04}
SKY_DAY = ((25, 70, 92), (111, 151, 157))
SKY_NIGHT = ((5, 14, 27), (38, 53, 62))
SEA_DAY, SEA_NIGHT = (9, 54, 67), (7, 35, 48)
HAZE = (150, 160, 165)
SCALE_COLOR = (220, 225, 225)
CROSSHAIR_COLOR = (235, 235, 210)
# Horizon motion: px per rad of wave slope, bounded.
MOTION_PX_PER_RAD = 260.0


def relative_offset(bearing: float, line_of_sight: float) -> float:
    """Signed angle from the line of sight to ``bearing`` (-180..180)."""
    return (bearing - line_of_sight + 180.0) % 360.0 - 180.0


def blend(a, b, t: float) -> tuple:
    t = config.clamp(t, 0.0, 1.0)
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def horizon_motion(seed: int, sim_t: float, sea_state: float) -> tuple:
    """(vertical offset px, tilt rad) of the horizon from the wave slope at
    ``seed`` (display only, deterministic in sim time)."""
    slope = ship_dynamics.wave_slope_rad(int(seed), sim_t, sea_state)
    offset = config.clamp(slope * MOTION_PX_PER_RAD, -40.0, 40.0)
    tilt = config.clamp(slope * 0.6, -0.25, 0.25)
    return offset, tilt


def draw_outline(s, cls: str, cx: int, base_y: int, width: int, color) -> None:
    """Procedural outline of a coarse class, ``width`` px long, sitting on the
    horizon (aircraft: hovering above it)."""
    width = max(3, int(width))
    height = max(2, int(width * HEIGHT_RATIO.get(cls, 0.15)))
    left = cx - width // 2
    if cls == "torpedo":
        pygame.draw.line(s, (215, 225, 225), (left, base_y + 1), (left + width, base_y + 1),
                         max(1, min(3, width // 12)))
        return
    if cls == "aircraft":
        body_y = base_y - height * 3
        pygame.draw.ellipse(s, color, (left, body_y, width, max(2, height // 2)))
        pygame.draw.line(s, color, (left - width // 6, body_y - 2),
                         (left + width + width // 6, body_y - 2), 1)
        pygame.draw.line(s, color, (left + width * 3 // 4, body_y),
                         (left + width, body_y - height // 2), 1)
        return
    hull_h = max(1, height // 3)
    bow = width // 10
    pygame.draw.polygon(s, color, [(left + bow, base_y - hull_h), (left + width, base_y - hull_h),
                                   (left + width - bow // 2, base_y), (left, base_y)])
    if cls == "warship":
        block_w, block_h = width // 3, height - hull_h
        block_x = left + width // 3
        pygame.draw.rect(s, color, (block_x, base_y - hull_h - block_h, block_w, block_h))
        pygame.draw.rect(s, color, (block_x + block_w // 3, base_y - height - height // 4,
                                    max(1, block_w // 6), height // 4 + 1))
        pygame.draw.line(s, color, (block_x + block_w // 2, base_y - height),
                         (block_x + block_w // 2, base_y - height - height // 2), 1)
        pygame.draw.rect(s, color, (left + width * 3 // 4, base_y - hull_h - block_h // 2,
                                    max(1, width // 12), block_h // 2))
    elif cls == "merchant":
        block_w, block_h = width // 6, height - hull_h
        block_x = left + width - width // 5
        pygame.draw.rect(s, color, (block_x, base_y - hull_h - block_h, block_w, block_h))
        pygame.draw.rect(s, color, (block_x + block_w // 3, base_y - height - height // 3,
                                    max(1, block_w // 4), height // 3 + 1))
        for post in range(1, 4):
            px = left + bow + post * (width - width // 5 - bow) // 4
            pygame.draw.line(s, color, (px, base_y - hull_h), (px, base_y - height), 1)
    else:
        pygame.draw.rect(s, color, (left + width // 3, base_y - height,
                                    width // 3, height - hull_h))


def draw_horizon(s, rect, *, line_of_sight: float, fov_deg: float, night: bool,
                 visibility_nm: float, motion: tuple, outlines, crosshair_deg=None) -> None:
    """The picture in the eyepiece or binoculars: sky, sea, the horizon in
    motion, the true-bearing scale, the outlines within the field and an
    optional crosshair with its measuring window (half width in degrees)."""
    rect = pygame.Rect(rect)
    haze = 1.0 - config.clamp(visibility_nm / config.WEATHER_VISIBILITY_MAX_NM, 0.0, 1.0)
    sky_top, sky_bottom = SKY_NIGHT if night else SKY_DAY
    sea = SEA_NIGHT if night else SEA_DAY
    haze_color = blend(HAZE, (40, 48, 54), 0.8 if night else 0.0)
    offset, tilt = motion
    horizon = rect.y + int(rect.h * 0.5 + offset)
    with layout.clip_to(s, rect):
        for py in range(rect.y, rect.bottom):
            t = (py - rect.y) / max(1, rect.h - 1)
            pygame.draw.line(s, blend(blend(sky_top, sky_bottom, t), haze_color, haze * 0.6),
                             (rect.x, py), (rect.right, py))
        dy = int(math.tan(tilt) * rect.w / 2)
        sea_color = blend(sea, haze_color, haze * 0.4)
        pygame.draw.polygon(s, sea_color, [(rect.x, horizon - dy), (rect.right, horizon + dy),
                                           (rect.right, rect.bottom), (rect.x, rect.bottom)])
        pygame.draw.line(s, blend(sea_color, (200, 210, 210), 0.35),
                         (rect.x, horizon - dy), (rect.right, horizon + dy), 1)
        px_per_deg = rect.w / fov_deg
        dark = (60, 66, 72) if night else (28, 34, 40)
        for bearing, span_deg, cls, stale in outlines:
            off = relative_offset(bearing, line_of_sight)
            if abs(off) > fov_deg / 2 + span_deg / 2:
                continue
            cx = rect.centerx + int(off * px_per_deg)
            base = horizon + int(math.tan(tilt) * (cx - rect.centerx))
            width = min(rect.w, max(3, int(span_deg * px_per_deg)))
            draw_outline(s, cls, cx, base, width,
                         blend(dark, haze_color, 0.5 if stale else haze * 0.5))
        first = int(math.floor((line_of_sight - fov_deg / 2) / 5.0)) * 5
        for tick in range(first, first + int(fov_deg) + 10, 5):
            off = relative_offset(tick, line_of_sight)
            if abs(off) > fov_deg / 2:
                continue
            tx = rect.x + int((off + fov_deg / 2) * px_per_deg)
            major = tick % 10 == 0
            pygame.draw.line(s, SCALE_COLOR, (tx, rect.y), (tx, rect.y + (10 if major else 5)), 1)
            if major and rect.h >= 40:
                layout.blit_line(s, raw_text(f"{tick % 360:03d}"), (tx - 16, rect.y + 11, 32, 13),
                                 SCALE_COLOR, size=11, align="center")
        if crosshair_deg is not None:
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx, rect.y + 26),
                             (rect.centerx, rect.bottom), 1)
            window = int(crosshair_deg * px_per_deg)
            pygame.draw.line(s, CROSSHAIR_COLOR, (rect.centerx - window, rect.centery),
                             (rect.centerx + window, rect.centery), 1)
        pygame.draw.rect(s, CROSSHAIR_COLOR, rect, 1)
