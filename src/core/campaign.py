"""Campaign ("Feldzug") of the frigate: a theatre of hotspots in one sector.

The campaign lives in its own file (``campaign.json`` beside the save
slots), never inside a game save.  The front situation, the enemy's
strength, the losses and the open hotspots are the theatre
(``src/core/theatre.py``); this module adds what the ship carries between
missions, exactly as before the theatre: the torpedo stock, compartments
left damaged, a lost helicopter and the captain's standing with fleet
headquarters (reputation 0..100).  After each mission the ship calls at
port: a full refit (restock by reputation, repairs, a new helicopter) costs
standing for the lost time; a quick turnaround sails on at once with half
the restock and the damage aboard.

A campaign mission is an ordinary scenario run with one difference: its
torpedo count is the carried stock (``difficulty_override``).  All missions
use seeds with the same ``seed % 128`` so the real-sector world mode keeps
the same sea area.  Saving during a mission uses the normal slots; such a
save is a plain mission, and the campaign continues from its own file by
choosing a hotspot again.  A version-1 file (the former fixed chain of six
legs) is lifted on load (``migrate_v1``).
"""

from __future__ import annotations

import json
import os

from src.core import config, theatre as theatre_model
from src.core.theatre import Theatre

VERSION = 2
LEGACY_VERSION = 1
# The legs of a version-1 file (the former fixed chain), for its migration.
LEGACY_LEGS = ("s1_patrouille", "s2_doppeljagd", "s1_patrouille", "s3_abfang",
               "s2_doppeljagd", "s3_abfang")
COMPARTMENTS = ("bridge", "sonar", "weapons", "opz", "radio", "engine", "flightdeck",
                "hull_left", "hull_right")
STATUSES = ("active", "won", "lost", "draw")
RESULTS = ("won", "lost", "sunk")
FILE_NAME = "campaign.json"
FILE_BYTES_MAX = 64 * 1024
STATE_FIELDS = frozenset({"version", "base_seed", "reputation", "torpedoes",
                          "damaged", "helo_lost", "status", "port", "history", "theatre"})
HISTORY_FIELDS = frozenset({"scenario", "result", "score"})
LEGACY_FIELDS = frozenset({"version", "base_seed", "leg", "reputation", "torpedoes",
                           "damaged", "helo_lost", "status", "port", "history"})
LEGACY_HISTORY_FIELDS = frozenset({"leg", "result", "score"})

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


def _valid_score(row) -> bool:
    return type(row["score"]) is int and abs(row["score"]) <= 10_000_000


def valid_history(history, fields, extra, side: str) -> bool:
    """Rows ``{scenario, result, ...}`` of one side's campaign, bounded."""
    if not isinstance(history, list) or len(history) > theatre_model.MISSIONS_MAX:
        return False
    roles = theatre_model.SCENARIO_ROLES[side]
    for row in history:
        if (not isinstance(row, dict) or set(row) != fields
                or type(row["scenario"]) is not str or row["scenario"] not in roles
                or type(row["result"]) is not str or row["result"] not in RESULTS
                or not extra(row)):
            return False
    return True


def valid_campaign_core(state, side: str, history_fields, extra) -> bool:
    """Status, port, history and theatre of a version-2 state agree."""
    if type(state["port"]) is not bool or type(state["status"]) is not str \
            or state["status"] not in STATUSES:
        return False
    theatre = state["theatre"]
    if not Theatre.valid_state(side, theatre):
        return False
    if theatre_model.status_of(theatre["outcome"]) != state["status"]:
        return False
    if state["port"] and state["status"] != "active":
        return False
    if not valid_history(state["history"], history_fields, extra, side):
        return False
    return len(state["history"]) == theatre["missions"]


def read_campaign_file(path: str):
    """The parsed JSON of a campaign file, or ``None`` (missing, symlinked,
    oversized or not strict JSON)."""
    try:
        if os.path.islink(path) or os.path.islink(config.SAVE_DIR):
            return None
        if not os.path.isfile(path) or os.path.getsize(path) > FILE_BYTES_MAX:
            return None
        with open(path, encoding="utf-8") as stream:
            return json.load(stream, parse_constant=_reject_constant)
    except (OSError, ValueError, TypeError, RecursionError):
        return None


