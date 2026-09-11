"""Small, dependency-free translation catalog loader."""

from __future__ import annotations

import json
import locale
import os
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from importlib import resources
from string import Formatter


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "de")
_RESOURCE_PACKAGE = "data.i18n"
_FORMATTER = Formatter()
_ACTIVE_TRANSLATOR: ContextVar[object | None] = ContextVar(
    "u_jagd_translator", default=None)
_MESSAGE_KEY = "__u_jagd_i18n__"
_RAW_TEXT_KEY = "__u_jagd_raw_text__"


# Persisted values remain the keys in these tables. Only their display labels
# are translated, in one place, at the UI boundary.
DISPLAY_KEYS = {
    "station": {
        "BRIDGE": "station.bridge", "SONAR": "station.sonar",
        "WEAPONS": "station.weapons", "DAMAGE": "station.damage",
        "OPZ": "station.opz", "RADIO": "station.radio",
        "ENGINE": "station.engine", "HELICOPTER": "station.helicopter",
        "ELOKA": "station.ew",
    },
    "classification": {
        None: "class.unknown", "UNKNOWN": "class.unknown",
        "UNBEKANNT": "class.unknown", "U_BOOT": "class.submarine",
        "SUBMARINE": "class.submarine", "KAMPFSCHIFF": "class.warship",
        "WARSHIP": "class.warship", "BIOLOGISCH": "class.biological",
        "BIOLOGICAL": "class.biological", "FAHRZEUG": "class.vehicle",
        "VEHICLE": "class.vehicle",
    },
    "affiliation": {
        "UNKNOWN": "affiliation.unknown", "FRIEND": "affiliation.friend",
        "FRIENDLY": "affiliation.friend", "NEUTRAL": "affiliation.neutral",
        "HOSTILE": "affiliation.hostile",
    },
    "domain": {
        "SURFACE": "domain.surface", "SUBSURFACE": "domain.subsurface",
        "AIR": "domain.air", "MISSILE": "domain.missile",
        "UNDERWATER_WEAPON": "domain.underwater_weapon",
    },
    "array": {"BOW": "enum.array.bow", "TOWED": "enum.array.towed"},
    "tow": {
        "STOWED": "state.stowed", "DEPLOYING": "state.deploying",
        "RETRIEVING": "state.retrieving", "STREAMED": "state.streamed",
        "FAULT": "state.fault",
    },
    "tma": {
        "ZU WENIG HISTORIE": "tma.no_history", "INSUFFICIENT HISTORY": "tma.no_history",
        "SCHWACHE GEOMETRIE": "tma.weak_geometry", "WEAK GEOMETRY": "tma.weak_geometry",
        "KONVERGIEREND": "tma.converging", "CONVERGING": "tma.converging",
        "LOESUNG STABIL": "tma.stable", "SOLUTION STABLE": "tma.stable",
        "VERALTET": "tma.stale", "STALE": "tma.stale",
        "BRAUCHBAR": "tma.useful", "USEFUL": "tma.useful",
        "SCHWACH": "tma.weak", "WEAK": "tma.weak",
    },
    "fusion": {
        "KEINE DATEN": "enum.fusion.none", "KEINE FUSION": "enum.fusion.none",
        "BESTAETIGT": "enum.fusion.confirmed", "DIVERGENT": "enum.fusion.divergent",
        "MOEGLICHER GEISTERKONTAKT": "enum.fusion.ghost",
    },
    "weapon_mode": {"DRAHT": "enum.weapon.wire", "SUCHER": "enum.weapon.seeker"},
    "profile_kind": {
        "sub": "enum.kind.sub", "surface": "enum.kind.surface",
        "aircraft": "enum.kind.aircraft", "animal": "enum.kind.animal",
        "torpedo": "enum.kind.torpedo", "decoy": "enum.kind.decoy",
    },
    "side": {
        "friendly": "enum.side.friendly", "neutral": "enum.side.neutral",
        "hostile": "enum.side.hostile",
    },
    "weather": {
        "clear": "enum.weather.clear", "rain": "enum.weather.rain",
        "storm": "enum.weather.storm", "fog": "enum.weather.fog",
    },
    "objective": {
        "sink": "enum.objective.sink", "survive": "enum.objective.survive",
        "protect": "enum.objective.protect", "reach": "enum.objective.reach",
    },
    "event": {
        "message": "enum.event.message", "spawn": "enum.event.spawn",
        "weather": "enum.event.weather", "objective": "enum.event.objective",
    },
    "placement": {"fixed": "enum.placement.fixed", "sector": "enum.placement.sector"},
    "used_by": {
        "frigate": "enum.used_by.frigate", "helo": "enum.used_by.helo",
        "enemy": "enum.used_by.enemy",
    },
    "sonar_page": {
        "BROADBAND": "sonar.broadband", "LOFAR": "enum.sonar_page.lofar",
        "DEMON": "enum.sonar_page.demon", "TMA": "enum.sonar_page.tma",
        "UMWELT/FUSION": "sonar.environment", "ACTIVE": "enum.sonar_page.active",
    },
    "audition_mode": {
        "BROADBAND": "enum.audition_mode.broadband",
        "FILTERED": "enum.audition_mode.filtered",
        "HETERODYNE": "enum.audition_mode.heterodyne",
    },
}


