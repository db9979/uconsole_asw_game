"""Stateless, counter-based deterministic randomness.

New simulation draws use these helpers instead of adding more mutable
``random.Random`` streams: a draw is a pure function of ``(seed, tag, key,
counter)``.  Nothing has to be saved, the existing saved streams keep their
sequences, and the result never depends on hash randomization, wall clock,
render rate or evaluation order.
"""

from __future__ import annotations

import math

_MASK = (1 << 64) - 1


def _mix(value: int) -> int:
    """splitmix64 finalizer."""
    value = (value + 0x9E3779B97F4A7C15) & _MASK
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK
    return value ^ (value >> 31)


def _tag_value(tag: str) -> int:
    # FNV-1a 64 over UTF-8: stable across processes (unlike ``hash``).
    value = 0xCBF29CE484222325
    for byte in tag.encode("utf-8"):
        value = ((value ^ byte) * 0x100000001B3) & _MASK
    return value


def bits(seed: int, tag: str, *keys: int) -> int:
    """Return 64 deterministic bits for integer ``keys`` in stream ``tag``."""
    value = _mix((int(seed) & _MASK) ^ _tag_value(tag))
    for key in keys:
        value = _mix(value ^ (int(key) & _MASK))
    return value


def u01(seed: int, tag: str, *keys: int) -> float:
    """Uniform float in ``[0, 1)`` with 53 bits of resolution."""
    return (bits(seed, tag, *keys) >> 11) * (1.0 / (1 << 53))


def uniform(low: float, high: float, seed: int, tag: str, *keys: int) -> float:
    return low + (high - low) * u01(seed, tag, *keys)


def normal(seed: int, tag: str, *keys: int) -> float:
    """Standard normal draw (Box-Muller on two independent sub-draws)."""
    u1 = max(u01(seed, tag, *keys, 1), 1e-300)
    u2 = u01(seed, tag, *keys, 2)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def phase(seed: int, tag: str, *keys: int) -> float:
    """Deterministic phase in ``[0, 2*pi)``."""
    return 2.0 * math.pi * u01(seed, tag, *keys)
