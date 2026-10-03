"""The service record: every finished mission, best scores and awards.

The logbook lives in its own file (``logbook.json`` beside the save slots),
never in a save: it belongs to the player, not to a mission.  Each side
keeps its own record.  The frigate's score is the mission score; the
submarine's is counted from its outcome (``boat_score``), both scaled by
the realism level, so the two sides can earn the same.  Both sides have
five awards of the same kinds:

- ``first``: the first victory on that side
- ``one_shot``: a victory with at most one weapon fired that sank the enemy
- ``unscathed``: a victory without any damage
- ``untouched``: a victory the enemy never fired a weapon at
- ``realist``: a victory on the Realistic level

The file is user data: strict schema, bounded, rejected (and started anew)
when anything in it is off.  Dates are the local calendar day of the
mission's end; the simulation never reads them.
"""

from __future__ import annotations

import json
import math
import os
import re

from src.core import config
from src.core.habits import ALL_HABITS

FILE_NAME = "logbook.json"
VERSION = 1
MAX_ENTRIES = 200
SIDES = ("frigate", "boat")
AWARDS = ("first", "one_shot", "unscathed", "untouched", "realist")
# The submarine's outcome points (``boat_debrief.outcome``); losses count 0.
BOAT_OUTCOME_POINTS = {"won": 1500, "supply_sunk": 1300, "convoy_sunk": 1200,
                       "landed": 1100, "broke_through": 1000, "passed": 1000,
                       "reported": 1000, "objective": 1000, "escaped": 800,
                       "survived": 600}
BOAT_UNDAMAGED_BONUS = 500           # less 5 points per percent of damage
BOAT_TORPEDO_BONUS = 100             # per torpedo left on a victory
MAX_SCORE = 1_000_000
SCENARIO_RE = re.compile(r"^[a-z0-9_]{1,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ENTRY_FIELDS = frozenset({"date", "side", "scenario", "level", "won", "score", "minutes",
                          "shots", "sunk", "awards"})
# Optional per entry (written only when set, so older builds still read the
# book): the mission ran with the language-model advisor, ran the
# experimental opponent advisor, the model's after-action report, and the
# habits the mission showed (``src/core/habits.py``; the enemy learns them).
OPTIONAL_FIELDS = frozenset({"advisor", "experimental", "report", "habits"})
REPORT_MAX = 2_000
BOOK_FIELDS = frozenset({"version", "entries", "best", "awards"})


def boat_score(outcome: str, damage: float, torpedoes_left: int, level: str) -> int:
    """The submarine's mission score from its outcome, scaled by the level."""
    points = BOAT_OUTCOME_POINTS.get(outcome)
    if points is None:
        return 0
    damage = max(0.0, min(100.0, float(damage)))
    points += max(0, int(BOAT_UNDAMAGED_BONUS - 5 * damage))
    points += BOAT_TORPEDO_BONUS * max(0, int(torpedoes_left))
    return int(round(points * config.LEVEL_SCORE_FACTOR.get(level, 1.0)))


def awards_for(*, won: bool, shots: int, sunk: int, damage: float, fired_at: bool,
               level: str) -> list:
    """The awards one mission earns (``first`` is decided by the book)."""
    if not won:
        return []
    earned = ["first"]
    if sunk >= 1 and shots <= 1:
        earned.append("one_shot")
    if damage <= 0.0:
        earned.append("unscathed")
    if not fired_at:
        earned.append("untouched")
    if level == "realistic":
        earned.append("realist")
    return earned


def _count(value, high) -> bool:
    return type(value) is int and 0 <= value <= high


def _valid_optional(row) -> bool:
    for name in ("advisor", "experimental"):
        if name in row and row[name] is not True:
            return False
    shown = row.get("habits", [])
    if (not isinstance(shown, list) or len(shown) != len(set(shown))
            or any(habit not in ALL_HABITS for habit in shown)):
        return False
    report = row.get("report")
    return report is None or (type(report) is str and 0 < len(report) <= REPORT_MAX
                              and all(char.isprintable() or char == "\n" for char in report))


def valid_entry(row) -> bool:
    if (not isinstance(row, dict) or not ENTRY_FIELDS <= set(row)
            or not set(row) <= ENTRY_FIELDS | OPTIONAL_FIELDS or not _valid_optional(row)):
        return False
    return (isinstance(row["date"], str) and bool(DATE_RE.match(row["date"]))
            and row["side"] in SIDES
            and isinstance(row["scenario"], str) and bool(SCENARIO_RE.match(row["scenario"]))
            and row["level"] in config.LEVELS and type(row["won"]) is bool
            and type(row["score"]) is int and -MAX_SCORE <= row["score"] <= MAX_SCORE
            and _count(row["minutes"], 100_000) and _count(row["shots"], 1000)
            and _count(row["sunk"], 100)
            and isinstance(row["awards"], list) and len(row["awards"]) <= len(AWARDS)
            and all(award in AWARDS for award in row["awards"])
            and len(set(row["awards"])) == len(row["awards"]))


