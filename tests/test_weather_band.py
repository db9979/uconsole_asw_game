"""The chart's rain/storm hatch is drawn once per look, not every frame."""

from types import SimpleNamespace as NS

import pygame

from src.ui import map_view, theme


def _game(rain=0.8, kind="rain"):
    world = NS(weather_values=lambda: {"rain_intensity": rain},
               weather_kind=lambda: kind)
    return NS(world=world, screen=pygame.Surface((1280, 720)))


def test_the_hatch_layer_is_reused_and_bounded(monkeypatch):
    map_view._HATCH_CACHE.clear()
    lines = []
    real = pygame.draw.line
    monkeypatch.setattr(pygame.draw, "line",
                        lambda *a, **k: (lines.append(1), real(*a, **k))[1])
    game = _game()
    map_view.draw_weather_band(game, (0, 0, 640, 500))
    first = len(lines)
    assert first > 100
    for _ in range(5):
        map_view.draw_weather_band(game, (0, 0, 640, 500))
    assert len(lines) == first
    for width in range(300, 320):
        map_view.draw_weather_band(game, (0, 0, width, 200))
    assert len(map_view._HATCH_CACHE) <= map_view._HATCH_CACHE_MAX


def test_rain_shows_on_the_day_chart(monkeypatch):
    monkeypatch.setattr(theme, "_ACTIVE", "day")
    map_view._HATCH_CACHE.clear()
    game = _game(rain=1.0)
    water = (226, 234, 244)
    game.screen.fill(water)
    map_view.draw_weather_band(game, (0, 0, 400, 400))
    pixels = pygame.surfarray.array3d(game.screen)[:400, :400].reshape(-1, 3)
    darkest = pixels.sum(axis=1).min()
    assert sum(water) - darkest > 60      # the old grey-white hatch gave ~10
