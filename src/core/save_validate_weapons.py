"""Save validator: helicopter, buoys, aircraft and weapons in flight.

Verbatim moves from ``valid_save_document``.
"""

from src.core import config
from src.weapons import depth_charge
from src.physics import torpedo_dyn
from src.physics import missile as missile_physics
from src.air.mpa import PatrolAircraft
from src.core.consort import ConsortOrders
from src.core import habits
from src.core.game_llm import valid_llm_state
from src.air.sonobuoy import OWNERS as BUOY_OWNERS
from src.weapons.torpedo import Torpedo
from src.weapons.asw import WeaponBattery
from src.core.limits import (MAX_SAVED_ASMS, MAX_SAVED_ESSMS,
                             MAX_SAVED_PLAYER_TORPEDOES)
from src.core.save_validate_common import bounded, identity


def check_helo(data, runtime_catalog):
    """The helicopter; False, or its saved row."""
    helo = data.get("helo")
    if not isinstance(helo, dict):
        return False
    if isinstance(helo, dict):
        required_helo = {
            "state", "x", "y", "course", "torps", "torpedo_profile_key",
            "buoys_left", "fuel_s", "waypoint_x", "waypoint_y",
            "dip_state", "dip_depth_m", "dip_depth_target_m",
            "dip_water_depth_m", "dip_ping_cooldown", "hover_x", "hover_y",
            "pattern", "pattern_queue", "mad_mode", "radar_on", "prep_s",
            "hoist", "hoist_s",
        }
        if set(helo) != required_helo:
            return False
        queue = helo["pattern_queue"]
        if (helo["pattern"] not in ("single", "field", "barrier", "circle")
                or type(helo["mad_mode"]) is not bool
                or type(helo["radar_on"]) is not bool
                or type(helo["hoist"]) is not bool
                or not bounded(helo["hoist_s"], 0, config.TASK_SAR_HELO_S_PER_PERSON)
                or (helo["hoist"] and helo["state"] != "AUF")
                or (helo["prep_s"] is not None
                    and (not bounded(helo["prep_s"], 0, config.HELO_PREP_S)
                         or helo["state"] != "HANGAR"))
                or not isinstance(queue, list) or len(queue) > 8
                or any(not isinstance(point, list) or len(point) != 2
                       or not bounded(point[0], -1_000_000, 1_000_000)
                       or not bounded(point[1], -1_000_000, 1_000_000)
                       for point in queue)
                or (helo["pattern"] == "single") != (not queue)
                or (helo["mad_mode"] and helo["state"] != "AUF")):
            return False
        if ((helo["hover_x"] is None) != (helo["hover_y"] is None)
                or (helo["hover_x"] is not None and (
                    not bounded(helo["hover_x"], -1_000_000, 1_000_000)
                    or not bounded(helo["hover_y"], -1_000_000, 1_000_000)))):
            return False
        if (helo.get("state") not in ("HANGAR", "AUF", "ZURUECK", "VERLOREN")
                or not bounded(helo.get("x"), -1_000_000, 1_000_000)
                or not bounded(helo.get("y"), -1_000_000, 1_000_000)
                or not bounded(helo.get("course"), 0, 360)
                or helo.get("course") == 360
                or type(helo.get("torps")) is not int
                or not 0 <= helo["torps"] <= config.HELO_TORPS
                or type(helo.get("buoys_left")) is not int
                or not 0 <= helo["buoys_left"] <= config.BUOY_COUNT
                or not bounded(helo.get("fuel_s"), 0, config.HELO_FUEL_S)
                or helo.get("dip_state") not in (
                    "STOWED", "DEPLOYING", "DEPLOYED", "RETRIEVING")
                or not bounded(helo.get("dip_depth_m"), 0,
                               config.HELO_DIP_DEPTH_MAX_M)
                or not bounded(helo.get("dip_depth_target_m"),
                               config.HELO_DIP_DEPTH_MIN_M,
                               config.HELO_DIP_DEPTH_MAX_M)
                or not bounded(helo.get("dip_water_depth_m"), 0, 10000)
                or not bounded(helo.get("dip_ping_cooldown"), 0,
                               config.HELO_DIP_PING_COOLDOWN_S)
                or (helo["dip_state"] == "STOWED"
                    and (helo["dip_depth_m"] != 0
                         or helo["dip_water_depth_m"] != 0))
                or (helo["dip_state"] in ("DEPLOYING", "DEPLOYED")
                    and helo["state"] != "AUF")
                or (helo["dip_state"] != "STOWED"
                    and (helo["dip_water_depth_m"]
                         <= config.HELO_DIP_BOTTOM_CLEARANCE_M
                         or helo["dip_depth_m"] > helo["dip_water_depth_m"]
                         - config.HELO_DIP_BOTTOM_CLEARANCE_M
                         or helo["dip_depth_target_m"]
                         > helo["dip_water_depth_m"]
                         - config.HELO_DIP_BOTTOM_CLEARANCE_M))
                or (helo["dip_state"] == "DEPLOYED"
                    and helo["dip_depth_m"] != helo["dip_depth_target_m"])
                or (helo["state"] in ("HANGAR", "VERLOREN")
                    and helo["dip_state"] != "STOWED")):
            return False
        wx, wy = helo.get("waypoint_x"), helo.get("waypoint_y")
        if ((wx is None) != (wy is None)
                or (wx is not None and (
                    not bounded(wx, -1_000_000, 1_000_000)
                    or not bounded(wy, -1_000_000, 1_000_000)))):
            return False
    if isinstance(helo, dict):
        profile = runtime_catalog.torpedoes.get(helo.get("torpedo_profile_key"))
        if profile is None or profile.used_by != "helo":
            return False
    return helo