class TranslationError(ValueError):
    """Raised when a catalog or translated message is invalid."""


def normalize_language(language: str | None) -> str:
    """Return a supported two-letter language code, falling back to English."""
    if not language:
        return DEFAULT_LANGUAGE
    value = language.strip().lower().replace("-", "_")
    prefix = value.split("_", 1)[0].split(".", 1)[0]
    if prefix in SUPPORTED_LANGUAGES:
        return prefix
    if value.startswith("german"):
        return "de"
    return DEFAULT_LANGUAGE


def detect_system_language(locale_name: str | None = None) -> str:
    """Detect the system language without changing the process locale."""
    if locale_name is not None:
        return normalize_language(locale_name)
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value:
            # LANGUAGE may contain a colon-separated preference list.
            return normalize_language(value.split(":", 1)[0])
    try:
        current = locale.getlocale()[0]
    except (ValueError, TypeError):
        current = None
    return normalize_language(current)


def _placeholders(message: str) -> frozenset[str]:
    fields: set[str] = set()
    try:
        parsed = _FORMATTER.parse(message)
        for _, field, format_spec, _ in parsed:
            if field is None:
                continue
            if not field or field.isdecimal():
                raise TranslationError("only named placeholders are supported")
            fields.add(field)
            if format_spec:
                fields.update(_placeholders(format_spec))
    except ValueError as exc:
        raise TranslationError(f"invalid format string: {message!r}") from exc
    return frozenset(fields)


def validate_catalog(catalog: Mapping[str, str],
                     reference: Mapping[str, str]) -> None:
    """Validate key parity and named placeholders against a reference."""
    if not all(isinstance(key, str) and isinstance(value, str)
               for key, value in reference.items()):
        raise TranslationError("reference keys and values must be strings")
    if not all(isinstance(key, str) and isinstance(value, str)
               for key, value in catalog.items()):
        raise TranslationError("catalog keys and values must be strings")
    if set(catalog) != set(reference):
        missing = sorted(set(reference) - set(catalog))
        extra = sorted(set(catalog) - set(reference))
        raise TranslationError(
            f"catalog key mismatch (missing={missing}, extra={extra})")
    for key, reference_message in reference.items():
        message = catalog[key]
        expected = _placeholders(reference_message)
        actual = _placeholders(message)
        if actual != expected:
            raise TranslationError(
                f"placeholder mismatch for {key!r}: "
                f"expected {sorted(expected)}, got {sorted(actual)}")


