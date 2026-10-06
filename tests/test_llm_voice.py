"""The optional voice of the language-model add-on: an OpenAI-compatible
``/audio/speech`` service lets the executive officer speak his answers and
the crew its reports; without it the game behaves exactly as before."""

import dataclasses
import json
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pygame
import pytest

from src.core.game import Game
from src.core.i18n import message
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.llm import keystore, voice
from tests.llm_fake import FakeLlmServer


def _wav(samples, rate=24000, channels=1, bits=16, streaming=False, fmt_tag=1):
    data = np.asarray(samples)
    if bits == 16:
        payload = (np.clip(data, -1, 1) * 32767).astype("<i2").tobytes()
    else:
        payload = data.astype("<f4").tobytes()
    size = 0xFFFFFFFF if streaming else len(payload)
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * channels * bits // 8,
                      channels * bits // 8, bits)
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF if streaming else 36 + len(payload))
            + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"LIST"
            + struct.pack("<I", 4) + b"INFO" + b"data" + struct.pack("<I", size) + payload)


TONE = np.sin(np.linspace(0, 200 * np.pi, 24000)).astype(np.float32) * 0.5


class FakeSpeechServer:
    """Answers ``/v1/audio/speech`` with a WAV (or an int status)."""

    def __init__(self, reply=None, delay_s=0.0):
        self.reply = reply
        self.delay_s = delay_s
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append(body)
                owner.headers.append(dict(self.headers))
                if owner.delay_s:
                    threading.Event().wait(owner.delay_s)
                answer = owner.reply(body) if callable(owner.reply) else owner.reply
                if answer is None:
                    answer = _wav(TONE)
                if self.path != "/v1/audio/speech" or isinstance(answer, int):
                    self.send_response(404 if self.path != "/v1/audio/speech" else answer)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()


def _service(server, **kw):
    config = voice.VoiceConfig(enabled=True, base_url=server.url, model="tts",
                               voice="onyx", api_key=kw.pop("api_key", ""))
    return voice.VoiceService(config, rate=kw.pop("rate", 22050), **kw)


# -- decoding --------------------------------------------------------------------

def test_wav_of_every_common_layout_decodes_to_mono():
    samples, rate = voice.parse_wav(_wav(TONE))
    assert rate == 24000 and len(samples) == 24000
    assert abs(float(np.max(samples)) - 0.5) < 0.01
    stereo = np.repeat(TONE[:, None], 2, axis=1).reshape(-1)
    samples, _ = voice.parse_wav(_wav(stereo, channels=2))
    assert len(samples) == 24000
    samples, _ = voice.parse_wav(_wav(TONE, bits=32, fmt_tag=3))
    assert len(samples) == 24000
    # Streaming servers do not know the length in advance.
    samples, _ = voice.parse_wav(_wav(TONE, streaming=True))
    assert len(samples) == 24000


@pytest.mark.parametrize("raw", [b"", b"ID3...", b"RIFF\0\0\0\0WAVE",
                                 _wav(TONE, bits=32, fmt_tag=1)],
                         ids=["empty", "mp3", "no_chunks", "pcm32"])
def test_anything_else_is_refused(raw):
    with pytest.raises(ValueError):
        voice.parse_wav(raw)


@pytest.mark.parametrize("text,said", [
    ("Peilung 431, Entfernung 0,9 sm.", "Peilung vier drei eins, Entfernung null Komma neun sm."),
    ("Kurs 270!", "Kurs zwo sieben null!"),
    ("F7 drücken", "F sieben drücken"),
    ("Keine Zahl.", "Keine Zahl."),
], ids=["bearing_and_decimal", "punctuation", "inside_a_word", "none"])
def test_numbers_are_spoken_digit_by_digit(text, said):
    digits = "null eins zwo drei vier fünf sechs sieben acht neun".split()
    assert voice.spell_digits(text, digits, "Komma") == said


