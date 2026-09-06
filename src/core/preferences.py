"""Persistent user preferences with atomic, corruption-safe storage."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from src.core.i18n import SUPPORTED_LANGUAGES, detect_system_language


@dataclass(frozen=True, slots=True)
class Preferences:
    language: str = field(default_factory=detect_system_language)
    fullscreen: bool = True
    audio: bool = True
    large_text: bool = False

    @classmethod
    def defaults(cls) -> "Preferences":
        return cls()


def default_preferences_path() -> Path:
    return Path.home() / ".u-jagd" / "settings.json"


def load_preferences(path: str | os.PathLike[str] | None = None) -> Preferences:
    """Load preferences, returning safe defaults for absent or corrupt files."""
    defaults = Preferences.defaults()
    target = Path(path).expanduser() if path is not None else default_preferences_path()
    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults

    language = payload.get("language", defaults.language)
    if language not in SUPPORTED_LANGUAGES:
        language = defaults.language
    values: dict[str, object] = {"language": language}
    for name in ("fullscreen", "audio", "large_text"):
        value = payload.get(name, getattr(defaults, name))
        values[name] = value if isinstance(value, bool) else getattr(defaults, name)
    return replace(defaults, **values)


def save_preferences(preferences: Preferences,
                     path: str | os.PathLike[str] | None = None) -> Path:
    """Atomically persist preferences and return the destination path."""
    if not isinstance(preferences, Preferences):
        raise TypeError("preferences must be a Preferences instance")
    target = Path(path).expanduser() if path is not None else default_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(asdict(preferences), handle, ensure_ascii=True,
                      indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return target
