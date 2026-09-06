"""Strictly validate the packaged contact catalog.

Usage: python tools/gen_contacts.py [--check] [DIRECTORY]

The historical filename is retained for tooling compatibility. This command
never generates or modifies catalog data.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import catalog  # noqa: E402


FILES = {
    "subs.json": {"key", "name", "speed_kn", "max_depth_m", "torpedoes",
                  "quiet", "aggression", "spawn_weight", "acoustic"},
    "warships.json": {"key", "name", "category", "hostile", "speed_kn",
                      "callsigns", "esm_prob", "asm_salvo", "asm_cooldown_s",
                      "loiter_nm", "spawn_weight", "acoustic"},
    "civilians.json": {"key", "name", "category", "hostile", "speed_kn",
                       "callsigns", "esm_prob", "asm_salvo", "asm_cooldown_s",
                       "loiter_nm", "spawn_weight", "acoustic"},
    "aircraft.json": {"key", "name", "nation", "kind", "speed_kn", "esm",
                      "esm_range_nm", "loiter_nm", "spawn_weight",
                      "signature_text"},
    "animals.json": {"key", "name", "depth_min", "depth_max", "speed_kn",
                     "quiet", "size_nm", "spawn_weight", "lines",
                     "signature_text"},
    "torpedoes.json": {"key", "name", "used_by", "speed_kn", "range_nm",
                       "hit_dist_nm"},
    "decoys.json": {"key", "name", "life_s", "speed_kn", "cooldown_s",
                    "chance", "lines", "signature_text"},
    "acoustics.json": {"key", "label", "propulsion", "blades", "rpm_range",
                       "tonal_band_hz", "cavitation_tendency", "category",
                       "secondary_tonals", "broadband", "signature_text"},
}
ACOUSTIC_FIELDS = FILES["acoustics.json"] - {"key"}
CATEGORIES = {*catalog.CIVIL_CATEGORIES, "KAMPFSCHIFF", "U_BOOT",
              "FAHRZEUG", "BIOLOGISCH"}


def _fail(where, message):
    raise ValueError(f"{where}: {message}")


def _object(value, fields, where, optional=()):
    if not isinstance(value, dict):
        _fail(where, "object expected")
    required = fields - set(optional)
    missing = required - value.keys()
    extra = value.keys() - fields
    if missing:
        _fail(where, f"missing fields: {', '.join(sorted(missing))}")
    if extra:
        _fail(where, f"unknown fields: {', '.join(sorted(extra))}")


def _string(value, where):
    if not isinstance(value, str) or not value.strip():
        _fail(where, "non-empty string expected")


def _number(value, where, low=0.0, high=None, strictly_positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, "number expected")
    if not math.isfinite(value):
        _fail(where, "finite number expected")
    if strictly_positive and value <= 0.0:
        _fail(where, "must be greater than zero")
    if not strictly_positive and value < low:
        _fail(where, f"must be at least {low}")
    if high is not None and value > high:
        _fail(where, f"must be at most {high}")


def _pair(value, where, allow_equal=False, integers=False):
    if not isinstance(value, list) or len(value) != 2:
        _fail(where, "two-item array expected")
    for index, item in enumerate(value):
        _number(item, f"{where}[{index}]")
        if integers and (not isinstance(item, int) or isinstance(item, bool)):
            _fail(f"{where}[{index}]", "integer expected")
    if value[0] > value[1] or (not allow_equal and value[0] == value[1]):
        _fail(where, "range must be ordered")


def _lines(value, where):
    if not isinstance(value, list):
        _fail(where, "array expected")
    for index, line in enumerate(value):
        if not isinstance(line, list) or len(line) != 3:
            _fail(f"{where}[{index}]", "three-item array expected")
        _number(line[0], f"{where}[{index}][0]", strictly_positive=True)
        _number(line[1], f"{where}[{index}][1]", high=1.0)
        _number(line[2], f"{where}[{index}][2]", strictly_positive=True)


def _acoustic(value, where, expected_category=None):
    _object(value, ACOUSTIC_FIELDS, where)
    for field in ("label", "propulsion", "signature_text"):
        _string(value[field], f"{where}.{field}")
    if not isinstance(value["blades"], list) or any(
            isinstance(blade, bool) or not isinstance(blade, int) or blade <= 0
            for blade in value["blades"]):
        _fail(f"{where}.blades", "positive integer array expected")
    _pair(value["rpm_range"], f"{where}.rpm_range",
          allow_equal=value["rpm_range"] == [0.0, 0.0])
    _pair(value["tonal_band_hz"], f"{where}.tonal_band_hz")
    _number(value["cavitation_tendency"],
            f"{where}.cavitation_tendency", high=1.0)
    if value["category"] not in CATEGORIES:
        _fail(f"{where}.category", "invalid category")
    if expected_category is not None and value["category"] != expected_category:
        _fail(f"{where}.category", f"must be {expected_category}")
    _lines(value["secondary_tonals"], f"{where}.secondary_tonals")
    broadband = value["broadband"]
    if broadband is not None:
        if not isinstance(broadband, list) or len(broadband) != 3:
            _fail(f"{where}.broadband", "null or three-item array expected")
        _number(broadband[0], f"{where}.broadband[0]", high=1.0)
        _number(broadband[1], f"{where}.broadband[1]", strictly_positive=True)
        _number(broadband[2], f"{where}.broadband[2]", strictly_positive=True)
        if broadband[1] >= broadband[2]:
            _fail(f"{where}.broadband", "frequency range must be ordered")


def _common(entry, where):
    _string(entry["key"], f"{where}.key")
    _string(entry["name"], f"{where}.name")


def _validate_entry(filename, entry, where):
    optional = {"acoustic"} if filename == "torpedoes.json" else set()
    _object(entry, FILES[filename] | optional, where, optional)
    if filename == "acoustics.json":
        _string(entry["key"], f"{where}.key")
        _acoustic({key: value for key, value in entry.items() if key != "key"},
                  where)
        return
    _common(entry, where)
    if filename == "subs.json":
        _pair(entry["speed_kn"], f"{where}.speed_kn")
        _number(entry["max_depth_m"], f"{where}.max_depth_m", strictly_positive=True)
        if isinstance(entry["torpedoes"], bool) or not isinstance(entry["torpedoes"], int) or entry["torpedoes"] < 0:
            _fail(f"{where}.torpedoes", "non-negative integer expected")
        _number(entry["quiet"], f"{where}.quiet", high=1.0)
        _number(entry["aggression"], f"{where}.aggression", high=1.0)
        _number(entry["spawn_weight"], f"{where}.spawn_weight")
        _acoustic(entry["acoustic"], f"{where}.acoustic", "U_BOOT")
    elif filename in {"warships.json", "civilians.json"}:
        allowed = {"KAMPFSCHIFF"} if filename == "warships.json" else set(catalog.CIVIL_CATEGORIES)
        if entry["category"] not in allowed:
            _fail(f"{where}.category", "invalid surface category")
        if not isinstance(entry["hostile"], bool) or entry["hostile"] != (filename == "warships.json"):
            _fail(f"{where}.hostile", "does not match surface catalog")
        _pair(entry["speed_kn"], f"{where}.speed_kn")
        if not isinstance(entry["callsigns"], list) or any(not isinstance(x, str) for x in entry["callsigns"]):
            _fail(f"{where}.callsigns", "string array expected")
        _number(entry["esm_prob"], f"{where}.esm_prob", high=1.0)
        _pair(entry["asm_salvo"], f"{where}.asm_salvo", allow_equal=True, integers=True)
        for field in ("asm_cooldown_s", "loiter_nm", "spawn_weight"):
            _number(entry[field], f"{where}.{field}")
        _acoustic(entry["acoustic"], f"{where}.acoustic", entry["category"])
    elif filename == "aircraft.json":
        _string(entry["nation"], f"{where}.nation")
        if entry["kind"] not in {"civil", "military"}:
            _fail(f"{where}.kind", "invalid aircraft kind")
        if not isinstance(entry["esm"], bool):
            _fail(f"{where}.esm", "boolean expected")
        _number(entry["speed_kn"], f"{where}.speed_kn", strictly_positive=True)
        _number(entry["esm_range_nm"], f"{where}.esm_range_nm")
        _pair(entry["loiter_nm"], f"{where}.loiter_nm", allow_equal=True)
        _number(entry["spawn_weight"], f"{where}.spawn_weight")
        _string(entry["signature_text"], f"{where}.signature_text")
    elif filename == "animals.json":
        for field in ("depth_min", "depth_max", "speed_kn", "size_nm", "spawn_weight"):
            _number(entry[field], f"{where}.{field}")
        if entry["depth_min"] >= entry["depth_max"]:
            _fail(where, "depth range must be ordered")
        _number(entry["quiet"], f"{where}.quiet", high=1.0)
        _lines(entry["lines"], f"{where}.lines")
        _string(entry["signature_text"], f"{where}.signature_text")
    elif filename == "torpedoes.json":
        if entry["used_by"] not in {"frigate", "helo", "enemy"}:
            _fail(f"{where}.used_by", "invalid torpedo owner")
        for field in ("speed_kn", "range_nm", "hit_dist_nm"):
            _number(entry[field], f"{where}.{field}", strictly_positive=True)
        if "acoustic" in entry:
            _acoustic(entry["acoustic"], f"{where}.acoustic", "FAHRZEUG")
    elif filename == "decoys.json":
        for field in ("life_s", "speed_kn", "cooldown_s"):
            _number(entry[field], f"{where}.{field}", strictly_positive=True)
        _number(entry["chance"], f"{where}.chance", high=1.0)
        _lines(entry["lines"], f"{where}.lines")
        _string(entry["signature_text"], f"{where}.signature_text")


def _read_documents(base_dir):
    documents = {}
    for filename in FILES:
        path = base_dir / filename
        with path.open("r", encoding="utf-8") as stream:
            document = json.load(stream)
        _object(document, {"version", "entries"}, filename)
        if type(document["version"]) is not int or document["version"] != 1:
            _fail(f"{filename}.version", "unsupported schema version")
        if not isinstance(document["entries"], list) or not document["entries"]:
            _fail(f"{filename}.entries", "non-empty array expected")
        seen = set()
        for index, entry in enumerate(document["entries"]):
            where = f"{filename}.entries[{index}]"
            _validate_entry(filename, entry, where)
            key = entry["key"]
            if key in seen:
                _fail(where, f"duplicate key {key!r}")
            seen.add(key)
        documents[filename] = document
    return documents


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
            "hostile": profile.hostile, "speed_kn": list(profile.speed_kn),
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


def validate(base_dir):
    base_dir = Path(base_dir)
    documents = _read_documents(base_dir)
    primary_files = [name for name in FILES if name != "acoustics.json"]
    owners = {}
    for filename in primary_files:
        for entry in documents[filename]["entries"]:
            if entry["key"] in owners:
                _fail(entry["key"], f"duplicate profile ID in {owners[entry['key']]} and {filename}")
            owners[entry["key"]] = filename
    library_keys = [entry["key"] for entry in documents["acoustics.json"]["entries"]]
    expected_library = {"animal", *(
        entry["key"] for entry in documents["decoys.json"]["entries"])}
    if set(library_keys) != expected_library:
        _fail("acoustics.json", "must define animal and every decoy library signature")

    loaded = catalog._load_catalog_from(base_dir)
    runtime = _runtime_documents(loaded, library_keys)
    for filename, document in documents.items():
        if runtime[filename] != document:
            _fail(filename, "runtime load parity mismatch")
    return loaded


def check(base_dir):
    try:
        loaded = validate(base_dir)
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
