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
import time


class WebHostAuth:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.setup_code = secrets.token_urlsafe(24)
        self.setup_deadline = time.monotonic() + 900
        self.failures: list[float] = []
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

    def _allowed(self):
        now = time.monotonic()
        self.failures = [value for value in self.failures if now - value < 60]
        return len(self.failures) < 5

    def _failure(self):
        self.failures.append(time.monotonic())

    def setup(self, code: str, password: str):
        if self.configured or not self._allowed():
            return False
        if (time.monotonic() > self.setup_deadline or type(code) is not str
                or not hmac.compare_digest(code, self.setup_code)):
            self._failure()
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

    def verify(self, password: str):
        if not self.configured or not self._allowed():
            return False
        if type(password) is not str or len(password) > 256:
            self._failure()
            return False
        digest = hashlib.scrypt(password.encode("utf-8"),
                                salt=bytes.fromhex(self.record["salt"]),
                                n=2**14, r=8, p=1, dklen=64)
        ok = hmac.compare_digest(digest, bytes.fromhex(self.record["hash"]))
        if not ok:
            self._failure()
        return ok

    def reset_local(self):
        """Explicit terminal-only reset for the next web setup flow."""
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("symlinked web host credential path")
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
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
