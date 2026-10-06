"""Player manual contract: EN/DE parity, generated tables, exports, web page.

These tests fail whenever controls, stations, or documented numbers drift
from the manual, so every gameplay change has to update the guides too.
"""

import ast
import http.client
import json
import re
from pathlib import Path

import pytest

from src.commander import CommanderServer
from src.core import config, manual
from src.core.help import _GLOBAL_HELP, STATION_HELP, STATION_SOP
from src.core.i18n import Translator, load_catalog
from src.core.station import Station

ROOT = Path(__file__).parents[1]
SECTIONS = ("purpose", "pages", "displays", "keys", "mouse", "sop", "tips", "limits")


def _blocks(chapter, lang):
    return manual.chapter_blocks(chapter, lang)


def test_every_chapter_exists_in_both_languages_with_identical_structure():
    files = {path.name for path in (ROOT / "data" / "manual").glob("*.md")}
    expected = {manual.chapter_filename(chapter, lang)
                for chapter in manual.CHAPTERS for lang in manual.LANGUAGES}
    assert files == expected
    anchors = []
    for chapter in manual.CHAPTERS:
        en, de = _blocks(chapter, "en"), _blocks(chapter, "de")
        assert [block.kind for block in en] == [block.kind for block in de], chapter
        assert ([(b.level, b.anchor) for b in en if b.kind == "heading"]
                == [(b.level, b.anchor) for b in de if b.kind == "heading"]), chapter
        assert [b.marker for b in en] == [b.marker for b in de], chapter
        for left, right in zip(en, de):
            if left.kind == "table" and not left.marker:
                assert len(left.rows) == len(right.rows), chapter
            if left.kind in ("ul", "ol") and not left.marker:
                assert len(left.items) == len(right.items), chapter
        assert en[0].kind == "heading" and en[0].level == 1
        anchors += [b.anchor for b in en if b.kind == "heading"]
    assert len(anchors) == len(set(anchors))


def test_every_station_has_a_complete_chapter_with_generated_keys_and_procedure():
    assert set(manual.STATION_CHAPTERS) == set(Station)  # RADAR aliases OPZ
    for station, chapter in manual.STATION_CHAPTERS.items():
        blocks = _blocks(chapter, "en")
        anchors = [b.anchor for b in blocks if b.kind == "heading"]
        assert anchors[0] == f"station-{chapter}"
        assert {f"{chapter}-{section}" for section in SECTIONS} <= set(anchors)
        markers = [b.marker for b in blocks if b.marker]
        assert f"keys:{chapter}" in markers and f"sop:{chapter}" in markers
        table = next(b for b in blocks if b.marker == f"keys:{chapter}")
        assert len(table.rows) == len(STATION_HELP[station][1])
    # Each station chapter keeps one order: purpose, pages, displays, keys,
    # mouse, standard procedure, tips, not modelled.
    for chapter in manual.STATION_CHAPTERS.values():
        anchors = [b.anchor for b in _blocks(chapter, "en") if b.kind == "heading"]
        order = [anchors.index(f"{chapter}-{section}") for section in SECTIONS]
        assert order == sorted(order), chapter

    def markers(chapter):
        return [b.marker for b in _blocks(chapter, "en") if b.marker and b.kind != "figure"]
    assert markers("quickstart") == ["keys:global"]
    assert markers("menu") == ["keys:menu"]
    assert markers("multiplayer") == ["keys:web"]


def test_quickstart_stays_short_and_names_both_sides():
    prose = [b for b in _blocks("quickstart", "en") if not b.marker]
    words = sum(len(manual.plain(" ".join([b.text, *b.items, *(" ".join(r) for r in b.rows)])).split())
                for b in prose)
    assert words <= 1500, words
    anchors = [b.anchor for b in _blocks("quickstart", "en") if b.kind == "heading"]
    assert {"qs-first-patrol", "qs-first-dive", "qs-controls"} <= set(anchors)


@pytest.mark.parametrize("lang", manual.LANGUAGES)
def test_generated_tables_follow_help_tables_and_catalogs(lang):
    catalog = load_catalog(lang)
    for station, keys in STATION_SOP.items():
        assert keys and all(key in catalog and catalog[key] for key in keys)
    tr = Translator(lang).t
    table = next(b for b in _blocks("quickstart", lang) if b.marker == "keys:global")
    assert table.rows == tuple((tr(key), tr(action)) for key, action in _GLOBAL_HELP[1])
    for chapter in manual.CHAPTERS:
        for block in _blocks(chapter, lang):
            assert "help." not in block.text and all(
                not str(cell).startswith("help.") for row in block.rows for cell in row)


