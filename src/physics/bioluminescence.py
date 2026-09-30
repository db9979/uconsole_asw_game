"""Bioluminescence: plankton that lights up where the water is stirred.

At night in warm water dinoflagellates flash when a hull, a screw or a
torpedo stirs them, so a wake, a periscope's feather and a torpedo's track
glow and are seen further.  The bloom of a world is fixed by its seed (some
waters bloom, some do not) and follows the sea-surface temperature, so it is
strongest in summer; it acts on both sides alike.  Pure functions: the
strength is a lookout contrast relief, the drawing reads the same value.
"""

from __future__ import annotations

from src.core import detrand

# Sea-surface temperature where the bloom starts and where it is full (deg C).
WARM_START_C = 11.0
WARM_FULL_C = 16.0
# The seeded patchiness: even warm water blooms at least this much.
PATCH_MIN = 0.3
# Stirring speed (kn) at which a wake glows fully; a torpedo always does.
WAKE_FULL_KN = 12.0
WAKE_MIN_KN = 2.0
# Share of the night's contrast penalty a fully glowing wake takes back.
NIGHT_RELIEF = 0.4
KINDS = ("SURFACE", "SUB", "TORP")


def bloom(seed: int, sst_c: float) -> float:
    """Bloom strength 0..1 of a world with surface temperature ``sst_c``."""
    warm = (float(sst_c) - WARM_START_C) / (WARM_FULL_C - WARM_START_C)
    warm = max(0.0, min(1.0, warm))
    patch = PATCH_MIN + (1.0 - PATCH_MIN) * detrand.u01(int(seed), "bioluminescence")
    return round(warm * patch, 4)


def wake_glow(bloom_level: float, kind: str, speed_kn: float) -> float:
    """How strongly a target of ``kind`` moving at ``speed_kn`` glows (0..1)."""
    if kind not in KINDS or bloom_level <= 0.0:
        return 0.0
    if kind == "TORP":
        stir = 1.0
    else:
        stir = (abs(float(speed_kn)) - WAKE_MIN_KN) / (WAKE_FULL_KN - WAKE_MIN_KN)
        stir = max(0.0, min(1.0, stir))
    return bloom_level * stir


def night_exponent(glow: float) -> float:
    """Exponent on the night threshold factor: 1 dark, lower when glowing."""
    return 1.0 - NIGHT_RELIEF * max(0.0, min(1.0, float(glow)))
