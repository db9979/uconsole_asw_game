"""Save validator: the entity groups and their weapon stores.

Verbatim moves from ``valid_save_document`` (submarines, animals, surface
ships, decoys and enemy torpedoes, with the launch bookkeeping of their
torpedoes, decoys, ASROCs and missiles).
"""

from src.core import config
from src.weapons import depth_charge
from src.physics import torpedo_dyn
from src.core.save_schema import SUB_CREW_FIELDS
from src.enemies.ballast import BoatBallast
from src.enemies.damage_control import BoatDamageControl
from src.enemies.endurance import SubmarineEndurance
from src.sensors.platform import SONAR_SIGNAL_MAX, validate_suite_state
from src.weapons.asw import (
    ConsumableStore,
    MAX_ASROCS,
    WeaponBattery,
    battery_matches_catalog,
    consumable_matches_catalog)
from src.core.limits import (MAX_DECOYS, MAX_ENEMY_TORPEDOES, MAX_SAVED_ASMS,
                             MAX_SAVED_ENTITIES)
from src.core.save_validate_common import bounded, finite_number, identity, point


def check_entities(data, runtime_catalog, platform_state_version, save_sim_t):
    """All entity groups; False, or (entity_ids, pending_missiles,
    used_asrocs, spent_asrocs) for the checks that follow."""
    def platform_speed_limit(profile_key, profile) -> float:
        systems = runtime_catalog.profile_systems.get(profile_key)
        if systems is not None and systems.machine_key is not None:
            return runtime_catalog.machines[systems.machine_key].maximum_speed_kn
        speed = profile.speed_kn
        return speed[1] if isinstance(speed, tuple) else speed
    groups = {"sub": ("subs",), "animal": ("animals",),
              "surface": ("civilians", "warships"), "decoy": ("decoys",),
              "enemy_torpedo": ("enemy_torpedoes",)}
    max_salvo = max(profile.asm_salvo[1]
                    for profile in runtime_catalog.surfaces.values())
    pending_missiles = 0
    pending_asrocs = 0
    pending_enemy_torpedoes = 0
    pending_decoys = 0
    spent_asrocs = {}
    # The frigate's own ASROC (no platform id) spends its own store.
    own_stores = data.get("asw", {}).get("own_stores", {})
    spent_asrocs[(None, depth_charge.OWN_ASROC_KEY)] = (
        depth_charge.OWN_ASROC_STOCK - own_stores.get("asroc", depth_charge.OWN_ASROC_STOCK))
    used_asrocs = {}
    spent_decoys = {}
    used_decoys = {}
    spent_enemy_torpedoes = {}
    used_enemy_torpedoes = {}
    entity_ids, group_ids = set(), {}
    for key, names in groups.items():
        group_ids[key] = set()
        for name in names:
            entries = data.get(name, [])
            if not isinstance(entries, list) or len(entries) > MAX_SAVED_ENTITIES:
                return False
            for entry in entries:
                if not isinstance(entry, dict):
                    return False
                # Early civilian saves may not contain an ID.
                entity_id = entry.get("id")
                if entity_id is not None:
                    if not identity(entity_id) or entity_id in entity_ids:
                        return False
                    entity_ids.add(entity_id)
                    group_ids[key].add(entity_id)
                elif name not in ("civilians", "warships", "decoys", "enemy_torpedoes"):
                    return False
                if any(not bounded(entry.get(axis), -1_000_000, 1_000_000)
                       for axis in ("x", "y")):
                    return False
                if name == "subs":
                    profile_key = entry.get("stype")
                    profile = runtime_catalog.subs.get(profile_key)
                    if profile is None:
                        return False
                elif name == "animals":
                    profile_key = entry.get("atype")
                    if profile_key not in runtime_catalog.animals:
                        return False
                elif name in ("civilians", "warships"):
                    profile_key = entry.get("signature_key")
                    profile = runtime_catalog.surfaces.get(profile_key)
                    if profile is None:
                        return False
                elif name == "decoys":
                    profile_key = entry.get("profile_key")
                    if not _check_decoy_entry(entry, profile_key, data,
                                              runtime_catalog, group_ids,
                                              used_decoys):
                        return False
                elif name == "enemy_torpedoes":
                    if not _check_enemy_torpedo_entry(
                            entry, data, runtime_catalog, group_ids,
                            used_enemy_torpedoes):
                        return False
                if name in ("subs", "civilians", "warships"):
                    if (not bounded(
                            entry.get("speed"), 0,
                            platform_speed_limit(profile_key, profile))):
                        return False
                    platform = entry.get("platform")
                    if (platform_state_version == 1 and platform is None) \
                            or (platform is not None and (
                                profile_key is None
                                or not validate_suite_state(
                                    platform, runtime_catalog, profile_key,
                                    save_sim_t))):
                        return False
                if name in ("civilians", "warships"):
                    if type(entry.get("emitter", False)) is not bool:
                        return False
                    sensor_seed = entry.get("sensor_seed")
                    if (type(sensor_seed) is not int
                            or not 0 <= sensor_seed < 2**31):
                        return False
                    observed = entry.get("sensor_contact")
                    if (observed is not None and (
                            not isinstance(observed, (list, tuple)) or len(observed) != 2
                            or any(not bounded(value, -1_000_000, 1_000_000) for value in observed))):
                        return False
                    if not bounded(entry.get("sensor_contact_age", config.RADAR_TRACK_STALE_S),
                                   0, config.RADAR_TRACK_STALE_S):
                        return False
                    direction = entry.get("orbit_direction", 1)
                    if type(direction) is not int or direction not in (-1, 1):
                        return False
                    awarded = entry.get("sunk_score_awarded", False)
                    if type(awarded) is not bool or (awarded and not entry.get("sunk", False)):
                        return False
                    if (not bounded(entry.get("torpedo_evade_left"), 0.0,
                                    config.WARSHIP_TORPEDO_EVADE_S)
                            or not bounded(entry.get("torpedo_threat_bearing"),
                                           0.0, 359.999999999)):
                        return False
                    if name == "warships":
                        pending_asrocs = _check_warship_entry(
                            entry, profile_key, entity_id, runtime_catalog,
                            save_sim_t, spent_decoys, spent_asrocs, used_asrocs,
                            pending_asrocs)
                        if pending_asrocs is False:
                            return False
                if name == "subs":
                    sub_stores = _check_sub_entry(
                        entry, profile_key, profile, entity_id, runtime_catalog,
                        spent_enemy_torpedoes, spent_decoys)
                    if sub_stores is False:
                        return False
                    battery, store = sub_stores
                for pending, width in (("pending_torpedoes", 9),
                                       ("pending_decoys", 2), ("pending_asm", 3)):
                    rows = entry.get(pending, [])
                    if (not isinstance(rows, list) or len(rows) > 10000
                            or any(not isinstance(row, (list, tuple))
                                   or len(row) != width
                                   or (pending != "pending_torpedoes"
                                       and any(not bounded(
                                           v, -1_000_000, 1_000_000)
                                               for v in row))
                                   or (pending == "pending_asm" and not identity(row[2]))
                                   for row in rows)):
                        return False
                    if pending == "pending_torpedoes" and rows:
                        if (name != "subs" or len(rows) > 2
                                or (battery is not None and len(rows) >
                                    WeaponBattery.restore(
                                        battery).capacity_total -
                                    WeaponBattery.restore(
                                        battery).remaining_total)):
                            return False
                        for row in rows:
                            if (any(not bounded(value, -1_000_000, 1_000_000)
                                    for value in row[:6])
                                    or not isinstance(row[6], str)
                                    or not identity(row[7])
                                    or row[7] != entity_id):
                                return False
                            pending_profile = runtime_catalog.torpedoes.get(row[6])
                            weapon_key = row[8]
                            if (pending_profile is None
                                    or pending_profile.used_by != "enemy"
                                    or (battery is None) != (weapon_key is None)
                                    or (weapon_key is not None and (
                                        weapon_key not in battery["weapon_keys"]
                                        or runtime_catalog.weapons[
                                            weapon_key].runtime_profile_key
                                            != row[6]))):
                                return False
                            key = (entity_id, weapon_key)
                            used_enemy_torpedoes[key] = (
                                used_enemy_torpedoes.get(key, 0) + 1)
                        pending_enemy_torpedoes += len(rows)
                        if (pending_enemy_torpedoes
                                + len(data.get("enemy_torpedoes", []))
                                > MAX_ENEMY_TORPEDOES):
                            return False
                    if pending == "pending_decoys" and rows:
                        if name != "subs" or len(rows) > 1:
                            return False
                        if store is not None:
                            consumables = ConsumableStore.restore(store)
                            if len(rows) > consumables.capacity - \
                                    consumables.remaining_total:
                                return False
                        used_decoys[entity_id] = (
                            used_decoys.get(entity_id, 0) + len(rows))
                        pending_decoys += len(rows)
                        if (pending_decoys
                                + len(data.get("decoys", [])) > MAX_DECOYS):
                            return False
                    if pending == "pending_asm" and rows:
                        if name != "warships":
                            return False
                        profile_key = entry.get("signature_key")
                        if profile_key is not None and not isinstance(profile_key, str):
                            return False
                        profile = runtime_catalog.surfaces.get(profile_key)
                        low, high = profile.asm_salvo if profile is not None else (1, max_salvo)
                        if any(not low <= row[2] <= high for row in rows):
                            return False
                        pending_missiles += sum(row[2] for row in rows)
                        if pending_missiles > MAX_SAVED_ASMS:
                            return False
    if any(count > spent_enemy_torpedoes.get(key, 0)
           for key, count in used_enemy_torpedoes.items()):
        return False
    for row in data["asw"]["asrocs"]:
        key = (row["launch_platform_id"], row["weapon_key"])
        used_asrocs[key] = used_asrocs.get(key, 0) + 1
    if any(count > spent_asrocs.get(key, 0)
           for key, count in used_asrocs.items()):
        return False
    if any(count > spent_decoys.get(source_id, 0)
           for source_id, count in used_decoys.items()):
        return False
    if len(entity_ids) > MAX_SAVED_ENTITIES:
        return False
    next_ids = data.get("next_entity_ids", {})
    if (not isinstance(next_ids, dict) or set(next_ids) != set(groups)
            or any(not identity(value) or value <= max(group_ids[key], default=0)
                   for key, value in next_ids.items())):
        return False
    return entity_ids, pending_missiles, used_asrocs, spent_asrocs