def test_marker_expansion_uses_a_custom_translator():
    blocks = manual.chapter_blocks("sonar", "en", tr=lambda key: f"<{key}>")
    table = next(b for b in blocks if b.marker == "keys:sonar")
    assert table.header == ("<help.manual.key>", "<help.manual.action>")
    with pytest.raises(manual.ManualError):
        manual.parse("<!-- keys:nowhere -->", str)
    with pytest.raises(manual.ManualError):
        manual.parse("## Heading without anchor", str)


@pytest.mark.parametrize("lang", manual.LANGUAGES)
def test_docs_export_is_current(lang):
    exported = (ROOT / "docs" / "manual" / f"manual.{lang}.md").read_text(encoding="utf-8")
    assert exported == manual.markdown(lang), "run python tools/build_manual.py"


@pytest.mark.parametrize("width", [40, 64, 86, 120])
def test_text_lines_are_width_bounded_for_the_ingame_reader(width):
    for lang in manual.LANGUAGES:
        for chapter in manual.CHAPTERS:
            lines = manual.text_lines(_blocks(chapter, lang), width)
            assert lines and all(len(line) <= width for line in lines), (chapter, lang)
            assert not any("`" in line or "**" in line for line in lines)


def test_ascii_diagrams_fit_the_1280x720_reader():
    for lang in manual.LANGUAGES:
        for chapter in manual.CHAPTERS:
            for block in _blocks(chapter, lang):
                if block.kind == "pre":
                    assert max(map(len, block.text.split("\n"))) <= 76, chapter


# Documented numbers that must follow the implementation. Each row is
# (value rendered as in the text, chapters that must contain it).
def _documented_numbers():
    torpedoes = {entry["key"]: entry for entry in json.loads(
        (ROOT / "data" / "contacts" / "torpedoes.json").read_text())["entries"]}
    return [
        (f"{config.SONAR_PASSIVE_BASE_NM:.0f}", ("reference",)),
        (f"{config.SONAR_ACTIVE_BASE_NM:.0f}", ("reference",)),
        (f"{config.SONAR_PING_COOLDOWN_S:.0f} s", ("reference", "helicopter")),
        (f"{config.SONAR_PING_HEAR_RANGE_NM:.0f}", ("sonar", "reference")),
        (f"{config.CAVITATION_KN:.0f} kn", ("engine", "reference")),
        (f"{config.SONAR_TOWED_DEPLOY_S:.0f} s", ("sonar", "reference")),
        (f"{config.SONAR_TOWED_RETRIEVE_S:.0f} s", ("sonar", "reference")),
        (f"{config.SONAR_TOWED_HANDLING_MIN_KN:.0f}-{config.SONAR_TOWED_HANDLING_MAX_KN:.0f} kn",
         ("sonar", "reference")),
        (f"{config.SONAR_TOWED_MAX_SAFE_KN:.0f} kn", ("sonar", "engine")),
        (f"{config.SONAR_TOWED_DEPTH_MIN_M:.0f}-{config.SONAR_TOWED_DEPTH_MAX_M:.0f} m",
         ("sonar", "reference")),
        (f"{config.TMA_MIN_SPAN_S:.0f} s", ("sonar",)),
        (f"{torpedoes['frigate_torp']['speed_kn']:.0f} kn", ("weapons", "reference")),
        (f"{torpedoes['helo_torp']['speed_kn']:.0f} kn", ("helicopter", "reference")),
        (f"{torpedoes['enemy_torp']['speed_kn']:.0f} kn", ("reference",)),
        (f"{config.RADAR_SURFACE_RANGE_NM:.0f}", ("opz", "reference")),
        (f"{config.RADAR_AIR_RANGE_NM:.0f}", ("opz", "reference")),
        (f"{config.HFDF_RANGE_NM:.0f}", ("radio", "reference")),
        (f"{config.ESM_RANGE_NM:.0f}", ("eloka", "reference")),
        (f"{config.HELO_LAUNCH_WIND_MAX_KN:.0f} kn", ("helicopter",)),
        (f"{config.HELO_DIP_PASSIVE_RANGE_NM:.0f}", ("helicopter", "reference")),
        (f"{config.BUOY_RANGE_NM:.0f}", ("helicopter", "reference")),
        (f"{config.MISSION_ESCAPE_RADIUS_NM:.0f}", ("quickstart", "reference")),
        (f"{config.SCORE_SUNK}", ("quickstart", "reference")),
        (f"{config.TORP_MAX_IN_AIR[config.TORP_DOCTRINE]}", ("weapons",)),
        (f"{config.DMG_DESTROY_FLOOD:.0f} %", ("damage",)),
    ]


@pytest.mark.parametrize("value,chapters", _documented_numbers())
def test_documented_numbers_match_the_implementation(value, chapters):
    for lang in manual.LANGUAGES:
        for chapter in chapters:
            text = "\n".join(manual.text_lines(_blocks(chapter, lang), 400))
            assert value in text, (value, chapter, lang)


