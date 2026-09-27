"""Campaign: six linked missions in one sector with consequences.

The campaign lives in its own file (``campaign.json`` beside the save
slots), never inside a v21 game save.  Between missions it carries the
torpedo stock, compartments left damaged, a lost helicopter and the
captain's standing with fleet headquarters (reputation 0..100).  After each
mission the ship calls at port: a full refit (restock by reputation,
repairs, a new helicopter) costs standing for the lost time; a quick
turnaround sails on at once with half the restock and the damage aboard.

A campaign mission is an ordinary scenario run with one difference: its
torpedo count is the carried stock (``difficulty_override``).  All missions
use seeds with the same ``seed % 128`` so the real-sector world mode keeps
the same sea area.  Saving during a mission uses the normal slots; such a
save is a plain mission, and the campaign continues from its own file by
starting the current leg again.
"""

from __future__ import annotations

import json
import os

from src.core import config

VERSION = 1
LEGS = ("s1_patrouille", "s2_doppeljagd", "s1_patrouille", "s3_abfang",
        "s2_doppeljagd", "s3_abfang")
COMPARTMENTS = ("bridge", "sonar", "weapons", "opz", "radio", "engine", "flightdeck",
                "hull_left", "hull_right")
STATUSES = ("active", "won", "lost")
RESULTS = ("won", "lost", "sunk")
FILE_NAME = "campaign.json"
STATE_FIELDS = frozenset({"version", "base_seed", "leg", "reputation", "torpedoes",
                          "damaged", "helo_lost", "status", "port", "history"})
HISTORY_FIELDS = frozenset({"leg", "result", "score"})

REPUTATION_START = 50
REPUTATION_WIN = 15
REPUTATION_LOSS = -20
REPUTATION_INCIDENT = -10
REPUTATION_TASK = 3
REPUTATION_REFIT = -5
REPUTATION_QUICK = 3
REPUTATION_RELIEVED = 10          # below this the captain is relieved
TORPEDOES_MIN, TORPEDOES_MAX = 2, 10   # the difficulty field's bounds


def resupply(reputation: int) -> int:
    """Torpedoes the base issues on a full refit (4 to 8 by standing)."""
    return 4 + int(round(reputation / 25.0))


