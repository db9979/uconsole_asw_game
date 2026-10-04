"""Free patrol ("Freie Fahrt"): no time limit, HQ orders and encounters.

Two scenarios, one per side. Own ship sails without a time limit; the patrol
ends only when it is lost (or, on the submarine's side, when it sinks the
hunting frigate). What there is to do comes over the radio and from the sea:

- HQ orders. The frigate's radio room gets the task board's offers without
  the scenario's cap and more often, and a sixth kind, ``patrol``: hold a
  sector for ``FREE_PATROL_HOLD_S`` (``game_tasking.py``). The submarine's
  broadcasts carry an order almost every time one is free, from four more
  kinds besides area, report and silence (``boat_radio.FREE_ORDER_KINDS``):
  ``attack`` a named merchant (one is brought in for it), ``landing``
  (swimmers out off the nearest coast, shallow and slow), ``supply`` (meet
  a supply boat at periscope depth, slow: torpedoes and battery full) and
  ``recon`` (a situation report with the frigate in sight).
- Encounters every ``FREE_ENCOUNTER_INTERVAL_S``: for the frigate a hostile
  submarine, a neutral one in transit (not to be sunk), an air raid or
  merchants; for the submarine a lead the hunting frigate gets on it, or
  merchants passing. Far-off, unheard units are reused for the next one, so
  the world stays bounded on a long patrol.
- Incidents at sea (``game_incidents.py``) without the scenario's cap and
  more often.

Saved as the root field ``free_roam`` (None outside a free patrol): the next
encounter's time, the count, a short log, the submarine's points and the
neutral submarines already charged. Every draw is counter-based
(``detrand``) or a local stream keyed by the seed and the count; new
entities use the saved world stream like every other spawn.

Observation boundary: HQ's reports are modelled intelligence with their
error; adjudication (sunk, inside an area, in sight) reads the true state
like every other end check.
"""

from __future__ import annotations

import math
import random

from src.core import boat_nav, config, detrand
from src.core.i18n import message, raw_text
from src.physics.geo import bearing_deg as _bearing

MODES = ("free", "free_boat")
VERSION = 1
FIELDS = frozenset({"version", "next_t", "count", "log", "points", "charged"})
LOG_FIELDS = frozenset({"t", "kind"})
LOG_KINDS = ("sub", "neutral_sub", "raid", "merchants", "hunt")
MAX_SUBS = 48                      # submarines in the world, sunk ones included
CHARGED_MAX = MAX_SUBS
MAX_TIME_S = 1e9
MAX_POINTS = 10_000_000
MAX_CIVILIANS = 64                 # never more ships than this in the world
MERCHANT_CATEGORIES = frozenset({"TANKER", "FRACHT", "PASSAGIER"})


# --- which mission ------------------------------------------------------------------------

def kind(game):
    """``free`` (frigate side), ``free_boat`` (submarine side) or None."""
    if getattr(game, "custom_mission_definition", None) is not None:
        return None
    value = getattr(getattr(game, "mission", None), "win_mode", None)
    return value if value in MODES else None


def active(game) -> bool:
    return kind(game) is not None and isinstance(getattr(game, "free_roam", None), dict)


def frigate_side(game) -> bool:
    return kind(game) == "free"


def boat_side(game) -> bool:
    return kind(game) == "free_boat"


def scenario_free(scenario_key) -> bool:
    spec = config.SCENARIOS.get(scenario_key, {})
    return config.MISSION_TYPES.get(spec.get("mission_type"), {}).get("win") in MODES


# --- state ----------------------------------------------------------------------------------

def new_state(seed: int) -> dict:
    return dict(version=VERSION,
                next_t=detrand.uniform(*config.FREE_FIRST_ENCOUNTER_S, seed, "free-first"),
                count=0, log=[], points=0, charged=[])


def _time(value) -> bool:
    return (type(value) in (int, float) and not isinstance(value, bool)
            and math.isfinite(value) and 0.0 <= value <= MAX_TIME_S)


