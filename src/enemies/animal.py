"""Meerestiere: Falschkontakte im Sonar (Captain's Log §6.2).

Profile kommen aus dem Kontakt-Katalog (src/data/catalog.py).
"""

import math
import random

from src.core import config
from src.data.catalog import CATALOG


class AnimalType:
    def __init__(self, key, name, depth_min, depth_max, speed_kn, quiet, size_nm):
        self.key = key
        self.name = name
        self.depth_min = depth_min
        self.depth_max = depth_max
        self.speed_kn = speed_kn
        self.quiet = quiet      # 0 = laut ... 1 = stumm (biologischer Lärm)
        self.size_nm = size_nm  # Kontaktgröße im Sonar


ANIMAL_TYPES = {
    p.key: AnimalType(p.key, p.name, p.depth_min, p.depth_max,
                      p.speed_kn, p.quiet, p.size_nm)
    for p in CATALOG.animals.values()
}


class Animal:
    """Tier: wandert langsam, erzeugt passive Sonarkontakte."""

    _next_id = 1000

    def __init__(self, x_nm: float, y_nm: float, atype_key: str,
                 rng: random.Random, depth_m: float = None):
        self.id = Animal._next_id
        Animal._next_id += 1
        self.kind = "animal"
        self.rng = rng
        self.sensor_seed = int(rng.randint(0, 2**31 - 1))
        self.atype = ANIMAL_TYPES[atype_key]
        self.x = x_nm
        self.y = y_nm
        self.depth = depth_m if depth_m is not None \
            else rng.uniform(self.atype.depth_min, self.atype.depth_max)
        self.course = rng.uniform(0, 360)
        self.target_course = self.course
        self.target_depth = self.depth
        self.speed = self.atype.speed_kn * rng.uniform(0.7, 1.1)
        self.turn_left = rng.uniform(*self._decision_interval())
        self.turn_delta = 0.0
        self.dead = False

    # Duck-Type-Interface wie Sub (für Sonar + Torpedo-Führung)
    @property
    def sunk(self) -> bool:
        return self.dead

    @property
    def state(self) -> str:
        return "DEAD" if self.dead else "RUN"

    def hit(self) -> None:
        self.dead = True

    def quiet_factor(self) -> float:
        return self.atype.quiet

    def lofar_lines(self, t_sim: float = 0.0) -> list:
        """W1: Biologische LOFAR-Signatur (Frequenz, Amplitude, Breite)."""
        if self.dead:
            return []
        profile = CATALOG.animals.get(self.atype.key)
        if profile is None:
            return []
        return [tuple(v) for v in profile.lines]

    def acoustic_signature(self) -> str:
        """M9: Hörbare Geräusch-Signatur (biologischer Kontakt)."""
        if self.dead:
            return ""
        profile = CATALOG.animals.get(self.atype.key)
        sig = profile.signature_text if profile else "unbekannt"
        return f"biologisch · {sig}"

    def update(self, dt: float, world) -> None:
        if self.dead:
            return
        self.turn_left -= dt
        if self.turn_left <= 0:
            self.turn_left = self.rng.uniform(*self._decision_interval())
            spread = 35.0 if self.atype.key == "whale" else 20.0
            if self.atype.key == "jellyfish":
                spread = 8.0
            self.target_course = (self.course
                                  + self.rng.uniform(-spread, spread)) % 360.0
            self.target_depth = self.rng.uniform(
                self.atype.depth_min, self.atype.depth_max)
            self.speed = self.atype.speed_kn * self.rng.uniform(0.7, 1.1)
        turn_rate = {"whale": .5, "fish_school": .8,
                     "jellyfish": .1}.get(self.atype.key, .5)
        diff = config.angle_diff_deg(self.target_course, self.course)
        self.course = (self.course + config.clamp(
            diff, -turn_rate * dt, turn_rate * dt)) % 360.0
        depth_rate = {"whale": 1.0, "fish_school": .2,
                      "jellyfish": .03}.get(self.atype.key, .2)
        self.depth += config.clamp(
            self.target_depth - self.depth, -depth_rate, depth_rate) * dt

        v = config.kn_to_nm_per_s(self.speed) * dt
        nx = self.x + v * math.sin(math.radians(self.course))
        ny = self.y - v * math.cos(math.radians(self.course))
        if world.on_land(nx, ny):
            self.target_course = (self.course + 120.0) % 360.0
        else:
            self.x, self.y = nx, ny

        world_size = world.size_nm
        if self.x < 0 or self.x > world_size:
            self.course = (360.0 - self.course) % 360.0
            self.x = config.clamp(self.x, 0.0, world_size)
        if self.y < 0 or self.y > world_size:
            self.course = (180.0 - self.course) % 360.0
            self.y = config.clamp(self.y, 0.0, world_size)

    def _decision_interval(self) -> tuple:
        return {
            "whale": (300.0, 900.0),
            "fish_school": (120.0, 480.0),
            "jellyfish": (1200.0, 3600.0),
        }.get(self.atype.key, (300.0, 900.0))

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0
