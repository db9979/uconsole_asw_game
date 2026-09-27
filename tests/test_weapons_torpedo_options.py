"""Plan 1.3, phase 4: two ship torpedo types, search patterns, enable point, salvo."""

import copy
import json
import math

import pytest

from src.core import config
from src.core.game import Game
from src.physics import torpedo_dyn
from src.weapons.asw import WeaponBattery, ownship_loadout, split_stock
from src.weapons.torpedo import Torpedo

MK1 = "weapon.ownship.torpedo"
MK2 = "weapon.ownship.torpedo_mk2"


def _game(seed=402):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _fresh_target(game):
    """A fresh, classified, ranged contact the interlock accepts."""
    from src.sonar.sonar import Contact
    sub = game.subs[0]
    contact = Contact(41, sub.id, "passiv", "sub")
    contact.update_passive(90.0, 1.0, .8, "", game.sim_t)
    contact.range_est, contact.range_source, contact.range_seen = 5.0, "ping", game.sim_t
    contact.observed_x, contact.observed_y = game.ship.x + 5.0, game.ship.y
    contact.player_class = "U_BOOT"
    game.sonar.contacts[sub.id] = contact
    game.roe = "FREE"
    return contact


# --- pure geometry ---------------------------------------------------------

def test_split_stock_gives_the_secondary_type_a_third_and_keeps_the_total():
    magazines = ownship_loadout()["magazines"]
    assert split_stock(6, magazines) == [4, 2]
    assert split_stock(4, magazines) == [3, 1]
    assert split_stock(2, magazines) == [2, 0]
    assert sum(split_stock(10, magazines)) == 10


def test_spread_courses_and_rotated_datums():
    assert torpedo_dyn.spread_courses(10.0, 1) == (10.0,)
    assert torpedo_dyn.spread_courses(5.0, 2) == (357.0, 13.0)
    x, y = torpedo_dyn.rotate_datum(0.0, 0.0, 0.0, -5.0, 90.0)   # north datum -> east
    assert (round(x, 6), round(y, 6)) == (5.0, 0.0)


def test_pattern_turn_rates_hold_their_radius_and_the_helix_opens():
    speed = 45.0 / 3600.0
    circle = torpedo_dyn.pattern_turn_deg_s("circle", speed, 0.0)
    assert math.isclose(circle, math.degrees(speed / torpedo_dyn.CIRCLE_RADIUS_NM))
    first = torpedo_dyn.pattern_turn_deg_s("helix", speed, 0.0)
    later = torpedo_dyn.pattern_turn_deg_s("helix", speed, 3.0)
    assert first > later > torpedo_dyn.pattern_turn_deg_s("helix", speed, 100.0) > 0
    assert torpedo_dyn.helix_radius_nm(100.0) == torpedo_dyn.HELIX_MAX_RADIUS_NM
    assert torpedo_dyn.pattern_turn_deg_s("snake", speed, 0.0) == 0.0


def test_enable_point_snaps_to_the_grid_inside_its_bounds():
    assert torpedo_dyn.quantized_enable_nm(1.25) == 1.2
    assert torpedo_dyn.quantized_enable_nm(0.1) == 0.6
    assert torpedo_dyn.quantized_enable_nm(9.0) == 3.0


# --- battery ----------------------------------------------------------------

def test_ownship_battery_splits_stock_and_retasks_a_tube():
    battery = WeaponBattery.ownship(6)
    assert battery.remaining_of(MK1) == 4 and battery.remaining_of(MK2) == 2
    assert battery.loaded_count(MK1) == 2 and battery.loaded_count(MK2) == 0
    assert battery.retask(MK2) is True
    # one tube gave its Mk1 back and reloads with Mk2
    assert battery.loaded_count(MK1) == 1 and battery.loading_count == 1
    assert battery.remaining_of(MK1) == 4 and battery.remaining_of(MK2) == 2
    battery.update(61.0)
    assert battery.loaded_count(MK2) == 1
    assert battery.fire(MK2) == MK2 and battery.fire(MK2) is None
    assert battery.fire(MK1) == MK1
    assert battery.retask("weapon.unknown") is False


def test_empty_type_cannot_be_retasked_but_tubes_never_stay_empty():
    battery = WeaponBattery.ownship(2)          # 2 Mk1, 0 Mk2
    assert battery.retask(MK2) is False
    battery.preferred_weapon_key = MK2
    assert battery.fire(MK1) == MK1
    battery.update(61.0)
    assert battery.ready_count + battery.loading_count <= 2
    assert battery.remaining_total == 1


# --- game commands ----------------------------------------------------------

