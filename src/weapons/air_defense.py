"""Profile-driven missile defense loadout and strict persistent stores."""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from importlib import resources

from src.weapons.asw import ConsumableStore, valid_consumable_state


AIR_DEFENSE_STATE_VERSION = 1
MAX_VLS_CELLS = 1024
MAX_FIRE_CHANNELS = 64


def _object(value, fields, where):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{where}: exact object expected")
    return value


def _number(value, low, high, where, *, integer=False):
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{where}: bounded number expected")
    return value


def _key(value, prefix, where):
    if (not isinstance(value, str) or not value.startswith(prefix)
            or not 1 <= len(value) <= 128):
        raise ValueError(f"{where}: logical key expected")
    return value


@lru_cache(maxsize=1)
def air_defense_loadout():
    path = resources.files("data.loadouts") / "air_defense.json"
    with path.open("r", encoding="utf-8") as stream:
        return validate_air_defense_loadout(json.load(stream))


def validate_air_defense_loadout(value):
    _object(value, {"version", "asm", "sam", "vls", "ciws", "softkill"},
            "air_defense")
    if value["version"] != 1:
        raise ValueError("air_defense.version: unsupported version")
    asm = _object(value["asm"], {
        "key", "speed_kn", "range_nm", "turn_rate_deg_s", "jam_probability",
        "jam_break_nm", "hit_distance_nm"}, "air_defense.asm")
    sam = _object(value["sam"], {
        "key", "speed_kn", "range_nm", "turn_rate_deg_s", "seeker_range_nm",
        "kill_distance_nm", "observation_max_age_s"}, "air_defense.sam")
    vls = _object(value["vls"], {
        "key", "capacity", "sam_loadout", "fire_channels"}, "air_defense.vls")
    ciws = _object(value["ciws"], {
        "key", "ammo", "range_nm", "rounds_per_attempt", "cycle_s",
        "kill_probability", "observation_max_age_s"}, "air_defense.ciws")
    softkill = _object(value["softkill"], {
        "key", "effect_type", "mission_count", "ready_count", "reload_s",
        "range_nm", "effect_duration_s", "defeat_probability"},
        "air_defense.softkill")
    for profile, prefix, where in ((asm, "weapon.", "asm"),
                                   (sam, "weapon.", "sam"),
                                   (vls, "launcher.", "vls"),
                                   (ciws, "weapon.", "ciws"),
                                   (softkill, "countermeasure.", "softkill")):
        _key(profile["key"], prefix, f"air_defense.{where}.key")
    for profile, fields in ((asm, ("speed_kn", "range_nm", "turn_rate_deg_s",
                                    "jam_break_nm", "hit_distance_nm")),
                            (sam, ("speed_kn", "range_nm", "turn_rate_deg_s",
                                    "seeker_range_nm", "kill_distance_nm",
                                    "observation_max_age_s")),
                            (ciws, ("range_nm", "cycle_s",
                                     "observation_max_age_s"))):
        for field in fields:
            _number(profile[field], .000001, 100000, f"air_defense.{field}")
    for profile, field in ((asm, "jam_probability"), (ciws, "kill_probability"),
                           (softkill, "defeat_probability")):
        _number(profile[field], 0, 1, f"air_defense.{field}")
    capacity = _number(vls["capacity"], 1, MAX_VLS_CELLS,
                       "air_defense.vls.capacity", integer=True)
    _number(vls["sam_loadout"], 0, capacity, "air_defense.vls.sam_loadout",
            integer=True)
    _number(vls["fire_channels"], 1, MAX_FIRE_CHANNELS,
            "air_defense.vls.fire_channels", integer=True)
    _number(ciws["ammo"], 0, 100000, "air_defense.ciws.ammo", integer=True)
    rounds = _number(ciws["rounds_per_attempt"], 1, 10000,
                     "air_defense.ciws.rounds_per_attempt", integer=True)
    if rounds > ciws["ammo"]:
        raise ValueError("air_defense.ciws: burst exceeds ammunition")
    total = _number(softkill["mission_count"], 0, 10000,
                    "air_defense.softkill.mission_count", integer=True)
    _number(softkill["ready_count"], 0, total,
            "air_defense.softkill.ready_count", integer=True)
    _number(softkill["reload_s"], 0, 604800, "air_defense.softkill.reload_s")
    _number(softkill["range_nm"], .000001, 10000, "air_defense.softkill.range_nm")
    duration = softkill["effect_duration_s"]
    if not isinstance(duration, list) or len(duration) != 2:
        raise ValueError("air_defense.softkill.effect_duration_s: pair expected")
    low = _number(duration[0], .000001, 3600, "air_defense.softkill.duration")
    high = _number(duration[1], low, 3600, "air_defense.softkill.duration")
    if softkill["effect_type"] not in ("chaff", "rf_softkill"):
        raise ValueError("air_defense.softkill.effect_type: invalid type")
    return copy.deepcopy(value)


def make_softkill_store(loadout):
    profile = loadout["softkill"]
    return ConsumableStore(profile["key"], profile["effect_type"], None,
                           profile["mission_count"], profile["ready_count"],
                           profile["reload_s"])


def valid_air_defense_state(value, *, vls_cells, ciws_ammo, ciws_cooldown_s,
                            chaff_cd):
    try:
        _object(value, {"version", "loadout", "sam_remaining", "essm_seq",
                        "softkill"}, "air_defense_state")
        if value["version"] != AIR_DEFENSE_STATE_VERSION:
            return False
        loadout = validate_air_defense_loadout(value["loadout"])
        remaining = _number(value["sam_remaining"], 0,
                            loadout["vls"]["sam_loadout"],
                            "air_defense_state.sam_remaining", integer=True)
        sequence = _number(value["essm_seq"], 0, 2**63 - 1,
                           "air_defense_state.essm_seq", integer=True)
        if sequence != loadout["vls"]["sam_loadout"] - remaining:
            return False
        store = value["softkill"]
        if not valid_consumable_state(store):
            return False
        profile = loadout["softkill"]
        if (store["key"] != profile["key"]
                or store["effect_type"] != profile["effect_type"]
                or store["payload_key"] is not None
                or store["capacity"] != profile["mission_count"]
                or store["reload_s"] != profile["reload_s"]
                or store["ready"] + len(store["loading"]) > profile["ready_count"]):
            return False
        expected_cd = min(store["loading"], default=0.0)
        return (type(vls_cells) is int and vls_cells == remaining
                and type(ciws_ammo) is int and 0 <= ciws_ammo <= loadout["ciws"]["ammo"]
                and type(ciws_cooldown_s) in (int, float)
                and math.isfinite(ciws_cooldown_s)
                and 0 <= ciws_cooldown_s <= loadout["ciws"]["cycle_s"]
                and type(chaff_cd) in (int, float) and math.isfinite(chaff_cd)
                and chaff_cd == expected_cd)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
