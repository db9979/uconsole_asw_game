"""Non-blocking client for an OpenAI-compatible ``/audio/speech`` endpoint.

The optional voice of the language-model add-on: the executive officer
speaks his answers and the crew its reports with a natural voice instead of
espeak-ng.  Standard library only for the transport (``urllib``), NumPy for
the decoding, like the game's other audio.

One daemon worker thread sends one request at a time; crew reports go
before the executive officer's longer answers.  The worker decodes the WAV
answer while it arrives and hands it on in short pieces resampled to the
mixer's rate, so a server that streams its audio is heard before it has
finished; the main loop only queues those pieces on the voice channel
(``src/core/game_voice.py``).  A slow
or dead server can never stall a frame, and the game without the service
(off, no key, offline) behaves exactly as before.  The API key travels only
in the ``Authorization`` header and never appears in errors, logs or repr.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass, field

import numpy as np

from src.core import https
from src.llm.client import clean_text, valid_model, valid_url

DEFAULT_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "onyx"
# The voices of the OpenAI preset (Left/Right cycles them; any other name
# can be typed for another server).
PRESET_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx",
                 "sage", "shimmer", "verse")
MAX_VOICE_LEN = 64
# Sampling of speech models that take it (Qwen-TTS and similar servers):
# lower temperature = calmer, steadier; lower top_p = fewer outliers; a
# fixed seed keeps the delivery alike across sentences (-1 = random: one
# seed drawn per launch, so the voice still stays alike from sentence to
# sentence within a session).
DEFAULT_TEMPERATURE = 0.9
DEFAULT_TOP_P = 1.0
DEFAULT_SEED = -1
TEMPERATURE_RANGE = (0.0, 2.0)
TOP_P_RANGE = (0.05, 1.0)
SEED_MAX = 2 ** 31 - 1
# OpenAI's own speech endpoint knows no sampling fields: never sent there.
_NO_SAMPLING_HOSTS = frozenset(("api.openai.com",))
MAX_INPUT_CHARS = 700
MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_AUDIO_S = 90.0
TIMEOUT_S = 30.0
QUEUE_MAX = 4
CACHE_CLIPS = 24
# In order of precedence: the crew's calls, the officer's answers, the
# settings' test sentence, then the stations' log entries read aloud.
ROLES = ("crew", "xo", "test", "log")
# A report older than this (wall seconds since it was asked for) is no
# longer worth saying: the crew's calls are tactical, the officer's
# answers keep a little longer.  Log entries are all read in order (the
# game hands them over two at a time), so theirs only guards a service
# that hangs.
STALE_S = {"crew": 20.0, "xo": 90.0, "test": 60.0, "log": 180.0}
# Roles whose full queue drops its oldest sentence instead of the new one.
_DROP_OLDEST = frozenset(("crew", "log"))
STATUSES = ("pending", "running", "streaming", "done", "failed", "dropped")
# Audio is handed to the main loop in pieces of about this length.
PIECE_S = 0.25
READ_BYTES = 16 * 1024
ERRORS = ("disabled", "network", "timeout", "auth", "rate_limit", "server", "bad_reply",
          "busy", "no_audio")

# How the voice should sound (models that take ``instructions``; a server
# that refuses the field is asked without it).  One style for every role:
# the crew's calls, the officer's answers and the log are one speaker, so
# voice and mood never jump from one sentence to the next.  The style is
# written in the language spoken: an English instruction pulls a model
# such as Qwen-TTS towards an English accent on German text.
_STYLE = {
    "de": ("Sprich wie ein ruhiger, erfahrener Marineoffizier, der über die Bordsprechanlage "
           "eines Kriegsschiffs meldet: gleichmäßig, klar und sachlich, immer dieselbe Stimme, "
           "dasselbe Tempo und derselbe Ton. Nie lachen, kichern, seufzen, flüstern oder "
           "Geräusche machen; keine Gefühlsschwankungen. Sprich nur Deutsch, reines Hochdeutsch "
           "mit deutscher Aussprache und ohne englischen Akzent, vom ersten bis zum letzten Wort."),
    "en": ("Speak as a calm, experienced naval officer reporting on a warship's internal net: "
           "steady, clear and neutral, the same voice, pace and tone throughout. Never laugh, "
           "chuckle, sigh, whisper or add sounds; no emotional changes. Speak English only, "
           "with native English pronunciation from the first word to the last."),
}
# The fixed language for servers that take a ``language`` field (Qwen-TTS
# and similar; without it they guess from the first words and the start of
# a sentence may come out in another language or accent).
_LANGUAGE_NAME = {"de": "German", "en": "English"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def valid_voice(voice) -> bool:
    return (type(voice) is str and 0 < len(voice) <= MAX_VOICE_LEN
            and voice == voice.strip() and _CONTROL.search(voice) is None)


def _number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def valid_temperature(value) -> bool:
    return _number(value) and TEMPERATURE_RANGE[0] <= value <= TEMPERATURE_RANGE[1]


def valid_top_p(value) -> bool:
    return _number(value) and TOP_P_RANGE[0] <= value <= TOP_P_RANGE[1]


def valid_seed(value) -> bool:
    return type(value) is int and -1 <= value <= SEED_MAX


_LINK = re.compile(r"\[([^\]\n]{1,200})\]\([^)\s]{1,500}\)")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_ACTION = re.compile(r"(?<![\w*])\*[^*\n]{1,60}\*(?![\w*])|\[[^\]\n]{0,60}\]")
_STAGE = re.compile(r"\((?:[^()\n]{0,40}?)(?:laugh|lach|chuckl|kicher|giggl|sigh|seufz|smil|"
                    r"läch|grins|grin|cough|hust|pause)[^()\n]{0,40}\)", re.IGNORECASE)
_LAUGH = re.compile(r"\b(?:(h[aei])\1+h?|lol|lmao|rofl|xd)\b!*", re.IGNORECASE)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
                    "\U0001F1E6-\U0001F1FF\uFE0E\uFE0F\u200D\u20E3]")
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


# A number, with an optional decimal part ("431", "0,9", "12.5").
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def spell_digits(text, digits, point: str) -> str:
    """Every number digit by digit, the way a watch speaks it: "431" becomes
    "vier drei eins" (``digits`` are the ten words, ``point`` the word for a
    decimal comma or point)."""
    if type(text) is not str:
        return ""

    def spell(match) -> str:
        words = [point if char in ".," else digits[int(char)] for char in match.group()]
        return " " + " ".join(words) + " "

    text = re.sub(r" {2,}", " ", _NUMBER.sub(spell, text))
    text = re.sub(r"([(\[]) ", r"\1", text)
    return re.sub(r" ([,.!?;:)\]])", r"\1", text).strip()


# Units and short forms the log writes, said in full ("12 kn" is "12
# Knoten"): ``words`` maps these names to the listener's language.
WORD_NAMES = ("knots", "nautical_miles", "metres_per_second", "metres", "kilometres",
              "seconds", "minutes", "hours", "hertz", "kilohertz", "decibels", "percent",
              "degrees", "arc_minutes", "north", "south", "east", "west", "bearing",
              "range", "about", "celsius", "fahrenheit", "minus", "plus", "plus_minus", "to",
              "times", "and", "at", "number", "equals")
_POSITION = re.compile(r"(\d+)\s?°\s?(\d+(?:[.,]\d+)?)\s?'\s?([NSEWO])(?![\w])")
_HEMISPHERE = {"N": "north", "S": "south", "E": "east", "O": "east", "W": "west"}
# After a number: unit -> word name (longest first, so "kHz" before "Hz").
_UNITS = (("m/s", "metres_per_second"), ("kHz", "kilohertz"), ("Hz", "hertz"),
          ("dB", "decibels"), ("kn", "knots"), ("kts", "knots"), ("sm", "nautical_miles"),
          ("NM", "nautical_miles"), ("nm", "nautical_miles"), ("km", "kilometres"),
          ("min", "minutes"), ("m", "metres"), ("s", "seconds"), ("h", "hours"))
_UNIT = re.compile(r"(\d)\s?(" + "|".join(re.escape(unit) for unit, _ in _UNITS)
                   + r")(?![\w/])")
_UNIT_WORD = dict(_UNITS)
_SHORT = {"Rtg": "bearing", "Brg": "bearing", "brg": "bearing", "Dst": "range"}
_SHORT_WORD = re.compile(r"(?<![\w])(" + "|".join(_SHORT) + r")\.?(?![\w])")


# Temperatures ("-2 °C"), signs, ranges ("0–360") and symbols a speech
# model would read out or stumble over at the start of a sentence.
_TEMPERATURE = re.compile(r"\s?°\s?([CF])(?![\w])")
_RANGE = re.compile(r"(\d)\s?[–—-]\s?(?=\d)")
_SIGN = re.compile(r"(?<![\w.,])[-−]\s?(?=\d)")
_COUNT = re.compile(r"(\d)\s?[x×](?=\s|$)")
_CLOCK = re.compile(r"(\d):(?=\d\d(?!\d))")
_SYMBOL_WORD = (("±", "plus_minus"), ("+", "plus"), ("×", "times"), ("&", "and"),
                ("@", "at"), ("#", "number"), ("=", "equals"), ("′", "arc_minutes"))
_PAUSE = re.compile(r"\s*(?:[|·•→←↑↓◀▶▲▼►◄›‹»«/\\]|\s[–—-]\s|[–—])\s*")
_DROP = re.compile(r"[„“”\"‚‘`\[\]{}<>_*^~]")
# All-capital words: short ones are spelled ("HQ" -> "H Q", "CIWS" ->
# "C I W S"), longer ones with vowels are said as words ("TORPEDO" ->
# "Torpedo", "NATO" -> "Nato").
_CAPITALS = re.compile(r"(?<![\w])[A-ZÄÖÜ]{2,}(?![\w])")
_VOWELS = frozenset("AEIOUYÄÖÜ")


def _capitals(match) -> str:
    word = match.group()
    vowels = sum(char in _VOWELS for char in word)
    if (len(word) >= 5 and vowels) or (len(word) == 4 and vowels >= 2):
        return word[0] + word[1:].lower()
    return " ".join(word)


def spoken_words(text, words) -> str:
    """Abbreviations said in full: units after a number, positions
    (54°21,4'N), degrees, percent, "Rtg"/"brg" and "~" (``words`` maps
    ``WORD_NAMES`` to the listener's words)."""
    if type(text) is not str:
        return ""

    def word(name):
        return f" {words.get(name, '')} "

    text = _POSITION.sub(lambda m: f"{m.group(1)}{word('degrees')}{m.group(2)}"
                         f"{word('arc_minutes')}{word(_HEMISPHERE[m.group(3)])}", text)
    text = _UNIT.sub(lambda m: m.group(1) + word(_UNIT_WORD[m.group(2)]), text)
    text = _TEMPERATURE.sub(lambda m: word("degrees") + word(
        "celsius" if m.group(1) == "C" else "fahrenheit"), text)
    text = re.sub(r"\s?°", lambda _m: word("degrees"), text)
    text = re.sub(r"\s?%", lambda _m: word("percent"), text)
    text = re.sub(r"~\s?", lambda _m: word("about"), text)
    text = _SHORT_WORD.sub(lambda m: word(_SHORT[m.group(1)]), text)
    text = _RANGE.sub(lambda m: m.group(1) + word("to"), text)
    text = _SIGN.sub(lambda _m: word("minus"), text)
    text = re.sub(r"(?<=[^\W\d_])-(?=\d)", " ", text)
    text = _CLOCK.sub(r"\1 ", text)
    text = _COUNT.sub(lambda m: m.group(1) + word("times"), text)
    for symbol, name in _SYMBOL_WORD:
        text = text.replace(symbol, word(name))
    text = _PAUSE.sub(", ", text)
    text = _DROP.sub(" ", text)
    text = re.sub(r"…|\.{3,}", ".", text)
    text = _CAPITALS.sub(_capitals, text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r" ([,.!?;:])", r"\1", text)
    # Pauses left next to other punctuation or at either end.
    text = re.sub(r",(?:\s*,)+", ",", text)
    text = re.sub(r",\s*([.!?;:])", r"\1", text)
    text = re.sub(r"([.!?;:])\s*,", r"\1", text)
    return text.strip(" ,")


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def sentence_chunks(text, first: int = 1, size: int = 240, limit: int = 4) -> list[str]:
    """Split an answer for faster speech: the first ``first`` sentence(s)
    alone, so the voice starts early, then pieces of whole sentences up to
    about ``size`` characters; at most ``limit`` pieces."""
    if type(text) is not str:
        return []
    sentences = [part for part in _SENTENCE_END.split(" ".join(text.split())) if part]
    chunks = [" ".join(sentences[:first])] if sentences else []
    for sentence in sentences[first:]:
        if len(chunks) < limit and (len(chunks) == 1 or len(chunks[-1]) + len(sentence) >= size):
            chunks.append(sentence)
        else:
            chunks[-1] = chunks[-1] + " " + sentence
    return [chunk for chunk in chunks if chunk]


def clean_for_speech(text) -> str:
    """Only what a person would say: no emojis, Markdown, links, laughter
    ("haha", "lol") or stage directions (*laughs*, (seufzt), [pause])."""
    if type(text) is not str:
        return ""
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(r"\2", text)
    text = _ACTION.sub(" ", text)
    text = _STAGE.sub(" ", text)
    text = _LAUGH.sub(" ", text)
    text = _EMOJI.sub("", text)
    text = _BULLET.sub("", text)
    text = clean_text(text, 8 * MAX_INPUT_CHARS)
    text = " ".join(text.split())
    # Punctuation left alone by a removed word.
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"[,;:]+(?=[,.!?;:])", "", text)
    text = re.sub(r"([.!?])[,;:]+", r"\1", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)|(?<=[!?])\.+", lambda m: "." if m.group() == ".." else "",
                  text)
    return re.sub(r"^[,.;:!?\s]+", "", text)


