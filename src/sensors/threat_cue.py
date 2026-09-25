"""Measurement-only threat cues.

A cue never reads an entity's type, class or hidden identity. Torpedo cues are
acoustic intercepts (a launch transient or high-frequency seeker pulses heard
on a measured bearing); an ASM cue is the radar picture of a fast, low,
inbound air track or a jamming strobe. Both are suspicions for the operator,
not classifications: a low-flying attack aircraft can raise an ASM cue just
as it would on a real combat system.
"""

from __future__ import annotations

import math

from src.core import config, detrand

TORPEDO_CUE_KINDS = ("transient", "seeker")


def torpedo_cue_kind(time_since_launch: float, terminal_active: bool,
                     distance_nm: float) -> str | None:
    """Return the audible torpedo intercept for one running weapon, if any.

    The launch transient is loud and brief (spool-up); the active seeker
    radiates high-frequency pulses that are heard well beyond its own homing
    range but far less than a launch.
    """
    if terminal_active and distance_nm <= config.TORP_SEEKER_INTERCEPT_NM:
        return "seeker"
    if (time_since_launch < config.TORP_SPOOLUP_S
            and distance_nm <= config.TORP_TRANSIENT_HEAR_NM):
        return "transient"
    return None


def measured_cue_bearing(true_bearing_deg: float, seed: int, key: int,
                         sim_t: float) -> float:
    """Noisy intercept bearing; a stateless draw per quarter-second epoch."""
    epoch = math.floor((sim_t + 1e-9) / 0.25)
    error = detrand.normal(seed, "torpedo-cue", key, epoch)
    return (true_bearing_deg + config.TORP_CUE_BEARING_SIGMA_DEG * error) % 360.0


def air_track_kind(previous_kind: str | None, derived_speed_kn: float | None,
                   altitude_m: float | None, jamming: bool) -> str:
    """Classify an air track from measurements only: ``"ASM"`` or ``"FLG"``.

    A jamming strobe or a fast track at sea-skimming altitude raises the
    missile cue; once raised it is held for the life of the track so the
    alarm does not flicker with the altitude noise.
    """
    if previous_kind == "ASM" or jamming:
        return "ASM"
    if (derived_speed_kn is not None and altitude_m is not None
            and derived_speed_kn >= config.ASM_CUE_SPEED_KN
            and altitude_m <= config.ASM_CUE_ALTITUDE_M):
        return "ASM"
    return "FLG"
