"""The talk key: Shift+Space at every station records a question, the speech
input (OpenAI-compatible /audio/transcriptions) turns it into text and the
executive officer answers it in a bubble over the station.  Off by default;
it only asks and never gives an order or touches the simulation."""

import dataclasses
import io
import itertools
import time
import wave

import numpy as np
import pygame
import pytest

from src.core import game_talk
from src.core.game import Game
from src.core.station import Station
from src.llm import advisor as advisor_model, prompts, stt
from src.llm.stt import SttConfig, SttService
from src.ui import layout, pointer, talk_view
from tests.llm_fake import FakeLlmServer
from tests.stt_fake import FakeSttServer

VOICE = (0.2 * np.sin(2 * np.pi * 300.0 * np.arange(16000) / 16000)).astype(np.float32)


class FakeMic:
    """Stands in for the SDL capture device: what was 'said' is ``VOICE``."""

    def __init__(self, samples=VOICE, works=True):
        self.samples = samples
        self.works = works
        self.device = None
        self.failure = ""
        self.tried = False
        self.recording = False

    def start(self):
        self.tried = True
        if self.works:
            self.device = object()
        else:
            self.failure = "no_device"
        return self.works

    def stop(self):
        self.device = None
        self.recording = False

    def check(self):
        return self.failure

    def begin_recording(self):
        if self.device is None:
            return False
        self.recording = True
        return True

    def end_recording(self):
        self.recording = False
        return self.samples

    def level(self):
        return 7 if self.recording else 0


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(game_talk.time, "monotonic", value)
    return value


def _game(seed=4471):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _connect(game, llm=None, speech=None, **prefs):
    game.preferences = dataclasses.replace(
        game.preferences, llm_enabled=llm is not None,
        llm_url=llm.url if llm else game.preferences.llm_url, llm_model="m",
        stt_enabled=speech is not None,
        stt_url=speech.url if speech else game.preferences.stt_url, stt_model="whisper-1",
        **prefs)
    game.configure_llm()
    game.configure_stt()
    game.__dict__["microphone"] = FakeMic()


def _key(game, down=True, key=pygame.K_SPACE, mod=pygame.KMOD_SHIFT):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP,
                                         key=key, mod=mod, unicode=" ", scancode=0))


def _pump(game, done, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        game.llm_tick()
        if done():
            return True
        time.sleep(0.02)
    return False


# -- the transcription client ------------------------------------------------------


def test_wav_is_16_bit_mono_and_bounded():
    data = stt.wav_bytes(np.ones(int(40 * 16000), dtype=np.float32))
    with wave.open(io.BytesIO(data)) as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, 16000)
        assert handle.getnframes() == int(stt.MAX_AUDIO_S * 16000)
    assert stt.check_audio(np.zeros(1000)) == "too_short"
    assert stt.check_audio(np.zeros(16000)) == "no_speech"
    assert stt.check_audio(np.array([np.nan] * 16000)) == "too_short"
    assert stt.check_audio(VOICE) is None


def test_off_or_unconfigured_sends_nothing():
    service = SttService()
    assert not service.active
    assert service.transcribe(VOICE, "de") is None
    assert not SttService(SttConfig(enabled=True, base_url="ftp://x")).active


def test_transcribes_with_model_language_and_key():
    with FakeSttServer("  Wo   steht\nder Kontakt?  ") as server:
        service = SttService(SttConfig(enabled=True, base_url=server.url, model="whisper-1",
                                       api_key="sk-secret"))
        request = service.transcribe(VOICE, "de")
        assert request.wait(5) and request.ok, request.error
        assert request.text == "Wo steht der Kontakt?"
        form = server.forms[0]
        assert form["model"] == "whisper-1" and form["language"] == "de"
        assert form["response_format"] == "json"
        assert form["file"][:4] == b"RIFF"
        assert server.headers[0]["Authorization"] == "Bearer sk-secret"
        assert "sk-secret" not in repr(service.config)
        assert request.wav == b""       # the audio is not kept


def test_a_server_without_the_language_field_is_asked_again():
    with FakeSttServer(lambda form: 400 if "language" in form else b"plain text answer") as server:
        service = SttService(SttConfig(enabled=True, base_url=server.url))
        request = service.transcribe(VOICE, "en")
        assert request.wait(5) and request.ok
        assert request.text == "plain text answer"
        assert len(server.forms) >= 2


