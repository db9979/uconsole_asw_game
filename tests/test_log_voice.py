"""The stations' log entries read aloud by the language model's voice
(``src/core/game_voice.py``), muted per station of the log."""

from __future__ import annotations

import dataclasses
import itertools
import json
import time

import pygame
import pytest

from src.core import config
from src.core.game_advisor import LOG_ROWS
from src.core.game import Game
from src.core.i18n import message, raw_text
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.llm import voice
from src.ui import layout, log_voice_view, pointer
from tests.test_llm_voice import FakeSpeechServer, _Mixer, _game, _pump, _voice_on


def _log(game, category, text):
    game.feed.add(game.world.format_time(), category, raw_text(text))


def _said(speech):
    return [body["input"] for body in speech.requests]


def test_log_entries_are_read_after_the_officer_and_dropped_when_old():
    service = voice.VoiceService(voice.VoiceConfig(enabled=True), queue_max=2)
    service._ensure_worker = lambda: None
    a, b, c = (service.say(text, "en", "log") for text in ("A.", "B.", "C."))
    # A full log queue drops its oldest entry, like the crew's calls.
    assert a.status == "dropped" and b.status == c.status == "pending"
    xo = service.say("Officer.", "en", "xo")
    assert service._next() is xo and service._next() is b
    assert voice.ROLES.index("log") > voice.ROLES.index("xo")
    assert voice.STALE_S["log"] < voice.STALE_S["crew"]


def test_new_log_entries_are_spoken_and_a_muted_station_is_not():
    with FakeSpeechServer() as speech:
        game = _game()
        mixer = _Mixer(game)
        _voice_on(game, speech)
        game._pump_speech()             # starts at the end of the log
        _log(game, "sonar", "Sonar: noise bearing 270.")
        assert _pump(game, lambda: mixer.played and game._voice_playing is None)
        # Numbers digit by digit, as the officer says them.
        assert _said(speech) == ["Sonar: noise bearing two seven zero."]
        game.toggle_log_voice("sonar")
        assert not game.preferences.tts_log_sonar
        _log(game, "sonar", "Sonar: second noise.")
        _log(game, "navigation", "Bridge: course 090.")
        assert _pump(game, lambda: len(speech.requests) == 2 and game._voice_playing is None)
        assert _said(speech)[-1] == "Bridge: course zero niner zero."
        # Both still counted for the settings page.
        assert game.log_voice_count("sonar") == 2 and game.log_voice_count("navigation") == 1
        # The master switch silences every station.
        game.set_voice_preference("tts_log", False)
        _log(game, "navigation", "Bridge: course 180.")
        _pump(game, lambda: False, timeout=0.3)
        assert len(speech.requests) == 2


def test_old_entries_of_a_new_mission_or_load_are_not_read():
    with FakeSpeechServer() as speech:
        game = _game()
        _Mixer(game)
        _voice_on(game, speech)
        _log(game, "sonar", "Before the voice looked.")
        game._pump_speech()
        game.reset(4471)
        _log(game, "sonar", "Logged during the reset.")
        _pump(game, lambda: False, timeout=0.3)
        assert speech.requests == []


def test_crew_calls_are_not_read_twice(monkeypatch):
    with FakeSpeechServer() as speech:
        game = _game()
        mixer = _Mixer(game)
        monkeypatch.setattr(game.speaker, "engine", "espeak-ng")
        monkeypatch.setattr(game.speaker, "say", lambda text, language: None)
        game.preferences = dataclasses.replace(game.preferences, speech=True)
        _voice_on(game, speech)
        game._pump_speech()
        game.announce(message("crew.action_stations_on"), "mission")
        assert _pump(game, lambda: mixer.played and game._voice_playing is None)
        _pump(game, lambda: False, timeout=0.3)
        # Only the crew's call, not the log line as well.
        assert len(speech.requests) == 1 and speech.requests[0]["instructions"] \
            .startswith(voice._STYLE["crew"][:20])


def test_the_officer_goes_before_a_waiting_log_entry():
    game = _game()
    _Mixer(game)

    class Request:
        def __init__(self, role, audible):
            self.role, self.audible, self.status = role, audible, "pending"
            self.pieces, self.finished, self.error = [], False, None

        def stale(self, now=None):
            return False

    log, xo = Request("log", True), Request("xo", False)
    game.voice._config = dataclasses.replace(game.voice.config, enabled=True)
    game._voice_queue.extend([log, xo])
    game._pump_voice()
    # The officer's answer is still being made: the log entry waits for it.
    assert game._voice_playing is None and list(game._voice_queue) == [log, xo]
    game._voice_queue.remove(xo)
    game._pump_voice()
    assert game._voice_playing is log


def test_a_stale_log_entry_is_dropped_even_with_its_audio():
    game = _game()
    _Mixer(game)
    request = voice.VoiceRequest("log", "Old news.", "en")
    request.pieces.append(b"x")
    request.created = time.monotonic() - voice.STALE_S["log"] - 1
    game._voice_queue.append(request)
    game._pump_voice()
    assert game._voice_playing is None and not game._voice_queue


def test_log_switches_persist_and_bad_values_fall_back(tmp_path):
    prefs = dataclasses.replace(Preferences(), tts_log_sonar=False, tts_log=False)
    path = save_preferences(prefs, tmp_path / "settings.json")
    loaded = load_preferences(path)
    assert not loaded.tts_log and not loaded.tts_log_sonar and loaded.tts_log_funk
    path.write_text(json.dumps({"tts_log": "no", "tts_log_waffen": 0}))
    loaded = load_preferences(path)
    assert loaded.tts_log and loaded.tts_log_waffen
    defaults = Preferences()
    assert defaults.tts_log and all(getattr(defaults, f"tts_log_{group}")
                                    for group in config.LOG_VOICE_GROUPS)


