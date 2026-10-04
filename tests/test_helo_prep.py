"""The helicopter's start preparation: a launch order lifts off only after
``HELO_PREP_S`` in the hangar (and a launch window); it can be stopped, is
saved, and the web and the AI hunters respect it."""

import pytest

from src.air.helicopter import DECK_WINDOW_S
from src.core import config, hunter
from src.core.game import Game


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    instance.ship.roll = instance.ship.pitch = 0.0
    instance.ship.deck_quiet_s = 60.0
    yield instance
    instance.audio.shutdown()


def _calm(game):
    game.ship.roll = game.ship.pitch = 0.0
    game.ship.deck_quiet_s = max(game.ship.deck_quiet_s, DECK_WINDOW_S)


def test_launch_order_prepares_for_five_minutes_then_lifts_off(game):
    if not game.helicopter_weather()["launch_safe"]:
        pytest.skip("seed without flight weather")
    assert config.HELO_PREP_S == 300.0
    assert game.launch_helicopter() is True
    assert game.helo.state == "HANGAR" and game.helo.preparing
    elapsed = 0.0
    while game.helo.state == "HANGAR" and elapsed < config.HELO_PREP_S + 5.0:
        _calm(game)
        game._update_aviation(1.0)
        elapsed += 1.0
    assert game.helo.state == "AUF"
    assert elapsed == pytest.approx(config.HELO_PREP_S)
    assert game.helo.prep_s is None


def test_repeated_orders_keep_the_running_preparation(game):
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    assert game.launch_helicopter() is True
    for _ in range(100):
        _calm(game)
        game._update_aviation(1.0)
    assert game.launch_helicopter() is True
    assert game.helo.prep_s == pytest.approx(config.HELO_PREP_S - 100.0)


def test_h_stops_the_preparation_and_the_recall_does_too(game):
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    game.toggle_helo()
    assert game.msg["__u_jagd_i18n__"] == "runtime.helo.prep"
    assert game.helo.preparing
    game.toggle_helo()
    assert game.msg["__u_jagd_i18n__"] == "runtime.helo.prep_cancelled"
    assert not game.helo.preparing and game.helo.state == "HANGAR"
    assert game.launch_helicopter() is True
    assert game.return_helicopter() is True
    assert not game.helo.preparing
    assert game.return_helicopter() == "not_ready"


def test_a_down_flight_deck_refuses_and_holds_a_prepared_launch(game):
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    game.damage.compartments["flightdeck"].state = "ZERSTOERT"
    assert game.launch_helicopter() == "flightdeck_down"
    assert not game.helo.preparing
    game.damage.compartments["flightdeck"].state = "OK"
    assert game.launch_helicopter() is True
    game.helo.prep_s = 0.0
    game.damage.compartments["flightdeck"].state = "ZERSTOERT"
    game._launch_prepared_helicopter()
    assert game.helo.state == "HANGAR" and game.helo.prep_ready


def test_a_recovered_helicopter_needs_a_new_preparation(game):
    game.helo.launch(game.ship)
    game.helo.order_return()
    game.helo.x, game.helo.y = game.ship.x, game.ship.y
    _calm(game)
    game._update_aviation(0.1)
    assert game.helo.state == "HANGAR" and not game.helo.preparing
    if game.helicopter_weather()["status"] != "no_go":
        assert game.launch_helicopter() is True
        assert game.helo.prep_s == config.HELO_PREP_S


def test_preparation_survives_save_and_load(game, tmp_path):
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    assert game.launch_helicopter() is True
    game.helo.prep_s = 123.5
    path = tmp_path / "slot.json"
    assert game.save_game(str(path)) == str(path)
    other = Game(seed=7, start_menu=False, audio_enabled=False, language="en")
    try:
        assert other.load_game(str(path)) is True
        assert other.helo.state == "HANGAR" and other.helo.prep_s == 123.5
    finally:
        other.audio.shutdown()


