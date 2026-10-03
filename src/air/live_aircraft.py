"""Live-Flugzeug-Kontakt aus dem OpenSky-ADS-B-Feed.

Minimal an ``src.air.raid.Raider`` angelehnt (per-Instanz ``altitude_m`` fuer
den Radarhorizont), aber mit Interpolation zwischen zwei Zustandsvektor-
Fixes fuer eine fluessige Darstellung zwischen den ~15-30s REST-Polls.
"""

from __future__ import annotations

import math
import hashlib

from src.core import config
from src.physics.geo import FrigateRelativeMixin


class _Fix:
    __slots__ = ("x", "y", "altitude_m", "course", "speed", "t")

    def __init__(self, x: float, y: float, altitude_m: float,
                 course: float, speed: float, t: float) -> None:
        self.x = x
        self.y = y
        self.altitude_m = altitude_m
        self.course = course
        self.speed = speed
        self.t = t


class LiveAircraft(FrigateRelativeMixin):
    """Ein per ICAO24 identifizierter, realer Flugkontakt."""

    def __init__(self, icao24: str, callsign: str | None, seq: int,
                 x: float, y: float, altitude_m: float, course: float,
                 speed_kn: float, t: float) -> None:
        self.icao24 = icao24
        self.callsign = (callsign or "").strip() or None
        self.seq = seq
        # Python's hash is deliberately randomized between processes.  Live
        # traffic still needs a stable seed because its radar activity is a
        # transparent gameplay assumption, never a fact obtained from ADS-B.
        self.sensor_seed = int.from_bytes(
            hashlib.blake2s(icao24.lower().encode("ascii", "strict"),
                            digest_size=4,
                            person=b"ujagdair").digest(), "big")
        self.x = float(x)
        self.y = float(y)
        self.altitude_m = float(altitude_m)
        self.course = float(course) % 360.0
        self.speed = float(speed_kn)
        self.hp = 1
        self.max_hp = 1
        self.evasion = 0.0
        self.despawned = False
        fix = _Fix(self.x, self.y, self.altitude_m, self.course, self.speed, t)
        self._prev_fix = fix
        self._curr_fix = fix

    def push_fix(self, x: float, y: float, altitude_m: float,
                 course: float, speed_kn: float, t: float) -> None:
        """Neuer ADS-B-Zustandsvektor: wird zum Interpolationsziel."""
        self._prev_fix = self._curr_fix
        self._curr_fix = _Fix(float(x), float(y), float(altitude_m),
                              float(course) % 360.0, float(speed_kn), t)

    @property
    def last_fix_at(self) -> float:
        """Zeitstempel des zuletzt empfangenen ADS-B-Fixes (fuer Aging/Pruning)."""
        return self._curr_fix.t

    def advance(self, now: float) -> None:
        """Interpoliert (oder extrapoliert) Position/Hoehe/Kurs auf ``now``."""
        prev, curr = self._prev_fix, self._curr_fix
        span = curr.t - prev.t
        if span > 1e-6:
            frac = (now - prev.t) / span
        else:
            frac = 1.0
        if frac <= 1.0:
            frac = max(0.0, frac)
            self.x = prev.x + (curr.x - prev.x) * frac
            self.y = prev.y + (curr.y - prev.y) * frac
            self.altitude_m = (prev.altitude_m
                               + (curr.altitude_m - prev.altitude_m) * frac)
            self.course = (prev.course
                           + config.angle_diff_deg(curr.course, prev.course)
                           * frac) % 360.0
        else:
            # Naechstes Poll verspaetet sich: linear mit letztem Kurs/Speed
            # weiter tot-rechnen statt einzufrieren.
            overshoot_s = now - curr.t
            step_nm = config.kn_to_nm_per_s(curr.speed) * overshoot_s
            rad = math.radians(curr.course)
            self.x = curr.x + step_nm * math.sin(rad)
            self.y = curr.y - step_nm * math.cos(rad)
            self.altitude_m = curr.altitude_m
            self.course = curr.course
        self.speed = curr.speed

    @property
    def radar_emitting(self) -> bool:
        return True

    @property
    def ais_transmitting(self) -> bool:
        return False

    @property
    def sensor_domain(self) -> str:
        return "air"

    def hit(self) -> None:
        self.hp -= 1
        if self.hp <= 0:
            self.despawned = True