def speakable(text, limit: int = MAX_INPUT_CHARS, clean: bool = True) -> str:
    """One paragraph of text, cut at a sentence end when too long; with
    ``clean`` only the words (``clean_for_speech``)."""
    if clean:
        text = clean_for_speech(text)
    else:
        text = _CONTROL.sub(" ", text) if type(text) is str else ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end >= limit // 3 else cut.rstrip() + " …"


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    base_url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    voice: str = DEFAULT_VOICE
    api_key: str = field(default="", repr=False)
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    seed: int = DEFAULT_SEED
    clean: bool = True

    @property
    def usable(self) -> bool:
        return (self.enabled and valid_url(self.base_url) and valid_model(self.model)
                and valid_voice(self.voice) and valid_temperature(self.temperature)
                and valid_top_p(self.top_p) and valid_seed(self.seed))

    @property
    def sound(self) -> tuple:
        """Everything that changes how a sentence sounds (the cache key)."""
        return (self.base_url, self.model, self.voice, self.temperature, self.top_p,
                self.seed)


class VoiceRequest:
    """One sentence to say; the worker fills ``status``/``pcm``/``error``."""

    def __init__(self, role: str, text: str, language: str):
        self.role = role
        self.text = text
        self.language = language
        self.created = time.monotonic()
        self.status = "pending"
        self.pcm = None            # int16 mono at the mixer's rate, once done
        # Pieces of ``pcm`` ready to play, filled while the answer arrives.
        self.pieces: deque = deque()
        self._parts: list = []
        self.error = None
        self.latency_s = None
        self.cached = False
        self._done = threading.Event()

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed", "dropped")

    @property
    def ok(self) -> bool:
        return self.status == "done"

    @property
    def audible(self) -> bool:
        """Audio has arrived (complete or still streaming)."""
        return bool(self.pieces) or self.status == "streaming"

    def stale(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return now - self.created > STALE_S.get(self.role, 30.0)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until finished (tests and tools only, never the game loop)."""
        return self._done.wait(timeout)

    def _push(self, pcm: np.ndarray, started: float) -> None:
        if not len(pcm):
            return
        if self.latency_s is None:
            # Until the first sound: what the listener waits.
            self.latency_s = time.monotonic() - started
        self._parts.append(pcm)
        self.pieces.append(pcm)
        self.status = "streaming"

    def _finish(self, status: str, pcm=None, error=None) -> None:
        if pcm is not None and not self._parts:
            self.pieces.append(pcm)
        elif pcm is None and self._parts and status == "done":
            pcm = np.concatenate(self._parts)
        self.pcm = pcm
        self.error = error
        self.status = status
        self._done.set()


# -- decoding (worker thread) ---------------------------------------------------

def parse_wav(raw: bytes) -> tuple[np.ndarray, int]:
    """Mono float32 samples in -1..1 and the sample rate of a WAV file.

    Streaming servers write 0 or 0xFFFFFFFF as the data length: the rest of
    the file is then the data.  Raises ``ValueError`` on anything else than
    8/16/24-bit PCM or 32-bit float.
    """
    if len(raw) < 12 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    offset, fmt = 12, None
    while offset + 8 <= len(raw):
        chunk, size = raw[offset:offset + 4], struct.unpack_from("<I", raw, offset + 4)[0]
        body = offset + 8
        if chunk == b"fmt ":
            if size < 16 or body + 16 > len(raw):
                raise ValueError("short fmt chunk")
            tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", raw, body)
            if tag == 0xFFFE and size >= 26 and body + 26 <= len(raw):
                tag = struct.unpack_from("<H", raw, body + 24)[0]
            fmt = (tag, channels, rate, bits)
        elif chunk == b"data":
            if fmt is None:
                raise ValueError("data before fmt")
            end = len(raw) if size in (0, 0xFFFFFFFF) or body + size > len(raw) else body + size
            return _samples(raw[body:end], *fmt)
        offset = body + size + (size & 1)
    raise ValueError("no data chunk")


def _samples(data: bytes, tag: int, channels: int, rate: int, bits: int):
    if not 1 <= channels <= 8 or not 4_000 <= rate <= 192_000:
        raise ValueError("unsupported layout")
    if tag == 1 and bits == 16:
        values = np.frombuffer(data[:len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    elif tag == 1 and bits == 8:
        values = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif tag == 1 and bits == 24:
        raw = np.frombuffer(data[:len(data) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        joined = (raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8)
                  | (raw[:, 2].astype(np.int32) << 16))
        joined = np.where(joined & 0x800000, joined - 0x1000000, joined)
        values = joined.astype(np.float32) / 8388608.0
    elif tag == 3 and bits == 32:
        values = np.frombuffer(data[:len(data) // 4 * 4], dtype="<f4").astype(np.float32)
    else:
        raise ValueError("unsupported sample format")
    frames = len(values) // channels
    if frames == 0:
        raise ValueError("empty audio")
    if frames > MAX_AUDIO_S * rate:
        frames = int(MAX_AUDIO_S * rate)
    values = values[:frames * channels].reshape(frames, channels).mean(axis=1)
    return np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0), int(rate)


def to_pcm(samples: np.ndarray, rate: int, target_rate: int) -> np.ndarray:
    """Resample (linear) to the mixer's rate, level to a fixed peak, int16."""
    samples = np.asarray(samples, dtype=np.float32)
    if rate != target_rate and len(samples) > 1:
        count = max(1, int(round(len(samples) * target_rate / rate)))
        positions = np.linspace(0.0, len(samples) - 1, count, dtype=np.float64)
        samples = np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak > 1e-4:
        samples = samples * (0.85 / peak)
    # 8 ms fades: no click at the start and end of the clip.
    fade = min(len(samples) // 2, max(1, target_rate // 125))
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)


_FORMATS = {(1, 8): 1, (1, 16): 2, (1, 24): 3, (3, 32): 4}


class WavStream:
    """Decodes a WAV answer while it arrives: header first, then mono
    float32 samples per block (same formats and checks as ``parse_wav``)."""

    def __init__(self):
        self._head = b""
        self._rest = b""
        self.fmt = None            # (tag, channels, rate, bits)
        self.frames = 0

    @property
    def rate(self) -> int:
        return self.fmt[2] if self.fmt else 0

    def feed(self, data: bytes) -> np.ndarray:
        if self.fmt is None:
            self._head += data
            data = self._header()
            if self.fmt is None:
                return np.zeros(0, dtype=np.float32)
        data = self._rest + data
        tag, channels, rate, bits = self.fmt
        frame = _FORMATS[(tag, bits)] * channels
        usable = len(data) // frame * frame
        self._rest = data[usable:]
        if not usable:
            return np.zeros(0, dtype=np.float32)
        samples, _ = _samples(data[:usable], tag, channels, rate, bits)
        room = int(MAX_AUDIO_S * rate) - self.frames
        samples = samples[:max(0, room)]
        self.frames += len(samples)
        return samples

    def _header(self) -> bytes:
        raw = self._head
        if len(raw) >= 12 and (raw[:4] != b"RIFF" or raw[8:12] != b"WAVE"):
            raise ValueError("not a WAV file")
        if len(raw) > 64 * 1024:
            raise ValueError("no data chunk")
        offset, fmt = 12, None
        while offset + 8 <= len(raw):
            chunk, size = raw[offset:offset + 4], struct.unpack_from("<I", raw, offset + 4)[0]
            body = offset + 8
            if chunk == b"fmt ":
                if body + min(size, 40) > len(raw):
                    return b""
                if size < 16:
                    raise ValueError("short fmt chunk")
                tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", raw, body)
                if tag == 0xFFFE and size >= 26:
                    tag = struct.unpack_from("<H", raw, body + 24)[0]
                if ((tag, bits) not in _FORMATS or not 1 <= channels <= 8
                        or not 4_000 <= rate <= 192_000):
                    raise ValueError("unsupported sample format")
                fmt = (tag, channels, rate, bits)
            elif chunk == b"data":
                if fmt is None:
                    raise ValueError("data before fmt")
                self.fmt, self._head = fmt, b""
                return raw[body:]
            elif body + size > len(raw):
                return b""
            offset = body + size + (size & 1)
        return b""

    def close(self) -> None:
        if self.fmt is None or self.frames == 0:
            raise ValueError("empty audio")


class Resampler:
    """Linear resampling across blocks without a seam between them."""

    def __init__(self, rate: int, target_rate: int):
        self.step = float(rate) / float(target_rate)
        self.pos = 0.0             # next output position (source index)
        self.base = 0              # source index of the next block's first sample
        self.prev = None

    def feed(self, samples: np.ndarray) -> np.ndarray:
        if not len(samples):
            return np.zeros(0, dtype=np.float32)
        start = self.base
        if self.prev is not None:
            samples = np.concatenate(([self.prev], samples)).astype(np.float32)
            start -= 1
        end = start + len(samples) - 1
        self.base, self.prev = end + 1, float(samples[-1])
        if self.pos > end:
            return np.zeros(0, dtype=np.float32)
        count = int(math.floor((end - self.pos) / self.step)) + 1
        positions = self.pos + self.step * np.arange(count, dtype=np.float64)
        self.pos += count * self.step
        return np.interp(positions, start + np.arange(len(samples)),
                         samples).astype(np.float32)


def _int16(samples: np.ndarray) -> np.ndarray:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)


