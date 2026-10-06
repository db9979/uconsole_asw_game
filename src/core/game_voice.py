"""The optional voice of the language-model add-on (``src/llm/voice.py``).

With a speech service configured (options page 2, Language model, page
"Voice") the executive officer speaks his answers and coach tips, and the
crew's spoken reports use the same natural voice instead of espeak-ng.
Requests run on the service's worker; this mixin only collects the pieces
of audio that have arrived, once per frame (wall time, outside the
simulation), and queues them on the audio engine's own voice channel, so
the sonar tone is never cut and a streaming service is heard while it still
speaks.  Every report goes to the service in one piece (a speech model
starts each request afresh, so a new request mid-answer audibly changes
the speaker's tone), ends with a full stop, and a short silence
(``VOICE_GAP_S``) follows it, so one report never runs into the next.
The local side's log entries (the event feed, F11) are read aloud too,
behind the officer: each station of the log can be muted on its own
(options page 2, page 4 "Log reports", and the F11 log's buttons).  Every
entry is read, one after the other in the log's order: the entries wait in
a backlog here and only two at a time go to the speech service, so its
queue never drops one.  Entries the crew already calls out are not read
twice.
Without the service (off, no key, offline, no audio) the crew keeps its
espeak-ng voice and the game behaves exactly as before.

A browser station's executive officer speaks too: the host asks the same
service for the answer (the key never leaves the host, also without a
speaker of its own, as "Server (nur Browser)") and keeps the finished
audio for that browser alone (``web_voice_clips``), which fetches it at
``GET /api/v2/advisor/voice`` (``src/commander/advisor_web.py``).
"""

from __future__ import annotations

import datetime
import time
import urllib.parse
from collections import OrderedDict, deque

import numpy as np

from src.core import callouts, config
from src.core.i18n import localize, message
from src.llm import keystore
from src.llm import voice as voice_model
from src.llm.voice import PRESET_VOICES, VoiceConfig, VoiceService

VOICE_QUEUE_MAX = 16
# Silence between two reports (wall seconds), so one never runs into the next.
VOICE_GAP_S = 0.6
# Failures after which a crew report is said by espeak-ng instead.
_FALLBACK_ERRORS = frozenset(("network", "timeout", "auth", "rate_limit", "server",
                              "bad_reply", "no_audio"))
# Log entries waiting to be read, in the log's order (only a flood beyond
# this drops its oldest), and how many of them are at the speech service
# at once (made or playing; below the service's own queue, so it never
# drops one).
LOG_BACKLOG_MAX = 48
LOG_IN_FLIGHT = 2
# Log entries per station counted over this many wall seconds (settings page).
LOG_COUNT_S = 300.0
LOG_COUNT_MAX = 256
# Spoken answers kept for the browsers (newest first out), and their bytes.
WEB_VOICE_CLIPS = 8
WEB_VOICE_BYTES = 24 * 1024 * 1024


def log_group(category) -> str | None:
    """The station of the log a feed category belongs to, or None."""
    group = config.LOG_VOICE_GROUP_OF.get(category, category)
    return group if group in config.LOG_VOICE_GROUPS else None


