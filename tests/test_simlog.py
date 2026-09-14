"""Simulationsprotokoll: Options-Toggle, begrenzte Aufnahme, Commander #simlog."""

import json
from contextlib import closing
from dataclasses import replace
import http.client
import time

import pygame
import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import CommanderServer
from src.core import config
from src.core.game import Game
from src.core.i18n import message
from src.core.preferences import load_preferences, save_preferences, Preferences
from src.sonar.sonar import Contact
import src.commander.server as transport
import src.commander.bridge as commander_bridge


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()


def test_preferences_simlog_defaults_off_and_roundtrips(tmp_path):
    assert Preferences.defaults().simlog is False
    path = tmp_path / "settings.json"
    save_preferences(Preferences(simlog=True), path)
    assert load_preferences(path).simlog is True
    save_preferences(Preferences(), path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["simlog"] is False


def test_preferences_rejects_non_bool_simlog(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"simlog": "ja"}), encoding="utf-8")
    assert load_preferences(path).simlog is False


def test_simlog_records_only_when_enabled(game):
    game.feed.add("00:00", "mission", "Erstes Ereignis")
    assert list(game.simlog) == []
    game.preferences = replace(game.preferences, simlog=True)
    game.sim_t = 12.5
    game.feed.add("00:01", "sonar", "Ping")
    row = game.simlog[0]
    assert row["seq"] == 1 and row["t"] == 12.5
    assert row["stamp"] == "00:01" and row["cat"] == "sonar"
    assert row["text"] == "Ping"


def test_simlog_stores_localizable_messages_raw(game):
    game.preferences = replace(game.preferences, simlog=True)
    game.feed.add("00:02", "waffen", message("runtime.raid.downed"))
    assert "params" in game.simlog[0]["text"]


def test_simlog_is_bounded(game):
    game.preferences = replace(game.preferences, simlog=True)
    for i in range(config.SIMLOG_MAX_ENTRIES + 10):
        game.feed.add("00:00", "mission", f"Ereignis {i}")
    assert len(game.simlog) == config.SIMLOG_MAX_ENTRIES
    assert game.simlog[-1]["seq"] == config.SIMLOG_MAX_ENTRIES + 10
    assert game.simlog[0]["seq"] == 11


def test_state_snapshots_record_on_sim_progress(game):
    game.preferences = replace(game.preferences, simlog=True)
    game.sim_t = 9.0
    # Unterhalb des Intervalls: kein Snapshot.
    for _ in range(9):
        game._record_simlog_state(1.0)
    assert all(row["cat"] != "state" for row in game.simlog)
    game._record_simlog_state(1.0)
    assert len(game.simlog) == 1
    row = game.simlog[0]
    assert row["cat"] == "state" and row["seq"] == 1
    assert row["t"] == game.sim_t and row["text"] == ""
    assert row["stamp"] == game.world.format_time()


def test_state_snapshot_covers_ship_weapons_and_all_map_items(game):
    game.preferences = replace(game.preferences, simlog=True)
    game._record_simlog_state(config.SIMLOG_INTERVAL_S)
    data = game.simlog[0]["data"]
    ship, weapons = data["ship"], data["weapons"]
    assert ship["x"] == round(game.ship.x, 2) and ship["y"] == round(game.ship.y, 2)
    assert ship["course"] == round(game.ship.course, 1)
    assert weapons["torpedoes"] == game.torpedo_count
    assert weapons["vls"] == game.vls_cells
    assert weapons["ciws"] == game.ciws_ammo
    assert weapons["aa"] == game.aa_ammo
    for key in ("world", "subs", "surfaces", "animals",
                "torpedoes", "enemy_torpedoes", "decoys", "asms", "essms",
                "asrocs", "nixies", "buoys", "helo", "flights", "raiders",
                "radars"):
        assert key in data, key
    assert set(ship["stations"]) == {"bridge", "sonar", "weapons", "opz",
                                     "radio", "engine", "flightdeck"}
    assert len(data["subs"]) == len(game.subs)
    assert len(data["raiders"]) == len(game.raiders)
    assert len(data["surfaces"]) == len(game.civilians) + len(game.warships)
    if game.subs:
        sub = data["subs"][0]
        assert sub["x"] == round(game.subs[0].x, 2)
        assert sub["state"] == game.subs[0].state
        assert sub["torps"] == game.subs[0].torpedoes_left
    # JSON-faechig und deterministisch.
    before = json.dumps(data, sort_keys=True, allow_nan=False)
    again = json.dumps(game._simlog_state_data(), sort_keys=True, allow_nan=False)
    assert before == again


def test_state_snapshots_stop_when_disabled_midway(game):
    game.preferences = replace(game.preferences, simlog=True)
    game._record_simlog_state(config.SIMLOG_INTERVAL_S)
    game.preferences = replace(game.preferences, simlog=False)
    game._simlog_acc = 0.0
    for _ in range(10):
        game._record_simlog_state(config.SIMLOG_INTERVAL_S)
    assert len(game.simlog) == 1


