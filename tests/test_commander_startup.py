"""Menu preparation is not a world replacement; actual replacements still revoke."""

import copy
import http.client
import json

import pygame
import pytest

from src.core import config
from src.core.game import Game, Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo


def key(game, value):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value))


def request(server, path, *, cookie=None, csrf=None, body=None):
    host, port = server.address
    client = http.client.HTTPConnection(host, port, timeout=3)
    headers = {"Origin": f"http://{host}:{port}"}
    if cookie is not None:
        headers["Cookie"] = cookie
    if csrf is not None:
        headers["X-U-Jagd-CSRF"] = csrf
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        client.request("GET" if body is None else "POST", path,
                       body=None if body is None else json.dumps(body), headers=headers)
        response = client.getresponse()
        return response.status, dict(response.getheaders()), json.loads(response.read())
    finally:
        client.close()


@pytest.fixture
def game():
    game = Game(seed=42, start_menu=True, audio_enabled=False)
    yield game
    game.commander.stop()
    game.audio.shutdown()


@pytest.fixture
def paired_menu(game):
    console = game.commander
    console.port = 0
    key(game, pygame.K_F9)
    key(game, pygame.K_RETURN)
    console.pump(game)
    status, headers, paired = request(console.server, "/api/v2/pair",
        body={"code": console.pairing_code, "name": "Bridge watch"})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert console.server.grant_station(paired["client_id"], "bridge")
    key(game, pygame.K_ESCAPE)
    console.pump(game)
    assert game.in_menu and game.main_menu and console.bridge.allowed
    return console.server, cookie, paired


@pytest.mark.parametrize("confirm", [pygame.K_RETURN, pygame.K_SPACE])
def test_normal_menu_start_keeps_world_pairing_grant_and_session(game, paired_menu, confirm):
    server, cookie, paired = paired_menu
    world, sonar = game.world, game.sonar
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    station_generation = assigned["station_generation"]
    key(game, confirm)  # Main menu -> scenarios.
    key(game, confirm)  # Default patrol -> briefing.
    assert game.menu_screen == "briefing" and game.in_menu
    game.commander.pump(game)
    before = request(server, "/api/v2/state", cookie=cookie)[2]
    assert before["phase"] == "menu" and before["role"] is None
    assert request(server, "/api/v2/chart", cookie=cookie)[2]["landmasses"] == []
    game.update(.1)  # Waiting in the briefing cannot dirty the preparation.
    assert game.sim_t == 0.0
    key(game, confirm)
    assert not game.in_menu and not game.main_menu
    assert game.world is world and game.sonar is sonar
    assert game.commander.bridge.status["epoch"] > before["epoch"]
    game.commander.pump(game)
    status, _, after = request(server, "/api/v2/state", cookie=cookie)
    assert status == 200 and after["phase"] == "live" and after["role"] == "bridge"
    current = request(server, "/api/v2/session", cookie=cookie)[2]
    assert current["station_generation"] == station_generation
    assert current["client_id"] == paired["client_id"]
    assert game.commander.server is server
    assert game.commander.bridge.allowed and after["session"] == before["session"]
    assert after["epoch"] > before["epoch"]
    assert after["bridge"]["navigation"]["x"] == game.ship.x
    assert request(server, "/api/v2/chart", cookie=cookie)[2]["landmasses"]


@pytest.mark.parametrize("change", ["seed", "world_mode", "scenario", "difficulty",
                                    "reset", "load"])