def _check_decoy_entry(entry, profile_key, data, runtime_catalog, group_ids,
                       used_decoys) -> bool:
    decoy_profile = runtime_catalog.decoys.get(profile_key)
    if decoy_profile is None:
        return False
    source_id = entry.get("source_id")
    # A decoy a mission placed has no launching unit and lies
    # still; a launched one runs at its profile speed.
    placed = source_id is None
    if (
            set(entry) != {"id", "x", "y", "depth", "course",
                           "speed", "life", "sensor_seed",
                           "profile_key", "source_id"}
            or (not placed and (
                not identity(source_id)
                or (source_id not in group_ids["sub"]
                    and source_id not in group_ids["surface"])))
            or (placed and data.get("mission_runtime", {}).get(
                "custom_definition") is None)
            or not bounded(entry.get("depth"), 0, 10000)
            or not bounded(entry.get("course"), 0, 360)
            or entry.get("course") == 360
            or decoy_profile is None
            or entry.get("speed") != (
                0.0 if placed else config.kn_to_nm_per_s(
                    decoy_profile.speed_kn))
            or not bounded(entry.get("life"), .000001,
                           decoy_profile.life_s)
            or type(entry.get("sensor_seed")) is not int
            or not 0 <= entry["sensor_seed"] < 2**31):
        return False
    if source_id is not None:
        used_decoys[source_id] = used_decoys.get(source_id, 0) + 1
    return True


