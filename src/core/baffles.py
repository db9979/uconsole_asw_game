"""Baffles: the blind sector astern of a hull-mounted sonar, and clearing it.

A hull array hears nothing within ``SONAR_BAFFLE_HALF_DEG`` of its own
stern (the hull and the screws are in the way).  Clearing the baffles is a
short turn: the ordered course swings ``BAFFLE_CLEAR_TURN_DEG`` to
starboard, holds for ``BAFFLE_CLEAR_HOLD_S`` and returns.  The frigate
keeps its clearing in the save root (``baffle_clear``), a crewed
submarine in ``crew.orders``; both as ``[return course, turn course, end
time]`` or None.  Any other course order ends it.
"""

from __future__ import annotations

import math

from src.core import config


def in_baffles(course: float, bearing: float,
               half_deg: float = config.SONAR_BAFFLE_HALF_DEG) -> bool:
    """Whether a true bearing lies in the baffles of a hull on ``course``."""
    astern = (course + 180.0) % 360.0
    return abs(config.angle_diff_deg(bearing, astern)) < half_deg


def start(order_course: float, now: float) -> list:
    """A new clearing from the current ordered course."""
    back = float(order_course) % 360.0
    turn = (back + config.BAFFLE_CLEAR_TURN_DEG) % 360.0
    return [back, turn, float(now) + config.BAFFLE_CLEAR_HOLD_S]


def step(state, order_course: float, now: float):
    """(new state, course to order or None).  A different course order than
    the clearing's turn ends it silently; when its time is up it returns."""
    if state is None:
        return None, None
    back, turn, until = state
    if abs(config.angle_diff_deg(order_course, turn)) > 0.5:
        return None, None
    if now >= until:
        return None, back
    return state, None


def valid_state(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, list) or len(value) != 3:
        return False
    if not all(type(item) in (int, float) and not isinstance(item, bool)
               and math.isfinite(item) for item in value):
        return False
    return 0.0 <= value[0] < 360.0 and 0.0 <= value[1] < 360.0 and 0.0 <= value[2] <= 1e9
