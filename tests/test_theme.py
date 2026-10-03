"""Colour themes: night (default), day and high contrast, one token set."""

from types import SimpleNamespace

import pygame
import pytest

from src.core import config, preferences
from src.ui import editor_widgets, layout, nato_symbols, sonar_view, theme


@pytest.fixture(autouse=True)
def _reset_theme():
    yield
    theme.configure_for(None)


def test_every_theme_defines_every_token_and_every_colour_name():
    names = set(theme.TOKENS["night"])
    for name in theme.THEMES:
        assert set(theme.TOKENS[name]) == names
        assert set(theme.CONFIG_COLORS[name]) == set(theme.CONFIG_COLORS["night"])
        assert set(theme.SONAR_COLORS[name]) == set(theme.SONAR_COLORS["night"])
        assert set(theme.EDITOR_PALETTES[name]) == set(theme.EDITOR_PALETTES["night"])
        assert set(theme.PHOSPHOR_PALETTES[name]) == {"green", "amber", "cyan"}


def test_night_is_the_default_and_config_carries_its_values():
    theme.configure_for(None)
    assert theme.active() == "night"
    assert config.COLOR_BG == (11, 15, 25)
    assert config.COLOR_PANEL_BG == (17, 24, 39)
    assert config.COLOR_OK == (16, 185, 129)
    assert sonar_view.NAVY == theme.SONAR_COLORS_STANDARD["NAVY"]
    assert editor_widgets.PALETTE.text == theme.EDITOR_PALETTE_STANDARD["text"]


def test_day_theme_is_light_with_dark_ink():
    game = SimpleNamespace(preferences=preferences.Preferences(theme="day"))
    theme.configure_for(game)
    assert theme.is_light()
    assert sum(config.COLOR_PANEL_BG) > sum(config.COLOR_TEXT) * 3
    assert sum(sonar_view.NAVY) > 600            # paper, not a dark scope
    assert sum(sonar_view.PHOSPHOR_PALETTES["green"]) < 200   # dark ink
    assert nato_symbols.AFFILIATION_COLORS["HOSTILE"] == (220, 38, 38)
    assert layout.METER_TRACK == theme.c("well")
    # Water stays blue (bathymetry and chart tests rely on the order).
    assert config.COLOR_GEO_BG[2] > config.COLOR_GEO_BG[1] > config.COLOR_GEO_BG[0]


def test_high_contrast_wins_over_the_chosen_theme_and_reverts():
    game = SimpleNamespace(preferences=preferences.Preferences(
        high_contrast=True, theme="day"))
    assert theme.configure_for(game) is True
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_HIGH_CONTRAST["COLOR_TEXT"]
    assert sonar_view.NAVY == theme.SONAR_COLORS_HIGH_CONTRAST["NAVY"]
    assert editor_widgets.PALETTE.focus == theme.EDITOR_PALETTE_HIGH_CONTRAST["focus"]
    theme.configure_for(None)
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_STANDARD["COLOR_TEXT"]


def test_red_light_forces_the_night_theme():
    game = SimpleNamespace(preferences=preferences.Preferences(theme="day"),
                           red_light_lit=True)
    assert theme.theme_for(game) == "night"
    game.red_light_lit = False
    assert theme.theme_for(game) == "day"


def test_layout_configure_for_applies_theme_from_game_preferences():
    game = SimpleNamespace(preferences=preferences.Preferences(high_contrast=True))
    layout.configure_for(game)
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_HIGH_CONTRAST["COLOR_TEXT"]
    layout.configure_for(None, large_text=False)
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_STANDARD["COLOR_TEXT"]


def test_revision_changes_with_the_theme_for_surface_caches():
    theme.set_theme("night")
    before = theme.revision()
    theme.set_theme("day")
    assert theme.revision() != before
    same = theme.revision()
    theme.set_theme("day")
    assert theme.revision() == same


def test_options_order_cycles_all_three_themes():
    assert theme.next_theme("night") == "day"
    assert theme.next_theme("day") == "contrast"
    assert theme.next_theme("contrast") == "night"


def test_css_tokens_cover_every_theme_and_token():
    css = theme.css_tokens()
    for name in theme.THEMES:
        assert f'data-theme="{name}"' in css
    for token in theme.TOKENS["night"]:
        assert f"--t-{token.replace('_', '-')}:" in css


def test_boxes_are_rounded_panels_with_an_accent_title_mark():
    surface = pygame.Surface((200, 120))
    theme.set_theme("night")
    surface.fill((0, 0, 0))
    layout.box(surface, (10, 10, 180, 100), "x")
    # Rounded: the very corner pixel keeps the background.
    assert surface.get_at((10, 10))[:3] == (0, 0, 0)
    assert surface.get_at((40, 60))[:3] == config.COLOR_PANEL_BG
    assert surface.get_at((19, 24))[:3] == theme.c("accent")


def test_red_light_turns_the_night_colours_to_readable_greys():
    game = SimpleNamespace(preferences=preferences.Preferences(theme="day"),
                           red_light_lit=True)
    theme.configure_for(game)
    assert theme.active() == "night" and theme.red_light()
    # The green accent keeps its brightness as grey instead of going black
    # under the red multiply; reds stay bright.
    accent = theme.c("accent")
    assert accent[0] == accent[1] == accent[2] >= 120
    assert config.COLOR_OK[0] == config.COLOR_OK[1] >= 120
    assert theme.c("alarm")[0] >= 200
    assert theme.pick((16, 185, 129), (0, 0, 0))[0] >= 120
    game.red_light_lit = False
    theme.configure_for(game)
    assert not theme.red_light() and theme.active() == "day"


def _mean_luma(surface, rect) -> float:
    total = count = 0
    for x in range(rect.left, rect.right, 9):
        for y in range(rect.top, rect.bottom, 9):
            r, g, b, *_ = surface.get_at((x, y))
            total += .299 * r + .587 * g + .114 * b
            count += 1
    return total / count


@pytest.mark.parametrize("name, light", [("night", False), ("day", True)])
def test_menu_and_overlay_backdrops_follow_the_theme(name, light):
    """The scene behind the main menu and every overlay is a light day scene
    in the light theme (dark text sits on it), the dark night hunt otherwise."""
    from src.ui import overlay_style, splash_view
    theme.set_theme(name)
    surface = pygame.Surface((1280, 720))
    for draw in (splash_view.draw_menu_backdrop, overlay_style.backdrop):
        draw(surface, 3.0)
        luma = _mean_luma(surface, pygame.Rect(0, 0, 1280, 720))
        assert (luma > 170) if light else (luma < 60), (name, draw.__name__, luma)
