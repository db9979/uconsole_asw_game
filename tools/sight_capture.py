"""Shared scene for the eyepiece screenshots (frigate binoculars, periscope).

Used by ``capture_screenshots.py`` (uConsole) and ``capture_commander.py``
(browser). Only the authored geometry is set here: the crewed submarine at
periscope depth with its mast up, the frigate close ahead of it and a warship
just off the frigate's bow, two neutral merchants crossing ahead, and the
hour of the world clock. What the lookout and the periscope then see comes
from the running simulation.
"""

from __future__ import annotations

import math

from src.sensors.platform import MAST_DEPTH_M

# Hours of the world clock for the day and the night picture.
SIGHT_TIMES = (("day", 11.0), ("night", 22.5))
SIGHT_STEPS = 120
SIGHT_STEP_S = 0.25
# The warship stands this far off the frigate's bow, the first merchant
# as far to the other side; the binoculars trained on the bow (where the
# browser card opens) show both.
WARSHIP_OFF_BOW_DEG = 3.0
# Browser clients must crew the boat before the sim would hand it back.
CAPTURE_HOLD_S = 3600.0


def _place(entity, origin, distance_nm: float, bearing_deg: float) -> None:
    rad = math.radians(bearing_deg)
    entity.x = origin.x + distance_nm * math.sin(rad)
    entity.y = origin.y - distance_nm * math.cos(rad)


def _bearing(origin, entity) -> float:
    return math.degrees(math.atan2(entity.x - origin.x, -(entity.y - origin.y))) % 360.0


def _between(first: float, second: float) -> float:
    """The bearing halfway between two bearings (the shorter way round)."""
    return (first + ((second - first + 180.0) % 360.0 - 180.0) / 2.0) % 360.0


def sight_world(game, hour: float):
    """Arrange ``game`` for the eyepiece pictures at ``hour`` and let the
    lookout and the periscope crew take in the scene. Returns the boat."""
    # The uConsole crews the boat while the scene runs, so its lookouts
    # report sightings; the caller's side is restored afterwards.
    side = getattr(game, "local_side", "frigate")
    game.local_side = "uboot"
    boat = game.claim_opfor_sub()
    if boat is None:
        raise RuntimeError("no submarine for the periscope picture")
    game._opfor_hold_s = CAPTURE_HOLD_S
    sub = boat.sub
    scope_depth = MAST_DEPTH_M - 3.0
    sub.depth = sub.target_depth = sub.order_depth = scope_depth
    sub.set_orders(speed=0.0)
    sub.command_mast(True)
    boat.orders.mast = True
    _place(game.ship, sub, 0.9, sub.course + 4.0)
    game.ship.course = game.ship.target_course = (sub.course + 100.0) % 360.0
    warship = game.warships[0]
    _place(warship, game.ship, 1.2, game.ship.course + WARSHIP_OFF_BOW_DEG)
    warship.course = (game.ship.course + 80.0) % 360.0
    # Neutral merchants crossing ahead: their navigation lights show at night.
    for ship, origin, distance, bearing in zip(
            game.civilians, (game.ship, sub),
            (2.0, 2.2), (game.ship.course - WARSHIP_OFF_BOW_DEG, sub.course + 16.0)):
        _place(ship, origin, distance, bearing)
        ship.course = (bearing + 90.0) % 360.0
        if hasattr(ship, "target_course"):
            ship.target_course = ship.course
    heading = game.ship.course
    for _ in range(SIGHT_STEPS):
        game.world.hour = hour
        # The frigate lies stopped on her heading, so the arranged bearings hold.
        game.ship.course = game.ship.target_course = heading
        game.ship.speed = game.ship.target_speed = 0.0
        game.update(SIGHT_STEP_S)
        sub.depth = sub.target_depth = scope_depth
    game._opfor_hold_s = CAPTURE_HOLD_S
    # Head the frigate between the warship and the merchant beside it, so
    # both stand in the binoculars trained on the bow (display only; the
    # simulation stays frozen from here on).
    game.ship.course = game.ship.target_course = _between(
        _bearing(game.ship, warship), _bearing(game.ship, game.civilians[0]))
    # Train the periscope between the frigate and the second merchant.
    toward = _between(_bearing(sub, game.ship), _bearing(sub, game.civilians[1]))
    boat.orders.scope_rel_deg = float(round((toward - sub.course) % 360.0))
    game.local_side = side
    game.msg = ""
    game.msg_until = 0.0
    return boat
