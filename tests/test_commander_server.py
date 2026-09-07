"""Live loopback tests; no simulation, audio, or user persistence is involved."""

from contextlib import closing
import base64
import http.client
import json
import re
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from src.commander import CommanderServer
from src.commander import server as transport


@pytest.fixture
def assets(tmp_path, monkeypatch):
    for name in ("index.html", "app.js", "style.css"):
        (tmp_path / name).write_text(f"fixture {name}", encoding="utf-8")
    calls = []

    def files(package):
        calls.append(package)
        assert package == "data.commander"
        return tmp_path

    monkeypatch.setattr(transport.resources, "files", files)
    return tmp_path, calls


@pytest.fixture
def server(assets):
    instance = CommanderServer({
        "en": {"commander.web.title": "Commander", "private.code": "secret"},
        "de": {"commander.web.title": "Kommandant"},
    })
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture
def deadline_timers(monkeypatch):
    timers = []
    original = threading.Timer

    def timer(*args, **kwargs):
        instance = original(*args, **kwargs)
        timers.append(instance)
        return instance

    monkeypatch.setattr(transport.threading, "Timer", timer)
    try:
        yield timers
    finally:
        for instance in timers:
            instance.cancel()
            if instance.ident is not None:
                instance.join(1)


def request(server, path, method="GET", body=None, token=None, headers=None, source_address=None):
    host, port = server.address
    request_headers = {}
    if method == "POST":
        request_headers.update({"Origin": f"http://{host}:{port}",
                                "Content-Type": "application/json"})
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode("utf-8")
    with closing(http.client.HTTPConnection(host, port, timeout=3,
                                           source_address=source_address)) as connection:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        if response.getheader("Content-Type").startswith("application/json"):
            data = json.loads(data)
        return response.status, dict(response.getheaders()), data


def pair(server):
    status, _, body = request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})
    assert status == 200
    assert set(body) == {"token"}
    assert len(body["token"]) == 43
    assert len(base64.urlsafe_b64decode(body["token"] + "=")) == 32
    return body["token"]


def command(**changes):
    result = {"id": "request-1", "session": "session", "epoch": 0,
              "revision": 0, "action": "classify", "track": "track-1", "value": "unknown"}
    result.update(changes)
    return result


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


def test_constructor_is_passive_and_lifecycle_is_explicit(assets):
    before = set(threading.enumerate())
    server = CommanderServer()
    assert set(threading.enumerate()) == before
    assert assets[1] == []
    assert not server.connected
    assert re.fullmatch(r"[0-9]{3}[A-Z]{3}", server.pairing_code)
    with pytest.raises(RuntimeError):
        _ = server.address
    server.stop()
    server.start("127.0.0.1", 0)
    try:
        assert server.address[0] == "127.0.0.1"
        assert server.address[1] > 0
        with pytest.raises(RuntimeError):
            server.start("127.0.0.1", 0)
    finally:
        server.stop()
    server.stop()
    assert not server.connected
    server.start("127.0.0.1", 0)
    server.stop()


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "::1", "localhost", "",
                                      "224.0.0.1", "169.254.1.1", "192.0.2.1", "0.1.2.3"])
def test_reject_non_explicit_lan_bind(host, assets):
    with pytest.raises(ValueError):
        CommanderServer().start(host, 0)
    assert assets[1] == []


@pytest.mark.parametrize("port", [-1, 65536, True, "8765", 1.5])
def test_reject_invalid_ports(port, assets):
    with pytest.raises(ValueError):
        CommanderServer().start("127.0.0.1", port)


def test_bind_failure_and_missing_assets_leave_no_listener(server, assets):
    another = CommanderServer()
    with pytest.raises(OSError):
        another.start(*server.address)
    assert not another.connected
    with pytest.raises(RuntimeError):
        _ = another.address
    (assets[0] / "app.js").unlink()
    with pytest.raises(FileNotFoundError):
        another.start("127.0.0.1", 0)
    another.stop()


