"""The stations' log entries read aloud by the language model's voice
(``src/core/game_voice.py``), muted per station of the log."""

from __future__ import annotations

import dataclasses
import itertools
import json
import time

import pygame
import numpy as np
import pytest

from src.core import config
from src.core.game_advisor import LOG_ROWS
from src.core.game import Game
from src.core.i18n import message, raw_text
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.llm import voice
from src.ui import layout, log_voice_view, pointer
from tests.test_llm_voice import FakeSpeechServer, _Mixer, _game, _pump, _voice_on


@pytest.fixture(autouse=True)
def _clean_pointer():
    """Click targets drawn here never reach the next test."""
    pointer.reset()
    yield
    pointer.reset()


def _log(game, category, text):
    game.feed.add(game.world.format_time(), category, raw_text(text))


def _said(speech):
    return [body["input"] for body in speech.requests]


def test_log_entries_are_read_after_the_officer():
    service = voice.VoiceService(voice.VoiceConfig(enabled=True), queue_max=2)
    service._ensure_worker = lambda: None
    a, b, c = (service.say(text, "en", "log") for text in ("A.", "B.", "C."))
    # A full log queue drops its oldest entry, like the crew's calls.
    assert a.status == "dropped" and b.status == c.status == "pending"
    xo = service.say("Officer.", "en", "xo")
    assert service._next() is xo and service._next() is b
    assert voice.ROLES.index("log") > voice.ROLES.index("xo")
    assert voice.STALE_S["log"] > voice.STALE_S["xo"]


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
            == voice._STYLE["en"]


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


def test_a_waiting_log_entry_with_audio_is_still_said():
    game = _game()
    _Mixer(game)
    request = voice.VoiceRequest("log", "Late but said.", "en")
    request.pieces.append(np.zeros(8, np.int16))
    request.created = time.monotonic() - voice.STALE_S["xo"] - 1
    game._voice_queue.append(request)
    game._pump_voice()
    assert game._voice_playing is request


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
    # The five tabs and the close box never touch.
    from src.ui import game_menu
    tabs = advisor_view.page_tab_rects()
    close = game_menu.close_rect(advisor_view.PANEL)
    assert len(tabs) == 5
    for a, b in itertools.combinations(list(tabs) + [close], 2):
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


def test_a_burst_is_read_in_order_one_by_one_and_counts_all():
    game = _game()
    _Mixer(game)
    game.preferences = dataclasses.replace(game.preferences, tts_enabled=True,
                                           tts_url="http://127.0.0.1:9/v1", tts_model="tts")
    game.configure_voice()
    queued = []

    def say(text, role):
        queued.append(text)
        game._voice_queue.append(voice.VoiceRequest(role, text, "en"))
        return True
    game.voice_say = say
    game._pump_speech()
    for number in range(40):
        _log(game, "waffen", f"Weapons entry {number}")
    game._pump_log_voice()
    from src.core.game_voice import LOG_IN_FLIGHT
    assert len(queued) == LOG_IN_FLIGHT
    for _round in range(40):
        game._voice_queue.clear()           # said: the next ones go out
        game._pump_log_voice()
    # Every entry is its own request (a pause follows each), closed with a
    # full stop, all of them in order.
    assert queued == [f"Weapons entry {n}." for n in range(40)]
    assert game.log_voice_count("waffen") == 40


def _words(language):
    catalog = json.loads((__import__("pathlib").Path("data/i18n") / f"{language}.json")
                         .read_text(encoding="utf-8"))
    words = {name: catalog[f"voice.word.{name}"] for name in voice.WORD_NAMES}
    words.update((f"letter_{letter}", catalog[f"voice.letter.{letter.lower()}"])
                 for letter in voice.LETTERS)
    return words


@pytest.mark.parametrize("language,text,said", [
    ("de", "Kontakt neu: Rtg 163° Dst ~4.2 sm", "Kontakt neu: Richtung 163 Grad Abstand etwa 4.2 Seemeilen"),
    ("de", "Fahrt 12 kn, Tiefe 45 m, 1500 m/s, 3 s", "Fahrt 12 Knoten, Tiefe 45 Meter, 1500 Meter pro Sekunde, 3 Sekunden"),
    ("de", "Ort 54°21,4'N 010°08,2'E", "Ort 54 Grad 21,4 Minuten Nord 010 Grad 08,2 Minuten Ost"),
    ("en", "Contact brg 219° ~3.1 NM, 8 kn, 38 %", "Contact bearing 219 degrees about 3.1 nautical miles, 8 knots, 38 percent"),
    ("en", "Ping 3.5 kHz 120 dB after 5 min", "Ping 3.5 kilohertz 120 decibels after 5 minutes"),
    ("de", "Mission: Alle U-Boote versenken", "Mission: Alle U-Boote versenken"),
])
def test_units_and_short_forms_are_said_in_full(language, text, said):
    assert voice.spoken_words(text, _words(language)) == said


def test_every_role_speaks_with_one_calm_style_and_one_seed():
    assert set(voice._STYLE) == {"de", "en"}
    assert "laugh" in voice._STYLE["en"] and "lachen" in voice._STYLE["de"]
    assert "Deutsch" in voice._STYLE["de"] and "Akzent" in voice._STYLE["de"]
    service = voice.VoiceService()
    assert 1 <= service._session_seed <= voice.SEED_MAX


