"""W2: Akustische Dekoy – driftet vom U-Boot weg und maskiert es kurz.

Parameter (Lebensdauer, Speed, Rauschlinien) kommen aus dem Kontakt-Katalog.
"""

import math
import random

from src.core import config
from src.data.catalog import CATALOG
from src.weapons.torpedo import underwater_path_blocked
from src.physics.geo import FrigateRelativeMixin


DECOY_SWEEP_FRACTION = 0.02
DECOY_SWEEP_PERIOD_S = 30.0


class Decoy(FrigateRelativeMixin):
    """Sonar-Objekt wie Sub/Animal (Duck-Typing), aber ohne KI-Fahrplan."""

    _next_id = 1000000  # Separate from surface contacts (which start at 5000).

    def __init__(self, x_nm: float, y_nm: float, depth_m: float,
                 rng: random.Random, profile=None, acoustic=None,
                 source_id: int | None = None):
        self.id = Decoy._next_id
        Decoy._next_id += 1
        self.kind = "decoy"
        self.rng = rng
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.source_id = source_id
        profile = profile or CATALOG.get_decoy("decoy")
        self.profile = profile
        self.acoustic = acoustic or CATALOG.acoustic_for(profile.key)
        self.x = x_nm
        self.y = y_nm
        self.depth = depth_m
        self.course = rng.uniform(0.0, 360.0)
        self.speed = config.kn_to_nm_per_s(profile.speed_kn)
        self.life = profile.life_s
        self.dead = False

    @property
    def sunk(self) -> bool:
        return self.dead

    def update(self, dt: float, world) -> None:
        if self.dead:
            return
        self.life -= dt
        if self.life <= 0.0:
            self.dead = True
            return
        ox, oy = self.x, self.y
        self.x += self.speed * dt * math.sin(math.radians(self.course))
        self.y -= self.speed * dt * math.cos(math.radians(self.course))
        # W2: Meeresstroemung - reiner Driftzusatz, kein Antrieb/keine Steuerung.
        current = getattr(world, "current_vec", None)
        if current is not None:
            cu, cv = current(self.x, self.y)
            self.x += config.kn_to_nm_per_s(cu) * dt
            self.y -= config.kn_to_nm_per_s(cv) * dt
        world_size = world.size_nm
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)
        if underwater_path_blocked(world, ox, oy, self.depth, self.x, self.y, self.depth):
            self.x, self.y = ox, oy
            self.dead = True

    def quiet_factor(self) -> float:
        # Lautes, leichtes Rauschen: maskiert das U-Boot im LOFAR
        return 0.15

    @property
    def speed_kn(self) -> float:
        return self.speed * 3600.0

    def battery_fraction(self) -> float:
        return max(0.0, min(1.0, self.life / max(self.profile.life_s, 1e-6)))

    def source_level_offset_db(self) -> float:
        """Emission weakens as the battery drains (amplifier voltage)."""
        return 20.0 * math.log10(max(0.1, math.sqrt(self.battery_fraction())))

    def acoustic_signature(self) -> str:
        if self.dead:
            return ""
        text = self.profile.signature_text
        return f"mechanisch · {text} (Dekoy?)"

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """Replica tonals with a slow frequency modulation (+/-2 %, 30 s) and
        a level that follows the battery."""
        if self.dead:
            return []
        sweep = 1.0 + DECOY_SWEEP_FRACTION * math.sin(
            2.0 * math.pi * t_sim / DECOY_SWEEP_PERIOD_S
            + (self.sensor_seed % 360) * math.pi / 180.0)
        level = math.sqrt(self.battery_fraction())
        return [(v[0] * sweep, v[1] * level, *v[2:]) for v in self.profile.lines]

    def broadband(self) -> dict:
        if self.dead:
            return {}
        signature = self.acoustic
        if signature is None or signature.broadband is None:
            return {}
        level, low, high = signature.broadband
        return {"level": level, "low_hz": low, "high_hz": high}
