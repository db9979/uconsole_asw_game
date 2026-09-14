"""Real loopback transport with authoritative main-thread crew acceptance."""

import copy
import http.client
import json
import re

import pygame
import pytest

from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact


def request(server, path, *, cookie=None, csrf=None, body=None):
    host, port = server.address
    connection = http.client.HTTPConnection(host, port, timeout=3)
    headers = {"Origin": f"http://{host}:{port}"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request("POST" if body is not None else "GET", path,
                           body=json.dumps(body) if body is not None else None,
                           headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), json.loads(response.read())
    finally:
        connection.close()


def test_real_http_pair_classify_propose_crew_accept_and_world_replace():
    game = Game(seed=42, audio_enabled=False)
    game.station = Station.SONAR
    game.sim_t = 10.
    contact = Contact(1, game.subs[0].id, "passiv", "sub")
    contact.update_passive(75., .8, .7, "", 10., bearing_uncertainty_deg=2.)
    game.sonar.contacts[contact.target_id] = contact
    game.air_picture.observe(track_id=f"U-{contact.target_id}", target_id=contact.target_id,
        kind="UNKNOWN", source="SONAR-BRG", bearing=75., range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.7, now=10., label="K1")
    game.selected_contact = contact
    game.sonar.listen_bearing = 123.
    console = game.commander
    console.port = 0
    try:
        console.activate(game)
        assert console.address is not None
        console.pump(game)
        assert re.fullmatch(r"[0-9]{3}[A-Z]{3}", console.pairing_code)
        join_code = console.pairing_code
        status, headers, paired = request(console.server, "/api/v2/pair",
            body={"code": console.pairing_code, "name": "Sonar watch"})
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert console.server.grant_station(paired["client_id"], "sonar")
        console.pump(game)
        status, _, session = request(console.server, "/api/v2/session", cookie=cookie)
        assert status == 200 and session["grants"]["command"]
        status, _, state = request(console.server, "/api/v2/state", cookie=cookie)
        assert status == 200 and state["role"] == "sonar"
        track = state["sonar"]["observations"][0]
        assert track["label"].startswith("K")
        assert track["range_nm"] is track["x"] is track["y"] is None
        assert track["classification"] is None
        for seq, (action, params) in enumerate((
                ("sonar_classify", {"ref": track["ref"], "classification": "U_BOOT"}),
                ("propose_target", {"ref": track["ref"]}))):
            command = dict(protocol=2, id=action, seq=seq, station="sonar",
                station_generation=session["station_generation"],
                active_generation=session["active_generation"],
                world_session=state["session"], world_epoch=state["epoch"],
                resource_revision=state["revision"], action=action, params=params)
            before = (contact.player_class, dict(game.opz_affiliations), game.target)
            assert request(console.server, "/api/v2/commands", cookie=cookie,
                           csrf=session["csrf"], body=command)[0] == 202
            assert (contact.player_class, dict(game.opz_affiliations), game.target) == before
            console.pump(game)
            results = request(console.server, "/api/v2/results", cookie=cookie)[2]
            assert results["results"][-1]["status"] == "applied"
            state = request(console.server, "/api/v2/state", cookie=cookie)[2]
        assert contact.player_class == "U_BOOT"
        assert game.target is None
        proposal = request(console.server, "/api/v2/proposals", cookie=cookie)[2]
        assert proposal["target"]["status"] == "pending"
        assert game.selected_contact is contact and game.sonar.listen_bearing == 123.
        assert console.confirm_visible(game)
        console.handle_confirm_key(game, pygame.K_F6)
        assert game.target is contact
        assert game.selected_contact is contact and game.sonar.listen_bearing == 123.
        console.pump(game)
        assert request(console.server, "/api/v2/proposals", cookie=cookie)[2][
            "target"]["status"] == "accepted"
        state = game.save_state()
        encoded = json.dumps(state, allow_nan=False)
        assert cookie not in encoded and join_code not in encoded and "commander" not in state
        session = console.bridge.status["session"]
        malformed = copy.deepcopy(state)
        malformed["ship"]["order_idx"] = 999
        with pytest.raises(ValueError):
            game.load_state(malformed)
        assert console.server.connected and console.bridge.status["session"] == session
        game.load_state(json.loads(encoded))
        assert console.server.connected  # No network side effects inside candidate restoration.
        console.pump(game)
        assert console.bridge.status["session"] != session
        assert console.pairing_code != join_code
        assert not console.bridge.allowed
        assert request(console.server, "/api/v2/state", cookie=cookie)[0] == 401
    finally:
        console.stop()
        game.audio.shutdown()


def test_menu_http_snapshot_does_not_expose_the_pregenerated_world():
    game = Game(seed=42, start_menu=True, audio_enabled=False)
    console = game.commander
    console.port = 0
    try:
        console.activate(game)
        console.pump(game)
        _, headers, _ = request(console.server, "/api/v2/pair",
            body={"code": console.pairing_code, "name": "Observer"})
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        _, _, state = request(console.server, "/api/v2/state", cookie=cookie)
        _, _, chart = request(console.server, "/api/v2/chart", cookie=cookie)
        assert state["phase"] == "menu" and state["role"] is None
        assert "clock" not in state and "environment" not in state
        assert chart["landmasses"] == []
        assert all(key not in json.dumps(state) for key in ("target_id", "sensor_seed", "rng"))
    finally:
        console.stop()
        game.audio.shutdown()


def test_pairing_does_not_restore_a_grant_across_a_new_game():
    game = Game(seed=43, audio_enabled=False)
    assert game.commander.address is None and game.commander.bridge.allowed
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F9))
    assert game.commander_open and game.administration_open
    time_before = game.sim_t
    game.update(.1)
    assert game.sim_t == time_before
    game._open_administration("")
    assert not game.administration_open
