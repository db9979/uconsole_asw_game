"""Knuckles: the bubble field a hull leaves in a hard turn at speed.

When a ship or a boat puts the rudder hard over at high speed, its stern
sweeps sideways through the water and leaves a slick of churned, bubbly
water (the knuckle) where it turned.  For a few minutes the bubbles

* damp sound that passes through them (passive and active sonar lose
  ``LOSS_DB`` x strength on a path crossing a knuckle),
* return an echo of their own to an active ping (a false target without
  Doppler), and
* can pull a wake-homing torpedo into them, which then circles in the
  cloud instead of following the wake.

Every platform makes them the same way, so both sides can use and suffer
them.  The field is simulation state (saved, root key ``knuckles``); its
draws are stateless (``detrand``) and it reads no wall clock.
"""

from __future__ import annotations

import math

from src.core import detrand

MAX_KNUCKLES = 24
# A knuckle forms above this speed (kn) and this turn rate (deg/s)...
SPEED_MIN_KN = 12.0
SPEED_FULL_KN = 26.0
TURN_MIN_DEG_S = 0.9
TURN_FULL_DEG_S = 1.8
# ...at most one every SPACING_S per platform, and lasts LIFE_S.
SPACING_S = 15.0
DECAY_S = 100.0
LIFE_S = 300.0
# Size of the slick (NM, about 150 m) and what it does at full strength.
RADIUS_NM = 0.08
LOSS_DB = 12.0
LOSS_MAX_DB = 20.0
ECHO_TS_DB = 4.0          # target-strength offset of a fresh knuckle echo
ECHO_DEPTH_M = 8.0
ECHO_MIN_STRENGTH = 0.15
LURE_MIN_STRENGTH = 0.3   # a torpedo is drawn in only by a strong cloud
LURE_SHARE = 0.6          # chance at full strength that it is drawn in
FIELDS = ("owner", "x", "y", "t", "strength")


def formation_strength(speed_kn: float, turn_deg_s: float) -> float:
    """Strength 0..1 of a knuckle laid at ``speed_kn`` turning ``turn_deg_s``."""
    speed = (abs(float(speed_kn)) - SPEED_MIN_KN) / (SPEED_FULL_KN - SPEED_MIN_KN)
    turn = (abs(float(turn_deg_s)) - TURN_MIN_DEG_S) / (TURN_FULL_DEG_S - TURN_MIN_DEG_S)
    if speed <= 0.0 or turn <= 0.0:
        return 0.0
    return round(min(1.0, 0.35 + 0.65 * speed) * min(1.0, 0.5 + 0.5 * turn), 4)


def _segment_distance(px, py, x0, y0, x1, y1) -> float:
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    k = 0.0 if length2 <= 0.0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length2))
    return math.hypot(px - (x0 + k * dx), py - (y0 + k * dy))


class KnuckleField:
    """The knuckles in the water (bounded, oldest dropped first)."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self.now = 0.0

    # --- life --------------------------------------------------------------

    def advance(self, now: float) -> None:
        self.now = float(now)
        self.items = [item for item in self.items if 0.0 <= self.now - item["t"] <= LIFE_S]

    def strength(self, item: dict, now: float | None = None) -> float:
        age = (self.now if now is None else now) - item["t"]
        if age < 0.0 or age > LIFE_S:
            return 0.0
        return item["strength"] * math.exp(-age / DECAY_S)

    def observe(self, owner, x: float, y: float, speed_kn: float,
                turn_deg_s: float, now: float):
        """A platform's step: lay a knuckle if it turns hard at speed.
        Returns the new knuckle or None."""
        strength = formation_strength(speed_kn, turn_deg_s)
        if strength <= 0.0:
            return None
        if any(item["owner"] == owner and now - item["t"] < SPACING_S for item in self.items):
            return None
        item = dict(owner=owner, x=float(x), y=float(y), t=float(now), strength=strength)
        self.items.append(item)
        del self.items[:-MAX_KNUCKLES]
        return item

    def fresh_from(self, owner, now: float, within_s: float) -> bool:
        """Did ``owner`` lay a knuckle in the last ``within_s`` before this one?"""
        return any(item["owner"] == owner and 0.0 < now - item["t"] <= within_s
                   for item in self.items)

    # --- effects -----------------------------------------------------------

    def path_loss_db(self, x0: float, y0: float, x1: float, y1: float) -> float:
        """Extra loss (dB) of sound on the path between two points."""
        loss = 0.0
        for item in self.items:
            strength = self.strength(item)
            if strength < 0.02:
                continue
            if _segment_distance(item["x"], item["y"], x0, y0, x1, y1) <= RADIUS_NM:
                loss += LOSS_DB * strength
        return min(LOSS_MAX_DB, loss)

    def echoes(self) -> list:
        """``(index, item, strength)`` of the knuckles that still return an echo."""
        rows = []
        for index, item in enumerate(self.items):
            strength = self.strength(item)
            if strength >= ECHO_MIN_STRENGTH:
                rows.append((index, item, strength))
        return rows

    def lure(self, x: float, y: float, torpedo_key: int):
        """The knuckle a wake-homing torpedo at (x, y) is drawn into, or None."""
        for item in self.items:
            strength = self.strength(item)
            if strength < LURE_MIN_STRENGTH:
                continue
            if math.hypot(item["x"] - x, item["y"] - y) > 2.0 * RADIUS_NM:
                continue
            draw = detrand.u01(int(item["t"] * 1000.0) & 0x7FFFFFFF, "knuckle-lure",
                               int(torpedo_key) & 0x7FFFFFFF)
            if draw < LURE_SHARE * strength:
                return item
        return None

    # --- save --------------------------------------------------------------

    def serialize(self) -> list:
        return [dict(item) for item in self.items]

    @staticmethod
    def valid(rows) -> bool:
        if not isinstance(rows, list) or len(rows) > MAX_KNUCKLES:
            return False
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(FIELDS):
                return False
            owner = row["owner"]
            if not (owner == "frigate" or (type(owner) is int and 0 <= owner < 2 ** 31)):
                return False
            for key in ("x", "y", "t", "strength"):
                value = row[key]
                if type(value) not in (int, float) or not math.isfinite(value):
                    return False
            if not 0.0 <= row["strength"] <= 1.0 or row["t"] < 0.0:
                return False
        return True

    def restore(self, rows, now: float) -> None:
        self.items = [dict(owner=row["owner"], x=float(row["x"]), y=float(row["y"]),
                           t=float(row["t"]), strength=float(row["strength"]))
                      for row in rows]
        self.now = float(now)
