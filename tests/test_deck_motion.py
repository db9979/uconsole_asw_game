"""Deck motion and the helicopter's launch/recovery windows."""

import pytest

from src.air import helicopter as helicopter_physics
from src.core.game import Game
from src.ship.ship import Ship


class _World:
    wind_from_deg = 0.0

    class ocean:
        seed = 5


def _max_pitch(course, speed, sea=5):
    ship = Ship(0.0, 0.0)
    ship.sea_state, ship.course, ship.speed = sea, course, speed
    peak = 0.0
    for step in range(6000):
        ship._update_roll_pitch(0.1, _World)
        if step > 600:
            peak = max(peak, abs(ship.pitch))
    return peak


def test_running_into_the_sea_pitches_harder_than_slowing_down():
    assert _max_pitch(0.0, 20.0) > 1.2 * _max_pitch(0.0, 5.0)
    assert _max_pitch(180.0, 15.0) < _max_pitch(0.0, 15.0)


def test_quiet_period_needs_the_deck_inside_its_limits():
    quiet = 0.0
    for _ in range(50):
        quiet = helicopter_physics.deck_quiet_step(quiet, 1.0, 1.0, 0.1)
    assert quiet == pytest.approx(5.0)
    assert not helicopter_physics.deck_window_open(quiet)
    quiet = helicopter_physics.deck_quiet_step(quiet, 1.0, 1.0, 1.0)
    assert helicopter_physics.deck_window_open(quiet)
    assert helicopter_physics.deck_quiet_step(quiet, 9.0, 0.0, 0.1) == 0.0


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()


def test_launch_waits_for_a_window_and_the_bridge_is_told(game):
    game.ship.deck_quiet_s = 1.0
    assert not game.helicopter_weather()["deck_safe"]
    assert game.launch_helicopter() == "weather_unsafe"
    game.toggle_helo()
    assert game.helo.state == "HANGAR"
    game.ship.deck_quiet_s = helicopter_physics.DECK_WINDOW_S
    if game.helicopter_weather()["launch_safe"]:
        assert game.launch_helicopter() is True


def test_deck_quiet_survives_save_and_reaches_the_web(game, tmp_path):
    from src.commander import projections
    game.ship.deck_quiet_s = 4.25
    data = game.save_state()
    assert data["ship"]["deck_quiet_s"] == 4.25
    other = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    try:
        other.load_state(data)
        assert other.ship.deck_quiet_s == 4.25
    finally:
        other.audio.shutdown()
    deck = projections._deck_motion(game)
    assert deck["quiet_s"] == 4.25 and deck["window_open"] is False
    assert deck["roll_limit_deg"] == helicopter_physics.DECK_ROLL_LIMIT_DEG
