"""Thunderstorms: lightning, thunder and sferics under a storm (pure).

A storm (the existing weather model's ``storm`` kind, from the weather epochs
or a front) carries thunderstorm cells.  Their activity (0..1) grows with the
rain.  The strikes are stateless: sim time is cut into ``BUCKET_S`` slots
and each slot holds a strike or not by a counter-based draw (``detrand``)
keyed by the world seed, so the same seed gives the same lightning on the
uConsole and in the browser, and nothing needs saving.

* Lightning lights the eyepieces for a moment (bearing and distance from the
  viewer; display only).
* Thunder follows after the sound's run time (343 m/s), louder when close.
* Sferics, the radio crackle of the discharges, spoil HF direction finding:
  every HFDF bearing (frigate and submarine alike) spreads by
  ``sferics_factor``, and the ESM and radio displays crackle.
"""

from __future__ import annotations

import math

from src.core import detrand

BUCKET_S = 2.0
STRIKE_SHARE = 0.16        # chance per slot at full activity (~1 in 12 s)
DISTANCE_NM = (1.5, 18.0)
FLASH_S = 0.7              # how long one strike lights the sky
SOUND_M_S = 343.0
NM_M = 1852.0
THUNDER_MAX_NM = 10.0      # beyond this the thunder is lost in the wind
SFERICS_SPREAD = 0.75      # HFDF bearing error at full activity: x1.75
RAIN_START = 0.55
RAIN_FULL = 0.9
MAX_SCAN_BUCKETS = 64


def activity(weather_kind: str, rain_intensity: float) -> float:
    """Thunderstorm activity 0..1: only under a storm, stronger in more rain."""
    if weather_kind != "storm":
        return 0.0
    k = (float(rain_intensity) - RAIN_START) / (RAIN_FULL - RAIN_START)
    return round(max(0.35, min(1.0, 0.35 + 0.65 * k)), 4)


def sferics_factor(level: float) -> float:
    """Multiplier on an HF bearing error under thunderstorm ``level``."""
    return 1.0 + SFERICS_SPREAD * max(0.0, min(1.0, float(level)))


def strike(seed: int, bucket: int, level: float):
    """The strike of one time slot as ``(t, bearing, distance_nm)``, or None."""
    if level <= 0.0 or bucket < 0:
        return None
    key = int(seed) & 0x7FFFFFFF
    if detrand.u01(key, "lightning", bucket) >= STRIKE_SHARE * level:
        return None
    t = (bucket + detrand.u01(key, "lightning-t", bucket)) * BUCKET_S
    bearing = 360.0 * detrand.u01(key, "lightning-brg", bucket)
    low, high = DISTANCE_NM
    distance = low + (high - low) * detrand.u01(key, "lightning-nm", bucket) ** 1.5
    return t, bearing, distance


def flash(seed: int, t: float, level: float):
    """``(brightness 0..1, bearing, distance_nm)`` of the lightning at ``t``
    (a double flicker fading over ``FLASH_S``), or None when dark."""
    if level <= 0.0:
        return None
    bucket = int(math.floor(t / BUCKET_S))
    for index in (bucket, bucket - 1):
        row = strike(seed, index, level)
        if row is None:
            continue
        age = t - row[0]
        if 0.0 <= age <= FLASH_S:
            flicker = 1.0 if age < 0.12 or 0.22 < age < 0.3 else 0.45
            near = 1.0 - 0.6 * (row[2] - DISTANCE_NM[0]) / (DISTANCE_NM[1] - DISTANCE_NM[0])
            return round(flicker * near * (1.0 - age / FLASH_S) ** 0.5, 4), row[1], row[2]
    return None


def thunder(seed: int, t0: float, t1: float, level: float) -> list:
    """``(loudness 0..1, bearing)`` of the thunderclaps arriving in (t0, t1]."""
    if level <= 0.0 or t1 <= t0:
        return []
    delay_max = THUNDER_MAX_NM * NM_M / SOUND_M_S
    first = int(math.floor((t0 - delay_max) / BUCKET_S))
    last = int(math.floor(t1 / BUCKET_S))
    first = max(first, last - MAX_SCAN_BUCKETS)
    rows = []
    for bucket in range(first, last + 1):
        row = strike(seed, bucket, level)
        if row is None or row[2] > THUNDER_MAX_NM:
            continue
        arrive = row[0] + row[2] * NM_M / SOUND_M_S
        if t0 < arrive <= t1:
            rows.append((round(1.0 - row[2] / THUNDER_MAX_NM, 4), row[1]))
    return rows