def test_clip_is_resampled_to_the_mixer_and_levelled():
    pcm = voice.to_pcm(TONE, 24000, 22050)
    assert pcm.dtype == np.int16 and abs(len(pcm) - 22050) <= 1
    assert 0.8 * 32767 < int(np.max(np.abs(pcm))) <= 0.86 * 32767
    assert pcm[0] == 0 and abs(int(pcm[-1])) < 200


def test_long_answers_are_cut_at_a_sentence():
    text = "First sentence here. " * 60
    said = voice.speakable(text)
    assert len(said) <= voice.MAX_INPUT_CHARS and said.endswith(".")
    assert voice.speakable("**Bold**\n\n# Heading") == "Bold Heading"


# -- the service ---------------------------------------------------------------------

def test_service_off_or_misconfigured_sends_nothing():
    assert voice.VoiceService().say("Hello", "en") is None
    bad = voice.VoiceService(voice.VoiceConfig(enabled=True, voice=" bad"))
    assert not bad.active and bad.say("Hello", "en") is None


def test_service_speaks_with_style_key_and_wav():
    with FakeSpeechServer() as server:
        service = _service(server, api_key="sk-voice-secret-1234")
        request = service.say("Torpedo im Wasser.", "de", "crew")
        assert request.wait(10) and request.ok
        assert request.pcm.dtype == np.int16 and abs(len(request.pcm) - 22050) <= 1
        body = server.requests[0]
        assert body["model"] == "tts" and body["voice"] == "onyx"
        assert body["input"] == "Torpedo im Wasser."
        assert body["response_format"] == "wav"
        assert "German" in body["instructions"]
        assert server.headers[0]["Authorization"] == "Bearer sk-voice-secret-1234"
        assert "secret" not in repr(service.config)


def test_server_without_instructions_is_asked_again_without():
    def reply(body):
        return 400 if "instructions" in body else None
    with FakeSpeechServer(reply) as server:
        service = _service(server)
        request = service.say("Contact.", "en", "crew")
        assert request.wait(10) and request.ok
        assert "instructions" not in server.requests[-1]


@pytest.mark.parametrize("status,error", [(401, "auth"), (429, "rate_limit"), (500, "server")])
def test_refusals_become_categories(status, error):
    with FakeSpeechServer(status) as server:
        request = _service(server).say("Contact.", "en", "xo")
        assert request.wait(10) and request.error == error


def test_unusable_audio_is_a_bad_reply():
    with FakeSpeechServer(b"not audio at all") as server:
        request = _service(server).say("Contact.", "en", "xo")
        assert request.wait(10) and request.error == "bad_reply"


def test_crew_reports_go_first_and_repeat_from_the_cache():
    with FakeSpeechServer(delay_s=0.2) as server:
        service = _service(server)
        first = service.say("Officer answer one.", "en", "xo")
        time.sleep(0.05)          # the worker holds the first one
        later = service.say("Officer answer two.", "en", "xo")
        crew = service.say("Action stations.", "en", "crew")
        assert later.wait(10) and crew.wait(10) and first.wait(10)
        inputs = [body["input"] for body in server.requests]
        assert inputs.index("Action stations.") < inputs.index("Officer answer two.")
        again = service.say("Action stations.", "en", "crew")
        assert again.wait(10) and again.cached and len(server.requests) == 3


def test_a_full_crew_queue_drops_its_oldest_report():
    service = voice.VoiceService(voice.VoiceConfig(enabled=True), queue_max=2)
    service._ensure_worker = lambda: None
    a, b, c = (service.say(text, "en", "crew") for text in ("A.", "B.", "C."))
    assert a.status == "dropped" and b.status == c.status == "pending"
    assert service.say("X.", "en", "xo") is not None
    assert service.say("Y.", "en", "xo") is not None
    assert service.say("Z.", "en", "xo") is None


# -- keys and settings -----------------------------------------------------------------