def test_static_resources_cached_and_security_headers(server, assets):
    for name in ("index.html", "app.js", "style.css"):
        (assets[0] / name).unlink()
    for route, name in (("/", "index.html"), ("/app.js", "app.js"), ("/style.css", "style.css")):
        status, headers, body = request(server, route)
        assert status == 200
        assert body == f"fixture {name}".encode()
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
        assert headers["Connection"] == "close"
        assert not any(name.lower().startswith("access-control-") for name in headers)
        assert "Server" not in headers
        assert server.pairing_code.encode() not in body
    assert assets[1] == ["data.commander"]


@pytest.mark.parametrize("path", ["/index.html", "/../AGENTS.md", "/%2e%2e/AGENTS.md",
                                     "/app.js?x=1", "/api/v1/ui", "/api/v1/ui?lang=fr",
                                     "/api/v1/ui?lang=en&lang=de", "/api/v1/state?token=secret"])
def test_only_fixed_routes(server, path):
    assert request(server, path)[0] == 404


def test_public_translations_are_filtered_and_copied(assets):
    translations = {"en": {"commander.web.title": "Title", "commander.secret": "private",
                            "commander.web.invalid": 1}, "de": {"commander.web.title": "Titel"}}
    server = CommanderServer(translations)
    translations["en"]["commander.web.title"] = "changed"
    server.start("127.0.0.1", 0)
    try:
        assert request(server, "/api/v1/ui?lang=en")[2] == {"commander.web.title": "Title"}
        assert request(server, "/api/v1/ui?lang=de")[2] == {"commander.web.title": "Titel"}
        assert not server.connected
    finally:
        server.stop()


def test_pair_one_use_revoke_and_bearer_only(server):
    code = server.pairing_code
    assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    assert request(server, "/api/v1/pair", "POST", {"code": "\ud800"})[0] == 403
    token = pair(server)
    assert server.connected
    assert server.pairing_code != code
    assert request(server, "/api/v1/pair", "POST", {"code": code})[0] == 409
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 409
    for route in ("/api/v1/state", "/api/v1/chart"):
        assert request(server, route)[0] == 401
        assert request(server, route, token="wrong")[0] == 401
        assert request(server, route, headers={"Cookie": f"token={token}"})[0] == 401
        assert request(server, route, token=token)[0] == 200
    assert request(server, "/api/v1/commands", "POST", command(), token)[0] == 202
    envelope = server.drain_commands()[0]
    assert server.is_current(envelope)
    request(server, "/api/v1/commands", "POST", command(), token)
    code = server.pairing_code
    server.revoke()
    assert not server.connected
    assert not server.is_current(envelope)
    assert server.drain_commands() == []
    assert server.pairing_code != code
    assert request(server, "/api/v1/state", token=token)[0] == 401
    assert request(server, "/api/v1/pair", "POST", {"code": code})[0] == 403
    pair(server)
    assert not server.is_current(envelope)