def _check_enemy_torpedo_entry(entry, data, runtime_catalog, group_ids,
                               used_enemy_torpedoes) -> bool:
    if not {
            "profile_key", "guidance_x", "guidance_y",
            "terminal_active", "seeker_acquired",
            "seeker_target", "travel", "launch_platform_id",
            "launch_weapon_key", "pattern", "enable_nm",
            "search_phase", "turns_done", "search_course"} <= set(entry):
        return False
    # Save v48: the crew's search pattern and seeker enable point.
    search_course = entry["search_course"]
    if (entry["pattern"] not in torpedo_dyn.BOAT_SEARCH_PATTERNS
            or not bounded(entry["enable_nm"], torpedo_dyn.ENABLE_RANGE_MIN_NM,
                           torpedo_dyn.BOAT_ENABLE_DEFAULT_NM)
            or not bounded(entry["search_phase"], 0, 1_000_000)
            or not bounded(entry["turns_done"], 0, 1_000_000)
            or (search_course is not None
                and (not bounded(search_course, 0, 360)
                     or search_course == 360))):
        return False
    profile_key = entry.get("profile_key")
    profile = runtime_catalog.torpedoes.get(profile_key)
    if profile is None or profile.used_by != "enemy":
        return False
    gx, gy = entry.get("guidance_x"), entry.get("guidance_y")
    # A torpedo a mission placed has no launching boat and
    # no guidance datum: it runs on its course.
    placed_torpedo = (entry.get("launch_platform_id") is None
                      and entry.get("launch_weapon_key") is None
                      and data.get("mission_runtime", {}).get(
                          "custom_definition") is not None)
    if ((gx is None) != (gy is None)
            or (gx is None and not placed_torpedo)
            or (gx is not None and (
                not bounded(gx, -1_000_000, 1_000_000)
                or not bounded(gy, -1_000_000, 1_000_000)))
            or type(entry.get("terminal_active", False)) is not bool
            or type(entry.get("seeker_acquired", False)) is not bool
            or not bounded(entry.get("travel", 0), 0, torpedo_dyn.travel_bound_nm(
                profile.range_nm, profile.speed_kn, config.TORP_SPOOLUP_S))):
        return False
    seeker = entry.get("seeker_target")
    nixie_ids = {row["seq"] for row in (
        data.get("asw", {}).get("nixies", [])
        if isinstance(data.get("asw"), dict) else [])}
    # A boat's shot at a convoy may hold a merchant (1.3.291).
    civilian_ids = {row.get("id") for row in data.get("civilians", [])
                    if isinstance(row, dict)}
    valid_seeker = (seeker is None or seeker == "ship"
                    or (isinstance(seeker, str)
                        and seeker.startswith("nixie:")
                        and seeker[6:].isdigit()
                        and int(seeker[6:]) in nixie_ids)
                    or (isinstance(seeker, str)
                        and seeker.startswith("civilian:")
                        and seeker[9:].isdigit()
                        and int(seeker[9:]) in civilian_ids))
    acquired = entry.get("seeker_acquired", False)
    launch_platform_id = entry.get("launch_platform_id")
    launch_weapon_key = entry.get("launch_weapon_key")
    if placed_torpedo:
        pass
    elif (not identity(launch_platform_id)
            or launch_platform_id not in group_ids["sub"]
            or (launch_weapon_key is not None
                and (not isinstance(launch_weapon_key, str)
                     or runtime_catalog.weapons.get(
                         launch_weapon_key) is None
                     or runtime_catalog.weapons[
                         launch_weapon_key].weapon_type != "torpedo"
                     or runtime_catalog.weapons[
                         launch_weapon_key].runtime_profile_key
                         != profile_key))):
        return False
    if not placed_torpedo:
        launch_key = (launch_platform_id, launch_weapon_key)
        used_enemy_torpedoes[launch_key] = (
            used_enemy_torpedoes.get(launch_key, 0) + 1)
    if (not valid_seeker or acquired != (seeker is not None)
            or (acquired and not entry["terminal_active"])
            or not bounded(entry.get("course"), 0, 360)
            or entry.get("course") == 360
            or not bounded(entry.get("depth"), 0, 10000)
            or not identity(entry.get("idx"))):
        return False
    return True


