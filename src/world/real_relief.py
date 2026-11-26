"""Real land heights around the real coastline sectors
(``data/coastlines/real_relief.json.gz``, built by
``tools/build_real_relief.py`` from NOAA ETOPO1).

Display only: the coasts and mountains on the horizon
(``src/ui/horizon.py``).  Nothing in the simulation reads a height, so a
missing file just leaves the horizon with its assumed coast heights.
"""

from __future__ import annotations

import base64
import gzip
import json
import math
import os
import zlib
from collections import OrderedDict

import numpy as np

from src.world.projection import NM_PER_DEGREE

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "data", "coastlines", "real_relief.json.gz")
# The relief around a sector's square (NM) that the horizon may show.
MARGIN_NM = 45.0
_CACHE_MAX = 2
_data = None
_cache = OrderedDict()


def _load():
    global _data
    if _data is None:
        try:
            with gzip.open(PATH, "rt", encoding="utf-8") as source:
                _data = json.load(source)
        except (OSError, ValueError):
            _data = {}
    return _data


class Relief:
    """Land heights (m) of one sector on a latitude/longitude grid, read at
    world positions in NM (the sector's own projection,
    ``src/world/projection.py``)."""

    def __init__(self, data: dict, center_lat: float, center_lon: float,
                 world_size_nm: float = 500.0):
        tile = int(data["tile"])
        scale_m = float(data["height_scale_m"])
        self.center_lat, self.center_lon = float(center_lat), float(center_lon)
        self.cos_lat = math.cos(math.radians(self.center_lat))
        # Game NM per catalog NM (a world may be built larger or smaller).
        self.scale = float(world_size_nm) / 500.0
        half = 250.0 + MARGIN_NM
        lat0 = max(-90, math.floor(self.center_lat - half / NM_PER_DEGREE))
        lat1 = min(89, math.floor(self.center_lat + half / NM_PER_DEGREE))
        span = half / (NM_PER_DEGREE * self.cos_lat)
        lon0 = math.floor(self.center_lon - span)
        lon1 = math.floor(self.center_lon + span)
        self.lat0, self.lon0, self.per_deg = lat0, lon0, tile
        grid = np.zeros(((lat1 - lat0 + 1) * tile, (lon1 - lon0 + 1) * tile), dtype=np.float32)
        tiles = data.get("tiles", {})
        for lat in range(lat0, lat1 + 1):
            for lon in range(lon0, lon1 + 1):
                text = tiles.get(f"{lat},{(lon + 180) % 360 - 180}")
                if text is None:
                    continue
                raw = np.frombuffer(zlib.decompress(base64.b64decode(text)), dtype=np.uint8)
                block = (raw.astype(np.float32) / 255.0) ** 2 * scale_m
                row, column = (lat - lat0) * tile, (lon - lon0) * tile
                grid[row:row + tile, column:column + tile] = block.reshape(tile, tile)
        self.grid = grid
        self.peak_m = float(grid.max()) if grid.size else 0.0

    def heights(self, x, y):
        """Land height (m, 0 over water) at world positions ``x``, ``y``
        (NM, arrays of one shape), bilinear between the grid points."""
        x = np.asarray(x, dtype=float) / self.scale
        y = np.asarray(y, dtype=float) / self.scale
        lat = self.center_lat + (250.0 - y) / NM_PER_DEGREE
        lon = self.center_lon + (x - 250.0) / (self.cos_lat * NM_PER_DEGREE)
        rows, columns = self.grid.shape
        fi = (lat - self.lat0) * self.per_deg
        fj = (lon - self.lon0) * self.per_deg
        i0 = np.clip(np.floor(fi).astype(int), 0, rows - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, columns - 2)
        ti = np.clip(fi - i0, 0.0, 1.0)
        tj = np.clip(fj - j0, 0.0, 1.0)
        g = self.grid
        top = g[i0, j0] * (1 - tj) + g[i0, j0 + 1] * tj
        bottom = g[i0 + 1, j0] * (1 - tj) + g[i0 + 1, j0 + 1] * tj
        inside = (fi >= 0) & (fi <= rows - 1) & (fj >= 0) & (fj <= columns - 1)
        return np.where(inside, top * (1 - ti) + bottom * ti, 0.0)


def for_coast(coast) -> Relief | None:
    """The relief of a real-sector coastline, None for any other coast (or
    without the data file).  The last few are kept."""
    metadata = getattr(coast, "metadata", None) or {}
    center = metadata.get("center")
    if not isinstance(center, dict):
        return None
    size = float(getattr(coast, "world_size_nm", 500.0))
    key = (metadata.get("sector_id"), center.get("latitude"), center.get("longitude"), size)
    relief = _cache.get(key)
    if relief is None:
        data = _load()
        if not data.get("tiles"):
            return None
        relief = Relief(data, center["latitude"], center["longitude"], size)
        _cache[key] = relief
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    return relief
