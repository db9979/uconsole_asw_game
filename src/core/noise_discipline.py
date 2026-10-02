"""Noise discipline: what the own crew makes audible besides the machinery.

Two sources, both sides alike:

* **Mishaps.** Now and then something falls or a hatch slams: a short metallic
  bang lasting one ``TICK_S`` window.  A tired, demoralised crew fumbles more
  often; silent running (the boat's "Schleichfahrt", the frigate's quiet mode)
  is "Ruhe im Boot": far fewer mishaps, but repairs and reloading go slower
  (``QUIET_WORK_FACTOR``).  Each window is a stateless ``detrand`` draw from
  the seed, the platform and the window index, with the risk from the crew's
  saved fatigue and morale, so nothing new is saved and nothing shifts an
  existing random stream.
* **Voices.** The players' own microphones (opt-in, browser and uConsole):
  the loudest level a side's crew reported (``0..VOICE_LEVEL_MAX``) is an
  input like a held key.  Below ``VOICE_SAFE`` it is unheard, up to
  ``VOICE_LOUD`` the enemy hears it only close by, above it further.

Both raise the platform's radiated noise for as long as they last
(``crew_noise``), masked by its own machinery noise, and an enemy within
earshot hears a transient on its bearing.  The game applies the result at the
start of every substep (``src/core/game_noise.py``); this module is pure.
"""

from __future__ import annotations

import math

from src.core import config, detrand

TICK_S = 3.0
# Mishaps per hour of a fresh crew in the normal routine; silent running cuts it.
MISHAP_PER_H = 2.0
QUIET_RISK = 0.3
RISK_MAX = 5.0
MISHAP_NOISE = 0.25
MISHAP_KINDS = ("tool", "hatch", "pot", "chain")
# Repairs and reloading under "Ruhe im Boot" (silent running / quiet mode).
QUIET_WORK_FACTOR = 0.75
# A mishap is heard this far at full strength (scaled by the listener's ears).
MISHAP_HEAR_NM = 4.0

VOICE_LEVEL_MAX = 20
VOICE_SAFE = 5
VOICE_LOUD = 11
VOICE_NOISE_MAX = 0.2
VOICE_HEAR_NM = 2.5
# A level report counts this long (sim seconds); browsers repeat it while loud.
VOICE_HOLD_S = 1.5
# The own crew is told off at most once per window while far too loud.
VOICE_WARN_S = 20.0
VOICE_REPORT_S = 15.0


def band(level: int) -> str:
    """``quiet`` (unheard), ``near`` (heard close by) or ``far``."""
    if level <= VOICE_SAFE:
        return "quiet"
    return "near" if level <= VOICE_LOUD else "far"


def voice_noise(level: int) -> float:
    level = max(0, min(VOICE_LEVEL_MAX, int(level)))
    if level <= VOICE_SAFE:
        return 0.0
    return VOICE_NOISE_MAX * (level - VOICE_SAFE) / (VOICE_LEVEL_MAX - VOICE_SAFE)


def sub_quiet(sub) -> bool:
    """A submarine under "Ruhe im Boot": its crew's silent running or
    bottoming, or an AI boat lying in wait."""
    if sub.manual and sub.crew is not None:
        return bool(sub.crew.quiet_active(sub))
    return sub.state in ("LAUER", "WRACK")


def tick(sim_t: float) -> int:
    return math.floor((sim_t + 1e-9) / TICK_S)


def risk_per_h(effectiveness: float, quiet: bool) -> float:
    """Mishaps per hour: a weaker crew (``CrewState.effectiveness``) fumbles more."""
    weak = max(0.0, 1.0 - float(effectiveness))
    rate = MISHAP_PER_H * min(RISK_MAX, 1.0 + 4.0 * weak)
    return rate * (QUIET_RISK if quiet else 1.0)


def mishap(seed: int, platform: int, window: int, rate_per_h: float) -> str | None:
    """The mishap of one platform in one window, or None."""
    if detrand.u01(seed, "crew-mishap", platform, window) >= rate_per_h * TICK_S / 3600.0:
        return None
    pick = detrand.u01(seed, "crew-mishap-kind", platform, window)
    return MISHAP_KINDS[min(len(MISHAP_KINDS) - 1, int(pick * len(MISHAP_KINDS)))]


def crew_noise(base_noise: float, mishap_now: bool, voice_level: int) -> float:
    """Noise the crew adds on top of ``base_noise`` (0..1), masked by it."""
    raw = (MISHAP_NOISE if mishap_now else 0.0) + voice_noise(voice_level)
    return raw * (1.0 - config.clamp(base_noise, 0.0, 1.0))


def hear_nm(mishap_now: bool, voice_level: int, base_noise: float) -> float:
    """How far an enemy with ideal ears hears the crew's noise now."""
    reach = MISHAP_HEAR_NM if mishap_now else 0.0
    if voice_level > VOICE_SAFE:
        reach = max(reach, VOICE_HEAR_NM * voice_noise(voice_level) / VOICE_NOISE_MAX)
    return reach * (1.0 - 0.8 * config.clamp(base_noise, 0.0, 1.0))
