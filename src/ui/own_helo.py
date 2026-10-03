"""The frigate's own helicopter as the bridge lookout's eye sees it.

The helicopter is a commanded own asset (legitimate truth): the bridge knows
where it flies, so its outline joins the eyepiece pictures (binoculars,
lookout strip, hit picture, Remote Crew and phone lookout) without any
sensor track or report.  Display only: nothing here feeds the air picture,
the lookout's calls or the simulation.
"""

from __future__ import annotations

import math

from src.core import config
from src.sensors import lookout_id, nav_lights
from src.sensors import visual as visual_physics

# Sea Lynx Mk88A of the Brandenburg class: 15.2 m over the rotors.
LENGTH_M = 15.2
# Height above the sea: transit, a MAD run, the dipping hover, the deck.
TRANSIT_ALTITUDE_M = 60.0
MAD_ALTITUDE_M = 30.0
DIP_HOVER_ALTITUDE_M = 15.0
DECK_ALTITUDE_M = 6.0
# The bridge sits forward of the frigate's centre, the flight deck aft of it
# (Brandenburg class: bridge about 28 m forward, deck centre about 51 m aft).
BRIDGE_FORWARD_M = 28.0
DECK_AFT_M = 51.0
# Within this distance of the ship the helicopter climbs off or settles onto
# the deck (the recovery distance: closer in it lands and is struck down).
DECK_BLEND_NM = config.HELO_RETURN_DIST_NM


def _altitude_m(helo, blend: float) -> float:
    if helo.dip_state != "STOWED":
        cruise = DIP_HOVER_ALTITUDE_M
    elif getattr(helo, "mad_mode", False):
        cruise = MAD_ALTITUDE_M
    else:
        cruise = TRANSIT_ALTITUDE_M
    return DECK_ALTITUDE_M + (cruise - DECK_ALTITUDE_M) * blend


def outline(game):
    """The own helicopter's eyepiece row (``seen``), or None."""
    seen_now = seen(game)
    return None if seen_now is None else seen_now[0]


def seen(game):
    """``(row, range_nm)`` of the own helicopter in the bridge's sight: its
    eyepiece row ``(bearing, span_deg, cls, stale,
    lights, elevation_deg, aob_deg, model, way, range_nm)`` as the bridge's eye sees
    it and its distance from the bridge, or None (in the hangar, lost,
    beyond what the eye reaches or behind land).  On launch and recovery it
    sits on the flight deck astern."""
    helo = getattr(game, "helo", None)
    if helo is None or not helo.airborne:
        return None
    ship = game.ship
    course = math.radians(ship.course)
    ahead_x, ahead_y = math.sin(course), -math.cos(course)
    eye_x = ship.x + ahead_x * BRIDGE_FORWARD_M / 1852.0
    eye_y = ship.y + ahead_y * BRIDGE_FORWARD_M / 1852.0
    away = math.hypot(helo.x - ship.x, helo.y - ship.y)
    blend = min(1.0, away / DECK_BLEND_NM) if DECK_BLEND_NM > 0 else 1.0
    # Close aboard the picture slides from the flight deck to its true place.
    deck = (1.0 - blend) * DECK_AFT_M / 1852.0
    hx, hy = helo.x - ahead_x * deck, helo.y - ahead_y * deck
    dx, dy = hx - eye_x, hy - eye_y
    distance = math.hypot(dx, dy)
    if distance <= 1e-6:
        return None
    altitude = _altitude_m(helo, blend)
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    # The lookout's own eye (contrast model, weather and light), without his
    # fatigue: at night the helicopter's position lights carry further.
    environment = game._lookout_environment()
    visibility = float(environment["visibility_nm"])
    lights = (nav_lights.aircraft_code(helo.course, bearing, distance, visibility)
              if nav_lights.lit(game.world.daylight_stage(), visibility) else None)
    if lights is None:
        from src.core.game_sim import LOOKOUT_MODEL
        if LOOKOUT_MODEL.margin("FLG", distance, altitude_m=altitude, **environment) < 1.0:
            return None
    if game.world.land_blocks_line(eye_x, eye_y, hx, hy):
        return None
    span = math.degrees(LENGTH_M / max(distance * 1852.0, 1.0))
    elevation = visual_physics.elevation_deg(altitude, distance,
                                             visual_physics.LOOKOUT_EYE_HEIGHT_M)
    return ((bearing, max(1e-3, min(180.0, span)), "aircraft", False, lights,
             max(-30.0, elevation), lookout_id.angle_on_bow(helo.course, bearing), None, None,
             distance), distance)
