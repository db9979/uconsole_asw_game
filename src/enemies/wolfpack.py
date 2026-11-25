"""AI submarines hunting as a pack, and the snap shot down a launch bearing.

Two or more free AI submarines of one side form a pack.  A pack boat that
holds a contact shadows it and reports it more often than a lone boat
(every ``PACK_REPORT_PERIOD_S`` instead of ``config.SUB_REPORT_PERIOD_S``):
it comes up to periscope depth for the call shortly before its slot, sends
the usual 20 s HF report (which the frigate's HF/DF hears, as before) and
the other boats of the pack get the datum when the call ends.  A boat that
holds no fresher contact of its own takes the datum as a coarse memory of
the target (dead-reckoned to now, with at least ``PACK_SIGMA_NM`` of
uncertainty), so its commander's plan closes the bearing or lies in wait as
it would for a contact it heard itself (``src/core/opfor_plans.py``); its
own torpedoes still need its own converged solution.

A free AI boat that hears the frigate launch a torpedo from its tubes may
answer at once with a snap shot down the launch bearing, if a tube is
already flooded: the range comes from the loudness of the transient (a
coarse estimate, ``SNAP_RANGE_ERROR``), the seeker does the rest.

Stateless: every decision derives from the boats' saved memory, the seed and
the simulation time (``src/core/detrand.py``), so nothing new is saved and a
loaded game continues identically.  Observation boundary: a boat only uses
what it heard itself or what a pack mate reported.
"""

from __future__ import annotations

import math

from src.core import config, detrand
from src.sensors.platform import MAST_DEPTH_M, PlatformObservation

# A pack boat with a contact reports this often (s); a lone boat keeps the
# old period.
PACK_REPORT_PERIOD_S = 600.0
# A contact younger than this (s) is worth reporting.
REPORT_CONTACT_AGE_S = 120.0
# Before its slot the shadower comes up to periscope depth this long (s).
RISE_S = 150.0
RISE_KN = 4.0
# A reported datum is at least this uncertain (NM) and grows with its age.
PACK_SIGMA_NM = 2.0
PACK_SIGMA_GROWTH_NM_PER_MIN = 0.15
# The receiver remembers it as if heard this long ago (s): it fades sooner
# than a contact the boat heard itself.
PACK_MEMORY_AGE_S = 0.5 * config.SUB_EVADE_DURATION_S
# A receiver keeps its own contact while it is younger than this (s).
OWN_CONTACT_KEEP_S = 90.0
# Snap shot: chance per heard launch (times the commander's aggression),
# the factor error of the range estimate, and its limits (NM).
SNAP_CHANCE = 0.5
SNAP_RANGE_ERROR = 0.35
SNAP_RANGE_NM = (2.0, 12.0)


def _free(sub) -> bool:
    return (sub.side == "hostile" and not sub.sunk and sub.state != "SINKING"
            and not sub.manual and not getattr(sub, "mission_peace", False))


def pack(game) -> list:
    """The free AI boats that hunt together (empty for a lone boat)."""
    boats = [sub for sub in game.subs if _free(sub)]
    return boats if len(boats) >= 2 else []


def report_period(game, sub) -> float:
    return PACK_REPORT_PERIOD_S if sub in pack(game) else config.SUB_REPORT_PERIOD_S


def _slot_start(game, sub, now: float, period: float) -> float:
    window = math.floor(now / period)
    return window * period + detrand.u01(
        game.seed, "sub-contact-report", int(sub.sensor_seed), window) * (
            period - config.SUB_REPORT_TX_S)


def report_on_air(game, sub, now: float) -> bool:
    """The boat's contact report is on the air (heard by the frigate's HF/DF)."""
    return sub.contact_report_on_air(game.seed, now, report_period(game, sub))


def _has_reportable_contact(sub) -> bool:
    return (sub.memory["contact"] is not None
            and sub.memory["contact_age"] <= REPORT_CONTACT_AGE_S)


def rising_orders(game, sub):
    """``(course, speed, depth)`` while a pack shadower comes up to report
    in its next slot, else None."""
    if sub not in pack(game) or not _has_reportable_contact(sub):
        return None
    now = game.sim_t
    for when in (now, now + RISE_S):
        start = _slot_start(game, sub, when, PACK_REPORT_PERIOD_S)
        if start - RISE_S <= now < start + config.SUB_REPORT_TX_S:
            return sub.course, RISE_KN, max(0.0, MAST_DEPTH_M - 2.0)
    return None