def test_lease_generation_is_read_only_thread_safe_and_expires_before_read(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    initial = server.lease_generation
    assert type(initial) is int
    token = pair(server)
    paired = server.lease_generation
    assert paired > initial
    assert request(server, "/api/v1/commands", "POST", command(), token)[0] == 202
    envelope = server.drain_commands()[0]
    assert envelope["lease"] == paired
    with pytest.raises(AttributeError):
        server.lease_generation = paired + 1

    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    with ThreadPoolExecutor(max_workers=1) as executor:
        started = threading.Event()

        def read_generation():
            started.set()
            return server.lease_generation

        with server._lock:
            future = executor.submit(read_generation)
            assert started.wait(1)
            with pytest.raises(TimeoutError):
                future.result(timeout=.05)
        assert future.result(timeout=1) == paired
    clock[0] += 30
    expired = server.lease_generation
    assert expired > paired and not server.connected
    assert not server.is_current(dict(envelope, received_at=clock[0]))
    assert request(server, "/api/v1/state", token=token)[0] == 401
    pair(server)
    assert server.lease_generation > expired
    paired = server.lease_generation
    server.revoke()
    assert server.lease_generation > paired
    revoked = server.lease_generation
    server.stop()
    assert server.lease_generation > revoked


@pytest.mark.parametrize("upper,expected", [
    (False, ("000AAA", "000AAB", "000AAA")),
    (True, ("999ZZZ", "999ZZY", "999ZZZ")),
])
def test_code_rotation_excludes_predecessor_without_retry(assets, monkeypatch, upper, expected):
    draws = []

    def draw(bound):
        draws.append(bound)
        return bound - 1 if upper else 0

    monkeypatch.setattr(transport.secrets, "randbelow", draw)
    server = CommanderServer()
    codes = [server.pairing_code]
    for _ in range(2):
        server.revoke()
        codes.append(server.pairing_code)
    assert tuple(codes) == expected
    assert all(re.fullmatch(r"[0-9]{3}[A-Z]{3}", code) for code in codes)
    assert draws == [1000 * 26**3, 1000 * 26**3 - 1, 1000 * 26**3 - 1]


def test_pairing_is_exact_uppercase_and_bearer_stays_32_random_bytes(server, monkeypatch):
    sizes = []
    original = transport.secrets.token_urlsafe

    def token_urlsafe(size):
        sizes.append(size)
        return original(size)

    monkeypatch.setattr(transport.secrets, "token_urlsafe", token_urlsafe)
    code = server.pairing_code
    assert request(server, "/api/v1/pair", "POST", {"code": code.lower()})[0] == 403
    assert request(server, "/api/v1/pair", "POST", {"code": " " + code})[0] == 403
    token = pair(server)
    assert sizes == [32]
    assert server.pairing_code != code
    assert re.fullmatch(r"[0-9]{3}[A-Z]{3}", server.pairing_code)
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 409
    assert request(server, "/api/v1/state", token=token)[0] == 200


@pytest.mark.parametrize("expire_via", ["property", "request"])
def test_unpaired_code_ttl_checked_before_exposure_and_pairing(server, monkeypatch, expire_via):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    server.revoke()
    code = server.pairing_code
    clock[0] += 299
    assert server.pairing_code == code
    clock[0] += 1
    if expire_via == "property":
        assert server.pairing_code != code
    assert request(server, "/api/v1/pair", "POST", {"code": code})[0] == 403
    assert server.pairing_code != code
    assert re.fullmatch(r"[0-9]{3}[A-Z]{3}", server.pairing_code)
    pair(server)


def test_global_pairing_lockout_includes_correct_code_and_recovers_after_window(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    code = server.pairing_code
    for index in range(5):
        status = request(server, "/api/v1/pair", "POST", {"code": "wrong"},
                         source_address=(f"127.0.0.{index + 1}", 0))[0]
        assert status == 403
        if index < 4:
            assert server.pairing_code == code
    rotated = server.pairing_code
    assert rotated != code
    assert re.fullmatch(r"[0-9]{3}[A-Z]{3}", rotated)
    for guess in (rotated, code, "wrong"):
        status, _, body = request(server, "/api/v1/pair", "POST", {"code": guess},
                                  source_address=("127.0.0.6", 0))
        assert status == 429
        assert body == {"error": "pairing_rate_limited"}
    assert not server.connected
    assert server.pairing_code == rotated
    clock[0] += 59
    assert request(server, "/api/v1/pair", "POST", {"code": rotated})[0] == 429
    clock[0] += 1
    pair(server)


def test_pairing_failure_window_is_rolling(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    clock[0] += 30
    for _ in range(4):
        assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    clock[0] += 30
    assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 429
    clock[0] += 30
    pair(server)


@pytest.mark.parametrize("rotation", ["code_ttl", "lease_expiry"])
def test_automatic_rotation_preserves_pairing_failure_budget(server, monkeypatch, rotation):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    server.revoke()
    if rotation == "code_ttl":
        clock[0] += 299
    for _ in range(4):
        assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    if rotation == "lease_expiry":
        pair(server)
    code = server.pairing_code
    clock[0] += 1 if rotation == "code_ttl" else 30
    assert server.pairing_code != code
    assert not server.connected
    code = server.pairing_code
    assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    assert server.pairing_code != code
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 429
    code = server.pairing_code
    server.revoke()
    assert server.pairing_code != code
    pair(server)


def test_concurrent_pairing_failures_cannot_exceed_global_budget(server):
    for _ in range(4):
        assert request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0] == 403
    barrier = threading.Barrier(4)
    results = []

    def attempt():
        barrier.wait(timeout=3)
        results.append(request(server, "/api/v1/pair", "POST", {"code": "wrong"})[0])

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(4)
        assert not thread.is_alive()
    assert sorted(results) == [403, 429, 429, 429]
    assert request(server, "/api/v1/pair", "POST", {"code": server.pairing_code})[0] == 429


def test_idle_lease_renewed_only_by_authenticated_get(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    token = pair(server)
    clock[0] += 29
    assert request(server, "/api/v1/state", token=token)[0] == 200
    clock[0] += 29
    assert request(server, "/api/v1/chart", token=token)[0] == 200
    clock[0] += 29
    assert request(server, "/api/v1/commands", "POST", command(), token)[0] == 202
    assert request(server, "/api/v1/ui?lang=en", token=token)[0] == 200
    assert request(server, "/api/v1/state", token="wrong")[0] == 401
    clock[0] += 1
    assert not server.connected
    assert server.drain_commands() == []
    assert request(server, "/api/v1/state", token=token)[0] == 401
    pair(server)


def test_publish_immutable_atomic_finite_json(server):
    snapshot, chart = {"tracks": [{"name": "<script>"}]}, {"land": [[1, 2]]}
    server.publish(snapshot, chart)
    snapshot["tracks"][0]["name"] = "mutated"
    chart["land"].append([3, 4])
    token = pair(server)
    assert request(server, "/api/v1/state", token=token)[2] == {"tracks": [{"name": "<script>"}]}
    assert request(server, "/api/v1/chart", token=token)[2] == {"land": [[1, 2]]}
    for bad in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            server.publish({"bad": bad})
        with pytest.raises(ValueError):
            server.publish({"new": True}, {"bad": bad})
    assert "tracks" in request(server, "/api/v1/state", token=token)[2]
    server.publish({"new": True})
    assert request(server, "/api/v1/state", token=token)[2] == {"new": True}
    assert request(server, "/api/v1/chart", token=token)[2] == {"land": [[1, 2]]}
    with pytest.raises(TypeError):
        server.publish([])


def test_queue_envelopes_limits_ttl_and_no_enum_validation(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    token = pair(server)
    for index in range(32):
        status, _, body = request(server, "/api/v1/commands", "POST",
                                  command(id=str(index), value="bridge-validates-this"), token)
        assert status == 202
        assert body == {"status": "queued", "id": str(index)}
    assert request(server, "/api/v1/commands", "POST", command(), token)[0] == 429
    batch = server.drain_commands()
    assert len(batch) == 4
    assert [item["command"]["id"] for item in batch] == ["0", "1", "2", "3"]
    for envelope in batch:
        assert set(envelope) == {"command", "lease", "received_at"}
        assert type(envelope["lease"]) is int
        assert type(envelope["received_at"]) is float
        assert server.is_current(envelope)
    assert len(server.drain_commands(2)) == 2
    assert server.drain_commands(0) == []
    with pytest.raises(ValueError):
        server.drain_commands(-1)
    clock[0] += 5
    assert server.is_current(batch[0])
    clock[0] += 0.001
    assert not server.is_current(batch[0])
    expired = server.drain_commands()
    assert [item["command"]["id"] for item in expired] == ["6", "7", "8", "9"]
    assert all(not server.is_current(item) for item in expired)
    remaining = server.drain_commands(32)
    assert [item["command"]["id"] for item in remaining] == [str(index) for index in range(10, 32)]
    assert all(not server.is_current(item) for item in remaining)
    assert server.drain_commands() == []
    assert not server.is_current({"lease": batch[0]["lease"], "received_at": float("nan")})
    assert not server.is_current({"lease": True, "received_at": clock[0]})


@pytest.mark.parametrize("action", ["classify", "affiliate", "propose", "clear_proposal"])
def test_exact_valid_command_shapes(server, action):
    token = pair(server)
    body = command(action=action)
    if action in ("propose", "clear_proposal"):
        del body["value"]
    else:
        body["value"] = None
    assert request(server, "/api/v1/commands", "POST", body, token)[0] == 202
    if action == "clear_proposal":
        del body["track"]
        assert request(server, "/api/v1/commands", "POST", body, token)[0] == 202


@pytest.mark.parametrize("change", [{"action": "fire"}, {"action": []}, {"extra": 0},
                                        {"id": "x" * 65}, {"session": None}, {"track": "x" * 65},
                                        {"epoch": True}, {"epoch": -1}, {"revision": 1.0},
                                        {"revision": False}, {"value": {}}, {"track": None},
                                        {"action": "propose"}, {"action": "clear_proposal"}])
def test_invalid_command_fields(server, change):
    token = pair(server)
    assert request(server, "/api/v1/commands", "POST", command(**change), token)[0] == 400
    assert server.drain_commands() == []


@pytest.mark.parametrize("field", ["id", "session", "epoch", "revision", "action", "track", "value"])
def test_missing_command_fields(server, field):
    token = pair(server)
    body = command()
    del body[field]
    assert request(server, "/api/v1/commands", "POST", body, token)[0] == 400


@pytest.mark.parametrize("body", [b'{"code":"x","code":"y"}', b'{"code":NaN}',
                                    b'{"code":Infinity}', b'{"code":-Infinity}',
                                    b'{"code":1e999}', b'{"code":{"a":1,"a":2}}',
                                    b'[]', b'null', b'"text"', b'{"code":1}',
                                    b'{"code":"x","other":1}', b'\xff', b'{',
                                    b'[' * 1100 + b']' * 1100])
def test_strict_pair_json(server, body):
    assert request(server, "/api/v1/pair", "POST", body)[0] == 400
    assert not server.connected


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE", "CONNECT"])
def test_unknown_methods(server, method):
    host, port = server.address
    response = raw_request(server, f"{method} / HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    assert response.startswith(b"HTTP/1.1 405")


@pytest.mark.parametrize("headers,expected", [
    (b"", 403),
    (b"Host: evil.test\r\n", 403),
    (b"Host: {host}\r\nHost: {host}\r\n", 400),
    (b"Host: {host}\r\nOrigin: http://evil.test\r\n", 403),
    (b"Host: {host}\r\nOrigin: null\r\n", 403),
    (b"Host: {host}\r\nContent-Length: 0\r\nContent-Length: 0\r\n", 400),
    (b"Host: {host}\r\nContent-Length: 0, 0\r\n", 400),
    (b"Host: {host}\r\nContent-Length: +0\r\n", 400),
    (b"Host: {host}\r\nContent-Length: -1\r\n", 400),
    (b"Host: {host}\r\nContent-Length: 4097\r\n", 413),
    (b"Host: {host}\r\nContent-Length: 1\r\n", 400),
    (b"Host: {host}\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n", 400),
    (b"Host: {host}\r\nExpect: 100-continue\r\n", 400),
    (b"Host: {host}\r\n folded: bad\r\n", 400),
    (b"Host: {host}\r\nBad : value\r\n", 400),
    (b"Host: {host}\r\nBad: \x00\r\n", 400),
    (b"Host: {host}\r\nAuthorization: a\r\nAuthorization: b\r\n", 400),
    (b"Host: {host}\r\nOrigin: a\r\nOrigin: b\r\n", 400),
    (b"Host: {host}\r\nContent-Type: a\r\nContent-Type: b\r\n", 400),
])
def test_host_headers_and_framing(server, headers, expected):
    host = "%s:%s" % server.address
    headers = headers.replace(b"{host}", host.encode())
    response = raw_request(server, b"GET / HTTP/1.1\r\n" + headers + b"\r\n")
    assert response.startswith(f"HTTP/1.1 {expected}".encode())
    assert b"Cache-Control: no-store" in response


def test_post_origin_media_type_and_auth(server):
    host, port = server.address
    body = json.dumps({"code": server.pairing_code}).encode()
    payload = (f"POST /api/v1/pair HTTP/1.1\r\nHost: {host}:{port}\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body
    assert raw_request(server, payload).startswith(b"HTTP/1.1 403")
    for origin in ("null", "https://%s:%s" % server.address, "http://evil.test", f"http://{host}:{port}/"):
        assert request(server, "/api/v1/pair", "POST", body, headers={"Origin": origin})[0] == 403
    assert request(server, "/api/v1/pair", "POST", body, headers={"Content-Type": "text/plain"})[0] == 415
    assert request(server, "/api/v1/commands", "POST", command())[0] == 401
    local_host = f"localhost:{port}"
    status = request(server, "/api/v1/pair", "POST", body,
                     headers={"Host": local_host, "Origin": f"http://{local_host}"})[0]
    assert status == 200
    assert request(server, "/", headers={"Host": local_host})[0] == 200


@pytest.mark.parametrize("line,extra,expected", [
    (b"GET /" + b"x" * 1024 + b" HTTP/1.1\r\n", b"", 400),
    (b"GET //evil.test/ HTTP/1.1\r\n", b"", 400),
    (b"GET http://evil.test/ HTTP/1.1\r\n", b"", 400),
    (b"GET / HTTP/1.1\n", b"", 400),
    (b"GET / HTTP/1.1\r\n", b"X: " + b"x" * 8192 + b"\r\n", 431),
    (b"GET / HTTP/1.1\r\n", b"X: x\r\n" * 65, 431),
])
def test_request_target_and_header_bounds(server, line, extra, expected):
    host = "%s:%s" % server.address
    response = raw_request(server, line + f"Host: {host}\r\n".encode() + extra + b"\r\n")
    assert response.startswith(f"HTTP/1.1 {expected}".encode())


def test_connection_cap_timeout_and_bounded_shutdown(server, deadline_timers):
    http = server._http
    clients = []
    try:
        for _ in range(4):
            client = socket.create_connection(server.address, timeout=3)
            client.sendall(b"GET / HTTP/1.1\r\n")
            clients.append(client)
        deadline = time.monotonic() + 1
        while len(http.workers) < 4 and time.monotonic() < deadline:
            time.sleep(0.005)
        with http.work_lock:
            workers = list(http.workers)
            assert len(workers) == 4
            assert all(connection.gettimeout() == 1.5 for connection in http.workers.values())
        with closing(socket.create_connection(server.address, timeout=3)) as fifth:
            assert fifth.recv(1) == b""
        start = time.monotonic()
        server.stop()
        assert time.monotonic() - start < 2.5
        assert all(not worker.is_alive() for worker in workers)
        assert not http.workers
        assert len(deadline_timers) == 4
        assert all(timer.daemon and not timer.is_alive() for timer in deadline_timers)
    finally:
        for client in clients:
            client.close()


def test_slow_connection_times_out_without_access_logs(server, capsys):
    with closing(socket.create_connection(server.address, timeout=3)) as client:
        client.sendall(b"GET / HTTP/1.1\r\n")
        assert client.recv(1) == b""
    token = pair(server)
    request(server, "/api/v1/state", token=token)
    request(server, "/not-found")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("stage", ["request_line", "header_line", "headers", "body"])
def test_trickle_cannot_extend_absolute_deadline(server, monkeypatch, deadline_timers, capsys, stage):
    monkeypatch.setattr(transport, "_CONNECTION_DEADLINE_S", 0.3)
    host = "%s:%s" % server.address
    prefix = f"GET / HTTP/1.1\r\nHost: {host}\r\n".encode()
    fragment = b"x"
    if stage == "request_line":
        prefix = b"GET /"
    elif stage == "header_line":
        prefix += b"X: "
    elif stage == "headers":
        fragment = b"X: x\r\n"
    else:
        prefix = (f"POST /api/v1/pair HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\n"
                  'Content-Type: application/json\r\nContent-Length: 4096\r\n\r\n{"code":"').encode()
    http = server._http
    clients = []
    try:
        for _ in range(4):
            client = socket.create_connection(server.address, timeout=1)
            clients.append(client)
            client.sendall(prefix)
        deadline = time.monotonic() + 1
        while len(deadline_timers) < 4 and time.monotonic() < deadline:
            time.sleep(0.005)
        with http.work_lock:
            workers = list(http.workers)
        assert len(workers) == len(deadline_timers) == 4
        assert all(timer.daemon for timer in deadline_timers)
        sends = 0
        while time.monotonic() < deadline:
            for client in clients:
                try:
                    client.sendall(fragment)
                    sends += 1
                except OSError:
                    pass
            with http.work_lock:
                if not http.workers:
                    break
            time.sleep(0.01)
        assert sends >= 8
        for worker in workers:
            worker.join(0.1)
            assert not worker.is_alive()
        assert all(not timer.is_alive() for timer in deadline_timers)
        assert not http.workers
        assert not server.connected
        assert server.drain_commands() == []
        assert request(server, "/")[0] == 200
        server.stop()
        assert all(not timer.is_alive() for timer in deadline_timers)
        captured = capsys.readouterr()
        assert captured.out == captured.err == ""
    finally:
        for client in clients:
            client.close()


def test_completed_requests_cancel_and_join_deadline_timers(server, deadline_timers):
    for _ in range(8):
        assert request(server, "/")[0] == 200
    assert len(deadline_timers) == 8
    for timer in deadline_timers:
        timer.join(0.5)
        assert not timer.is_alive()
        assert timer.finished.is_set()


def test_concurrent_pairing_grants_exactly_one_lease(server):
    code = server.pairing_code
    barrier = threading.Barrier(4)
    results = []

    def attempt():
        barrier.wait(timeout=3)
        results.append(request(server, "/api/v1/pair", "POST", {"code": code})[0])

    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(4)
        assert not thread.is_alive()
    assert sorted(results) == [200, 409, 409, 409]


def test_expired_commands_observable_when_uploads_finish_out_of_order(server, monkeypatch):
    clock = [time.monotonic()]
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    token = pair(server)
    waiting, release = threading.Event(), threading.Event()
    original = transport._Handler._post

    def delayed_post(handler, body, received_at):
        if body.get("id") == "older":
            waiting.set()
            assert release.wait(3)
        original(handler, body, received_at)

    monkeypatch.setattr(transport._Handler, "_post", delayed_post)
    results = []
    older = threading.Thread(target=lambda: results.append(
        request(server, "/api/v1/commands", "POST", command(id="older"), token)[0]))
    older.start()
    try:
        assert waiting.wait(3)
        clock[0] += 2
        assert request(server, "/api/v1/commands", "POST", command(id="newer"), token)[0] == 202
    finally:
        release.set()
        older.join(4)
    assert not older.is_alive()
    assert results == [202]
    clock[0] += 4
    envelopes = server.drain_commands()
    assert [item["command"]["id"] for item in envelopes] == ["newer", "older"]
    assert server.is_current(envelopes[0])
    assert not server.is_current(envelopes[1])
    assert server.drain_commands() == []


def test_post_body_bound_and_incomplete_framing(server):
    token = pair(server)
    body = json.dumps(command(value="")).encode()
    body = json.dumps(command(value="x" * (4096 - len(body)))).encode()
    assert len(body) == 4096
    assert request(server, "/api/v1/commands", "POST", body, token)[0] == 202
    assert request(server, "/api/v1/commands", "POST", body + b" ", token)[0] == 413
    host = "%s:%s" % server.address
    prefix = (f"POST /api/v1/pair HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\n"
              "Content-Type: application/json\r\n").encode()
    assert raw_request(server, prefix + b"\r\n").startswith(b"HTTP/1.1 400")
    with closing(socket.create_connection(server.address, timeout=3)) as client:
        client.sendall(prefix + b"Content-Length: 10\r\n\r\n{}")
        client.shutdown(socket.SHUT_WR)
        assert client.recv(4096).startswith(b"HTTP/1.1 400")


def test_no_keepalive_or_pipeline_dispatch(server):
    host = "%s:%s" % server.address
    payload = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: keep-alive\r\n\r\n".encode()
    response = raw_request(server, payload + payload)
    assert response.count(b"HTTP/1.1 200") == 1


def test_stop_invalidates_drained_envelopes_and_restart_tokens(server):
    token = pair(server)
    assert request(server, "/api/v1/commands", "POST", command(), token)[0] == 202
    envelope = server.drain_commands()[0]
    code = server.pairing_code
    server.stop()
    assert not server.is_current(envelope)
    assert server.pairing_code != code
    server.start("127.0.0.1", 0)
    assert request(server, "/api/v1/state", token=token)[0] == 401
    pair(server)
    assert not server.is_current(envelope)
