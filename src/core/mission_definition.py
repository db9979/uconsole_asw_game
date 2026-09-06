"""Standalone mission authoring model, validation, and seeded static preview."""

from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from src.data.validation import (ValidationIssue, enum, finite_number, integer,
                                 issue, pair, sequence, text, unique,
                                 validate_user_key)


MISSION_VERSION = 1
SIDES = ("friendly", "neutral", "hostile")
OBJECTIVE_TYPES = ("sink", "survive", "protect", "reach")
EVENT_TYPES = ("message", "spawn", "weather", "objective")
PLACEMENT_TYPES = ("fixed", "sector")


@dataclass(frozen=True)
class FieldMetadata:
    supported: bool
    effective: bool
    note: str = ""


# ``supported`` means represented and validated by this editor. ``effective``
# only means consumed by the current game runtime, not that a field is useful.
MISSION_FIELD_METADATA = {
    "key": FieldMetadata(True, False, "User content identity; integration pending."),
    "name": FieldMetadata(True, False),
    "description": FieldMetadata(True, False),
    "seed": FieldMetadata(True, False),
    "world": FieldMetadata(True, False, "Fixed coordinates and sector references are previewed."),
    "player": FieldMetadata(True, False),
    "environment": FieldMetadata(True, False),
    "units.exact": FieldMetadata(True, False),
    "units.random_groups": FieldMetadata(True, False, "Resolved only in static preview."),
    "objective": FieldMetadata(True, False),
    "events": FieldMetadata(True, False),
}


def default_mission(key: str = "user.new_mission") -> dict[str, Any]:
    return {
        "version": MISSION_VERSION,
        "key": key,
        "name": "New mission",
        "description": "",
        "seed": 1,
        "world": {"kind": "fixed", "size_nm": 500.0, "sectors": []},
        "player": {"x": 250.0, "y": 250.0, "course_deg": 0.0,
                   "speed_kn": 12.0},
        "environment": {"sea_state": 3, "time_hour": 12.0,
                        "thermocline_depth_m": 80.0, "weather": "clear"},
        "units": {"exact": [], "random_groups": []},
        "objective": {"type": "sink", "target_ids": [], "time_limit_s": 3600.0},
        "events": [],
    }


