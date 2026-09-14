"""Bounded, role-filtered Remote Crew v2 event publication."""

from contextlib import closing
import http.client
import json
import time

import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import CommanderServer, STATIONS
from src.core.game import Game
from src.sonar.sonar import Contact


@pytest.fixture
def game():
    instance = Game(seed=531, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()


@pytest.fixture
def server():
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


def request(server, path, method="GET", body=None, cookie=None, csrf=None):
    host, port = server.address
    headers = {}
    if method == "POST":
        headers.update(Origin=f"http://{host}:{port}",
                       **{"Content-Type": "application/json"})
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    payload = None if body is None else json.dumps(body)
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as client:
        client.request(method, path, body=payload, headers=headers)
        response = client.getresponse()
        raw = response.read()
        return response.status, dict(response.getheaders()), (
            json.loads(raw) if raw else None)


def pair(server, name, role=None):
    status, headers, session = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": name})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    if role is not None:
        assert server.grant_station(session["client_id"], role)
    session = request(server, "/api/v2/session", cookie=cookie)[2]
    return cookie, session


def events(server, cookie):
    status, _, body = request(server, "/api/v2/events", cookie=cookie)
    assert status == 200
    assert set(body) == {"protocol", "session", "epoch", "role", "latest_seq",
                         "events"}
    assert body["protocol"] == 2
    return body


def proposal_command(session, bridge, ref):
    status = bridge.status
    return {
        "protocol": 2,
        "id": "target-proposal",
        "seq": 0,
        "station": "sonar",
        "station_generation": session["station_generation"],
        "active_generation": session["active_generation"],
        "world_session": status["session"],
        "world_epoch": status["epoch"],
        "resource_revision": status["revision"],
        "action": "propose_target",
        "params": {"ref": ref},
    }


def test_events_requires_cookie_and_active_role(server):
    assert request(server, "/api/v2/events")[0] == 401
    cookie, _ = pair(server, "Observer")
    assert request(server, "/api/v2/events", cookie=cookie)[0] == 403


def test_event_role_policy_and_context_are_exact(game, server):
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    clients = {role: pair(server, role, role)[0] for role in STATIONS}
    bridge._event("damage", "warning", "commander.event.damage")
    bridge._event("threat", "warning", "commander.event.threat")
    bridge._event("mission", "info", "commander.event.mission.won")
    bridge.pump(game, server, now=time.monotonic() + .6)

    expected = {
        "bridge": {"damage", "threat", "mission"},
        "damage": {"damage", "mission"},
        "opz": {"threat", "mission"},
        "weapons": {"threat", "mission"},
        "sonar": {"mission"},
        "radio": {"mission"},
        "engine": {"mission"},
        "helicopter": {"mission"},
        "eloka": {"mission"},
    }
    for role, cookie in clients.items():
        body = events(server, cookie)
        state = request(server, "/api/v2/state", cookie=cookie)[2]
        assert (body["session"], body["epoch"], body["role"]) == (
            state["session"], state["epoch"], role)
        assert {row["kind"] for row in body["events"]} == expected[role]
        assert body["latest_seq"] >= max(row["seq"] for row in body["events"])


def test_proposal_lifecycle_events_are_visible_only_to_origin_session_and_role(
        game, server):
    contact = Contact(1, 7654321, "passiv", "sub")
    contact.update_passive(90.0, .8, .8, "hidden", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    sonar_cookie, sonar = pair(server, "Origin sonar", "sonar")
    bridge_cookie, _ = pair(server, "Bridge", "bridge")
    bridge.pump(game, server, now=time.monotonic() + .6)
    ref = request(server, "/api/v2/state", cookie=sonar_cookie)[2][
        "sonar"]["observations"][0]["ref"]
    body = proposal_command(sonar, bridge, ref)
    assert request(server, "/api/v2/commands", "POST", body, sonar_cookie,
                   sonar["csrf"])[0] == 202
    bridge.pump(game, server, now=time.monotonic() + 1.2)

    assert any(row["kind"] == "proposal"
               for row in events(server, sonar_cookie)["events"])
    assert all(row["kind"] != "proposal"
               for row in events(server, bridge_cookie)["events"])

    assert server.grant_station(sonar["client_id"], "bridge")
    refreshed = request(server, "/api/v2/session", cookie=sonar_cookie)[2]
    generation = refreshed["stations"]["bridge"]["station_generation"]
    assert server.activate_station(sonar["client_id"], "bridge", generation)
    immediate = events(server, sonar_cookie)
    assert immediate["role"] == "bridge"
    assert all(row["kind"] != "proposal" for row in immediate["events"])

    replacement_cookie, _ = pair(server, "Replacement sonar", "sonar")
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    assert all(row["kind"] != "proposal"
               for row in events(server, sonar_cookie)["events"])
    assert all(row["kind"] != "proposal"
               for row in events(server, replacement_cookie)["events"])


def test_events_are_bounded_detached_and_reset_with_world(game, server):
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, "Bridge", "bridge")
    for _ in range(140):
        bridge._event("mission", "info", "commander.event.mission.won")
    bridge.pump(game, server, now=time.monotonic() + .6)
    first = events(server, cookie)
    assert len(first["events"]) == 128
    assert first["latest_seq"] == first["events"][-1]["seq"]
    assert first["events"][0]["seq"] == first["latest_seq"] - 127
    first["events"].clear()
    assert len(events(server, cookie)["events"]) == 128

    game.reset(532)
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    assert request(server, "/api/v2/events", cookie=cookie)[0] == 401
