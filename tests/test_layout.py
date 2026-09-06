"""Headless wrapping, clipping, and iterable regression tests."""

import pygame
import pytest

from src.ui import layout


@pytest.fixture
def text_font():
    pygame.font.init()
    return pygame.font.Font(None, 24)


@pytest.mark.parametrize("prefix", ["", "ok "])
def test_wrap_long_word_preserves_text_and_fits(text_font, prefix):
    word = "Wabcdefghijklmno" * 8
    width = text_font.size("WWW")[0]
    lines = layout.wrap_text(prefix + word, text_font, width)

    assert len(lines) > 2
    assert "".join(lines).replace(" ", "") == prefix.strip() + word
    assert all(text_font.size(line)[0] <= width for line in lines)


def test_wrap_preserves_paragraphs_and_normal_word_boundaries(text_font):
    width = text_font.size("one two")[0]
    assert layout.wrap_text("one two three\n\nfour\n", text_font, width) == [
        "one two", "three", "", "four", ""
    ]


def test_wrap_skips_glyphs_that_cannot_fit(text_font):
    width = text_font.size("i")[0]
    assert text_font.size("W")[0] > width
    lines = layout.wrap_text("WiWi", text_font, width)
    assert "".join(lines) == "ii"
    assert all(text_font.size(line)[0] <= width for line in lines)


@pytest.mark.parametrize("width", [0, -1])
def test_wrap_nonpositive_width(text_font, width):
    assert layout.wrap_text("long word\nnext", text_font, width) == []


def test_fit_text_does_not_emit_an_oversized_ellipsis(monkeypatch, text_font):
    monkeypatch.setattr(layout, "font", lambda size: text_font)
    width = text_font.size("i")[0]
    assert text_font.size("\u2026")[0] > width
    fitted_font, lines = layout.fit_text("i\ni\ni", 24, width, 1, min_size=24)
    assert len(lines) == 1
    assert all(fitted_font.size(line)[0] <= width for line in lines)


class SolidFont:
    """Tall, solid glyphs make alignment and clipping pixel-exact."""

    def size(self, text):
        return len(text) * 6, 40

    def get_linesize(self):
        return 10

    def render(self, text, antialias, color):
        surface = pygame.Surface(self.size(text), pygame.SRCALPHA)
        surface.fill(color)
        return surface


@pytest.mark.parametrize("align", ["left", "center", "right"])
@pytest.mark.parametrize("valign", ["top", "center", "bottom"])
@pytest.mark.parametrize("width", [12, 36])
@pytest.mark.parametrize("height", [5, 30])
def test_blit_block_clips_to_original_rect(monkeypatch, align, valign, width, height):
    f = SolidFont()
    monkeypatch.setattr(layout, "fit_text", lambda *args: (f, ["XXXX"]))
    screen = pygame.Surface((80, 80), pygame.SRCALPHA)
    original_clip = pygame.Rect(22, 18, 30, 45)
    screen.set_clip(original_clip)
    requested = pygame.Rect(20, 20, width, height)

    layout.blit_block(screen, "XXXX", *requested, color="white",
                      align=align, valign=valign)

    px = requested.x + {"left": 0, "center": max(0, (width - 24) // 2),
                        "right": width - 24}[align]
    offset = {"top": 0, "center": max(0, (height - 11) // 2),
              "bottom": max(0, height - 11)}[valign]
    expected = pygame.Rect(px, requested.y + offset, 24, 40)
    expected = expected.clip(requested).clip(original_clip)
    assert screen.get_bounding_rect() == expected
    assert pygame.mask.from_surface(screen).count() == expected.w * expected.h
    assert screen.get_clip() == original_clip


@pytest.mark.parametrize("width,height", [(0, 20), (20, 0), (-1, 20), (20, -1)])
def test_blit_block_empty_rect_does_not_draw(monkeypatch, width, height):
    def unexpected_fit(*args):
        pytest.fail("An empty rectangle should not fit or render text")

    monkeypatch.setattr(layout, "fit_text", unexpected_fit)
    screen = pygame.Surface((40, 40), pygame.SRCALPHA)
    layout.blit_block(screen, "text", 10, 10, width, height, "white")
    assert pygame.mask.from_surface(screen).count() == 0


@pytest.mark.parametrize("inner", [(0, 0, 25, 25), (0, 0, 5, 5)])
def test_nested_clip_intersects_and_restores_on_exception(inner):
    screen = pygame.Surface((60, 60), pygame.SRCALPHA)
    original = pygame.Rect(10, 10, 30, 30)
    outer = pygame.Rect(20, 5, 30, 30)
    screen.set_clip(original)

    with pytest.raises(RuntimeError, match="render failed"):
        with layout.clip_to(screen, outer):
            assert screen.get_clip() == original.clip(outer)
            try:
                with layout.clip_to(screen, inner):
                    assert screen.get_clip() == original.clip(outer).clip(inner)
                    screen.fill("white")
                    raise RuntimeError("render failed")
            finally:
                assert screen.get_clip() == original.clip(outer)

    expected = original.clip(outer).clip(inner)
    assert pygame.mask.from_surface(screen).count() == expected.w * expected.h
    if expected.w and expected.h:
        assert screen.get_bounding_rect() == expected
    assert screen.get_clip() == original


@pytest.mark.parametrize("height,visible", [(0, 0), (12, 1), (24, 2), (60, 3)])
@pytest.mark.parametrize("kind", ["list", "generator", "one_shot"])
def test_blit_lines_consumes_iterable_once(monkeypatch, height, visible, kind):
    monkeypatch.setattr(layout, "font", lambda size: SolidFont())
    drawn = []
    monkeypatch.setattr(layout, "blit_line",
                        lambda screen, text, rect, color, size: drawn.append((text, rect)))
    values = ["first", "second", "third"]

    class OneShot:
        iterations = 0

        def __iter__(self):
            self.iterations += 1
            assert self.iterations == 1
            return iter(values)

    lines = {"list": values, "generator": (value for value in values),
             "one_shot": OneShot()}[kind]
    screen = pygame.Surface((80, 80), pygame.SRCALPHA)
    original_clip = screen.get_clip()

    count = layout.blit_lines(screen, lines, (10, 10, 50, height), "white")

    assert count == visible
    assert drawn == [(text, (10, 10 + i * 12, 50, 12))
                     for i, text in enumerate(values[:visible])]
    assert screen.get_clip() == original_clip
