"""Small, dependency-free translation catalog loader."""

from __future__ import annotations

import json
import locale
import os
import re
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from importlib import resources
from string import Formatter


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "de")
_RESOURCE_PACKAGE = "data.i18n"
_FORMATTER = Formatter()
_ACTIVE_TRANSLATOR: ContextVar[object | None] = ContextVar(
    "u_jagd_translator", default=None)


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


def _alternate_german_spelling(message: str) -> str:
    """Match legacy ASCII German UI text against the UTF-8 catalog and back."""
    replacements = (("Ae", "Ä"), ("Oe", "Ö"), ("Ue", "Ü"),
                    ("ae", "ä"), ("oe", "ö"), ("ue", "ü"))
    for ascii_text, unicode_text in replacements:
        message = message.replace(ascii_text, unicode_text)
    return message


def _fold_german(message: str) -> str:
    for unicode_text, ascii_text in (("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"),
                                     ("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
                                     ("ß", "ss")):
        message = message.replace(unicode_text, ascii_text)
    return message


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
        self._literal_sources.update({
            _alternate_german_spelling(value): key
            for key, value in self.german.items()
        })
        self._literal_sources_casefold = {
            _fold_german(value).casefold(): key
            for value, key in self._literal_sources.items()
        }
        self._literal_templates = []
        for source_catalog in (self.reference, self.german):
            for catalog_key, source in source_catalog.items():
                if "{" not in source:
                    continue
                parts = []
                seen = set()
                for literal, field, _, _ in _FORMATTER.parse(source):
                    parts.append(re.escape(literal))
                    if field is not None:
                        if field in seen:
                            parts.append(f"(?P={field})")
                        else:
                            parts.append(f"(?P<{field}>.+?)")
                            seen.add(field)
                self._literal_templates.append(
                    (re.compile("^" + "".join(parts) + "$"), catalog_key))
        phrase_prefixes = ("ui.", "class.", "affiliation.", "domain.",
                           "damage.", "map.", "panel.", "event.", "state.",
                           "tma.", "literal.", "compartment.")
        pairs = []
        for source_catalog in (self.reference, self.german):
            pairs.extend((source, self.catalog[key])
                         for key, source in source_catalog.items()
                         if key.startswith(phrase_prefixes) and len(source) <= 40)
        self._display_replacements = sorted(
            ((source, target) for source, target in pairs
             if source != target and len(source) >= 3 and "{" not in source),
            key=lambda pair: len(pair[0]), reverse=True)

    def translate(self, key: str, **values: object) -> str:
        message = self.catalog.get(key)
        if message is None:
            literal_key = self._literal_sources.get(key)
            if literal_key is None:
                literal_key = self._literal_sources_casefold.get(
                    _fold_german(key).casefold())
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
        """Translate a rendered literal, including text with runtime values."""
        return self._display_cached(str(value))

    @lru_cache(maxsize=4096)
    def _display_cached(self, text: str) -> str:
        if text in self.catalog:
            return self.translate(text)
        direct = self._literal_sources.get(text)
        if direct is None:
            direct = self._literal_sources_casefold.get(
                _fold_german(text).casefold())
        if direct is not None:
            return self.catalog[direct]
        for pattern, catalog_key in self._literal_templates:
            match = pattern.match(text)
            if match is not None:
                try:
                    values = {key: self._display_cached(value)
                              for key, value in match.groupdict().items()}
                    return self.catalog[catalog_key].format(**values)
                except (KeyError, TypeError, ValueError):
                    break
        for source, target in self._display_replacements:
            for old, new in ((source.upper(), target.upper()),
                             (source, target), (source.title(), target.title()),
                             (_alternate_german_spelling(source), target)):
                text = re.sub(r"(?<!\w)" + re.escape(old) + r"(?!\w)",
                              new, text)
        return text


def get_translator(language: str | None = None) -> Translator:
    return Translator(language)


def localize(value: object, tr=None) -> str:
    """Translate display text in the current draw scope."""
    translator = tr if tr is not None else _ACTIVE_TRANSLATOR.get()
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
