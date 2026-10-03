"""Remote Crew lock scope and per-source rate limits (audit 2026-10-03, C8-C11).

Slow work (host commands, scrypt) never runs under the server's global lock,
polls never re-parse the full role state, failed logins and pairings are
counted per source address, and an observer never cuts an operator's audio.
"""

from contextlib import closing
import http.client
import json
import threading
import time

from src.commander import web_auth as web_auth_module
from src.commander.server import CommanderServer
from src.commander.web_auth import FailureLimiter, WebHostAuth
from test_commander_commands_v2 import command, pair, post, results, server  # noqa: F401
from test_commander_sessions_v2 import pair_v2, request as session_request

PASSWORD = "a long private password"


def _lock_free_from_another_thread(lock):
    """True when a thread other than the caller can take ``lock`` now."""
    outcome = []

    def probe():
        acquired = lock.acquire(timeout=1.0)
        outcome.append(acquired)
        if acquired:
            lock.release()

    worker = threading.Thread(target=probe)
    worker.start()
    worker.join(2.0)
    return outcome == [True]


# C8 -------------------------------------------------------------------------

def test_apply_runs_outside_the_global_lock_and_completes_exactly_once(server):
    cookie, session = pair(server, "Sonar", "sonar")
    assert post(server, cookie, session, command(session, command_id="slow"))[0] == 202
    envelope = server.drain_commands_v2()[0]
    calls = []

    def apply(action, params):
        # A transport thread (poll, push, audio, pairing) can take the lock
        # while the command runs, and may even revoke the station meanwhile.
        calls.append(_lock_free_from_another_thread(server._lock))
        revoker = threading.Thread(target=server.revoke_station, args=("sonar",))
        revoker.start()
        revoker.join(2.0)
        return True

    assert server.apply_command_v2(
        envelope, now=time.monotonic(), phase="live", world_session="world",
        world_epoch=3, resource_revision=5, apply=apply)
    assert calls == [True]
    # Recorded once; a second application of the same envelope is refused
    # without calling apply again.
    assert not server.apply_command_v2(
        envelope, now=time.monotonic(), phase="live", world_session="world",
        world_epoch=3, resource_revision=5, apply=lambda *_: calls.append("again"))
    assert calls == [True]
    rows = [row for row in results(server, cookie) if row["id"] == "slow"]
    assert [(row["status"], row["reasoncode"]) for row in rows] == [("applied", "ok")]


def test_rejected_command_never_reaches_apply(server):
    cookie, session = pair(server, "Sonar", "sonar")
    assert post(server, cookie, session, command(session, command_id="stale"))[0] == 202
    envelope = server.drain_commands_v2()[0]
    calls = []
    assert server.apply_command_v2(
        envelope, now=time.monotonic(), phase="live", world_session="world",
        world_epoch=4, resource_revision=5, apply=lambda *_: calls.append(1))
    assert calls == []
    rows = [row for row in results(server, cookie) if row["id"] == "stale"]
    assert [(row["status"], row["reasoncode"]) for row in rows] == [
        ("rejected", "stale_world_epoch")]


# C9 -------------------------------------------------------------------------

def test_polls_use_the_stored_head_and_never_parse_the_role_state(server):
    _, cookie, _, paired = pair_v2(server, "Sonar")
    assert server.grant_station(paired["client_id"], "sonar")
    assert server.set_client_grant(paired["client_id"], "simlog", True)
    with server._lock:
        # Not JSON at all: a route that re-parsed it would fail with 400.
        server._v2_states["sonar"] = b"\xff not json"
        server._v2_state_heads["sonar"] = ("head-world", 7)
    for path, extra in (("/api/v2/proposals", {"target": None, "navigation": None}),
                        ("/api/v2/events", {"latest_seq": 0, "events": []}),
                        ("/api/v2/simlog", {"entries": []})):
        status, _, body = session_request(server, path, cookie=cookie)
        assert status == 200, path
        assert body == {"protocol": 2, "session": "head-world", "epoch": 7,
                        "role": "sonar", **extra}


def test_private_events_are_served_only_to_their_stored_role(server):
    _, cookie, token, paired = pair_v2(server, "Sonar")
    assert server.grant_station(paired["client_id"], "sonar")
    import hashlib
    digest = hashlib.sha256(token.encode("ascii")).digest()
    with server._lock:
        server._v2_state_heads["sonar"] = ("w", 1)
        server._v2_private_events = {digest: ("bridge", b'{"private":true}')}
    body = session_request(server, "/api/v2/events", cookie=cookie)[2]
    assert body["role"] == "sonar" and body["events"] == []
    with server._lock:
        server._v2_private_events = {digest: ("sonar", b'{"private":true}')}
    assert session_request(server, "/api/v2/events", cookie=cookie)[2] == {"private": True}


# C10 / C6 -------------------------------------------------------------------

def _room(tmp_path):
    auth = WebHostAuth(tmp_path / "web-host.json")
    room = CommanderServer(web_auth=auth, public_origin="https://game.test")
    room.start("127.0.0.1", 0)
    return auth, room


