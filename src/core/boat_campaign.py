"""Boat campaign ("Feldzug" of the submarine): a theatre of boat missions.

The submarine's counterpart to ``src/core/campaign.py``: its own file
(``boat_campaign.json`` beside the save slots), never inside a game save.
The front situation and the hotspots are the theatre
(``src/core/theatre.py``); between missions the boat carries, exactly as
before the theatre, its torpedoes, its hull damage and the captain's
standing with U-boat command (reputation 0..100).  After each mission the
boat calls at its base: a full refit (full torpedo load, hull repaired)
costs standing for the lost time; a quick turnaround sails on at once with
a part load by standing and the damage aboard.

A hotspot is an ordinary boat mission with the uConsole on the boat side;
the carried stock and damage are put aboard the crewed boat when it starts.
All missions use seeds with the same ``seed % 128`` so the real-sector world
mode keeps the same sea area.  A version-1 file (the former fixed chain of
five legs) is lifted on load (``migrate_v1``).
"""

from __future__ import annotations

import os

from src.core import config, theatre as theatre_model
from src.core.campaign import (REPUTATION_LOSS, REPUTATION_QUICK, REPUTATION_REFIT,
                               REPUTATION_RELIEVED, REPUTATION_START, REPUTATION_WIN,
                               read_campaign_file, resupply,
                               valid_campaign_core, valid_legacy_history)
from src.core.theatre import Theatre

VERSION = 2
LEGACY_VERSION = 1
LEGACY_LEGS = ("s6_aufklaerung", "s5_durchbruch", "s7_geleitzug", "s5_durchbruch",
               "s7_geleitzug")
FILE_NAME = "boat_campaign.json"
STATE_FIELDS = frozenset({"version", "base_seed", "reputation", "torpedoes",
                          "damage", "status", "port", "history", "theatre"})
HISTORY_FIELDS = frozenset({"scenario", "result"})
LEGACY_FIELDS = frozenset({"version", "base_seed", "leg", "reputation", "torpedoes",
                           "damage", "status", "port", "history"})
LEGACY_HISTORY_FIELDS = frozenset({"leg", "result"})
TORPEDOES_MAX = 40                # above any boat's load; ``None`` is a full load
DAMAGE_CARRY_MAX = 60             # hull damage (%) a boat can sail with
# The boat's side of ``boat_debrief.outcome``: the missions it won.
WINS = ("won", "broke_through", "reported", "convoy_sunk", "passed", "landed",
        "supply_sunk", "escaped", "survived", "objective")
# Outcomes that cost the enemy a ship (besides the frigate, outcome "won").
ENEMY_SHIP_SUNK = ("convoy_sunk", "supply_sunk")


def _any(_row) -> bool:
    return True


