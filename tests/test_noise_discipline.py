"""Noise discipline: crew mishaps, the players' voices and who hears them."""

import sys
from pathlib import Path

import pytest

from src.core import noise_discipline as nd
from src.core.game import Game
from src.core.i18n import localize

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402
from test_commander_sessions_v2 import pair_v2, request, server  # noqa: E402,F401


def test_voice_bands_and_noise_follow_the_thresholds():
    assert [nd.band(level) for level in (0, nd.VOICE_SAFE, nd.VOICE_SAFE + 1,
                                         nd.VOICE_LOUD, nd.VOICE_LOUD + 1, nd.VOICE_LEVEL_MAX)] \
        == ["quiet", "quiet", "near", "near", "far", "far"]
    assert nd.voice_noise(nd.VOICE_SAFE) == 0.0
    assert nd.voice_noise(nd.VOICE_LEVEL_MAX) == pytest.approx(nd.VOICE_NOISE_MAX)
    assert nd.voice_noise(8) < nd.voice_noise(15)


def test_a_weak_crew_fumbles_more_and_silent_running_cuts_it():
    fresh, tired = nd.risk_per_h(1.0, False), nd.risk_per_h(0.6, False)
    assert tired > fresh
    assert nd.risk_per_h(1.0, True) == pytest.approx(fresh * nd.QUIET_RISK)
    windows = range(200000)
    count = sum(nd.mishap(7, 3, window, fresh) is not None for window in windows)
    expected = fresh * nd.TICK_S / 3600.0 * len(windows)
    assert 0.7 * expected <= count <= 1.3 * expected
    assert [nd.mishap(7, 3, w, 50.0) for w in range(50)] == \
        [nd.mishap(7, 3, w, 50.0) for w in range(50)]


def test_own_machinery_masks_the_crew():
    assert nd.crew_noise(0.0, True, 0) == pytest.approx(nd.MISHAP_NOISE)
    assert nd.crew_noise(0.9, True, 0) < 0.1 * nd.MISHAP_NOISE + 1e-9
    assert nd.hear_nm(False, nd.VOICE_SAFE, 0.0) == 0.0
    assert nd.hear_nm(True, 0, 0.0) == pytest.approx(nd.MISHAP_HEAR_NM)


@pytest.fixture
def game(monkeypatch):
    value = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    monkeypatch.setattr(value.world, "sonar_path_blocked", lambda *args: False)
    return value


def _texts(game, count=6):
    return [str(localize(item.text, game.tr)) for item in game.feed.recent(count)]


def test_a_mishap_under_quiet_mode_is_louder_and_reported(game, monkeypatch):
    game.ship.quiet_mode = True
    quiet = game.ship.noise_level()
    monkeypatch.setattr(nd, "mishap", lambda seed, key, window, rate: "hatch" if key == 0 else None)
    game._update_sim(0.1)
    assert game.ship.crew_noise > 0.0
    assert game.ship.noise_level() > quiet
    assert any("hatch slammed" in text for text in _texts(game))
    monkeypatch.setattr(nd, "mishap", lambda *args: None)
    game._update_sim(0.1)
    assert game.ship.crew_noise == 0.0


def test_the_frigate_hears_a_submarine_crew_fumble(game, monkeypatch):
    sub = next(sub for sub in game.subs if not sub.sunk)
    sub.x, sub.y = game.ship.x + 0.5, game.ship.y
    sub_key = int(sub.id) + 1
    monkeypatch.setattr(nd, "mishap",
                        lambda seed, key, window, rate: "tool" if key == sub_key else None)
    game.ship.speed = 0.0
    events = len(game._sound_events)
    game._update_sim(0.1)
    assert sub.crew_noise > 0.0
    assert any("metallic transient" in text for text in _texts(game))
    assert "crew_transient" in [row["kind"] for row in list(game._sound_events)[events:]]
    reported = len([text for text in _texts(game, 20) if "metallic transient" in text])
    game._update_sim(0.1)
    assert len([text for text in _texts(game, 20) if "metallic transient" in text]) == reported


