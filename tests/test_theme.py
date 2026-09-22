"""Theme consolidation: high-contrast palette swap and reset."""

from types import SimpleNamespace

from src.core import config, preferences
from src.ui import editor_widgets, layout, sonar_view, theme


def test_standard_theme_matches_previous_hardcoded_colors():
    theme.configure_for(None)
    assert config.COLOR_TEXT == (140, 230, 160)
    assert sonar_view.NAVY == (6, 13, 25)
    assert editor_widgets.PALETTE.text == (200, 232, 214)


def test_high_contrast_theme_swaps_and_reverts_module_colors():
    game = SimpleNamespace(preferences=preferences.Preferences(high_contrast=True))
    try:
        assert theme.configure_for(game) is True
        assert config.COLOR_TEXT == theme.CONFIG_COLORS_HIGH_CONTRAST["COLOR_TEXT"]
        assert sonar_view.NAVY == theme.SONAR_COLORS_HIGH_CONTRAST["NAVY"]
        assert editor_widgets.PALETTE.focus == theme.EDITOR_PALETTE_HIGH_CONTRAST["focus"]
    finally:
        theme.configure_for(None)
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_STANDARD["COLOR_TEXT"]
    assert sonar_view.NAVY == theme.SONAR_COLORS_STANDARD["NAVY"]
    assert editor_widgets.PALETTE.focus == theme.EDITOR_PALETTE_STANDARD["focus"]


def test_layout_configure_for_applies_theme_from_game_preferences():
    game = SimpleNamespace(preferences=preferences.Preferences(high_contrast=True))
    try:
        layout.configure_for(game)
        assert config.COLOR_TEXT == theme.CONFIG_COLORS_HIGH_CONTRAST["COLOR_TEXT"]
    finally:
        layout.configure_for(None, large_text=False)
    assert config.COLOR_TEXT == theme.CONFIG_COLORS_STANDARD["COLOR_TEXT"]
