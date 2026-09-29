"""User unit profiles (Unit Editor documents) as runtime catalog entries.

A custom mission that names ``user.*`` profiles runs on a catalog made of
the packaged profiles plus exactly the referenced user profiles. The
extension goes through the save's own runtime snapshot path, so a mission
with user units saves and loads like any other (the save's
``catalog_snapshot`` carries the user entries) and every entry passes the
same strict schema as the packaged data.

Only runtime-relevant fields are copied. The Wikipedia import extras
(``radar_emitter``, ``radar_range_km``, ``weapons``, ``countermeasures``)
stay descriptive, as does a surface profile's ``hostile`` flag (the side
belongs to the mission unit).
"""

from __future__ import annotations

import copy
import re
from typing import Any, Iterable, Mapping

from src.data.catalog import (ContactCatalog,
                              catalog_from_runtime_snapshot)

# Unit-editor profile kind -> catalog document (surfaces split by category).
KIND_FILES = {"sub": "subs.json", "aircraft": "aircraft.json",
              "animal": "animals.json", "torpedo": "torpedoes.json",
              "decoy": "decoys.json"}
SUB_PROPULSIONS = ("Diesel-elektrisch", "elektrisch/AIP", "elektrisch/Kernantrieb")
_CATALOG_OPTIONAL = ("wiki_url", "default_faction", "rcs_m2")
_KIND_FIELDS = {
    "sub": ("name", "speed_kn", "max_depth_m", "torpedoes", "quiet",
            "aggression", "spawn_weight", "acoustic"),
    "surface": ("name", "category", "speed_kn", "callsigns", "esm_prob",
                "asm_salvo", "asm_cooldown_s", "loiter_nm", "spawn_weight",
                "acoustic"),
    "aircraft": ("name", "nation", "speed_kn", "esm", "esm_range_nm",
                 "loiter_nm", "spawn_weight", "signature_text"),
    "animal": ("name", "depth_min", "depth_max", "speed_kn", "quiet",
               "size_nm", "spawn_weight", "lines", "signature_text"),
    "torpedo": ("name", "used_by", "speed_kn", "range_nm", "hit_dist_nm"),
    "decoy": ("name", "life_s", "speed_kn", "cooldown_s", "chance", "lines",
              "signature_text"),
}


def sub_propulsion(text: str) -> str:
    """The catalog's submarine propulsion for an editor's free text:
    nuclear ("kern"/"nuclear") or AIP ("aip") by keyword, else diesel."""
    lowered = str(text).lower()
    if "kern" in lowered or "nuclear" in lowered:
        return "elektrisch/Kernantrieb"
    if "aip" in lowered:
        return "elektrisch/AIP"
    return "Diesel-elektrisch"


def _acoustic(value: Mapping[str, Any], category: str, label: str) -> dict:
    acoustic = {key: copy.deepcopy(item) for key, item in value.items() if key != "key"}
    acoustic["category"] = category
    if not str(acoustic.get("label", "")).strip():
        acoustic["label"] = label
    if not str(acoustic.get("signature_text", "")).strip():
        acoustic["signature_text"] = label
    if not str(acoustic.get("propulsion", "")).strip():
        acoustic["propulsion"] = "unknown"
    return acoustic


