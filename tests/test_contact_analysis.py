import ast
import hashlib
import json
from pathlib import Path

from src.data import catalog
from src.data.contact_analysis import (
    ASSET_ROUTE_PREFIX, CONTACTS_ROUTE, MAX_ANALYSIS_PROFILES,
    MAX_COMPONENTS_PER_PROFILE, load_contact_analysis_assets,
    project_contact_catalog,
)


def _walk(value):
    yield value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(key)
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_projection_is_bounded_ordered_detached_json_primitives():
    projected = project_contact_catalog()
    assert len(projected["profiles"]) == len(catalog.CATALOG.profile_systems) <= \
        MAX_ANALYSIS_PROFILES
    assert [item["key"] for item in projected["profiles"]] == \
        list(catalog.CATALOG.profile_systems)
    assert all(type(value) in (dict, list, str, int, float, bool, type(None))
               for value in _walk(projected))
    assert all(len(items) <= MAX_COMPONENTS_PER_PROFILE
               for profile in projected["profiles"]
               for items in profile["components"].values())
    projected["profiles"][0]["reference"]["aliases"].append("detached")
    assert "detached" not in catalog.CATALOG.references[
        catalog.CATALOG.profile_systems[projected["profiles"][0]["key"]].reference_key
    ].aliases


def test_projection_omits_forbidden_data_and_imports():
    projected = project_contact_catalog()
    keys = {key for value in _walk(projected) if isinstance(value, dict)
            for key in value}
    assert keys.isdisjoint({"hostile", "side", "source_ids", "runtime_profile_key"})
    encoded = json.dumps(projected, sort_keys=True).lower()
    assert "https://" not in encoded and "http://" not in encoded
    assert "silhouette" not in encoded
    source = Path("src/data/contact_analysis.py").read_text(encoding="utf-8")
    imports = {alias.name for node in ast.walk(ast.parse(source))
               if isinstance(node, (ast.Import, ast.ImportFrom))
               for alias in node.names}
    assert not any(name == "pygame" or name.startswith((
        "src.core.game", "src.ui", "src.ship", "src.enemies", "src.air",
        "src.weapons")) for name in imports)


def test_asset_applicability_routes_and_projection_hash():
    projected = project_contact_catalog()
    for profile in projected["profiles"]:
        machine, assets = profile["machine"], profile["assets"]
        assert "silhouette" not in assets
        assert ("acoustic_cruise" in assets) == bool(
            machine["cruise_lines"] or machine["cruise_broadband"] is not None)
        assert ("acoustic_high" in assets) == bool(
            machine["high_speed_lines"] or machine["high_speed_broadband"] is not None)
        for route in assets.values():
            assert route.startswith(ASSET_ROUTE_PREFIX)
            leaf = route.removeprefix(ASSET_ROUTE_PREFIX)
            assert leaf and "/" not in leaf and "\\" not in leaf and ".." not in leaf
    digest = hashlib.sha256(json.dumps(
        projected, ensure_ascii=True, separators=(",", ":")
    ).encode()).hexdigest()
    assert len(digest) == 64


def test_packaged_manifest_routes_hashes_and_projection_bytes_have_exact_parity():
    routes = load_contact_analysis_assets()
    projection = project_contact_catalog()
    expected_images = {route for profile in projection["profiles"]
                       for route in profile["assets"].values()}
    assert routes.keys() == {CONTACTS_ROUTE, *expected_images}
    assert routes[CONTACTS_ROUTE] == (
        "application/json; charset=utf-8",
        json.dumps(projection, allow_nan=False, ensure_ascii=True,
                   separators=(",", ":")).encode("ascii"),
    )
    manifest = json.loads(Path("data/contact_analysis/manifest.json").read_text())
    assert {item["route"] for item in manifest["assets"]} == expected_images
    for item in manifest["assets"]:
        mime, payload = routes[item["route"]]
        assert mime == "image/png"
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]
