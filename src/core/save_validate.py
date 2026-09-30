"""Strict validation of a save v16 document and its catalog binding.

Pure functions (no game state): ``valid_save_document`` is the single
acceptance check a load must pass before a candidate restore begins;
``catalog_for_save`` resolves the runtime catalog a document was written
with.  Verbatim moves from ``game_save.py`` (plan 1.3, phase 2, step 1).
"""

import json
import math


from src.core import config
from src.weapons import depth_charge
from src.core.plot import PlotLayer
from src.ship.route import Route
from src.core.autocrew import AutocrewController
from src.core.boat_esm import BoatESM
from src.core.boat_radio import BoatRadio
from src.core import opfor
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.sensors.ais import AISReceiver
from src.sensors import lookout_id
from src.sonar import equation as sonar_equation
from src.physics import ship_dynamics
from src.physics import torpedo_dyn
from src.physics import missile as missile_physics
from src.ship import damage as damage_physics
from src.world.ocean import OceanEnvironment
from src.core.save_schema import (
    WEAPON_SETTINGS_FIELDS,
    COMPARTMENT_FIELDS, COMPARTMENT_STATES, CREW_BATTERY_STATES, CREW_FEED_FIELDS,
    CREW_FIELDS, CREW_ORDERS_FIELDS, CREW_SIGHTING_FIELDS, CREW_STATION_FIELDS,
    CREW_TDC_FIELDS,
    CREW_WIRE_FIELDS,
    CREW_WIRE_STATES, DAMAGE_FIELDS, PING_INTERCEPTS_MAX, RADAR_BLIP_FIELDS,
    RADAR_MARKED_MAX, RADAR_MARKS_FIELDS, RNG_STREAMS, SAVE_ROOT_FIELDS, SHIP_FIELDS,
    SUB_CREW_FIELDS, WORLD_FIELDS)
from src.data.catalog import CATALOG, catalog_from_runtime_snapshot
from src.enemies.ballast import BoatBallast
from src.enemies.damage_control import BoatDamageControl
from src.core.tasking import TaskBoard
from src.core import baffles
from src.core.incidents import IncidentBoard
from src.core.hq_reports import HqReports
from src.weapons import rbu
from src.core.crew import CrewState
from src.air.mpa import PatrolAircraft
from src.air.sonobuoy import OWNERS as BUOY_OWNERS
from src.enemies.endurance import SubmarineEndurance
from src.sensors.esm import valid_esm_state
from src.sensors.platform import validate_suite_state
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import FIX_SOURCES, SONAR_ARRAY_MODES, SonarSystem, TowState
from src.ui.stations_view import opz_ppi_rect
from src.air import chaff as chaff_physics
from src.air.flights import FlightManager
from src.world.world import World
from src.world.coastline import Coastline
from src.world.grounding import (DEFAULT_HULL_SPEC, GroundingContact, HullSpec,
                                 grounding_contact_is_consistent)
from src.weapons.torpedo import Torpedo
from src.weapons.asw import (
    ConsumableStore,
    MAX_ASROCS,
    WeaponBattery,
    battery_matches_catalog,
    consumable_matches_catalog,
    valid_asw_state)
from src.weapons.air_defense import valid_air_defense_state

from src.core.limits import (MAX_AIR_PICTURE_TRACKS, MAX_DECOYS, MAX_ENEMY_TORPEDOES,
                             MAX_SAVED_ASMS, MAX_SAVED_ENTITIES, MAX_SAVED_ESSMS,
                             MAX_SAVED_PLAYER_TORPEDOES)



def _valid_difficulty_dict(value) -> bool:
    """Bounded, exact-shape check for a custom-difficulty payload.

    Shared shape check used by ``Game.start_new_game`` and (independently,
    for defense-in-depth) the Remote Crew ``_new_game_params`` validator and
    the save-document validator.
    """
    if not isinstance(value, dict) or set(value) != set(config.DIFFICULTY_FIELDS):
        return False
    for name, (kind, low, high, _step, _default) in config.DIFFICULTY_FIELDS.items():
        amount = value[name]
        if kind is int:
            if type(amount) is not int or not low <= amount <= high:
                return False
        elif (type(amount) not in (int, float) or isinstance(amount, bool)
                or not math.isfinite(amount) or not low <= amount <= high):
            return False
    return True


