import ast
from pathlib import Path

import pygame
import pytest

from src.core.i18n import Translator, pseudolocale
from src.data.contact_analysis import load_contact_analysis_assets
from src.ui import layout
from src.ui.contact_analyzer import ContactAnalyzer, MAX_FILTER_CHARS, SURFACE_CACHE_SIZE


def test_analyzer_source_has_no_live_game_or_observation_dependencies():
    source = Path("src/ui/contact_analyzer.py").read_text(encoding="utf-8")
    imports = {alias.name for node in ast.walk(ast.parse(source))
               if isinstance(node, (ast.Import, ast.ImportFrom))
               for alias in node.names}
    assert not any(name.startswith(("src.core.game", "src.ui.observations",
                                    "src.sensors", "src.ship", "src.enemies",
                                    "src.air", "src.weapons")) for name in imports)
    assert "project_contact_catalog" in source


def test_filter_selection_images_and_internal_detail_scroll_are_bounded(monkeypatch):
    pygame.init()
    loads = []
    original_load = pygame.image.load

    def tracked_load(*args, **kwargs):
        loads.append(args[1])
        return original_load(*args, **kwargs)

    monkeypatch.setattr(pygame.image, "load", tracked_load)
    analyzer = ContactAnalyzer(packaged_assets=load_contact_analysis_assets())
    assert loads
    initialized_loads = len(loads)
    screen = pygame.Surface((1280, 720))
    analyzer.draw(screen)
    assert len(loads) == initialized_loads

    for char in "warship_":
        analyzer.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=ord(char), unicode=char, mod=0))
    assert analyzer.filter_text == "warship_"
    assert analyzer.filtered
    assert all("warship_" in profile["key"]
               for profile in (analyzer.profiles[index] for index in analyzer.filtered))
    analyzer.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_TAB, unicode="", mod=0))
    for _ in range(40):
        analyzer.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_DOWN, unicode="", mod=0))
    assert 0 < analyzer.detail_scroll <= len(analyzer._detail_lines())

    analyzer.focus = "list"
    for _ in range(min(12, len(analyzer.filtered) - 1)):
        analyzer.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_DOWN, unicode="", mod=0))
    assert len(analyzer.surface_cache) <= SURFACE_CACHE_SIZE
    analyzer._set_filter("x" * (MAX_FILTER_CHARS + 20))
    assert len(analyzer.filter_text) == MAX_FILTER_CHARS
    pygame.quit()


@pytest.mark.parametrize("translator", [
    Translator("en"), Translator("de"),
    Translator("en", catalog=pseudolocale()),
])
@pytest.mark.parametrize("large_text", [False, True])
def test_analyzer_draws_1280x720_localized_and_large_text(translator, large_text):
    pygame.init()
    layout.configure_for(large_text=large_text)
    analyzer = ContactAnalyzer(tr=translator.t)
    screen = pygame.Surface((1280, 720))
    analyzer.draw(screen)
    assert screen.get_clip() == pygame.Rect(0, 0, 1280, 720)
    assert screen.get_rect().contains(analyzer._rects["list"])
    assert screen.get_rect().contains(analyzer._rects["detail"])
    assert screen.get_rect().contains(analyzer._rects["spectrum_legend"])
    assert screen.get_rect().contains(analyzer._rects["hypothesis_legend"])
    assert analyzer._detail_visible > 0
    pygame.quit()


def test_main_menu_analyzer_owns_input_and_blocks_simulation():
    from src.core.game import Game

    game = Game(seed=811, start_menu=True, audio_enabled=False)
    game.main_menu_sel = 4
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, unicode="", mod=0))
    assert isinstance(game.editor, ContactAnalyzer)
    before = game.sim_t
    game.in_menu = False
    game.update(1.0)
    assert game.sim_t == before
    station = game.station
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_2, unicode="2", mod=0))
    assert game.station is station
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
    assert game.editor is None and game.main_menu