def _sentence(text: str) -> str:
    """A log entry closed like a sentence (a full stop as its end)."""
    return voice_model.close_sentence(text)


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
        # A short silence after each report before the next one starts.
        self._voice_quiet_until = 0.0
        # Which log is being read and how far (display state, never saved).
        self._log_voice_source = None
        self._log_voice_mark = 0
        self._log_voice_seen: deque = deque(maxlen=LOG_COUNT_MAX)
        self._log_voice_backlog: deque = deque(maxlen=LOG_BACKLOG_MAX)
        # Browser askers' answers: requests on their way, finished clips
        # ((asker, seq) -> int16 mono bytes at ``web_voice_rate``).
        self._web_voice_pending: list = []
        self.web_voice_clips: OrderedDict = OrderedDict()
        self.web_voice_rate = self._voice_rate()

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
        # Every report ends with a full stop: the model then closes it with
        # its sentence pause instead of running on.
        text = voice_model.close_sentence(
            voice_model.speakable(self._voice_text(text), clean=self.voice.config.clean))
        if not text:
            return False
        # One request for the whole report: the model would start every
        # extra request with a slightly different voice.
        request = self.voice.say(text, self.llm_language(), role)
        if request is None:
            return False
        self._voice_queue.append(request)
        return True

    def _voice_text(self, text) -> str:
        """Numbers digit by digit in the game's language ("vier drei eins"),
        units and short forms said in full ("Knoten", "Seemeilen")."""
        digits = [self.tr(f"voice.digit_{digit}") for digit in range(10)]
        # Units and short forms in full first ("12 kn" -> "12 Knoten").
        words = {name: self.tr(f"voice.word.{name}") for name in voice_model.WORD_NAMES}
        words.update((f"letter_{letter}", self.tr(f"voice.letter.{letter.lower()}"))
                     for letter in voice_model.LETTERS)
        text = voice_model.spoken_words(text, words)
        return voice_model.spell_digits(text, digits, self.tr("voice.digit_point"))

    def voice_advisor_entry(self, entry) -> None:
        """Speak a finished answer the executive officer gave: on the
        uConsole's own speaker, or as audio for the browser that asked."""
        if entry.get("status") != "done" or not entry.get("answer"):
            return
        if any(row is entry for row in self.advisor.logs.get("local", ())):
            self.voice_say(entry["answer"], "xo")
            return
        asker = next((name for name, rows in self.advisor.logs.items()
                      if name.startswith("web:") and any(row is entry for row in rows)), None)
        if asker is not None:
            self.voice_web_answer(asker, entry["seq"], entry["answer"])

    def voice_web_answer(self, asker: str, seq: int, answer) -> bool:
        """Ask the service to say a browser asker's answer (host side only:
        the browser fetches the audio, never the service or its key)."""
        if not self.voice.active or not self.preferences.tts_xo:
            return False
        text = voice_model.speakable(self._voice_text(answer), clean=self.voice.config.clean)
        request = self.voice.say(text, self.llm_language(), "xo") if text else None
        if request is None:
            return False
        self._web_voice_pending.append((asker, int(seq), request))
        return True

    def _pump_web_voice(self) -> None:
        """Keep the browsers' finished answers (wall time, every frame)."""
        if not hasattr(self, "voice") or not self._web_voice_pending:
            return
        waiting = []
        for asker, seq, request in self._web_voice_pending:
            if not request.finished:
                waiting.append((asker, seq, request))
                continue
            if request.ok and request.pcm is not None and len(request.pcm):
                self._keep_web_voice((asker, seq), request.pcm)
        self._web_voice_pending = waiting

    def _keep_web_voice(self, key, pcm) -> None:
        clips = self.web_voice_clips
        rate = self.voice.rate
        if rate != self.web_voice_rate:
            # Clips of another rate cannot share the browsers' header.
            clips.clear()
            self.web_voice_rate = rate
        clips[key] = np.asarray(pcm, dtype="<i2").tobytes()
        clips.move_to_end(key)
        while clips and (len(clips) > WEB_VOICE_CLIPS
                         or sum(len(clip) for clip in clips.values()) > WEB_VOICE_BYTES):
            clips.popitem(last=False)

    def web_voice_stop(self) -> None:
        self._web_voice_pending = []
        self.web_voice_clips.clear()

    def voice_stop(self) -> None:
        voice = getattr(self, "voice", None)
        if voice is None:
            return
        voice.clear()
        self._voice_queue.clear()
        self._log_voice_backlog.clear()
        self.web_voice_stop()
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
                self._voice_quiet_until = time.monotonic() + VOICE_GAP_S
            return
        queue = self._voice_queue
        if not queue:
            return
        now = time.monotonic()
        if now < self._voice_quiet_until:
            return
        kept = []
        for request in queue:
            if request.status in ("failed", "dropped"):
                if (request.role == "crew" and request.error in _FALLBACK_ERRORS
                        and self.preferences.speech and self.speaker.available
                        and not request.stale(now)):
                    self.speaker.say(request.text, self.llm_language())
                continue
            if request.stale(now) and not request.audible:
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
        if len(pieces) > 1:
            # Everything that has arrived plays as one sound: a frame that
            # comes late (the uConsole under load) then never finds the
            # channel empty between two short pieces, which made the voice
            # stumble and drop syllables.
            joined = np.concatenate(list(pieces))
            pieces.clear()
            pieces.append(joined)
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
        """Read the local side's new log entries aloud, in order (wall time,
        once per frame; reads the log the operator already sees)."""
        self._collect_log_voice()
        self._feed_log_voice()

    def _collect_log_voice(self) -> None:
        source, count, entries = self._log_voice_entries()
        if source is not self._log_voice_source or count < self._log_voice_mark:
            # A new mission, a loaded game or the other side: start at its end.
            self._log_voice_source, self._log_voice_mark = source, count
            self._log_voice_backlog.clear()
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
        for row in rows:
            category, text = ((row["category"], row["text"]) if isinstance(row, dict)
                              else (row.category, row.text))
            group = log_group(category)
            if group is None:
                continue
            self._log_voice_seen.append((now, group))
            if not ready or not self.log_voice_on(group):
                continue
            if crew_speaks and callouts.callout_of(text, side) is not None:
                continue            # the crew already calls this one out
            spoken = localize(text, self.tr)
            if spoken:
                self._log_voice_backlog.append(spoken)

    def _feed_log_voice(self) -> None:
        """Hand the waiting entries to the speech service, oldest first, at
        most ``LOG_IN_FLIGHT`` at a time."""
        backlog = self._log_voice_backlog
        if not backlog:
            return
        if not self.voice_ready():
            backlog.clear()
            return
        in_flight = sum(1 for request in self._voice_queue if request.role == "log")
        playing = self._voice_playing
        if playing is not None and playing.role == "log":
            in_flight += 1
        while backlog and in_flight < LOG_IN_FLIGHT:
            # Each entry is its own request, closed with a full stop, and
            # VOICE_GAP_S of silence follows it: a speech model leaves only
            # its short sentence pause between entries sent together.
            if self.voice_say(_sentence(backlog.popleft()), "log"):
                in_flight += 1

    # -- settings -----------------------------------------------------------------

    def set_voice_preference(self, name: str, value) -> None:
        self._set_preference(name, value)
        self.configure_voice()
        if name == "tts_url" and hasattr(self, "configure_stt"):
            self.configure_stt()        # the speech input may share its key
        if name == "tts_enabled" and not value:
            self.voice_stop()

    def save_voice_key(self, value: str) -> bool:
        ok = keystore.save_key(value, keystore.VOICE_FILE_NAME)
        self.configure_voice()
        if hasattr(self, "configure_stt"):
            self.configure_stt()
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
