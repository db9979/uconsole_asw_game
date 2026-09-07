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


def request(server, path, *, token=None, body=None):
    host, port = server.address
    client = http.client.HTTPConnection(host, port, timeout=3)
    headers = {"Origin": f"http://{host}:{port}"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        client.request("GET" if body is None else "POST", path,
                       body=None if body is None else json.dumps(body), headers=headers)
        response = client.getresponse()
        return response.status, json.loads(response.read())
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
    status, paired = request(console.server, "/api/v1/pair",
                             body={"code": console.pairing_code})
    assert status == 200
    for _ in range(3):
        key(game, pygame.K_DOWN)
    key(game, pygame.K_RETURN)
    key(game, pygame.K_ESCAPE)
    console.pump(game)
    assert game.in_menu and game.main_menu and console.bridge.allowed
    return console.server, paired["token"]


@pytest.mark.parametrize("confirm", [pygame.K_RETURN, pygame.K_SPACE])
def test_normal_menu_start_keeps_world_pairing_grant_and_session(game, paired_menu, confirm):
    server, token = paired_menu
    world, sonar = game.world, game.sonar
    lease = server.lease_generation
    key(game, confirm)  # Main menu -> scenarios.
    key(game, confirm)  # Default patrol -> briefing.
    assert game.menu_screen == "briefing" and game.in_menu
    game.commander.pump(game)
    _, before = request(server, "/api/v1/state", token=token)
    assert before["phase"] == "menu" and not before["commands_allowed"]
    assert before["ownship"]["x"] is None and before["tracks"] == []
    assert request(server, "/api/v1/chart", token=token)[1]["landmasses"] == []
    old_action = dict(id="before-start", session=before["session"],
                      epoch=before["epoch"], revision=before["revision"],
                      action="clear_proposal")
    assert request(server, "/api/v1/commands", token=token, body=old_action)[0] == 202
    game.update(.1)  # Waiting in the briefing cannot dirty the preparation.
    assert game.sim_t == 0.0
    key(game, confirm)
    assert not game.in_menu and not game.main_menu
    assert game.world is world and game.sonar is sonar
    assert game.commander.bridge.status["epoch"] > before["epoch"]
    game.commander.pump(game)
    status, after = request(server, "/api/v1/state", token=token)
    assert status == 200 and after["phase"] == "live" and after["commands_allowed"]
    assert game.commander.server is server and server.lease_generation == lease
    assert game.commander.bridge.allowed and after["session"] == before["session"]
    assert after["epoch"] > before["epoch"]
    assert after["ownship"]["x"] == game.ship.x
    assert after["results"][-1] == dict(id="before-start", status="rejected",
                                       reasoncode="stale_epoch")
    assert request(server, "/api/v1/chart", token=token)[1]["landmasses"]


@pytest.mark.parametrize("change", ["seed", "world_mode", "scenario", "difficulty",
                                    "reset", "load"])
def test_real_replacements_still_revoke_on_next_pump(game, paired_menu, change):
    server, token = paired_menu
    world, sonar = game.world, game.sonar
    session = game.commander.bridge.status["session"]
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
    assert request(server, "/api/v1/state", token=token)[0] == 200
    game.commander.pump(game)
    assert game.commander.server is server
    assert not server.connected and not game.commander.bridge.allowed
    assert game.commander.bridge.status["session"] != session
    assert request(server, "/api/v1/state", token=token)[0] == 401


def test_late_failed_load_preserves_preparation_and_pairing(game, paired_menu, monkeypatch):
    server, token = paired_menu
    world, sonar = game.world, game.sonar
    bridge = game.commander.bridge
    before, lease = bridge.status, server.lease_generation
    restore = Game._restore_state

    def fail_after_restore(candidate, data):
        restore(candidate, data)
        raise ValueError("late candidate failure")

    monkeypatch.setattr(Game, "_restore_state", fail_after_restore)
    with pytest.raises(ValueError):
        game.load_state(game.save_state())
    assert game.world is world and game.sonar is sonar
    assert bridge.status == before and bridge.allowed
    assert server.connected and server.lease_generation == lease
    game.commander.pump(game)
    assert bridge.status == before
    for _ in range(3):
        key(game, pygame.K_RETURN)
    game.commander.pump(game)
    assert game.world is world and game.sonar is sonar
    assert request(server, "/api/v1/state", token=token)[0] == 200
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
