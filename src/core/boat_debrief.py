"""The crewed boat's debrief: its mission beside the hunters' truth.

Same bounded recorder as the frigate's (``src/core/debrief.py``), from the
boat's side: its own track, what its sonar room held on the frigate, the
hunters' true positions (frigate, helicopter, patrol aircraft, buoys), the
torpedoes both ways, the pings it took, and when the frigate really held
contact on it.  All of it is shown only after the mission ends; recording
reads the simulation and changes nothing.
"""

from __future__ import annotations

import math

from src.core import config
from src.core.debrief import DebriefRecorder, _bearing, _known_position
from src.sonar.platforms import OWNSHIP_TARGET_ID

PING_KINDS = ("hull", "dipping", "buoy")
PING_EVENT_GAP_S = 60.0          # one "pinged" event per episode
TRACKED_MIN_S = 60.0


def outcome(game, boat) -> str:
    """The mission from the boat's side: won, broke_through, reported,
    convoy_sunk, passed, landed, supply_sunk, escaped, survived, objective,
    trained, lost, over."""
    sub = boat.sub if boat is not None else None
    if sub is not None and (sub.sunk or sub.state == "SINKING"):
        return "lost"
    coach = getattr(game, "training", None)
    if coach is not None and coach.done and coach.lesson.startswith("boat_"):
        return "trained"
    if game.damage.ship_sunk:
        return "won"
    reason = game.result_reason if isinstance(game.result_reason, dict) else {}
    key = reason.get("__u_jagd_i18n__")
    if key == "end.reason.boat_broke_through":
        return "broke_through"
    if key == "end.reason.boat_reported":
        return "reported"
    if key == "end.reason.convoy_lost":
        return "convoy_sunk"
    if key == "end.reason.boat_passed_strait":
        return "passed"
    if key == "end.reason.swimmers_landed":
        return "landed"
    if key == "end.reason.supply_sunk":
        return "supply_sunk"
    from src.core import mission_modes
    extra = mission_modes.outcome(game, key)
    if extra is not None:
        return extra
    if key == "end.reason.sub_escaped" and sub is not None and \
            str(reason.get("params", {}).get("contact")) == str(sub.id):
        return "escaped"
    from src.core import custom_boat
    if custom_boat.definition(game) is not None:
        # A submarine custom mission: the frigate's loss is the boat's win.
        if key == custom_boat.HELD_OUT_REASON:
            return "survived"
        return "objective" if game.mission_result == "VERLOREN" else "over"
    if key == "end.reason.time_limit" and game.mission.win_mode == "sink":
        return "survived"
    return "over"


