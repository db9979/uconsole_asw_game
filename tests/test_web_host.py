"""Loopback web-host setup, proxy-origin, and room authority contracts."""

from contextlib import closing
import http.client
import json
import os
import pytest
import time
from types import SimpleNamespace

from src.commander.server import CommanderServer, STATIONS
from src.commander.web_auth import WebHostAuth
from src.commander.local import CommanderConsole
from src.core import config
from src.core.game import Game
from src.core import game as game_module
from src.core import game_draw
import pygame


def test_web_bind_is_explicit_and_limited_to_private_ipv4(tmp_path, monkeypatch):
    import main as entry

    calls = []

    class FakeConsole:
        def start_web(self, _auth, origin, port, bind_host):
            calls.append((origin, port, bind_host))

    class FakeGame:
        def __init__(self, **kwargs):
            assert kwargs["web_mode"] is True
            self.commander = FakeConsole()

        def run(self):
            pass

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "WebHostAuth", lambda _path: type(
        "Auth", (), {"configured": True})())
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "Prefs", (), {"fullscreen": False, "audio": False})())
    assert entry.main(["--web-host", "--public-origin", "https://game.test",
                       "--web-bind", "192.168.178.36", "--web-port", "9000", "5"]) == 0
    assert calls == [("https://game.test", 9000, "192.168.178.36")]
    for address in ("0.0.0.0", "8.8.8.8", "fe80::1", "192.168.178.36/24"):
        with pytest.raises(SystemExit):
            entry.main(["--web-host", "--public-origin", "https://game.test",
                        "--web-bind", address, "5"])
    assert calls == [("https://game.test", 9000, "192.168.178.36")]


def test_local_game_accepts_a_proxy_origin_for_remote_crew(monkeypatch):
    import main as entry

    consoles = []

    class FakeConsole:
        public_origin = None
        solo = False

        def autostart_solo(self):
            self.solo = True

    class FakeGame:
        def __init__(self, **kwargs):
            assert kwargs["web_mode"] is False
            self.commander = FakeConsole()
            consoles.append(self.commander)

        def run(self):
            pass

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "Prefs", (), {"fullscreen": False, "audio": False})())
    assert entry.main(["--public-origin", "https://crew.example.lan",
                       "--solo-crew", "5"]) == 0
    assert consoles[-1].public_origin == "https://crew.example.lan"
    assert consoles[-1].solo
    for origin in ("http://crew.example.lan", "https://crew.example.lan/",
                   "https://crew.example.lan/path"):
        with pytest.raises(SystemExit):
            entry.main(["--public-origin", origin, "5"])


def test_web_server_rejects_public_and_wildcard_binds(tmp_path):
    auth = WebHostAuth(tmp_path / "web-host.json")
    server = CommanderServer(web_auth=auth, public_origin="https://game.test")
    for address in ("0.0.0.0", "8.8.8.8"):
        with pytest.raises(ValueError):
            server.start(address, 0)


def test_web_live_status_reports_missing_geography_and_provider_limits():
    status = CommanderConsole._web_live_status
    assert status(False, False, None) == "disabled"
    assert status(True, False, None) == "no_geography"
    assert status(True, True, None, missing_key=True) == "no_key"
    assert status(True, True, SimpleNamespace(connected=False,
                                               last_error="HTTP 429")) == "rate_limited"
    assert status(True, True, SimpleNamespace(connected=True,
                                               last_error=None)) == "connected"


def request(server, path, method="GET", body=None, cookie=None, csrf=None,
            origin="https://game.test", request_id="e6bc1d21-4321-4c18-8abd-503ff48b1554"):
    host, port = server.address
    headers = {"Host": "game.test", "Origin": origin}
    if method == "POST":
        headers["Content-Type"] = "application/json"
        if path in ("/api/v2/web/admin", "/api/v2/web/options"):
            headers["X-U-Jagd-Request-ID"] = request_id
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-U-Jagd-CSRF"] = csrf
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as connection:
        connection.request(method, path, body=None if body is None else json.dumps(body),
                           headers=headers)
        response = connection.getresponse()
        raw = response.read()
        value = json.loads(raw) if response.getheader("Content-Type", "").startswith(
            "application/json") else raw
        return response.status, dict(response.getheaders()), value


