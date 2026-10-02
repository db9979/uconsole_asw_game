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
        "action_stations", "mpa_on_station", "ping", "dipping", "buoy_ping", "splash",
        "evade", "mast_threat", "leak", "fire", "detonation_near", "detonation",
        "broadcast", "broadcast_report", "sighting_warship", "sighting_merchant",
        "sighting_aircraft", "sighting_torpedo", "sighting_unknown", "test_depth_near",
        "test_depth_over", "hull_damage", "bridge_aircraft", "crash_dive",
        # The phone lookout's and periscope's own calls (src/core/phone_lookout.py).
        "lookout_contact", "lookout_ship", "lookout_warship", "lookout_merchant",
        "lookout_aircraft", "lookout_submarine", "lookout_torpedo")
_CALLED = {"frigate": "lookout.called.", "boat": "uboot.event.scope_called."}

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
# The crewed boat's own feed (CrewedBoat.notice): its sonar room and crew.
_BOAT = {
    "uboot.event.torpedo_heard": "torpedo",
    "uboot.event.ping_heard": "ping",
    "uboot.event.ping_dipping_heard": "dipping",
    "uboot.event.ping_buoy_heard": "buoy_ping",
    "uboot.event.buoy_splash": "splash",
    "uboot.event.rbu_splash": "splash",
    "runtime.contact.new_range": "contact",
    "runtime.contact.new_bearing": "contact",
    "uboot.event.evade": "evade",
    "uboot.event.evade_decoy": "evade",
    "uboot.event.esm_mast_threat": "mast_threat",
    "uboot.event.dc_leak": "leak",
    "uboot.event.dc_fire": "fire",
    "crew.action_stations_on": "action_stations",
    "uboot.event.torpedo_fired": "torpedo_away",
    "uboot.event.torpedo_fired_tubeless": "torpedo_away",
    "uboot.event.detonation_near": "detonation_near",
    "uboot.event.detonation_far": "detonation",
    "uboot.event.breakup_heard": "breakup",
    "uboot.event.radio_copied": "broadcast",
    "uboot.event.radio_copied_report": "broadcast_report",
    "uboot.event.sighting_warship": "sighting_warship",
    "uboot.event.sighting_merchant": "sighting_merchant",
    "uboot.event.sighting_aircraft": "sighting_aircraft",
    "uboot.event.sighting_torpedo": "sighting_torpedo",
    "uboot.event.sighting_unknown": "sighting_unknown",
    # The surfaced boat's bridge watch, and the crash dive it calls for.
    "uboot.event.bridge_warship": "sighting_warship",
    "uboot.event.bridge_merchant": "sighting_merchant",
    "uboot.event.bridge_aircraft": "bridge_aircraft",
    "uboot.event.bridge_torpedo": "sighting_torpedo",
    "uboot.event.bridge_unknown": "sighting_unknown",
    "uboot.event.crash_dive": "crash_dive",
    "uboot.event.test_depth_near": "test_depth_near",
    "uboot.event.test_depth_over": "test_depth_over",
    "uboot.event.hull_hit": "hit",
    "uboot.event.hull_bolts": "hull_damage",
    "uboot.event.hull_seal": "hull_damage",
    "uboot.event.hull_fracture": "hull_damage",
    "uboot.event.hull_collapse": "hull_damage",
    "uboot.event.mission_won": "won",
    "uboot.event.mission_lost": "lost",
}
_WITH_BEARING = frozenset({"torpedo", "contact", "breakup", "ping", "dipping", "buoy_ping",
                           "splash", "detonation_near", "detonation", "sighting_warship",
                           "sighting_merchant", "sighting_aircraft", "sighting_torpedo",
                           "sighting_unknown", "bridge_aircraft"} | {key for key in KEYS if key.startswith("lookout_")})
SIDES = ("frigate", "boat")


def callout_of(text, side: str = "frigate") -> tuple[str, int | None] | None:
    """``(callout key, bearing)`` for a feed message worth saying, else None."""
    if not isinstance(text, dict):
        return None
    key = text.get(_MESSAGE_KEY)
    if type(key) is not str:
        return None
    called = _CALLED.get(side, "")
    if called and key.startswith(called) and f"lookout_{key[len(called):]}" in KEYS:
        callout = f"lookout_{key[len(called):]}"
    elif side == "boat":
        callout = _BOAT.get(key)
    else:
        callout = _EXACT.get(key)
        if callout is None:
            callout = next((name for prefix, name in _PREFIX if key.startswith(prefix)),
                           None)
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

    def __init__(self, side: str = "frigate"):
        self.side = side
        self.seq = 0
        self.spoken = 0            # the uConsole speaker's high-water mark
        self.rows: deque = deque(maxlen=MAX_CALLOUTS)

    def add(self, text) -> dict | None:
        found = callout_of(text, self.side)
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
