#!/usr/bin/env python3
"""Gameplay calibration harness for the physics upgrade.

``--record`` measures observable gameplay quantities (equilibrium speeds,
acceleration and turn behaviour, sensor detection ranges, weapon timings,
damage progression) through the *public runtime behaviour* of the current
code and writes them to ``tests/calibration/golden.json``.  ``--check``
re-measures and compares against that file with per-metric tolerances.

The golden file was recorded once against the U-Jagd 1.0.0 kinematic models
before any physics replacement.  Later physics phases must reproduce these
values within tolerance; an intentional deviation is listed with its reason in
``tests/calibration/deviations.json`` rather than by re-recording.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

GOLDEN_PATH = os.path.join(ROOT, "tests", "calibration", "golden.json")
DEVIATIONS_PATH = os.path.join(ROOT, "tests", "calibration", "deviations.json")

# Tolerance classes (relative): equilibrium values, transients, range grids.
TOL = {"equilibrium": 0.02, "transient": 0.10, "range": 0.10,
       "statistic": 0.20}


def _metric(value: float, kind: str) -> dict:
    return {"value": round(float(value), 6), "kind": kind}


# --------------------------------------------------------------------------
# Own ship


def _ship_run(order: str, seconds: float, *, turn_deg: float = 0.0,
              start_speed: float = 0.0, dt: float = 0.05):
    from src.core import config
    from src.ship.ship import Ship

    ship = Ship(100.0, 100.0, 0.0, speed_kn=start_speed)
    index = next(i for i, item in enumerate(config.TELEGRAPH_ORDERS)
                 if item[0] == order)
    ship.order_idx = index
    ship.target_speed = config.TELEGRAPH_ORDERS[index][1]
    ship.target_course = turn_deg % 360.0
    for step in range(int(round(seconds / dt))):
        ship.update(dt)
        yield (step + 1) * dt, ship


def measure_ship() -> dict:
    from src.core import config

    out = {}
    for name, speed in config.TELEGRAPH_ORDERS:
        final = None
        for _t, ship in _ship_run(name, 900.0):
            final = ship
        out[f"ship.speed_eq.{name}"] = _metric(final.speed, "equilibrium")
        out[f"ship.rpm_eq.{name}"] = _metric(final.rpm(), "equilibrium")
        out[f"ship.fuel_kg_h.{name}"] = _metric(final.fuel_burn_kg_h(),
                                                "equilibrium")
    # Time to 90 % of FULL from rest.
    full = dict(config.TELEGRAPH_ORDERS)["FULL"]
    t90 = None
    for t, ship in _ship_run("FULL", 900.0):
        if ship.speed >= 0.9 * full:
            t90 = t
            break
    out["ship.t90_full_s"] = _metric(t90, "transient")
    # Coast-down from FULL to 10 % after STOP.
    t10 = None
    for t, ship in _ship_run("STOP", 1800.0, start_speed=full):
        if ship.speed <= 0.1 * full:
            t10 = t
            break
    out["ship.t10_stop_from_full_s"] = _metric(t10, "transient")
    # Steady turn: yaw rate and tactical diameter with a continuous
    # 90-degree lead on the ordered course.
    for name in ("HALF", "FULL"):
        speed = dict(config.TELEGRAPH_ORDERS)[name]
        xs, prev_course, turned, yaw = [], 0.0, 0.0, 0.0
        for _t, ship in _ship_run(name, 1200.0, start_speed=speed):
            ship.target_course = (ship.course + 90.0) % 360.0
            turned += (ship.course - prev_course + 540.0) % 360.0 - 180.0
            prev_course = ship.course
            xs.append(ship.x)
            yaw = ship.yaw_rate
            if turned >= 360.0:
                break
        out[f"ship.yaw_steady_deg_s.{name}"] = _metric(yaw, "equilibrium")
        out[f"ship.tactical_diameter_nm.{name}"] = _metric(
            max(xs) - min(xs), "transient")
    # Cavitation onset (smallest steady speed that cavitates).
    from src.ship.ship import Ship
    onset = None
    for tenth in range(0, 300):
        ship = Ship(0.0, 0.0, speed_kn=tenth / 10.0)
        if ship.cavitating:
            onset = tenth / 10.0
            break
    out["ship.cavitation_onset_kn"] = _metric(onset, "equilibrium")
    return out


# --------------------------------------------------------------------------
# Sonar


def _game(seed: int = 4242):
    from src.core.game import Game

    return Game(seed=seed, start_menu=False)


def _open_water_geometry(game, depth_needed=400.0):
    """Deterministically find a deep-water observer spot with open bearings."""
    world = game.world
    size = world.size_nm
    for index in range(400):
        x = size * (0.2 + 0.6 * ((index * 0.6180339887) % 1.0))
        y = size * (0.2 + 0.6 * ((index * 0.4142135623) % 1.0))
        ok = True
        for bearing in range(0, 360, 30):
            for dist in (0.0, 10.0, 20.0, 35.0):
                px = x + dist * math.sin(math.radians(bearing))
                py = y - dist * math.cos(math.radians(bearing))
                if (not 0 <= px <= size or not 0 <= py <= size
                        or world.on_land(px, py)
                        or world.depth_m(px, py) < depth_needed):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return x, y
    raise RuntimeError("no open deep-water calibration spot")


def _detection_range(game, target, mode: str, bearings=(0, 90, 180, 270),
                     max_nm: float = 80.0) -> float:
    sonar = game.sonar
    ship = game.ship
    results = []
    for bearing in bearings:
        def excess(dist):
            target.x = ship.x + dist * math.sin(math.radians(bearing))
            target.y = ship.y - dist * math.cos(math.radians(bearing))
            reach = sonar._passive_range_nm(
                target, dist, ship, game.world, 1.0, mode,
                target.bearing_from_frigate(ship), True)
            return reach - dist
        low, high = 0.05, max_nm
        if excess(low) <= 0.0:
            results.append(0.0)
            continue
        if excess(high) > 0.0:
            results.append(high)
            continue
        for _ in range(40):
            mid = 0.5 * (low + high)
            if excess(mid) > 0.0:
                low = mid
            else:
                high = mid
        results.append(0.5 * (low + high))
    return statistics.median(results)


def _set_sea(world, sea_state: int) -> None:
    """Pin the weather at ``sea_state`` with no transition blend."""
    world.sea_state = sea_state
    world.weather_shift_timer = 0.0
    world.refresh_weather()


def measure_sonar() -> dict:
    out = {}
    game = _game()
    ship = game.ship
    x, y = _open_water_geometry(game)
    ship.x, ship.y, ship.course = x, y, 45.0
    from src.core import config
    from src.sonar.sonar import TowState
    game.sonar.tow_state = TowState.STREAMED
    game.sonar.tow_payout = 1.0
    game.sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    game.sonar.towed_depth_m = 150.0
    # The golden reference boat, not whichever boat the mission drew.
    target = _reference_sub(game)
    target.speed = min(target.stype.speed_kn, 6.0)
    for sea in (1, 4):
        _set_sea(game.world, sea)
        for own_speed in (6.0, 12.0, 18.0, 25.0):
            ship.speed = ship.target_speed = own_speed
            for depth in (30.0, 150.0):
                target.depth = depth
                for mode in ("BOW", "TOWED"):
                    if mode == "TOWED" and own_speed > 12.0:
                        continue
                    key = (f"sonar.passive_nm.{mode}.sea{sea}."
                           f"own{int(own_speed)}.d{int(depth)}")
                    out[key] = _metric(_detection_range(game, target, mode),
                                       "range")
    # Active detection range (signal excess zero) for a target above and
    # below the layer, broadside-ish geometry fixed by the target course.
    _set_sea(game.world, 1)
    for depth in (30.0, 250.0):
        target.depth = depth

        def excess(dist):
            target.x, target.y = ship.x + dist, ship.y
            return (game.sonar._active_range_nm(target, game.world, 1.0, "BOW",
                                                ship) - dist)
        low, high = 0.05, 60.0
        for _ in range(40):
            mid = 0.5 * (low + high)
            if excess(mid) > 0.0:
                low = mid
            else:
                high = mid
        out[f"sonar.active_nm.BOW.d{int(depth)}"] = _metric(0.5 * (low + high),
                                                           "range")
    from src.sonar.sonar import bearing_error_deg
    for mode in ("BOW", "TOWED"):
        for speed in (6.0, 12.0):
            out[f"sonar.bearing_err_deg.{mode}.own{int(speed)}.q05"] = _metric(
                bearing_error_deg(mode, speed, 0.5), "equilibrium")
    return out


# --------------------------------------------------------------------------
# Radar / lookout


def measure_radar() -> dict:
    out = {}
    game = _game()
    real_world = game.world
    for sea, rain in ((1, 0.0), (5, 0.0), (6, 0.0), (1, 1.0)):
        stub = types.SimpleNamespace(
            sea_state=sea, effective_sea_state=float(sea),
            rain_intensity=rain, world=real_world)
        game.world = stub
        try:
            for domain in ("surface", "air"):
                out[f"radar.range_nm.{domain}.sea{sea}.rain{rain:g}"] = _metric(
                    game.radar_effective_range(domain), "range")
        finally:
            game.world = real_world
    from src.core import config
    out["radar.horizon_nm.surface_target"] = _metric(config.radar_horizon_nm(
        config.RADAR_ANTENNA_HEIGHT_M, config.RADAR_SURFACE_TARGET_HEIGHT_M),
        "equilibrium")
    # Lookout detection range, by kind, clear day, sea state 1.
    ship = game.ship
    x, y = _open_water_geometry(game, depth_needed=20.0)
    ship.x, ship.y = x, y
    _set_sea(real_world, 1)
    real_world.hour = 12.0
    for namespace, kind, base in (
            ("surface", "SURFACE", config.LOOKOUT_SURFACE_RANGE_NM),
            ("sub", "SUB", config.LOOKOUT_SUB_RANGE_NM),
            ("flight", "FLG", config.LOOKOUT_AIR_RANGE_NM)):
        low, high = 0.05, 60.0
        for step in range(30):
            mid = 0.5 * (low + high)
            actor = types.SimpleNamespace(x=x + mid, y=y, id=900000 + step,
                                          seq=900000 + step, depth=0.0,
                                          altitude_m=100.0)
            before = len(game.air_picture._tracks)
            game.sim_t += 10.0
            try:
                game._lookout_observe(actor, namespace, kind, 12345 + step,
                                      altitude_m=100.0 if kind == "FLG" else None)
            except TypeError:   # 1.0.0 signature (golden recording)
                game._lookout_observe(actor, namespace, kind, base, 12345 + step)
            seen = len(game.air_picture._tracks) > before
            if seen:
                low = mid
            else:
                high = mid
        out[f"lookout.range_nm.{namespace}.day.sea1"] = _metric(
            0.5 * (low + high), "range")
    return out


# --------------------------------------------------------------------------
# Torpedo


def measure_torpedo() -> dict:
    from src.core import config
    from src.data.catalog import CATALOG
    from src.weapons.torpedo import Torpedo

    out = {}
    profile = CATALOG.get_torpedo("frigate_torp")
    torp = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=profile,
                   time_since_launch=0.0, guidance_x=100.0, guidance_y=0.0)
    dt = 0.05
    t = 0.0
    t_cruise = None
    while torp.state == "RUN" and t < 7200.0:
        torp._midcourse_timer = 0.0
        torp.update(dt)
        t += dt
        if t_cruise is None and torp.time_since_launch >= config.TORP_SPOOLUP_S:
            t_cruise = t
    out["torpedo.run_time_s.frigate_torp"] = _metric(t, "equilibrium")
    out["torpedo.travel_nm.frigate_torp"] = _metric(torp.travel, "equilibrium")
    out["torpedo.depth_after_run_m"] = _metric(torp.depth, "equilibrium")
    # Turn rate on the wire toward a datum 90 degrees off the bow.
    torp = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=profile,
                   guidance_x=130.0, guidance_y=100.0)
    torp.update(dt)
    start = torp.course
    for _ in range(20):
        torp._midcourse_timer = 0.0
        torp.update(dt)
    out["torpedo.wire_turn_deg_s"] = _metric(
        ((torp.course - start + 540.0) % 360.0 - 180.0) / (20 * dt),
        "transient")
    # Depth change rate.
    torp = Torpedo(100.0, 100.0, 0.0, 200.0, None, 0, profile=profile,
                   guidance_x=100.0, guidance_y=0.0)
    for _ in range(100):
        torp._midcourse_timer = 0.0
        torp.update(dt)
    out["torpedo.depth_after_5s_m"] = _metric(torp.depth, "transient")
    return out


# --------------------------------------------------------------------------
# Submarine


# Pose of the boat the default mission drew for the golden record.
REFERENCE_SUB_COURSE = 140.494967523381
REFERENCE_SUB_SENSOR_SEED = 1378635661


def _reference_sub(game):
    """The reference submarine of the golden record, built from the catalog.

    It used to be whatever the default mission drew; since the patrol always
    brings its old diesel (1.3), the AIP boat is built here directly, with
    the same profile, difficulty and defaults the mission would give it, and
    the course and sensor seed the drawn boat had (the active ranges depend
    on its aspect).
    """
    import random

    from src.enemies.sub import Sub

    catalog = game.runtime_catalog
    key = "aip_modern"
    sub = Sub(game.ship.x + 20.0, game.ship.y, depth_m=60.0,
              course_deg=REFERENCE_SUB_COURSE,
               stype_key=key, rng=random.Random(4242),
               quiet_mult=game.difficulty["quiet_mult"],
               attack_mult=game.difficulty["enemy_attack_mult"],
               attack_cooldown_s=game.difficulty["enemy_cooldown_s"],
               solution_threshold=game.difficulty["enemy_solution_threshold"],
               profile=catalog.subs[key],
               decoy_profile=catalog.decoys[catalog.runtime_bindings["submarine_decoy"]],
               enemy_torpedo_profile=catalog.torpedoes[
                   catalog.runtime_bindings["enemy_torpedo"]],
               side="hostile", runtime_catalog=catalog, asw_rng=game.rng_asw)
    sub.sensor_seed = REFERENCE_SUB_SENSOR_SEED
    return sub


def measure_sub() -> dict:
    out = {}
    game = _game()
    sub = _reference_sub(game)
    key = sub.stype.key
    out[f"sub.max_speed_kn.{key}"] = _metric(sub.stype.speed_kn, "equilibrium")
    out[f"sub.quiet.{key}.patrol"] = _metric(sub.quiet_factor(), "equilibrium")
    return out


# --------------------------------------------------------------------------
# Damage


def measure_damage() -> dict:
    from src.core import config
    from src.ship.damage import DamageModel

    out = {}
    totals_600, fires = [], []
    for seed in range(20):
        model = DamageModel(random.Random(1000 + seed))
        model.torpedo_hit("center")
        for _ in range(int(600 / 0.25)):
            model.update(0.25)
        totals_600.append(model.total)
        fires.append(sum(c.fire for c in model.compartments.values()))
    out["damage.flood_total_600s_no_repair.mean"] = _metric(
        statistics.mean(totals_600), "statistic")
    totals_two = []
    for seed in range(20):
        model = DamageModel(random.Random(2000 + seed))
        model.torpedo_hit("center")
        model.torpedo_hit("port")
        for _ in range(1800):
            model.update(1.0)
        totals_two.append(model.total)
    out["damage.flood_total_1800s_two_hits.mean"] = _metric(
        statistics.mean(totals_two), "statistic")
    out["damage.sink_total"] = _metric(config.DMG_SHIP_SINK_TOTAL,
                                       "equilibrium")
    return out


# --------------------------------------------------------------------------
# Air defence (added with phase 11; golden values measured on the 1.0.0
# tree with this same probe)


def _air_game(seed):
    from src.core import config
    from src.core.game import Game
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.world.land_blocks_line = lambda *args: False
    game.subs, game.warships, game.civilians, game.raiders = [], [], [], []
    game.flights.flights = []
    game.mission.asm_count = 0
    game.ship.speed = game.ship.target_speed = 0.0
    game.ship.order_idx = next(i for i, item in enumerate(config.TELEGRAPH_ORDERS)
                               if item[1] == 0.0)
    return game


def _air_run(seed, *, ciws, chaff_at=None, distance=30.0, max_s=400.0, dt=0.1):
    from src.air.asm import ASM

    game = _air_game(seed)
    game.ciws_authorized = ciws
    asm = ASM(game.ship.x + distance, game.ship.y, 270.0, 1, game.rng_asm,
              game._air_defense_loadout["asm"])
    asm.jammer = False
    game.asms = [asm]
    elapsed, chaffed = 0.0, False
    while elapsed < max_s:
        if (chaff_at is not None and not chaffed
                and math.hypot(asm.x - game.ship.x, asm.y - game.ship.y) <= chaff_at):
            tracks = game.asm_tracks()
            if tracks:
                game.launch_chaff_at(tracks[0])
                chaffed = True
        game._update_sim(dt)
        elapsed += dt
        if asm.state in ("TREFFER", "ABGEFANGEN", "VERLOREN"):
            break
    return asm.state, elapsed


def measure_air() -> dict:
    out = {}
    _state, elapsed = _air_run(1, ciws=False)
    out["air.asm.time_to_impact_s.30nm"] = _metric(elapsed, "transient")
    samples = 40
    leaks = sum(_air_run(100 + seed, ciws=True)[0] == "TREFFER"
                for seed in range(samples))
    out["air.ciws.leak_fraction"] = _metric(leaks / samples, "statistic")
    leaks = sum(_air_run(300 + seed, ciws=False, chaff_at=7.0)[0] == "TREFFER"
                for seed in range(samples))
    out["air.chaff.leak_fraction"] = _metric(leaks / samples, "statistic")
    return out


SECTIONS = {
    "ship": measure_ship,
    "sonar": measure_sonar,
    "radar": measure_radar,
    "torpedo": measure_torpedo,
    "sub": measure_sub,
    "damage": measure_damage,
    "air": measure_air,
}


def measure_all(sections=None) -> dict:
    metrics = {}
    for name, function in SECTIONS.items():
        if sections is None or name in sections:
            metrics.update(function())
    return dict(sorted(metrics.items()))


def section_of(key: str) -> str:
    """The ``SECTIONS`` name that measures the metric ``key``."""
    prefix = key.split(".", 1)[0]
    return "radar" if prefix == "lookout" else prefix


def golden_for_sections(golden: dict, sections) -> dict:
    """``golden`` reduced to the metrics measured by ``sections``."""
    wanted = set(sections)
    return {"metrics": {key: value for key, value in golden["metrics"].items()
                        if section_of(key) in wanted}}


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def compare(measured: dict, golden: dict, deviations: dict) -> list[str]:
    problems = []
    for key, entry in golden["metrics"].items():
        if key in deviations:
            expected = deviations[key].get("value")
            if expected is None:
                continue
            tolerance = deviations[key].get("tolerance", TOL[entry["kind"]])
        else:
            expected = entry["value"]
            tolerance = TOL[entry["kind"]]
        if key not in measured:
            problems.append(f"{key}: not measured")
            continue
        value = measured[key]["value"]
        # Relative tolerance with a small absolute floor for zero-valued
        # references (e.g. speed at STOP).
        if abs(value - expected) > max(tolerance * abs(expected), 0.02):
            problems.append(f"{key}: {value:.4f} vs golden {expected:.4f} "
                            f"(tol {tolerance:.0%})")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--section", action="append", choices=sorted(SECTIONS))
    args = parser.parse_args(argv)
    measured = measure_all(args.section)
    if args.record:
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
        document = {"recorded_from_commit": commit,
                    "note": "Kinematic U-Jagd 1.0.0 reference behaviour.",
                    "metrics": measured}
        with open(GOLDEN_PATH, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=1, sort_keys=True,
                      allow_nan=False)
            handle.write("\n")
        print(f"recorded {len(measured)} metrics -> {GOLDEN_PATH}")
        return 0
    golden = load_json(GOLDEN_PATH, None)
    if golden is None:
        print("no golden file; run --record first", file=sys.stderr)
        return 2
    if args.section:
        golden = golden_for_sections(golden, args.section)
    problems = compare(measured, golden, load_json(DEVIATIONS_PATH, {}))
    for line in problems:
        print(line)
    print(f"{len(golden['metrics']) - len(problems)}/{len(golden['metrics'])} "
          "calibration metrics within tolerance")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
