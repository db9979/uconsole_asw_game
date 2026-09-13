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


def test_native_detail_lists_each_sensor_and_emitter_field():
    analyzer = ContactAnalyzer(tr=Translator("en").t,
                               packaged_assets=load_contact_analysis_assets())
    selected = next(index for index, profile in enumerate(analyzer.profiles)
                    if profile["components"]["sensors"]
                    and profile["components"]["emitters"])
    analyzer.filtered = [selected]
    analyzer.listbox.selected = 0
    lines = "\n".join(analyzer._detail_lines())
    for label in ("Sensor", "Emitter", "Domain", "Modes", "Emits",
                  "Synthetic range", "Sensitivity", "Cadence",
                  "Bearing uncertainty", "Range uncertainty",
                  "Depth uncertainty", "Frequency band", "PRF band",
                  "Modulation"):
        assert label in lines


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


def test_f8_opens_analyzer_in_running_game_and_esc_returns_to_game():
    from src.core.game import Game

    game = Game(seed=811, start_menu=False, audio_enabled=False)
    assert not game.in_menu and game.editor is None
    before = game.sim_t
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_F8, unicode="", mod=0))
    assert isinstance(game.editor, ContactAnalyzer)
    assert not game.in_menu and not game.main_menu
    game.update(1.0)
    assert game.sim_t == before  # Simulation steht waehrend der TUA offen ist
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_F8, unicode="", mod=0))
    assert isinstance(game.editor, ContactAnalyzer)  # kein Re-Entry
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
    assert game.editor is None
    assert not game.in_menu and not game.main_menu
    game.update(1.0)
    assert game.sim_t > before  # Simulation laeuft wieder


def test_f8_analyzer_keeps_active_remote_crew_phase_live():
    from src.core.game import Game

    game = Game(seed=811, start_menu=False, audio_enabled=False)
    game.commander.active_crew = True
    game._open_analyzer_in_game()
    assert isinstance(game.editor, ContactAnalyzer)
    assert game.commander.bridge._phase(game) == "live"
    assert game.commander.bridge._phase(game, local=True) == "blocked"


def test_f8_keeps_commander_confirmation_priority(monkeypatch):
    from src.core.game import Game

    game = Game(seed=811, start_menu=False, audio_enabled=False)
    game.commander.confirm_kind = "target"
    game.commander._confirm_suppressed = None
    monkeypatch.setattr(game.commander, "confirm_visible", lambda _game: True)
    monkeypatch.setattr(game.commander, "handle_confirm_key",
                        lambda _game, key: key == pygame.K_F8)
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_F8, unicode="", mod=0))
    assert game.editor is None  # F8 bleibt der Bestaetigungsbox vorbehalten


def test_audio_sample_button_and_space_play_the_shown_mode():
    pygame.init()
    calls, stops = [], []

    def record(*args):
        calls.append(args)

    def record_stop():
        stops.append(1)

    analyzer = ContactAnalyzer(on_play_sample=record,
                               on_stop_sample=record_stop)
    analyzer._set_filter("diesel_alt")
    screen = pygame.Surface((1280, 720))
    analyzer.draw(screen)
    profile = analyzer.selected_profile
    assert profile["key"] == "diesel_alt"
    rect = analyzer._rects.get("audio_sample")
    assert rect is not None
    assert screen.get_rect().contains(rect)
    kinds = analyzer._asset_kinds()
    assert analyzer.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ", mod=0)) is True
    assert calls and calls[0] == (profile["key"], kinds[0], profile["machine"])
    assert stops == []
    # Zweiter Space-Klick stoppt die laufende Hörprobe wieder.
    assert analyzer.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ", mod=0)) is True
    assert len(calls) == 1 and len(stops) == 1
    # Button-Klick startet die Hörprobe neu.
    assert analyzer.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)) is True
    assert len(calls) == 2 and len(stops) == 1
    pygame.quit()


def test_audio_sample_hidden_and_inert_without_audio_or_callback():
    pygame.init()
    calls = []
    analyzer = ContactAnalyzer(on_play_sample=calls.append)
    analyzer._set_filter("frigate_torp")
    screen = pygame.Surface((1280, 720))
    analyzer.draw(screen)
    assert analyzer._rects.get("audio_sample") is None
    assert analyzer.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ", mod=0)) is False
    assert calls == []
    bare = ContactAnalyzer()
    bare._set_filter("diesel_alt")
    bare.draw(screen)
    assert bare._rects.get("audio_sample") is None
    assert bare.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" ", mod=0)) is False
    pygame.quit()


def test_game_wires_the_analyzer_audio_sample(monkeypatch):
    from src.core.game import Game

    game = Game(seed=811, start_menu=True, audio_enabled=False)
    game.main_menu_sel = 4
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_RETURN, unicode="", mod=0))
    analyzer = game.editor
    assert isinstance(analyzer, ContactAnalyzer)
    assert analyzer.on_play_sample.__func__ is game._play_unit_audio.__func__
    assert analyzer.on_play_sample.__self__ is game
    calls = []
    monkeypatch.setattr(game.audio, "play_unit_preview",
                        lambda synth, key, volume=0.9: calls.append((key, volume)))
    analyzer._set_filter("diesel_alt")
    assert analyzer._play_sample()
    assert len(calls) == 1
    key, volume = calls[0]
    assert key[0] == "sonar" and key[1] == "unit_preview"
    profile = analyzer.selected_profile
    assert key[2] == profile["key"]
    assert key[3] in analyzer._asset_kinds()
    assert key[4] == game.audio.sample_rate
    game.handle_event(pygame.event.Event(
        pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode="", mod=0))
    assert game.editor is None and game.main_menu
