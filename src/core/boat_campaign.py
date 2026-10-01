"""Boat campaign: five linked boat missions with consequences.

The submarine's counterpart to ``src/core/campaign.py``: its own file
(``boat_campaign.json`` beside the save slots), never inside a game save.
Between missions it carries the boat's torpedoes, its hull damage and the
captain's standing with U-boat command (reputation 0..100).  After each
mission the boat calls at its base: a full refit (full torpedo load, hull
repaired) costs standing for the lost time; a quick turnaround sails on at
once with a part load by standing and the damage aboard.

A leg is an ordinary boat mission (scenarios 5 to 7) with the uConsole on
the boat side; the carried stock and damage are put aboard the crewed boat
when the leg starts.  All legs use seeds with the same ``seed % 128`` so the
real-sector world mode keeps the same sea area.
"""

from __future__ import annotations

import json
import os

from src.core import config
from src.core.campaign import (REPUTATION_LOSS, REPUTATION_QUICK, REPUTATION_REFIT,
                               REPUTATION_RELIEVED, REPUTATION_START, REPUTATION_WIN,
                               RESULTS, STATUSES, _reject_constant, resupply)

VERSION = 1
LEGS = ("s6_aufklaerung", "s5_durchbruch", "s7_geleitzug", "s5_durchbruch",
        "s7_geleitzug")
FILE_NAME = "boat_campaign.json"
STATE_FIELDS = frozenset({"version", "base_seed", "leg", "reputation", "torpedoes",
                          "damage", "status", "port", "history"})
HISTORY_FIELDS = frozenset({"leg", "result"})
TORPEDOES_MAX = 40                # above any boat's load; ``None`` is a full load
DAMAGE_CARRY_MAX = 60             # hull damage (%) a boat can sail with
# The boat's side of ``boat_debrief.outcome``: the missions it won.
WINS = ("won", "broke_through", "reported", "convoy_sunk", "passed", "landed",
        "supply_sunk", "escaped", "survived", "objective")


class BoatCampaignState:
    """One boat campaign's progress and carried state."""

    def __init__(self, base_seed: int):
        self.base_seed = int(base_seed)
        self.leg = 0
        self.reputation = REPUTATION_START
        self.torpedoes: int | None = None      # a full load
        self.damage = 0
        self.status = "active"
        self.port = False
        self.history: list[dict] = []

    @property
    def scenario_key(self) -> str:
        return LEGS[min(self.leg, len(LEGS) - 1)]

    def mission_seed(self) -> int:
        """Same ``seed % 128`` (same real sector) for every leg."""
        seed = self.base_seed + 128 * self.leg
        return seed if seed < 1_000_000_000 else self.base_seed

    def can_sail(self) -> bool:
        return self.status == "active" and not self.port

    def quick_load(self) -> int | None:
        """Torpedoes aboard after a quick turnaround (``None`` stays full)."""
        if self.torpedoes is None:
            return None
        return min(TORPEDOES_MAX, self.torpedoes + resupply(self.reputation) // 2)

    def record(self, *, won: bool, boat_sunk: bool, torpedoes_left: int,
               damage: float) -> None:
        """A leg ended: standing, carried state, the base next."""
        if not self.can_sail():
            return
        result = "sunk" if boat_sunk else ("won" if won else "lost")
        self.history.append(dict(leg=self.leg, result=result))
        delta = REPUTATION_WIN if won else REPUTATION_LOSS
        self.reputation = int(config.clamp(self.reputation + delta, 0, 100))
        self.torpedoes = int(config.clamp(torpedoes_left, 0, TORPEDOES_MAX))
        self.damage = int(config.clamp(round(damage), 0, DAMAGE_CARRY_MAX))
        if boat_sunk or self.reputation < REPUTATION_RELIEVED:
            self.status = "lost"
        elif self.leg >= len(LEGS) - 1:
            self.status = "won"
        else:
            self.port = True

    def call_at_port(self, choice: str) -> bool:
        """``refit`` or ``quick``; then the next leg is ready."""
        if self.status != "active" or not self.port or choice not in ("refit", "quick"):
            return False
        if choice == "refit":
            self.torpedoes = None
            self.damage = 0
            self.reputation = int(config.clamp(self.reputation + REPUTATION_REFIT, 0, 100))
        else:
            self.torpedoes = self.quick_load()
            self.reputation = int(config.clamp(self.reputation + REPUTATION_QUICK, 0, 100))
        self.port = False
        self.leg += 1
        return True

    # --- file ----------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, base_seed=self.base_seed, leg=self.leg,
                    reputation=self.reputation, torpedoes=self.torpedoes,
                    damage=self.damage, status=self.status, port=self.port,
                    history=[dict(row) for row in self.history])

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False

        def integer(key, low, high):
            return type(state[key]) is int and low <= state[key] <= high

        if not (integer("version", VERSION, VERSION)
                and integer("base_seed", 1, 999_999_999)
                and integer("leg", 0, len(LEGS) - 1)
                and integer("reputation", 0, 100)
                and integer("damage", 0, DAMAGE_CARRY_MAX)
                and (state["torpedoes"] is None or integer("torpedoes", 0, TORPEDOES_MAX))):
            return False
        if type(state["port"]) is not bool:
            return False
        if state["status"] not in STATUSES or (state["port"] and state["status"] != "active"):
            return False
        history = state["history"]
        if not isinstance(history, list) or len(history) > len(LEGS):
            return False
        for index, row in enumerate(history):
            if (not isinstance(row, dict) or set(row) != HISTORY_FIELDS
                    or type(row["leg"]) is not int or row["leg"] != index
                    or row["result"] not in RESULTS):
                return False
        played = state["leg"] + (1 if state["port"] or state["status"] != "active" else 0)
        return len(history) == played

    @classmethod
    def restore(cls, state) -> "BoatCampaignState":
        if not cls.valid_state(state):
            raise ValueError("invalid boat campaign state")
        campaign = cls(state["base_seed"])
        for key in ("leg", "reputation", "torpedoes", "damage", "status", "port"):
            setattr(campaign, key, state[key])
        campaign.history = [dict(row) for row in state["history"]]
        return campaign


def campaign_path() -> str:
    return os.path.join(config.SAVE_DIR, FILE_NAME)


def load_campaign() -> BoatCampaignState | None:
    """The saved boat campaign, or ``None`` (missing, symlinked or invalid)."""
    path = campaign_path()
    try:
        if os.path.islink(path) or os.path.islink(config.SAVE_DIR):
            return None
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream, parse_constant=_reject_constant)
        return BoatCampaignState.restore(data)
    except (OSError, ValueError, TypeError):
        return None


def save_campaign(state: BoatCampaignState) -> bool:
    """Atomic write beside the save slots; False leaves the old file."""
    from src.data.user_content import ContentValidationError, atomic_write_json
    try:
        atomic_write_json(campaign_path(), state.serialize())
        return True
    except (OSError, ValueError, ContentValidationError):
        return False


def put_aboard(sub, state: BoatCampaignState) -> None:
    """The carried torpedo stock and hull damage, on the crewed boat."""
    if state.torpedoes is not None:
        battery = sub.weapon_battery
        if battery is not None:
            battery.limit_to(state.torpedoes)
            sub.torpedoes_left = battery.remaining_total
        else:
            sub.torpedoes_left = min(sub.torpedoes_left, state.torpedoes)
    sub.damage = float(state.damage)