@pytest.mark.parametrize("reply,error", [(401, "auth"), (429, "rate_limit"), (500, "server"),
                                         ({"nope": 1}, "bad_reply")])
def test_failures_are_named(reply, error):
    with FakeSttServer(reply) as server:
        service = SttService(SttConfig(enabled=True, base_url=server.url))
        request = service.transcribe(VOICE, "en")
        assert request.wait(5) and request.status == "failed" and request.error == error


def test_silence_and_short_recordings_never_leave_the_game():
    with FakeSttServer() as server:
        service = SttService(SttConfig(enabled=True, base_url=server.url))
        assert service.transcribe(np.zeros(16000), "de").error == "no_speech"
        assert service.transcribe(VOICE[:1000], "de").error == "too_short"
        time.sleep(0.1)
        assert server.forms == []


def test_long_transcripts_are_cut_to_one_question():
    text = stt.clean_transcript("wort " * 200)
    assert len(text) <= stt.MAX_TEXT and text.endswith("…")


# -- the talk key in the game --------------------------------------------------------


def test_off_by_default_the_key_only_says_how_to_switch_it_on(clock):
    game = _game()
    game.__dict__["microphone"] = FakeMic()
    assert not game.preferences.stt_enabled and not game.stt.active
    _key(game)
    assert game.talk_state == "idle"
    assert game.msg is not None
    assert not game.talk_shown()


def test_hold_speak_release_asks_the_executive_officer(clock):
    with FakeLlmServer("Kontakt K1 in Peilung 045.") as llm, FakeSttServer("Wo ist K1?") as speech:
        game = _game()
        _connect(game, llm, speech)
        game.station = Station.SONAR
        _key(game)
        assert game.talk_state == "recording" and game.__dict__["microphone"].recording
        clock.now += 2.0
        _key(game, down=False)
        assert game.talk_state == "transcribing"
        assert _pump(game, lambda: game.talk_state == "idle"
                     and game.talk_bubble["entry"] is not None
                     and game.talk_bubble["entry"]["status"] == "done")
        entry = game.advisor.log("local")[-1]
        assert entry["kind"] == "question" and entry["question"] == "Wo ist K1?"
        assert game.talk_bubble["question"] == "Wo ist K1?"
        assert "Peilung" in game.talk_bubble["entry"]["answer"]
        assert speech.forms[0]["language"] in ("de", "en")
        # The bubble goes away by itself.
        assert game.talk_bubble_shown()
        clock.now += game_talk.BUBBLE_S + 1
        assert not game.talk_bubble_shown()


@pytest.mark.parametrize("text", [
    "Volle Fahrt voraus", "Volle Fahrt voraus.", "Kurs 270, 12 Knoten", "Ruder hart Steuerbord",
    "Auf Sehrohrtiefe gehen", "Rohr eins los", "Gefechtsstationen!", "Alle Maschinen stopp",
    "All ahead full", "Come right to 090", "Make depth 100 metres", "Fire tube one",
])
def test_orders_are_told_apart_from_questions(text):
    assert advisor_model.looks_like_order(text)


@pytest.mark.parametrize("text", [
    "Wo ist K1?", "Wie schnell sollen wir fahren", "Soll ich volle Fahrt voraus gehen",
    "Was bedeutet Sehrohrtiefe", "Erkläre mir die Schleichfahrt", "Wo steht der Kontakt gerade",
    "Where is the contact?", "Should we go to periscope depth", "What does all ahead full mean",
    "Kontakt K1 peilt 045", "",
])
def test_questions_are_never_taken_for_orders(text):
    assert not advisor_model.looks_like_order(text)


