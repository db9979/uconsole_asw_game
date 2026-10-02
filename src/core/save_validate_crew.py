"""Save validation of the crewed boat's ``crew`` block.

``_valid_crew_block`` checks the exact save ``crew`` block (None, or the
crewed boat's binding) of a document.  Verbatim move from
``save_validate.py``, which re-exports it.
"""

import json

from src.core import config
from src.core.plot import PlotLayer
from src.ship.route import Route
from src.core.boat_esm import BoatESM
from src.core.boat_radio import BoatRadio
from src.core import opfor
from src.physics import torpedo_dyn
from src.core.save_schema import (
    CREW_BATTERY_STATES, CREW_FEED_FIELDS,
    CREW_FIELDS, CREW_ORDERS_FIELDS, CREW_SIGHTING_FIELDS, CREW_STATION_FIELDS,
    CREW_TDC_FIELDS,
    CREW_WIRE_FIELDS,
    CREW_WIRE_STATES)
from src.core import baffles, boat_nav, buoy_antenna
from src.core.crew import CrewState
from src.sonar.sonar import SONAR_ARRAY_MODES


def _valid_crew_block(data, *, valid_sonar, valid_sonar_controls, entity_ids,
                      bounded, identity, finite_number, sim_t, emitter_keys) -> bool:
    """Exact save v15 ``crew`` block: None, or the crewed boat's binding.

    Every reference (boat, torpedoes, contacts) must point at an entity of
    the same document; the boat's sonar station is validated with the same
    rules as the frigate's.
    """
    from src.sonar.platforms import (OWNSHIP_TARGET_ID, OWN_TORPEDO_TARGET_BASE,
                                     SCOPE_AIR_TARGET_ID, SCOPE_MPA_TARGET_ID)

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
            or not buoy_antenna.valid_state(orders["buoy"])
            or orders["torpedo_pattern"] not in torpedo_dyn.BOAT_SEARCH_PATTERNS
            or not bounded(orders["torpedo_enable_nm"], torpedo_dyn.ENABLE_RANGE_MIN_NM,
                           torpedo_dyn.BOAT_ENABLE_DEFAULT_NM)
            or not boat_nav.valid_state(orders["nav"])
            or not Route.valid_state(orders["route"], config.WORLD_SIZE_NM)
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
    sighting_ids = (set(entity_ids) | {OWNSHIP_TARGET_ID, SCOPE_AIR_TARGET_ID,
                                       SCOPE_MPA_TARGET_ID} | own_torpedo_ids)
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
