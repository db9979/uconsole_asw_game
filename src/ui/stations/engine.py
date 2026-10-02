"""Engine room view: plant, telegraph and noise (verbatim from ``stations_view``)."""


import math

import pygame

from src.core import config
from src.core.i18n import display_message, display_value, localized, localize, raw_text
from src.core.station import Station
from src.ship.ship import NOISE_LEVEL_MAX, PLANT_DIESEL_MAX_KN, Ship
from src.ui import console, layout


from src.ui.stations.common import (
    STATE_LABEL,
    _panel,
    _shortcut_footer,
    _station_content_top,
    draw_station_page_tabs,
    message)


# --- Maschinenraum (M10) ---------------------------------------------------

@localized
def draw_engine_view(game, tr=None) -> None:
    layout.configure_for(game)
    s = game.screen
    ship = game.ship
    from src.core.commands import STATION_PAGES
    pages = STATION_PAGES[Station.ENGINE]
    page = int(getattr(game, "station_page", 0)) % len(pages)
    r, y = _panel(game, title="station.engine.title")
    station_rect = pygame.Rect(config.STATION_RECT)
    draw_station_page_tabs(s, station_rect, pages, page, tr)
    cy = _station_content_top(station_rect, len(pages))
    content_h = station_rect.bottom - cy - 34
    x, w = r[0] + 14, r[2] - 28

    if page == 0:
        gap = 16
        col_w = (w - gap) // 2
        _draw_orders(s, game, ship, (x, cy, col_w, content_h))
        _draw_propulsion(s, game, ship, (x + col_w + gap, cy, col_w, content_h))
    else:
        _draw_systems(s, game, ship, (x, cy, w, content_h))

    station_bottom = config.STATION_RECT[1] + config.STATION_RECT[3]
    _shortcut_footer(s, (x, station_bottom - 26, w, 20), (
        ("↑/↓", "engine.footer.telegraph"),
        ("A", "engine.footer.quiet"),
        ("C", "engine.footer.set_course"),
        ("V", "engine.footer.set_speed"),
    ))


# --- console parts (display only) ------------------------------------------

SECTIONS = ("sonar", "bridge", "weapons", "opz", "radio", "engine", "flightdeck")


def _state_level(state: str) -> str:
    return "alarm" if state == "ZERSTOERT" else "on" if state == "OK" else "caution"


def _step_speed(ship) -> float:
    return (config.ASTERN_SPEED_KN if getattr(ship, "astern", False)
            else config.TELEGRAPH_ORDERS[ship.order_idx][1])


def _telegraph_click(game, row: int) -> None:
    """A click on a telegraph step: the ↑/↓ presses that reach it, so the
    order runs through the keyboard path with its checks and feedback."""
    from src.core import pointer_input
    ship = game.ship
    current = 0 if getattr(ship, "astern", False) else ship.order_idx + 1
    key = pygame.K_UP if row > current else pygame.K_DOWN
    pointer_input.press(game, key, times=abs(row - current))