def test_a_long_log_entry_is_one_request():
    with FakeSpeechServer() as speech:
        game = _game()
        mixer = _Mixer(game)
        _voice_on(game, speech)
        game._pump_speech()
        entry = "Funk: HQ meldet Kontakt. Peilung unsicher. Suche fortsetzen. " * 3
        _log(game, "funk", entry)
        assert _pump(game, lambda: mixer.played and game._voice_playing is None)
        assert len(speech.requests) == 1
        assert speech.requests[0]["input"] == " ".join(entry.replace("HQ", "H Q").split())


@pytest.mark.parametrize("language,text,said", [
    ("de", "Wasser -2 °C, Luft 14 °C", "Wasser minus 2 Grad Celsius, Luft 14 Grad Celsius"),
    ("en", "Water -2 °C, air 57 °F", "Water minus 2 degrees Celsius, air 57 degrees Fahrenheit"),
    ("de", "TORPEDO AUFGESCHALTET 163° · Einschlag ~45s",
     "Torpedo Aufgeschaltet 163 Grad, Einschlag etwa 45 Sekunden"),
    ("de", "Peilung 0–360° | Tiefe 45 m / Wasser 120 m",
     "Peilung 0 bis 360 Grad, Tiefe 45 Meter, Wasser 120 Meter"),
    ("de", "Um 14:35 meldet die OPZ „Fregatte“ & HQ", "Um 14 35 meldet die O Pe Zett Fregatte und Ha Ku"),
    ("en", "S3 brg 219±4° @12/34, U-212", "S 3 bearing 219 plus or minus 4 degrees at 12, 34, U 212"),
    ("en", "Don’t panic… [check] NATO", "Don’t panic. check Nato"),
    ("de", "Aufklärung: 1x Altmetall, 2 × Welle", "Aufklärung: 1 mal Altmetall, 2 mal Welle"),
    ("de", "CIWS: ASM abgefangen", "Ze I We Es: A Es Em abgefangen"),
    ("de", "Kontakt K1 neu, K2 verloren", "Kontakt Ka 1 neu, Ka 2 verloren"),
    ("de", "U-Boot getaucht", "U-Boot getaucht"),
    ("en", "Contact K1, HQ", "Contact K 1, H Q"),
])
def test_temperatures_signs_and_symbols_are_said_as_words(language, text, said):
    assert voice.spoken_words(text, _words(language)) == said


def test_a_spelled_number_keeps_its_brackets_tight():
    digits = ["null", "eins", "zwo", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]
    assert voice.spell_digits("3 Verwundete (bisher 3): leer [7]", digits, "Komma") \
        == "drei Verwundete (bisher drei): leer [sieben]"


def test_pieces_that_have_arrived_play_as_one_sound():
    game = _game()
    mixer = _Mixer(game)
    request = voice.VoiceRequest("log", "Joined.", "en")
    for _ in range(3):
        request.pieces.append(np.ones(100, np.int16))
    game._feed_voice(request)
    assert not request.pieces
    assert [len(pcm) for pcm in mixer.played] == [300]


def test_spoken_letters_never_rename_a_key_chip():
    from src.core.i18n import Translator
    german = Translator("de")
    for key in ("Z", "A", "D", "R", "2", "minus"):
        assert german.display(key) == key


@pytest.mark.parametrize("text,said", [
    ("Kontakt K1 neu", "Kontakt K1 neu."),
    ("Sonar meldet:", "Sonar meldet."),
    ("Warte …", "Warte."),
    ("Kurs 270, ", "Kurs 270."),
    ("Torpedo im Wasser!", "Torpedo im Wasser!"),
    ("Fahrt (12 kn)", "Fahrt (12 kn)."),
    ("Schon zu Ende.", "Schon zu Ende."),
    ("  ", ""),
])
def test_every_report_ends_with_a_full_stop(text, said):
    assert voice.close_sentence(text) == said


def test_a_report_sent_to_the_service_ends_with_a_full_stop():
    game = _game()
    _Mixer(game)
    game.preferences = dataclasses.replace(game.preferences, tts_enabled=True,
                                           tts_url="http://127.0.0.1:9/v1", tts_model="tts")
    game.configure_voice()
    sent = []
    game.voice.say = lambda text, language, role: sent.append(text) or voice.VoiceRequest(
        role, text, language)
    assert game.voice_say("Contact K1 bearing 270", "crew")
    assert sent[-1].endswith(".") and not sent[-1].endswith("..")


def test_reports_are_parted_by_a_short_silence(monkeypatch):
    from src.core import game_voice
    game = _game()
    mixer = _Mixer(game)
    game.preferences = dataclasses.replace(game.preferences, tts_enabled=True,
                                           tts_url="http://127.0.0.1:9/v1", tts_model="tts")
    game.configure_voice()
    clock = [100.0]
    monkeypatch.setattr(game_voice.time, "monotonic", lambda: clock[0])
    first, second = (voice.VoiceRequest("log", text, "en") for text in ("One.", "Two."))
    for request in (first, second):
        request.created = clock[0]
        request._finish("done", pcm=np.ones(100, np.int16))
        game._voice_queue.append(request)
    game._pump_voice()
    assert len(mixer.played) == 1
    game._pump_voice()                      # the first one has ended
    game._pump_voice()
    assert len(mixer.played) == 1           # silence before the next report
    clock[0] += game_voice.VOICE_GAP_S + 0.01
    game._pump_voice()
    assert len(mixer.played) == 2
