"""Atmosphere in the crewed boat: hull creaks, detonations, red light."""

import re
import sys
from pathlib import Path

import numpy as np
import pygame

from src.audio.engine import AudioEngine
from src.audio.synthesis import boat_effect
from src.core import config, opfor
from src.ui import uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _cues(boat):
    return [row["kind"] for row in boat.sound_events]


def test_the_hull_creaks_only_deep_down_and_deterministically():
    test = 250.0
    assert opfor.creak_chance(100.0, test) == 0.0
    assert opfor.creak_chance(test * config.UBOOT_CREAK_START, test) \
        == config.UBOOT_CREAK_MIN_CHANCE
    assert opfor.creak_chance(test, test) == 1.0
    heard = []
    for _ in range(2):
        game, _server, _bridge = _crewed(seed=61)
        boat = game.opfor
        game.world.depth_m = lambda x, y: 3000.0
        sub = boat.sub
        sub.depth = sub.target_depth = sub.order_depth = sub.stype.max_depth_m * 0.8
        _run(game, 120)
        heard.append(_cues(boat).count("hull_creak"))
    assert heard[0] == heard[1] >= 3
    game, _server, _bridge = _crewed(seed=61)
    game.opfor.sub.depth = game.opfor.sub.target_depth = 30.0
    game.opfor.sub.order_depth = 30.0
    _run(game, 30)
    assert "hull_creak" not in _cues(game.opfor)


def test_the_hull_rests_between_creaks_even_at_test_depth():
    """At test depth every check would creak; a quiet spell after each creak
    keeps it from ticking every 4 s at every station (1.3.169)."""
    game, _server, _bridge = _crewed(seed=63)
    boat = game.opfor
    game.world.depth_m = lambda x, y: 3000.0
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = sub.stype.max_depth_m
    times = []
    for _ in range(int(180 / 0.1)):
        before = boat.sound_seq
        game._update_sim(0.1)
        sub.depth = sub.stype.max_depth_m
        if any(row["kind"] == "hull_creak" and row["seq"] > before
               for row in boat.sound_events):
            times.append(game.sim_t)
    low, high = config.UBOOT_CREAK_GAP_TICKS
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) >= 5
    assert min(gaps) >= low * config.UBOOT_CREAK_TICK_S - 0.2
    assert max(gaps) <= high * config.UBOOT_CREAK_TICK_S + 0.2


def test_the_boat_hears_detonations_near_and_far_with_a_bearing():
    game, server, bridge = _crewed(seed=62)
    boat = game.opfor
    sub = boat.sub
    game._emit_sound("explosion", at=(sub.x + 1.0, sub.y))            # 090, close
    game._emit_sound("explosion", at=(sub.x, sub.y - 10.0))           # 000, distant
    game._emit_sound("explosion", at=(sub.x + 40.0, sub.y))           # out of hearing
    assert _cues(boat) == ["detonation_near", "detonation_far"]
    events = {key: values for key, values in boat.orders._events}
    near = int(events["detonation_near"]["bearing"])
    far = int(events["detonation_far"]["bearing"])
    assert abs(((near - 90 + 180) % 360) - 180) <= 12
    assert abs(((far + 180) % 360) - 180) <= 12
    _run(game, 1)
    texts = _feed_texts(game)
    assert any("Detonation close aboard" in text for text in texts)
    assert any("Distant detonation" in text for text in texts)
    # The boat's browsers get the boat's cues; the frigate's stations never do.
    game._emit_sound("gunfire")
    bridge.pump(game, server, now=5.0)
    assert [row["cue"] for row in server.v2_states["uboot"]["audio"]["events"]] == _cues(boat)
    assert [row["cue"] for row in server.v2_states["uboot_sonar"]["audio"]["events"]] \
        == _cues(boat)


def test_a_hull_failure_cracks_audibly():
    game, _server, _bridge = _crewed(seed=63)
    boat = game.opfor
    game.world.depth_m = lambda x, y: 3000.0
    boat.sub.depth = boat.sub.stype.max_depth_m * 1.2
    boat.sub._hull_failure(1.2)
    opfor.update_crew(game, boat)
    assert "hull_crack" in _cues(boat)


def test_boat_cues_synthesize_and_play_only_as_boat_cues():
    rate = 8000
    signals = [boat_effect(kind, rate) for kind in sorted(AudioEngine.BOAT_CUES)]
    for signal in signals:
        assert signal.dtype == np.float32 and signal.size > 100
        assert np.isfinite(signal).all() and 0 < np.max(np.abs(signal)) <= 1
        assert signal[0] == signal[-1] == 0
    assert np.array_equal(boat_effect("hull_creak", rate), boat_effect("hull_creak", rate))
    engine = AudioEngine(enabled=False)
    assert engine.play_boat_cue("hull_creak") is False
    assert engine.play_boat_cue("explosion") is False


def test_every_published_cue_is_known_to_the_browser():
    shared = (ROOT / "data/commander/js/state/shared.js").read_text(encoding="utf-8")
    block = re.search(r"gameEffectKinds = new Set\(\[(.*?)\]\)", shared, re.S).group(1)
    kinds = set(re.findall(r'"([a-z_]+)"', block))
    assert AudioEngine.BOAT_CUES <= kinds and set(opfor.BOAT_CUES) <= kinds
    emitted = set()
    for path in (ROOT / "src").rglob("*.py"):
        emitted |= set(re.findall(r'_emit_sound\("([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert emitted <= kinds
    audio = (ROOT / "data/commander/js/audio/audio.js").read_text(encoding="utf-8")
    for kind in kinds:
        assert re.search(rf"\b{kind}:", audio), kind


def test_silent_running_rigs_the_boat_for_red_light():
    game, _server, _bridge = _crewed(seed=64)
    boat = game.opfor
    surface = pygame.Surface((8, 8))
    surface.fill((255, 255, 255))
    assert uboot_view.silent_light(surface, boat) is False
    boat.orders.silent = True
    assert uboot_view.silent_light(surface, boat) is True
    assert tuple(surface.get_at((1, 1)))[:3] == tuple(
        min(255, a + b) for a, b in zip(config.UBOOT_SILENT_LIGHT, config.UBOOT_SILENT_LIGHT_FLOOR))
    game.local_side = "uboot"
    uboot_view.draw(game)
    red, green, blue = tuple(game.screen.get_at((640, 400)))[:3]
    assert red > green and red > blue
