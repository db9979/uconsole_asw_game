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


def test_host_only_leaves_every_station_to_the_browsers_and_the_ai(game):
    from src.core import boat_autocrew
    from src.core.lobby import HOST_ONLY, station_choices
    assert station_choices("uboot")[-1] == HOST_ONLY
    game.open_lobby()
    game.lobby.row = ROWS.index("station")
    key(game, pygame.K_LEFT)                       # bridge -> host only
    assert game.lobby.station == HOST_ONLY
    assert game.lobby.publication()["host_station"] is None
    game.draw()
    game.lobby.row = ROWS.index("side")
    key(game, pygame.K_RIGHT)                      # the choice survives a side change
    assert game.lobby.station == HOST_ONLY
    game._start_lobby_mission()
    assert game.host_only and game.crew_assist and game.local_side == "frigate"
    # No station is the uConsole's: the AI works the one on screen too.
    assert game.autocrew.status(game, game.station.name.lower()) == "active"
    assert game._local_station_input_locked()
    assert not boat_autocrew.held(game, "uboot")
    game._return_to_main_menu()
    key(game, pygame.K_ESCAPE)
    assert not game.host_only


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
def test_hotspot_lobby_shows_the_wifi_step_and_the_page_step_together(
        game, language, large):
    from itertools import combinations

    from src.commander.access_point import HotspotDetails
    from src.core.i18n import Translator, pseudolocale, translation_scope
    from src.ui import layout

    game.open_lobby()
    console = game.commander
    console.network_mode = "hotspot"
    console.address = ("10.42.0.1", 8765)
    console.pairing_code = "123ABC"
    console.hotspot.details = HotspotDetails(
        ssid="U-Jagd-7KPX", password="abcdefghijkmnopqrs",
        address="10.42.0.1", interface="wlan0")
    drawn = []
    wifi, page = console._hotspot_qr, console._url_qr
    console._hotspot_qr = lambda *a, **k: drawn.append(("wifi", a)) or wifi(*a, **k)
    console._url_qr = lambda *a, **k: drawn.append(("page", a)) or page(*a, **k)
    game.tr = (Translator("en", pseudolocale()).t if language == "pseudo"
               else Translator(language).t)
    layout.configure_for(large_text=large)
    try:
        with layout.capture_text() as text, translation_scope(game.tr):
            game._draw_lobby_page()
    finally:
        layout.configure_for(large_text=False)
        console.address = None
        console.hotspot.details = None
    assert drawn == [("wifi", ("U-Jagd-7KPX", "abcdefghijkmnopqrs")),
                     ("page", ("10.42.0.1", 8765))]
    shown = [entry["text"] for entry in text]
    if language != "pseudo":
        step1 = next(entry for entry in text
                     if entry["text"] == game.tr("commander.local.hotspot.step1"))
        step2 = next(entry for entry in text
                     if entry["text"] == game.tr("commander.local.hotspot.step2"))
        assert step1["rect"].bottom <= step2["rect"].top
    assert "abcdefghijkmnopqrs" in shown and "123 ABC" in shown
    assert "U-Jagd-7KPX" in shown
    assert "http://10.42.0.1:8765/" in shown
    panel = pygame.Rect(40, 116, config.SCREEN_W - 80, 500)
    for entry in text:
        assert entry["bounds"].contains(entry["ink"]), entry
        assert panel.contains(entry["bounds"]), entry
        assert "commander." not in entry["text"] and "lobby." not in entry["text"]
    overlaps = [(a["text"], b["text"]) for a, b in combinations(text, 2)
                if a["ink"].colliderect(b["ink"])]
    assert not overlaps, overlaps


def _launch(monkeypatch, argv, onboarded=True):
    """Run ``main.main(argv)`` with a real Game up to its main loop."""
    import main as entry
    from src.commander.local import CommanderConsole
    from src.core.preferences import Preferences

    seen = []
    autostarts = []
    monkeypatch.setattr(CommanderConsole, "autostart",
                        lambda self, solo=False: autostarts.append((solo, self.port)))
    monkeypatch.setattr(Game, "run", lambda self: seen.append(self))
    monkeypatch.setattr(entry, "load_preferences", lambda: Preferences(
        language="en", fullscreen=False, audio=False, onboarded=onboarded))
    assert entry.main(argv) == 0
    game = seen[0]
    game.commander.stop()
    return game, autostarts


