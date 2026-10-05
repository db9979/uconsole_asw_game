"""Boat missions: scenarios whose objective belongs to the submarine.

``breakthrough``: reach a goal area beyond the frigate's start, seen from the
boat's start. ``recon``: sight the frigate through the periscope and get a
situation report off by radio while it is in sight. ``convoy_attack``: sink
``BOAT_CONVOY_SINK`` merchants of the convoy the frigate escorts (the convoy is
remembered in ``mission_units`` as ``convoy-<n>``, saved). ``strait``: pass a
strait the frigate holds, to a goal area beyond its gate, among merchants
passing through (``traffic-<n>``). ``swimmers``: stop in a zone off a coast
the frigate guards, at swimmer depth and speed, for ``SWIMMER_HOLD_S``
without a break (save ``swimmer_hold_s``). ``escort``: sink the supply ship
the frigate escorts on a zigzag (``supply-1``). The frigate wins by sinking
the boat or by holding out to the time limit.

The goal is a pure function of the scenario's frigate start, the boat's saved
start position and the world (``mission_geo``), so it needs no saved state;
mission adjudication may read the boat's true position like every other end
check. The frigate knows the area it guards (the strait's gate, a coast
section around the swimmers' zone), never the boat's goal inside it.
"""

from __future__ import annotations

import math
import random

from src.core import config, detrand, mission_geo
from src.core.i18n import message, raw_text
from src.sonar.platforms import OWNSHIP_TARGET_ID

# Scenarios 11 to 20 add the modes of ``src/core/mission_modes.py``.
MODES = ("breakthrough", "recon", "convoy_attack", "strait", "swimmers", "escort",
         "datum", "trail", "ras", "rescue", "duel", "homecoming", "pickup", "elint",
         "free_boat")
# Modes whose merchants the boat's torpedoes may take.
SHIP_MODES = ("convoy_attack", "escort", "ras")
# Scenarios 8 to 10: the boat slips past or attacks a guarding frigate.
GUARDED_MODES = ("strait", "swimmers", "escort", "pickup", "rescue", "duel")
# Missions where HQ has no intelligence on the boat: no start report, no
# datum task. The supply ship escort keeps HQ's reports like the convoy.
UNREPORTED_MODES = ("strait", "swimmers", "pickup", "elint", "free_boat")
# Missions where the boat slips past a guard and snaps a shot at it when it
# comes loud down its bearing (src/enemies/sub.py).
SNAP_MODES = ("strait", "swimmers", "pickup", "rescue", "duel")
# The coast section and swimmers' zone serve the agent pick-up too.
ZONE_MODES = ("swimmers", "pickup")


def mode(game):
    """One of ``MODES``, or None for a frigate mission."""
    if getattr(game, "custom_mission_definition", None) is not None:
        return None
    value = getattr(getattr(game, "mission", None), "win_mode", None)
    return value if value in MODES else None


def target_sub(game):
    """The boat the mission belongs to: the crewed one, else the first hostile."""
    boat = getattr(game, "_opfor", None)
    if boat is not None and boat.sub in game.subs:
        return boat.sub
    hostile = sorted((sub for sub in game.subs if sub.side == "hostile"),
                     key=lambda sub: sub.id)
    return hostile[0] if hostile else None


def _water(game, x, y) -> bool:
    size = float(game.world.size_nm)
    return (5.0 <= x <= size - 5.0 and 5.0 <= y <= size - 5.0
            and not game.world.on_land(x, y)
            and game.world.depth_m(x, y) >= config.BOAT_GOAL_MIN_DEPTH_M)


def _nominal(scenario_key):
    start = config.SCENARIOS.get(scenario_key, {}).get("ship_start")
    return None if start is None else (float(start[0]), float(start[1]))


def scenario_mode(scenario_key):
    """The boat mission a scenario plays, or None (before the game exists)."""
    spec = config.SCENARIOS.get(scenario_key, {})
    value = config.MISSION_TYPES.get(spec.get("mission_type"), {}).get("win")
    return value if value in MODES else None


def _gate_ends(gate) -> tuple:
    """The gate's two ends across the passage."""
    px, py = math.sin(math.radians(gate["axis"] + 90.0)), -math.cos(
        math.radians(gate["axis"] + 90.0))
    half = gate["half_nm"]
    return ((gate["x"] + half * px, gate["y"] + half * py),
            (gate["x"] - half * px, gate["y"] - half * py))


