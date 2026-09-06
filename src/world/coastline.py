"""W3: Kuestenlinien & Inseln - Landgeometrie, Kollisionsabfrage, Airbases.

Fixed data uses region.json; generated mode selects an offline real-world sector.
Koordinaten in NM, y nach Sueden. 0° = Nord (oben).
"""

from collections import OrderedDict
import json
import math
import os
import random

from src.core import config

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "data", "coastlines",
    "region.json")
_OCCLUSION_CACHE_LIMIT = 1024
_GEOMETRY_EPSILON = 1e-9


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


def _segment_intersection_parameters(first: tuple, second: tuple,
                                     edge_first: tuple,
                                     edge_second: tuple) -> list[float]:
    """Return positions where a path touches an edge, including collinear ends."""
    x1, y1 = first
    dx, dy = second[0] - x1, second[1] - y1
    x3, y3 = edge_first
    ex, ey = edge_second[0] - x3, edge_second[1] - y3
    cross = dx * ey - dy * ex
    qx, qy = x3 - x1, y3 - y1
    if abs(cross) > _GEOMETRY_EPSILON:
        t = (qx * ey - qy * ex) / cross
        u = (qx * dy - qy * dx) / cross
        if (-_GEOMETRY_EPSILON <= t <= 1.0 + _GEOMETRY_EPSILON
                and -_GEOMETRY_EPSILON <= u <= 1.0 + _GEOMETRY_EPSILON):
            return [max(0.0, min(1.0, t))]
        return []

    if abs(qx * dy - qy * dx) > _GEOMETRY_EPSILON:
        return []
    length2 = dx * dx + dy * dy
    if length2 <= _GEOMETRY_EPSILON:
        return []
    values = []
    for x, y in (edge_first, edge_second):
        t = ((x - x1) * dx + (y - y1) * dy) / length2
        if -_GEOMETRY_EPSILON <= t <= 1.0 + _GEOMETRY_EPSILON:
            values.append(max(0.0, min(1.0, t)))
    return values


class Landmass:
    def __init__(self, name: str, nation: str, points: list):
        self.name = name
        self.nation = nation
        self.points = points
        self.centroid = (sum(p[0] for p in points) / len(points),
                         sum(p[1] for p in points) / len(points))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        self.bounds = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, x: float, y: float) -> bool:
        left, top, right, bottom = self.bounds
        if x < left or x > right or y < top or y > bottom:
            return False
        return _point_in_poly(x, y, self.points)

    def contains_strict(self, x: float, y: float) -> bool:
        """Interior test which does not classify an exact coastline touch as land."""
        if not self.contains(x, y):
            return False
        for index, first in enumerate(self.points):
            second = self.points[(index + 1) % len(self.points)]
            if _distance_to_segment(x, y, first, second) <= _GEOMETRY_EPSILON:
                return False
        return True