def test_voices_are_held_input_heard_and_told_off(game):
    assert game.set_crew_voice("frigate", nd.VOICE_LEVEL_MAX)
    assert not game.set_crew_voice("frigate", nd.VOICE_LEVEL_MAX + 1)
    assert not game.set_crew_voice("helicopter", 3)
    game._update_sim(0.1)
    assert game.crew_voice_level("frigate") == nd.VOICE_LEVEL_MAX
    assert game.ship.crew_noise > 0.0
    assert any("too loud" in text for text in _texts(game))
    for _ in range(int(nd.VOICE_HOLD_S / 0.1) + 2):
        game._update_sim(0.1)
    assert game.crew_voice_level("frigate") == 0
    assert game.ship.crew_noise == 0.0 or game.ship.crew_noise == pytest.approx(
        nd.crew_noise(game.ship.machinery_noise_level(), True, 0))


def test_quiet_mode_slows_the_repair_teams(game):
    game._apply_crew_effects()
    normal = game.damage.crew_factor
    game.ship.quiet_mode = True
    game._apply_crew_effects()
    assert game.damage.crew_factor == pytest.approx(normal * nd.QUIET_WORK_FACTOR)


def test_the_crewed_boat_hears_the_frigate_and_its_own_fumbles(monkeypatch):
    game, server, bridge = _crewed()
    boat = game.opfor
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: False)
    boat.sub.x, boat.sub.y = game.ship.x + 0.4, game.ship.y
    game.ship.speed = 0.0
    boat.orders.silent = True
    boat.sub.speed = 2.0
    boat_key = int(boat.sub.id) + 1
    monkeypatch.setattr(nd, "mishap", lambda seed, key, window, rate: "pot")
    game._update_sim(0.1)
    keys = [key for key, _ in boat.orders._events]
    assert "crew_mishap_pot" in keys and "transient_heard" in keys
    cues = [row["kind"] for row in boat.sound_events]
    assert "crew_clank" in cues and "crew_transient" in cues
    assert boat.sub.crew_noise > 0.0 and boat_key > 0


def test_the_bridge_hands_browser_microphones_to_the_game(game):
    class Levels:
        def mic_levels(self, now=None):
            return {"frigate": 14, "uboot": 0}

    from src.commander.bridge import CommanderBridge
    CommanderBridge._pump_microphones(game, Levels(), "live", None)
    assert game.crew_voice_level("frigate") == 14
    assert game.crew_voice_level("uboot") == 0
    game.clear_crew_voices()
    CommanderBridge._pump_microphones(game, Levels(), "menu", None)
    assert game.crew_voice_level("frigate") == 0


def test_server_keeps_only_fresh_levels_of_station_holders():
    from src.commander.server import CommanderServer
    server = CommanderServer()
    session = {"active_station": "sonar", "lookout_only": False, "observer": False,
               "leases": {"sonar": {"generation": 1}}}
    phone = dict(session, active_station="lookout", leases={"lookout": {}}, lookout_only=True)
    with server._lock:
        server._sessions_v2["a"] = session
        server._sessions_v2["b"] = phone
        assert server.set_mic_level_locked(session, "a", 13, 100.0)
        assert not server.set_mic_level_locked(session, "a", 21, 100.0)
        assert not server.set_mic_level_locked(session, "a", 2.5, 100.0)
        assert not server.set_mic_level_locked(phone, "b", 13, 100.0)
    assert server.mic_levels(100.5) == {"frigate": 13, "uboot": 0}
    assert server.mic_levels(100.0 + 10.0) == {"frigate": 0, "uboot": 0}


def test_level_mapping_of_the_local_microphone():
    from src.audio.microphone import Microphone, level_of
    assert level_of(0.0) == 0
    assert level_of(1.0) == 20
    assert 0 < level_of(0.01) < level_of(0.1) < 20
    assert Microphone().level() == 0


def test_mic_route_needs_csrf_a_station_and_a_valid_level(server):  # noqa: F811
    _, cookie, _, body = pair_v2(server)
    route = "/api/v2/mic"
    assert request(server, route, "POST", {"protocol": 2, "level": 12},
                   cookie, body["csrf"])[0] == 409          # no station yet
    assert server.grant_station(body["client_id"], "sonar")
    assert request(server, route, "POST", {"protocol": 2, "level": 12},
                   cookie, "wrong")[0] == 403
    for invalid in ({"protocol": 2, "level": 21}, {"protocol": 2, "level": 1.5},
                    {"protocol": 1, "level": 3}, {"level": 3}, []):
        assert request(server, route, "POST", invalid, cookie, body["csrf"])[0] in (400, 409)
    assert request(server, route, "POST", {"protocol": 2, "level": 12},
                   cookie, body["csrf"])[0] == 200
    assert server.mic_levels() == {"frigate": 12, "uboot": 0}
