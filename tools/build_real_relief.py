"""Build ``data/coastlines/real_relief.json.gz``: the real land heights
around every real coastline sector, for the coasts and mountains on the
horizon (src/world/real_relief.py, src/ui/horizon.py).

Source: NOAA ETOPO1 (1 arc-minute relief, via the ERDDAP dataset
``etopo180``, the same source as tools/build_real_ocean.py), every second
grid point (``STEP_ARCMIN``, about 2 NM).  The file holds one tile per
whole degree of latitude and longitude that has land, ``TILE`` x ``TILE``
heights from its south-west corner, each a byte on a square-root scale up
to ``HEIGHT_SCALE_M`` (fine on the coast, about 18 m steps at 1000 m).
Water is 0.  Only tiles within ``MARGIN_NM`` of a sector's square are kept:
a mountain beyond the edge of the sea area still shows on the horizon.

U.S. government data, free to use and redistribute.  This tool needs the
network; the game only reads the committed file.

    python3 tools/build_real_relief.py [--out PATH] [--cache DIR]
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.world.real_coast import load_catalog  # noqa: E402

ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.esriAscii"
STEP_ARCMIN = 2
TILE = 60 // STEP_ARCMIN
HEIGHT_SCALE_M = 4500.0
WORLD_NM = 500.0
MARGIN_NM = 45.0
BAND_DEG = 5
RUN_MAX_DEG = 20
OUT = os.path.join(ROOT, "data", "coastlines", "real_relief.json.gz")


def sector_tiles(center_lat, center_lon):
    """Whole-degree tiles ``(lat, lon)`` (south-west corners, lon in
    -180..179) under a sector's square and its margin."""
    half = WORLD_NM * 0.5 + MARGIN_NM
    half_lat = half / 60.0
    half_lon = half / (60.0 * math.cos(math.radians(center_lat)))
    lat0 = max(-90, math.floor(center_lat - half_lat))
    lat1 = min(89, math.floor(center_lat + half_lat))
    lon0 = math.floor(center_lon - half_lon)
    lon1 = math.floor(center_lon + half_lon)
    return {(lat, (lon + 180) % 360 - 180)
            for lat in range(lat0, lat1 + 1) for lon in range(lon0, lon1 + 1)}


def fetch_boxes(tiles):
    """Rectangles ``(lat0, lat1, lon0, lon1)`` in whole degrees (end
    exclusive) that cover ``tiles``: ``BAND_DEG`` latitude bands, each cut
    into runs of neighbouring longitudes."""
    boxes = []
    bands = sorted({lat - lat % BAND_DEG for lat, _ in tiles})
    for band in bands:
        lons = sorted({lon for lat, lon in tiles if band <= lat < band + BAND_DEG})
        lats = [lat for lat, _ in tiles if band <= lat < band + BAND_DEG]
        lat0, lat1 = min(lats), max(lats) + 1
        start = previous = lons[0]
        for lon in lons[1:] + [None]:
            if lon is None or lon != previous + 1 or lon - start >= RUN_MAX_DEG:
                boxes.append((lat0, lat1, start, previous + 1))
                if lon is not None:
                    start = lon
            if lon is not None:
                previous = lon
    return boxes


def _get(url, cache_path):
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="ascii") as source:
            return source.read()
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=300) as reply:
                text = reply.read().decode("ascii")
            break
        except OSError:
            if attempt == 4:
                raise
            time.sleep(3.0 * (attempt + 1))
    if cache_path:
        with open(cache_path, "w", encoding="ascii") as target:
            target.write(text)
    return text


def fetch_box(lat0, lat1, lon0, lon1, cache_dir=None):
    """``{(lat_index, lon_index): altitude_m}`` on the global
    ``STEP_ARCMIN`` grid (index = degrees * TILE) for one box."""
    step = STEP_ARCMIN / 60.0
    last_lat = lat1 - step
    last_lon = lon1 - step
    query = (f"altitude[({lat0:.5f}):{STEP_ARCMIN}:({last_lat:.5f})]"
             f"[({lon0:.5f}):{STEP_ARCMIN}:({last_lon:.5f})]")
    url = ERDDAP + "?" + urllib.parse.quote(query, safe="[]():,")
    cache = (os.path.join(cache_dir, f"{lat0}_{lat1}_{lon0}_{lon1}.asc")
             if cache_dir else None)
    lines = _get(url, cache).split("\n")
    header = {}
    for line in lines[:6]:
        key, value = line.split()
        header[key.lower()] = float(value)
    ncols, nrows = int(header["ncols"]), int(header["nrows"])
    south = round(header["yllcenter"] * TILE)
    west = round(header["xllcenter"] * TILE)
    values = {}
    for row, line in enumerate(lines[6:6 + nrows]):
        lat_index = south + nrows - 1 - row  # the first row is the north edge
        for column, cell in enumerate(line.split()[:ncols]):
            values[(lat_index, west + column)] = float(cell)
    return values


def encode_tile(heights):
    raw = bytes(min(255, max(0, round(math.sqrt(max(0.0, h) / HEIGHT_SCALE_M) * 255.0)))
                for h in heights)
    return base64.b64encode(zlib.compress(raw, 9)).decode("ascii")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--cache", default=None,
                        help="keep the ERDDAP answers here and reuse them")
    args = parser.parse_args(argv)
    if args.cache:
        os.makedirs(args.cache, exist_ok=True)
    wanted = set()
    for sector in load_catalog()["sectors"]:
        center = sector["center"]
        wanted |= sector_tiles(center["latitude"], center["longitude"])
    boxes = fetch_boxes(wanted)
    print(len(wanted), "tiles in", len(boxes), "requests", flush=True)
    samples = {}
    for number, box in enumerate(boxes, 1):
        samples.update(fetch_box(*box, cache_dir=args.cache))
        print(f"{number}/{len(boxes)}", box, flush=True)
    tiles = {}
    highest = 0.0
    for lat, lon in sorted(wanted):
        heights = [samples.get((lat * TILE + i, lon * TILE + j), 0.0)
                   for i in range(TILE) for j in range(TILE)]
        if max(heights) <= 0.0:
            continue
        highest = max(highest, max(heights))
        tiles[f"{lat},{lon}"] = encode_tile(heights)
    data = {
        "schema": 1,
        "step_arcmin": STEP_ARCMIN,
        "tile": TILE,
        "height_scale_m": HEIGHT_SCALE_M,
        "provenance": {
            "relief": "NOAA NGDC ETOPO1 1 arc-minute global relief (ERDDAP etopo180), "
                      f"every {STEP_ARCMIN}nd arc-minute, land heights only",
            "license": "U.S. government data, free to use and redistribute",
        },
        "tiles": tiles,
    }
    with gzip.GzipFile(args.out, "wb", compresslevel=9, mtime=0) as target:
        target.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    print("wrote", args.out, len(tiles), "land tiles, highest", round(highest), "m,",
          os.path.getsize(args.out), "bytes")


if __name__ == "__main__":
    main()
