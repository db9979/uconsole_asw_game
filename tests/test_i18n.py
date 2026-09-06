import ast
from pathlib import Path

import pytest

from src.core.help import get_help
from src.core.i18n import (
    TranslationError,
    Translator,
    detect_system_language,
    load_catalog,
    pseudolocale,
    translation_scope,
    validate_catalog,
)
from src.core.station import Station


def test_catalogs_have_exact_key_and_placeholder_parity():
    english = load_catalog("en")
    german = load_catalog("de")
    assert english.keys() == german.keys()
    validate_catalog(german, english)


def test_translation_formats_named_values_and_falls_back_to_english():
    assert Translator("de").t("menu.seed", seed=42) == "Seed: 42"
    assert Translator("fr").language == "en"
    assert Translator("de").t("missing.key") == "missing.key"
    with pytest.raises(TranslationError, match="missing placeholders"):
        Translator("en").t("menu.seed")


def test_system_language_normalization():
    assert detect_system_language("de_DE.UTF-8") == "de"
    assert detect_system_language("en-US") == "en"
    assert detect_system_language("fr_FR") == "en"


def test_pseudolocale_preserves_keys_and_placeholders():
    source = load_catalog("en")
    pseudo = pseudolocale(source)
    assert pseudo.keys() == source.keys()
    assert pseudo["menu.seed"].format(seed=7).startswith("[!!")
    validate_catalog(pseudo, source)


def test_literal_lookup_supports_legacy_german_and_english_ui_text():
    english = Translator("en")
    german = Translator("de")

    assert english.display("Brücke / Nautik") == "Bridge / Navigation"
    assert english.display("K3 klassifiziert: U-Boot") == \
        "K3 classified: Submarine"
    assert german.t("Saved") == "Gespeichert"
    assert german.display("STOWED") == "VERSTAUT"


def test_help_and_open_editor_literals_follow_the_current_draw_scope():
    intro_en, controls_en, _, _ = get_help(Station.BRIDGE, Translator("en").t)
    intro_de, controls_de, _, _ = get_help(Station.BRIDGE, Translator("de").t)
    assert intro_en.startswith("Bridge / Navigation")
    assert intro_de.startswith("Brücke / Nautik")
    assert controls_en[0][1] == "Rudder: change target course"
    assert controls_de[0][1] == "Ruder: Zielkurs aendern"

    with translation_scope(Translator("de").t):
        from src.core.i18n import localize
        assert localize("Mission library") == "Missionsbibliothek"
    with translation_scope(Translator("en").t):
        assert localize("Mission library") == "Mission library"


def test_ui_direct_font_literals_are_explicitly_technical_allowlist():
    """New prose must use bounded/localized helpers, not Font.render directly."""
    allowed = {"[ ]", "ASM", "ESM", "HOJ", "HSP-5"}
    roots = [Path("src/ui"), Path("src/core/game.py")]
    violations = []
    paths = [roots[1]] + sorted(roots[0].glob("*.py"))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "render" and node.args):
                continue
            value = node.args[0]
            if (isinstance(value, ast.Constant) and isinstance(value.value, str)
                    and value.value not in allowed):
                violations.append(f"{path}:{node.lineno}: {value.value!r}")
    assert not violations, "hardcoded Font.render UI literals:\n" + "\n".join(violations)
