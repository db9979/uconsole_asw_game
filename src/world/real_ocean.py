"""Real water depths and the monthly surface layer of the real coastline
sectors (``data/coastlines/real_ocean.json.gz``, built by
``tools/build_real_ocean.py`` from NOAA ETOPO1 and the World Ocean Atlas
2023).

A sector without an entry (a custom map, a damaged file) falls back to the
synthetic model: callers get ``None``.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import math
import os

PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "coastlines", "real_ocean.json.gz")
# Grid points the game charts as water keep at least this depth (m): the
# 15-NM ETOPO mean of a coastal cell may hold only land.
MIN_WATER_DEPTH_M = 20.0
MAX_DEPTH_M = 10_000.0
# Mid-month days of the year (non-leap) for the monthly means.
_MID_MONTH = (16, 45, 75, 105, 136, 166, 197, 228, 258, 289, 319, 350)

_data = None
_failed = False


def _valid(data) -> bool:
    if not isinstance(data, dict) or data.get("schema") != 1:
        return False
    grid = data.get("grid")
    sectors = data.get("sectors")
    if type(grid) is not int or not 2 <= grid <= 257 or not isinstance(sectors, dict):
        return False
    for entry in sectors.values():
        depth = entry.get("depth") if isinstance(entry, dict) else None
        if (not isinstance(depth, list) or len(depth) != grid
                or any(not isinstance(row, list) or len(row) != grid for row in depth)):
            return False
        if any(not isinstance(v, (int, float)) or not 0 <= v <= MAX_DEPTH_M
               for row in depth for v in row):
            return False
        for key, low, high in (("sst_c", -3.0, 40.0), ("mld_m", 0.0, 6000.0)):
            values = entry.get(key)
            if (not isinstance(values, list) or len(values) != 12
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v)
                           or not low <= v <= high for v in values)):
                return False
    return True


def load(path: str = PATH) -> dict | None:
    """The validated data, or None when the file is missing or damaged."""
    global _data, _failed
    if path == PATH and (_data is not None or _failed):
        return _data
    try:
        with gzip.open(path, "rt", encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError):
        data = None
    if data is not None and not _valid(data):
        data = None
    if path == PATH:
        _data, _failed = data, data is None
    return data


_reference_depth = 0


@contextlib.contextmanager
def reference_sea():
    """Inside it every sector uses the synthetic sea (the calibration's
    reference, ``tools/calibrate.py``)."""
    global _reference_depth
    _reference_depth += 1
    try:
        yield
    finally:
        _reference_depth -= 1


def hold_reference_sea() -> None:
    """Use the synthetic sea for the rest of this process (a measuring
    process such as ``tools/fairness.py --synthetic-sea``)."""
    global _reference_depth
    _reference_depth += 1


def sector(sector_id) -> dict | None:
    data = load()
    if _reference_depth or data is None or not isinstance(sector_id, str):
        return None
    return data["sectors"].get(sector_id)


def bathymetry(sector_id, on_land, world_size_nm: float) -> dict | None:
    """``{"size", "values"}`` for a coastline: real depths, 0 where the
    game's coastline has land, at least ``MIN_WATER_DEPTH_M`` elsewhere."""
    entry = sector(sector_id)
    if entry is None:
        return None
    rows = entry["depth"]
    size = len(rows)
    spacing = world_size_nm / (size - 1)
    values = []
    for row, line in enumerate(rows):
        values.append([0.0 if on_land(column * spacing, row * spacing)
                       else max(MIN_WATER_DEPTH_M, float(depth))
                       for column, depth in enumerate(line)])
    return {"size": size, "values": values}


def monthly(values, day_of_year: float) -> float:
    """Interpolate twelve monthly means (cyclic) at a day of the year."""
    day = float(day_of_year)
    for index in range(12):
        start = _MID_MONTH[index]
        end = _MID_MONTH[(index + 1) % 12] + (365 if index == 11 else 0)
        probe = day if day >= start else day + 365
        if start <= probe < end:
            share = (probe - start) / (end - start)
            return values[index] * (1.0 - share) + values[(index + 1) % 12] * share
    return float(values[0])
