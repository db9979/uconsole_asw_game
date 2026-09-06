from types import SimpleNamespace as NS

from src.core import config
from src.core.commands import SONAR_PAGE_COUNT, sonar_page_step, toggle_tas
from src.core.help import get_help
from src.core.station import Station


def test_sonar_page_command_includes_active_page():
    assert SONAR_PAGE_COUNT == config.SONAR_PAGE_COUNT == 6
    assert sonar_page_step(4, 1) == 5
    assert sonar_page_step(5, 1) == 0


def test_tas_command_uses_public_api_and_reports_handling_pause():
    calls, flashes = [], []

    class Sonar:
        def toggle_tow(self, speed):
            calls.append(speed)
            return True

        def tow_status(self, speed):
            return dict(state="DEPLOYING", handling_ok=False)

    game = NS(sonar=Sonar(), ship=NS(speed=14.),
              flash=lambda text, duration: flashes.append((text, duration)))
    assert toggle_tas(game)
    assert calls == [14.]
    assert flashes == [("TAS ausbringen | Fahrt 3-12 kn erforderlich", 2.0)]


def test_sonar_help_has_tas_command_active_page_and_translation_hook():
    _, controls, parameters, _ = get_help(Station.SONAR)
    assert ("Y", "TAS ausbringen / einholen (nur bei 3-12 kn)") in controls
    assert any("ACTIVE" in action for _, action in controls)
    assert any("Echo-Messungen" in text for text in parameters)

    intro, translated, _, _ = get_help(Station.SONAR, lambda text: f"tr:{text}")
    assert intro.startswith("tr:")
    assert all(key.startswith("tr:") and action.startswith("tr:")
               for key, action in translated)


def test_game_y_toggles_tas_without_force_selecting_array():
    import pygame
    from src.core.game import Game

    game = Game(seed=55, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_mode = "BOW"
    game.ship.speed = 6.0
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_y))
    assert game.sonar.tow_status()["state"] == "DEPLOYING"
    assert game.sonar_mode == "BOW"
    assert game.feed.recent(1)


def test_unavailable_towed_ping_has_no_side_effects(monkeypatch):
    import pygame
    from src.core.game import Game

    game = Game(seed=56, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    game.sonar_mode = "TOWED"
    flashes, sounds = [], []
    monkeypatch.setattr(game, "flash", lambda *args: flashes.append(args))
    monkeypatch.setattr(game.audio, "play_ping", lambda: sounds.append(True))
    target = NS(hear_ping=lambda: (_ for _ in ()).throw(
        AssertionError("unavailable TOWED ping notified a target")))
    monkeypatch.setattr(game, "_sonar_targets", lambda: [target])

    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))

    assert game.sonar.ping_cooldown == 0.0
    assert not game.sonar.ping_active
    assert flashes == []
    assert sounds == []


def test_main_menu_mission_editor_has_no_legacy_builtins_and_enter_is_safe():
    import pygame
    from src.core.game import Game
    from src.ui.mission_editor import MissionEditor

    game = Game(seed=57, start_menu=True, audio_enabled=False)
    game.main_menu_sel = 2
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert isinstance(game.editor, MissionEditor)
    assert game.editor.builtins == {}
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
