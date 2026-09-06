"""Stations-Audit: Eingaben, Zustandsuebergaben und Rendering-Smoke."""

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact


def key(game, value):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value))


def test_all_stations_are_selectable():
    game = Game(seed=31415, start_menu=False)
    keys = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
            pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8]
    expected_stations = [Station.BRIDGE, Station.SONAR, Station.WEAPONS,
                         Station.DAMAGE, Station.OPZ,
                         Station.RADIO, Station.ENGINE, Station.HELICOPTER]
    for expected, input_key in zip(expected_stations, keys):
        key(game, input_key)
        assert game.station is expected
        game.draw()


def test_sonar_to_weapon_handoff_requires_valid_track():
    game = Game(seed=31415, start_menu=False)
    sub = game.subs[0]
    sub.x, sub.y, sub.depth = game.ship.x + 5.0, game.ship.y, 40.0
    key(game, pygame.K_2)
    game.sonar.fire_ping()
    game.sonar.apply_ping(game.ship, game._sonar_targets(), game.world,
                          game.sim_t, mode=game.sonar_mode)
    game._cycle_selected_contact(1)
    key(game, pygame.K_m)
    key(game, pygame.K_3)
    assert game.station is Station.WEAPONS
    assert game.target is not None
    assert game.target.range_est is not None


def test_pause_blocks_simulation_and_resume_continues():
    game = Game(seed=31415, start_menu=False)
    before = game.sim_t
    key(game, pygame.K_p)
    game.update(1.0)
    assert game.sim_t == before
    key(game, pygame.K_p)
    game.update(1.0 / 60.0)
    assert game.sim_t > before


def test_map_wheel_without_position_does_not_crash():
    game = Game(seed=31415, start_menu=False)
    game.station = Station.BRIDGE
    event = pygame.event.Event(pygame.MOUSEWHEEL, y=1)
    game.handle_event(event)


def test_map_wheel_is_ignored_when_station_has_no_map():
    game = Game(seed=31415, start_menu=False)
    game.station = Station.SONAR
    before = game.map_view.scale
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=1,
                                         pos=(320, 285)))
    assert game.map_view.scale == before


def test_sonar_controls_change_gain_band_and_notch():
    game = Game(seed=31415, start_menu=False)
    game.station = Station.SONAR
    key(game, pygame.K_o)
    assert game.sonar.gain_db > 0.0
    before = (game.sonar.band_low_hz, game.sonar.band_high_hz)
    key(game, pygame.K_f)
    assert (game.sonar.band_low_hz, game.sonar.band_high_hz) != before
    key(game, pygame.K_n)
    assert game.sonar.notch_enabled is True


def test_direct_course_and_speed_input():
    game = Game(seed=31415, start_menu=False)
    key(game, pygame.K_u)
    for value in (pygame.K_0, pygame.K_9, pygame.K_0):
        key(game, value)
    key(game, pygame.K_RETURN)
    assert game.ship.target_course == 90.0

    key(game, pygame.K_v)
    for value in (pygame.K_1, pygame.K_8, pygame.K_PERIOD, pygame.K_5):
        key(game, value)
    key(game, pygame.K_RETURN)
    assert game.ship.target_speed == 18.5


def test_numeric_navigation_input_can_be_cancelled():
    game = Game(seed=31415, start_menu=False)
    original = game.ship.target_course
    key(game, pygame.K_u)
    key(game, pygame.K_1)
    key(game, pygame.K_ESCAPE)
    assert game.input_mode is None
    assert game.ship.target_course == original


def test_save_load_restores_navigation_ui_state():
    game = Game(seed=31415, start_menu=False)
    game.station = Station.ENGINE
    game.map_follow = False
    game.map_view.cx = 123.0
    game.map_view.cy = 234.0
    game.map_view.scale = 4.0
    data = game.save_state()

    restored = Game(seed=999, start_menu=False)
    restored.load_state(data)
    assert restored.station is Station.ENGINE
    assert restored.map_follow is False
    assert restored.map_view.cx == 123.0
    assert restored.map_view.cy == 234.0
    assert restored.map_view.scale == 4.0


def test_escape_requires_explicit_quit_confirmation():
    game = Game(seed=31415, start_menu=False)
    key(game, pygame.K_ESCAPE)
    assert game.running is True
    assert game.quit_confirm is True
    key(game, pygame.K_n)
    assert game.running is True
    assert game.quit_confirm is False
    key(game, pygame.K_ESCAPE)
    key(game, pygame.K_RETURN)
    assert game.running is True
    assert game.quit_confirm is False
    key(game, pygame.K_ESCAPE)
    key(game, pygame.K_DOWN)
    key(game, pygame.K_DOWN)
    key(game, pygame.K_RETURN)
    assert game.running is False