def test_voice_key_has_its_own_file_and_never_enters_settings(isolated_saves, tmp_path):
    assert keystore.save_key("sk-voice-key-987654", keystore.VOICE_FILE_NAME)
    assert keystore.load_key(keystore.VOICE_ENV_NAME, keystore.VOICE_FILE_NAME) \
        == "sk-voice-key-987654"
    assert keystore.load_key() == ""
    prefs = dataclasses.replace(Preferences(), tts_enabled=True, tts_voice="nova")
    path = save_preferences(prefs, tmp_path / "settings.json")
    text = path.read_text()
    assert "sk-voice" not in text
    loaded = load_preferences(path)
    assert loaded.tts_enabled and loaded.tts_voice == "nova" and loaded.tts_xo


def test_bad_voice_settings_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"tts_url": "ftp://x", "tts_model": "", "tts_voice": 7,
                                "tts_enabled": "yes"}))
    loaded = load_preferences(path)
    defaults = Preferences()
    assert (loaded.tts_url, loaded.tts_model, loaded.tts_voice, loaded.tts_enabled) == (
        defaults.tts_url, defaults.tts_model, defaults.tts_voice, False)


def _game():
    return Game(seed=4471, start_menu=False, audio_enabled=False)


class _Mixer:
    """Stands in for the audio engine's voice channel."""

    def __init__(self, game):
        self.played = []
        game.audio.enabled = game.audio.available = True
        game.audio.play_voice = lambda pcm: self.played.append(pcm) or True
        game.audio.voice_busy = lambda: False


def _voice_on(game, server, **prefs):
    game.preferences = dataclasses.replace(
        game.preferences, tts_enabled=True, tts_url=server.url, tts_model="tts", **prefs)
    game.configure_voice()


