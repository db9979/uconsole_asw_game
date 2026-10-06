"""Non-blocking client for an OpenAI-compatible ``/audio/transcriptions`` endpoint.

The optional speech input of the language-model add-on: the player holds
the talk key (``Ctrl+Space``) at any station, speaks a question, and the
recording is turned into text here before the executive officer answers it
(``src/core/game_talk.py``).  Standard library only for the transport
(``urllib``), NumPy only to write the 16-bit WAV, like the game's other audio.

One daemon worker thread sends one recording at a time from a small bounded
queue; the main loop only submits and later reads finished results, so a
slow or dead server can never stall a frame.  Nothing is stored: the audio
lives only in memory until the request ends.  The API key travels only in
the ``Authorization`` header and never appears in errors, logs or repr.
"""

from __future__ import annotations

import io
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import wave
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from src.core import https
from src.llm.client import clean_text, valid_model, valid_url

DEFAULT_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "whisper-1"
SAMPLE_RATE = 16000
# A question is short: longer recordings are cut here (the key held down
# by mistake never sends minutes of audio).
MAX_AUDIO_S = 30.0
MIN_AUDIO_S = 0.3
# Below this peak level the recording is taken as silence and not sent.
SILENCE_PEAK = 0.004
MAX_TEXT = 300
MAX_RESPONSE_BYTES = 64 * 1024
TIMEOUT_S = 30.0
QUEUE_MAX = 4
STATUSES = ("pending", "running", "done", "failed", "dropped")
# Error categories shown to the player (never a raw server message).
ERRORS = ("disabled", "network", "timeout", "auth", "rate_limit", "server", "bad_reply",
          "busy", "too_short", "no_speech")
# ISO 639-1 codes of the game's languages (the field OpenAI's API takes).
_LANGUAGE = {"de": "de", "en": "en"}
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SttConfig:
    enabled: bool = False
    base_url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    api_key: str = field(default="", repr=False)

    @property
    def usable(self) -> bool:
        return self.enabled and valid_url(self.base_url) and valid_model(self.model)


def as_samples(samples) -> np.ndarray:
    """Mono float32 samples in -1..1 (anything else becomes an empty array)."""
    array = np.asarray(samples, dtype=np.float32).reshape(-1)
    if not array.size or not np.all(np.isfinite(array)):
        return np.zeros(0, dtype=np.float32)
    return np.clip(array, -1.0, 1.0)


def check_audio(samples, rate: int = SAMPLE_RATE) -> str | None:
    """Why a recording is not worth sending ("too_short", "no_speech"), or None."""
    samples = as_samples(samples)
    if samples.size < MIN_AUDIO_S * rate:
        return "too_short"
    if float(np.max(np.abs(samples))) < SILENCE_PEAK:
        return "no_speech"
    return None


def wav_bytes(samples, rate: int = SAMPLE_RATE) -> bytes:
    """16-bit mono PCM WAV of at most ``MAX_AUDIO_S`` seconds."""
    samples = as_samples(samples)[:int(MAX_AUDIO_S * rate)]
    pcm = np.round(samples * 32767.0).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(pcm.tobytes())
    return buffer.getvalue()


