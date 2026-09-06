"""W3: Kuestenlinien & Inseln – Landgeometrie, Kollisionsabfrage, Airbases.

Daten: data/coastlines/region.json (stilisierter Nordsee/Ostsee-Sektor).
Koordinaten in NM, y nach Sueden. 0° = Nord (oben).
"""

import json
import math
import os
import random

from src.core import config

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "data", "coastlines",
    "region.json")


def _point_in_poly(x: float, y: float, pts: list) -> bool:
    """Ray-Casting (Punkt in Polygon)."""
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if ((y1 > y) != (y2 > y)):
            xt = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < xt:
                inside = not inside
    return inside


def _distance_to_segment(x: float, y: float, first: tuple,
                         second: tuple) -> float:
    x1, y1 = first
    x2, y2 = second
    dx, dy = x2 - x1, y2 - y1
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def _irregular_profile(rng: random.Random, size: float, count: int,
                       low: float, high: float) -> list:
    """A correlated 1-D coastline profile, expressed in world coordinates."""
    value = rng.uniform(low, high)
    out = []
    for index in range(count):
        target = rng.uniform(low, high)
        value = value * 0.58 + target * 0.42
        # Broad waves keep the coast visibly irregular without sharp spikes.
        wave = math.sin(index * rng.uniform(0.55, 0.85) + rng.random())
        out.append((index * size / (count - 1),
                    max(low, min(high, value + wave * size * 0.012))))
    return out


def _island_points(rng: random.Random, cx: float, cy: float,
                   radius: float, count: int = 12) -> list:
    points = []
    phase = rng.uniform(0.0, math.tau)
    for index in range(count):
        angle = phase + index * math.tau / count
        r = radius * rng.uniform(0.62, 1.15)
        points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    return points


class Landmass:
    def __init__(self, name: str, nation: str, points: list):
        self.name = name
        self.nation = nation
        self.points = points
        self.centroid = (sum(p[0] for p in points) / len(points),
                         sum(p[1] for p in points) / len(points))

    def contains(self, x: float, y: float) -> bool:
        return _point_in_poly(x, y, self.points)


