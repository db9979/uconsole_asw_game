"""The observer pseudo-role: host-granted, read-only, at most two, SimLog
included, never a lease, never a command, never persisted."""

import json

from src.commander import server as transport
from src.commander.v2.wire import OBSERVER_MAX, ROLES
from test_commander_commands_v2 import apply_all, command, post
from test_commander_sessions_v2 import pair_v2, projection_states, request, server


def _publish(server, revision="observer-world"):
    states = projection_states(revision)
    chart = dict(protocol=2, revision=revision, size_nm=500, landmasses=[], disclaimer="")
    server.publish_v2(states, {role: chart for role in states})


def _session(server, cookie):
    status, _, body = request(server, "/api/v2/session", cookie=cookie)
    assert status == 200
    return body


def test_observer_views_any_station_read_only_and_gets_the_simlog(server):
    _publish(server)
    _, cookie, _, paired = pair_v2(server, "Observer")
    client = paired["client_id"]
    assert server.set_client_grant(client, "observer", True)
    body = _session(server, cookie)
    assert body["observer"] is True and body["simlog"] is True and body["station"] is None
    assert body["grants"] == {"command": False, "direct_fire": False,
                              "sonar_audio": False, "simlog": True}
    assert server.observer_count() == 1
    assert [row["observer"] for row in server.client_statuses()] == [True]
    # Requests are refused; the view switches through "activate" with generation 0.
    status, _, response = request(server, "/api/v2/stations/request", "POST",
                                  {"station": "bridge"}, cookie, paired["csrf"])
    assert status == 403 and response == {"error": "observer"}
    for station in ("bridge", "uboot_sonar", "opz"):
        status, _, body = request(server, "/api/v2/stations/activate", "POST",
                                  {"station": station, "station_generation": 0,
                                   "active_generation": body["active_generation"]},
                                  cookie, paired["csrf"])
        assert status == 200, station
        assert body["station"] == station and body["station_generation"] == 0
        assert body["stations"][station] == {
            "status": "mine", "requested": False, "request_generation": 0,
            "station_generation": 0,
            "grants": {"command": False, "direct_fire": False, "sonar_audio": False}}
        assert body["grants"]["command"] is False
        # The state is that station's ordinary projection; no lease exists.
        status, _, state = request(server, "/api/v2/state", cookie=cookie)
        assert status == 200 and state["role"] == station
        assert not server.station_leased(station)
    # A wrong generation is stale; other crews see the station as free.
    status, _, _ = request(server, "/api/v2/stations/activate", "POST",
                           {"station": "bridge", "station_generation": 3,
                            "active_generation": body["active_generation"]},
                           cookie, paired["csrf"])
    assert status == 409
    _, crew_cookie, _, crew = pair_v2(server, "Crew")
    assert server.grant_station(crew["client_id"], "opz")
    assert _session(server, crew_cookie)["stations"]["opz"]["status"] == "mine"
    assert _session(server, cookie)["stations"]["opz"]["status"] == "mine"   # the view
    # SimLog is readable; every command is rejected as a role the session lacks.
    status, _, _ = request(server, "/api/v2/simlog", cookie=cookie)
    assert status == 200
    body = _session(server, cookie)
    status, _, response = post(server, cookie, body, command(
        body, command_id="obs-1", world_session="observer-world", world_epoch=0,
        resource_revision=0))
    applied = []
    if status == 202:
        seen = apply_all(server, world_session="observer-world", world_epoch=0,
                         resource_revision=0, seen=applied)
        assert seen == []                                   # nothing reached the game
        status, _, results = request(server, "/api/v2/results", cookie=cookie)
        assert status == 200 and results["results"]
        assert all(result["status"] == "rejected" for result in results["results"])
    else:
        assert status in (403, 409), response
    assert applied == []
    # Releasing the view leaves the observer in the lobby; revoking the grant
    # returns a plain client without SimLog.
    status, _, body = request(server, "/api/v2/stations/release", "POST",
                              {"station": "opz", "station_generation": 0,
                               "active_generation": body["active_generation"]},
                              cookie, paired["csrf"])
    assert status == 200 and body["station"] is None and body["observer"] is True
    assert server.set_client_grant(client, "observer", False)
    body = _session(server, cookie)
    assert body["observer"] is False and body["simlog"] is False
    assert server.observer_count() == 0


def test_observer_grant_is_bounded_and_drops_leases(server):
    _publish(server)
    clients = []
    for name in ("One", "Two", "Three"):
        _, cookie, _, paired = pair_v2(server, name)
        clients.append((cookie, paired))
    assert server.grant_station(clients[0][1]["client_id"], "sonar")
    assert server.set_client_grant(clients[0][1]["client_id"], "observer", True)
    assert not server.station_leased("sonar")               # the lease is gone
    assert server.set_client_grant(clients[1][1]["client_id"], "observer", True)
    assert not server.set_client_grant(clients[2][1]["client_id"], "observer", True)
    assert server.observer_count() == OBSERVER_MAX == 2
    # An observer never gains a lease, not even from the host.
    assert not server.grant_station(clients[0][1]["client_id"], "bridge")
    body = _session(server, clients[0][0])
    assert body["stations"]["bridge"]["status"] == "available"
    # Revoking everything clears observers too.
    server.revoke_all()
    assert server.observer_count() == 0


def test_observer_state_never_carries_truth_or_secrets(server):
    _publish(server)
    _, cookie, _, paired = pair_v2(server, "Watcher")
    assert server.set_client_grant(paired["client_id"], "observer", True)
    body = _session(server, cookie)
    request(server, "/api/v2/stations/activate", "POST",
            {"station": "weapons", "station_generation": 0,
             "active_generation": body["active_generation"]}, cookie, paired["csrf"])
    status, _, state = request(server, "/api/v2/state", cookie=cookie)
    assert status == 200
    forbidden = {"target_id", "track_id", "seed", "rng", "rngs", "csrf", "cookie", "token",
                 "credentials", "settings"}

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)
    assert not forbidden & set(keys(state))
    assert json.dumps(state) == json.dumps(json.loads(transport._json_bytes(state)))
