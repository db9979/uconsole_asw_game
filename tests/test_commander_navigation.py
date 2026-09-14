"""Remote Crew v2 proposals stage requests for local host decisions."""

from contextlib import closing
from copy import deepcopy
from itertools import combinations
import http.client
import json
import time

import pygame
import pytest

from src.commander.access_point import HotspotDetails
from src.commander.bridge import CommanderBridge
from src.commander.server import CommanderServer
from src.core import config
from src.core.game import Game
from src.core.i18n import Translator, pseudolocale
from src.sonar.sonar import Contact
from src.ui import layout


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()
    layout.configure_for(large_text=False)


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
        data = json.loads(raw) if raw else None
        return response.status, dict(response.getheaders()), data


def pair(server, name, role):
    status, headers, session = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": name})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert server.grant_station(session["client_id"], role)
    session = request(server, "/api/v2/session", cookie=cookie)[2]
    return cookie, session


def command(session, bridge, action, params, *, command_id="proposal", seq=0):
    status = bridge.status
    return {
        "protocol": 2,
        "id": command_id,
        "seq": seq,
        "station": session["station"],
        "station_generation": session["station_generation"],
        "active_generation": session["active_generation"],
        "world_session": status["session"],
        "world_epoch": status["epoch"],
        "resource_revision": status["revision"],
        "action": action,
        "params": params,
    }


def post(server, cookie, session, body):
    return request(server, "/api/v2/commands", "POST", body, cookie,
                   session["csrf"])


def result(server, cookie):
    status, _, body = request(server, "/api/v2/results", cookie=cookie)
    assert status == 200 and body["protocol"] == 2
    return body["results"][-1]


def begin(game, server):
    bridge = game.commander.bridge
    bridge.pump(game, server, now=time.monotonic())
    return bridge


def sonar_contact(game):
    contact = Contact(7, 7654321, "passiv", "sub")
    contact.update_passive(90.0, .8, .8, "hidden-class", game.sim_t)
    game.sonar.contacts[contact.target_id] = contact
    return contact


def proposals(server, cookie):
    status, _, body = request(server, "/api/v2/proposals", cookie=cookie)
    assert status == 200
    assert set(body) == {"protocol", "session", "epoch", "role", "target",
                         "navigation"}
    assert body["protocol"] == 2
    return body


def test_protocol_v1_routes_and_legacy_validator_are_absent(server):
    import src.commander.server as transport

    assert not hasattr(transport, "_command_valid")
    for path in ("/api/v1/pair", "/api/v1/state", "/api/v1/chart",
                 "/api/v1/commands", "/api/v1/results", "/api/v1/simlog",
                 "/api/v1/anything"):
        assert request(server, path)[0] == 404
        assert request(server, path, "POST", {})[0] == 404


@pytest.mark.parametrize("params", [
    {}, {"course": True}, {"speed_kn": False}, {"course": None},
    {"speed_kn": None}, {"course": "90"}, {"course": float("nan")},
    {"course": float("inf")}, {"course": -float("inf")},
    {"speed_kn": float("nan")}, {"speed_kn": float("inf")},
    {"course": -1}, {"course": 360}, {"speed_kn": -1},
    {"speed_kn": config.SHIP_SPEED_MAX_KN + .01},
    {"course": 90, "track": "any"}, {"course": 90, "value": None},
    {"course": 90, "speed_kn": True},
])
def test_navigation_params_are_closed_finite_and_bounded(game, server, params):
    bridge = begin(game, server)
    cookie, session = pair(server, "Navigator", "bridge")
    body = command(session, bridge, "propose_navigation", params)
    assert post(server, cookie, session, body)[0] == 400
    bridge.pump(game, server, now=time.monotonic())
    assert bridge.navigation_proposal is None