def _pump(game, done, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        game.llm_tick()
        game._pump_speech()
        if done():
            return True
        time.sleep(0.02)
    return False


def test_language_model_key_is_shared_on_the_same_server(isolated_saves):
    game = _game()
    keystore.save_key("sk-shared-key-123456")
    game.preferences = dataclasses.replace(game.preferences, llm_url="https://api.openai.com/v1")
    game.configure_voice()
    assert game.voice_key_source() == "shared"
    assert game.voice.config.api_key == "sk-shared-key-123456"
    game.set_llm_preference("llm_url", "http://localhost:11434/v1")
    assert game.voice_key_source() == "none" and game.voice.config.api_key == ""
    game.save_voice_key("sk-own-voice-key-42")
    assert game.voice_key_source() == "own"


def test_off_by_default_the_crew_keeps_espeak(monkeypatch):
    game = _game()
    said = []
    monkeypatch.setattr(game.speaker, "engine", "espeak-ng")
    monkeypatch.setattr(game.speaker, "say", lambda text, language: said.append(text))
    game.preferences = dataclasses.replace(game.preferences, speech=True)
    game.callouts.add(message("crew.action_stations_on"))
    game._pump_speech()
    assert said and game.voice.sent == 0 and not game._voice_queue


def test_executive_officer_speaks_his_answer():
    with FakeLlmServer("Lage ruhig, Kontakt in 431.") as llm, FakeSpeechServer() as speech:
        game = _game()
        game._set_preference("language", "de")
        mixer = _Mixer(game)
        game.preferences = dataclasses.replace(game.preferences, llm_enabled=True,
                                               llm_url=llm.url, llm_model="m")
        game.configure_llm()
        _voice_on(game, speech)
        assert isinstance(game.advisor_ask("situation"), dict)
        assert _pump(game, lambda: mixer.played)
        # Numbers digit by digit, the way the watch speaks them.
        assert speech.requests[0]["input"] == "Lage ruhig, Kontakt in vier drei eins."
        # Switched off: the next answer stays silent.
        game.set_voice_preference("tts_xo", False)
        assert isinstance(game.advisor_ask("situation"), dict)
        _pump(game, lambda: game.advisor.log("local")[-1]["status"] == "done")
        _pump(game, lambda: False, timeout=0.3)
        assert len(speech.requests) == 1


def test_crew_reports_use_the_voice_and_fall_back_to_espeak(monkeypatch):
    with FakeSpeechServer() as speech:
        game = _game()
        mixer = _Mixer(game)
        said = []
        monkeypatch.setattr(game.speaker, "engine", "espeak-ng")
        monkeypatch.setattr(game.speaker, "say", lambda text, language: said.append(text))
        game.preferences = dataclasses.replace(game.preferences, speech=True)
        _voice_on(game, speech)
        game.callouts.add(message("crew.action_stations_on"))
        assert _pump(game, lambda: mixer.played)
        assert not said and len(speech.requests) == 1
        speech.reply = 500
        game.callouts.add(message("crew.action_stations_on"))
        game.voice._cache.clear()
        assert _pump(game, lambda: said)
        assert len(mixer.played) == 1


def test_voice_never_changes_the_simulation():
    with FakeSpeechServer() as speech:
        plain, spoken = Game(seed=4472, start_menu=False, audio_enabled=False), \
            Game(seed=4472, start_menu=False, audio_enabled=False)
        _Mixer(spoken)
        spoken.preferences = dataclasses.replace(spoken.preferences, speech=True)
        _voice_on(spoken, speech)
        for _ in range(60):
            plain.update(0.1)
            spoken.update(0.1)
            spoken._pump_speech()
        assert (plain.ship.x, plain.ship.y, plain.sim_t) == (spoken.ship.x, spoken.ship.y,
                                                              spoken.sim_t)


def test_settings_have_a_voice_page_by_key_and_mouse(isolated_saves, monkeypatch):
    from src.core.game_advisor import VOICE_ROWS
    from src.ui import advisor_view, pointer
    game = _game()
    game._open_administration("llm")
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0, unicode="\t"))
    assert game.llm_page == 1 and game.llm_rows() == VOICE_ROWS
    game.click_llm_row(VOICE_ROWS.index("tts_enabled"))
    assert game.preferences.tts_enabled
    game.click_llm_row(VOICE_ROWS.index("tts_voice"))
    assert game.preferences.tts_voice != "onyx"
    game.click_llm_row(VOICE_ROWS.index("tts_key"))
    assert game.llm_field_name == "tts_key" and game.llm_field.secret
    game.llm_field.value = "sk-typed-voice-key-77"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert keystore.load_key(keystore.VOICE_ENV_NAME, keystore.VOICE_FILE_NAME) \
        == "sk-typed-voice-key-77"
    assert game.voice.config.api_key == "sk-typed-voice-key-77"
    # Drawn: tabs and rows are click targets; the key file is not read per frame.
    shown = []
    monkeypatch.setattr(keystore, "load_key", lambda *a: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(advisor_view.layout, "blit_line",
                        lambda _s, text, *a, **k: shown.append(str(text)))
    pointer.reset()
    with pointer.layer("overlay"):
        advisor_view.draw_llm_settings(game)
    assert not any("typed-voice" in text for text in shown)
    tab = advisor_view.page_tab_rects()[0]
    pointer.hit(tab.center, "overlay").action(tab.center)
    assert game.llm_page == 0


def test_voice_has_its_own_reserved_channel_beside_the_sonar(monkeypatch):
    from unittest.mock import Mock
    from src.audio.engine import AudioEngine
    channels = [Mock() for _ in range(5)]
    for channel in channels:
        channel.get_busy.return_value = False
        channel.get_queue.return_value = None
    backend = Mock()
    backend.get_init.return_value = (22050, -16, 2)
    backend.get_num_channels.return_value = 4
    backend.Channel.side_effect = channels.__getitem__
    monkeypatch.setattr(pygame, "mixer", backend)
    made = []
    monkeypatch.setattr(pygame.sndarray, "make_sound", lambda pcm: made.append(pcm) or Mock())
    engine = AudioEngine()
    backend.set_reserved.assert_called_once_with(4)
    assert engine.play_voice(np.zeros(100, dtype=np.int16))
    backend.set_num_channels.assert_called_with(5)
    backend.set_reserved.assert_called_with(5)
    assert channels[4].play.called and not channels[1].play.called
    assert made[0].shape == (100, 2)
    channels[4].get_busy.return_value = True
    assert engine.voice_busy()
    engine.stop_voice()
    assert channels[4].stop.called


# -- how the voice sounds (temperature, top_p, seed, clean-up) -----------------------

@pytest.mark.parametrize("text,said", [
    ("**Lage:** ruhig 😀 haha. *lacht* Kontakt Peilung 270.",
     "Lage: ruhig. Kontakt Peilung 270."),
    ("- Punkt eins\n- [Handbuch](http://x/y) LOL!", "Punkt eins Handbuch"),
    ("Hahaha, gut gemacht 👍🏽! (seufzt) [Pause]", "gut gemacht!"),
    ("Die Hohe See. Kurs 270... hehe", "Die Hohe See. Kurs 270..."),
])
def test_text_is_cleaned_before_speaking(text, said):
    assert voice.clean_for_speech(text) == said


def test_clean_up_can_be_switched_off():
    assert voice.speakable("**Ja** 😀 haha", clean=False) == "**Ja** 😀 haha"


def test_sampling_reaches_services_that_take_it():
    with FakeSpeechServer() as server:
        config = voice.VoiceConfig(enabled=True, base_url=server.url, model="qwen-tts",
                                   voice="Chelsie", temperature=0.6, top_p=0.8, seed=7)
        request = voice.VoiceService(config).say("Kontakt.", "de", "xo")
        assert request.wait(10) and request.ok
        body = server.requests[0]
        assert (body["temperature"], body["top_p"], body["seed"]) == (0.6, 0.8, 7)
        random = dataclasses.replace(config, seed=-1)
        service = voice.VoiceService(random)
        assert service.say("Kontakt zwei.", "de", "xo").wait(10)
        assert "seed" not in server.requests[-1]


def test_a_service_refusing_sampling_is_asked_without_it_first():
    def reply(body):
        return 422 if "temperature" in body else None
    with FakeSpeechServer(reply) as server:
        request = _service(server).say("Kontakt.", "en", "xo")
        assert request.wait(10) and request.ok
        assert "temperature" not in server.requests[-1]
        assert "instructions" in server.requests[-1]


def test_openai_never_gets_sampling_fields():
    sent = []

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, _limit):
            return _wav(TONE)

    def opener(request, timeout):
        sent.append(json.loads(request.data))
        return Answer()
    config = voice.VoiceConfig(enabled=True, seed=5)
    request = voice.VoiceService(config, opener=opener).say("Contact.", "en", "xo")
    assert request.wait(10) and request.ok
    assert not {"temperature", "top_p", "seed"} & set(sent[0])


