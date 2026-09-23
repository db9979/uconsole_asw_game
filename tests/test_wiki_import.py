"""Wikipedia importer: offline parser/suggestion tests + editor wiring.

No live network access in tests - fetch_wikitext is exercised only via its
URL-parsing/error path and via monkeypatching in the editor-flow test.
"""

import pytest

from src.core.i18n import Translator
from src.data import wiki_import
from src.data.wiki_import import (
    WikiImportError, map_infobox_to_fields, parse_infobox,
    suggest_missing_fields, _parse_wiki_url, _strip_wikitext,
)

SAMPLE_WIKITEXT = """{{Infobox Schiffsklasse
|Land = {{RUS}}
|Klasse = Steregushchiy-Klasse
|Verdraengung = 2200&nbsp;[[Tonne (Einheit)|t]]
|Laenge = 104,5&nbsp;m
|Breite = 13&nbsp;m
|Antrieb = 4 Diesel im CODAD-Verbund
|Geschwindigkeit = 27&nbsp;kn
|Besatzung = 99
|Bewaffnung = 1x 100mm A-190, Uran-Flugkoerper, Kortik-CIWS
}}
Rest of the article with [[links|labels]] and <ref>a citation</ref>.
"""


def test_parse_wiki_url_accepts_https_wikipedia_wiki_paths():
    assert _parse_wiki_url("https://de.wikipedia.org/wiki/Stereguschtschi-Klasse") == (
        "de", "Stereguschtschi-Klasse")
    assert _parse_wiki_url("https://en.wikipedia.org/wiki/Su-25") == ("en", "Su-25")


@pytest.mark.parametrize("url", [
    "", "not a url", "ftp://de.wikipedia.org/wiki/X",
    "https://example.com/wiki/X", "https://de.wikipedia.org/notwiki/X",
    "https://de.wikipedia.org/wiki/",
])
def test_parse_wiki_url_rejects_invalid_urls(url):
    with pytest.raises(WikiImportError):
        _parse_wiki_url(url)


def test_strip_wikitext_removes_markup_and_entities():
    assert _strip_wikitext("[[Tonne (Einheit)|t]]") == "t"
    assert _strip_wikitext("[[Severnaja Verf]]") == "Severnaja Verf"
    assert _strip_wikitext("text<ref>a citation</ref> more") == "text more"
    assert "&nbsp;" not in _strip_wikitext("2200&nbsp;t")


def test_parse_infobox_extracts_known_fields():
    infobox = parse_infobox(SAMPLE_WIKITEXT)
    assert infobox["verdraengung"] == "2200 t"
    assert infobox["laenge"] == "104,5 m"
    assert infobox["geschwindigkeit"] == "27 kn"
    assert infobox["besatzung"] == "99"
    assert "Kortik-CIWS" in infobox["bewaffnung"]


def test_parse_infobox_returns_empty_for_no_infobox():
    assert parse_infobox("just plain article text, no template here") == {}


def test_map_infobox_to_fields_converts_units_and_flags_unmapped():
    infobox = parse_infobox(SAMPLE_WIKITEXT)
    concepts = map_infobox_to_fields(infobox, "surface")
    assert concepts["displacement_t"] == 2200.0
    assert concepts["length_m"] == 104.5
    assert concepts["max_speed_kn"] == 27.0
    assert concepts["propulsion_text"] == "4 Diesel im CODAD-Verbund"
    assert "klasse" in concepts["_unmapped"]


def test_map_infobox_to_fields_converts_kmh_to_knots():
    infobox = {"Geschwindigkeit": "50 km/h"}
    concepts = map_infobox_to_fields(infobox, "surface")
    assert concepts["max_speed_kn"] == pytest.approx(50.0 / 1.852)


def test_suggest_missing_fields_is_deterministic_and_scales_with_displacement():
    small = suggest_missing_fields({}, propulsion_text="Diesel", displacement_t=1000.0)
    large = suggest_missing_fields({}, propulsion_text="Diesel", displacement_t=1000.0)
    assert small == large  # pure function, no hidden randomness
    assert small["demon_blade_count"] == 4  # diesel heuristic
    assert small["lofar_base_freq_hz"][0] > 0
    heavier = suggest_missing_fields({}, propulsion_text="Diesel", displacement_t=8000.0)
    assert heavier["hull_health_max"] > small["hull_health_max"]
    assert heavier["rcs_m2"] > small["rcs_m2"]


def test_suggest_missing_fields_recognizes_propulsion_keywords():
    nuclear = suggest_missing_fields({}, propulsion_text="Atom-U-Boot (Kernantrieb)")
    diesel = suggest_missing_fields({}, propulsion_text="Diesel-elektrisch")
    assert nuclear["demon_blade_count"] != diesel["demon_blade_count"]


def test_fetch_wikitext_rejects_invalid_url_without_network():
    with pytest.raises(WikiImportError):
        wiki_import.fetch_wikitext("not-a-url")


def test_editor_wiki_import_flow_applies_fetched_and_suggested_fields(monkeypatch):
    pygame = pytest.importorskip("pygame")
    pygame.init()
    from src.ui.unit_editor import UnitEditor, UnitDefinition, default_unit

    editor = UnitEditor()
    editor.current = UnitDefinition(default_unit("surface", "user.test_wiki"))
    editor.mode = "editor"
    monkeypatch.setattr(wiki_import, "fetch_wikitext", lambda url, **kw: SAMPLE_WIKITEXT)

    editor._begin_wiki_import()
    assert editor.mode == "wiki_import"
    editor.wiki_input.value = "https://de.wikipedia.org/wiki/Stereguschtschi-Klasse"
    editor._fetch_wiki()
    assert editor.wiki_result is not None
    assert editor.wiki_result["demon_blade_count"][1] == "suggested"
    assert editor.wiki_result["max_speed_kn"][1] == "wiki"

    editor._apply_wiki_result()
    assert editor.mode == "editor"
    assert editor.current.data["wiki_url"] == \
        "https://de.wikipedia.org/wiki/Stereguschtschi-Klasse"
    assert editor.current.data["speed_kn"][1] == 27.0
    assert editor.current.data["acoustic"]["propulsion"] == "4 Diesel im CODAD-Verbund"
    assert editor.current.data["acoustic"]["lofar_base_freq_hz"]
    assert editor.current.data["rcs_m2"] > 0
    assert editor.current.validate() == []


def test_editor_wiki_import_surfaces_fetch_errors_without_crashing(monkeypatch):
    pygame = pytest.importorskip("pygame")
    pygame.init()
    from src.ui.unit_editor import UnitEditor, UnitDefinition, default_unit

    editor = UnitEditor(tr=Translator("en").translate)
    editor.current = UnitDefinition(default_unit("sub", "user.test_wiki_fail"))
    editor.mode = "editor"

    def _boom(url, **kwargs):
        raise WikiImportError("network error reaching Wikipedia: boom")

    monkeypatch.setattr(wiki_import, "fetch_wikitext", _boom)
    editor._begin_wiki_import()
    editor.wiki_input.value = "https://de.wikipedia.org/wiki/Irrelevant"
    editor._fetch_wiki()
    assert editor.wiki_result is None
    assert editor.mode == "wiki_import"  # stays put so the user can retry
    assert "boom" in editor.status