def share(game, dt: float) -> int:
    """Hand each report that ended in this substep to the pack; returns how
    many boats took a datum."""
    boats = pack(game)
    if not boats or dt <= 0.0:
        return 0
    now = game.sim_t
    taken = 0
    for sender in boats:
        if sender.memory["contact"] is None:
            continue
        if not (sender.contact_report_on_air(game.seed, now - dt, PACK_REPORT_PERIOD_S)
                and not sender.contact_report_on_air(game.seed, now, PACK_REPORT_PERIOD_S)):
            continue
        for receiver in boats:
            if receiver is sender or not _free(receiver):
                continue
            if (receiver.memory["contact"] is not None
                    and receiver.memory["contact_age"] < OWN_CONTACT_KEEP_S):
                continue
            _take_datum(receiver, sender, now)
            taken += 1
    return taken


def _take_datum(receiver, sender, now: float) -> None:
    contact = sender.memory["contact"]
    heard_at = sender.memory["contact_t"]
    age_s = max(0.0, now - heard_at) if heard_at is not None else sender.memory["contact_age"]
    speed = float(contact["speed"])
    course = float(contact["course"])
    run = config.kn_to_nm_per_s(speed) * age_s
    x = float(contact["x"]) + run * math.sin(math.radians(course))
    y = float(contact["y"]) - run * math.cos(math.radians(course))
    sigma = max(PACK_SIGMA_NM, float(sender.memory["contact_sigma_nm"] or 0.0)) \
        + PACK_SIGMA_GROWTH_NM_PER_MIN * age_s / 60.0
    receiver.memory["contact"] = dict(x=x, y=y, speed=speed, course=course,
                                      noise=float(contact["noise"]))
    receiver.memory["contact_age"] = PACK_MEMORY_AGE_S
    receiver.memory["contact_bearing"] = math.degrees(math.atan2(
        x - receiver.x, -(y - receiver.y))) % 360.0
    receiver.memory["contact_sigma_nm"] = min(10_000.0, sigma)
    receiver.memory["contact_t"] = float(now)
    receiver.memory["contact_reopen_left"] = 0


def snap_shot(game, sub, source, launch_seq: int) -> bool:
    """A free AI boat answers a heard tube launch down its bearing (once per
    launch, only from a flooded tube); True when it fired."""
    if (not _free(sub) or sub.torpedoes_left <= 0 or sub.ai_tube_left != 0.0
            or sub.attack_left > 0.0
            or (sub.weapon_battery is not None and sub.weapon_battery.ready_count <= 0)):
        return False
    seed = int(sub.sensor_seed)
    chance = SNAP_CHANCE * sub.stype.aggression
    if detrand.u01(game.seed, "snap-shot", seed, int(launch_seq)) >= chance:
        return False
    sx, sy = source
    distance = math.hypot(sx - sub.x, sy - sub.y)
    bearing = math.degrees(math.atan2(sx - sub.x, -(sy - sub.y))) % 360.0
    # The loudness of the transient gives only a coarse range.
    error = math.exp(SNAP_RANGE_ERROR * detrand.normal(
        game.seed, "snap-range", seed, int(launch_seq)))
    guess = min(SNAP_RANGE_NM[1], max(SNAP_RANGE_NM[0], distance * error))
    x = sub.x + guess * math.sin(math.radians(bearing))
    y = sub.y - guess * math.cos(math.radians(bearing))
    observation = PlatformObservation(
        track_id="MEMORY", domain="sonar", source="SONAR",
        observer_x=sub.x, observer_y=sub.y, bearing=bearing, range_nm=guess,
        x=x, y=y, course=None, speed_kn=None, depth_m=5.0, quality=0.3,
        signal=1.0, last_seen=float(game.sim_t), bearing_uncertainty_deg=None,
        range_uncertainty_nm=guess * SNAP_RANGE_ERROR, depth_uncertainty_m=None,
        label=None, fix_source="TRANSIENT")
    if not sub._fire_salvo(observation, 1):
        return False
    sub.attack_left = sub.attack_cooldown
    return True