def valid_state(value, save_sim_t: float) -> bool:
    """Save ``free_roam``: None, or the exact block of a free patrol."""
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != FIELDS:
        return False
    if type(value["version"]) is not int or value["version"] != VERSION:
        return False
    if not _time(value["next_t"]):
        return False
    if type(value["count"]) is not int or not 0 <= value["count"] <= 1_000_000:
        return False
    if type(value["points"]) is not int or not -MAX_POINTS <= value["points"] <= MAX_POINTS:
        return False
    log = value["log"]
    if not isinstance(log, list) or len(log) > config.FREE_LOG_MAX:
        return False
    previous = 0.0
    for row in log:
        if (not isinstance(row, dict) or set(row) != LOG_FIELDS
                or not _time(row["t"]) or row["t"] > save_sim_t or row["t"] < previous
                or row["kind"] not in LOG_KINDS):
            return False
        previous = row["t"]
    charged = value["charged"]
    return (isinstance(charged, list) and len(charged) <= CHARGED_MAX
            and all(type(item) is int and 0 <= item <= 2**31 for item in charged)
            and charged == sorted(set(charged)))


def restore(value):
    if value is None:
        return None
    return dict(value, next_t=float(value["next_t"]),
                log=[dict(row, t=float(row["t"])) for row in value["log"]],
                charged=list(value["charged"]))


def serialize(game):
    value = getattr(game, "free_roam", None)
    if value is None:
        return None
    return dict(value, log=[dict(row) for row in value["log"]], charged=list(value["charged"]))


# --- setup ----------------------------------------------------------------------------------

def setup(game) -> None:
    """A free patrol's own schedule (after the world is populated)."""
    if kind(game) is None:
        game.free_roam = None
        return
    game.free_roam = new_state(int(game.seed))
    board = getattr(game, "tasking", None)
    if board is not None:
        # The frigate's radio room is busy from early on; on the submarine's
        # side the AI frigate keeps the scenario's schedule.
        if frigate_side(game):
            board.next_offer_t = detrand.uniform(*config.FREE_TASK_FIRST_S,
                                                 game.seed, "free-task-first")
    incidents = getattr(game, "incidents", None)
    if incidents is not None:
        incidents.next_t = detrand.uniform(*config.FREE_INCIDENT_FIRST_S,
                                           game.seed, "free-incident-first")


def task_interval(game):
    """The HQ task schedule of the frigate: ``(interval, cap)``."""
    if frigate_side(game):
        return config.FREE_TASK_INTERVAL_S, None
    return config.TASK_INTERVAL_S, config.TASK_MAX_OFFERS


def incident_interval(game):
    """The incident schedule: ``(interval, cap)``."""
    if kind(game) is not None:
        return config.FREE_INCIDENT_INTERVAL_S, None
    return config.INCIDENT_INTERVAL_S, config.INCIDENT_MAX


# --- geometry -------------------------------------------------------------------------------

def water_point(game, x, y, low, high, tag, index, min_depth=60.0):
    """A deterministic point ``low..high`` NM from ``x, y`` in water at least
    ``min_depth`` deep, or None."""
    size = float(game.world.size_nm)
    for attempt in range(12):
        angle = math.radians(360.0 * detrand.u01(game.seed, tag + "-brg", index, attempt))
        distance = detrand.uniform(low, high, game.seed, tag + "-rng", index, attempt)
        px = x + distance * math.sin(angle)
        py = y - distance * math.cos(angle)
        if not (5.0 <= px <= size - 5.0 and 5.0 <= py <= size - 5.0):
            continue
        if not game.world.on_land(px, py) and game.world.depth_m(px, py) >= min_depth:
            return float(px), float(py)
    return None


def own_unit(game):
    """``(x, y)`` of the side's own ship: the frigate or the patrol boat."""
    if boat_side(game):
        boat = patrol_boat(game)
        if boat is not None:
            return boat.x, boat.y
    return game.ship.x, game.ship.y


def patrol_boat(game):
    """The submarine of the submarine's free patrol (crewed or not), or None."""
    from src.core import boat_missions
    return boat_missions.target_sub(game) if boat_side(game) else None


def _far(game, x, y) -> bool:
    """Beyond ``FREE_RECYCLE_NM`` of the frigate and the patrol boat."""
    points = [(game.ship.x, game.ship.y)]
    boat = patrol_boat(game)
    if boat is not None:
        points.append((boat.x, boat.y))
    return all(math.hypot(x - px, y - py) > config.FREE_RECYCLE_NM for px, py in points)


def _heard_lately(game, entity) -> bool:
    contact = game.sonar.contacts.get(entity.id)
    return (contact is not None
            and 0.0 <= game.sim_t - contact.last_seen <= config.FREE_RECYCLE_QUIET_S)


# --- every substep --------------------------------------------------------------------------

