"""Where the language model's API key lives: never in ``settings.json``.

The key comes from the environment variable ``U_JAGD_LLM_KEY`` or from the
file ``~/.u-jagd/llm_key`` (owner read/write only); the speech service's key
likewise from ``U_JAGD_TTS_KEY`` or ``~/.u-jagd/tts_key``, and the speech
input's from ``U_JAGD_STT_KEY`` or ``~/.u-jagd/stt_key``.  It never enters a save,
the settings, a log, a bug report or a browser.  A server in the LAN usually
needs no key at all.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from src.core import config

ENV_NAME = "U_JAGD_LLM_KEY"
FILE_NAME = "llm_key"
# The speech service's own key (``src/llm/voice.py``), kept the same way.
VOICE_ENV_NAME = "U_JAGD_TTS_KEY"
VOICE_FILE_NAME = "tts_key"
# The speech input's own key (``src/llm/stt.py``).
STT_ENV_NAME = "U_JAGD_STT_KEY"
STT_FILE_NAME = "stt_key"
MAX_KEY_LEN = 512


def key_path(file_name: str = FILE_NAME) -> Path:
    return Path(config.SAVE_DIR).expanduser() / file_name


def _clean(value) -> str:
    if type(value) is not str:
        return ""
    value = value.strip()
    if not value or len(value) > MAX_KEY_LEN or any(ord(c) < 33 or ord(c) == 127 for c in value):
        return ""
    return value


def load_key(env_name: str = ENV_NAME, file_name: str = FILE_NAME) -> str:
    """The key from the environment, else from the key file, else ``""``."""
    env = _clean(os.environ.get(env_name, ""))
    if env:
        return env
    path = key_path(file_name)
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        if path.stat().st_size > MAX_KEY_LEN + 2:
            return ""
        return _clean(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return ""


def key_from_env(env_name: str = ENV_NAME) -> bool:
    return bool(_clean(os.environ.get(env_name, "")))


def save_key(value: str, file_name: str = FILE_NAME) -> bool:
    """Store (or with an empty value remove) the key file; atomic, mode 0600."""
    path = key_path(file_name)
    value = _clean(value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.is_symlink():
            return False
        if not value:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return True
        fd, temporary = tempfile.mkstemp(prefix=f".{file_name}.", suffix=".tmp",
                                         dir=path.parent)
        try:
            os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


def mask(value: str) -> str:
    """How a key is shown: only that one is set and its last characters."""
    value = _clean(value)
    if not value:
        return "-"
    return "..." + value[-4:] if len(value) > 8 else "*" * len(value)