def _check_warship_entry(entry, profile_key, entity_id, runtime_catalog,
                         save_sim_t, spent_decoys, spent_asrocs, used_asrocs,
                         pending_asrocs):
    """A warship's ASROC battery and pending launches; False, or the
    running count of pending ASROCs."""
    if not {
            "asroc_battery", "pending_asroc",
            "asw_last_seen"} <= set(entry):
        return False
    left = entry.get("countermeasures_left")
    if (type(left) is not int
            or not 0 <= left <= config.WARSHIP_TORPEDO_DECOYS):
        return False
    if entity_id is not None:
        spent_decoys[entity_id] = (
            config.WARSHIP_TORPEDO_DECOYS - left)
    battery = entry.get("asroc_battery")
    expected_battery = WeaponBattery.from_catalog(
        runtime_catalog, profile_key, "asroc")
    if ((battery is None) !=
            (expected_battery is None)):
        return False
    if battery is not None and not battery_matches_catalog(
            battery, runtime_catalog, profile_key, "asroc"):
        return False
    if battery is not None:
        restored_battery = WeaponBattery.restore(battery)
        if entity_id is None:
            return False
        for weapon_key in restored_battery.weapon_keys:
            capacity = sum(
                item.capacity
                for item in restored_battery.magazines.values()
                if item.weapon_key == weapon_key)
            remaining = sum(
                item.stowed
                for item in restored_battery.magazines.values()
                if item.weapon_key == weapon_key)
            remaining += sum(
                tube.loaded_weapon_key == weapon_key
                or tube.loading_weapon_key == weapon_key
                for tube in restored_battery.tubes)
            spent_asrocs[(entity_id, weapon_key)] = (
                capacity - remaining)
    last_seen = entry.get("asw_last_seen", -1.0)
    if (not finite_number(last_seen)
            or not -1.0 <= last_seen <= save_sim_t):
        return False
    pending_asroc = entry.get("pending_asroc", [])
    if (not isinstance(pending_asroc, list)
            or len(pending_asroc) > MAX_ASROCS
            or (battery is not None and
                len(pending_asroc) >
                WeaponBattery.restore(
                    battery).capacity_total -
                WeaponBattery.restore(
                    battery).remaining_total)):
        return False
    for row in pending_asroc:
        if (not isinstance(row, dict)
                or set(row) != {"x", "y", "datum_x",
                               "datum_y", "weapon_key",
                               "target_depth_m"}
                or any(not bounded(row.get(field),
                                       -1_000_000, 1_000_000)
                       for field in ("x", "y", "datum_x",
                                     "datum_y"))
                or not bounded(row.get("target_depth_m"),
                               0, 10000)):
            return False
        weapon = runtime_catalog.weapons.get(
            row.get("weapon_key"))
        if (weapon is None or weapon.weapon_type != "asroc"
                or battery is None
                or row["weapon_key"] not in
                    battery["weapon_keys"]):
            return False
        key = (entity_id, row["weapon_key"])
        used_asrocs[key] = used_asrocs.get(key, 0) + 1
    pending_asrocs += len(pending_asroc)
    if pending_asrocs > MAX_ASROCS:
        return False
    return pending_asrocs


