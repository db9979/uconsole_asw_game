"""Chaff clouds: drifting, blooming radar reflectors (own ship softkill).

A rocket lays the cloud beside the ship, off the threat axis, inside the
missile seeker's resolution cell.  The dipoles bloom to full cross-section
over a few seconds, drift with the wind and fall out after about 90 s.  The
missile decides between cloud and ship when it is launched against (see
``ASM.launch_chaff``); a cloud that has not bloomed by the time the missile
arrives is less likely to win.
"""

from __future__ import annotations

import math

from src.core import config

MAX_CLOUDS = 8
BLOOM_S = 3.0
LIFE_S = 90.0
LAY_DISTANCE_NM = 0.4
LAY_OFFSET_DEG = 60.0
FIELDS = frozenset({"seq", "x", "y", "age_s"})


class ChaffCloud:
    def __init__(self, seq: int, x: float, y: float, age_s: float = 0.0):
        self.seq = int(seq)
        self.x = float(x)
        self.y = float(y)
        self.age_s = float(age_s)

    @property
    def active(self) -> bool:
        return self.age_s < LIFE_S

    def bloom(self) -> float:
        """Fraction of the full cross-section reached."""
        return 1.0 - math.exp(-self.age_s / BLOOM_S)

    def update(self, dt: float, wind_from_deg: float, wind_speed_kn: float) -> None:
        drift = config.kn_to_nm_per_s(wind_speed_kn) * dt
        towards = math.radians((wind_from_deg + 180.0) % 360.0)
        self.x += drift * math.sin(towards)
        self.y -= drift * math.cos(towards)
        self.age_s += dt

    def to_dict(self) -> dict:
        return dict(seq=self.seq, x=self.x, y=self.y, age_s=self.age_s)


def lay_position(ship_x: float, ship_y: float, threat_bearing_deg: float,
                 seq: int) -> tuple[float, float]:
    """Cloud position off the threat axis (alternating sides)."""
    side = LAY_OFFSET_DEG if seq % 2 else -LAY_OFFSET_DEG
    bearing = math.radians((threat_bearing_deg + side) % 360.0)
    return (ship_x + LAY_DISTANCE_NM * math.sin(bearing),
            ship_y - LAY_DISTANCE_NM * math.cos(bearing))


def seduction_probability(defeat_probability: float, arrival_s: float) -> float:
    """Swerling-1 ship echo against the cloud echo at the missile's arrival.

    The profiled defeat probability is the fully bloomed case,
    P = 1 - exp(-sigma_c / sigma_s); a young cloud has only the bloom
    fraction of sigma_c."""
    p = max(0.0, min(1.0, defeat_probability))
    if p >= 1.0:
        return 1.0 if arrival_s > 0.0 else 0.0
    ratio = -math.log(1.0 - p)
    bloom = 1.0 - math.exp(-max(0.0, arrival_s) / BLOOM_S)
    return 1.0 - math.exp(-ratio * bloom)


def valid_row(row) -> bool:
    def number(value, low, high):
        return (type(value) in (int, float) and math.isfinite(value)
                and low <= value <= high)
    return (isinstance(row, dict) and set(row) == FIELDS
            and type(row["seq"]) is int and 0 < row["seq"] <= 2**63 - 1
            and number(row["x"], -1_000_000, 1_000_000)
            and number(row["y"], -1_000_000, 1_000_000)
            and number(row["age_s"], 0.0, LIFE_S))
