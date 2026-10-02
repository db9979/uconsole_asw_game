"""Spoken crew reports: feed mapping, spoken text, speaker and projection."""

import json
import re
from pathlib import Path

import pygame

from src.audio.speech import QUEUE_MAX, Speaker
from src.core import callouts
from src.core.game import Game
from src.core.i18n import Translator, message

ROOT = Path(__file__).resolve().parents[1]


def _game(**kwargs):
    return Game(seed=77, start_menu=False, audio_enabled=False, language="en", **kwargs)


def test_feed_messages_map_to_callouts_with_bearings():
    assert callouts.callout_of(message("runtime.torpedo_cue.seeker", bearing="270.4")) == (
        "torpedo", 270)
    assert callouts.callout_of(message("runtime.contact.new_bearing", contact=3,
                                       bearing=" 359.7", range="", origin="P")) == ("contact", 0)
    assert callouts.callout_of(message("runtime.torpedo.feed", torpedo=1,
                                       contact=2)) == ("torpedo_away", None)
    assert callouts.callout_of(message("runtime.mission.won")) == ("won", None)
    assert callouts.callout_of(message("runtime.echo.feed")) is None
    assert callouts.callout_of("plain text") is None
    # A malformed bearing is never spoken.
    assert callouts.callout_of(message("runtime.breakup_noise", bearing="n/a")) is None
    assert callouts.callout_of(message("runtime.breakup_noise", bearing="nan")) is None


def test_spoken_text_says_bearings_digit_by_digit_in_both_languages():
    row = dict(seq=1, key="torpedo", bearing=270)
    assert callouts.spoken_text(row, Translator("en").t) == (
        "Torpedo in the water, bearing two seven zero")
    assert callouts.spoken_text(row, Translator("de").t) == (
        "Torpedo im Wasser, Peilung zwo sieben null")
    assert callouts.spoken_text(dict(seq=2, key="contact", bearing=5),
                                Translator("en").t).endswith("zero zero five")
    for key in callouts.KEYS:
        for language in ("en", "de"):
            text = callouts.spoken_text(dict(seq=1, key=key, bearing=90), Translator(language).t)
            assert text and "{" not in text and callouts.PREFIX not in text


def test_game_feed_fills_a_bounded_transient_log():
    game = _game()
    for index in range(callouts.MAX_CALLOUTS + 5):
        game.feed.add("00:00", "sonar", message("runtime.breakup_noise",
                                                bearing=f"{index:05.1f}"))
    rows = game.callouts.detached()
    assert len(rows) == callouts.MAX_CALLOUTS
    assert [row["seq"] for row in rows] == list(range(6, callouts.MAX_CALLOUTS + 6))
    assert rows[-1] == dict(seq=callouts.MAX_CALLOUTS + 5, key="breakup",
                            bearing=callouts.MAX_CALLOUTS + 4)
    rows[-1]["key"] = "changed"
    assert game.callouts.rows[-1]["key"] == "breakup"
    game.reset(77)
    assert not game.callouts.rows and game.callouts.seq == callouts.MAX_CALLOUTS + 5


class _Process:
    def __init__(self, calls, args):
        calls.append(args)
        self.running = True

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.running = False


def test_speaker_runs_one_process_and_bounds_its_queue():
    calls = []
    processes = []

    def popen(args, **kwargs):
        assert kwargs["stdout"] is not None and kwargs["close_fds"] is True
        processes.append(_Process(calls, args))
        return processes[-1]

    speaker = Speaker("/usr/bin/espeak-ng", popen=popen)
    for index in range(6):
        speaker.say(f"report {index}", "de")
    assert len(calls) == 1 and calls[0][:3] == ["/usr/bin/espeak-ng", "-v", "de"]
    assert calls[0][-2:] == ["--", "report 0"]
    assert [text for text, _ in speaker.queue] == [f"report {i}" for i in range(3, 6)]
    assert len(speaker.queue) == QUEUE_MAX
    processes[0].running = False
    speaker.pump()
    assert calls[-1][-1] == "report 3"
    speaker.stop()
    assert not speaker.queue and processes[-1].running is False
    silent = Speaker(None, popen=popen)
    silent.say("nothing", "en")
    assert len(calls) == 2 and not silent.queue


