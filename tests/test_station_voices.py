"""Each station speaks with its own voice and over its net, and browser
stations hear their side's log (``src/core/game_voice.py``,
``src/audio/voice_colour.py``, ``src/commander/log_voice_web.py``)."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

from src.audio import voice_colour
from src.commander.log_voice_web import (LOG_VOICE_CLIP_ROUTE, LogVoiceServerMixin,
                                         pump_log_voice)
from src.core import callouts
from src.core.i18n import raw_text
from src.llm import voice
from src.ui import pointer
from tests.test_llm_voice import FakeSpeechServer, _Mixer, _game, _pump, _voice_on


@pytest.fixture(autouse=True)
def _clean_pointer():
    pointer.reset()
    yield
    pointer.reset()


def _log(game, category, text):
    game.feed.add(game.world.format_time(), category, raw_text(text))


# -- voices and nets ---------------------------------------------------------------

def test_each_station_takes_another_voice_of_the_chosen_family():
    voices = [voice.station_voice("aiden", group) for group in voice.STATION_VOICE_ORDER]
    assert "aiden" not in voices and len(set(voices)) == len(voices)
    assert all(name in voice.QWEN_VOICES for name in voices)
    assert voice.station_voice("onyx", "sonar") in voice.PRESET_VOICES
    assert voice.station_voice("onyx", "sonar") != "onyx"
    # The officer, the mission, the world and unknown voices keep the chosen one.
    for group in (None, "mission", "welt"):
        assert voice.station_voice("aiden", group) == "aiden"
    assert voice.station_voice("my-own-voice", "sonar") == "my-own-voice"


def _tone(freq, rate=22050, seconds=1.0):
    t = np.arange(int(rate * seconds)) / rate
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_the_internal_net_keeps_speech_and_cuts_rumble():
    rate = 22050
    speech = voice_colour.VoiceColour("intercom", rate).feed(_tone(1000.0))
    rumble = voice_colour.VoiceColour("intercom", rate).feed(_tone(60.0))
    assert float(np.abs(speech[2000:]).max()) > 0.25
    assert float(np.abs(rumble[2000:]).max()) < 0.05
    # No colour: the officer is heard as he is.
    plain = _tone(1000.0)
    assert voice_colour.VoiceColour("", rate).feed(plain) is plain


def test_pieces_join_like_one_sound_and_the_radio_ends_with_squelch():
    rate = 22050
    tone = _tone(800.0)
    whole = voice_colour.VoiceColour("intercom", rate).feed(tone)
    parts = voice_colour.VoiceColour("intercom", rate)
    joined = np.concatenate([parts.feed(tone[:3001]), parts.feed(tone[3001:])])
    assert np.allclose(whole, joined, atol=1e-5)
    radio = voice_colour.VoiceColour("radio", rate)
    radio.feed(tone)
    tail = radio.tail()
    assert len(tail) > rate * 0.1 and float(np.abs(tail).max()) > 0.0


def test_a_station_report_asks_for_its_voice_and_comes_over_the_net():
    with FakeSpeechServer() as speech:
        game = _game()
        mixer = _Mixer(game)
        _voice_on(game, speech, tts_voice="aiden")
        game._pump_speech()
        _log(game, "sonar", "Sonar: noise bearing 270.")
        _log(game, "funk", "Radio: broadcast copied.")
        assert _pump(game, lambda: len(speech.requests) == 2 and game._voice_playing is None)
        sent = {body["input"]: body["voice"] for body in speech.requests}
        assert sent["Sonar: noise bearing two seven zero."] == voice.station_voice("aiden", "sonar")
        assert sent["Radio: broadcast copied."] == voice.station_voice("aiden", "funk")
        assert mixer.played
        assert game.voice_colour_of("log", "funk") == "radio"
        assert game.voice_colour_of("crew", "sonar") == "intercom"
        assert game.voice_colour_of("xo", None) == ""
        # Both switches off: one voice, heard as it is.
        game.set_voice_preference("tts_station_voices", False)
        game.set_voice_preference("tts_intercom", False)
        _log(game, "sonar", "Sonar: second noise.")
        assert _pump(game, lambda: len(speech.requests) == 3)
        assert speech.requests[-1]["voice"] == "aiden"
        assert game.voice_colour_of("log", "funk") == ""


def test_crew_calls_belong_to_their_station():
    assert callouts.group_of("torpedo") == "sonar"
    assert callouts.group_of("torpedo_away") == "waffen"
    assert callouts.group_of("sighting_warship") == "ausguck"
    assert callouts.group_of("lookout_torpedo") == "ausguck"
    assert callouts.group_of("broadcast") == "funk"
    assert callouts.group_of("action_stations") is None
    assert all(callouts.group_of(key) in (None, *voice.STATION_VOICE_ORDER, "mission")
               for key in callouts.KEYS)


# -- the log read aloud for browser stations ----------------------------------------

class _Server(LogVoiceServerMixin):
    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self._init_log_voice()


def _session(role):
    return {"active_station": role, "observer": False}


def test_a_listening_browser_side_gets_its_log_as_clips():
    with FakeSpeechServer() as speech:
        game = _game()
        # A host without a speaker of its own ("Server, browser only").
        _voice_on(game, speech, tts_voice="aiden")
        assert not game.voice_ready()
        server = _Server()
        published = {}
        frigate = _session("sonar")
        # Nobody listens: the host asks the service for nothing.
        pump_log_voice(server, game, published)
        game.llm_tick()
        _log(game, "sonar", "Sonar: noise bearing 270.")
        for _ in range(5):
            game.llm_tick()
        assert speech.requests == []
        # A probe only shows the switch; it does not listen.
        assert json.loads(server.log_voice_index_locked(frigate, probe=True))["on"] is True
        assert server.log_voice_listeners() == frozenset()
        json.loads(server.log_voice_index_locked(frigate))
        assert server.log_voice_listeners() == frozenset({"frigate"})
        pump_log_voice(server, game, published)
        game.llm_tick()                 # starts at the end of the log
        _log(game, "sonar", "Sonar: noise bearing 090.")

        def ready():
            game.llm_tick()
            pump_log_voice(server, game, published)
            return bool(json.loads(server.log_voice_index_locked(frigate))["clips"])
        assert _pump(game, ready)
        index = json.loads(server.log_voice_index_locked(frigate))
        assert index["on"] is True
        row = index["clips"][0]
        assert row["group"] == "sonar" and row["called"] is False
        pcm, rate = server.log_voice_clip_locked(frigate, LOG_VOICE_CLIP_ROUTE + str(row["seq"]))
        assert len(pcm) > 0 and rate == game.web_voice_rate
        assert speech.requests[-1]["voice"] == voice.station_voice("aiden", "sonar")
        # The other side's browser hears none of it, a lookout nothing at all.
        boat = _session("uboot")
        assert json.loads(server.log_voice_index_locked(boat))["clips"] == []
        assert server.log_voice_clip_locked(boat, LOG_VOICE_CLIP_ROUTE + str(row["seq"])) is None
        assert server.log_voice_index_locked(_session("lookout")) is None


def test_listeners_fade_after_a_few_seconds():
    server = _Server()
    server.publish_log_voice({}, 22050, True)
    server.log_voice_index_locked(_session("opz"))
    now = time.monotonic()
    assert server.log_voice_listeners(now) == frozenset({"frigate"})
    assert server.log_voice_listeners(now + 30.0) == frozenset()
