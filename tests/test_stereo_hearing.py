"""Directional hearing: detonations, echoes and pings panned by their bearing."""

import sys
from pathlib import Path

import numpy as np

from src.audio.engine import AudioEngine
from src.audio.synthesis import PAN_STEPS, bearing_pan, stereo_pan
from src.core import opfor

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _last(rows):
    return list(rows)[-1]


def test_the_pan_follows_the_relative_bearing_in_bounded_steps():
    assert bearing_pan(90.0, 0.0) == 1.0 and bearing_pan(270.0, 0.0) == -1.0
    assert bearing_pan(0.0, 0.0) == 0.0 and bearing_pan(180.0, 0.0) == 0.0
    # Relative to the listener's head: starboard beam of a ship heading 090.
    assert bearing_pan(180.0, 90.0) == 1.0 and bearing_pan(0.0, 90.0) == -1.0
    pans = {bearing_pan(float(b), 37.0) for b in range(360)}
    assert len(pans) <= 2 * PAN_STEPS + 1 and all(-1.0 <= p <= 1.0 for p in pans)
    left, right = stereo_pan(np.ones(4, dtype=np.float32), -1.0).T
    assert np.allclose(left, 1.0) and np.allclose(right, 0.0, atol=1e-6)
    left, right = stereo_pan(np.ones(4, dtype=np.float32), 0.0).T
    assert np.allclose(left ** 2 + right ** 2, 1.0) and np.allclose(left, right)


def test_the_engine_caches_one_sound_per_pan_step():
    engine = AudioEngine(enabled=False)
    assert engine.play_effect("explosion", pan=0.5) is False
    assert engine.play_boat_cue("ping_heard", pan=-1.0) is False
    assert "ping_heard" in AudioEngine.BOAT_CUES


def test_the_frigate_hears_detonations_echoes_and_pings_from_their_bearing():
    game, server, bridge = _crewed(seed=91)
    ship = game.ship
    ship.course = 0.0
    game._emit_sound("explosion", at=(ship.x + 5.0, ship.y))         # starboard beam
    assert _last(game._sound_events)["pan"] == 1.0
    game._emit_sound("explosion", at=(ship.x - 5.0, ship.y))         # port beam
    assert _last(game._sound_events)["pan"] == -1.0
    game._emit_sound("explosion", at=(ship.x, ship.y))               # own hull: centred
    assert _last(game._sound_events)["kind"] == "shock_heavy"        # and shakes the ship
    assert [row for row in game._sound_events
            if row["kind"] == "explosion"][-1]["pan"] == 0.0
    game._emit_sound("sonar_ping")                                   # own ping: centred
    assert _last(game._sound_events)["pan"] is None
    game._emit_echo(dict(t=game.sim_t, bearing=270.0, snr_db=20.0))
    assert _last(game._sound_events)["pan"] == -1.0
    game._ping_intercepts = [(game.sim_t, ship.x + 3.0, ship.y)]
    game._deliver_ping_intercepts()
    row = _last(game._sound_events)
    assert row["kind"] == "enemy_ping" and row["pan"] == 1.0
    bridge.pump(game, server, now=5.0)
    events = server.v2_states["bridge"]["audio"]["events"]
    assert [event["pan"] for event in events[-2:]] == [-1.0, 1.0]
    assert events[-1]["cue"] == "enemy_ping"


def test_the_crewed_submarine_hears_from_its_own_head():
    game, server, bridge = _crewed(seed=92)
    boat = game.opfor
    sub = boat.sub
    sub.course = 90.0
    game._emit_sound("explosion", at=(sub.x, sub.y + 1.0))           # south: starboard
    row = _last(boat.sound_events)
    assert row["kind"] == "detonation_near" and row["pan"] == 1.0
    boat.orders.intercept("hull", 0.0, 120.0)                        # north: port
    opfor.update_crew(game, boat)
    row = _last(boat.sound_events)
    assert row["kind"] == "ping_heard" and row["pan"] == -1.0
    # A torpedo's sound or a splash is no ping on the hull.
    count = len(boat.sound_events)
    boat.orders.intercept("torpedo", 0.0, None)
    opfor.update_crew(game, boat)
    assert all(r["kind"] != "ping_heard" for r in list(boat.sound_events)[count:])
    bridge.pump(game, server, now=5.0)
    assert server.v2_states["uboot"]["audio"]["events"][-1]["pan"] == -1.0


def test_the_browser_pans_every_cue_it_is_given():
    audio = (ROOT / "data/commander/js/audio/audio.js").read_text(encoding="utf-8")
    assert "createStereoPanner" in audio and "playGameEffect(event.cue, event.pan)" in audio
    schema = (ROOT / "data/commander/js/state/schema.js").read_text(encoding="utf-8")
    assert '["seq", "cue", "pan"]' in schema
