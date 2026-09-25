"""Phase 8: torpedo energy, turning, depth, wire, warhead, noise, wake."""

import copy
import json
import math
import random
from types import SimpleNamespace

import pytest

from src.core import config
from src.core.game import Game
from src.data.catalog import CATALOG
from src.enemies.sub import Sub
from src.physics import torpedo_dyn
from src.ship.ship import Ship
from src.weapons.torpedo import EnemyTorpedo, Torpedo

PROFILE = CATALOG.get_torpedo("frigate_torp")


def _run(torpedo, seconds, dt=0.5, **kwargs):
    for _ in range(int(seconds / dt)):
        torpedo._midcourse_timer = 0.0
        torpedo.update(dt, **kwargs)
        if torpedo.state != "RUN":
            break


def test_energy_store_sets_range_and_the_weapon_coasts_then_is_lost():
    torpedo = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=PROFILE,
                      guidance_x=100.0, guidance_y=0.0)
    _run(torpedo, 5000.0)
    assert torpedo.state == "SASE"
    assert torpedo.energy_s == 0.0
    assert torpedo.motor_fraction < torpedo_dyn.COAST_SINK_FRACTION
    assert torpedo.travel == pytest.approx(PROFILE.range_nm, rel=0.02)


def test_slower_running_stretches_the_store():
    assert torpedo_dyn.energy_rate(0.5) == pytest.approx(0.125)
    assert torpedo_dyn.coast_step(1.0, 10.0) < 0.25


def test_turn_rate_scales_with_speed():
    assert torpedo_dyn.turn_rate_deg_s(8.0, 0.5) == pytest.approx(4.0)
    fresh = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=PROFILE,
                    guidance_x=130.0, guidance_y=100.0, time_since_launch=0.0)
    cruising = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=PROFILE,
                       guidance_x=130.0, guidance_y=100.0)
    for torpedo in (fresh, cruising):
        torpedo._midcourse_timer = 0.0
        torpedo.update(1.0)
    assert fresh.course < cruising.course


def test_wire_breaks_on_ship_overspeed_or_spool_end():
    torpedo = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=PROFILE,
                      guidance_x=100.0, guidance_y=90.0)
    for _ in range(20):
        torpedo.wire_tension_update(0.5, 16.0, 0.5)
    assert torpedo.wire_state != "BROKEN"
    for _ in range(12):
        torpedo.wire_tension_update(0.5, 24.0, 0.0)
    assert torpedo.wire_state == "BROKEN"
    spool = Torpedo(100.0, 100.0, 0.0, 60.0, None, 0, profile=PROFILE,
                    guidance_x=100.0, guidance_y=90.0)
    spool.wire_ship_out_nm = torpedo_dyn.WIRE_SHIP_SPOOL_NM - 0.001
    spool.wire_tension_update(10.0, 12.0, 0.0)
    assert spool.wire_state == "BROKEN"


def test_proximity_fuze_damage_follows_shock_factor():
    close = torpedo_dyn.submarine_damage(20.0)
    far = torpedo_dyn.submarine_damage(150.0)
    assert close == 100.0 and 10.0 < far < 50.0
    sub = Sub(100.0, 100.0, 60.0, 0.0, "aip_modern", random.Random(1))
    sub.hit(far)
    assert sub.damage == pytest.approx(far) and sub.state == "EVADE"


def test_enemy_torpedo_rises_to_keel_depth_when_homing():
    ship = Ship(100.0, 100.0)
    torpedo = EnemyTorpedo(100.0, 101.0, 0.0, 40.0, 1)
    for _ in range(60):
        torpedo.update(0.5, ship)
        if torpedo.state != "RUN":
            break
    assert torpedo.target_depth < 10.0 and torpedo.depth < 40.0


def test_enemy_torpedo_follows_the_wake():
    ship = Ship(100.0, 100.0, course_deg=90.0, speed_kn=20.0)
    ship.target_speed = 20.0
    for _ in range(120):
        ship.update(1.0)
    tail = ship.wake[0]
    torpedo = EnemyTorpedo(tail[0], tail[1] + 0.02, 180.0, 10.0, 1,
                           guidance_x=tail[0], guidance_y=tail[1] + 10.0)
    start = torpedo.course
    for _ in range(20):
        torpedo.update(0.5, ship)
    assert abs(config.angle_diff_deg(torpedo.course, 90.0)) < abs(
        config.angle_diff_deg(start, 90.0))


def test_lookout_sees_a_shallow_torpedo_wake_by_day():
    game = Game(seed=8801, start_menu=False, audio_enabled=False)
    game.world.hour = 12.0
    game.world.sea_state = 1
    game.world.weather_shift_timer = 0.0
    game.world.refresh_weather()
    game.world.land_blocks_line = lambda *args: False
    torpedo = EnemyTorpedo(game.ship.x + 1.0, game.ship.y, 270.0, 8.0, 1)
    game.enemy_torpedoes = [torpedo]
    game._update_lookout_picture()
    # The wake is sighted; the torpedo domain follows only on recognition.
    assert any(track.kind in ("TORP", "UNKNOWN") and track.source == "LOOKOUT"
               for track in game.air_picture._tracks.values())


def test_torpedo_physics_state_round_trips_and_is_validated():
    game = Game(seed=8802, start_menu=False, audio_enabled=False)
    weapon_key = game.player_torpedo_battery.fire()
    weapon = next(row for row in game._ownship_loadout["weapons"]
                  if row["key"] == weapon_key)
    profile = game.runtime_catalog.torpedoes[weapon["runtime_profile_key"]]
    game.torpedo_count = game.player_torpedo_battery.remaining_total
    torpedo = Torpedo(game.ship.x, game.ship.y, 0.0, 60.0, None, 1, profile=profile,
                      guidance_x=game.ship.x, guidance_y=game.ship.y - 5.0,
                      kill_dist_nm=game.difficulty["kill_dist_nm"],
                      kill_depth_m=game.difficulty["kill_depth_m"])
    game.torpedo_seq = 1
    torpedo.energy_s, torpedo.depth_rate = 100.0, 3.0
    torpedo.wire_ship_out_nm, torpedo.wire_stress_s = 1.5, 2.0
    game.torpedoes = [torpedo]
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    twin = restored.torpedoes[0]
    assert (twin.energy_s, twin.depth_rate, twin.wire_ship_out_nm,
            twin.wire_stress_s) == (100.0, 3.0, 1.5, 2.0)
    broken = copy.deepcopy(state)
    broken["torpedoes_in_flight"][0]["motor_fraction"] = 2.0
    assert not restored._load_save_data(broken)
