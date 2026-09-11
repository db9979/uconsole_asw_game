"""Welt: Meer, Küsten (W3), Thermokline, Wetter, Tag/Nacht, Schallfeld (W2)."""

import math
import random

from src.core import config
from src.world.coastline import Coastline
from src.world.grounding import (DEFAULT_HULL_SPEC, grounding_contact,
                                 hull_is_safe, swept_grounding)


class World:
    """Segebiets-Modell.

    Tiefe (m) und Thermoklinentiefe sind raumabhängig, damit aktive Pings
    je nach Position unzuverlässig werden. W3: Küstenlinien/Inseln mit
    Land-Abfrage (Oberflächeneinheiten dürfen nicht in Land fahren).
    """

    def __init__(self, seed: int = 42, size_nm: float = config.WORLD_SIZE_NM,
                 coast: "Coastline | None" = None):
        self.rng = random.Random(seed)
        if coast is None:
            coast = Coastline.generate(seed, size_nm=size_nm)
        else:
            size_nm = coast.world_size_nm
        self.size_nm = size_nm
        self.coast = coast
        # Grobe Rausch-Felder (12 x 12 Zellen für ~40 NM Blöcke)
        grid_n = 12
        self._grid = grid_n
        self._depth = [[self.rng.uniform(200.0, 900.0) for _ in range(grid_n)]
                       for _ in range(grid_n)]
        self._thermo = [[self.rng.uniform(40.0, 120.0) for _ in range(grid_n)]
                        for _ in range(grid_n)]
        # Wetter & Tageszeit
        self.sea_state = self.rng.randint(2, 4)     # 0-6
        self.hour = float(self.rng.randint(6, 18))  # Uhrzeit 0-24
        self.weather_shift_timer = 0.0

    # --- Zugriff mit bilinearem Interpolieren ---

    def _cell(self, x_nm: float, y_nm: float, field) -> float:
        g = self._grid
        fx = x_nm / (self.size_nm / (g - 1))
        fy = y_nm / (self.size_nm / (g - 1))
        fx = min(max(fx, 0.0), g - 1.001)
        fy = min(max(fy, 0.0), g - 1.001)
        x0 = int(fx)
        y0 = int(fy)
        x1 = min(x0 + 1, g - 1)
        y1 = min(y0 + 1, g - 1)
        tx = fx - x0
        ty = fy - y0
        a = field[y0][x0]
        b = field[y0][x1]
        c = field[y1][x0]
        d = field[y1][x1]
        return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty

    def depth_m(self, x_nm: float, y_nm: float) -> float:
        if self.coast.has_bathymetry:
            return self.coast.depth_m(x_nm, y_nm)
        return self._cell(x_nm, y_nm, self._depth)

    def physical_depth_m(self, x_nm: float, y_nm: float) -> float:
        if self.coast.has_bathymetry:
            return self.coast.physical_depth_m(x_nm, y_nm)
        return self._cell(x_nm, y_nm, self._depth)

    def grounding_contact(self, x_nm, y_nm, course_deg,
                          hull=DEFAULT_HULL_SPEC):
        return grounding_contact(self, x_nm, y_nm, course_deg, hull)

    def hull_is_safe(self, x_nm, y_nm, course_deg, hull=DEFAULT_HULL_SPEC):
        return hull_is_safe(self, x_nm, y_nm, course_deg, hull)

    def swept_grounding(self, start, end, hull=DEFAULT_HULL_SPEC):
        return swept_grounding(self, start, end, hull)

    def nearest_safe_hull(self, x_nm: float, y_nm: float, course_deg: float,
                          hull=DEFAULT_HULL_SPEC,
                          max_radius_nm: float | None = None) -> tuple[float, float]:
        """Deterministically locate a footprint-safe start without randomness."""
        if self.hull_is_safe(x_nm, y_nm, course_deg, hull):
            return x_nm, y_nm
        maximum = self.size_nm if max_radius_nm is None else max_radius_nm
        radius = 1.0
        while radius <= maximum:
            for index in range(64):
                angle = math.radians(index * 137.50776405003785)
                px = x_nm + radius * math.cos(angle)
                py = y_nm + radius * math.sin(angle)
                if self.hull_is_safe(px, py, course_deg, hull):
                    return px, py
            radius += 1.0
        raise ValueError("no hull-safe start found")

    def thermocline_depth_m(self, x_nm: float, y_nm: float) -> float:
        measured = self._cell(x_nm, y_nm, self._thermo)
        return min(measured, max(10.0, self.depth_m(x_nm, y_nm) - 20.0))

    # --- W3: Land / Küsten ---

    def on_land(self, x_nm: float, y_nm: float) -> bool:
        return self.coast.on_land(x_nm, y_nm)

    def nearest_water(self, x_nm: float, y_nm: float) -> tuple:
        return self.coast.nearest_water(x_nm, y_nm)

    def landmass_at(self, x_nm: float, y_nm: float):
        return self.coast.landmass_at(x_nm, y_nm)

    def land_blocks_line(self, x1_nm: float, y1_nm: float,
                         x2_nm: float, y2_nm: float) -> bool:
        """Delegate a radar/HFDF-style terrain occlusion query."""
        return self.coast.land_blocks_line(x1_nm, y1_nm, x2_nm, y2_nm)

    def sonar_path_blocked(self, x1_nm: float, y1_nm: float,
                           source_depth_m: float, x2_nm: float, y2_nm: float,
                           target_depth_m: float,
                           clearance_m: float = 0.0) -> bool:
        """Delegate a straight-ray sonar terrain occlusion query."""
        return self.coast.sonar_path_blocked(
            x1_nm, y1_nm, source_depth_m, x2_nm, y2_nm, target_depth_m,
            clearance_m)

    # --- W2: Schallfeld ---

    def echo_delay_s(self, dist_nm: float) -> float:
        """Echolatenz eines Pings: 2*R / Schallgeschwindigkeit (Salzwasser)."""
        return (dist_nm * 1852.0 * 2.0) / config.SOUND_SPEED_M_S

    # --- Wetter / Tageszyklus ---

    def update(self, dt: float) -> None:
        # Eine Simulationssekunde ist bei 1x eine reale Sekunde.
        self.hour = (self.hour + dt * config.GAME_TIME_PER_SEC / 60.0) % 24.0
        self.weather_shift_timer += dt
        if self.weather_shift_timer > config.WEATHER_SHIFT_PERIOD_S:
            self.weather_shift_timer -= config.WEATHER_SHIFT_PERIOD_S
            d = self.rng.choice([-1, 0, 0, 1])
            self.sea_state = max(0, min(6, self.sea_state + d))

    def is_night(self) -> bool:
        return self.hour < 5.5 or self.hour >= 19.5

    def format_time(self) -> str:
        h = int(self.hour)
        m = int((self.hour - h) * 60)
        return f"{h:02d}:{m:02d}"
