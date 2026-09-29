"""The frigate's ASW rocket launcher (RBU/Bofors type, save ``rbu``).

A salvo of six rockets flies ballistically to the aim point and each round
sinks fast to its set depth, where it detonates.  Two patterns:

- ``attack``: against a located submarine contact 0.4-3 NM away, one round
  on the aim point and five on a ring of 80 m around it.  Needs a fresh
  range fix; the small charges only hurt close to the boat, so a stale or
  rough fix wastes the salvo.
- ``defence``: against an incoming torpedo on the bearing of a torpedo
  warning, six rounds in a line 0.3-0.8 NM out along that bearing set
  shallow.  A round that detonates close to a running torpedo destroys it.

The rounds hitting the water are loud: every submarine within
``SPLASH_HEARD_NM`` hears the splashes (the crewed boat gets the bearing,
an AI boat starts to evade), so the boat has the time of flight and the
sinking to get out of the way.

Pure and deterministic; the whole state is the rounds in flight or in the
water plus the store and the reload.  Gameplay values of a fictional
frigate, not real weapon data.
"""

from __future__ import annotations

import math

from src.physics import torpedo_dyn

VERSION = 1
STOCK = 36
SALVO = 6
RELOAD_S = 60.0
RANGE_NM = (0.4, 3.0)
FLIGHT_SPEED_KN = 400.0
SINK_RATE_MPS = 11.0
CHARGE_KG = 23.0
MIN_DEPTH_M = 10.0
MAX_DEPTH_M = 300.0
DAMAGE_RADIUS_M = 60.0            # beyond this the shock only alerts
ATTACK_RING_M = 80.0
DEFENCE_RANGES_NM = (0.30, 0.40, 0.50, 0.60, 0.70, 0.80)
DEFENCE_DEPTH_M = 15.0
DEFENCE_WARNING_AGE_S = 5.0
TORPEDO_KILL_M = 35.0
SPLASH_HEARD_NM = 3.0
MAX_ROUNDS = 24
MODES = ("attack", "defence")
ROUND_FIELDS = frozenset({"seq", "x", "y", "depth", "set_depth", "flight_s", "lead", "mode"})
STATE_FIELDS = frozenset({"version", "seq", "rounds", "rockets", "reload_s"})


def damage(slant_m: float) -> float:
    """Submarine damage (percent) of one round at this slant distance."""
    if slant_m > DAMAGE_RADIUS_M:
        return 0.0
    return min(100.0, 100.0 * torpedo_dyn.shock_factor(CHARGE_KG, slant_m)
               / torpedo_dyn.SF_LETHAL_SUBMARINE)


def flight_s(distance_nm: float) -> float:
    return max(0.0, distance_nm) / (FLIGHT_SPEED_KN / 3600.0)


def attack_points(x: float, y: float) -> list:
    """Aim point and a ring of five around it (chart NM)."""
    ring = ATTACK_RING_M / 1852.0
    points = [(x, y)]
    for index in range(SALVO - 1):
        rad = math.radians(index * 360.0 / (SALVO - 1))
        points.append((x + ring * math.sin(rad), y - ring * math.cos(rad)))
    return points


def defence_points(x: float, y: float, bearing: float) -> list:
    """A line of rounds out along the torpedo's bearing (chart NM)."""
    rad = math.radians(bearing)
    return [(x + distance * math.sin(rad), y - distance * math.cos(rad))
            for distance in DEFENCE_RANGES_NM[:SALVO]]


class RbuRound:
    """One rocket: in flight until ``flight_s`` runs out, then sinking."""

    __slots__ = ("seq", "x", "y", "depth", "set_depth", "flight_s", "lead", "mode")

    def __init__(self, seq: int, x: float, y: float, set_depth: float, flight: float,
                 lead: bool, mode: str, depth: float = 0.0):
        self.seq = int(seq)
        self.x, self.y = float(x), float(y)
        self.set_depth = float(set_depth)
        self.flight_s = float(flight)
        self.lead = bool(lead)
        self.mode = mode
        self.depth = float(depth)

    @property
    def flying(self) -> bool:
        return self.flight_s > 0.0

    def update(self, dt: float, bottom_m: float):
        """Advance; returns ``"splash"`` when it hits the water in this step,
        ``"detonate"`` when it goes off, else None."""
        dt = max(0.0, dt)
        if self.flight_s > 0.0:
            self.flight_s = max(0.0, self.flight_s - dt)
            if self.flight_s > 0.0:
                return None
            return "splash"
        floor = min(self.set_depth, max(0.0, bottom_m))
        self.depth = min(floor, self.depth + SINK_RATE_MPS * dt)
        return "detonate" if self.depth >= floor - 1e-9 else None

    def serialize(self) -> dict:
        return {"seq": self.seq, "x": self.x, "y": self.y, "depth": self.depth,
                "set_depth": self.set_depth, "flight_s": self.flight_s,
                "lead": self.lead, "mode": self.mode}

    @classmethod
    def restore(cls, row: dict) -> "RbuRound":
        return cls(row["seq"], row["x"], row["y"], row["set_depth"], row["flight_s"],
                   row["lead"], row["mode"], row["depth"])


def _finite(value, low: float, high: float) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value <= high)


def valid_state(state, world_size_nm: float) -> bool:
    """Strict check of the saved launcher."""
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        return False
    if type(state["version"]) is not int or state["version"] != VERSION:
        return False
    seq, rounds = state["seq"], state["rounds"]
    if (type(seq) is not int or not 0 <= seq <= 2**63 - 1
            or not isinstance(rounds, list) or len(rounds) > MAX_ROUNDS):
        return False
    if (type(state["rockets"]) is not int or not 0 <= state["rockets"] <= STOCK
            or not _finite(state["reload_s"], 0.0, RELOAD_S)):
        return False
    seen = set()
    for row in rounds:
        if (not isinstance(row, dict) or set(row) != ROUND_FIELDS
                or type(row["seq"]) is not int or not 1 <= row["seq"] <= seq
                or row["seq"] in seen or row["mode"] not in MODES
                or type(row["lead"]) is not bool
                or not _finite(row["x"], -world_size_nm, 2 * world_size_nm)
                or not _finite(row["y"], -world_size_nm, 2 * world_size_nm)
                or not _finite(row["set_depth"], MIN_DEPTH_M, MAX_DEPTH_M)
                or not _finite(row["depth"], 0.0, row["set_depth"])
                or not _finite(row["flight_s"], 0.0, flight_s(RANGE_NM[1]) + 1.0)
                or (row["flight_s"] > 0.0 and row["depth"] != 0.0)):
            return False
        seen.add(row["seq"])
    # Every round in flight or in the water came out of the store.
    return len(rounds) <= STOCK - state["rockets"]
