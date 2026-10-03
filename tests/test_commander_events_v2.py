"""Bounded, role-filtered Remote Crew v2 event publication."""

from contextlib import closing
import http.client
import json
import time

import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import EVENTS_MAX, CommanderServer, STATIONS
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
        alerts = {row["kind"] for row in body["events"]} & {"damage", "threat", "mission"}
        assert alerts == expected[role]
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
    for _ in range(EVENTS_MAX + 12):
        game.feed.add("08:00", "funk", "Log line")
    bridge.pump(game, server, now=time.monotonic() + .6)
    first = events(server, cookie)
    assert len(first["events"]) == EVENTS_MAX
    assert first["latest_seq"] == first["events"][-1]["seq"]
    assert first["events"][0]["seq"] == first["latest_seq"] - EVENTS_MAX + 1
    first["events"].clear()
    assert len(events(server, cookie)["events"]) == EVENTS_MAX

    game.reset(532)
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    assert request(server, "/api/v2/events", cookie=cookie)[0] == 401


def test_mission_log_matches_the_uconsole_f11_log_on_both_sides(game, server):
    """Dominik: the web mission log stayed empty. Every station of a side now
    gets that side's F11 log: the frigate's event feed or the boat log."""
    from src.core.i18n import localize

    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    frigate, _ = pair(server, "Bridge", "bridge")
    boat, _ = pair(server, "Boat", "uboot")
    bridge.pump(game, server, now=time.monotonic() + .3)
    assert game.opfor is not None
    game.feed.add("08:12", "sonar", "Frigate sonar line")
    game.opfor.notice(game.sim_t, "navigation", "Boat navigation line", stamp="08:13")
    bridge.pump(game, server, now=time.monotonic() + .6)

    def log(cookie):
        # No alert has fired yet: every row is a log line.
        return events(server, cookie)["events"]

    rows = log(frigate)
    assert [row["message"] for row in rows] == [
        str(localize(entry.text, game.tr)) for entry in game.feed.entries]
    assert [(row["stamp"], row["tag"]) for row in rows] == [
        (entry.stamp, entry.tag()) for entry in game.feed.entries]
    assert rows[-1] == {"seq": rows[-1]["seq"], "kind": "sonar", "severity": "info",
                        "message": "Frigate sonar line", "stamp": "08:12", "tag": "SONAR"}
    boat_rows = log(boat)
    assert [row["message"] for row in boat_rows] == [
        str(localize(row["text"], game.tr)) for row in game.opfor.feed]
    assert boat_rows[-1]["message"] == "Boat navigation line"
    assert (boat_rows[-1]["stamp"], boat_rows[-1]["tag"]) == ("08:13", "NAV")
    # Each side sees only its own log.
    assert "Boat navigation line" not in {row["message"] for row in rows}
    assert "Frigate sonar line" not in {row["message"] for row in boat_rows}

    # New lines arrive once, numbered after the earlier ones.
    seen = rows[-1]["seq"]
    game.feed.add("08:14", "waffen", "Second line")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    fresh = [row for row in log(frigate) if row["seq"] > seen]
    assert [row["message"] for row in fresh] == ["Second line"]


def test_unchanged_log_is_not_published_again(game, server):
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, "Bridge", "bridge")
    bridge.pump(game, server, now=time.monotonic() + .6)
    published = server._v2_events
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    assert server._v2_events is published
    game.feed.add("08:20", "funk", "Fresh line")
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    assert server._v2_events is not published
    assert events(server, cookie)["events"][-1]["message"] == "Fresh line"
