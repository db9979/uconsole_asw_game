#!/usr/bin/env python3
"""Build the checked-in 128-sector runtime catalog without GIS dependencies.

Two pinned, offline steps (network access is deliberately outside them):

``build``: a pinned Natural Earth 1:50m countries GeoJSON and a saved Wikidata
SPARQL JSON result select the 128 sectors (centres, countries, airbases).

``refine``: that 1:50m catalog (pinned by its SHA-256; it is the catalog of
1.3.205 in git history) and the pinned Natural Earth 1:10m countries GeoJSON
of the same commit redraw every sector's land at the finer scale. Sector
order, ids, centres, names, countries and airbases stay exactly as selected,
so seeds keep their sea area; only the coast becomes finer.
"""

import argparse
from collections import deque
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.world.projection import lonlat_to_nm


SIZE = 500.0
COUNT = 128
NE_SHA256 = "3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb"
WD_SHA256 = "f7126b7680afe9dcbb76ee8212ac82175e5b8e586f8fb3fafe57a071a8a6ffa9"
NE10_SHA256 = "239eec57ac17f100a11e2536cffc56752c318b50ae765b0918ff7aab4ce8f255"
CATALOG50_SHA256 = "595b70d6b9290bfcb10a500f7d1be2162b6b5337fc7e7f0f6932dfe7bd8c6979"
NE_COMMIT = "9380cca83db5f9aef52d5e762765100745f84b27"
# Douglas-Peucker tolerance of the 1:10m land (NM): about 90 m, far below
# the source's own accuracy, so the coast keeps its shape with fewer points.
REFINE_TOLERANCE_NM = 0.05


def sha256(path):
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def clip_polygon(points, size=SIZE):
    def clip(items, inside, intersection):
        output = []
        if not items:
            return output
        previous = items[-1]
        for current in items:
            if inside(current):
                if not inside(previous):
                    output.append(intersection(previous, current))
                output.append(current)
            elif inside(previous):
                output.append(intersection(previous, current))
            previous = current
        return output

    out = list(points)
    for axis, edge, keep_greater in ((0, 0.0, True), (0, size, False),
                                     (1, 0.0, True), (1, size, False)):
        def inside(point, axis=axis, edge=edge, keep_greater=keep_greater):
            return point[axis] >= edge if keep_greater else point[axis] <= edge

        def cross(first, second, axis=axis, edge=edge):
            delta = second[axis] - first[axis]
            factor = 0.0 if abs(delta) < 1e-12 else (edge - first[axis]) / delta
            point = [first[0] + factor * (second[0] - first[0]),
                     first[1] + factor * (second[1] - first[1])]
            point[axis] = edge
            return tuple(point)
        out = clip(out, inside, cross)
    cleaned = []
    for point in out:
        rounded = (round(point[0], 3), round(point[1], 3))
        if not cleaned or rounded != cleaned[-1]:
            cleaned.append(rounded)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def point_in_polygon(x, y, points):
    inside = False
    for index, first in enumerate(points):
        second = points[(index + 1) % len(points)]
        if (first[1] > y) != (second[1] > y):
            crossing = first[0] + (y - first[1]) * (second[0] - first[0]) / (second[1] - first[1])
            if x < crossing:
                inside = not inside
    return inside