class Logbook:
    """All finished missions of this player, per side."""

    def __init__(self):
        self.entries: list[dict] = []
        # "side:scenario" -> best score.
        self.best: dict[str, int] = {}
        # "side:award" -> the date it was first earned.
        self.awards: dict[str, str] = {}

    def record(self, *, date: str, side: str, scenario: str, level: str, won: bool,
               score: int, minutes: int, shots: int, sunk: int, earned: list,
               advisor: bool = False, experimental: bool = False, habits=None) -> dict:
        """File a mission; returns what is new (best score, awards).

        A mission with the advisor or the experimental opponent is marked and
        never sets a best score or earns an award."""
        key = f"{side}:{scenario}"
        assisted = bool(advisor or experimental)
        if assisted:
            earned = []
        new_best = not assisted and won and score > 0 and score > self.best.get(key, 0)
        if new_best:
            self.best[key] = int(score)
        fresh = [award for award in earned if f"{side}:{award}" not in self.awards]
        for award in fresh:
            self.awards[f"{side}:{award}"] = date
        entry = dict(date=date, side=side, scenario=scenario, level=level, won=bool(won),
                     score=int(score), minutes=int(minutes), shots=int(shots),
                     sunk=int(sunk), awards=list(fresh))
        if advisor:
            entry["advisor"] = True
        if experimental:
            entry["experimental"] = True
        if habits is not None:
            entry["habits"] = [habit for habit in ALL_HABITS if habit in habits]
        self.entries.append(entry)
        del self.entries[:-MAX_ENTRIES]
        return dict(entry=entry, new_best=new_best, awards=fresh)

    def attach_report(self, entry: dict, text: str) -> bool:
        """Add the after-action report to the filed entry equal to ``entry``."""
        text = str(text).strip()[:REPORT_MAX]
        if not text:
            return False
        wanted = {key: value for key, value in entry.items() if key != "report"}
        for row in reversed(self.entries):
            if {key: value for key, value in row.items() if key != "report"} == wanted:
                row["report"] = text
                return True
        return False

    def record_daily(self, side: str, key: str, won: bool, score: int, keep: int) -> bool:
        """A daily mission's best score under ``side:daily_YYYYMMDD``; only the
        newest ``keep`` days per side are kept. Returns whether it is new."""
        full = f"{side}:{key}"
        new_best = bool(won) and score > 0 and score > self.best.get(full, 0)
        if new_best:
            self.best[full] = int(min(score, MAX_SCORE))
        days = sorted((name for name in self.best
                       if name.startswith(f"{side}:daily_")), reverse=True)
        for old in days[keep:]:
            del self.best[old]
        return new_best

    def totals(self, side: str) -> tuple:
        """(missions, victories) of one side, over the kept entries."""
        rows = [row for row in self.entries if row["side"] == side]
        return len(rows), sum(1 for row in rows if row["won"])

    def serialize(self) -> dict:
        return dict(version=VERSION, entries=[dict(row, awards=list(row["awards"]))
                                              for row in self.entries],
                    best=dict(self.best), awards=dict(self.awards))

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != BOOK_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        entries, best, awards = state["entries"], state["best"], state["awards"]
        if (not isinstance(entries, list) or len(entries) > MAX_ENTRIES
                or not all(valid_entry(row) for row in entries)):
            return False
        if not isinstance(best, dict) or len(best) > 256:
            return False
        for key, value in best.items():
            side, _, scenario = key.partition(":")
            if (side not in SIDES or not SCENARIO_RE.match(scenario)
                    or type(value) is not int or not 0 < value <= MAX_SCORE):
                return False
        if not isinstance(awards, dict) or len(awards) > len(SIDES) * len(AWARDS):
            return False
        for key, value in awards.items():
            side, _, award = key.partition(":")
            if (side not in SIDES or award not in AWARDS or not isinstance(value, str)
                    or not DATE_RE.match(value)):
                return False
        return True

    @classmethod
    def restore(cls, state) -> "Logbook":
        if not cls.valid_state(state):
            raise ValueError("invalid logbook")
        book = cls()
        book.entries = [dict(row, awards=list(row["awards"])) for row in state["entries"]]
        book.best = dict(state["best"])
        book.awards = dict(state["awards"])
        return book


def logbook_path() -> str:
    return os.path.join(config.SAVE_DIR, FILE_NAME)


def _reject_constant(name):
    raise ValueError(name)


def load_logbook() -> Logbook:
    """The saved logbook, or an empty one (missing, symlinked or invalid)."""
    path = logbook_path()
    try:
        if os.path.islink(path) or os.path.islink(config.SAVE_DIR):
            return Logbook()
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream, parse_constant=_reject_constant)
        return Logbook.restore(data)
    except (OSError, ValueError, TypeError):
        return Logbook()


def save_logbook(book: Logbook) -> bool:
    """Atomic write beside the save slots; False leaves the old file."""
    from src.data.user_content import ContentValidationError, atomic_write_json
    try:
        atomic_write_json(logbook_path(), book.serialize())
        return True
    except (OSError, ValueError, ContentValidationError):
        return False


def finite(value) -> float:
    value = float(value)
    return value if math.isfinite(value) else 0.0
