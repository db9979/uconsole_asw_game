"""Damage-control page of the crewed submarine's engine room (uConsole).

Own-ship state only (``src/enemies/damage_control.py``): the six
compartments from stern (left) to bow (right) as a mimic with their water,
fire, gas and bulkheads on LEDs, the picked compartment's numbers on lamps,
and the two teams with the order the operator is about to give.
"""

import pygame

from src.core import config
from src.core.i18n import message, raw_text
from src.enemies.damage_control import COMPARTMENTS, TASKS, capacity_kg
from src.ui import console, layout, lines

_GAS = (150, 190, 60)


def selection(boat) -> tuple:
    """The compartment and task the operator has picked (display state)."""
    index = boat.dc_selected % len(COMPARTMENTS)
    task = boat.dc_task if boat.dc_task in TASKS else "seal"
    return index, task


def _alert(control, index) -> tuple:
    c = control.compartments[index]
    if c.fire > 0.0 or control.down(COMPARTMENTS[index]) or (
            COMPARTMENTS[index] == "battery" and not control.power()):
        return config.COLOR_DANGER
    if c.leak > 0.0 or c.chlorine > 0.0 or c.water_kg > 0.0:
        return config.COLOR_WARN
    return None


def _levels(control, index) -> dict:
    """LED levels of one compartment: leak, fire, gas and its bulkheads."""
    c = control.compartments[index]
    return {"leak": "caution" if c.leak > 0.0 else "off",
            "fire": "alarm" if c.fire > 0.0 else "off",
            "gas": "alarm" if c.chlorine > 0.0 else "off",
            "bulkhead": "on" if c.closed else "off"}


LEDS = ("leak", "fire", "gas", "bulkhead")


