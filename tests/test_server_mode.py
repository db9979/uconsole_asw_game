"""Server mode: the uConsole only serves the lobby and a crew browser leads."""

import pygame
import pytest

from src.commander.server import CommanderServer, V2_ACTION_REGISTRY
from src.commander.v2.commands import (_lobby_campaign_params, _lobby_set_params,
                                       _ordinal_params)
from src.core import config, daily
from src.core.game import Game
from src.core.game_lobby import LOBBY_SCREEN
from src.core.game_server import SERVER_ENTRY
from src.core.lobby import COUNTDOWN_S, HOST_ONLY, LobbyRoom

from test_commander_sessions_v2 import pair_v2, request


def key(game, code):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A real game in server mode with Remote Crew on an ephemeral port."""
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = Game(seed=23, start_menu=True, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console.prepare()
    console.hosts = ("127.0.0.1",)
    game.start_server_mode()
    assert console.address is not None
    yield game
    console.stop()
    game.audio.shutdown()


def frame(game, wall=.05):
    game.commander.pump(game)
    game.lobby_tick(wall)
    game.commander.pump(game)


def join(game, name):
    _, cookie, _, body = pair_v2(game.commander.server, name)
    frame(game)
    return cookie, body


def session_of(game, cookie):
    return request(game.commander.server, "/api/v2/session", cookie=cookie)[2]


def host_command(game, cookie, action, params, cid):
    """Post one host command as the browser would and run the frames."""
    server = game.commander.server
    frame(game)
    session = session_of(game, cookie)
    view = request(server, "/api/v2/host", cookie=cookie)[2]
    body = {"protocol": 2, "id": cid, "seq": session["next_command_seq"],
            "station": "host", "station_generation": session["host"]["generation"],
            "active_generation": 0, "world_session": view["session"],
            "world_epoch": view["epoch"], "resource_revision": 0,
            "action": action, "params": params}
    status, _, reply = request(server, "/api/v2/commands", "POST", body, cookie,
                               session["csrf"])
    assert (status, reply["status"]) == (202, "pending"), reply
    frame(game)
    rows = request(server, "/api/v2/results", cookie=cookie)[2]["results"]
    return next(row for row in rows if row["id"] == cid)


def choices(**changes):
    params = dict(side="frigate", choice="s1_patrouille", versus="ai",
                  weather="random", time="random", length="normal")
    params.update(changes)
    return params


# --- the server half ---------------------------------------------------------------

def test_the_oldest_crew_browser_leads_and_can_hand_over():
    server = CommanderServer()
    server.start("127.0.0.1", 0)
    try:
        _, first, _, body = pair_v2(server, "First")
        assert body["host"] is None                  # no server mode, no leader
        server.set_server_mode(True)
        _, second, _, _ = pair_v2(server, "Second")
        one = request(server, "/api/v2/session", cookie=first)[2]
        two = request(server, "/api/v2/session", cookie=second)[2]
        assert one["host"] == {"generation": one["host"]["generation"], "leader": True}
        assert two["host"] is None
        assert server.leader_name() == "First"
        assert request(server, "/api/v2/host", cookie=first)[0] == 200
        assert request(server, "/api/v2/host", cookie=second)[0] == 403
        assert server.pass_leader(two["ordinal"])
        one_after = request(server, "/api/v2/session", cookie=first)[2]
        assert one_after["host"] is None
        assert request(server, "/api/v2/session", cookie=second)[2]["host"]["leader"] is True
        # The leader never becomes an observer; leaving the room passes the lead.
        assert not server.set_client_grant(two["client_id"], "observer", True)
        assert server.revoke_client(two["client_id"])
        assert server.leader_name() == "First"
        server.set_server_mode(False)
        assert server.leader_name() is None
        assert request(server, "/api/v2/session", cookie=first)[2]["host"] is None
    finally:
        server.stop()


def test_crew_rebase_keeps_sessions_and_leases_under_new_generations():
    server = CommanderServer()
    server.start("127.0.0.1", 0)
    try:
        server.set_server_mode(True)
        _, cookie, _, body = pair_v2(server, "Sonar")
        status, _, taken = request(server, "/api/v2/stations/request", "POST",
                                   {"station": "sonar"}, cookie, body["csrf"])
        assert status == 200 and taken["stations"]["sonar"]["status"] == "mine"
        before = taken["stations"]["sonar"]["station_generation"]
        code = server.pairing_code
        server.crew_rebase()
        after = request(server, "/api/v2/session", cookie=cookie)[2]
        assert after["stations"]["sonar"]["status"] == "mine"
        assert after["stations"]["sonar"]["station_generation"] > before
        assert after["active_generation"] > taken["active_generation"]
        # The leader keeps its host generation: its commands name the world.
        assert after["host"] == taken["host"]
        assert server.pairing_code == code
    finally:
        server.stop()


def test_leader_command_validators_are_closed():
    assert _lobby_set_params(choices())
    for choice in ("daily", "campaign:3", "own:user.night_hunt", "frei_uboot"):
        assert _lobby_set_params(choices(choice=choice))
    for bad in (choices(choice="campaign:x"), choices(choice="own:../x"),
                choices(choice="s99"), choices(side="both"), choices(weather="snow"),
                dict(choices(), extra=1), {**choices(), "versus": True}):
        assert not _lobby_set_params(bad)
    assert _lobby_campaign_params({"side": "uboot", "action": "refit"})
    assert not _lobby_campaign_params({"side": "uboot", "action": "delete"})
    assert _ordinal_params({"ordinal": 3}) and not _ordinal_params({"ordinal": -1})
    for action in ("host_lobby_set", "host_lobby_start", "host_lobby_cancel",
                   "host_lobby_campaign", "host_end_mission", "host_pass_lead"):
        assert V2_ACTION_REGISTRY[action].stations == frozenset({"host"})


# --- the game half -----------------------------------------------------------------

def test_main_menu_entry_and_flag_open_the_host_only_lobby(host):
    assert host.server_mode and host.lobby_active and host.menu_screen == LOBBY_SCREEN
    assert host.lobby.station == HOST_ONLY and host.lobby.server
    assert host.commander.server.server_mode
    # The uConsole may not take a station in server mode.
    host.lobby.row = 2
    key(host, pygame.K_RIGHT)
    assert host.lobby.station == HOST_ONLY
    host.draw()
    key(host, pygame.K_ESCAPE)
    assert host.main_menu and not host.server_mode
    frame(host)
    assert not host.commander.server.server_mode
    assert host.main_menu_sel == host.main_menu_index(SERVER_ENTRY)
    key(host, pygame.K_RETURN)
    assert host.server_mode and host.lobby_active


def test_the_leader_picks_starts_ends_and_the_crew_stays(host):
    leader, _ = join(host, "Lead")
    crew, crew_body = join(host, "Crew")
    assert session_of(host, leader)["lobby"]["server"] is True
    view = request(host.commander.server, "/api/v2/host", cookie=leader)[2]
    assert view["lobby"]["choice"] == "s1_patrouille"
    assert view["lobby"]["daily"]["uboot"] == daily.scenario_for(daily.today(), "uboot")
    # An unknown choice changes nothing; a valid one moves the lobby.
    assert host_command(host, leader, "host_lobby_set", choices(choice="campaign:7"),
                        "a")["reasoncode"] == "lobby_invalid"
    assert host_command(host, leader, "host_lobby_set",
                        choices(side="uboot", choice="s6_aufklaerung", weather="fog"),
                        "b")["status"] == "applied"
    assert (host.lobby.side, host.lobby.scenario_key, host.lobby.weather) == (
        "uboot", "s6_aufklaerung", "fog")
    # A crewmate without the lead cannot send host commands.
    session = session_of(host, crew)
    assert session["host"] is None
    # Not everyone is ready: the first start asks, the second starts.
    assert host_command(host, leader, "host_lobby_start", {}, "c")["reasoncode"] == "lobby_confirm"
    assert host_command(host, leader, "host_lobby_start", {}, "d")["status"] == "applied"
    assert host.lobby.countdown_s == pytest.approx(COUNTDOWN_S, abs=.2)
    host.lobby_tick(COUNTDOWN_S + .1)
    frame(host)
    assert not host.in_menu and host.lobby_round and host.host_only
    assert host.scenario_key == "s6_aufklaerung" and host.umpire_view_active()
    host.draw()
    # The crew is still paired and seated in the new world.
    after = session_of(host, crew)
    assert after["client_id"] == crew_body["client_id"]
    assert any(record["status"] == "mine" for record in after["stations"].values())
    # Missions start from the lobby only.
    assert host_command(host, leader, "host_new_game",
                        {"scenario": "s1_patrouille", "world_mode": "fixed"},
                        "e")["reasoncode"] == "use_lobby"
    assert host_command(host, leader, "host_end_mission", {}, "f")["status"] == "applied"
    assert host.lobby_active and host.server_mode and host.lobby.station == HOST_ONLY


def test_daily_mission_and_campaign_start_from_the_lobby(host):
    leader, _ = join(host, "Lead")
    assert host_command(host, leader, "host_lobby_set", choices(choice="daily"),
                        "a")["status"] == "applied"
    host._start_lobby_mission()
    day = daily.today()
    assert host.seed == daily.seed_for(day, "frigate")
    assert host.scenario_key == daily.scenario_for(day, "frigate")
    assert host.world_mode == daily.WORLD_MODE
    host.server_end_mission()
    frame(host)
    # No campaign yet: the leader starts one, then sails its first hotspot.
    assert host_command(host, leader, "host_lobby_campaign",
                        {"side": "frigate", "action": "refit"}, "b")["reasoncode"] == (
        "campaign_unavailable")
    assert host_command(host, leader, "host_lobby_campaign",
                        {"side": "frigate", "action": "new"}, "c")["status"] == "applied"
    view = request(host.commander.server, "/api/v2/host", cookie=leader)[2]["lobby"]
    spot = view["campaign"]["frigate"]["hotspots"][0]
    assert view["campaign"]["frigate"]["status"] == "active"
    assert host_command(host, leader, "host_lobby_set",
                        choices(choice=f"campaign:{spot['id']}"), "d")["status"] == "applied"
    assert host.lobby.publication()["mission_type"] == "campaign"
    host._start_lobby_mission()
    assert host.campaign_mission and host.campaign_hotspot == spot["id"]
    assert host.scenario_key == spot["scenario"]


def test_leader_actions_outside_server_mode_are_refused(host):
    leader, _ = join(host, "Lead")
    host.leave_server_mode()
    frame(host)
    assert session_of(host, leader)["host"] is None


def test_lobby_room_lists_daily_campaign_and_own_choices():
    room = LobbyRoom()
    room.set_extra_missions({"frigate": {"daily": "s2_doppeljagd",
                                         "campaign": ((4, "s3_abfang", "North Cape"),)}})
    options = room.options()
    assert options[:len(config.scenarios_for_side("frigate"))] == list(
        config.scenarios_for_side("frigate"))
    assert options[-2:] == ["daily", "campaign:4"]
    assert room.set_choice("campaign:4") and room.scenario_key == "s3_abfang"
    assert room.publication()["mission_name"] == "North Cape"
    assert room.set_choice("daily") and room.daily and room.hotspot is None
    assert not room.set_choice("campaign:5")
    # The other side has no campaign: switching drops the choice.
    assert room.set_side("uboot") and room.choice == config.scenarios_for_side("uboot")[0]


def test_a_lobby_round_keeps_its_crew_when_the_mission_changes(tmp_path, monkeypatch):
    """Starting another mission than the menu's prepared one replaces the world;
    the lobby's browsers stay paired and seated (not only in server mode)."""
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = Game(seed=19, start_menu=True, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console.prepare()
    console.hosts = ("127.0.0.1",)
    try:
        game.open_lobby()
        game.lobby.station = HOST_ONLY
        game.lobby.change(1)
        frame(game)
        cookie, body = join(game, "Crew")
        world = id(game.world)
        game._start_lobby_mission()
        for _ in range(3):
            console.pump(game)
            game.update(.05)
        assert id(game.world) != world
        session = session_of(game, cookie)
        assert session["client_id"] == body["client_id"]
        assert session["station"] is not None
    finally:
        console.stop()
        game.audio.shutdown()


def test_server_flag_opens_server_mode(monkeypatch):
    import main as entry
    from src.commander.local import CommanderConsole
    from src.core.preferences import Preferences

    seen = []
    monkeypatch.setattr(CommanderConsole, "autostart", lambda self, solo=False: None)
    monkeypatch.setattr(Game, "run", lambda self: seen.append(self))
    monkeypatch.setattr(entry, "load_preferences", lambda: Preferences(
        language="en", fullscreen=False, audio=False))
    assert entry.main(["--server", "--windowed", "5"]) == 0
    game = seen[0]
    try:
        assert game.server_mode and game.lobby_active and game.lobby.station == HOST_ONLY
    finally:
        game.commander.stop()
    for argv in (["--server", "--multiplayer"], ["--server", "--solo-crew"]):
        with pytest.raises(SystemExit):
            entry.main(argv)


def test_server_status_screen_shows_the_join_line(host, monkeypatch):
    import src.ui.umpire_view as umpire
    from src.core.i18n import localize

    join(host, "Lead")
    host._start_lobby_mission()
    frame(host)
    texts = []
    original = umpire.layout.blit_line

    def spy(surface, text, rect, *args, **kwargs):
        texts.append(localize(text, host.tr))
        return original(surface, text, rect, *args, **kwargs)

    monkeypatch.setattr(umpire.layout, "blit_line", spy)
    umpire.draw(host)
    assert "SERVER MODE" in texts
    assert any("Leader: Lead" in text and host.commander.pairing_code[:3] in text
               for text in texts)


def test_the_crew_follows_the_side_the_leader_picks(host):
    """Against the AI every browser sails the lobby's unit, both ways."""
    frame(host)
    leader, _ = join(host, "Lead")
    crew, _ = join(host, "Crew")

    def held(cookie):
        stations = session_of(host, cookie)["stations"]
        return sorted(name for name, record in stations.items() if record["status"] == "mine")

    assert (held(leader), held(crew)) == (["bridge"], ["sonar"])
    assert host_command(host, leader, "host_lobby_set",
                        choices(side="uboot", choice="s6_aufklaerung"), "a")["status"] == "applied"
    frame(host)
    assert (held(leader), held(crew)) == (["uboot"], ["uboot_sonar"])
    assert session_of(host, leader)["station"] == "uboot"
    assert host_command(host, leader, "host_lobby_set", choices(), "b")["status"] == "applied"
    frame(host)
    assert (held(leader), held(crew)) == (["bridge"], ["sonar"])
    # A second crew keeps each team where it is.
    assert host_command(host, leader, "host_lobby_set", choices(versus="crew"),
                        "c")["status"] == "applied"
    assert host_command(host, leader, "host_lobby_set",
                        choices(side="uboot", choice="s6_aufklaerung", versus="crew"),
                        "d")["status"] == "applied"
    frame(host)
    assert (held(leader), held(crew)) == (["bridge"], ["sonar"])
