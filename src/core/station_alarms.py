"""Alarm lamps of the station tabs and the battle lighting.

Each station gets a lamp level from what its own side already knows: a
torpedo alarm or an anti-ship missile on the own radar, fire or flooding
in the own compartments, a pinger heard by the boat.  ``"danger"`` blinks
red, ``"warn"`` shows steady amber, ``None`` stays dark.  The lamps are
display only (nothing is saved, nothing feeds back); the uConsole tabs,
the Remote Crew tabs (projection ``alarms``) and the automatic red light
read them.
"""

from __future__ import annotations

from src.core import boat_threat

LEVELS = ("warn", "danger")
# A torpedo alarm or classified torpedo this fresh lights the lamps (s).
TORPEDO_FRESH_S = 90.0
# Mean flooding of the frigate's compartments that counts as a leak.
FLOOD_WARN = 0.02
# Lamp blink period (wall time, s) and the red light's fade time.
BLINK_S = 0.8
FADE_S = 1.5


def _raise(levels: dict, station: str, level: str) -> None:
    """Set ``level`` unless the station already shows a higher one."""
    current = levels.get(station)
    if current is None or LEVELS.index(level) > LEVELS.index(current):
        levels[station] = level


def frigate(game) -> dict:
    """``{station key: "warn"|"danger"}`` of the frigate's stations
    (``Station.name.lower()``)."""
    levels: dict = {}
    if getattr(game, "game_over", False) or getattr(game.ship, "sunk", False):
        return levels
    torpedo = any(row["age_s"] <= TORPEDO_FRESH_S for row in game.torpedo_warnings())
    if torpedo:
        for station in ("bridge", "sonar", "weapons"):
            _raise(levels, station, "danger")
    if game.asm_tracks():
        for station in ("bridge", "weapons", "opz", "eloka"):
            _raise(levels, station, "danger")
    damage = game.damage
    rooms = list(damage.compartments.values())
    if any(room.fire > 0.0 for room in rooms):
        _raise(levels, "damage", "danger")
    elif damage.avg_flood() > FLOOD_WARN or any(room.state != "OK" for room in rooms):
        _raise(levels, "damage", "warn")
    if damage.station_degraded("engine"):
        _raise(levels, "engine", "danger" if damage.station_down("engine") else "warn")
    return levels


def boat(game, boat_state) -> dict:
    """``{role: "warn"|"danger"}`` of the crewed boat's stations
    (``OPFOR_ROLES``), from the boat's own intercepts and compartments."""
    levels: dict = {}
    sub = boat_state.sub
    if getattr(game, "game_over", False) or sub.sunk:
        return levels
    source = boat_threat.alarm_source(boat_state)
    if source is not None:
        level = "danger" if source[0] == "torpedo" else "warn"
        for role in ("uboot", "uboot_sonar"):
            _raise(levels, role, level)
        if source[0] == "torpedo":
            _raise(levels, "uboot_weapons", "warn")
    orders = boat_state.orders
    if orders.mast and orders.esm:
        _raise(levels, "uboot_esm", "warn")
    control = sub.damage_control
    if any(c.fire > 0.0 for c in control.compartments):
        _raise(levels, "uboot_engine", "danger")
    elif control.any_damage():
        _raise(levels, "uboot_engine", "warn")
    return levels


def for_side(game) -> dict:
    """The lamps of the side the uConsole shows."""
    crewed = getattr(game, "_opfor", None)
    if getattr(game, "local_side", "frigate") == "uboot" and crewed is not None:
        return boat(game, crewed)
    return frigate(game)


def lamp_on(level, wall_t: float) -> bool:
    """A danger lamp blinks, a warning lamp is steady."""
    if level == "danger":
        return (wall_t % BLINK_S) < BLINK_S * 0.55
    return level == "warn"


def red_light_target(game, levels: dict) -> float:
    """1 where the automatic red light wants to be (night, or an alarm
    on the side shown), else 0."""
    if any(level == "danger" for level in levels.values()):
        return 1.0
    world = getattr(game, "world", None)
    return 1.0 if world is not None and world.is_night() else 0.0