def test_broken_engine_silences_the_speaker():
    def popen(*_args, **_kwargs):
        raise OSError("gone")

    speaker = Speaker("/usr/bin/espeak-ng", popen=popen)
    speaker.say("x", "en")
    assert not speaker.available and not speaker.queue


def test_game_speaks_only_when_enabled_and_on_the_frigate(monkeypatch):
    from dataclasses import replace
    game = _game()
    said = []
    game.speaker = Speaker("espeak-ng", popen=lambda args, **_k: said.append(args[-1]) or
                           type("P", (), {"poll": lambda self: 0})())
    game.feed.add("00:00", "sonar", message("runtime.torpedo_cue.transient", bearing="045.0"))
    game._pump_speech()
    assert said == []          # option off: consumed, not spoken
    game.preferences = replace(game.preferences, speech=True)
    game._pump_speech()
    assert said == []          # already consumed
    game.feed.add("00:00", "mission", message("runtime.mission.lost"))
    game._pump_speech()
    assert said == ["Mission lost"]
    game.local_side = "uboot"
    game.feed.add("00:00", "sonar", message("runtime.breakup_noise", bearing="100"))
    game._pump_speech()
    assert said == ["Mission lost"]


def test_speech_preference_round_trips_and_defaults_off(tmp_path):
    from src.core.preferences import Preferences, load_preferences, save_preferences
    path = tmp_path / "settings.json"
    assert load_preferences(path).speech is False
    save_preferences(Preferences(speech=True), path)
    assert load_preferences(path).speech is True
    path.write_text(json.dumps({"speech": 1}), encoding="utf-8")
    assert load_preferences(path).speech is False


def test_options_setup_page_toggles_speech(monkeypatch):
    from src.core import game_draw
    monkeypatch.setattr(game_draw, "save_preferences", lambda *_a, **_k: None)
    game = Game(seed=77, start_menu=True, audio_enabled=False, language="de")
    game._open_administration("options")
    game._set_options_page(1)
    for _ in range(2):
        game._handle_administration_key(pygame.K_DOWN)
    assert game._option_rows()[game.options_sel] == "speech"
    game.draw()
    game._handle_administration_key(pygame.K_RETURN)
    assert game.preferences.speech is True
    game.draw()
    rects = Game._option_row_hit_rects(Game._OPTION_ROWS_SETUP)
    assert rects[2] == Game._options_row_rects()[Game._SETUP_ROW_INDICES[2]]


def test_projection_carries_callouts_to_every_frigate_role():
    from src.commander.bridge import CommanderBridge
    from test_commander_bridge import Server
    game = _game()
    game.feed.add("00:00", "sonar", message("runtime.torpedo_cue.seeker", bearing="123.0"))
    server = Server()
    CommanderBridge().pump(game, server, now=10.0)
    expected = [dict(seq=1, key="torpedo", bearing=123)]
    for role in ("bridge", "sonar", "eloka"):
        assert server.v2_states[role]["audio"]["callouts"] == expected


def test_browser_allowlist_matches_the_callout_keys():
    shared = (ROOT / "data/commander/js/state/shared.js").read_text(encoding="utf-8")
    block = shared[shared.index("const calloutKinds"):]
    block = block[:block.index(";")]
    assert tuple(re.findall(r'"([a-z_]+)"', block)) == callouts.KEYS
    catalog = json.loads((ROOT / "data/i18n/en.json").read_text(encoding="utf-8"))
    for key in callouts.KEYS:
        assert callouts.PREFIX + key in catalog
    audio = (ROOT / "data/commander/js/audio/audio.js").read_text(encoding="utf-8")
    assert "speechSynthesis" in audio and "innerHTML" not in audio