@pytest.mark.parametrize("params", [
    {"course": 0}, {"course": 359.999}, {"speed_kn": 0},
    {"speed_kn": config.SHIP_SPEED_MAX_KN},
    {"course": 123.5, "speed_kn": 17.25},
])
def test_navigation_stages_only_and_local_accept_applies_atomically(
        game, server, params):
    bridge = begin(game, server)
    cookie, session = pair(server, "Navigator", "bridge")
    before = deepcopy(game.ship.__dict__)
    body = command(session, bridge, "propose_navigation", params)
    assert post(server, cookie, session, body)[0] == 202
    assert bridge.navigation_proposal is None and game.ship.__dict__ == before

    bridge.pump(game, server, now=time.monotonic())
    assert result(server, cookie)["reasoncode"] == "ok"
    pending = proposals(server, cookie)["navigation"]
    assert pending == {"course": params.get("course"),
                       "speed_kn": params.get("speed_kn"), "status": "pending"}
    assert game.ship.__dict__ == before
    assert "navigation_proposal" not in json.dumps(game.save_state())

    detached = bridge.navigation_proposal
    detached["course"] = -1
    assert bridge.navigation_proposal["course"] == params.get("course")
    game.commander_open = True
    assert bridge.accept_navigation(game)
    assert not bridge.accept_navigation(game)
    assert game.ship.target_course == params.get("course", before["target_course"])
    assert game.ship.target_speed == params.get("speed_kn", before["target_speed"])
    bridge.pump(game, server, now=time.monotonic())
    assert proposals(server, cookie)["navigation"]["status"] == "accepted"