class CampaignState:
    """One campaign's progress and carried state."""

    def __init__(self, base_seed: int):
        self.base_seed = int(base_seed)
        self.leg = 0
        self.reputation = REPUTATION_START
        self.torpedoes = resupply(REPUTATION_START)
        self.damaged: list[str] = []
        self.helo_lost = False
        self.status = "active"
        self.port = False          # a mission ended; the port choice is due
        self.history: list[dict] = []

    # --- the next mission ------------------------------------------------------

    @property
    def scenario_key(self) -> str:
        return LEGS[min(self.leg, len(LEGS) - 1)]

    def mission_seed(self) -> int:
        """Same ``seed % 128`` (same real sector) for every leg."""
        seed = self.base_seed + 128 * self.leg
        return seed if seed < 1_000_000_000 else self.base_seed

    def difficulty_override(self) -> dict:
        return {"torpedo_count": int(config.clamp(self.torpedoes, TORPEDOES_MIN,
                                                  TORPEDOES_MAX))}

    def can_sail(self) -> bool:
        return self.status == "active" and not self.port

    # --- results -----------------------------------------------------------------

    def record(self, *, won: bool, ship_sunk: bool, score: int, torpedoes_left: int,
               damaged, helo_lost: bool, incident: bool, tasks_done: int,
               tasks_failed: int) -> None:
        """A campaign mission ended: standing, carried state, port next."""
        if not self.can_sail():
            return
        result = "sunk" if ship_sunk else ("won" if won else "lost")
        self.history.append(dict(leg=self.leg, result=result, score=int(score)))
        delta = REPUTATION_WIN if won else REPUTATION_LOSS
        delta += REPUTATION_INCIDENT if incident else 0
        delta += REPUTATION_TASK * (int(tasks_done) - int(tasks_failed))
        self.reputation = int(config.clamp(self.reputation + delta, 0, 100))
        self.torpedoes = int(config.clamp(torpedoes_left, 0, TORPEDOES_MAX))
        self.damaged = sorted({name for name in damaged if name in COMPARTMENTS})
        self.helo_lost = bool(helo_lost)
        if ship_sunk or self.reputation < REPUTATION_RELIEVED:
            self.status = "lost"
        elif self.leg >= len(LEGS) - 1:
            self.status = "won"
        else:
            self.port = True

    def call_at_port(self, choice: str) -> bool:
        """``refit`` or ``quick``; then the next leg is ready."""
        if self.status != "active" or not self.port or choice not in ("refit", "quick"):
            return False
        issue = resupply(self.reputation)
        if choice == "refit":
            self.torpedoes = max(self.torpedoes, issue)
            self.damaged = []
            self.helo_lost = False
            self.reputation = int(config.clamp(self.reputation + REPUTATION_REFIT, 0, 100))
        else:
            self.torpedoes = min(TORPEDOES_MAX, self.torpedoes + issue // 2)
            self.reputation = int(config.clamp(self.reputation + REPUTATION_QUICK, 0, 100))
        self.torpedoes = int(config.clamp(self.torpedoes, TORPEDOES_MIN, TORPEDOES_MAX))
        self.port = False
        self.leg += 1
        return True

    # --- file ----------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, base_seed=self.base_seed, leg=self.leg,
                    reputation=self.reputation, torpedoes=self.torpedoes,
                    damaged=list(self.damaged), helo_lost=self.helo_lost,
                    status=self.status, port=self.port,
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
                and integer("torpedoes", 0, TORPEDOES_MAX)):
            return False
        damaged = state["damaged"]
        if (not isinstance(damaged, list) or damaged != sorted(set(damaged))
                or any(name not in COMPARTMENTS for name in damaged)):
            return False
        if type(state["helo_lost"]) is not bool or type(state["port"]) is not bool:
            return False
        if state["status"] not in STATUSES or (state["port"] and state["status"] != "active"):
            return False
        history = state["history"]
        if not isinstance(history, list) or len(history) > len(LEGS):
            return False
        for index, row in enumerate(history):
            if (not isinstance(row, dict) or set(row) != HISTORY_FIELDS
                    or type(row["leg"]) is not int or row["leg"] != index
                    or row["result"] not in RESULTS
                    or type(row["score"]) is not int or abs(row["score"]) > 10_000_000):
                return False
        # Legs played so far: the current one once its result is in.
        played = state["leg"] + (1 if state["port"] or state["status"] != "active" else 0)
        return len(history) == played

    @classmethod
    def restore(cls, state) -> "CampaignState":
        if not cls.valid_state(state):
            raise ValueError("invalid campaign state")
        campaign = cls(state["base_seed"])
        for key in ("leg", "reputation", "torpedoes", "helo_lost", "status", "port"):
            setattr(campaign, key, state[key])
        campaign.damaged = list(state["damaged"])
        campaign.history = [dict(row) for row in state["history"]]
        return campaign


def campaign_path() -> str:
    return os.path.join(config.SAVE_DIR, FILE_NAME)


def load_campaign() -> CampaignState | None:
    """The saved campaign, or ``None`` (missing, symlinked or invalid)."""
    path = campaign_path()
    try:
        if os.path.islink(path) or os.path.islink(config.SAVE_DIR):
            return None
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream, parse_constant=_reject_constant)
        return CampaignState.restore(data)
    except (OSError, ValueError, TypeError):
        return None


def _reject_constant(name):
    raise ValueError(name)


def save_campaign(state: CampaignState) -> bool:
    """Atomic write beside the save slots; False leaves the old file."""
    from src.data.user_content import ContentValidationError, atomic_write_json
    try:
        atomic_write_json(campaign_path(), state.serialize())
        return True
    except (OSError, ValueError, ContentValidationError):
        return False


def delete_campaign() -> None:
    path = campaign_path()
    if os.path.isfile(path) and not os.path.islink(path):
        os.remove(path)