def test_real_replacements_still_revoke_on_next_pump(game, paired_menu, change):
    server, cookie, _ = paired_menu
    world, sonar = game.world, game.sonar
    session = game.commander.bridge.status["session"]
    join_code = server.pairing_code
    if change == "reset":
        game.reset(game.seed)  # Even an identical explicit reset is a replacement.
    elif change == "load":
        game.load_state(game.save_state())  # Includes a sim_t == 0 save.
    else:
        key(game, pygame.K_RETURN)
        if change == "seed":
            key(game, pygame.K_r)
        elif change == "world_mode":
            key(game, pygame.K_w)
        elif change == "scenario":
            key(game, pygame.K_2)
        else:
            key(game, pygame.K_4)
        key(game, pygame.K_RETURN)
        if change == "difficulty":
            key(game, pygame.K_3)
        key(game, pygame.K_RETURN)
    assert game.world is not world and game.sonar is not sonar
    assert server.connected and game.commander.bridge.allowed
    assert request(server, "/api/v2/state", cookie=cookie)[0] == 200
    game.commander.pump(game)
    assert server.pairing_code != join_code
    assert game.commander.server is server
    assert not server.connected and not game.commander.bridge.allowed
    assert game.commander.bridge.status["session"] != session
    assert request(server, "/api/v2/state", cookie=cookie)[0] == 401


def test_late_failed_load_preserves_preparation_and_pairing(game, paired_menu, monkeypatch):
    server, cookie, _ = paired_menu
    world, sonar = game.world, game.sonar
    bridge = game.commander.bridge
    before = bridge.status
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    restore = Game._restore_state

    def fail_after_restore(candidate, data):
        restore(candidate, data)
        raise ValueError("late candidate failure")

    monkeypatch.setattr(Game, "_restore_state", fail_after_restore)
    with pytest.raises(ValueError):
        game.load_state(game.save_state())
    assert game.world is world and game.sonar is sonar
    assert bridge.status == before and bridge.allowed
    assert server.connected
    assert request(server, "/api/v2/session", cookie=cookie)[2][
        "station_generation"] == assigned["station_generation"]
    game.commander.pump(game)
    assert bridge.status == before
    for _ in range(3):
        key(game, pygame.K_RETURN)
    game.commander.pump(game)
    assert game.world is world and game.sonar is sonar
    assert request(server, "/api/v2/state", cookie=cookie)[0] == 200
    assert bridge.allowed and bridge.status["session"] == before["session"]


@pytest.mark.parametrize("field,value", [
    ("sim_t", .1), ("mission_time", .1), ("custom_mission_definition", {}),
    ("mission_result", "SIEG"), ("game_over", True), ("running", False),
    ("paused", True), ("level", "harte"),
])
def test_nonpristine_or_changed_configuration_is_not_reused(game, field, value):
    world = game.world
    setattr(game, field, value)
    game._start_menu_mission()
    assert game.world is not world
    assert game.sim_t == game.mission_time == 0.0
    assert game.custom_mission_definition is None and game.mission_result is None
    assert not game.game_over and game.running and not game.paused


def test_preparation_is_one_use_and_load_identity_cannot_reuse_it(game):
    world = game.world
    game._start_menu_mission()
    assert game.world is world
    game.in_menu = True
    game._start_menu_mission()  # No simulation tick is needed to consume it.
    assert game.world is not world
    game.in_menu = True
    game.reset(game.seed)
    game.load_state(game.save_state())
    loaded = game.world
    game.in_menu = True
    game._start_menu_mission()
    assert game.world is not loaded


@pytest.mark.parametrize("scenario", config.SCENARIO_ORDER)
def test_prepared_start_matches_fresh_reset_and_continuation(game, monkeypatch, scenario):
    # Hold allocator baselines equal, rather than hiding IDs or sensor seeds in
    # the comparison. Reset legitimately allocates a new set of entity IDs.
    classes = (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo)
    baseline = {cls: cls._next_id for cls in classes}
    game.reset(game.seed, scenario)
    game._t = 123.0  # Menu wall time is not simulation time.
    game._start_menu_mission()
    prepared = copy.deepcopy(game.save_state())
    for _ in range(3):
        game.update(.1)
    continued = copy.deepcopy(game.save_state())
    for cls, next_id in baseline.items():
        monkeypatch.setattr(cls, "_next_id", next_id)
    game.reset(game.seed, scenario)
    assert game.save_state() == prepared
    for _ in range(3):
        game.update(.1)
    assert game.save_state() == continued