class VoiceService:
    """The game's single link to the speech service; safe from the main loop."""

    def __init__(self, config: VoiceConfig | None = None, *, opener=None,
                 timeout_s: float = TIMEOUT_S, rate: int = 22050,
                 queue_max: int = QUEUE_MAX):
        self._config = config or VoiceConfig()
        self._opener = opener or https.urlopen
        self._timeout = float(timeout_s)
        self._rate = int(rate)
        self._queue_max = int(queue_max)
        self._queues = {role: deque() for role in ROLES}
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._thread = None
        self._closed = False
        self.sent = 0
        self.answered = 0
        self.failed = 0
        self.last_error = None
        # Ask with a speaking style and sampling until a server refuses them.
        self._instructions = True
        self._sampling = True
        self._language = True
        # Seed -1 ("random"): drawn once per launch, never per sentence, so
        # the delivery does not jump (wall-side only, never the simulation).
        self._session_seed = secrets.randbelow(SEED_MAX) + 1

    # -- configuration -------------------------------------------------------

    @property
    def config(self) -> VoiceConfig:
        return self._config

    @property
    def rate(self) -> int:
        return self._rate

    def configure(self, config: VoiceConfig, rate: int | None = None) -> None:
        with self._lock:
            if (config.base_url, config.model) != (self._config.base_url, self._config.model):
                self._instructions = True
                self._sampling = True
                self._language = True
            if config.sound != self._config.sound:
                self._cache.clear()
            if rate is not None and int(rate) != self._rate:
                self._rate = int(rate)
                self._cache.clear()
            self._config = config

    @property
    def active(self) -> bool:
        """Switched on and configured (says nothing about reach)."""
        return self._config.usable and not self._closed

    # -- requests ------------------------------------------------------------

    def say(self, text, language: str, role: str = "xo"):
        """Queue one sentence; ``None`` when off, empty or the queue is full
        (a full crew or log queue drops its oldest report instead)."""
        if not self.active or role not in ROLES:
            return None
        text = speakable(text, clean=self._config.clean)
        if not text:
            return None
        request = VoiceRequest(role, text, language if language in _STYLE else "en")
        with self._lock:
            pending = self._queues[role]
            if len(pending) >= self._queue_max:
                if role not in _DROP_OLDEST:
                    return None
                pending.popleft()._finish("dropped", error="busy")
            pending.append(request)
            self._wake.notify()
        self._ensure_worker()
        return request

    def clear(self) -> None:
        """Drop every sentence not yet sent (a new mission, the main menu)."""
        with self._lock:
            for pending in self._queues.values():
                while pending:
                    pending.popleft()._finish("dropped", error="disabled")

    def close(self) -> None:
        self._closed = True
        self.clear()
        with self._lock:
            self._wake.notify_all()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="voice-client",
                                            daemon=True)
            self._thread.start()

    def _next(self):
        with self._lock:
            deadline = time.monotonic() + 5.0
            while not self._closed:
                for role in ROLES:
                    if self._queues[role]:
                        return self._queues[role].popleft()
                left = deadline - time.monotonic()
                if left <= 0:
                    self._thread = None
                    return None
                self._wake.wait(left)
            return None

    def _run(self) -> None:
        while not self._closed:
            request = self._next()
            if request is None:
                return
            config = self._config
            if not config.usable or self._closed:
                request._finish("dropped", error="disabled")
                continue
            if request.stale():
                request._finish("dropped", error="busy")
                continue
            request.status = "running"
            started = time.monotonic()
            key = (request.role, request.language, request.text)
            with self._lock:
                pcm = self._cache.get(key)
                if pcm is not None:
                    self._cache.move_to_end(key)
            if pcm is not None:
                request.cached = True
                request.latency_s = 0.0
                request._finish("done", pcm=pcm)
                continue
            self.sent += 1
            try:
                self._speak(config, request, started)
            except (_VoiceError, ValueError, MemoryError) as exc:
                category = exc.category if isinstance(exc, _VoiceError) else "bad_reply"
                self.failed += 1
                self.last_error = category
                if request._parts:
                    # Cut off midway: what arrived is still said.
                    request._finish("done")
                else:
                    request._finish("failed", error=category)
                continue
            if not request._parts:
                self.failed += 1
                self.last_error = "bad_reply"
                request._finish("failed", error="bad_reply")
                continue
            self.answered += 1
            self.last_error = None
            pcm = np.concatenate(request._parts)
            if request.role in _DROP_OLDEST:
                # Crew reports and log entries repeat ("action stations"): keep a few.
                with self._lock:
                    self._cache[key] = pcm
                    while len(self._cache) > CACHE_CLIPS:
                        self._cache.popitem(last=False)
            request._finish("done")

    def _speak(self, config: VoiceConfig, request: VoiceRequest, started: float) -> None:
        """Send one request and pass its audio on in pieces as it arrives."""
        state = {}
        piece = max(1, int(self._rate * PIECE_S))

        def block(data: bytes) -> None:
            if "wav" not in state:
                state.update(wav=WavStream(), out=[], size=0, first=True)
            wav = state["wav"]
            samples = wav.feed(data)
            if wav.fmt is None or not len(samples):
                return
            if "resample" not in state:
                state["resample"] = Resampler(wav.rate, self._rate)
            out = state["resample"].feed(samples)
            if state["first"] and len(out):
                # 8 ms fade-in: no click at the start.
                fade = min(len(out), max(1, self._rate // 125))
                out[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
                state["first"] = False
            state["out"].append(out)
            state["size"] += len(out)
            if state["size"] >= piece:
                self._hand_on(request, state, started)

        self._post(config, request, block)
        if "wav" not in state:
            raise ValueError("empty audio")
        state["wav"].close()
        self._hand_on(request, state, started)

    @staticmethod
    def _hand_on(request: VoiceRequest, state: dict, started: float) -> None:
        if state["out"]:
            request._push(_int16(np.concatenate(state["out"])), started)
            state["out"], state["size"] = [], 0

    # -- transport -----------------------------------------------------------

    def _post(self, config: VoiceConfig, request: VoiceRequest, sink) -> None:
        body = {"model": config.model, "input": request.text, "voice": config.voice,
                "response_format": "wav"}
        if self._instructions:
            body["instructions"] = _STYLE[request.language]
        sampling = self._sampling and _host(config.base_url) not in _NO_SAMPLING_HOSTS
        if sampling:
            body["temperature"] = float(config.temperature)
            body["top_p"] = float(config.top_p)
            body["seed"] = int(config.seed) if config.seed >= 0 else self._session_seed
        language = (self._language and _host(config.base_url) not in _NO_SAMPLING_HOSTS
                    and request.language in _LANGUAGE_NAME)
        if language:
            body["language"] = _LANGUAGE_NAME[request.language]
        url = config.base_url.rstrip("/") + "/audio/speech"
        headers = {"Content-Type": "application/json", "Accept": "audio/wav",
                   "User-Agent": "u-jagd"}
        if config.api_key:
            headers["Authorization"] = "Bearer " + config.api_key
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        http_request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._opener(http_request, timeout=self._timeout) as response:
                read = getattr(response, "read1", None) or response.read
                total = 0
                while True:
                    data = read(READ_BYTES)
                    if not data:
                        break
                    total += len(data)
                    if total > MAX_AUDIO_BYTES:
                        raise _VoiceError("bad_reply")
                    if self._closed:
                        raise _VoiceError("disabled")
                    sink(data)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _VoiceError("auth") from None
            if exc.code == 429:
                raise _VoiceError("rate_limit") from None
            if sampling and exc.code in (400, 422):
                # A server that does not know a field: first without sampling,
                # then without the fixed language, then without the style.
                self._sampling = False
                return self._post(config, request, sink)
            if language and exc.code in (400, 422):
                self._language = False
                return self._post(config, request, sink)
            if self._instructions and exc.code in (400, 422):
                self._instructions = False
                return self._post(config, request, sink)
            raise _VoiceError("server") from None
        except TimeoutError:
            raise _VoiceError("timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise _VoiceError("timeout") from None
            raise _VoiceError("network") from None
        except OSError:
            raise _VoiceError("network") from None


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class _VoiceError(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category
