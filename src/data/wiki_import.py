"""Live Wikipedia import + physics-based suggestion helpers for the Unit Editor.

Fetches a Wikipedia article's infobox via the public MediaWiki Action API
(stdlib ``urllib`` only, no new dependency - matches the project's existing
stdlib-only networking convention, e.g. ``src/commander/server.py``) and maps
a curated set of well-known German infobox keys onto editor-friendly values.
Anything not published on Wikipedia (LOFAR/DEMON acoustics, in-game damage/
hit-chance numbers) is never scraped - it is estimated by
``suggest_missing_fields()`` from simple, documented physical heuristics and
tagged so the caller can show the developer which fields are sourced facts
and which are engine-side guesses to double check.

The device this game runs on is a handheld with no guaranteed connectivity,
so every network/parse failure is caught and re-raised as ``WikiImportError``
- callers should always expect this to fail and show a status message rather
than let it propagate.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "u-jagd-unit-editor/1 (contact: repo maintainer; stdlib urllib)"
REQUEST_TIMEOUT_S = 8.0


class WikiImportError(Exception):
    """Raised for any network, HTTP, or parsing failure during import."""


def _parse_wiki_url(url: str) -> tuple[str, str]:
    if not isinstance(url, str) or not url.strip():
        raise WikiImportError("empty URL")
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise WikiImportError("expected a https:// Wikipedia URL")
    hostname = parsed.hostname.lower()
    if not hostname.endswith(".wikipedia.org"):
        raise WikiImportError("expected a *.wikipedia.org URL")
    lang = hostname.removesuffix(".wikipedia.org")
    if not lang or "/" in lang:
        raise WikiImportError("could not determine Wikipedia language from URL")
    if not parsed.path.startswith("/wiki/"):
        raise WikiImportError("expected a /wiki/<title> URL")
    title = urllib.parse.unquote(parsed.path.removeprefix("/wiki/"))
    if not title:
        raise WikiImportError("empty article title")
    return lang, title


def fetch_wikitext(url: str, *, timeout: float = REQUEST_TIMEOUT_S) -> str:
    """Fetch the raw wikitext of the article at ``url`` via the Action API.

    Raises ``WikiImportError`` for any network, HTTP, or missing-page failure.
    Never raises the underlying ``urllib``/``json`` exception types, so callers
    can catch a single, stable error type.
    """
    lang, title = _parse_wiki_url(url)
    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode({
            "action": "query", "prop": "revisions", "rvslots": "main",
            "rvprop": "content", "format": "json", "formatversion": "2",
            "titles": title,
        })
    )
    request = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise WikiImportError(f"HTTP {response.status} from Wikipedia")
            payload = response.read(8 * 1024 * 1024)
    except urllib.error.URLError as exc:
        raise WikiImportError(f"network error reaching Wikipedia: {exc}") from exc
    except TimeoutError as exc:
        raise WikiImportError("timed out reaching Wikipedia") from exc
    try:
        data = json.loads(payload.decode("utf-8"))
        pages = data["query"]["pages"]
        if not pages or pages[0].get("missing"):
            raise WikiImportError(f"article {title!r} not found on {lang}.wikipedia.org")
        wikitext = pages[0]["revisions"][0]["slots"]["main"]["content"]
    except (KeyError, IndexError, ValueError, UnicodeDecodeError) as exc:
        raise WikiImportError("unexpected Wikipedia API response shape") from exc
    if not isinstance(wikitext, str) or not wikitext:
        raise WikiImportError("empty article content")
    return wikitext


def _strip_wikitext(value: str) -> str:
    value = re.sub(r"<ref[^>]*/?>.*?</ref>|<ref[^>]*/>", "", value, flags=re.S)
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    # [[target|label]] -> label ; [[target]] -> target
    value = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\[\[([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\{\{[Cc]onvert\|([0-9.,]+)\|([a-zA-Z²]+)[^}]*\}\}", r"\1 \2", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)  # drop remaining simple templates
    value = value.replace("'''", "").replace("''", "")
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip(" \n\t,;")
    return value


def _find_infobox_block(wikitext: str) -> str | None:
    match = re.search(r"\{\{\s*Infobox", wikitext, flags=re.I)
    if match is None:
        return None
    start = match.start()
    depth = 0
    i = start
    while i < len(wikitext) - 1:
        pair = wikitext[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start:i]
            continue
        i += 1
    return None


def parse_infobox(wikitext: str) -> dict[str, str]:
    """Best-effort parse of the article's first ``{{Infobox ...}}`` template.

    Returns raw (markup-stripped) key -> value text. Unrecognized keys are
    kept, not discarded, so a caller can show them for manual review.
    """
    block = _find_infobox_block(wikitext)
    if block is None:
        return {}
    inner = block[block.index("{{") + 2:-2]
    fields: dict[str, str] = {}
    depth = 0
    current_key: str | None = None
    buf: list[str] = []

    def flush():
        if current_key is not None:
            text = _strip_wikitext("".join(buf))
            if text:
                fields[current_key] = text

    i = 0
    key_buf: list[str] = []
    in_key = True
    while i < len(inner):
        chunk = inner[i:i + 2]
        if chunk in ("{{", "[["):
            depth += 1
            (key_buf if in_key else buf).append(chunk)
            i += 2
            continue
        if chunk in ("}}", "]]"):
            depth = max(0, depth - 1)
            (key_buf if in_key else buf).append(chunk)
            i += 2
            continue
        char = inner[i]
        if depth == 0 and char == "|" and in_key is False:
            flush()
            current_key = None
            buf = []
            in_key = True
            key_buf = []
            i += 1
            continue
        if depth == 0 and char == "|" and in_key:
            # stray '|' before any '=' (e.g. template default) - ignore key so far
            key_buf = []
            i += 1
            continue
        if depth == 0 and char == "=" and in_key:
            current_key = "".join(key_buf).strip().lower()
            in_key = False
            i += 1
            continue
        (key_buf if in_key else buf).append(char)
        i += 1
    flush()
    return fields


# German infobox key (lowercased) -> our concept name. Multiple aliases map to
# the same concept since infobox templates vary between ship/aircraft types.
_KEY_ALIASES = {
    "verdrängung": "displacement_t", "wasserverdrängung": "displacement_t",
    "verdraengung": "displacement_t",
    "länge": "length_m", "laenge": "length_m", "länge (lüa)": "length_m",
    "breite": "beam_m",
    "tiefgang": "draft_m",
    "geschwindigkeit": "max_speed_kn", "höchstgeschwindigkeit": "max_speed_kn",
    "hoechstgeschwindigkeit": "max_speed_kn",
    "besatzung": "crew",
    "antrieb": "propulsion_text",
    "bewaffnung": "armament_text",
    "sensoren": "sensors_text", "radar": "sensors_text",
    "indienststellung": "commission_year", "erstflug": "first_flight_year",
    "einheiten": "class_ships",
}

_SPEED_KMH_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:km\s*/\s*h|kn|kt)", re.I)
_NUMBER_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)")


def _first_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace(".", "").replace(",", "."))
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _speed_to_kn(text: str) -> float | None:
    match = _SPEED_KMH_RE.search(text)
    if match is None:
        return _first_number(text)
    value = float(match.group(1).replace(".", "").replace(",", "."))
    unit = match.group(0).lower()
    return value / 1.852 if "km" in unit else value


def map_infobox_to_fields(infobox: dict[str, str], kind: str) -> dict[str, Any]:
    """Map recognized infobox keys onto plain concept names for ``kind``.

    ``kind`` is one of the unit-editor profile kinds ("sub", "surface",
    "aircraft"). Returns only concepts we recognized; anything else in the
    infobox is left for the caller to show as unmapped raw text.
    """
    concepts: dict[str, Any] = {}
    for raw_key, raw_value in infobox.items():
        concept = _KEY_ALIASES.get(raw_key.strip().lower())
        if concept is None:
            continue
        if concept in ("displacement_t",):
            value = _first_number(raw_value)
        elif concept in ("length_m", "beam_m", "draft_m"):
            value = _first_number(raw_value)
        elif concept == "max_speed_kn":
            value = _speed_to_kn(raw_value)
        elif concept in ("commission_year", "first_flight_year"):
            value = None
            match = re.search(r"(1[89]\d\d|20\d\d)", raw_value)
            if match:
                value = int(match.group(1))
        else:
            value = raw_value
        if value is not None:
            concepts[concept] = value
    concepts["_unmapped"] = {
        key: value for key, value in infobox.items()
        if key.strip().lower() not in _KEY_ALIASES
    }
    return concepts


_PROPULSION_PROFILES = {
    # propulsion keyword -> (shaft_rpm, blade_count, cavitation_speed_knots)
    "diesel": (300.0, 4, 14.0),
    "gas_turbine": (350.0, 5, 20.0),
    "nuclear": (180.0, 7, 22.0),
    "aip": (140.0, 5, 12.0),
    "unknown": (250.0, 5, 16.0),
}


def _guess_propulsion_key(propulsion_text: str | None, hull_type: str) -> str:
    text = (propulsion_text or "").lower()
    if "nuklear" in text or "kern" in text or "nuclear" in text:
        return "nuclear"
    if "aip" in text or "brennstoffzelle" in text:
        return "aip"
    if "gasturbine" in text or "codog" in text or "codag" in text or "turbine" in text:
        return "gas_turbine"
    if "diesel" in text:
        return "diesel"
    return "unknown"


def suggest_missing_fields(known: dict[str, Any], *, hull_type: str = "unknown",
                          propulsion_text: str | None = None,
                          displacement_t: float | None = None) -> dict[str, Any]:
    """Plausible physical estimates for fields Wikipedia never publishes.

    Every returned value is a game-model estimate, not a verified spec -
    consistent with how the packaged catalog already documents its acoustic
    numbers (see docs/contacts-db.md "Modellannahmen"). Callers should tag
    these as "suggested" and let a developer review/adjust them before saving.
    """
    displacement_t = displacement_t if displacement_t is not None else known.get("displacement_t")
    propulsion_key = _guess_propulsion_key(propulsion_text, hull_type)
    shaft_rpm, blades, cavitation_kn = _PROPULSION_PROFILES[propulsion_key]

    suggestions: dict[str, Any] = {
        "demon_blade_count": blades,
        "demon_rpm_idle": round(shaft_rpm * 0.35, 1),
        "demon_rpm_max": round(shaft_rpm, 1),
        "lofar_base_freq_hz": [round(blades * shaft_rpm / 60.0 * n, 2) for n in (1, 2, 3)],
        "cavitation_speed_knots": cavitation_kn,
    }
    if displacement_t:
        suggestions["hull_health_max"] = round(min(2000.0, max(50.0, displacement_t * 0.15)), 1)
        suggestions["rcs_m2"] = round(min(5000.0, max(5.0, displacement_t * 0.25)), 1)
    else:
        suggestions["hull_health_max"] = 200.0
        suggestions["rcs_m2"] = 100.0
    return suggestions
