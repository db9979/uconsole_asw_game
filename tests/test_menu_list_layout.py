"""Start-menu pages never overlap or run off the 1280x720 canvas.

Every centred menu line, list row and note is traced with its glyph box
(``layout.capture_text``); on each page, in English and German, with normal
and large text, and with the extra footer line of a fixed real sector, no
two lines may overlap and none may leave the screen. The scenario lists and
the own-missions list scroll, so the check also runs with far more entries
than the game ships today.
"""

from __future__ import annotations

import itertools

import pygame
import pytest

from src.core import config
from src.core import game_custom, game_draw
from src.core import habits as habit_model
from src.core import logbook as logbook_model
from src.core.game import Game
from src.core.preferences import Preferences
from src.ui import layout, menu_list

SCREEN = pygame.Rect(0, 0, config.SCREEN_W, config.SCREEN_H)


class _Record:
    def __init__(self, index: int):
        self.key = f"user.mission_{index}"
        self.data = {"name": f"Own mission number {index + 1} with a long name",
                     "description": "A long description of the mission. " * 8}


@pytest.fixture(autouse=True)
def _no_backdrop(monkeypatch):
    # The dimmed night-hunt scene (and its hull number) lies behind the
    # menu on purpose; only the menu's own lines are checked.
    monkeypatch.setattr(game_draw, "draw_menu_backdrop", lambda surface, t: None)


def _game(language: str, large: bool) -> Game:
    prefs = Preferences(language=language, fullscreen=False, audio=False,
                        large_text=large)
    game = Game(seed=22, start_menu=True, show_splash=False, preferences=prefs)
    game.splash_active = False
    game.main_menu = False
    return game


def _overlaps(game: Game) -> list:
    game._t = 5.0
    with layout.capture_text() as traced:
        game.draw()
    problems = []
    for item in traced:
        if not SCREEN.contains(item["ink"]):
            problems.append(f"off screen: {item['text']!r} {item['ink']}")
    for a, b in itertools.combinations(traced, 2):
        if a["ink"].colliderect(b["ink"]):
            problems.append(f"overlap: {a['text']!r} {a['ink']} / {b['text']!r} {b['ink']}")
    return problems


def _pages(game: Game):
    """(name, setup) for every list page of the start menu."""
    for side in ("frigate", "uboot"):
        rows = None

        def scenario(sel, side=side):
            game.local_side = side
            game.menu_screen = "scenario"
            game.menu_sel = sel
        game.local_side = side
        rows = game.scenario_menu_rows()
        for sel in rows:
            yield f"scenario-{side}-{sel}", lambda sel=sel, f=scenario: f(sel)
        for key in config.scenarios_for_side(side):
            def briefing(key=key, side=side):
                game.local_side = side
                game.menu_screen = "briefing"
                game.scenario_key = key
                game.menu_sel = 0
            yield f"briefing-{key}", briefing
        for count, sel in ((0, 0), (40, 0), (40, 20), (40, 39)):
            def custom(count=count, sel=sel, side=side):
                game.local_side = side
                game._custom_records = [_Record(i) for i in range(count)]
                game.menu_screen = game_custom.CUSTOM_SCREEN
                game.menu_sel = sel
            yield f"custom-{side}-{count}-{sel}", custom
    for sel in range(len(config.DIFFICULTY_FIELD_ORDER) + 1):
        def difficulty(sel=sel):
            game.menu_screen = "difficulty"
            game.menu_sel = sel
        yield f"difficulty-{sel}", difficulty
    def full_logbook(side="frigate"):
        book = logbook_model.Logbook()
        for i, key in enumerate(config.SCENARIO_ORDER * 2):
            book_side = "frigate" if config.scenario_side(key) == "frigate" else "boat"
            # Every habit known (src/core/habits.py): the longest line.
            book.record(date="2026-10-02", side=book_side, scenario=key,
                        level="realistic", won=i % 2 == 0, score=900 + i, minutes=95,
                        shots=3, sunk=1, earned=[], advisor=i % 3 == 0,
                        habits=list(habit_model.HABITS[book_side]))
        game.logbook_view = book
        game.logbook_side = side
        game.menu_screen = "logbook"
    yield "logbook-full", full_logbook
    yield "logbook-full-boat", lambda: full_logbook("boat")
    from dataclasses import replace

    from src.core import training
    for done, sel in ((training.LESSONS[:4], 4), (training.LESSONS, len(training.LESSONS) - 1)):
        def lessons(done=done, sel=sel):
            # Ticks, the "next" mark and the progress line, scrolled to the end.
            game.preferences = replace(game.preferences, lessons_done=tuple(done))
            game.menu_screen = "training"
            game.menu_sel = sel
        yield f"training-{len(done)}-{sel}", lessons
    for screen in ("side", "training", "logbook", "daily", "campaign"):
        def page(screen=screen):
            game.menu_screen = screen
            game.menu_sel = 0
        yield screen, page


@pytest.mark.parametrize("language,large", [("en", False), ("de", False),
                                            ("en", True), ("de", True)])
def test_menu_pages_never_overlap_or_leave_the_screen(language, large):
    game = _game(language, large)
    problems = []
    for world_mode in ("procedural", "real_fixed"):
        game.world_mode = world_mode
        for name, setup in _pages(game):
            setup()
            problems += [f"{world_mode} {name}: {p}" for p in _overlaps(game)]
    pygame.quit()
    assert not problems, "\n".join(problems[:40])