def _zone_of(world, scenario_key):
    """The swimmers' zone ``{x, y, radius_nm, seaward}``; the nominal start
    stands in on a world without a usable coast."""
    nominal = _nominal(scenario_key)
    found = mission_geo.swimmer_zone(world, nominal)
    if found is None:
        x, y = world.nearest_water(*nominal)
        found = dict(x=float(x), y=float(y), seaward=0.0)
    return dict(x=found["x"], y=found["y"], radius_nm=config.SWIMMER_ZONE_NM,
                seaward=found["seaward"])


def _guard_shift(seed) -> float:
    """How far along the coast the guarded section's centre lies off the zone."""
    return (detrand.u01(seed, "swimmer-guard", 0) * 2.0 - 1.0) * config.SWIMMER_GUARD_SHIFT_NM


def _guard_of(world, scenario_key, seed):
    """The coast section the frigate guards: a circle whose centre lies up to
    ``SWIMMER_GUARD_SHIFT_NM`` along the coast from the zone, off the coast."""
    zone = _zone_of(world, scenario_key)
    shift = _guard_shift(seed)
    along = math.radians(zone["seaward"] + 90.0)
    out = math.radians(zone["seaward"])
    x = zone["x"] + shift * math.sin(along) + 3.0 * math.sin(out)
    y = zone["y"] - shift * math.cos(along) - 3.0 * math.cos(out)
    x, y = world.nearest_water(x, y)
    return dict(kind="circle", x=float(x), y=float(y), radius_nm=config.SWIMMER_GUARD_NM,
                course=(zone["seaward"] + 90.0) % 360.0,
                # The end of the section the frigate starts from (+1 ahead
                # along ``course``, -1 astern), drawn from the seed.
                start=1.0 if detrand.u01(seed, "swimmer-guard-end", 0) < 0.5 else -1.0)


def escort_base_course(world, scenario_key) -> float:
    spec = config.SCENARIOS[scenario_key]
    return mission_geo.escort_course(world, _nominal(scenario_key),
                                     float(spec["ship_course"]))


def frigate_start(world, scenario_key, seed, short: bool = False):
    """``(x, y, course)`` of the frigate in scenarios 8 to 20, else None."""
    from src.core import mission_modes
    kind = scenario_mode(scenario_key)
    if kind == "strait":
        gate = mission_geo.strait(world, _nominal(scenario_key))
        return gate["x"], gate["y"], (gate["axis"] + 90.0) % 360.0
    if kind in ZONE_MODES:
        # At one end of its coast section, sweeping back along it.
        guard = _guard_of(world, scenario_key, seed)
        reach = guard["start"] * guard["radius_nm"] * config.SWIMMER_GUARD_START
        rad = math.radians(guard["course"])
        x, y = world.nearest_water(guard["x"] + reach * math.sin(rad),
                                   guard["y"] - reach * math.cos(rad))
        return float(x), float(y), (guard["course"] + (180.0 if guard["start"] > 0 else 0.0)) % 360.0
    if kind == "escort":
        course = escort_base_course(world, scenario_key)
        nx, ny = _nominal(scenario_key)
        side = math.radians(course + 90.0)
        return (nx + config.ESCORT_FRIGATE_ABEAM_NM * math.sin(side),
                ny - config.ESCORT_FRIGATE_ABEAM_NM * math.cos(side), course)
    return mission_modes.frigate_start(world, scenario_key, seed, short)


def gate(game):
    """The strait's gate ``{x, y, axis, half_nm, natural}`` or None."""
    if mode(game) != "strait":
        return None
    return mission_geo.strait(game.world, _nominal(game.scenario_key))


def zone(game):
    """The swimmers' (or agents') zone ``{x, y, radius_nm, seaward}`` or None."""
    if mode(game) not in ZONE_MODES:
        return None
    return _zone_of(game.world, game.scenario_key)


