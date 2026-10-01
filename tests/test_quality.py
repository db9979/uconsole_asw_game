"""Graphics level and canvas scaling (src/ui/quality.py)."""

import pygame

from src.core.game import Game
from src.ui import overlay_style, quality


def _canvas():
    canvas = pygame.Surface((1280, 720))
    canvas.fill((0, 0, 0))
    # One-pixel white lines every 3 px: plain 1.5x scaling makes them 1 or 2 px.
    for x in range(0, 1280, 3):
        pygame.draw.line(canvas, (255, 255, 255), (x, 0), (x, 719))
    return canvas


def _row(surface, y=10):
    return [surface.get_at((x, y))[0] for x in range(0, 300)]


def test_whole_factor_repeats_pixels_exactly():
    out = quality.scale_canvas(_canvas(), (2560, 1440), "normal")
    assert out.get_size() == (2560, 1440)
    assert set(_row(out)) == {0, 255}


def test_native_size_is_the_canvas_itself():
    canvas = _canvas()
    assert quality.scale_canvas(canvas, (1280, 720), "normal") is canvas


def test_sharp_scaling_keeps_thin_lines_even_at_one_and_a_half():
    canvas = _canvas()
    plain = quality.scale_canvas(canvas, (1920, 1080), "low")
    sharp = quality.scale_canvas(canvas, (1920, 1080), "normal")
    assert plain.get_size() == sharp.get_size() == (1920, 1080)
    # Plain pixel scaling: the lines come out 1 or 2 px wide (uneven).
    widths, run = [], 0
    for value in _row(plain):
        if value == 255:
            run += 1
        elif run:
            widths.append(run)
            run = 0
    assert set(widths) == {1, 2}
    # Sharp scaling: every line carries the same light (even weight).
    light = [sum(_row(sharp)[i:i + 9]) for i in range(0, 270, 9)]
    assert max(light) - min(light) <= 0.05 * max(light)


def test_levels_switch_effects_and_lines():
    from src.ui import lines
    assert quality.configure("full") == "full" and lines.ENABLED
    assert quality.afterglow()
    assert quality.configure("low") == "low" and not lines.ENABLED
    assert not quality.afterglow()
    assert quality.backdrop_time(1.37) == 1.25
    assert quality.configure("bogus") == "normal" and quality.backdrop_time(1.37) == 1.37


def test_low_level_reuses_the_backdrop_frame(monkeypatch):
    calls = []
    real = overlay_style.splash_view.draw_scene
    monkeypatch.setattr(overlay_style.splash_view, "draw_scene",
                        lambda surface, t: (calls.append(t), real(surface, t)))
    quality.configure("low")
    try:
        surface = pygame.Surface((1280, 720))
        for t in (2.0, 2.05, 2.1, 2.2, 2.3):
            overlay_style.backdrop(surface, t)
        assert calls == [2.0, 2.25]
    finally:
        quality.configure("normal")


def test_compose_frame_letterboxes_with_the_level(monkeypatch):
    game = Game(seed=3, start_menu=True, show_splash=False, audio_enabled=False)
    seen = []
    monkeypatch.setattr(quality, "scale_canvas",
                        lambda canvas, size, level=None: (seen.append(size),
                                                          pygame.Surface(size))[1])
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1920, 1200))
    game.compose_frame()
    assert seen == [(1920, 1080)]