def test_scenario_list_scrolls_with_many_more_missions(monkeypatch):
    """Future missions: a list three times today's length still fits."""
    game = _game("de", True)
    extra = tuple(f"extra_{i}" for i in range(2 * len(config.SCENARIO_ORDER)))
    order = config.SCENARIO_ORDER + extra
    monkeypatch.setattr(config, "SCENARIO_ORDER", order)
    monkeypatch.setattr(config, "SCENARIOS", {
        **config.SCENARIOS, **{key: config.SCENARIOS["s1_patrouille"] for key in extra}})
    monkeypatch.setattr(config, "SCENARIO_NAMES", {
        **config.SCENARIO_NAMES, **{key: "patrol" for key in extra}})
    real_side = config.scenario_side
    monkeypatch.setattr(config, "scenario_side",
                        lambda key: "frigate" if key in extra else real_side(key))
    game.local_side = "frigate"
    game.menu_screen = "scenario"
    rows = game.scenario_menu_rows()
    assert len(rows) > 3 * game_custom.SCENARIO_ROWS
    problems = []
    for sel in (rows[0], rows[len(rows) // 2], rows[-2], rows[-1]):
        game.menu_sel = sel
        problems += _overlaps(game)
    # Down from the first row reaches the last one, End jumps there.
    game.menu_sel = rows[0]
    for _ in range(len(rows) - 1):
        game._handle_menu_key(pygame.K_DOWN)
    assert game.menu_sel == rows[-1]
    game._handle_menu_key(pygame.K_HOME)
    assert game.menu_sel == rows[0]
    game._handle_menu_key(pygame.K_PAGEDOWN)
    assert game.menu_sel == rows[game_custom.SCENARIO_ROWS - 1]
    game._handle_menu_key(pygame.K_END)
    assert game.menu_sel == game.custom_row_sel()
    pygame.quit()
    assert not problems, "\n".join(problems[:40])


def test_list_window_follows_the_selection():
    assert menu_list.first_row(5, 4, 9) == 0
    assert menu_list.first_row(13, 0, 9) == 0
    assert menu_list.first_row(13, 6, 9) == 2
    assert menu_list.first_row(13, 12, 9) == 4
    for count, rows in ((13, 9), (40, 9), (3, 9)):
        for sel in range(count):
            first = menu_list.first_row(count, sel, rows)
            assert first <= sel < first + rows
            assert 0 <= first <= max(0, count - rows)
    assert menu_list.page_step(13, 0, 9, 1) == 8
    assert menu_list.page_step(13, 8, 9, 1) == 12
    assert menu_list.page_step(13, 3, 9, -1) == 0


def test_browser_new_game_list_names_every_scenario_and_has_room_for_more():
    """The solo browser's scenario list: a name for each mission (no
    "unknown" row) and a host-view bound well above today's count."""
    import json
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    host = (root / "data/commander/js/views/host.js").read_text(encoding="utf-8")
    table = host[host.index("export const scenarioText"):]
    table = table[:table.index("};")]
    names = dict(re.findall(r"(\w+): \"(scenario_\w+)\"", table))
    catalogs = {lang: json.loads((root / f"data/i18n/{lang}.json").read_text(encoding="utf-8"))
                for lang in ("en", "de")}
    for key in config.SCENARIO_ORDER:
        assert key in names, key
        for catalog in catalogs.values():
            assert "commander.web." + names[key] in catalog, (key, names[key])
    net = (root / "data/commander/js/net/host.js").read_text(encoding="utf-8")
    bound = int(re.search(r"boundedArray\(value\.scenarios, (\d+)\)", net).group(1))
    assert bound >= 4 * len(config.SCENARIO_ORDER)


@pytest.mark.parametrize("language,large", [("en", False), ("de", False),
                                            ("en", True), ("de", True)])
def test_language_model_settings_pages_never_overlap(language, large):
    """Options page 2, Language model: all its pages (model, voice, sound,
    log reports, speech input), with the longest values (the shared key, a failed voice
    test, a busy station's count)."""
    import dataclasses
    game = _game(language, large)
    game.preferences = dataclasses.replace(
        game.preferences, tts_enabled=True, llm_enabled=True,
        tts_url="https://speech.example-provider.internal.example.com/v1",
        llm_url="https://speech.example-provider.internal.example.com/v1",
        tts_voice="shimmer", llm_coach="often", tts_seed=2147483647, tts_temperature=1.95,
        stt_enabled=True, stt_url="https://speech.example-provider.internal.example.com/v1",
        stt_model="gpt-4o-mini-transcribe")
    game._voice_key_source = "shared"
    game._stt_key_source = "shared"
    from src.ui.advisor_view import PANEL, draw_llm_settings
    game._open_administration("llm")
    problems = []
    import time
    game._log_voice_seen.extend((time.monotonic(), "schaden") for _ in range(188))
    for page in (0, 1, 2, 3, 4):
        game.set_llm_page(page)
        for test in (None, dict(status="failed", error="rate_limit")):
            game.voice_test = test
            game.llm_test = test
            game.stt_test = test
            for sel in (0, 7, 9):
                game.llm_sel = sel
                game._t = 5.0
                with layout.capture_text() as traced:
                    draw_llm_settings(game)
                for item in traced:
                    if not PANEL.contains(item["ink"]):
                        problems.append(f"page {page}: outside the panel {item['text']!r}")
                for a, b in itertools.combinations(traced, 2):
                    if a["ink"].colliderect(b["ink"]):
                        problems.append(f"page {page} sel {sel}: overlap {a['text']!r} "
                                        f"{a['ink']} / {b['text']!r} {b['ink']}")
    pygame.quit()
    assert not problems, "\n".join(problems[:40])