def test_weapon_arrows_select_contact_horizontally_and_depth_vertically():
    game = Game(seed=31415, start_menu=False)
    game.station = Station.WEAPONS
    game.sonar.contacts = {
        1: Contact(1, 1, "passiv", "sub"),
        2: Contact(2, 2, "passiv", "sub"),
    }
    depth = game.torpedo_depth
    key(game, pygame.K_RIGHT)
    assert game.selected_contact.id == 1
    key(game, pygame.K_RIGHT)
    assert game.selected_contact.id == 2
    key(game, pygame.K_UP)
    game.update(0.5)
    assert game.torpedo_depth > depth
    assert game.ship.target_course == game.ship.course


def test_helicopter_m_designates_selected_sonar_contact():
    game = Game(seed=31415, start_menu=False)
    contact = Contact(1, game.subs[0].id, "passiv", "sub")
    game.sonar.contacts[contact.target_id] = contact
    game.selected_contact = contact
    game.station = Station.HELICOPTER
    key(game, pygame.K_m)
    assert game.target is contact


@pytest.mark.parametrize("affiliation", ["FRIEND", "NEUTRAL"])
def test_opz_protected_affiliation_blocks_ship_torpedo(affiliation):
    game = Game(seed=2718, start_menu=False)
    target = game.subs[0]
    contact = Contact(9, target.id, "ping", "sub")
    contact.update_ping(90.0, 5.0, 50.0, 1.0, game.sim_t)
    contact.player_class = "U_BOOT"
    game.sonar.contacts[target.id] = contact
    game.target = contact
    track_id = f"U-{target.id}"
    game.air_picture.observe(
        track_id=track_id, kind="SUB", target_id=target.id,
        source="SONAR-PING", bearing=90.0, range_nm=5.0,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=1.0, now=game.sim_t, label="K9")
    game.opz_affiliations[track_id] = affiliation

    readiness, _ = game.torpedo_readiness()
    assert f"ZUGEHOERIGKEIT {affiliation}" in readiness
    before = game.torpedo_count
    game.launch_torpedo()
    assert game.torpedo_count == before
    assert not game.torpedoes
    assert "ROE-Sperre" in game.msg


def test_unknown_opz_affiliation_keeps_existing_ship_launch_policy():
    game = Game(seed=2719, start_menu=False)
    target = game.subs[0]
    contact = Contact(10, target.id, "ping", "sub")
    contact.update_ping(90.0, 5.0, 50.0, 1.0, game.sim_t)
    contact.player_class = "U_BOOT"
    game.sonar.contacts[target.id] = contact
    game.target = contact
    game.air_picture.observe(
        track_id=f"U-{target.id}", kind="SUB", target_id=target.id,
        source="SONAR-PING", bearing=90.0, range_nm=5.0,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=1.0, now=game.sim_t, label="K10")
    assert game.torpedo_readiness()[0] == "FEUER FREI"
    game.launch_torpedo()
    assert len(game.torpedoes) == 1


def test_enemy_launch_is_hidden_until_first_sonar_observation(monkeypatch):
    game = Game(seed=2720, start_menu=False)
    sub = game.subs[0]
    sub.pending_torpedoes.append((sub.x, sub.y, 180.0, sub.depth))
    game.msg = "unrelated"
    game._drain_enemy_torpedoes()
    assert game.msg == "unrelated"

    torpedo = game.enemy_torpedoes[0]

    def observe_torpedo(*args, **kwargs):
        contact = Contact(88, torpedo.id, "passiv", "torpedo")
        contact.update_passive(180.0, .8, .8, "", game.sim_t)
        game.sonar.contacts[torpedo.id] = contact

    monkeypatch.setattr(game.sonar, "update", observe_torpedo)
    game._update_sensors(.25)
    assert "Torpedo erstmals beobachtet" in game.msg
    game.sonar.contacts.clear()
    game.msg = "keine neue Warnung"
    game._update_sensors(.25)
    assert game.msg == "keine neue Warnung"


def test_bridge_arrows_match_horizontal_steering_and_vertical_telegraph():
    game = Game(seed=31415, start_menu=False)
    speed = game.ship.target_speed
    key(game, pygame.K_RIGHT)
    assert game.steering_input() == (1, 0)
    key(game, pygame.K_UP)
    assert game.ship.target_speed > speed