class Coastline:
    def __init__(self, data: dict, world_size_nm: float = config.WORLD_SIZE_NM):
        self.world_size_nm = world_size_nm
        self.landmasses = [
            Landmass(m["name"], m.get("nation", "ZIVIL"), m["points"])
            for m in data.get("landmasses", [])]
        self.airbases = data.get("airbases", [])
        self._bathymetry = data.get("bathymetry")

    @classmethod
    def load(cls, path: str = None) -> "Coastline":
        """Load the fixed legacy coastline (or another file in that format)."""
        path = path or _DEFAULT_PATH
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {"landmasses": [], "airbases": []}
        return cls(data, world_size_nm=float(data.get("world_nm", config.WORLD_SIZE_NM)))

    @classmethod
    def generate(cls, seed: int, size_nm: float = 500.0) -> "Coastline":
        """Generate deterministic land, airbases and bathymetry for a square sea."""
        size = float(size_nm)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError("size_nm must be a positive finite number")
        rng = random.Random(seed)
        count = 19

        west_profile = _irregular_profile(
            rng, size, count, size * 0.09, size * 0.19)
        east_widths = _irregular_profile(
            rng, size, count, size * 0.09, size * 0.19)
        north_profile = _irregular_profile(
            rng, size, count, size * 0.07, size * 0.15)

        west = [(0.0, 0.0)] + [(width, along)
                               for along, width in west_profile] + [(0.0, size)]
        east_coast = [(size - width, along) for along, width in east_widths]
        east = [(size, 0.0), (size, size)] + list(reversed(east_coast))
        north = [(0.0, 0.0), (size, 0.0)] + [
            (along, width) for along, width in reversed(north_profile)]

        landmasses = [
            {"name": "Westmark", "nation": "HANSE", "points": west},
            {"name": "Ostmark", "nation": "BOREN", "points": east},
            {"name": "Nordkap", "nation": "SKANDIA", "points": north},
        ]

        island_sites = ((0.27, 0.68), (0.73, 0.74), (0.31, 0.43),
                        (0.70, 0.39))
        island_count = rng.randint(2, 4)
        for index, (fx, fy) in enumerate(rng.sample(island_sites, island_count), 1):
            cx = (fx + rng.uniform(-0.025, 0.025)) * size
            cy = (fy + rng.uniform(-0.025, 0.025)) * size
            radius = rng.uniform(0.014, 0.032) * size
            landmasses.append({
                "name": f"Insel {index}", "nation": "ZIVIL",
                "points": _island_points(rng, cx, cy, radius),
            })

        def profile_base(profile: list, index: int, from_far_edge: bool = False):
            along, width = profile[index]
            across = width * 0.72
            return (size - across, along) if from_far_edge else (across, along)

        west_base_1 = profile_base(west_profile, 8)
        west_base_2 = profile_base(west_profile, 14)
        east_base = profile_base(east_widths, 10, from_far_edge=True)
        north_x, north_width = north_profile[11]
        airbases = [
            {"id": "ab_westhaven", "name": "WESTHAVEN", "nation": "HANSE",
             "x": west_base_1[0], "y": west_base_1[1]},
            {"id": "ab_nordhavn", "name": "NORDHAVN", "nation": "HANSE",
             "x": west_base_2[0], "y": west_base_2[1]},
            {"id": "ab_gothost", "name": "GOTH-OST", "nation": "BOREN",
             "x": east_base[0], "y": east_base[1]},
            {"id": "ab_ostland", "name": "OSTLAND", "nation": "SKANDIA",
             "x": north_x, "y": north_width * 0.72},
        ]

        coast = cls({"landmasses": landmasses, "airbases": airbases}, size)
        coast._bathymetry = coast._generate_bathymetry(rng)
        return coast

    def _distance_to_coast(self, x: float, y: float) -> float:
        nearest = self.world_size_nm
        for landmass in self.landmasses:
            for index, first in enumerate(landmass.points):
                second = landmass.points[(index + 1) % len(landmass.points)]
                nearest = min(nearest, _distance_to_segment(x, y, first, second))
        return nearest

    def _generate_bathymetry(self, rng: random.Random) -> dict:
        grid_size = 17
        phase_x = rng.uniform(0.0, math.tau)
        phase_y = rng.uniform(0.0, math.tau)
        values = []
        for row in range(grid_size):
            line = []
            y = row * self.world_size_nm / (grid_size - 1)
            for column in range(grid_size):
                x = column * self.world_size_nm / (grid_size - 1)
                if self.on_land(x, y):
                    line.append(0.0)
                    continue
                distance = self._distance_to_coast(x, y)
                shelf = 55.0 + 790.0 * (1.0 - math.exp(
                    -distance / (self.world_size_nm * 0.105)))
                variation = (75.0 * math.sin(column * 0.72 + phase_x)
                             + 55.0 * math.cos(row * 0.61 + phase_y)
                             + rng.uniform(-24.0, 24.0))
                line.append(max(35.0, min(1000.0, shelf + variation)))
            values.append(line)
        return {"size": grid_size, "values": values}

    def depth_m(self, x: float, y: float) -> float:
        """Return interpolated generated water depth, or zero on land."""
        if self.on_land(x, y):
            return 0.0
        if not self._bathymetry:
            raise ValueError("this coastline has no bathymetry")
        grid = self._bathymetry["values"]
        grid_size = int(self._bathymetry["size"])
        scale = (grid_size - 1) / self.world_size_nm
        fx = max(0.0, min(grid_size - 1.0, x * scale))
        fy = max(0.0, min(grid_size - 1.0, y * scale))
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(x0 + 1, grid_size - 1), min(y0 + 1, grid_size - 1)
        tx, ty = fx - x0, fy - y0
        top = grid[y0][x0] * (1.0 - tx) + grid[y0][x1] * tx
        bottom = grid[y1][x0] * (1.0 - tx) + grid[y1][x1] * tx
        return max(35.0, top * (1.0 - ty) + bottom * ty)

    @property
    def has_bathymetry(self) -> bool:
        return self._bathymetry is not None

    def to_dict(self) -> dict:
        """Canonical geometry snapshot for generator-independent save files."""
        return {
            "world_nm": self.world_size_nm,
            "landmasses": [
                {"name": land.name, "nation": land.nation,
                 "points": [[x, y] for x, y in land.points]}
                for land in self.landmasses
            ],
            "airbases": [dict(base) for base in self.airbases],
            "bathymetry": self._bathymetry,
        }

    # --- Abfragen ---

    def on_land(self, x: float, y: float) -> bool:
        if x < 0 or y < 0 or x > self.world_size_nm or y > self.world_size_nm:
            return True
        for m in self.landmasses:
            if m.contains(x, y):
                return True
        return False

    def landmass_at(self, x: float, y: float):
        for m in self.landmasses:
            if m.contains(x, y):
                return m
        return None

    def nearest_water(self, x: float, y: float,
                      max_radius_nm: float = 25.0) -> tuple:
        """Naechsten Wasser-Punkt (Spirale in 1-NM-Ringen)."""
        if not self.on_land(x, y):
            return x, y
        r = 1.0
        while r <= max_radius_nm:
            for i in range(8):
                ang = math.radians(i * 45.0 + r * 37.0)
                px, py = x + r * math.cos(ang), y + r * math.sin(ang)
                if not self.on_land(px, py) and \
                        0.0 <= px <= self.world_size_nm and \
                        0.0 <= py <= self.world_size_nm:
                    return px, py
            r += 1.0
        return x, y

    def contour_segments_in_circle(self, cx: float, cy: float,
                                   radius_nm: float) -> list:
        """Anonyme Kuestenkanten, exakt auf einen Kreis zugeschnitten."""
        radius = max(0.0, float(radius_nm))
        if radius <= 0.0:
            return []
        radius2 = radius * radius
        out = []
        for landmass in self.landmasses:
            points = landmass.points
            if len(points) < 2:
                continue
            for index, first in enumerate(points):
                second = points[(index + 1) % len(points)]
                x1, y1 = float(first[0]), float(first[1])
                x2, y2 = float(second[0]), float(second[1])
                dx, dy = x2 - x1, y2 - y1
                a = dx * dx + dy * dy
                if a <= 1e-12:
                    continue
                # Segment/Kreis-Schnitt; ein konvexer Kreis erzeugt hoechstens
                # ein zusammenhaengendes Teilsegment innerhalb der Reichweite.
                ox, oy = x1 - cx, y1 - cy
                b = 2.0 * (ox * dx + oy * dy)
                c = ox * ox + oy * oy - radius2
                disc = b * b - 4.0 * a * c
                cuts = [0.0, 1.0]
                if disc >= 0.0:
                    root = math.sqrt(max(0.0, disc))
                    for value in ((-b - root) / (2.0 * a),
                                  (-b + root) / (2.0 * a)):
                        if 0.0 < value < 1.0:
                            cuts.append(value)
                cuts = sorted(set(cuts))
                for lo, hi in zip(cuts, cuts[1:]):
                    middle = (lo + hi) * 0.5
                    mx, my = x1 + dx * middle, y1 + dy * middle
                    if (mx - cx) ** 2 + (my - cy) ** 2 > radius2 + 1e-9:
                        continue
                    start = (x1 + dx * lo, y1 + dy * lo)
                    end = (x1 + dx * hi, y1 + dy * hi)
                    if math.hypot(end[0] - start[0], end[1] - start[1]) > 1e-9:
                        out.append((start, end))
        return out

    def airbases_of(self, nation: str) -> list:
        return [a for a in self.airbases if a.get("nation") == nation]

    def hostile_base(self) -> dict:
        for a in self.airbases:
            if a.get("nation") == "BOREN":
                return a
        return {"id": "ab_fall", "name": "GOTH-OST", "nation": "BOREN",
                "x": 480.0, "y": 240.0}

    def friendly_bases(self) -> list:
        return self.airbases_of("HANSE")

    def neutral_base(self) -> dict:
        for a in self.airbases:
            if a.get("nation") == "SKANDIA":
                return a
        return {"id": "ab_fall2", "name": "OSTLAND", "nation": "SKANDIA",
                "x": 410.0, "y": 55.0}

    # --- Rendering (vom map_view aufgerufen) ---

    def land_points_px(self, view) -> list:
        """Alle Landmassen als List von Pixel-Polygonen (ohne Clipping)."""
        out = []
        for m in self.landmasses:
            out.append([view.world_to_screen(px, py) for px, py in m.points])
        return out

    def airbase_px(self, view) -> list:
        out = []
        for a in self.airbases:
            px, py = view.world_to_screen(a["x"], a["y"])
            out.append((a, px, py))
        return out
