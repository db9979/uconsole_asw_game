"""The game window (src/ui/window.py): pygame's display window everywhere
but the Mac, where an SDL window with the Retina screen's real pixels
shows the canvas through a renderer."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.ui import hires, layout, window


@pytest.fixture(autouse=True)
def _plain_afterwards():
    yield
    if window._RETINA is not None:
        window._RETINA.close()
    hires.deactivate()
    layout.clear_font_cache()


def _game(monkeypatch, retina: bool, size=(1280, 720)):
    monkeypatch.setenv(window.RETINA_ENV, "1" if retina else "0")
    return Game(seed=11, show_splash=False, audio_enabled=False,
                start_menu=False, window_size=size)


def test_the_mac_gets_the_retina_window():
    assert window.wants_retina("darwin", {})
    assert not window.wants_retina("darwin", {window.NO_RETINA_ENV: "1"})
    assert not window.wants_retina("win32", {})
    assert not window.wants_retina("linux", {})
    assert window.wants_retina("linux", {window.RETINA_ENV: "1"})


def test_other_systems_keep_pygames_display(monkeypatch):
    game = _game(monkeypatch, retina=False)
    assert game.window.kind == "display"
    assert pygame.display.get_surface() is not None
    assert window.live_token() is None


def test_retina_window_shows_the_same_picture(monkeypatch):
    plain = _game(monkeypatch, retina=False)
    plain.draw()
    expected = plain.screen.copy()
    game = _game(monkeypatch, retina=True)
    assert game.window.kind == "retina"
    assert game.window.size() == (1280, 720)
    game.draw()
    game.compose_frame()
    shown = game.window.renderer.to_surface()
    assert shown.get_size() == (1280, 720)
    for point in ((5, 5), (640, 360), (1000, 600), (200, 650)):
        assert shown.get_at(point)[:3] == expected.get_at(point)[:3], point
    # The font cache lives with the window while no display surface exists.
    assert window.live_token() is game.window.window
    assert layout.font(18) is layout.font(18)


def test_retina_pixels_draw_a_sharper_canvas(monkeypatch):
    game = _game(monkeypatch, retina=True)
    # A Retina screen: the window counts points, the renderer twice the pixels.
    monkeypatch.setattr(window.RetinaWindow, "pixel_size", lambda self: (2560, 1440))
    game.draw()
    assert hires.k_of(game.screen) == 2
    game.compose_frame()
    assert game.window._texture_size == (2560, 1440)
    # The mouse keeps window coordinates.
    assert game._window_to_canvas((640, 360)) == (640, 360)


def test_retina_window_switches_fullscreen_and_title(monkeypatch):
    game = _game(monkeypatch, retina=True)
    game.toggle_fullscreen(persist=False)
    assert game.fullscreen
    game.toggle_fullscreen(persist=False)
    assert not game.fullscreen
    assert game.window.size() == (config.SCREEN_W, config.SCREEN_H)
    game.window.set_title("U-Jagd")
    assert game.window.window.title == "U-Jagd"


def test_the_mac_bundle_carries_the_window_icon():
    # pygame's SDL window loads this icon; without it the window fails to open.
    from pathlib import Path
    spec = (Path(__file__).resolve().parents[1] / "packaging" / "macos"
            / "u-jagd-macos.spec").read_text(encoding="utf-8")
    assert '"pygame_icon.bmp"), "pygame")' in spec
