"""Variable-depth sonar (VDS): handling, depth, detection, active, input and saves."""

import copy
import json
import random
from types import SimpleNamespace

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem, TowState


def press(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _streamed(sonar, depth_m=50.0):
    sonar.vds_state = TowState.STREAMED
    sonar.vds_payout = 1.0
    sonar._vds_settle_s = config.SONAR_VDS_SETTLE_S
    sonar.vds_depth_m = sonar.vds_depth_target_m = depth_m
    return sonar


def _advance(sonar, seconds, speed_kn=8.0, sea_state=3.0, step=1.0):
    ship = SimpleNamespace(speed=speed_kn, course=0.0)
    for _ in range(int(seconds / step)):
        sonar.advance_mechanics(step, 0.0, ship, sea_state)


def test_lowering_takes_two_minutes_then_settles():
    sonar = SonarSystem(1)
    assert sonar.toggle_vds(8.0, 3.0)
    _advance(sonar, config.SONAR_VDS_DEPLOY_S - 2)
    assert sonar.vds_state == TowState.DEPLOYING and not sonar.vds_status()["available"]
    _advance(sonar, 3)
    assert sonar.vds_state == TowState.STREAMED and sonar.vds_status()["available"]
    assert sonar.vds_performance < 1.0
    _advance(sonar, config.SONAR_VDS_SETTLE_S)
    assert sonar.vds_performance == 1.0
    assert sonar.toggle_vds(8.0, 3.0) and sonar.vds_state == TowState.RETRIEVING
    _advance(sonar, config.SONAR_VDS_RETRIEVE_S + 1)
    assert sonar.vds_state == TowState.STOWED and sonar.vds_payout == 0.0


@pytest.mark.parametrize("speed_kn,sea_state", [(1.0, 3.0), (18.0, 3.0), (8.0, 6.0)])
def test_handling_pauses_outside_speed_and_sea_state(speed_kn, sea_state):
    sonar = SonarSystem(1)
    sonar.toggle_vds(speed_kn, sea_state)
    _advance(sonar, 60, speed_kn, sea_state)
    assert sonar.vds_payout == 0.0 and not sonar.vds_status()["handling_ok"]
    _advance(sonar, 60, 8.0, 3.0)
    assert sonar.vds_payout == pytest.approx(60 / config.SONAR_VDS_DEPLOY_S)


def test_overspeed_loses_a_lowered_body():
    sonar = _streamed(SonarSystem(1))
    _advance(sonar, 1, speed_kn=config.SONAR_VDS_MAX_SAFE_KN + 1)
    assert sonar.vds_state == TowState.FAULT
    assert not sonar.toggle_vds(8.0, 3.0)


def test_depth_follows_target_within_the_cable_limit():
    sonar = _streamed(SonarSystem(1), 50.0)
    sonar.vds_depth_target_m = 300.0
    _advance(sonar, 10, speed_kn=10.0)
    assert sonar.vds_depth_m == pytest.approx(50.0 + 10 * config.SONAR_VDS_DEPTH_RATE_M_S)
    limit = config.SONAR_VDS_DEPTH_MAX_M - 10.0 * config.SONAR_VDS_SPEED_SHALLOW_M_PER_KN
    assert sonar.vds_depth_target_m == pytest.approx(limit)
    _advance(sonar, 200, speed_kn=10.0)
    assert sonar.vds_depth_m == pytest.approx(limit)


def test_vds_below_the_layer_hears_a_deep_boat_better_than_the_hull():
    ship = Ship(250, 250, speed_kn=6)
    world = SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)
    sub = Sub(255, 250, 160, 0, "diesel_alt", random.Random(4))
    sonar = _streamed(SonarSystem(4), 150.0)
    hull = sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "BOW")
    deep = sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "VDS")
    sonar.vds_depth_m = 40.0
    shallow = sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "VDS")
    assert deep > shallow > hull
    sonar.vds_state = TowState.STOWED
    assert sonar.passive_range_nm(sub, 5.0, ship, world, 1.0, "VDS") == 0.0


def test_vds_pings_from_its_own_depth():
    game = Game(seed=6, start_menu=False)
    # 6 NM: the echo is noise-limited, so the layer crossing costs
    # signal excess (reverberation-limited echoes lose it on both sides).
    world = game.world
    thermo = world.thermocline_depth_m(game.ship.x + 6, game.ship.y)
    assert thermo + 20.0 <= config.SONAR_VDS_DEPTH_MAX_M
    sonar = _streamed(game.sonar, thermo + 20.0)
    deep = SimpleNamespace(x=game.ship.x + 6, y=game.ship.y, depth=thermo + 80, course=90.0,
                           speed=5.0, length_m=70.0)
    shallow = SimpleNamespace(x=game.ship.x + 6, y=game.ship.y, depth=10.0, course=90.0,
                              speed=5.0, length_m=70.0)
    hull_deep = sonar.active_terms(deep, game.ship, world, 1.0, "BOW").signal_excess_db
    vds_deep = sonar.active_terms(deep, game.ship, world, 1.0, "VDS").signal_excess_db
    hull_shallow = sonar.active_terms(shallow, game.ship, world, 1.0, "BOW").signal_excess_db
    vds_shallow = sonar.active_terms(shallow, game.ship, world, 1.0, "VDS").signal_excess_db
    sonar.vds_depth_m = max(config.SONAR_VDS_DEPTH_MIN_M, thermo - 20.0)
    vds_above_deep = sonar.active_terms(deep, game.ship, world, 1.0, "VDS").signal_excess_db
    assert vds_deep > vds_above_deep and vds_deep > hull_deep
    assert vds_shallow < hull_shallow


