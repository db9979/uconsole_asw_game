"""Profile-driven missile defense loadout and strict persistent stores."""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from importlib import resources

from src.weapons.asw import ConsumableStore, valid_consumable_state


AIR_DEFENSE_STATE_VERSION = 2
MAX_VLS_CELLS = 1024
MAX_FIRE_CHANNELS = 64
MAX_RAIDERS = 16


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
    _object(value, {"version", "asm", "sam", "vls", "ciws", "softkill",
                    "raider", "aa_gun"}, "air_defense")
    if value["version"] != 2:
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
    raider = _object(value["raider"], {
        "key", "speed_kn", "altitude_m", "hp", "evasion", "weapon_range_nm",
        "salvo", "weapon_cooldown_s", "retreat_radius_nm"},
        "air_defense.raider")
    aa_gun = _object(value["aa_gun"], {
        "key", "ammo", "range_nm", "rounds_per_attempt", "cycle_s",
        "hit_probability", "observation_max_age_s"}, "air_defense.aa_gun")
    _key(raider["key"], "aircraft.", "air_defense.raider.key")
    _key(aa_gun["key"], "weapon.", "air_defense.aa_gun.key")
    for profile, fields in ((raider, ("speed_kn", "weapon_range_nm",
                                      "weapon_cooldown_s",
                                      "retreat_radius_nm")),
                            (aa_gun, ("range_nm", "cycle_s",
                                      "observation_max_age_s"))):
        for field in fields:
            _number(profile[field], .000001, 100000, f"air_defense.{field}")
    _number(raider["altitude_m"], 0, 20000, "air_defense.altitude_m")
    _number(raider["hp"], 1, 100000, "air_defense.hp", integer=True)
    _number(raider["evasion"], 0, 1, "air_defense.evasion")
    salvo = raider["salvo"]
    if not isinstance(salvo, list) or len(salvo) != 2:
        raise ValueError("air_defense.raider.salvo: pair expected")
    salvo_min = _number(salvo[0], 1, 1000, "air_defense.salvo", integer=True)
    _number(salvo[1], salvo_min, 1000, "air_defense.salvo", integer=True)
    _number(aa_gun["ammo"], 0, 100000, "air_defense.ammo", integer=True)
    aa_rounds = _number(aa_gun["rounds_per_attempt"], 1, 10000,
                        "air_defense.rounds_per_attempt", integer=True)
    if aa_rounds > aa_gun["ammo"]:
        raise ValueError("air_defense.aa_gun: burst exceeds ammunition")
    _number(aa_gun["hit_probability"], 0, 1, "air_defense.hit_probability")
    return copy.deepcopy(value)


def make_softkill_store(loadout):
    profile = loadout["softkill"]
    return ConsumableStore(profile["key"], profile["effect_type"], None,
                           profile["mission_count"], profile["ready_count"],
                           profile["reload_s"])


def _valid_raider_row(row, loadout):
    profile = loadout["raider"]
    if (not isinstance(row, dict)
            or set(row) != {"x", "y", "course", "seq", "phase", "hp",
                            "salvo_cd", "pending_asm", "attack_t"}):
        return False
    if (not _is_finite(row["x"]) or not _is_finite(row["y"])
            or not bounded_range(row["x"], -1_000_000, 1_000_000)
            or not bounded_range(row["y"], -1_000_000, 1_000_000)):
        return False
    course = row["course"]
    if (type(course) not in (int, float) or not math.isfinite(course)
            or not 0 <= course < 360):
        return False
    if (type(row["seq"]) is not int or row["seq"] < 1
            or row["seq"] > 2**63 - 1):
        return False
    if row["phase"] not in ("APPROACH", "ATTACK", "RETREAT"):
        return False
    hp = row["hp"]
    if (type(hp) is not int or not 1 <= hp <= profile["hp"]):
        return False
    salvo_cd = row["salvo_cd"]
    if (type(salvo_cd) not in (int, float) or not math.isfinite(salvo_cd)
            or not -3600 <= salvo_cd <= 3600):
        return False
    pending = row["pending_asm"]
    if (type(pending) is not int or not 0 <= pending <= profile["salvo"][1] * 8):
        return False
    attack_t = row["attack_t"]
    if (type(attack_t) not in (int, float) or not math.isfinite(attack_t)
            or not 0 <= attack_t <= 3600):
        return False
    return True


def _is_finite(value):
    return type(value) in (int, float) and not isinstance(value, bool) \
        and math.isfinite(value)


def bounded_range(value, low, high):
    return _is_finite(value) and low <= value <= high


def valid_air_defense_state(value, *, vls_cells, ciws_ammo, ciws_cooldown_s,
                             chaff_cd):
    try:
        _object(value, {"version", "loadout", "sam_remaining", "essm_seq",
                        "softkill", "aa_ammo", "aa_cooldown_s", "raiders",
                        "raider_seq", "waves_spawned"}, "air_defense_state")
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
        aa_profile = loadout["aa_gun"]
        aa_ammo = _number(value["aa_ammo"], 0, aa_profile["ammo"],
                          "air_defense_state.aa_ammo", integer=True)
        aa_cd = _number(value["aa_cooldown_s"], 0, aa_profile["cycle_s"],
                        "air_defense_state.aa_cooldown_s")
        raiders = value["raiders"]
        if (not isinstance(raiders, list) or len(raiders) > MAX_RAIDERS
                or not all(_valid_raider_row(row, loadout) for row in raiders)
                or any(row["seq"] > value["raider_seq"] for row in raiders)):
            return False
        _number(value["raider_seq"], 0, 2**63 - 1,
                "air_defense_state.raider_seq", integer=True)
        _number(value["waves_spawned"], 0, 2**63 - 1,
                "air_defense_state.waves_spawned", integer=True)
        return (type(vls_cells) is int and vls_cells == remaining
                and type(ciws_ammo) is int and 0 <= ciws_ammo <= loadout["ciws"]["ammo"]
                and type(ciws_cooldown_s) in (int, float)
                and math.isfinite(ciws_cooldown_s)
                and 0 <= ciws_cooldown_s <= loadout["ciws"]["cycle_s"]
                and type(chaff_cd) in (int, float) and math.isfinite(chaff_cd)
                and chaff_cd == expected_cd)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
