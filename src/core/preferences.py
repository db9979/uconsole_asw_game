"""Persistent user preferences with atomic, corruption-safe storage."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from src.core.config import BOTTOM_PANEL_MODES, FPS_CHOICES, FPS_DEFAULT
from src.core.i18n import SUPPORTED_LANGUAGES, detect_system_language

_MAX_CREDENTIAL_LEN = 256


@dataclass(frozen=True, slots=True)
class Preferences:
    language: str = field(default_factory=detect_system_language)
    fullscreen: bool = True
    audio: bool = True
    large_text: bool = False
    tooltips: bool = True
    simlog: bool = False
    night_mode: bool = False
    high_contrast: bool = False
    # Anti-aliased chart and plot lines (pygame.gfxdraw); off by default
    # until the uConsole frame-time cost is measured (plan 1.3, phase 10).
    aa_lines: bool = False
    # Spoken crew reports through an installed espeak-ng (silent without).
    speech: bool = False
    # Frame-rate cap from FPS_CHOICES; the default 30 saves uConsole CPU.
    frame_rate: int = FPS_DEFAULT
    # Event feed + telemetry: "ticker" (one status strip, full feed on F11)
    # frees station space on the 1280x720 uConsole; "docked" is the 180 px band.
    bottom_panel: str = "ticker"
    # Operator assistance: "off" = raw data and manual tools only (default);
    # "training" adds automatic peak labels, blade-rate/catalog ranking and
    # ESM emitter candidates. Display only, never simulation state.
    operator_assist: str = "off"
    live_ais_enabled: bool = False
    live_adsb_enabled: bool = False
    aisstream_api_key: str = ""
    opensky_credentials: str = ""
    # First-launch welcome page ("What do you want to play?") already shown.
    # True by default: only a launch without any settings.json shows it;
    # settings files written before the field existed count as onboarded.
    onboarded: bool = True

    @classmethod
    def defaults(cls) -> "Preferences":
        return cls()


def default_preferences_path() -> Path:
    return Path.home() / ".u-jagd" / "settings.json"


def load_preferences(path: str | os.PathLike[str] | None = None) -> Preferences:
    """Load preferences, returning safe defaults for absent or corrupt files.

    Only an absent file marks a first launch (``onboarded`` False); a corrupt
    or unreadable one keeps the default, so the welcome page is not repeated.
    """
    defaults = Preferences.defaults()
    target = Path(path).expanduser() if path is not None else default_preferences_path()
    try:
        with target.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return replace(defaults, onboarded=False)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults

    language = payload.get("language", defaults.language)
    if language not in SUPPORTED_LANGUAGES:
        language = defaults.language
    values: dict[str, object] = {"language": language}
    for name in ("fullscreen", "audio", "large_text", "tooltips", "simlog",
                 "night_mode", "high_contrast", "aa_lines", "speech", "live_ais_enabled",
                 "live_adsb_enabled", "onboarded"):
        value = payload.get(name, getattr(defaults, name))
        values[name] = value if isinstance(value, bool) else getattr(defaults, name)
    frame_rate = payload.get("frame_rate", defaults.frame_rate)
    values["frame_rate"] = (frame_rate if type(frame_rate) is int
                            and frame_rate in FPS_CHOICES else defaults.frame_rate)
    bottom_panel = payload.get("bottom_panel", defaults.bottom_panel)
    values["bottom_panel"] = (bottom_panel if bottom_panel in BOTTOM_PANEL_MODES
                              else defaults.bottom_panel)
    assist = payload.get("operator_assist", defaults.operator_assist)
    values["operator_assist"] = (assist if assist in ("off", "training")
                                 else defaults.operator_assist)
    for name in ("aisstream_api_key", "opensky_credentials"):
        value = payload.get(name, getattr(defaults, name))
        values[name] = value.strip()[:_MAX_CREDENTIAL_LEN] \
            if isinstance(value, str) else getattr(defaults, name)
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