def _post(room, path, body, forwarded=None, host="game.test",
          origin="https://game.test"):
    address, port = room.address
    headers = {"Host": host, "Origin": origin, "Content-Type": "application/json"}
    if forwarded is not None:
        headers["X-Forwarded-For"] = forwarded
    with closing(http.client.HTTPConnection(address, port, timeout=5)) as connection:
        connection.request("POST", path, body=json.dumps(body), headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"null")


def test_failure_limiter_counts_per_source_and_is_bounded():
    limiter = FailureLimiter(limit=2, window_s=60.0, max_sources=3)
    for _ in range(2):
        limiter.record("a")
    assert not limiter.allowed("a") and limiter.allowed("b")
    limiter.record("b")
    limiter.record("c")
    assert len(limiter) == 3
    # Full table: an unknown source is refused (fail closed), never evicting
    # the record of a known one, and the table never grows.
    assert not limiter.allowed("d")
    limiter.record("d")
    assert len(limiter) == 3 and not limiter.allowed("a")


def test_scrypt_runs_outside_the_global_lock(tmp_path, monkeypatch):
    auth, room = _room(tmp_path)
    original = web_auth_module.hashlib.scrypt
    free = []

    def scrypt(*args, **kwargs):
        free.append(_lock_free_from_another_thread(room._lock))
        return original(*args, **kwargs)

    monkeypatch.setattr(web_auth_module.hashlib, "scrypt", scrypt)
    try:
        assert _post(room, "/api/v2/web/setup", {
            "code": auth.setup_code, "password": PASSWORD})[0] == 200
        assert _post(room, "/api/v2/web/login", {"password": "wrong password"})[0] == 403
        assert _post(room, "/api/v2/web/login", {"password": PASSWORD})[0] == 200
    finally:
        room.stop()
    assert free == [True, True, True]


def test_a_strangers_failed_logins_never_lock_out_the_host(tmp_path):
    auth, room = _room(tmp_path)
    try:
        assert _post(room, "/api/v2/web/setup", {
            "code": auth.setup_code, "password": PASSWORD})[0] == 200
        for _ in range(5):
            assert _post(room, "/api/v2/web/login", {"password": "guess"},
                         forwarded="198.51.100.7")[0] == 403
        # The stranger is limited (even the right password fails for it) ...
        assert _post(room, "/api/v2/web/login", {"password": PASSWORD},
                     forwarded="198.51.100.7")[0] == 403
        # ... the host behind the same proxy, from its own address, is not.
        # The proxy appends the real peer last; a spoofed left entry is ignored.
        assert _post(room, "/api/v2/web/login", {"password": PASSWORD},
                     forwarded="198.51.100.7, 203.0.113.9")[0] == 200
    finally:
        room.stop()


def test_room_pairing_failures_are_per_source_and_never_rotate_the_code(tmp_path):
    _, room = _room(tmp_path)
    try:
        code = room.pairing_code
        for _ in range(5):
            assert _post(room, "/api/v2/pair", {"code": "000AAA", "name": "x"},
                         forwarded="198.51.100.7") == (403, {"error": "invalid_code"})
        assert _post(room, "/api/v2/pair", {"code": code, "name": "x"},
                     forwarded="198.51.100.7")[0] == 429
        assert room.pairing_code == code
        assert _post(room, "/api/v2/pair", {"code": code, "name": "Crew"},
                     forwarded="203.0.113.9")[0] == 200
    finally:
        room.stop()


def test_lan_pairing_still_rotates_the_code_after_five_wrong_codes(server):
    code = server.pairing_code
    for _ in range(5):
        assert session_request(server, "/api/v2/pair", "POST",
                               {"code": "000AAA", "name": "x"})[0] == 403
    assert server.pairing_code != code
    assert session_request(server, "/api/v2/pair", "POST",
                           {"code": server.pairing_code, "name": "x"})[0] == 429


# C11 ------------------------------------------------------------------------

def test_an_observer_switching_views_never_clears_the_operators_audio(server):
    _, _, _, operator = pair_v2(server, "Operator")
    assert server.grant_station(operator["client_id"], "sonar")
    _, cookie, _, paired = pair_v2(server, "Observer")
    assert server.set_client_grant(paired["client_id"], "observer", True)
    with server._lock:
        server._sonar_audio.append((41, b"pcm"))
        server._sonar_audio_context = ("operator",)
        server._helicopter_audio.append((5, b"pcm"))
        server._helicopter_audio_context = ("pilot",)
    generation = session_request(server, "/api/v2/session", cookie=cookie)[2][
        "active_generation"]
    for station in ("sonar", "helicopter", "bridge"):
        status, _, body = session_request(
            server, "/api/v2/stations/activate", "POST",
            {"station": station, "station_generation": 0,
             "active_generation": generation}, cookie, paired["csrf"])
        assert status == 200 and body["station"] == station
        generation = body["active_generation"]
    with server._lock:
        assert list(server._sonar_audio) == [(41, b"pcm")]
        assert server._sonar_audio_context == ("operator",)
        assert list(server._helicopter_audio) == [(5, b"pcm")]
        assert server._helicopter_audio_context == ("pilot",)
    # The lease holder leaving its station still restarts the stream.
    assert server.grant_station(operator["client_id"], "opz")
    with server._lock:
        session = server._session_by_client_locked(operator["client_id"])
        assert server._set_active_station_locked(session, "opz")
        assert not server._sonar_audio and server._sonar_audio_context is None
