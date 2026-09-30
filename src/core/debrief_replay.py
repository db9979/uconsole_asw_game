"""Replay of the mission debrief: the recording played back after the end.

``src/core/debrief.py`` records frames (truth beside the crew's picture) and
events.  The replay runs a cursor over that recording at 10x or 60x on
wall time, interpolates the positions between two frames so the tracks
grow smoothly, and lets shots, pings, hits and sinkings flash where they
happened.  It reads the finished recording only; nothing here touches the
simulation, and the page (uConsole and browser) exists only once the
mission is over.  ``document`` detaches the recording for the browser.
"""

from __future__ import annotations

import math

from src.core.i18n import Translator, translation_scope

SPEEDS = (10, 60)
# Events that flash on the chart, and how long a flash shows (wall seconds).
FLASH_KINDS = ("own_shot", "enemy_shot", "pinged", "sub_sunk", "ship_sunk", "own_damage",
               "first_contact")
FLASH_WALL_S = 1.6
# A published document stays small: frames and events are already bounded
# by ``config.DEBRIEF_MAX_FRAMES``/``DEBRIEF_MAX_EVENTS``.
FRAME_KEYS = ("t", "ship", "subs", "known", "assets", "own_weapons", "enemy_weapons", "buoys")


def _lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def _course(a: float, b: float, k: float) -> float:
    delta = (b - a + 180.0) % 360.0 - 180.0
    return (a + delta * k) % 360.0


def bracket(frames: list, t: float):
    """``(index, k)``: the frame at or before ``t`` and the fraction to the next."""
    if not frames:
        return 0, 0.0
    lo, hi = 0, len(frames) - 1
    if t <= frames[0]["t"]:
        return 0, 0.0
    if t >= frames[hi]["t"]:
        return hi, 0.0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if frames[mid]["t"] <= t:
            lo = mid
        else:
            hi = mid
    span = frames[hi]["t"] - frames[lo]["t"]
    return lo, (t - frames[lo]["t"]) / span if span > 0 else 0.0


def interpolate(frames: list, t: float) -> dict | None:
    """The frame at ``t`` with the own ship, the boats and aircraft moved
    part of the way to the next frame (weapons and picture stay as recorded)."""
    if not frames:
        return None
    index, k = bracket(frames, t)
    frame = frames[index]
    if k <= 0.0 or index + 1 >= len(frames):
        return frame
    after = frames[index + 1]
    ship, ship_after = frame["ship"], after["ship"]
    moved = dict(frame, t=float(t), ship=dict(
        x=_lerp(ship["x"], ship_after["x"], k), y=_lerp(ship["y"], ship_after["y"], k),
        course=_course(ship["course"], ship_after["course"], k)))
    later = {row["id"]: row for row in after["subs"]}
    subs = []
    for row in frame["subs"]:
        other = later.get(row["id"])
        if other is None or row["sunk"]:
            subs.append(row)
        else:
            subs.append(dict(row, x=_lerp(row["x"], other["x"], k),
                             y=_lerp(row["y"], other["y"], k)))
    moved["subs"] = subs
    if len(frame["assets"]) == len(after["assets"]):
        moved["assets"] = [dict(a, x=_lerp(a["x"], b["x"], k), y=_lerp(a["y"], b["y"], k))
                           if a["kind"] == b["kind"] else a
                           for a, b in zip(frame["assets"], after["assets"])]
    return moved


def flashes(events: list, t: float, speed: float) -> list:
    """``(event, fraction)`` of the events flashing at ``t``: fraction 0 at
    the event, 1 when its flash is over (``FLASH_WALL_S`` of wall time)."""
    window = FLASH_WALL_S * max(1.0, float(speed))
    rows = []
    for event in events:
        if event["kind"] not in FLASH_KINDS:
            continue
        age = t - event["t"]
        if 0.0 <= age <= window:
            rows.append((event, age / window))
    return rows[-8:]


def flash_position(event: dict, frame: dict):
    """Where an event flashes: at the sunk boat, else at the own ship."""
    if event["kind"] == "sub_sunk":
        sub = event["params"].get("sub")
        row = next((row for row in frame["subs"] if row["id"] == sub), None)
        if row is not None:
            return row["x"], row["y"]
    ship = frame["ship"]
    return ship["x"], ship["y"]


class Replay:
    """The cursor of a debrief replay (UI state, wall time)."""

    def __init__(self) -> None:
        self.t = 0.0
        self.playing = False
        self.speed = SPEEDS[0]
        self._wall = None

    def seek(self, t: float) -> None:
        self.t = max(0.0, float(t))
        self._wall = None

    def toggle(self, frames: list) -> None:
        if not frames:
            return
        if not self.playing and self.t >= frames[-1]["t"] - 1e-6:
            self.t = frames[0]["t"]         # at the end: play from the start
        self.playing = not self.playing
        self._wall = None

    def cycle_speed(self) -> None:
        self.speed = SPEEDS[(SPEEDS.index(self.speed) + 1) % len(SPEEDS)] \
            if self.speed in SPEEDS else SPEEDS[0]

    def advance(self, frames: list, wall_now: float) -> None:
        if not self.playing or not frames:
            self._wall = None
            return
        if self._wall is not None:
            self.t += max(0.0, min(0.25, wall_now - self._wall)) * self.speed
        self._wall = wall_now
        if self.t >= frames[-1]["t"]:
            self.t = frames[-1]["t"]
            self.playing = False
            self._wall = None


def _frame(frame: dict) -> dict:
    """A recorded frame for the browser (the truth link of contacts dropped)."""
    out = {key: frame[key] for key in FRAME_KEYS}
    out["known"] = [dict(label=str(row["label"])[:16], bearing=row["bearing"],
                         x=row["x"], y=row["y"]) for row in frame["known"]][:32]
    out["subs"] = [dict(id=str(row["id"])[:8], x=row["x"], y=row["y"],
                        depth=int(row["depth"]), sunk=bool(row["sunk"]),
                        hostile=bool(row["hostile"])) for row in frame["subs"]][:16]
    out["assets"] = [dict(type=str(row["kind"]), x=row["x"], y=row["y"])
                     for row in frame["assets"]][:4]
    return out


def document(recorder, side: str) -> dict:
    """The finished recording of one side for the browser replay, with each
    event worded in both catalog languages."""
    from src.ui.debrief_view import event_text
    texts = {}
    for language in ("en", "de"):
        with translation_scope(Translator(language).t):
            texts[language] = [event_text(event, recorder.prefix) for event in recorder.events]
    events = [dict(t=float(event["t"]), type=str(event["kind"]),
                   sub=(str(event["params"].get("sub"))[:8]
                        if event["kind"] == "sub_sunk" else None),
                   en=texts["en"][index][:160], de=texts["de"][index][:160])
              for index, event in enumerate(recorder.events)]
    frames = [_frame(frame) for frame in recorder.frames]
    for frame in frames:
        for key in ("x", "y"):
            if not math.isfinite(frame["ship"][key]):
                raise ValueError("non-finite debrief frame")
    return dict(side=side, frames=frames, events=events, speeds=list(SPEEDS))