def test_the_boat_radio_room_is_read_as_radio():
    from src.core.game_voice import log_group
    assert log_group("radio") == "funk" and log_group("sonar") == "sonar"
    assert log_group("unknown") is None
    assert set(log_voice_view.BOAT_GROUPS) <= set(config.LOG_VOICE_GROUPS)


def test_settings_page_four_by_key_and_mouse(isolated_saves):
    from src.ui import advisor_view
    game = _game()
    game._open_administration("llm")
    for _ in range(3):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0,
                                             unicode="\t"))
    assert game.llm_page == 3 and game.llm_rows() == LOG_ROWS
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, mod=0, unicode=""))
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert not game.preferences.tts_log_navigation
    pointer.reset()
    with pointer.layer("overlay"):
        advisor_view.draw_llm_settings(game)
    row = advisor_view.settings_row_rects(len(LOG_ROWS))[LOG_ROWS.index("tts_log_sonar")]
    pointer.hit(row.center, "overlay").action(row.center)
    assert not game.preferences.tts_log_sonar
    tab = advisor_view.page_tab_rects()[3]
    game.set_llm_page(0)
    pointer.reset()
    with pointer.layer("overlay"):
        advisor_view.draw_llm_settings(game)
    pointer.hit(tab.center, "overlay").action(tab.center)
    assert game.llm_page == 3
    # Four tabs and the title never touch.
    tabs = advisor_view.page_tab_rects()
    title = advisor_view._title_rect()
    for a, b in itertools.combinations(list(tabs) + [title], 2):
        assert not a.colliderect(b)


def _feed_game(language):
    game = _game()
    game._set_preference("language", language)
    game.preferences = dataclasses.replace(game.preferences, tts_enabled=True,
                                           tts_url="http://127.0.0.1:9/v1", tts_model="tts")
    game.configure_voice()
    return game


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("side", ["frigate", "uboot"])
def test_f11_log_buttons_mute_a_station_and_fit(language, side, monkeypatch):
    game = _feed_game(language)
    monkeypatch.setattr(game, "local_side", side, raising=False)
    for group in config.LOG_VOICE_GROUPS:
        _log(game, group, "Entry of a station that keeps on reporting and reporting.")
    game.feed_overlay_open = True
    pointer.reset()
    with layout.capture_text() as traced:
        game.draw_feed_overlay()
    rect = game.feed_overlay_rect()
    label, chips = log_voice_view.chip_rects(game, pygame.Rect(
        rect.x + 10, rect.y + 30, rect.w - 360 - 30, rect.h - 40))
    names = [group for group, _chip in chips]
    assert names == list(log_voice_view.groups(game))
    problems = [item["text"] for item in traced if not rect.contains(item["ink"])]
    for a, b in itertools.combinations(traced, 2):
        if a["ink"].colliderect(b["ink"]):
            problems.append(f"overlap {a['text']!r} / {b['text']!r}")
    assert not problems, problems[:10]
    for _group, chip in chips:
        assert chip.right <= rect.x + rect.w - 360 - 20 and label.right <= chip.x
    group, chip = chips[2]
    pointer.hit(chip.center, "station").action(chip.center)
    assert not game.log_voice_on(group)
    tip = pointer.tip_at(chip.center)
    assert tip is not None
    # Without a voice the log keeps its full height and no buttons.
    game.set_voice_preference("tts_enabled", False)
    assert not log_voice_view.shown(game)
    pointer.reset()
    game.draw_feed_overlay()
    pointer.hit(chip.center, "station").action(chip.center)
    assert not game.log_voice_on(group)


def test_the_submarine_reads_its_own_log_not_the_frigates():
    with FakeSpeechServer() as speech:
        game = Game(seed=61, start_menu=False, audio_enabled=False, language="en")
        game.reset(61, "s5_durchbruch")
        game.local_side = "uboot"
        game._update(0.05)
        boat = game.opfor
        mixer = _Mixer(game)
        _voice_on(game, speech)
        game._pump_speech()
        _log(game, "sonar", "Frigate sonar: not for the boat.")
        boat.notice(game.sim_t, "radio", raw_text("Radio room: broadcast copied."))
        assert _pump(game, lambda: mixer.played and game._voice_playing is None)
        assert _said(speech) == ["Radio room: broadcast copied."]
        assert game.log_voice_count("funk") == 1


def test_a_burst_keeps_its_newest_entries_and_counts_all():
    game = _game()
    _Mixer(game)
    game.preferences = dataclasses.replace(game.preferences, tts_enabled=True,
                                           tts_url="http://127.0.0.1:9/v1", tts_model="tts")
    game.configure_voice()
    queued = []
    game.voice_say = lambda text, role: queued.append((text, role)) or True
    game._pump_speech()
    for number in range(10):
        _log(game, "waffen", f"Weapons entry {number}.")
    game._pump_log_voice()
    from src.core.game_voice import LOG_BURST
    assert [text for text, _role in queued] == [f"Weapons entry {n}." for n in range(10 - LOG_BURST, 10)]
    assert {role for _text, role in queued} == {"log"}
    assert game.log_voice_count("waffen") == 10
