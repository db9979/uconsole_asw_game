"""The crewed submarine's orders: trim and ballast, damage control, tubes and
firing, decoy, ping, blow, surfacing, snorkel, air, mast, silent running and
bottoming (``Sub.command_*``), with the tube and air upkeep they drive.

Moved verbatim out of ``src/enemies/sub.py`` (a mixin of ``Sub``) to keep that
module within the line limit; every method works on the ``Sub`` it is mixed
into.
"""

import math

from src.core import config
from src.sensors.platform import MAST_DEPTH_M, PlatformObservation

# A crewed boat keeps at most this many fired torpedoes waiting for launch.
SUB_MAX_PENDING_TORPEDOES = 2


class SubCommandsMixin:
    """Crew orders of ``Sub`` (see the module note)."""

    def command_trim_auto(self, enabled):
        """Crew: the engineer keeps the boat trimmed, or the crew does."""
        if not self._crew_ready():
            return "not_ready"
        return self.ballast.set_auto(enabled)

    def command_ballast(self, tank, direction):
        """Crew: flood (+1) or pump out (-1) the regulating tank, or move
        trim water forward (+1) or aft (-1); switches the automatic trim off."""
        if not self._crew_ready():
            return "not_ready"
        return self.ballast.step(tank, direction)

    def command_dc_team(self, team, compartment, task):
        """Crew: send a damage-control team to a compartment with a task."""
        if not self._crew_ready():
            return "not_ready"
        return self.damage_control.order_team(team, compartment, task)

    def command_bulkhead(self, compartment, closed):
        """Crew: shut (or open) a compartment's bulkheads."""
        if not self._crew_ready():
            return "not_ready"
        return self.damage_control.set_bulkhead(compartment, closed)

    @property
    def crew_tubes(self):
        """The crew's flood state per tube (``[state, seconds left]``), or None
        when nobody crews the boat (the AI's tubes fire and reload by themselves)."""
        crew = self.crew
        tubes = getattr(crew, "tubes", None) if self.manual else None
        if (not tubes or self.weapon_battery is None
                or len(tubes) != len(self.weapon_battery.tubes)):
            return None
        return tubes

    def _update_tubes(self, dt: float, tubes, was_loading) -> None:
        for index, row in enumerate(tubes):
            tube = self.weapon_battery.tubes[index]
            if was_loading[index] and tube.loaded_weapon_key is not None:
                self.crew.event("tube_loaded", tube=f"{index + 1}")
            if tube.loaded_weapon_key is None and row[0] != "dry":
                tubes[index] = ["dry", 0.0]
            elif row[0] == "flooding":
                left = max(0.0, row[1] - dt)
                tubes[index] = ["flooded", 0.0] if left <= 1e-9 else ["flooding", left]
                if left <= 1e-9:
                    self.crew.event("tube_flooded", tube=f"{index + 1}")

    def _tube_order_ready(self):
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if self.crew_tubes is None:
            return "not_ready"
        if self.damage_control.down("bow"):
            return "uboot_compartment_down"     # torpedo room flooded or burning
        return None

    def command_load_tube(self, tube=None):
        """Load one empty tube from the racks (the first empty one by default)."""
        reason = self._tube_order_ready()
        if reason is not None:
            return reason
        battery = self.weapon_battery
        if tube is None:
            tube = next((item.index for item in battery.tubes
                         if item.loaded_weapon_key is None
                         and item.loading_weapon_key is None), None)
            if tube is None:
                return "uboot_tubes_full"
        if type(tube) is not int or not 0 <= tube < len(battery.tubes):
            return "invalid_value"
        row = battery.tubes[tube]
        if row.loaded_weapon_key is not None or row.loading_weapon_key is not None:
            return "uboot_tubes_full"
        if not battery.load_tube(tube):
            return "no_torpedoes"
        self.crew_tubes[tube] = ["dry", 0.0]
        return True

    def command_flood_tube(self, tube=None, quiet: bool = False):
        """Flood a loaded tube and open its outer door: only a flooded tube fires.
        Flooding takes ``UBOOT_TUBE_FLOOD_S`` and is a short, audible transient;
        quiet flooding takes ``UBOOT_TUBE_FLOOD_QUIET_S`` and is heard only close."""
        reason = self._tube_order_ready()
        if reason is not None:
            return reason
        battery, tubes = self.weapon_battery, self.crew_tubes
        if tube is None:
            tube = next((item.index for item in battery.tubes
                         if item.loaded_weapon_key is not None
                         and tubes[item.index][0] == "dry"), None)
            if tube is None:
                return "uboot_no_dry_tube"
        if type(tube) is not int or not 0 <= tube < len(battery.tubes):
            return "invalid_value"
        if battery.tubes[tube].loaded_weapon_key is None or tubes[tube][0] != "dry":
            return "uboot_no_dry_tube"
        tubes[tube] = ["flooding", float(config.UBOOT_TUBE_FLOOD_QUIET_S if quiet
                                         else config.UBOOT_TUBE_FLOOD_S)]
        self.flood_transient(bool(quiet))
        return True

    def fire_readiness(self, bearing=None, salvo: int = 1):
        """Why a crew torpedo shot is impossible now, or None when ready."""
        if (not self.manual or self.sunk or self.state in ("SINKING", "SUNK")
                or self.mission_peace):
            # Scenario 13 is peacetime: the tubes stay closed.
            return "not_ready"
        if self.damage_control.down("bow"):
            return "uboot_compartment_down"     # torpedo room flooded or burning
        if self.torpedoes_left <= 0:
            return "no_torpedoes"
        if self.torpedoes_left < salvo:
            return "no_torpedoes"
        if self.weapon_battery is not None and self.weapon_battery.ready_count < salvo:
            return "reloading"
        if len(self.pending_torpedoes) + salvo > SUB_MAX_PENDING_TORPEDOES:
            return "reloading"
        tubes = self.crew_tubes
        if tubes is not None and sum(
                row[0] == "flooded" and self.weapon_battery.tubes[index].loaded_weapon_key
                is not None for index, row in enumerate(tubes)) < salvo:
            return "uboot_tube_dry"
        if bearing is not None and self.weapon_battery is not None:
            launcher = self.runtime_catalog.launchers[self.weapon_battery.launcher_key]
            arc_center = (self.course + launcher.arc_center_deg) % 360.0
            if abs(config.angle_diff_deg(bearing, arc_center)) \
                    > launcher.arc_width_deg / 2.0:
                return "out_of_arc"
        return None

    def command_fire(self, bearing, range_nm=None, target_course=None,
                     target_speed_kn=None, now: float = 0.0, *, depth_m=None,
                     salvo: int = 1):
        """Fire one torpedo down a crew-chosen bearing.

        ``range_nm`` places the guidance datum; with a crew solution
        (``target_course``/``target_speed_kn``) the shot is led as the AI's
        interception course.  All values are crew estimates, never truth.
        """
        numbers = [value for value in (bearing, range_nm, target_course,
                                       target_speed_kn, depth_m) if value is not None]
        if type(salvo) is not int or salvo not in (1, 2):
            return "invalid_value"
        if bearing is None or any(
                type(value) not in (int, float) or isinstance(value, bool)
                or not math.isfinite(value) for value in numbers):
            return "invalid_value"
        if (not 0.0 <= bearing < 360.0
                or (range_nm is not None and not 0.05 <= range_nm <= 40.0)
                or (target_course is not None and not 0.0 <= target_course < 360.0)
                or (target_speed_kn is not None and not 0.0 <= target_speed_kn <= 60.0)
                or ((target_course is None) != (target_speed_kn is None))
                or (target_course is not None and range_nm is None)
                or (depth_m is not None and not config.UBOOT_TORPEDO_MIN_DEPTH_M
                    <= depth_m <= config.UBOOT_TORPEDO_MAX_DEPTH_M)):
            return "invalid_value"
        reason = self.fire_readiness(bearing, salvo)
        if reason is not None:
            return reason
        x = y = None
        if range_nm is not None:
            x = self.x + range_nm * math.sin(math.radians(bearing))
            y = self.y - range_nm * math.cos(math.radians(bearing))
        observation = PlatformObservation(
            track_id="CREW", domain="sonar", source="SONAR",
            observer_x=self.x, observer_y=self.y, bearing=float(bearing),
            range_nm=range_nm, x=x, y=y, course=target_course,
            speed_kn=target_speed_kn, depth_m=None, quality=1.0, signal=0.0,
            last_seen=now, bearing_uncertainty_deg=None,
            range_uncertainty_nm=None, depth_uncertainty_m=None, label=None)
        launched = self._fire_salvo(observation, salvo)
        if not launched:
            return "not_ready"
        for _ in range(launched):
            self.ballast.torpedo_away()
        # Crew presets on the rows just loaded: run depth, and a two-torpedo
        # spread either side of the fire-control course.
        first = len(self.pending_torpedoes) - launched
        for index in range(first, len(self.pending_torpedoes)):
            row = list(self.pending_torpedoes[index])
            if depth_m is not None:
                row[3] = float(depth_m)
            if launched == 2:
                # Each torpedo gets its own datum, turned about the boat by
                # the same angle, so the wire keeps the spread open.
                offset = config.UBOOT_SALVO_SPREAD_DEG * (-1 if index == first else 1)
                row[2] = (row[2] + offset) % 360.0
                if row[4] is not None and row[5] is not None:
                    angle = math.radians(offset)
                    dx, dy = row[4] - self.x, row[5] - self.y
                    row[4] = self.x + dx * math.cos(angle) - dy * math.sin(angle)
                    row[5] = self.y + dx * math.sin(angle) + dy * math.cos(angle)
            self.pending_torpedoes[index] = tuple(row)
        return True

    def command_decoy(self):
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if (self.countermeasure_store is None or self._decoy_cd > 0.0
                or self.pending_decoys):
            return "not_ready"
        if not self.countermeasure_store.fire():
            return "no_decoys"
        self.pending_decoys.append((self.x, self.y))
        self._decoy_cd = self.decoy_profile.cooldown_s
        return True

    def command_ping(self):
        """Transmit once: every ship in reach hears it on the next update."""
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        self._manual_ping_pending = True
        return True

    def command_blow(self):
        """Blow main ballast with the one high-pressure air charge."""
        if not self.manual or self.sunk or self.state in ("SINKING", "SUNK"):
            return "not_ready"
        if self.emergency_ascent or self.depth <= 30.0:
            return "not_ready"
        result = self.ballast.blow()
        if result is not True:
            return result
        self.blow_available = False
        self.emergency_ascent = True
        self.transient_left = max(self.transient_left, 20.0)
        # Up and stay up: the crew orders a depth again to flood and dive.
        self.order_depth = config.UBOOT_MBT_SURFACE_DEPTH_M
        if self.crew is not None and self.ballast.blows_left() == 0:
            self.crew.event("hp_air_low")
        return True

    @property
    def surfaced(self) -> bool:
        """Fully up: hull and conning tower above the water."""
        return not self.sunk and self.depth <= config.UBOOT_SURFACED_DEPTH_M

    def command_surface(self, on):
        """Crew: surface (once up, the low-pressure blower empties the main
        ballast) or, near the surface, a crash dive."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if not on:
            return self.command_crash_dive()
        if self.damage_control.down("control"):
            return "uboot_compartment_down"
        self.crew.bottomed = False
        self.order_depth = 0.0
        return True

    def command_crash_dive(self):
        """Crew: alarm dive from the surface or snorkel depth: masts and snorkel
        down, vents open, full ahead and down to ``UBOOT_CRASH_DIVE_DEPTH_M``.
        Blown tanks hold the boat up until the vents have flooded them."""
        if not self._crew_ready():
            return "not_ready"
        if self.depth > config.UBOOT_MBT_SURFACE_DEPTH_M + 2.0:
            return "uboot_not_surfaced"
        self.crew.mast = False
        self.crew.bottomed = False
        if self.snorkeling:
            self.endurance.stop_snorkel()
        self.order_depth = config.UBOOT_CRASH_DIVE_DEPTH_M
        self.order_speed = float(self.motion.maximum_speed_kn)
        self.transient_left = max(self.transient_left, config.UBOOT_CRASH_DIVE_NOISE_S)
        self.crew.event("crash_dive")
        return True

    @property
    def snorkeling(self) -> bool:
        return self.endurance is not None and self.endurance.phase == "SNORKEL"

    @property
    def snorkel_rate(self) -> str:
        """How hard the snorkel run works: the AI always charges in full; a
        crew charges at its ordered rate, and dry bunkers leave only the fans."""
        endurance = self.endurance
        if endurance is None or not self.manual:
            return "full"
        if endurance.generator_kw() <= 0.0:
            return "vent"
        return endurance.charge_rate

    def _snorkel_lines(self) -> list:
        scale = config.UBOOT_CHARGE_LINE_SCALE[self.snorkel_rate]
        return [(hz, amp * scale, width) for hz, amp, width in config.UBOOT_SNORKEL_LINES
                if scale > 0.0]

    def crew_efficiency(self) -> float:
        """The torpedo gang's performance: the boat's air (1.0 without an air
        model) and its empty posts (``weapons_crew_factor``, set by the game
        from the wounded, not saved)."""
        air = 1.0 if self.endurance is None else self.endurance.air.efficiency()
        return air * self.weapons_crew_factor

    def _update_air(self, dt: float) -> None:
        """Breathe, scrub and air the boat; the AI's crew also answers foul air."""
        endurance = self.endurance
        airing = (endurance.phase in ("SNORKEL", "RADIO")
                  and self.depth <= endurance.profile.snorkel_depth_m
                  + endurance.DEPTH_TOLERANCE_M) or (self.manual and self.surfaced)
        notices = endurance.air.update(dt, ventilating=airing, automatic=not self.manual)
        if not self.manual:
            if (endurance.air.level() == "danger"
                    and endurance.phase in ("SUBMERGED", "AIP")):
                # Foul air: the boat must come up and air, whatever the battery.
                endurance.return_depth_m = max(self.depth, endurance.profile.snorkel_depth_m)
                endurance.phase = "ASCENDING"
            return
        if self.crew is None:
            return
        for key in notices:
            self.crew.event(key)
        # Bunker level at the previous step (display state only: a loaded boat
        # starts from its current level and so announces nothing).
        fuel = endurance.fuel_kwh / max(endurance.fuel_capacity_kwh, 1e-9)
        fuel_before = getattr(self, "_fuel_seen", fuel)
        self._fuel_seen = fuel
        if fuel <= 0.0 < fuel_before:
            self.crew.event("fuel_empty")
        elif fuel <= config.UBOOT_FUEL_LOW_FRACTION < fuel_before:
            self.crew.event("fuel_low")

    def command_charge_rate(self, rate):
        """Crew: snorkel charge rate (full, half, or only airing the boat)."""
        if rate not in config.UBOOT_CHARGE_RATES:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_snorkel"
        return self.endurance.set_charge_rate(rate)

    def command_absorber(self):
        """Crew: fit a fresh CO2 absorber set."""
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_air_stores"
        return self.endurance.air.change_absorber()

    def command_o2_candle(self):
        """Crew: light an oxygen candle."""
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_air_stores"
        return self.endurance.air.burn_candle()

    def _crew_ready(self) -> bool:
        return (self.manual and self.crew is not None and not self.sunk
                and self.state not in ("SINKING", "SUNK"))

    def command_snorkel(self, on):
        """Crew: raise the snorkel and run the diesels (or stop them)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if self.endurance is None:
            return "uboot_no_snorkel"           # nuclear boat: no diesels
        if not on:
            self.endurance.stop_snorkel()
            return True
        if self.damage_control.down("engine"):
            return "uboot_compartment_down"
        if self.depth > self.endurance.profile.snorkel_depth_m + 1.0:
            return "uboot_too_deep"
        self.crew.bottomed = False
        if self.order_depth > config.UBOOT_SURFACED_DEPTH_M:
            # Surfaced (or surfacing) the diesels run in the open air.
            self.order_depth = self.endurance.profile.snorkel_depth_m
        self.endurance.start_snorkel(self.depth)
        return True

    def command_mast(self, on):
        """Crew: raise the ESM/radar-warning mast (periscope depth only)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if on and self.depth > MAST_DEPTH_M:
            return "uboot_mast_depth"
        if on and self.damage_control.down("control"):
            return "uboot_compartment_down"     # control room out: no masts
        self.crew.mast = on
        return True

    def command_silent(self, on):
        """Crew: silent running (speed ceiling, the lurker's quiet)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        self.crew.silent = on
        return True

    def command_bottom(self, on):
        """Crew: lie the boat on the bottom (all stop, 3 m keel clearance)."""
        if type(on) is not bool:
            return "invalid_value"
        if not self._crew_ready():
            return "not_ready"
        if not on:
            self.crew.bottomed = False
            self.order_depth = self.depth
            return True
        if self.last_bottom_m is None or self.last_bottom_m > self.stype.max_depth_m:
            return "uboot_too_deep"
        if self.snorkeling:
            self.endurance.stop_snorkel()
        self.crew.bottomed = True
        self.order_speed = 0.0
        return True