def test_telegraph_orders_in_reference_match_config():
    text = "\n".join(manual.text_lines(_blocks("reference", "en"), 400))
    row = ", ".join(f"{name} {speed:.0f}" for name, speed in config.TELEGRAPH_ORDERS)
    assert row in text


# --- Key coverage: every station binding in Game._handle_owned_event (and its
# ``_owned_*`` parts) must be documented in src/core/help.py (and therefore in
# F1, manual, and web page).

_KEY_TOKENS = {
    "K_UP": ("Up",), "K_DOWN": ("Down",), "K_LEFT": ("<-", "←", "Left"),
    "K_RIGHT": ("->", "→", "Right"), "K_PAGEUP": ("Page",), "K_PAGEDOWN": ("Page",),
    "K_RETURN": ("Enter",), "K_KP_ENTER": ("Enter",), "K_BACKSPACE": ("Backspace",),
    "K_DELETE": ("Delete",), "K_SPACE": ("Space",), "K_COMMA": (",",),
    "K_PERIOD": (".",), "K_EQUALS": ("+",), "K_PLUS": ("+",), "K_KP_PLUS": ("+",),
    "K_MINUS": ("-",), "K_KP_MINUS": ("-",), "K_TAB": ("Tab",),
}
# Bindings intentionally not listed per station (documented elsewhere).
_EXEMPT = {
    ("OPZ", "K_RIGHT"), ("OPZ", "K_LEFT"),  # "<- / ->" row for ASM tracks
}


def _refs(test, prefix):
    """Names referenced positively (is / == / in) in an if-test."""
    names = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Compare) and any(
                isinstance(op, (ast.IsNot, ast.NotEq, ast.NotIn)) for op in node.ops):
            continue
        if isinstance(node, ast.Compare):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                        and sub.value.id == prefix[0] and sub.attr.startswith(prefix[1])):
                    names.add(sub.attr)
    return names


def _station_bindings():
    # The event owner lives in the EventMixin module since plan 1.3, phase 2.
    source = (ROOT / "src" / "core" / "game_events.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    # The owner and its verbatim parts (``_owned_*``), each visited alone.
    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                and (node.name == "_handle_owned_event" or node.name.startswith("_owned_"))]
    assert len(handlers) > 1
    pairs = set()

    def visit(statements, stations, keys):
        for statement in statements:
            if isinstance(statement, ast.If):
                here_stations = stations | _refs(statement.test, ("Station", ""))
                here_keys = keys | _refs(statement.test, ("pygame", "K_"))
                if here_stations and here_keys:
                    pairs.update((s, k) for s in here_stations for k in here_keys)
                visit(statement.body, here_stations, here_keys)
                visit(statement.orelse, stations, keys)
            elif isinstance(statement, (ast.For, ast.While, ast.With, ast.Try)):
                visit(getattr(statement, "body", []), stations, keys)

    for handler in handlers:
        visit(handler.body, set(), set())
    return pairs


def _documented(label, key):
    if key in _KEY_TOKENS:
        return any(token.lower() in label.lower() for token in _KEY_TOKENS[key])
    token = key[2:].upper()
    return re.search(rf"(?<![A-Za-z]){re.escape(token)}(?![a-z])", label) is not None


def test_every_station_key_binding_is_documented_in_help():
    tr = Translator("en").t
    global_labels = [tr(key) for key, _ in _GLOBAL_HELP[1]]
    bindings = _station_bindings()
    assert len(bindings) > 60
    missing = []
    for station_name, key in sorted(bindings):
        if (station_name, key) in _EXEMPT or station_name == "RADAR":
            continue
        station = Station[station_name]
        labels = [tr(label) for label, _ in STATION_HELP[station][1]] + global_labels
        if not any(_documented(label, key) for label in labels):
            missing.append(f"{station_name}: {key}")
    assert not missing, "undocumented station keys (update src/core/help.py):\n" + \
        "\n".join(missing)


# --- Remote Crew web page

@pytest.mark.parametrize("lang", manual.LANGUAGES)
def test_html_manual_is_static_escaped_and_linkable(lang):
    page = manual.html_page(lang)
    assert page.startswith("<!doctype html>") and f'<html lang="{lang}">' in page
    assert "<script" not in page and not re.search(r"<[^>]*\s(style|on[a-z]+)=", page)
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == len(set(ids))
    for chapter in manual.STATION_CHAPTERS.values():
        assert f'id="station-{chapter}"' in page
    for href in re.findall(r'href="#([^"]+)"', page):
        assert href in ids
    assert "<kbd>" in page and '<table class="keys">' in page and 'class="sop"' in page
    assert '<link rel="stylesheet" href="/manual.css">' in page
    # The page shares the crew client's design tokens and fonts.
    assert page.index('href="/css/tokens.css"') < page.index('href="/css/fonts.css"') < page.index('href="/manual.css"')