def catalog_entry(unit: Mapping[str, Any]) -> tuple[str, dict]:
    """(catalog document, entry) for one validated Unit Editor profile."""
    kind = unit["profile_kind"]
    entry: dict[str, Any] = {"key": unit["key"]}
    for field in _KIND_FIELDS[kind]:
        entry[field] = copy.deepcopy(unit[field])
    for field in _CATALOG_OPTIONAL:
        if field in unit and kind in ("sub", "surface", "aircraft"):
            entry[field] = copy.deepcopy(unit[field])
    name = str(unit["name"])
    if kind == "sub":
        entry["acoustic"] = _acoustic(unit["acoustic"], "U_BOOT", name)
        entry["acoustic"]["propulsion"] = sub_propulsion(unit["acoustic"].get("propulsion", ""))
        return KIND_FILES[kind], entry
    if kind == "surface":
        warship = unit["category"] == "KAMPFSCHIFF"
        entry["hostile"] = warship
        entry["acoustic"] = _acoustic(unit["acoustic"], unit["category"], name)
        return ("warships.json" if warship else "civilians.json"), entry
    if kind == "aircraft":
        entry["kind"] = unit["aircraft_kind"]
        if not str(entry.get("signature_text", "")).strip():
            entry.pop("signature_text", None)
        return KIND_FILES[kind], entry
    if kind in ("animal", "decoy"):
        if not str(entry.get("signature_text", "")).strip():
            entry["signature_text"] = name
        return KIND_FILES[kind], entry
    if kind == "torpedo":
        if unit.get("acoustic") is not None:
            entry["acoustic"] = _acoustic(unit["acoustic"], "FAHRZEUG", name)
        return KIND_FILES[kind], entry
    raise ValueError(f"unknown profile kind: {kind}")


def _torpedo_acoustic(snapshot: dict, catalog: ContactCatalog, name: str) -> dict:
    """A user torpedo without its own signature sounds like the bound
    enemy torpedo (relabelled)."""
    bound = catalog.runtime_bindings["enemy_torpedo"]
    for entry in snapshot["entries"]["torpedoes.json"]:
        if entry["key"] == bound and "acoustic" in entry:
            acoustic = copy.deepcopy(entry["acoustic"])
            acoustic["label"] = name
            return acoustic
    raise ValueError("enemy torpedo binding has no acoustic signature")


def _decoy_signature(snapshot: dict, catalog: ContactCatalog, key: str, entry: dict) -> dict:
    """The acoustic library entry of a user decoy: the bound decoy's
    signature under the user key, name and description."""
    bound = catalog.runtime_bindings["submarine_decoy"]
    for signature in snapshot["entries"]["acoustics.json"]:
        if signature["key"] == bound:
            result = copy.deepcopy(signature)
            result.update(key=key, label=entry["name"],
                          signature_text=entry["signature_text"])
            return result
    raise ValueError("decoy binding has no acoustic signature")


# Built-in submarine whose systems (sensors, mast radar, tubes, decoys,
# battery/diesel/AIP) a user submarine of that propulsion takes over.
SUB_SYSTEM_TEMPLATES = {"Diesel-elektrisch": "diesel_alt",
                        "elektrisch/AIP": "aip_modern",
                        "elektrisch/Kernantrieb": "ssn"}
_V2_FIELDS = ("references", "machines", "endurances", "sensors", "emitters",
              "weapons", "launchers", "magazines", "countermeasures")


def _renamed(key: str, template: str, user_key: str) -> str:
    """``machine.diesel_alt`` -> ``machine.user.x``;
    ``sensor.diesel_alt.sonar`` -> ``sensor.user.x.sonar``."""
    return re.sub(rf"(?<=\.){re.escape(template)}(?=\.|$)", user_key, key, count=1)


