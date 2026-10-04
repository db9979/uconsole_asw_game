"""Phase 12: missile flight physics, chaff clouds, CIWS, raiders, helo, buoys."""

import copy
import json
import math
import random
from types import SimpleNamespace

import pytest

from src.air import chaff
from src.air.asm import ASM
from src.air.helicopter import (DECK_PITCH_LIMIT_DEG, HOVER_FUEL_FACTOR,
                                Helicopter, deck_within_limits)
from src.air.sonobuoy import Sonobuoy
from src.core import config
from src.core.game import Game
from src.physics import missile
from src.weapons import ciws


def _ocean(**extra):
    return SimpleNamespace(size_nm=500.0, land_blocks_line=lambda *args: False,
                           **extra)


def test_launched_missile_boosts_to_cruise_and_settles_to_sea_skim_height():
    ship = SimpleNamespace(x=100.0, y=60.0)
    asm = ASM(100.0, 100.0, 0.0, 1, random.Random(1), launch_speed_kn=0.0,
              altitude_m=10.0, datum=(100.0, 60.0))
    boost = missile.boost_time_s(0.0, asm.cruise_kn)
    asm.update(boost / 2, ship, _ocean())
    assert 0.0 < asm.speed_kn < asm.cruise_kn and asm.boosting
    asm.update(boost, ship, _ocean())
    assert asm.speed_kn == asm.cruise_kn and not asm.boosting
    for _ in range(30):
        asm.update(1.0, ship, _ocean())
    assert asm.altitude_m == pytest.approx(missile.CRUISE_ALTITUDE_M)
    while asm.distance_nm(ship) > missile.TERMINAL_RANGE_NM - 1.0:
        asm.update(1.0, ship, _ocean())
    assert asm.altitude_m == pytest.approx(missile.TERMINAL_ALTITUDE_M)


def test_seeker_needs_field_of_view_and_lock_time_then_flies_pn_within_g_limit():
    ship = SimpleNamespace(x=110.0, y=100.0)
    # Heading north with the ship due east: outside the 30 deg cone.
    asm = ASM(100.0, 100.0, 0.0, 1, random.Random(1), datum=(100.0, 50.0))
    asm.update(1.0, ship, _ocean())
    assert not asm.locked and asm.lock_s == 0.0
    asm = ASM(100.0, 100.0, 80.0, 2, random.Random(1), datum=(110.0, 100.0))
    asm.update(missile.SEEKER_LOCK_S * 0.5, ship, _ocean())
    assert not asm.locked
    asm.update(missile.SEEKER_LOCK_S, ship, _ocean())
    assert asm.locked
    limit = missile.max_turn_rate_deg_s(asm.speed_kn)
    for _ in range(40):
        before = asm.course
        asm.update(0.1, ship, _ocean())
        assert abs(config.angle_diff_deg(asm.course, before)) <= limit * 0.1 + 1e-6


def test_proportional_navigation_hits_a_crossing_ship():
    class Mover:
        def __init__(self):
            self.x, self.y = 115.0, 100.0

        def step(self, dt):
            self.y -= config.kn_to_nm_per_s(28.0) * dt   # northbound, crossing

    ship = Mover()
    asm = ASM(100.0, 100.0, 90.0, 3, random.Random(1), datum=(115.0, 100.0))
    for _ in range(2000):
        asm.update(0.1, ship, _ocean())
        ship.step(0.1)
        if asm.state != "LAUF":
            break
    assert asm.state == "TREFFER"


def _fly_west(asm, dt):
    """Advance a test missile on its 270 deg course so radar sees it move."""
    asm.x -= config.kn_to_nm_per_s(asm.speed_kn) * dt


def test_sea_skimmer_is_below_the_radar_horizon_until_close(monkeypatch):
    game = Game(seed=1201, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M,
                                      missile.CRUISE_ALTITUDE_M)
    far = ASM(game.ship.x + horizon + 3.0, game.ship.y, 270.0, 5, game.rng_asm)
    far.jammer = True   # not even the jammer is heard over the horizon
    game.asms = [far]
    for _ in range(6):
        game.sim_t += 4.0
        game._update_air_picture(full_scan=True)
    assert not game.asm_tracks()
    near = ASM(game.ship.x + horizon - 3.0, game.ship.y, 270.0, 6, game.rng_asm)
    near.jammer = False
    game.asms = [near]
    for _ in range(6):
        game.sim_t += 4.0
        _fly_west(near, 4.0)
        game._update_air_picture(full_scan=True)
    # The ASM cue rests on measured speed and altitude, so it needs plots.
    assert game.asm_tracks()


def test_chaff_cloud_blooms_drifts_downwind_and_expires():
    cloud = chaff.ChaffCloud(1, 100.0, 100.0)
    assert cloud.bloom() == 0.0
    cloud.update(chaff.BLOOM_S, wind_from_deg=270.0, wind_speed_kn=20.0)
    assert cloud.bloom() == pytest.approx(1 - math.exp(-1), rel=1e-6)
    assert cloud.x > 100.0 and cloud.y == pytest.approx(100.0)   # blown east
    cloud.update(chaff.LIFE_S, wind_from_deg=270.0, wind_speed_kn=20.0)
    assert not cloud.active
    assert chaff.seduction_probability(.4, 0.0) == 0.0
    assert chaff.seduction_probability(.4, 60.0) == pytest.approx(.4, abs=1e-6)
    assert chaff.seduction_probability(.4, 1.0) < .4


