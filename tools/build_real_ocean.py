"""Build ``data/coastlines/real_ocean.json.gz``: real water depths and the
monthly surface layer of every real coastline sector.

Depths: NOAA ETOPO1 (1 arc-minute relief, via the ERDDAP dataset
``etopo180``), averaged over the water cells around each point of a
``GRID`` x ``GRID`` grid across the 500-NM sector.  Surface layer: the
World Ocean Atlas 2023 one-degree monthly mean temperature (decadal average
"decav"): per month the mean sea-surface temperature of the sector and the
median mixed-layer depth (0.5 degC below the surface temperature).

Both sources are U.S. government data, free to use and redistribute.  This
tool needs the network; the game only reads the committed file.

    python3 tools/build_real_ocean.py --woa-dir /tmp/woa [--out PATH]

``--woa-dir`` holds ``woa23_decav_tMMmn01.csv.gz`` for MM = 01..12 (from
https://www.ncei.noaa.gov/data/oceans/woa/WOA23/DATA/temperature/csv/decav/1.00/).
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.world.projection import nm_to_lonlat  # noqa: E402
from src.world.real_coast import load_catalog  # noqa: E402

GRID = 33
WORLD_NM = 500.0
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.json"
STRIDE = 3  # arc-minutes between ETOPO samples (about 3 NM)
MLD_DELTA_C = 0.5
OUT = os.path.join(ROOT, "data", "coastlines", "real_ocean.json.gz")


def _fetch_relief(lat0, lat1, lon0, lon1):
    """``{(lat, lon): altitude_m}`` for one box that does not cross 180 deg."""
    query = (f"altitude[({lat0:.4f}):{STRIDE}:({lat1:.4f})]"
             f"[({lon0:.4f}):{STRIDE}:({lon1:.4f})]")
    url = ERDDAP + "?" + urllib.parse.quote(query, safe="[]():,")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as reply:
                table = json.load(reply)["table"]
            break
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2.0 * (attempt + 1))
    return {(round(lat, 4), round(lon, 4)): alt for lat, lon, alt in table["rows"]}


def relief_samples(center_lat, center_lon):
    half_lat = WORLD_NM * 0.5 / 60.0 + 0.2
    half_lon = WORLD_NM * 0.5 / (60.0 * math.cos(math.radians(center_lat))) + 0.2
    lat0, lat1 = max(-89.9, center_lat - half_lat), min(89.9, center_lat + half_lat)
    lon0, lon1 = center_lon - half_lon, center_lon + half_lon
    boxes = []
    if lon0 < -180.0:
        boxes += [(lon0 + 360.0, 180.0), (-180.0, lon1)]
    elif lon1 > 180.0:
        boxes += [(lon0, 180.0), (-180.0, lon1 - 360.0)]
    else:
        boxes.append((lon0, lon1))
    samples = []
    for left, right in boxes:
        for (lat, lon), alt in _fetch_relief(lat0, lat1, left, right).items():
            samples.append((lat, lon, alt))
    return samples


def depth_grid(sector, samples):
    """Mean water depth (m) around each grid point; 0 where ETOPO has no
    water near it."""
    from src.world.projection import lonlat_to_nm

    center = sector["center"]
    spacing = WORLD_NM / (GRID - 1)
    sums = [[0.0] * GRID for _ in range(GRID)]
    counts = [[0] * GRID for _ in range(GRID)]
    for lat, lon, alt in samples:
        if alt is None or alt >= 0.0:
            continue
        x, y = lonlat_to_nm(lon, lat, center["longitude"], center["latitude"], WORLD_NM)
        column = round(x / spacing)
        row = round(y / spacing)
        if 0 <= row < GRID and 0 <= column < GRID:
            sums[row][column] += -alt
            counts[row][column] += 1
    return [[int(round(sums[r][c] / counts[r][c])) if counts[r][c] else 0
             for c in range(GRID)] for r in range(GRID)]


def load_woa(woa_dir):
    """Per month ``{(lat, lon): (depths, temps)}`` of the 1-degree cells."""
    months = []
    for month in range(1, 13):
        path = os.path.join(woa_dir, f"woa23_decav_t{month:02d}mn01.csv.gz")
        cells = {}
        depths = None
        with gzip.open(path, "rt") as source:
            for line in source:
                if line.startswith("#"):
                    if "DEPTHS" in line:
                        depths = [float(v) for v in line.split(":", 1)[1].split(",")]
                    continue
                parts = line.strip().split(",")
                lat, lon = float(parts[0]), float(parts[1])
                temps = [float(v) for v in parts[2:] if v.strip() != ""]
                if temps:
                    cells[(lat, lon)] = temps
        months.append((depths, cells))
    return months


def _mld(depths, temps):
    limit = temps[0] - MLD_DELTA_C
    for index in range(1, len(temps)):
        if temps[index] < limit:
            upper, lower = temps[index - 1], temps[index]
            share = (upper - limit) / max(1e-6, upper - lower)
            return depths[index - 1] + share * (depths[index] - depths[index - 1])
    return depths[len(temps) - 1]


def surface_layer(sector, months):
    center = sector["center"]
    lat_c, lon_c = center["latitude"], center["longitude"]
    half_lat = WORLD_NM * 0.5 / 60.0
    half_lon = WORLD_NM * 0.5 / (60.0 * math.cos(math.radians(lat_c)))
    sst, mld = [], []
    for depths, cells in months:
        temps = []
        layers = []
        for (lat, lon), profile in cells.items():
            dlon = (lon - lon_c + 180.0) % 360.0 - 180.0
            if abs(lat - lat_c) > half_lat or abs(dlon) > half_lon:
                continue
            temps.append(profile[0])
            layers.append(_mld(depths, profile))
        sst.append(round(statistics.fmean(temps), 2))
        mld.append(round(statistics.median(layers), 1))
    return sst, mld


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--woa-dir", required=True)
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args(argv)
    catalog = load_catalog()
    months = load_woa(args.woa_dir)
    sectors = {}
    for sector in catalog["sectors"]:
        center = sector["center"]
        samples = relief_samples(center["latitude"], center["longitude"])
        sst, mld = surface_layer(sector, months)
        sectors[sector["id"]] = {"depth": depth_grid(sector, samples),
                                 "sst_c": sst, "mld_m": mld}
        print(sector["id"], sector["name"], "max depth",
              max(max(row) for row in sectors[sector["id"]]["depth"]),
              "SST", min(sst), "-", max(sst), "MLD", min(mld), "-", max(mld),
              flush=True)
    data = {
        "schema": 1,
        "grid": GRID,
        "provenance": {
            "depth": "NOAA NGDC ETOPO1 1 arc-minute global relief (ERDDAP etopo180), "
                     f"mean water depth per {WORLD_NM / (GRID - 1):.1f} NM cell",
            "surface_layer": "NOAA NCEI World Ocean Atlas 2023, 1-degree monthly mean "
                             "temperature (decav); mixed layer at "
                             f"{MLD_DELTA_C} degC below the surface",
            "license": "U.S. government data, free to use and redistribute",
        },
        "sectors": sectors,
    }
    with gzip.open(args.out, "wt", encoding="utf-8", compresslevel=9) as target:
        json.dump(data, target, separators=(",", ":"), sort_keys=True)
    print("wrote", args.out, os.path.getsize(args.out), "bytes")


if __name__ == "__main__":
    main()
