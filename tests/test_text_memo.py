"""The display-only text memo and the silent light's blit tint.

Both exist for the uConsole's frame time; both must give exactly the pixels
and layouts the direct calls give, follow every change of the rendered value
and stay bounded.
"""

from types import SimpleNamespace as NS

import numpy as np
import pygame
import pytest

from src.core import config
from src.ui import layout, uboot_view


@pytest.fixture
def cached_fonts(monkeypatch):
    pygame.font.init()
    display = pygame.Surface((1, 1))
    monkeypatch.setattr(pygame.display, "get_surface", lambda: display)
    layout.clear_font_cache()
    yield
    layout.clear_font_cache()


def _pixels(surface):
    return pygame.image.tobytes(surface, "RGBA")


def test_rendered_line_is_reused_and_follows_text_and_colour(cached_fonts):
    face = layout.font(16)
    first = layout.render_line(face, "KURS 270", (200, 200, 200))
    assert layout.render_line(face, "KURS 270", (200, 200, 200)) is first
    assert _pixels(first) == _pixels(face.render("KURS 270", True, (200, 200, 200)))
    changed = layout.render_line(face, "KURS 271", (200, 200, 200))
    assert changed is not first
    assert _pixels(changed) == _pixels(face.render("KURS 271", True, (200, 200, 200)))
    recoloured = layout.render_line(face, "KURS 270", [255, 0, 0])
    assert recoloured is not first
    assert _pixels(recoloured) == _pixels(face.render("KURS 270", True, (255, 0, 0)))
    assert layout.text_size(face, "KURS 270") == face.size("KURS 270")
    assert layout.text_width(face, "KURS 2700") == face.size("KURS 2700")[0]


def test_wrap_memo_matches_direct_wrap_and_returns_a_copy(cached_fonts):
    face = layout.font(16)
    text = "Periscope depth reached, snorkel ready\nbattery 64 %"
    for width in (40, 120, 400):
        lines = layout.wrap_text(text, face, width)
        assert lines == layout._wrap_text(text, face, width)
        lines.append("changed by the caller")
        assert layout.wrap_text(text, face, width) == layout._wrap_text(text, face, width)
    assert layout.wrap_text(text, face, 0) == []


def test_memo_is_bounded_and_cleared_with_the_fonts(cached_fonts, monkeypatch):
    monkeypatch.setattr(layout, "IMAGE_MEMO_MAX", 8)
    monkeypatch.setattr(layout, "WIDTH_MEMO_MAX", 8)
    monkeypatch.setattr(layout, "WRAP_MEMO_MAX", 8)
    face = layout.font(14)
    for index in range(50):
        layout.render_line(face, f"T+{index}", (1, 2, 3))
        layout.text_width(face, f"T+{index}")
        layout.wrap_text(f"line {index}", face, 200)
        assert len(layout._IMAGE_MEMO) <= 8
        assert len(layout._WIDTH_MEMO) <= 8
        assert len(layout._WRAP_MEMO) <= 8
    layout.clear_font_cache()
    assert not (layout._IMAGE_MEMO or layout._WIDTH_MEMO or layout._WRAP_MEMO
                or layout._MEMO_FONT_IDS)


def test_fonts_outside_the_cache_are_never_memoized(cached_fonts):
    rendered = []
    face = layout.font(12)
    spy = NS(size=face.size, render=lambda text, aa, color: rendered.append(text)
             or face.render(text, aa, color))
    layout.render_line(spy, "A", (1, 1, 1))
    layout.render_line(spy, "A", (1, 1, 1))
    assert rendered == ["A", "A"]
    assert layout.text_width(spy, "AB") == face.size("AB")[0]
    assert layout.wrap_text("A B", spy, 500) == ["A B"]
    assert not (layout._IMAGE_MEMO or layout._WIDTH_MEMO or layout._WRAP_MEMO)


def test_blit_block_pixels_follow_a_changed_value(cached_fonts):
    def draw(text):
        surface = pygame.Surface((200, 40))
        layout.blit_block(surface, text, 4, 4, 190, 30, (220, 220, 220), size=16)
        return _pixels(surface)

    first = draw("Tiefe 50 m")
    assert draw("Tiefe 50 m") == first
    assert draw("Tiefe 51 m") != first


def _silent_boat():
    return NS(orders=NS(silent=True), sub=NS(sunk=False))


@pytest.mark.parametrize("clip", [None, (3, 5, 40, 20)])
def test_silent_light_blit_equals_the_blended_fills(clip):
    rng = np.random.default_rng(5)
    base = pygame.Surface((64, 48))
    pygame.surfarray.blit_array(base, rng.integers(0, 256, (64, 48, 3), dtype=np.uint8))
    expected, actual = base.copy(), base.copy()
    if clip is not None:
        expected.set_clip(clip)
        actual.set_clip(clip)
    expected.fill(config.UBOOT_SILENT_LIGHT, special_flags=pygame.BLEND_MULT)
    expected.fill(config.UBOOT_SILENT_LIGHT_FLOOR, special_flags=pygame.BLEND_ADD)
    assert uboot_view.silent_light(actual, _silent_boat()) is True
    assert _pixels(actual) == _pixels(expected)
    assert len(uboot_view._SILENT_TINT) == 1
    other = pygame.Surface((10, 10))
    uboot_view.silent_light(other, _silent_boat())
    assert len(uboot_view._SILENT_TINT) == 1


def test_draw_benchmark_tool_runs(capsys):
    from tools import bench_draw

    assert bench_draw.main(["--side", "uboot", "--view", "uboot_radio", "--frames", "2",
                            "--warmup", "0.2", "--silent"]) == 0
    out = capsys.readouterr().out
    assert "uboot_radio/uboot_radio" in out and "draw mean" in out