def _clone_sub_systems(snapshot: dict, entry: dict) -> None:
    """Attach copies of the propulsion template's v2 systems to a user
    submarine: its speeds, shaft revolutions and torpedo load are the
    user's, everything else is the template's."""
    template = SUB_SYSTEM_TEMPLATES[entry["acoustic"]["propulsion"]]
    user_key = entry["key"]
    component = snapshot["components"]["subs.json"]
    renames = {}
    for field in _V2_FIELDS:
        for row in list(component.get(field, [])):
            if _renamed(row["key"], template, user_key) == row["key"]:
                continue
            clone = copy.deepcopy(row)
            clone["key"] = renames[row["key"]] = _renamed(row["key"], template, user_key)
            component[field].append(clone)
    for field in _V2_FIELDS:
        for row in component.get(field, []):
            if row["key"] not in renames.values():
                continue
            for name, value in list(row.items()):
                if name != "key" and isinstance(value, str) and value in renames:
                    row[name] = renames[value]
                elif isinstance(value, list) and value and all(
                        isinstance(item, str) for item in value):
                    row[name] = [renames.get(item, item) for item in value]
            if field == "machines":
                low, high = (float(value) for value in entry["speed_kn"])
                high = max(high, 0.1)
                cruise = low if low > 0 else high / 2.0
                row["cruise_speed_kn"], row["maximum_speed_kn"] = cruise, high
                if row["quiet_speed_kn"] is not None:
                    row["quiet_speed_kn"] = min(row["quiet_speed_kn"], cruise)
                rpm = entry["acoustic"]["rpm_range"]
                if rpm[0] > 0 and rpm[1] > rpm[0]:
                    row["shaft_rpm"] = list(rpm)
                # The machine's lines carry the audible tonals: the user's
                # tonal band sets the cruise fundamental (lower edge) and the
                # high-speed one (upper edge), the broadband its noise.
                low_hz, high_hz = (float(value) for value in entry["acoustic"]["tonal_band_hz"])
                if low_hz > 0:
                    high_hz = max(high_hz, low_hz)
                    row["cruise_lines"] = [[low_hz, 1.0, 1.5], [2 * low_hz, 0.5, 1.2]]
                    row["high_speed_lines"] = [[high_hz, 1.0, 2.0], [2 * high_hz, 0.5, 1.5]]
                broadband = entry["acoustic"]["broadband"]
                if broadband is not None:
                    row["cruise_broadband"] = list(broadband)
                    row["high_speed_broadband"] = [min(1.0, broadband[0] + 0.25),
                                                   broadband[1], broadband[2]]
            elif field == "magazines":
                row["mission_count"] = int(entry["torpedoes"])
    profile = next(row for row in component["profiles"] if row["profile_key"] == template)
    clone = copy.deepcopy(profile)
    clone["profile_key"] = user_key
    for name, value in list(clone.items()):
        if isinstance(value, str) and value in renames:
            clone[name] = renames[value]
        elif isinstance(value, list):
            clone[name] = [renames.get(item, item) for item in value]
    component["profiles"].append(clone)


def extend_catalog(catalog: ContactCatalog,
                   units: Iterable[Mapping[str, Any]]) -> ContactCatalog:
    """A new runtime catalog with the given (validated) user profiles
    added; raises ``ValueError`` when one does not fit the runtime schema
    (the error names the profile)."""
    units = sorted(units, key=lambda unit: str(unit["key"]))
    if not units:
        return catalog
    snapshot = catalog.runtime_snapshot()
    for unit in units:
        filename, entry = catalog_entry(unit)
        if filename == "torpedoes.json" and entry["used_by"] == "enemy" \
                and "acoustic" not in entry:
            entry["acoustic"] = _torpedo_acoustic(snapshot, catalog, entry["name"])
        snapshot["entries"][filename].append(entry)
        if filename == "subs.json":
            _clone_sub_systems(snapshot, entry)
        if filename == "decoys.json":
            snapshot["entries"]["acoustics.json"].append(
                _decoy_signature(snapshot, catalog, entry["key"], entry))
    try:
        return catalog_from_runtime_snapshot(snapshot)
    except ValueError as exc:
        keys = ", ".join(str(unit["key"]) for unit in units)
        raise ValueError(f"user profiles {keys}: {exc}") from exc


def referenced_user_keys(definition: Mapping[str, Any]) -> list[str]:
    """The ``user.*`` profile keys a mission definition references, sorted."""
    units = definition.get("units", {})
    keys = {unit.get("profile") for unit in units.get("exact", [])}
    for group in units.get("random_groups", []):
        keys.update(group.get("profiles", []))
    return sorted(key for key in keys if isinstance(key, str) and key.startswith("user."))


__all__ = ["KIND_FILES", "SUB_PROPULSIONS", "catalog_entry",
           "extend_catalog", "referenced_user_keys", "sub_propulsion"]
