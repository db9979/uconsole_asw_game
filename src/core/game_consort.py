"""The consort destroyer in the game (OPZ page 4, Remote Crew OPZ).

``src/core/consort.py`` holds its orders and the steering they ask for; this
mixin places the destroyer in a group-hunt scenario, takes the OPZ's orders,
runs its active sonar and its ASROC, and decides what reaches the frigate.
The destroyer itself is commanded own-force truth (datalink); its sonar
reaches the frigate only as measurements: a ``CONSORT`` fix on the frigate's
own sonar contact (its active echo, or its passive bearing crossed with the
frigate's), and its bearing lines on the OPZ.
"""

from __future__ import annotations

import math
import random

from src.core import config, consort as consort_model
from src.core.consort import ConsortOrders
from src.core.i18n import message
from src.enemies.surface import SurfaceShip


class ConsortMixin:
    """Orders, sensors and weapons of the consort destroyer."""

    def _reset_consort(self) -> None:
        self.consort = None
        # Display only (rebuilt on the report cadence, never saved): the
        # consort's passive bearing lines, keyed by its opaque track id.
        self._consort_bearings: dict = {}

    def _setup_consort(self) -> None:
        """Place the destroyer on its formation station (group-hunt scenarios)."""
        self._reset_consort()
        if not config.SCENARIOS.get(self.scenario_key, {}).get("consort"):
            return
        catalog = self.runtime_catalog
        profile = catalog.surfaces.get(config.CONSORT_PROFILE)
        if profile is None:
            return
        orders = ConsortOrders(0, config.CONSORT_CALLSIGN)
        x, y = self.world.nearest_water(*consort_model.station_point(orders, self.ship))
        # A stream of its own: the destroyer never shifts the world's draws.
        ship = SurfaceShip(x, y, rng=random.Random(f"consort:{self.seed}"), hostile=False,
                           profile=profile, side="friendly", doctrine="surface_combatant",
                           runtime_catalog=catalog)
        ship.rng = self.rng_world
        ship.name = ship.callsign = config.CONSORT_CALLSIGN
        ship.course = ship.target_course = self.ship.course
        ship.speed = ship.target_speed = min(12.0, ship.speed_cap_kn)
        ship.emitter = True
        ship.commanded = True
        orders.warship_id = ship.id
        self.warships.append(ship)
        self.consort = orders

    def consort_ship(self):
        orders = getattr(self, "consort", None)
        if orders is None:
            return None
        return next((ship for ship in self.warships if ship.id == orders.warship_id), None)

    def consort_datalink(self) -> bool:
        ship = self.consort_ship()
        return (ship is not None and not ship.sunk
                and math.hypot(ship.x - self.ship.x, ship.y - self.ship.y)
                <= config.CONSORT_DATALINK_NM)

    # --- what the frigate knows ------------------------------------------------------

    def _consort_prosecution(self):
        """Auto mode: the freshest located submarine of the frigate's own
        picture (classified by the operator, or the fire-control target)."""
        best = None
        for _, contact in sorted(self.sonar.contacts.items()):
            if contact.player_class != "U_BOOT" and contact is not self.target:
                continue
            fixes = [fix for fix in contact.active_fixes(self.sim_t)
                     if self.sim_t - fix["measured_at"] <= config.CONSORT_AUTO_FIX_S]
            if not fixes:
                continue
            fix = max(fixes, key=lambda item: (item["measured_at"], item["source"]))
            if best is None or fix["measured_at"] > best[0]["measured_at"]:
                best = (fix, contact)
        return best

    def consort_effective(self):
        """``(mode, point, active)`` the destroyer works on now."""
        orders = self.consort
        if orders.mode != "auto":
            return orders.mode, orders.point, orders.active or orders.mode == "prosecute"
        found = self._consort_prosecution()
        if found is None:
            return "formation", None, orders.active
        fix, _contact = found
        return "prosecute", (fix["x"], fix["y"]), True

    def consort_view(self) -> dict | None:
        """Own-force datalink state for the OPZ page and Remote Crew."""
        orders = getattr(self, "consort", None)
        ship = self.consort_ship()
        if orders is None or ship is None:
            return None
        mode, point, active = self.consort_effective()
        battery = ship.asroc_battery
        key = ship.asroc_weapon_key()
        dx, dy = ship.x - self.ship.x, ship.y - self.ship.y
        return dict(
            callsign=orders.callsign, sunk=bool(ship.sunk), datalink=self.consort_datalink(),
            x=ship.x, y=ship.y, course=ship.course, speed_kn=ship.speed,
            bearing=math.degrees(math.atan2(dx, -dy)) % 360.0, range_nm=math.hypot(dx, dy),
            mode=orders.mode, working=mode, station=orders.station,
            point=None if point is None else (float(point[0]), float(point[1])),
            active=bool(active), weapons_free=orders.weapons_free,
            asroc=0 if battery is None or key is None else int(battery.remaining_of(key)),
            bearings=[dict(row) for _, row in sorted(self._consort_bearings.items())])

    # --- orders ------------------------------------------------------------------

    def _consort_order_check(self):
        if getattr(self, "consort", None) is None or self.consort_ship() is None:
            return "no_consort"
        if self.consort_ship().sunk:
            return "consort_lost"
        if self.damage.station_down("opz"):
            return "opz_down"
        if not self.consort_datalink():
            return "no_link"
        return True

    def set_consort_mode(self, mode):
        if type(mode) is not str or mode not in consort_model.MODES:
            return "invalid_value"
        check = self._consort_order_check()
        if check is not True:
            return check
        if mode in ("search", "prosecute") and self.consort.point is None:
            ship = self.consort_ship()
            self.consort.point = (float(ship.x), float(ship.y))
        self.consort.mode = mode
        return True

    def set_consort_point(self, x, y):
        """Search or prosecute about a chart point (a plain click keeps the mode
        unless it is formation, hold or auto, which become search)."""
        size = float(self.world.size_nm)
        if not all(type(v) in (int, float) and math.isfinite(v) and 0.0 <= v <= size
                   for v in (x, y)):
            return "invalid_value"
        check = self._consort_order_check()
        if check is not True:
            return check
        self.consort.point = (float(x), float(y))
        if self.consort.mode not in ("search", "prosecute"):
            self.consort.mode = "search"
        return True

    def consort_point_to_selection(self):
        """Prosecute the selected OPZ track's plotted position."""
        from src.ui import observations
        track = self.selected_opz_track()
        if track is None:
            return "no_track"
        x, y = observations.position(track)
        if x is None or y is None:
            return "not_located"
        result = self.set_consort_point(config.clamp(float(x), 0.0, float(self.world.size_nm)),
                                        config.clamp(float(y), 0.0, float(self.world.size_nm)))
        if result is True:
            self.consort.mode = "prosecute"
        return result

    def cycle_consort_station(self):
        check = self._consort_order_check()
        if check is not True:
            return check
        keys = consort_model.STATION_KEYS
        self.consort.station = keys[(keys.index(self.consort.station) + 1) % len(keys)]
        self.consort.mode = "formation"
        return True

    def set_consort_station(self, station):
        if type(station) is not str or station not in consort_model.STATION_KEYS:
            return "invalid_value"
        check = self._consort_order_check()
        if check is not True:
            return check
        self.consort.station = station
        self.consort.mode = "formation"
        return True

    def set_consort_active(self, on):
        if type(on) is not bool:
            return "invalid_value"
        check = self._consort_order_check()
        if check is not True:
            return check
        self.consort.active = on
        return True

    def set_consort_weapons(self, free):
        if type(free) is not bool:
            return "invalid_value"
        check = self._consort_order_check()
        if check is not True:
            return check
        self.consort.weapons_free = free
        return True

    def consort_fire(self):
        """One ASROC from the destroyer: on the selected OPZ track's fresh fix
        (uConsole), else on the submarine it prosecutes."""
        if getattr(self, "consort", None) is not None and self.selected_opz_track() is not None:
            return self.consort_fire_on_selection()
        return self.consort_fire_on_prosecution()

    def consort_fire_on_prosecution(self):
        """One ASROC on the freshest located submarine of the frigate's picture
        (classified by the operator, or the fire-control target)."""
        check = self._consort_order_check()
        if check is not True:
            return check
        found = self._consort_prosecution()
        if found is None:
            return "not_located"
        fix, _contact = found
        if self.sim_t - fix["measured_at"] > config.CONSORT_FIX_FRESH_S:
            return "stale_fix"
        return self._consort_shoot(fix["x"], fix["y"], fix["depth_m"])

    def consort_fire_on_selection(self):
        """One ASROC from the destroyer on the selected track's fresh fix."""
        from src.ui import observations
        check = self._consort_order_check()
        if check is not True:
            return check
        track = self.selected_opz_track()
        if track is None:
            return "no_track"
        x, y = observations.position(track)
        age = observations.position_age(track, self.sim_t)
        if x is None or y is None or age is None:
            return "not_located"
        if age > config.CONSORT_FIX_FRESH_S:
            return "stale_fix"
        return self._consort_shoot(float(x), float(y), track.depth_m)

    def _consort_shoot(self, x: float, y: float, depth):
        ship = self.consort_ship()
        key = ship.asroc_weapon_key()
        if key is None or ship.asroc_battery.remaining_of(key) <= 0:
            return "no_weapon"
        if ship.pending_asroc or any(getattr(item, "launch_platform_id", None) == ship.id
                                     for item in self.asrocs):
            return "busy"
        if not ship.fire_asroc_at(x, y, depth):
            return "out_of_range"
        self.consort.last_shot_s = self.sim_t
        notice = message("consort.asroc_away", callsign=self.consort.callsign)
        self.flash(notice, 3.0)
        self.feed.add(self.world.format_time(), "waffen", notice)
        return True

    def _consort_feedback(self, result) -> None:
        """Banner for a refused uConsole order (the browser shows its own)."""
        if result is not True:
            self.flash(message("consort.refused." + str(result)), 2.0)

    # --- time ----------------------------------------------------------------------

    def _update_consort(self, dt: float) -> None:
        """Steer the destroyer, then let its sonar and weapons work (runs in
        the entity stage, after the platform sensors, before it moves)."""
        orders = getattr(self, "consort", None)
        ship = self.consort_ship()
        if orders is None or ship is None:
            return
        if ship.sunk:
            if not orders.lost:
                orders.lost = True
                notice = message("consort.lost", callsign=orders.callsign)
                self.flash(notice, 5.0)
                self.feed.add(self.world.format_time(), "schaden", notice)
            return
        mode, point, active = self.consort_effective()
        if ship._torpedo_evade_left <= 0.0:
            ship.target_course, ship.target_speed = consort_model.steer(
                orders, ship, self.ship, mode, point, self.sim_t)
        if not self.consort_datalink():
            self._consort_bearings.clear()
            return
        previous = self.sim_t - dt
        if math.floor(self.sim_t / config.CONSORT_REPORT_S) != math.floor(
                previous / config.CONSORT_REPORT_S):
            self._consort_passive_reports(ship)
        if active and self.sim_t >= orders.next_ping_s:
            orders.next_ping_s = self.sim_t + config.CONSORT_PING_S
            self._consort_ping(ship)
        if (orders.weapons_free and self.sim_t - orders.last_shot_s
                >= config.CONSORT_SHOT_GAP_S):
            found = self._consort_prosecution()
            if found is not None:
                fix, _contact = found
                if self.sim_t - fix["measured_at"] <= config.CONSORT_FIX_FRESH_S:
                    self._consort_shoot(fix["x"], fix["y"], fix["depth_m"])

    def _consort_passive_reports(self, ship) -> None:
        """Its hull sonar's bearings: lines on the OPZ, and a cross-fix with the
        frigate's own passive bearing on the same contact."""
        bearings = {}
        for sub in sorted(self.subs, key=lambda item: item.id):
            if sub.sunk:
                continue
            reports = [report for report in ship.sensor_suite.tracks_for_candidate(
                sub, self.sim_t) if report.domain == "sonar"
                and self.sim_t - report.last_seen <= 2.0 * config.CONSORT_REPORT_S]
            if not reports:
                continue
            report = max(reports, key=lambda item: item.last_seen)
            sigma = report.bearing_uncertainty_deg or 2.0
            bearings[report.track_id] = dict(
                x=report.observer_x, y=report.observer_y, bearing=report.bearing,
                uncertainty_deg=sigma, t=report.last_seen, quality=report.quality)
            contact = self.sonar.contacts.get(sub.id)
            if contact is None or contact.passive_bearing is None:
                continue
            seen = (contact._bearing_filter_t if contact._bearing_filter_t is not None
                    else contact.last_seen)
            if not 0.0 <= self.sim_t - seen < config.SONAR_CONTACT_LOST_S:
                continue
            ox = (contact.ship_observer_x if contact.ship_observer_x is not None
                  else self.ship.x)
            oy = (contact.ship_observer_y if contact.ship_observer_y is not None
                  else self.ship.y)
            cut = consort_model.cross_fix((ox, oy, contact.passive_bearing),
                                          (report.observer_x, report.observer_y,
                                           report.bearing), config.CONSORT_XFIX_MAX_NM)
            if cut is None:
                continue
            x, y, geometry = cut
            own_sigma = contact.bearing_uncertainty_deg or 2.0
            distance = max(math.hypot(x - ox, y - oy),
                           math.hypot(x - report.observer_x, y - report.observer_y))
            uncertainty = max(0.2, distance * math.radians(math.hypot(own_sigma, sigma))
                              / geometry)
            if uncertainty > 5.0:
                continue
            contact._fx, contact._fy = self.ship.x, self.ship.y
            contact.update_consort(x, y, self.sim_t, uncertainty,
                                   config.clamp(min(contact.quality, report.quality)
                                                * geometry, 0.1, 1.0))
        self._consort_bearings = bearings

    def _consort_ping(self, ship) -> None:
        """One active transmission: echoes become frigate contact fixes; every
        submarine in earshot hears the ping."""
        tick = int(round(self.sim_t * 10.0))
        blocked = getattr(self.world, "sonar_path_blocked", lambda *args: False)
        echoes = 0
        for sub in sorted(self.subs, key=lambda item: item.id):
            if sub.sunk:
                continue
            distance = math.hypot(sub.x - ship.x, sub.y - ship.y)
            if distance <= config.CONSORT_HEAR_PING_NM:
                sub.hear_ping(source=(ship.x, ship.y), kind="hull")
            echo = consort_model.ping_echo(
                self.seed, ship, sub, tick,
                blocked(ship.x, ship.y, 5.0, sub.x, sub.y, sub.depth))
            if echo is None:
                continue
            x, y, depth, quality = echo
            contact = self.sonar._get_contact(sub)
            contact._fx, contact._fy = self.ship.x, self.ship.y
            contact.update_consort(x, y, self.sim_t,
                                   config.CONSORT_ACTIVE_ERR_NM, quality,
                                   depth, config.CONSORT_ACTIVE_DEPTH_ERR_M)
            echoes += 1
        if echoes:
            notice = message("consort.echo", callsign=self.consort.callsign,
                             count=str(echoes))
            self.flash(notice, 2.5)
            self.feed.add(self.world.format_time(), "sonar", notice)