def test_sound_settings_are_kept_and_checked(tmp_path):
    prefs = dataclasses.replace(Preferences(), tts_temperature=0.55, tts_top_p=0.9,
                                tts_seed=1234, tts_clean=False)
    loaded = load_preferences(save_preferences(prefs, tmp_path / "settings.json"))
    assert (loaded.tts_temperature, loaded.tts_top_p, loaded.tts_seed, loaded.tts_clean) \
        == (0.55, 0.9, 1234, False)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"tts_temperature": 9, "tts_top_p": 0, "tts_seed": True}))
    loaded = load_preferences(path)
    assert (loaded.tts_temperature, loaded.tts_top_p, loaded.tts_seed) == (0.9, 1.0, -1)


def test_sound_page_steps_and_types_numbers(isolated_saves):
    from src.core.game_advisor import TUNE_ROWS
    game = _game()
    game._open_administration("llm")
    game.set_llm_page(2)
    game.llm_sel = TUNE_ROWS.index("tts_temperature")
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0, unicode=""))
    assert game.preferences.tts_temperature == 0.85
    game.click_llm_row(TUNE_ROWS.index("tts_seed"))
    assert game.llm_field_name == "tts_seed"
    game.llm_field.value = "42"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert game.preferences.tts_seed == 42 and game.voice.config.seed == 42
    game.click_llm_row(TUNE_ROWS.index("tts_top_p"))
    game.llm_field.value = "nan"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r"))
    assert game.preferences.tts_top_p == 1.0
    game.click_llm_row(TUNE_ROWS.index("tts_clean"))
    assert not game.preferences.tts_clean and not game.voice.config.clean