def _valid_crew_block(data, *, valid_sonar, valid_sonar_controls, entity_ids,
                      bounded, identity, finite_number, sim_t, emitter_keys) -> bool:
    """Exact save v15 ``crew`` block: None, or the crewed boat's binding.

    Every reference (boat, torpedoes, contacts) must point at an entity of
    the same document; the boat's sonar station is validated with the same
    rules as the frigate's.
    """
    from src.sonar.platforms import (OWNSHIP_TARGET_ID, OWN_TORPEDO_TARGET_BASE,
                                     SCOPE_AIR_TARGET_ID)

    crew = data.get("crew")
    sub_rows = {row.get("id"): row for row in data.get("subs", ())
                if isinstance(row, dict)}
    manual_ids = {sub_id for sub_id, row in sub_rows.items()
                  if row.get("manual") is True}
    if crew is None:
        return not manual_ids
    if not isinstance(crew, dict) or set(crew) != CREW_FIELDS:
        return False
    sub_id = crew["sub_id"]
    if (not identity(sub_id) or sub_id not in sub_rows
            or manual_ids != {sub_id}):
        return False
    if (not CrewState.valid_state(crew["watch"])
            or crew["watch"]["watch_t"] > data.get("sim_t", 0.0)):
        return False
    if not BoatRadio.valid_state(crew["radio"]):
        return False
    torpedo_ids = {row.get("id") for row in data.get("enemy_torpedoes", ())
                   if isinstance(row, dict)}

    def bearing_or_none(value) -> bool:
        return value is None or (bounded(value, 0.0, 360.0) and value < 360.0)

    orders = crew["orders"]
    if not isinstance(orders, dict) or set(orders) != CREW_ORDERS_FIELDS:
        return False
    if (any(type(orders[key]) is not bool for key in (
                "silent", "bottomed", "mast", "keel_warned", "obstacle_warned"))
            or type(orders["alarm_seq"]) is not int
            or not 0 <= orders["alarm_seq"] <= 10**9
            or not bearing_or_none(orders["ping_bearing"])
            or not bearing_or_none(orders["torpedo_bearing"])
            or not bearing_or_none(orders["last_course"])
            or not bearing_or_none(orders["pending_bearing"])
            or not (orders["torpedo_depth"] is None
                    or bounded(orders["torpedo_depth"], 0.0, 1000.0))
            or orders["salvo"] not in (1, 2) or type(orders["salvo"]) is not int
            or orders["battery_state"] not in CREW_BATTERY_STATES
            or not baffles.valid_state(orders["baffle_clear"])
            or not (orders["obstacle_ahead_nm"] is None
                    or bounded(orders["obstacle_ahead_nm"], 0.0, 10_000.0))):
        return False
    esm = orders["esm"]
    if (not isinstance(esm, list) or len(esm) > 16
            or any(not isinstance(row, list) or len(row) != 3
                   or not bounded(row[0], 0.0, 360.0) or row[0] >= 360.0
                   or not bounded(row[1], 0.0, 1e6) or not bounded(row[2], 0.0, 1e12)
                   for row in esm)):
        return False
    own_torpedo_ids = {OWN_TORPEDO_TARGET_BASE + row.get("idx")
                       for row in data.get("torpedoes_in_flight", ())
                       if isinstance(row, dict) and type(row.get("idx")) is int}
    if not (bounded(orders["scope_rel_deg"], 0.0, 360.0) and orders["scope_rel_deg"] < 360.0):
        return False
    sightings = orders["sightings"]
    if not isinstance(sightings, list) or len(sightings) > config.UBOOT_SIGHTINGS_MAX:
        return False
    sighting_ids = set(entity_ids) | {OWNSHIP_TARGET_ID, SCOPE_AIR_TARGET_ID} | own_torpedo_ids
    refs = set()
    for row in sightings:
        if (not isinstance(row, dict) or set(row) != CREW_SIGHTING_FIELDS
                or not isinstance(row["ref"], str) or not 1 <= len(row["ref"]) <= 16
                or row["ref"] in refs
                or type(row["target_id"]) is not int or row["target_id"] not in sighting_ids
                or row["cls"] not in opfor.SIGHTING_CLASSES
                or row["kind"] != opfor.SIGHTING_KINDS[row["cls"]]
                or not bounded(row["bearing"], 0.0, 360.0) or row["bearing"] >= 360.0
                or not bounded(row["span_deg"], 1e-3, 180.0)
                or not bounded(row["aspect"], 0.0, 1.0)
                or not bounded(row["quality"], 0.0, 1.0)
                or not bounded(row["first_t"], 0.0, sim_t)
                or not bounded(row["t"], row["first_t"], sim_t)
                or (row["range_nm"] is None) != (row["range_sigma_nm"] is None)
                or (row["range_nm"] is None) != (row["range_t"] is None)
                or (row["range_nm"] is not None and (
                    not bounded(row["range_nm"], 0.05, 40.0)
                    or not bounded(row["range_sigma_nm"], 0.0, 100.0)
                    or not bounded(row["range_t"], row["first_t"], sim_t)))):
            return False
        refs.add(row["ref"])
    tdc = orders["tdc"]
    if not isinstance(tdc, dict) or len(tdc) > config.UBOOT_TDC_TARGETS_MAX:
        return False
    for ref, entry in tdc.items():
        if (not isinstance(ref, str) or not 1 <= len(ref) <= 16
                or not isinstance(entry, dict) or set(entry) != CREW_TDC_FIELDS
                or type(entry["target_id"]) is not int
                or entry["target_id"] not in sighting_ids
                or not isinstance(entry["marks"], list)
                or not 1 <= len(entry["marks"]) <= config.UBOOT_TDC_MARKS_MAX):
            return False
        last_t = -1.0
        for mark in entry["marks"]:
            if (not isinstance(mark, list) or len(mark) != 3
                    or not bounded(mark[0], 0.0, sim_t) or mark[0] <= last_t
                    or not bounded(mark[1], -1e5, 1e5) or not bounded(mark[2], -1e5, 1e5)):
                return False
            last_t = mark[0]
    # Save v26: the flood state of each tube of the crewed boat's battery.
    battery = sub_rows[sub_id].get("asw_battery")
    battery_tubes = battery.get("tubes") if isinstance(battery, dict) else None
    tubes = orders["tubes"]
    if (not isinstance(tubes, list)
            or len(tubes) != (len(battery_tubes) if isinstance(battery_tubes, list) else 0)):
        return False
    for index, row in enumerate(tubes):
        if (not isinstance(row, list) or len(row) != 2
                or row[0] not in config.UBOOT_TUBE_STATES
                or not bounded(row[1], 0.0, config.UBOOT_TUBE_FLOOD_S)
                or (row[0] == "flooding") != (row[1] > 0.0)
                or (row[0] != "dry" and (not isinstance(battery_tubes[index], dict)
                                         or battery_tubes[index].get("loaded_weapon_key")
                                         is None))):
            return False
    seen = orders["sightings_seen"]
    if (not isinstance(seen, list) or len(seen) > 64
            or any(not isinstance(item, str) or not 1 <= len(item) <= 16 for item in seen)
            or seen != sorted(set(seen))):
        return False
    wires = orders["wires"]
    if not isinstance(wires, dict) or len(wires) > 64:
        return False
    wire_ids = set()
    for key, wire in wires.items():
        if (not isinstance(key, str) or not key.isdigit() or str(int(key)) != key
                or int(key) not in torpedo_ids
                or not isinstance(wire, dict) or set(wire) != CREW_WIRE_FIELDS
                or wire["state"] not in CREW_WIRE_STATES
                or not bounded(wire["ship_out_nm"], 0.0, 1000.0)
                or not bounded(wire["stress_s"], 0.0, 1e6)):
            return False
        wire_ids.add(int(key))
    known = orders["known_torpedoes"]
    if (not isinstance(known, list) or len(known) > 64
            or any(not identity(item) or item not in torpedo_ids for item in known)
            or known != sorted(set(known))):
        return False
    steer = orders["steer_torpedo"]
    if steer is not None and (not identity(steer) or steer not in torpedo_ids):
        return False
    events = orders["events"]
    if (not isinstance(events, list) or len(events) > 64
            or any(not isinstance(event, list) or len(event) != 2
                   or event[0] not in opfor.CrewOrders.EVENTS
                   or not isinstance(event[1], dict) or len(event[1]) > 8
                   or any(not isinstance(name, str) or len(name) > 32
                          or not isinstance(value, str) or len(value) > 64
                          for name, value in event[1].items())
                   for event in events)):
        return False
    if (type(crew["command_page"]) is not int or not 0 <= crew["command_page"] < 8
            or type(crew["chart_follow"]) is not bool
            or not PlotLayer.valid_save(crew["plot"])
            or not BoatESM.valid_save(crew["esm"], sim_t, emitter_keys)
            or not bounded(crew["hold_s"], 0.0, config.UBOOT_RESTORE_HOLD_S)
            or type(crew["feed_seq"]) is not int
            or not 0 <= crew["feed_seq"] <= 10**9):
        return False
    feed = crew["feed"]
    if not isinstance(feed, list) or len(feed) > opfor.OPFOR_FEED_MAX:
        return False
    last_seq = 0
    for row in feed:
        if (not isinstance(row, dict) or set(row) != CREW_FEED_FIELDS
                or type(row["seq"]) is not int or not last_seq < row["seq"] <= crew["feed_seq"]
                or not bounded(row["t"], 0.0, sim_t)
                or not isinstance(row["stamp"], str) or len(row["stamp"]) > 32
                or not isinstance(row["category"], str) or len(row["category"]) > 32
                or not isinstance(row["text"], (str, dict))):
            return False
        try:
            if len(json.dumps(row["text"], allow_nan=False)) > 2000:
                return False
        except (TypeError, ValueError):
            return False
        last_seq = row["seq"]
    station = crew["station"]
    if (not isinstance(station, dict) or set(station) != CREW_STATION_FIELDS
            or station["mode"] not in SONAR_ARRAY_MODES
            or not valid_sonar_controls(station["controls"])):
        return False
    allowed_ids = set(entity_ids) | {OWNSHIP_TARGET_ID} | own_torpedo_ids
    if not valid_sonar(station["sonar"], allowed_ids):
        return False
    for key in ("selected_contact_id", "target_id"):
        value = station[key]
        if value is not None and (type(value) is not int or value < 0):
            return False
    raw_rng = station["rng"]
    try:
        if (not isinstance(raw_rng, list) or len(raw_rng) != 3
                or not isinstance(raw_rng[1], list)):
            return False
        import random
        random.Random().setstate((raw_rng[0], tuple(raw_rng[1]), raw_rng[2]))
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _same_save_value(left, right) -> bool:
    """Compare canonical JSON values while treating tuples as JSON arrays."""
    if isinstance(left, dict) and isinstance(right, dict):
        return (set(left) == set(right)
                and all(_same_save_value(left[key], right[key]) for key in left))
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return (len(left) == len(right)
                and all(_same_save_value(a, b) for a, b in zip(left, right)))
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _same_save_value_strict(left, right) -> bool:
    """Recursively compare an exact JSON tree, including numeric types."""
    if isinstance(left, dict) and isinstance(right, dict):
        return (set(left) == set(right)
                and all(_same_save_value_strict(left[key], right[key])
                        for key in left))
    if isinstance(left, list) and isinstance(right, list):
        return (len(left) == len(right)
                and all(_same_save_value_strict(a, b)
                        for a, b in zip(left, right)))
    return type(left) is type(right) and left == right


def catalog_for_save(data):
    if (not isinstance(data, dict) or data.get("version") != SAVE_VERSION
            or data.get("save_schema") != SAVE_SCHEMA):
        raise ValueError("unsupported save version")
    return catalog_from_runtime_snapshot(data["catalog_snapshot"])

