"""Wounded crew in the game (``Game`` mixin; model in ``casualties.py``).

The frigate and every submarine keep a roster.  It advances with the crew
(0.5 s cadence) from each ship's own compartments, and its station factors
join the crew's effectiveness: the sonar room's recognition, the weapons'
reload and flooding, the damage-control parties' work.  Both sides decide
the same two things: where the medical team works and which station gets
men from the resting watches.  AI ships re-man a station on their own.
"""

from __future__ import annotations

from src.core import casualties as model
from src.core import hunter
from src.core.casualties import Casualties
from src.core.i18n import message
from src.enemies import damage_control

# An AI ship re-mans a station with this many empty posts.
AUTO_REASSIGN_GAPS = 2
MAX_SUB_ROSTERS = 64


def frigate_damage_points(damage) -> float:
    return sum(room.flood + room.fire for room in damage.compartments.values())


def frigate_levels(damage):
    """Exposure per station and the station of the worst-hit room."""
    levels = {station: 0.0 for station in model.STATIONS}
    worst, worst_value = None, 0.0
    for key, room in damage.compartments.items():
        station = model.station_of(key, model.FRIGATE_ROOMS)
        value = max(room.fire, room.flood) / 100.0
        levels[station] = max(levels[station], value)
        if room.flood + room.fire > worst_value:
            worst, worst_value = station, room.flood + room.fire
    return levels, worst


def boat_levels(control):
    levels = {station: 0.0 for station in model.STATIONS}
    worst, worst_value = None, 0.0
    for index, name in enumerate(damage_control.COMPARTMENTS):
        room = control.compartments[index]
        station = model.station_of(name, model.BOAT_ROOMS)
        water = room.water_kg / max(1.0, damage_control.capacity_kg(index))
        value = max(room.fire, water, room.chlorine)
        levels[station] = max(levels[station], min(1.0, value))
        if value > worst_value:
            worst, worst_value = station, value
    return levels, worst