def update(game, dt: float) -> None:
    """The encounter schedule and the neutral submarines' account."""
    if not active(game) or game.game_over:
        return
    state = game.free_roam
    if game.sim_t < state["next_t"]:
        return
    index = state["count"]
    state["count"] += 1
    happened = encounter(game, index)
    if happened is not None:
        state["log"].append(dict(t=float(game.sim_t), kind=happened))
        del state["log"][:-config.FREE_LOG_MAX]
    state["next_t"] = game.sim_t + detrand.uniform(*config.FREE_ENCOUNTER_INTERVAL_S,
                                                   game.seed, "free-interval", index)


def candidates(game) -> list:
    """The encounters that can happen now, with their weights."""
    side = "uboot" if boat_side(game) else "frigate"
    rows = []
    for name, weight in config.FREE_ENCOUNTER_WEIGHTS[side]:
        if name == "sub" and _sub_slot(game, "hostile") is False:
            continue
        if name == "neutral_sub" and _sub_slot(game, "neutral") is False:
            continue
        if name == "raid" and (len(game.raiders) >= config.RAID_MAX_CONCURRENT
                               or game.mission_time < config.FREE_RAID_AFTER_S):
            continue
        if name == "merchants" and _merchants_about(game) >= config.FREE_MAX_MERCHANTS:
            continue
        if name == "hunt" and (patrol_boat(game) is None or game.damage.ship_sunk
                               or game.mission_time < config.FREE_HUNT_AFTER_S
                               or _hunted_lately(game)):
            continue
        rows.append((name, weight))
    return rows


def _hunted_lately(game) -> bool:
    last = [row["t"] for row in game.free_roam["log"] if row["kind"] == "hunt"]
    return bool(last) and game.sim_t - last[-1] < config.FREE_HUNT_GAP_S


def encounter(game, index: int, forced: str | None = None):
    """Start encounter ``index`` (``forced`` names one, for tests); returns its kind."""
    rows = [row for row in candidates(game) if forced is None or row[0] == forced]
    if not rows:
        return None
    total = sum(weight for _name, weight in rows)
    pick = detrand.u01(game.seed, "free-kind", index) * total
    name = rows[-1][0]
    for row_name, weight in rows:
        if pick < weight:
            name = row_name
            break
        pick -= weight
    done = {"sub": lambda: _sub_encounter(game, index, "hostile"),
            "neutral_sub": lambda: _sub_encounter(game, index, "neutral"),
            "raid": lambda: _raid(game),
            "merchants": lambda: spawn_merchants(game, index) > 0,
            "hunt": lambda: _hunt(game, index)}[name]()
    return name if done else None


# --- submarines -------------------------------------------------------------------------------

def _subs(game, side: str) -> list:
    return [sub for sub in sorted(game.subs, key=lambda item: item.id)
            if sub.side == side and not sub.sunk and sub.state not in ("SINKING", "SUNK")
            and not sub.manual]


def _sub_slot(game, side: str):
    """True: a new boat fits; a far, unheard boat to reuse; False: none."""
    alive = _subs(game, side)
    cap = config.FREE_MAX_HOSTILE if side == "hostile" else config.FREE_MAX_NEUTRAL
    if len(alive) < cap and len(game.subs) < MAX_SUBS:
        return True
    for sub in alive:
        if _far(game, sub.x, sub.y) and not _heard_lately(game, sub):
            return sub
    return False


def _sub_encounter(game, index: int, side: str) -> bool:
    slot = _sub_slot(game, side)
    if slot is False:
        return False
    point = water_point(game, game.ship.x, game.ship.y, *config.FREE_SUB_SPAWN_NM,
                        "free-sub", index)
    if point is None:
        return False
    course = (_bearing(*point, game.ship.x, game.ship.y)
              + 120.0 * (detrand.u01(game.seed, "free-sub-course", index) - 0.5)) % 360.0
    if slot is True:
        sub = _new_sub(game, index, side, point, course)
    else:
        # A boat long gone from the area comes back as the next one.
        sub = slot
        sub.x, sub.y = point
        sub.course = sub.target_course = course
        _drop_frigate_picture(game, sub.id)
        sub.forget()
    sub.start_pos = (sub.x, sub.y)
    if side == "hostile":
        _hq_threat(game, sub, "free.hq.sub")
    else:
        _hq_threat(game, sub, "free.hq.neutral_sub")
    return True