def test_settings_commands_validate_and_flash():
    game = _game()
    assert game.set_torpedo_type("weapon.nope") == "invalid_value"
    assert game.set_torpedo_type(MK2) is True and game.torpedo_type == MK2
    assert game.set_torpedo_pattern("zigzag") == "invalid_value"
    assert game.set_torpedo_pattern("helix") is True
    assert game.set_torpedo_enable(3.5) == "invalid_value"
    assert game.set_torpedo_enable(2.05) is True and game.torpedo_enable_nm == 2.0
    assert game.set_torpedo_salvo(3) == "invalid_value"
    assert game.set_torpedo_salvo(2) is True
    game._cycle_torpedo_pattern()
    assert game.torpedo_pattern == "snake"
    game._adjust_torpedo_enable(-1)
    assert game.torpedo_enable_nm == pytest.approx(1.8)
    game._cycle_torpedo_salvo()
    assert game.torpedo_salvo == 1
    game._cycle_torpedo_type()
    assert game.torpedo_type == MK1


def test_launch_uses_the_selected_type_pattern_and_enable_point():
    game = _game(403)
    contact = _fresh_target(game)
    game.set_torpedo_pattern("circle")
    game.set_torpedo_enable(2.0)
    assert game.launch_torpedo_at(contact, 60.0) is True
    torpedo = game.torpedoes[-1]
    assert torpedo.pattern == "circle" and torpedo.enable_nm == 2.0
    assert torpedo.profile_key == "frigate_torp"
    game.set_torpedo_type(MK2)
    assert game.launch_torpedo_at(contact, 60.0) == "no_tube_type"
    game.player_torpedo_battery.update(61.0)
    game.torpedoes.clear()
    assert game.launch_torpedo_at(contact, 60.0) is True
    assert game.torpedoes[-1].profile_key == "frigate_torp_mk2"
    assert game.torpedoes[-1].speed_kn == 55.0


def test_salvo_of_two_opens_a_spread_with_rotated_datums():
    game = _game(404)
    contact = _fresh_target(game)
    game.set_torpedo_salvo(2)
    assert game.launch_torpedo_at(contact, 60.0) is True
    assert len(game.torpedoes) == 2
    first, second = game.torpedoes
    line = math.degrees(math.atan2(contact.observed_x - game.ship.x,
                                   -(contact.observed_y - game.ship.y))) % 360.0
    assert config.angle_diff_deg(first.course, line) == pytest.approx(-8.0)
    assert config.angle_diff_deg(second.course, line) == pytest.approx(8.0)
    assert (first.guidance_x, first.guidance_y) != (second.guidance_x, second.guidance_y)
    assert game.player_torpedo_battery.loaded_count(MK1) == 0
    # doctrine: no third torpedo while two run
    game.player_torpedo_battery.update(61.0)
    assert game.launch_torpedo_at(contact, 60.0) == "salvo_limit"


def test_circle_pattern_turns_once_enabled_and_snake_stays_default():
    game = _game(405)
    contact = _fresh_target(game)
    game.set_torpedo_pattern("circle")
    game.set_torpedo_enable(3.0)
    assert game.launch_torpedo_at(contact, 60.0) is True
    torpedo = game.torpedoes[-1]
    torpedo.guidance_x, torpedo.guidance_y = torpedo.x + 2.0, torpedo.y   # inside enable point
    start = torpedo.course
    for _ in range(40):
        torpedo.update(0.25, seeker_candidates=[], world=game.world)
    assert torpedo.terminal_active and torpedo._turns_done > 0.0
    assert abs(config.angle_diff_deg(torpedo.course, start)) > 10.0
    plain = Torpedo(0.0, 0.0, 0.0, 60.0, None, 9, guidance_x=0.0, guidance_y=-5.0)
    assert plain.pattern == "snake" and plain.enable_nm == config.TORP_HOME_RANGE_NM


def test_weapon_settings_and_torpedo_pattern_round_trip(tmp_path):
    game = _game(406)
    contact = _fresh_target(game)
    game.set_torpedo_type(MK2)
    game.set_torpedo_pattern("helix")
    game.set_torpedo_enable(1.6)
    game.set_torpedo_salvo(2)
    game.player_torpedo_battery.update(61.0)
    game.set_torpedo_salvo(1)
    assert game.launch_torpedo_at(contact, 60.0) is True
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["weapon_settings"] == dict(torpedo_type=MK2, pattern="helix",
                                            enable_nm=1.6, salvo=1)
    assert state["torpedoes_in_flight"][0]["pattern"] == "helix"
    restored = _game(406)
    restored.load_state(copy.deepcopy(state))
    assert restored.torpedo_type == MK2 and restored.torpedo_pattern == "helix"
    assert restored.player_torpedo_battery.preferred_weapon_key == MK2
    assert restored.torpedoes[0].pattern == "helix"
    for mutate in (lambda s: s["weapon_settings"].__setitem__("pattern", "zigzag"),
                   lambda s: s["weapon_settings"].__setitem__("salvo", 3),
                   lambda s: s["weapon_settings"].__setitem__("torpedo_type", "weapon.x"),
                   lambda s: s["torpedoes_in_flight"][0].__setitem__("enable_nm", 5.0),
                   lambda s: s["weapon_settings"].pop("enable_nm")):
        broken = copy.deepcopy(state)
        mutate(broken)
        assert not restored._load_save_data(broken)