@pytest.mark.parametrize("language", ["en", "de"])
def test_a_spoken_order_is_never_confirmed_or_carried_out(clock, language):
    """Bug 2026-10-06: "Volle Fahrt voraus" by the talk key was answered with a
    confirmation of 30 kn, yet nothing was set.  The talk key only asks: the
    game itself says that nothing was done and where orders are given."""
    with FakeLlmServer("Volle Fahrt voraus, 30 Knoten werden gesetzt.") as llm, \
            FakeSttServer("Volle Fahrt voraus.") as speech:
        game = _game()
        game._set_preference("language", language)
        _connect(game, llm, speech)
        game.station = Station.BRIDGE
        speed = game.ship.target_speed
        _key(game)
        clock.now += 2.0
        _key(game, down=False)
        assert _pump(game, lambda: game.talk_state == "idle" and game.talk_bubble
                     and game.talk_bubble["entry"] is not None
                     and game.talk_bubble["entry"]["status"] == "done")
        answer = game.talk_bubble["entry"]["answer"]
        assert answer == game.tr("advisor.not_an_order")
        assert "30" not in answer
        # Nothing went to the model, nothing was set, and it is no advisor help.
        assert llm.requests == []
        assert game.ship.target_speed == speed
        assert not game.llm_advisor_used


def test_the_question_prompt_forbids_confirming_orders():
    system = prompts.advisor("de", "frigate", "question", "facts", "x")[0]["content"]
    assert "cannot carry out orders" in system and "never repeat it back" in system


def test_a_tap_keeps_recording_until_the_next_press(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer("Status?") as speech:
        game = _game()
        _connect(game, llm, speech)
        _key(game)
        clock.now += 0.1
        _key(game, down=False)
        assert game.talk_state == "recording"
        clock.now += 3.0
        _key(game)
        assert game.talk_state == "transcribing"
        _key(game, down=False)
        assert _pump(game, lambda: game.advisor.log("local")
                     and game.advisor.log("local")[-1]["status"] == "done")


def test_the_talk_key_never_reaches_a_station_or_types_a_space(clock, monkeypatch):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech)
        game.station = Station.SONAR
        pressed = []
        monkeypatch.setattr(game, "_handle_station_key", lambda *a, **k: pressed.append(a),
                            raising=False)
        _key(game)
        game.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=" "))
        assert pressed == []
        # In the executive officer's chat the space is not typed either.
        game.talk_cancel()
        game.open_talk_chat()
        assert game.advisor_open and game.advisor_mode_name() == "question"
        _key(game)
        game.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=" "))
        assert game.advisor_field.value == ""
        assert game.talk_state == "recording"


def test_the_talk_key_belongs_to_missions_only(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech)
        game._open_administration("help")
        _key(game)
        assert game.talk_state == "idle"
        game.help_open = False
        game.game_over = True
        _key(game)
        assert game.talk_state == "idle"


def test_focus_loss_and_switching_off_drop_the_recording(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech)
        _key(game)
        game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        assert game.talk_state == "idle" and game.talk_bubble is None
        _key(game)
        game.set_stt_preference("stt_enabled", False)
        assert game.talk_state == "idle"
        clock.now += 1
        assert speech.forms == []


def test_no_microphone_says_why(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech)
        game.__dict__["microphone"] = FakeMic(works=False)
        _key(game)
        assert game.talk_state == "idle" and game.msg is not None


def test_recording_is_never_heard_by_the_enemy(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech, microphone=True)
        _key(game)
        game._pump_microphone(0.1)
        assert game.__dict__["mic_level"] == 0
        assert game.crew_voice_level("frigate") == 0


