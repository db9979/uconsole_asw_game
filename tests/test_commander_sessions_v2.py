"""Protocol-v2 session tests over the real bounded loopback transport."""

from contextlib import closing
import hashlib
import http.client
import json
import socket
import time
import threading
from types import SimpleNamespace

import pytest

from src.commander import CommanderServer
from src.commander import server as transport


@pytest.fixture
def server(tmp_path, monkeypatch):
    for name in ("index.html", "app.js", "style.css"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(transport.resources, "files", lambda package: tmp_path)
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


def request(server, path, method="GET", body=None, cookie=None, csrf=None, headers=None):
    host, port = server.address
    request_headers = {}
    if method == "POST":
        request_headers.update({
            "Origin": f"http://{host}:{port}",
            "Content-Type": "application/json",
        })
    if cookie is not None:
        request_headers["Cookie"] = cookie
    if csrf is not None:
        request_headers["X-U-Jagd-CSRF"] = csrf
    if headers:
        request_headers.update(headers)
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode("utf-8")
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        response_headers = dict(response.getheaders())
        if response_headers.get("Content-Type", "").startswith("application/json"):
            payload = json.loads(payload)
        return response.status, response_headers, payload


def raw_request(server, payload):
    with closing(socket.create_connection(server.address, timeout=3)) as connection:
        connection.sendall(payload)
        result = bytearray()
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            result.extend(chunk)
        return bytes(result)


def pair_v2(server, name=" Watch Officer "):
    status, headers, body = request(
        server, "/api/v2/pair", "POST", {"code": server.pairing_code, "name": name})
    assert status == 200
    cookie_header = headers["Set-Cookie"]
    prefix = "ujagd_remote_v2="
    assert cookie_header.startswith(prefix)
    token = cookie_header[len(prefix):].split(";", 1)[0]
    return cookie_header, prefix + token, token, body


def projection_states(revision="chart"):
    common = dict(protocol=2, version="test", session=revision, epoch=0,
                  revision=0, seq=1, phase="live", chart_revision=revision,
                  clock={}, environment={}, mission={})
    return {None: {key: value for key, value in common.items()
                   if key not in ("clock", "environment", "mission")} | {"role": None},
            **{role: dict(common, role=role, **{role: {}})
               for role in transport.STATIONS}}


def assert_session(body, name):
    assert set(body) == {
        "protocol", "client_id", "name", "csrf", "station",
        "requested_station", "grants", "ordinal", "station_generation",
        "active_station", "active_generation", "simlog",
        "next_command_seq", "presence", "stations",
    }
    assert body["protocol"] == 2
    assert isinstance(body["client_id"], str) and body["client_id"]
    assert body["name"] == name
    assert isinstance(body["csrf"], str) and body["csrf"]
    assert type(body["ordinal"]) is int and body["ordinal"] >= 0
    assert type(body["station_generation"]) is int and body["station_generation"] >= 0
    assert body["active_station"] is None and body["active_generation"] == 0
    assert body["next_command_seq"] == 0
    assert type(body["presence"]) is float and body["presence"] >= 0
    assert body["station"] is body["requested_station"] is None
    assert body["grants"] == {"command": False, "direct_fire": False, "simlog": False,
                              "sonar_audio": False}
    assert list(body["stations"]) == list(transport.STATIONS)
    assert all(row == {
        "status": "available", "requested": False, "request_generation": 0,
        "station_generation": None,
        "grants": {"command": False, "direct_fire": False, "sonar_audio": False},
    } for row in body["stations"].values())
    assert body["simlog"] is False


def test_pair_sets_host_only_cookie_and_stores_digest_only(server):
    code = server.pairing_code
    set_cookie, cookie, token, body = pair_v2(server)
    assert set_cookie == (
        f"{cookie}; Path=/api/v2; HttpOnly; SameSite=Strict")
    for forbidden in ("Domain=", "Secure", "Max-Age="):
        assert forbidden not in set_cookie
    assert token not in json.dumps(body)
    assert_session(body, "Watch Officer")
    assert server.pairing_code == code
    with server._lock:
        assert list(server._sessions_v2) == [hashlib.sha256(token.encode("ascii")).digest()]
        assert token not in repr(server._sessions_v2)


def test_multiple_pairings_reload_and_read_only_snapshots(server):
    server.publish({"protocol": 1, "tracks": [{"id": "detached"}]}, {"land": [[1, 2]]})
    states = projection_states()
    charts = {role: {"protocol": 2, "revision": "chart", "role_marker": role}
              for role in (None, *transport.STATIONS)}
    server.publish_v2(states, charts)
    code = server.pairing_code
    sessions = []
    for name in ("Alpha", "Bravo", "Charlie"):
        _, cookie, _, body = pair_v2(server, name)
        sessions.append((cookie, body))
        assert server.pairing_code == code
    assert len({body["client_id"] for _, body in sessions}) == 3
    assert len({body["csrf"] for _, body in sessions}) == 3
    for cookie, expected in sessions:
        status, _, body = request(server, "/api/v2/session", cookie=cookie)
        assert status == 200
        assert {key: value for key, value in body.items() if key != "presence"} == {
            key: value for key, value in expected.items() if key != "presence"}
        assert body["presence"] >= expected["presence"]
        assert request(server, "/api/v2/state", cookie=cookie)[2] == states[None]
        assert request(server, "/api/v2/chart", cookie=cookie)[2] == charts[None]
        assert request(server, "/api/v2/simlog", cookie=cookie)[0] == 403


def test_cookie_get_renews_eight_hour_idle_session(server, monkeypatch):
    clock = [float(int(time.monotonic()))]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    _, cookie, _, body = pair_v2(server, "Helm")
    clock[0] += 8 * 60 * 60 - 1
    resumed = request(server, "/api/v2/session", cookie=cookie)[2]
    assert resumed["client_id"] == body["client_id"]
    assert resumed["presence"] == clock[0]
    clock[0] += 8 * 60 * 60 - 1
    assert request(server, "/api/v2/state", cookie=cookie)[0] == 200
    clock[0] += 8 * 60 * 60
    status, headers, response = request(server, "/api/v2/session", cookie=cookie)
    assert status == 401 and response == {"error": "unauthorized"}
    assert headers["Set-Cookie"].endswith("SameSite=Strict; Max-Age=0")


def test_logout_requires_csrf_and_isolates_other_sessions(server):
    code = server.pairing_code
    _, first_cookie, _, first = pair_v2(server, "First")
    _, second_cookie, _, second = pair_v2(server, "Second")
    assert request(server, "/api/v2/logout", "POST", {}, first_cookie, "wrong")[0] == 403
    assert request(server, "/api/v2/logout", "POST", {}, first_cookie,
                   second["csrf"])[0] == 403
    host, port = server.address
    assert request(server, "/api/v2/logout", "POST", {}, first_cookie, first["csrf"],
                   {"Origin": f"http://localhost:{port}"})[0] == 403
    status, headers, body = request(
        server, "/api/v2/logout", "POST", None, first_cookie, first["csrf"])
    assert status == 200 and body == {"status": "logged_out"}
    assert "Max-Age=0" in headers["Set-Cookie"]
    assert request(server, "/api/v2/session", cookie=first_cookie)[0] == 401
    resumed = request(server, "/api/v2/session", cookie=second_cookie)[2]
    assert resumed["client_id"] == second["client_id"]
    assert resumed["presence"] >= second["presence"]
    assert server.pairing_code == code


def test_twelve_session_limit_and_expiry_reopens_slot(server, monkeypatch):
    clock = [float(int(time.monotonic()))]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    cookies = [pair_v2(server, f"Client {index}")[1] for index in range(12)]
    code = server.pairing_code
    status, _, body = request(
        server, "/api/v2/pair", "POST", {"code": code, "name": "Thirteenth"})
    assert status == 429 and body == {"error": "session_limit"}
    clock[0] += 8 * 60 * 60
    assert request(server, "/api/v2/session", cookie=cookies[0])[0] == 401
    assert pair_v2(server, "Replacement")[3]["name"] == "Replacement"


@pytest.mark.parametrize("name", ["", "   ", "x" * 33, "bad\nname", "bad\u200ename"])
def test_pair_name_is_trimmed_bounded_and_control_free(server, name):
    status, _, body = request(
        server, "/api/v2/pair", "POST", {"code": server.pairing_code, "name": name})
    assert status == 400 and body == {"error": "invalid_request"}


@pytest.mark.parametrize("body", [
    {}, {"code": "x"}, {"name": "x"}, {"code": "x", "name": "x", "extra": 1},
    {"code": 1, "name": "x"}, {"code": "x", "name": 1}, [], None,
])
def test_pair_json_shape_is_exact(server, body):
    assert request(server, "/api/v2/pair", "POST", body)[0] == 400


def test_duplicate_headers_and_ambiguous_or_malformed_cookies(server):
    _, cookie, _, session = pair_v2(server)
    host = "%s:%s" % server.address
    for headers in (
        f"Cookie: {cookie}\r\nCookie: {cookie}\r\n",
        "X-U-Jagd-CSRF: one\r\nX-U-Jagd-CSRF: two\r\n",
    ):
        response = raw_request(
            server, f"GET /api/v2/session HTTP/1.1\r\nHost: {host}\r\n{headers}\r\n".encode())
        assert response.startswith(b"HTTP/1.1 400")
    for value in (f"{cookie}; {cookie}", "ujagd_remote_v2", "=value", "other"):
        assert request(server, "/api/v2/session", cookie=value)[0] == 400
    resumed = request(server, "/api/v2/session", cookie=f"other=x; {cookie}")[2]
    assert resumed["client_id"] == session["client_id"]


def test_unknown_revoked_cookie_is_cleared_and_missing_cookie_is_not(server):
    _, cookie, _, _ = pair_v2(server)
    status, headers, _ = request(server, "/api/v2/session", cookie="ujagd_remote_v2=unknown")
    assert status == 401 and "Max-Age=0" in headers["Set-Cookie"]
    status, headers, _ = request(server, "/api/v2/session")
    assert status == 401 and "Set-Cookie" not in headers
    server.revoke()
    status, headers, _ = request(server, "/api/v2/session", cookie=cookie)
    assert status == 401 and "Max-Age=0" in headers["Set-Cookie"]


def test_v1_v2_pairing_is_mutually_exclusive_and_failure_budget_is_shared(server):
    for _ in range(4):
        assert request(server, "/api/v2/pair", "POST", {"code": "wrong", "name": "x"})[0] == 403
    assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    assert request(server, "/api/v2/pair", "POST",
                   {"code": server.pairing_code, "name": "x"})[0] == 429
    server.revoke()
    _, cookie, _, _ = pair_v2(server)
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 409
    server.revoke()
    status, _, body = request(
        server, "/api/v1/pair", "POST", {"code": server.pairing_code})
    assert status == 200
    assert request(server, "/api/v2/pair", "POST",
                   {"code": server.pairing_code, "name": "x"})[0] == 409
    assert request(server, "/api/v2/session", cookie=cookie)[0] == 401


def test_stop_revokes_sessions_across_restart(server):
    code = server.pairing_code
    _, cookie, _, _ = pair_v2(server)
    server.stop()
    server.start("127.0.0.1", 0)
    assert server.pairing_code == code
    status, headers, _ = request(server, "/api/v2/session", cookie=cookie)
    assert status == 401 and "Max-Age=0" in headers["Set-Cookie"]


def test_station_request_requires_cookie_csrf_and_exact_schema(server):
    _, cookie, _, session = pair_v2(server, "Requester")
    route = "/api/v2/stations/request"
    assert request(server, route, "POST", {"station": "bridge"})[0] == 401
    assert request(server, route, "POST", {"station": "bridge"}, cookie)[0] == 403
    assert request(server, route, "POST", {"station": "bridge"}, cookie, "wrong")[0] == 403
    for body in ({}, {"station": "Bridge"}, {"station": "bridge", "extra": 1},
                 {"station": 1}, [], None):
        assert request(server, route, "POST", body, cookie, session["csrf"])[0] == 400

    status, _, requested = request(
        server, route, "POST", {"station": "sonar"}, cookie, session["csrf"])
    assert status == 200
    assert requested["requested_station"] == "sonar"
    assert requested["station"] is None
    assert requested["stations"]["sonar"]["status"] == "available"
    assert requested["stations"]["sonar"]["requested"] is True
    status = server.client_statuses()[0]
    assert status["stations"]["sonar"]["requested"] and status["active_station"] is None

    second = request(server, route, "POST", {"station": "bridge"}, cookie,
                     session["csrf"])[2]
    assert second["stations"]["sonar"]["requested"]
    assert second["stations"]["bridge"]["requested"]
    assert second["requested_station"] == "bridge"  # Canonical compatibility alias.


def test_multi_station_activation_and_station_specific_release_are_exact(server):
    _, cookie, _, paired = pair_v2(server, "Multi watch")
    client_id = paired["client_id"]
    assert server.grant_station(client_id, "bridge")
    assert server.grant_station(client_id, "sonar")
    assert server.set_client_grant(client_id, "bridge", "command", True)
    assert server.set_client_grant(client_id, "sonar", "command", True)
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    assert assigned["active_station"] == "bridge" and assigned["active_generation"] == 1
    assert assigned["stations"]["bridge"]["status"] == "mine"
    assert assigned["stations"]["sonar"]["status"] == "mine"
    sonar_generation = assigned["stations"]["sonar"]["station_generation"]

    activate = "/api/v2/stations/activate"
    exact = {"station": "sonar", "station_generation": sonar_generation,
             "active_generation": assigned["active_generation"]}
    assert request(server, activate, "POST", exact)[0] == 401
    assert request(server, activate, "POST", exact, cookie)[0] == 403
    for invalid in ({}, {"station": "sonar"}, dict(exact, extra=True),
                    dict(exact, station_generation=True)):
        assert request(server, activate, "POST", invalid, cookie, paired["csrf"])[0] == 400
    assert request(server, activate, "POST", {
        "station": "weapons", "station_generation": 0,
        "active_generation": assigned["active_generation"],
    }, cookie, paired["csrf"])[0] == 409
    activated = request(server, activate, "POST", exact, cookie, paired["csrf"])[2]
    assert activated["active_station"] == "sonar"
    assert activated["active_generation"] == 2
    assert activated["grants"]["command"]

    release = "/api/v2/stations/release"
    body = {"station": "sonar", "station_generation": sonar_generation,
            "active_generation": activated["active_generation"]}
    assert request(server, release, "POST", {}, cookie, paired["csrf"])[0] == 400
    released = request(server, release, "POST", body, cookie, paired["csrf"])[2]
    assert released["active_station"] == "bridge" and released["active_generation"] == 3
    assert released["stations"]["bridge"]["status"] == "mine"
    assert released["stations"]["sonar"]["status"] == "available"
    assert request(server, release, "POST", body, cookie, paired["csrf"])[0] == 409


def test_host_revoke_and_grants_are_station_scoped(server):
    _, cookie, _, paired = pair_v2(server, "Scoped watch")
    client_id = paired["client_id"]
    for station in ("bridge", "weapons", "sonar"):
        assert server.grant_station(client_id, station)
        assert server.set_client_grant(client_id, station, "command", True)
    assert server.set_client_grant(client_id, "weapons", "direct_fire", True)
    assert server.set_client_grant(client_id, "sonar", "sonar_audio", True)
    assert server.set_client_grant(client_id, "simlog", True)

    assert server.revoke_station("weapons")
    state = request(server, "/api/v2/session", cookie=cookie)[2]
    assert state["stations"]["weapons"]["status"] == "available"
    assert state["stations"]["bridge"]["grants"]["command"]
    assert state["stations"]["sonar"]["grants"] == {
        "command": True, "direct_fire": False, "sonar_audio": True}
    assert state["simlog"] is True and state["active_station"] == "bridge"
    server.publish_simlog(b'[{"detached":true}]')
    assert request(server, "/api/v2/simlog", cookie=cookie)[2] == [{"detached": True}]
    roster = server.client_statuses()[0]
    assert set(roster) == {"client_id", "name", "ordinal", "active_station",
                           "active_generation", "simlog", "stations", "presence"}
    assert roster["stations"]["bridge"]["leased"]
    assert not roster["stations"]["weapons"]["leased"]


def test_exclusive_grant_takeover_generation_and_occupancy(server):
    _, alpha_cookie, _, alpha = pair_v2(server, "Alpha")
    _, bravo_cookie, _, bravo = pair_v2(server, "Bravo")
    assert server.grant_station(alpha["client_id"], "bridge")
    alpha_assigned = request(server, "/api/v2/session", cookie=alpha_cookie)[2]
    bravo_observer = request(server, "/api/v2/session", cookie=bravo_cookie)[2]
    assert alpha_assigned["station"] == "bridge"
    assert alpha_assigned["station_generation"] == 1
    assert alpha_assigned["stations"]["bridge"]["status"] == "mine"
    assert bravo_observer["stations"]["bridge"]["status"] == "occupied"

    assert server.set_client_grant(alpha["client_id"], "command", True)
    assert server.set_client_grant(alpha["client_id"], "simlog", True)
    assert server.grant_station(bravo["client_id"], "bridge")
    alpha_revoked = request(server, "/api/v2/session", cookie=alpha_cookie)[2]
    bravo_assigned = request(server, "/api/v2/session", cookie=bravo_cookie)[2]
    assert alpha_revoked["station"] is None
    assert alpha_revoked["station_generation"] == 0
    assert alpha_revoked["grants"] == {"command": False, "direct_fire": False, "simlog": True,
                                       "sonar_audio": False}
    assert bravo_assigned["station"] == "bridge"
    assert bravo_assigned["station_generation"] == 2
    assert bravo_assigned["grants"] == {"command": False, "direct_fire": False, "simlog": False,
                                        "sonar_audio": False}


def test_state_and_chart_selection_follows_current_role_atomically(server):
    states = projection_states("r")
    charts = {role: {"protocol": 2, "revision": "r", "role_marker": role}
              for role in (None, *transport.STATIONS)}
    server.publish_v2(states, charts)
    _, first_cookie, _, first = pair_v2(server, "First")
    _, second_cookie, _, second = pair_v2(server, "Second")
    assert request(server, "/api/v2/state", cookie=first_cookie)[2] == states[None]
    assert server.grant_station(first["client_id"], "sonar")
    assert request(server, "/api/v2/state", cookie=first_cookie)[2] == states["sonar"]
    assert request(server, "/api/v2/chart", cookie=first_cookie)[2] == charts["sonar"]
    assert server.grant_station(second["client_id"], "sonar")
    assert request(server, "/api/v2/state", cookie=first_cookie)[2] == states[None]
    assert request(server, "/api/v2/state", cookie=second_cookie)[2] == states["sonar"]
    assert server.revoke_station("sonar")
    assert request(server, "/api/v2/chart", cookie=second_cookie)[2] == charts[None]


def test_v2_publication_is_bounded_exact_and_atomic(server):
    states = projection_states("r")
    charts = {role: {"protocol": 2, "revision": "r"}
              for role in (None, *transport.STATIONS)}
    server.publish_v2(states, charts)
    previous = dict(server._v2_states)
    with pytest.raises(ValueError):
        server.publish_v2({None: states[None]}, charts)
    oversized = dict(states)
    oversized["bridge"] = dict(states["bridge"], payload="x" * (512 * 1024))
    with pytest.raises(ValueError):
        server.publish_v2(oversized, charts)
    assert server._v2_states == previous


def test_capability_invariants_and_release(server):
    _, cookie, _, session = pair_v2(server, "Weapons")
    client_id = session["client_id"]
    assert not server.set_client_grant(client_id, "command", True)
    assert server.set_client_grant(client_id, "simlog", True)
    assert server.grant_station(client_id, "sonar")
    assert server.set_client_grant(client_id, "sonar_audio", True)
    assert request(server, "/api/v2/session", cookie=cookie)[2]["grants"]["command"] is False
    assert server.set_client_grant(client_id, "command", True)
    assert not server.set_client_grant(client_id, "direct_fire", True)
    assert server.grant_station(client_id, "weapons")
    assert not server.set_client_grant(client_id, "weapons", "sonar_audio", True)
    assert server.set_client_grant(client_id, "weapons", "command", True)
    assert server.set_client_grant(client_id, "weapons", "direct_fire", True)
    assert server.set_client_grant(client_id, "weapons", "command", False)
    current = request(server, "/api/v2/session", cookie=cookie)[2]
    assert current["stations"]["weapons"]["grants"] == {
        "command": False, "direct_fire": False, "sonar_audio": False}
    assert current["stations"]["sonar"]["grants"] == {
        "command": True, "direct_fire": False, "sonar_audio": True}
    assert current["simlog"] is True

    assert server.set_client_grant(client_id, "weapons", "command", True)
    assert server.set_client_grant(client_id, "simlog", True)
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    assert server.activate_station(
        client_id, "weapons",
        assigned["stations"]["weapons"]["station_generation"])
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    status, _, released = request(
        server, "/api/v2/stations/release", "POST", {
            "station": "weapons",
            "station_generation": assigned["stations"]["weapons"]["station_generation"],
            "active_generation": assigned["active_generation"],
        }, cookie, session["csrf"])
    assert status == 200 and released["station"] == "sonar"
    assert released["requested_station"] is None
    assert released["stations"]["weapons"]["status"] == "available"
    assert released["grants"] == {"command": True, "direct_fire": False, "simlog": True,
                                   "sonar_audio": True}
    for capability, enabled in (("unknown", True), ("command", 1)):
        with pytest.raises(ValueError):
            server.set_client_grant(client_id, capability, enabled)


def test_presence_expiry_releases_role_but_session_reconnects(server, monkeypatch):
    clock = [float(int(time.monotonic()))]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    _, cookie, _, session = pair_v2(server, "Quiet")
    assert server.grant_station(session["client_id"], "radio")
    assert server.set_client_grant(session["client_id"], "command", True)
    clock[0] += 14.999
    assert server.client_statuses()[0]["active_station"] == "radio"
    clock[0] += .001
    status, _, resumed = request(server, "/api/v2/session", cookie=cookie)
    assert status == 200
    assert resumed["station"] is None and resumed["station_generation"] == 0
    assert resumed["active_generation"] == 2
    assert resumed["grants"] == {"command": False, "direct_fire": False, "simlog": False,
                                  "sonar_audio": False}
    assert resumed["presence"] == clock[0]
    assert server.grant_station(session["client_id"], "radio")
    resumed = request(server, "/api/v2/session", cookie=cookie)[2]
    assert resumed["station_generation"] == 3 and resumed["active_generation"] == 3


def test_independent_revoke_reject_revoke_all_and_roster_order(server):
    code = server.pairing_code
    clients = {}
    for name in ("Unassigned first", "Engine", "Bridge", "Unassigned last"):
        _, cookie, _, session = pair_v2(server, name)
        clients[name] = (cookie, session)
    assert [entry["ordinal"] for entry in server.client_statuses()] == [0, 1, 2, 3]
    assert server.grant_station(clients["Engine"][1]["client_id"], "engine")
    assert server.grant_station(clients["Bridge"][1]["client_id"], "bridge")
    assert [entry["name"] for entry in server.client_statuses()] == [
        "Bridge", "Engine", "Unassigned first", "Unassigned last"]

    requester = clients["Unassigned first"][1]
    assert request(server, "/api/v2/stations/request", "POST", {"station": "opz"},
                   clients["Unassigned first"][0], requester["csrf"])[0] == 200
    assert server.reject_station_request(requester["client_id"])
    assert server.revoke_station("engine")
    assert request(server, "/api/v2/session", cookie=clients["Bridge"][0])[2]["station"] == "bridge"
    assert server.revoke_client(clients["Unassigned last"][1]["client_id"])
    assert request(server, "/api/v2/session", cookie=clients["Unassigned last"][0])[0] == 401
    server.revoke_all()
    roster = server.client_statuses()
    assert [entry["name"] for entry in roster] == ["Unassigned first", "Engine", "Bridge"]
    assert all(entry["active_station"] is None for entry in roster)
    assert all(not any(detail["leased"] or detail["requested"]
                       for detail in entry["stations"].values()) for entry in roster)
    roster[0]["simlog"] = True
    roster[0]["stations"]["bridge"]["grants"]["command"] = True
    detached = server.client_statuses()[0]
    assert not detached["simlog"]
    assert not detached["stations"]["bridge"]["grants"]["command"]
    assert server.pairing_code == code


def test_local_api_validation_and_full_revoke_clears_transient_state(server):
    _, cookie, _, session = pair_v2(server)
    for call in (
        lambda: server.grant_station(session["client_id"], "captain"),
        lambda: server.reject_station_request(None),
        lambda: server.revoke_station("captain"),
        lambda: server.revoke_client(None),
    ):
        with pytest.raises(ValueError):
            call()
    assert not server.grant_station("missing", "bridge")
    assert not server.reject_station_request("missing")
    assert not server.revoke_station("bridge")
    assert not server.revoke_client("missing")
    assert server.grant_station(session["client_id"], "damage")
    server.revoke()
    assert server.client_statuses() == []
    assert request(server, "/api/v2/session", cookie=cookie)[0] == 401


def test_sonar_audio_endpoint_is_bounded_context_bound_and_does_not_renew_presence(server, monkeypatch):
    original_reply = transport._Handler._sonar_audio_reply
    lock_checks = []

    def check_unlocked(handler, *args, **kwargs):
        def acquire():
            acquired = server._lock.acquire(timeout=.3)
            lock_checks.append(acquired)
            if acquired:
                server._lock.release()
        thread = threading.Thread(target=acquire)
        thread.start()
        thread.join(timeout=1)
        return original_reply(handler, *args, **kwargs)

    monkeypatch.setattr(transport._Handler, "_sonar_audio_reply", check_unlocked)
    _, cookie, _, paired = pair_v2(server, "Sonar")
    client_id = paired["client_id"]
    assert server.grant_station(client_id, "sonar")
    assert server.set_client_grant(client_id, "sonar_audio", True)
    session = request(server, "/api/v2/session", cookie=cookie)[2]
    body = {"protocol": 2, "after": None, "world_session": "world-a",
            "world_epoch": 7, "station_generation": session["station_generation"],
            "active_generation": session["active_generation"]}
    presence = server.client_statuses()[0]["presence"]

    assert server.prepare_sonar_audio(world_session="world-a", world_epoch=7) == session["station_generation"]
    assert request(server, "/api/v2/sonar/audio", "POST", body, cookie,
                   session["csrf"])[0] == 204
    assert server.client_statuses()[0]["presence"] == presence

    blocks = [bytes([value]) * transport.SONAR_AUDIO_BYTES for value in (1, 2, 3)]
    for pcm in blocks:
        assert server.publish_sonar_audio(
            pcm, world_session="world-a", world_epoch=7,
            station_generation=session["station_generation"])
    assert len(server._sonar_audio) == 2
    status, headers, payload = request(
        server, "/api/v2/sonar/audio", "POST", body, cookie, session["csrf"])
    assert status == 200 and payload == blocks[-1]
    assert headers["Content-Type"] == "audio/pcm"
    assert headers["Content-Length"] == "2048"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-U-Jagd-PCM"] == "s16le"
    assert headers["X-U-Jagd-Sample-Rate"] == "4096"
    assert headers["X-U-Jagd-Audio-Frames"] == "1024"
    assert headers["X-U-Jagd-Audio-Sequence"] == "3"
    assert headers["X-U-Jagd-Audio-Discontinuity"] == "0"

    body["after"] = 0
    status, headers, payload = request(
        server, "/api/v2/sonar/audio", "POST", body, cookie, session["csrf"])
    assert status == 200 and payload == blocks[-1]
    assert headers["X-U-Jagd-Audio-Discontinuity"] == "1"
    assert lock_checks and all(lock_checks), "audio socket writes must not block the main-thread lock"


def test_sonar_audio_fails_closed_for_auth_schema_role_grant_and_context(server):
    _, cookie, _, paired = pair_v2(server, "Sonar")
    body = {"protocol": 2, "after": None, "world_session": "world-a",
            "world_epoch": 0, "station_generation": 0,
            "active_generation": 0}
    route = "/api/v2/sonar/audio"
    assert request(server, route, "POST", body)[0] == 401
    assert request(server, route, "POST", body, cookie)[0] == 403
    assert request(server, route, "POST", body, cookie, paired["csrf"])[0] == 403
    host, port = server.address
    assert request(server, route, "POST", body, cookie, paired["csrf"],
                   {"Origin": f"http://localhost:{port}"})[0] == 403
    assert server.grant_station(paired["client_id"], "sonar")
    assigned = request(server, "/api/v2/session", cookie=cookie)[2]
    body["station_generation"] = assigned["station_generation"]
    body["active_generation"] = assigned["active_generation"]
    assert request(server, route, "POST", body, cookie, assigned["csrf"])[0] == 403
    assert server.set_client_grant(paired["client_id"], "sonar_audio", True)
    for invalid in (
        {}, dict(body, extra=True), dict(body, protocol=1), dict(body, after=-1),
        dict(body, after=2**53), dict(body, world_epoch=True),
        dict(body, station_generation=True), dict(body, active_generation=True),
        dict(body, world_session=""),
    ):
        assert request(server, route, "POST", invalid, cookie, assigned["csrf"])[0] == 400
    assert request(server, route, "POST", body, cookie, assigned["csrf"])[0] == 503
    server.prepare_sonar_audio(world_session="world-a", world_epoch=0)
    assert request(server, route, "POST", dict(body, world_epoch=1), cookie,
                   assigned["csrf"])[0] == 503
    assert request(server, route, "POST", dict(body, station_generation=0), cookie,
                   assigned["csrf"])[0] == 409
    assert server.set_client_grant(paired["client_id"], "sonar_audio", False)
    assert not server._sonar_audio and server._sonar_audio_context is None
