"""Live v2 transport tests; no simulation or user persistence is involved."""

from contextlib import closing
import http.client
import json
import re
import socket
import threading
import time

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


def request(server, path, method="GET", body=None, headers=None):
    host, port = server.address
    request_headers = {}
    if method == "POST":
        request_headers.update({
            "Origin": f"http://{host}:{port}",
            "Content-Type": "application/json",
        })
    if headers:
        request_headers.update(headers)
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode("utf-8")
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        response_headers = dict(response.getheaders())
        if response_headers.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return response.status, response_headers, data


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
    code = server.pairing_code
    server.stop()
    server.start("127.0.0.1", 0)
    try:
        assert server.address[0] == "127.0.0.1"
        with pytest.raises(RuntimeError):
            server.start("127.0.0.1", 0)
    finally:
        server.stop()
    server.start("127.0.0.1", 0)
    assert server.pairing_code == code
    server.stop()


@pytest.mark.parametrize("host", [
    "0.0.0.0", "8.8.8.8", "::1", "localhost", "", "224.0.0.1",
    "169.254.1.1", "192.0.2.1", "0.1.2.3",
])
def test_reject_non_explicit_lan_bind(host, assets):
    with pytest.raises(ValueError):
        CommanderServer().start(host, 0)
    assert assets[1] == []


@pytest.mark.parametrize("port", [-1, 80, 1023, 65536, True, "8765", 1.5])
def test_reject_invalid_ports(port, assets):
    with pytest.raises(ValueError):
        CommanderServer().start("127.0.0.1", port)


def test_static_resources_cached_and_security_headers(server, assets):
    for name in ("index.html", "app.js", "style.css"):
        (assets[0] / name).unlink()
    for route, name in (("/", "index.html"), ("/app.js", "app.js"),
                        ("/style.css", "style.css")):
        status, headers, body = request(server, route)
        assert status == 200 and body == f"fixture {name}".encode()
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
        assert headers["Connection"] == "close"
        assert "Server" not in headers
        assert server.pairing_code.encode() not in body
    assert assets[1] == ["data.commander"]


def test_public_v2_ui_is_exact_filtered_and_does_not_pair(server):
    assert request(server, "/api/v2/ui?lang=en")[2] == {
        "commander.web.title": "Commander"}
    assert request(server, "/api/v2/ui?lang=de")[2] == {
        "commander.web.title": "Kommandant"}
    assert not server.connected
    for path in ("/api/v2/ui", "/api/v2/ui?lang=fr",
                 "/api/v2/ui?lang=en&lang=de", "/api/v2/ui?lang=EN"):
        assert request(server, path)[0] == 404


def test_prebuilt_contact_routes_use_exact_v2_contract(assets):
    projection = b'{"version":1,"profiles":[]}'
    png = b"\x89PNG\r\n\x1a\nfixture"
    server = CommanderServer(contact_analysis_assets={
        "/api/v2/contacts": ("application/json; charset=utf-8", projection),
        "/contact-analysis/unit-cruise.png": ("image/png", png),
    })
    server.start("127.0.0.1", 0)
    try:
        status, headers, body = request(server, "/api/v2/contacts")
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert body == {"version": 1, "profiles": []}
        status, headers, body = request(server, "/contact-analysis/unit-cruise.png")
        assert status == 200 and headers["Content-Type"] == "image/png" and body == png
        for path in ("/api/v1/contacts", "/api/v2/Contacts",
                     "/api/v2/contacts?x=1", "/contact-analysis/UNIT-cruise.png",
                     "/contact-analysis/unit-cruise.png?x=1",
                     "/contact-analysis/../unit-cruise.png"):
            assert request(server, path)[0] == 404
    finally:
        server.stop()


@pytest.mark.parametrize("prebuilt", [
    [],
    {"/contact-analysis/unit.png": ("image/png", b"png")},
    {"/contact-analysis/unit-silhouette.png": ("image/png", b"png")},
    {"/api/v1/contacts": ("application/json; charset=utf-8", b"{}")},
    {"/api/v2/contacts?x=1": ("application/json; charset=utf-8", b"{}")},
    {"/api/v2/contacts": ("image/png", b"{}")},
    {"/api/v2/contacts": ("application/json; charset=utf-8", bytearray(b"{}"))},
])
def test_prebuilt_contact_route_map_is_strict(prebuilt):
    with pytest.raises(ValueError):
        CommanderServer(contact_analysis_assets=prebuilt)


@pytest.mark.parametrize("path", [
    "/api/v1/ui?lang=en", "/api/v1/contacts", "/api/v1/state",
    "/api/v1/chart", "/api/v1/simlog", "/api/v1/results",
    "/api/v1/session", "/api/v1/commands", "/api/v1/pair",
    "/api/v1/anything",
])
def test_all_v1_get_routes_are_retired(server, path):
    assert request(server, path, headers={"Authorization": "Bearer legacy"})[0] == 404


@pytest.mark.parametrize("path", [
    "/api/v1/pair", "/api/v1/commands", "/api/v1/logout",
    "/api/v1/stations/request", "/api/v1/anything",
])
def test_all_v1_post_routes_are_retired(server, path):
    assert request(server, path, "POST", {}, {
        "Authorization": "Bearer legacy"})[0] == 404


def test_v1_auth_publication_and_global_queue_machinery_is_retired(server):
    for name in ("lease_generation", "publish", "drain_commands", "is_current"):
        assert not hasattr(server, name)
    for name in ("_token", "_lease", "_last_get", "_commands", "_snapshot", "_chart"):
        assert not hasattr(server, name)
    assert request(server, "/api/v2/state", headers={
        "Authorization": "Bearer legacy"})[0] == 401


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
    (b"Host: {host}\r\nContent-Length: 0\r\nContent-Length: 0\r\n", 400),
    (b"Host: {host}\r\nContent-Length: 4097\r\n", 413),
    (b"Host: {host}\r\nTransfer-Encoding: chunked\r\n", 400),
    (b"Host: {host}\r\nAuthorization: a\r\nAuthorization: b\r\n", 400),
    (b"Host: {host}\r\nCookie: a=b\r\nCookie: c=d\r\n", 400),
])
def test_host_headers_and_framing(server, headers, expected):
    host = "%s:%s" % server.address
    response = raw_request(
        server, b"GET / HTTP/1.1\r\n" + headers.replace(b"{host}", host.encode()) + b"\r\n")
    assert response.startswith(f"HTTP/1.1 {expected}".encode())
    assert b"Cache-Control: no-store" in response


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
        with closing(socket.create_connection(server.address, timeout=3)) as fifth:
            assert fifth.recv(1) == b""
        started = time.monotonic()
        server.stop()
        assert time.monotonic() - started < 2.5
        assert all(not worker.is_alive() for worker in workers)
        assert not http.workers
        assert len(deadline_timers) == 4
    finally:
        for client in clients:
            client.close()


def test_no_keepalive_or_pipeline_dispatch(server):
    host = "%s:%s" % server.address
    payload = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: keep-alive\r\n\r\n".encode()
    assert raw_request(server, payload + payload).count(b"HTTP/1.1 200") == 1