def _drop_frigate_picture(game, target_id: int) -> None:
    """The frigate's leftovers on a boat's old identity go with it."""
    station = game._frigate_sonar
    sonar = station.sonar
    for store in (sonar.contacts, sonar._tracks, sonar._tma_versions, sonar._tma_next,
                  sonar.tma_proposals, station.tma_hypotheses):
        store.pop(target_id, None)


def _new_sub(game, index: int, side: str, point, course):
    from src.enemies.sub import Sub
    pool = config.MISSION_TYPES["freifahrt"]["sub_types"]
    if side == "neutral":
        pool = ["aip_modern", "ssn"]
    stype = pool[int(detrand.u01(game.seed, "free-sub-type", index) * len(pool)) % len(pool)]
    lv = game.difficulty
    profile = game.runtime_catalog.subs[stype]
    depth = 40.0 + (min(100.0, profile.max_depth_m * 0.5) - 40.0) * detrand.u01(
        game.seed, "free-sub-depth", index)
    sub = Sub(point[0], point[1], depth_m=depth, course_deg=course, stype_key=stype,
              rng=game.rng_world, quiet_mult=lv["quiet_mult"],
              attack_mult=lv["enemy_attack_mult"],
              attack_cooldown_s=lv["enemy_cooldown_s"],
              solution_threshold=lv["enemy_solution_threshold"], profile=profile,
              decoy_profile=game.runtime_catalog.decoys[
                  game.runtime_catalog.runtime_bindings["submarine_decoy"]],
              enemy_torpedo_profile=game.runtime_catalog.torpedoes[
                  game.runtime_catalog.runtime_bindings["enemy_torpedo"]],
              side=side, runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)
    game.subs.append(sub)
    return sub