def test_commander_serves_manual_pages_with_security_headers():
    pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    server = CommanderServer(manual_pages=pages)
    server.start("127.0.0.1", 0)
    try:
        port = server._http.server_address[1]
        for route, expected in (("/manual-en", "text/html"), ("/manual-de", "text/html"),
                                ("/manual.css", "text/css")):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", route)
            response = connection.getresponse()
            body = response.read()
            connection.close()
            assert response.status == 200 and body
            assert response.getheader("Content-Type").startswith(expected)
            assert "script-src 'self'" in response.getheader("Content-Security-Policy")
            assert response.getheader("Cache-Control") == "no-store"
    finally:
        server.stop()
    for invalid in ({"fr": "x"}, {"en": ""}, {"en": b"x"}, ["en"]):
        with pytest.raises(ValueError):
            CommanderServer(manual_pages=invalid)


def test_the_submarine_chapter_carries_every_boat_station_procedure():
    from src.core.help import UBOOT_SOP, UBOOT_SOP_SLUGS
    for lang in manual.LANGUAGES:
        catalog = load_catalog(lang)
        blocks = _blocks("submarine", lang)
        markers = [b.marker for b in blocks if b.marker and b.kind != "figure"]
        assert markers == ["keys:uboot_global"] + [f"sop:uboot_{slug}"
                                                   for slug in UBOOT_SOP_SLUGS.values()] + ["keys:uboot"]
        for station, keys in UBOOT_SOP.items():
            assert len(keys) == 5 and all(catalog.get(key) for key in keys), station
            block = next(b for b in blocks if b.marker == f"sop:uboot_{UBOOT_SOP_SLUGS[station]}")
            assert block.items == tuple(catalog[key] for key in keys)
    text = "\n".join(manual.text_lines(_blocks("submarine", "en"), 400))
    assert f"{config.UBOOT_GPS_FIX_S:.0f} s" in text
    assert f"{config.UBOOT_DR_DRIFT_KN:.1f} kn" in text
    assert f"{config.UBOOT_DR_ERROR_MAX_NM:.0f} NM" in text


def test_f1_on_the_submarine_side_shows_the_station_procedure_and_chapter():
    from src.core.game import Game
    game = Game(seed=7, start_menu=False, audio_enabled=False, language="en")
    game.local_side = "uboot"
    game.uboot_station = "uboot_nav"
    game._open_administration("help")
    assert manual.CHAPTERS[game.help_manual_chapter] == "submarine"
    game.help_page = 1
    lines, _visible = game._help_lines()
    text = " ".join(lines)
    assert "Standard procedure" in text
    assert Translator("en").t("help.sop.uboot.nav.2")[:30] in text


def test_every_manual_figure_has_a_screenshot_in_both_languages():
    root = Path(__file__).resolve().parents[1] / "docs" / "manual" / "figures"
    names = set()
    for chapter in manual.CHAPTERS:
        for lang in manual.LANGUAGES:
            for block in _blocks(chapter, lang):
                if block.kind == "figure":
                    names.add(manual.figure_name(block))
                    assert (root / manual.figure_file(manual.figure_name(block), lang)).is_file()
    # Every frigate station and every submarine station is pictured.
    assert {f"station-{s}" for s in ("bridge", "sonar", "weapons", "damage-control",
                                     "opz-cic", "radio", "engineering", "helicopter",
                                     "eloka")} <= names
    assert {f"uboot-{s}" for s in ("command", "sonar", "weapons", "engine",
                                   "mast-esm", "navigation", "radio")} <= names


def test_figures_stay_out_of_the_reader_and_web_page_but_reach_markdown_and_pdf():
    blocks = _blocks("bridge", "en")
    assert any(b.kind == "figure" for b in blocks)
    assert "figure:" not in "\n".join(manual.text_lines(blocks, 120))
    assert "<img" not in manual.html_page("en")
    assert '<img src="file:///x/station-bridge.png"' in manual.html_page("en", "file:///x")
    assert "](figures/de-station-bridge.png)" in manual.markdown("de")
    with pytest.raises(manual.ManualError):
        manual.parse("![caption](figure:Bad Name)", lambda key: key)


def test_reader_digits_open_the_quickstart_and_the_station_chapters():
    import pygame
    from src.core.game import Game
    from src.core.game_shared import HELP_MANUAL_PAGE
    game = Game(seed=7, start_menu=False, audio_enabled=False, language="en")
    game._open_administration("help")
    game.help_page = HELP_MANUAL_PAGE
    for digit, chapter in ((0, "quickstart"), (1, "bridge"), (3, "weapons"), (9, "eloka")):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0 + digit, mod=0,
                                             unicode=str(digit), scancode=0))
        assert manual.CHAPTERS[game.help_manual_chapter] == chapter
