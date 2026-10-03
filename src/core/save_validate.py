"""Strict validation of a save v16 document and its catalog binding.

Pure functions (no game state): ``valid_save_document`` is the single
acceptance check a load must pass before a candidate restore begins;
``catalog_for_save`` resolves the runtime catalog a document was written
with.  Verbatim moves from ``game_save.py`` (plan 1.3, phase 2, step 1).
``valid_save_document`` runs one check per save block in a fixed order; the
entity groups live in ``save_validate_entities``, the helicopter, buoys and
weapons in flight in ``save_validate_weapons``, the crew and sonar blocks in
``save_validate_crew``/``save_validate_sonar``.
"""

import math


from src.core import config
from src.core.plot import PlotLayer
from src.ship.route import Route
from src.core.autocrew import AutocrewController
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.sensors.ais import AISReceiver
from src.sensors import lookout_id
from src.physics import ship_dynamics
from src.physics import torpedo_dyn
from src.ship import damage as damage_physics
from src.world.ocean import OceanEnvironment
from src.core.save_schema import (
    WEAPON_SETTINGS_FIELDS,
    COMPARTMENT_FIELDS, COMPARTMENT_STATES, DAMAGE_FIELDS, PING_INTERCEPTS_MAX, RADAR_BLIP_FIELDS,
    RADAR_MARKED_MAX, RADAR_MARKS_FIELDS, RNG_STREAMS, SAVE_ROOT_FIELDS, SHIP_FIELDS,
    WORLD_FIELDS)
from src.data.catalog import CATALOG, catalog_from_runtime_snapshot
from src.core.tasking import TaskBoard
from src.core import baffles
from src.core.incidents import IncidentBoard
from src.core.hq_reports import HqReports
from src.weapons import rbu
from src.core.crew import CrewState
from src.sensors.esm import valid_esm_state
from src.sensors.platform import validate_suite_state
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.sonar.sonar import SONAR_ARRAY_MODES
from src.ui.stations_view import opz_ppi_rect
from src.air import chaff as chaff_physics
from src.air.flights import FlightManager
from src.world.world import World
from src.world.coastline import Coastline
from src.world.grounding import (DEFAULT_HULL_SPEC, GroundingContact, HullSpec,
                                 grounding_contact_is_consistent)
from src.weapons.asw import valid_asw_state
from src.weapons.air_defense import valid_air_defense_state

from src.core.limits import MAX_AIR_PICTURE_TRACKS
from src.core.save_validate_common import (bounded, finite_number, finite_tree,
                                           identity)
from src.core.save_validate_entities import check_entities
from src.core.save_validate_weapons import (
    check_buoys_and_aircraft, check_essms, check_helo, check_missiles,
    check_player_torpedoes)
# Verbatim moves: the crew block and the sonar station checks.
from src.core.save_validate_crew import _valid_crew_block  # noqa: F401
from src.core.save_validate_sonar import valid_sonar_block




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

def opz_chart_size() -> tuple[int, int]:
    """The OPZ chart's size on the canvas (font and text-scale dependent).

    Computed on the main thread: it reads pygame fonts and the UI scale, so a
    background check passes it to ``valid_save_document`` instead."""
    chart = opz_ppi_rect(config.OPZ_STATION_RECT)
    return int(chart.w), int(chart.h)


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


def _check_preamble(data) -> bool:
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
    if not valid_sonar_controls(data.get("sonar_controls")):
        return False
    return True


