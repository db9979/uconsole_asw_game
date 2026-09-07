"""W2: Akustische Dekoy – driftet vom U-Boot weg und maskiert es kurz.

Parameter (Lebensdauer, Speed, Rauschlinien) kommen aus dem Kontakt-Katalog.
"""

import math
import random

from src.core import config
from src.data.catalog import CATALOG
from src.weapons.torpedo import underwater_path_blocked


class Decoy:
    """Sonar-Objekt wie Sub/Animal (Duck-Typing), aber ohne KI-Fahrplan."""

    _next_id = 1000000  # Separate from surface contacts (which start at 5000).

    def __init__(self, x_nm: float, y_nm: float, depth_m: float,
                 rng: random.Random):
        self.id = Decoy._next_id
        Decoy._next_id += 1
        self.kind = "decoy"
        self.rng = rng
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        profile = CATALOG.get_decoy("decoy")
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

    def acoustic_signature(self) -> str:
        if self.dead:
            return ""
        text = CATALOG.get_decoy("decoy").signature_text
        return f"mechanisch · {text} (Dekoy?)"

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        if self.dead:
            return []
        return [tuple(v) for v in CATALOG.get_decoy("decoy").lines]

    def broadband(self) -> dict:
        if self.dead:
            return {}
        signature = CATALOG.acoustic_for("decoy")
        if signature is None or signature.broadband is None:
            return {}
        level, low, high = signature.broadband
        return {"level": level, "low_hz": low, "high_hz": high}

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0
