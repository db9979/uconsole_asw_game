"""Individueller akustischer Fingerprint pro Kontakt-Instanz.

Zwei Schiffe derselben Klasse klingen nicht identisch: jeder Kontakt
zieht bei der Erschaffung Blätterzahl, Takt-Skala (Drehzahl), Linien-
Offsets (Profil-Fehler/Montagetoleranz) und Kavitationsschwelle aus dem
RNG-Stream. Der Fingerprint ist ein Datenobjekt und wird in Saves
persistiert; alte Saves (ohne Fingerprint) rollen ihn deterministisch
aus dem sensor_seed neu.
"""

import random
from dataclasses import dataclass, asdict

MIN_RATE_SCALE = 0.85
MAX_RATE_SCALE = 1.15
OFFSET_HZ = 0.5
MIN_CAV = 0.5
MAX_CAV = 1.5
MIN_BB_LEVEL = 0.5
MAX_BB_LEVEL = 1.4


@dataclass(frozen=True)
class Fingerprint:
    blades: int                 # reale Schrauben-Blätterzahl
    rate_scale: float           # 0.85..1.15 (Takt/Drehzahl)
    offsets: tuple              # 3x +/-0.5 Hz (Haupt-, 2f-, 3f-Linie)
    cavitation: float           # 0.5..1.5 (Faktor auf Tendenz)
    bb_level: float             # 0.5..1.4 (Faktor auf Breitband-Level)
    bb_low_hz: float            # Band-Unterkante
    bb_high_hz: float           # Band-Oberkante

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Fingerprint":
        return Fingerprint(
            blades=int(d.get("blades", 5)),
            rate_scale=float(d.get("rate_scale", 1.0)),
            offsets=tuple(float(o) for o in d.get("offsets", (0.0, 0.0, 0.0))),
            cavitation=float(d.get("cavitation", 1.0)),
            bb_level=float(d.get("bb_level", 1.0)),
            bb_low_hz=float(d.get("bb_low_hz", 0.0)),
            bb_high_hz=float(d.get("bb_high_hz", 0.0)))


def roll_fingerprint(rng, sig) -> Fingerprint:
    """Zieht den Fingerprint aus `rng` (6 Draw: choice, 4x uniform, 1 uniform).

    `sig` muss blade_counts, cavitation_tendency und broadband haben.
    """
    blades = rng.choice(list(sig.blade_counts) or [5])
    rate_scale = rng.uniform(MIN_RATE_SCALE, MAX_RATE_SCALE)
    offsets = tuple(rng.uniform(-OFFSET_HZ, OFFSET_HZ) for _ in range(3))
    cav = sig.cavitation_tendency * rng.uniform(MIN_CAV, MAX_CAV)
    bb_level = sig.broadband[0] * rng.uniform(MIN_BB_LEVEL, MAX_BB_LEVEL) \
        if sig.broadband else 0.0
    low = sig.broadband[1] * rng.uniform(0.8, 1.1) if sig.broadband else 0.0
    high = sig.broadband[2] * rng.uniform(0.9, 1.15) if sig.broadband else 0.0
    return Fingerprint(blades, rate_scale, offsets, cav, bb_level, low, high)


def roll_from_seed(seed: int, sig) -> Fingerprint:
    """Deterministisch aus einem Seed (z.B. sensor_seed alter Saves)."""
    return roll_fingerprint(random.Random(seed), sig)