def distance_to_segment(x, y, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(x - first[0], y - first[1])
    amount = max(0.0, min(1.0, ((x - first[0]) * dx
                                + (y - first[1]) * dy) / length2))
    return math.hypot(x - first[0] - amount * dx,
                      y - first[1] - amount * dy)


def distance_to_coast(x, y, landmasses):
    return min(distance_to_segment(x, y, points[index],
                                   points[(index + 1) % len(points)])
               for land in landmasses for points in (land["points"],)
               for index in range(len(points)))


def water_reachable(x, y, landmasses):
    """Match the runtime's bounded nearest-water search exactly."""
    for radius in range(1, 26):
        for index in range(8):
            angle = math.radians(index * 45.0 + radius * 37.0)
            px = x + radius * math.cos(angle)
            py = y + radius * math.sin(angle)
            if (0.0 <= px <= SIZE and 0.0 <= py <= SIZE
                    and not any(point_in_polygon(px, py, land["points"])
                                for land in landmasses)):
                return True
    return False


def load_land(path):
    with open(path, encoding="utf-8") as source:
        raw = json.load(source)
    polygons = []
    for feature in raw["features"]:
        props = feature["properties"]
        country = props.get("ADMIN") or props.get("NAME_EN") or props["NAME"]
        geometry = feature["geometry"]
        groups = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for group in groups:
            exterior = group[0]
            # Dateline-spanning exteriors need topology-aware splitting; other
            # polygons of the same countries still provide ample candidates.
            if len(exterior) >= 4 and max(p[0] for p in exterior) - min(p[0] for p in exterior) < 180.0:
                polygons.append((country, exterior))
    return polygons


def load_bases(path):
    with open(path, encoding="utf-8") as source:
        bindings = json.load(source)["results"]["bindings"]
    bases = []
    for item in bindings:
        match = re.fullmatch(r"Point\(([-.0-9]+) ([-.0-9]+)\)", item["coord"]["value"])
        label = item.get("itemLabel", {}).get("value", "")
        country = item.get("countryLabel", {}).get("value", "")
        qid = item["item"]["value"].rsplit("/", 1)[-1]
        if match and label and country and label != qid:
            bases.append({"id": qid.lower(), "name": label, "nation": country,
                          "wikidata": qid, "lon": float(match.group(1)),
                          "lat": float(match.group(2))})
    # OPTIONAL country values can yield duplicate rows for one Wikidata item.
    return list({base["id"]: base for base in bases}.values())


def simplify_ring(points, tolerance):
    """Douglas-Peucker on a closed ring (iterative, deterministic)."""
    count = len(points)
    if count < 4:
        return list(points)
    first = points[0]
    far = max(range(count), key=lambda index: (
        (points[index][0] - first[0]) ** 2 + (points[index][1] - first[1]) ** 2, -index))
    keep = [False] * count
    keep[0] = keep[far] = True
    pending = [(0, far), (far, count)]
    while pending:
        start, end = pending.pop()
        a, c = points[start], points[end % count]
        best, chosen = -1.0, None
        for index in range(start + 1, end):
            distance = distance_to_segment(points[index][0], points[index][1], a, c)
            if distance > best:
                best, chosen = distance, index
        if chosen is not None and best > tolerance:
            keep[chosen] = True
            pending.append((start, chosen))
            pending.append((chosen, end))
    return [point for point, kept in zip(points, keep) if kept]


def geometry_for(center_lon, center_lat, polygons, tolerance=None):
    landmasses = []
    for country, exterior in polygons:
        projected = [lonlat_to_nm(lon, lat, center_lon, center_lat, SIZE)
                     for lon, lat in exterior]
        if (max(p[0] for p in projected) < 0 or min(p[0] for p in projected) > SIZE
                or max(p[1] for p in projected) < 0 or min(p[1] for p in projected) > SIZE):
            continue
        clipped = clip_polygon(projected)
        if tolerance is not None:
            clipped = simplify_ring(clipped, tolerance)
        area = abs(sum(clipped[i][0] * clipped[(i + 1) % len(clipped)][1]
                       - clipped[(i + 1) % len(clipped)][0] * clipped[i][1]
                       for i in range(len(clipped))) / 2.0) if len(clipped) >= 3 else 0.0
        if len(clipped) >= 3 and area >= 0.5:
            landmasses.append({"name": country, "nation": country,
                               "points": clipped})
    return landmasses


def playable(landmasses):
    n = 21
    if not landmasses or distance_to_coast(SIZE * .5, SIZE * .5, landmasses) < 70.0:
        return None
    water = set()
    for row in range(n):
        for column in range(n):
            x, y = (column + .5) * SIZE / n, (row + .5) * SIZE / n
            if not any(point_in_polygon(x, y, land["points"]) for land in landmasses):
                water.add((column, row))
    ratio = 1.0 - len(water) / (n * n)
    center = (n // 2, n // 2)
    if center not in water or not 0.08 <= ratio <= 0.46:
        return None
    reached, pending = {center}, deque([center])
    while pending:
        column, row = pending.popleft()
        for neighbor in ((column - 1, row), (column + 1, row),
                         (column, row - 1), (column, row + 1)):
            if neighbor in water and neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    if len(reached) < len(water) * .94:
        return None
    return round(ratio, 4)


def build(polygons, bases):
    candidates = {}
    # Real base clusters produce useful coastal windows and guarantee that any
    # included base has a source record. Offsets put open water near the center.
    offsets = [(dx, dy) for dx in (-220.0, -140.0, 140.0, 220.0)
               for dy in (-140.0, 0.0, 140.0)]
    for base in bases:
        offset_index = int(hashlib.sha256(base["wikidata"].encode()).hexdigest()[:8], 16)
        dx, dy = offsets[offset_index % len(offsets)]
        center_lat = base["lat"] + dy / 60.0
        center_lon = base["lon"] - dx / (
            math.cos(math.radians(center_lat)) * 60.0)
        if abs(center_lat) > 72.0:
            continue
        key = (round(center_lon, 1), round(center_lat, 1))
        candidates[key] = (center_lon, center_lat)

    valid = []
    for center_lon, center_lat in candidates.values():
        landmasses = geometry_for(center_lon, center_lat, polygons)
        ratio = playable(landmasses)
        if ratio is None:
            continue
        local_bases = []
        for base in bases:
            x, y = lonlat_to_nm(base["lon"], base["lat"], center_lon, center_lat, SIZE)
            if 3.0 <= x <= SIZE - 3.0 and 3.0 <= y <= SIZE - 3.0:
                local = {key: value for key, value in base.items() if key not in ("lon", "lat")}
                local.update({"x": round(x, 3), "y": round(y, 3),
                              "longitude": base["lon"], "latitude": base["lat"]})
                if (any(point_in_polygon(x, y, land["points"]) for land in landmasses)
                        and distance_to_coast(x, y, landmasses) <= 15.0
                        and water_reachable(x, y, landmasses)):
                    local_bases.append(local)
        if len(local_bases) < 4:
            continue
        countries = sorted({land["nation"] for land in landmasses})
        score = abs(ratio - .24) - min(len(countries), 4) * .012 - min(len(local_bases), 8) * .003
        valid.append((score, center_lon, center_lat, ratio, countries,
                      landmasses, local_bases))

    # One best sector per 5-degree geographic cell first prevents dense UK and
    # US base records from overwhelming the global selection.
    valid.sort(key=lambda row: (row[0], round(row[2], 6), round(row[1], 6)))
    selected, cells = [], set()
    for candidate in valid:
        cell = (math.floor(candidate[1] / 5.0), math.floor(candidate[2] / 5.0))
        if cell not in cells:
            selected.append(candidate)
            cells.add(cell)
        if len(selected) == COUNT:
            break
    if len(selected) < COUNT:
        for candidate in valid:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) == COUNT:
                break
    if len(selected) != COUNT:
        raise RuntimeError(f"only {len(selected)} prevalidated sectors available")

    sectors = []
    for index, (_, lon, lat, ratio, countries, landmasses, local_bases) in enumerate(selected):
        # Dense regions can contain hundreds of duplicate or historic records.
        # Twelve stable records are enough for gameplay and rendering.
        local_bases = sorted(local_bases, key=lambda base: base["id"])[:12]
        roles = ("friendly", "friendly", "hostile", "neutral")
        for base_index, base in enumerate(local_bases):
            base["gameplay_role"] = roles[base_index] if base_index < len(roles) else "civil"
        sectors.append({
            "id": f"real-{index:03d}", "name": " / ".join(countries[:3]) + " coastal waters",
            "world_nm": SIZE, "center": {"longitude": round(lon, 6),
                                           "latitude": round(lat, 6)},
            "countries": countries, "land_ratio": ratio,
            "landmasses": landmasses, "airbases": local_bases,
        })
    return sectors


def refine(catalog, polygons):
    """The 1:50m catalog's sectors with their land redrawn from 1:10m."""
    sectors = []
    for sector in catalog["sectors"]:
        center = sector["center"]
        landmasses = geometry_for(center["longitude"], center["latitude"],
                                  polygons, REFINE_TOLERANCE_NM)
        if not landmasses:
            raise RuntimeError(f"{sector['id']} lost its land")
        countries = sorted({land["nation"] for land in landmasses})
        sectors.append(dict(sector, landmasses=landmasses, countries=countries,
                            name=" / ".join(countries[:3]) + " coastal waters"))
    return sectors


def _provenance(dataset, sha):
    return {
        "natural_earth": {"dataset": dataset,
            "license": "Public Domain", "commit": NE_COMMIT,
            "sha256": sha, "url": "https://github.com/nvkelso/natural-earth-vector"},
        "airbases": {"dataset": "Wikidata airbase (Q695850) coordinate query snapshot",
            "license": "CC0 1.0", "retrieved": "2026-09-06", "sha256": WD_SHA256,
            "query": "?item wdt:P31/wdt:P279* wd:Q695850; wdt:P625 ?coord; optional P17"},
        "projection": "local equirectangular at sector center; 60 NM per latitude degree",
    }


def _write(catalog, output):
    payload = json.dumps(catalog, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    with open(output, "wb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as packed:
            packed.write(payload)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build_args = commands.add_parser("build", help="select sectors from 1:50m and Wikidata")
    build_args.add_argument("natural_earth")
    build_args.add_argument("wikidata_airbases")
    build_args.add_argument("output")
    refine_args = commands.add_parser("refine", help="redraw the land from 1:10m")
    refine_args.add_argument("catalog_50m")
    refine_args.add_argument("natural_earth_10m")
    refine_args.add_argument("output")
    args = parser.parse_args()
    if args.command == "build":
        if sha256(args.natural_earth) != NE_SHA256 or sha256(args.wikidata_airbases) != WD_SHA256:
            raise SystemExit("input checksum mismatch; refusing an unpinned build")
        _write({"schema": 1,
                "provenance": _provenance("Natural Earth 1:50m Admin 0 Countries v5.1.1", NE_SHA256),
                "sectors": build(load_land(args.natural_earth),
                                 load_bases(args.wikidata_airbases))}, args.output)
        return
    if sha256(args.catalog_50m) != CATALOG50_SHA256 or sha256(args.natural_earth_10m) != NE10_SHA256:
        raise SystemExit("input checksum mismatch; refusing an unpinned build")
    with gzip.open(args.catalog_50m, "rt", encoding="utf-8") as source:
        catalog = json.load(source)
    _write({"schema": 1,
            "provenance": _provenance("Natural Earth 1:10m Admin 0 Countries v5.1.1", NE10_SHA256),
            "sectors": refine(catalog, load_land(args.natural_earth_10m))}, args.output)


if __name__ == "__main__":
    main()