def guard_area(game):
    """What the frigate guards, as its orders give it (authored mission
    data): ``{kind: "gate", ends}`` or ``{kind: "circle", x, y, radius_nm}``."""
    from src.core import mission_modes
    kind = mode(game)
    if kind == "strait":
        return dict(kind="gate", ends=_gate_ends(gate(game)))
    if kind in ZONE_MODES:
        return _guard_of(game.world, game.scenario_key, game.seed)
    return mission_modes.guard_area(game, kind)


def exit_heading(gate_row, start_pos) -> float:
    """Away from the side of the gate the boat started on."""
    ahead, _across = mission_geo.along(start_pos, gate_row)
    return gate_row["axis"] if ahead < 0.0 else (gate_row["axis"] + 180.0) % 360.0


def goal(game):
    """The boat's goal area ``{x, y, radius_nm}`` or None: the breakthrough
    goal, the area beyond the strait or the swimmers' zone."""
    from src.core import mission_modes
    kind = mode(game)
    if kind == "swimmers":
        return zone(game)
    if kind in ("homecoming", "pickup"):
        return mission_modes.goal(game, kind)
    if kind == "strait":
        return _strait_goal(game)
    if kind != "breakthrough":
        return None
    sub = target_sub(game)
    start = config.SCENARIOS.get(game.scenario_key, {}).get("ship_start")
    if sub is None or start is None:
        return None
    key = (game.seed, game.scenario_key, sub.id, tuple(sub.start_pos))
    cached = getattr(game, "_boat_goal_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    sx, sy = sub.start_pos
    fx, fy = start
    bearing = math.degrees(math.atan2(fx - sx, -(fy - sy))) % 360.0
    point = None
    beyond = config.BOAT_GOAL_BEYOND_NM * distance_scale(game)
    for distance in (beyond, beyond * 1.5, beyond * 0.5):
        for delta in (0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0, 90.0, -90.0):
            rad = math.radians(bearing + delta)
            x = fx + distance * math.sin(rad)
            y = fy - distance * math.cos(rad)
            if _water(game, x, y):
                point = (x, y)
                break
        if point is not None:
            break
    if point is None:
        point = (fx, fy)
    result = dict(x=float(point[0]), y=float(point[1]),
                  radius_nm=config.BOAT_GOAL_RADIUS_NM)
    game._boat_goal_cache = (key, result)
    return result


def _strait_goal(game):
    sub = target_sub(game)
    row = gate(game)
    if sub is None or row is None:
        return None
    key = ("strait", game.seed, game.scenario_key, sub.id, tuple(sub.start_pos))
    cached = getattr(game, "_boat_goal_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    exit_nm = config.STRAIT_EXIT_NM * distance_scale(game)
    point = mission_geo.walk(game.world, row["x"], row["y"], exit_heading(row, sub.start_pos),
                             (exit_nm, exit_nm * 0.75, exit_nm * 1.25, exit_nm * 0.5))
    if point is None:
        point = (row["x"], row["y"])
    result = dict(x=float(point[0]), y=float(point[1]), radius_nm=config.BOAT_GOAL_RADIUS_NM)
    game._boat_goal_cache = (key, result)
    return result


def distance_scale(game) -> float:
    """Start distances of a boat mission: shorter in the short variant; a
    mission type may scale its full length too (``scale``)."""
    if not getattr(game, "short_mission", False):
        return float((game.mission.spec or {}).get("scale", 1.0))
    return float(game.mission.spec.get("short_scale", config.SHORT_DISTANCE_SCALE))


def setup(game) -> None:
    """Place a boat mission's own units once the world is populated."""
    from src.core import free_roam, mission_modes
    free_roam.setup(game)
    kind = mode(game)
    if kind in mission_modes.MODES:
        mission_modes.setup(game, kind)
    elif kind == "convoy_attack":
        spawn_convoy(game)
    elif kind == "strait":
        _setup_strait(game)
    elif kind == "swimmers":
        _setup_swimmers(game)
    elif kind == "escort":
        _setup_escort(game)


def _place_boat(game, x, y, course) -> None:
    sub = target_sub(game)
    if sub is None:
        return
    sub.x, sub.y = float(x), float(y)
    sub.start_pos = (sub.x, sub.y)
    sub.course = sub.target_course = float(course) % 360.0


def _setup_strait(game) -> None:
    """The boat before the gate on a side drawn from the seed, and merchants
    passing through the strait both ways."""
    from src.enemies.civilian import CivilianShip
    row = gate(game)
    first = 0.0 if detrand.u01(game.seed, "strait-side", 0) < 0.5 else 180.0
    entry = config.STRAIT_ENTRY_NM * distance_scale(game)
    for turn in (first, 180.0 - first):
        heading = (row["axis"] + turn) % 360.0
        point = mission_geo.walk(game.world, row["x"], row["y"], heading,
                                 (entry, entry * 0.75, entry * 1.25, entry * 0.5))
        if point is not None:
            _place_boat(game, point[0], point[1], heading + 180.0)
            break
    rng = random.Random(game.seed * 7907 + 211)
    count = config.STRAIT_TRAFFIC
    ux, uy = math.sin(math.radians(row["axis"])), -math.cos(math.radians(row["axis"]))
    for index in range(count):
        ahead = (index - (count - 1) / 2.0) * config.STRAIT_TRAFFIC_SPACING_NM
        x, y = game.world.nearest_water(row["x"] + ahead * ux, row["y"] + ahead * uy)
        ship = CivilianShip(x, y, rng=rng,
                            profile=game.runtime_catalog.pick_surface(rng, hostile=False),
                            side="neutral", doctrine="surface_transit",
                            runtime_catalog=game.runtime_catalog)
        ship.course = ship.target_course = (row["axis"] + (0.0 if index % 2 == 0 else 180.0)) % 360.0
        ship.target_speed = ship.speed
        ship.turn_left = game.mission.time_limit_s + 3600.0
        game.civilians.append(ship)
        game.mission_units[f"traffic-{index + 1}"] = int(ship.id)


def _setup_swimmers(game) -> None:
    """The boat out at sea, seaward of the zone."""
    row = zone(game)
    approach = config.SWIMMER_APPROACH_NM * distance_scale(game)
    point = mission_geo.walk(game.world, row["x"], row["y"], row["seaward"],
                             (approach, approach * 0.8, approach * 1.2, approach * 0.6,
                              approach * 0.4))
    if point is not None:
        _place_boat(game, point[0], point[1], row["seaward"] + 180.0)


def _setup_escort(game) -> None:
    """The supply ship at the nominal start on its base course, the boat on
    its bow."""
    from src.enemies.civilian import CivilianShip
    course = escort_base_course(game.world, game.scenario_key)
    x, y = game.world.nearest_water(*_nominal(game.scenario_key))
    rng = random.Random(game.seed * 7907 + 307)
    ship = CivilianShip(x, y, rng=rng, side="friendly", doctrine="surface_transit",
                        profile=game.runtime_catalog.surfaces[config.TASK_RAS_PROFILE],
                        runtime_catalog=game.runtime_catalog)
    ship.course = ship.target_course = course
    ship.speed = ship.target_speed = min(config.ESCORT_SPEED_KN, ship.speed_cap_kn)
    ship.turn_left = game.mission.time_limit_s + 3600.0
    game.civilians.append(ship)
    game.mission_units["supply-1"] = int(ship.id)
    _station_boat_ahead(game, course, (ship.x, ship.y))


def escort_origin(game):
    """Where the supply ship's base track starts (its start position)."""
    return game.world.nearest_water(*_nominal(game.scenario_key))


def supply(game):
    """The escorted supply ship or the replenishment tanker (sunk or not), or None."""
    if mode(game) not in ("escort", "ras"):
        return None
    return game.mission_entity("supply-1")


def update(game, dt: float) -> None:
    """The supply ship's zigzag, the swimmers' lock-out and the strait's
    traffic, every substep (and the counters of scenarios 11 to 20, the
    encounters of a free patrol)."""
    from src.core import free_roam, mission_modes
    free_roam.update(game, dt)
    kind = mode(game)
    if kind in mission_modes.MODES:
        mission_modes.update(game, kind, dt)
    elif kind == "escort":
        _zigzag(game)
    elif kind == "swimmers":
        _hold(game, dt)
    elif kind == "strait":
        _shuttle(game)


def _shuttle(game) -> None:
    """The strait stays busy: a merchant ``STRAIT_TRAFFIC_TURN_NM`` beyond
    the gate turns back through it (stateless, from its position)."""
    row = gate(game)
    for index in range(config.STRAIT_TRAFFIC):
        ship = game.mission_entity(f"traffic-{index + 1}")
        if ship is None or ship.sunk:
            continue
        ahead, _across = mission_geo.along((ship.x, ship.y), row)
        if abs(ahead) < config.STRAIT_TRAFFIC_TURN_NM:
            continue
        back = row["axis"] if ahead < 0.0 else (row["axis"] + 180.0) % 360.0
        if abs(config.angle_diff_deg(ship.target_course, back)) > 90.0:
            ship.target_course = back


def zigzag_course(game) -> float:
    """The supply ship's ordered course now: legs alternating either side of
    the base course, each ``ESCORT_ZIGZAG_DEG`` off (a stateless draw)."""
    base = escort_base_course(game.world, game.scenario_key)
    leg = int(math.floor(game.sim_t / config.ESCORT_ZIGZAG_LEG_S))
    low, high = config.ESCORT_ZIGZAG_DEG
    offset = low + (high - low) * detrand.u01(game.seed, "escort-zigzag", leg)
    return (base + (offset if leg % 2 else -offset)) % 360.0


def _zigzag(game) -> None:
    ship = supply(game)
    if ship is None or ship.sunk or ship._torpedo_evade_left > 0.0:
        return
    ship.target_course = zigzag_course(game)
    ship.target_speed = min(config.ESCORT_SPEED_KN, ship.speed_cap_kn)


def in_lockout(game, sub) -> bool:
    """The boat lies in the zone slow and shallow enough for the swimmers."""
    row = zone(game)
    return (row is not None and sub is not None and not sub.sunk
            and sub.state not in ("SINKING", "SUNK")
            and math.hypot(sub.x - row["x"], sub.y - row["y"]) <= row["radius_nm"]
            and sub.depth <= config.SWIMMER_DEPTH_M
            and sub.speed <= config.SWIMMER_SPEED_KN)


def _hold(game, dt: float) -> None:
    if in_lockout(game, target_sub(game)):
        game.swimmer_hold_s = min(config.SWIMMER_HOLD_S, game.swimmer_hold_s + dt)
    else:
        game.swimmer_hold_s = 0.0


def valid_hold(value) -> bool:
    return (type(value) is float and math.isfinite(value)
            and 0.0 <= value <= config.SWIMMER_HOLD_S)


def spawn_convoy(game) -> None:
    """The escorted convoy in a box about the frigate, on the frigate's course.

    A local stream keyed by the seed keeps every other draw unchanged."""
    import random

    from src.enemies.civilian import CivilianShip
    spec = config.SCENARIOS[game.scenario_key]
    course = float(spec["ship_course"])
    rng = random.Random(game.seed * 7907 + 101)
    spacing = config.BOAT_CONVOY_SPACING_NM
    offsets = ((spacing, -spacing), (spacing, spacing), (-spacing, -spacing),
               (-spacing, spacing))[:config.BOAT_CONVOY_SIZE]
    rad = math.radians(course)
    for index, (ahead, side) in enumerate(offsets, start=1):
        x = game.ship.x + ahead * math.sin(rad) + side * math.cos(rad)
        y = game.ship.y - ahead * math.cos(rad) + side * math.sin(rad)
        x, y = game.world.nearest_water(x, y)
        ship = CivilianShip(x, y, rng=rng,
                            profile=game.runtime_catalog.pick_surface(rng, hostile=False),
                            side="neutral", doctrine="surface_transit",
                            runtime_catalog=game.runtime_catalog)
        ship.course = ship.target_course = course
        ship.speed = ship.target_speed = min(config.BOAT_CONVOY_SPEED_KN, ship.speed_cap_kn)
        # Holds its course for the whole mission.
        ship.turn_left = game.mission.time_limit_s + 3600.0
        game.civilians.append(ship)
        game.mission_units[f"convoy-{index}"] = int(ship.id)
    _station_boat_ahead(game, course, (game.ship.x, game.ship.y))


def _station_boat_ahead(game, course: float, around, ahead_nm: float | None = None) -> None:
    """Put the mission boat on the convoy's bow, where it can wait for it: a
    convoy running away is faster than a dived boat, and the escort screens
    dead ahead. The side is a stateless draw keyed by the seed, so no
    stream shifts."""
    sub = target_sub(game)
    if sub is None:
        return
    draw = detrand.u01(game.seed, "convoy-boat-side", 0) * 2.0 - 1.0
    side = math.copysign(config.BOAT_CONVOY_BOAT_SIDE_NM
                         + abs(draw) * config.BOAT_CONVOY_BOAT_SIDE_SPREAD_NM, draw
                         ) * distance_scale(game)
    rad = math.radians(course)
    nominal = (config.BOAT_CONVOY_BOAT_AHEAD_NM if ahead_nm is None else ahead_nm
               ) * distance_scale(game)
    for ahead in (nominal, nominal * 0.75, nominal * 1.25):
        for offset in (side, -side, 0.0):
            x = around[0] + ahead * math.sin(rad) + offset * math.cos(rad)
            y = around[1] - ahead * math.cos(rad) + offset * math.sin(rad)
            if _water(game, x, y):
                sub.x, sub.y = float(x), float(y)
                sub.start_pos = (sub.x, sub.y)
                return


def convoy(game) -> list:
    """The convoy's merchants, in convoy order (sunk ones included); in the
    supply ship escort, the supply ship."""
    if mode(game) in ("escort", "ras"):
        ship = supply(game)
        return [] if ship is None else [ship]
    rows = []
    for index in range(1, config.BOAT_CONVOY_SIZE + 1):
        entity = game.mission_entity(f"convoy-{index}")
        if entity is not None:
            rows.append(entity)
    return rows


def convoy_sunk(game) -> int:
    return sum(1 for ship in convoy(game) if ship.sunk)


def distress_call(game, ship) -> dict:
    """A torpedoed merchant's distress call as the frigate's radio hears it:
    its rough bearing (nearest 10 degrees) and range (whole miles)."""
    dx, dy = ship.x - game.ship.x, ship.y - game.ship.y
    bearing = round(math.degrees(math.atan2(dx, -dy)) / 10.0) * 10 % 360
    return message("runtime.merchant_distress", bearing=f"{bearing:03d}",
                   range=f"{max(1, round(math.hypot(dx, dy)))}")


def attacker_held(game, attacker_id) -> bool:
    """The frigate's sonar picture heard the attacking boat within
    ``MERCHANT_BLAME_S``: only then could it have stopped the attack."""
    if attacker_id is None:
        return False
    contact = game.sonar.contacts.get(attacker_id)
    return (contact is not None
            and 0.0 <= game.sim_t - contact.last_seen <= config.MERCHANT_BLAME_S)


def merchant_struck(game, ship, attacker_id=None) -> None:
    """A submarine's torpedo hit a merchant: book the warhead, report it."""
    if ship is None or ship.sunk:
        return
    escort = mode(game) in ("escort", "ras") and ship is supply(game)
    ship.hit(config.ESCORT_WARHEAD if escort else config.BOAT_CONVOY_WARHEAD)
    game.sight_events.ship_hit(ship, game.sim_t)
    game._emit_sound("explosion", at=(ship.x, ship.y))
    game.feed.add(game.world.format_time(), "schaden",
                  message("runtime.supply_torpedoed") if escort
                  else message("runtime.merchant_torpedoed") if ship in convoy(game)
                  else distress_call(game, ship))
    if ship.sunk:
        game._report_breakup_noise(ship.x, ship.y, 0.0, ship.id)
        from src.core import free_roam
        free_roam.merchant_sunk(game, ship)
        if mode(game) is None and attacker_held(game, attacker_id):
            # A frigate mission: shipping lost to a boat the frigate held.
            game.score -= config.SCORE_MERCHANT_LOST


def check(game) -> bool:
    """End a boat mission when it is decided; True when this module owns it."""
    from src.core import mission_modes
    kind = mode(game)
    if kind is None:
        return False
    if kind == "free_boat":
        from src.core import free_roam
        return free_roam.check(game)
    sub = target_sub(game)
    if kind in mission_modes.MODES:
        return mission_modes.check(game, kind, sub,
                                   sub is None or sub.sunk or sub.state == "SINKING")
    if sub is None or sub.sunk or sub.state == "SINKING":
        game._end_mission(True, message("end.reason.targets_sunk"))
        return True
    if kind in ("breakthrough", "strait"):
        point = goal(game)
        if point is not None and math.hypot(sub.x - point["x"], sub.y - point["y"]) \
                <= point["radius_nm"]:
            game._end_mission(False, message("end.reason.boat_broke_through"
                                             if kind == "breakthrough"
                                             else "end.reason.boat_passed_strait"))
            return True
    if kind == "convoy_attack" and convoy_sunk(game) >= config.BOAT_CONVOY_SINK:
        game._end_mission(False, message("end.reason.convoy_lost",
                                         count=convoy_sunk(game)))
        return True
    if kind == "escort" and convoy_sunk(game) >= 1:
        game._end_mission(False, message("end.reason.supply_sunk"))
        return True
    if kind == "swimmers" and game.swimmer_hold_s >= config.SWIMMER_HOLD_S:
        game._end_mission(False, message("end.reason.swimmers_landed"))
        return True
    if game.mission_time >= game.mission.time_limit_s:
        game._end_mission(True, message({"breakthrough": "end.reason.boat_stopped",
                                         "recon": "end.reason.boat_report_denied",
                                         "convoy_attack": "end.reason.convoy_survived",
                                         "strait": "end.reason.strait_held",
                                         "swimmers": "end.reason.swimmers_denied",
                                         "escort": "end.reason.supply_protected"}[kind]))
    return True


def frigate_in_sight(boat) -> bool:
    return any(row["target_id"] == OWNSHIP_TARGET_ID for row in boat.orders.sightings)


def report_sent(game, boat) -> None:
    """A situation report went out: with the frigate in sight it wins recon,
    with the recording complete the listening post."""
    if mode(game) == "elint" and boat.sub is target_sub(game):
        from src.core import mission_modes
        mission_modes.elint_report(game)
        return
    if (mode(game) == "recon" and not game.game_over and game.mission_result is None
            and boat.sub is target_sub(game) and frigate_in_sight(boat)):
        game._end_mission(False, message("end.reason.boat_reported"))


def objective(game, boat):
    """The boat's own mission line (its orders from HQ, own truth only)."""
    from src.core import mission_modes
    kind = mode(game)
    if boat.sub.sunk:
        return message("uboot.objective_lost")
    from src.core import custom_boat
    custom = custom_boat.objective(game, boat)
    if custom is not None:
        return custom
    if kind == "free_boat":
        from src.core import free_roam
        return free_roam.boat_objective(game, boat)
    if kind in mission_modes.MODES:
        return mission_modes.boat_objective(game, boat, kind)
    if kind in ("breakthrough", "strait", "swimmers"):
        # Bearing and range from where the crew believes the boat is; the
        # swimmers in the lock (adjudicated on the true position) are a fact.
        from src.core import boat_nav
        point = goal(game)
        bx, by = boat_nav.position(boat)
        dx, dy = point["x"] - bx, point["y"] - by
        bearing = f"{math.degrees(math.atan2(dx, -dy)) % 360.0:03.0f}"
        if kind == "swimmers" and (in_lockout(game, boat.sub)
                                   or math.hypot(dx, dy) <= point["radius_nm"]):
            left = max(0.0, config.SWIMMER_HOLD_S - game.swimmer_hold_s)
            return message("uboot.objective.swimmers_hold" if in_lockout(game, boat.sub)
                           else "uboot.objective.swimmers_zone",
                           left=f"{int(left // 60)}:{int(left % 60):02d}",
                           depth=int(config.SWIMMER_DEPTH_M),
                           speed=f"{config.SWIMMER_SPEED_KN:.1f}")
        return message("uboot.objective." + kind, bearing=bearing,
                       range=f"{math.hypot(dx, dy):.1f}")
    if kind == "escort":
        ship = supply(game)
        return message("uboot.objective.escort",
                       name=raw_text(str(getattr(ship, "name", "") or "-")))
    if kind == "convoy_attack":
        return message("uboot.objective.convoy_attack", target=config.BOAT_CONVOY_SINK,
                       total=len(convoy(game)), sunk=convoy_sunk(game))
    if kind == "recon":
        return message("uboot.objective.recon_sighted" if frigate_in_sight(boat)
                       else "uboot.objective.recon")
    return message("uboot.objective")
