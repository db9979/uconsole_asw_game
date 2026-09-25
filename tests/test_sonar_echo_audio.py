"""Audible active-sonar echoes: timing, pulse character and strength."""

from unittest.mock import Mock

import pytest

from src.core import config
from src.core.game import Game


def echo_cues(game):
    return [event["kind"] for event in game._sound_events
            if event["kind"].startswith("sonar_echo")]


def pinged_game(range_nm=3.0):
    game = Game(seed=31415, start_menu=False, audio_enabled=False)
    sub = game.subs[0]
    sub.x, sub.y, sub.speed = game.ship.x + range_nm, game.ship.y, 0
    game.audio.play_echo = Mock(return_value=True)
    assert game.send_active_ping() is True
    return game


def test_echo_sounds_only_after_its_two_way_travel_time():
    game = pinged_game(3.0)
    travel_s = 2 * 3.0 * 1852 / config.SOUND_SPEED_M_S
    while game.sim_t < travel_s - .5:
        game.update(.1)
        assert not echo_cues(game)
    while not echo_cues(game) and game.sim_t < travel_s + 2:
        game.update(.1)
    assert echo_cues(game) and game.sim_t == pytest.approx(travel_s, abs=.5)
    pulse, level = game.audio.play_echo.call_args.args
    assert pulse == "CW" and 0 <= level <= 1


def test_echo_keeps_the_pulse_it_was_sent_with():
    game = pinged_game(3.0)
    assert game.sonar.cycle_pulse() == "LFM"   # operator switches after the ping
    while not echo_cues(game) and game.sim_t < 15:
        game.update(.1)
    assert echo_cues(game)[-1].startswith("sonar_echo_cw")
    assert game.audio.play_echo.call_args.args[0] == "CW"


@pytest.mark.parametrize("snr_db, cue", [(25.0, "sonar_echo_lfm"),
                                         (2.0, "sonar_echo_lfm_faint")])
def test_echo_strength_selects_loud_or_faint_cue(snr_db, cue):
    game = Game(seed=31415, start_menu=False, audio_enabled=False)
    game.audio.play_echo = Mock(return_value=True)
    game._ping_pulses[5.0] = "LFM"
    game._emit_echo(dict(t=5.0, snr_db=snr_db))
    assert echo_cues(game) == [cue]
    loud = game.audio.play_echo.call_args.args[1]
    assert loud == pytest.approx(config.clamp((snr_db + 5) / 35, 0, 1))


def test_browser_knows_every_echo_cue():
    from pathlib import Path
    app = (Path(__file__).resolve().parents[1] / "data/commander/app.js").read_text()
    for pulse in ("cw", "lfm"):
        for suffix in ("", "_faint"):
            assert f'"sonar_echo_{pulse}{suffix}"' in app
