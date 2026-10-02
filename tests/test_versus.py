"""Crew versus crew: two teams, the frigate's crew against the boat's."""

import pygame
import pytest

from src.commander.server import OPFOR_ROLES, STATIONS
from src.commander.voice import PCM_BYTES, VoicePeer
from src.core.game import Game
from src.core.lobby import HOST_ONLY, ROWS, LobbyRoom

from test_commander_sessions_v2 import pair_v2, request, server  # noqa: F401


def player(stations, ready=True, observer=False):
    return dict(name="Crew", stations=list(stations), ready=ready, observer=observer,
                you=False)


def lobby(versus="crew", side="frigate", host_station="bridge"):
    return {"mission": "s1_patrouille", "side": side, "host_station": host_station,
            "versus": versus, "countdown_s": None}


def test_versus_row_cycles_and_is_published():
    room = LobbyRoom("s1_patrouille", "frigate", "bridge")
    assert room.versus == "ai" and room.publication()["versus"] == "ai"
    room.row = ROWS.index("versus")
    room.change(1)
    assert room.versus == "crew" and room.publication()["versus"] == "crew"
    room.change(1)
    assert room.versus == "ai"


def test_start_asks_again_while_a_team_has_nobody():
    room = LobbyRoom("s1_patrouille", "frigate", "bridge")
    room.versus = "crew"
    frigate_only = [player(["sonar"])]
    assert not room.teams_manned(frigate_only)
    assert room.request_start(frigate_only) == "confirm"
    assert room.request_start(frigate_only) == "started"
    both = LobbyRoom("s1_patrouille", "frigate", "bridge")
    both.versus = "crew"
    assert both.teams_manned([player(["uboot"])])
    assert both.request_start([player(["uboot"])]) == "started"
    # A host-only uConsole crews neither team.
    host = LobbyRoom("s1_patrouille", "frigate", HOST_ONLY)
    host.versus = "crew"
    assert not host.teams_manned([player(["uboot"])])
    assert host.teams_manned([player(["uboot"]), player(["bridge"])])
    # Against the AI the teams are never asked.
    assert LobbyRoom().teams_manned([])


def test_browsers_pairing_into_a_versus_lobby_fill_the_smaller_team(server):  # noqa: F811
    server.publish_lobby(lobby())
    for _ in range(3):
        pair_v2(server)
    # The uConsole is on the bridge: the boat first, then alternating.
    assert [player["stations"] for player in server.lobby_players()] == [
        ["uboot"], ["sonar"], ["uboot_sonar"]]
    # Against the AI everybody joins the uConsole's unit (unchanged).
    server.publish_lobby(lobby(versus="ai"))
    pair_v2(server)
    assert server.lobby_players()[-1]["stations"] == ["weapons"]


def test_locked_teams_keep_every_browser_with_its_unit(server):  # noqa: F811
    server.publish_lobby(lobby())
    _, cookie, _, body = pair_v2(server)                    # seated on the boat
    assert server.lobby_players()[0]["stations"] == ["uboot"]
    server.lock_teams(True)
    assert server.teams_locked()
    client = body["client_id"]
    # Even after giving up every boat station it cannot cross to the frigate.
    with server._lock:
        session = server._session_by_client_locked(client)
        server._release_station_locked(session, "uboot")
    assert server.lobby_players()[0]["stations"] == []
    assert not server.grant_station(client, "sonar")
    status, _, session = request(server, "/api/v2/stations/request", "POST",
                                 {"station": "sonar"}, cookie=cookie, csrf=body["csrf"])
    assert server.lobby_players()[0]["stations"] == []
    assert server.grant_station(client, "uboot_sonar")
    # A new round unlocks the teams again.
    server.lock_teams(False)
    with server._lock:
        server._release_station_locked(server._session_by_client_locked(client), "uboot_sonar")
    assert server.grant_station(client, "sonar")


def test_each_unit_hears_only_its_own_voice_room(server):  # noqa: F811
    peers = {}
    for station in ("bridge", "sonar", "uboot", "uboot_sonar"):
        peer = VoicePeer(station.encode(), {}, station, 1, 1)
        server._voice_peers[peer.digest] = peer
        peers[station] = peer
    with server._lock:
        server.voice_press_locked(peers["bridge"])
        server.voice_press_locked(peers["uboot"])
        # Both units have their own talker at the same time.
        assert server.voice_talker_for_locked("sonar") == "bridge"
        assert server.voice_talker_for_locked("uboot_sonar") == "uboot"
        for peer in peers.values():
            peer.outgoing.clear()
        server.voice_relay_locked(peers["uboot"], b"\0" * PCM_BYTES)
        server.voice_relay_locked(peers["sonar"], b"\0" * PCM_BYTES)   # not talking
    assert [len(peer.outgoing) for peer in peers.values()] == [0, 0, 0, 1]
    opcode, frame = peers["uboot_sonar"].outgoing[0]
    assert opcode == 2 and frame[0] == (STATIONS + OPFOR_ROLES).index("uboot")
    with server._lock:
        server.voice_release_locked(peers["uboot"])
        assert server.voice_talker_for_locked("uboot") is None
        assert server.voice_talker_for_locked("bridge") == "bridge"


@pytest.fixture
def game(monkeypatch):
    game = Game(seed=19, start_menu=True, audio_enabled=False)
    monkeypatch.setattr(game.commander, "autostart", lambda solo=False: None)
    yield game
    game.commander.stop()


def key(game, code):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


@pytest.mark.parametrize("language", ["en", "de"])
def test_host_only_versus_round_shows_the_umpire_screen(game, language):
    from src.core.i18n import Translator, translation_scope
    from src.ui import layout

    game.open_lobby()
    game.lobby.station = HOST_ONLY
    game.lobby.versus = "crew"
    game._draw_lobby_page()
    game._start_lobby_mission()
    assert game.versus_round and game.host_only and game.umpire_view_active()
    game.tr = Translator(language).t
    with layout.capture_text() as text, translation_scope(game.tr):
        game.draw()
    shown = " ".join(entry["text"] for entry in text)
    assert Translator(language).t("umpire.title") in shown
    # No station key reaches a unit from the umpire screen.
    station, ship_order = game.station, game.ship.target_speed
    key(game, pygame.K_2)
    key(game, pygame.K_UP)
    assert (game.station, game.ship.target_speed) == (station, ship_order)
    key(game, pygame.K_F1)
    assert game.help_open
    game._return_to_main_menu()
    assert not game.versus_round and game.lobby_active


def test_versus_end_line_reports_each_units_own_result(game):
    game.open_lobby()
    game.lobby.versus = "crew"
    game._start_lobby_mission()
    assert game.versus_round and not game.umpire_view_active()
    assert game.versus_end_line() is None
    boat = game.claim_opfor_sub()
    assert boat is not None
    game.game_over = True
    game.mission_result = "SIEG"
    boat.sub.sunk = True
    assert game.versus_outcome() == (True, False)
    game.mission_result = "VERLOREN"
    boat.sub.sunk = False
    game.damage.ship_sunk = True
    assert game.versus_outcome() == (False, True)
    assert game.versus_end_line() is not None
    game.draw()