def test_save_validator_rejects_a_preparation_in_flight(game):
    from src.core.save_validate_weapons import check_helo
    data = game.save_state()
    data["helo"]["prep_s"] = 10.0
    assert check_helo(data, game.runtime_catalog) is not False
    data["helo"]["prep_s"] = config.HELO_PREP_S + 1.0
    assert check_helo(data, game.runtime_catalog) is False
    data["helo"]["prep_s"] = 10.0
    data["helo"]["state"] = "AUF"
    assert check_helo(data, game.runtime_catalog) is False


def test_web_projection_shows_the_preparation(game):
    from src.commander import projections
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    view = projections._helicopter(game, [], {}, {})
    assert view["asset"]["prep_s"] is None
    assert view["readiness"]["can_launch"] and not view["readiness"]["can_return"]
    game.launch_helicopter()
    view = projections._helicopter(game, [], {}, {})
    assert view["asset"]["prep_s"] == config.HELO_PREP_S
    assert not view["readiness"]["can_launch"] and view["readiness"]["can_return"]
    assert projections._helicopter(game, [], {}, {}, asset_only=True)["asset"]["prep_s"] \
        == config.HELO_PREP_S


def test_ai_hunter_waits_for_the_preparation(game):
    """The hunters' own wait for the order is halved so their mean time to
    launch stays where it was (the preparation now takes the other half)."""
    assert hunter.HELO_READY_MEAN_S + config.HELO_PREP_S == 600.0
    if game.helicopter_weather()["status"] == "no_go":
        pytest.skip("seed without flight weather")
    game.launch_helicopter()
    assert game.helo.preparing
    game._update_aviation(1.0)
    assert game.helo.state == "HANGAR"


def test_ground_speed_is_zero_in_the_hover_and_cruise_in_transit(game):
    helo = game.helo
    helo.launch(game.ship)
    helo.set_waypoint(game.ship.x + 10.0, game.ship.y)
    helo.update(1.0, game.ship, game.world)
    assert helo.ground_speed_kn == helo.SPEED_KN
    helo.hover_x, helo.hover_y = helo.x, helo.y
    helo.dip_state = "DEPLOYING"
    helo.dip_water_depth_m = 500.0
    helo.update(1.0, game.ship, game.world)
    assert helo.ground_speed_kn == 0.0


@pytest.mark.parametrize("scale", [4.0, 20.0, 160.0])
def test_a_chart_click_puts_the_waypoint_exactly_there_and_the_helicopter_stops_on_it(scale):
    import math
    import pygame
    from src.core.station import Station
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    try:
        game.helo.launch(game.ship)
        game.station = Station.HELICOPTER
        game.station_page = 0
        game.map_follow = True
        game.map_view.scale = scale
        game.draw()
        from src.ui import layout
        with layout.bottom_panel_regions(game.bottom_panel_mode()):
            chart = pygame.Rect(config.MAP_RECT)
            click = (chart.x + int(chart.w * .3), chart.y + int(chart.h * .7))
            game.map_view.set_rect(config.MAP_RECT)
            expected = game.map_view.screen_to_world(*click)
        window = game._canvas_to_window(click) if hasattr(game, "_canvas_to_window") else click
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=window, button=1))
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=window, button=1))
        assert game.helo.waypoint_x == pytest.approx(expected[0], abs=1e-9)
        assert game.helo.waypoint_y == pytest.approx(expected[1], abs=1e-9)
        # Within reach: the helicopter flies there and stops on the point.
        helo = game.helo
        helo.set_waypoint(helo.x + 3.0, helo.y - 2.0)
        for _ in range(4000):
            helo.update(0.1, game.ship, game.world)
        assert math.hypot(helo.x - helo.waypoint_x, helo.y - helo.waypoint_y) < 0.015
        assert helo.ground_speed_kn == 0.0
    finally:
        game.audio.shutdown()
