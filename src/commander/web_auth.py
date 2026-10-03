"""Persistent web-host password and one-time local setup secret."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import threading
import time
from collections import deque


class FailureLimiter:
    """Failed attempts per source address in a sliding window, bounded.

    One stranger's failures never lock out another address. The table holds at
    most ``max_sources`` addresses; while it is full a source that is not in it
    yet is refused (fail closed) until entries age out of the window, so many
    addresses cannot wash out the record of one. Thread-safe on its own lock.
    """

    def __init__(self, limit=5, window_s=60.0, max_sources=256):
        self.limit = limit
        self.window_s = window_s
        self.max_sources = max_sources
        self._lock = threading.Lock()
        self._failures: dict[str, deque] = {}

    def _prune(self, now):
        for source in tuple(self._failures):
            times = self._failures[source]
            while times and now - times[0] >= self.window_s:
                times.popleft()
            if not times:
                del self._failures[source]

    def allowed(self, source: str) -> bool:
        with self._lock:
            self._prune(time.monotonic())
            times = self._failures.get(source)
            if times is None:
                return len(self._failures) < self.max_sources
            return len(times) < self.limit

    def record(self, source: str) -> int:
        """Count one failure; returns that source's failures in the window."""
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            times = self._failures.get(source)
            if times is None:
                if len(self._failures) >= self.max_sources:
                    return self.limit
                times = self._failures[source] = deque(maxlen=self.limit)
            times.append(now)
            return len(times)

    def clear(self):
        with self._lock:
            self._failures.clear()

    def __len__(self):
        with self._lock:
            return len(self._failures)


class WebHostAuth:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.setup_code = secrets.token_urlsafe(24)
        self.setup_deadline = time.monotonic() + 900
        # Failed setup/login attempts per source address (routes._source_address).
        self.failures = FailureLimiter()
        # Guards the record and the setup secret. A login's slow scrypt runs
        # outside it and always outside the server's global lock.
        self._lock = threading.Lock()
        self.record = self._read()

    def _read(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("symlinked web host credential path")
        if self.path.exists() and stat.S_IMODE(self.path.stat().st_mode) & 0o077:
            raise ValueError("web host credential file is accessible by other users")
        try:
            with self.path.open("r", encoding="ascii") as stream:
                record = json.load(stream)
        except FileNotFoundError:
            return None
        if (type(record) is not dict or set(record) != {"version", "salt", "hash"}
                or record["version"] != 1 or type(record["salt"]) is not str
                or type(record["hash"]) is not str or len(record["salt"]) != 32
                or len(record["hash"]) != 128):
            raise ValueError("invalid web host credential file")
        bytes.fromhex(record["salt"])
        bytes.fromhex(record["hash"])
        return record

    @property
    def configured(self):
        return self.record is not None

    def setup(self, code: str, password: str, source: str = ""):
        if self.configured or not self.failures.allowed(source):
            return False
        # One-time flow: the auth lock (never the server lock) makes the
        # check-and-set atomic against a second concurrent setup.
        with self._lock:
            if self.record is not None:
                return False
            if (time.monotonic() > self.setup_deadline or type(code) is not str
                    or not self.setup_code
                    or not hmac.compare_digest(code, self.setup_code)):
                self.failures.record(source)
                return False
            if type(password) is not str or not 12 <= len(password) <= 256:
                return False
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                    n=2**14, r=8, p=1, dklen=64)
            record = {"version": 1, "salt": salt.hex(), "hash": digest.hex()}
            self._write(record)
            self.record = record
            self.setup_code = ""
            return True

    def verify(self, password: str, source: str = ""):
        with self._lock:
            record = self.record
        if record is None or not self.failures.allowed(source):
            return False
        if type(password) is not str or len(password) > 256:
            self.failures.record(source)
            return False
        digest = hashlib.scrypt(password.encode("utf-8"),
                                salt=bytes.fromhex(record["salt"]),
                                n=2**14, r=8, p=1, dklen=64)
        ok = hmac.compare_digest(digest, bytes.fromhex(record["hash"]))
        if not ok:
            self.failures.record(source)
        return ok

    def reset_local(self):
        """Explicit terminal-only reset for the next web setup flow."""
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("symlinked web host credential path")
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        with self._lock:
            self.record = None
            self.setup_code = secrets.token_urlsafe(24)
            self.setup_deadline = time.monotonic() + 900
        self.failures.clear()

    def _write(self, record):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise ValueError("symlinked web host credential path")
        fd, temporary = tempfile.mkstemp(prefix=".web-host.", suffix=".tmp",
                                         dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                json.dump(record, stream, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