def _read_catalog(language: str) -> dict[str, str]:
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(f"{language}.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranslationError(f"cannot load {language!r} catalog") from exc
    if not isinstance(payload, dict):
        raise TranslationError(f"{language!r} catalog must be a JSON object")
    if not all(isinstance(key, str) and isinstance(value, str)
               for key, value in payload.items()):
        raise TranslationError("catalog keys and values must be strings")
    return payload


def load_catalog(language: str | None = None) -> dict[str, str]:
    """Load a validated catalog; unsupported languages resolve to English."""
    selected = normalize_language(language)
    english = _read_catalog(DEFAULT_LANGUAGE)
    validate_catalog(english, english)
    if selected == DEFAULT_LANGUAGE:
        return english
    try:
        catalog = _read_catalog(selected)
        validate_catalog(catalog, english)
    except TranslationError:
        return english
    return catalog


def _alternate_german_spelling(text: str) -> str:
    """Support exact legacy umlaut spellings without parsing composed text."""
    for ascii_text, unicode_text in (("Ae", "Ä"), ("Oe", "Ö"), ("Ue", "Ü"),
                                     ("ae", "ä"), ("oe", "ö"), ("ue", "ü")):
        text = text.replace(ascii_text, unicode_text)
    return text


class Translator:
    """Translate message keys and safely substitute named placeholders."""

    def __init__(self, language: str | None = None,
                 catalog: Mapping[str, str] | None = None):
        self.language = normalize_language(language)
        self.catalog = (dict(catalog) if catalog is not None
                        else load_catalog(self.language))
        if catalog is not None:
            validate_catalog(self.catalog, load_catalog(DEFAULT_LANGUAGE))
        if self.language != DEFAULT_LANGUAGE and self.catalog == load_catalog():
            self.language = DEFAULT_LANGUAGE
        self.reference = load_catalog(DEFAULT_LANGUAGE)
        self.german = load_catalog("de")
        self._literal_sources = {value: key for key, value in self.reference.items()}
        self._literal_sources.update({value: key for key, value in self.german.items()})
        self._literal_sources.update({_alternate_german_spelling(value): key
                                      for key, value in self.german.items()})

    def translate(self, key: str, **values: object) -> str:
        message = self.catalog.get(key)
        if message is None:
            literal_key = self._literal_sources.get(key)
            message = self.catalog.get(literal_key, key)
        required = _placeholders(message)
        missing = required - values.keys()
        if missing:
            raise TranslationError(
                f"missing placeholders for {key!r}: {sorted(missing)}")
        try:
            return message.format(**values)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            raise TranslationError(f"cannot format translation {key!r}") from exc

    gettext = translate
    t = translate
    __call__ = translate

    def display(self, value: object) -> str:
        """Translate a catalog key or exact legacy literal."""
        return self._display_cached(str(value))

    def _display_cached(self, text: str) -> str:
        """Translate a key or exact legacy literal, never parse composed text."""
        if text in self.catalog:
            return self.translate(text)
        direct = self._literal_sources.get(text)
        if direct is not None:
            return self.catalog[direct]
        return text


def get_translator(language: str | None = None) -> Translator:
    return Translator(language)


def message(key: str, **params: object) -> dict[str, object]:
    """Return a JSON-safe localizable message for feeds, flashes, and saves."""
    return {_MESSAGE_KEY: str(key), "params": dict(params)}


class RawText(dict):
    """JSON-safe opaque user-authored text that must never be translated."""

    def __init__(self, value: object):
        super().__init__({_RAW_TEXT_KEY: str(value)})

    @property
    def value(self) -> str:
        return self[_RAW_TEXT_KEY]


def raw_text(value: object) -> RawText:
    return RawText(value)


def is_message(value: object) -> bool:
    return (isinstance(value, Mapping)
            and isinstance(value.get(_MESSAGE_KEY), str)
            and isinstance(value.get("params", {}), Mapping))


def _is_raw_text(value: object) -> bool:
    return (isinstance(value, Mapping)
            and isinstance(value.get(_RAW_TEXT_KEY), str))


def display_value(kind: str, value: object, tr=None) -> str:
    """Translate a display enum without changing its internal stored value."""
    key = DISPLAY_KEYS.get(kind, {}).get(value)
    if key is None:
        key = DISPLAY_KEYS.get(kind, {}).get(str(value))
    translator = tr if tr is not None else _ACTIVE_TRANSLATOR.get()
    if key is None:
        return str(value)
    translator = translator or get_translator().t
    return str(translator(key))


def localize(value: object, tr=None) -> str:
    """Translate display text in the current draw scope."""
    if _is_raw_text(value):
        return str(value[_RAW_TEXT_KEY])
    translator = tr if tr is not None else _ACTIVE_TRANSLATOR.get()
    if is_message(value):
        if translator is None:
            translator = get_translator().t
        params = {
            key: localize(param, translator)
            if is_message(param) or _is_raw_text(param) else param
            for key, param in value.get("params", {}).items()
        }
        try:
            return str(translator(value[_MESSAGE_KEY], **params))
        except TypeError:
            # Lightweight test/plugin hooks historically accepted one argument.
            return str(translator(value[_MESSAGE_KEY]))
    if translator is None:
        return str(value)
    owner = getattr(translator, "__self__", None)
    if isinstance(owner, Translator):
        return owner.display(value)
    if isinstance(translator, Translator):
        return translator.display(value)
    return str(translator(str(value)))


@contextmanager
def translation_scope(tr=None):
    """Temporarily select a translator for nested rendering helpers."""
    token = _ACTIVE_TRANSLATOR.set(tr)
    try:
        yield
    finally:
        _ACTIVE_TRANSLATOR.reset(token)


def localized(draw):
    """Decorate a draw/hit-test function while preserving its signature."""
    @wraps(draw)
    def wrapped(owner, *args, **kwargs):
        tr = kwargs.get("tr")
        if tr is None and args and callable(args[-1]):
            tr = args[-1]
        if tr is None:
            tr = getattr(owner, "tr", None)
        with translation_scope(tr):
            return draw(owner, *args, **kwargs)
    return wrapped


_PSEUDO_TABLE = str.maketrans({
    "a": "á", "e": "ë", "i": "ï", "o": "ö", "u": "ü",
    "A": "Á", "E": "Ë", "I": "Ï", "O": "Ö", "U": "Ü",
    "c": "ç", "n": "ñ", "C": "Ç", "N": "Ñ",
})


def pseudolocalize(message: str) -> str:
    """Expand visible text while preserving format placeholders for UI tests."""
    chunks: list[str] = []
    try:
        for literal, field, format_spec, conversion in _FORMATTER.parse(message):
            pseudo = literal.translate(_PSEUDO_TABLE)
            chunks.append(pseudo.replace("{", "{{").replace("}", "}}"))
            if field is not None:
                placeholder = "{" + field
                if conversion:
                    placeholder += "!" + conversion
                if format_spec:
                    placeholder += ":" + format_spec
                chunks.append(placeholder + "}")
    except ValueError as exc:
        raise TranslationError(f"invalid format string: {message!r}") from exc
    return "[!! " + "".join(chunks) + " !!]"


def pseudolocale(catalog: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a pseudolocalized catalog with unchanged keys/placeholders."""
    source = load_catalog() if catalog is None else catalog
    result = {key: pseudolocalize(value) for key, value in source.items()}
    validate_catalog(result, source)
    return result
