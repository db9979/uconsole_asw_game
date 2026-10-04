"""The microphone meter in the top bar never covers the status line.

With the own microphone on (or a crew voice held), on both sides, in English
and German, with normal and large text, in every colour theme and with the
longest mission title, the status line's glyphs stay left of the meter and
the meter keeps its place right of the status line, left of the menu button.
"""

from __future__ import annotations

from dataclasses import replace

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.preferences import Preferences
from src.ui import game_menu, layout, mic_meter

TOP = pygame.Rect(0, 0, config.SCREEN_W, config.TOP_BAR_H)


def _longest_title(language: str) -> str:
    tr = Translator(language)
    titles = [tr("scenario." + name + ".title") for name in config.SCENARIO_NAMES.values()]
    return max(titles, key=len) + " - " + max(titles, key=len)


def _game(language: str, large: bool, theme: str, side: str) -> Game:
    prefs = Preferences(language=language, fullscreen=False, audio=False,
                        large_text=large, microphone=True)
    game = Game(seed=7, start_menu=False, audio_enabled=False, preferences=prefs)
    game.preferences = replace(game.preferences, high_contrast=theme == "contrast",
                               theme="day" if theme == "day" else "night")
    game._apply_text_size()
    if side == "uboot":
        game.local_side = "uboot"
        game._update(0.05)
    game.mic_level = 14
    game.msg = ""
    return game


@pytest.mark.parametrize("side", ["frigate", "uboot"])
@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("theme", ["night", "day", "contrast"])
def test_status_line_stays_left_of_the_meter(monkeypatch, side, language, large, theme):
    game = _game(language, large, theme, side)
    title = _longest_title(language)
    monkeypatch.setattr(game, "top_bar_scenario", lambda: title)
    meter = mic_meter.rect(game)
    assert TOP.contains(meter)
    assert meter.right + mic_meter.GAP <= game_menu.button_rect().x
    with layout.capture_text() as traced:
        game.draw()
    status = [item for item in traced if item["ink"].colliderect(TOP)
              and item["ink"].x > meter.x - 400]
    assert status, "no status line drawn"
    # The long title gives way; clock and course stay whole.
    line = " ".join(item["text"] for item in status)
    assert game.world.format_time() in line and "°" in line, line
    for item in traced:
        assert not item["ink"].colliderect(meter), (item["text"], item["ink"], meter)


def test_the_status_line_uses_the_whole_width_without_a_meter():
    game = _game("en", False, "night", "frigate")
    game.preferences = replace(game.preferences, microphone=False)
    right = game_menu.button_rect().x - 10
    assert not mic_meter.shown(game, "frigate")
    assert mic_meter.status_right(game, "frigate", right) == right
    game.preferences = replace(game.preferences, microphone=True)
    assert mic_meter.status_right(game, "frigate", right) == mic_meter.rect(game).x - mic_meter.GAP


def test_unlit_segments_are_filled_not_empty_outlines():
    game = _game("en", False, "day", "frigate")
    game.mic_level = 0
    game.draw()
    meter = mic_meter.rect(game)
    track_x = meter.x + mic_meter.ICON_W + 3
    # Every unlit segment's middle carries a tinted fill, not the track colour.
    from src.ui import theme
    well = theme.c("well")
    pitch = (meter.w - mic_meter.ICON_W - 3 - 4) / 20
    for index in range(20):
        x = round(track_x + 2 + index * pitch) + 1
        assert tuple(game.screen.get_at((x, meter.y + 6)))[:3] != well