@pytest.mark.parametrize("flag", ["--multiplayer", "--remote-crew"])
def test_multiplayer_flag_opens_the_lobby_after_the_splash(monkeypatch, flag):
    game, autostarts = _launch(monkeypatch, [flag, "--windowed", "5"])
    assert autostarts == [(False, 8765)]  # crew mode, as the menu entry
    assert game.splash_active and not game.commander.solo
    game._t = game.splash_started_at + 1.0
    key(game, pygame.K_SPACE)
    assert not game.splash_active
    assert game.lobby_active and game.menu_screen == LOBBY_SCREEN
    game.draw()
    key(game, pygame.K_ESCAPE)
    assert game.main_menu and not game.lobby_active
    assert game.main_menu_sel == game.main_menu_index(MULTIPLAYER_ENTRY)


def test_multiplayer_flag_wins_over_the_first_launch_welcome(monkeypatch):
    game, autostarts = _launch(monkeypatch, ["--multiplayer", "--web-port", "9000", "5"],
                               onboarded=False)
    assert autostarts == [(False, 9000)]
    assert game.lobby_active and not game.welcome_active


def test_without_the_flag_the_game_opens_the_main_menu(monkeypatch):
    game, autostarts = _launch(monkeypatch, ["5"])
    assert autostarts == [] and game.main_menu and not game.lobby_active


@pytest.mark.parametrize("argv", [
    ["--play-sub"], ["--status-file", "s.json"],
    ["--multiplayer", "--solo-crew"], ["--remote-crew", "--solo-crew"],
    ["--multiplayer", "--web-host", "--public-origin", "https://a.test"],
    ["--multiplayer", "--web-port", "80"]])
def test_removed_and_conflicting_launch_flags_are_rejected(argv, capsys):
    import main as entry

    with pytest.raises(SystemExit) as raised:
        entry.main(argv)
    assert raised.value.code == 2
    capsys.readouterr()


def test_help_lists_multiplayer_and_hides_the_old_and_advanced_flags(capsys):
    import main as entry

    with pytest.raises(SystemExit):
        entry.main(["--help"])
    text = capsys.readouterr().out
    assert "--multiplayer" in text
    for hidden in ("--remote-crew", "--solo-crew", "--play-sub", "--status-file"):
        assert hidden not in text


def test_a_lobby_round_alone_is_a_solo_game_without_the_crew_assist(game, monkeypatch):
    game.open_lobby()
    game._start_lobby_mission()
    assert game.lobby_round and not game.crew_assist
    assert not any(game.autocrew.enabled.values())
    game._return_to_main_menu()
    crew = [dict(name="Sonar", stations=["sonar"], ready=True, observer=False, you=False)]
    monkeypatch.setattr(type(game), "lobby_players", lambda self: crew)
    game._start_lobby_mission()
    assert game.crew_assist


def test_a_browser_pairing_into_the_lobby_is_seated_in_order(server):  # noqa: F811
    from src.commander.server import LOBBY_SEAT_ORDER, OPFOR_ROLES, STATIONS
    assert sorted(LOBBY_SEAT_ORDER["frigate"]) == sorted(STATIONS)
    assert sorted(LOBBY_SEAT_ORDER["uboot"]) == sorted(OPFOR_ROLES)
    server.publish_lobby({"mission": "s1_patrouille", "side": "frigate",
                          "host_station": "bridge", "countdown_s": None})
    for _ in range(3):
        pair_v2(server)
    # The uConsole plays the bridge: the crew starts at sonar, weapons, helicopter.
    assert [player["stations"] for player in server.lobby_players()] == [
        ["sonar"], ["weapons"], ["helicopter"]]
    # A host-only uConsole on the boat: the first browser takes command.
    server.publish_lobby({"mission": "s1_patrouille", "side": "uboot",
                          "host_station": None, "countdown_s": None})
    pair_v2(server)
    assert server.lobby_players()[-1]["stations"] == ["uboot"]


def test_a_browser_pairing_without_a_lobby_gets_no_seat(server):  # noqa: F811
    pair_v2(server)
    server.publish_lobby({"mission": "s1_patrouille", "side": "frigate",
                          "host_station": "bridge", "countdown_s": None})
    assert server.lobby_players()[0]["stations"] == []
