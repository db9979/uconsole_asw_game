"""The optional voice of the language-model add-on (``src/llm/voice.py``).

With a speech service configured (options page 2, Language model, page
"Voice") the executive officer speaks his answers and coach tips, and the
crew's spoken reports use the same natural voice instead of espeak-ng.
Requests run on the service's worker; this mixin only collects the pieces
of audio that have arrived, once per frame (wall time, outside the
simulation), and queues them on the audio engine's own voice channel, so
the sonar tone is never cut and a streaming service is heard while it still
speaks.  A long answer is sent sentence by sentence: the first sentence
plays while the rest is still being made.
The local side's log entries (the event feed, F11) are read aloud too,
behind the officer: each station of the log can be muted on its own
(options page 2, page 4 "Log reports", and the F11 log's buttons), and an
entry still waiting when it is old news is dropped, so the voice never lags
behind the game.  Entries the crew already calls out are not read twice.
Without the service (off, no key, offline, no audio) the crew keeps its
espeak-ng voice and the game behaves exactly as before.
"""

from __future__ import annotations

import datetime
import time
import urllib.parse
from collections import deque

from src.core import callouts, config
from src.core.callouts import PREFIX as CALLOUT_PREFIX
from src.core.i18n import localize, message
from src.llm import keystore
from src.llm import voice as voice_model
from src.llm.voice import PRESET_VOICES, VoiceConfig, VoiceService

VOICE_QUEUE_MAX = 16
# Failures after which a crew report is said by espeak-ng instead.
_FALLBACK_ERRORS = frozenset(("network", "timeout", "auth", "rate_limit", "server",
                              "bad_reply", "no_audio"))
# At most this many new log entries are queued per frame (a burst keeps its
# newest ones; the voice service's own log queue is shorter still).
LOG_BURST = 4
# Log entries per station counted over this many wall seconds (settings page).
LOG_COUNT_S = 300.0
LOG_COUNT_MAX = 256


