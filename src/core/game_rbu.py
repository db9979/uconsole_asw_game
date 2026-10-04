"""The frigate's ASW rocket launcher in the game (``Game`` mixin).

An attack salvo goes to the designated contact's observed position through
the same interlocks as the ASROC (fresh range fix, classified submarine,
not friend or neutral, weapons room up).  A defence salvo goes out along
the bearing of a fresh torpedo warning; no target designation is needed,
the rounds are set shallow and destroy a torpedo they detonate close to.
Model in ``src/weapons/rbu.py``; saved as the root field ``rbu``.
"""

from __future__ import annotations

import math

from src.core import config, detrand, free_roam
from src.core.i18n import message
from src.weapons import rbu
from src.weapons.rbu import RbuRound

# Subs within this range of a detonation hear it and evade.
RBU_ALERT_NM = 4.0


class RbuMixin:
    """Salvoes, rounds in flight and in the water, store and reload."""

    def _reset_rbu(self) -> None:
        self.rbu_rounds: list[RbuRound] = []
        self.rbu_seq = 0
        self.rbu_rockets = rbu.STOCK
        self.rbu_reload_s = 0.0

    def rbu_serialize(self) -> dict:
        return dict(version=rbu.VERSION, seq=self.rbu_seq,
                    rounds=[item.serialize() for item in self.rbu_rounds],
                    rockets=self.rbu_rockets, reload_s=self.rbu_reload_s)

    def rbu_restore(self, state) -> None:
        self.rbu_seq = state["seq"]
        self.rbu_rounds = [RbuRound.restore(row) for row in state["rounds"]]
        self.rbu_rockets = state["rockets"]
        self.rbu_reload_s = float(state["reload_s"])

    def _rbu_ready(self):
        """None when a salvo can go, else a refusal code."""
        if self.damage.station_down("weapons"):
            return "weapons_down"
        if self.rbu_rockets <= 0:
            return "rbu_empty"
        if self.rbu_reload_s > 0.0:
            return "rbu_reloading"
        if len(self.rbu_rounds) + rbu.SALVO > rbu.MAX_ROUNDS:
            return "salvo_limit"
        return None

    def _rbu_refused(self, result: str) -> str:
        keys = {"rbu_empty": "runtime.rbu.empty", "rbu_reloading": "runtime.rbu.reloading",
                "rbu_no_warning": "runtime.rbu.no_warning",
                "out_of_range": "runtime.rbu.out_of_range"}
        if result in keys:
            self.flash(message(keys[result]), 2.5)
            return result
        return self._own_attack_refused(result)

    def fire_rbu(self) -> str:
        """Weapons key: an attack salvo at the designated target."""
        return self.fire_rbu_at(self.target)

    def fire_rbu_at(self, contact, depth_m=None) -> str:
        """An attack salvo at a contact's observed position (range needed),
        set to ``depth_m`` (default: the torpedo depth preset)."""
        blocked = self._own_attack_interlock(contact)
        if blocked is not None:
            return self._rbu_refused(blocked)
        if (contact.observed_x is None or contact.observed_y is None
                or not self._contact_range_fresh(contact)):
            return self._rbu_refused("not_located")
        distance = math.hypot(contact.observed_x - self.ship.x,
                              contact.observed_y - self.ship.y)
        if not rbu.RANGE_NM[0] <= distance <= rbu.RANGE_NM[1]:
            return self._rbu_refused("out_of_range")
        refusal = self._rbu_ready()
        if refusal is not None:
            return self._rbu_refused(refusal)
        wanted = self.torpedo_depth if depth_m is None else depth_m
        set_depth = config.clamp(float(wanted), rbu.MIN_DEPTH_M, rbu.MAX_DEPTH_M)
        count = self._rbu_launch(rbu.attack_points(contact.observed_x, contact.observed_y),
                                 set_depth, "attack")
        text = message("runtime.rbu.fired", count=count, range=f"{distance:.1f}",
                       depth=f"{set_depth:.0f}", left=self.rbu_rockets)
        self.flash(text, 2.5)
        self.feed.add(self.world.format_time(), "waffen", text)
        return "ok"

    def rbu_defence_bearing(self):
        """Bearing of the freshest torpedo warning, or None."""
        warnings = [row for row in self.torpedo_warnings()
                    if row["age_s"] <= rbu.DEFENCE_WARNING_AGE_S and row["source"] != "flood"]
        return None if not warnings else float(warnings[0]["bearing"]) % 360.0

    def fire_rbu_defence(self) -> str:
        """Weapons key: a defence salvo along the torpedo warning's bearing."""
        if self.damage.station_degraded("weapons") or self.damage.station_down("weapons"):
            return self._rbu_refused("weapons_down" if self.damage.station_down("weapons")
                                     else "weapons_degraded")
        bearing = self.rbu_defence_bearing()
        if bearing is None:
            return self._rbu_refused("rbu_no_warning")
        refusal = self._rbu_ready()
        if refusal is not None:
            return self._rbu_refused(refusal)
        count = self._rbu_launch(rbu.defence_points(self.ship.x, self.ship.y, bearing),
                                 rbu.DEFENCE_DEPTH_M, "defence")
        text = message("runtime.rbu.defence", count=count, bearing=f"{bearing:03.0f}",
                       left=self.rbu_rockets)
        self.flash(text, 2.5)
        self.feed.add(self.world.format_time(), "waffen", text)
        return "ok"

    def _rbu_launch(self, points, set_depth: float, mode: str) -> int:
        count = min(len(points), self.rbu_rockets)
        for index, (x, y) in enumerate(points[:count]):
            self.rbu_seq += 1
            distance = math.hypot(x - self.ship.x, y - self.ship.y)
            self.rbu_rounds.append(RbuRound(self.rbu_seq, x, y, set_depth,
                                            rbu.flight_s(distance), index == 0, mode))
        self.rbu_rockets -= count
        self.rbu_reload_s = rbu.RELOAD_S
        self._emit_sound("torpedo_launch")
        return count

    def _update_rbu(self, dt: float) -> None:
        self.rbu_reload_s = max(0.0, self.rbu_reload_s - dt)
        if not self.rbu_rounds:
            return
        survivors = []
        for item in self.rbu_rounds:
            bottom = self.world.physical_depth_m(item.x, item.y)
            event = item.update(dt, bottom)
            if event == "detonate":
                self._rbu_detonate(item)
                continue
            if event == "splash" and item.lead:
                self._rbu_splash(item)
            survivors.append(item)
        self.rbu_rounds = survivors

    def _rbu_splash(self, item) -> None:
        """The salvo hits the water: submarines near enough hear it."""
        boat = self._opfor
        for sub in sorted(self.subs, key=lambda entry: entry.id):
            if sub.sunk or sub.state == "SINKING":
                continue
            if math.hypot(sub.x - item.x, sub.y - item.y) > rbu.SPLASH_HEARD_NM:
                continue
            if boat is not None and boat.sub is sub:
                if boat.sonar_down():
                    continue
                bearing = (math.degrees(math.atan2(item.x - sub.x, -(item.y - sub.y)))
                           + config.UBOOT_DETONATION_BEARING_SD_DEG
                           * detrand.normal(sub.sensor_seed, "rbu-splash", item.seq)) % 360.0
                boat.orders.event("rbu_splash", bearing=f"{round(bearing) % 360:03d}")
            elif not sub.manual:
                sub.alert_torpedo(source=(item.x, item.y))

    def _rbu_detonate(self, item) -> None:
        for sub in self.subs:
            if sub.sunk or sub.state == "SINKING":
                continue
            horizontal_m = math.hypot(sub.x - item.x, sub.y - item.y) * 1852.0
            if horizontal_m / 1852.0 > RBU_ALERT_NM:
                continue
            slant = math.hypot(horizontal_m, sub.depth - item.depth)
            amount = rbu.damage(slant)
            if amount >= 1.0 and not self.world.sonar_path_blocked(
                    item.x, item.y, item.depth, sub.x, sub.y, sub.depth):
                sub.hit(amount)
                free_roam.charge_frigate_hit(self, sub)
            elif item.lead:
                sub.alert_torpedo(source=(item.x, item.y))
        for torpedo in self.enemy_torpedoes:
            if torpedo.state != "RUN":
                continue
            slant = math.hypot(math.hypot(torpedo.x - item.x, torpedo.y - item.y) * 1852.0,
                               torpedo.depth - item.depth)
            if slant <= rbu.TORPEDO_KILL_M:
                torpedo.state = "SASE"
                text = message("runtime.rbu.torpedo_silent")
                self.flash(text, 4.0)
                self.feed.add(self.world.format_time(), "sonar", text)
        if item.lead:
            self.sight_events.detonation(item.x, item.y, self.sim_t, "rbu", item.depth)
            self.map_fx.splash("frigate", self.sim_t, item.x, item.y)
            self._emit_sound("explosion", at=(item.x, item.y))

    def rbu_stores_line(self):
        reload = (message("weapons.dc_reload", seconds=f"{self.rbu_reload_s:.0f}")
                  if self.rbu_reload_s > 0.0 else message("weapons.dc_ready"))
        return message("weapons.rbu_stores", rockets=self.rbu_rockets, reload=reload)


__all__ = ["RbuMixin", "RBU_ALERT_NM"]
