"""Stations-Audit: Eingaben, Zustandsuebergaben und Rendering-Smoke."""

import pygame

from src.core.game import Game
from src.core.station import Station


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
