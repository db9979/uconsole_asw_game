"""Persistent user preferences with atomic, corruption-safe storage."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from src.core.config import BOTTOM_PANEL_MODES, FPS_CHOICES, FPS_DEFAULT, LEVELS
from src.core.i18n import SUPPORTED_LANGUAGES, detect_system_language
from src.core import opz_display
from src.llm.client import (DEFAULT_MODEL as LLM_DEFAULT_MODEL,
                            DEFAULT_URL as LLM_DEFAULT_URL, valid_model, valid_url)

_MAX_CREDENTIAL_LEN = 256
GRAPHICS_LEVELS = ("low", "normal", "full")
LLM_COACH_LEVELS = ("off", "rare", "often")
THEME_CHOICES = ("night", "day")


def _default_graphics() -> str:
    import sys
    return "full" if sys.platform == "win32" else "normal"


@dataclass(frozen=True, slots=True)
class Preferences:
    language: str = field(default_factory=detect_system_language)
    fullscreen: bool = True
    audio: bool = True
    large_text: bool = False
    tooltips: bool = True
    simlog: bool = False
    night_mode: bool = False
    # Red light by itself at night and on an alarm (night_mode keeps it on).
    red_light_auto: bool = True
    high_contrast: bool = False
    # Colour theme (``src/ui/theme.py``): "night" (Tactical Night, default)
    # or "day" (Tactical Day); high_contrast above overrides both.
    theme: str = "night"
    # Graphics level (src/ui/quality.py): "low", "normal" (uConsole default)
    # or "full" (Windows default, adds anti-aliased chart lines).
    graphics: str = field(default_factory=lambda: _default_graphics())
    # Legacy switch of the anti-aliased lines, kept in step with "full" so an
    # older build reading this file sees the same choice (also by default:
    # on Windows a fresh "full" reloads as aa_lines True).
    aa_lines: bool = field(default_factory=lambda: _default_graphics() == "full")
    # Spoken crew reports through an installed espeak-ng (silent without).
    speech: bool = False
    # Noise discipline: the uConsole's own microphone (level only, opt-in).
    microphone: bool = False
    # Frame-rate cap from FPS_CHOICES; the default 30 saves uConsole CPU.
    frame_rate: int = FPS_DEFAULT
    # Event feed + telemetry: "ticker" (one status strip, full feed on F11)
    # frees station space on the 1280x720 uConsole; "docked" is the 180 px band.
    bottom_panel: str = "ticker"
    # Operator assistance: "off" = raw data and manual tools only (default);
    # "training" adds automatic peak labels, blade-rate/catalog ranking and
    # ESM emitter candidates. Display only, never simulation state.
    operator_assist: str = "off"
    # Realism level of the next mission (``config.LEVELS``): Beginner turns
    # the assistance on and softens the computer opponent, Realistic turns
    # it off and sharpens the opponent; the score is scaled to match.
    level: str = "standard"
    live_ais_enabled: bool = False
    live_adsb_enabled: bool = False
    aisstream_api_key: str = ""
    opensky_credentials: str = ""
    # Optional language model (OpenAI-compatible chat endpoint, cloud or a
    # server in the LAN). Off by default; the API key is never stored here
    # (``src/llm/keystore.py``). Radio wording, coach and the experimental
    # opponent advisor are its sub-switches.
    llm_enabled: bool = False
    llm_url: str = LLM_DEFAULT_URL
    llm_model: str = LLM_DEFAULT_MODEL
    llm_radio: bool = True
    llm_coach: str = "off"
    llm_opfor: bool = False
    # The enemy adapts to the player's habits from the logbook
    # (``src/core/habits.py``); switched on the logbook page with L.
    enemy_learns: bool = True
    # First-launch welcome page ("What do you want to play?") already shown.
    # True by default: only a launch without any settings.json shows it;
    # settings files written before the field existed count as onboarded.
    onboarded: bool = True
    # OPZ chart display (``src/core/opz_display.py``): the settings that
    # differ from the default as (key, value) pairs. Display only.
    opz_display: tuple = ()

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
                 "night_mode", "red_light_auto", "high_contrast", "aa_lines", "speech", "microphone", "live_ais_enabled",
                 "live_adsb_enabled", "onboarded", "llm_enabled", "llm_radio", "llm_opfor", "enemy_learns"):
        value = payload.get(name, getattr(defaults, name))
        values[name] = value if isinstance(value, bool) else getattr(defaults, name)
    frame_rate = payload.get("frame_rate", defaults.frame_rate)
    values["frame_rate"] = (frame_rate if type(frame_rate) is int
                            and frame_rate in FPS_CHOICES else defaults.frame_rate)
    bottom_panel = payload.get("bottom_panel", defaults.bottom_panel)
    values["bottom_panel"] = (bottom_panel if bottom_panel in BOTTOM_PANEL_MODES
                              else defaults.bottom_panel)
    theme = payload.get("theme", defaults.theme)
    values["theme"] = theme if theme in THEME_CHOICES else defaults.theme
    assist = payload.get("operator_assist", defaults.operator_assist)
    values["operator_assist"] = (assist if assist in ("off", "training")
                                 else defaults.operator_assist)
    graphics = payload.get("graphics")
    if graphics not in GRAPHICS_LEVELS:
        # Settings from before the levels: the line switch meant "full".
        graphics = "full" if values["aa_lines"] else defaults.graphics
    values["graphics"] = graphics
    values["aa_lines"] = graphics == "full"
    level = payload.get("level")
    if level not in LEVELS:
        # Settings from before the levels: assistance meant the beginner.
        level = "beginner" if values["operator_assist"] == "training" else defaults.level
    values["level"] = level
    url = payload.get("llm_url", defaults.llm_url)
    values["llm_url"] = url if valid_url(url) else defaults.llm_url
    model = payload.get("llm_model", defaults.llm_model)
    values["llm_model"] = model if valid_model(model) else defaults.llm_model
    coach = payload.get("llm_coach", defaults.llm_coach)
    values["llm_coach"] = coach if coach in LLM_COACH_LEVELS else defaults.llm_coach
    values["opz_display"] = opz_display.to_pairs(
        opz_display.normalize(payload.get("opz_display", ())))
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
