"""The optional voice of the language-model add-on (``src/llm/voice.py``).

With a speech service configured (options page 2, Language model, page
"Voice") the executive officer speaks his answers and coach tips, and the
crew's spoken reports use the same natural voice instead of espeak-ng.
Requests run on the service's worker; this mixin only collects finished
clips once per frame (wall time, outside the simulation) and plays them on
the audio engine's own voice channel, so the sonar tone is never cut.
Without the service (off, no key, offline, no audio) the crew keeps its
espeak-ng voice and the game behaves exactly as before.
"""

from __future__ import annotations

import datetime
import time
import urllib.parse
from collections import deque

from src.core.i18n import localize, message
from src.llm import keystore
from src.llm.voice import PRESET_VOICES, VoiceConfig, VoiceService

VOICE_QUEUE_MAX = 16
# Failures after which a crew report is said by espeak-ng instead.
_FALLBACK_ERRORS = frozenset(("network", "timeout", "auth", "rate_limit", "server",
                              "bad_reply", "no_audio"))


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class VoiceMixin:
    def _init_voice(self) -> None:
        self.voice = VoiceService(self._voice_config(), rate=self._voice_rate())
        self._voice_queue: deque = deque(maxlen=VOICE_QUEUE_MAX)
        self.voice_test = None

    def _voice_rate(self) -> int:
        return int(getattr(self.audio, "sample_rate", 22050) or 22050)

    def voice_key_source(self) -> str:
        """"env", "own", "shared" (the model's key, same server) or "none";
        read when the voice was configured, never per frame."""
        return getattr(self, "_voice_key_source", "none")

    def _voice_shared_key(self) -> str:
        """The language model's key when both talk to the same server."""
        prefs = self.preferences
        host = _host(prefs.tts_url)
        if not host or host != _host(prefs.llm_url):
            return ""
        return keystore.load_key()

    def _voice_config(self) -> VoiceConfig:
        prefs = self.preferences
        key = keystore.load_key(keystore.VOICE_ENV_NAME, keystore.VOICE_FILE_NAME)
        source = ("env" if keystore.key_from_env(keystore.VOICE_ENV_NAME)
                  else "own" if key else "none")
        if not key:
            key = self._voice_shared_key()
            source = "shared" if key else "none"
        self._voice_key_source = source
        return VoiceConfig(enabled=bool(prefs.tts_enabled), base_url=prefs.tts_url,
                           model=prefs.tts_model, voice=prefs.tts_voice, api_key=key)

    def configure_voice(self) -> None:
        self.voice.configure(self._voice_config(), rate=self._voice_rate())

    def voice_ready(self) -> bool:
        """The service is on and this uConsole can play what it says."""
        return (self.voice.active and not getattr(self, "web_mode", False)
                and bool(getattr(self.audio, "enabled", False))
                and bool(getattr(self.audio, "available", False)))

    # -- speaking ----------------------------------------------------------------

    def voice_say(self, text, role: str) -> bool:
        """Queue one sentence for the natural voice; False when it is not used
        (the caller keeps its own voice, if any)."""
        if not self.voice_ready():
            return False
        if role == "crew" and not self.preferences.tts_crew:
            return False
        if role == "xo" and not self.preferences.tts_xo:
            return False
        request = self.voice.say(text, self.llm_language(), role)
        if request is None:
            return False
        self._voice_queue.append(request)
        return True

    def voice_advisor_entry(self, entry) -> None:
        """Speak a finished answer the uConsole's own executive officer gave."""
        if entry.get("status") != "done" or not entry.get("answer"):
            return
        if not any(row is entry for row in self.advisor.logs.get("local", ())):
            return
        self.voice_say(entry["answer"], "xo")

    def voice_stop(self) -> None:
        voice = getattr(self, "voice", None)
        if voice is None:
            return
        voice.clear()
        self._voice_queue.clear()
        self.audio.stop_voice()

    def _pump_voice(self) -> None:
        """Play the next finished clip when the voice channel is free."""
        if not hasattr(self, "voice"):
            return
        if self.voice.rate != self._voice_rate():
            self.configure_voice()
        queue = self._voice_queue
        if not queue:
            return
        now = time.monotonic()
        kept = []
        for request in queue:
            if request.status in ("failed", "dropped"):
                if (request.role == "crew" and request.error in _FALLBACK_ERRORS
                        and self.preferences.speech and self.speaker.available
                        and not request.stale(now)):
                    self.speaker.say(request.text, self.llm_language())
                continue
            if request.stale(now):
                continue
            kept.append(request)
        queue.clear()
        queue.extend(kept)
        if not kept or self.audio.voice_busy():
            return
        ready = [request for request in kept if request.ok]
        if not ready:
            return
        pick = next((request for request in ready if request.role == "crew"), ready[0])
        queue.remove(pick)
        if not self.audio.play_voice(pick.pcm) and pick.role == "test":
            self.voice_test = dict(status="failed", error="no_audio")

    # -- settings -----------------------------------------------------------------

    def set_voice_preference(self, name: str, value) -> None:
        self._set_preference(name, value)
        self.configure_voice()
        if name == "tts_enabled" and not value:
            self.voice_stop()

    def save_voice_key(self, value: str) -> bool:
        ok = keystore.save_key(value, keystore.VOICE_FILE_NAME)
        self.configure_voice()
        return ok

    def cycle_voice(self, step: int) -> None:
        current = self.preferences.tts_voice
        index = PRESET_VOICES.index(current) if current in PRESET_VOICES else -1
        if index < 0 and step < 0:
            index = 0
        self.set_voice_preference("tts_voice",
                                  PRESET_VOICES[(index + step) % len(PRESET_VOICES)])

    def start_voice_test(self) -> bool:
        """Say one sample sentence and show how long the service took."""
        if not self.voice.active:
            self.voice_test = dict(status="failed", error="disabled")
            return False
        if not self.voice_ready():
            self.voice_test = dict(status="failed", error="no_audio")
            return False
        request = self.voice.say(localize(message("voice.test.phrase"), self.tr),
                                 self.llm_language(), "test")
        if request is None:
            self.voice_test = dict(status="failed", error="busy")
            return False
        self._voice_queue.append(request)
        self.voice_test = dict(status="pending", request=request,
                               started=datetime.datetime.now())
        return True

    def voice_test_state(self) -> dict | None:
        test = self.voice_test
        if test is None or test["status"] != "pending":
            return test
        request = test["request"]
        if not request.finished:
            return test
        self.voice_test = (dict(status="done", latency_s=request.latency_s or 0.0)
                           if request.ok else dict(status="failed", error=request.error))
        return self.voice_test