def test_talking_never_changes_the_simulation(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer("Lage?") as speech:
        plain, talking = _game(4472), _game(4472)
        _connect(talking, llm, speech)
        _key(talking)
        clock.now += 1.0
        _key(talking, down=False)
        for _ in range(30):
            plain.update(0.1)
            talking.update(0.1)
            talking.llm_tick()
        assert (plain.ship.x, plain.ship.y, plain.sim_t) == \
            (talking.ship.x, talking.ship.y, talking.sim_t)


# -- what the player sees ----------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("side", ["frigate", "uboot"])
def test_button_and_bubble_fit_and_take_the_mouse(clock, language, side, tmp_path):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        game._set_preference("language", language)
        _connect(game, llm, speech)
        if side == "uboot":
            from tests.test_opfor_sub import _game as boat_game
            game = boat_game()
            game._set_preference("language", language)
            _connect(game, llm, speech)
            game.local_side = "uboot"
            game._update(0.05)
        game.msg = None
        answer = ("Der Kontakt K1 steht in Peilung 045 bei etwa 8 Seemeilen, Kurs 210, "
                  "Fahrt 12 Knoten. ") * 6
        entry = dict(seq=1, kind="question", question="Wo steht der Kontakt K1 gerade? " * 4,
                     answer=answer, status="done", error=None, proposal=None, applied=False)
        game.talk_bubble = dict(question=entry["question"], entry=entry, error=None,
                                until=clock.now + 10)
        pointer.reset()
        with layout.capture_text() as traced:
            game._draw()
        panel = talk_view.bubble_rect(talk_view.MAX_LINES)
        start = next(index for index, item in enumerate(traced)
                     if item["text"] == game.tr("talk.state.answer"))
        inside = [item for item in traced[start:] if panel.colliderect(item["ink"])]
        assert len(inside) >= talk_view.MAX_LINES, "bubble drew no text"
        pygame.image.save(game.screen, str(tmp_path / f"talk-bubble-{side}-{language}.png"))
        problems = [f"{a['text']!r} / {b['text']!r}"
                    for a, b in itertools.combinations(inside, 2)
                    if a["ink"].colliderect(b["ink"])]
        assert not problems
        assert all(panel.contains(item["ink"]) for item in inside)
        # The top bar's button opens the chat; the bubble keeps its clicks.
        button = next(t for t in pointer.targets("station")
                      if t.rect.y < 30 and t.action is not None
                      and t.rect.w == talk_view.BUTTON_W)
        button.action(button.rect.center)
        assert game.advisor_open and game.advisor_mode_name() == "question"
        assert game.talk_bubble is None


def test_bubble_close_box_and_talk_button(clock):
    with FakeLlmServer("Ja.") as llm, FakeSttServer() as speech:
        game = _game()
        _connect(game, llm, speech)
        game.talk_bubble = dict(question="", entry=None, error="no_speech",
                                until=clock.now + 5)
        pointer.reset()
        game._draw()
        panel = talk_view.bubble_rect(0)
        assert pointer.blocked(panel.center, "station")
        from src.ui import game_menu
        close = game_menu.close_rect(panel)
        pointer.hit(close.center, "station").action(close.center)
        assert game.talk_bubble is None
        game.talk_bubble = dict(question="", entry=None, error="no_speech",
                                until=clock.now + 5)
        pointer.reset()
        game._draw()
        talk = next(t for t in pointer.targets("station")
                    if panel.contains(t.rect) and t.action is not None and not t.blocker
                    and t.rect.w > 100 and t.rect.x == panel.x + talk_view.PAD)
        talk.action(talk.rect.center)
        assert game.talk_state == "recording"
        talk.action(talk.rect.center)
        assert game.talk_state == "transcribing"


def test_settings_page_five(isolated_saves):
    game = _game()
    game._open_administration("llm")
    for _ in range(4):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0,
                                             unicode="\t"))
    from src.core.game_advisor import STT_ROWS
    assert game.llm_page == 4 and game.llm_rows() == STT_ROWS
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert game.preferences.stt_enabled and game.stt.config.enabled
    game.click_llm_row(STT_ROWS.index("stt_url"))
    game.llm_field.value = "http://192.168.1.2:31001/v1"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert game.preferences.stt_url == "http://192.168.1.2:31001/v1"
    assert game.stt.config.base_url == "http://192.168.1.2:31001/v1"
    game.click_llm_row(STT_ROWS.index("stt_key"))
    game.llm_field.value = "sk-test-1234567890"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert game.stt.config.api_key == "sk-test-1234567890"
    assert game.stt_key_source() == "own"
    assert "sk-test" not in str(game.preferences)


def test_settings_test_reports_the_round_trip(isolated_saves):
    with FakeSttServer("") as speech:
        game = _game()
        game.preferences = dataclasses.replace(game.preferences, stt_enabled=True,
                                               stt_url=speech.url)
        game.configure_stt()
        assert game.start_stt_test()
        end = time.time() + 5
        while game.stt_test_state()["status"] == "pending" and time.time() < end:
            time.sleep(0.02)
        assert game.stt_test_state()["status"] == "done"
