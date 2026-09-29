"""The frigate's own radio messages to HQ (save ``hq_reports``).

Besides answering HQ's tasks the radio room can call HQ itself:

- ``contact``: a contact report with the position of the freshest located
  submarine contact (ping, TMA, buoy or fused fix).  HQ passes it to the
  patrol aircraft when it is airborne.  Whether a hostile submarine really
  was near the fix is decided when the call goes out and only counts at the
  mission's end (the radio room never learns it during the mission).
- ``support``: a request for support; HQ sends the on-call patrol aircraft
  toward the ship when it can.

Each call is an HF transmission of ``RADIO_TX_S``.  While it goes out a
submarine with its antenna up can take an HF/DF bearing on the frigate: the
radio is a sensor for the other side too.  This module holds the state; the
game mixin (``game_reports.py``) connects it to the world.
"""

from __future__ import annotations

import math

VERSION = 1
KINDS = ("contact", "support")
MAX_LOG = 8
MAX_TIME_S = 1e9
COORD_LIMIT_NM = 1_000.0
LOG_FIELDS = frozenset({"t", "kind", "x", "y", "accurate"})
STATE_FIELDS = frozenset({"version", "tx_kind", "tx_until", "next_t", "log"})


def _number(value) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value))


def _time(value) -> bool:
    return _number(value) and 0.0 <= value <= MAX_TIME_S


def valid_row(row) -> bool:
    if not isinstance(row, dict) or set(row) != LOG_FIELDS:
        return False
    if not _time(row["t"]) or row["kind"] not in KINDS:
        return False
    contact = row["kind"] == "contact"
    if contact:
        return (_number(row["x"]) and _number(row["y"])
                and abs(row["x"]) <= COORD_LIMIT_NM and abs(row["y"]) <= COORD_LIMIT_NM
                and type(row["accurate"]) is bool)
    return row["x"] is None and row["y"] is None and row["accurate"] is None


class HqReports:
    """The radio room's own calls: the one on the air and the log."""

    def __init__(self):
        self.tx_kind: str | None = None
        self.tx_until = 0.0
        self.next_t = 0.0
        self.log: list[dict] = []

    @property
    def transmitting(self) -> bool:
        return self.tx_kind is not None

    def ready(self, now: float) -> bool:
        return not self.transmitting and now >= self.next_t

    def start(self, kind: str, now: float, tx_s: float, interval_s: float, *,
              x=None, y=None, accurate=None) -> dict:
        row = dict(t=float(now), kind=kind, x=None if x is None else float(x),
                   y=None if y is None else float(y), accurate=accurate)
        self.tx_kind = kind
        self.tx_until = float(now) + tx_s
        self.next_t = float(now) + interval_s
        self.log.append(row)
        del self.log[:-MAX_LOG]
        return row

    def finish(self):
        """End the call on the air; returns the finished log row."""
        kind, self.tx_kind = self.tx_kind, None
        return next((row for row in reversed(self.log) if row["kind"] == kind), None)

    def accurate_reports(self) -> int:
        return sum(1 for row in self.log if row["kind"] == "contact" and row["accurate"])

    def serialize(self) -> dict:
        return dict(version=VERSION, tx_kind=self.tx_kind, tx_until=self.tx_until,
                    next_t=self.next_t, log=[dict(row) for row in self.log])

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            return False
        if type(state["version"]) is not int or state["version"] != VERSION:
            return False
        if state["tx_kind"] is not None and state["tx_kind"] not in KINDS:
            return False
        if not (_time(state["tx_until"]) and _time(state["next_t"])):
            return False
        log = state["log"]
        if (not isinstance(log, list) or len(log) > MAX_LOG
                or not all(valid_row(row) for row in log)):
            return False
        times = [row["t"] for row in log]
        if times != sorted(times):
            return False
        # A call on the air is the newest row of its kind.
        return state["tx_kind"] is None or any(row["kind"] == state["tx_kind"] for row in log)

    @classmethod
    def restore(cls, state) -> "HqReports":
        if not cls.valid_state(state):
            raise ValueError("invalid hq_reports state")
        reports = cls()
        reports.tx_kind = state["tx_kind"]
        reports.tx_until = float(state["tx_until"])
        reports.next_t = float(state["next_t"])
        reports.log = [dict(row) for row in state["log"]]
        return reports