class BoatDebriefRecorder(DebriefRecorder):
    """Frames and events of the crewed boat's mission, bounded."""

    prefix = "debrief.boat."

    def __init__(self, sub_id: int):
        super().__init__()
        self.sub_id = sub_id
        self._intercept_t = -1.0
        self._last_ping_event = -math.inf

    def _boat(self, game):
        boat = getattr(game, "_opfor", None)
        return boat if boat is not None and boat.sub_id == self.sub_id else None

    def observe(self, game, t: float) -> None:
        boat = self._boat(game)
        if boat is None:
            return
        sub = boat.sub
        for contact in boat.station.sonar.active_contacts():
            if contact.target_id != OWNSHIP_TARGET_ID:
                continue
            label = f"K{contact.id:02d}"
            if OWNSHIP_TARGET_ID not in self._seen_contacts:
                self._seen_contacts.add(OWNSHIP_TARGET_ID)
                self.add_event(t, "first_contact", contact=label,
                               bearing=round(float(contact.bearing), 0))
            if OWNSHIP_TARGET_ID not in self._fixed and _known_position(contact)[0] is not None:
                self._fixed.add(OWNSHIP_TARGET_ID)
                self.add_event(t, "first_fix", contact=label)
            if OWNSHIP_TARGET_ID not in self._classified and \
                    contact.player_class == "KAMPFSCHIFF":
                self._classified.add(OWNSHIP_TARGET_ID)
                self.add_event(t, "classified", contact=label)
        own = sorted(torpedo.id for torpedo in game.enemy_torpedoes
                     if torpedo.launch_platform_id == self.sub_id)
        for torpedo_id in own:
            key = ("T", torpedo_id)
            if key not in self._own_weapons:
                self._own_weapons.add(key)
                self.add_event(t, "own_shot", weapon=f"T{len(self._own_weapons)}")
        hunters = [("T", torpedo.idx, torpedo) for torpedo in game.torpedoes]
        hunters += [("A", asroc.seq, asroc) for asroc in game.asrocs]
        for kind, number, weapon in hunters:
            key = (kind, number)
            if key not in self._enemy_weapons:
                self._enemy_weapons.add(key)
                self.add_event(t, "enemy_shot",
                               bearing=round(_bearing(sub.x, sub.y, weapon.x, weapon.y), 0))
        for row in boat.intercepts:
            if row["t"] <= self._intercept_t:
                continue
            self._intercept_t = row["t"]
            if row["kind"] in PING_KINDS and row["t"] - self._last_ping_event >= PING_EVENT_GAP_S:
                self._last_ping_event = row["t"]
                self.add_event(t, "pinged", source=row["kind"], bearing=round(row["bearing"]))
        step = int(sub.damage // config.DEBRIEF_DAMAGE_STEP)
        if step > self._damage_step:
            self._damage_step = step
            self.add_event(t, "own_damage", damage=round(float(sub.damage), 0))
        if game.damage.ship_sunk and OWNSHIP_TARGET_ID not in self._sunk:
            self._sunk.add(OWNSHIP_TARGET_ID)
            self.add_event(t, "sub_sunk", sub="F")
        if sub.sunk and not self._ship_lost:
            self._ship_lost = True
            self.add_event(t, "ship_sunk")

    def capture(self, game, t: float) -> dict:
        boat = self._boat(game)
        if boat is None:
            return self.frames[-1] | {"t": float(t)} if self.frames else _empty(t)
        return capture_boat(game, boat, t)

    def spans(self) -> list[dict]:
        return tracked_spans(self.frames)

    def result(self, game):
        return outcome(game, self._boat(game))


def _empty(t):
    return dict(t=float(t), ship=dict(x=0.0, y=0.0, course=0), subs=[], known=[], errors=[],
                assets=[], own_weapons=[], enemy_weapons=[], buoys=[], tracked=False)


def capture_boat(game, boat, t: float) -> dict:
    """One frame from the boat's side: the frigate is the "target"."""
    def r(value):
        return round(float(value), 3)

    sub, ship = boat.sub, game.ship
    target = dict(id="F", x=r(ship.x), y=r(ship.y), depth=0,
                  sunk=bool(game.damage.ship_sunk), hostile=True, layer=False)
    known, errors = [], []
    for contact in boat.station.sonar.active_contacts():
        x, y = _known_position(contact)
        frigate = contact.target_id == OWNSHIP_TARGET_ID
        known.append(dict(label=f"K{contact.id:02d}", bearing=round(float(contact.bearing), 1),
                          x=None if x is None else r(x), y=None if y is None else r(y),
                          target="F" if frigate else None))
        if x is not None and frigate and not game.damage.ship_sunk:
            errors.append(round(math.hypot(x - ship.x, y - ship.y), 2))
    assets = []
    if game.helo.airborne:
        assets.append(dict(kind="helo", x=r(game.helo.x), y=r(game.helo.y)))
    mpa = getattr(game, "mpa", None)
    if mpa is not None and mpa.airborne:
        assets.append(dict(kind="mpa", x=r(mpa.x), y=r(mpa.y)))
    layer = False
    try:
        layer = sub.depth > game.world.thermocline_depth_m(sub.x, sub.y)
    except (AttributeError, ValueError):
        layer = False
    tracked = any(contact.target_id == sub.id for contact in game.sonar.active_contacts())
    return dict(
        t=float(t),
        ship=dict(x=r(sub.x), y=r(sub.y), course=round(float(sub.course))),
        subs=[target], known=known, errors=errors, assets=assets,
        own_weapons=[dict(x=r(item.x), y=r(item.y)) for item in game.enemy_torpedoes
                     if item.launch_platform_id == boat.sub_id][:16],
        enemy_weapons=[dict(x=r(item.x), y=r(item.y))
                       for item in list(game.torpedoes) + list(game.asrocs)][:16],
        buoys=[dict(x=r(buoy.x), y=r(buoy.y)) for buoy in game.buoys if buoy.active][:24],
        tracked=tracked, below_layer=layer)


def tracked_spans(frames: list[dict]) -> list[dict]:
    """Spans in which the frigate's sonar really held a contact on the boat."""
    spans, current = [], None
    for frame in frames:
        if frame.get("tracked"):
            distance = (math.hypot(frame["subs"][0]["x"] - frame["ship"]["x"],
                                   frame["subs"][0]["y"] - frame["ship"]["y"])
                        if frame["subs"] else 0.0)
            if current is None:
                current = dict(t=frame["t"], end=frame["t"], min_range_nm=distance,
                               frames=0, layer_frames=0)
            current["end"] = frame["t"]
            current["min_range_nm"] = min(current["min_range_nm"], distance)
            current["frames"] += 1
            current["layer_frames"] += int(bool(frame.get("below_layer")))
        elif current is not None:
            spans.append(current)
            current = None
    if current is not None:
        spans.append(current)
    return [dict(t=span["t"], duration_s=max(span["end"] - span["t"], 0.0),
                 min_range_nm=span["min_range_nm"],
                 layer=span["layer_frames"] * 2 > span["frames"])
            for span in spans if span["end"] - span["t"] >= TRACKED_MIN_S]
