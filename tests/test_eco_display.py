"""Solo Remote Crew: the uConsole falls back to a cheap status screen (display only)."""

import time

import pytest

from src.core import config
from src.core.game import Game
from src.commander.server import CommanderServer
from src.ui import layout
from tests.test_commander_solo import pair, solo_pair


@pytest.fixture
def server():
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


def attach(game, server):
    console = game.commander
    console.server, console.address, console.solo = server, server.address, True
    console._eco_polled = float("-inf")
    return console


def lapse(server, seconds):
    with server._lock:
        for session in server._sessions_v2.values():
            session["presence"] -= seconds


def test_presence_is_reported_only_for_a_live_solo_browser(server):
    assert server.solo_browser_present() is False
    server.set_solo_mode(True)
    assert server.solo_browser_present() is False
    solo_pair(server)
    assert server.solo_browser_present() is True
    lapse(server, 10.0)
    assert server.solo_browser_present() is False
    assert server.solo_browser_present(max_age=60.0) is True


def test_crew_sessions_never_enable_the_eco_display(server, game):
    pair(server)
    attach(game, server).solo = False
    assert game._eco_display_active() is False


def test_eco_display_replaces_the_station_views_while_the_browser_is_live(
        server, game, monkeypatch):
    solo_pair(server)
    attach(game, server)
    assert game._eco_display_active() is True

    def forbidden(*_args, **_kwargs):
        raise AssertionError("full station view drawn in eco mode")

    for name in ("draw_map_view", "draw_bridge_view", "draw_sonar_view"):
        monkeypatch.setattr("src.core.game_draw." + name, forbidden)
    calls = []
    monkeypatch.setattr(Game, "draw_eco_display",
                        lambda self: calls.append(self.station))
    game.draw()
    assert calls == [game.station]


def test_eco_display_draws_status_text_for_running_and_paused(server, game):
    solo_pair(server)
    attach(game, server)
    game.draw()
    game.paused = True
    game.draw()


@pytest.mark.parametrize("setup", [
    lambda g: setattr(g, "help_open", True),
    lambda g: setattr(g, "quit_confirm", True),
    lambda g: setattr(g, "commander_open", True),
    lambda g: setattr(g, "options_open", True),
    lambda g: setattr(g, "in_menu", True),
    lambda g: setattr(g, "game_over", True),
    lambda g: setattr(g, "autocrew_overview_open", True),
    lambda g: setattr(g, "simlog_view_open", True),
])
def test_host_owned_screens_always_draw_in_full(server, game, setup):
    solo_pair(server)
    attach(game, server)
    assert game._eco_display_active() is True
    setup(game)
    assert game._eco_display_active() is False


def test_a_lapsed_browser_restores_the_full_display(server, game):
    solo_pair(server)
    console = attach(game, server)
    assert game._eco_display_active() is True
    lapse(server, 10.0)
    console._eco_polled = float("-inf")
    assert game._eco_display_active() is False


def test_pending_host_confirmation_forces_the_full_display(server, game):
    solo_pair(server)
    console = attach(game, server)
    console._confirm_requested = True
    console.confirm_visible = lambda _game: True
    assert game._eco_display_active() is False


def test_eco_frames_are_throttled_and_refreshed_by_time(server, game):
    solo_pair(server)
    attach(game, server)
    game._t = 100.0
    assert game._skip_eco_frame() is False       # first eco frame is drawn
    game._t += config.ECO_REDRAW_S / 2
    assert game._skip_eco_frame() is True
    game._t += config.ECO_REDRAW_S
    assert game._skip_eco_frame() is False
    game.help_open = True                         # full display resets the timer
    assert game._skip_eco_frame() is False
    game.help_open = False
    assert game._skip_eco_frame() is False


def test_eco_display_does_not_change_the_simulation(server):
    def run(eco):
        instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
        try:
            if eco:
                solo_pair(server)
                attach(instance, server)
            for _ in range(120):
                instance.update(1 / 60)
                if eco:
                    instance.draw()
            return (instance.ship.x, instance.ship.y, instance.world.hour,
                    tuple((s.x, s.y) for s in instance.subs))
        finally:
            instance.audio.shutdown()
            layout.configure_for(large_text=False)
    assert run(False) == run(True)