def _draw_orders(s, game, ship, rect) -> None:
    """The telegraph as a column of lit steps."""
    ox, oy, ow, oh = layout.box(s, rect, "panel.engine_order")
    layout.blit_line(s, display_message("telegraph", ship.telegraph), (ox, oy, ow, 40),
                     config.COLOR_TEXT, size=28)
    oy += 40
    if abs(abs(ship.target_speed) - _step_speed(ship)) > 0.05:
        # Speed ordered directly (V or the start of a mission): say so,
        # the step row alone would show the wrong speed.
        layout.blit_line(s, message("engine.line.direct_speed",
                                    speed=f"{abs(ship.target_speed):.1f}"),
                         (ox, oy, ow, layout.line_pitch(16, 0)), config.COLOR_WARN, size=16)
    oy += layout.line_pitch(16, 4)
    displayed = (("ASTERN", config.ASTERN_SPEED_KN), *config.TELEGRAPH_ORDERS)
    astern = getattr(ship, "astern", False)
    step_h = max(24, min(52, (rect[1] + rect[3] - 10 - oy) // len(displayed) - 4))
    for i, (name, sp) in enumerate(displayed):
        selected = astern if i == 0 else not astern and i - 1 == ship.order_idx
        level = ("caution" if i == 0 else "on") if selected else "off"
        console.lamp(s, (ox, oy, ow, step_h), display_message("telegraph", name),
                     message("bridge.line.speed", speed=f"{sp:4.1f}"), level, size=18,
                     key=lambda _pos, row=i: _telegraph_click(game, row))
        oy += step_h + 4


def _draw_propulsion(s, game, ship, rect) -> None:
    """Speed, shaft and noise dials over a panel of plant lamps."""
    px, py, pw, ph = layout.box(s, rect, "panel.propulsion",
                                border=config.COLOR_DANGER if ship.cavitating else config.COLOR_TEXT)
    cap = game.damage.engine_speed_cap()
    rpm, max_rpm = ship.rpm(), Ship.max_rpm()
    noise = ship.noise_level()
    plant = getattr(ship, "plant_mode", "AUTO")
    rows = [
        ("panel.shaft", display_message("telegraph", ship.telegraph),
         "caution" if getattr(ship, "astern", False) else "on" if abs(ship.speed) > .05 else "off"),
        ("ui.plant_mode", display_value("plant", plant),
         "on" if plant == "DIESEL" else "caution" if plant == "TURBINE" else "off", "G"),
        ("engine.course", raw_text(f"{ship.course:03.0f}° / {ship.target_course:03.0f}°"),
         "on" if abs((ship.course - ship.target_course + 180) % 360 - 180) < 1 else "caution",
         "C"),
        ("ui.acoustic_mode", "engine.quiet_short" if ship.quiet_mode else "station.normal",
         "on" if ship.quiet_mode else "off", "A"),
        ("engine.lamp.cavitation", "common.yes" if ship.cavitating else "common.no",
         "alarm" if ship.cavitating else "off"),
        ("view.engine.speed_limit", message("bridge.line.speed", speed=f"{cap:.0f}"),
         "caution" if cap < config.SHIP_SPEED_MAX_KN - .05 else "off"),
    ]
    lamp_rows = 3
    lamp_h = lamp_rows * 38 + (lamp_rows - 1) * 6
    dial_h = max(80, ph - lamp_h - 12)
    speed_dial, *side_dials = (
        dict(value=abs(ship.speed), lo=0.0, hi=config.SHIP_SPEED_MAX_KN,
             text=message("bridge.line.speed", speed=f"{ship.speed:.1f}"), label="engine.dial.speed",
             order=abs(ship.target_speed),
             zones=((cap, config.SHIP_SPEED_MAX_KN, config.COLOR_DANGER),)
             if cap < config.SHIP_SPEED_MAX_KN - .05 else ()),
        dict(value=rpm, lo=0.0, hi=max_rpm, text=message("engine.line.rpm", rpm=f"{rpm:.0f}"),
             label="engine.label.rpm"),
        dict(value=noise, lo=0.0, hi=NOISE_LEVEL_MAX,
             text=message("engine.value.noise", noise=f"{noise * 100:.0f}"),
             label="engine.label.noise", zones=((0.85, NOISE_LEVEL_MAX, config.COLOR_DANGER),)),
    )
    # The speed dial large on the left, shaft and noise stacked beside it.
    half = (pw - 8) // 2
    console.dial(s, (px, py, half, dial_h), **speed_dial)
    console.dial_row(s, (px + half + 8, py, pw - half - 8, dial_h), side_dials)
    console.lamp_grid(s, (px, py + dial_h + 12, pw, lamp_h), rows, 2, gap=6)


def _fuel_fraction(ship) -> float:
    return ship.fuel_kg / ship.fuel_capacity_kg if ship.fuel_capacity_kg > 0.0 else 0.0


def _system_lamps(game, ship) -> list:
    damage = game.damage
    cap = damage.engine_speed_cap()
    machinery = damage.compartments.get("engine")
    rooms = list(damage.compartments.values())
    fires = sum(1 for room in rooms if room.fire > 0)
    flooded = sum(1 for room in rooms if room.flood > 0)
    teams = damage.teams_on("engine")
    fuel = _fuel_fraction(ship)
    list_deg = damage.list_deg()
    plant = getattr(ship, "plant_mode", "AUTO")
    plant_cap = min(cap, PLANT_DIESEL_MAX_KN) if plant == "DIESEL" else cap
    sea = getattr(game.world, "effective_sea_state", game.world.sea_state)
    rows = []
    if machinery is not None:
        rows += [
            ("engine.lamp.machinery", STATE_LABEL[machinery.state], _state_level(machinery.state)),
            ("engine.lamp.flooding", raw_text(f"{machinery.flood:.0f} %"),
             "alarm" if machinery.flood >= 50 else "caution" if machinery.flood > 0 else "off"),
            ("engine.lamp.fire", raw_text(f"{machinery.fire:.0f} %"),
             "alarm" if machinery.fire > 0 else "off"),
        ]
    rows += [
        ("engine.repairs", raw_text(", ".join(str(team) for team in teams) or "--"),
         "on" if teams else "off"),
        ("view.engine.speed_limit", message("bridge.line.speed", speed=f"{cap:.0f}"),
         "caution" if cap < config.SHIP_SPEED_MAX_KN - .05 else "off"),
        ("ui.plant_mode", message("engine.plant_short", plant=display_value("plant", plant),
                                  cap=f"{plant_cap:.0f}"),
         "on" if plant == "DIESEL" else "caution" if plant == "TURBINE" else "off", "G"),
        ("engine.fuel", raw_text(f"{fuel:.0%}"),
         "alarm" if fuel <= 0.1 else "caution" if fuel <= 0.25 else "on"),
        ("engine.lamp.fires_aboard", raw_text(str(fires)), "alarm" if fires else "off"),
        ("engine.lamp.flooded", raw_text(str(flooded)), "caution" if flooded else "off"),
        ("panel.hull_list", raw_text(f"{abs(list_deg):.1f}°"),
         "caution" if abs(list_deg) > .05 else "off"),
        ("engine.lamp.grounded", "common.yes" if getattr(ship, "grounded", False) else "common.no",
         "alarm" if getattr(ship, "grounded", False) else "off"),
        ("ui.acoustic_mode", "engine.quiet_short" if ship.quiet_mode else "station.normal",
         "on" if ship.quiet_mode else "off", "A"),
    ]
    sonar_range = ship.passive_sonar_range_nm(0.5, sea)
    if game.sonar_mode == "TOWED":
        sonar_range *= max(0.5, config.SONAR_ARRAY_TOWED_PASSIVE
                           - config.SONAR_TOWED_SPEED_PENALTY * ship.speed)
    available = game.sonar_mode != "TOWED" or game.sonar._tow_available()
    rows.append(("engine.lamp.sonar",
                 message("engine.line.sonar_effect", range=f"{sonar_range:4.1f}",
                         array=display_value("array", game.sonar_mode))
                 if available else "engine.tas_unavailable",
                 "on" if available and sonar_range > 10 else "caution"))
    rows.append(("panel.sea_state", raw_text(f"{sea:.1f}"), "caution" if sea >= 5 else "on"))
    return rows


def _draw_systems(s, game, ship, rect) -> None:
    """Annunciator panel over fuel bunker, ship motion and the section mimic."""
    x, y, w, h = rect
    rows = _system_lamps(game, ship)
    columns = 5
    lamp_h = math.ceil(len(rows) / columns) * 34 + 8
    title_h = layout.font(16, bold=True).get_linesize() + 8
    ann = pygame.Rect(x, y, w, min(h // 2, title_h + lamp_h + 16))
    master = console.master_level(row[2] for row in rows)
    ax, ay, aw, ah = layout.box(s, ann, "engine.panel.annunciator",
                                border={"alarm": config.COLOR_DANGER,
                                        "caution": config.COLOR_WARN}.get(master))
    alarms = sum(1 for row in rows if row[2] == "alarm")
    cautions = sum(1 for row in rows if row[2] == "caution")
    console.led(s, (ann.right - 232, ann.y + 8 + title_h // 2 - 4), 6, master)
    layout.blit_line(s, message("engine.line.master", alarms=str(alarms), cautions=str(cautions)),
                     (ann.right - 220, ann.y + 6, 210, title_h - 4),
                     console.level_color(master) if master != "on" else config.COLOR_TEXT_DIM,
                     size=16)
    console.lamp_grid(s, (ax, ay, aw, ah), rows, columns)
    low_y = ann.bottom + 8
    low_h = y + h - low_y
    fuel_w = max(200, w // 4)
    motion_w = max(200, w // 4)
    _draw_fuel(s, ship, (x, low_y, fuel_w, low_h))
    _draw_motion(s, game, ship, (x + fuel_w + 8, low_y, motion_w, low_h))
    mimic_x = x + fuel_w + motion_w + 16
    _draw_sections(s, game, (mimic_x, low_y, x + w - mimic_x, low_h))


def _draw_fuel(s, ship, rect) -> None:
    fx, fy, fw, fh = layout.box(s, rect, "engine.panel.fuel")
    fuel = _fuel_fraction(ship)
    level = "alarm" if fuel <= 0.1 else "caution" if fuel <= 0.25 else "on"
    tank_w = 70
    console.tank(s, (fx, fy, tank_w, fh), fuel, label="engine.tank.bunker",
                 text=raw_text(f"{fuel:.0%}"), level=level)
    endurance, distance = ship.fuel_endurance_h(), ship.fuel_range_nm()
    readouts = (
        ("engine.readout.stock", raw_text(f"{ship.fuel_kg / 1000.0:.1f} t")),
        ("engine.readout.burn", raw_text(f"{ship.fuel_burn_kg_h():.0f} kg/h")),
        ("engine.readout.endurance", raw_text(f"{endurance:.0f} h" if endurance is not None else "--")),
        ("engine.readout.range", raw_text(f"{distance:.0f} NM" if distance is not None else "--")),
    )
    rx, rw = fx + tank_w + 8, fw - tank_w - 8
    row = layout.font(16).get_linesize()
    pitch = max(2 * row + 4, min(fh // len(readouts), 3 * row))
    for index, (label, value) in enumerate(readouts):
        ry = fy + index * pitch
        if ry + 2 * row > fy + fh:
            break
        layout.blit_line(s, label, (rx, ry, rw, row), config.COLOR_TEXT_DIM, size=16)
        layout.blit_line(s, value, (rx, ry + row, rw, row), config.COLOR_OK, size=16)


def _draw_motion(s, game, ship, rect) -> None:
    mx, my, mw, mh = layout.box(s, rect, "engine.panel.motion")
    list_deg = game.damage.list_deg()
    specs = (
        dict(value=ship.roll, lo=-30.0, hi=30.0, text=raw_text(f"{ship.roll:+.1f}°"),
             label="engine.dial.roll",
             zones=((-30.0, -15.0, config.COLOR_WARN), (15.0, 30.0, config.COLOR_WARN))),
        dict(value=ship.pitch, lo=-10.0, hi=10.0, text=raw_text(f"{ship.pitch:+.1f}°"),
             label="engine.dial.pitch",
             zones=((-10.0, -5.0, config.COLOR_WARN), (5.0, 10.0, config.COLOR_WARN))),
    )
    if abs(list_deg) > .05:
        specs = (*specs, dict(value=list_deg, lo=-20.0, hi=20.0,
                              text=raw_text(f"{list_deg:+.1f}°"), label="panel.hull_list",
                              zones=((-20.0, -8.0, config.COLOR_DANGER), (8.0, 20.0, config.COLOR_DANGER))))
    console.dial_row(s, (mx, my, mw, mh), specs)

def _draw_sections(s, game, rect) -> None:
    """Sections from bow (left) to stern between the starboard and port hull strips."""
    sx, sy, sw, sh = layout.box(s, rect, "engine.panel.sections")
    compartments = game.damage.compartments
    strip_h = 30
    for key, top in (("hull_right", sy), ("hull_left", sy + sh - strip_h)):
        room = compartments.get(key)
        if room is None:
            continue
        level = ("alarm" if room.fire > 0 or room.state == "ZERSTOERT"
                 else "caution" if room.flood > 0 or room.state != "OK" else "on")
        value = raw_text(f"{room.flood:.0f} %") if room.flood > 0 else STATE_LABEL[room.state]
        console.lamp(s, (sx + 26, top, sw - 26, strip_h), f"engine.room.{key}", value, level)
    keys = [key for key in SECTIONS if key in compartments]
    if not keys:
        return
    body_y, body_h = sy + strip_h + 6, sh - 2 * strip_h - 12
    left = sx + 26
    width = (sx + sw - left) // len(keys)
    teams = game.damage.teams
    for index, key in enumerate(keys):
        room = compartments[key]
        on = [team for team, place in sorted(teams.items()) if place == key]
        console.room(s, (left + index * width, body_y, width - 3, body_h), f"engine.room.{key}",
                     flood=room.flood, down=room.state == "ZERSTOERT", bow=index == 0,
                     leds=(_state_level(room.state),
                           "alarm" if room.flood >= 50 else "caution" if room.flood > 0 else "off",
                           "alarm" if room.fire > 0 else "off"),
                     teams=on)