def test_host_setup_login_and_station_transfer(tmp_path):
    auth = WebHostAuth(tmp_path / "web-host.json")
    server = CommanderServer(web_auth=auth, public_origin="https://game.test")
    server.start("127.0.0.1", 0)
    try:
        assert request(server, "/api/v2/web/status")[2] == {"configured": False}
        assert request(server, "/api/v2/web/setup", "POST", {
            "code": auth.setup_code, "password": "a long private password"})[0] == 200
        assert request(server, "/api/v2/web/setup", "POST", {
            "code": auth.setup_code, "password": "a long private password"})[0] == 409
        assert request(server, "/api/v2/web/login", "POST", {
            "password": "incorrect password"})[0] == 403
        status, headers, host_session = request(server, "/api/v2/web/login", "POST", {
            "password": "a long private password"})
        assert status == 200
        assert "; Secure" in headers["Set-Cookie"]
        assert host_session["host"] is not None
        assert set(station for station, detail in host_session["stations"].items()
                   if detail["status"] == "mine") == set(STATIONS)
        host_cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, room = request(server, "/api/v2/web/room", cookie=host_cookie)
        assert status == 200 and room["code"] == server.pairing_code
        status, headers, crew = request(server, "/api/v2/pair", "POST", {
            "code": room["code"], "name": "Crew"})
        assert status == 200 and crew["host"] is None
        crew_cookie = headers["Set-Cookie"].split(";", 1)[0]
        assert request(server, "/api/v2/stations/request", "POST", {
            "station": "sonar"}, cookie=crew_cookie, csrf=crew["csrf"])[0] == 200
        assert request(server, "/api/v2/web/admin", "POST", {
            "action": "assign", "client_id": crew["client_id"], "station": "sonar",
            "value": False}, cookie=crew_cookie, csrf=crew["csrf"])[0] == 401
        assert request(server, "/api/v2/web/admin", "POST", {
            "action": "assign", "client_id": crew["client_id"], "station": "sonar",
            "value": False}, cookie=host_cookie, csrf=host_session["csrf"],
            origin="http://game.test")[0] == 403
        status, _, result = request(server, "/api/v2/web/admin", "POST", {
            "action": "assign", "client_id": crew["client_id"], "station": "sonar",
            "value": False}, cookie=host_cookie, csrf=host_session["csrf"])
        assert status == 202 and result["id"]
        item = server.drain_web_admin()[0]
        assert item[0] == result["id"]
        assert server.drain_web_admin() == []
        assert server.grant_station(crew["client_id"], "sonar")
        server.finish_web_admin(result["id"], True)
        assert request(server, "/api/v2/web/admin", "POST", {
            "action": "assign", "client_id": crew["client_id"], "station": "sonar",
            "value": False}, cookie=host_cookie, csrf=host_session["csrf"])[2] == {
                "id": result["id"], "result": True}
        assert server.drain_web_admin() == []
        server.web_reclaim_available()
        assert request(server, "/api/v2/session", cookie=crew_cookie)[2]["stations"]["sonar"]["status"] == "mine"
        assert request(server, "/api/v2/session", cookie=host_cookie)[2]["stations"]["sonar"]["status"] == "occupied"
        old_request_id = "bd15a751-9250-41ee-995d-a6304f9d1942"
        status, _, old_pending = request(server, "/api/v2/web/admin", "POST", {
            "action": "rotate_code", "client_id": "", "station": "", "value": False},
            cookie=host_cookie, csrf=host_session["csrf"], request_id=old_request_id)
        assert status == 202
        assert server.drain_web_admin()[0][0] == old_pending["id"]
        status, replacement_headers, replacement = request(server,
            "/api/v2/web/login", "POST", {"password": "a long private password"})
        assert status == 200 and replacement["host"] is not None
        server.finish_web_admin(old_pending["id"], {"ok": True})
        assert request(server, "/api/v2/web/room", cookie=host_cookie)[0] == 401
        replacement_cookie = replacement_headers["Set-Cookie"].split(";", 1)[0]
        replacement_room = request(server, "/api/v2/web/room", cookie=replacement_cookie)
        assert replacement_room[0] == 200
        assert old_pending["id"] not in replacement_room[2]["results"]
        assert request(server, "/api/v2/session", cookie=crew_cookie)[2]["stations"]["sonar"]["status"] == "mine"
        server.web_rebase()
        assert request(server, "/api/v2/session", cookie=crew_cookie)[2]["station"] is None
        rebased = request(server, "/api/v2/session", cookie=replacement_cookie)[2]
        assert rebased["host"] is not None
        # The host holds every frigate station; the submarine roles are
        # never part of the web-host room.
        assert set(station for station, detail in rebased["stations"].items()
                   if detail["status"] == "mine") == set(STATIONS)
    finally:
        server.stop()


