"""The crewed submarine's towed buoy antenna (save v42 ``crew.orders.buoy``).

A small buoy on a cable streams astern and floats just under the surface,
so the radio room copies the broadcast deep without raising a mast: down to
``UBOOT_BUOY_DEPTH_M`` and only at ``UBOOT_BUOY_SPEED_KN`` or less (faster
and the buoy is pulled under).  It only receives; a situation report still
needs the mast.  Faster than ``UBOOT_BUOY_TEAR_KN`` the cable parts and the
buoy is lost for the mission.  Streaming or recovering it takes
``UBOOT_BUOY_STREAM_S``.

The buoy is a small thing on the water: the frigate's lookout and surface
radar can find it close in (``game_radar`` / ``game_sim``), about
``UBOOT_BUOY_TRAIL_NM`` astern of the boat.

State: ``[payout 0..1, ordered out, lost]``; pure functions, no randomness.
"""

from __future__ import annotations

import math

from src.core import config


def new_state() -> list:
    return [0.0, False, False]


def valid_state(value) -> bool:
    return (isinstance(value, list) and len(value) == 3
            and type(value[0]) is float and math.isfinite(value[0])
            and 0.0 <= value[0] <= 1.0
            and type(value[1]) is bool and type(value[2]) is bool
            and not (value[2] and (value[1] or value[0] > 0.0)))


def order(state: list, out: bool):
    """Stream (``out``) or recover the buoy; a lost buoy cannot stream."""
    if type(out) is not bool:
        return "invalid_value"
    if out and state[2]:
        return "uboot_buoy_lost"
    state[1] = out
    return True


def step(state: list, dt: float, speed_kn: float) -> str | None:
    """Advance the winch; returns an event key when something happened."""
    payout, out, lost = state
    if lost:
        return None
    if payout > 0.0 and speed_kn > config.UBOOT_BUOY_TEAR_KN:
        state[:] = [0.0, False, True]
        return "buoy_torn"
    rate = dt / config.UBOOT_BUOY_STREAM_S
    before = payout
    payout = min(1.0, payout + rate) if out else max(0.0, payout - rate)
    state[0] = payout
    if out and before < 1.0 <= payout:
        return "buoy_streamed"
    if not out and before > 0.0 >= payout:
        return "buoy_recovered"
    return None


def streamed(state) -> bool:
    return state is not None and not state[2] and state[0] >= 1.0


def receiving(state, depth_m: float, speed_kn: float) -> bool:
    """The buoy floats and hears the broadcast."""
    return (streamed(state) and depth_m <= config.UBOOT_BUOY_DEPTH_M
            and speed_kn <= config.UBOOT_BUOY_SPEED_KN)


def afloat(state, speed_kn: float) -> bool:
    """The buoy rides on the surface (visible): streamed and slow enough."""
    return streamed(state) and speed_kn <= config.UBOOT_BUOY_SPEED_KN


def position(sub) -> tuple[float, float]:
    """Where the buoy floats: the cable's length astern of the boat."""
    rad = math.radians(sub.course)
    return (sub.x - config.UBOOT_BUOY_TRAIL_NM * math.sin(rad),
            sub.y + config.UBOOT_BUOY_TRAIL_NM * math.cos(rad))


def status(state) -> str:
    """One word for the displays: stowed, streaming, out, recovering, lost."""
    payout, out, lost = state
    if lost:
        return "lost"
    if out:
        return "out" if payout >= 1.0 else "streaming"
    return "recovering" if payout > 0.0 else "stowed"
