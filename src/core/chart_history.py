"""Chart history: the own track and the recent picture of each contact.

A display aid for the tactical charts (Bridge, OPZ, the crewed submarine's
chart): where the own ship or boat has been, where a positioned track was
seen before, and the last bearings of each sonar contact from where they
were taken.  Everything is sampled from public observations (own-ship truth,
published tracks, the operator's contacts) on fixed simulation-time steps,
so the history never reveals anything the crew did not already see and is
the same for the same run.  It is display state only: it never feeds back
into the simulation, is not saved and starts anew after a load or a new
mission.  All buffers are bounded for the uConsole.
"""

from __future__ import annotations

from collections import OrderedDict, deque

from src.ui import observations

# Own track: one point every OWN_STEP_S of simulation time, two hours kept.
OWN_STEP_S = 30.0
OWN_POINTS = 240
# Positioned tracks and sonar fixes: one point a minute, the last 12.
TRACK_STEP_S = 60.0
TRACK_POINTS = 12
MAX_TRACKS = 48
# The OPZ's picture (its own, fused track numbers): one point every 30 s,
# twelve minutes kept, for the OPZ chart's trails.
OPZ_STEP_S = 30.0
OPZ_POINTS = 24
# Bearing-only contacts: the last six bearings, one a minute.
BEARING_POINTS = 6
MAX_BEARING_CONTACTS = 32
# A track not refreshed for this long is dropped from the history.
FORGET_S = 900.0


class _Side:
    """History of one chart (the frigate's picture or one crewed boat)."""

    def __init__(self) -> None:
        self.own: deque = deque(maxlen=OWN_POINTS)
        self.tracks: OrderedDict = OrderedDict()
        self.bearings: OrderedDict = OrderedDict()
        self.opz: OrderedDict = OrderedDict()
        self.own_slot = -1
        self.track_slot = -1
        self.opz_slot = -1

    def sample_own(self, t: float, x: float, y: float) -> None:
        slot = int(t // OWN_STEP_S)
        if slot != self.own_slot:
            self.own_slot = slot
            self.own.append((float(x), float(y)))

    def due(self, t: float) -> bool:
        slot = int(t // TRACK_STEP_S)
        if slot == self.track_slot:
            return False
        self.track_slot = slot
        return True

    def due_opz(self, t: float) -> bool:
        slot = int(t // OPZ_STEP_S)
        if slot == self.opz_slot:
            return False
        self.opz_slot = slot
        return True

    def add_opz(self, t: float, key, x: float, y: float) -> None:
        self._put(self.opz, key, (t, float(x), float(y)), OPZ_POINTS, MAX_TRACKS)

    def opz_positions(self, key, now: float, minutes: float) -> tuple:
        """Earlier OPZ positions of one track from the last ``minutes``."""
        return tuple(row for row in self.opz.get(key, ())
                     if now - row[0] <= minutes * 60.0 + 1e-6)

    @staticmethod
    def _put(table: OrderedDict, key, row, points: int, limit: int) -> None:
        rows = table.get(key)
        if rows is None:
            rows = table[key] = deque(maxlen=points)
        table.move_to_end(key)
        rows.append(row)
        while len(table) > limit:
            table.popitem(last=False)

    def add_position(self, t: float, key, x: float, y: float) -> None:
        self._put(self.tracks, key, (t, float(x), float(y)), TRACK_POINTS, MAX_TRACKS)

    def add_bearing(self, t: float, key, ox: float, oy: float, bearing: float) -> None:
        self._put(self.bearings, key, (t, float(ox), float(oy), float(bearing) % 360.0),
                  BEARING_POINTS, MAX_BEARING_CONTACTS)

    def forget(self, t: float) -> None:
        for table in (self.tracks, self.bearings, self.opz):
            for key in [k for k, rows in table.items() if t - rows[-1][0] > FORGET_S]:
                del table[key]

    def positions(self, key) -> tuple:
        return tuple(self.tracks.get(key, ()))

    def bearing_history(self, key) -> tuple:
        return tuple(self.bearings.get(key, ()))


class ChartHistory:
    """Per-game chart history, keyed by side ("frigate" or a boat's id)."""

    def __init__(self) -> None:
        self.sides: dict = {}
        self._last_t = None
        self._world = None

    def side(self, key) -> _Side:
        side = self.sides.get(key)
        if side is None:
            side = self.sides[key] = _Side()
        return side

    def reset(self) -> None:
        self.sides.clear()
        self._last_t = None

    def record(self, game) -> None:
        """Sample the current public picture (called once per frame)."""
        t = float(getattr(game, "sim_t", 0.0))
        world = getattr(game, "world", None)
        if world is not self._world or (self._last_t is not None and t < self._last_t):
            # New mission, load or reset: the history starts anew.
            self.reset()
            self._world = world
        self._last_t = t
        self._record_frigate(game, t)
        boat = getattr(game, "_opfor", None)
        if boat is not None and getattr(boat, "sub", None) is not None:
            self._record_boat(game, boat, t)

    def _record_frigate(self, game, t: float) -> None:
        ship = getattr(game, "ship", None)
        if ship is None:
            return
        side = self.side("frigate")
        side.sample_own(t, ship.x, ship.y)
        if side.due_opz(t):
            opz_tracks = getattr(game, "opz_tracks", None)
            for track in (opz_tracks() if callable(opz_tracks) else ()):
                x, y = observations.position(track)
                if x is not None and y is not None:
                    side.add_opz(t, track.track_id, x, y)
        if not side.due(t):
            return
        radar_tracks = getattr(game, "radar_tracks", None)
        for track in (radar_tracks() if callable(radar_tracks) else ()):
            x, y = observations.position(track)
            if x is not None and y is not None:
                side.add_position(t, ("track", track["track_id"]), x, y)
        sonar = getattr(game, "sonar", None)
        contacts = sonar.active_contacts() if sonar is not None else ()
        for contact in contacts:
            x, y = observations.position(contact)
            if x is not None and y is not None:
                side.add_position(t, ("sonar", contact.id), x, y)
            bearing = getattr(contact, "passive_bearing", None)
            if bearing is None:
                bearing = getattr(contact, "bearing", None)
            if bearing is not None:
                side.add_bearing(t, contact.id,
                                 getattr(contact, "observer_x", ship.x),
                                 getattr(contact, "observer_y", ship.y), bearing)
        side.forget(t)

    def _record_boat(self, game, boat, t: float) -> None:
        sub = boat.sub
        side = self.side(("boat", sub.id))
        side.sample_own(t, sub.x, sub.y)
        if not side.due(t):
            return
        station = getattr(boat, "station", None)
        sonar = getattr(station, "sonar", None) if station is not None else None
        contacts = sonar.active_contacts() if sonar is not None else ()
        for contact in contacts:
            x, y = getattr(contact, "observed_x", None), getattr(contact, "observed_y", None)
            if (x is not None and y is not None
                    and getattr(contact, "range_source", None) in ("ping", "tma", "visual")):
                side.add_position(t, ("sonar", contact.id), x, y)
            bearing = getattr(contact, "passive_bearing", None)
            if bearing is None:
                bearing = getattr(contact, "bearing", None)
            if bearing is not None:
                side.add_bearing(t, contact.id, sub.x, sub.y, bearing)
        side.forget(t)
