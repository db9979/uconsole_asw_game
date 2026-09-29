"""The frigate's depth charges and own ASROC stores.

A depth-charge pattern is five charges: three rolled from the stern rack
along the wake and two thrown abeam. Each sinks at a steady rate to its
set depth (or the seabed) and detonates there; the shock factor of its
charge at the slant distance damages every submarine it reaches. The
ASROC is the ship-launched stand-off weapon: the same ballistic transit
to a fixed datum as the friendly warships' ASROC (``src/weapons/asw.py``),
carrying the helicopter's lightweight torpedo.

Pure and deterministic: no randomness, no wall clock; the whole state is
the charges in the water plus the stores in the save's ``asw`` block.
Gameplay values of a fictional frigate, not real weapon data.
"""

from __future__ import annotations

import math

from src.physics import torpedo_dyn

DEPTH_CHARGE_STOCK = 20
PATTERN_SIZE = 5
PATTERN_RELOAD_S = 45.0
SINK_RATE_MPS = 3.5
CHARGE_KG = 90.0
MIN_DROP_SPEED_KN = 10.0       # slower and the own stern takes the blast
MIN_DEPTH_M = 15.0
MAX_DEPTH_M = 300.0
# Pattern geometry in metres: (astern, starboard) of the stern at the drop.
PATTERN_OFFSETS_M = ((20.0, 0.0), (80.0, 0.0), (140.0, 0.0),
                     (80.0, -70.0), (80.0, 70.0))
MAX_DEPTH_CHARGES = 64
DAMAGE_RADIUS_M = 100.0         # beyond this the shock only alerts

OWN_ASROC_STOCK = 4
OWN_ASROC_KEY = "weapon.ownship.asroc"
OWN_ASROC_SPEED_KN = 500.0
OWN_ASROC_RANGE_NM = (1.0, 10.0)


def depth_charge_damage(slant_m: float) -> float:
    """Submarine damage (percent) of one charge at this slant distance."""
    if slant_m > DAMAGE_RADIUS_M:
        return 0.0
    return min(100.0, 100.0 * torpedo_dyn.shock_factor(CHARGE_KG, slant_m)
               / torpedo_dyn.SF_LETHAL_SUBMARINE)


def pattern_points(x: float, y: float, course: float) -> list:
    """Chart points (NM) of a pattern dropped from a ship at (x, y)."""
    rad = math.radians(course)
    ahead = (math.sin(rad), -math.cos(rad))
    starboard = (math.cos(rad), math.sin(rad))
    points = []
    for astern_m, abeam_m in PATTERN_OFFSETS_M[:PATTERN_SIZE]:
        back, side = astern_m / 1852.0, abeam_m / 1852.0
        points.append((x - ahead[0] * back + starboard[0] * side,
                       y - ahead[1] * back + starboard[1] * side))
    return points


class DepthCharge:
    """One charge sinking to its set depth."""

    __slots__ = ("seq", "x", "y", "depth", "set_depth")

    def __init__(self, seq: int, x: float, y: float, set_depth: float,
                 depth: float = 0.0):
        self.seq = int(seq)
        self.x, self.y = float(x), float(y)
        self.set_depth = float(set_depth)
        self.depth = float(depth)

    def update(self, dt: float, bottom_m: float) -> bool:
        """Sink; True exactly when the charge detonates (set depth or seabed)."""
        floor = min(self.set_depth, max(0.0, bottom_m))
        self.depth = min(floor, self.depth + SINK_RATE_MPS * max(0.0, dt))
        return self.depth >= floor - 1e-9

    def serialize(self) -> dict:
        return {"seq": self.seq, "x": self.x, "y": self.y,
                "depth": self.depth, "set_depth": self.set_depth}

    @classmethod
    def restore(cls, value: dict) -> "DepthCharge":
        return cls(value["seq"], value["x"], value["y"], value["set_depth"],
                   value["depth"])


def _finite(value, low: float, high: float) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and low <= value <= high)


def valid_state(charges, seq, stores, world_size_nm: float) -> bool:
    """Strict check of the saved charges, sequence and own stores."""
    if (type(seq) is not int or not 0 <= seq <= 2**63 - 1
            or not isinstance(charges, list) or len(charges) > MAX_DEPTH_CHARGES):
        return False
    seen = set()
    for row in charges:
        if (not isinstance(row, dict)
                or set(row) != {"seq", "x", "y", "depth", "set_depth"}
                or type(row["seq"]) is not int or not 1 <= row["seq"] <= seq
                or row["seq"] in seen
                or not _finite(row["x"], -world_size_nm, 2 * world_size_nm)
                or not _finite(row["y"], -world_size_nm, 2 * world_size_nm)
                or not _finite(row["set_depth"], MIN_DEPTH_M, MAX_DEPTH_M)
                or not _finite(row["depth"], 0.0, row["set_depth"])):
            return False
        seen.add(row["seq"])
    if (not isinstance(stores, dict)
            or set(stores) != {"depth_charges", "asroc", "depth_charge_reload_s"}
            or type(stores["depth_charges"]) is not int
            or not 0 <= stores["depth_charges"] <= DEPTH_CHARGE_STOCK
            or type(stores["asroc"]) is not int
            or not 0 <= stores["asroc"] <= OWN_ASROC_STOCK
            or not _finite(stores["depth_charge_reload_s"], 0.0, PATTERN_RELOAD_S)):
        return False
    # Every charge in the water came out of the rack.
    return len(charges) <= DEPTH_CHARGE_STOCK - stores["depth_charges"]
