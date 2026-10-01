"""Oberflächenschiffe: Zivil (AIS/ESM) + feindliche Kriegsschiffe (KAMPFSCHIFF).

Einheitliche Klasse; feindliche Variante lochert um Ankerpunkt und feuert
ASM-Salven. Akustik und Profil aus dem Kontakt-Katalog (src/data/catalog.py).
"""

import math
import random

from src.core import config
from src.physics import submarine as sub_physics

# Hostile-hull damage effects (percent): radar and missile systems are lost,
# and progressive flooding runs above the threshold.
NPC_RADAR_LOST_DAMAGE = 60.0
NPC_WEAPONS_LOST_DAMAGE = 75.0
NPC_FLOOD_THRESHOLD = 30.0
NPC_FLOOD_RATE = 0.01          # %/s at full damage
from src.data import catalog
from src.data import fingerprint as fingerprint_mod
from src.sensors.platform import (
    PlatformObservation,
    PlatformSensorSuite,
    machine_acoustics,
    motion_limits,
    side_datalink_group,
    snapshot_observation,
)
from src.weapons.asw import WeaponBattery

CATALOG = catalog.CATALOG


class SurfaceShip:
    """Ziviles Oberflächenschiff oder feindliches Kriegsschiff."""

    _next_id = 5000

    def __init__(self, x_nm: float, y_nm: float, rng: random.Random,
                 hostile: bool = False, profile=None, *, side: str = None,
                 doctrine: str = None, runtime_catalog=None):
        self.id = SurfaceShip._next_id
        SurfaceShip._next_id += 1
        self.rng = rng
        self.side = side or ("hostile" if hostile else "neutral")
        self.doctrine = doctrine or (
            "surface_combatant" if self.side == "hostile" else "surface_transit")
        runtime_catalog = runtime_catalog or CATALOG
        self.runtime_catalog = runtime_catalog
        self.profile = (profile if profile is not None
                        else runtime_catalog.pick_surface(
                            rng, hostile=self.side == "hostile"))
        self.signature_key = self.profile.key
        if self.profile.category == "KAMPFSCHIFF":
            self.name = self.profile.name
            self.callsign = self.profile.name
        else:
            pool = self.profile.callsigns or ("MV UNBEKANNT",)
            self.callsign = rng.choice(pool)
            self.name = self.callsign
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.fingerprint = fingerprint_mod.roll_from_seed(
            self.sensor_seed, self.profile.acoustic)
        self.motion = motion_limits(
            runtime_catalog, self.signature_key,
            cruise_speed=self.profile.speed_kn[1],
            maximum_speed=self.profile.speed_kn[1], turn_rate=1.0,
            acceleration=0.03)
        # W2: hydrodynamische Fahrtantwort (Exponential-Verzug, siehe Ship) -
        # Zeitkonstante aus der katalogspezifischen Beschleunigung abgeleitet,
        # damit unterschiedliche Schiffstypen ihre relative Trägheit behalten.
        self.speed_tau_s = max(5.0, self.motion.cruise_speed_kn
                               / max(0.001, self.motion.acceleration_kn_s) / 3.0)
        systems = runtime_catalog.profile_systems.get(self.signature_key)
        self.legacy_observation_model = bool(
            systems is not None and systems.machine_key is not None
            and runtime_catalog.machines[
                systems.machine_key].propulsor_type == "unknown")
        self.sensor_suite = PlatformSensorSuite(
            runtime_catalog, self.signature_key, self.sensor_seed,
            side=self.side, doctrine=self.doctrine,
            datalink_group=side_datalink_group(self.side))
        self.x = x_nm
        self.y = y_nm
        self.depth = 5.0
        self.course = rng.uniform(0.0, 360.0)
        self.speed = rng.uniform(*self.profile.speed_kn)
        self.target_course = self.course
        self.target_speed = self.speed
        self.emitter = rng.random() < self.profile.esm_prob
        self.turn_left = rng.uniform(600.0, 1800.0)
        self.turn_delta = 0.0
        self.sunk = False
        self.damage = 0.0
        self.sunk_score_awarded = False
        # Von einem echten AIS-Kontakt gesteuert (MMSI); unterdrueckt die
        # zufaellige Kurs-/Geschwindigkeitswahl in _update_civil, siehe
        # LiveTrafficManager.
        self.live_mmsi: int | None = None
        # Detached, bounded metadata received for a real AIS contact. It is
        # diagnostic/transient state and intentionally not part of the save.
        self.live_ais_details: dict[str, object] = {}
        self.sensor_contact = None
        self.sensor_contact_age = config.RADAR_TRACK_STALE_S
        # Kriegsschiff: Loiter + ASM
        self.anchor = None  # (x, y) – vom Game gesetzt
        # The consort of a group hunt (src/core/game_consort.py): the
        # frigate's OPZ sets its course and speed and decides its weapons.
        self.commanded = False
        self.waypoint = None
        self.orbit_direction = rng.choice((-1, 1))
        self.attack_left = self.profile.asm_cooldown_s
        self.pending_asm: list[tuple[float, float, int]] = []
        self.asroc_battery = WeaponBattery.from_catalog(
            runtime_catalog, self.signature_key, "asroc")
        self.pending_asroc: list[dict] = []
        self.asw_last_seen = -1.0
        # W2: Torpedo-Alarm -> harte Wende weg von der Bedrohung
        self._torpedo_evade_left = 0.0
        self._torpedo_threat_bearing = 0.0
        # Acoustic torpedo decoys carried by combatants (saved).
        self.countermeasures_left = (config.WARSHIP_TORPEDO_DECOYS
                                     if doctrine == "surface_combatant" else 0)

    @property
    def hostile(self) -> bool:
        return self.side == "hostile"

    @property
    def speed_cap_kn(self) -> float:
        """Propulsion damage caps top speed, mirroring Sub's degradation."""
        return self.motion.maximum_speed_kn * (1.0 - 0.25 * self.damage / 100.0)

    @property
    def hull_length_m(self) -> float:
        catalog = self.runtime_catalog
        systems = catalog.profile_systems.get(self.signature_key)
        reference = (catalog.references.get(systems.reference_key)
                     if systems is not None and systems.reference_key else None)
        return float(reference.length_m) if reference and reference.length_m else 120.0

    def source_level_offset_db(self) -> float:
        """Radiated level versus the catalog cruise speed (40 log v)."""
        return sub_physics.source_speed_db(
            self.speed, max(self.motion.cruise_speed_kn, 1.0))

    @property
    def radar_emitting(self) -> bool:
        return (not self.sunk and self.emitter
                and self.damage < NPC_RADAR_LOST_DAMAGE)

    @property
    def ais_transmitting(self) -> bool:
        return not self.sunk and self.doctrine == "surface_transit"

    # --- Torpedo-Treffer ---

    def hit(self, amount: float | None = None) -> None:
        """Warhead damage (shock-factor amount from the fuze, else legacy)."""
        if self.sunk:
            return
        self.damage = min(100.0, self.damage + (34.0 if amount is None else amount))
        if self.damage >= 100.0:
            self.sunk = True

    def _progressive_flooding(self, dt: float) -> None:
        """A holed hull keeps taking water in proportion to its damage."""
        if NPC_FLOOD_THRESHOLD < self.damage < 100.0:
            self.damage = min(100.0, self.damage + NPC_FLOOD_RATE * dt * (
                self.damage - NPC_FLOOD_THRESHOLD) / (100.0 - NPC_FLOOD_THRESHOLD))
            if self.damage >= 100.0:
                self.sunk = True

    def alert_torpedo(self, bearing_deg: float) -> None:
        """W2: Torpedostart gehört -> Wende weg von der Bedrohung, Flankfahrt."""
        if self.sunk:
            return
        self._torpedo_evade_left = config.WARSHIP_TORPEDO_EVADE_S
        self._torpedo_threat_bearing = bearing_deg % 360.0

    # --- Bewegung ---

    def update(self, dt: float, observation, world, asw_observation=None) -> None:
        if self.sunk:
            return
        self._progressive_flooding(dt)
        if self.sunk:
            return
        if self.doctrine == "surface_combatant":
            self._update_combatant(dt, observation, world, asw_observation)
        else:
            self._update_civil(dt, world)

    def _update_civil(self, dt: float, world) -> None:
        if self._torpedo_evade_left > 0.0:
            # A detonation close by (src/enemies/traffic.py): run from it.
            self._torpedo_evade_left = max(0.0, self._torpedo_evade_left - dt)
            self.target_course = (self._torpedo_threat_bearing + 180.0) % 360.0
            self.target_speed = self.speed_cap_kn
            if self._torpedo_evade_left <= 0.0:
                self.target_speed = sum(self.profile.speed_kn) * 0.5
        elif self.live_mmsi is None and self.turn_delta >= 1.0:
            # On a shipping lane: src/enemies/traffic.py orders the course.
            self.turn_left -= dt
        elif self.live_mmsi is None:
            self.turn_left -= dt
            if self.turn_left <= 0:
                self.turn_left = self.rng.uniform(600.0, 1800.0)
                self.target_course = (self.course
                                      + self.rng.uniform(-30.0, 30.0)) % 360.0
                self.target_speed = self.rng.uniform(
                    self.profile.speed_kn[0], self.speed_cap_kn)
        self._steer(dt, min(.5, self.motion.turn_rate_deg_s), world)
        self._move(dt, world)

    def _update_combatant(self, dt: float, observation, world,
                          asw_observation=None) -> None:
        if self.asroc_battery is not None:
            self.asroc_battery.update(dt)
        self.sensor_contact_age = min(config.RADAR_TRACK_STALE_S,
                                      self.sensor_contact_age + dt)
        if observation is not None and not isinstance(observation, PlatformObservation):
            target = observation
            observation = (snapshot_observation(self, target, domain="radar")
                           if self.emitter
                           and self.distance_nm(target) <= config.WARSHIP_ASM_RANGE_NM
                           and not getattr(
                               world, "land_blocks_line", lambda *args: False)(
                                   self.x, self.y, target.x, target.y)
                           else None)
        fresh_observation = (observation is not None and (
            observation.track_id == "LEGACY"
            or observation.last_seen > self.sensor_suite.last_consumed_s))
        if (fresh_observation
                and observation.x is not None and observation.y is not None
                and (observation.range_nm is None
                     or observation.range_nm <= config.WARSHIP_ASM_RANGE_NM)):
            self.sensor_contact = (observation.x, observation.y)
            self.sensor_contact_age = 0.0
            self.sensor_suite.last_consumed_s = max(
                self.sensor_suite.last_consumed_s, observation.last_seen)
        if self.sensor_contact_age >= config.RADAR_TRACK_STALE_S:
            self.sensor_contact = None
        if self._torpedo_evade_left > 0.0:
            self._torpedo_evade_left = max(0.0, self._torpedo_evade_left - dt)
            self.target_course = (self._torpedo_threat_bearing + 180.0) % 360.0
            self.target_speed = self.speed_cap_kn
            self._steer(dt, self.motion.turn_rate_deg_s, world)
            self._move(dt, world)
            self._maybe_asm(dt)
            if not self.commanded:
                self._maybe_asroc(asw_observation)
            return
        if self.commanded:
            self._steer(dt, self.motion.turn_rate_deg_s, world)
            self._move(dt, world)
            return
        dist = (math.hypot(self.sensor_contact[0] - self.x, self.sensor_contact[1] - self.y)
                if self.sensor_contact is not None else float("inf"))
        bearing = (math.degrees(math.atan2(self.sensor_contact[0] - self.x,
                                           -(self.sensor_contact[1] - self.y))) % 360.0
                   if self.sensor_contact is not None else self.course)
        if dist < 18.0:
            self.target_course = (bearing + 180.0) % 360.0
            self.target_speed = self.speed_cap_kn
        elif dist <= config.WARSHIP_ASM_RANGE_NM:
            self.target_course = (bearing + self.orbit_direction * 90.0) % 360.0
            self.target_speed = min(18.0, self.speed_cap_kn)
        elif self.anchor is not None:
            ax, ay = self.anchor
            radius = min(20.0, max(8.0, self.profile.loiter_nm * .75))
            if self.waypoint is None or math.hypot(
                    self.x - self.waypoint[0], self.y - self.waypoint[1]) < 1.0:
                angle = math.atan2(self.y - ay, self.x - ax) \
                    + self.orbit_direction * math.radians(60.0)
                self.waypoint = (ax + radius * math.cos(angle),
                                 ay + radius * math.sin(angle))
            wx, wy = self.waypoint
            self.target_course = math.degrees(
                math.atan2(wx - self.x, -(wy - self.y))) % 360.0
            self.target_speed = min(16.0, self.speed_cap_kn)
        self._steer(dt, self.motion.turn_rate_deg_s, world)
        self._move(dt, world)
        self._maybe_asm(dt)
        self._maybe_asroc(asw_observation)

    def _maybe_asroc(self, observation: PlatformObservation | None) -> None:
        """Queue one ASROC using only a fresh local/datalink sonar datum."""
        if (self.side != "friendly" or self.asroc_battery is None
                or observation is None or observation.domain != "sonar"
                or observation.fix_source not in ("ACTIVE", "TMA", "BUOY", "FUSED")
                or observation.last_seen <= self.asw_last_seen):
            return
        self.asw_last_seen = observation.last_seen
        if observation.x is not None and observation.y is not None:
            datum_x, datum_y = observation.x, observation.y
        elif observation.range_nm is not None:
            datum_x = observation.observer_x + observation.range_nm * math.sin(
                math.radians(observation.bearing))
            datum_y = observation.observer_y - observation.range_nm * math.cos(
                math.radians(observation.bearing))
        else:
            return
        self.fire_asroc_at(datum_x, datum_y, observation.depth_m)

    def asroc_weapon_key(self) -> str | None:
        if self.asroc_battery is None:
            return None
        return next((key for key in self.asroc_battery.weapon_keys
                     if self.runtime_catalog.weapons[key].weapon_type == "asroc"), None)

    def fire_asroc_at(self, datum_x: float, datum_y: float, depth_m=None) -> bool:
        """Queue one ASROC on a datum (own sonar, or passed over the datalink)
        when it lies inside the weapon's engagement range."""
        if self.side != "friendly" or self.sunk:
            return False
        weapon_key = self.asroc_weapon_key()
        if weapon_key is None:
            return False
        low, high = self.runtime_catalog.weapons[weapon_key].engagement_range_nm
        distance = math.hypot(datum_x - self.x, datum_y - self.y)
        if not low <= distance <= high or self.pending_asroc:
            return False
        if self.asroc_battery.fire(weapon_key) is None:
            return False
        self.pending_asroc.append({
            "x": self.x, "y": self.y, "datum_x": datum_x,
            "datum_y": datum_y, "weapon_key": weapon_key,
            "target_depth_m": depth_m if depth_m is not None else 60.0,
        })
        return True

    def _steer(self, dt: float, max_rate: float, world=None) -> None:
        # Safety owns the final steering order, after tactical/route orders.
        if world is not None:
            land = getattr(world, "on_land", lambda x, y: False)
            blocked = getattr(world, "land_blocks_line", lambda x0, y0, x1, y1: land(x1, y1))
            lookahead = max(1.0, self.speed / 6.0)
            for offset in (0.0, 60.0, 120.0, 180.0):
                course = (self.course + self.orbit_direction * offset) % 360.0
                x = self.x + lookahead * math.sin(math.radians(course))
                y = self.y - lookahead * math.cos(math.radians(course))
                if not blocked(self.x, self.y, x, y):
                    if offset:
                        self.target_course = course
                    break
        # Nomoto steering as on the own ship: steady turn rate grows linearly
        # with speed (constant turning circle), no turning without way on.
        speed_factor = config.clamp(self.speed / 10.0, 0.0, 1.5)
        diff = config.angle_diff_deg(self.target_course, self.course)
        effective_rate = max_rate * speed_factor
        self.course = (self.course + config.clamp(
            diff, -effective_rate * dt, effective_rate * dt)) % 360.0
        # W2: Schub/Widerstand-Gleichgewicht als Exponential-Verzug (geschlossene
        # Form -> dt-unabhaengig, siehe Ship.update()).
        # Added resistance in waves lowers the attainable speed.
        sea_state = float(getattr(world, "effective_sea_state",
                                  getattr(world, "sea_state", 0.0))) if world else 0.0
        cap = self.speed_cap_kn * sub_physics.wave_speed_fraction(
            sea_state, self.hull_length_m, self.hull_length_m / 8.0)
        target = min(self.target_speed, cap)
        if abs(target - self.speed) <= 0.05:
            self.speed = target
        else:
            self.speed = target + (self.speed - target) \
                * math.exp(-dt / self.speed_tau_s)
        self.speed = config.clamp(self.speed, 0.0, self.speed_cap_kn)

    def _move(self, dt: float, world) -> None:
        on_land = getattr(world, "on_land", lambda x, y: False)
        v = config.kn_to_nm_per_s(self.speed) * dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None:
            cu, cv = current(self.x, self.y)
            nx += config.kn_to_nm_per_s(cu) * dt
            ny -= config.kn_to_nm_per_s(cv) * dt
        world_size = world.size_nm
        if (on_land(nx, ny) or getattr(world, "land_blocks_line", lambda *args: False)(
                self.x, self.y, nx, ny)):
            self.target_course = (self.course + 90.0) % 360.0
            return
        self.x, self.y = nx, ny
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)

    def _maybe_asm(self, dt: float) -> None:
        if (self.side != "hostile" or self.profile.asm_salvo[0] <= 0
                or self.damage >= NPC_WEAPONS_LOST_DAMAGE):
            return
        self.attack_left -= dt
        if self.attack_left > 0.0:
            return
        if self.sensor_contact is None:
            return
        dist = math.hypot(self.sensor_contact[0] - self.x, self.sensor_contact[1] - self.y)
        if dist <= config.WARSHIP_ASM_RANGE_NM:
            n = self.rng.randint(self.profile.asm_salvo[0],
                                 self.profile.asm_salvo[1])
            self.pending_asm.append((self.x, self.y, n))
            self.attack_left = self.profile.asm_cooldown_s

    # --- Akustik ---

    def quiet_factor(self) -> float:
        if self.sunk:
            return 0.0
        return max(0.05, 0.45 - self.speed / 60.0)

    def noise_level(self) -> float:
        return 1.0 - self.quiet_factor()

    def acoustic_signature(self) -> str:
        if self.sunk:
            return ""
        sig = self.profile.acoustic
        base = sig.signature_text or "unbekannter Antrieb"
        if self.speed >= 18.0:
            freq = "Frequenz hoch (volle Fahrt)"
        elif self.speed >= 10.0:
            freq = "Frequenz mittel"
        else:
            freq = "Frequenz niedrig (Langfahrt)"
        detail = (f" · DEMON {sig.tonal_band_hz[0]:.0f}-"
                  f"{sig.tonal_band_hz[1]:.0f} Hz")
        return f"mechanisch · {base} · {freq}{detail}"

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        if self.sunk:
            return []
        profiled = machine_acoustics(
            self.runtime_catalog, self.signature_key, self.speed)
        if profiled is not None:
            lines, _ = profiled
            return list(lines) + ([(55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0)]
                                  if self.damage > 30.0 else [])
        lines = []
        v = max(0.0, self.speed)
        sig = self.profile.acoustic
        fp = self.fingerprint
        vmax = max(1.0, self.profile.speed_kn[1])
        if v > 0.3:
            f = (fp.rate_scale
                 * (sig.tonal_band_hz[0]
                    + (sig.tonal_band_hz[1] - sig.tonal_band_hz[0])
                    * min(1.0, v / vmax))
                 + fp.offsets[0])
            f = max(2.0, f)
            amp = 0.20 + 0.60 * min(1.0, v / 24.0)
            lines.append((f, amp, 1.5))
            if v > 8.0:
                lines.append((f * 2.0 + fp.offsets[1], amp * 0.45, 1.2))
                lines.append((f * 3.0 + fp.offsets[2], amp * 0.25, 1.0))
            for hz, a, width in sig.secondary_tonals:
                lines.append((hz, a * min(1.0, v / 6.0), width))
        if self.damage > 30.0:
            lines.append((55.0, 0.25 + 0.45 * self.damage / 100.0, 4.0))
        return lines

    def broadband(self) -> dict:
        sig = self.profile.acoustic
        profiled = machine_acoustics(
            self.runtime_catalog, self.signature_key, self.speed)
        if profiled is not None:
            _, broadband = profiled
            if self.sunk or broadband is None:
                return {}
            return {"level": min(1.0, broadband[0]
                                 + 0.10 * self.damage / 100.0),
                    "low_hz": broadband[1], "high_hz": broadband[2]}
        if self.sunk or sig.broadband is None:
            return {}
        v = max(0.0, self.speed)
        vmax = max(1.0, self.profile.speed_kn[1])
        level = self.fingerprint.bb_level * (0.2 + 0.8 * min(1.0, v / vmax))
        level = min(1.0, level + 0.10 * (self.damage / 100.0))
        return {"level": min(1.0, level),
                "low_hz": sig.broadband[1],
                "high_hz": sig.broadband[2]}

    # --- Geometrie ---

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    @property
    def sensor_domain(self) -> str:
        return "surface"
