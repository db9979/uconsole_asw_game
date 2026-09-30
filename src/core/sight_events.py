"""What an eye on the sea sees happen: water columns, fire, smoke, sinkings.

Detonations and hits leave a short, bounded list of display events at the
point where they happened.  An observer (the frigate's lookout, the boat's
periscope, a phone lookout) gets detached rows of the events its eye can
reach: bearing and range from its own position, limited by the weather's
visibility and the geometric horizon of the event's height.  A water column
over a detonation is what anyone in sight of it sees, so it is legitimate
sensor output; the rows carry no entity, no identity and no depth.

Everything here is display only: it is never saved, never read by the
simulation and never draws a random number.  A fire follows the ship it
burns on (internally) and turns into a sinking when that ship goes down.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

KINDS = ("column", "blast", "fire", "sinking")
EVENTS_MAX = 24
ROWS_MAX = 8
# Lifetimes (s): a column collapses in half a minute, a burning ship smokes
# for minutes, a sinking takes a minute and a half.
COLUMN_S = 28.0
BLAST_S = 20.0
FIRE_S = 540.0
SINKING_S = 95.0
# Heights (m) that decide the geometric horizon of an event: the water
# column of a charge, the smoke of a fire, the hull of a sinking ship.
COLUMN_M = {"depth_charge": 70.0, "rbu": 45.0, "torpedo": 110.0}
SMOKE_M = 180.0
HULL_M = 14.0
# A detonation deeper than this throws no column that reaches the surface.
COLUMN_DEPTH_MAX_M = 160.0
# The observer's own hull: events on it are not in its picture.
OWN_HULL_NM = 0.15


@dataclass
class SightEvent:
    kind: str
    x: float
    y: float
    at_s: float
    dur_s: float
    size_m: float
    ref: object = None          # the burning or sinking ship (internal only)
    level: float = 1.0


def horizon_nm(eye_m: float, height_m: float) -> float:
    """Geometric range (NM, standard refraction) at which an object of
    ``height_m`` shows above the horizon of an eye ``eye_m`` high."""
    return 2.08 * (math.sqrt(max(0.0, eye_m)) + math.sqrt(max(0.0, height_m)))


class SightEvents:
    """The bounded list of what happened on the sea lately (display only)."""

    def __init__(self) -> None:
        self.events: list[SightEvent] = []

    def clear(self) -> None:
        self.events.clear()

    def _add(self, event: SightEvent) -> None:
        self.events.append(event)
        if len(self.events) > EVENTS_MAX:
            del self.events[0]

    def detonation(self, x: float, y: float, now: float, source: str,
                   depth_m: float = 0.0) -> None:
        """An underwater charge: a white column, lower the deeper it went."""
        if depth_m > COLUMN_DEPTH_MAX_M:
            return
        height = COLUMN_M.get(source, 60.0) * (1.0 - 0.6 * max(0.0, depth_m) / COLUMN_DEPTH_MAX_M)
        self._add(SightEvent("column", float(x), float(y), now, COLUMN_S, height))

    def ship_hit(self, ship, now: float, *, blast: bool = False) -> None:
        """A warhead on a ship: a column (torpedo) or a fireball (missile)
        against the hull, then fire and smoke that follow her."""
        if blast:
            self._add(SightEvent("blast", float(ship.x), float(ship.y), now, BLAST_S, 40.0))
        else:
            self._add(SightEvent("column", float(ship.x), float(ship.y), now, COLUMN_S,
                                 COLUMN_M["torpedo"]))
        for event in self.events:
            if event.kind == "fire" and event.ref is ship:
                event.at_s, event.level = now - 5.0, 1.0
                break
        else:
            self._add(SightEvent("fire", float(ship.x), float(ship.y), now, FIRE_S,
                                 _hull_length(ship), ref=ship))
        if getattr(ship, "sunk", False):
            self.sinking(ship, now)

    def sinking(self, ship, now: float) -> None:
        if any(event.kind == "sinking" and event.ref is ship for event in self.events):
            return
        self._add(SightEvent("sinking", float(ship.x), float(ship.y), now, SINKING_S,
                             _hull_length(ship), ref=ship))

    def refresh(self, now: float, fire_level=None) -> None:
        """Move fires with their ships, turn a fire into a sinking when the
        ship goes down and drop what is over.  ``fire_level(ship)`` gives a
        ship's own fire state (0..1, the frigate's compartments) or None."""
        for event in list(self.events):
            ship = event.ref
            if ship is None:
                continue
            if event.kind == "fire":
                if getattr(ship, "sunk", False):
                    event.dur_s = min(event.dur_s, now - event.at_s + 20.0)
                    self.sinking(ship, now)
                    continue
                event.x, event.y = float(ship.x), float(ship.y)
                level = fire_level(ship) if fire_level is not None else None
                if level is not None:
                    event.level = max(0.0, min(1.0, level))
                    # The frigate's own fire: it smokes while a room burns.
                    if event.level > 0.0:
                        event.dur_s = max(event.dur_s, now - event.at_s + 60.0)
                else:
                    event.level = max(0.0, 1.0 - (now - event.at_s) / event.dur_s)
        self.events = [event for event in self.events if now - event.at_s <= event.dur_s]

    def visible(self, eye_x: float, eye_y: float, eye_m: float, now: float, *,
                visibility_nm: float, exclude=None) -> list[dict]:
        """Detached rows of the events an eye at (eye_x, eye_y), ``eye_m``
        high, can see: ``kind``, ``bearing``, ``range_nm``, ``at_s``,
        ``dur_s``, ``size_m`` and ``level`` (fire 0..1), nearest first."""
        rows = []
        for event in self.events:
            if exclude is not None and event.ref is exclude:
                continue
            dx, dy = event.x - eye_x, event.y - eye_y
            distance = math.hypot(dx, dy)
            if distance < OWN_HULL_NM or distance > visibility_nm:
                continue
            height = {"fire": SMOKE_M, "sinking": HULL_M}.get(event.kind, event.size_m)
            if distance > horizon_nm(eye_m, height):
                continue
            rows.append(dict(kind=event.kind, bearing=math.degrees(math.atan2(dx, -dy)) % 360.0,
                             range_nm=round(distance, 2), at_s=float(event.at_s),
                             dur_s=float(event.dur_s), size_m=float(event.size_m),
                             level=round(float(event.level), 2)))
        rows.sort(key=lambda row: row["range_nm"])
        return rows[:ROWS_MAX]


def _hull_length(ship) -> float:
    length = getattr(ship, "hull_length_m", None)
    if isinstance(length, (int, float)) and length > 0:
        return float(length)
    # The frigate: her hull model's length.
    from src.physics import ship_dynamics
    return float(ship_dynamics.HULL.length_m)


def frigate_rows(game) -> list[dict]:
    """What the frigate's lookout can see happen (not her own hull)."""
    from src.sensors.visual import LOOKOUT_EYE_HEIGHT_M
    events = getattr(game, "sight_events", None)
    if events is None:
        return []
    return events.visible(game.ship.x, game.ship.y, LOOKOUT_EYE_HEIGHT_M, game.sim_t,
                          visibility_nm=_visibility(game), exclude=game.ship)


def boat_rows(game, boat) -> list[dict]:
    """What the crewed boat's periscope can see happen (scope up only)."""
    from src.core import config, opfor
    events = getattr(game, "sight_events", None)
    if events is None or not opfor.scope_available(boat):
        return []
    return events.visible(boat.sub.x, boat.sub.y, config.UBOOT_SCOPE_EYE_HEIGHT_M, game.sim_t,
                          visibility_nm=_visibility(game))


def _visibility(game) -> float:
    from src.core import config
    return float(getattr(game.world, "visibility_nm", config.WEATHER_VISIBILITY_MAX_NM))
