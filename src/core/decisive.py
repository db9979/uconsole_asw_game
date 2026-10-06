"""What decided a mission: one line for the end panel of either side.

Read from a finished debrief recording (``src/core/debrief.py`` for the
frigate, ``src/core/boat_debrief.py`` for the crewed boat): its events and
the spans it found (the frigate's missed chances, the spans in which the
frigate held the boat).  Shown only after the mission ends, like the
debrief, so the truth in it never reaches a running mission.  Pure: no
state, no random numbers.
"""

from __future__ import annotations

import math

from src.core.boat_campaign import WINS as WINS_BOAT
from src.core.i18n import message


def _minutes(t) -> int:
    return max(0, int(round(float(t) / 60.0)))


def _first(events, kind):
    return next((event for event in events if event["kind"] == kind), None)


def _last_before(events, kind, t):
    rows = [event for event in events if event["kind"] == kind and event["t"] <= t + 1e-6]
    return rows[-1] if rows else None


def _result(events):
    end = _first(events, "mission_end")
    return None if end is None else end["params"].get("result")


def _longest(spans):
    return max(spans, key=lambda span: (span["duration_s"], -span["t"]), default=None)


def _range(value) -> str:
    return f"{float(value):.1f}"


def frigate_line(recorder):
    """The frigate's decisive line (catalog message) or None."""
    events = recorder.events
    won = _result(events) == "SIEG"
    contact = _first(events, "first_contact")
    sunk = _first(events, "sub_sunk")
    if won and sunk is not None:
        shot = _last_before(events, "own_shot", sunk["t"])
        if shot is None:
            return message("end.decisive.sunk_plain", minutes=_minutes(sunk["t"]))
        if contact is None:
            return message("end.decisive.sunk_short", weapon=shot["params"]["weapon"],
                           shot=_minutes(shot["t"]))
        return message("end.decisive.sunk", contact=_minutes(contact["t"]),
                       weapon=shot["params"]["weapon"], shot=_minutes(shot["t"]))
    if won:
        if contact is None:
            return None
        return message("end.decisive.held", minutes=_minutes(contact["t"]))
    lost = _first(events, "ship_sunk")
    if lost is not None:
        shot = _last_before(events, "enemy_shot", lost["t"])
        if shot is None:
            return message("end.decisive.ship_lost", minutes=_minutes(lost["t"]))
        return message("end.decisive.ship_sunk", bearing=f"{int(shot['params']['bearing']):03d}",
                       minutes=_minutes(shot["t"]))
    span = _longest(recorder.spans())
    if span is not None:
        return message("end.decisive.missed_layer" if span["layer"] else
                       "end.decisive.missed_open",
                       minutes=_minutes(span["duration_s"]),
                       range=_range(span["min_range_nm"]))
    if contact is None:
        return message("end.decisive.never_heard")
    fix = _first(events, "first_fix")
    if fix is None:
        return message("end.decisive.no_fix", minutes=_minutes(contact["t"]))
    shots = sum(1 for event in events if event["kind"] == "own_shot")
    if shots == 0:
        return message("end.decisive.no_shot", minutes=_minutes(fix["t"]))
    return message("end.decisive.missed_shots", shots=shots)


def _closest(frames):
    best = math.inf
    for frame in frames:
        for target in frame["subs"][:1]:
            best = min(best, math.hypot(target["x"] - frame["ship"]["x"],
                                        target["y"] - frame["ship"]["y"]))
    return None if best == math.inf else best


def boat_line(recorder):
    """The crewed boat's decisive line (catalog message) or None."""
    events = recorder.events
    result = _result(events)
    if result in (None, "trained", "over"):
        return None
    shots = [event for event in events if event["kind"] == "own_shot"]
    if result in WINS_BOAT:
        sunk = _first(events, "sub_sunk")
        if sunk is not None:
            shot = _last_before(events, "own_shot", sunk["t"])
            if shot is not None:
                return message("end.decisive.boat.frigate_sunk",
                               weapon=shot["params"]["weapon"], minutes=_minutes(shot["t"]))
        if result in ("convoy_sunk", "supply_sunk") and shots:
            return message("end.decisive.boat.ships_sunk", shots=len(shots),
                           minutes=_minutes(shots[0]["t"]))
        spans = recorder.spans()
        closest = _closest(recorder.frames)
        if not spans:
            if closest is None:
                return None
            return message("end.decisive.boat.never_held", range=_range(closest))
        held = sum(span["duration_s"] for span in spans)
        return message("end.decisive.boat.held_briefly", minutes=_minutes(held),
                       range=_range(min(span["min_range_nm"] for span in spans)))
    lost = _first(events, "ship_sunk")
    if lost is not None:
        shot = _last_before(events, "enemy_shot", lost["t"])
        if shot is None:
            return message("end.decisive.boat.lost", minutes=_minutes(lost["t"]))
        return message("end.decisive.boat.sunk", bearing=f"{int(shot['params']['bearing']):03d}",
                       minutes=_minutes(shot["t"]))
    span = _longest(recorder.spans())
    if span is not None:
        return message("end.decisive.boat.tracked_layer" if span["layer"] else
                       "end.decisive.boat.tracked_open",
                       minutes=_minutes(span["duration_s"]),
                       range=_range(span["min_range_nm"]))
    if not shots:
        return message("end.decisive.boat.no_attack")
    return message("end.decisive.boat.missed_shots", shots=len(shots))


def line(recorder):
    """The decisive line of a finished recording (either side), or None."""
    if recorder is None or not getattr(recorder, "_ended", False):
        return None
    if recorder.prefix == "debrief.boat.":
        return boat_line(recorder)
    return frigate_line(recorder)