def test_state_snapshot_mixed_with_events_keeps_monotonic_seq(game):
    game.preferences = replace(game.preferences, simlog=True)
    game._record_simlog_state(config.SIMLOG_INTERVAL_S)
    game.feed.add(game.world.format_time(), "sonar", "Ping")
    game._record_simlog_state(config.SIMLOG_INTERVAL_S)
    seqs = [row["seq"] for row in game.simlog]
    assert seqs == [1, 2, 3] and seqs == sorted(seqs)
    assert [row["cat"] for row in game.simlog] == ["state", "sonar", "state"]


def test_in_game_f4_view_is_gated_live_and_input_isolated(game):
    """F4 oeffnet die Live-Ansicht nur mit aktiver Aufnahme; die Simulation
    laeuft weiter, Stations-Keys bleiben verschluckt, F4/Esc schliessen."""
    key = lambda k: pygame.event.Event(pygame.KEYDOWN, key=k, unicode="", mod=0)
    assert game.preferences.simlog is False
    game.handle_event(key(pygame.K_F4))
    assert game.simlog_view_open is False
    assert game.msg  # Hinweis-Flash

    game.preferences = replace(game.preferences, simlog=True)
    game.handle_event(key(pygame.K_F4))
    assert game.simlog_view_open is True and game.simlog_view_scroll == 0
    before = game.sim_t
    game.update(1.0)
    assert game.sim_t > before  # live: Simulation steht nicht
    station = game.station
    game.handle_event(key(pygame.K_2))
    assert game.station is station  # Stations-Keys werden verschluckt
    game.handle_event(key(pygame.K_PAGEDOWN))
    assert game.simlog_view_scroll > 0
    game.handle_event(key(pygame.K_F4))
    assert game.simlog_view_open is False and game.simlog_view_scroll == 0
    game.handle_event(key(pygame.K_F4))
    game.handle_event(key(pygame.K_ESCAPE))
    assert game.simlog_view_open is False
    game.draw()  # Ansicht laesst sich in EN zeichnen
    # Reset schliesst die Ansicht.
    game.handle_event(key(pygame.K_F4))
    assert game.simlog_view_open is True
    game.reset(31)
    assert game.simlog_view_open is False


def test_in_game_simlog_view_draws_all_languages_and_large_text(game):
    from src.core.i18n import Translator, pseudolocale
    from src.ui import layout

    game.preferences = replace(game.preferences, simlog=True)
    game.simlog_view_open = True
    for translator in (Translator("en"), Translator("de"),
                        Translator("en", catalog=pseudolocale())):
        for large in (False, True):
            game.translator = translator
            game.tr = translator.t
            game.preferences = replace(game.preferences,
                                       large_text=large, simlog=True)
            game._apply_text_size()
            with layout.capture_geometry():
                game.draw()
            assert game.screen.get_clip() == pygame.Rect(0, 0, 1280, 720)
    game.simlog_view_open = False


def test_options_menu_has_seven_rows_and_toggles_simlog(game):
    assert len(game._options_row_rects()) == 7
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F10))
    assert game.options_open
    for _ in range(5):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                             key=pygame.K_DOWN))
    assert game.options_sel == 5
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert game.preferences.simlog is True
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert game.preferences.simlog is False
    # Commander-Eintrag verschob sich auf Zeile 6.
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert game.commander_open


# --- Role-safe Remote Crew v2 history (real loopback transport) ---

@pytest.fixture
def assets(tmp_path, monkeypatch):
    for name in ("index.html", "app.js", "style.css"):
        (tmp_path / name).write_text(f"fixture {name}", encoding="utf-8")

    def files(package):
        assert package == "data.commander"
        return tmp_path

    monkeypatch.setattr(transport.resources, "files", files)
    return tmp_path


@pytest.fixture
def server(assets):
    instance = transport.CommanderServer()
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


def pair(server, name="Recorder", role=None, simlog=False):
    status, headers, session = request(server, "/api/v2/pair", "POST", {
        "code": server.pairing_code, "name": name})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    if role is not None:
        assert server.grant_station(session["client_id"], role)
    if simlog:
        assert server.set_client_grant(session["client_id"], "simlog", True)
    session = request(server, "/api/v2/session", cookie=cookie)[2]
    return cookie, session


def remote_simlog(server, cookie):
    status, _, body = request(server, "/api/v2/simlog", cookie=cookie)
    assert status == 200
    assert set(body) == {"protocol", "session", "epoch", "role", "entries"}
    assert body["protocol"] == 2
    return body


def test_v2_simlog_requires_cookie_active_role_and_host_grant(server):
    assert request(server, "/api/v2/simlog")[0] == 401
    cookie, session = pair(server)
    assert request(server, "/api/v2/simlog", cookie=cookie)[0] == 403
    assert server.set_client_grant(session["client_id"], "simlog", True)
    assert request(server, "/api/v2/simlog", cookie=cookie)[0] == 403
    assert server.grant_station(session["client_id"], "bridge")
    assert request(server, "/api/v2/simlog", cookie=cookie)[0] == 200


