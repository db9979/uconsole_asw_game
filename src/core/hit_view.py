"""The hit picture: a small window that shows a hit for a few seconds.

When the shown side's eye sees a hit happen (a fireball, a torpedo's water
column or a ship going down, from ``sight_events``), a small window trained
on its bearing opens at every station for ``SHOW_S`` seconds; when the hit is
only heard (the crew's callout of a hit or of breaking-up noises), the window
shows the bearing with the noise instead.  Everything comes from the side's
own observations (sight rows, callouts); nothing is saved, nothing feeds the
simulation, and the trackers below only remember what they have shown.
"""

from __future__ import annotations

from src.core import sight_events

SHOW_S = 8.0
# A heard hit waits this long for the eye before the sonar picture opens.
SIGHT_GRACE_S = 2.0
FOV_DEG = 12.0
# Water columns tall enough to be a torpedo's warhead (depth charges are not hits).
HIT_COLUMN_M = 100.0
HEARD_KEYS = ("hit", "breakup")


class HitTracker:
    """The newest hit one side saw or heard (sim time, display only)."""

    def __init__(self) -> None:
        self.context = None
        self.callout_seq = 0
        self.sight_at = None
        self.shown = None

    def update(self, context, now: float, rows, callouts) -> dict | None:
        callouts = list(callouts)
        latest = max((int(row["seq"]) for row in callouts), default=0)
        if context != self.context or latest < self.callout_seq:
            self.context = context
            self.callout_seq = latest
            self.sight_at = max((row["at_s"] for row in rows), default=None)
            self.shown = None
            return None
        for row in rows:
            fresh = self.sight_at is None or row["at_s"] > self.sight_at
            if fresh and _is_hit(row) and 0.0 <= now - row["at_s"] <= SHOW_S:
                self.shown = dict(mode="sight", bearing=float(row["bearing"]),
                                  kind=str(row["kind"]), start=float(row["at_s"]))
        if rows:
            self.sight_at = max([row["at_s"] for row in rows]
                                + ([self.sight_at] if self.sight_at is not None else []))
        for row in callouts:
            if int(row["seq"]) <= self.callout_seq:
                continue
            if row["key"] in HEARD_KEYS and row.get("bearing") is not None:
                if not (self.shown is not None and self.shown["mode"] == "sight"
                        and now - self.shown["start"] <= SIGHT_GRACE_S):
                    self.shown = dict(mode="sonar", bearing=float(row["bearing"]),
                                      kind=str(row["key"]), start=float(now))
        self.callout_seq = max(self.callout_seq, latest)
        if self.shown is None or not 0.0 <= now - self.shown["start"] <= SHOW_S:
            return None
        return dict(self.shown, age_s=now - self.shown["start"])


def _is_hit(row) -> bool:
    if row["kind"] in ("blast", "sinking"):
        return True
    return row["kind"] == "column" and row["size_m"] >= HIT_COLUMN_M


def current(game, side: str) -> dict | None:
    """The hit window of ``side`` ("frigate" or "uboot") now, or None:
    ``mode`` ("sight" or "sonar"), ``bearing``, ``kind``, ``age_s``."""
    trackers = getattr(game, "_hit_trackers", None)
    if trackers is None:
        trackers = game._hit_trackers = {}
    tracker = trackers.setdefault(side, HitTracker())
    if side == "uboot":
        boat = game.opfor
        if boat is None:
            return None
        rows = sight_events.boat_rows(game, boat)
        callouts = boat.callouts.rows
        context = ("uboot", id(boat), id(game.sight_events))
    else:
        rows = sight_events.frigate_rows(game)
        callouts = game.callouts.rows
        context = ("frigate", id(game.ship), id(game.sight_events))
    return tracker.update(context, game.sim_t, rows, callouts)
