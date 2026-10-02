"""The character of a computer commander: what the enemy is like this time.

Every AI submarine commander and the AI hunter frigate's captain get one of
four characters from the seed (a stateless ``detrand`` draw, nothing saved):

* ``daring``: attacks early, gives way briefly, rarely lies in wait;
* ``fox``: waits, lies in wait under the layer and by wrecks, pings little;
* ``cautious``: gives way long and wide, holds fire, keeps its distance;
* ``hunter``: stubborn, stays on a contact and runs a lost bearing down.

Each character is a handful of factors on existing tactics (attack rate,
evasion time, the distance it lies in wait at; the hunter's closing speed,
ping interval, firing range and how long it runs down a lost bearing), never
a new random draw, so a game stays deterministic and the four average out
(the fairness harness measures both sides).  HQ sometimes hints at the
character, the debrief names it.
"""

from __future__ import annotations

from types import MappingProxyType

from src.core import detrand

KINDS = ("daring", "fox", "cautious", "hunter")

# Submarine commander: attack rate, evasion time after a ping, lurk distance.
SUB = MappingProxyType({
    "daring": MappingProxyType(dict(attack=1.5, evade=0.6, lurk=0.6)),
    "fox": MappingProxyType(dict(attack=0.9, evade=1.0, lurk=1.5)),
    "cautious": MappingProxyType(dict(attack=0.6, evade=1.5, lurk=1.1)),
    "hunter": MappingProxyType(dict(attack=1.15, evade=0.7, lurk=1.3)),
})
# Hunter frigate captain: closing speed, ping interval, firing range, lead time.
HUNTER = MappingProxyType({
    "daring": MappingProxyType(dict(close=1.3, ping=0.6, fire=1.15, lead=0.8)),
    "fox": MappingProxyType(dict(close=0.8, ping=1.5, fire=1.0, lead=1.2)),
    "cautious": MappingProxyType(dict(close=0.9, ping=1.2, fire=0.8, lead=1.0)),
    "hunter": MappingProxyType(dict(close=1.1, ping=0.9, fire=1.0, lead=1.6)),
})
# HQ hints at the enemy's character this often, once, early in the mission.
HINT_CHANCE = 0.6
HINT_AT_S = 90.0


def sub_kind(sub) -> str:
    """The character of one submarine's commander."""
    return KINDS[detrand.bits(int(sub.sensor_seed), "commander", int(sub.id)) % len(KINDS)]


def sub_factor(sub, name: str) -> float:
    return SUB[sub_kind(sub)][name]


def hunter_kind(seed: int) -> str:
    """The character of the AI hunter frigate's captain."""
    return KINDS[detrand.bits(int(seed), "hunter-commander", 1) % len(KINDS)]


def hunter_factor(game, name: str) -> float:
    return HUNTER[hunter_kind(game.seed)][name]


def hinted(seed: int, side: str) -> bool:
    """Whether HQ hints at the enemy's character in this mission."""
    return detrand.u01(int(seed), "commander-hint", 1 if side == "uboot" else 0) < HINT_CHANCE