def multipart(fields: dict, file_name: str, data: bytes,
              content_type: str = "audio/wav") -> tuple[bytes, str]:
    """``multipart/form-data`` body with text ``fields`` and one file."""
    boundary = "u-jagd-" + secrets.token_hex(12)
    parts = []
    for name, value in fields.items():
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                      f"{value}\r\n").encode("utf-8"))
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                  f"filename=\"{file_name}\"\r\nContent-Type: {content_type}\r\n\r\n")
                 .encode("utf-8"))
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def clean_transcript(text) -> str:
    """One plain line of at most ``MAX_TEXT`` characters (cut at a word)."""
    text = _SPACE.sub(" ", clean_text(text if type(text) is str else "", 2_000)).strip()
    text = "".join(char for char in text if char.isprintable())
    if len(text) > MAX_TEXT:
        cut = text[:MAX_TEXT - 1]
        space = cut.rfind(" ")
        text = (cut[:space] if space > MAX_TEXT // 2 else cut).rstrip() + "…"
    return text


class SttRequest:
    """One recording to transcribe; the worker fills ``status``/``text``/``error``."""

    def __init__(self, wav: bytes, language: str, tag: str):
        self.wav = wav
        self.language = language
        self.tag = tag
        self.status = "pending"
        self.text = ""
        self.error = None
        self.latency_s = None
        self._done = threading.Event()

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed", "dropped")

    @property
    def ok(self) -> bool:
        return self.status == "done"

    def wait(self, timeout: float | None = None) -> bool:
        """Block until finished (tests and tools only, never the game loop)."""
        return self._done.wait(timeout)

    def _finish(self, status: str, text: str = "", error=None) -> None:
        self.wav = b""          # the audio is not kept once it was sent
        self.text = text
        self.error = error
        self.status = status
        self._done.set()


class SttService:
    """The game's single link to the transcription service; safe from the main loop."""

    def __init__(self, config: SttConfig | None = None, *, opener=None,
                 timeout_s: float = TIMEOUT_S, queue_max: int = QUEUE_MAX):
        self._config = config or SttConfig()
        self._opener = opener or https.urlopen
        self._timeout = float(timeout_s)
        self._queue_max = int(queue_max)
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._thread = None
        self._closed = False
        # Ask with the game's language and a JSON answer until a server
        # refuses the fields.
        self._language = True
        self._json = True
        self.sent = 0
        self.answered = 0
        self.failed = 0
        self.last_error = None

    @property
    def config(self) -> SttConfig:
        return self._config

    def configure(self, config: SttConfig) -> None:
        with self._lock:
            if (config.base_url, config.model) != (self._config.base_url, self._config.model):
                self._language = True
                self._json = True
            self._config = config

    @property
    def active(self) -> bool:
        """Switched on and configured (says nothing about reach)."""
        return self._config.usable and not self._closed

    def transcribe(self, samples, language: str, *, rate: int = SAMPLE_RATE,
                   tag: str = "local", check: bool = True):
        """Queue one recording; the request, or None when off or full.  A
        recording too short or silent finishes at once with that error."""
        if not self.active:
            return None
        why = check_audio(samples, rate) if check else None
        request = SttRequest(b"" if why else wav_bytes(samples, rate),
                             _LANGUAGE.get(language, "en"), tag)
        if why:
            request._finish("failed", error=why)
            return request
        with self._lock:
            if len(self._queue) >= self._queue_max:
                return None
            self._queue.append(request)
            self._wake.notify()
        self._ensure_worker()
        return request

    def clear(self) -> None:
        with self._lock:
            while self._queue:
                self._queue.popleft()._finish("dropped", error="disabled")

    def close(self) -> None:
        self._closed = True
        self.clear()
        with self._lock:
            self._wake.notify_all()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="stt-client", daemon=True)
            self._thread.start()

    def _next(self):
        with self._lock:
            deadline = time.monotonic() + 5.0
            while not self._closed:
                if self._queue:
                    return self._queue.popleft()
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
            request.status = "running"
            started = time.monotonic()
            self.sent += 1
            try:
                text = self._post(config, request)
            except _SttError as exc:
                self.failed += 1
                self.last_error = exc.category
                request._finish("failed", error=exc.category)
                continue
            request.latency_s = time.monotonic() - started
            self.answered += 1
            self.last_error = None
            request._finish("done", text=text)

    # -- transport -----------------------------------------------------------

    def _post(self, config: SttConfig, request: SttRequest) -> str:
        fields = {"model": config.model}
        if self._json:
            fields["response_format"] = "json"
        if self._language:
            fields["language"] = request.language
        body, content_type = multipart(fields, "speech.wav", request.wav)
        url = config.base_url.rstrip("/") + "/audio/transcriptions"
        headers = {"Content-Type": content_type, "Accept": "application/json, text/plain",
                   "User-Agent": "u-jagd"}
        if config.api_key:
            headers["Authorization"] = "Bearer " + config.api_key
        http_request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with self._opener(http_request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _SttError("auth") from None
            if exc.code == 429:
                raise _SttError("rate_limit") from None
            if exc.code in (400, 422) and self._language:
                # A server that does not know a field: first without the
                # language, then without the answer format.
                self._language = False
                return self._post(config, request)
            if exc.code in (400, 422) and self._json:
                self._json = False
                return self._post(config, request)
            raise _SttError("server") from None
        except TimeoutError:
            raise _SttError("timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise _SttError("timeout") from None
            raise _SttError("network") from None
        except (OSError, ValueError):
            raise _SttError("network") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise _SttError("bad_reply")
        try:
            decoded = raw.decode("utf-8")
        except UnicodeError:
            raise _SttError("bad_reply") from None
        text = decoded
        if decoded.lstrip().startswith("{"):
            try:
                payload = json.loads(decoded)
                text = payload["text"]
            except (ValueError, KeyError, TypeError):
                raise _SttError("bad_reply") from None
            if type(text) is not str:
                raise _SttError("bad_reply")
        return clean_transcript(text)


class _SttError(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category
