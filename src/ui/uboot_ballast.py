"""Tanks page of the crewed submarine's engine room (uConsole).

Own-ship state only: main ballast, regulating and trim tanks, the air
bottles and the trim the boat is in (``src/enemies/ballast.py``).  A small
cross-section shows the tank fills; the numbers beside it are what the crew
orders against.
"""

import math

import pygame

from src.core import config
from src.core.i18n import message
from src.enemies.ballast import flooding_kg
from src.ui import layout, lines


def _fmt(value, pattern="{:.0f}"):
    return "--" if value is None or not math.isfinite(value) else pattern.format(value)


def _tonnes(kg: float) -> str:
    return f"{kg / 1000.0:+.1f}"


def _tank(s, rect, fraction, color) -> None:
    """One tank: its outline and the water in it from the bottom up."""
    rect = pygame.Rect(rect)
    fraction = max(0.0, min(1.0, fraction))
    water = rect.copy()
    water.h = int(round(rect.h * fraction))
    water.bottom = rect.bottom
    if water.h > 0:
        pygame.draw.rect(s, color, water)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)


def draw_cross_section(s, sub, rect) -> None:
    """Hull with the tanks (bow to the right) and the trim angle above it."""
    ballast = sub.ballast
    rect = pygame.Rect(rect)
    cx, cy = rect.centerx, rect.y + int(rect.h * 0.64)
    half_w, half_h = rect.w // 2 - 8, max(14, int(rect.h * 0.3))
    hull = [(cx - half_w, cy), (cx - half_w + 20, cy - half_h), (cx + half_w - 30, cy - half_h),
            (cx + half_w, cy), (cx + half_w - 30, cy + half_h), (cx - half_w + 20, cy + half_h)]
    pygame.draw.polygon(s, config.COLOR_TEXT_DIM, hull, 1)
    water = config.COLOR_SONAR_RING
    tank_h = half_h * 2 - 8
    top = cy - half_h + 4
    main_w = max(18, half_w // 4)
    # Main ballast fore and aft.
    _tank(s, (cx - half_w + 22, top, main_w, tank_h), ballast.mbt, water)
    _tank(s, (cx + half_w - 32 - main_w, top, main_w, tank_h), ballast.mbt, water)
    # Trim tanks at the ends of the pressure hull, the regulating tank amidships.
    trim_cap = config.UBOOT_TRIM_TANK_KG
    fore = 0.5 + 0.5 * ballast.trim_kg / trim_cap
    small_w, small_h = max(14, half_w // 7), max(10, tank_h // 2)
    _tank(s, (cx + half_w // 2 - small_w, cy - small_h // 2, small_w, small_h), fore,
          config.COLOR_WARN)
    _tank(s, (cx - half_w // 2, cy - small_h // 2, small_w, small_h), 1.0 - fore,
          config.COLOR_WARN)
    reg_cap = config.UBOOT_REGULATING_KG
    _tank(s, (cx - small_w, cy - small_h // 2, small_w * 2, small_h),
          0.5 + 0.5 * ballast.regulating_kg / reg_cap, config.COLOR_OK)
    # Trim angle, drawn four times steeper so a degree can be seen (and no
    # steeper than the space above the hull).
    reach = half_w - 10
    y0 = rect.y + max(10, (cy - half_h - rect.y) // 2)
    limit = math.degrees(math.asin(min(1.0, max(2.0, y0 - rect.y - 2) / reach)))
    angle = math.radians(max(-limit, min(limit, ballast.trim_deg() * 4.0)))
    lines.line(s, config.COLOR_TEXT_DIM, (cx - reach, y0), (cx + reach, y0), 1)
    color = (config.COLOR_WARN if abs(ballast.trim_deg()) > config.UBOOT_TRIM_WARN_DEG
             else config.COLOR_OK)
    lines.line(s, color, (cx - reach * math.cos(angle), y0 - reach * math.sin(angle)),
               (cx + reach * math.cos(angle), y0 + reach * math.sin(angle)), 2)


def _state_text(ballast) -> str:
    if ballast.blowing:
        return "uboot.ballast.blowing"
    if ballast.venting:
        return "uboot.ballast.venting"
    return "uboot.ballast.dived" if ballast.dived() else "uboot.ballast.blown"


def draw_ballast_page(s, game, boat, x, y, w, h) -> None:
    """Main ballast and air, then the trim: tanks, set points and residual."""
    sub = boat.sub
    ballast = sub.ballast
    damage = sub.damage
    residual = ballast.residual_kg(damage)
    drift = ballast.vertical_drift_mps(damage, sub.speed)
    trim = ballast.trim_deg()
    out_of_trim = (abs(residual) > config.UBOOT_HEAVY_WARN_KG
                   or abs(trim) > config.UBOOT_TRIM_WARN_DEG)
    section = layout.box(s, (x, y, w, 130), "uboot.panel.tanks",
                         border=config.COLOR_WARN if out_of_trim else config.COLOR_TEXT)
    draw_cross_section(s, sub, section)
    tanks_y = y + 138
    box = layout.box(s, (x, tanks_y, w, 96), "uboot.panel.hp_air",
                     border=(config.COLOR_WARN if ballast.blows_left() == 0
                             else config.COLOR_TEXT))
    bx, by, bw, _ = box
    layout.status_line(s, bx, by, bw, "uboot.ballast.label.main",
                       message(_state_text(ballast), pct=_fmt(ballast.mbt * 100.0)),
                       color=config.COLOR_WARN if not ballast.dived() else None,
                       size=15, label_w=150)
    compressor = (sub.snorkeling and sub.snorkel_rate != "vent"
                  and ballast.hp_air_bar < config.UBOOT_HP_AIR_MAX_BAR)
    layout.status_line(s, bx, by + 22, bw, "uboot.ballast.label.air",
                       message("uboot.ballast.air_compressor" if compressor
                               else "uboot.ballast.air", bar=_fmt(ballast.hp_air_bar),
                               max=_fmt(config.UBOOT_HP_AIR_MAX_BAR),
                               blows=ballast.blows_left()),
                       size=15, label_w=150)
    fraction = ballast.hp_air_bar / config.UBOOT_HP_AIR_MAX_BAR
    rect = pygame.Rect(bx, by + 46, bw, 10)
    pygame.draw.rect(s, config.COLOR_BG, rect)
    fill = rect.copy()
    fill.w = int(rect.w * max(0.0, min(1.0, fraction)))
    pygame.draw.rect(s, config.COLOR_DANGER if ballast.blows_left() == 0
                     else config.COLOR_OK, fill)
    pygame.draw.rect(s, config.COLOR_SONAR_RING, rect, 1)
    trim_y = tanks_y + 104
    trim_box = layout.box(s, (x, trim_y, w, max(60, y + h - trim_y)), "uboot.panel.trim",
                          border=config.COLOR_WARN if out_of_trim else config.COLOR_TEXT)
    tx, ty, tw, th = trim_box
    heavy = ("uboot.ballast.heavy" if residual > config.UBOOT_PUMP_DEADBAND_KG
             else "uboot.ballast.light" if residual < -config.UBOOT_PUMP_DEADBAND_KG
             else "uboot.ballast.neutral")
    rows = [
        ("uboot.ballast.label.auto", message("uboot.ballast.auto_on" if ballast.auto
                                             else "uboot.ballast.auto_off"), None),
        ("uboot.ballast.label.regulating", message(
            "uboot.ballast.tank", value=_tonnes(ballast.regulating_kg),
            order=_tonnes(ballast.regulating_order_kg)), None),
        ("uboot.ballast.label.trim_tanks", message(
            "uboot.ballast.tank", value=_tonnes(ballast.trim_kg),
            order=_tonnes(ballast.trim_order_kg)), None),
        ("uboot.ballast.label.balance", message(heavy, weight=f"{abs(residual) / 1000.0:.1f}"),
         config.COLOR_WARN if abs(residual) > config.UBOOT_HEAVY_WARN_KG else None),
        ("uboot.ballast.label.angle", message("uboot.ballast.angle", angle=f"{trim:+.1f}"),
         config.COLOR_WARN if abs(trim) > config.UBOOT_TRIM_WARN_DEG else None),
        ("uboot.ballast.label.drift", message("uboot.ballast.drift", rate=f"{drift:+.2f}"),
         None),
        ("uboot.ballast.label.flooding", message(
            "uboot.ballast.weight", weight=f"{flooding_kg(damage) / 1000.0:.1f}"),
         config.COLOR_DANGER if damage > 30.0 else None),
        ("uboot.ballast.label.pumps", message("uboot.ballast.pumps_on" if ballast.pumping
                                              else "uboot.ballast.pumps_off"),
         config.COLOR_WARN if ballast.pumping else None),
    ]
    for index, (label, value, color) in enumerate(rows):
        if (index + 1) * 20 > th:
            break
        layout.status_line(s, tx, ty + index * 20, tw, label, value, color=color,
                           size=15, label_w=180)
