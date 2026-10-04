"""The maritime patrol aircraft in the game (OPZ page 3, Remote Crew OPZ).

``src/air/mpa.py`` flies the aircraft; this mixin gives it its orders,
drops its buoys, runs its surface-search radar and its torpedo release, and
decides what reaches the ship.  The aircraft itself is commanded own-force
truth (datalink); what it senses reaches the ship only as observations:
radar tracks with source ``RADAR-MPA`` and the reports of its buoys while
it relays them.
"""

from __future__ import annotations

import math

from src.air import helicopter as helicopter_physics
from src.air.mpa import PatrolAircraft
from src.core import boat_threat
from src.core import config, detrand
from src.core.i18n import display_value, message
from src.sensors import mad as mad_physics
from src.sensors import radar as radar_physics
from src.weapons.torpedo import Torpedo

MPA_BUOY_OWNER = "MPA"
PATTERNS = ("field", "barrier", "circle")


class MpaMixin:
    """Orders, sensors and weapons of the on-call patrol aircraft."""

    def _reset_mpa(self) -> None:
        x, y = self._mpa_base()
        self.mpa = PatrolAircraft(x, y)

    def _mpa_base(self) -> tuple[float, float]:
        """The nearest friendly airfield, or the nearest map edge."""
        ship = self.ship
        bases = [base for base in self.world.coast.friendly_bases()
                 if "x" in base and "y" in base]
        if bases:
            base = min(bases, key=lambda item: (math.hypot(item["x"] - ship.x,
                                                           item["y"] - ship.y),
                                                str(item.get("id", ""))))
            return float(base["x"]), float(base["y"])
        size = float(self.world.size_nm)
        edges = sorted(((ship.x, (0.0, ship.y)), (size - ship.x, (size, ship.y)),
                        (ship.y, (ship.x, 0.0)), (size - ship.y, (ship.x, size))),
                       key=lambda item: item[0])
        return tuple(float(value) for value in edges[0][1])

    # --- what the ship knows ------------------------------------------------------

    def mpa_datalink(self) -> bool:
        mpa = self.mpa
        return mpa.airborne and math.hypot(mpa.x - self.ship.x,
                                           mpa.y - self.ship.y) <= config.MPA_DATALINK_NM

    def _buoy_relayed(self, buoy) -> bool:
        if getattr(buoy, "owner", "HELO") != MPA_BUOY_OWNER:
            return True
        mpa = self.mpa
        return self.mpa_datalink() and math.hypot(
            mpa.x - buoy.x, mpa.y - buoy.y) <= config.MPA_RELAY_NM

    def heard_buoys(self) -> list:
        """Buoys whose reports reach the ship (the aircraft relays its own)."""
        return [buoy for buoy in self.buoys if self._buoy_relayed(buoy)]

    def mpa_view(self) -> dict:
        mpa = self.mpa
        airborne = mpa.airborne
        dx, dy = mpa.x - self.ship.x, mpa.y - self.ship.y
        return dict(
            state=mpa.state, airborne=airborne,
            x=mpa.x if airborne else None, y=mpa.y if airborne else None,
            course=mpa.course if airborne else None,
            bearing=math.degrees(math.atan2(dx, -dy)) % 360.0 if airborne else None,
            range_nm=math.hypot(dx, dy) if airborne else None,
            waypoint_x=mpa.waypoint_x, waypoint_y=mpa.waypoint_y,
            fuel_s=mpa.fuel_s, bingo_s=mpa.bingo_s() if airborne else None,
            ready_in_s=mpa.ready_in_s(self.sim_t),
            sorties_left=config.MPA_SORTIES - mpa.sorties,
            buoys=mpa.buoys_left, torpedoes=mpa.torps, radar=mpa.radar_on,
            mad=mpa.mad_mode,
            buoy_mode=mpa.buoy_mode, pattern=mpa.pattern,
            pattern_points=[tuple(point) for point in mpa.pattern_queue],
            datalink=self.mpa_datalink(),
            relayed=sum(1 for buoy in self.buoys
                        if getattr(buoy, "owner", "HELO") == MPA_BUOY_OWNER
                        and self._buoy_relayed(buoy)))

    # --- orders ---------------------------------------------------------------------

    def _mpa_notice(self, key: str, seconds: float = 3.0, **params) -> None:
        text = message(key, **params)
        self.feed.add(self.world.format_time(), "opz", text)
        if getattr(self, "local_side", "frigate") != "uboot":
            self.flash(text, seconds)

    def request_mpa(self):
        """Request the aircraft; it heads for the ship's position first."""
        if self.game_over:
            return "not_ready"
        if self.damage.station_down("opz"):
            return "opz_down"
        if not self.mpa.launch(self.ship.x, self.ship.y, self.sim_t):
            return "not_ready"
        eta = math.hypot(self.ship.x - self.mpa.x, self.ship.y - self.mpa.y) / (
            config.kn_to_nm_per_s(config.MPA_TRANSIT_KN) * 60.0)
        self._mpa_notice("mpa.requested", minutes=f"{eta:.0f}")
        return True

    def mpa_return(self):
        if self.damage.station_down("opz"):
            return "opz_down"
        if not self.mpa.order_return():
            return "not_ready"
        self._mpa_notice("mpa.rtb")
        return True

    def toggle_mpa(self):
        return self.mpa_return() if self.mpa.airborne else self.request_mpa()

    def set_mpa_waypoint(self, x, y):
        if self.damage.station_down("opz"):
            return "opz_down"
        size = float(self.world.size_nm)
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y)
                or not (0.0 <= x <= size and 0.0 <= y <= size)):
            return "invalid_value"
        if self.mpa.state not in ("TRANSIT", "STATION"):
            return "not_ready"
        self.mpa.set_waypoint(float(x), float(y))
        self.mpa.pattern_queue = []
        self.mpa.pattern = "single"
        bearing = math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y))) % 360.0
        self._mpa_notice("mpa.waypoint", 1.5, bearing=f"{bearing:03.0f}",
                         range=f"{math.hypot(x - self.ship.x, y - self.ship.y):.0f}")
        return True

    def mpa_waypoint_to_selection(self):
        """Waypoint on the selected OPZ track's plotted position, else on the
        ship; a bearing-only track has no position to fly to."""
        from src.ui import observations
        track = self.selected_opz_track()
        if track is None:
            x, y = self.ship.x, self.ship.y
        else:
            x, y = observations.position(track)
            if x is None or y is None:
                return "not_located"
        size = float(self.world.size_nm)
        return self.set_mpa_waypoint(config.clamp(float(x), 0.0, size),
                                     config.clamp(float(y), 0.0, size))

    def set_mpa_pattern(self, kind: str):
        """Plan a buoy pattern about the waypoint (``single`` cancels it)."""
        if type(kind) is not str or kind not in helicopter_physics.BUOY_PATTERNS:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        mpa = self.mpa
        if kind == "single":
            mpa.pattern_queue = []
            mpa.pattern = "single"
            return True
        if mpa.state not in ("TRANSIT", "STATION"):
            return "not_ready"
        if mpa.buoys_left <= 0:
            return "no_buoys"
        bearing = math.degrees(math.atan2(mpa.waypoint_x - self.ship.x,
                                          -(mpa.waypoint_y - self.ship.y))) % 360.0
        points = helicopter_physics.plan_buoy_pattern(kind, mpa.waypoint_x, mpa.waypoint_y,
                                                      bearing, mpa.buoys_left)
        size = float(self.world.size_nm)
        points = [(config.clamp(x, 0.0, size), config.clamp(y, 0.0, size)) for x, y in points]
        if not points:
            return "invalid_value"
        mpa.pattern = kind
        mpa.pattern_queue = points
        self._mpa_notice("mpa.pattern", 2.0, pattern=display_value("buoy_pattern", kind),
                         count=str(len(points)))
        return True

    def cycle_mpa_pattern(self):
        current = self.mpa.pattern
        index = PATTERNS.index(current) + 1 if current in PATTERNS else 0
        if index >= len(PATTERNS):
            return self.set_mpa_pattern("single")
        return self.set_mpa_pattern(PATTERNS[index])

    def mpa_drop_buoy(self, x=None, y=None):
        """One buoy at the aircraft (or, on a pattern run, the planned point)."""
        if self.damage.station_down("opz"):
            return "opz_down"
        mpa = self.mpa
        if mpa.state not in ("TRANSIT", "STATION"):
            return "not_ready"
        if mpa.buoys_left <= 0:
            return "no_buoys"
        at_x, at_y = (mpa.x, mpa.y) if x is None else (x, y)
        size = float(self.world.size_nm)
        if (not (0.0 <= at_x <= size and 0.0 <= at_y <= size)
                or self.world.on_land(at_x, at_y) or self.world.depth_m(at_x, at_y) <= 5.0):
            return "water_required"
        saved = mpa.x, mpa.y
        mpa.x, mpa.y = at_x, at_y
        buoy = mpa.deploy_buoy(self.buoy_seq + 1, self.world)
        mpa.x, mpa.y = saved
        if buoy is None:
            return "not_ready"
        self.buoy_seq += 1
        self.buoys.append(buoy)
        boat_threat.record_splash(self, buoy.x, buoy.y, buoy.seq)
        self._mpa_notice("mpa.buoy", 1.5, buoy=str(buoy.seq))
        return True

    def set_mpa_buoy_mode(self, mode: str):
        if mode not in ("PASSIVE", "ACTIVE"):
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.mpa.buoy_mode = mode
        return True

    def toggle_mpa_buoy_mode(self):
        mode = "ACTIVE" if self.mpa.buoy_mode == "PASSIVE" else "PASSIVE"
        result = self.set_mpa_buoy_mode(mode)
        if result is True:
            self.flash(message("mpa.buoy_mode", mode=display_value("buoy_mode", mode)), 1.5)
        return result

    def set_mpa_radar(self, enabled):
        if type(enabled) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        self.mpa.radar_on = enabled
        return True

    def toggle_mpa_radar(self):
        result = self.set_mpa_radar(not self.mpa.radar_on)
        if result is True:
            self.flash(message("mpa.radar_on" if self.mpa.radar_on else "mpa.radar_off"), 1.5)
        return result

    def mpa_attack(self):
        """Release a lightweight torpedo on the designated sonar contact."""
        contact = self.target
        if (contact is None
                or self.sim_t - contact.last_seen >= config.SONAR_CONTACT_LOST_S):
            return "invalid_target"
        if self.damage.station_down("opz"):
            return "opz_down"
        if self._target_affiliation_interlock(contact) is not None or self.weapons_tight():
            return "roe_blocked"
        if self.roe == "STD" and not self._contact_range_fresh(contact):
            return "not_located"
        if self.weapon_classification(contact) != "U_BOOT":
            return "not_classified"
        mpa = self.mpa
        if mpa.state not in ("TRANSIT", "STATION") or not self.mpa_datalink():
            return "not_ready"
        if mpa.torps <= 0:
            return "empty"
        use_fix = (self._contact_range_fresh(contact) and contact.observed_x is not None
                   and contact.observed_y is not None)
        if use_fix:
            datum_x, datum_y = contact.observed_x, contact.observed_y
        else:
            range_nm = (contact.range_est if contact.range_est is not None
                        else config.ROE_FREE_LAUNCH_RANGE_NM)
            rad = math.radians(contact.bearing)
            datum_x = self.ship.x + range_nm * math.sin(rad)
            datum_y = self.ship.y - range_nm * math.cos(rad)
        if math.hypot(mpa.x - datum_x, mpa.y - datum_y) > config.MPA_DROP_NM:
            return "out_of_range"
        if (self.world.on_land(mpa.x, mpa.y) or self.world.depth_m(mpa.x, mpa.y) <= 5.0):
            return "water_required"
        profile = helicopter_physics.HELO_TORPEDO_PROFILE
        level = self.difficulty
        mpa.torps -= 1
        course = math.degrees(math.atan2(datum_x - mpa.x, -(datum_y - mpa.y))) % 360.0
        torpedo = Torpedo(mpa.x, mpa.y, course, self.torpedo_depth,
                          self._find_target(contact.target_id), self.torpedo_seq + 1,
                          kill_dist_nm=level["kill_dist_nm"], kill_depth_m=level["kill_depth_m"],
                          speed_kn=profile.speed_kn, guidance_x=datum_x, guidance_y=datum_y,
                          range_nm=profile.range_nm, profile=profile, launch_origin="mpa")
        torpedo.break_wire()
        self.torpedo_seq += 1
        self.torpedoes.append(torpedo)
        self._mpa_notice("mpa.torpedo", 2.5, torpedo=str(self.torpedo_seq))
        return True

    def _mpa_order_feedback(self, result) -> None:
        """Banner for a refused uConsole order (the browser shows its own)."""
        if result is not True:
            self.flash(message("mpa.refused." + str(result)), 2.0)

    # --- time ----------------------------------------------------------------------------

    def _update_mpa(self, dt: float) -> None:
        mpa = self.mpa
        if not mpa.airborne:
            return
        event = mpa.update(dt, self.sim_t)
        if event == "on_station":
            self._mpa_notice("mpa.on_station")
        elif event == "bingo":
            self._mpa_notice("mpa.bingo")
        elif event == "landed":
            self._mpa_notice("mpa.landed")
            return
        if mpa.pattern_queue and mpa.state in ("TRANSIT", "STATION"):
            px, py = mpa.pattern_queue[0]
            if math.hypot(mpa.x - px, mpa.y - py) <= config.MPA_DROP_POINT_NM:
                result = self.mpa_drop_buoy(px, py)
                mpa.pattern_queue.pop(0)
                if result == "no_buoys":
                    mpa.pattern_queue = []
                if not mpa.pattern_queue:
                    mpa.pattern = "single"
                    self._mpa_notice("mpa.pattern_done", 2.0)
        self._update_mpa_radar(dt)
        self._update_mpa_mad(dt)

    def _update_mpa_radar(self, dt: float) -> None:
        """One surface-search look per target and scan, published over the
        datalink as ``RADAR-MPA`` tracks (measured from the aircraft)."""
        mpa = self.mpa
        if not (mpa.radar_on and self.mpa_datalink()):
            return
        self._airborne_radar_sweep(
            dt, mpa.x, mpa.y, mpa.altitude_m, config.MPA_RADAR_RANGE_NM,
            "mpa-radar-", "M-", "RADAR-MPA")

    def _update_mpa_mad(self, dt: float) -> None:
        """MAD passes: a stateless draw per submerged hull under the aircraft;
        a detection reaches the ship over the datalink as a MAD fix."""
        mpa = self.mpa
        if not (mpa.mad_run and self.mpa_datalink()):
            return
        look = config.MPA_MAD_LOOK_S
        tick = math.floor((self.sim_t + 1e-9) / look)
        if tick == math.floor((self.sim_t - dt + 1e-9) / look):
            return
        for target in self._sonar_targets():
            if (getattr(target, "sensor_domain", None) != "subsurface"
                    or getattr(target, "sunk", False)):
                continue
            slant = mad_physics.slant_m(math.hypot(mpa.x - target.x, mpa.y - target.y),
                                        getattr(target, "depth", 0.0),
                                        config.MPA_MAD_ALTITUDE_M)
            if slant > mad_physics.MAD_MAX_SLANT_M:
                continue
            probability = mad_physics.detection_probability(slant)
            if detrand.u01(self.seed, "mpa-mad", int(target.sensor_seed), tick) >= probability:
                continue
            contact = self.sonar._get_contact(target)
            contact._fx, contact._fy = self.ship.x, self.ship.y
            previous = contact.fixes.get("MAD")
            contact.update_mad(mpa.x, mpa.y, self.sim_t,
                               mad_physics.MAD_FIX_UNCERTAINTY_NM,
                               mad_physics.MAD_FIX_QUALITY)
            if previous is None or self.sim_t - previous["measured_at"] >= 10.0:
                self._mpa_notice("mpa.mad_contact", contact=contact.id)
        self._mad_wreck_anomalies(mpa.x, mpa.y, config.MPA_MAD_ALTITUDE_M, "mpa-mad", tick,
                                  "mpa.mad_anomaly")

    def set_mpa_mad(self, enabled):
        """Start or end the aircraft's MAD passes over its waypoint."""
        if type(enabled) is not bool:
            return "invalid_value"
        if self.damage.station_down("opz"):
            return "opz_down"
        mpa = self.mpa
        if enabled and mpa.state not in ("TRANSIT", "STATION"):
            return "not_airborne"
        mpa.mad_mode = enabled
        return True

    def toggle_mpa_mad(self):
        result = self.set_mpa_mad(not self.mpa.mad_mode)
        if result is True:
            self.flash(message("mpa.mad_on" if self.mpa.mad_mode else "mpa.mad_off"), 1.5)
        return result

    def _update_helo_radar(self, dt: float) -> None:
        """The helicopter's surface-search radar: on while it flies with the
        dipping sonar stowed (the same condition as its emission a boat's
        ESM intercepts); contacts reach the OPZ as ``RADAR-HELO`` tracks."""
        if not self.helo_radar_active():
            return
        helo = self.helo
        self._airborne_radar_sweep(
            dt, helo.x, helo.y, config.HELO_RADAR_ALTITUDE_M,
            config.HELO_RADAR_RANGE_NM, "helo-radar-", "H-", "RADAR-HELO")

    def _update_aircrew_eyes(self, dt: float) -> None:
        """The helicopter's and patrol aircraft's crews look out too: a
        raised periscope or snorkel head is seen by its feather (the
        lookout's contrast model from the aircraft's height), published as
        ``HELO-EYE`` or, over the datalink, ``MPA-EYE`` tracks."""
        look = config.MPA_RADAR_LOOK_S
        tick = math.floor((self.sim_t + 1e-9) / look)
        if tick == math.floor((self.sim_t - dt + 1e-9) / look):
            return
        observers = []
        helo = self.helo
        if helo.airborne:
            observers.append((helo.x, helo.y,
                              config.HELO_RADAR_ALTITUDE_M if helo.dip_state == "STOWED"
                              else config.AIRCREW_HOVER_EYE_M, "HELO-EYE", "HE-"))
        mpa = getattr(self, "mpa", None)
        if mpa is not None and self.mpa_datalink():
            observers.append((mpa.x, mpa.y, mpa.altitude_m, "MPA-EYE", "ME-"))
        if not observers:
            return
        from src.core.game_sim import LOOKOUT_MODEL
        from src.sensors import lookout_id
        from src.sensors import visual as visual_physics
        environment = self._lookout_environment()
        for sub in sorted(self.subs, key=lambda item: item.id):
            if (sub.sunk or sub.state == "SINKING"
                    or sub.depth <= config.LOOKOUT_SUB_SURFACED_MAX_DEPTH_M
                    or not self._mast_up(sub)):
                continue
            strength = visual_physics.feather_strength(sub.speed)
            for x, y, altitude, source, prefix in observers:
                dx, dy = sub.x - x, sub.y - y
                distance = math.hypot(dx, dy)
                if (LOOKOUT_MODEL.margin("MAST", distance, eye_m=altitude, **environment)
                        * strength < 1.0 or self.world.land_blocks_line(x, y, sub.x, sub.y)):
                    continue
                recognized = LOOKOUT_MODEL.margin(
                    "MAST", distance, eye_m=altitude,
                    detail=lookout_id.RECOGNIZE_CYCLES, **environment) * strength >= 1.0
                key = int(sub.sensor_seed)
                bearing = (math.degrees(math.atan2(dx, -dy))
                           + config.LOOKOUT_BEARING_ERR_DEG
                           * detrand.normal(self.seed, source + "-brg", key, tick)) % 360.0
                measured = max(0.0, distance * (1.0 + config.LOOKOUT_RANGE_ERR_FRAC
                                                * detrand.normal(self.seed, source + "-rng",
                                                                 key, tick)))
                track_id = prefix + self._observation_key("eye", key)
                self.air_picture.observe(
                    track_id=track_id, kind="SUB" if recognized else "SURFACE",
                    target_id=0, source=source, bearing=bearing, range_nm=measured,
                    observer_x=x, observer_y=y, course=None, quality=.6,
                    now=self.sim_t, label=track_id,
                    bearing_uncertainty_deg=config.LOOKOUT_BEARING_ERR_DEG)

    def helo_radar_active(self) -> bool:
        return (self.helo.airborne and self.helo.dip_state == "STOWED"
                and self.helo.radar_on)

    def set_helicopter_radar(self, enabled):
        """Switch the helicopter's search radar (it radiates only while
        airborne with the dipping sonar stowed)."""
        if type(enabled) is not bool:
            return "invalid_value"
        self.helo.radar_on = enabled
        self.flash(message("runtime.helo.radar_on" if enabled
                           else "runtime.helo.radar_off"), 1.5)
        return True

    def _update_sub_radar_alert(self, dt: float) -> None:
        """AI submarines' ESM against the frigate's aircraft radars: a boat
        with its mast or snorkel up that hears one breaks off the snorkel or
        radio call, goes deep and stays down for ``SUB_RADAR_HOLD_S``."""
        look = config.SUB_RADAR_ALERT_LOOK_S
        tick = math.floor((self.sim_t + 1e-9) / look)
        if tick == math.floor((self.sim_t - dt + 1e-9) / look):
            return
        emitters = []
        if self.helo_radar_active():
            emitters.append((self.helo.x, self.helo.y, config.HELO_RADAR_ALTITUDE_M))
        mpa = getattr(self, "mpa", None)
        if mpa is not None and mpa.airborne and mpa.radar_on:
            emitters.append((mpa.x, mpa.y, mpa.altitude_m))
        if not emitters:
            return
        for sub in self.subs:
            if sub.sunk or sub.manual or sub.state == "SINKING" or not self._mast_up(sub):
                continue
            heard = any(
                math.hypot(sub.x - x, sub.y - y) <= min(
                    config.SUB_RADAR_ALERT_NM,
                    config.radar_horizon_nm(altitude, config.SUB_MAST_HEIGHT_M))
                for x, y, altitude in emitters)
            if not heard or detrand.u01(self.seed, "sub-radar-alert", int(sub.sensor_seed),
                                        tick) >= config.SUB_RADAR_ALERT_P:
                continue
            sub.radar_hold_s = config.SUB_RADAR_HOLD_S
            endurance = sub.endurance
            if endurance is not None and endurance.surface_operation:
                endurance.phase = "DESCENDING"
                endurance.return_depth_m = (endurance.profile.snorkel_depth_m
                                            + config.SUB_RADAR_DIVE_M)

    def _airborne_radar_sweep(self, dt, observer_x, observer_y, altitude_m,
                              range_nm, tag_prefix, id_prefix, source) -> None:
        """One look per target and scan from an own aircraft: ships, surfaced
        boats and raised masts inside range and radar horizon."""
        look = config.MPA_RADAR_LOOK_S
        tick = math.floor((self.sim_t + 1e-9) / look)
        if tick == math.floor((self.sim_t - dt + 1e-9) / look):
            return
        conditions = dict(
            sea_state=getattr(self.world, "effective_sea_state", self.world.sea_state),
            rain_intensity=self.radar_rain_severity(), capability=1.0)
        candidates = []
        for ship in list(self.civilians) + list(self.warships):
            if not ship.sunk:
                candidates.append(("surface", ship, 10.0, 1.0))
        for sub in self.subs:
            if sub.sunk:
                continue
            if sub.depth <= config.UBOOT_SURFACED_DEPTH_M:
                candidates.append(("sub", sub, config.SUB_SURFACED_HEIGHT_M,
                                   config.SUB_SURFACED_RCS_FACTOR))
            elif self._mast_up(sub):
                candidates.append(("sub", sub, config.SUB_MAST_HEIGHT_M,
                                   config.SUB_MAST_RCS_FACTOR))
        for namespace, actor, height_m, rcs in candidates:
            dx, dy = actor.x - observer_x, actor.y - observer_y
            distance = math.hypot(dx, dy)
            if distance > min(range_nm, config.radar_horizon_nm(altitude_m, height_m)):
                continue
            sinr = radar_physics.sinr(distance, range_nm, rcs_factor=rcs,
                                      domain="surface", **conditions)
            tag, key = tag_prefix + namespace, int(actor.sensor_seed)
            if detrand.u01(self.seed, tag, key, tick) >= radar_physics.pd_from_sinr(sinr):
                continue
            bearing = (math.degrees(math.atan2(dx, -dy))
                       + config.MPA_RADAR_BEARING_ERR_DEG
                       * detrand.normal(self.seed, tag + "-brg", key, tick)) % 360.0
            measured = max(0.0, distance * (1.0 + config.MPA_RADAR_RANGE_ERR_FRAC
                                            * detrand.normal(self.seed, tag + "-rng",
                                                             key, tick)))
            track_id = id_prefix + self._observation_key(namespace, actor.id)
            self.air_picture.observe(
                track_id=track_id, kind="SURFACE", target_id=actor.id, source=source,
                bearing=bearing, range_nm=measured, observer_x=observer_x,
                observer_y=observer_y, course=None, quality=.6, now=self.sim_t,
                label=track_id, bearing_uncertainty_deg=config.MPA_RADAR_BEARING_ERR_DEG)
        self._aircraft_radar_rafts(observer_x, observer_y, altitude_m, range_nm,
                                   conditions, tag_prefix, tick)
