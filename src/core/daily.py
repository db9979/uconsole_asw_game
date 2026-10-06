"""The daily mission: one fixed mission per side and day, the same for everyone.

The date (the device's own calendar, no network) picks a scenario of the side
that has a short variant and the seed, which also picks the real sea area;
weather and time follow from that seed as in any mission, the length is the
short one (30 to 60 minutes, the variants with measured fairness).  Pure
functions: nothing is saved, a finished daily mission is recognised from its
seed, scenario, world and length (today's or yesterday's, for a mission run
over midnight) and its best score kept in the logbook under
``daily_YYYYMMDD`` (the newest ``KEEP_DAYS`` days per side).
"""

from __future__ import annotations

import datetime
import hashlib

from src.core import config

KEEP_DAYS = 30
# Everyone sails the same real sea area: the packaged sector seed % 128.
WORLD_MODE = "real_fixed"
SEED_MAX = 999_999_937
PREFIX = "daily_"


def today() -> datetime.date:
    return datetime.date.today()


def date_key(day: datetime.date) -> str:
    return day.isoformat()


def _digest(day: datetime.date, side: str, what: str) -> int:
    text = f"u-jagd-daily:{date_key(day)}:{side}:{what}".encode("ascii")
    return int.from_bytes(hashlib.sha256(text).digest()[:8], "big")


LENGTH = "short"


def has_short_variant(key: str) -> bool:
    spec = config.MISSION_TYPES.get(config.SCENARIOS[key]["mission_type"], {})
    return "short_time_limit_s" in spec


def scenarios(side: str) -> tuple:
    """The side's scenarios a daily mission may be: fixed settings, no free
    patrol, and a short variant (the daily mission is a short one)."""
    return tuple(key for key in config.scenarios_for_side(side)
                 if config.SCENARIOS[key]["difficulty"] is not None
                 and not key.startswith("frei_") and has_short_variant(key))


def minutes(key: str) -> int:
    """The daily mission's time limit in minutes (its short variant)."""
    spec = config.MISSION_TYPES[config.SCENARIOS[key]["mission_type"]]
    return int(round(spec["short_time_limit_s"] / 60.0))


def scenario_for(day: datetime.date, side: str) -> str:
    pool = scenarios(side)
    return pool[_digest(day, side, "scenario") % len(pool)]


def seed_for(day: datetime.date, side: str) -> int:
    return 1 + _digest(day, side, "seed") % SEED_MAX


def match(seed: int, scenario: str, side: str, day: datetime.date | None = None):
    """The day whose daily mission this is (today or yesterday), or None."""
    day = today() if day is None else day
    for candidate in (day, day - datetime.timedelta(days=1)):
        if seed == seed_for(candidate, side) and scenario == scenario_for(candidate, side):
            return candidate
    return None


def best_key(day: datetime.date) -> str:
    return PREFIX + day.strftime("%Y%m%d")


def is_daily_key(scenario: str) -> bool:
    return scenario.startswith(PREFIX)