def log_group(category) -> str | None:
    """The station of the log a feed category belongs to, or None."""
    group = config.LOG_VOICE_GROUP_OF.get(category, category)
    return group if group in config.LOG_VOICE_GROUPS else None


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
        self._voice_playing = None
        # Which log is being read and how far (display state, never saved).
        self._log_voice_source = None
        self._log_voice_mark = 0
        self._log_voice_seen: deque = deque(maxlen=LOG_COUNT_MAX)

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
                           model=prefs.tts_model, voice=prefs.tts_voice, api_key=key,
                           temperature=float(prefs.tts_temperature),
                           top_p=float(prefs.tts_top_p), seed=int(prefs.tts_seed),
                           clean=bool(prefs.tts_clean))

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
        text = voice_model.speakable(self._voice_text(text), clean=self.voice.config.clean)
        queued = False
        # A log entry or a crew call is said in one piece, like one sentence;
        # only the officer's longer answers start with their first sentence.
        chunks = ([text] if role in ("log", "crew") and text
                  else voice_model.sentence_chunks(text, limit=voice_model.QUEUE_MAX))
        for chunk in chunks:
            request = self.voice.say(chunk, self.llm_language(), role)
            if request is None:
                break
            self._voice_queue.append(request)
            queued = True
        return queued

    def _voice_text(self, text) -> str:
        """Numbers digit by digit in the game's language ("vier drei eins"),
        units and short forms said in full ("Knoten", "Seemeilen")."""
        digits = [self.tr(f"{CALLOUT_PREFIX}digit_{digit}") for digit in range(10)]
        # Units and short forms in full first ("12 kn" -> "12 Knoten").
        words = {name: self.tr(f"voice.word.{name}") for name in voice_model.WORD_NAMES}
        text = voice_model.spoken_words(text, words)
        return voice_model.spell_digits(text, digits, self.tr("voice.digit_point"))

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
        self._voice_playing = None
        self.audio.stop_voice()

    def _pump_voice(self) -> None:
        """Play the next finished clip when the voice channel is free."""
        if not hasattr(self, "voice"):
            return
        if self.voice.rate != self._voice_rate():
            self.configure_voice()
        playing = self._voice_playing
        if playing is not None:
            self._feed_voice(playing)
            if playing.finished and not playing.pieces and not self.audio.voice_busy():
                self._voice_playing = None
            return
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
            if request.stale(now) and (not request.audible or request.role == "log"):
                # A log entry that is old news before its turn is not said.
                continue
            kept.append(request)
        queue.clear()
        queue.extend(kept)
        if not kept or self.audio.voice_busy():
            return
        # A crew report that has sound goes first; the officer's sentences
        # keep their order (never one before the sentence ahead of it); log
        # entries wait until the officer has nothing left to say.
        pick = next((request for request in kept if request.role == "crew" and request.audible),
                    None)
        if pick is None:
            first = next((request for request in kept if request.role not in ("crew", "log")),
                         None)
            if first is None:
                first = next((request for request in kept if request.role == "log"), None)
            pick = first if first is not None and first.audible else None
        if pick is None:
            return
        queue.remove(pick)
        self._voice_playing = pick
        self._feed_voice(pick)

    def _feed_voice(self, request) -> None:
        """Queue the pieces that have arrived behind the one playing."""
        pieces = request.pieces
        while pieces:
            if not self.audio.voice_busy():
                played = self.audio.play_voice(pieces[0])
                if not played:
                    pieces.clear()
                    if request.role == "test":
                        self.voice_test = dict(status="failed", error="no_audio")
                    return
            elif not self.audio.queue_voice(pieces[0]):
                return
            pieces.popleft()

    # -- log entries read aloud ---------------------------------------------------

    def log_voice_on(self, group: str) -> bool:
        prefs = self.preferences
        return bool(prefs.tts_log and getattr(prefs, f"tts_log_{group}", False))

    def toggle_log_voice(self, group: str) -> None:
        """Mute or unmute one station of the log (settings page, F11 log)."""
        if group in config.LOG_VOICE_GROUPS:
            name = f"tts_log_{group}"
            self.set_voice_preference(name, not getattr(self.preferences, name))

    def log_voice_count(self, group: str) -> int:
        """Log entries of one station in the last LOG_COUNT_S wall seconds."""
        since = time.monotonic() - LOG_COUNT_S
        return sum(1 for when, seen in self._log_voice_seen if seen == group and when >= since)

    def _log_voice_entries(self):
        """``(log, count, entries)`` of the local side: the frigate's feed
        or the crewed boat's log; entries as ``(category, text)``."""
        if getattr(self, "local_side", "frigate") == "uboot":
            boat = getattr(self, "_opfor", None)
            if boat is None:
                return None, 0, ()
            return boat, boat.feed_seq, boat.feed
        feed = getattr(self, "feed", None)
        if feed is None:
            return None, 0, ()
        return feed, feed.added, feed.entries

    def _pump_log_voice(self) -> None:
        """Queue the local side's new log entries for the voice (wall time,
        once per frame; reads the log the operator already sees)."""
        source, count, entries = self._log_voice_entries()
        if source is not self._log_voice_source or count < self._log_voice_mark:
            # A new mission, a loaded game or the other side: start at its end.
            self._log_voice_source, self._log_voice_mark = source, count
            return
        fresh = count - self._log_voice_mark
        if fresh <= 0:
            return
        self._log_voice_mark = count
        rows = list(entries)[-min(fresh, LOG_COUNT_MAX):]
        now = time.monotonic()
        ready = self.voice_ready()
        side = "boat" if getattr(self, "local_side", "frigate") == "uboot" else "frigate"
        crew_speaks = bool(self.preferences.speech and (
            self.speaker.available or (ready and self.preferences.tts_crew)))
        for index, row in enumerate(rows):
            category, text = ((row["category"], row["text"]) if isinstance(row, dict)
                              else (row.category, row.text))
            group = log_group(category)
            if group is None:
                continue
            self._log_voice_seen.append((now, group))
            if (not ready or index < len(rows) - LOG_BURST
                    or not self.log_voice_on(group)):
                continue
            if crew_speaks and callouts.callout_of(text, side) is not None:
                continue            # the crew already calls this one out
            spoken = localize(text, self.tr)
            if spoken:
                self.voice_say(spoken, "log")

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

    def step_voice_number(self, name: str, step: int) -> None:
        """Left/Right on temperature, top_p or seed."""
        prefs = self.preferences
        if name == "tts_seed":
            value = max(-1, min(voice_model.SEED_MAX, int(prefs.tts_seed) + step))
        else:
            low, high = (voice_model.TEMPERATURE_RANGE if name == "tts_temperature"
                         else voice_model.TOP_P_RANGE)
            value = round(min(high, max(low, getattr(prefs, name) + 0.05 * step)), 2)
        self.set_voice_preference(name, value)

    def start_voice_test(self) -> bool:
        """Say one sample sentence and show how long the service took."""
        if not self.voice.active:
            self.voice_test = dict(status="failed", error="disabled")
            return False
        if not self.voice_ready():
            self.voice_test = dict(status="failed", error="no_audio")
            return False
        phrase = localize(message("voice.test.phrase"), self.tr)
        request = self.voice.say(self._voice_text(phrase), self.llm_language(), "test")
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
