"""Bounded, presentation-only projection and packaged analyzer resources."""

import hashlib
from importlib import resources
import json
import math
import re
import struct

from src.data.catalog import CATALOG


MAX_ANALYSIS_PROFILES = 4096
MAX_COMPONENTS_PER_PROFILE = 128
ASSET_ROUTE_PREFIX = "/contact-analysis/"
CONTACTS_ROUTE = "/api/v1/contacts"
MAX_ANALYSIS_ASSETS = MAX_ANALYSIS_PROFILES * 2
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 1024 * 1024
MAX_ANALYSIS_BYTES = 32 * 1024 * 1024
_ASSET_FIELDS = {"profile_key", "kind", "route", "filename", "width",
                 "height", "bytes", "sha256"}
_ASSET_DIMENSIONS = {
    "acoustic_cruise": (320, 180),
    "acoustic_high": (320, 180),
}
_SHA256 = re.compile(r"[0-9a-f]{64}").fullmatch


def _asset_filename(profile_key, kind):
    if (not isinstance(profile_key, str) or not profile_key or len(profile_key) > 96
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-."
                   for char in profile_key)
            or profile_key.startswith(".") or ".." in profile_key):
        raise ValueError("unsafe contact-analysis profile key")
    return f"{profile_key}-{kind}.png"


def _lines(lines):
    return [[line.frequency_hz, line.relative_level, line.width_hz]
            for line in lines]


def _reference_summary(reference):
    return {
        "variant": reference.variant,
        "variant_year": reference.variant_year,
        "refit_year": reference.refit_year,
        "aliases": list(reference.aliases),
        "roles": list(reference.roles),
        "hull_type": reference.hull_type,
        "displacement_tonnes": reference.displacement_tonnes,
        "displacement_basis": reference.displacement_basis,
        "length_m": reference.length_m,
        "beam_waterline_m": reference.beam_waterline_m,
        "beam_overall_m": reference.beam_overall_m,
        "flight_deck_width_m": reference.flight_deck_width_m,
        "draft_m": reference.draft_m,
        "ship_crew": None if reference.ship_crew is None else list(reference.ship_crew),
        "air_group_crew": (None if reference.air_group_crew is None
                             else list(reference.air_group_crew)),
    }


def _machine_summary(machine):
    return {
        "cruise_speed_kn": machine.cruise_speed_kn,
        "maximum_speed_kn": machine.maximum_speed_kn,
        "quiet_speed_kn": machine.quiet_speed_kn,
        "propulsion_codes": list(machine.propulsion_codes),
        "motor_rpm": None if machine.motor_rpm is None else list(machine.motor_rpm),
        "shaft_rpm": None if machine.shaft_rpm is None else list(machine.shaft_rpm),
        "propulsor_type": machine.propulsor_type,
        "blade_count": machine.blade_count,
        "cruise_lines": _lines(machine.cruise_lines),
        "high_speed_lines": _lines(machine.high_speed_lines),
        "cruise_broadband": (None if machine.cruise_broadband is None
                              else list(machine.cruise_broadband)),
        "high_speed_broadband": (None if machine.high_speed_broadband is None
                                  else list(machine.high_speed_broadband)),
    }


def _component_summaries(cat, systems):
    sensors = [{
        "domain": item.domain, "modes": list(item.modes), "emits": item.emits,
        "synthetic_range_nm": item.synthetic_range_nm,
        "sensitivity_db": item.sensitivity_db, "cadence_s": item.cadence_s,
        "bearing_uncertainty_deg": item.bearing_uncertainty_deg,
        "range_uncertainty_nm": item.range_uncertainty_nm,
        "depth_uncertainty_m": item.depth_uncertainty_m,
    } for key in systems.sensor_keys for item in (cat.sensors[key],)]
    emitters = [{
        "domain": item.domain, "frequency_band_hz": list(item.frequency_band_hz),
        "prf_band_hz": None if item.prf_band_hz is None else list(item.prf_band_hz),
        "modulation_codes": list(item.modulation_codes),
    } for key in systems.emitter_keys for item in (cat.emitters[key],)]

    weapon_keys = []
    for launcher_key in systems.launcher_keys:
        for weapon_key in cat.launchers[launcher_key].weapon_keys:
            if weapon_key not in weapon_keys:
                weapon_keys.append(weapon_key)
    for magazine_key in systems.magazine_keys:
        weapon_key = cat.magazines[magazine_key].weapon_key
        if weapon_key not in weapon_keys:
            weapon_keys.append(weapon_key)
    weapons = [{
        "weapon_type": item.weapon_type, "target_domains": list(item.target_domains),
        "maximum_speed_kn": item.maximum_speed_kn,
        "engagement_range_nm": list(item.engagement_range_nm),
        "seeker_type": item.seeker_type, "guidance_type": item.guidance_type,
        "payload_type": item.payload_type,
    } for key in weapon_keys for item in (cat.weapons[key],)]
    launchers = [{
        "launcher_type": item.launcher_type, "mount_count": item.mount_count,
        "ready_count": item.ready_count, "reload_s": item.reload_s,
        "arc_center_deg": item.arc_center_deg, "arc_width_deg": item.arc_width_deg,
        "vls_cells": item.vls_cells,
    } for key in systems.launcher_keys for item in (cat.launchers[key],)]
    magazines = [{"mission_count": cat.magazines[key].mission_count}
                 for key in systems.magazine_keys]
    countermeasures = [{
        "effect_type": item.effect_type, "mission_count": item.mission_count,
        "ready_count": item.ready_count, "reload_s": item.reload_s,
    } for key in systems.countermeasure_keys
      for item in (cat.countermeasures[key],)]
    result = {
        "sensors": sensors, "emitters": emitters, "weapons": weapons,
        "launchers": launchers, "magazines": magazines,
        "countermeasures": countermeasures,
    }
    if any(len(items) > MAX_COMPONENTS_PER_PROFILE for items in result.values()):
        raise ValueError("contact-analysis component limit exceeded")
    return result


