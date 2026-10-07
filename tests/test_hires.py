"""High-resolution drawing in large windows (src/ui/hires.py)."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.ui import hires, layout


@pytest.fixture(autouse=True)
def _plain_afterwards():
    yield
    hires.deactivate()
    layout.clear_font_cache()


def _game(size, **kwargs):
    kwargs.setdefault("start_menu", False)
    return Game(seed=11, show_splash=False, audio_enabled=False,
                window_size=size, **kwargs)


@pytest.mark.parametrize("size, k", [
    ((1280, 720), 1), ((1300, 740), 1), ((1366, 768), 2), ((1920, 1080), 2),
    ((2560, 1440), 2), ((2880, 1800), 3), ((3840, 2160), 3), ((5120, 2880), 3),
])
def test_factor_follows_the_window(size, k):
    assert hires.choose_scale(*size, 1280, 720) == k


def test_low_level_and_switch_keep_plain_pixels(monkeypatch):
    assert hires.choose_scale(2560, 1440, 1280, 720, "low") == 1
    monkeypatch.setenv(hires.DISABLE_ENV, "1")
    assert hires.choose_scale(2560, 1440, 1280, 720) == 1


def test_the_uconsole_screen_never_switches_on():
    game = _game((1280, 720))
    game.draw()
    assert type(game.screen) is pygame.Surface
    assert not hires.ACTIVE
    assert pygame.draw.line is not None and hires._RAW == {}
    assert type(hires.surface((10, 10))) is pygame.Surface


def test_large_window_draws_the_canvas_at_twice_the_pixels():
    game = _game((2560, 1440))
    game.draw()
    assert hires.k_of(game.screen) == 2
    assert game.screen.get_size() == (1280, 720)
    assert hires.physical_size(game.screen) == (2560, 1440)
    # The main canvas stays opaque (no per-pixel alpha).
    assert not game.screen.get_flags() & pygame.SRCALPHA
    game.compose_frame()
    shown = pygame.display.get_surface()
    assert shown.get_size() == (2560, 1440)
    # Something was drawn, not an empty frame.
    assert shown.get_bounding_rect().w > 0


def test_back_to_a_small_window_returns_to_plain_pixels(monkeypatch):
    game = _game((2560, 1440))
    game.draw()
    assert hires.k_of(game.screen) == 2
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game.draw()
    assert hires.k_of(game.screen) == 1
    assert hires.physical_size(game.screen) == (1280, 720)


def _layout_trace(size, station):
    game = _game(size)
    for _ in range(60):
        game.update(0.1)
    game.station = station
    with layout.capture_text() as texts:
        game.draw()
    return [(t["text"], tuple(t["rect"]), tuple(t["bounds"])) for t in texts]


@pytest.mark.parametrize("station", [Station.BRIDGE, Station.SONAR, Station.OPZ,
                                     Station.WEAPONS, Station.DAMAGE])
def test_layout_is_the_same_as_on_the_uconsole(station):
    plain = _layout_trace((1280, 720), station)
    hires.deactivate()
    layout.clear_font_cache()
    sharp = _layout_trace((2560, 1440), station)
    assert hires.SCALE == 2
    assert plain and len(sharp) == len(plain)
    for (text, rect, bounds), (text2, rect2, bounds2) in zip(plain, sharp):
        assert (text2, bounds2) == (text, bounds)
        # Text centred on its visible glyphs may sit one pixel finer.
        assert all(abs(a - b) <= 1 for a, b in zip(rect, rect2)), text


def test_text_measures_logical_and_renders_sharp():
    pygame.display.set_mode((1280, 720))
    plain = layout.font(18)
    hires.set_scale(2)
    sharp = layout.font(18)
    assert isinstance(sharp, hires.HiFont)
    text = "Kurs 300° · Fahrt 12 kn"
    assert sharp.size(text) == plain.size(text)
    assert sharp.get_linesize() == plain.get_linesize()
    image = sharp.render(text, True, (255, 255, 255))
    assert image.get_size() == plain.size(text)
    assert hires.physical_size(image) == tuple(2 * v for v in plain.size(text))
    # The glyphs keep inside their logical box.
    assert image.get_rect().contains(image.get_bounding_rect())


def test_drawing_scales_coordinates_on_a_large_canvas():
    hires.set_scale(2)
    s = hires.surface((100, 50))
    s.fill((0, 0, 0))
    pygame.draw.rect(s, (255, 0, 0), (10, 10, 20, 10))
    raw = pygame.Surface.get_at
    assert raw(s, (20, 20))[:3] == (255, 0, 0)
    assert raw(s, (59, 39))[:3] == (255, 0, 0)
    assert raw(s, (60, 40))[:3] == (0, 0, 0)
    assert s.get_at((15, 15))[:3] == (255, 0, 0)
    pygame.draw.line(s, (0, 255, 0), (0, 40), (99, 40))
    assert raw(s, (100, 80))[:3] == (0, 255, 0)
    assert raw(s, (100, 81))[:3] == (0, 255, 0)
    s.set_clip((0, 0, 50, 50))
    assert s.get_clip() == pygame.Rect(0, 0, 50, 50)
    sub = s.subsurface((10, 10, 20, 10))
    assert sub.get_size() == (20, 10) and hires.k_of(sub) == 2
    # Plain pictures blitted onto it are enlarged to its pixels.
    dot = pygame.Surface((2, 2))
    dot.fill((0, 0, 255))
    s.set_clip(None)
    s.blit(dot, (90, 0))
    assert raw(s, (183, 3))[:3] == (0, 0, 255)


def test_plain_surfaces_are_untouched_after_activation():
    hires.set_scale(2)
    plain = pygame.Surface((20, 20))
    plain.fill((0, 0, 0))
    pygame.draw.rect(plain, (255, 255, 255), (2, 2, 4, 4))
    assert plain.get_bounding_rect(1) == plain.get_rect()
    assert plain.get_at((5, 5))[:3] == (255, 255, 255)
    assert plain.get_at((6, 6))[:3] == (0, 0, 0)


def test_windows_asks_for_real_pixels_and_keeps_the_window_size():
    env = {}
    hires.prepare_platform("win32", env)
    assert env == {"SDL_WINDOWS_DPI_AWARENESS": "permonitorv2"}
    other = {}
    hires.prepare_platform("darwin", other)
    hires.prepare_platform("linux", other)
    assert other == {}
    assert hires.window_size(1280, 720, 1.5, (2560, 1440)) == (1920, 1080)
    assert hires.window_size(1280, 720, 2.0, (1920, 1080)) == (1728, 972)
    assert hires.window_size(1280, 720, 1.0, (1280, 720)) == (1280, 720)
    assert Game.default_window_size() == (config.SCREEN_W, config.SCREEN_H)