def _coarse(game, x, y):
    """Bearing to 45° and range to 5 NM from own ship, as HQ prints them."""
    dx, dy = x - game.ship.x, y - game.ship.y
    bearing = int(((math.degrees(math.atan2(dx, -dy)) % 360.0 + 22.5) // 45.0) * 45.0) % 360
    distance = max(5, int((math.hypot(dx, dy) + 2.5) // 5.0) * 5)
    return bearing, distance


def _hq_threat(game, sub, key: str) -> None:
    """HQ's coarse report of a boat entering the area (frigate side)."""
    bearing, distance = _coarse(game, sub.x, sub.y)
    text = message(key, bearing=f"{bearing:03d}", range=str(distance))
    game.hq_msg(text)
    game.announce(text, "funk", 5.0)


def charge_frigate_hit(game, sub) -> None:
    """A neutral submarine the frigate's own weapons sent down costs the
    frigate ``FREE_NEUTRAL_SUNK`` once. Groundings, collisions and the
    hostile boat's shots cost nothing, and on the submarine's side the
    frigate's score is not the player's."""
    if not active(game) or not frigate_side(game):
        return
    state = game.free_roam
    if (getattr(sub, "side", None) != "neutral" or sub.state not in ("SINKING", "SUNK")
            or sub.id in state["charged"] or len(state["charged"]) >= CHARGED_MAX):
        return
    state["charged"] = sorted(state["charged"] + [int(sub.id)])
    game.score -= config.FREE_NEUTRAL_SUNK
    text = message("free.neutral_sunk", points=f"{-config.FREE_NEUTRAL_SUNK:+d}")
    game.hq_msg(text)
    game.announce(text, "funk", 6.0)


# --- air raid -------------------------------------------------------------------------------

def _raid(game) -> bool:
    game._spawn_raid_wave(game._air_defense_loadout["raider"])
    text = message("free.hq.raid")
    game.hq_msg(text)
    game.announce(text, "funk", 5.0)
    return True


# --- merchants -------------------------------------------------------------------------------

def _merchants_about(game) -> int:
    x, y = own_unit(game)
    return sum(1 for ship in game.civilians
               if not ship.sunk and math.hypot(ship.x - x, ship.y - y) <= 60.0)


def _referenced(game) -> set:
    ids = set()
    for task in getattr(getattr(game, "tasking", None), "tasks", ()):
        if task["target_id"] is not None and task["state"] in ("offered", "active"):
            ids.add(task["target_id"])
    for item in getattr(getattr(game, "incidents", None), "items", ()):
        if item.get("target_id") is not None:
            ids.add(item["target_id"])
    boat = getattr(game, "_opfor", None)
    if boat is not None:
        for order in boat.radio.orders:
            if order["target_id"] is not None:
                ids.add(order["target_id"])
    ids.update(getattr(game, "mission_units", {}).values())
    return ids


def _reusable_merchant(game, taken: set):
    referenced = _referenced(game)
    for ship in sorted(game.civilians, key=lambda item: item.id):
        if (not ship.sunk and ship.side == "neutral" and ship.id not in referenced
                and ship.id not in taken and getattr(ship, "live_mmsi", None) is None
                and _far(game, ship.x, ship.y)):
            return ship
    return None


def merchant(game, x, y, course, index: int, member: int, taken: set):
    """A merchant at ``x, y`` on ``course``: a new one, or a far-off one reused."""
    from src.enemies.civilian import CivilianShip
    ship = None
    if len(game.civilians) >= MAX_CIVILIANS - 8:
        ship = _reusable_merchant(game, taken)
        if ship is None:
            return None
        ship.x, ship.y = x, y
    else:
        rng = random.Random(int(game.seed) * 7907 + 1009 * (index + 1) + member)
        ship = CivilianShip(x, y, rng=game.rng_world,
                            profile=game.runtime_catalog.pick_surface(rng, hostile=False),
                            side="neutral", doctrine="surface_transit",
                            runtime_catalog=game.runtime_catalog)
        game.civilians.append(ship)
    ship.course = ship.target_course = course % 360.0
    ship.target_speed = ship.speed
    ship.turn_left = 3600.0
    taken.add(ship.id)
    return ship


def spawn_merchants(game, index: int) -> int:
    """A group of merchants crossing ahead of own ship; returns how many."""
    ox, oy = own_unit(game)
    point = water_point(game, ox, oy, *config.FREE_MERCHANT_SPAWN_NM, "free-merchant",
                        index, min_depth=25.0)
    if point is None:
        return 0
    low, high = config.FREE_MERCHANT_GROUP
    count = low + int(detrand.u01(game.seed, "free-merchant-count", index) * (high - low + 1))
    count = min(count, high)
    across = _bearing(*point, ox, oy) + (90.0 if detrand.u01(
        game.seed, "free-merchant-side", index) < 0.5 else -90.0)
    course = across + 40.0 * (detrand.u01(game.seed, "free-merchant-course", index) - 0.5)
    taken = set()
    placed = 0
    for member in range(count):
        back = member * 1.5
        x = point[0] - back * math.sin(math.radians(course))
        y = point[1] + back * math.cos(math.radians(course))
        if game.world.on_land(x, y):
            continue
        if merchant(game, x, y, course, index, member, taken) is not None:
            placed += 1
    return placed


# --- the submarine's hunter -----------------------------------------------------------------

def _hunt(game, index: int) -> bool:
    """The frigate's HQ reports the patrol boat (with its error): the AI hunt
    runs the lead down; the boat's radio room hears of the search."""
    from src.core import hunter
    boat = patrol_boat(game)
    if boat is None:
        return False
    sigma = config.FREE_HUNT_SIGMA_NM
    x = boat.x + sigma * detrand.normal(game.seed, "free-hunt-x", index)
    y = boat.y + sigma * detrand.normal(game.seed, "free-hunt-y", index)
    dx, dy = x - game.ship.x, y - game.ship.y
    bearing = round(math.degrees(math.atan2(dx, -dy)) % 360.0 / 5.0) * 5.0 % 360.0
    distance = max(1.0, round(math.hypot(dx, dy)))
    hunter.set_hq_lead(game, bearing, distance)
    game.hq_msg(message("free.hq.hunt", bearing=f"{bearing:03.0f}", range=f"{distance:.0f}"))
    crewed = getattr(game, "_opfor", None)
    if crewed is not None and crewed.sub is boat:
        crewed.notice(game.sim_t, "radio", message("free.boat.hunted"),
                      stamp=game.world.format_time())
    return True


# --- the submarine's orders -----------------------------------------------------------------

def _order_kinds(game, boat) -> list:
    from src.core import boat_radio
    sub = boat.sub
    kinds = list(boat_radio.FREE_ORDER_KINDS)
    if not _supply_needed(sub):
        kinds.remove("supply")
    if game.damage.ship_sunk:
        kinds.remove("recon")
    return kinds


def _supply_needed(sub) -> bool:
    battery = sub.weapon_battery
    torpedoes_low = (battery is not None
                     and battery.remaining_total <= battery.capacity_total // 2)
    endurance = sub.endurance
    battery_low = (endurance is not None
                   and endurance.battery_kwh < 0.4 * endurance.profile.battery_capacity_kwh)
    return torpedoes_low or battery_low


def issue_order(game, boat, radio, number: int, now: float):
    """The order a free patrol's broadcast ``number`` carries, or None."""
    from src.core import boat_radio
    seed = int(game.seed)
    if (number < 1 or radio.active_order() is not None
            or radio.order_seq >= boat_radio.ORDER_SEQ_LIMIT
            or detrand.u01(seed, "free-order", number) >= config.FREE_ORDER_P):
        return None
    kinds = _order_kinds(game, boat)
    name = kinds[min(len(kinds) - 1, int(detrand.u01(seed, "free-order-kind", number)
                                         * len(kinds)))]
    fields = _order_fields(game, boat, name, number)
    if fields is None:
        name, fields = "report", {}
    duration = config.FREE_ORDER_S.get(name, {"report": config.UBOOT_ORDER_REPORT_S,
                                              "silence": config.UBOOT_ORDER_SILENCE_S,
                                              "area": config.UBOOT_ORDER_AREA_S}.get(name))
    radio.order_seq += 1
    return boat_radio.new_order(radio.order_seq, name, number, now, now + duration, **fields)


def _order_fields(game, boat, name: str, number: int):
    """Position and target of an order, or None when it cannot be given."""
    from src.core import boat_radio, mission_geo
    sub = boat.sub
    if name == "area":
        point = boat_radio._order_area(game, sub, int(game.seed), number)
        if point is None:
            return None
        return dict(x=point[0], y=point[1], radius_nm=config.UBOOT_ORDER_RADIUS_NM)
    if name == "attack":
        point = water_point(game, sub.x, sub.y, *config.FREE_ATTACK_RANGE_NM,
                            "free-attack", number, min_depth=25.0)
        if point is None:
            return None
        course = (_bearing(*point, sub.x, sub.y) + (90.0 if detrand.u01(
            game.seed, "free-attack-side", number) < 0.5 else -90.0)) % 360.0
        ship = merchant(game, point[0], point[1], course, 100_000 + number, 0, set())
        if ship is None:
            return None
        sigma = config.FREE_ATTACK_SIGMA_NM
        ship.turn_left = config.FREE_ORDER_S["attack"] + 600.0
        return dict(x=round(ship.x + sigma * detrand.normal(game.seed, "free-attack-x", number), 2),
                    y=round(ship.y + sigma * detrand.normal(game.seed, "free-attack-y", number), 2),
                    radius_nm=2.0 * sigma, target_id=int(ship.id),
                    name=raw_name(ship), course=float(round(ship.course / 5.0) * 5.0 % 360.0),
                    speed_kn=float(round(max(0.0, ship.speed))))
    if name == "landing":
        zone = mission_geo.swimmer_zone(game.world, (round(sub.x), round(sub.y)))
        if zone is None or math.hypot(zone["x"] - sub.x, zone["y"] - sub.y) \
                > config.FREE_LANDING_MAX_NM:
            return None
        return dict(x=round(zone["x"], 2), y=round(zone["y"], 2),
                    radius_nm=config.SWIMMER_ZONE_NM)
    if name == "supply":
        point = water_point(game, sub.x, sub.y, 6.0, 12.0, "free-supply", number)
        if point is None:
            return None
        return dict(x=round(point[0], 2), y=round(point[1], 2),
                    radius_nm=config.FREE_SUPPLY_RADIUS_NM)
    return {}


def raw_name(ship) -> str:
    from src.core import boat_radio
    return (str(getattr(ship, "name", "") or "-").strip() or "-")[:boat_radio.MAX_NAME]


def target_position(order, now: float):
    """An attack order's reported position, dead-reckoned to ``now``."""
    from src.core import tasking
    return tasking.dead_reckon(order["x"], order["y"], order["course"], order["speed_kn"],
                               now - order["issued_t"])


def _civilian(game, ship_id):
    return next((ship for ship in game.civilians if ship.id == ship_id), None)


def in_landing(game, sub, order) -> bool:
    return (not sub.sunk and math.hypot(sub.x - order["x"], sub.y - order["y"])
            <= order["radius_nm"] and sub.depth <= config.SWIMMER_DEPTH_M
            and sub.speed <= config.SWIMMER_SPEED_KN)


def at_supply(game, sub, order) -> bool:
    from src.sensors.platform import MAST_DEPTH_M
    return (not sub.sunk and math.hypot(sub.x - order["x"], sub.y - order["y"])
            <= order["radius_nm"] and sub.depth <= MAST_DEPTH_M + 1.0
            and sub.speed <= config.FREE_SUPPLY_KN)


def order_state(game, boat, order, now: float):
    """Progress of a free patrol's own order kinds: "done", "failed" or None."""
    sub = boat.sub
    if order["kind"] == "attack":
        ship = _civilian(game, order["target_id"])
        if ship is not None and ship.sunk:
            return "done"
        if ship is None or now >= order["deadline_t"]:
            return "failed"
        return None
    if order["kind"] in ("landing", "supply"):
        holding = (in_landing if order["kind"] == "landing" else at_supply)(game, sub, order)
        if not holding:
            order["since"] = None
        elif order["since"] is None:
            order["since"] = float(now)
        need = (config.FREE_LANDING_HOLD_S if order["kind"] == "landing"
                else config.FREE_SUPPLY_HOLD_S)
        if order["since"] is not None and now - order["since"] >= need:
            if order["kind"] == "supply":
                _resupply(game, boat)
            return "done"
    if now >= order["deadline_t"]:
        return "failed"
    return None


def hold_left(order, now: float) -> float | None:
    """Seconds still to hold for a landing or supply order, or None."""
    if order["kind"] not in ("landing", "supply"):
        return None
    need = (config.FREE_LANDING_HOLD_S if order["kind"] == "landing"
            else config.FREE_SUPPLY_HOLD_S)
    if order["since"] is None:
        return need
    return max(0.0, need - (now - order["since"]))


def _resupply(game, boat) -> None:
    sub = boat.sub
    if sub.weapon_battery is not None:
        sub.weapon_battery.replenish()
        sub.torpedoes_left = sub.weapon_battery.remaining_total
    endurance = sub.endurance
    if endurance is not None:
        endurance.battery_kwh = endurance.profile.battery_capacity_kwh
    boat.notice(game.sim_t, "radio", message("free.boat.resupplied"),
                stamp=game.world.format_time())


def order_closed(game, boat, order) -> None:
    """Book a closed order's points on a free patrol."""
    if not boat_side(game) or not active(game):
        return
    done, failed = config.FREE_ORDER_POINTS.get(order["kind"], (0, 0))
    points = done if order["state"] == "done" else failed
    order["points"] = int(points)
    _add_points(game, points)


def _add_points(game, points: int) -> None:
    state = game.free_roam
    state["points"] = max(-MAX_POINTS, min(MAX_POINTS, state["points"] + int(points)))


def merchant_sunk(game, ship) -> None:
    """The submarine sank a merchant: the ordered one counts with its order."""
    if not boat_side(game) or not active(game):
        return
    boat = getattr(game, "_opfor", None)
    ordered = boat is not None and any(
        order["target_id"] == ship.id for order in boat.radio.orders)
    if not ordered:
        _add_points(game, config.FREE_MERCHANT_SUNK)


def frigate_sunk(game) -> None:
    if boat_side(game) and active(game):
        _add_points(game, config.FREE_FRIGATE_SUNK)


def ai_targets(game, sub) -> list:
    """The ships the patrol boat may attack: its ordered merchant."""
    order = active_order(game)
    if order is None or order["kind"] != "attack" or game._opfor.sub is not sub:
        return []
    ship = _civilian(game, order["target_id"])
    return [] if ship is None or ship.sunk else [ship]


def active_order(game):
    boat = getattr(game, "_opfor", None)
    if boat is None or not boat_side(game):
        return None
    return boat.radio.active_order()


def ai_leg(game, sub):
    """The patrol boat's leg ``(course, speed, depth)`` for its open order, or None."""
    from src.core import boat_ai
    from src.sensors.platform import MAST_DEPTH_M
    order = active_order(game)
    if order is None:
        # No order: loiter slowly at loop-antenna depth to copy the next broadcast.
        return (boat_ai._course(game, sub, sub.course), config.BOAT_AI_PERISCOPE_KN,
                config.UBOOT_RADIO_VLF_DEPTH_M - 3.0)
    if order["kind"] in ("report", "silence", "recon"):
        return None
    deep = boat_ai._deep(game, sub)
    if order["kind"] == "attack":
        ship = _civilian(game, order["target_id"])
        if ship is None or ship.sunk:
            return None
        x, y = target_position(order, game.sim_t)
        if math.hypot(x - sub.x, y - sub.y) <= 4.0:
            return (boat_ai._course(game, sub, _bearing(sub.x, sub.y, x, y)),
                    config.BOAT_AI_PERISCOPE_KN, deep)
        px, py = boat_ai.lead(sub, x, y, order["course"], order["speed_kn"],
                              boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN))
        return (boat_ai._course(game, sub, _bearing(sub.x, sub.y, px, py)),
                boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN), deep)
    distance = math.hypot(order["x"] - sub.x, order["y"] - sub.y)
    heading = _bearing(sub.x, sub.y, order["x"], order["y"])
    if order["kind"] == "landing" and distance <= order["radius_nm"] * 0.5:
        return heading, 0.0, config.SWIMMER_DEPTH_M - 3.0
    if order["kind"] == "landing" and distance <= config.BOAT_AI_SWIMMER_APPROACH_NM:
        return heading, config.BOAT_AI_PERISCOPE_KN, config.SWIMMER_DEPTH_M - 3.0
    if order["kind"] == "supply" and distance <= order["radius_nm"] * 0.5:
        return heading, 0.0, MAST_DEPTH_M - 3.0
    course = boat_ai.detour(sub, heading, distance)
    return (boat_ai._course(game, sub, course), boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN),
            deep)


# --- the boat's order line -------------------------------------------------------------------

def boat_objective(game, boat):
    """The patrol boat's mission line: its open order and its points."""
    radio = boat.radio
    order = radio.active_order()
    points = game.free_roam["points"] if active(game) else 0
    if order is None:
        return message("free.objective.boat_idle", points=str(points))
    return message("free.objective.boat_order", order=order_text(game, boat, order),
                   points=str(points))


def order_text(game, boat, order) -> object:
    """One HQ order as text (bearing and range from the boat now)."""
    now = float(game.sim_t)
    left = max(0.0, order["deadline_t"] - now)
    params = dict(number=str(order["id"]), left=f"{int(left // 60)}:{int(left % 60):02d}")
    if order["x"] is not None:
        x, y = ((target_position(order, now)) if order["kind"] == "attack"
                else (order["x"], order["y"]))
        bx, by = boat_nav.position(boat)
        params.update(bearing=f"{_bearing(bx, by, x, y):03.0f}",
                      range=f"{math.hypot(x - bx, y - by):.1f}",
                      radius=f"{order['radius_nm']:.0f}")
    if order["kind"] == "attack":
        params.update(name=raw_text(order["name"]), course=f"{order['course']:03.0f}",
                      speed=f"{order['speed_kn']:.0f}")
    hold = hold_left(order, now)
    if hold is not None:
        params["hold"] = f"{int(hold // 60)}:{int(hold % 60):02d}"
    return message("uboot.radio.order_" + order["kind"], **params)


# --- frigate's objective line and the end ----------------------------------------------------

def frigate_objective(game):
    board = game.tasking
    done = sum(1 for task in board.tasks if task["state"] == "done")
    open_count = len(board.open_tasks())
    return message("free.objective.frigate", open=str(open_count), done=str(done),
                   score=str(int(game.score)))


def _hours(game) -> str:
    return f"{game.mission_time / 3600.0:.1f}"


def check(game) -> bool:
    """End a free patrol when own ship is lost; True when this module owns it."""
    if not active(game):
        return False
    if frigate_side(game):
        if game.damage.ship_sunk:
            game._end_mission(False, message("end.reason.free_frigate_lost", hours=_hours(game),
                                             score=str(int(game.score))))
        elif game.incident:
            game._end_mission(False, message("end.reason.free_incident", hours=_hours(game)))
        return True
    from src.core import boat_missions
    sub = boat_missions.target_sub(game)
    if game.damage.ship_sunk:
        frigate_sunk(game)
        game._end_mission(False, message("end.reason.free_boat_frigate", hours=_hours(game),
                                         points=str(game.free_roam["points"])))
    elif sub is None or sub.sunk or sub.state == "SINKING":
        game._end_mission(True, message("end.reason.free_boat_lost", hours=_hours(game),
                                        points=str(game.free_roam["points"])))
    return True