def _profile_name(cat, key):
    for registry in (cat.subs, cat.surfaces, cat.aircraft, cat.animals,
                     cat.torpedoes, cat.decoys):
        if key in registry:
            return registry[key].name
    raise ValueError(f"contact-analysis profile missing: {key}")


def project_contact_catalog(cat=CATALOG):
    """Return detached JSON primitives in validated catalog order."""
    if len(cat.profile_systems) > MAX_ANALYSIS_PROFILES:
        raise ValueError("contact-analysis profile limit exceeded")
    profiles = []
    for key, systems in cat.profile_systems.items():
        reference = cat.references[systems.reference_key]
        machine = cat.machines[systems.machine_key]
        assets = {}
        if machine.cruise_lines or machine.cruise_broadband is not None:
            assets["acoustic_cruise"] = ASSET_ROUTE_PREFIX + _asset_filename(key, "cruise")
        if machine.high_speed_lines or machine.high_speed_broadband is not None:
            assets["acoustic_high"] = ASSET_ROUTE_PREFIX + _asset_filename(key, "high")
        profiles.append({
            "key": key,
            "name": _profile_name(cat, key),
            "resource": cat.profile_resources[key],
            "reference": _reference_summary(reference),
            "machine": _machine_summary(machine),
            "components": _component_summaries(cat, systems),
            "assets": assets,
        })
    return {"version": 1, "profiles": profiles}


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate contact-analysis manifest key")
        result[key] = value
    return result


def _finite_number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("nonfinite contact-analysis manifest number")
    return value


def _read_bounded(resource, limit, label):
    with resource.open("rb") as stream:
        payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"contact-analysis {label} size limit exceeded")
    return payload


def _png_dimensions(payload):
    if (len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n"
            or payload[8:16] != b"\x00\x00\x00\rIHDR"):
        raise ValueError("invalid contact-analysis PNG")
    return struct.unpack(">II", payload[16:24])


def load_contact_analysis_assets(cat=CATALOG):
    """Validate and prebuild the exact public analyzer HTTP route byte map."""
    projection = project_contact_catalog(cat)
    expected = {}
    for profile in projection["profiles"]:
        for kind, route in profile["assets"].items():
            expected[route] = (profile["key"], kind, route.removeprefix(ASSET_ROUTE_PREFIX))
    if len(expected) > MAX_ANALYSIS_ASSETS:
        raise ValueError("contact-analysis asset count limit exceeded")

    root = resources.files("data.contact_analysis")
    raw_manifest = _read_bounded(root.joinpath("manifest.json"), MAX_MANIFEST_BYTES,
                                 "manifest")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"), object_pairs_hook=_json_object,
                              parse_float=_finite_number, parse_constant=_finite_number)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid contact-analysis manifest") from exc
    if (not isinstance(manifest, dict) or manifest.keys() != {"version", "assets"}
            or type(manifest["version"]) is not int or manifest["version"] != 1
            or not isinstance(manifest["assets"], list)
            or len(manifest["assets"]) > MAX_ANALYSIS_ASSETS):
        raise ValueError("invalid contact-analysis manifest schema")

    result = {}
    aggregate = 0
    seen = set()
    for item in manifest["assets"]:
        if not isinstance(item, dict) or item.keys() != _ASSET_FIELDS:
            raise ValueError("invalid contact-analysis asset schema")
        profile_key, kind = item["profile_key"], item["kind"]
        route, filename = item["route"], item["filename"]
        width, height, size, digest = (item["width"], item["height"],
                                       item["bytes"], item["sha256"])
        expected_item = expected.get(route) if isinstance(route, str) else None
        if (not isinstance(kind, str)
                or expected_item != (profile_key, kind, filename)
                or route in seen
                or not isinstance(filename, str)
                or filename != _asset_filename(profile_key, {
                    "acoustic_cruise": "cruise", "acoustic_high": "high",
                }.get(kind, ""))
                or type(width) is not int or type(height) is not int
                or (width, height) != _ASSET_DIMENSIONS.get(kind)
                or type(size) is not int or not 0 < size <= MAX_ASSET_BYTES
                or not isinstance(digest, str) or _SHA256(digest) is None):
            raise ValueError("invalid contact-analysis asset metadata")
        aggregate += size
        if aggregate > MAX_ANALYSIS_BYTES:
            raise ValueError("contact-analysis aggregate size limit exceeded")
        payload = _read_bounded(root.joinpath(filename), MAX_ASSET_BYTES, "asset")
        if (len(payload) != size or hashlib.sha256(payload).hexdigest() != digest
                or _png_dimensions(payload) != (width, height)):
            raise ValueError("contact-analysis asset integrity mismatch")
        result[route] = ("image/png", payload)
        seen.add(route)
    if seen != expected.keys():
        raise ValueError("contact-analysis manifest route mismatch")

    projection_bytes = json.dumps(
        projection, allow_nan=False, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    if len(projection_bytes) > MAX_ANALYSIS_BYTES:
        raise ValueError("contact-analysis projection size limit exceeded")
    return {CONTACTS_ROUTE: ("application/json; charset=utf-8", projection_bytes),
            **result}
