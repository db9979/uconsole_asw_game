"""Validated loader for the committed real-world coastline sector catalog."""

import gzip
import hashlib
import json
import math
import os


SECTOR_COUNT = 128
SECTOR_ID_ORDER_SHA256 = "3f061f22b0619cc25b86dc1f3fa8512e23cd257a383b545919ccb432c7dd5c99"
CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "coastlines", "real_sectors.json.gz")

_catalog = None


def _validate(catalog: dict) -> None:
    if catalog.get("schema") != 1:
        raise ValueError("unsupported real coastline catalog schema")
    sectors = catalog.get("sectors")
    if not isinstance(sectors, list) or len(sectors) != SECTOR_COUNT:
        raise ValueError(f"real coastline catalog must contain exactly {SECTOR_COUNT} sectors")
    ids = set()
    for sector in sectors:
        sector_id = sector.get("id")
        if not isinstance(sector_id, str) or sector_id in ids:
            raise ValueError("real coastline catalog has invalid or duplicate sector IDs")
        ids.add(sector_id)
        if sector.get("world_nm") != 500.0 or not sector.get("landmasses"):
            raise ValueError(f"real coastline sector {sector_id} is incomplete")
        for land in sector["landmasses"]:
            points = land.get("points", [])
            if len(points) < 3 or not land.get("name") or not land.get("nation"):
                raise ValueError(f"real coastline sector {sector_id} has invalid land data")
            if any(not (math.isfinite(float(x)) and math.isfinite(float(y))
                        and 0.0 <= float(x) <= 500.0 and 0.0 <= float(y) <= 500.0)
                   for x, y in points):
                raise ValueError(f"real coastline sector {sector_id} has out-of-bounds geometry")
        for base in sector.get("airbases", []):
            if not all(base.get(key) for key in ("id", "name", "nation", "wikidata")):
                raise ValueError(f"real coastline sector {sector_id} has an unsourced airbase")
    ordered_ids = "\n".join(sector["id"] for sector in sectors).encode("utf-8")
    if hashlib.sha256(ordered_ids).hexdigest() != SECTOR_ID_ORDER_SHA256:
        raise ValueError("real coastline sector order does not match the stable seed mapping")


def load_catalog(path: str = CATALOG_PATH) -> dict:
    global _catalog
    if path == CATALOG_PATH and _catalog is not None:
        return _catalog
    try:
        with gzip.open(path, "rt", encoding="utf-8") as source:
            catalog = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"real coastline catalog unavailable or corrupt: {path}") from exc
    _validate(catalog)
    if path == CATALOG_PATH:
        _catalog = catalog
    return catalog


def sector_for_seed(seed: int) -> tuple[dict, dict]:
    catalog = load_catalog()
    return catalog["sectors"][int(seed) % SECTOR_COUNT], catalog["provenance"]