def check_buoys_and_aircraft(data, helo, world_size, save_sim_t):
    """Buoys, the patrol aircraft, the language model's marks, the
    player's habits and the consort; False, or the buoy ids."""
    buoys = data.get("buoys", [])
    max_mpa_buoys = config.MPA_BUOYS * config.MPA_SORTIES
    if (not isinstance(buoys, list)
            or len(buoys) > config.BUOY_COUNT + max_mpa_buoys):
        return False
    # Save v21: the patrol aircraft (its stores bound its buoys and torpedoes).
    mpa = data.get("mpa")
    if not PatrolAircraft.valid_state(mpa, world_size):
        return False
    # Save v49: the language model's marks and the experimental opponent's plan.
    if not valid_llm_state(data.get("llm")):
        return False
    # Save v50: the player's habits the enemy knows (None until decided).
    if not habits.valid_state(data.get("habits")):
        return False
    # Save v47: the consort destroyer's orders; it must be a friendly warship.
    consort = data.get("consort")
    if not ConsortOrders.valid_state(consort, world_size, save_sim_t):
        return False
    if consort is not None and not any(
            isinstance(row, dict) and row.get("id") == consort["warship_id"]
            and isinstance(row.get("platform"), dict)
            and row["platform"].get("side") == "friendly"
            for row in data.get("warships", [])):
        return False
    buoy_ids = set()
    for buoy in buoys:
        if (not isinstance(buoy, dict)
                or set(buoy) != {"x", "y", "seq", "battery_s", "mode",
                                 "last_ping_epoch", "owner"}
                or buoy["owner"] not in BUOY_OWNERS
                or not bounded(buoy.get("x"), -1_000_000, 1_000_000)
                or not bounded(buoy.get("y"), -1_000_000, 1_000_000)
                or not identity(buoy.get("seq"))
                or buoy["seq"] in buoy_ids
                or not bounded(buoy.get("battery_s"), .000001,
                               config.BUOY_BATTERY_S)
                or buoy.get("mode", "PASSIVE") not in ("PASSIVE", "ACTIVE")
                or type(buoy.get("last_ping_epoch", -1)) is not int
                or not -1 <= buoy.get("last_ping_epoch", -1)
                <= int(save_sim_t // config.BUOY_PING_COOLDOWN_S)):
            return False
        buoy_ids.add(buoy["seq"])
    helo_buoys = sum(1 for buoy in buoys if buoy["owner"] == "HELO")
    if (isinstance(helo, dict)
            and helo_buoys > config.BUOY_COUNT - helo["buoys_left"]):
        return False
    if len(buoys) - helo_buoys > max_mpa_buoys:
        return False
    return buoy_ids


def check_missiles(data, pending_missiles):
    """Missiles and torpedoes in flight; False, or (asms, torpedoes,
    essms, asm_ids)."""
    asms = data.get("asms", [])
    torpedoes = data.get("torpedoes_in_flight", [])
    essms = data.get("essms", [])
    if (not isinstance(asms, list) or len(asms) > MAX_SAVED_ASMS
            or not isinstance(torpedoes, list)
            or len(torpedoes) > MAX_SAVED_PLAYER_TORPEDOES
            or not isinstance(essms, list)
            or len(essms) > MAX_SAVED_ESSMS
            or any(not isinstance(row, dict)
                   for rows in (asms, torpedoes, essms) for row in rows)):
        return False
    if len(asms) + pending_missiles > MAX_SAVED_ASMS:
        return False
    # Phase 8 torpedo physics state.
    for row in torpedoes:
        if (not bounded(row.get("energy_s"), 0.0, 1e6)
                or not bounded(row.get("motor_fraction"), 0.0, 1.0)
                or not bounded(row.get("depth_rate"), -20.0, 20.0)
                or not bounded(row.get("wire_ship_out_nm"), 0.0, 1e4)
                or not bounded(row.get("wire_stress_s"), 0.0, 1e6)
                or not isinstance(row.get("rejected_ids"), list)
                or len(row["rejected_ids"]) > 4
                or any(not identity(item) for item in row["rejected_ids"])):
            return False
    for row in data.get("enemy_torpedoes", []):
        if (not isinstance(row, dict)
                or not bounded(row.get("energy_s"), 0.0, 1e6)
                or not bounded(row.get("motor_fraction"), 0.0, 1.0)
                or not bounded(row.get("depth_rate"), -20.0, 20.0)
                or not bounded(row.get("target_depth"), 0.0, 10000.0)):
            return False
    asm_ids = set()
    for asm in asms:
        seq = asm.get("seq")
        if not identity(seq) or seq in asm_ids:
            return False
        asm_ids.add(seq)
        asm_profile = data["air_defense"]["loadout"]["asm"]
        if (set(asm) != {"x", "y", "course", "seq", "profile_key", "state",
                         "jammer", "age_s", "travel", "chaff_left", "broken",
                         "speed_kn", "boosting", "altitude_m", "datum_x",
                         "datum_y", "lock_s", "locked", "los_prev",
                         "chaff_cloud"}
                or not bounded(asm.get("speed_kn"), 0, asm_profile["speed_kn"])
                or type(asm.get("boosting")) is not bool
                or type(asm.get("locked")) is not bool
                or not bounded(asm.get("altitude_m"), 0, 20_000)
                or not bounded(asm.get("datum_x"), -1_000_000, 1_000_000)
                or not bounded(asm.get("datum_y"), -1_000_000, 1_000_000)
                or not bounded(asm.get("lock_s"), 0, 3600)
                or (asm.get("los_prev") is not None
                    and not bounded(asm.get("los_prev"), 0, 360))
                or (asm.get("chaff_cloud") is not None
                    and not identity(asm.get("chaff_cloud")))
                or asm.get("profile_key") != asm_profile["key"]
                or not bounded(asm.get("x"), -1_000_000, 1_000_000)
                or not bounded(asm.get("y"), -1_000_000, 1_000_000)
                or not bounded(asm.get("course"), 0, 360)
                or asm.get("course") == 360
                or asm.get("state", "LAUF") not in (
                    "LAUF", "CHAFF", "ABGEFANGEN", "TREFFER", "VERLOREN")
                or type(asm.get("jammer")) is not bool
                or type(asm.get("broken")) is not bool
                # Powered flight time: range at cruise plus the boost.
                or not bounded(asm.get("age_s", 0), 0,
                               missile_physics.flight_time_bound_s(
                                   asm_profile["range_nm"],
                                   asm_profile["speed_kn"]))
                or not bounded(asm.get("travel", 0), 0, asm_profile["range_nm"])
                or not bounded(asm.get("chaff_left"), -3600, 3600)):
            return False
    if "asm_seq" in data and data["asm_seq"] < max(asm_ids, default=0):
        return False
    for weapon in torpedoes + essms:
        if any(not bounded(weapon.get(axis), -1_000_000, 1_000_000)
               for axis in ("x", "y")):
            return False
        for flag in ("terminal_active", "seeker_acquired"):
            if flag in weapon and type(weapon[flag]) is not bool:
                return False
        if ("guidance_x" in weapon) != ("guidance_y" in weapon):
            return False
        gx, gy = weapon.get("guidance_x"), weapon.get("guidance_y")
        if (gx is None) != (gy is None) or (gx is not None and (
                not bounded(gx, -1_000_000, 1_000_000)
                or not bounded(gy, -1_000_000, 1_000_000))):
            return False
    return asms, torpedoes, essms, asm_ids


def check_player_torpedoes(data, torpedoes, entity_ids, runtime_catalog,
                           difficulty, helo, used_asrocs, spent_asrocs,
                           buoy_ids) -> bool:
    active_origins = {"frigate": 0, "helo": 0, "asroc": 0, "mpa": 0}
    for torpedo in torpedoes:
        if torpedo.get("guidance_x") is None:
            return False
        target_id = torpedo.get("target_id")
        if target_id is not None and (not identity(target_id)
                or target_id not in entity_ids):
            return False
        profile_key = torpedo.get("profile_key")
        profile = runtime_catalog.torpedoes.get(profile_key)
        if profile is None or profile.used_by not in ("frigate", "helo"):
            return False
        distance = torpedo.get("range_nm", Torpedo.RANGE_NM)
        if (not bounded(distance, .001, 10000)
                or not identity(torpedo.get("idx"))
                or not bounded(torpedo.get("speed_kn", Torpedo.SPEED_KN), 0, 10000)
                or not bounded(torpedo.get("depth", 5), 0, 10000)
                or not bounded(torpedo.get("target_depth", 5), 0, 10000)
                or not bounded(torpedo.get("travel", 0), 0, distance)
                or not bounded(torpedo.get("midcourse_timer", 0), 0, Torpedo.WIRE_BREAK_S)
                or not {"search_phase", "midcourse", "pattern", "enable_nm",
                        "turns_done"} <= set(torpedo)
                or torpedo["pattern"] not in torpedo_dyn.SEARCH_PATTERNS
                or not bounded(torpedo["enable_nm"], torpedo_dyn.ENABLE_RANGE_MIN_NM,
                               torpedo_dyn.ENABLE_RANGE_MAX_NM)
                or not bounded(torpedo["turns_done"], 0, 1e6)
                or not bounded(torpedo.get("search_phase", 0), 0, 1e12)
                or not bounded(torpedo.get("midcourse", torpedo.get("course")),
                               0, 360)
                or torpedo.get("midcourse", torpedo.get("course")) == 360
                or torpedo.get("state", "RUN") not in ("RUN", "HIT", "SASE")):
            return False
        if torpedo.get("seeker_acquired", False) and target_id is None:
            return False
        origin = torpedo.get("launch_origin")
        launch_platform_id = torpedo.get("launch_platform_id")
        launch_weapon_key = torpedo.get("launch_weapon_key")
        if (origin not in active_origins
                or not {"launch_platform_id", "launch_weapon_key"}
                <= set(torpedo)
                or (origin == "asroc" and launch_weapon_key == depth_charge.OWN_ASROC_KEY
                    and launch_platform_id is not None)
                or (origin == "asroc" and launch_weapon_key != depth_charge.OWN_ASROC_KEY and (
                    not identity(launch_platform_id)
                    or not isinstance(launch_weapon_key, str)
                    or runtime_catalog.weapons.get(launch_weapon_key) is None
                    or runtime_catalog.weapons[
                        launch_weapon_key].weapon_type != "asroc"))
                or (origin != "asroc" and (
                    launch_platform_id is not None
                    or launch_weapon_key is not None))):
            return False
        loadout_weapons = data["asw"]["loadout"]["weapons"]
        own_weapon = next((item for item in loadout_weapons
                           if item["runtime_profile_key"] == profile_key), None)
        if origin in ("frigate", "helo", "mpa") and (
                origin != "frigate" or own_weapon is not None):
            # Fregatte und Helo teilen sich denselben Custom-Difficulty-
            # Treffwert (keine getrennten Level-Tabellen mehr).
            expected_hit_distance = difficulty["kill_dist_nm"]
            expected_hit_depth = difficulty["kill_depth_m"]
        else:
            expected_hit_distance = profile.hit_dist_nm
            expected_hit_depth = Torpedo.KILL_DEPTH_M
        if ((origin == "frigate" and profile.used_by != "frigate")
                or (profile.used_by == "frigate" and own_weapon is None)
                or torpedo.get("speed_kn") != profile.speed_kn
                or distance != profile.range_nm
                or torpedo.get("kill_dist_nm") != expected_hit_distance
                or torpedo.get("kill_depth_m") != expected_hit_depth
                or (origin in ("helo", "asroc", "mpa")
                    and profile.used_by != "helo")
                or (torpedo.get("seeker_acquired", False)
                    and not torpedo.get("terminal_active", False))):
            return False
        active_origins[origin] += 1
        if origin == "asroc":
            key = (launch_platform_id, launch_weapon_key)
            used_asrocs[key] = used_asrocs.get(key, 0) + 1
    player_battery = WeaponBattery.restore(data["asw"]["player_battery"])
    if active_origins["frigate"] > (
            player_battery.capacity_total - player_battery.remaining_total):
        return False
    if (not isinstance(helo, dict)
            or active_origins["helo"] > config.HELO_TORPS - helo["torps"]):
        return False
    if active_origins["mpa"] > config.MPA_TORPS * config.MPA_SORTIES:
        return False
    if any(count > spent_asrocs.get(key, 0)
           for key, count in used_asrocs.items()):
        return False
    torpedo_seq = data.get("torpedo_seq", 0)
    buoy_seq = data.get("buoy_seq", 0)
    if (type(torpedo_seq) is not int or not 0 <= torpedo_seq <= 2**63 - 1
            or type(buoy_seq) is not int or not 0 <= buoy_seq <= 2**63 - 1
            or torpedo_seq < max(
                (row["idx"] for row in torpedoes), default=0)
            or buoy_seq < max(buoy_ids, default=0)):
        return False
    return True


def check_essms(data, essms, asm_ids) -> bool:
    essm_ids = set()
    for essm in essms:
        target_id = essm.get("target_id")
        track_id = essm.get("track_target_id")
        sam_profile = data["air_defense"]["loadout"]["sam"]
        if (set(essm) != {"x", "y", "course", "seq", "profile_key", "state",
                          "travel", "guidance_x", "guidance_y",
                          "track_target_id", "seeker_acquired", "target_id",
                          "los_prev"}
                or (essm.get("los_prev") is not None
                    and not bounded(essm.get("los_prev"), 0, 360))
                or essm.get("profile_key") != sam_profile["key"]
                or (target_id is not None and (not identity(target_id)
                                        or target_id not in asm_ids))
                or not identity(essm.get("seq"))
                or essm.get("seq") in essm_ids
                or (track_id is not None and not identity(track_id))
                or not bounded(essm.get("course"), 0, 360)
                or essm.get("course") == 360
                or not bounded(essm.get("travel", 0), 0, sam_profile["range_nm"])
                or essm.get("state", "LAUF") not in ("LAUF", "HIT", "SASE")
                or (essm.get("seeker_acquired", False)
                    and target_id is None)
                or essm.get("guidance_x") is None):
            return False
        essm_ids.add(essm["seq"])
        if "asm_seq" in data and track_id is not None and track_id > data["asm_seq"]:
            return False
    if (data["air_defense"]["essm_seq"] < max(
            (row["seq"] for row in essms), default=0)
            or len(essms) > data["air_defense"]["loadout"]["vls"]["fire_channels"]
            or len(essms) > data["air_defense"]["loadout"]["vls"][
                "sam_loadout"] - data["vls_cells"]):
        return False
    return True