def test_a_vds_only_contact_is_unambiguous():
    ship = Ship(250, 250, speed_kn=6)
    sub = Sub(262, 250, 160, 0, "diesel_alt", random.Random(4))
    world = SimpleNamespace(sea_state=0, effective_sea_state=0,
                            thermocline_depth_m=lambda x, y: 100)
    sonar = _streamed(SonarSystem(4), 150.0)
    sonar._passive_range_nm = lambda tgt, dist, frigate, world, rf, mode, *a, **k: (
        30.0 if mode == "VDS" else 0.0)
    sonar._measure_tonal = lambda *args: None
    sonar.update(1.0, 1.0, ship, [sub], world, mode="VDS", advance_mechanics=False)
    contact = sonar.contacts[sub.id]
    assert set(contact.array_observations) == {"VDS"}
    assert contact.fusion_status == "NUR VDS"
    assert not contact.towed_ambiguous


@pytest.fixture
def game():
    game = Game(seed=6, start_menu=False)
    game.station = Station.SONAR
    game.ship.speed = 8.0
    return game


def test_keys_lower_select_and_steer_the_vds(game):
    press(game, pygame.K_y, pygame.KMOD_SHIFT)
    assert game.sonar.vds_state == TowState.DEPLOYING
    assert game.sonar.tow_state == TowState.STOWED
    modes = []
    for _ in range(3):
        press(game, pygame.K_b, pygame.KMOD_SHIFT)
        modes.append(game.sonar_mode)
    assert modes == ["TOWED", "VDS", "BOW"]
    press(game, pygame.K_b, pygame.KMOD_SHIFT)
    press(game, pygame.K_b, pygame.KMOD_SHIFT)
    assert game.sonar_mode == "VDS"
    _streamed(game.sonar, 50.0)
    tas_before = game.sonar.towed_depth_target_m
    press(game, pygame.K_v)
    assert game.sonar.vds_depth_target_m == 60.0
    assert game.sonar.towed_depth_target_m == tas_before
    # Pinging on the VDS needs the body down.
    game.sonar.vds_state = TowState.STOWED
    assert game.send_active_ping() == "not_ready"


def test_operator_commands_validate_their_input(game):
    assert game.set_sonar_array_mode("VDS") is True
    assert game.set_sonar_array_mode("vds") == "invalid_value"
    assert game.set_sonar_vds("yes") == "invalid_value"
    assert game.set_sonar_vds_depth(80.0) == "not_ready"
    assert game.set_sonar_vds(True) is True
    _streamed(game.sonar)
    assert game.set_sonar_vds_depth(float("nan")) == "invalid_value"
    assert game.set_sonar_vds_depth(400.0) == "invalid_value"
    assert game.set_sonar_vds_depth(299.0) == "not_ready"   # cable limit at 8 kn
    assert game.set_sonar_vds_depth(120.0) is True
    assert game.sonar.vds_depth_target_m == 120.0


def test_vds_state_round_trips_and_bad_values_are_rejected(game):
    game.sonar.toggle_vds(8.0, 3.0)
    game.sonar.vds_payout = .37
    game.sonar.vds_depth_target_m = 140.0
    game.sonar_mode = "VDS"
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.sonar.vds_state == TowState.DEPLOYING
    assert restored.sonar.vds_payout == pytest.approx(.37)
    assert restored.sonar.vds_depth_target_m == 140.0
    assert restored.sonar_mode == "VDS"
    assert restored.save_state()["sonar"]["vds_payout"] == pytest.approx(.37)
    for key, value in (("vds_state", "SUNK"), ("vds_payout", 1.5), ("vds_depth_m", 900.0),
                       ("vds_handling_ok", 1), ("vds_settle_s", float("inf"))):
        broken = copy.deepcopy(state)
        broken["sonar"][key] = value
        before = restored.save_state()
        assert not restored._load_save_data(broken), key
        assert restored.save_state() == before
    broken = copy.deepcopy(state)
    broken["sonar_mode"] = "SIDEWAYS"
    assert not restored._load_save_data(broken)
