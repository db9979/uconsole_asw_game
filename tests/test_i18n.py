import ast
import json
from pathlib import Path
import re

import pytest

from src.core.help import get_help
from src.core.i18n import (
    DISPLAY_KEYS,
    TranslationError,
    Translator,
    detect_system_language,
    load_catalog,
    display_value,
    localize,
    message,
    raw_text,
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


def test_exact_legacy_literals_work_but_composed_text_is_not_parsed():
    english = Translator("en")
    german = Translator("de")

    assert english.display("Brücke / Nautik") == "Bridge / Navigation"
    assert english.display("K3 klassifiziert: U-Boot") == \
        "K3 klassifiziert: U-Boot"
    assert german.t("Saved") == "Gespeichert"
    assert german.display("STOWED") == "VERSTAUT"


def test_structured_messages_retranslate_and_keep_authored_braces_opaque():
    value = message("runtime.mission.started", name=raw_text("{author.name}"),
                    level=message("level.hard"),
                    objective=raw_text("Reach {sector[0]}"))
    json.dumps(value)
    assert localize(value, Translator("en").t) == \
        "Mission: {author.name} (Hard) - Reach {sector[0]}"
    assert localize(value, Translator("de").t) == \
        "Mission: {author.name} (Hart) - Reach {sector[0]}"


def test_raw_text_bypasses_catalog_literals():
    assert localize(raw_text("Saved"), Translator("de").t) == "Saved"
    assert localize("Saved", Translator("de").t) == "Gespeichert"


def test_display_mappings_cover_required_persisted_enum_families():
    required = {"station", "classification", "affiliation", "array", "tow",
                "tma", "fusion", "weapon_mode", "profile_kind", "side",
                "weather", "objective", "event", "placement", "used_by"}
    assert required <= DISPLAY_KEYS.keys()
    assert display_value("classification", "U_BOOT", Translator("de").t) == "U-Boot"
    assert display_value("weather", "storm", Translator("en").t) == "Storm"


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


def test_static_text_sent_to_ui_helpers_is_cataloged_or_technical():
    """Audit every bounded rendering entry point, not only Font.render."""
    english = load_catalog("en")
    catalog_text = set(english) | set(english.values()) | set(load_catalog("de").values())
    proper_names = {"U-JAGD – FREGATTE F-217"}
    text_arguments = {
        "tr": (0,), "translate": (0,), "center": (0,),
        "blit_line": (1,), "blit_block": (1,), "draw_text": (1,), "_text": (1,),
        "box": (2,), "panel": (2,), "status_line": (4, 5),
        "tooltip_payload": tuple(range(8)),
    }
    technical = re.compile(r"[A-Z0-9+./<>|= :_\-\[\]]+")
    violations = []
    paths = [Path("src/core/game.py"), Path("src/core/help.py"),
             *sorted(Path("src/ui").glob("*.py"))]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute) else
                    node.func.id if isinstance(node.func, ast.Name) else "")
            for index in text_arguments.get(name, ()):
                if index >= len(node.args):
                    continue
                value = node.args[index]
                if (not isinstance(value, ast.Constant)
                        or not isinstance(value.value, str) or not value.value):
                    continue
                if (value.value not in catalog_text and value.value not in proper_names
                        and technical.fullmatch(value.value) is None):
                    violations.append(f"{path}:{node.lineno}: {value.value!r}")
    assert not violations, "uncataloged static UI text:\n" + "\n".join(violations)


def test_runtime_message_sinks_do_not_receive_composed_prose():
    """Runtime notices must remain structured so a language switch can redraw them."""
    path = Path("src/core/game.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    composed = (ast.Constant, ast.JoinedStr, ast.BinOp, ast.IfExp)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if name in ("flash", "hq_msg"):
            value = node.args[0]
        elif (name == "add" and isinstance(node.func.value, ast.Attribute)
              and node.func.value.attr == "feed" and len(node.args) >= 3):
            value = node.args[2]
        else:
            continue
        if isinstance(value, composed):
            violations.append(f"{path}:{node.lineno}: {ast.unparse(value)}")
    assert not violations, "composed runtime UI prose:\n" + "\n".join(violations)


def test_game_does_not_send_composed_text_to_exact_localization():
    path = Path("src/core/game.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute) else
                node.func.id if isinstance(node.func, ast.Name) else "")
        if name in ("localize", "display") and isinstance(
                node.args[0], (ast.JoinedStr, ast.BinOp)):
            violations.append(f"{path}:{node.lineno}: {ast.unparse(node.args[0])}")
    assert not violations, "composed exact-localization input:\n" + "\n".join(violations)