def test_seduced_missile_steers_to_the_cloud():
    ship = SimpleNamespace(x=100.0, y=100.0)
    cloud = chaff.ChaffCloud(1, 100.4, 99.6)
    asm = ASM(104.0, 100.0, 270.0, 7, random.Random(1))
    asm.state, asm.chaff_left, asm.broken, asm.chaff_cloud = "CHAFF", 4.0, True, 1
    asm.update(2.0, ship, _ocean(), chaff_target=cloud)
    bearing = math.degrees(math.atan2(cloud.x - asm.x, -(cloud.y - asm.y))) % 360
    assert abs(config.angle_diff_deg(bearing, asm.course)) < 10.0


def test_game_lays_a_cloud_and_saves_it(monkeypatch):
    game = Game(seed=1202, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    asm = ASM(game.ship.x + 6.0, game.ship.y, 270.0, 8, game.rng_asm)
    asm.jammer = False
    game.asms = [asm]
    for _ in range(6):
        game.sim_t += 4.0
        _fly_west(asm, 4.0)
        game._update_air_picture(full_scan=True)
        if game.asm_tracks():
            break
    assert game.launch_chaff_at(game.asm_tracks()[0]) is True
    assert len(game.chaff_clouds) == 1 and game.chaff_seq == 1
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert [c.to_dict() for c in restored.chaff_clouds] == [
        c.to_dict() for c in game.chaff_clouds]
    broken = copy.deepcopy(state)
    broken["chaff_clouds"][0]["age_s"] = -1.0
    assert not restored._load_save_data(broken)


def test_ciws_burst_physics():
    near = ciws.burst_kill_probability(.2, 6, False, .3)
    far = ciws.burst_kill_probability(1.4, 6, False, .3)
    assert near > far > 0.0
    assert ciws.burst_kill_probability(.5, 6, True, .3) < \
        ciws.burst_kill_probability(.5, 6, False, .3)
    assert ciws.time_of_flight_s(1.5) == pytest.approx(1.5 * 1852 / 950)
    assert ciws.slew(0.0, 90.0, .5) == pytest.approx(ciws.SLEW_DEG_S * .5)
    assert ciws.on_target(89.0, 90.0) and not ciws.on_target(80.0, 90.0)


def test_missile_state_round_trips_and_age_is_bounded_by_flight_time():
    game = Game(seed=1203, start_menu=False, audio_enabled=False)
    asm = ASM(game.ship.x + 30.0, game.ship.y, 270.0, 9, game.rng_asm,
              launch_speed_kn=100.0, altitude_m=60.0,
              datum=(game.ship.x, game.ship.y))
    game.asms = [asm]
    game.asm_seq = 9
    asm.update(3.0, game.ship, game.world)
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    twin = restored.asms[0]
    for key in ("speed_kn", "boosting", "altitude_m", "datum_x", "datum_y",
                "lock_s", "locked", "los_prev"):
        assert getattr(twin, key) == getattr(asm, key)
    for dt in (1.0, 1.0, 1.0):
        asm.update(dt, game.ship, game.world)
        twin.update(dt, restored.ship, restored.world)
    assert (twin.x, twin.y, twin.altitude_m) == (asm.x, asm.y, asm.altitude_m)
    broken = copy.deepcopy(state)
    profile = game._air_defense_loadout["asm"]
    broken["asms"][0]["age_s"] = missile.flight_time_bound_s(
        profile["range_nm"], profile["speed_kn"]) + 1.0
    assert not restored._load_save_data(broken)


def test_helicopter_hover_burns_more_fuel_and_holds_near_its_hover_point():
    world = SimpleNamespace(wind_speed_kn=30.0, wind_from_deg=0.0,
                            depth_m=lambda x, y: 500.0, size_nm=500.0,
                            on_land=lambda x, y: False)
    frigate = SimpleNamespace(x=100.0, y=100.0, course=0.0)
    helo = Helicopter(random.Random(1))
    helo.launch(frigate)
    helo.dip_state = "DEPLOYED"
    start_fuel, start = helo.fuel_s, (helo.x, helo.y)
    for _ in range(600):
        helo.update(1.0, frigate, world)
    assert start_fuel - helo.fuel_s == pytest.approx(600 * HOVER_FUEL_FACTOR)
    offset = math.hypot(helo.x - start[0], helo.y - start[1])
    assert 0.0 < offset < 0.05 and helo.y > start[1]     # pushed south


def test_deck_motion_limits_block_launch():
    assert deck_within_limits(2.0, 1.0)
    assert not deck_within_limits(0.0, DECK_PITCH_LIMIT_DEG + .5)
    game = Game(seed=1204, start_menu=False, audio_enabled=False)
    game.ship.pitch = DECK_PITCH_LIMIT_DEG + 1.0
    assert game.launch_helicopter() is True          # the start preparation runs
    game.helo.prep_s = 0.0
    game._launch_prepared_helicopter()
    assert game.helo.state == "HANGAR"
    game.ship.pitch = 0.0
    if game.helicopter_weather()["launch_safe"]:
        game._launch_prepared_helicopter()
        assert game.helo.state == "AUF"


def test_sonobuoys_drift_with_current_and_windage():
    world = SimpleNamespace(current_vec=lambda x, y: (1.0, 0.0),
                            wind_speed_kn=20.0, wind_from_deg=0.0)
    buoy = Sonobuoy(100.0, 100.0, 1)
    buoy.update(3600.0, world)
    assert buoy.x == pytest.approx(101.0)            # 1 kn east for an hour
    assert buoy.y == pytest.approx(100.0 + 20.0 * 0.02)   # windage south
    still = Sonobuoy(100.0, 100.0, 2)
    still.update(3600.0)
    assert (still.x, still.y) == (100.0, 100.0)
