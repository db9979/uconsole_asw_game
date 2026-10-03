"""Shipboard atmosphere cues: alarm bells, hull slamming, the boat's fans (1.3.119)."""

import re
import sys
from pathlib import Path

import numpy as np

from src.audio.engine import AudioEngine
from src.audio.synthesis import ATMOSPHERE_KINDS, atmosphere_effect
from src.core import config
from src.core.game import Game

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _kinds(game):
    return [row["kind"] for row in game._sound_events]


def test_atmosphere_cues_are_bounded_and_deterministic():
    for kind in ATMOSPHERE_KINDS:
        first = atmosphere_effect(kind, 22050)
        assert first.dtype == np.float32 and 0 < first.size <= 22050 * 3
        assert np.all(np.isfinite(first)) and np.max(np.abs(first)) <= 1.0
        assert np.array_equal(first, atmosphere_effect(kind, 22050))
    for kind in ("alarm_bell", "fans_down", "fans_up"):
        assert kind in AudioEngine.BOAT_CUES


def test_action_stations_ring_the_general_alarm():
    game = Game(seed=4, start_menu=False, audio_enabled=False)
    assert game.set_action_stations(True) is True
    assert _kinds(game)[-1] == "general_alarm"
    count = len(game._sound_events)
    assert game.set_action_stations(False) is True
    assert len(game._sound_events) == count
    game.audio.shutdown()


def test_bow_slams_into_a_heavy_head_sea():
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.world.sea_state = 5
    game.world.refresh_weather()
    game.ship.target_speed = 20.0
    for _ in range(1500):
        game._update_sim(0.1)
    assert "hull_slam" in _kinds(game) or any(
        row["kind"] == "hull_slam" for row in game._sound_events)
    game.audio.shutdown()
    calm = Game(seed=5, start_menu=False, audio_enabled=False)
    calm.world.sea_state = 1
    calm.world.refresh_weather()
    calm.ship.target_speed = 20.0
    for _ in range(600):
        calm._update_sim(0.1)
        assert "hull_slam" not in _kinds(calm)
    calm.audio.shutdown()


def test_the_bow_slams_now_and_then_not_on_every_wave():
    """A heavy head sea used to slam the bow every 5 to 18 s at every
    station; after a slam the next waits HULL_SLAM_GAP_MIN_S to _MAX_S."""
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.world.sea_state = 6
    game.world.refresh_weather()
    game.ship.target_speed = 25.0
    times = []
    for _ in range(6000):
        before = game._sound_event_seq
        game._update_sim(0.1)
        if any(row["kind"] == "hull_slam" and row["seq"] > before
               for row in game._sound_events):
            times.append(game.sim_t)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) >= 3
    assert min(gaps) >= config.HULL_SLAM_GAP_MIN_S
    game.audio.shutdown()


def test_silent_running_runs_the_fans_down_and_up():
    game, _server, _bridge = _crewed()
    boat = game.opfor
    for _ in range(3):
        game._update_sim(0.1)
    assert boat.sub.command_silent(True) is True
    for _ in range(3):
        game._update_sim(0.1)
    assert boat.sound_events[-1]["kind"] == "fans_down"
    assert boat.sub.command_silent(False) is True
    for _ in range(3):
        game._update_sim(0.1)
    assert boat.sound_events[-1]["kind"] == "fans_up"
    game.audio.shutdown()


def test_the_browser_knows_every_atmosphere_cue():
    shared = (ROOT / "data/commander/js/state/shared.js").read_text(encoding="utf-8")
    audio = (ROOT / "data/commander/js/audio/audio.js").read_text(encoding="utf-8")
    for kind in ATMOSPHERE_KINDS:
        assert f'"{kind}"' in shared
        assert re.search(rf"\b{kind}: \[", audio)
