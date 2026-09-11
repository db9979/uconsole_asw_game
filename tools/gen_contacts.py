"""Strictly validate the packaged contact catalog.

Usage: python tools/gen_contacts.py [--check] [DIRECTORY]

The historical filename is retained for tooling compatibility. This command
never generates or modifies catalog data.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import catalog  # noqa: E402


FILES = catalog.CONTACT_FIELDS


def _fail(where, message):
    raise ValueError(f"{where}: {message}")


def _read_documents(base_dir):
    return {filename: catalog._read_document(base_dir / filename)
            for filename in FILES}


def _same_json(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (left.keys() == right.keys()
                and all(_same_json(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same_json(a, b) for a, b in zip(left, right))
    return left == right


def _sig_dict(signature):
    return {
        "label": signature.label, "propulsion": signature.propulsion,
        "blades": list(signature.blade_counts),
        "rpm_range": list(signature.rpm_range),
        "tonal_band_hz": list(signature.tonal_band_hz),
        "cavitation_tendency": signature.cavitation_tendency,
        "category": signature.category,
        "secondary_tonals": [list(line) for line in signature.secondary_tonals],
        "broadband": list(signature.broadband) if signature.broadband else None,
        "signature_text": signature.signature_text,
    }


def _runtime_documents(cat, library_keys):
    def surface(profile):
        return {
            "key": profile.key, "name": profile.name, "category": profile.category,
            "hostile": profile.category == "KAMPFSCHIFF",
            "speed_kn": list(profile.speed_kn),
            "callsigns": list(profile.callsigns), "esm_prob": profile.esm_prob,
            "asm_salvo": list(profile.asm_salvo),
            "asm_cooldown_s": profile.asm_cooldown_s, "loiter_nm": profile.loiter_nm,
            "spawn_weight": profile.spawn_weight, "acoustic": _sig_dict(profile.acoustic),
        }

    entries = {}
    entries["subs.json"] = [{
        "key": p.key, "name": p.name, "speed_kn": list(p.speed_kn),
        "max_depth_m": p.max_depth_m, "torpedoes": p.torpedoes,
        "quiet": p.quiet, "aggression": p.aggression,
        "spawn_weight": p.spawn_weight, "acoustic": _sig_dict(p.acoustic),
    } for p in cat.subs.values()]
    entries["warships.json"] = [surface(p) for p in cat.hostile_surfaces]
    entries["civilians.json"] = [surface(p) for p in cat.civilian_surfaces]
    entries["aircraft.json"] = [{
        "key": p.key, "name": p.name, "nation": p.nation, "kind": p.kind,
        "speed_kn": p.speed_kn, "esm": p.esm, "esm_range_nm": p.esm_range_nm,
        "loiter_nm": list(p.loiter_nm), "spawn_weight": p.spawn_weight,
        "signature_text": p.signature_text,
    } for p in cat.aircraft.values()]
    entries["animals.json"] = [{
        "key": p.key, "name": p.name, "depth_min": p.depth_min,
        "depth_max": p.depth_max, "speed_kn": p.speed_kn, "quiet": p.quiet,
        "size_nm": p.size_nm, "spawn_weight": p.spawn_weight,
        "lines": [list(line) for line in p.lines], "signature_text": p.signature_text,
    } for p in cat.animals.values()]
    entries["torpedoes.json"] = []
    for p in cat.torpedoes.values():
        value = {"key": p.key, "name": p.name, "used_by": p.used_by,
                 "speed_kn": p.speed_kn, "range_nm": p.range_nm,
                 "hit_dist_nm": p.hit_dist_nm}
        if p.acoustic is not None:
            value["acoustic"] = _sig_dict(p.acoustic)
        entries["torpedoes.json"].append(value)
    entries["decoys.json"] = [{
        "key": p.key, "name": p.name, "life_s": p.life_s,
        "speed_kn": p.speed_kn, "cooldown_s": p.cooldown_s, "chance": p.chance,
        "lines": [list(line) for line in p.lines], "signature_text": p.signature_text,
    } for p in cat.decoys.values()]
    entries["acoustics.json"] = [
        {"key": key, **_sig_dict(cat.acoustic_by_key[key])}
        for key in library_keys
    ]
    return {name: {"version": 1, "entries": values}
            for name, values in entries.items()}


def _validate_provenance_coverage(cat):
    expected = set()
    registries = {
        "endurances": cat.endurances,
        "sensors": cat.sensors, "emitters": cat.emitters,
        "launchers": cat.launchers, "magazines": cat.magazines,
        "countermeasures": cat.countermeasures,
    }
    for profile_key, systems in cat.profile_systems.items():
        resource = cat.profile_resources[profile_key]
        for name, key, registry in (
                ("reference", systems.reference_key, cat.references),
                ("machine", systems.machine_key, cat.machines)):
            if key is not None:
                component = registry[key]
                expected.update((resource, profile_key, f"/{name}/{field}")
                                for field in component.__dataclass_fields__
                                if field != "key")
        for registry_name, keys in (
                ("endurances", ((f"endurance.{profile_key}",)
                                if f"endurance.{profile_key}" in cat.endurances else ())),
                ("sensors", systems.sensor_keys),
                ("emitters", systems.emitter_keys),
                ("launchers", systems.launcher_keys),
                ("magazines", systems.magazine_keys),
                ("countermeasures", systems.countermeasure_keys)):
            for key in keys:
                component = registries[registry_name][key]
                expected.update((resource, profile_key,
                                 f"/{registry_name}/{key}/{field}")
                                for field in component.__dataclass_fields__
                                if field != "key")
        weapon_keys = {
            weapon for key in systems.launcher_keys
            for weapon in cat.launchers[key].weapon_keys
        } | {cat.magazines[key].weapon_key for key in systems.magazine_keys}
        for key in weapon_keys:
            expected.update((resource, profile_key, f"/weapons/{key}/{field}")
                            for field in cat.weapons[key].__dataclass_fields__
                            if field != "key")
    actual = {
        (claim.resource, claim.profile_key, field_path)
        for claim in cat.provenance_claims for field_path in claim.field_paths
    }
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _fail(catalog.SOURCES_FILENAME,
              f"incomplete field coverage (missing={missing[:8]}, extra={extra[:8]})")


def validate(base_dir):
    base_dir = Path(base_dir)
    documents = _read_documents(base_dir)
    library_keys = [entry["key"] for entry in documents["acoustics.json"]["entries"]]

    loaded = catalog._load_catalog_from(base_dir)
    runtime = _runtime_documents(loaded, library_keys)
    for filename, document in documents.items():
        if runtime[filename]["entries"] != document["entries"]:
            _fail(filename, "runtime load parity mismatch")
    reconstructed = loaded.reconstruct_documents()
    for filename, document in documents.items():
        if not _same_json(reconstructed[filename], document):
            _fail(filename, "lossless document reconstruction mismatch")
    source_path = base_dir / catalog.SOURCES_FILENAME
    if source_path.is_file():
        source_document = catalog._read_json(source_path)
        if not _same_json(loaded.reconstruct_provenance(), source_document):
            _fail(catalog.SOURCES_FILENAME, "lossless provenance reconstruction mismatch")
    return loaded


def check(base_dir):
    try:
        loaded = validate(base_dir)
        _validate_provenance_coverage(loaded)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        print(f"contact catalog invalid: {exc}", file=sys.stderr)
        return 1
    print(f"contact catalog valid: {len(loaded.acoustic_profiles)} acoustic profiles")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("directory", nargs="?", default=catalog.CONTACTS_DIR)
    args = parser.parse_args(argv)
    return check(args.directory)


if __name__ == "__main__":
    sys.exit(main())
