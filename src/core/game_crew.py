"""Crew watches, fatigue and morale in the game (frigate and crewed boat).

``src/core/crew.py`` holds the model; this mixin advances it, credits
morale events from the world (kills, damage, tasks) and hands the crew's
effectiveness to the sonar operator, the lookout and the damage-control
teams.  The effects are derived from saved state, so a load re-applies
them exactly (``_apply_crew_effects``).
"""

from __future__ import annotations

from src.core import crew as crew_model
from src.core.crew import CrewState
from src.core.i18n import message


class CrewMixin:
    """Crew watch bill of the frigate and the crewed submarine."""

    def _reset_crew(self) -> None:
        self.crew_watch = CrewState(self.sim_t)

    def _boat_watch(self, boat) -> CrewState:
        """A fresh watch bill for a newly crewed boat; past events are not
        credited again."""
        watch = CrewState(self.sim_t)
        watch.kills = self._boat_sinkings()
        watch.damaged = int(boat.sub.damage // crew_model.BOAT_DAMAGE_STEP)
        return watch

    def _boat_sinkings(self) -> int:
        return (sum(1 for ship in self.civilians if ship.sunk)
                + sum(1 for ship in self.warships if ship.sunk)
                + int(bool(self.damage.ship_sunk)))

    # --- read by sensors and views -------------------------------------------

    def crew_effect(self) -> float:
        """The frigate crew's performance factor (1.0 fresh at start)."""
        watch = getattr(self, "crew_watch", None)
        return 1.0 if watch is None else watch.effectiveness(self.sim_t)

    def crew_view(self, watch: CrewState | None = None) -> dict:
        """Display state of one crew (the frigate's by default)."""
        watch = self.crew_watch if watch is None else watch
        return dict(
            watches=[dict(index=index + 1, fatigue=watch.fatigue[index],
                          on_duty=watch.action_stations or index == watch.on_watch)
                     for index in range(crew_model.WATCHES)],
            on_watch=watch.on_watch + 1,
            watch_left_s=watch.watch_left_s(self.sim_t),
            turnover=watch.in_turnover(self.sim_t),
            action_stations=watch.action_stations,
            morale=watch.morale,
            effectiveness=watch.effectiveness(self.sim_t))

    # --- orders ------------------------------------------------------------------

    def set_action_stations(self, enabled: bool):
        """Frigate: action stations on/off (Bridge ``G``, Remote Crew)."""
        if self.game_over:
            return "not_ready"
        if not self.crew_watch.set_action_stations(enabled, self.sim_t):
            return "not_ready"
        self._crew_notice("crew.action_stations_on" if enabled else "crew.action_stations_off")
        self._apply_crew_effects()
        return True

    def toggle_action_stations(self) -> None:
        self.set_action_stations(not self.crew_watch.action_stations)

    def change_watch(self):
        """Frigate: relieve the duty watch early (Damage page 3 ``W``)."""
        if self.game_over:
            return "not_ready"
        if not self.crew_watch.change_watch(self.sim_t):
            return "not_ready"
        self._crew_notice("crew.watch_relieved",
                          watch=str(self.crew_watch.on_watch + 1))
        self._apply_crew_effects()
        return True

    def boat_set_action_stations(self, enabled: bool):
        boat = self._opfor
        if boat is None or self.game_over:
            return "not_ready"
        if not boat.watch.set_action_stations(enabled, self.sim_t):
            return "not_ready"
        self._boat_crew_notice(boat, "crew.action_stations_on" if enabled
                               else "crew.action_stations_off")
        self._apply_crew_effects()
        return True

    def boat_change_watch(self):
        boat = self._opfor
        if boat is None or self.game_over:
            return "not_ready"
        if not boat.watch.change_watch(self.sim_t):
            return "not_ready"
        self._boat_crew_notice(boat, "crew.watch_relieved",
                               watch=str(boat.watch.on_watch + 1))
        self._apply_crew_effects()
        return True

    def _crew_event(self, name: str) -> None:
        """A morale event of the frigate crew (tasks call this)."""
        self.crew_watch.event(name)

    # --- notices -------------------------------------------------------------------

    def _crew_notice(self, key: str, **params) -> None:
        text = message(key, **params)
        self.feed.add(self.world.format_time(), "navigation", text)
        if getattr(self, "local_side", "frigate") != "uboot":
            self.flash(text, 3.0)

    def _boat_crew_notice(self, boat, key: str, **params) -> None:
        text = message(key, **params)
        boat.notice(self.sim_t, "navigation", text, stamp=self.world.format_time())
        if getattr(self, "local_side", "frigate") == "uboot":
            self.flash(text, 3.0)

    # --- time ---------------------------------------------------------------------

    def _update_crew(self, dt: float) -> None:
        watch = self.crew_watch
        damaged = sum(1 for room in self.damage.compartments.values() if room.state != "OK")
        kills = sum(1 for sub in self.subs if sub.side == "hostile" and sub.sunk)
        self._credit_morale(watch, kills, damaged)
        stress = crew_model.stress(damaged > 0)
        if watch.update(dt, self.sim_t, stress) and not self.game_over:
            self._crew_notice("crew.watch_relieved", watch=str(watch.on_watch + 1))
        boat = self._opfor
        if boat is not None and boat.sub in self.subs:
            sub = boat.sub
            sunk = self._boat_sinkings()
            hurt = int(sub.damage // crew_model.BOAT_DAMAGE_STEP)
            self._credit_morale(boat.watch, sunk, hurt)
            if (boat.watch.update(dt, self.sim_t, crew_model.stress(hurt > 0))
                    and not self.game_over):
                self._boat_crew_notice(boat, "crew.watch_relieved",
                                       watch=str(boat.watch.on_watch + 1))
        self._apply_crew_effects()

    @staticmethod
    def _credit_morale(watch: CrewState, kills: int, damaged: int) -> None:
        for _ in range(max(0, kills - watch.kills)):
            watch.event("kill")
        watch.kills = max(watch.kills, min(kills, crew_model.MAX_COUNT))
        if damaged > watch.damaged:
            for _ in range(damaged - watch.damaged):
                watch.event("damage")
        elif damaged < watch.damaged:
            for _ in range(watch.damaged - damaged):
                watch.event("repair")
        watch.damaged = min(damaged, crew_model.MAX_COUNT)

    def _apply_crew_effects(self) -> None:
        """Hand the crews' effectiveness to their sonar and repair teams."""
        effect = self.crew_effect()
        self._frigate_sonar.sonar.operator_dt_db = crew_model.sonar_penalty_db(effect)
        self.damage.crew_factor = effect
        boat = self._opfor
        if boat is not None:
            boat_effect = boat.watch.effectiveness(self.sim_t)
            boat.station.sonar.operator_dt_db = crew_model.sonar_penalty_db(boat_effect)
            boat.sub.damage_control.crew_factor = boat_effect