def test_host_password_file_is_private_and_reset_is_local(tmp_path):
    path = tmp_path / "web-host.json"
    auth = WebHostAuth(path)
    assert not auth.setup("wrong", "a long private password")
    assert auth.setup(auth.setup_code, "a long private password")
    assert path.stat().st_mode & 0o077 == 0
    assert WebHostAuth(path).verify("a long private password")
    os.chmod(path, 0o644)
    with pytest.raises(ValueError):
        WebHostAuth(path)
    os.chmod(path, 0o600)
    auth.reset_local()
    assert not path.exists() and not auth.configured


def test_web_host_publishes_game_without_local_display_work(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    monkeypatch.setattr(game_draw, "save_preferences", lambda prefs: tmp_path / "settings.json")
    game = Game(seed=31, start_menu=True, fullscreen=False,
                audio_enabled=False, language="en", web_mode=True)
    game.world_mode = "fixed"
    game.reset(31)
    auth = WebHostAuth(tmp_path / "web-host.json")
    game.commander.start_web(auth, "https://game.test", 0)
    try:
        game.commander.pump(game)
        assert request(game.commander.server, "/api/v2/web/setup", "POST", {
            "code": auth.setup_code, "password": "a long private password"})[0] == 200
        status, headers, session = request(game.commander.server,
            "/api/v2/web/login", "POST", {"password": "a long private password"})
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        game.commander.pump(game)
        status, _, host = request(game.commander.server, "/api/v2/host", cookie=cookie)
        assert status == 200 and host["phase"] == "menu"
        assert request(game.commander.server, "/api/v2/web/editor", cookie=cookie)[0] == 404
        status, _, queued = request(game.commander.server, "/api/v2/web/options", "POST",
            {"name": "language", "value": "de"}, cookie=cookie, csrf=session["csrf"])
        assert status == 202
        game.commander.pump(game)
        room = request(game.commander.server, "/api/v2/web/room", cookie=cookie)[2]
        assert room["results"][queued["id"]] == {"ok": True}
        assert request(game.commander.server, "/api/v2/web/options", cookie=cookie)[2]["language"] == "de"
        status, _, queued = request(game.commander.server, "/api/v2/web/options", "POST",
            {"name": "voice_enabled", "value": True}, cookie=cookie,
            csrf=session["csrf"], request_id="a6612ed1-3d21-4e72-852e-9a54d4939768")
        assert status == 202
        game.commander.pump(game)
        assert request(game.commander.server, "/api/v2/web/room", cookie=cookie)[2][
            "results"][queued["id"]] == {"ok": True}
        assert request(game.commander.server, "/api/v2/web/options", cookie=cookie)[2][
            "voice_enabled"] is True
        assert request(game.commander.server, "/api/v2/voice/status", cookie=cookie)[2][
            "enabled"] is True
        status, _, queued = request(game.commander.server, "/api/v2/web/options", "POST",
            {"name": "live_adsb_enabled", "value": True}, cookie=cookie,
            csrf=session["csrf"], request_id="6034304e-1b66-4e7a-af03-8bf7934346a1")
        assert status == 202
        game.commander.pump(game)
        options = request(game.commander.server, "/api/v2/web/options", cookie=cookie)[2]
        assert options["live_adsb_status"] == "no_geography"
        restarted = []
        with monkeypatch.context() as patch:
            patch.setattr(game.live_traffic, "configure",
                          lambda *_args: restarted.append(True))
            status, _, _ = request(game.commander.server, "/api/v2/web/options", "POST",
                {"name": "live_adsb_enabled", "value": True}, cookie=cookie,
                csrf=session["csrf"], request_id="386b80c5-768d-4c0d-a477-2e49b0c2ee61")
            assert status == 202
            game.commander.pump(game)
        assert restarted == []
        assert request(game.commander.server, "/api/v2/web/editor/apply", "POST",
            {"operation": "validate", "kind": "mission", "data": {}, "key": "",
             "overwrite": False}, cookie=cookie, csrf=session["csrf"])[0] == 404
        assert game.start_new_game("s1_patrouille", "fixed")
        with game.commander.server._lock:
            game.commander.server._sessions_v2[
                game.commander.server._web_host_digest]["presence"] = time.monotonic() - 20
        game.draw = lambda: (_ for _ in ()).throw(AssertionError("headless drew a frame"))
        game.auto_quit = 2
        before = game.sim_t
        game.run()
        # No auto-pause without a browser host: the mission keeps real time.
        assert not hasattr(game, "paused") and game.sim_t > before
    finally:
        game.commander.stop()
        game.audio.shutdown()
        pygame.quit()


def test_web_host_can_start_from_initial_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = Game(seed=31, start_menu=True, fullscreen=False,
                audio_enabled=False, language="en", web_mode=True)
    auth = WebHostAuth(tmp_path / "web-host.json")
    game.commander.start_web(auth, "https://game.test", 0)
    try:
        assert request(game.commander.server, "/api/v2/web/setup", "POST", {
            "code": auth.setup_code, "password": "a long private password"})[0] == 200
        status, headers, logged_in = request(game.commander.server,
            "/api/v2/web/login", "POST", {"password": "a long private password"})
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        game.commander.pump(game)
        server = game.commander.server
        session = request(server, "/api/v2/session", cookie=cookie)[2]
        view = request(server, "/api/v2/host", cookie=cookie)[2]
        assert view["phase"] == "menu"
        body = {"protocol": 2, "id": "new-web-game", "seq": session["next_command_seq"],
                "station": "host", "station_generation": logged_in["host"]["generation"],
                "active_generation": 0, "world_session": view["session"],
                "world_epoch": view["epoch"], "resource_revision": 0,
                "action": "host_new_game", "params": {"scenario": "s1_patrouille",
                                                   "world_mode": "fixed", "seed": 57}}
        assert request(server, "/api/v2/commands", "POST", body,
                       cookie=cookie, csrf=logged_in["csrf"])[0] == 202
        game.commander.pump(game)
        results = request(server, "/api/v2/results", cookie=cookie)[2]["results"]
        assert results[-1]["reasoncode"] == "ok"
        assert game.main_menu is False
        game.commander.pump(game)
        assert request(server, "/api/v2/host", cookie=cookie)[2]["phase"] == "live"
    finally:
        game.commander.stop()
        game.audio.shutdown()
        pygame.quit()


def test_headless_web_host_produces_live_sonar_pcm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = Game(seed=31, start_menu=False, fullscreen=False,
                audio_enabled=False, language="en", web_mode=True)
    auth = WebHostAuth(tmp_path / "web-host.json")
    game.commander.start_web(auth, "https://game.test", 0)
    try:
        assert request(game.commander.server, "/api/v2/web/setup", "POST", {
            "code": auth.setup_code, "password": "a long private password"})[0] == 200
        status, headers, session = request(game.commander.server,
            "/api/v2/web/login", "POST", {"password": "a long private password"})
        assert status == 200
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        server = game.commander.server
        sonar = session["stations"]["sonar"]
        status, _, activated = request(server, "/api/v2/stations/activate", "POST", {
            "station": "sonar", "station_generation": sonar["station_generation"],
            "active_generation": session["active_generation"]},
            cookie=cookie, csrf=session["csrf"])
        assert status == 200 and activated["grants"]["sonar_audio"] is True
        for _ in range(15):
            game.commander.pump(game)
            game.update(.1)
        game.commander.pump(game)
        state = request(server, "/api/v2/state", cookie=cookie)[2]
        body = {"protocol": 2, "after": None, "world_session": state["session"],
                "world_epoch": state["epoch"],
                "station_generation": activated["station_generation"],
                "active_generation": activated["active_generation"]}
        status, headers, pcm = request(server, "/api/v2/sonar/audio", "POST",
                                       body, cookie=cookie, csrf=session["csrf"])
        assert status == 200 and headers["Content-Type"] == "audio/pcm"
        assert len(pcm) == 2048 and any(pcm)
    finally:
        game.commander.stop()
        game.audio.shutdown()
        pygame.quit()