def draw_boat_compartments(s, control, rect, selected=None) -> None:
    """The pressure hull as a compartment mimic, bow to the right.

    Every compartment shows its water level, a fire glow, a gas haze, the
    leak/fire/gas/bulkhead LEDs, the water in tonnes and the teams inside.
    """
    rect = pygame.Rect(rect)
    count = len(COMPARTMENTS)
    legend_h = layout.line_pitch(16, 0) + 4
    hull = pygame.Rect(rect.x + 24, rect.y + 4, rect.w - 58, rect.h - legend_h - 10)
    stern = (rect.x + 4, hull.centery)
    bow = (rect.right - 4, hull.centery)
    outline = (hull.topleft, hull.topright,
               (hull.right + 14, hull.y + hull.h // 5), bow,
               (hull.right + 14, hull.bottom - hull.h // 5), hull.bottomright,
               hull.bottomleft, stern)
    pygame.draw.polygon(s, config.COLOR_PANEL_BG, outline)
    seg_w = hull.w / count
    row = layout.font(16).get_linesize()
    for index in range(count):
        c = control.compartments[index]
        left = hull.x + int(round((count - 1 - index) * seg_w))
        right = hull.x + int(round((count - index) * seg_w))
        cell = pygame.Rect(left, hull.y, right - left, hull.h)
        fraction = max(0.0, min(1.0, c.water_kg / capacity_kg(index)))
        water = round(cell.h * fraction)
        if water:
            pygame.draw.rect(s, console._mix(config.COLOR_PANEL_BG, console.WATER, .6),
                             (cell.x, cell.bottom - water, cell.w, water))
            pygame.draw.line(s, console.WATER, (cell.x, cell.bottom - water),
                             (cell.right - 1, cell.bottom - water), 1)
        if c.chlorine > 0.0 or c.fire > 0.0:
            layer = pygame.Surface(cell.size, pygame.SRCALPHA)
            if c.chlorine > 0.0:
                layer.fill((*_GAS, round(30 + 60 * min(1.0, c.chlorine))))
            if c.fire > 0.0:
                for step in range(4, 0, -1):
                    alpha = min(220, round(40 + 150 * min(1.0, c.fire) * (5 - step) / 4))
                    pygame.draw.ellipse(layer, (255, 110 + 20 * step, 50, alpha),
                                        (cell.w // 2 - cell.w * step // 8,
                                         cell.h // 2 - cell.h * step // 8,
                                         cell.w * step // 4, cell.h * step // 4))
            s.blit(layer, cell.topleft)
        alert = _alert(control, index)
        border = config.COLOR_TEXT if selected == index else alert or layout.BRACKET_COLOR
        layout.record_geometry("room", cell, f"uboot.compartment.{COMPARTMENTS[index]}")
        layout.blit_line(s, f"uboot.dc.room.{COMPARTMENTS[index]}",
                         (cell.x + 3, cell.y + 4, cell.w - 6, row),
                         config.COLOR_TEXT, size=16, align="center")
        radius, spacing = 5, 16
        lx = cell.centerx - (len(LEDS) * spacing - 6) // 2 + radius
        levels = _levels(control, index)
        for number, name in enumerate(LEDS):
            console.led(s, (lx + number * spacing, cell.y + row + 14), radius, levels[name])
        layout.blit_line(s, raw_text(f"{c.water_kg / 1000.0:.1f} t"),
                         (cell.x + 3, cell.y + row + 24, cell.w - 6, row),
                         config.COLOR_WARN if c.water_kg > 0.0 else config.COLOR_TEXT_DIM,
                         size=16, align="center")
        teams = [team + 1 for team in control.teams_in(COMPARTMENTS[index])]
        if teams:
            console.badges(s, cell.centerx, cell.bottom - 26, teams)
        pygame.draw.rect(s, border, cell, 2 if selected == index or alert else 1)
        if c.closed:
            for edge in (cell.left, cell.right - 1):
                pygame.draw.line(s, config.COLOR_WARN, (edge, cell.y - 3),
                                 (edge, cell.bottom + 2), 3)
    lines.lines(s, layout.BRACKET_COLOR, True, outline, 1)
    # LED legend under the hull.
    legend_y = rect.bottom - legend_h
    width = rect.w // len(LEDS)
    for number, name in enumerate(LEDS):
        x = rect.x + number * width
        level = {"leak": "caution", "fire": "alarm", "gas": "alarm", "bulkhead": "on"}[name]
        console.led(s, (x + 10, legend_y + legend_h // 2), 5, level)
        layout.blit_line(s, f"uboot.dc.lamp.{name}", (x + 20, legend_y, width - 24, legend_h),
                         config.COLOR_TEXT_DIM, size=16)


def _pct(value: float) -> str:
    return f"{value * 100.0:.0f}"


def draw_damage_page(s, game, boat, x, y, w, h) -> None:
    """Compartment picture, the table of compartments and the two teams."""
    control = boat.sub.damage_control
    selected, task = selection(boat)
    alarm = any(_alert(control, index) == config.COLOR_DANGER for index in range(len(COMPARTMENTS)))
    mimic_h = min(230, max(170, h * 2 // 5))
    picture = layout.box(s, (x, y, w, mimic_h), "uboot.panel.compartments",
                         border=config.COLOR_DANGER if alarm else config.COLOR_TEXT)
    draw_boat_compartments(s, control, picture, selected)
    # The picked compartment as an annunciator: its numbers on lamps.
    table_y = y + mimic_h + 8
    c = control.compartments[selected]
    levels = _levels(control, selected)
    rows = [("uboot.dc.lamp.water", raw_text(f"{c.water_kg / 1000.0:.1f} t"),
             "caution" if c.water_kg > 0.0 else "off"),
            ("uboot.dc.lamp.leak", raw_text(f"{_pct(c.leak)} %"), levels["leak"]),
            ("uboot.dc.lamp.fire", raw_text(f"{_pct(c.fire)} %"), levels["fire"]),
            ("uboot.dc.lamp.gas", raw_text(f"{_pct(c.chlorine)} %"), levels["gas"]),
            ("uboot.dc.lamp.bulkhead", "uboot.dc.closed" if c.closed else "uboot.dc.open",
             levels["bulkhead"]),
            ("uboot.dc.lamp.power",
             "uboot.dc.power_on" if control.power() else "uboot.dc.power_off_short",
             "on" if control.power() else "alarm")]
    grid_h = 2 * 36 + 4
    name_h = layout.line_pitch(18, 2)
    table_h = layout.line_pitch(16, 16, bold=True) + name_h + grid_h + 8
    tx, ty, tw, _th = layout.box(s, (x, table_y, w, table_h), "uboot.panel.dc_status",
                                 border=_alert(control, selected) or config.COLOR_TEXT)
    console.led(s, (tx + 7, ty + name_h // 2), 6,
                "alarm" if _alert(control, selected) == config.COLOR_DANGER else
                "caution" if _alert(control, selected) else "on")
    layout.blit_line(s, f"uboot.compartment.{COMPARTMENTS[selected]}",
                     (tx + 20, ty, tw - 20, name_h), config.COLOR_TEXT, size=18)
    console.lamp_grid(s, (tx, ty + name_h, tw, grid_h), rows, 3)
    teams_y = table_y + table_h + 8
    bx, by, bw, bh = layout.box(s, (x, teams_y, w, max(60, y + h - teams_y)),
                                "uboot.panel.dc_teams",
                                border=config.COLOR_TEXT if control.power() else config.COLOR_DANGER)
    rows = [] if control.power() else [
        ("uboot.dc.label.power", message("uboot.dc.power_off"), config.COLOR_DANGER)]
    for number, team in enumerate(control.teams):
        state = (message("uboot.dc.team_transit", compartment=message(
                     f"uboot.compartment.{team['compartment']}"),
                     seconds=f"{team['transit_s']:.0f}")
                 if team["transit_s"] > 0.0 else
                 message("uboot.dc.team_at", compartment=message(
                     f"uboot.compartment.{team['compartment']}"),
                     task=message(f"uboot.dc.task.{team['task']}")))
        rows.append((message("uboot.dc.label.team", number=number + 1), state, None))
    watch = boat.watch
    rows.append(("uboot.dc.label.crew", message(
        "uboot.dc.crew", state=message(
            "uboot.dc.crew_action" if watch.action_stations else "uboot.dc.crew_watch",
            watch=str(watch.on_watch + 1)),
        effect=f"{watch.effectiveness(game.sim_t) * 100:.0f}",
        fatigue=f"{watch.duty_fatigue() * 100:.0f}",
        morale=f"{watch.morale * 100:.0f}"),
        config.COLOR_WARN if watch.effectiveness(game.sim_t) < 0.9 else None))
    rows.append(("uboot.dc.label.order", message(
        "uboot.dc.order", compartment=message(f"uboot.compartment.{COMPARTMENTS[selected]}"),
        task=message(f"uboot.dc.task.{task}")), config.COLOR_WARN))
    for index, (label, value, color) in enumerate(rows):
        if (index + 1) * 20 > bh:
            break
        layout.status_line(s, bx, by + index * 20, bw, label, value, color=color,
                           size=15, label_w=150)
