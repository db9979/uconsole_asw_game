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
from src.physics import torpedo_dyn
from src.air import helicopter as helicopter_physics
from src.core.station import Station
from src.core import opfor
from src.core.optics import optics_key
from src.core.limits import MAX_DECOYS
from src.sonar import analysis_tools
from src.sonar import class_library
from src.sonar import tma_operator
from src.enemies.decoy import Decoy
from src.sonar.sonar import SONAR_ARRAY_MODES, Contact, TowState
from src.ui.contact_analyzer import ContactAnalyzer
from src.air.asm import ESSM
from src.air import chaff as chaff_physics
from src.weapons.torpedo import Torpedo
from src.weapons.asw import MAX_TOWED_DECOYS, TowedAcousticDecoy
# Shared display/help constants and helpers (re-exported for tests/tools).
from src.core.game_shared import SONAR_BAND_PRESETS, TMA_ACCEPT_MIN_FIT
from src.sensors.fusion import live_members
# Names tests and tools import from ``src.core.game`` (kept as re-exports).


class OperatorMixin:
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

    def _feed_ping(self, tgt, contact) -> None:
        """W1/W2: Ping-Echo-Feed inkl. Echolatenz (W3: Salzwasser-Schallfeld)."""
        dist = tgt.distance_nm(self.ship)
        mx, my = (self.ship.x + tgt.x) * .5, (self.ship.y + tgt.y) * .5
        latenz = self.world.echo_delay_s(dist, mx, my)
        klass = {"diesel_alt": "Diesel", "aip_modern": "AIP",
                 "ssn": "Nuclear propulsion?"}.get(
            getattr(tgt, "stype", None) and tgt.stype.key or "",
            "unknown") if getattr(tgt, "stype", None) else \
            ("Decoy?" if getattr(tgt, "kind", "") == "decoy"
             else ("biological" if hasattr(tgt, "atype") else "vessel"))
        self.feed.add(self.world.format_time(), "sonar",
                      message("runtime.ping.feed", contact=tgt.id,
                              bearing=f"{contact.bearing:4.0f}",
                              range=f"{contact.range_est:4.1f}",
                              latency=f"{latenz:3.1f}",
                              speed=f"{self.world.mean_sound_speed_m_s(mx, my):.0f}",
                              classification=klass))

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
        else:
            result = self.launch_helicopter()
            if result == "flightdeck_down":
                self.flash(message("runtime.helo.deck_down"))
                return
            if result == "weather_unsafe":
                flight = self.helicopter_weather()
                if flight["status"] != "no_go" and not flight["deck_safe"]:
                    # Only the deck moves too much: wait for the next lull.
                    self.flash(message("runtime.helo.deck_motion"))
                else:
                    self.flash(message("runtime.helo.weather_unsafe"))
                return
            if result is not True:
                self.flash(message("runtime.helo.lost"))
                return
            self.announce(message("runtime.helo.launch", torpedoes=self.helo.torps,
                                  buoys=self.helo.buoys_left), "waffen", 3.0)

    def launch_helicopter(self):
        if self.damage.station_down("flightdeck"):
            return "flightdeck_down"
        if not self.helicopter_weather()["launch_safe"]:
            return "weather_unsafe"
        if self.helo.state != "HANGAR":
            return "not_ready"
        self.helo.launch(self.ship)
        return True

    def return_helicopter(self):
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
                           range=f"{distance:.0f}"), 1.5)

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

    def launch_helo_torpedo(self) -> None:
        """Leichttorpedo vom HSP-5 (eigene Munition, nicht Fregatten-Rohre)."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_helicopter_torpedo_at(self.target, self.torpedo_depth)

    def launch_helicopter_torpedo_at(self, contact, depth_m: float):
        """Release a helicopter torpedo against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.weapons_tight():
            self.flash(message("runtime.roe.weapons_tight"))
            return "roe_blocked"
        if self.roe == "STD" and not self._contact_range_fresh(contact):
            self.flash(message("runtime.target.not_located"))
            return "not_located"
        if self.weapon_classification(contact) != "U_BOOT":
            self.flash(message("runtime.target.air_class"))
            return "not_classified"
        if not self.helo.airborne:
            self.flash(message("runtime.helo.not_airborne"))
            return "not_ready"
        if self.helo.torps <= 0:
            self.flash(message("runtime.helo_no_torpedoes"))
            return "empty"
        if not self.helo.water_entry_clear(self.world):
            self.flash(message("runtime.helo.water_required"))
            return "water_required"
        tgt = self._find_target(contact.target_id)
        lv = self.difficulty
        range_nm = (contact.range_est if contact.range_est is not None
                    else config.ROE_FREE_LAUNCH_RANGE_NM)
        use_fix = (self._contact_range_fresh(contact)
                   and contact.observed_x is not None
                   and contact.observed_y is not None)
        datum = self.helo.release_datum_from_ship_observation(
            self.ship, contact.bearing, range_nm,
            bearing_uncertainty_deg=max(0.0, (1.0 - contact.quality) * 8.0),
            range_uncertainty_nm=contact.range_sigma_nm or 0.0,
            datum_x=contact.observed_x if use_fix else None,
            datum_y=contact.observed_y if use_fix else None)
        torp = self.helo.drop_torpedo(
            tgt, depth_m, self.torpedo_seq + 1,
            kill_dist_nm=lv["kill_dist_nm"], kill_depth_m=lv["kill_depth_m"],
            guidance_x=datum.x_nm, guidance_y=datum.y_nm, world=self.world)
        if torp is None:
            return "not_ready"
        self.torpedo_seq += 1
        self.torpedoes.append(torp)
        self._emit_sound("water_entry")
        self.flash(message("runtime.helo_torpedo.launched",
                           torpedo=self.torpedo_seq), 2.0)
        self.feed.add(self.world.format_time(), "waffen",
                      message("runtime.helo_torpedo.feed",
                              torpedo=self.torpedo_seq, contact=contact.id))
        return True

    @staticmethod
    def _missile_seq(track):
        """Internal missile sequence behind an ``M-`` air track, else None.

        An ASM cue can also sit on an aircraft track; fire control resolves
        the engaged weapon only through the missile's own track namespace.
        """
        track_id = str(getattr(track, "track_id", ""))
        suffix = track_id[2:]
        return int(suffix) if track_id.startswith("M-") and suffix.isdigit() else None

    def _cycle_asm_track(self, delta: int) -> None:
        n = len(self.asm_tracks())
        if n == 0:
            self.asm_sel = 0
            return
        self.asm_sel = (self.asm_sel + delta) % n

    def launch_essm(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_essm_at(track)

    def launch_essm_at(self, track):
        """Launch against an explicit current positioned ASM observation."""
        profiles = self._air_defense_loadout
        if self.damage.station_down("opz") or self.damage.station_degraded("opz"):
            self.flash(message("runtime.opz.degraded"))
            return "opz_degraded"
        if self.vls_cells <= 0:
            self.flash(message("runtime.vls.empty"))
            return "empty"
        if len(self.essms) >= profiles["vls"]["fire_channels"]:
            self.flash(message("runtime.vls.empty"))
            return "active_limit"
        if not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.asm.none"))
            return "invalid_target"
        sam = profiles["sam"]
        if track.range_nm is None or track.range_nm > sam["range_nm"]:
            self.flash(message("runtime.asm.range", range=f"{sam['range_nm']:.0f}"))
            return "out_of_range"
        if (track.x is None or track.y is None or track.position_seen is None
                or self.sim_t - track.position_seen
                > sam["observation_max_age_s"]):
            self.flash(message("runtime.asm.stale"))
            return "stale_ref"
        missile_seq = self._missile_seq(track)
        tgt = next((a for a in self.asms if a.seq == missile_seq), None)
        course = math.degrees(math.atan2(track.x - self.ship.x,
                                        -(track.y - self.ship.y))) % 360.0
        self.essm_seq += 1
        self.essms.append(ESSM(self.ship.x, self.ship.y, course, tgt,
                               self.essm_seq,
                               guidance_x=track.x, guidance_y=track.y,
                               target_id=missile_seq, profile=sam))
        self.vls_cells -= 1
        self._emit_sound("missile_launch")
        self.announce(message("runtime.essm.launched", cells=self.vls_cells),
                      "waffen", 2.0)
        return True

    def launch_chaff(self) -> None:
        tracks = self.asm_tracks()
        track = tracks[min(self.asm_sel, len(tracks) - 1)] if tracks else None
        self.launch_chaff_at(track)

    def launch_chaff_at(self, track):
        """Deploy one softkill round against an explicit ASM observation."""
        if self.damage.station_down("opz"):
            self.flash(message("runtime.chaff.disabled"))
            return "opz_down"
        if self.softkill_store.ready <= 0:
            self.flash(message("runtime.chaff.cooldown", seconds=f"{self.chaff_cd:.0f}"))
            return "not_ready"
        if track is None or not any(item is track for item in self.asm_tracks()):
            self.flash(message("runtime.chaff.none"))
            return "invalid_target"
        a = next((item for item in self.asms
                  if item.seq == self._missile_seq(track)
                  and item.state == "LAUF"), None)
        profile = self._air_defense_loadout["softkill"]
        if (a is not None and track.range_nm is not None
                and track.position_seen is not None
                and self.sim_t - track.position_seen <= self._air_defense_loadout[
                    "sam"]["observation_max_age_s"]
                and track.range_nm <= profile["range_nm"]
                and self.softkill_store.fire()):
            self.chaff_seq += 1
            threat = math.degrees(math.atan2(a.x - self.ship.x,
                                             -(a.y - self.ship.y))) % 360.0
            cloud = chaff_physics.ChaffCloud(
                self.chaff_seq, *chaff_physics.lay_position(
                    self.ship.x, self.ship.y, threat, self.chaff_seq))
            self.chaff_clouds = (self.chaff_clouds + [cloud])[
                -chaff_physics.MAX_CLOUDS:]
            arrival = (math.hypot(a.x - cloud.x, a.y - cloud.y)
                       / max(config.kn_to_nm_per_s(a.speed_kn), 1e-9))
            broke = a.launch_chaff(self.rng_asm, profile, cloud_seq=cloud.seq,
                                   arrival_s=arrival)
            self.chaff_cd = min(self.softkill_store.loading, default=0.0)
            self.announce(message("runtime.chaff.decoyed" if broke
                                  else "runtime.chaff.jammed"), "waffen")
            return True
        else:
            self.flash(message("runtime.chaff.none"))
            return "stale_ref"

    def deploy_nixie(self) -> None:
        """Deploy one finite towed acoustic countermeasure from own ship."""
        self.deploy_nixie_result()

    def deploy_nixie_result(self):
        if len(self.nixies) >= MAX_TOWED_DECOYS:
            self.flash(message("runtime.nixie.active"))
            return "active_limit"
        if not self.nixie_store.fire():
            self.flash(message("runtime.nixie.empty"))
            return "empty"
        definition = self._ownship_loadout["countermeasure"]
        self.nixie_seq += 1
        self.nixies.append(TowedAcousticDecoy(
            self.nixie_seq, self.ship, life_s=definition["active_life_s"],
            tether_nm=definition["tether_nm"], depth_m=definition["depth_m"]))
        self.announce(message("runtime.nixie.deployed",
                              count=self.nixie_store.remaining_total), "waffen")
        return True

    def set_flak_authorized(self, authorized: bool):
        """Fire-release gate for the AA gun; it never engages FLG raiders
        while withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("weapons"):
            return "weapons_down"
        self.flak_authorized = authorized
        return True

    def set_ciws_authorized(self, authorized: bool):
        """Fire-release gate for CIWS; it never engages inbound ASMs while
        withheld, regardless of ammo/cooldown/range readiness."""
        if type(authorized) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.ciws_authorized = authorized
        return True

    def set_target(self) -> None:
        contacts = [c for c in self.sonar.active_contacts()
                    if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S]
        if not contacts:
            self.target = None
            self.flash(message("runtime.contacts.none"))
            return
        if self.selected_contact in contacts:
            best = self.selected_contact
        else:
            best = max(contacts, key=lambda c: c.confidence)
        if self.designate_sonar_target(best) is not True:
            return
        self.flash(message("runtime.target.set", contact=best.id), 2.0)

    def torpedo_readiness(self) -> tuple[str, tuple]:
        """Return an operator-readable fire-control state and color."""
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            return "BLOCKIERT: KEIN ZIEL", config.COLOR_WARN
        blocked = self._target_affiliation_interlock()
        if blocked is not None:
            return (f"BLOCKIERT: ZUGEHOERIGKEIT {blocked}",
                    config.COLOR_DANGER)
        if self.weapons_tight():
            return "BLOCKIERT: WAFFEN GESPERRT", config.COLOR_DANGER
        if not self._contact_range_fresh(self.target) and self.roe == "STD":
            return "BLOCKIERT: KEINE ENTFERNUNG", config.COLOR_WARN
        if self.weapon_classification(self.target) not in ("U_BOOT", "KAMPFSCHIFF"):
            return ("BLOCKIERT: NICHT ALS U-BOOT/KAMPFSCHIFF KLASSIFIZIERT",
                    config.COLOR_WARN)
        if self.torpedo_count <= 0:
            return "BLOCKIERT: KEINE TORPEDOS", config.COLOR_DANGER
        if self.player_torpedo_battery.ready_count <= 0:
            return "BLOCKIERT: KEIN ROHR BEREIT", config.COLOR_WARN
        if len([t for t in self.torpedoes if t.state == "RUN"]) >= \
                config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]:
            return "BLOCKIERT: SALVENLIMIT", config.COLOR_WARN
        if self.damage.station_down("weapons") or \
                self.damage.station_degraded("weapons"):
            return "BLOCKIERT: WAFFENZENTRALE GESTOERT", config.COLOR_DANGER
        return "FEUER FREI", config.COLOR_OK

    def _contact_affiliations(self, contact) -> list:
        """Return every OPZ affiliation annotation bound to a sonar target."""
        if contact is None:
            return []
        # Operator annotations outlive measurements. Aircraft/missile sequence
        # IDs are a separate namespace and must not annotate a sonar target.
        affiliations = [self.opz_affiliations.get(
            f"{prefix}-{contact.target_id}", "UNKNOWN")
            for prefix in ("U", "S")]
        self.opz_source_observations()
        affiliations.extend(
            self.opz_affiliation(observation_id)
            for observation_id, source in self._opz_source_bindings.items()
            if (source is contact or getattr(source, "target_id", None)
                == contact.target_id and str(
                    getattr(source, "track_id", "")).split("-", 1)[0]
                in ("U", "S")))
        # An affiliation set on an OPZ fusion covers every sonar report in it.
        affiliations.extend(
            self.opz_fusion.fusion_affiliations[fusion.fusion_id]
            for fusion in self._contact_fusions(contact)
            if fusion.fusion_id in self.opz_fusion.fusion_affiliations)
        return affiliations

    def _contact_fusions(self, contact) -> list:
        """Intact OPZ fusions holding a report bound to this sonar contact.

        Read-only: a fusion counts only while its member reports are current
        (``live_members``, the condition ``OPZFusion.prune`` applies), so the result
        never depends on whether a frame pruned the register first.
        """
        if contact is None or not self.opz_fusion.fusions:
            return []
        current = {item.observation_id for item in self.opz_source_observations()}
        bindings = self._opz_source_bindings
        fusions = []
        for _, fusion in sorted(self.opz_fusion.fusions.items()):
            members = live_members(fusion, current)
            if members is not None and any(bindings.get(member) is contact
                                           for member in members):
                fusions.append(fusion)
        return fusions

    def weapon_classification(self, contact) -> str | None:
        """Operator class that fire control uses for one sonar contact.

        The sonar contact's own class wins; otherwise the class the OPZ gave a
        fusion holding this contact's report applies.
        """
        if contact is None:
            return None
        if contact.player_class in config.PLAYER_CLASSES:
            return contact.player_class
        return next((self.opz_fusion.classifications[fusion.fusion_id]
                     for fusion in self._contact_fusions(contact)
                     if self.opz_fusion.classifications.get(fusion.fusion_id)
                     in config.PLAYER_CLASSES), None)

    def contact_affiliation(self, contact) -> str:
        """Resolve one affiliation for a contact, FRIEND/NEUTRAL taking
        precedence over HOSTILE so callers stay conservative by default."""
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL", "HOSTILE")
                     if value in affiliations), "UNKNOWN")

    def weapons_tight(self) -> bool:
        """Scenario 13 is peacetime: no weapon may be released at a submarine."""
        from src.core import boat_missions
        return boat_missions.mode(self) == "trail"

    def _target_affiliation_interlock(self, contact=None):
        """Return a protected OPZ affiliation for the assigned sonar target."""
        contact = self.target if contact is None else contact
        if contact is None:
            return None
        affiliations = self._contact_affiliations(contact)
        return next((value for value in ("FRIEND", "NEUTRAL")
                     if value in affiliations), None)

    def _contact_range_fresh(self, contact) -> bool:
        if contact is None or contact.range_est is None:
            return False
        observed_at = (contact.range_seen if contact.range_seen is not None
                       else contact.last_seen)
        return self.sim_t - observed_at <= config.SONAR_CONTACT_LOST_S

    # --- M9: Kontakt-Auswahl & manuelle Klassifizierung ---

    def _cycle_selected_contact(self, delta: int) -> None:
        cs = sorted((c for c in self.sonar.contacts.values()
                     if self.sim_t - c.last_seen < config.SONAR_CONTACT_LOST_S),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]
        if self.sonar.focus_locked:
            self.sonar.reset_listening_history()

    def _cycle_helo_contact(self, delta: int) -> None:
        """W2: browse only what the helicopter's own dip has plotted - its
        own active/passive picture, independent of the ship's sonar picture -
        so the operator can select one and release it to CIC from here."""
        cs = sorted((c for c in self.sonar.contacts.values()
                     if (c.dip_last_seen is not None
                         and 0 <= self.sim_t - c.dip_last_seen
                         < config.SONAR_CONTACT_LOST_S)
                     or any(fix["source"] == "DIPPING"
                            for fix in c.active_fixes(self.sim_t))
                     or any(0 <= self.sim_t - row["measured_at"]
                            < config.SONAR_CONTACT_LOST_S
                            for row in c.buoy_reports.values())),
                    key=lambda c: c.id)
        if not cs:
            self.selected_contact = None
            self.flash(message("runtime.contact.none_selected"))
            return
        try:
            i = cs.index(self.selected_contact)
        except ValueError:
            i = -1
        self.selected_contact = cs[(i + delta) % len(cs)]

    def _cycle_classification(self) -> None:
        if self.selected_contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        if self.selected_contact.target_id not in self.sonar.contacts:
            self.selected_contact = None
            return
        c = self.selected_contact
        order = [None] + list(config.PLAYER_CLASSES)
        value = order[(order.index(c.player_class) + 1) % len(order)]
        if self.classify_sonar_contact(c, value) is not True:
            return
        self.flash(message("runtime.contact.classified", contact=c.id,
                           classification=display_value("classification",
                                                        c.player_class, self.tr)), 2.0)

    def _toggle_sonar_release(self) -> None:
        contact = self.selected_contact
        if contact is None:
            self.flash(message("runtime.contact.none_selected"))
            return
        helicopter = self.station is Station.HELICOPTER
        buoy = helicopter and self.helo_sensor_source == "BUOY"
        released = not (contact.buoy_released_to_opz if buoy else
                        contact.dip_released_to_opz if helicopter
                        else contact.released_to_opz)
        if self.release_sonar_contact(contact, released,
                                      source="buoy" if buoy else
                                      "helicopter" if helicopter else "sonar") is not True:
            return
        self.flash(message("runtime.sonar.release" if released
                           else "runtime.sonar.withdraw",
                           contact=contact.id), 2.0)

    def _find_target(self, target_id: int):
        for s in self.subs:
            if s.id == target_id:
                return s
        for a in self.animals:
            if a.id == target_id:
                return a
        for d in self.decoys:
            if d.id == target_id:
                return d
        for civilian in self.civilians:
            if civilian.id == target_id:
                return civilian
        for w in self.warships:
            if w.id == target_id:
                return w
        for t in self.enemy_torpedoes:
            if t.id == target_id:
                return t
        return None

    # --- torpedo settings (type, pattern, enable point, salvo) --------------

    def torpedo_type_choices(self) -> list:
        """(weapon key, profile name, remaining) of every ship torpedo type."""
        battery = self.player_torpedo_battery
        rows = []
        for weapon in self._ownship_loadout["weapons"]:
            profile = self.runtime_catalog.torpedoes.get(weapon["runtime_profile_key"])
            rows.append((weapon["key"], profile.name if profile is not None
                         else weapon["runtime_profile_key"],
                         battery.remaining_of(weapon["key"])))
        return rows

    def set_torpedo_type(self, weapon_key):
        """Select the torpedo type the tubes load next (a tube swaps over if
        none holds it yet). Returns True or a reason code."""
        if weapon_key not in {row[0] for row in self.torpedo_type_choices()}:
            return "invalid_value"
        self.torpedo_type = weapon_key
        if not self.player_torpedo_battery.retask(weapon_key):
            self.flash(message("runtime.torpedo.type_empty"), 2.0)
            return "empty"
        name = next(row[1] for row in self.torpedo_type_choices() if row[0] == weapon_key)
        self.flash(message("runtime.torpedo.type", name=raw_text(name)), 2.0)
        return True

    def _cycle_torpedo_type(self) -> None:
        keys = [row[0] for row in self.torpedo_type_choices()]
        index = keys.index(self.torpedo_type) if self.torpedo_type in keys else -1
        self.set_torpedo_type(keys[(index + 1) % len(keys)])

    def set_torpedo_pattern(self, pattern):
        if pattern not in torpedo_dyn.SEARCH_PATTERNS:
            return "invalid_value"
        self.torpedo_pattern = pattern
        self.flash(message("runtime.torpedo.pattern",
                           pattern=display_value("torpedo_pattern", pattern, self.tr)), 2.0)
        return True

    def _cycle_torpedo_pattern(self) -> None:
        patterns = torpedo_dyn.SEARCH_PATTERNS
        self.set_torpedo_pattern(patterns[(patterns.index(self.torpedo_pattern) + 1)
                                          % len(patterns)])

    def set_torpedo_enable(self, enable_nm):
        if (type(enable_nm) not in (int, float) or not math.isfinite(enable_nm)
                or not torpedo_dyn.ENABLE_RANGE_MIN_NM <= enable_nm
                <= torpedo_dyn.ENABLE_RANGE_MAX_NM):
            return "invalid_value"
        self.torpedo_enable_nm = torpedo_dyn.quantized_enable_nm(enable_nm)
        self.flash(message("runtime.torpedo.enable",
                           range=f"{self.torpedo_enable_nm:.1f}"), 2.0)
        return True

    def _adjust_torpedo_enable(self, steps: int) -> None:
        wanted = self.torpedo_enable_nm + steps * torpedo_dyn.ENABLE_RANGE_STEP_NM
        self.set_torpedo_enable(config.clamp(wanted, torpedo_dyn.ENABLE_RANGE_MIN_NM,
                                             torpedo_dyn.ENABLE_RANGE_MAX_NM))

    def set_torpedo_salvo(self, salvo):
        if type(salvo) is not int or salvo not in torpedo_dyn.SALVO_SIZES:
            return "invalid_value"
        self.torpedo_salvo = salvo
        self.flash(message("runtime.torpedo.salvo", salvo=salvo), 2.0)
        return True

    def _cycle_torpedo_salvo(self) -> None:
        sizes = torpedo_dyn.SALVO_SIZES
        self.set_torpedo_salvo(sizes[(sizes.index(self.torpedo_salvo) + 1) % len(sizes)])

    def launch_torpedo(self) -> None:
        if (self.target is None
                or self.sim_t - self.target.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.target = None
            self.flash(message("runtime.target.invalid"))
            return
        self.launch_torpedo_at(self.target, self.torpedo_depth)

    def launch_torpedo_at(self, contact, depth_m: float):
        """Launch from ownship against one explicit sonar observation."""
        if (contact is None or type(depth_m) not in (int, float)
                or not math.isfinite(depth_m) or not 10 <= depth_m <= 300
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            self.flash(message("runtime.target.invalid"))
            return "invalid_target"
        blocked = self._target_affiliation_interlock(contact)
        if blocked is not None:
            self.flash(message("runtime.roe.blocked",
                               affiliation=display_value("affiliation", blocked, self.tr)))
            return "roe_blocked"
        if self.weapons_tight():
            self.flash(message("runtime.roe.weapons_tight"))
            return "roe_blocked"
        if self.roe == "STD":
            if not self._contact_range_fresh(contact):
                self.flash(message("runtime.target.not_located"))
                return "not_located"
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        else:
            if self.weapon_classification(contact) not in ("U_BOOT", "KAMPFSCHIFF"):
                self.flash(message("runtime.target.not_classified"))
                return "not_classified"
        active_torpedoes = len([t for t in self.torpedoes if t.state == "RUN"])
        salvo_limit = config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]
        if active_torpedoes >= salvo_limit:
            self.flash(message("runtime.salvo.limit", limit=salvo_limit))
            return "salvo_limit"
        if self.torpedo_count <= 0:
            self.flash(message("event.no_torpedoes"))
            return "empty"
        if self.player_torpedo_battery.ready_count <= 0:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        if self.damage.station_down("weapons"):
            self.flash(message("runtime.weapons.down"))
            return "weapons_down"
        if self.damage.station_degraded("weapons"):
            self.flash(message("runtime.weapons.degraded"))
            return "weapons_degraded"
        tgt = self._find_target(contact.target_id)
        if (contact.observed_x is not None
                and contact.observed_y is not None
                and self._contact_range_fresh(contact)):
            est_x, est_y = contact.observed_x, contact.observed_y
        else:
            range_nm = (contact.range_est if contact.range_est is not None
                        else config.ROE_FREE_LAUNCH_RANGE_NM)
            est_x = self.ship.x + range_nm * math.sin(math.radians(contact.bearing))
            est_y = self.ship.y - range_nm * math.cos(math.radians(contact.bearing))
        course = math.degrees(math.atan2(est_x - self.ship.x,
                                         -(est_y - self.ship.y))) % 360.0
        battery = self.player_torpedo_battery
        if battery.loaded_count(self.torpedo_type) <= 0:
            self.flash(message("runtime.torpedo.no_tube_type"))
            return "no_tube_type"
        # A two-torpedo salvo opens a spread about the line of fire; every
        # weapon gets its own datum turned about the ship by the same angle.
        salvo = 2 if (self.torpedo_salvo == 2
                      and battery.loaded_count(self.torpedo_type) >= 2
                      and active_torpedoes + 2 <= salvo_limit) else 1
        launches = []
        for launch_course in torpedo_dyn.spread_courses(course, salvo):
            offset = config.angle_diff_deg(launch_course, course)
            launches.append((launch_course, *torpedo_dyn.rotate_datum(
                self.ship.x, self.ship.y, est_x, est_y, offset)))
        launched = []
        for launch_course, datum_x, datum_y in launches:
            weapon_key = battery.fire(self.torpedo_type)
            if weapon_key is None:
                break
            self.torpedo_seq += 1
            weapon_definition = next(
                item
                for item in self._ownship_loadout["weapons"]
                if item["key"] == weapon_key)
            profile_key = weapon_definition["runtime_profile_key"]
            profile = self.runtime_catalog.torpedoes[profile_key]
            self.torpedoes.append(Torpedo(self.ship.x, self.ship.y, launch_course,
                                          depth_m, tgt, self.torpedo_seq,
                                          kill_dist_nm=self.difficulty["kill_dist_nm"],
                                          kill_depth_m=self.difficulty["kill_depth_m"],
                                          guidance_x=datum_x, guidance_y=datum_y,
                                          profile=profile, time_since_launch=0.0,
                                          pattern=self.torpedo_pattern,
                                          enable_nm=self.torpedo_enable_nm))
            launched.append(self.torpedo_seq)
        if not launched:
            self.flash(message("runtime.torpedo.no_tube"))
            return "no_tube"
        self.torpedo_count = self.player_torpedo_battery.remaining_total
        # W2: the launch transient itself is a loud, one-time acoustic event,
        # audible passively much farther than a torpedo's own terminal seeker
        # ever gets (TORP_HOME_RANGE_NM) - distinct concept, separate gate.
        for sub in self.subs:
            if (not sub.sunk and sub.state != "SINKING"
                    and math.hypot(self.ship.x - sub.x, self.ship.y - sub.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        sub.x, sub.y, sub.depth)):
                sub.alert_torpedo(source=(self.ship.x, self.ship.y))
        for warship in self.warships:
            if (not warship.sunk and warship.doctrine == "surface_combatant"
                    and math.hypot(self.ship.x - warship.x, self.ship.y - warship.y)
                    <= config.SUB_TORPEDO_ALERT_NM
                    and not self.world.sonar_path_blocked(
                        self.ship.x, self.ship.y, 5.0,
                        warship.x, warship.y, warship.depth)):
                bearing = math.degrees(math.atan2(
                    self.ship.x - warship.x,
                    -(self.ship.y - warship.y))) % 360.0
                warship.alert_torpedo(bearing)
                if (warship.countermeasures_left > 0 and warship.side == "hostile"
                        and len(self.decoys) < MAX_DECOYS):
                    # Stream an acoustic decoy while turning away.
                    warship.countermeasures_left -= 1
                    decoy_profile = self.runtime_catalog.decoys[
                        self.runtime_catalog.runtime_bindings["submarine_decoy"]]
                    self.decoys.append(Decoy(
                        warship.x, warship.y, 10.0, self.rng_asw, decoy_profile,
                        self.runtime_catalog.acoustic_for(decoy_profile.key),
                        source_id=warship.id))
        self._emit_sound("torpedo_launch")
        for torpedo_idx in launched:
            self.flash(message("runtime.torpedo.launched", torpedo=torpedo_idx), 2.0)
            self.feed.add(self.world.format_time(), "waffen",
                          message("runtime.torpedo.feed", torpedo=torpedo_idx,
                                  contact=contact.id))
        return True

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
