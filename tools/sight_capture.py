"""Shared scene for the eyepiece screenshots (frigate binoculars, periscope).

Used by ``capture_screenshots.py`` (uConsole) and ``capture_commander.py``
(browser). Only the authored geometry is set here: the crewed submarine at
periscope depth with its mast up, the frigate close ahead of it and a warship
just off the frigate's bow, and the hour of the world clock. What the
lookout and the periscope then see comes from the running simulation.
"""

from __future__ import annotations

import math

from src.sensors.platform import MAST_DEPTH_M

# Hours of the world clock for the day and the night picture.
SIGHT_TIMES = (("day", 11.0), ("night", 22.5))
SIGHT_STEPS = 120
SIGHT_STEP_S = 0.25
# The warship stands this far off the frigate's bow, so the binoculars
# trained on the bow (the browser card opens there) show it.
WARSHIP_OFF_BOW_DEG = 3.0
# Browser clients must crew the boat before the sim would hand it back.
CAPTURE_HOLD_S = 3600.0


def _place(entity, origin, distance_nm: float, bearing_deg: float) -> None:
    rad = math.radians(bearing_deg)
    entity.x = origin.x + distance_nm * math.sin(rad)
    entity.y = origin.y - distance_nm * math.cos(rad)


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
    for _ in range(SIGHT_STEPS):
        game.world.hour = hour
        game.update(SIGHT_STEP_S)
        sub.depth = sub.target_depth = scope_depth
    game._opfor_hold_s = CAPTURE_HOLD_S
    # The frigate's helm may have come round meanwhile: steady her head just
    # off the warship again (display only; the simulation stays frozen).
    toward = math.degrees(math.atan2(warship.x - game.ship.x,
                                     -(warship.y - game.ship.y))) % 360.0
    game.ship.course = game.ship.target_course = (toward - WARSHIP_OFF_BOW_DEG) % 360.0
    # Train the periscope on the nearest ship (the widest sighting).
    rows = [row for row in boat.orders.sightings if row["cls"] != "aircraft"]
    nearest = max(rows, key=lambda row: row.get("span_deg") or 0.0, default=None)
    boat.orders.scope_rel_deg = (
        0.0 if nearest is None else float(round((nearest["bearing"] - sub.course) % 360.0)))
    game.local_side = side
    game.msg = ""
    game.msg_until = 0.0
    return boat