def _obj(value: Any, path: str, problems: list[ValidationIssue]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        problems.append(issue(path, "object", "must be an object"))
        return None
    return value


def _placement(value: Any, path: str, size: float,
               sectors: set[str]) -> list[ValidationIssue]:
    problems = []
    value = _obj(value, path, problems)
    if value is None:
        return problems
    kind = value.get("kind")
    problems += enum(kind, f"{path}.kind", PLACEMENT_TYPES)
    if kind == "fixed":
        problems += finite_number(value.get("x"), f"{path}.x", minimum=0, maximum=size)
        problems += finite_number(value.get("y"), f"{path}.y", minimum=0, maximum=size)
    elif kind == "sector":
        problems += text(value.get("sector"), f"{path}.sector", maximum=64)
        if isinstance(value.get("sector"), str) and value["sector"] not in sectors:
            problems.append(issue(f"{path}.sector", "reference", "unknown sector"))
    return problems


def validate_mission(data: Mapping[str, Any],
                     profile_keys: Iterable[str] | None = None) -> list[ValidationIssue]:
    """Strictly validate a mission without mutating or loading runtime state."""
    if not isinstance(data, Mapping):
        return [issue("", "object", "mission must be an object")]
    problems = []
    problems += integer(data.get("version"), "version", minimum=MISSION_VERSION,
                        maximum=MISSION_VERSION)
    problems += validate_user_key(data.get("key"))
    problems += text(data.get("name"), "name", maximum=80)
    problems += text(data.get("description", ""), "description", required=False, maximum=2000)
    problems += integer(data.get("seed"), "seed", minimum=0, maximum=2**31 - 1)

    world = _obj(data.get("world"), "world", problems)
    size, sectors, sector_specs = 500.0, set(), {}
    if world is not None:
        problems += enum(world.get("kind"), "world.kind", ("fixed", "reference"))
        problems += finite_number(world.get("size_nm"), "world.size_nm", minimum=10, maximum=5000)
        if isinstance(world.get("size_nm"), (int, float)) and not isinstance(world.get("size_nm"), bool):
            size = float(world["size_nm"])
        if world.get("kind") == "reference":
            problems += text(world.get("reference"), "world.reference", maximum=128)
            ref = world.get("reference")
            if isinstance(ref, str) and (ref.startswith(("/", "~")) or "\\" in ref
                                         or ".." in ref.split("/")):
                problems.append(issue("world.reference", "path", "must be a logical reference, not a path"))
        raw_sectors = world.get("sectors", [])
        if not isinstance(raw_sectors, list):
            problems.append(issue("world.sectors", "array", "must be an array"))
            raw_sectors = []
        ids = [item.get("id") for item in raw_sectors if isinstance(item, Mapping)]
        problems += unique(ids, "world.sectors.id")
        for index, sector in enumerate(raw_sectors):
            path = f"world.sectors[{index}]"
            sector = _obj(sector, path, problems)
            if sector is None:
                continue
            problems += text(sector.get("id"), f"{path}.id", maximum=64)
            for field in ("x", "y", "width", "height"):
                minimum = 0.01 if field in ("width", "height") else 0
                problems += finite_number(sector.get(field), f"{path}.{field}", minimum=minimum,
                                          maximum=size)
            if isinstance(sector.get("id"), str):
                sectors.add(sector["id"])
                sector_specs[sector["id"]] = sector
            if all(isinstance(sector.get(f), (int, float)) for f in ("x", "y", "width", "height")):
                if sector["x"] + sector["width"] > size or sector["y"] + sector["height"] > size:
                    problems.append(issue(path, "bounds", "sector exceeds world bounds"))

    player = _obj(data.get("player"), "player", problems)
    if player is not None:
        problems += finite_number(player.get("x"), "player.x", minimum=0, maximum=size)
        problems += finite_number(player.get("y"), "player.y", minimum=0, maximum=size)
        problems += finite_number(player.get("course_deg"), "player.course_deg", minimum=0, maximum=359.999)
        problems += finite_number(player.get("speed_kn"), "player.speed_kn", minimum=0, maximum=100)

    environment = _obj(data.get("environment"), "environment", problems)
    if environment is not None:
        problems += integer(environment.get("sea_state"), "environment.sea_state", minimum=0, maximum=9)
        problems += finite_number(environment.get("time_hour"), "environment.time_hour", minimum=0, maximum=23.999)
        problems += finite_number(environment.get("thermocline_depth_m"),
                                  "environment.thermocline_depth_m", minimum=0, maximum=2000)
        problems += enum(environment.get("weather"), "environment.weather",
                         ("clear", "rain", "storm", "fog"))

    units = _obj(data.get("units"), "units", problems)
    exact, groups = [], []
    if units is not None:
        exact = units.get("exact", [])
        groups = units.get("random_groups", [])
        if not isinstance(exact, list):
            problems.append(issue("units.exact", "array", "must be an array")); exact = []
        if not isinstance(groups, list):
            problems.append(issue("units.random_groups", "array", "must be an array")); groups = []
    profile_set = set(profile_keys) if profile_keys is not None else None
    unit_ids = []
    for index, unit in enumerate(exact):
        path = f"units.exact[{index}]"
        unit = _obj(unit, path, problems)
        if unit is None:
            continue
        unit_ids.append(unit.get("id"))
        problems += text(unit.get("id"), f"{path}.id", maximum=64)
        problems += text(unit.get("profile"), f"{path}.profile", maximum=80)
        problems += enum(unit.get("side"), f"{path}.side", SIDES)
        problems += _placement(unit.get("placement"), f"{path}.placement", size, sectors)
        problems += finite_number(unit.get("course_deg", 0), f"{path}.course_deg", minimum=0, maximum=359.999)
        problems += finite_number(unit.get("speed_kn", 0), f"{path}.speed_kn", minimum=0, maximum=1000)
        if "depth_m" in unit:
            problems += finite_number(unit["depth_m"], f"{path}.depth_m", minimum=0, maximum=2000)
        if profile_set is not None and unit.get("profile") not in profile_set:
            problems.append(issue(f"{path}.profile", "reference", "unknown unit profile"))
    group_ids = []
    for index, group in enumerate(groups):
        path = f"units.random_groups[{index}]"
        group = _obj(group, path, problems)
        if group is None:
            continue
        group_ids.append(group.get("id"))
        problems += text(group.get("id"), f"{path}.id", maximum=64)
        profiles = group.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            problems.append(issue(f"{path}.profiles", "array", "must be a non-empty array"))
            profiles = []
        else:
            problems += unique(profiles, f"{path}.profiles")
            for pindex, profile in enumerate(profiles):
                problems += text(profile, f"{path}.profiles[{pindex}]", maximum=80)
                if profile_set is not None and profile not in profile_set:
                    problems.append(issue(f"{path}.profiles[{pindex}]", "reference", "unknown unit profile"))
        problems += pair(group.get("count"), f"{path}.count", minimum=0, maximum=100,
                         integer_values=True)
        problems += enum(group.get("side"), f"{path}.side", SIDES)
        problems += _placement(group.get("placement"), f"{path}.placement", size, sectors)
    problems += unique(unit_ids + group_ids, "units.id")

    objective = _obj(data.get("objective"), "objective", problems)
    if objective is not None:
        problems += enum(objective.get("type"), "objective.type", OBJECTIVE_TYPES)
        problems += finite_number(objective.get("time_limit_s"), "objective.time_limit_s",
                                  minimum=1, maximum=7 * 24 * 3600)
        targets = objective.get("target_ids", [])
        if not isinstance(targets, list):
            problems.append(issue("objective.target_ids", "array", "must be an array"))
        else:
            problems += unique(targets, "objective.target_ids")
            known = set(unit_ids + group_ids)
            for index, target in enumerate(targets):
                problems += text(target, f"objective.target_ids[{index}]", maximum=64)
                if target not in known:
                    problems.append(issue(f"objective.target_ids[{index}]", "reference", "unknown unit/group id"))

    events = data.get("events")
    if not isinstance(events, list):
        problems.append(issue("events", "array", "must be an array")); events = []
    event_ids = []
    for index, event in enumerate(events):
        path = f"events[{index}]"
        event = _obj(event, path, problems)
        if event is None:
            continue
        event_ids.append(event.get("id"))
        problems += text(event.get("id"), f"{path}.id", maximum=64)
        problems += finite_number(event.get("at_s"), f"{path}.at_s", minimum=0,
                                  maximum=7 * 24 * 3600)
        problems += enum(event.get("type"), f"{path}.type", EVENT_TYPES)
        problems += text(event.get("message", ""), f"{path}.message", required=False, maximum=500)
        if event.get("type") == "message":
            problems += text(event.get("message"), f"{path}.message", maximum=500)
        elif event.get("type") == "spawn":
            target = event.get("target_id")
            problems += text(target, f"{path}.target_id", maximum=64)
            if target not in set(group_ids):
                problems.append(issue(f"{path}.target_id", "reference", "spawn event requires a random group id"))
        elif event.get("type") == "weather":
            problems += enum(event.get("weather"), f"{path}.weather",
                             ("clear", "rain", "storm", "fog"))
        elif event.get("type") == "objective":
            problems += enum(event.get("action"), f"{path}.action", ("complete", "fail"))
    problems += unique(event_ids, "events.id")
    return problems


def _stable_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def static_preview(data: Mapping[str, Any], seed: int | None = None) -> dict[str, Any]:
    """Resolve authoring data into deterministic markers without touching Game."""
    problems = validate_mission(data)
    if problems:
        from src.data.validation import ContentValidationError
        raise ContentValidationError(problems)
    seed = int(data["seed"] if seed is None else seed)
    sectors = {sector["id"]: sector for sector in data["world"].get("sectors", [])}

    def locate(placement: Mapping[str, Any], rng: random.Random) -> tuple[float, float]:
        if placement["kind"] == "fixed":
            return float(placement["x"]), float(placement["y"])
        sector = sectors[placement["sector"]]
        return (sector["x"] + rng.random() * sector["width"],
                sector["y"] + rng.random() * sector["height"])

    markers = [{"id": "player", "profile": "player", "side": "friendly",
                "x": float(data["player"]["x"]), "y": float(data["player"]["y"]),
                "source": "player"}]
    for unit in data["units"]["exact"]:
        rng = random.Random(_stable_seed(seed, f"exact:{unit['id']}"))
        x, y = locate(unit["placement"], rng)
        markers.append({"id": unit["id"], "profile": unit["profile"],
                        "side": unit["side"], "x": x, "y": y, "source": "exact"})
    for group in data["units"]["random_groups"]:
        rng = random.Random(_stable_seed(seed, f"group:{group['id']}"))
        count = rng.randint(group["count"][0], group["count"][1])
        for index in range(count):
            x, y = locate(group["placement"], rng)
            markers.append({"id": f"{group['id']}:{index + 1}",
                            "group_id": group["id"], "profile": rng.choice(group["profiles"]),
                            "side": group["side"], "x": x, "y": y,
                            "source": "seeded_random"})
    return {"seed": seed, "world_size_nm": float(data["world"]["size_nm"]),
            "markers": markers, "sectors": copy.deepcopy(list(sectors.values())),
            "events": copy.deepcopy(sorted(data["events"], key=lambda event: event["at_s"])),
            "objective": copy.deepcopy(data["objective"]),
            "runtime_effective": False}


class MissionDefinition:
    def __init__(self, data: Mapping[str, Any] | None = None):
        self.data = copy.deepcopy(dict(data)) if data is not None else default_mission()

    @property
    def key(self) -> str:
        return str(self.data.get("key", ""))

    @property
    def field_metadata(self) -> Mapping[str, FieldMetadata]:
        return MISSION_FIELD_METADATA

    def validate(self, profile_keys: Iterable[str] | None = None) -> list[ValidationIssue]:
        return validate_mission(self.data, profile_keys)

    def preview(self, seed: int | None = None) -> dict[str, Any]:
        return static_preview(self.data, seed)

    def clone(self, key: str) -> "MissionDefinition":
        cloned = copy.deepcopy(self.data)
        cloned["key"] = key
        return MissionDefinition(cloned)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)
