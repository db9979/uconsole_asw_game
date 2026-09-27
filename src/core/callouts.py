"""Spoken crew reports ("callouts") taken from the frigate's event feed.

A few feed messages are also said aloud, the way a watch officer would call
them: a torpedo in the water, a new contact, a hit.  The feed sink turns
each such message into a small detached record ``{seq, key, bearing}``;
nothing else is read, so a callout never carries more than the feed line
the operator already sees.  Records are transient (never saved) and do not
touch the simulation.

The spoken text is built at the listener's end in the listener's language:
the uConsole speaks through espeak-ng when it is installed
(``src/audio/speech.py``), a Remote Crew browser through SpeechSynthesis.
Bearings are spoken digit by digit ("two seven zero", "zwo sieben null").
"""

from __future__ import annotations

from collections import deque

from src.core.i18n import _MESSAGE_KEY

MAX_CALLOUTS = 16
# One catalog serves both ends: the browser receives the commander.web keys.
PREFIX = "commander.web.callout_"
KEYS = ("torpedo", "contact", "breakup", "torpedo_away", "hit", "won", "lost",
        "action_stations", "mpa_on_station")

# Feed message key -> callout key; the torpedo cues match by prefix.
_EXACT = {
    "runtime.contact.new_range": "contact",
    "runtime.contact.new_bearing": "contact",
    "runtime.breakup_noise": "breakup",
    "runtime.torpedo.feed": "torpedo_away",
    "runtime.hit.damage": "hit",
    "runtime.hit.asm": "hit",
    "runtime.mission.won": "won",
    "runtime.mission.lost": "lost",
    "crew.action_stations_on": "action_stations",
    "mpa.on_station": "mpa_on_station",
}
_PREFIX = (("runtime.torpedo_cue.", "torpedo"),)
_WITH_BEARING = frozenset({"torpedo", "contact", "breakup"})


def callout_of(text) -> tuple[str, int | None] | None:
    """``(callout key, bearing)`` for a feed message worth saying, else None."""
    if not isinstance(text, dict):
        return None
    key = text.get(_MESSAGE_KEY)
    if type(key) is not str:
        return None
    callout = _EXACT.get(key)
    if callout is None:
        callout = next((name for prefix, name in _PREFIX if key.startswith(prefix)), None)
    if callout is None:
        return None
    bearing = None
    if callout in _WITH_BEARING:
        params = text.get("params")
        try:
            bearing = int(round(float(str(params.get("bearing")).strip()))) % 360
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
    return callout, bearing


class CalloutLog:
    """The last few callouts, numbered; read by the speaker and the browser."""

    def __init__(self):
        self.seq = 0
        self.rows: deque = deque(maxlen=MAX_CALLOUTS)

    def add(self, text) -> dict | None:
        found = callout_of(text)
        if found is None:
            return None
        self.seq += 1
        row = dict(seq=self.seq, key=found[0], bearing=found[1])
        self.rows.append(row)
        return row

    def clear(self) -> None:
        self.rows.clear()

    def detached(self) -> list[dict]:
        return [dict(row) for row in self.rows]


def spoken_bearing(bearing: int, tr) -> str:
    """Three digits, each its own word ("zwo sieben null")."""
    return " ".join(tr(f"{PREFIX}digit_{digit}") for digit in f"{int(bearing) % 360:03d}")


def spoken_text(row: dict, tr) -> str:
    """The sentence of one callout in the translator's language."""
    key = PREFIX + row["key"]
    if row.get("bearing") is None:
        return tr(key)
    return tr(key, bearing=spoken_bearing(row["bearing"], tr))
