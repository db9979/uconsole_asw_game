"""Damage-control page of the crewed submarine's engine room (uConsole).

Own-ship state only (``src/enemies/damage_control.py``): the six
compartments from stern (left) to bow (right) with their water, fire, gas
and bulkheads, a table of the numbers, and the two teams with the order the
operator is about to give.
"""

import pygame

from src.core import config
from src.core.i18n import message
from src.enemies.damage_control import COMPARTMENTS, TASKS, capacity_kg
from src.ui import layout

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


def draw_boat_compartments(s, control, rect, selected=None) -> None:
    """The pressure hull cut into its compartments, bow to the right."""
    rect = pygame.Rect(rect)
    count = len(COMPARTMENTS)
    hull = rect.inflate(-16, -24)
    seg_w = hull.w / count
    for index in range(count):
        c = control.compartments[index]
        left = hull.x + int(round((count - 1 - index) * seg_w))
        right = hull.x + int(round((count - index) * seg_w))
        cell = pygame.Rect(left, hull.y, right - left, hull.h)
        fraction = max(0.0, min(1.0, c.water_kg / capacity_kg(index)))
        water = cell.copy()
        water.h = int(round(cell.h * fraction))
        water.bottom = cell.bottom
        if water.h > 0:
            pygame.draw.rect(s, config.COLOR_SONAR_RING, water)
        if c.chlorine > 0.0:
            gas = cell.inflate(-6, -6)
            pygame.draw.rect(s, _GAS, gas, max(1, int(round(3 * c.chlorine))))
        if c.fire > 0.0:
            flame = pygame.Rect(cell.x + 3, cell.y + 3, max(1, int((cell.w - 6) * c.fire)), 6)
            pygame.draw.rect(s, config.COLOR_DANGER, flame)
        if c.leak > 0.0:
            pygame.draw.circle(s, config.COLOR_WARN, (cell.centerx, cell.bottom - 6),
                               max(2, int(round(5 * c.leak))))
        border = config.COLOR_TEXT if selected == index else config.COLOR_TEXT_DIM
        pygame.draw.rect(s, border, cell, 2 if selected == index else 1)
        if c.closed:
            for edge in (cell.left, cell.right - 1):
                pygame.draw.line(s, config.COLOR_WARN, (edge, cell.y - 4),
                                 (edge, cell.bottom + 3), 3)
        teams = [str(team + 1) for team in control.teams_in(COMPARTMENTS[index])]
        if teams:
            layout.blit_line(s, " ".join(teams), (cell.x + 4, cell.y + 12, cell.w - 8, 16),
                             config.COLOR_OK, size=13)
    # Bow and stern caps.
    pygame.draw.line(s, config.COLOR_TEXT_DIM, (hull.right, hull.y), (rect.right - 2, hull.centery))
    pygame.draw.line(s, config.COLOR_TEXT_DIM, (hull.right, hull.bottom),
                     (rect.right - 2, hull.centery))
    pygame.draw.line(s, config.COLOR_TEXT_DIM, (hull.x, hull.y), (rect.x + 2, hull.centery))
    pygame.draw.line(s, config.COLOR_TEXT_DIM, (hull.x, hull.bottom), (rect.x + 2, hull.centery))


def _pct(value: float) -> str:
    return f"{value * 100.0:.0f}"


def draw_damage_page(s, game, boat, x, y, w, h) -> None:
    """Compartment picture, the table of compartments and the two teams."""
    control = boat.sub.damage_control
    selected, task = selection(boat)
    alarm = any(_alert(control, index) == config.COLOR_DANGER for index in range(len(COMPARTMENTS)))
    picture = layout.box(s, (x, y, w, 130), "uboot.panel.compartments",
                         border=config.COLOR_DANGER if alarm else config.COLOR_TEXT)
    draw_boat_compartments(s, control, picture, selected)
    table_y = y + 138
    table_h = 30 + 20 * (len(COMPARTMENTS) + 1)
    tx, ty, tw, _th = layout.box(s, (x, table_y, w, table_h), "uboot.panel.dc_status")
    name_w = max(90, int(tw * 0.24))
    columns = ("uboot.dc.col.water", "uboot.dc.col.leak", "uboot.dc.col.fire",
               "uboot.dc.col.gas", "uboot.dc.col.bulkhead")
    cell_w = (tw - name_w) // len(columns)
    for column, key in enumerate(columns):
        layout.blit_line(s, key, (tx + name_w + column * cell_w, ty, cell_w - 4, 18),
                         config.COLOR_TEXT_DIM, size=13)
    for index, name in enumerate(COMPARTMENTS):
        c = control.compartments[index]
        row_y = ty + 20 * (index + 1)
        color = _alert(control, index) or config.COLOR_TEXT
        if index == selected:
            pygame.draw.rect(s, config.COLOR_SELECT_BG, (tx - 4, row_y - 1, tw + 8, 19))
        layout.blit_line(s, f"uboot.compartment.{name}", (tx, row_y, name_w - 4, 18),
                         color, size=14)
        values = (f"{c.water_kg / 1000.0:.1f}", _pct(c.leak), _pct(c.fire), _pct(c.chlorine),
                  "uboot.dc.closed" if c.closed else "uboot.dc.open")
        for column, value in enumerate(values):
            layout.blit_line(s, value, (tx + name_w + column * cell_w, row_y, cell_w - 4, 18),
                             color, size=14)
    teams_y = table_y + table_h + 8
    bx, by, bw, bh = layout.box(s, (x, teams_y, w, max(60, y + h - teams_y)),
                                "uboot.panel.dc_teams",
                                border=config.COLOR_TEXT if control.power() else config.COLOR_DANGER)
    rows = [("uboot.dc.label.power",
             message("uboot.dc.power_on" if control.power() else "uboot.dc.power_off"),
             None if control.power() else config.COLOR_DANGER)]
    for number, team in enumerate(control.teams):
        state = (message("uboot.dc.team_transit", compartment=message(
                     f"uboot.compartment.{team['compartment']}"),
                     seconds=f"{team['transit_s']:.0f}")
                 if team["transit_s"] > 0.0 else
                 message("uboot.dc.team_at", compartment=message(
                     f"uboot.compartment.{team['compartment']}"),
                     task=message(f"uboot.dc.task.{team['task']}")))
        rows.append((message("uboot.dc.label.team", number=number + 1), state, None))
    rows.append(("uboot.dc.label.order", message(
        "uboot.dc.order", compartment=message(f"uboot.compartment.{COMPARTMENTS[selected]}"),
        task=message(f"uboot.dc.task.{task}")), config.COLOR_WARN))
    for index, (label, value, color) in enumerate(rows):
        if (index + 1) * 20 > bh:
            break
        layout.status_line(s, bx, by + index * 20, bw, label, value, color=color,
                           size=15, label_w=150)