class Coastline:
    def __init__(self, data: dict, world_size_nm: float = config.WORLD_SIZE_NM):
        self.world_size_nm = world_size_nm
        self.landmasses = [
            Landmass(m["name"], m.get("nation", "ZIVIL"), m["points"])
            for m in data.get("landmasses", [])]
        self.airbases = data.get("airbases", [])
        self._bathymetry = data.get("bathymetry")
        self.metadata = data.get("metadata")
        self._occlusion_cache = OrderedDict()

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
    def from_dict(cls, data: dict) -> "Coastline":
        """Restore a canonical snapshot produced by :meth:`to_dict`."""
        return cls(data, world_size_nm=float(
            data.get("world_nm", config.WORLD_SIZE_NM)))

    @classmethod
    def generate(cls, seed: int, size_nm: float = 500.0) -> "Coastline":
        """Select one of 128 prevalidated real 500-NM coastal sectors."""
        size = float(size_nm)
        if not math.isfinite(size) or size <= 0.0:
            raise ValueError("size_nm must be a positive finite number")
        from src.world.real_coast import sector_for_seed

        sector, provenance = sector_for_seed(seed)
        scale = size / 500.0
        data = {
            "landmasses": [
                {"name": land["name"], "nation": land["nation"],
                 "points": [[x * scale, y * scale] for x, y in land["points"]]}
                for land in sector["landmasses"]],
            "airbases": [dict(base, x=base["x"] * scale,
                              y=base["y"] * scale)
                         for base in sector.get("airbases", [])],
            "metadata": {"sector_id": sector["id"], "name": sector["name"],
                         "center": sector["center"], "countries": sector["countries"],
                         "land_ratio": sector["land_ratio"],
                         "provenance": provenance},
        }
        coast = cls(data, size)
        sector_number = int(sector["id"].rsplit("-", 1)[-1])
        coast._bathymetry = coast._generate_bathymetry(random.Random(sector_number))
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

    def _memoized_occlusion(self, key: tuple, calculate) -> bool:
        try:
            result = self._occlusion_cache.pop(key)
        except KeyError:
            result = bool(calculate())
            if len(self._occlusion_cache) >= _OCCLUSION_CACHE_LIMIT:
                self._occlusion_cache.popitem(last=False)
        self._occlusion_cache[key] = result
        return result

    @property
    def occlusion_cache_entries(self) -> int:
        """Current bounded memoization footprint, exposed for diagnostics."""
        return len(self._occlusion_cache)

    def clear_occlusion_cache(self) -> None:
        self._occlusion_cache.clear()

    @staticmethod
    def _canonical_line_key(first: tuple, second: tuple) -> tuple:
        return (first, second) if first <= second else (second, first)

    def _land_blocks_line(self, first: tuple, second: tuple) -> bool:
        size = self.world_size_nm
        if any(value < 0.0 or value > size for value in (*first, *second)):
            return True

        path_left, path_right = sorted((first[0], second[0]))
        path_top, path_bottom = sorted((first[1], second[1]))
        dx, dy = second[0] - first[0], second[1] - first[1]
        for landmass in self.landmasses:
            left, top, right, bottom = landmass.bounds
            if (right < path_left or left > path_right
                    or bottom < path_top or top > path_bottom):
                continue
            if (landmass.contains_strict(*first)
                    or landmass.contains_strict(*second)):
                return True

            cuts = [0.0, 1.0]
            for index, edge_first in enumerate(landmass.points):
                edge_second = landmass.points[(index + 1) % len(landmass.points)]
                cuts.extend(_segment_intersection_parameters(
                    first, second, edge_first, edge_second))
            cuts.sort()
            distinct = []
            for value in cuts:
                if not distinct or value - distinct[-1] > _GEOMETRY_EPSILON:
                    distinct.append(value)
            for start, end in zip(distinct, distinct[1:]):
                if end - start <= _GEOMETRY_EPSILON:
                    continue
                middle = (start + end) * 0.5
                if landmass.contains_strict(
                        first[0] + dx * middle, first[1] + dy * middle):
                    return True
        return False

    def land_blocks_line(self, x1: float, y1: float,
                         x2: float, y2: float) -> bool:
        """Whether mapped land blocks a radar/HFDF-style line.

        This is a 2-D gameplay approximation: terrain elevation, diffraction,
        antenna height and Earth curvature are intentionally not modeled. Exact
        coastline tangencies do not block, which avoids false positive contacts
        from low-resolution polygon edges. Paths outside the playable sector do.
        """
        values = tuple(float(value) for value in (x1, y1, x2, y2))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("line coordinates must be finite")
        first, second = values[:2], values[2:]
        line = self._canonical_line_key(first, second)
        return self._memoized_occlusion(
            ("land", *line), lambda: self._land_blocks_line(*line))

    def _depth_along_line(self, first: tuple, second: tuple, t: float) -> float:
        x = first[0] + (second[0] - first[0]) * t
        y = first[1] + (second[1] - first[1]) * t
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

    def _sonar_path_blocked(self, first: tuple, second: tuple,
                            source_depth: float, target_depth: float,
                            clearance: float) -> bool:
        if self._land_blocks_line(first, second):
            return True
        if not self._bathymetry:
            return False

        grid_size = int(self._bathymetry["size"])
        spacing = self.world_size_nm / (grid_size - 1)
        dx, dy = second[0] - first[0], second[1] - first[1]
        cuts = [0.0, 1.0]
        for axis_start, delta in ((first[0], dx), (first[1], dy)):
            if abs(delta) <= _GEOMETRY_EPSILON:
                continue
            for index in range(1, grid_size - 1):
                t = (index * spacing - axis_start) / delta
                if _GEOMETRY_EPSILON < t < 1.0 - _GEOMETRY_EPSILON:
                    cuts.append(t)
        cuts = sorted(set(cuts))

        def bottom_clearance(t: float) -> float:
            ray_depth = source_depth + (target_depth - source_depth) * t
            return self._depth_along_line(first, second, t) - ray_depth - clearance

        # Bilinear bathymetry restricted to a straight line is quadratic. Three
        # samples reconstruct it, allowing an exact minimum within each grid cell.
        for start, end in zip(cuts, cuts[1:]):
            middle = (start + end) * 0.5
            f0, fm, f1 = (bottom_clearance(start),
                          bottom_clearance(middle), bottom_clearance(end))
            if min(f0, fm, f1) <= _GEOMETRY_EPSILON:
                return True
            quadratic = 2.0 * (f0 + f1 - 2.0 * fm)
            linear = f1 - f0 - quadratic
            if quadratic > _GEOMETRY_EPSILON:
                local_t = -linear / (2.0 * quadratic)
                if 0.0 < local_t < 1.0:
                    global_t = start + (end - start) * local_t
                    if bottom_clearance(global_t) <= _GEOMETRY_EPSILON:
                        return True
        return False

    def sonar_path_blocked(self, x1: float, y1: float, source_depth_m: float,
                           x2: float, y2: float, target_depth_m: float,
                           clearance_m: float = 0.0) -> bool:
        """Whether land or interpolated seabed blocks a straight sonar ray.

        This deliberately models neither refraction nor multipath. Positive
        depths are below the surface; ``clearance_m`` reserves water below the
        ray. With no bathymetry, only exact coastline geometry can block.
        """
        values = tuple(float(value) for value in (
            x1, y1, source_depth_m, x2, y2, target_depth_m, clearance_m))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("sonar path values must be finite")
        first, second = values[:2], values[3:5]
        source_depth, target_depth, clearance = values[2], values[5], values[6]
        if source_depth < 0.0 or target_depth < 0.0 or clearance < 0.0:
            raise ValueError("depths and clearance must not be negative")
        if second < first:
            first, second = second, first
            source_depth, target_depth = target_depth, source_depth
        key = ("sonar", first, source_depth, second, target_depth, clearance)
        return self._memoized_occlusion(key, lambda: self._sonar_path_blocked(
            first, second, source_depth, target_depth, clearance))

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
            **({"metadata": self.metadata} if self.metadata is not None else {}),
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
            if a.get("gameplay_role") == "hostile":
                return a
        for a in self.airbases:
            if a.get("nation") == "BOREN":
                return a
        return {"id": "ab_fall", "name": "GOTH-OST", "nation": "BOREN",
                "x": 480.0, "y": 240.0}

    def friendly_bases(self) -> list:
        roles = [base for base in self.airbases
                 if base.get("gameplay_role") == "friendly"]
        return roles or self.airbases_of("HANSE")

    def neutral_base(self) -> dict:
        for a in self.airbases:
            if a.get("gameplay_role") == "neutral":
                return a
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