def test_remote_simlog_is_prior_exact_projection_not_local_truth(game, server):
    hidden = Contact(1, 998877, "passiv", "sub")
    hidden.update_passive(47.0, .8, .8, "hidden-class", game.sim_t)
    game.sonar.contacts[hidden.target_id] = hidden
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="sonar", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    prior = request(server, "/api/v2/state", cookie=cookie)[2]

    game.sim_t = 12.5
    game.feed.add("00:01", "sonar", "classified locally")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    body = remote_simlog(server, cookie)
    assert (body["session"], body["epoch"], body["role"]) == (
        prior["session"], prior["epoch"], "sonar")
    entry = body["entries"][-1]
    assert set(entry) == {"seq", "t", "stamp", "state"}
    assert entry["t"] == 12.5 and entry["stamp"] == "00:01"
    assert entry["state"] == prior
    encoded = json.dumps(body)
    assert "998877" not in encoded and "hidden-class" not in encoded
    assert not ({"subs", "surfaces", "enemy_torpedoes", "raiders"}
                & set(entry["state"]))


def test_remote_simlog_history_is_role_and_session_specific(game, server):
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    bridge_cookie, _ = pair(server, "Bridge log", "bridge", True)
    sonar_cookie, _ = pair(server, "Sonar log", "sonar", True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    bridge_prior = request(server, "/api/v2/state", cookie=bridge_cookie)[2]
    sonar_prior = request(server, "/api/v2/state", cookie=sonar_cookie)[2]
    game.feed.add("00:02", "mission", "checkpoint")
    bridge.pump(game, server, now=time.monotonic() + 1.2)

    bridge_log = remote_simlog(server, bridge_cookie)
    sonar_log = remote_simlog(server, sonar_cookie)
    assert bridge_log["entries"][-1]["state"] == bridge_prior
    assert sonar_log["entries"][-1]["state"] == sonar_prior
    assert bridge_log["entries"][-1]["state"] != sonar_log["entries"][-1]["state"]
    assert all(row["state"]["role"] == "bridge" for row in bridge_log["entries"])
    assert all(row["state"]["role"] == "sonar" for row in sonar_log["entries"])


def test_remote_simlog_is_empty_when_recording_disabled_or_context_redacted(
        game, server):
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="bridge", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    assert remote_simlog(server, cookie)["entries"] == []

    game.preferences = replace(game.preferences, simlog=True)
    game.feed.add("00:03", "mission", "visible")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    assert remote_simlog(server, cookie)["entries"]
    game.in_menu = True
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    assert remote_simlog(server, cookie)["entries"] == []


def test_remote_simlog_rebaselines_on_nonredacted_epoch_change(game, server):
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="bridge", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    game.feed.add("00:04", "mission", "before help")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    previous_epoch = remote_simlog(server, cookie)["epoch"]

    game.help_open = True
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    body = remote_simlog(server, cookie)
    assert body["epoch"] == previous_epoch + 1
    assert body["entries"] == []


def test_remote_simlog_rebaselines_when_transport_invalidates_commands(game, server):
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="bridge", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    game.feed.add("00:05", "mission", "before restart")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    assert remote_simlog(server, cookie)["entries"]

    bridge.invalidate_commands()
    bridge.pump(game, server, now=time.monotonic() + 1.8)
    body = remote_simlog(server, cookie)
    assert body["epoch"] == bridge.status["epoch"]
    assert body["entries"] == []


def test_remote_simlog_is_bounded_to_64_entries(game, server):
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="bridge", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    for index in range(80):
        game.sim_t = float(index)
        game.feed.add(f"00:{index % 60:02d}", "mission", f"event {index}")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    entries = remote_simlog(server, cookie)["entries"]
    assert len(entries) == 64
    assert len(transport._json_bytes(entries)) <= transport.SIMLOG_MAX_BYTES
    assert [entry["seq"] for entry in entries] == sorted(
        entry["seq"] for entry in entries)


def test_remote_simlog_publication_respects_byte_bound(
        game, server, monkeypatch):
    limit = 12 * 1024
    monkeypatch.setattr(transport, "SIMLOG_MAX_BYTES", limit)
    monkeypatch.setattr(commander_bridge, "SIMLOG_MAX_BYTES", limit)
    game.preferences = replace(game.preferences, simlog=True)
    bridge = CommanderBridge()
    bridge.pump(game, server, now=time.monotonic())
    cookie, _ = pair(server, role="bridge", simlog=True)
    bridge.pump(game, server, now=time.monotonic() + .6)
    for index in range(40):
        game.feed.add("00:00", "mission", f"bounded {index}")
    bridge.pump(game, server, now=time.monotonic() + 1.2)
    body = remote_simlog(server, cookie)
    entries = body["entries"]
    assert entries
    assert len(transport._json_bytes(body)) <= limit
