"""The frigate's own ASROC and depth charges (``Game`` mixin).

Both fire from the Weapons station against the designated sonar contact,
through the same interlocks as the torpedo (affiliation, classification,
weapons room). The ASROC flies to the contact's observed position and
drops the helicopter's lightweight torpedo there; a depth-charge pattern
goes over the stern where the ship is. The flight and payload of an ASROC
are the friendly warships' (``SimMixin._update_asrocs``); only the store,
the datum and the depth charges live here. Model in
``src/weapons/depth_charge.py``.
"""

from __future__ import annotations

import math

from src.core import config, free_roam
from src.core.i18n import message
from src.weapons import depth_charge
from src.weapons.asw import ASROC, MAX_ASROCS
from src.weapons.depth_charge import DepthCharge

# Subs within this range hear a detonation and evade.
DEPTH_CHARGE_ALERT_NM = 5.0


class AswWeaponsMixin:
    """Own ASROC and depth charges of the frigate."""

    def _own_attack_interlock(self, contact):
        """The torpedo's target checks for a stand-off or close attack:
        a fresh contact, not marked friend or neutral, classified submarine.
        Returns a result code or None."""
        if contact is None or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S:
            return "invalid_target"
        if self._target_affiliation_interlock(contact) is not None or self.weapons_tight():
            return "roe_blocked"
        if self.weapon_classification(contact) != "U_BOOT":
            return "not_classified"
        if self.damage.station_down("weapons"):
            return "weapons_down"
        if self.damage.station_degraded("weapons"):
            return "weapons_degraded"
        return None

    def _own_attack_refused(self, result: str) -> str:
        keys = {"invalid_target": "runtime.target.invalid",
                "roe_blocked": "runtime.asw.roe_blocked",
                "not_classified": "runtime.asw.not_submarine",
                "weapons_down": "runtime.weapons.down",
                "weapons_degraded": "runtime.weapons.degraded",
                "not_located": "runtime.target.not_located",
                "out_of_range": "runtime.asroc.out_of_range",
                "salvo_limit": "runtime.asroc.salvo_limit",
                "empty_asroc": "runtime.asroc.empty",
                "empty_depth_charges": "runtime.depth_charge.empty",
                "reloading": "runtime.depth_charge.reloading",
                "too_slow": "runtime.depth_charge.too_slow"}
        key = keys[result]
        if result == "roe_blocked" and self.weapons_tight():
            key = "runtime.roe.weapons_tight"
        self.flash(message(key), 2.5)
        return result

    def fire_own_asroc(self) -> str:
        """Weapons key: an ASROC at the designated target."""
        return self.fire_own_asroc_at(self.target)

    def fire_own_asroc_at(self, contact, depth_m=None) -> str:
        """Fire one ASROC at a contact's observed position (range needed);
        the payload torpedo searches at ``depth_m`` (default: the preset)."""
        blocked = self._own_attack_interlock(contact)
        if blocked is not None:
            return self._own_attack_refused(blocked)
        if (contact.observed_x is None or contact.observed_y is None
                or not self._contact_range_fresh(contact)):
            return self._own_attack_refused("not_located")
        datum_x, datum_y = contact.observed_x, contact.observed_y
        distance = math.hypot(datum_x - self.ship.x, datum_y - self.ship.y)
        low, high = depth_charge.OWN_ASROC_RANGE_NM
        if not low <= distance <= high:
            return self._own_attack_refused("out_of_range")
        if self.own_asrocs_left <= 0:
            return self._own_attack_refused("empty_asroc")
        running = (len([t for t in self.torpedoes if t.state == "RUN"])
                   + len([a for a in self.asrocs if a.launch_platform_id is None]))
        if (running >= config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]
                or len(self.asrocs) >= MAX_ASROCS):
            return self._own_attack_refused("salvo_limit")
        self.own_asrocs_left -= 1
        self.asroc_seq += 1
        self.asrocs.append(ASROC(
            self.ship.x, self.ship.y, datum_x, datum_y, self.asroc_seq,
            depth_charge.OWN_ASROC_KEY,
            self.runtime_catalog.runtime_bindings["helicopter_torpedo"],
            depth_charge.OWN_ASROC_SPEED_KN, depth_charge.OWN_ASROC_RANGE_NM[1],
            "friendly", float(self.torpedo_depth if depth_m is None else depth_m), None))
        self._emit_sound("torpedo_launch")
        text = message("runtime.asroc.launched", contact=contact.id,
                       range=f"{distance:.1f}", left=self.own_asrocs_left)
        self.flash(text, 2.5)
        self.feed.add(self.world.format_time(), "waffen", text)
        return "ok"

    def drop_depth_charges(self) -> str:
        """Weapons key: a depth-charge pattern over the stern, set to the
        torpedo depth preset, against the designated contact."""
        return self.drop_depth_charges_at(self.target)

    def drop_depth_charges_at(self, contact, depth_m=None) -> str:
        """A pattern against ``contact``, set to ``depth_m`` (default: the
        torpedo depth preset)."""
        blocked = self._own_attack_interlock(contact)
        if blocked is not None:
            return self._own_attack_refused(blocked)
        if self.depth_charges_left <= 0:
            return self._own_attack_refused("empty_depth_charges")
        if self.depth_charge_reload_s > 0.0:
            return self._own_attack_refused("reloading")
        if abs(self.ship.speed) < depth_charge.MIN_DROP_SPEED_KN:
            return self._own_attack_refused("too_slow")
        wanted = self.torpedo_depth if depth_m is None else depth_m
        set_depth = config.clamp(float(wanted), depth_charge.MIN_DEPTH_M,
                                 depth_charge.MAX_DEPTH_M)
        points = depth_charge.pattern_points(self.ship.x, self.ship.y, self.ship.course)
        count = min(len(points), self.depth_charges_left,
                    depth_charge.MAX_DEPTH_CHARGES - len(self.depth_charges))
        for x, y in points[:count]:
            self.depth_charge_seq += 1
            self.depth_charges.append(DepthCharge(self.depth_charge_seq, x, y, set_depth))
        self.depth_charges_left -= count
        self.depth_charge_reload_s = depth_charge.PATTERN_RELOAD_S
        text = message("runtime.depth_charge.dropped", count=count,
                       depth=f"{set_depth:.0f}", left=self.depth_charges_left)
        self.flash(text, 2.5)
        self.feed.add(self.world.format_time(), "waffen", text)
        return "ok"

    def _update_depth_charges(self, dt: float) -> None:
        """Sink the charges; each detonates at its set depth or the seabed."""
        self.depth_charge_reload_s = max(0.0, self.depth_charge_reload_s - dt)
        # The rocket launcher's rounds share this stage (``SIM_ORDER``).
        self._update_rbu(dt)
        if not self.depth_charges:
            return
        survivors = []
        for charge in self.depth_charges:
            bottom = self.world.physical_depth_m(charge.x, charge.y)
            if not charge.update(dt, bottom):
                survivors.append(charge)
                continue
            self._detonate_depth_charge(charge)
        self.depth_charges = survivors

    def _detonate_depth_charge(self, charge) -> None:
        for sub in self.subs:
            if sub.sunk or sub.state == "SINKING":
                continue
            horizontal_m = math.hypot(sub.x - charge.x, sub.y - charge.y) * 1852.0
            if horizontal_m / 1852.0 > DEPTH_CHARGE_ALERT_NM:
                continue
            slant = math.hypot(horizontal_m, sub.depth - charge.depth)
            amount = depth_charge.depth_charge_damage(slant)
            if amount >= 1.0 and not self.world.sonar_path_blocked(
                    charge.x, charge.y, charge.depth, sub.x, sub.y, sub.depth):
                sub.hit(amount)
                free_roam.charge_frigate_hit(self, sub)
            else:
                sub.alert_torpedo(source=(charge.x, charge.y))
        self.sight_events.detonation(charge.x, charge.y, self.sim_t, "depth_charge",
                                     charge.depth)
        self.map_fx.splash("frigate", self.sim_t, charge.x, charge.y)
        self._emit_sound("explosion", at=(charge.x, charge.y))

    def own_asw_stores_line(self):
        """Weapons stores page: ASROC and depth charges left, reload."""
        reload = (message("weapons.dc_reload", seconds=f"{self.depth_charge_reload_s:.0f}")
                  if self.depth_charge_reload_s > 0.0 else message("weapons.dc_ready"))
        return message("weapons.asw_stores", asroc=self.own_asrocs_left,
                       charges=self.depth_charges_left, reload=reload)


__all__ = ["AswWeaponsMixin", "DEPTH_CHARGE_ALERT_NM"]