class CasualtiesMixin:
    """Rosters of the frigate and the submarines."""

    def _reset_casualties(self) -> None:
        self.casualties = Casualties(frigate_damage_points(self.damage))
        self.sub_casualties: dict[int, Casualties] = {}

    def casualties_serialize(self) -> dict:
        present = {sub.id for sub in self.subs}
        return dict(frigate=self.casualties.serialize(),
                    subs=[dict(id=sub_id, roster=roster.serialize())
                          for sub_id, roster in sorted(self.sub_casualties.items())
                          if sub_id in present])

    @staticmethod
    def casualties_valid(state, sub_ids) -> bool:
        if not isinstance(state, dict) or set(state) != {"frigate", "subs"}:
            return False
        if not Casualties.valid_state(state["frigate"]):
            return False
        rows = state["subs"]
        if not isinstance(rows, list) or len(rows) > MAX_SUB_ROSTERS:
            return False
        seen = []
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"id", "roster"}
                    or type(row["id"]) is not int or row["id"] not in sub_ids
                    or not Casualties.valid_state(row["roster"])):
                return False
            seen.append(row["id"])
        return seen == sorted(set(seen))

    def casualties_restore(self, state) -> None:
        self.casualties = Casualties.restore(state["frigate"])
        self.sub_casualties = {row["id"]: Casualties.restore(row["roster"])
                               for row in state["subs"]}

    def peek_roster(self, sub) -> Casualties:
        """A submarine's roster for display, never creating one."""
        roster = self.sub_casualties.get(sub.id)
        return Casualties(float(sub.damage)) if roster is None else roster

    def sub_roster(self, sub) -> Casualties:
        roster = self.sub_casualties.get(sub.id)
        if roster is None:
            roster = Casualties(float(sub.damage))
            if len(self.sub_casualties) < MAX_SUB_ROSTERS:
                self.sub_casualties[sub.id] = roster
        return roster

    def casualties_hit(self, rooms) -> None:
        """A torpedo hit wounds people at once where it struck: three in the
        first compartment's station, one in the second's."""
        hurt = 0
        for index, room in enumerate(list(rooms)[:2]):
            station = model.station_of(room, model.FRIGATE_ROOMS)
            for _ in range(3 if index == 0 else 1):
                hurt += int(self.casualties.wound(station))
        if hurt and not self.game_over:
            self._crew_notice("casualties.wounded", count=hurt,
                              total=self.casualties.wounded)

    # --- time ------------------------------------------------------------------

    def _update_casualties(self, dt: float) -> None:
        levels, worst = frigate_levels(self.damage)
        hurt = self.casualties.update(dt, frigate_damage_points(self.damage), levels, worst)
        if hurt and not self.game_over:
            self._crew_notice("casualties.wounded", count=hurt,
                              total=self.casualties.wounded)
        if hunter.active(self):
            self._auto_reassign(self.casualties, self.crew_watch)
        boat = self._opfor
        present = {sub.id for sub in self.subs}
        for sub_id in [key for key in self.sub_casualties if key not in present]:
            del self.sub_casualties[sub_id]
        for sub in sorted(self.subs, key=lambda item: item.id):
            if sub.sunk:
                continue
            roster = self.sub_roster(sub)
            levels, worst = boat_levels(sub.damage_control)
            hurt = roster.update(dt, float(sub.damage), levels, worst)
            crewed = boat is not None and boat.sub is sub
            if crewed:
                if hurt and not self.game_over:
                    boat.orders.event("wounded", count=str(hurt), total=str(roster.wounded))
            else:
                self._auto_reassign(roster, None)

    def _auto_reassign(self, roster: Casualties, watch) -> None:
        station = roster.worst()
        if station is not None and roster.gaps(station) >= AUTO_REASSIGN_GAPS:
            self._reassign(roster, watch, station)

    def _reassign(self, roster: Casualties, watch, station=None):
        result = roster.reassign(self.sim_t, station)
        if isinstance(result, str):
            return result
        _station, men = result
        if watch is not None:
            # The men come off their rest: every resting watch tires.
            for index in range(len(watch.fatigue)):
                if watch.action_stations or index != watch.on_watch:
                    watch.fatigue[index] = min(1.0, watch.fatigue[index]
                                               + model.REASSIGN_FATIGUE * men)
        return result

    # --- orders ----------------------------------------------------------------

    def casualty_medic(self):
        """Frigate: the medical team to the next station (Damage page 3 ``M``)."""
        if self.game_over:
            return "not_ready"
        order = self.casualties.cycle_medic()
        self._crew_notice("casualties.medic_" + ("auto" if order is None else "to"),
                          station=message("casualties.station." + (order or "damage")))
        return True

    def casualty_reassign(self):
        """Frigate: men from the resting watches to the worst station (``U``)."""
        if self.game_over:
            return "not_ready"
        result = self._reassign(self.casualties, self.crew_watch)
        if isinstance(result, str):
            self.flash(message("casualties.refused." + result), 2.5)
            return result
        station, men = result
        self._crew_notice("casualties.reassigned", men=men,
                          station=message("casualties.station." + station))
        self._apply_crew_effects()
        return True

    def boat_casualty_medic(self):
        boat = self._opfor
        if boat is None or self.game_over:
            return "not_ready"
        order = self.sub_roster(boat.sub).cycle_medic()
        self._boat_crew_notice(boat, "casualties.medic_" + ("auto" if order is None else "to"),
                               station=message("casualties.station." + (order or "damage")))
        return True

    def boat_casualty_reassign(self):
        boat = self._opfor
        if boat is None or self.game_over:
            return "not_ready"
        result = self._reassign(self.sub_roster(boat.sub), boat.watch)
        if isinstance(result, str):
            if self.local_side == "uboot":
                self.flash(message("casualties.refused." + result), 2.5)
            return result
        station, men = result
        self._boat_crew_notice(boat, "casualties.reassigned", men=men,
                               station=message("casualties.station." + station))
        self._apply_crew_effects()
        return True

    # --- effects and views -------------------------------------------------------

    def casualty_factor(self, station: str, sub=None) -> float:
        roster = self.casualties if sub is None else self.sub_casualties.get(sub.id)
        return 1.0 if roster is None else roster.factor(station)

    def casualty_view(self, roster: Casualties | None = None) -> dict:
        roster = self.casualties if roster is None else roster
        return dict(wounded=roster.wounded,
                    serious=sum(roster.serious.values()),
                    returned=roster.returned,
                    stations=[dict(station=station, gaps=roster.gaps(station),
                                   posts=model.POSTS[station],
                                   factor=roster.factor(station))
                              for station in model.STATIONS],
                    medic=roster.medic, medic_order=roster.medic_order,
                    spare=roster.spare(),
                    reassign_in_s=max(0.0, roster.reassign_t - self.sim_t))


__all__ = ["CasualtiesMixin", "frigate_levels", "boat_levels"]