def _reject_constant(name):
    raise ValueError(name)


class CampaignState:
    """One campaign's theatre and carried state."""

    side = "frigate"

    def __init__(self, base_seed: int):
        self.base_seed = int(base_seed)
        self.reputation = REPUTATION_START
        self.torpedoes = resupply(REPUTATION_START)
        self.damaged: list[str] = []
        self.helo_lost = False
        self.status = "active"
        self.port = False          # a mission ended; the port choice is due
        self.history: list[dict] = []
        self.theatre = Theatre(self.side, self.base_seed)

    # --- the next mission ------------------------------------------------------

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

    def difficulty_override(self) -> dict:
        return {"torpedo_count": int(config.clamp(self.torpedoes, TORPEDOES_MIN,
                                                  TORPEDOES_MAX))}

    def can_sail(self) -> bool:
        return self.status == "active" and not self.port

    # --- results -----------------------------------------------------------------

    def record(self, hotspot_id: int, *, won: bool, ship_sunk: bool, score: int,
               torpedoes_left: int, damaged, helo_lost: bool, incident: bool,
               tasks_done: int, tasks_failed: int, enemy_sunk: int = 0) -> bool:
        """A campaign mission ended: standing, theatre, carried state, port next."""
        scenario = self.scenario_of(hotspot_id)
        if not self.can_sail() or scenario is None:
            return False
        result = "sunk" if ship_sunk else ("won" if won else "lost")
        delta = REPUTATION_WIN if won else REPUTATION_LOSS
        delta += REPUTATION_INCIDENT if incident else 0
        delta += REPUTATION_TASK * (int(tasks_done) - int(tasks_failed))
        self.reputation = int(config.clamp(self.reputation + delta, 0, 100))
        self.torpedoes = int(config.clamp(torpedoes_left, 0, TORPEDOES_MAX))
        self.damaged = sorted({name for name in damaged if name in COMPARTMENTS})
        self.helo_lost = bool(helo_lost)
        self.theatre.resolve(hotspot_id, won=won, enemy_sunk=enemy_sunk, sunk=ship_sunk,
                             relieved=self.reputation < REPUTATION_RELIEVED)
        self.history.append(dict(scenario=scenario, result=result, score=int(score)))
        self.status = theatre_model.status_of(self.theatre.outcome)
        self.port = self.status == "active"
        return True

    def port_offer(self, choice: str) -> int:
        """Torpedoes aboard after ``refit`` or ``quick``."""
        issue = resupply(self.reputation)
        if choice == "refit":
            stock = max(self.torpedoes, issue)
        else:
            stock = min(TORPEDOES_MAX, self.torpedoes + issue // 2)
        return int(config.clamp(stock, TORPEDOES_MIN, TORPEDOES_MAX))

    def call_at_port(self, choice: str) -> bool:
        """``refit`` or ``quick``; then the next hotspot can be chosen."""
        if self.status != "active" or not self.port or choice not in ("refit", "quick"):
            return False
        self.torpedoes = self.port_offer(choice)
        if choice == "refit":
            self.damaged = []
            self.helo_lost = False
            self.reputation = int(config.clamp(self.reputation + REPUTATION_REFIT, 0, 100))
        else:
            self.reputation = int(config.clamp(self.reputation + REPUTATION_QUICK, 0, 100))
        self.port = False
        return True

    # --- file ----------------------------------------------------------------------

    def serialize(self) -> dict:
        return dict(version=VERSION, base_seed=self.base_seed,
                    reputation=self.reputation, torpedoes=self.torpedoes,
                    damaged=list(self.damaged), helo_lost=self.helo_lost,
                    status=self.status, port=self.port,
                    history=[dict(row) for row in self.history],
                    theatre=self.theatre.serialize())

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False

        def integer(key, low, high):
            return type(state[key]) is int and low <= state[key] <= high

        if not (integer("version", VERSION, VERSION)
                and integer("base_seed", 1, 999_999_999)
                and integer("reputation", 0, 100)
                and integer("torpedoes", 0, TORPEDOES_MAX)):
            return False
        if not _valid_compartments(state["damaged"]) or type(state["helo_lost"]) is not bool:
            return False
        return valid_campaign_core(state, "frigate", HISTORY_FIELDS, _valid_score)

    @classmethod
    def restore(cls, state) -> "CampaignState":
        if isinstance(state, dict) and state.get("version") == LEGACY_VERSION:
            state = migrate_v1(state)
        if not cls.valid_state(state):
            raise ValueError("invalid campaign state")
        campaign = cls.__new__(cls)
        campaign.base_seed = state["base_seed"]
        for key in ("reputation", "torpedoes", "helo_lost", "status", "port"):
            setattr(campaign, key, state[key])
        campaign.damaged = list(state["damaged"])
        campaign.history = [dict(row) for row in state["history"]]
        campaign.theatre = Theatre.restore("frigate", state["base_seed"], state["theatre"])
        return campaign


def _valid_compartments(damaged) -> bool:
    return (isinstance(damaged, list)
            and all(type(name) is str and name in COMPARTMENTS for name in damaged)
            and damaged == sorted(set(damaged)))


def valid_legacy_history(state, legs: int, fields, extra) -> bool:
    """The history of a version-1 chain: one row per leg played, in order."""
    history = state["history"]
    if not isinstance(history, list) or len(history) > legs:
        return False
    for index, row in enumerate(history):
        if (not isinstance(row, dict) or set(row) != fields
                or type(row["leg"]) is not int or row["leg"] != index
                or type(row["result"]) is not str or row["result"] not in RESULTS
                or not extra(row)):
            return False
    if type(state["port"]) is not bool or type(state["status"]) is not str \
            or state["status"] not in ("active", "won", "lost") \
            or (state["port"] and state["status"] != "active"):
        return False
    played = state["leg"] + (1 if state["port"] or state["status"] != "active" else 0)
    return len(history) == played


def valid_v1(state) -> bool:
    """The former fixed-chain format (version 1), checked as strictly as before."""
    if not isinstance(state, dict) or set(state) != LEGACY_FIELDS:
        return False

    def integer(key, low, high):
        return type(state[key]) is int and low <= state[key] <= high

    if not (integer("version", LEGACY_VERSION, LEGACY_VERSION)
            and integer("base_seed", 1, 999_999_999)
            and integer("leg", 0, len(LEGACY_LEGS) - 1)
            and integer("reputation", 0, 100)
            and integer("torpedoes", 0, TORPEDOES_MAX)):
        return False
    if not _valid_compartments(state["damaged"]) or type(state["helo_lost"]) is not bool:
        return False
    return valid_legacy_history(state, len(LEGACY_LEGS), LEGACY_HISTORY_FIELDS,
                                _valid_score)


def migrate_v1(state) -> dict:
    """Pure: a version-1 file as version 2 (returned unchanged when it is not
    a valid version-1 file, so the version-2 check rejects it).  The carried
    state is kept as it was; the played legs become the history and set the
    theatre (``Theatre.from_legacy``)."""
    if not valid_v1(state):
        return state
    results = [row["result"] for row in state["history"]]
    theatre = Theatre.from_legacy("frigate", state["base_seed"], results, state["status"])
    return dict(version=VERSION, base_seed=state["base_seed"],
                reputation=state["reputation"], torpedoes=state["torpedoes"],
                damaged=list(state["damaged"]), helo_lost=state["helo_lost"],
                status=theatre_model.status_of(theatre.outcome),
                port=state["port"] and theatre.outcome is None,
                history=[dict(scenario=LEGACY_LEGS[row["leg"]], result=row["result"],
                              score=row["score"]) for row in state["history"]],
                theatre=theatre.serialize())


def campaign_path() -> str:
    return os.path.join(config.SAVE_DIR, FILE_NAME)


def load_campaign() -> CampaignState | None:
    """The saved campaign, or ``None`` (missing, symlinked or invalid)."""
    data = read_campaign_file(campaign_path())
    if data is None:
        return None
    try:
        return CampaignState.restore(data)
    except (ValueError, TypeError, KeyError):
        return None


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