def _check_frame(data, runtime_catalog, opz_chart):
    """Platform state, sim time, finite tree, UI, catalog, ESM and the
    torpedo inventory; False, or (platform_state_version, save_sim_t,
    world_size, runtime_catalog, torpedo_inventory)."""
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
    chart_w, chart_h = opz_chart if opz_chart is not None else opz_chart_size()
    opz_min_scale = min(chart_w, chart_h) / world_size
    opz_max_scale = max(opz_min_scale, min(chart_w, chart_h) / (
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
    return (platform_state_version, save_sim_t, world_size, runtime_catalog,
            torpedo_inventory)


def _check_mission_blocks(data, save_sim_t):
    """Mission runtime and the per-version blocks; False, or
    (runtime_mission, difficulty)."""
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
    # Save v44: the combat swimmers' lock-out so far.
    from src.core import boat_missions
    if not boat_missions.valid_hold(data.get("swimmer_hold_s")):
        return False
    # Save v45: the counters of scenarios 13, 19 and 20.
    from src.core import mission_modes
    if not mission_modes.valid_progress(data.get("mission_progress")):
        return False
    # Save v46: a free patrol's encounters and points; only in one.
    from src.core import free_roam
    free = data.get("free_roam")
    if not free_roam.valid_state(free, save_sim_t):
        return False
    if free is not None and not free_roam.scenario_free(data.get("scenario_key")):
        return False
    # Save v39: the AI hunters' ESM bearing lines.
    from src.core import hunter
    if not hunter.valid_esm_log(data.get("hunter_esm"), save_sim_t):
        return False
    # Save v43: the AI hunters' lead.
    if not hunter.valid_lead(data.get("hunter_lead"), save_sim_t):
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
    return runtime_mission, difficulty


def _check_mission_stores(data, runtime_mission, difficulty, torpedo_inventory,
                          runtime_catalog) -> bool:
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
    return True


def _check_air_picture(data, runtime_catalog, save_sim_t) -> bool:
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
    return True


def _check_hfdf(data) -> bool:
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
    return True


def _check_ship(data):
    """The frigate, its radars and grounding; False, or (hull, grounding,
    pose, contact)."""
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
                # The hull fractions come out of float geometry and may
                # overshoot the hull's end by rounding.
                or not -1.0 - 1e-9 <= contact["hull_longitudinal"] <= 1.0 + 1e-9
                or not -1.0 - 1e-9 <= contact["hull_lateral"] <= 1.0 + 1e-9))
            or any(abs(ship[key] - pose[index]) > 1e-9
                   for index, key in enumerate(("x", "y", "course")))):
        return False
    return hull, grounding, pose, contact


def _check_damage(data) -> bool:
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
    return True


def _check_air_defense_state(data, runtime_catalog, platform_state_version,
                             save_sim_t) -> bool:
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
    return True


def _check_world(data, hull, grounding, contact, pose) -> bool:
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
    return True


def _check_weapon_settings(data) -> bool:
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
    return True


def valid_save_document(data, runtime_catalog=None, opz_chart=None) -> bool:
    """Strict check of a parsed save document. With ``opz_chart`` (from
    ``opz_chart_size()``) it is pure: no pygame, no live game or global
    state, so it may run off the main thread."""
    if not _check_preamble(data):
        return False
    frame = _check_frame(data, runtime_catalog, opz_chart)
    if frame is False:
        return False
    (platform_state_version, save_sim_t, world_size, runtime_catalog,
     torpedo_inventory) = frame
    mission = _check_mission_blocks(data, save_sim_t)
    if mission is False:
        return False
    runtime_mission, difficulty = mission
    if not _check_mission_stores(data, runtime_mission, difficulty,
                                 torpedo_inventory, runtime_catalog):
        return False
    if not _check_air_picture(data, runtime_catalog, save_sim_t):
        return False
    if not _check_hfdf(data):
        return False
    ship = _check_ship(data)
    if ship is False:
        return False
    hull, grounding, pose, contact = ship
    if not _check_damage(data):
        return False
    entities = check_entities(data, runtime_catalog, platform_state_version,
                              save_sim_t)
    if entities is False:
        return False
    entity_ids, pending_missiles, used_asrocs, spent_asrocs = entities
    if not _check_air_defense_state(data, runtime_catalog,
                                    platform_state_version, save_sim_t):
        return False
    helo = check_helo(data, runtime_catalog)
    if helo is False:
        return False
    buoy_ids = check_buoys_and_aircraft(data, helo, world_size, save_sim_t)
    if buoy_ids is False:
        return False
    missiles = check_missiles(data, pending_missiles)
    if missiles is False:
        return False
    asms, torpedoes, essms, asm_ids = missiles
    if not check_player_torpedoes(data, torpedoes, entity_ids, runtime_catalog,
                                  difficulty, helo, used_asrocs, spent_asrocs,
                                  buoy_ids):
        return False
    if not check_essms(data, essms, asm_ids):
        return False
    if not _check_world(data, hull, grounding, contact, pose):
        return False
    def valid_sonar(sonar, allowed_ids) -> bool:
        return valid_sonar_block(
            sonar, allowed_ids, data=data, runtime_catalog=runtime_catalog,
            default_catalog=CATALOG, save_sim_t=save_sim_t, buoy_ids=buoy_ids,
            finite_number=finite_number, bounded=bounded, identity=identity)

    if data.get("sonar_mode") not in SONAR_ARRAY_MODES:
        return False
    if not valid_sonar(data.get("sonar"), entity_ids):
        return False
    if not _check_weapon_settings(data):
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
