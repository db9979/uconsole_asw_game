"""Central color theme, consolidating what used to be three separate,
hardcoded palettes (config.COLOR_*, sonar_view's module colors, and
editor_widgets.EditorPalette) and applying a high-contrast/colorblind-safe
variant on request.

STANDARD mirrors the previously hardcoded values exactly, so the default
appearance is unchanged. HIGH_CONTRAST boosts background/text contrast and
separates the friend/neutral/hostile/warn/danger/ok hues using an
Okabe-Ito-style palette, which stays distinguishable under the common forms
of color-vision deficiency.
"""

from __future__ import annotations

CONFIG_COLORS_STANDARD = {
    "COLOR_BG": (8, 14, 10),
    "COLOR_GEO_BG": (5, 18, 34),
    "COLOR_GRID": (20, 38, 28),
    "COLOR_GEO_GRID": (18, 49, 72),
    "COLOR_TEXT": (140, 230, 160),
    "COLOR_TEXT_DIM": (105, 158, 126),
    "COLOR_WARN": (230, 190, 60),
    "COLOR_DANGER": (230, 80, 70),
    "COLOR_OK": (90, 210, 120),
    "COLOR_SONAR_RING": (40, 90, 60),
    "COLOR_CONTACT": (255, 255, 255),
    "COLOR_CONTACT_ZIVIL": (90, 200, 120),
    "COLOR_CONTACT_WARSHIP": (230, 120, 60),
    "COLOR_CONTACT_UNBEST": (230, 200, 80),
    "COLOR_CONTACT_UBOOT": (230, 90, 70),
    "COLOR_CONTACT_BIO": (110, 200, 200),
    "COLOR_LAND": (25, 43, 55),
    "COLOR_LAND_EDGE": (76, 126, 153),
    "COLOR_SHALLOW": (12, 43, 68),
    "COLOR_DEEP": (4, 24, 48),
    "COLOR_ESM": (140, 150, 220),
    "COLOR_HFDF": (200, 140, 220),
    "COLOR_FLIGHT": (220, 180, 90),
    "COLOR_CONTACT_MISSILE": (235, 70, 180),
}

CONFIG_COLORS_HIGH_CONTRAST = {
    "COLOR_BG": (0, 0, 0),
    "COLOR_GEO_BG": (0, 0, 0),
    "COLOR_GRID": (70, 70, 70),
    "COLOR_GEO_GRID": (70, 70, 100),
    "COLOR_TEXT": (255, 255, 255),
    "COLOR_TEXT_DIM": (210, 210, 210),
    "COLOR_WARN": (230, 159, 0),
    "COLOR_DANGER": (213, 94, 0),
    "COLOR_OK": (0, 158, 115),
    "COLOR_SONAR_RING": (100, 100, 100),
    "COLOR_CONTACT": (255, 255, 255),
    "COLOR_CONTACT_ZIVIL": (0, 158, 115),
    "COLOR_CONTACT_WARSHIP": (230, 159, 0),
    "COLOR_CONTACT_UNBEST": (240, 228, 66),
    "COLOR_CONTACT_UBOOT": (213, 94, 0),
    "COLOR_CONTACT_BIO": (86, 180, 233),
    "COLOR_LAND": (45, 45, 45),
    "COLOR_LAND_EDGE": (160, 160, 160),
    "COLOR_SHALLOW": (0, 65, 95),
    "COLOR_DEEP": (0, 20, 40),
    "COLOR_ESM": (0, 114, 178),
    "COLOR_HFDF": (204, 121, 167),
    "COLOR_FLIGHT": (240, 228, 66),
    "COLOR_CONTACT_MISSILE": (204, 121, 167),
}

SONAR_COLORS_STANDARD = {
    "NAVY": (6, 13, 25),
    "PANEL": (10, 22, 37),
    "GRID": (24, 49, 65),
    "DIM": (119, 151, 169),
    "TEXT": (211, 229, 233),
    "CYAN": (79, 224, 202),
    "AMBER": (244, 190, 97),
}

SONAR_COLORS_HIGH_CONTRAST = {
    "NAVY": (0, 0, 0),
    "PANEL": (12, 12, 12),
    "GRID": (80, 80, 80),
    "DIM": (210, 210, 210),
    "TEXT": (255, 255, 255),
    "CYAN": (86, 180, 233),
    "AMBER": (230, 159, 0),
}

EDITOR_PALETTE_STANDARD = dict(
    background=(8, 14, 17), panel=(14, 25, 29), raised=(23, 39, 43),
    border=(62, 125, 128), text=(200, 232, 214), dim=(116, 150, 142),
    focus=(232, 183, 74), danger=(224, 91, 79), friendly=(92, 174, 225),
    hostile=(224, 91, 79), neutral=(202, 198, 132),
)

EDITOR_PALETTE_HIGH_CONTRAST = dict(
    background=(0, 0, 0), panel=(14, 14, 14), raised=(35, 35, 35),
    border=(160, 160, 160), text=(255, 255, 255), dim=(210, 210, 210),
    focus=(230, 159, 0), danger=(213, 94, 0), friendly=(0, 114, 178),
    hostile=(213, 94, 0), neutral=(240, 228, 66),
)


def _high_contrast_enabled(game) -> bool:
    preferences = getattr(game, "preferences", None)
    return bool(getattr(preferences, "high_contrast", False))


def configure_for(game=None) -> bool:
    """Apply the standard or high-contrast palette to every color global.

    Every consumer (config.COLOR_*, sonar_view's module colors,
    editor_widgets.PALETTE) reads these as live module attributes, so
    reassigning them here covers all existing call sites with no further
    changes. Imports are local to avoid a cycle: sonar_view/editor_widgets
    import layout, and layout calls this function.
    """
    high_contrast = _high_contrast_enabled(game)

    from src.core import config
    colors = CONFIG_COLORS_HIGH_CONTRAST if high_contrast else CONFIG_COLORS_STANDARD
    for name, value in colors.items():
        setattr(config, name, value)

    from src.ui import sonar_view
    colors = SONAR_COLORS_HIGH_CONTRAST if high_contrast else SONAR_COLORS_STANDARD
    for name, value in colors.items():
        setattr(sonar_view, name, value)

    from src.ui import editor_widgets
    palette = EDITOR_PALETTE_HIGH_CONTRAST if high_contrast else EDITOR_PALETTE_STANDARD
    editor_widgets.PALETTE = editor_widgets.EditorPalette(**palette)

    return high_contrast
