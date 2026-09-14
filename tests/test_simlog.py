"""Simulationsprotokoll: Options-Toggle, begrenzte Aufnahme, Commander #simlog."""

import json
import re
from contextlib import closing
from dataclasses import replace
from importlib import resources

import pygame
import pytest

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.i18n import message
from src.core.preferences import load_preferences, save_preferences, Preferences
import src.commander.server as transport


class FakeServer:
    """Detached transport fixture for bridge-level simlog tests."""

    def __init__(self):
        self.connected = True
        self.lease = 1
        self.queue = []
        self.state = None
        self.simlog = b"[]"
        self.simlog_calls = 0

    @property
    def lease_generation(self):
        return self.lease

    def publish(self, state, chart=None):
        json.dumps(state, allow_nan=False)
        self.state = state

    def publish_simlog(self, payload):
        rows = json.loads(payload.decode("utf-8"))
        assert type(rows) is list
        self.simlog = payload
        self.simlog_calls += 1

    def drain_commands(self, limit=4):
        assert limit == 4
        batch, self.queue = self.queue[:limit], self.queue[limit:]
        return batch

    def is_current(self, envelope):
        return self.connected and envelope["lease"] == self.lease

    def revoke(self):
        self.lease += 1
        self.connected = False
        self.queue.clear()


@pytest.fixture
def game():
    return Game(seed=31, start_menu=False, audio_enabled=False, language="en")


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


def test_bridge_publishes_simlog_once_per_change_and_localizes(game):
    server = FakeServer()
    bridge = CommanderBridge()
    game.preferences = replace(game.preferences, simlog=True)
    game.sim_t = 5.0
    game.feed.add("00:05", "mission", message("runtime.raid.downed"))
    bridge.pump(game, server, now=1.0)
    rows = json.loads(server.simlog.decode("utf-8"))
    assert len(rows) == 1
    assert rows[0]["text"] == "AA gun: hostile aircraft destroyed."
    assert rows[0]["stamp"] == "00:05" and rows[0]["cat"] == "mission"
    calls = server.simlog_calls
    bridge.pump(game, server, now=1.6)
    assert server.simlog_calls == calls  # ohne Aenderung nicht erneut
    game.feed.add("00:06", "sonar", "Ping")
    bridge.pump(game, server, now=2.2)
    assert len(json.loads(server.simlog.decode("utf-8"))) == 2


def test_bridge_publishes_empty_simlog_when_disabled_or_redacted(game):
    server = FakeServer()
    bridge = CommanderBridge()
    bridge.pump(game, server, now=1.0)
    assert server.simlog == b"[]"
    game.preferences = replace(game.preferences, simlog=True)
    game.feed.add("00:05", "mission", "Ereignis")
    bridge.pump(game, server, now=1.6)
    assert len(json.loads(server.simlog.decode("utf-8"))) == 1
    game.in_menu = True
    bridge.pump(game, server, now=2.2)
    assert server.simlog == b"[]"


def test_bridge_simlog_payload_respects_server_byte_bound(monkeypatch, game):
    server = FakeServer()
    bridge = CommanderBridge()
    big = "x" * (transport.SIMLOG_MAX_BYTES // 4 + 1)
    rows = [dict(seq=i + 1, t=0.0, stamp="00:00", cat="mission", text=big)
            for i in range(128)]
    game.preferences = replace(game.preferences, simlog=True)
    game.simlog.extend(rows)
    game._simlog_seq = 128
    bridge.pump(game, server, now=1.0)
    published = json.loads(server.simlog.decode("utf-8"))
    assert len(published) < len(rows)
    assert all(type(item["text"]) is str for item in published)


# --- Server-Route (echte Loopback) ---

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


def test_simlog_route_requires_authentication(server):
    import http.client
    host, port = server.address
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as client:
        client.request("GET", "/api/v1/simlog")
        assert client.getresponse().status == 401


def test_simlog_route_serves_published_payload(server):
    import http.client
    token = None
    host, port = server.address
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as client:
        client.request("POST", "/api/v1/pair",
                       body=json.dumps({"code": server.pairing_code}),
                       headers={"Content-Type": "application/json",
                                "Origin": f"http://{host}:{port}"})
        body = json.loads(client.getresponse().read())
        token = body["token"]
    server.publish_simlog(json.dumps(
        [{"seq": 1, "t": 2.0, "stamp": "00:07", "cat": "mission",
          "text": "Missionsstart"}],
        ensure_ascii=False).encode("utf-8"))
    with closing(http.client.HTTPConnection(host, port, timeout=3)) as client:
        client.request("GET", "/api/v1/simlog",
                       headers={"Authorization": f"Bearer {token}"})
        response = client.getresponse()
        assert response.status == 200
        rows = json.loads(response.read().decode("utf-8"))
        assert rows[0]["text"] == "Missionsstart" and rows[0]["seq"] == 1


@pytest.mark.parametrize("payload", [b"{}", b"[", b"]", b"[[1]]", b""])
def test_publish_simlog_rejects_invalid_payload(server, payload):
    with pytest.raises(ValueError):
        server.publish_simlog(payload)


def test_web_assets_expose_hidden_simlog_view():
    assets = resources.files("data.commander")
    html = assets.joinpath("index.html").read_text(encoding="utf-8")
    js = assets.joinpath("app.js").read_text(encoding="utf-8")
    css = assets.joinpath("style.css").read_text(encoding="utf-8")
    assert 'id="simlog-view"' in html and "hidden" in html
    assert 'id="simlog-list"' in html
    assert 'id="simlog-current"' in html
    for identity in ("simlog-current-map", "simlog-map-dialog", "simlog-map",
                     "simlog-map-close", "simlog-map-world",
                     "simlog-map-units-fit", "simlog-map-units"):
        assert f'id="{identity}"' in html
    assert "#simlog" in js and "/simlog" in js
    assert "hashchange" in js and "validateSimlog" in js
    # State-Snapshots werden als Tabellen gerendert, nicht als rohes JSON.
    assert "simlogCurrentState" in js and "simlog-table" in js
    assert "simlogMapItems" in js and "drawSimlogMap" in js
    assert "simlogMapLabel" in js and "Math.sin(angle)" in js
    assert "plotted.forEach(({ item, x }, index)" in js
    assert 'item.section === "ship"' in js
    assert "simlogSectionRows" in js  # helo object is rendered as one row
    assert "JSON.stringify(row.data" not in js
    assert ".simlog-list" in css and ".simlog-entry" in css
    assert ".simlog-table" in css and ".simlog-current" in css
    assert re.search(r"\.simlog-table-wrap\s*\{[^}]*grid-column:\s*1\s*/\s*-1", css)
    assert re.search(r"\.simlog-table-wrap\s*\{[^}]*overflow-x:\s*auto", css)
    assert "#simlog-map-dialog" in css and "#simlog-map" in css
    map_renderer = js.split("function simlogMapItems", 1)[1].split(
        "function simlogSummary", 1)[0]
    assert "sendCommand" not in map_renderer and "snapshot.tracks" not in map_renderer
    for section in ("subs", "surfaces", "animals", "torpedoes",
                    "enemy_torpedoes", "decoys", "asms", "essms", "asrocs",
                    "nixies", "buoys", "flights", "raiders", "helo"):
        assert section in map_renderer or section in js.split(
            "const simlogStateSections", 1)[1].split(";", 1)[0]
    # Die versteckte Ansicht ist nicht aus der normalen UI verlinkt.
    assert 'href="#simlog"' not in html
