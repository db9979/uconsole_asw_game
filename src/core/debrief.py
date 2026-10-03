"""Mission debrief: a bounded recording of truth beside what the crew knew.

While a mission runs the game hands the recorder compact frames (every
``config.DEBRIEF_INTERVAL_S`` of mission time) and events (first contact,
first fix, shots, hits, damage).  Nothing here is shown before the mission
ends: the debrief page opens only from the end panel, so the observation
boundary holds during play.  The recording is display data only.  It reads
the simulation, never draws random numbers or changes state, and is not
saved: after a load it covers the mission from the load onwards.

Memory stays bounded for the uConsole: when ``DEBRIEF_MAX_FRAMES`` is
reached every other frame is dropped and the interval doubles, so a long
mission keeps an even, coarser timeline instead of losing its start.
"""

from __future__ import annotations

import math

from src.core import commander_traits, config
from src.physics.geo import bearing_deg as _bearing

# Event kinds in display order of importance (the timeline colours them).
EVENT_KINDS = ("first_contact", "first_fix", "classified", "own_shot", "enemy_shot",
               "sub_sunk", "own_damage", "ship_sunk", "missed", "pinged", "enemy_commander",
               "enemy_habits", "mission_end")


class DebriefRecorder:
    """Frames and events of one mission, bounded (the frigate's view)."""

    # Catalog prefix of the page's perspective-specific texts.
    prefix = "debrief."

    def __init__(self):
        self.frames: list[dict] = []
        self.events: list[dict] = []
        self.interval_s = config.DEBRIEF_INTERVAL_S
        self._next_t = 0.0
        self._seen_contacts: set[int] = set()
        self._fixed: set[int] = set()
        self._classified: set[int] = set()
        self._own_weapons: set[tuple] = set()
        self._enemy_weapons: set[int] = set()
        self._sunk: set[int] = set()
        self._damage_step = 0
        self._ship_lost = False
        self._ended = False

    # --- recording --------------------------------------------------------------

    def due(self, mission_t: float) -> bool:
        return mission_t + 1e-9 >= self._next_t

    def add_frame(self, frame: dict) -> None:
        self.frames.append(frame)
        self._next_t = frame["t"] + self.interval_s
        if len(self.frames) >= config.DEBRIEF_MAX_FRAMES:
            # Keep the first and every other frame; the rest comes coarser.
            last = self.frames[-1]
            self.frames = self.frames[::2]
            if self.frames[-1] is not last:
                self.frames.append(last)
            self.interval_s *= 2.0
            self._next_t = last["t"] + self.interval_s

    def add_event(self, t: float, kind: str, **params) -> None:
        if kind not in EVENT_KINDS:
            raise ValueError(kind)
        if len(self.events) >= config.DEBRIEF_MAX_EVENTS and kind != "mission_end":
            return
        self.events.append(dict(t=float(t), kind=kind, params=params))

    def observe(self, game, t: float) -> None:
        """Turn changes since the last look into events (read-only)."""
        hostile = {sub.id: sub for sub in game.subs if sub.side == "hostile"}
        for contact in game.sonar.active_contacts():
            target = contact.target_id
            if target not in hostile:
                continue
            label = game.contact_display_id(contact)
            if target not in self._seen_contacts:
                self._seen_contacts.add(target)
                self.add_event(t, "first_contact", contact=label,
                               bearing=round(float(contact.bearing), 0))
            if target not in self._fixed and _known_position(contact)[0] is not None:
                self._fixed.add(target)
                self.add_event(t, "first_fix", contact=label)
            if target not in self._classified and contact.player_class == "U_BOOT":
                self._classified.add(target)
                self.add_event(t, "classified", contact=label)
        own = [("T", torpedo.idx) for torpedo in game.torpedoes]
        own += [("A", asroc.seq) for asroc in game.asrocs]
        for key in own:
            if key not in self._own_weapons:
                self._own_weapons.add(key)
                self.add_event(t, "own_shot", weapon=f"{key[0]}{key[1]}")
        for torpedo in game.enemy_torpedoes:
            if torpedo.id not in self._enemy_weapons:
                self._enemy_weapons.add(torpedo.id)
                self.add_event(t, "enemy_shot", bearing=round(_bearing(
                    game.ship.x, game.ship.y, torpedo.x, torpedo.y), 0))
        for sub_id, sub in hostile.items():
            if sub.sunk and sub_id not in self._sunk:
                self._sunk.add(sub_id)
                self.add_event(t, "sub_sunk", sub=sub_id)
        step = int(game.damage.total // config.DEBRIEF_DAMAGE_STEP)
        if step > self._damage_step:
            self._damage_step = step
            self.add_event(t, "own_damage", damage=round(float(game.damage.total), 0))
        if game.damage.ship_sunk and not self._ship_lost:
            self._ship_lost = True
            self.add_event(t, "ship_sunk")

    def finish(self, game, t: float) -> None:
        """Mission over: last frame, the result and the missed chances."""
        if self._ended:
            return
        self.add_frame(self.capture(game, t))
        for span in self.spans():
            self.add_event(span["t"], "missed", minutes=round(span["duration_s"] / 60.0),
                           range=round(span["min_range_nm"], 1), layer=span["layer"])
        character = self.enemy_character(game)
        if character is not None:
            self.add_event(t, "enemy_commander", character=character)
        self.add_event(t, "mission_end", result=self.result(game))
        self.events.sort(key=lambda event: event["t"])
        self._ended = True

    def capture(self, game, t: float) -> dict:
        return capture(game, t)

    def enemy_character(self, game):
        """The first AI submarine commander's character (``commander_traits``)."""
        crewed = getattr(game, "_opfor", None)
        subs = sorted((sub for sub in game.subs if sub.side == "hostile"
                       and (crewed is None or sub is not crewed.sub)), key=lambda sub: sub.id)
        return commander_traits.sub_kind(subs[0]) if subs else None

    def spans(self) -> list[dict]:
        return missed_chances(self.frames)

    def result(self, game):
        return game.mission_result

    # --- reading -------------------------------------------------------------------

    def frame_index_at(self, t: float) -> int:
        if not self.frames:
            return 0
        best = 0
        for index, frame in enumerate(self.frames):
            if frame["t"] <= t:
                best = index
        return best

    def metrics(self) -> dict:
        """Headline numbers of the mission."""
        first = {kind: next((event["t"] for event in self.events if event["kind"] == kind), None)
                 for kind in ("first_contact", "first_fix", "classified")}
        errors = [error for frame in self.frames for error in frame["errors"]]
        shots = sum(1 for event in self.events if event["kind"] == "own_shot")
        sunk = sum(1 for event in self.events if event["kind"] == "sub_sunk")
        missed = [event for event in self.events if event["kind"] == "missed"]
        return dict(first_contact_t=first["first_contact"], first_fix_t=first["first_fix"],
                    classified_t=first["classified"], shots=shots, sunk=sunk,
                    mean_error_nm=(sum(errors) / len(errors)) if errors else None,
                    missed=len(missed),
                    duration_t=self.frames[-1]["t"] if self.frames else 0.0)


def _known_position(contact):
    if contact.observed_x is not None and contact.observed_y is not None:
        return float(contact.observed_x), float(contact.observed_y)
    if contact.tma_pos is not None:
        return float(contact.tma_pos[0]), float(contact.tma_pos[1])
    return None, None


def capture(game, t: float) -> dict:
    """One frame: truth and the crew's knowledge at mission time ``t``."""
    def r(value):
        return round(float(value), 3)

    ship = game.ship
    subs = []
    for sub in game.subs:
        layer = False
        try:
            layer = sub.depth > game.world.thermocline_depth_m(sub.x, sub.y)
        except (AttributeError, ValueError):
            layer = False
        subs.append(dict(id=sub.id, x=r(sub.x), y=r(sub.y), depth=round(float(sub.depth)),
                         sunk=bool(sub.sunk), hostile=sub.side == "hostile", layer=layer))
    known, errors = [], []
    truth = {sub.id: sub for sub in game.subs}
    for contact in game.sonar.active_contacts():
        x, y = _known_position(contact)
        known.append(dict(label=game.contact_display_id(contact),
                          bearing=round(float(contact.bearing), 1),
                          x=None if x is None else r(x), y=None if y is None else r(y),
                          target=contact.target_id if contact.target_id in truth else None))
        sub = truth.get(contact.target_id)
        if x is not None and sub is not None and sub.side == "hostile" and not sub.sunk:
            errors.append(round(math.hypot(x - sub.x, y - sub.y), 2))
    assets = []
    if game.helo.airborne:
        assets.append(dict(kind="helo", x=r(game.helo.x), y=r(game.helo.y)))
    mpa = getattr(game, "mpa", None)
    if mpa is not None and mpa.airborne:
        assets.append(dict(kind="mpa", x=r(mpa.x), y=r(mpa.y)))
    return dict(
        t=float(t),
        ship=dict(x=r(ship.x), y=r(ship.y), course=round(float(ship.course))),
        subs=subs, known=known, errors=errors, assets=assets,
        own_weapons=[dict(x=r(item.x), y=r(item.y))
                     for item in list(game.torpedoes) + list(game.asrocs)][:16],
        enemy_weapons=[dict(x=r(item.x), y=r(item.y)) for item in game.enemy_torpedoes][:16],
        buoys=[dict(x=r(buoy.x), y=r(buoy.y)) for buoy in game.buoys if buoy.active][:24])


def missed_chances(frames: list[dict]) -> list[dict]:
    """Spans where a live hostile boat stayed close without any contact on it."""
    spans, open_spans = [], {}
    limit = config.DEBRIEF_MISSED_NM
    for frame in frames:
        ship = frame["ship"]
        heard = {row["target"] for row in frame["known"] if row["target"] is not None}
        present = set()
        for sub in frame["subs"]:
            if not sub["hostile"] or sub["sunk"]:
                continue
            distance = math.hypot(sub["x"] - ship["x"], sub["y"] - ship["y"])
            if distance > limit or sub["id"] in heard:
                continue
            present.add(sub["id"])
            span = open_spans.setdefault(sub["id"], dict(
                t=frame["t"], end=frame["t"], min_range_nm=distance, layer_frames=0, frames=0))
            span["end"] = frame["t"]
            span["min_range_nm"] = min(span["min_range_nm"], distance)
            span["frames"] += 1
            span["layer_frames"] += int(sub["layer"])
        for sub_id in list(open_spans):
            if sub_id not in present:
                spans.append(open_spans.pop(sub_id))
    spans.extend(open_spans.values())
    result = []
    for span in spans:
        duration = span["end"] - span["t"]
        if duration >= config.DEBRIEF_MISSED_S:
            result.append(dict(t=span["t"], duration_s=duration,
                               min_range_nm=span["min_range_nm"],
                               layer=span["layer_frames"] * 2 > span["frames"]))
    return sorted(result, key=lambda span: span["t"])
