"""Multiplayer lobby: host page, ready ticks, shared countdown and return."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.game_lobby import LOBBY_SCREEN, MULTIPLAYER_ENTRY
from src.core.lobby import COUNTDOWN_S, LobbyRoom, ROWS
from src.core.station import Station

from test_commander_sessions_v2 import pair_v2, request, server  # noqa: F401


def key(game, code):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def player(ready, stations=("sonar",), observer=False):
    return dict(name="Crew", stations=list(stations), ready=ready, observer=observer, you=False)


def test_room_rows_change_mission_side_and_station():
    room = LobbyRoom("s1_patrouille", "frigate", "bridge")
    room.change(1)
    assert room.scenario_key == config.SCENARIO_ORDER[1]
    room.move(1)
    room.change(1)
    assert (room.side, room.station) == ("uboot", "uboot")
    room.move(1)
    room.change(1)
    assert room.station == "uboot_sonar"
    assert ROWS[room.row] == "station"


def test_start_asks_again_while_a_crew_member_is_not_ready():
    room = LobbyRoom()
    players = [player(True), player(False), player(False, stations=())]
    assert room.request_start(players) == "confirm"
    assert room.countdown_s is None
    assert room.request_start(players) == "started"
    assert room.countdown_s == COUNTDOWN_S
    # Observers and browsers without a station never hold the start up.
    fresh = LobbyRoom()
    assert fresh.request_start([player(True), player(False, observer=True),
                                player(False, stations=())]) == "started"


def test_countdown_runs_on_wall_time_and_can_be_cancelled():
    room = LobbyRoom()
    room.request_start([])
    assert not room.tick(COUNTDOWN_S / 2)
    assert room.publication()["countdown_s"] == pytest.approx(COUNTDOWN_S / 2)
    assert room.cancel() and room.countdown_s is None
    room.request_start([])
    assert room.tick(COUNTDOWN_S) and room.countdown_s is None


@pytest.fixture
def game(monkeypatch):
    game = Game(seed=19, start_menu=True, audio_enabled=False)
    started = []
    monkeypatch.setattr(game.commander, "autostart", lambda solo=False: started.append(solo))
    game.autostarts = started
    yield game
    game.commander.stop()


def test_main_menu_entry_opens_the_lobby_and_starts_crew_mode(game):
    game.main_menu_sel = game.main_menu_index(MULTIPLAYER_ENTRY)
    key(game, pygame.K_RETURN)
    assert game.lobby_active and game.menu_screen == LOBBY_SCREEN
    assert game.autostarts == [False]
    # Nothing is simulated while the lobby is open.
    sim_t = game.sim_t
    game.update(0.5)
    assert game.sim_t == sim_t
    game.draw()
    key(game, pygame.K_ESCAPE)
    assert game.main_menu and not game.lobby_active


def test_countdown_starts_the_mission_on_the_lobby_station_and_returns(game):
    game.open_lobby()
    game.lobby.row = ROWS.index("station")
    for _ in range(4):
        key(game, pygame.K_RIGHT)          # bridge -> sonar -> weapons -> damage -> opz
    game.lobby.row = ROWS.index("start")
    key(game, pygame.K_RETURN)
    assert game.lobby.countdown_s == COUNTDOWN_S
    for _ in range(int(COUNTDOWN_S / 0.5) + 1):
        game.lobby_tick(0.5)
    assert not game.in_menu and game.lobby_round
    assert game.station is Station.RADAR and game.local_side == "frigate"
    game._return_to_main_menu()
    assert game.lobby_active and not game.main_menu
    assert game.lobby.countdown_s is None


def test_submarine_side_puts_the_uconsole_on_its_boat_station(game):
    game.open_lobby()
    game.lobby.row = ROWS.index("side")
    key(game, pygame.K_RIGHT)
    game.lobby.row = ROWS.index("station")
    key(game, pygame.K_RIGHT)
    game._start_lobby_mission()
    assert game.local_side == "uboot" and game.uboot_station == "uboot_sonar"
    assert game.station is Station.SONAR


def test_server_publishes_lobby_and_ready_ticks(server):  # noqa: F811
    _, cookie, _, body = pair_v2(server)
    assert body["lobby"] is None
    status, _, refused = request(server, "/api/v2/lobby/ready", "POST", {"ready": True},
                                 cookie=cookie, csrf=body["csrf"])
    assert status == 409 and refused == {"error": "no_lobby"}
    server.publish_lobby({"mission": "s1_patrouille", "side": "frigate",
                          "host_station": "bridge", "countdown_s": None})
    status, _, session = request(server, "/api/v2/session", cookie=cookie)
    assert session["lobby"]["players"] == [dict(name="Watch Officer", stations=[],
                                                ready=False, observer=False, you=True)]
    for invalid in ({"ready": 1}, {"ready": True, "extra": 0}, []):
        status, _, _ = request(server, "/api/v2/lobby/ready", "POST", invalid,
                               cookie=cookie, csrf=body["csrf"])
        assert status == 400
    status, _, _ = request(server, "/api/v2/lobby/ready", "POST", {"ready": True},
                           cookie=cookie, csrf="wrong")
    assert status == 403
    status, _, ready = request(server, "/api/v2/lobby/ready", "POST", {"ready": True},
                               cookie=cookie, csrf=body["csrf"])
    assert status == 200 and ready["lobby"]["ready"] is True
    assert server.lobby_players()[0]["ready"] is True
    # Closing the lobby (the mission starts) clears every tick.
    server.publish_lobby(None)
    assert server.lobby_players()[0]["ready"] is False
    status, _, session = request(server, "/api/v2/session", cookie=cookie)
    assert session["lobby"] is None