def valid_save_document(data, runtime_catalog=None) -> bool:
    def finite_number(value) -> bool:
        try:
            return (isinstance(value, (int, float))
                    and not isinstance(value, bool) and math.isfinite(value))
        except OverflowError:
            return False

    def finite_tree(value, path=()) -> bool:
        if len(path) > 100:
            return False
        if value is None or isinstance(value, (str, bool)):
            return True
        if isinstance(value, (int, float)):
            return finite_number(value)
        if isinstance(value, dict):
            return all(isinstance(key, str) and finite_tree(item, path + (key,))
                       for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return all(finite_tree(item, path + (index,))
                       for index, item in enumerate(value))
        return False

    def bounded(value, low=0.0, high=1_000_000.0) -> bool:
        return finite_number(value) and low <= value <= high

    def identity(value) -> bool:
        return type(value) is int and 1 <= value <= 2**63 - 1

    if not isinstance(data, dict):
        return False
    version = data.get("version")
    if (type(version) is not int or version != SAVE_VERSION
            or data.get("save_schema") != SAVE_SCHEMA):
        return False
    if set(data) != SAVE_ROOT_FIELDS:
        return False
    if not PlotLayer.valid_save(data.get("plot")):
        return False
    if not Route.valid_state(data.get("route"), config.WORLD_SIZE_NM):
        return False
    if not AISReceiver.valid_state(
            data.get("ais"), data.get("sim_t"),
            {row.get("id") for row in data.get("civilians", ())
             if isinstance(row, dict)}):
        return False
    if not AutocrewController.valid_state(data.get("autocrew"), data.get("sim_t")):
        return False
    def valid_sonar_controls(controls) -> bool:
        control_fields = {"gain_db", "band_low_hz", "band_high_hz",
                          "notch_enabled", "peak_hold", "focus_locked",
                          "tma_enabled", "listen_bearing", "listen_filtered",
                          "audition_mode", "sonar_page", "audio_enabled", "volume",
                          "tma_method"}
        if (not isinstance(controls, dict) or set(controls) != control_fields
                or controls["tma_method"] not in ("hypothesis", "ekelund", "dotstack")
                or controls["audition_mode"] not in (
                    "BROADBAND", "FILTERED", "HETERODYNE")
                or controls["listen_filtered"] != (
                    controls["audition_mode"] == "FILTERED")
                or any(type(controls[key]) is not bool for key in (
                    "notch_enabled", "peak_hold", "focus_locked", "tma_enabled",
                    "listen_filtered", "audio_enabled"))
                or not bounded(controls["gain_db"], -12, 24)
                or not bounded(controls["band_low_hz"], 0, config.LOFAR_FMAX_HZ)
                or not bounded(controls["band_high_hz"], 0, config.LOFAR_FMAX_HZ)
                or controls["band_low_hz"] > controls["band_high_hz"]
                or not bounded(controls["listen_bearing"], 0, 360)
                or controls["listen_bearing"] == 360
                or type(controls["sonar_page"]) is not int
                or not 0 <= controls["sonar_page"] < 6
                or not bounded(controls["volume"], 0, 1)):
            return False
        return True

    if not valid_sonar_controls(data.get("sonar_controls")):
        return False
    platform_state_version = data.get("platform_state_version")
    if type(platform_state_version) is not int or platform_state_version != 1:
        return False
    save_sim_t = data.get("sim_t", 0.0)
    if not finite_number(save_sim_t) or not 0.0 <= save_sim_t <= 1e12:
        return False
    if not finite_tree(data):
        return False
    ui = data.get("ui")
    world_data = data.get("world")
    coast_data = (world_data.get("coast")
                  if isinstance(world_data, dict) else None)
    world_size = (coast_data.get("world_nm")
                  if isinstance(coast_data, dict) else None)
    if not bounded(world_size, 1e-6, 1_000_000.0):
        return False
    opz_chart = opz_ppi_rect(config.OPZ_STATION_RECT)
    opz_min_scale = min(opz_chart.w, opz_chart.h) / world_size
    opz_max_scale = max(opz_min_scale, min(opz_chart.w, opz_chart.h) / (
        2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM)
    )
    if (not isinstance(ui, dict)
            or ui.get("local_side") not in ("frigate", "uboot")
            or type(ui.get("opz_map_follow")) is not bool
            or not bounded(ui.get("opz_map_cx"), -1_000_000, 1_000_000)
            or not bounded(ui.get("opz_map_cy"), -1_000_000, 1_000_000)
            or not bounded(ui.get("opz_map_scale"), opz_min_scale,
                           opz_max_scale)):
        return False
    try:
        if runtime_catalog is None:
            runtime_catalog = catalog_for_save(data)
        elif not _same_save_value(
                runtime_catalog.runtime_snapshot(), data["catalog_snapshot"]):
            normalized = catalog_from_runtime_snapshot(
                data["catalog_snapshot"]).runtime_snapshot()
            if not _same_save_value(runtime_catalog.runtime_snapshot(), normalized):
                return False
    except Exception:
        return False
    if ("esm" not in data
            or not valid_esm_state(data["esm"], save_sim_t,
                                   runtime_catalog.emitters)):
        return False
    torpedo_inventory = data.get("torpedoes")
    if (not isinstance(torpedo_inventory, dict)
            or set(torpedo_inventory) != {"total", "count", "depth"}
            or type(torpedo_inventory["total"]) is not int
            or type(torpedo_inventory["count"]) is not int
            or not 0 <= torpedo_inventory["count"] <= torpedo_inventory["total"] <= 100
            or not bounded(torpedo_inventory["depth"], 0, 10000)):
        return False
    # The mission's realism level; the difficulty values it already scaled
    # live in mission_runtime["difficulty"] (checked just below).
    if data.get("level") not in config.LEVELS:
        return False
    runtime_mission = data.get("mission_runtime")
    if not isinstance(runtime_mission, dict):
        return False
    difficulty = runtime_mission.get("difficulty")
    if (not isinstance(difficulty, dict)
            or set(difficulty) != set(config.DIFFICULTY_FIELDS)):
        return False
    pending_events = data.get("mission_events")
    definition = runtime_mission.get("custom_definition")
    known_events = {event.get("id") for event in definition.get("events", ())
                    if isinstance(event, dict)} if isinstance(definition, dict) else set()
    if (not isinstance(pending_events, list) or len(pending_events) > 64
            or any(not isinstance(item, str) or item not in known_events
                   for item in pending_events)
            or len(set(pending_events)) != len(pending_events)):
        return False
    # Save v21: the frigate crew's watch bill, fatigue and morale.
    watch = data.get("watch")
    if not CrewState.valid_state(watch) or watch["watch_t"] > save_sim_t:
        return False
    # Save v21: the radio tasking board; a task's ship must be in this save.
    board = data.get("tasking")
    if not TaskBoard.valid_state(board):
        return False
    surface_ids = {row.get("id") for row in data.get("civilians", ())
                   if isinstance(row, dict)}
    if any(task["kind"] in ("identify", "ras") and task["state"] in ("offered", "active")
           and task["target_id"] not in surface_ids for task in board["tasks"]):
        return False
    if any(task["offered_t"] > save_sim_t for task in board["tasks"]):
        return False
    # Save v38: wounded crew of the frigate and each submarine.
    from src.core.game_casualties import CasualtiesMixin
    if not CasualtiesMixin.casualties_valid(
            data.get("casualties"), {row.get("id") for row in data.get("subs", ())
                                     if isinstance(row, dict)}):
        return False
    # Save v41: the bubble slicks of hard turns (knuckles); none laid after
    # the save time (a boat that laid one may be gone since).
    from src.world.knuckles import KnuckleField
    knuckles = data.get("knuckles")
    if (not KnuckleField.valid(knuckles)
            or any(row["t"] > save_sim_t for row in knuckles)):
        return False
    # Save v39: the AI hunters' ESM bearing lines.
    from src.core import hunter
    if not hunter.valid_esm_log(data.get("hunter_esm"), save_sim_t):
        return False
    # Save v37: the ASW rocket launcher.
    if not rbu.valid_state(data.get("rbu"), 1_000_000.0):
        return False
    # Save v36: the radio room's own calls; none logged after the save time.
    reports = data.get("hq_reports")
    if (not HqReports.valid_state(reports)
            or any(row["t"] > save_sim_t for row in reports["log"])):
        return False
    # Save v35: the Bridge's baffle clearing, ending after the save time.
    if (not baffles.valid_state(data.get("baffle_clear"))
            or data["baffle_clear"] is not None
            and data["baffle_clear"][2] > save_sim_t + config.BAFFLE_CLEAR_HOLD_S):
        return False
    # Save v34: incidents at sea; none announced after the save time.
    incidents = data.get("incidents")
    if (not IncidentBoard.valid_state(incidents)
            or any(item["announced_t"] > save_sim_t for item in incidents["items"])):
        return False
    intercepts = data.get("ping_intercepts")
    if (not isinstance(intercepts, list) or len(intercepts) > PING_INTERCEPTS_MAX
            or any(not isinstance(row, list) or len(row) != 3
                   or any(type(value) is not float or not math.isfinite(value)
                          or abs(value) > 1e9 for value in row)
                   or row[0] < 0.0 for row in intercepts)
            or intercepts != sorted(intercepts)):
        return False
    if not _radar_marks_ok(data.get("radar_marks"), save_sim_t):
        return False
    units = runtime_mission.get("units")
    if (not isinstance(units, dict) or len(units) > 512
            or any(not isinstance(key, str) or not 1 <= len(key) <= 64
                   or not identity(value) for key, value in units.items())):
        return False
    for name, (kind, low, high, _step, _default) in config.DIFFICULTY_FIELDS.items():
        amount = difficulty[name]
        if kind is int:
            if type(amount) is not int or not low <= amount <= high:
                return False
        elif not bounded(amount, low, high):
            return False
    if torpedo_inventory["total"] != difficulty["torpedo_count"]:
        return False
    if ("asw" not in data or not valid_asw_state(
                data["asw"], torpedo_inventory["total"],
                torpedo_inventory["count"], runtime_catalog)):
        return False
    if ("air_defense" not in data or not valid_air_defense_state(
            data["air_defense"], vls_cells=data.get("vls_cells"),
            ciws_ammo=data.get("ciws_ammo"),
            ciws_cooldown_s=data.get("ciws_cooldown_s"),
            chaff_cd=data.get("chaff_cd"))):
        return False
    rng_data = data.get("rngs")
    if not isinstance(rng_data, dict) or set(rng_data) != RNG_STREAMS:
        return False
    for raw_rng in rng_data.values():
        try:
            if (not isinstance(raw_rng, list) or len(raw_rng) != 3
                    or not isinstance(raw_rng[1], list)):
                return False
            import random
            random.Random().setstate(
                (raw_rng[0], tuple(raw_rng[1]), raw_rng[2]))
        except (TypeError, ValueError, OverflowError):
            return False

    def platform_speed_limit(profile_key, profile) -> float:
        systems = runtime_catalog.profile_systems.get(profile_key)
        if systems is not None and systems.machine_key is not None:
            return runtime_catalog.machines[systems.machine_key].maximum_speed_kn
        speed = profile.speed_kn
        return speed[1] if isinstance(speed, tuple) else speed
    air_rows = data.get("air_picture", [])
    required_track_fields = {
        "track_id", "kind", "target_id", "source", "bearing",
        "range_nm", "x", "y", "course", "quality", "last_seen", "label",
    }
    if (not isinstance(air_rows, list)
            or len(air_rows) > MAX_AIR_PICTURE_TRACKS):
        return False
    approved_esm_names = {
        runtime_catalog.emitter_name(key)
        for key, emitter in runtime_catalog.emitters.items()
        if emitter.domain == "radar"
    }
    for row in air_rows:
        if (not isinstance(row, dict)
                or not required_track_fields <= set(row)
                or any(not isinstance(row[key], str) or len(row[key]) > 128
                       for key in ("track_id", "kind", "source", "label"))
                or type(row["target_id"]) is not int or row["target_id"] < 0
                or not bounded(row["bearing"], 0, 360)
                or row["bearing"] == 360
                or not bounded(row["quality"], 0, 1)
                or not bounded(row["last_seen"], 0, save_sim_t)):
            return False
        if row["source"] == "ESM" and (
                not row["track_id"].startswith("E-")
                or len(row["track_id"]) != 18
                or any(char not in "0123456789ABCDEF"
                       for char in row["track_id"][2:])
                or row["kind"] != "UNKNOWN" or row["target_id"] != 0
                or row["range_nm"] is not None or row["x"] is not None
                or row["y"] is not None or row["course"] is not None
                or row.get("raw_range_nm") is not None
                or row.get("raw_x") is not None or row.get("raw_y") is not None
                or row.get("raw_course") is not None
                or row.get("position_seen") is not None
                or row["label"] not in approved_esm_names
                or row.get("hostile") is not False
                or row.get("jamming") is not False):
            return False
        if row["source"] == "LOOKOUT" and (
                not row["track_id"].startswith("L-")
                or len(row["track_id"]) != 18
                or any(char not in "0123456789ABCDEF"
                       for char in row["track_id"][2:])
                or row["kind"] not in ("SURFACE", "SUB", "FLG", "TORP",
                                       "UNKNOWN")
                or row["target_id"] != 0 or row["range_nm"] is None
                or row["range_nm"] > config.LOOKOUT_AIR_RANGE_NM * (
                    1.0 + config.LOOKOUT_RANGE_ERR_FRAC)
                or row["x"] is None or row["y"] is None
                or row["course"] is not None
                or row.get("raw_course") is not None
                or not lookout_id.valid_label(
                    row["label"], lookout_id.type_keys(runtime_catalog))
                or row.get("hostile") is not False
                or row.get("jamming") is not False):
            return False
        if ((row["x"] is None) != (row["y"] is None)
                or any(value is not None and not bounded(
                    value, -1_000_000, 1_000_000)
                       for value in (row["x"], row["y"]))
                or (row["range_nm"] is not None
                    and not bounded(row["range_nm"], 0, 1_000_000))
                or (row["course"] is not None
                    and (not bounded(row["course"], 0, 360)
                         or row["course"] == 360))):
            return False
        position_seen = row.get("position_seen")
        uncertainty = row.get("bearing_uncertainty_deg")
        if ((position_seen is not None
             and not bounded(position_seen, 0, save_sim_t))
                or (uncertainty is not None
                    and not bounded(uncertainty, .05, 180))):
            return False
    fixes = data.get("hfdf_fixes", {})
    reports = data.get("hfdf_log", [])
    if not isinstance(fixes, dict) or len(fixes) > 10000:
        return False
    if not isinstance(reports, list) or len(reports) > 20:
        return False
    for report in reports:
        if (not isinstance(report, dict)
                or not isinstance(report.get("track_id"), str)
                or not isinstance(report.get("label"), str)
                or not bounded(report.get("t"))
                or not bounded(report.get("bearing"), 0, 360)
                or not all(bounded(report.get(key), -1_000_000, 1_000_000)
                           for key in ("observer_x", "observer_y"))):
            return False
    for fix in fixes.values():
        if (not isinstance(fix, dict) or not isinstance(fix.get("label"), str)
                or not bounded(fix.get("t")) or not bounded(fix.get("sigma_nm"))
                or not all(bounded(fix.get(key), -1_000_000, 1_000_000)
                           for key in ("x", "y"))):
            return False
        covariance = fix.get("covariance_nm2")
        if covariance is not None:
            if (not isinstance(covariance, (list, tuple)) or len(covariance) != 3
                    or not all(bounded(value, -1e12, 1e12) for value in covariance)):
                return False
            xx, xy, yy = covariance
            if xx < 0 or yy < 0 or xy * xy > xx * yy + 1e-9 * max(1., xx * yy):
                return False
    affiliations = data.get("opz_affiliations")
    if (not isinstance(affiliations, dict)
            or len(affiliations) > MAX_AIR_PICTURE_TRACKS
            or any(not isinstance(track_id, str)
                   or not 1 <= len(track_id) <= 128
                   or value not in config.NATO_AFFILIATIONS
                   for track_id, value in affiliations.items())):
        return False
    ship = data.get("ship")
    if not isinstance(ship, dict) or set(ship) != SHIP_FIELDS:
        return False
    wake = ship["wake"]
    if (any(not bounded(ship[key], -100.0, 100.0)
            for key in ("roll_rate", "pitch_rate"))
            or not bounded(ship["clock"], 0.0, 1e12)
            or not bounded(ship["deck_quiet_s"], 0.0, 3600.0)
            or not isinstance(wake, list)
            or len(wake) > ship_dynamics.HULL.wake_max_points
            or any(not isinstance(point, list) or len(point) != 4
                   or not all(bounded(value, -1_000_000, 1_000_000)
                              for value in point)
                   or not 0.0 <= point[2] <= ship["clock"]
                   or not 0.0 <= point[3] <= config.SHIP_SPEED_MAX_KN
                   for point in wake)):
        return False
    radars = data.get("radars")
    if (not isinstance(radars, dict)
            or set(radars) != {"surface", "air", "range_nm", "scan_phase",
                               "scan_pending_deg"}
            or type(radars["surface"]) is not bool
            or type(radars["air"]) is not bool
            or radars["range_nm"] not in config.RADAR_RANGE_SCALES_NM
            or type(radars["scan_phase"]) is not float
            or not 0.0 <= radars["scan_phase"] < 360.0
            or type(radars["scan_pending_deg"]) is not float
            or not 0.0 <= radars["scan_pending_deg"] <= 360.0):
        return False
    order = ship.get("order_idx", config.TELEGRAPH_DEFAULT)
    hull = ship.get("hull")
    grounding = ship.get("grounding")
    hull_fields = {"mass_t", "length_m", "beam_m", "draft_m", "keel_reserve_m"}
    contact_fields = {"kind", "x_nm", "y_nm", "normal_x", "normal_y",
                      "hull_longitudinal", "hull_lateral"}
    pose = grounding.get("last_safe_pose") if isinstance(grounding, dict) else None
    contact = grounding.get("contact") if isinstance(grounding, dict) else None
    if (type(order) is not int or not 0 <= order < len(config.TELEGRAPH_ORDERS)
            or type(ship.get("astern")) is not bool
            or (ship["astern"] and order != 0)
            or (ship["astern"] and ship.get("target_speed") != config.ASTERN_SPEED_KN)
            or type(ship.get("quiet_mode")) is not bool
            or ship.get("plant_mode") not in Ship.PLANT_MODES
            or ship.get("fuel_capacity_kg") != config.SHIP_FUEL_CAPACITY_KG
            or not bounded(ship.get("fuel_kg"), 0, config.SHIP_FUEL_CAPACITY_KG)
            or any(not bounded(ship.get(key), 0, config.SHIP_SPEED_MAX_KN)
                   for key in ("speed", "target_speed"))
            or not isinstance(hull, dict) or set(hull) != hull_fields
            or not _same_save_value_strict(
                hull, DEFAULT_HULL_SPEC.to_dict())
            or not isinstance(grounding, dict)
            or set(grounding) != {"latched", "last_safe_pose", "contact"}
            or type(grounding["latched"]) is not bool
            or not isinstance(pose, list) or len(pose) != 3
            or any(not bounded(value, -1_000_000, 1_000_000) for value in pose)
            or (contact is None) != (not grounding["latched"])
            or (contact is not None and (
                not isinstance(contact, dict) or set(contact) != contact_fields
                or contact.get("kind") not in ("boundary", "land", "shallow")
                or any(not bounded(contact.get(key), -1_000_000, 1_000_000)
                       for key in contact_fields - {"kind"})
                or any(type(contact[key]) is not float
                       for key in contact_fields - {"kind"})
                or not -1.0 <= contact["normal_x"] <= 1.0
                or not -1.0 <= contact["normal_y"] <= 1.0
                or not -1.0 <= contact["hull_longitudinal"] <= 1.0
                or not -1.0 <= contact["hull_lateral"] <= 1.0))
            or any(abs(ship[key] - pose[index]) > 1e-9
                   for index, key in enumerate(("x", "y", "course")))):
        return False
    team = data.get("dmg_team", 1)
    if type(team) is not int or not 1 <= team <= DamageModel.TEAM_COUNT:
        return False
    from src.ship.damage import COMPARTMENTS
    compartment_keys = {key for key, _ in COMPARTMENTS}
    damage = data.get("damage")
    if not isinstance(damage, dict) or set(damage) != DAMAGE_FIELDS:
        return False
    teams = damage["teams"]
    compartments = damage["compartments"]
    if not isinstance(teams, dict) or not isinstance(compartments, dict):
        return False
    if not bounded(damage["repair_mult"], 0.1, 10.0):
        return False
    team_keys = {str(i) for i in range(1, DamageModel.TEAM_COUNT + 1)}
    if (not isinstance(damage["team_position"], dict)
            or set(damage["team_position"]) != team_keys
            or any(room not in compartment_keys
                   for room in damage["team_position"].values())
            or not isinstance(damage["team_eta"], dict)
            or set(damage["team_eta"]) != team_keys
            or any(not bounded(value, 0.0, 3600.0)
                   for value in damage["team_eta"].values())
            or type(damage["patch_kits"]) is not int
            or not 0 <= damage["patch_kits"] <= damage_physics.PATCH_KITS
            or type(damage["cooked_off"]) is not bool
            or type(damage["capsized"]) is not bool
            or not bounded(damage["draft_m"], 1.0, 20.0)):
        return False
    if (set(teams) != {str(i) for i in range(1, DamageModel.TEAM_COUNT + 1)}
            or any(room is not None and (not isinstance(room, str)
                                         or room not in compartment_keys)
                   for room in teams.values())):
        return False
    if set(compartments) != compartment_keys or any(
            not isinstance(room, dict) or set(room) != COMPARTMENT_FIELDS
            or room["state"] not in COMPARTMENT_STATES
            or not bounded(room["flood"], 0, config.DMG_DESTROY_FLOOD)
            # A lethal fire may overshoot the kill threshold by one step.
            or not bounded(room["fire"], 0, config.DMG_FIRE_KILL + 5.0)
            or not bounded(room["hole_m2"], 0.0, 10.0)
            or not bounded(room["heat_s"], 0.0, 1e6)
            or type(room["shorted"]) is not bool
            or not bounded(room["counterflood"], 0.0, config.DMG_DESTROY_FLOOD)
            for room in compartments.values()):
        return False
    if any(compartments[key]["counterflood"] > 0.0
           for key in compartments if key not in DamageModel.COUNTERFLOOD_ROOMS):
        return False

    groups = {"sub": ("subs",), "animal": ("animals",),
              "surface": ("civilians", "warships"), "decoy": ("decoys",),
              "enemy_torpedo": ("enemy_torpedoes",)}
    max_ship_noise = Ship(0, 0, speed_kn=config.SHIP_SPEED_MAX_KN).noise_level()
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
                elif name == "enemy_torpedoes":
                    if not {
                            "profile_key", "guidance_x", "guidance_y",
                            "terminal_active", "seeker_acquired",
                            "seeker_target", "travel", "launch_platform_id",
                            "launch_weapon_key"} <= set(entry):
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
                            or not bounded(entry.get("travel", 0), 0,
                                           profile.range_nm if profile else 10000)):
                        return False
                    seeker = entry.get("seeker_target")
                    nixie_ids = {row["seq"] for row in (
                        data.get("asw", {}).get("nixies", [])
                        if isinstance(data.get("asw"), dict) else [])}
                    valid_seeker = (seeker is None or seeker == "ship"
                                    or (isinstance(seeker, str)
                                        and seeker.startswith("nixie:")
                                        and seeker[6:].isdigit()
                                        and int(seeker[6:]) in nixie_ids))
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
                if name == "subs":
                    if not {
                            "asw_battery", "countermeasure_store",
                            "endurance"} | SUB_CREW_FIELDS <= set(entry):
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
                            or not bounded(entry.get("torpedo_alarm_left"), -1.0, 15.0)):
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
                                or not bounded(observed["noise"], 0, max_ship_noise)):
                            return False
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
    for key in ("asm_seq", "asm_spawned", "warship_asm_seq"):
        value = data.get(key, 0)
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            return False
    if not bounded(data.get("ciws_cooldown_s", 0), 0, 1):
        return False
    mount = data.get("ciws_mount_deg")
    clouds = data.get("chaff_clouds")
    if (not bounded(mount, 0, 360) or mount == 360
            or type(data.get("chaff_seq")) is not int
            or not 0 <= data["chaff_seq"] <= 2**63 - 1
            or not isinstance(clouds, list)
            or len(clouds) > chaff_physics.MAX_CLOUDS
            or not all(chaff_physics.valid_row(row) for row in clouds)
            or len({row["seq"] for row in clouds}) != len(clouds)
            or any(row["seq"] > data["chaff_seq"] for row in clouds)):
        return False
    if type(data.get("air_threat_reported", False)) is not bool:
        return False
    flights = data.get("flights", {})
    if (not isinstance(flights, dict)
            or not isinstance(flights.get("items", []), list)
            or len(flights.get("items", [])) > FlightManager.MAX_FLIGHTS):
        return False
    for flight in flights.get("items", []):
        if not isinstance(flight, dict):
            return False
        bearing = flight.get("sensor_bearing")
        radar_emitting = flight.get("radar_emitting", False)
        if (type(radar_emitting) is not bool
                or not bounded(flight.get("sensor_age", config.RADAR_TRACK_STALE_S),
                               0, config.RADAR_TRACK_STALE_S)
                or (bearing is not None and (not bounded(bearing, 0, 360) or bearing == 360))):
            return False
        profile = runtime_catalog.aircraft.get(flight.get("akey"))
        if profile is None or profile.kind != flight.get("kind"):
            return False
        if radar_emitting != (profile.kind == "military"):
            return False
        platform = flight.get("platform")
        if (platform_state_version == 1 and platform is None) \
                or (platform is not None and (
                    profile is None or not validate_suite_state(
                        platform, runtime_catalog, profile.key, save_sim_t))):
            return False
    helo = data.get("helo")
    if not isinstance(helo, dict):
        return False
    if isinstance(helo, dict):
        required_helo = {
            "state", "x", "y", "course", "torps", "torpedo_profile_key",
            "buoys_left", "fuel_s", "waypoint_x", "waypoint_y",
            "dip_state", "dip_depth_m", "dip_depth_target_m",
            "dip_water_depth_m", "dip_ping_cooldown", "hover_x", "hover_y",
            "pattern", "pattern_queue", "mad_mode", "radar_on",
        }
        if set(helo) != required_helo:
            return False
        queue = helo["pattern_queue"]
        if (helo["pattern"] not in ("single", "field", "barrier", "circle")
                or type(helo["mad_mode"]) is not bool
                or type(helo["radar_on"]) is not bool
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
    buoys = data.get("buoys", [])
    max_mpa_buoys = config.MPA_BUOYS * config.MPA_SORTIES
    if (not isinstance(buoys, list)
            or len(buoys) > config.BUOY_COUNT + max_mpa_buoys):
        return False
    # Save v21: the patrol aircraft (its stores bound its buoys and torpedoes).
    mpa = data.get("mpa")
    if not PatrolAircraft.valid_state(mpa, world_size):
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
    world = data.get("world")
    if (not isinstance(world, dict) or set(world) != WORLD_FIELDS
            or world["mode"] not in ("fixed", "procedural", "real_fixed")
            or world["generator"] != (
                "natural-earth-v1" if world["mode"] in ("procedural", "real_fixed")
                else "fixed-reference-v1")
            or not bounded(world["hour"], 0.0, 24.0)
            or world["hour"] == 24.0
            or type(world["sea_state"]) is not int
            or not 0 <= world["sea_state"] <= 6
            or not bounded(world["weather_shift_timer"], 0.0,
                           config.WEATHER_SHIFT_PERIOD_S)
            or world["weather_override"] not in (None, "fair", "rain", "storm", "fog")
            or not OceanEnvironment.valid_state(world["ocean"])
            or not Coastline.valid_snapshot(world["coast"])):
        return False
    validation_coast = Coastline.from_dict(world["coast"])
    validation_world = World(seed=data["seed"], coast=validation_coast)
    validation_world.hour = world["hour"]
    validation_world.ocean.restore(world["ocean"])
    validation_hull = HullSpec(**hull)
    if grounding["latched"]:
        saved_contact = GroundingContact(**contact)
        if not grounding_contact_is_consistent(
                validation_world, tuple(pose), validation_hull, saved_contact):
            return False
    elif not validation_world.hull_is_safe(*pose, validation_hull):
        return False
    schedulers = data.get("schedulers", {})
    if not isinstance(schedulers, dict):
        return False
    for key, limit in (("sensor", .25), ("esm", .5),
                       ("radio", .5), ("slow", .5)):
        value = schedulers.get(key, 0.0)
        if not finite_number(value) or not 0.0 <= value < limit:
            return False
    def valid_sonar(sonar, allowed_ids) -> bool:
        if not isinstance(sonar, dict):
            return False
        for key in ("lofar", "lofar_times", "lofar_bearings",
                    "broadband", "history_times", "echo_history",
                    "pending_pings"):
            if key in sonar and not isinstance(sonar[key], list):
                return False
        for key in ("lofar", "broadband"):
            if any(not isinstance(row, list)
                   or any(not finite_number(value) for value in row)
                   for row in sonar.get(key, [])):
                return False
        for key in ("lofar_times", "lofar_bearings", "history_times"):
            if any(not finite_number(value) for value in sonar.get(key, [])):
                return False
        if not bounded(sonar.get("bt_cooldown"), 0,
                       config.SONAR_BT_COOLDOWN_S):
            return False
        # Variable-depth sonar (save v23): exact, typed and inside its envelope.
        if (sonar.get("vds_state") not in {state.value for state in TowState}
                or not bounded(sonar.get("vds_payout"), 0.0, 1.0)
                or not bounded(sonar.get("vds_depth_m"), config.SONAR_VDS_DEPTH_MIN_M,
                               config.SONAR_VDS_DEPTH_MAX_M)
                or not bounded(sonar.get("vds_depth_target_m"), config.SONAR_VDS_DEPTH_MIN_M,
                               config.SONAR_VDS_DEPTH_MAX_M)
                or not bounded(sonar.get("vds_settle_s"), 0.0, config.SONAR_VDS_SETTLE_S)
                or type(sonar.get("vds_handling_ok")) is not bool):
            return False
        bt_profile = sonar.get("bt_profile")
        if bt_profile is not None:
            bt_fields = {"t", "x", "y", "thermocline_m", "water_depth_m",
                         "sea_state", "depths_m", "speeds_m_s", "cz_bands_nm"}
            if not isinstance(bt_profile, dict) or set(bt_profile) != bt_fields:
                return False
            water_depth = bt_profile["water_depth_m"]
            thermocline = bt_profile["thermocline_m"]
            depths = bt_profile["depths_m"]
            speeds = bt_profile["speeds_m_s"]
            if (not bounded(bt_profile["t"], 0, save_sim_t)
                    or not bounded(bt_profile["x"], -1_000_000, 1_000_000)
                    or not bounded(bt_profile["y"], -1_000_000, 1_000_000)
                    or not bounded(water_depth, 1, 10_000)
                    or not bounded(thermocline, 0, water_depth)
                    or not isinstance(bt_profile["sea_state"], int)
                    or isinstance(bt_profile["sea_state"], bool)
                    or not 0 <= bt_profile["sea_state"] <= 6
                    or not isinstance(depths, list) or len(depths) != 21
                    or not isinstance(speeds, list) or len(speeds) != 21
                    or any(not finite_number(depth) for depth in depths)
                    or any(not finite_number(speed) for speed in speeds)
                    or not isinstance(bt_profile["cz_bands_nm"], list)
                    or len(bt_profile["cz_bands_nm"]) > 4
                    or any(not isinstance(band, list) or len(band) != 2
                           or not bounded(band[0], 0.0, 200.0)
                           or not bounded(band[1], 0.0, 200.0)
                           or not band[0] < band[1]
                           for band in bt_profile["cz_bands_nm"])):
                return False
            maximum = min(water_depth, config.SONAR_BT_MAX_DEPTH_M)
            expected_depths = [maximum * index / 20 for index in range(21)]
            if (any(abs(depth - expected) > 1e-9
                    for depth, expected in zip(depths, expected_depths))
                    or any(not 1400.0 <= speed <= 1600.0 for speed in speeds)):
                return False
        contacts = sonar.get("contacts", {})
        if not isinstance(contacts, dict):
            return False
        contact_ids = [contact.get("contact_id")
                       for contact in contacts.values()
                       if isinstance(contact, dict)]
        next_contact_id = sonar.get("next_id")
        if (not identity(next_contact_id)
                or any(not identity(contact_id) for contact_id in contact_ids)
                or next_contact_id <= max(contact_ids, default=0)):
            return False
        for contact in contacts.values():
            if not isinstance(contact, dict):
                return False
            if (type(contact.get("released_to_opz")) is not bool
                    or type(contact.get("dip_released_to_opz", False)) is not bool
                    or type(contact.get("helo_qualified", False)) is not bool
                    or type(contact.get("buoy_released_to_opz", False)) is not bool
                    or ((contact.get("ship_observer_x") is None)
                        != (contact.get("ship_observer_y") is None))
                    or (contact.get("ship_observer_x") is not None
                        and (not bounded(contact["ship_observer_x"], -1_000_000, 1_000_000)
                             or not bounded(contact["ship_observer_y"], -1_000_000, 1_000_000)))
                    or contact.get("passive_source") not in (
                        "SONAR-BRG", "SONAR-DIP-BRG")
                    or not bounded(contact.get("observer_x"), -1_000_000, 1_000_000)
                    or not bounded(contact.get("observer_y"), -1_000_000, 1_000_000)):
                return False
            buoy_reports = contact.get("buoy_reports", {})
            report_fields = {"mode", "bearing", "bearing_uncertainty_deg",
                             "quality", "measured_at", "observer_x", "observer_y",
                             "range_nm", "x", "y"}
            if (not isinstance(buoy_reports, dict)
                    or len(buoy_reports) > config.BUOY_COUNT
                    or any(type(key) is not str or not key.isdecimal()
                           or int(key) not in buoy_ids
                           or not isinstance(row, dict) or set(row) != report_fields
                           or row["mode"] not in ("PASSIVE", "ACTIVE")
                           or not bounded(row["bearing"], 0, 360)
                           or row["bearing"] == 360
                           or not bounded(row["bearing_uncertainty_deg"], 0, 180)
                           or not bounded(row["quality"], 0, 1)
                           or not bounded(row["measured_at"], 0, save_sim_t)
                           or not bounded(row["observer_x"], -1_000_000, 1_000_000)
                           or not bounded(row["observer_y"], -1_000_000, 1_000_000)
                           or (row["mode"] == "PASSIVE" and any(
                               row[field] is not None for field in ("range_nm", "x", "y")))
                           or (row["mode"] == "ACTIVE" and any(
                               not bounded(row[field], -1_000_000, 1_000_000)
                               for field in ("x", "y")))
                           or (row["mode"] == "ACTIVE" and not bounded(
                               row["range_nm"], 0, config.BUOY_RANGE_NM + .25))
                           for key, row in buoy_reports.items())):
                return False
            reports = contact.get("array_observations", {})
            if not isinstance(reports, dict) or not set(reports) <= set(SONAR_ARRAY_MODES):
                return False
            for report in reports.values():
                if (not isinstance(report, dict)
                        or not {"bearing", "quality", "snr", "last_seen"} <= set(report)
                        or not set(report) <= {"bearing", "quality", "snr", "last_seen", "uncertainty_deg"}
                        or not bounded(report["bearing"], 0, 360) or report["bearing"] == 360
                        or not bounded(report["quality"], 0, 1)
                        or not bounded(report["snr"], -200, 200)
                        or not bounded(report["last_seen"], 0, 1e12)
                        or ("uncertainty_deg" in report
                            and not bounded(report["uncertainty_deg"], .05, 180))):
                    return False
            tma_seen = contact.get("tma_seen")
            if tma_seen is not None and not bounded(tma_seen, 0, 1e12):
                return False
            published_fixes = contact.get("fixes")
            if (not isinstance(published_fixes, list) or len(published_fixes) > 5
                    or len({fix.get("source") for fix in published_fixes
                            if isinstance(fix, dict)}) != len(published_fixes)):
                return False
            for fix in published_fixes:
                fields = {"source", "measured_at", "fixed_at", "x", "y",
                          "uncertainty_nm", "depth_m", "depth_uncertainty_m",
                          "quality"}
                if (not isinstance(fix, dict) or set(fix) != fields
                        or fix["source"] not in FIX_SOURCES
                        or not bounded(fix["measured_at"], 0, save_sim_t)
                        or not bounded(fix["fixed_at"], fix["measured_at"], save_sim_t)
                        or not bounded(fix["x"], -1_000_000, 1_000_000)
                        or not bounded(fix["y"], -1_000_000, 1_000_000)
                        or not bounded(fix["uncertainty_nm"], 1e-9, 100)
                        or not bounded(fix["quality"], 0, 1)
                        or ((fix["depth_m"] is None)
                            != (fix["depth_uncertainty_m"] is None))
                        or (fix["depth_m"] is not None
                            and (not bounded(fix["depth_m"], 0, 10_000)
                                 or not bounded(fix["depth_uncertainty_m"],
                                                1e-9, 10_000)))):
                    return False
            fixes = contact.get("buoy_fixes", [])
            if (not isinstance(fixes, list) or len(fixes) > 80
                    or any(not isinstance(row, (list, tuple)) or len(row) != 4
                           or not bounded(row[0], 0, 1e12)
                           or any(not bounded(v, -1_000_000, 1_000_000) for v in row[1:3])
                           or not bounded(row[3], 0, 1) for row in fixes)):
                return False
            history = contact.get("raw_bearings", [])
            if (not isinstance(history, list)
                    or len(history) > config.BEARING_TRACK_MAX_PTS
                    or any(not isinstance(row, (list, tuple)) or len(row) != 3
                           or any(not finite_number(value) for value in row)
                           or not 0.0 <= row[1] < 360.0
                           or not 0.0 <= row[2] <= 180.0
                           for row in history)):
                return False
            uncertainty = contact.get("bearing_uncertainty_deg")
            if (uncertainty is not None
                    and (not finite_number(uncertainty)
                         or not 0.0 <= uncertainty <= 180.0)):
                return False
            # v13: the operator's catalog assignment is required (None = none).
            if "player_profile" not in contact:
                return False
            profile = contact["player_profile"]
            if profile is not None and (
                    type(profile) is not str or profile not in (
                        runtime_catalog or CATALOG).profile_systems):
                return False
            passive_bearing = contact.get("passive_bearing")
            if (passive_bearing is not None
                    and (not finite_number(passive_bearing)
                         or not 0.0 <= passive_bearing < 360.0)):
                return False
            epoch = contact.get("passive_epoch")
            if epoch is not None and (not isinstance(epoch, int)
                                      or isinstance(epoch, bool) or epoch < 0):
                return False
            filter_t = contact.get("bearing_filter_t")
            if (filter_t is not None
                    and (not finite_number(filter_t) or filter_t < 0.0)):
                return False
            filter_rate = contact.get("bearing_filter_rate_deg_s", 0.0)
            if (not finite_number(filter_rate)
                    or abs(filter_rate) > config.SONAR_BEARING_RATE_MAX_DEG_S):
                return False
            filter_uncertainty = contact.get("bearing_filter_uncertainty_deg")
            if (filter_uncertainty is not None
                    and (not finite_number(filter_uncertainty)
                         or not 0.05 <= filter_uncertainty <= 180.0)):
                return False
            if (filter_t is None and filter_rate != 0.0) \
                    or (filter_t is not None
                        and (passive_bearing is None
                             or filter_uncertainty is None)):
                return False
            # W2: the helicopter's own independent dip-passive bearing track.
            dip_bearing = contact.get("dip_bearing")
            if (dip_bearing is not None
                    and (not finite_number(dip_bearing)
                         or not 0.0 <= dip_bearing < 360.0)):
                return False
            dip_uncertainty = contact.get("dip_bearing_uncertainty_deg")
            if (dip_uncertainty is not None
                    and (not finite_number(dip_uncertainty)
                         or not 0.05 <= dip_uncertainty <= 180.0)):
                return False
            dip_last_seen = contact.get("dip_last_seen")
            if dip_last_seen is not None and not bounded(
                    dip_last_seen, 0, save_sim_t):
                return False
            if any(contact.get(name) is not None
                   and not bounded(contact.get(name), -1_000_000, 1_000_000)
                   for name in ("dip_observer_x", "dip_observer_y")):
                return False
            if dip_bearing is not None and (
                    dip_uncertainty is None or dip_last_seen is None
                    or contact.get("dip_observer_x") is None
                    or contact.get("dip_observer_y") is None):
                return False
            ellipse = contact.get("tma_ellipse")
            if ellipse is not None and (
                    not isinstance(ellipse, list) or len(ellipse) != 3
                    or not bounded(ellipse[0], 0.0, 1e6)
                    or not bounded(ellipse[1], 0.0, ellipse[0] + 1e-9)
                    or not bounded(ellipse[2], 0.0, 180.0)):
                return False
            if (contact.get("towed_side") not in ("STBD", "PORT")
                    or type(contact.get("towed_ambiguous")) is not bool
                    or type(contact.get("towed_resolved")) is not bool
                    or (contact["towed_ambiguous"] and contact["towed_resolved"])
                    or (contact["towed_ambiguous"] and (
                        not bounded(contact.get("ambiguity_axis"), 0.0, 360.0)
                        or not bounded(contact.get("mirror_bearing"), 0.0, 360.0)))
                    or (contact.get("tonal_hz") is not None
                        and not bounded(contact["tonal_hz"], 0.1, 20000.0))):
                return False
        echoes = sonar.get("echo_history", [])
        if any(not isinstance(item, dict)
               or not finite_number(item.get("t"))
               or not finite_number(item.get("contact_id"))
               or any(name in item and not finite_number(item[name])
                      for name in ("bearing", "range_nm", "range_sigma_nm",
                                   "depth_m", "depth_sigma_m", "snr_db"))
               for item in echoes):
            return False
        tracks = sonar.get("tracks", {})
        if not isinstance(tracks, dict):
            return False
        if any(not isinstance(points, list)
               or len(points) > config.BEARING_TRACK_MAX_PTS
               or any(not isinstance(point, dict)
                       or any(not finite_number(point.get(name))
                              for name in ("t", "bearing", "fx", "fy",
                                           "fcourse"))
                       or ("uncertainty_deg" in point
                           and (not finite_number(point["uncertainty_deg"])
                                or not 0.05 <= point["uncertainty_deg"] <= 180.0))
                       or (point.get("freq_hz") is not None
                           and not bounded(point["freq_hz"], 0.1, 20000.0))
                       or not bounded(point.get("fspeed"), 0.0, 60.0)
                       for point in points)
               for points in tracks.values()):
            return False
        track_versions = sonar.get("track_versions", {})
        tma_versions = sonar.get("tma_versions", {})
        tma_next = sonar.get("tma_next", {})
        if any(not isinstance(values, dict)
               for values in (track_versions, tma_versions, tma_next)):
            return False
        if any(not isinstance(value, int) or isinstance(value, bool)
               or not 0 <= value <= 1_000_000_000
               for values in (track_versions, tma_versions)
               for value in values.values()):
            return False
        if any(not finite_number(value) or value < 0.0
               for value in tma_next.values()):
            return False
        try:
            all_keys = (set(tracks) | set(track_versions)
                        | set(tma_versions) | set(tma_next))
            if any(not isinstance(key, str) or str(int(key)) != key
                   for key in all_keys):
                return False
            gate_keys = ({int(key) for key in track_versions}
                         | {int(key) for key in tma_versions}
                         | {int(key) for key in tma_next})
            track_keys = {int(key) for key in tracks}
        except (TypeError, ValueError):
            return False
        if any(key < 0 for key in gate_keys | track_keys) \
                or not gate_keys <= track_keys:
            return False
        if any(track_versions.get(key, len(points)) < len(points)
               for key, points in tracks.items()):
            return False
        if any(value > track_versions.get(key, len(tracks[key]))
               for key, value in tma_versions.items()):
            return False
        sim_t = data.get("sim_t", 0.0)
        if (not finite_number(sim_t) or sim_t < 0.0
                or any(value > sim_t + config.TMA_RESOLVE_EVERY_S
                       for value in tma_next.values())
                or any(contact.get("bearing_filter_t") is not None
                       and contact["bearing_filter_t"] > sim_t
                       for contact in contacts.values())):
            return False
        if sonar.get("ping_pulse") not in sonar_equation.PULSES:
            return False
        clutter = sonar.get("pending_clutter")
        if (not isinstance(clutter, list)
                or len(clutter) > SonarSystem.MAX_PENDING_CLUTTER
                or any(not isinstance(item, dict)
                       or set(item) != {"ready_at", "mode", "snapshot"}
                       or item["mode"] not in SONAR_ARRAY_MODES + ("DIPPING",)
                       or not SonarSystem.valid_ping_snapshot(item["snapshot"])
                       or not bounded(item["ready_at"], 0, 1e12)
                       or not item["snapshot"]["t"] <= sim_t
                       or not 0 <= item["ready_at"] - item["snapshot"]["t"] <= 25000
                       for item in clutter)):
            return False
        pending_pings = sonar.get("pending_pings", [])
        # 25000 s covers two-way propagation across the 10000 NM snapshot bound.
        if len(pending_pings) > SonarSystem.MAX_PENDING_PINGS or any(not isinstance(item, dict)
               or set(item) != {"target_id", "sent_at", "ready_at", "range_factor", "mode", "snapshot"}
               or not identity(item.get("target_id"))
               or item["target_id"] not in allowed_ids
               or any(not bounded(item.get(key, 0), 0, 1e12)
                      for key in ("sent_at", "ready_at"))
               or not bounded(item.get("range_factor", 1), 0, 100)
                or item.get("mode", "BOW") not in SONAR_ARRAY_MODES + ("DIPPING",)
               or item.get("sent_at", sim_t) > sim_t
               or not 0 <= item.get("ready_at", sim_t) - item.get("sent_at", sim_t) <= 25000
               or not SonarSystem.valid_ping_snapshot(item["snapshot"])
               or not item["sent_at"] <= item["snapshot"]["t"] <= sim_t
               for item in pending_pings):
            return False
        return True

    if data.get("sonar_mode") not in SONAR_ARRAY_MODES:
        return False
    if not valid_sonar(data.get("sonar"), entity_ids):
        return False
    settings = data.get("weapon_settings")
    asw_block = data.get("asw")
    loadout = asw_block.get("loadout") if isinstance(asw_block, dict) else None
    weapon_keys = ({weapon.get("key") for weapon in loadout.get("weapons", ())
                    if isinstance(weapon, dict)}
                   if isinstance(loadout, dict) and isinstance(loadout.get("weapons"), list)
                   else set())
    if (not isinstance(settings, dict) or set(settings) != WEAPON_SETTINGS_FIELDS
            or settings["torpedo_type"] not in weapon_keys
            or settings["pattern"] not in torpedo_dyn.SEARCH_PATTERNS
            or not bounded(settings["enable_nm"], torpedo_dyn.ENABLE_RANGE_MIN_NM,
                           torpedo_dyn.ENABLE_RANGE_MAX_NM)
            or type(settings["salvo"]) is not int
            or settings["salvo"] not in torpedo_dyn.SALVO_SIZES):
        return False
    if not _valid_crew_block(
            data, valid_sonar=valid_sonar,
            valid_sonar_controls=valid_sonar_controls,
            entity_ids=entity_ids, bounded=bounded, identity=identity,
            finite_number=finite_number, sim_t=save_sim_t,
            emitter_keys=frozenset(key for key, emitter in runtime_catalog.emitters.items()
                                   if emitter.domain == "radar")):
        return False
    return True


def _radar_marks_ok(marks, save_sim_t) -> bool:
    """Save v25 ``radar_marks``: unmarked mast echoes and marked boats."""
    def real(value, limit=1e9):
        return type(value) is float and math.isfinite(value) and abs(value) <= limit

    def count(value):
        return type(value) is int and 0 <= value <= 2**53

    if not isinstance(marks, dict) or set(marks) != RADAR_MARKS_FIELDS:
        return False
    blips, marked = marks["blips"], marks["marked"]
    if (not count(marks["blip_seq"]) or not isinstance(blips, list)
            or len(blips) > config.RADAR_BLIP_MAX
            or not isinstance(marked, list) or len(marked) > RADAR_MARKED_MAX):
        return False
    previous = 0
    for blip in blips:
        if (not isinstance(blip, dict) or set(blip) != RADAR_BLIP_FIELDS
                or not count(blip["seq"]) or not count(blip["target"])
                or not previous < blip["seq"] <= marks["blip_seq"]
                or not all(real(blip[key]) for key in (
                    "t", "bearing", "range_nm", "error", "observer_x", "observer_y", "x", "y"))
                or not 0.0 <= blip["t"] <= save_sim_t
                or not 0.0 <= blip["bearing"] < 360.0 or blip["range_nm"] < 0.0
                or blip["error"] < 0.0):
            return False
        previous = blip["seq"]
    subs = [row[0] for row in marked if isinstance(row, list) and row]
    if len(set(subs)) != len(subs):
        return False
    return all(isinstance(row, list) and len(row) == 3 and count(row[0])
               and type(row[1]) is str and 1 <= len(row[1]) <= 32 and real(row[2])
               and 0.0 <= row[2] <= save_sim_t for row in marked)
