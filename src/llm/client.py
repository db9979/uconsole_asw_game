"""Non-blocking client for an OpenAI-compatible ``/chat/completions`` endpoint.

The server may be a cloud service or a local one in the LAN (Ollama,
LM Studio, llama.cpp, vLLM ...); only the base URL differs.  Standard
library only (``urllib``), like the other network clients of the game.

One daemon worker thread sends one request at a time from a small bounded
queue; the game's main loop only submits and later reads finished results,
so a slow or dead server can never stall a frame.  A full queue drops the
new request (the caller keeps its built-in text).  The API key travels only
in the ``Authorization`` header and never appears in errors, logs or repr.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

DEFAULT_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:7b"
MAX_URL_LEN = 256
MAX_MODEL_LEN = 96
QUEUE_MAX = 8
TIMEOUT_S = 45.0
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TEXT_CHARS = 4_000
MAX_PROMPT_CHARS = 24_000
STATUSES = ("pending", "running", "done", "failed", "dropped")
# Error categories shown to the player (never a raw server message).
ERRORS = ("disabled", "bad_url", "network", "timeout", "auth", "rate_limit",
          "server", "bad_reply", "busy")

_THINK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def valid_url(url) -> bool:
    """An absolute http(s) base URL without credentials or fragments."""
    if type(url) is not str or not 0 < len(url) <= MAX_URL_LEN or url != url.strip():
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        parts.port  # raises on a malformed port
    except ValueError:
        return False
    return (parts.scheme in ("http", "https") and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and not parts.fragment and not parts.query)


def valid_model(model) -> bool:
    return (type(model) is str and 0 < len(model) <= MAX_MODEL_LEN
            and model == model.strip() and _CONTROL.search(model) is None)


def clean_text(text, limit: int = MAX_TEXT_CHARS) -> str:
    """Plain, bounded text: no reasoning block, no control characters, no
    Markdown emphasis; at most ``limit`` characters."""
    if type(text) is not str:
        return ""
    text = _THINK.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = _CONTROL.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    lines = [re.sub(r"^#+\s*", "", line).rstrip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    base_url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    api_key: str = field(default="", repr=False)

    @property
    def usable(self) -> bool:
        return self.enabled and valid_url(self.base_url) and valid_model(self.model)


class LlmRequest:
    """One chat request; the worker fills ``status``/``text``/``error``."""

    def __init__(self, purpose: str, messages: list, *, max_tokens: int,
                 temperature: float, json_mode: bool):
        self.purpose = purpose
        self.messages = messages
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.json_mode = json_mode
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
        self.text = text
        self.error = error
        self.status = status
        self._done.set()


def _bounded_messages(messages) -> list:
    """Copy of the chat messages with the prompt bounded in size."""
    out, budget = [], MAX_PROMPT_CHARS
    for row in messages:
        content = str(row.get("content", ""))[:budget]
        budget -= len(content)
        out.append({"role": row.get("role", "user"), "content": content})
    return out


class LlmService:
    """The game's single link to the model; safe to call from the main loop."""

    def __init__(self, config: LlmConfig | None = None, *, opener=None,
                 timeout_s: float = TIMEOUT_S, queue_max: int = QUEUE_MAX):
        self._config = config or LlmConfig()
        self._opener = opener or urllib.request.urlopen
        self._timeout = float(timeout_s)
        self._queue: queue.Queue = queue.Queue(maxsize=queue_max)
        self._lock = threading.Lock()
        self._thread = None
        self._closed = False
        self.sent = 0
        self.answered = 0
        self.failed = 0
        self.last_error = None
        self.last_latency_s = None

    # -- configuration -------------------------------------------------------

    @property
    def config(self) -> LlmConfig:
        return self._config

    def configure(self, config: LlmConfig) -> None:
        with self._lock:
            self._config = config

    @property
    def active(self) -> bool:
        """The link is switched on and configured (says nothing about reach)."""
        return self._config.usable and not self._closed

    @property
    def busy(self) -> bool:
        return not self._queue.empty()

    # -- requests ------------------------------------------------------------

    def submit(self, purpose: str, messages: list, *, max_tokens: int = 300,
               temperature: float = 0.6, json_mode: bool = False):
        """Queue one request; ``None`` when the link is off or the queue is full."""
        if not self.active:
            return None
        request = LlmRequest(purpose, _bounded_messages(messages),
                             max_tokens=int(max_tokens), temperature=float(temperature),
                             json_mode=bool(json_mode))
        try:
            self._queue.put_nowait(request)
        except queue.Full:
            return None
        self._ensure_worker()
        return request

    def close(self) -> None:
        self._closed = True
        while True:
            try:
                self._queue.get_nowait()._finish("dropped", error="disabled")
            except queue.Empty:
                break

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="llm-client",
                                            daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while not self._closed:
            try:
                request = self._queue.get(timeout=5.0)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._thread = None
                        return
                continue
            config = self._config
            if not config.usable or self._closed:
                request._finish("dropped", error="disabled")
                continue
            request.status = "running"
            started = time.monotonic()
            self.sent += 1
            try:
                text = self._post(config, request)
            except _LlmError as exc:
                self.failed += 1
                self.last_error = exc.category
                request._finish("failed", error=exc.category)
                continue
            request.latency_s = time.monotonic() - started
            self.last_latency_s = request.latency_s
            self.answered += 1
            self.last_error = None
            request._finish("done", text=text)

    # -- transport -----------------------------------------------------------

    def _post(self, config: LlmConfig, request: LlmRequest) -> str:
        body = {
            "model": config.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        url = config.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "u-jagd"}
        if config.api_key:
            headers["Authorization"] = "Bearer " + config.api_key
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        http_request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._opener(http_request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise _LlmError("auth") from None
            if exc.code == 429:
                raise _LlmError("rate_limit") from None
            if request.json_mode and exc.code == 400:
                # Some servers do not know response_format: ask once without.
                request.json_mode = False
                return self._post(config, request)
            raise _LlmError("server") from None
        except TimeoutError:
            raise _LlmError("timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise _LlmError("timeout") from None
            raise _LlmError("network") from None
        except (OSError, ValueError):
            raise _LlmError("network") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise _LlmError("bad_reply")
        try:
            payload = json.loads(raw.decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except (UnicodeError, ValueError, KeyError, IndexError, TypeError):
            raise _LlmError("bad_reply") from None
        text = clean_text(content)
        if not text:
            raise _LlmError("bad_reply")
        return text


class _LlmError(Exception):
    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def parse_json_object(text: str):
    """The first JSON object in a model answer (models like to wrap it)."""
    if type(text) is not str:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