class BoatCampaignState:
    """One boat campaign's theatre and carried state."""

    side = "boat"

    def __init__(self, base_seed: int):
        self.base_seed = int(base_seed)
        self.reputation = REPUTATION_START
        self.torpedoes: int | None = None      # a full load
        self.damage = 0
        self.status = "active"
        self.port = False
        self.history: list[dict] = []
        self.theatre = Theatre(self.side, self.base_seed)

    @property
    def missions(self) -> int:
        return len(self.history)

    @property
    def outcome(self):
        return self.theatre.outcome

    def mission_seed(self) -> int:
        """Same ``seed % 128`` (same real sector) for every mission."""
        return self.theatre.mission_seed()

    def scenario_of(self, hotspot_id) -> str | None:
        spot = self.theatre.hotspot(hotspot_id)
        return None if spot is None else spot["scenario"]

    def can_sail(self) -> bool:
        return self.status == "active" and not self.port

    def quick_load(self) -> int | None:
        """Torpedoes aboard after a quick turnaround (``None`` stays full)."""
        if self.torpedoes is None:
            return None
        return min(TORPEDOES_MAX, self.torpedoes + resupply(self.reputation) // 2)

    def record(self, hotspot_id: int, *, won: bool, boat_sunk: bool,
               torpedoes_left: int, damage: float, enemy_sunk: int = 0) -> bool:
        """A mission ended: standing, theatre, carried state, the base next."""
        scenario = self.scenario_of(hotspot_id)
        if not self.can_sail() or scenario is None:
            return False
        result = "sunk" if boat_sunk else ("won" if won else "lost")
        delta = REPUTATION_WIN if won else REPUTATION_LOSS
        self.reputation = int(config.clamp(self.reputation + delta, 0, 100))
        self.torpedoes = int(config.clamp(torpedoes_left, 0, TORPEDOES_MAX))
        self.damage = int(config.clamp(round(damage), 0, DAMAGE_CARRY_MAX))
        self.theatre.resolve(hotspot_id, won=won, enemy_sunk=enemy_sunk, sunk=boat_sunk,
                             relieved=self.reputation < REPUTATION_RELIEVED)
        self.history.append(dict(scenario=scenario, result=result))
        self.status = theatre_model.status_of(self.theatre.outcome)
        self.port = self.status == "active"
        return True

    def call_at_port(self, choice: str) -> bool:
        """``refit`` or ``quick``; then the next hotspot can be chosen."""
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
        return True

    # --- file ----------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, base_seed=self.base_seed,
                    reputation=self.reputation, torpedoes=self.torpedoes,
                    damage=self.damage, status=self.status, port=self.port,
                    history=[dict(row) for row in self.history],
                    theatre=self.theatre.serialize())

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False
        if not _valid_carried(state, VERSION):
            return False
        return valid_campaign_core(state, "boat", HISTORY_FIELDS, _any)

    @classmethod
    def restore(cls, state) -> "BoatCampaignState":
        if isinstance(state, dict) and state.get("version") == LEGACY_VERSION:
            state = migrate_v1(state)
        if not cls.valid_state(state):
            raise ValueError("invalid boat campaign state")
        campaign = cls.__new__(cls)
        campaign.base_seed = state["base_seed"]
        for key in ("reputation", "torpedoes", "damage", "status", "port"):
            setattr(campaign, key, state[key])
        campaign.history = [dict(row) for row in state["history"]]
        campaign.theatre = Theatre.restore("boat", state["base_seed"], state["theatre"])
        return campaign


def _valid_carried(state, version: int) -> bool:
    def integer(key, low, high):
        return type(state[key]) is int and low <= state[key] <= high

    return (integer("version", version, version)
            and integer("base_seed", 1, 999_999_999)
            and integer("reputation", 0, 100)
            and integer("damage", 0, DAMAGE_CARRY_MAX)
            and (state["torpedoes"] is None or integer("torpedoes", 0, TORPEDOES_MAX)))


def valid_v1(state) -> bool:
    """The former fixed-chain format (version 1), checked as strictly as before."""
    if not isinstance(state, dict) or set(state) != LEGACY_FIELDS:
        return False
    if not _valid_carried(state, LEGACY_VERSION):
        return False
    if type(state["leg"]) is not int or not 0 <= state["leg"] < len(LEGACY_LEGS):
        return False
    return valid_legacy_history(state, len(LEGACY_LEGS), LEGACY_HISTORY_FIELDS, _any)


def migrate_v1(state) -> dict:
    """Pure: a version-1 file as version 2 (unchanged when it is not a valid
    version-1 file, so the version-2 check rejects it)."""
    if not valid_v1(state):
        return state
    results = [row["result"] for row in state["history"]]
    theatre = Theatre.from_legacy("boat", state["base_seed"], results, state["status"])
    return dict(version=VERSION, base_seed=state["base_seed"],
                reputation=state["reputation"], torpedoes=state["torpedoes"],
                damage=state["damage"],
                status=theatre_model.status_of(theatre.outcome),
                port=state["port"] and theatre.outcome is None,
                history=[dict(scenario=LEGACY_LEGS[row["leg"]], result=row["result"])
                         for row in state["history"]],
                theatre=theatre.serialize())


def campaign_path() -> str:
    return os.path.join(config.SAVE_DIR, FILE_NAME)


def load_campaign() -> BoatCampaignState | None:
    """The saved boat campaign, or ``None`` (missing, symlinked or invalid)."""
    data = read_campaign_file(campaign_path())
    if data is None:
        return None
    try:
        return BoatCampaignState.restore(data)
    except (ValueError, TypeError, KeyError):
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
    """The carried torpedo stock and hull damage, on the crewed boat.  A
    mission that starts the boat damaged (the homecoming) keeps its own
    damage when it is the greater: the carried state never makes a mission
    easier than from the scenario menu."""
    if state.torpedoes is not None:
        battery = sub.weapon_battery
        if battery is not None:
            battery.limit_to(state.torpedoes)
            sub.torpedoes_left = battery.remaining_total
        else:
            sub.torpedoes_left = min(sub.torpedoes_left, state.torpedoes)
    sub.damage = max(float(sub.damage), float(state.damage))
