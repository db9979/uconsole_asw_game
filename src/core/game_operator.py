"""Operator commands of the frigate's stations: navigation and plant orders,
sonar and TMA controls, radar, helicopter, weapons and radio actions. Local
keys and Remote Crew commands both end here and pass the same checks
(``Game`` mixin).

Verbatim moves from ``game.py`` (plan 1.3, phase 2, step 4b)."""

import math


from src.core import boat_threat
from src.core import baffles
from src.core import config
from src.ship import route as route_model
from src.core.commands import STATION_PAGES, station_page_step
from src.core.i18n import display_value, message, raw_text
from src.air import helicopter as helicopter_physics
from src.core.station import Station
from src.core import opfor
from src.core.optics import optics_key
from src.sonar import analysis_tools
from src.sonar import class_library
from src.sonar import tma_operator
from src.sonar.sonar import SONAR_ARRAY_MODES, Contact, TowState
from src.ui.contact_analyzer import ContactAnalyzer
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import SONAR_BAND_PRESETS, TMA_ACCEPT_MIN_FIT
from src.core.game_weapon_orders import WeaponOrdersMixin
# Names tests and tools import from ``src.core.game`` (kept as re-exports).


class OperatorMixin(WeaponOrdersMixin):
    """Command half of ``Game``: every station action shared by keys and browsers."""

    def _navigation_order_live(self) -> bool:
        # The simulation never pauses: menus and overlays own local input only,
        # so crew orders stay live behind them.
        return (self.running and not self.game_over
                and not self.in_menu and not self.main_menu
                and not self.splash_active
                and self.input_mode in (None, "course", "speed"))

    def _set_course_order(self, course: float, station: str) -> str:
        """Apply a validated shared helm order for one local station owner."""
        if type(course) not in (int, float):
            return "invalid_value"
        try:
            valid = math.isfinite(course) and 0.0 <= course < 360.0
        except OverflowError:
            valid = False
        if not valid:
            return "invalid_value"
        if not self._navigation_order_live():
            return "phase_blocked"
        if self.damage.station_down(station):
            return f"{station}_down"
        self.ship.target_course = course
        self.feed.add(self.world.format_time(), "navigation",
                      message("runtime.numeric.course_feed", course=f"{course:03.0f}"))
        # A helm order takes over from the autopilot.
        self.cancel_route()
        return "ok"

    # --- Bridge autopilot route (save v28 ``route``) ---

    def _route_order_check(self):
        if not self._navigation_order_live():
            return "phase_blocked"
        if self.damage.station_down("bridge"):
            return "bridge_down"
        return None

    def add_route_waypoint(self, x: float, y: float) -> str:
        """Append a waypoint to the autopilot route; the helm follows it."""
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y)):
            return "invalid_value"
        blocked = self._route_order_check()
        if blocked is not None:
            return blocked
        size = float(self.world.size_nm)
        x, y = config.clamp(float(x), 0.0, size), config.clamp(float(y), 0.0, size)
        if not self.route.active or self.route.kind != "manual":
            self.route.clear()
        start = self.route.points[-1] if self.route.points else (self.ship.x, self.ship.y)
        detour = route_model.plan_leg(
            self._route_depth, start[0], start[1], x, y, self._route_min_depth(), size,
            max(0, route_model.MAX_ROUTE_POINTS - len(self.route.points) - 1))
        if not self.route.add(x, y, detour or ()):
            return "route_full"
        number = len(self.route.points)
        self.feed.add(self.world.format_time(), "navigation", message(
            "runtime.route.waypoint", number=number,
            bearing=f"{route_model.bearing_to(self.ship.x, self.ship.y, x, y):03.0f}"))
        self._report_route_leg(number, detour)
        return "ok"

    def _route_depth(self, x: float, y: float) -> float:
        """Chart depth the autopilot plans on: chart datum shoaled by the
        charted rocks and wrecks (known geography, no live tide)."""
        depth = self.world.charted_depth_m(x, y)
        hazard = self.world.ocean.hazard_top_depth_m(x, y)
        return depth if hazard is None else min(depth, hazard)

    def _route_min_depth(self) -> float:
        return self.ship.hull_spec.minimum_depth_m + route_model.ROUTE_DEPTH_MARGIN_M

    def _report_route_leg(self, number: int, detour) -> None:
        """Feed the planning result of the leg ending at waypoint ``number``."""
        if detour is None:
            text = message("runtime.route.hazard", number=number)
        elif detour:
            text = message("runtime.route.detour", number=number, count=len(detour))
        else:
            return
        self.feed.add(self.world.format_time(), "navigation", text)
        self.flash(text, 3.0)

    def _plan_route_legs(self, points) -> tuple[list, list]:
        """Detours for a whole generated route from the ship's position:
        (points with detours, numbers of legs left crossing a hazard)."""
        size = float(self.world.size_nm)
        planned, unsafe = [], []
        x, y = self.ship.x, self.ship.y
        for px, py in points:
            detour = route_model.plan_leg(
                self._route_depth, x, y, px, py, self._route_min_depth(), size,
                max(0, route_model.MAX_ROUTE_POINTS - len(planned) - 1))
            if detour and len(planned) + len(detour) + 1 <= route_model.MAX_ROUTE_POINTS:
                planned.extend(detour)
            elif detour is None or detour:
                unsafe.append(len(planned) + 1)
            planned.append((px, py))
            x, y = px, py
        return planned, unsafe

    def start_route_pattern(self, kind: str) -> str:
        """Start a search pattern from the ship's position and course."""
        if kind not in route_model.PATTERNS:
            return "invalid_value"
        blocked = self._route_order_check()
        if blocked is not None:
            return blocked
        self.route.start_pattern(kind, self.ship.x, self.ship.y, self.ship.course)
        size = float(self.world.size_nm)
        self.route.points, unsafe = self._plan_route_legs(
            [(config.clamp(x, 0.0, size), config.clamp(y, 0.0, size))
             for x, y in self.route.points])
        self.feed.add(self.world.format_time(), "navigation",
                      message(f"runtime.route.pattern_{kind}"))
        for number in unsafe:
            self._report_route_leg(number, None)
        return "ok"

    def cycle_route_pattern(self) -> str:
        """Bridge key: no route -> zigzag -> expanding square -> off."""
        if self.route.active and self.route.kind == route_model.PATTERNS[-1]:
            return self.clear_route()
        index = (route_model.PATTERNS.index(self.route.kind) + 1
                 if self.route.active and self.route.kind in route_model.PATTERNS else 0)
        return self.start_route_pattern(route_model.PATTERNS[index])

    def clear_route(self) -> str:
        blocked = self._route_order_check()
        if blocked is not None:
            return blocked
        self.cancel_route()
        return "ok"

    def clear_baffles(self) -> str:
        """Bridge: swing the ordered course to hear into the own baffles,
        then come back (``baffles.py``)."""
        blocked = self._route_order_check()
        if blocked:
            return blocked
        state = baffles.start(self.ship.target_course, self.sim_t)
        result = self._set_course_order(state[1], "bridge")
        if result != "ok":
            return result
        self.baffle_clear = state
        text = message("runtime.baffles.clearing", course=f"{state[1]:03.0f}",
                       back=f"{state[0]:03.0f}")
        self.feed.add(self.world.format_time(), "navigation", text)
        self.flash(text, 4.0)
        return "ok"

    def _steer_baffle_clear(self) -> None:
        """Return to the previous course once the baffles are cleared."""
        state, back = baffles.step(self.baffle_clear, self.ship.target_course, self.sim_t)
        self.baffle_clear = state
        if back is not None and not self.damage.station_down("bridge"):
            self.ship.target_course = back
            self.feed.add(self.world.format_time(), "navigation", message(
                "runtime.baffles.cleared", course=f"{back:03.0f}"))

    def cancel_route(self) -> None:
        """Drop an active route (a helm order or the rudder took over)."""
        if not self.route.active:
            return
        self.route.clear()
        self.feed.add(self.world.format_time(), "navigation",
                      message("runtime.route.cancelled"))

    def _steer_route(self, dt: float = 0.0) -> None:
        """Autopilot: steer the ordered course to the route's next waypoint."""
        if not self.route.active or self.damage.station_down("bridge"):
            return
        period = route_model.WATCH_PERIOD_S
        if dt > 0.0 and math.floor(self.sim_t / period) != math.floor((self.sim_t + dt) / period):
            if not self._watch_route_ahead():
                return
        course, reached = self.route.steer(self.ship.x, self.ship.y)
        if reached:
            if course is None:
                self.feed.add(self.world.format_time(), "navigation",
                              message("runtime.route.complete"))
                self.route.clear()
                return
            self.feed.add(self.world.format_time(), "navigation", message(
                "runtime.route.reached", number=self.route.index))
        if course is not None and abs(((course - self.ship.target_course + 180.0)
                                       % 360.0) - 180.0) > 0.05:
            self.ship.target_course = course

    def _watch_route_ahead(self) -> bool:
        """Look ahead on the leg (two minutes at the present speed, at
        least half a mile): chart shoal water there gets a detour to the
        current waypoint, or stops the route. False when it stopped."""
        wx, wy = self.route.current()
        x, y = self.ship.x, self.ship.y
        distance = math.hypot(wx - x, wy - y)
        ahead = min(distance, max(route_model.WATCH_MIN_NM, config.kn_to_nm_per_s(
            abs(self.ship.speed)) * route_model.WATCH_AHEAD_S))
        if distance <= 0.0 or ahead <= 0.0:
            return True
        ex, ey = x + (wx - x) * ahead / distance, y + (wy - y) * ahead / distance
        minimum = self._route_min_depth()
        if route_model.leg_hazard(self._route_depth, x, y, ex, ey, minimum) is None:
            return True
        detour = route_model.plan_leg(
            self._route_depth, x, y, wx, wy, minimum, float(self.world.size_nm),
            max(0, route_model.MAX_ROUTE_POINTS - len(self.route.points)))
        if detour and self.route.insert_detour(detour):
            text = message("runtime.route.replanned", count=len(detour))
            self.feed.add(self.world.format_time(), "navigation", text)
            self.flash(text, 3.0)
            return True
        # No way on: the autopilot turns back the way it came (known safe
        # water) and hands the ship to the helm.
        text = message("runtime.route.hazard_stop")
        self.route.clear()
        self.ship.target_course = (route_model.bearing_to(x, y, wx, wy) + 180.0) % 360.0
        self.feed.add(self.world.format_time(), "navigation", text)
        self.flash(text, 4.0)
        return False

    def order_course(self, course: float) -> str:
        """Apply a Bridge course order and return a stable result code."""
        return self._set_course_order(course, "bridge")

    def set_engine_course(self, course: float) -> str:
        """Set the common course controller from the machinery station."""
        return self._set_course_order(course, "engine")

    def order_speed(self, speed_kn: float) -> str:
        """Apply a validated ahead-speed order and return a stable result code."""
        if type(speed_kn) not in (int, float):
            return "invalid_value"
        try:
            valid = (math.isfinite(speed_kn)
                     and 0.0 <= speed_kn <= config.SHIP_SPEED_MAX_KN)
        except OverflowError:
            valid = False
        if not valid:
            return "invalid_value"
        if not self._navigation_order_live():
            return "phase_blocked"
        if self.ship.fuel_kg <= 0.0:
            return "no_fuel"
        self.ship.target_speed = speed_kn
        self.ship.astern = False
        self.ship.order_idx = min(range(len(config.TELEGRAPH_ORDERS)),
                                  key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1]
                                                    - speed_kn))
        self.feed.add(self.world.format_time(), "navigation",
                      message("runtime.numeric.speed_feed", speed=f"{speed_kn:.1f}"))
        return "ok"

    def set_engine_telegraph(self, order: str):
        if type(order) is not str:
            return "invalid_value"
        if self.damage.station_down("engine"):
            return "engine_down"
        if self.ship.fuel_kg <= 0.0:
            return "no_fuel"
        if order == "ASTERN":
            self.ship.astern = True
            self.ship.order_idx = 0
            self.ship.target_speed = config.ASTERN_SPEED_KN
        else:
            index = next((i for i, item in enumerate(config.TELEGRAPH_ORDERS)
                          if item[0] == order), None)
            if index is None:
                return "invalid_value"
            self.ship.astern = False
            self.ship.order_idx = index
            self.ship.target_speed = config.TELEGRAPH_ORDERS[index][1]
        return True

    def _cycle_engine_telegraph(self, delta: int):
        orders = ("ASTERN", *(item[0] for item in config.TELEGRAPH_ORDERS))
        index = orders.index(self.ship.telegraph)
        return self.set_engine_telegraph(
            orders[config.clamp(index + delta, 0, len(orders) - 1)])

    def set_engine_speed(self, speed_kn: float):
        if self.damage.station_down("engine"):
            return "engine_down"
        return self.order_speed(speed_kn)

    def set_plant_mode(self, mode: str):
        """Select the propulsion plant: AUTO (both as needed), DIESEL (quiet,
        18 kn) or TURBINE (loud, full speed, more fuel)."""
        if type(mode) is not str or mode not in self.ship.PLANT_MODES:
            return "invalid_value"
        if self.damage.station_down("engine"):
            return "engine_down"
        self.ship.plant_mode = mode
        self.flash(message("runtime.plant." + mode.lower()), 2.0)
        return True

    def _cycle_plant_mode(self) -> None:
        modes = self.ship.PLANT_MODES
        self.set_plant_mode(modes[(modes.index(self.ship.plant_mode) + 1) % len(modes)])

    def set_counterflood(self, enabled: bool):
        """Open (True) or close (False) the counter-flooding valve of the hull
        side opposite the list; the model closes it below one degree."""
        if type(enabled) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "not_ready"
        if not enabled:
            self.damage.stop_counterflood()
            self.flash(message("runtime.counterflood.off"), 2.0)
            return True
        result = self.damage.order_counterflood()
        if result is not True:
            self.flash(message("runtime.counterflood." + result), 2.0)
            return result
        self.flash(message("runtime.counterflood.on",
                           room=display_value("compartment", self.damage.counterflood_room)), 2.0)
        return True

    def _toggle_counterflood(self) -> None:
        self.set_counterflood(self.damage.counterflood_room is None)

    def set_quiet_mode(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self.damage.station_down("engine"):
            return "engine_down"
        self.ship.quiet_mode = enabled
        return True

    def assign_damage_team(self, team: int, compartment: str):
        if type(team) is not int or type(compartment) is not str:
            return "invalid_value"
        if team not in self.damage.teams or compartment not in self.damage.compartments:
            return "invalid_value"
        if self.damage.ship_sunk:
            return "not_ready"
        if not self.damage.assign_team(team, compartment):
            return "not_ready"
        return True

    def unassign_damage_team(self, team: int, compartment: str):
        if (type(team) is not int or type(compartment) is not str
                or team not in self.damage.teams
                or compartment not in self.damage.compartments):
            return "invalid_value"
        if self.damage.teams[team] != compartment:
            return "stale_ref"
        self.damage.unassign_team(team)
        return True

    def set_sonar_listen_bearing(self, bearing: float):
        if (type(bearing) not in (int, float) or not 0 <= bearing < 360
                or not math.isfinite(bearing)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        # Retuning keeps the listening stream running: the receiver reset is a
        # sequence gap that _update_audio joins without a silent re-buffer.
        self.sonar.set_listen_bearing(bearing)
        return True

    def set_sonar_focus(self, contact):
        if self._sonar_down():
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact):
            return "stale_ref"
        if not 0 <= self.sim_t - contact.last_seen <= 2.0:
            return "stale_ref"
        self.selected_contact = contact
        self.sonar.set_listen_bearing(contact.bearing)
        self.sonar.focus_locked = True
        self.sonar._listen_target_id = contact.target_id
        return True

    def clear_sonar_focus(self):
        if self._sonar_down():
            return "sonar_down"
        self.sonar.focus_locked = False
        self.sonar._listen_target_id = None
        return True

    def set_sonar_array_mode(self, mode: str):
        if type(mode) is not str or mode not in SONAR_ARRAY_MODES:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar_mode = mode
        return True

    def set_sonar_tas(self, deployed: bool):
        if type(deployed) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        state = self.sonar.tow_status(self.sonar_observer.speed)["state"]
        if state == "FAULT":
            return "tas_fault"
        is_deploying = state in ("DEPLOYING", "STREAMED")
        if deployed == is_deploying:
            return True
        return True if self.sonar.toggle_tow(self.sonar_observer.speed) else "tas_fault"

    def set_sonar_tow_depth(self, depth_m: float):
        if (type(depth_m) not in (int, float)
                or not config.SONAR_TOWED_DEPTH_MIN_M <= depth_m
                <= config.SONAR_TOWED_DEPTH_MAX_M or not math.isfinite(depth_m)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        if self.sonar.tow_state != TowState.STREAMED:
            return "not_ready"
        limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                    config.SONAR_TOWED_DEPTH_MAX_M
                    - self.sonar_observer.speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
        if depth_m > limit:
            return "not_ready"
        self.sonar.towed_depth_target_m = depth_m
        return True

    def _sea_state_now(self) -> float:
        return float(getattr(self.world, "effective_sea_state", self.world.sea_state))

    def set_sonar_vds(self, deployed: bool):
        if type(deployed) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        state = self.sonar.vds_status()["state"]
        if state == "FAULT":
            return "vds_fault"
        if deployed == (state in ("DEPLOYING", "STREAMED")):
            return True
        return (True if self.sonar.toggle_vds(self.sonar_observer.speed, self._sea_state_now())
                else "vds_fault")

    def set_sonar_vds_depth(self, depth_m: float):
        if (type(depth_m) not in (int, float) or not math.isfinite(depth_m)
                or not config.SONAR_VDS_DEPTH_MIN_M <= depth_m <= config.SONAR_VDS_DEPTH_MAX_M):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        if self.sonar.vds_state != TowState.STREAMED:
            return "not_ready"
        if depth_m > self.sonar.vds_depth_limit_m(self.sonar_observer.speed):
            return "not_ready"
        self.sonar.vds_depth_target_m = float(depth_m)
        return True

    def measure_sonar_bt(self):
        if self._sonar_down():
            return "sonar_down"
        return (True if self.sonar.measure_environment(
            self.world, self.sonar_observer, self.sim_t) else "not_ready")

    def send_active_ping(self):
        if self._opfor is not None and self._sonar_ctx is self._opfor.station:
            return opfor.send_ping(self, self._opfor)
        if self._sonar_down():
            return "sonar_down"
        if not self.sonar.array_available(self.sonar_mode, self.ship.speed):
            return "not_ready"
        if not self.sonar.fire_ping():
            return "not_ready"
        self._remember_ping_pulse()
        self.map_fx.ping("frigate", self.sim_t, self.ship.x, self.ship.y)
        self._emit_sound("sonar_ping")
        self.sonar.queue_ping(self.ship, self._sonar_targets(), self.world,
                              self.sim_t, self._sonar_range_factor(),
                              mode=self.sonar_mode)
        return True

    def set_helicopter_dipping(self, deployed: bool):
        if type(deployed) is not bool:
            return "invalid_value"
        if self.damage.station_down("flightdeck"):
            return "flightdeck_down"
        if not self.helo.airborne:
            return "not_ready"
        if deployed and not self.helicopter_weather()["dipping_safe"]:
            return "weather_unsafe"
        if not self.helo.set_dipping(deployed, self.world):
            return "water_required" if deployed else "not_ready"
        return True

    def set_helicopter_dip_depth(self, depth_m: float):
        if (type(depth_m) not in (int, float) or isinstance(depth_m, bool)
                or not math.isfinite(depth_m)
                or not config.HELO_DIP_DEPTH_MIN_M <= depth_m
                <= config.HELO_DIP_DEPTH_MAX_M):
            return "invalid_value"
        if (not self.helo.airborne
                or self.helo.dip_state not in ("DEPLOYING", "DEPLOYED")):
            return "not_ready"
        return (True if self.helo.set_dip_depth(depth_m, self.world)
                else "water_required")

    def send_helicopter_dipping_ping(self):
        if self.damage.station_down("sonar"):
            return "sonar_down"
        if not self.helo.fire_dipping_ping():
            return "not_ready"
        self._remember_ping_pulse()
        self.map_fx.ping("frigate", self.sim_t, self.helo.x, self.helo.y)
        self._emit_sound("sonar_ping")
        self.sonar.queue_ping(self.helo, self._sonar_targets(), self.world,
                              self.sim_t, self._sonar_range_factor(),
                              mode="DIPPING")
        return True

    def set_sonar_tma_enabled(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.tma_enabled = enabled
        return True

    def set_sonar_gain(self, gain_db: float):
        if (type(gain_db) not in (int, float) or not -12 <= gain_db <= 24
                or not math.isfinite(gain_db)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.gain_db = gain_db
        return True

    def set_sonar_audition_mode(self, mode: str):
        if type(mode) is not str or mode not in ("BROADBAND", "FILTERED", "HETERODYNE"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.set_audition_mode(mode)
        return True

    def set_sonar_band_preset(self, preset: str):
        band = SONAR_BAND_PRESETS.get(preset) if type(preset) is str else None
        if band is None:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.band_low_hz, self.sonar.band_high_hz = band
        return True

    def set_sonar_notch(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.notch_enabled = enabled
        return True

    def set_sonar_peak_hold(self, enabled: bool):
        if type(enabled) is not bool:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.peak_hold = enabled
        return True

    def sonar_harmonic_candidates(self):
        return tuple(sorted({float(hz) for hz, _ in list(
            getattr(self.sonar.receiver, "peaks", []))[:6]
            if type(hz) in (int, float) and math.isfinite(hz)
            and 0 < float(hz) <= config.LOFAR_FMAX_HZ}))

    def sonar_class_library(self, limit: int = class_library.MAX_ROWS):
        """Catalog classes sorted by fit to the operator's own line marks
        (LOFAR fundamental, DEMON shaft and blade lines)."""
        signatures = self.sonar.acoustic_profiles
        if signatures is None:
            signatures = self.runtime_catalog.acoustic_profiles
        tools = self.sonar_tools
        return class_library.rank(signatures, tools.shaft_hz, tools.blade_hz,
                                  self.sonar_harmonic_hz, limit)

    def sonar_library_marks(self) -> int:
        tools = self.sonar_tools
        return class_library.marks_count(tools.shaft_hz, tools.blade_hz,
                                         self.sonar_harmonic_hz)

    def set_sonar_harmonic(self, frequency_hz):
        if self._sonar_down():
            return "sonar_down"
        if frequency_hz is None:
            self.sonar_harmonic_hz = None
            return True
        if (type(frequency_hz) not in (int, float)
                or not 0 < frequency_hz <= config.LOFAR_FMAX_HZ
                or not math.isfinite(frequency_hz)):
            return "invalid_value"
        # Any operator-chosen fundamental (the cursor), not only detected peaks.
        self.sonar_harmonic_hz = float(frequency_hz)
        return True

    def designate_sonar_target(self, contact):
        if self._sonar_down():
            return "sonar_down"
        if (not isinstance(contact, Contact)
                or self.sonar.contacts.get(contact.target_id) is not contact
                or not 0 <= self.sim_t - contact.last_seen
                < config.SONAR_CONTACT_LOST_S):
            return "stale_ref"
        self.target = contact
        return True


    # --- Display (M8): Letterbox-Scaling + Vollbild ---

    def _cycle_sonar_mode(self) -> None:
        order = SONAR_ARRAY_MODES
        self.set_sonar_array_mode(order[(order.index(self.sonar_mode) + 1) % len(order)])
        self.flash(message({"TOWED": "runtime.sonar_array.towed", "VDS": "runtime.sonar_array.vds"}
                           .get(self.sonar_mode, "runtime.sonar_array.bow")), 1.5)

    def _handle_sonar_click(self, target) -> bool:
        """Execute the sonar view's closed allowlist of non-critical actions."""
        if not isinstance(target, dict) or target.get("safe") is not True:
            return False
        action = target.get("action")
        if action == "page_set":
            value = target.get("value")
            if type(value) is not int or not 0 <= value < len(STATION_PAGES[Station.SONAR]):
                return False
            self.sonar_page = value
        elif action == "page":
            self.sonar_page = station_page_step(Station.SONAR, self.sonar_page, 1)
        elif action in ("contact", "echo", "contact_listen"):
            contact_id = target.get("value")
            contact = next((item for item in self.sonar.active_contacts()
                            if item.id == contact_id), None)
            if contact is None:
                return False
            if action == "contact_listen":
                if self.set_sonar_focus(contact) is not True:
                    return False
            else:
                self.selected_contact = contact
        elif action == "listen_bearing":
            value = target.get("value")
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value < 360):
                return False
            self.set_sonar_listen_bearing(value)
            self.flash(message("runtime.numeric.true_bearing",
                               bearing=f"{value:05.1f}"), 2.0)
        elif action == "array":
            self._cycle_sonar_mode()
        elif action == "gain":
            self._adjust_sonar_gain(3.0)
        elif action == "band_filter":
            self._cycle_sonar_band()
        elif action == "notch":
            self.set_sonar_notch(not self.sonar.notch_enabled)
            self.flash(message("runtime.notch.on" if self.sonar.notch_enabled
                               else "runtime.notch.off"), 1.5)
        elif action == "harmonic":
            self._cycle_sonar_harmonic()
        elif action == "tma_accept":
            self._accept_tma_with_notice(self._tma_contact())
        elif action == "integration":
            seconds = self.sonar_tools.cycle_integration()
            self.flash(message("runtime.integration", seconds=seconds), 1.5)
        elif action == "cursor":
            pass   # the cursor moves with Z/X; the segment is a readout
        elif action == "peak":
            self.set_sonar_peak_hold(not self.sonar.peak_hold)
            self.flash(message("runtime.peak_hold.on" if self.sonar.peak_hold
                               else "runtime.peak_hold.off"), 1.5)
        elif action == "audio":
            self.sonar_audio_enabled = not self.sonar_audio_enabled
            self._stop_sonar_audio()
            self.flash(message("runtime.sonar_audio.on" if self.sonar_audio_enabled
                               else "runtime.sonar_audio.off"))
        else:
            return False
        return True

    def _cycle_sonar_harmonic(self) -> None:
        """K: mark the line under the operator cursor (LOFAR fundamental,
        DEMON shaft then blade line); pressing again on the mark clears it."""
        page = "demon" if self.sonar_page == 2 else "lofar"
        if self.mark_sonar_cursor(page) is not True:
            return
        tools = self.sonar_tools
        if page == "demon":
            key = ("runtime.demon.blade" if tools.blade_hz is not None
                   else "runtime.demon.shaft" if tools.shaft_hz is not None
                   else "runtime.demon.cleared")
            self.flash(message(key, frequency=f"{tools.demon_cursor_hz:.1f}"), 1.5)
        elif self.sonar_harmonic_hz is None:
            self.flash(message("runtime.harmonic.cleared"), 1.5)
        else:
            self.flash(message("runtime.harmonic.selected",
                               frequency=f"{self.sonar_harmonic_hz:.1f}"), 1.5)

    def _tma_contact(self):
        contact = self.selected_contact
        if contact is None or contact.target_id not in self.sonar.contacts:
            return None
        return contact

    def _tma_points(self, contact):
        track = self.sonar._tracks.get(getattr(contact, "target_id", None))
        return list(getattr(track, "pts", ()))

    def tma_hypothesis(self, contact):
        hypothesis = self.tma_hypotheses.get(contact.target_id)
        if hypothesis is None:
            hypothesis = tma_operator.default_hypothesis(self._tma_points(contact))
        return hypothesis

    def set_tma_hypothesis(self, contact, course, speed_kn, range_nm):
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for value in (course, speed_kn, range_nm)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.tma_hypotheses[contact.target_id] = tma_operator.Hypothesis(
            float(course), float(speed_kn), float(range_nm)).clamped()
        while len(self.tma_hypotheses) > 64:
            self.tma_hypotheses.pop(next(iter(self.tma_hypotheses)))
        return True

    def tma_evaluation(self, contact):
        points = self._tma_points(contact)
        return tma_operator.evaluate(points, self.tma_hypothesis(contact))

    def accept_tma(self, contact):
        """Write the operator's hypothesis as the contact's TMA fix."""
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if self._sonar_down():
            return "sonar_down"
        points = self._tma_points(contact)
        evaluation = tma_operator.evaluate(points, self.tma_hypothesis(contact))
        if evaluation is None:
            return "not_ready"
        if evaluation["observability"] < 0.5:
            return "unobservable"
        if evaluation["fit"] < TMA_ACCEPT_MIN_FIT:
            return "poor_fit"
        hypothesis = self.tma_hypothesis(contact)
        position = tma_operator.position_at(points, hypothesis, self.sim_t)
        contact.accept_operator_tma(position, hypothesis.course,
                                    hypothesis.speed_kn, evaluation["quality"],
                                    self.sim_t)
        return True

    def copy_tma_proposal(self, contact):
        """Training aid: start the hypothesis from the automatic solver."""
        if not self.operator_assist():
            return "not_available"
        if contact is None:
            return "stale_ref"
        proposal = self.sonar.tma_proposals.get(contact.target_id)
        points = self._tma_points(contact)
        if proposal is None or not points:
            return "not_ready"
        # The proposal's position is at its newest bearing; its range from
        # that observation point seeds the hypothesis range.
        ref = points[-1]
        return self.set_tma_hypothesis(
            contact, proposal.course, proposal.speed,
            math.hypot(proposal.pos[0] - ref.fx, proposal.pos[1] - ref.fy))

    def _accept_tma_with_notice(self, contact) -> None:
        result = self.accept_tma(contact) if contact is not None else "stale_ref"
        if result is True:
            self.flash(message("runtime.tma.accepted", contact=contact.id,
                               quality=f"{contact.tma_quality:.0%}"), 2.0)
        elif result == "poor_fit":
            self.flash(message("runtime.tma.poor_fit"), 2.0)
        elif result == "unobservable":
            self.flash(message("runtime.tma.unobservable"), 2.0)
        else:
            self.flash(message("runtime.tma.not_ready"), 2.0)

    def set_tma_method(self, method: str):
        if type(method) is not str or method not in tma_operator.TMA_METHODS:
            return "invalid_value"
        self.tma_method = method
        self.flash(message("runtime.tma.method",
                           method=display_value("tma_method", method)), 1.5)
        return True

    def _cycle_tma_method(self) -> None:
        methods = tma_operator.TMA_METHODS
        current = self.tma_method if self.tma_method in methods else "hypothesis"
        self.set_tma_method(methods[(methods.index(current) + 1) % len(methods)])

    def tma_ekelund(self, contact):
        """(range_nm, uncertainty_nm) of the Ekelund method, or None."""
        if contact is None:
            return None
        return tma_operator.ekelund_range_nm(self._tma_points(contact))

    def copy_tma_ekelund(self, contact):
        """Put the Ekelund range into the hypothesis (course/speed unchanged)."""
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        estimate = self.tma_ekelund(contact)
        if estimate is None:
            return "not_ready"
        hypothesis = self.tma_hypothesis(contact)
        return self.set_tma_hypothesis(contact, hypothesis.course, hypothesis.speed_kn,
                                       estimate[0])

    def operator_assist(self) -> bool:
        """Training aids (auto peaks, blade-rate/catalog ranking, ESM IDs) on?

        The mission's realism level decides: Beginner always, Realistic
        never, Standard as the preference says."""
        level = getattr(self, "level", config.LEVEL_DEFAULT)
        if level != config.LEVEL_DEFAULT:
            return level == "beginner"
        return getattr(self.preferences, "operator_assist", "off") == "training"

    def _preferred_level(self) -> str:
        """The realism level the next mission starts with (preference)."""
        level = getattr(self.preferences, "level", config.LEVEL_DEFAULT)
        return level if level in config.LEVELS else config.LEVEL_DEFAULT

    def level_score_factor(self) -> float:
        return config.LEVEL_SCORE_FACTOR.get(self.level, 1.0)

    def set_sonar_cursor(self, page, frequency_hz):
        if page not in ("lofar", "demon"):
            return "invalid_value"
        if (type(frequency_hz) not in (int, float)
                or not math.isfinite(frequency_hz)):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        value = analysis_tools.clamp_cursor(frequency_hz, page)
        if page == "lofar":
            self.sonar_tools.lofar_cursor_hz = value
        else:
            self.sonar_tools.demon_cursor_hz = value
        return True

    def mark_sonar_cursor(self, page):
        if page not in ("lofar", "demon"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        tools = self.sonar_tools
        if page == "demon":
            tools.mark_demon(tools.demon_cursor_hz)
            return True
        cursor = tools.lofar_cursor_hz
        if (self.sonar_harmonic_hz is not None
                and abs(self.sonar_harmonic_hz - cursor) < 1e-6):
            return self.set_sonar_harmonic(None)
        return self.set_sonar_harmonic(cursor)

    def set_sonar_integration(self, seconds):
        if type(seconds) is not int or seconds not in analysis_tools.INTEGRATION_CHOICES_S:
            return "invalid_value"
        self.sonar_tools.integration_s = seconds
        return True

    def set_sonar_vernier(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        self.sonar_tools.vernier = enabled
        return True

    def set_sonar_band(self, low_hz, high_hz):
        """Free band-pass edges (low 0 = low-pass, high 300 = high-pass)."""
        if (any(type(value) not in (int, float) or not math.isfinite(value)
                for value in (low_hz, high_hz))
                or not 0.0 <= low_hz < high_hz <= config.LOFAR_FMAX_HZ):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.band_low_hz, self.sonar.band_high_hz = float(low_hz), float(high_hz)
        return True

    def set_tas_side(self, contact, action: str):
        """Operator decision on a towed-only contact's array side.

        ``flip`` shows the other side (and reopens a confirmed choice);
        ``confirm`` commits the shown side. Nothing is decided automatically.
        """
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if action not in ("flip", "confirm"):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        if action == "flip":
            if not contact.towed_ambiguous:
                if not contact.towed_resolved:
                    return "not_ambiguous"
                contact.towed_ambiguous, contact.towed_resolved = True, False
                contact.ambiguity_axis = self.sonar.tow_heading_deg
            contact.towed_side = "PORT" if contact.towed_side == "STBD" else "STBD"
            return True
        if not contact.towed_ambiguous:
            return "not_ambiguous"
        contact.towed_ambiguous, contact.towed_resolved = False, True
        contact.mirror_bearing = contact.ambiguity_axis = None
        return True

    def set_sonar_demon_band(self, low_hz, high_hz):
        if (low_hz, high_hz) not in analysis_tools.DEMON_BANDS_HZ:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.receiver.demon_band_hz = (float(low_hz), float(high_hz))
        return True

    def set_sonar_heterodyne(self, frequency_hz):
        if frequency_hz not in analysis_tools.HETERODYNE_OFFSETS_HZ:
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.heterodyne_hz = float(frequency_hz)
        return True

    def set_sonar_operator_notch(self, frequency_hz):
        if frequency_hz is not None and (
                type(frequency_hz) not in (int, float) or not math.isfinite(frequency_hz)
                or not 0.0 < frequency_hz <= config.LOFAR_FMAX_HZ):
            return "invalid_value"
        if self._sonar_down():
            return "sonar_down"
        self.sonar.operator_notch_hz = (None if frequency_hz is None
                                        else float(frequency_hz))
        return True

    def _adjust_sonar_gain(self, delta: float) -> None:
        self.set_sonar_gain(config.clamp(self.sonar.gain_db + delta, -12.0, 24.0))
        self.flash(message("runtime.sonar_gain", gain=f"{self.sonar.gain_db:+.0f}"), 1.2)

    def _cycle_sonar_display_palette(self) -> None:
        palettes = ("green", "amber", "cyan")
        current = (palettes.index(self.sonar_display_palette)
                   if self.sonar_display_palette in palettes else -1)
        self.sonar_display_palette = palettes[(current + 1) % len(palettes)]
        self.flash(message("runtime.sonar_palette",
                           palette=self.sonar_display_palette.upper()), 1.2)

    def _adjust_sonar_display_contrast(self, delta: float) -> None:
        self.sonar_display_contrast = round(config.clamp(
            self.sonar_display_contrast + delta, .5, 4.0), 1)
        self.flash(message("runtime.sonar_contrast",
                           contrast=f"{self.sonar_display_contrast:.1f}"), 1.2)

    def _adjust_sonar_display_black(self, delta: float) -> None:
        self.sonar_display_black = round(config.clamp(
            self.sonar_display_black + delta, 0.0, .8), 2)
        self.flash(message("runtime.sonar_black_level",
                           level=f"{self.sonar_display_black:.2f}"), 1.2)

    def _cycle_sonar_display_history(self) -> None:
        depths = (.25, .5, 1.0)
        current = next((index for index, value in enumerate(depths)
                        if abs(self.sonar_display_history - value) < 1e-6), -1)
        self.sonar_display_history = depths[(current + 1) % len(depths)]
        self.flash(message("runtime.sonar_history",
                           history=f"{self.sonar_display_history:.0%}"), 1.2)

    def _set_sonar_audition_mode(self, mode: str) -> None:
        if self.set_sonar_audition_mode(mode) is not True:
            return
        key = {"BROADBAND": "runtime.listen.broadband",
               "FILTERED": "runtime.listen.filtered",
               "HETERODYNE": "runtime.listen.heterodyne"}[mode]
        self.flash(message(key), 1.2)

    def sonar_audio_status(self) -> dict:
        status = self.audio.availability_status()
        locally_ready = (self.station is Station.SONAR and self.sonar_audio_enabled
                         and not self.damage.station_down("sonar"))
        return dict(status, local_enabled=bool(self.sonar_audio_enabled),
                    mode=self.sonar.audition_mode, gain_db=self.sonar.gain_db,
                    band_hz=[self.sonar.band_low_hz, self.sonar.band_high_hz],
                    notch=bool(self.sonar.notch_enabled), volume=self.sonar_volume,
                    stale=bool(self.audio.sonar_stale),
                    audible=bool(status["global_enabled"]
                                 and status["device_available"] and locally_ready))

    def _cycle_sonar_band(self) -> None:
        bands = tuple(SONAR_BAND_PRESETS.values())
        current = (self.sonar.band_low_hz, self.sonar.band_high_hz)
        try:
            index = bands.index(current)
        except ValueError:
            index = 0
        low, high = bands[(index + 1) % len(bands)]
        preset = next(key for key, value in SONAR_BAND_PRESETS.items()
                      if value == (low, high))
        self.set_sonar_band_preset(preset)
        self.flash(message("runtime.sonar_band", low=f"{low:.0f}",
                           high=f"{high:.0f}"), 1.5)

    def toggle_radar(self, domain: str = "surface") -> None:
        enabled = not (self.air_radar_on if domain == "air"
                       else self.surface_radar_on)
        if self.set_opz_radar(domain, enabled) is not True:
            self.flash(message("runtime.opz.disabled"))
            return
        if domain == "air":
            radar, active = "air", self.air_radar_on
        else:
            radar, active = "surface", self.surface_radar_on
        suffix = "on" if active else "off"
        self.hq_msg(message(f"runtime.emcon.{radar}.{suffix}.hq"))
        self.flash(message(f"runtime.emcon.{radar}.{suffix}"), 2.0)

    def set_opz_radar(self, domain: str, enabled: bool):
        """Set one OPZ radar from a validated local or remote station action."""
        if self.damage.station_down("opz"):
            return "opz_down"
        if domain not in ("surface", "air") or type(enabled) is not bool:
            return "invalid_value"
        setattr(self, f"{domain}_radar_on", enabled)
        return True

    def set_opz_range(self, range_nm: float):
        if self.damage.station_down("opz"):
            return "opz_down"
        if type(range_nm) not in (int, float) or range_nm not in config.RADAR_RANGE_SCALES_NM:
            return "invalid_value"
        self.opz_range_nm = float(range_nm)
        return True

    def _cycle_lookout_range(self, delta: int) -> None:
        """Bridge lookout page: step the display scale (presentation only)."""
        scales = config.LOOKOUT_DISPLAY_RANGES_NM
        current = getattr(self, "lookout_range_nm", 12.0)
        index = min(range(len(scales)), key=lambda i: abs(scales[i] - current))
        self.lookout_range_nm = scales[max(0, min(len(scales) - 1, index + delta))]
        self.flash(message("runtime.lookout.range", range=f"{self.lookout_range_nm:.0f}"), 1.5)

    def lookout_glasses_shown(self) -> bool:
        """The bridge lookout's binoculars cover the chart (display only)."""
        return (bool(getattr(self, "lookout_glasses", False))
                and self.station is Station.BRIDGE and self.station_page == 2)

    def _toggle_lookout_glasses(self) -> None:
        self.lookout_glasses = not self.lookout_glasses
        self._map_drag = None
        self.flash(message("runtime.lookout.glasses_on" if self.lookout_glasses
                           else "runtime.lookout.glasses_off"), 1.5)

    def _train_lookout_glasses(self, delta_deg: float) -> None:
        """Train the binoculars relative to the bow (presentation only)."""
        self.lookout_glasses_rel = (self.lookout_glasses_rel + delta_deg) % 360.0

    def _lookout_optics_key(self, event) -> bool:
        """Tilt, zoom or stabilize the raised binoculars; True if the key was
        theirs (presentation only)."""
        return optics_key(self, self.lookout_optics, event.key, getattr(event, "mod", 0))

    def _train_lookout_glasses_to(self, bearing: float) -> None:
        self.lookout_glasses_rel = (bearing - self.ship.course) % 360.0

    def lookout_sightings(self) -> list:
        """Current bridge-lookout tracks (measured bearing/range, visual label)."""
        return [track for track in self.air_picture.tracks(self.sim_t)
                if track.source == "LOOKOUT" and track.x is not None and track.y is not None]

    def _cycle_radar_range(self, delta: int) -> None:
        scales = config.RADAR_RANGE_SCALES_NM
        try:
            index = scales.index(float(self.opz_range_nm))
        except ValueError:
            index = len(scales) - 1
        index = max(0, min(len(scales) - 1, index + delta))
        if self.set_opz_range(scales[index]) is not True:
            return
        self.flash(message("runtime.radar.range", range=f"{self.opz_range_nm:.0f}"), 1.5)

    def radar_blip_view(self) -> list:
        """Unmarked radar blips still glowing (measured positions only)."""
        if not (self.surface_radar_on and not self.damage.station_down("opz")):
            return []
        return [blip for blip in self.radar_blips
                if 0.0 <= self.sim_t - blip["t"] < config.RADAR_BLIP_LIFE_S
                and blip["target"] not in self._radar_marked]

    def mark_radar_blip(self, seq):
        """OPZ: start a radar track from a blip (its measurement only)."""
        if type(seq) is not int:
            return "invalid_value"
        blip = next((item for item in self.radar_blip_view() if item["seq"] == seq), None)
        if blip is None:
            return "stale_ref"
        track_id = f"R-{blip['seq']}"
        self._observe_mast(track_id, blip["target"], blip["bearing"], blip["range_nm"],
                           blip["observer_x"], blip["observer_y"], blip["error"])
        self.announce(message("runtime.opz.blip_marked", track=track_id), "opz", 2.0)
        return True

    def _mark_newest_blip(self) -> None:
        blips = self.radar_blip_view()
        if not blips:
            self.flash(message("runtime.opz.no_blip"), 1.5)
            return
        self.mark_radar_blip(blips[-1]["seq"])

    def radar_sweep_bearing(self) -> float:
        """Nautische Peilung: zunehmende Werte drehen Nord -> Ost rechtsherum."""
        return self.radar_scan_phase

    def toggle_helo(self) -> None:
        if self.helo.airborne:
            if self.return_helicopter() is True:
                self.announce(message("runtime.helo.return"), "waffen")
        elif self.helo.preparing:
            if self.return_helicopter() is True:
                self.announce(message("runtime.helo.prep_cancelled"), "waffen")
        else:
            result = self.launch_helicopter()
            if result == "flightdeck_down":
                self.flash(message("runtime.helo.deck_down"))
                return
            if result == "weather_unsafe":
                self.flash(message("runtime.helo.weather_unsafe"))
                return
            if result is not True:
                self.flash(message("runtime.helo.lost"))
                return
            self.announce(message("runtime.helo.prep",
                                  minutes=f"{config.HELO_PREP_S / 60:.0f}"), "waffen", 3.0)

    def launch_helicopter(self):
        """Order the launch: the deck prepares the helicopter in the hangar
        for ``HELO_PREP_S``; it lifts off at the next deck window after that
        (``_launch_prepared_helicopter``). An order already running stands."""
        if self.damage.station_down("flightdeck"):
            return "flightdeck_down"
        if self.helo.state != "HANGAR":
            return "not_ready"
        if self.helo.preparing:
            return True
        if self.helicopter_weather()["status"] == "no_go":
            return "weather_unsafe"
        self.helo.order_prep()
        return True

    def _launch_prepared_helicopter(self) -> None:
        """Lift off once prepared, with the flight deck up and the weather
        and deck motion inside the launch limits; until then it waits."""
        if (not self.helo.prep_ready or self.damage.station_down("flightdeck")
                or not self.helicopter_weather()["launch_safe"]):
            return
        self.helo.launch(self.ship)
        self.announce(message("runtime.helo.launch", torpedoes=self.helo.torps,
                              buoys=self.helo.buoys_left), "waffen", 3.0)

    def return_helicopter(self):
        """Recall the helicopter, or stop its start preparation."""
        if self.helo.cancel_prep():
            return True
        if not self.helo.airborne:
            return "not_ready"
        self.helo.order_return()
        return True

    def set_helicopter_waypoint(self, x: float, y: float):
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not 0 <= x <= self.world.size_nm
                or not 0 <= y <= self.world.size_nm
                or not math.isfinite(x) or not math.isfinite(y)):
            return "invalid_value"
        if self.helo.state == "VERLOREN":
            return "not_ready"
        self.helo.set_waypoint(x, y)
        return True

    def helicopter_waypoint_to_selection(self):
        """Waypoint on the selected contact's plotted position (W, as the
        patrol aircraft's W); a bearing-only contact has no position."""
        from src.ui import observations
        contact = self.selected_contact
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "no_contact"
        x, y = observations.position(contact)
        if x is None or y is None:
            return "not_located"
        size = float(self.world.size_nm)
        return self.set_helicopter_waypoint(config.clamp(float(x), 0.0, size),
                                            config.clamp(float(y), 0.0, size))

    def _helo_waypoint_feedback(self, result) -> None:
        if result is True:
            bearing, distance = self._helo_waypoint_polar()
            self.flash(message("runtime.helo.waypoint", bearing=f"{bearing:03.0f}",
                               range=f"{distance:.1f}"), 1.5)
        elif result == "no_contact":
            self.flash(message("runtime.contact.none_selected"))
        elif result == "not_located":
            self.flash(message("mpa.refused.not_located"), 2.0)
        else:
            self.flash(message("runtime.helo.not_airborne"))

    def _helo_waypoint_polar(self) -> tuple[float, float]:
        if self.helo.waypoint_x is None or self.helo.waypoint_y is None:
            return self.ship.course, 2.0
        dx = self.helo.waypoint_x - self.ship.x
        dy = self.helo.waypoint_y - self.ship.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy)

    def _adjust_helo_waypoint(self, bearing_delta: float = 0.0,
                              range_delta: float = 0.0) -> None:
        bearing, distance = self._helo_waypoint_polar()
        bearing = (bearing + bearing_delta) % 360.0
        distance = config.clamp(distance + range_delta, 1.0, 30.0)
        self.helo.set_waypoint(
            self.ship.x + distance * math.sin(math.radians(bearing)),
            self.ship.y - distance * math.cos(math.radians(bearing)))
        self.flash(message("runtime.helo.waypoint", bearing=f"{bearing:03.0f}",
                           range=f"{distance:.1f}"), 1.5)

    def deploy_buoys(self) -> None:
        result = self.deploy_helicopter_buoy()
        if result == "not_ready":
            self.flash(message("runtime.helo.not_airborne"))
            return
        if result == "water_required":
            self.flash(message("runtime.helo.water_required"))
            return
        if result is True:
            buoy = self.buoys[-1]
            self.flash(message("runtime.buoy.deployed", buoy=buoy.seq))
            self.feed.add(self.world.format_time(), "sonar",
                          message("runtime.buoy.active", buoy=buoy.seq))
        else:
            self.flash(message("event.no_buoys"))

    def deploy_helicopter_buoy(self):
        if not self.helo.airborne:
            return "not_ready"
        if not self.helo.water_entry_clear(self.world):
            return "water_required"
        if self.helo.buoys_left <= 0:
            return "no_buoys"
        next_sequence = self.buoy_seq + 1
        buoy = self.helo.deploy_buoy(next_sequence, world=self.world,
                                    mode=getattr(self, "helo_buoy_mode", "PASSIVE"))
        if buoy is None:
            return "not_ready"
        self.buoy_seq = next_sequence
        self.buoys.append(buoy)
        boat_threat.record_splash(self, buoy.x, buoy.y, buoy.seq)
        if buoy.mode == "PASSIVE" and not self.helicopter_audio_ready():
            self.set_helicopter_listen_source(f"SB{buoy.seq}")
        return True

    def set_helicopter_pattern(self, kind: str):
        """Plan a buoy pattern about the current waypoint (single clears it)."""
        if type(kind) is not str or kind not in helicopter_physics.BUOY_PATTERNS:
            return "invalid_value"
        helo = self.helo
        if kind == "single":
            helo.pattern_queue = []
            helo.pattern = "single"
            self.flash(message("runtime.helo.pattern_cleared"), 1.5)
            return True
        if helo.state != "AUF":
            return "not_ready"
        if helo.buoys_left <= 0:
            return "no_buoys"
        bearing, distance = self._helo_waypoint_polar()
        centre_x = self.ship.x + distance * math.sin(math.radians(bearing))
        centre_y = self.ship.y - distance * math.cos(math.radians(bearing))
        points = helicopter_physics.plan_buoy_pattern(kind, centre_x, centre_y, bearing,
                                                      helo.buoys_left)
        size = float(self.world.size_nm)
        points = [(config.clamp(x, 0.0, size), config.clamp(y, 0.0, size)) for x, y in points]
        if not points:
            return "invalid_value"
        helo.pattern = kind
        helo.pattern_queue = points
        helo.set_waypoint(*points[0])
        self.flash(message("runtime.helo.pattern", pattern=display_value("buoy_pattern", kind),
                           count=len(points)), 2.0)
        return True

    def _cycle_helicopter_pattern(self) -> None:
        kinds = helicopter_physics.BUOY_PATTERNS
        current = self.helo.pattern if self.helo.pattern_queue else "single"
        self.set_helicopter_pattern(kinds[(kinds.index(current) + 1) % len(kinds)])

    def set_helicopter_mad(self, enabled: bool):
        """Start or end the MAD run (low and slow, dipping sonar stowed)."""
        if type(enabled) is not bool:
            return "invalid_value"
        helo = self.helo
        if not enabled:
            helo.mad_mode = False
            self.flash(message("runtime.helo.mad_off"), 1.5)
            return True
        if helo.state != "AUF":
            return "not_ready"
        if helo.dip_state != "STOWED":
            return "dip_deployed"
        helo.mad_mode = True
        self.flash(message("runtime.helo.mad_on"), 2.0)
        return True

    def set_helicopter_buoy_mode(self, mode: str):
        if mode not in ("PASSIVE", "ACTIVE") or type(mode) is not str:
            return "invalid_value"
        self.helo_buoy_mode = mode
        return True

    def set_helicopter_listen_source(self, source: str):
        if source != "DIP":
            if (type(source) is not str or not source.startswith("SB")
                    or not source[2:].isdigit() or len(source) > 5):
                return "invalid_value"
            seq = int(source[2:])
            if not any(b.seq == seq and b.active for b in self.buoys):
                return "stale_ref"
        if source != self.helo_listen_source:
            self.helo_listen_source = source
            self.helo_receiver.reset()
            self.helo_audition.reset_audition_audio()
            self.helo_spectra.clear()
            self.helo_broadband_history.clear()
            self.helo_demon_history.clear()
            self._helo_receiver_timer = 0.0
        return True

    def set_helicopter_listen_bearing(self, bearing):
        if bearing is not None and (type(bearing) not in (int, float)
                                    or not math.isfinite(bearing)
                                    or not 0 <= bearing < 360):
            return "invalid_value"
        self.helo_listen_bearing = bearing
        return True

    def set_helicopter_audio_mode(self, mode: str):
        if type(mode) is not str or not self.helo_audition.set_audition_mode(mode):
            return "invalid_value"
        return True

    def set_helicopter_audio_band(self, preset: str):
        band = SONAR_BAND_PRESETS.get(preset) if type(preset) is str else None
        if band is None:
            return "invalid_value"
        self.helo_audition.band_low_hz, self.helo_audition.band_high_hz = band
        self.helo_audio_band = preset
        return True

    def set_helicopter_audio_gain(self, gain_db):
        if type(gain_db) not in (int, float) or not math.isfinite(gain_db) \
                or not -12 <= gain_db <= 24:
            return "invalid_value"
        self.helo_audition.gain_db = float(gain_db)
        return True

    def set_helicopter_audio_notch(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        self.helo_audition.notch_enabled = enabled
        return True

    def helicopter_audio_ready(self) -> bool:
        """The selected helicopter hydrophone must be in the water."""
        source = self.helo_listen_source
        if source == "DIP":
            return self.helo.dip_available and self.helo.dip_depth_m > 0.0
        if not source.startswith("SB") or not source[2:].isdigit():
            return False
        seq = int(source[2:])
        return any(b.seq == seq and b.active and b.mode == "PASSIVE"
                   for b in self.buoys)

    # --- Update ---

    def hq_msg(self, text: object) -> None:
        """M13/W3: Teletype-Nachricht – Funkraum-Verkehr + Ereignis-Feed."""
        stamp = self.world.format_time()
        self.messages.append((stamp, text))
        if len(self.messages) > 40:
            self.messages.pop(0)
        self.feed.add(stamp, "funk", text)
        # With the optional language model, the radio room also gets the
        # message worded like real traffic (display only, src/llm/radio.py).
        self.llm_radio_offer(stamp, text)

    def assign_contact_profile(self, contact, profile_key):
        """Operator annotation: this contact matches that catalog profile."""
        if contact is None or contact.target_id not in self.sonar.contacts:
            return "stale_ref"
        if profile_key is not None and (
                type(profile_key) is not str
                or profile_key not in self.runtime_catalog.profile_systems):
            return "invalid_value"
        contact.player_profile = profile_key
        if profile_key is None:
            notice = message("runtime.profile.cleared",
                             contact=self.contact_display_id(contact))
        else:
            notice = message("runtime.profile.assigned",
                             contact=self.contact_display_id(contact),
                             profile=raw_text(self.profile_name(profile_key)))
        self._sonar_notice(notice, 2.0)
        return True

    def profile_name(self, key):
        """Display name of a catalog profile (as listed in the analyser)."""
        if key is None:
            return None
        names = self.__dict__.get("_profile_names")
        if names is None:
            from src.data.contact_analysis import project_contact_catalog
            names = {row["key"]: str(row["name"])
                     for row in project_contact_catalog()["profiles"]}
            self._profile_names = names
        return names.get(key, key)

    def _make_analyzer(self, fits=None) -> ContactAnalyzer:
        """Read-only Kontakt-Katalog-Browser (Menue und In-Game, F8)."""
        return ContactAnalyzer(
            tr=self.tr, on_play_sample=self._play_unit_audio,
            on_stop_sample=self.audio.stop_preview,
            preview_active=self.audio.preview_playing, fits=fits)

    def _library_fits(self) -> dict:
        """F8 in a mission: every class's fit to the operator's line marks."""
        return {signature.key: fit for signature, fit in self.sonar_class_library(limit=1000)}

    def _open_analyzer_in_game(self) -> None:
        """TUA im laufenden Spiel: Simulation laeuft weiter, Esc kehrt ins Spiel zurueck.

        With a sonar contact selected, Enter assigns the browsed profile to
        it (the operator's catalog comparison result)."""
        self._clear_controls()
        contact = self.selected_contact
        fits = self._library_fits()
        if contact is None or contact.target_id not in self.sonar.contacts:
            self.editor = self._make_analyzer(fits)
            return
        analyzer = self._make_analyzer(fits)
        analyzer.on_assign = lambda key: self.assign_contact_profile(contact, key)
        analyzer.assign_label = self.contact_display_id(contact)
        analyzer.current_assignment = lambda: self.profile_name(contact.player_profile)
        self.editor = analyzer

    def _open_simlog_view(self) -> None:
        """F4: Live-Protokoll-Ansicht; nur bei aktiver simlog-Option."""
        if not self.preferences.simlog:
            self.flash(message("simlog.view_disabled"), 2.0)
            return
        self._clear_station_input()
        self.simlog_view_open = True
        self.simlog_view_scroll = 0
        self.simlog_view_map = False

    def _close_simlog_view(self) -> None:
        self.simlog_view_open = False
        self.simlog_view_scroll = 0
        self.simlog_view_map = False
        self._clear_station_input()

    def _scroll_simlog_view(self, amount: int) -> None:
        self.simlog_view_scroll = max(0, self.simlog_view_scroll + amount)

    def capture_hfdf(self) -> None:
        reports = self.hfdf_bearings()
        if not reports:
            self.flash(message("runtime.hfdf.none"))
            return
        report = reports[min(self.radio_sel, len(reports) - 1)]
        self.capture_hfdf_report(report)

    def capture_hfdf_report(self, report):
        if self.damage.station_down("radio"):
            return "radio_down"
        if not any(item is report for item in self.hfdf_bearings()):
            return "stale_ref"
        if report.age(self.sim_t) > config.RADAR_TRACK_STALE_S:
            self.flash(message("runtime.hfdf.stale"))
            return "stale_ref"
        measurement = (report.measurement_history[-1]
                       if report.measurement_history else {})
        display_id = self.hfdf_display_id(report)
        row = dict(track_id=report.track_id, label=display_id,
                   bearing=measurement.get("bearing", report.bearing),
                   observer_x=measurement.get("observer_x", self.ship.x),
                   observer_y=measurement.get("observer_y", self.ship.y),
                   t=measurement.get("t", report.last_seen))
        self.hfdf_log.append(row)
        self.hfdf_log = self.hfdf_log[-20:]
        previous = next((item for item in reversed(self.hfdf_log[:-1])
                          if item["track_id"] == report.track_id
                          and 0 < row["t"] - item["t"] <= 300.0
                         and math.hypot(item["observer_x"] - row["observer_x"],
                                        item["observer_y"] - row["observer_y"]) >= 1.0), None)
        if previous is None:
            self.announce(message("runtime.hfdf.logged", label=display_id,
                                  bearing=f"{report.bearing:05.1f}"), "funk")
            return True
        fix = self._bearing_intersection(previous, row)
        if fix is None:
            self.announce(message("runtime.hfdf.geometry"), "funk")
            return True
        x, y, geometry = fix
        # Angular errors projected at the two measurement origins. This assumes
        # a stationary emitter throughout the bounded observation span.
        b1, b2 = math.radians(previous["bearing"]), math.radians(row["bearing"])
        # Sky-wave intercepts carry the larger ionospheric-tilt uncertainty.
        sigma_rad = math.radians(report.bearing_uncertainty_deg
                                 or config.HFDF_BEARING_ERR_DEG / math.sqrt(3.0))
        v1 = sigma_rad ** 2 * ((x - previous["observer_x"]) ** 2
                              + (y - previous["observer_y"]) ** 2)
        v2 = sigma_rad ** 2 * ((x - row["observer_x"]) ** 2
                              + (y - row["observer_y"]) ** 2)
        xx = (math.sin(b2) ** 2 * v1 + math.sin(b1) ** 2 * v2) / geometry ** 2
        yy = (math.cos(b2) ** 2 * v1 + math.cos(b1) ** 2 * v2) / geometry ** 2
        xy = -(math.sin(b2) * math.cos(b2) * v1
               + math.sin(b1) * math.cos(b1) * v2) / geometry ** 2
        self.hfdf_fixes[report.track_id] = dict(
            label=display_id, x=x, y=y,
            sigma_nm=math.sqrt(max(0.0, (xx + yy + math.hypot(xx - yy, 2 * xy)) / 2)),
            covariance_nm2=(xx, xy, yy),
            t=row["t"])
        dist = math.hypot(x - row["observer_x"], y - row["observer_y"])
        bearing = math.degrees(math.atan2(
            x - row["observer_x"], -(y - row["observer_y"]))) % 360.0
        self.air_picture.observe(
            track_id=f"H-{report.target_id}", kind="UNKNOWN",
            target_id=report.target_id, source="HFDF-FIX", bearing=bearing,
            range_nm=dist, observer_x=row["observer_x"],
            observer_y=row["observer_y"],
            course=None, quality=max(.25, geometry), now=row["t"],
            label=display_id)
        self.flash(message("runtime.hfdf.fix", label=display_id), 3.0)
        self.feed.add(self.world.format_time(), "funk",
                      message("runtime.hfdf.feed", label=display_id))
        return True

    def _cycle_hfdf(self, delta: int) -> None:
        reports = self.hfdf_bearings()
        self.radio_sel = 0 if not reports else (self.radio_sel + delta) % len(reports)

    @staticmethod
    def _bearing_intersection(first: dict, second: dict):
        """Intersect two nautical bearing rays; return None for weak geometry."""
        b1, b2 = math.radians(first["bearing"]), math.radians(second["bearing"])
        r = (math.sin(b1), -math.cos(b1))
        s = (math.sin(b2), -math.cos(b2))
        denom = r[0] * s[1] - r[1] * s[0]
        if abs(denom) < math.sin(math.radians(12.0)):
            return None
        qx, qy = second["observer_x"] - first["observer_x"], \
            second["observer_y"] - first["observer_y"]
        along_first = (qx * s[1] - qy * s[0]) / denom
        along_second = (qx * r[1] - qy * r[0]) / denom
        if along_first < 0.0 or along_second < 0.0:
            return None
        return (first["observer_x"] + along_first * r[0],
                first["observer_y"] + along_first * r[1], abs(denom))

    def hfdf_bearings(self) -> list:
        """Current and recently retained HFDF observations."""
        return self.radio_picture.tracks(self.sim_t, ("HF",))

    def hfdf_display_id(self, report) -> str:
        """Return the stable public identifier for an HFDF observation."""
        track_id = report if isinstance(report, str) else report.track_id
        return "H-" + self._observation_key("hfdf-display", track_id)[-6:]
