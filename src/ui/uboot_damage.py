"""Damage-control page of the crewed submarine's engine room (uConsole).

Own-ship state only (``src/enemies/damage_control.py``): the six
compartments from stern (left) to bow (right) as a cutaway drawing with
their water, fire, gas, leaks and bulkhead doors (``damage_section``), the
picked compartment's numbers on lamps, and the two teams with the order the
operator is about to give.
"""

import pygame

from src.core import config, status_tips
from src.core.i18n import message, raw_text
from src.enemies.damage_control import COMPARTMENTS, TASKS, capacity_kg
from src.ui import console, damage_section, layout, pointer



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




def draw_boat_compartments(s, control, rect, selected=None, trim_deg=0.0) -> None:
    """The boat as a cutaway drawing, bow to the right.

    Every compartment shows its water tilted by the trim, fire and smoke,
    chlorine haze, a leak with the water rushing in and the round bulkhead
    doors; its name, the water in tonnes and the teams inside.
    """
    rect = pygame.Rect(rect)
    count = len(COMPARTMENTS)
    row = layout.font(16).get_linesize()
    art = pygame.Rect(rect.x, rect.y, rect.w, rect.h - 2 * row - 4)
    cells = damage_section.draw_boat_section(s, art, control, capacity_kg, trim_deg, selected)
    for index in range(count):
        c = control.compartments[index]
        cell = cells[index]
        alert = _alert(control, index)
        layout.record_geometry("room", cell, f"uboot.compartment.{COMPARTMENTS[index]}")
        if alert and selected != index:
            pygame.draw.rect(s, alert, cell, 1)
        label_y = art.bottom + 2
        layout.blit_line(s, f"uboot.dc.room.{COMPARTMENTS[index]}",
                         (cell.x + 1, label_y, cell.w - 2, row),
                         alert or config.COLOR_TEXT, size=16, align="center")
        layout.blit_line(s, raw_text(f"{c.water_kg / 1000.0:.1f} t"),
                         (cell.x + 1, label_y + row, cell.w - 2, row),
                         config.COLOR_WARN if c.water_kg > 0.0 else config.COLOR_TEXT_DIM,
                         size=16, align="center")
        teams = [team + 1 for team in control.teams_in(COMPARTMENTS[index])]
        if teams:
            console.badges(s, cell.centerx, cell.centery - 10, teams)


def _pct(value: float) -> str:
    return f"{value * 100.0:.0f}"


def draw_damage_page(s, game, boat, x, y, w, h) -> None:
    """Cutaway picture, the table of compartments and the two teams."""
    control = boat.sub.damage_control
    selected, task = selection(boat)
    alarm = any(_alert(control, index) == config.COLOR_DANGER for index in range(len(COMPARTMENTS)))
    mimic_h = min(230, max(170, h * 2 // 5))
    picture = layout.box(s, (x, y, w, mimic_h), "uboot.panel.compartments",
                         border=config.COLOR_DANGER if alarm else config.COLOR_TEXT)
    sub = boat.sub
    trim = sub.ballast.trim_deg(sub.flood_moment_kg()) if hasattr(sub, "ballast") else 0.0
    draw_boat_compartments(s, control, picture, selected, trim)
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
             levels["bulkhead"], "I"),
            ("uboot.dc.lamp.power",
             "uboot.dc.power_on" if control.power() else "uboot.dc.power_off_short",
             "on" if control.power() else "alarm")]
    grid_h = 2 * 36 + 4
    name_h = layout.line_pitch(18, 2)
    table_h = layout.line_pitch(16, 16, bold=True) + name_h + grid_h + 8
    tx, ty, tw, _th = layout.box(s, (x, table_y, w, table_h), "uboot.panel.dc_status",
                                 border=_alert(control, selected) or config.COLOR_TEXT)
    room_level = ("alarm" if _alert(control, selected) == config.COLOR_DANGER else
                  "caution" if _alert(control, selected) else "on")
    console.led(s, (tx + 7, ty + name_h // 2), 6, room_level)
    pointer.add_tip((tx, ty, tw, name_h), lambda: status_tips.payload(
        status_tips.boat_compartment(control, selected, room_level,
                                     f"uboot.compartment.{COMPARTMENTS[selected]}")))
    layout.blit_line(s, f"uboot.compartment.{COMPARTMENTS[selected]}",
                     (tx + 20, ty, tw - 20, name_h), config.COLOR_TEXT, size=18)
    console.lamp_grid(s, (tx, ty + name_h, tw, grid_h), console.with_tips(rows, [
        status_tips.lazy(lambda: status_tips.boat(game, boat), name) for name in (
            "dc_water", "dc_leak", "dc_fire", "dc_gas", "dc_bulkhead", "dc_power")]), 3)
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
    hurt = game.casualty_view(game.peek_roster(boat.sub))
    gaps = {row["station"]: row["gaps"] for row in hurt["stations"]}
    rows.append(("uboot.dc.label.wounded", message(
        "uboot.dc.wounded", wounded=hurt["wounded"], serious=hurt["serious"],
        spare=hurt["spare"], **gaps),
        config.COLOR_WARN if any(gaps.values()) else None))
    rows.append(("uboot.dc.label.order", message(
        "uboot.dc.order", compartment=message(f"uboot.compartment.{COMPARTMENTS[selected]}"),
        task=message(f"uboot.dc.task.{task}")), config.COLOR_WARN))
    for index, (label, value, color) in enumerate(rows):
        if (index + 1) * 20 > bh:
            break
        layout.status_line(s, bx, by + index * 20, bw, label, value, color=color,
                           size=15, label_w=150)