def test_navigation_reject_and_atomic_local_revalidation(game, server, monkeypatch):
    bridge = begin(game, server)
    cookie, session = pair(server, "Navigator", "bridge")
    body = command(session, bridge, "propose_navigation",
                   {"course": 123, "speed_kn": 19})
    assert post(server, cookie, session, body)[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    before = deepcopy(game.ship.__dict__)
    game.commander_open = True
    monkeypatch.setattr(game.damage, "station_down",
                        lambda station: station == "bridge")
    assert not bridge.accept_navigation(game)
    assert bridge.navigation_error == "commander.local.navigation.bridge_down"
    assert game.ship.__dict__ == before
    assert bridge.reject_navigation(game)
    assert game.ship.__dict__ == before


def test_command_grant_toggle_cannot_restore_proposal_authority(game, server):
    bridge = begin(game, server)
    cookie, session = pair(server, "Navigator", "bridge")
    body = command(session, bridge, "propose_navigation", {"course": 123})
    assert post(server, cookie, session, body)[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert bridge.navigation_proposal["status"] == "pending"

    assert server.set_client_grant(session["client_id"], "command", False)
    assert server.set_client_grant(session["client_id"], "command", True)
    game.commander_open = True
    assert not bridge.accept_navigation(game)
    assert bridge.navigation_proposal["status"] == "expired"


@pytest.mark.parametrize("action,params,role", [
    ("propose_target", {"ref": "opaque"}, "bridge"),
    ("clear_target_proposal", {}, "bridge"),
    ("propose_navigation", {"course": 90}, "sonar"),
])
def test_proposal_actions_are_role_scoped(game, server, action, params, role):
    bridge = begin(game, server)
    cookie, session = pair(server, "Wrong role", role)
    body = command(session, bridge, action, params)
    body["station"] = "sonar" if action != "propose_navigation" else "bridge"
    assert post(server, cookie, session, body)[0] in (400, 403)


@pytest.mark.parametrize("action,params", [
    ("propose_target", {}), ("propose_target", {"ref": "x", "extra": 1}),
    ("propose_target", {"ref": True}),
    ("clear_target_proposal", {"ref": "x"}),
])
def test_target_proposal_params_are_exact(game, server, action, params):
    bridge = begin(game, server)
    cookie, session = pair(server, "Sonar", "sonar")
    assert post(server, cookie, session,
                command(session, bridge, action, params))[0] == 400


def test_target_proposal_uses_observed_ref_and_clear_is_remote_rejection(
        game, server):
    target = sonar_contact(game)
    bridge = begin(game, server)
    cookie, session = pair(server, "Sonar", "sonar")
    bridge.pump(game, server, now=time.monotonic())
    state = request(server, "/api/v2/state", cookie=cookie)[2]
    ref = state["sonar"]["observations"][0]["ref"]
    body = command(session, bridge, "propose_target", {"ref": ref})
    assert post(server, cookie, session, body)[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert result(server, cookie)["reasoncode"] == "ok"
    assert proposals(server, cookie)["target"]["status"] == "pending"
    assert game.target is not target

    clear = command(session, bridge, "clear_target_proposal", {},
                    command_id="clear", seq=1)
    assert post(server, cookie, session, clear)[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert result(server, cookie)["reasoncode"] == "ok"
    assert proposals(server, cookie)["target"] is None
    assert game.target is not target


@pytest.mark.parametrize("accepted", [True, False])
def test_local_host_decides_target_proposal_authoritatively(
        game, server, accepted):
    target = sonar_contact(game)
    bridge = begin(game, server)
    cookie, session = pair(server, "Sonar", "sonar")
    bridge.pump(game, server, now=time.monotonic())
    ref = request(server, "/api/v2/state", cookie=cookie)[2][
        "sonar"]["observations"][0]["ref"]
    assert post(server, cookie, session, command(
        session, bridge, "propose_target", {"ref": ref}))[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert game.target is not target

    game.commander_open = True
    decide = bridge.accept_proposal if accepted else bridge.reject_proposal
    assert decide(game)
    assert (game.target is target) is accepted
    bridge.pump(game, server, now=time.monotonic())
    assert proposals(server, cookie)["target"]["status"] == (
        "accepted" if accepted else "rejected")


def test_each_origin_sees_only_its_applicable_proposal(game, server):
    sonar_contact(game)
    bridge = begin(game, server)
    sonar_cookie, sonar = pair(server, "Sonar", "sonar")
    bridge_cookie, helm = pair(server, "Helm", "bridge")
    bridge.pump(game, server, now=time.monotonic())
    ref = request(server, "/api/v2/state", cookie=sonar_cookie)[2][
        "sonar"]["observations"][0]["ref"]
    assert post(server, sonar_cookie, sonar, command(
        sonar, bridge, "propose_target", {"ref": ref}, command_id="target"))[0] == 202
    assert post(server, bridge_cookie, helm, command(
        helm, bridge, "propose_navigation", {"course": 123},
        command_id="navigation"))[0] == 202
    bridge.pump(game, server, now=time.monotonic())

    sonar_view = proposals(server, sonar_cookie)
    bridge_view = proposals(server, bridge_cookie)
    assert sonar_view["role"] == "sonar" and sonar_view["target"] is not None
    assert sonar_view["navigation"] is None
    assert bridge_view["role"] == "bridge" and bridge_view["target"] is None
    assert bridge_view["navigation"] is not None


def test_proposals_route_requires_cookie_and_active_role(server):
    assert request(server, "/api/v2/proposals")[0] == 401
    status, headers, _ = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": "Observer"})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    assert request(server, "/api/v2/proposals", cookie=cookie)[0] == 403


@pytest.mark.parametrize("change", [
    "switch", "revoke", "takeover", "disconnect", "world",
])
def test_pending_navigation_cannot_be_inherited_after_context_loss(
        game, server, change):
    bridge = begin(game, server)
    cookie, session = pair(server, "Origin", "bridge")
    assert post(server, cookie, session, command(
        session, bridge, "propose_navigation", {"course": 123}))[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert proposals(server, cookie)["navigation"]["status"] == "pending"

    inheritor_cookie = None
    if change == "switch":
        assert server.grant_station(session["client_id"], "sonar")
        refreshed = request(server, "/api/v2/session", cookie=cookie)[2]
        generation = refreshed["stations"]["sonar"]["station_generation"]
        assert server.activate_station(session["client_id"], "sonar", generation)
        immediate = proposals(server, cookie)
        assert immediate["role"] == "sonar"
        assert immediate["target"] is None and immediate["navigation"] is None
    elif change == "revoke":
        assert server.revoke_station("bridge")
    elif change == "takeover":
        inheritor_cookie, inheritor = pair(server, "Replacement", "bridge")
        assert inheritor["station"] == "bridge"
    elif change == "disconnect":
        assert request(server, "/api/v2/logout", "POST", {}, cookie,
                       session["csrf"])[0] == 200
    else:
        game.reset(32)
    before = deepcopy(game.ship.__dict__)
    bridge.pump(game, server, now=time.monotonic())
    game.commander_open = True
    assert not bridge.accept_navigation(game)
    assert game.ship.__dict__ == before
    if change == "switch":
        assert proposals(server, cookie)["navigation"] is None
        refreshed = request(server, "/api/v2/session", cookie=cookie)[2]
        generation = refreshed["stations"]["bridge"]["station_generation"]
        assert server.activate_station(session["client_id"], "bridge", generation)
        assert proposals(server, cookie)["navigation"] is None
    elif change == "revoke":
        assert request(server, "/api/v2/proposals", cookie=cookie)[0] == 403
    elif change == "takeover":
        assert request(server, "/api/v2/proposals", cookie=cookie)[0] == 403
        assert proposals(server, inheritor_cookie)["navigation"] is None
    else:
        assert request(server, "/api/v2/proposals", cookie=cookie)[0] == 401


def test_target_proposal_expires_when_observed_contact_binding_disappears(
        game, server):
    target = sonar_contact(game)
    bridge = begin(game, server)
    cookie, session = pair(server, "Sonar", "sonar")
    bridge.pump(game, server, now=time.monotonic())
    ref = request(server, "/api/v2/state", cookie=cookie)[2][
        "sonar"]["observations"][0]["ref"]
    assert post(server, cookie, session, command(
        session, bridge, "propose_target", {"ref": ref}))[0] == 202
    bridge.pump(game, server, now=time.monotonic())
    assert proposals(server, cookie)["target"]["status"] == "pending"

    del game.sonar.contacts[target.target_id]
    bridge.pump(game, server, now=time.monotonic() + .6)
    proposal = proposals(server, cookie)["target"]
    assert proposal is None or proposal["status"] == "expired"
    game.commander_open = True
    assert not bridge.accept_proposal(game)


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("network_mode", ["lan", "hotspot"])
def test_native_five_rows_nonoverlap_and_roomy_join_code(
        game, language, large, network_mode):
    console = game.commander
    console.bridge = CommanderBridge()
    console.bridge._navigation_proposal = {
        "course": 359.999, "speed_kn": 25, "status": "pending"}
    console.address = ("127.0.0.1", 8765)
    console.pairing_code = "123ABC"
    console.network_mode = network_mode
    if network_mode == "hotspot":
        console.hotspot.state = "running"
        console.hotspot.details = HotspotDetails(
            ssid="U-Jagd-7KPX", password="SecureCrewKey2345",
            address="10.42.0.1", interface="wlan0")
    game.tr = (Translator("en", pseudolocale()).t if language == "pseudo"
               else Translator(language).t)
    layout.configure_for(large_text=large)
    console.error = "commander.local.navigation.bridge_down"
    with layout.capture_text() as text:
        console.draw(game)
    assert len(console.row_rects()) == 5
    for entry in text:
        assert entry["bounds"].contains(entry["rect"])
        assert pygame.Rect(0, 0, 1280, 720).contains(entry["bounds"])
        assert "commander." not in entry["text"]
    assert all(not a["rect"].colliderect(b["rect"])
               for a, b in combinations(text, 2))
    join = next(entry for entry in text if entry["text"] == "123 ABC")
    assert join["rect"].height >= 60
    game.commander_open = True
    console.selection = 0
    for expected in (1, 2, 3, 4, 0):
        console.handle_key(game, pygame.K_DOWN)
        assert console.selection == expected
    console.handle_key(game, pygame.K_UP)
    assert console.selection == 4