def _check_sub_entry(entry, profile_key, profile, entity_id, runtime_catalog,
                     spent_enemy_torpedoes, spent_decoys):
    """A submarine's crew, stores and memory; False, or its (battery,
    store) for the pending-launch checks."""
    if not {
            "asw_battery", "countermeasure_store",
            "endurance"} | SUB_CREW_FIELDS <= set(entry):
        return False
    if not point(entry.get("start_pos")):
        return False
    if (type(entry["manual"]) is not bool
            or type(entry["manual_ping_pending"]) is not bool
            or not bounded(entry["order_course"], -360.0, 720.0)
            or not bounded(entry["order_speed"], 0.0, 100.0)
            or not bounded(entry["order_depth"], 0.0, 10_000.0)
            or not (entry["last_bottom_m"] is None
                    or bounded(entry["last_bottom_m"], 0.0, 20_000.0))):
        return False
    try:
        BoatBallast.restore(entry["ballast"])
        BoatDamageControl.restore(entry["damage_control"])
    except (TypeError, ValueError):
        return False
    if not bounded(entry.get("active_ping_cd"), 0.0,
                   config.SUB_ACTIVE_PING_COOLDOWN_S):
        return False
    if not bounded(entry.get("radar_hold_s"), 0.0, config.SUB_RADAR_HOLD_S):
        return False
    if (type(entry.get("blow_available")) is not bool
            or type(entry.get("emergency_ascent")) is not bool
            or (entry["emergency_ascent"]
                and entry["blow_available"])
            or not bounded(entry.get("transient_left"), 0.0, 60.0)
            or not bounded(entry.get("flood_noise_left"), 0.0, 60.0)
            or type(entry.get("flood_quiet")) is not bool
            or type(entry.get("flood_seq")) is not int
            or not 0 <= entry["flood_seq"] < config.SUB_FLOOD_SEQ_MAX
            or not bounded(entry.get("ai_tube_left"), -1.0,
                           config.UBOOT_TUBE_FLOOD_QUIET_S)
            or (entry["ai_tube_left"] < 0.0
                and entry["ai_tube_left"] != -1.0)
            or type(entry.get("ai_fire_pending")) is not bool
            or not bounded(entry.get("hull_fatigue"), 0.0, 1.0)
            or not bounded(entry.get("speed_order"), 0.0, 100.0)
            or not isinstance(entry.get("tma_track"), list)
            or len(entry["tma_track"]) > config.BEARING_TRACK_MAX_PTS
            or any(not isinstance(point, dict) or set(point) != {
                "t", "bearing", "fx", "fy", "fcourse",
                "uncertainty_deg", "fspeed"}
                   or not all(bounded(value, -1_000_000, 1e12)
                              for value in point.values())
                   or not 0.05 <= point["uncertainty_deg"] <= 180.0
                   for point in entry["tma_track"])
            or (entry.get("tma_track_id") is not None
                and (not isinstance(entry["tma_track_id"], str)
                     or len(entry["tma_track_id"]) > 64))
            or not bounded(entry.get("tma_next_t"), 0.0, 1e12)
            or not bounded(entry.get("torpedo_alarm_left"), -1.0, 15.0)
            or "torpedo_threat_bearing" not in entry
            or not (entry["torpedo_threat_bearing"] is None
                    or bounded(entry["torpedo_threat_bearing"], 0.0, 360.0))):
        return False
    endurance_profile = runtime_catalog.endurances.get(
        f"endurance.{profile_key}")
    endurance_state = entry.get("endurance")
    if ((endurance_profile is None) != (endurance_state is None)):
        return False
    if endurance_profile is not None:
        try:
            SubmarineEndurance.restore(
                endurance_profile, endurance_state)
        except (TypeError, ValueError):
            return False
    torpedoes_left = entry.get("torpedoes_left")
    if (type(torpedoes_left) is not int
            or not 0 <= torpedoes_left <= 100):
        return False
    battery = entry.get("asw_battery")
    expected_battery = WeaponBattery.from_catalog(
        runtime_catalog, profile_key, "torpedo")
    if ((battery is None) !=
            (expected_battery is None)):
        return False
    if battery is not None and not battery_matches_catalog(
            battery, runtime_catalog, profile_key, "torpedo"):
        return False
    if battery is not None:
        restored_battery = WeaponBattery.restore(battery)
        for weapon_key in restored_battery.weapon_keys:
            capacity = sum(
                item.capacity for item in
                restored_battery.magazines.values()
                if item.weapon_key == weapon_key)
            remaining = sum(
                item.stowed for item in
                restored_battery.magazines.values()
                if item.weapon_key == weapon_key)
            remaining += sum(
                tube.loaded_weapon_key == weapon_key
                or tube.loading_weapon_key == weapon_key
                for tube in restored_battery.tubes)
            spent_enemy_torpedoes[(entity_id, weapon_key)] = (
                capacity - remaining)
    else:
        spent_enemy_torpedoes[(entity_id, None)] = max(
            0, profile.torpedoes - torpedoes_left)
    store = entry.get("countermeasure_store")
    expected_store = ConsumableStore.from_catalog(
        runtime_catalog, profile_key, "acoustic_decoy")
    if ((store is None) != (expected_store is None)):
        return False
    if store is not None and not consumable_matches_catalog(
            store, runtime_catalog, profile_key,
            "acoustic_decoy"):
        return False
    if store is not None:
        consumables = ConsumableStore.restore(store)
        spent_decoys[entity_id] = (
            consumables.capacity - consumables.remaining_total)
    battery = entry.get("asw_battery")
    store = entry.get("countermeasure_store")
    if (battery is not None
            and WeaponBattery.restore(battery).remaining_total
            != entry.get("torpedoes_left")):
        return False
    memory = entry.get("memory", {})
    if not isinstance(memory, dict):
        return False
    for age in ("last_ping_age", "last_torpedo_age"):
        value = memory.get(age)
        if value is not None and not bounded(value, 0, 1e12):
            return False
    if not bounded(memory.get("contact_age", config.SUB_EVADE_DURATION_S),
                   0, config.SUB_EVADE_DURATION_S):
        return False
    bearing = memory.get("contact_bearing")
    if bearing is not None and (not bounded(bearing, 0, 360) or bearing == 360):
        return False
    if not {"contact_sigma_nm", "contact_t", "contact_reopen_left"} <= set(memory):
        return False
    if (type(memory["contact_reopen_left"]) is not int
            or not 0 <= memory["contact_reopen_left"] <= 10):
        return False
    sigma = memory["contact_sigma_nm"]
    if sigma is not None and not bounded(sigma, 0, 10_000):
        return False
    contact_t = memory["contact_t"]
    if contact_t is not None and not bounded(contact_t, 0, 1e12):
        return False
    if not bounded(entry.get("solution_threshold"), 0.05, 0.40):
        return False
    observed = memory.get("contact")
    if observed is not None:
        if (not isinstance(observed, dict)
                or set(observed) != {"x", "y", "speed", "course", "noise"}
                or any(not bounded(observed[axis], -1_000_000, 1_000_000)
                       for axis in ("x", "y"))
                or not bounded(observed["speed"], 0, 100)
                or not bounded(observed["course"], 0, 360)
                # The remembered received signal, not the ship's
                # own noise figure (that stays below it).
                or not bounded(observed["noise"], 0, SONAR_SIGNAL_MAX)):
            return False
    return battery, store
