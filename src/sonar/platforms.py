"""Duck-typed sonar adapters for a crewed submarine's sonar workstation.

``SonarSystem`` was written from the frigate's point of view: its observer
is anything with a position, course, speed and self noise, and its targets
are anything radiating LOFAR lines.  A crewed submarine listens with the
same system, so it needs

* ``SubSonarPlatform`` - the boat as the listening observer (its hull array
  sits at the boat's own depth, which is what makes the layer matter), and
* ``OwnShipAcousticSource`` / ``OwnTorpedoAcousticSource`` - the player
  frigate and its running torpedoes as radiating targets.  The frigate has
  no radiated-noise model of its own (nothing ever listened to it through
  ``SonarSystem`` before); it radiates like the catalogue's German CODOG
  frigate, read from ``data/contacts/warships.json``.

These adapters read the live entities only inside the simulation's sensor
update, exactly like every other sonar target.  They never leave the
simulation: crews only ever see the resulting ``Contact`` measurements.
"""

import math

from src.core import config
from src.data import fingerprint as fingerprint_mod
from src.enemies.surface import SurfaceShip
from src.physics import submarine as sub_physics

# The frigate radiates like the catalogue's German CODOG frigate (F123).
OWNSHIP_SIGNATURE_KEY = "warship_30"
# Sonar target IDs of the adapters: disjoint from subs (1...), animals
# (1000...), surface ships (5000...), decoys (1000000...) and enemy
# torpedoes (2000000...).
OWNSHIP_TARGET_ID = 900_000
OWN_TORPEDO_TARGET_BASE = 3_000_000
# Radiated-level steps of the own cavitation and quiet state (gameplay tuning).
OWNSHIP_CAVITATION_DB = 6.0
OWNSHIP_QUIET_MODE_DB = 4.0
# Fixed fingerprint seed: the frigate's tonal offsets never change.
_OWNSHIP_FINGERPRINT_SEED = 0x5F123


def _bearing(tgt, observer) -> float:
    return math.degrees(math.atan2(tgt.x - observer.x,
                                   -(tgt.y - observer.y))) % 360.0


class SubSonarPlatform:
    """A crewed submarine seen as a ``SonarSystem`` observer."""

    quiet_mode = False

    def __init__(self, sub):
        self.sub = sub

    @property
    def x(self) -> float:
        return self.sub.x

    @property
    def y(self) -> float:
        return self.sub.y

    @property
    def course(self) -> float:
        return self.sub.course

    @property
    def speed(self) -> float:
        return self.sub.speed

    @property
    def depth(self) -> float:
        return self.sub.depth

    @property
    def sonar_depth_m(self) -> float:
        """The hull array listens at the boat's own depth."""
        return max(0.0, float(self.sub.depth))

    @property
    def cavitating(self) -> bool:
        return bool(self.sub.cavitating)

    def noise_level(self) -> float:
        return self.sub.noise_level()

    def passive_sonar_range_nm(self, target_quiet: float = 0.5,
                               sea_state: int = 0) -> float:
        """Same self-noise law as ``Ship.passive_sonar_range_nm``."""
        own_penalty = 1.0 - 0.8 * self.noise_level()
        if self.cavitating:
            own_penalty *= config.CAVITATION_PASSIVE_FACTOR
        target_bonus = 1.0 + 0.8 * (1.0 - target_quiet)
        sea = 1.0 - config.SEA_STATE_SONAR_FACTOR * max(0, sea_state - 1)
        return config.SONAR_PASSIVE_BASE_NM * own_penalty * target_bonus * sea


class OwnShipAcousticSource:
    """The player frigate as a radiating sonar target."""

    id = OWNSHIP_TARGET_ID
    kind = "surface"
    # SurfaceShip's radiated-noise model, driven by the frigate's own state.
    lofar_lines = SurfaceShip.lofar_lines
    broadband = SurfaceShip.broadband
    acoustic_signature = SurfaceShip.acoustic_signature
    quiet_factor = SurfaceShip.quiet_factor
    noise_level = SurfaceShip.noise_level
    distance_nm = SurfaceShip.distance_nm
    bearing_from_frigate = SurfaceShip.bearing_from_frigate

    def __init__(self, ship, damage, runtime_catalog):
        self._ship = ship
        self._damage = damage
        self.runtime_catalog = runtime_catalog
        self.signature_key = OWNSHIP_SIGNATURE_KEY
        self.profile = runtime_catalog.surfaces[OWNSHIP_SIGNATURE_KEY]
        self.sensor_seed = _OWNSHIP_FINGERPRINT_SEED
        self.fingerprint = fingerprint_mod.roll_from_seed(
            self.sensor_seed, self.profile.acoustic)

    @property
    def x(self) -> float:
        return self._ship.x

    @property
    def y(self) -> float:
        return self._ship.y

    @property
    def course(self) -> float:
        return self._ship.course

    @property
    def speed(self) -> float:
        return self._ship.speed

    depth = 5.0

    @property
    def sunk(self) -> bool:
        return bool(self._damage.ship_sunk)

    @property
    def damage(self) -> float:
        return float(self._damage.total)

    @property
    def hull_length_m(self) -> float:
        return SurfaceShip.hull_length_m.fget(self)

    def source_level_offset_db(self) -> float:
        """The catalogue class's speed law (as SurfaceShip), plus the own
        cavitation and quiet-state machinery."""
        level = sub_physics.source_speed_db(
            self.speed, max(1.0, float(self.profile.speed_kn[1])))
        if self._ship.cavitating:
            level += OWNSHIP_CAVITATION_DB
        if self._ship.quiet_mode:
            level -= OWNSHIP_QUIET_MODE_DB
        return level


class OwnTorpedoAcousticSource:
    """A running frigate torpedo as a radiating sonar target."""

    torpedo_class = "frigate"
    kind = "torpedo"

    def __init__(self, torpedo):
        self._torpedo = torpedo
        self.id = OWN_TORPEDO_TARGET_BASE + int(torpedo.idx)
        self.sensor_seed = self.id

    @property
    def x(self) -> float:
        return self._torpedo.x

    @property
    def y(self) -> float:
        return self._torpedo.y

    @property
    def depth(self) -> float:
        return self._torpedo.depth

    @property
    def course(self) -> float:
        return self._torpedo.course

    @property
    def speed(self) -> float:
        return self._torpedo.speed_kn * self._torpedo.speed_fraction()

    @property
    def sunk(self) -> bool:
        return self._torpedo.state != "RUN"

    def source_level_offset_db(self) -> float:
        return self._torpedo.source_level_offset_db()

    def quiet_factor(self) -> float:
        return self._torpedo.quiet_factor()

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        return self._torpedo.lofar_lines(t_sim)

    def broadband(self) -> dict:
        return {}

    def acoustic_signature(self) -> str:
        return "" if self.sunk else "mechanisch · hochfrequentes Kreischen (Torpedo?)"

    def distance_nm(self, observer) -> float:
        return math.hypot(self.x - observer.x, self.y - observer.y)

    def bearing_from_frigate(self, observer) -> float:
        return _bearing(self, observer)
