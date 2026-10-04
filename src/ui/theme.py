"""Colour themes: semantic tokens and the theme manager.

Three themes share one set of token names (``TOKENS``): ``night`` (Tactical
Night, the default: obsidian surfaces, phosphor green, amber and red),
``day`` (Tactical Day: light glare-free greys, navy and dark ink) and
``contrast`` (the high-contrast / colour-blind palette with Okabe-Ito hues).
The browser stations use the same names as CSS custom properties (``--t-*``,
generated into ``data/commander/css/tokens.css`` by
``tools/gen_web_schema.py``), so both platforms change together.

Drawing code asks ``theme.c("panel")``; older code reads the
``config.COLOR_*``, ``sonar_view`` and ``editor_widgets.PALETTE`` module
globals, which ``configure_for`` reassigns from the same tokens. Colours are
display only: nothing here reads or changes the simulation, and the choice
lives in ``settings.json`` (``Preferences.theme``), never in a save.
"""

from __future__ import annotations

THEMES = ("night", "day", "contrast")
# The two themes the top bar's switch flips between; high contrast is chosen
# in the options.
SWITCH_THEMES = ("night", "day")


def _rgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# Semantic tokens. Every theme defines every name (tests/test_theme.py).
TOKENS = {
    "night": {
        "bg": "#0B0F19", "panel": "#111827", "raised": "#1A2333", "well": "#060912",
        "line": "#243045", "line_strong": "#34507A", "shadow": "#05070D", "hilite": "#1F2A3D",
        "text": "#E5E7EB", "dim": "#8B95A7", "faint": "#56607A",
        "accent": "#10B981", "on_accent": "#03140D", "phosphor": "#00FF87",
        "caution": "#F59E0B", "alarm": "#EF4444", "info": "#60A5FA", "focus": "#00FF87",
        "friend": "#60A5FA", "neutral": "#34D399", "hostile": "#F87171", "unknown": "#FBBF24",
        "select": "#11353A", "water": "#0A1424", "land": "#1B2433", "land_edge": "#4B5F80",
    },
    "day": {
        "bg": "#F3F4F6", "panel": "#FFFFFF", "raised": "#F9FAFB", "well": "#EEF1F5",
        "line": "#D1D5DB", "line_strong": "#94A3B8", "shadow": "#C9CED6", "hilite": "#FFFFFF",
        "text": "#1F2937", "dim": "#4B5563", "faint": "#8A93A3",
        "accent": "#1E3A8A", "on_accent": "#FFFFFF", "phosphor": "#059669",
        "caution": "#B45309", "alarm": "#DC2626", "info": "#1D4ED8", "focus": "#1E3A8A",
        "friend": "#1D4ED8", "neutral": "#047857", "hostile": "#DC2626", "unknown": "#B45309",
        "select": "#DBE4F7", "water": "#E2EAF4", "land": "#E7E1D2", "land_edge": "#A8A08A",
    },
    "contrast": {
        "bg": "#000000", "panel": "#0C0C0C", "raised": "#232323", "well": "#000000",
        "line": "#A0A0A0", "line_strong": "#D2D2D2", "shadow": "#000000", "hilite": "#0C0C0C",
        "text": "#FFFFFF", "dim": "#D2D2D2", "faint": "#A0A0A0",
        "accent": "#0072B2", "on_accent": "#FFFFFF", "phosphor": "#56B4E9",
        "caution": "#E69F00", "alarm": "#D55E00", "info": "#56B4E9", "focus": "#E69F00",
        "friend": "#0072B2", "neutral": "#009E73", "hostile": "#D55E00", "unknown": "#F0E442",
        "select": "#282850", "water": "#000000", "land": "#2D2D2D", "land_edge": "#A0A0A0",
    },
}

# config.COLOR_* per theme (the names every older drawing call reads).
CONFIG_COLORS_STANDARD = {
    "COLOR_BG": (11, 15, 25),
    "COLOR_GEO_BG": (10, 20, 36),
    "COLOR_GRID": (24, 34, 54),
    "COLOR_GEO_GRID": (26, 42, 68),
    "COLOR_TEXT": (229, 231, 235),
    "COLOR_TEXT_DIM": (139, 149, 167),
    "COLOR_WARN": (245, 158, 11),
    "COLOR_DANGER": (239, 68, 68),
    "COLOR_OK": (16, 185, 129),
    "COLOR_SONAR_RING": (52, 80, 122),
    "COLOR_CONTACT": (240, 244, 248),
    "COLOR_CONTACT_ZIVIL": (52, 211, 153),
    "COLOR_CONTACT_WARSHIP": (251, 146, 60),
    "COLOR_CONTACT_UNBEST": (251, 191, 36),
    "COLOR_CONTACT_UBOOT": (248, 113, 113),
    "COLOR_CONTACT_BIO": (103, 232, 249),
    "COLOR_LAND": (27, 36, 51),
    "COLOR_LAND_EDGE": (75, 95, 128),
    "COLOR_SHALLOW": (14, 30, 52),
    "COLOR_DEEP": (7, 15, 29),
    "COLOR_ESM": (165, 180, 252),
    "COLOR_HFDF": (216, 180, 254),
    "COLOR_FLIGHT": (252, 211, 77),
    "COLOR_PLOT": (249, 168, 212),
    "COLOR_CONTACT_MISSILE": (236, 72, 153),
    "COLOR_FEED_BG": (6, 9, 18),
    "COLOR_PANEL_BG": (17, 24, 39),
    "COLOR_OVERLAY_BG": (12, 17, 29),
    "COLOR_SELECT_BG": (17, 53, 58),
    "COLOR_ALARM_BG": (14, 19, 32),
    "COLOR_TAB_ACTIVE": (16, 69, 64),
}

CONFIG_COLORS_DAY = {
    "COLOR_BG": (243, 244, 246),
    "COLOR_GEO_BG": (222, 232, 244),
    "COLOR_GRID": (215, 220, 228),
    "COLOR_GEO_GRID": (190, 205, 225),
    "COLOR_TEXT": (31, 41, 55),
    "COLOR_TEXT_DIM": (75, 85, 99),
    "COLOR_WARN": (180, 83, 9),
    "COLOR_DANGER": (220, 38, 38),
    "COLOR_OK": (5, 150, 105),
    "COLOR_SONAR_RING": (148, 163, 184),
    "COLOR_CONTACT": (17, 24, 39),
    "COLOR_CONTACT_ZIVIL": (4, 120, 87),
    "COLOR_CONTACT_WARSHIP": (194, 65, 12),
    "COLOR_CONTACT_UNBEST": (161, 98, 7),
    "COLOR_CONTACT_UBOOT": (220, 38, 38),
    "COLOR_CONTACT_BIO": (14, 116, 144),
    "COLOR_LAND": (231, 225, 210),
    "COLOR_LAND_EDGE": (150, 140, 112),
    "COLOR_SHALLOW": (200, 216, 236),
    "COLOR_DEEP": (222, 232, 244),
    "COLOR_ESM": (67, 56, 202),
    "COLOR_HFDF": (126, 34, 206),
    "COLOR_FLIGHT": (161, 98, 7),
    "COLOR_PLOT": (190, 24, 93),
    "COLOR_CONTACT_MISSILE": (219, 39, 119),
    "COLOR_FEED_BG": (238, 241, 245),
    "COLOR_PANEL_BG": (255, 255, 255),
    "COLOR_OVERLAY_BG": (249, 250, 251),
    "COLOR_SELECT_BG": (226, 233, 248),
    "COLOR_ALARM_BG": (238, 241, 245),
    "COLOR_TAB_ACTIVE": (219, 228, 247),
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
    "COLOR_PLOT": (255, 120, 255),
    "COLOR_CONTACT_MISSILE": (204, 121, 167),
    "COLOR_FEED_BG": (0, 0, 0),
    "COLOR_PANEL_BG": (12, 12, 12),
    "COLOR_OVERLAY_BG": (0, 0, 0),
    "COLOR_SELECT_BG": (40, 40, 80),
    "COLOR_ALARM_BG": (0, 0, 0),
    "COLOR_TAB_ACTIVE": (0, 70, 110),
}

# The sonar room's own names (sonar_view), and its phosphor ramps: dark scope
# to bright trace at night, paper to dark ink by day (like a LOFARgram
# recorder's chart).
SONAR_COLORS_STANDARD = {
    "NAVY": (6, 9, 18),
    "PANEL": (17, 24, 39),
    "GRID": (36, 48, 69),
    "DIM": (139, 149, 167),
    "TEXT": (229, 231, 235),
    "CYAN": (52, 230, 160),
    "AMBER": (245, 158, 11),
}

SONAR_COLORS_DAY = {
    "NAVY": (244, 247, 246),
    "PANEL": (255, 255, 255),
    "GRID": (209, 217, 228),
    "DIM": (75, 85, 99),
    "TEXT": (31, 41, 55),
    "CYAN": (4, 120, 87),
    "AMBER": (180, 83, 9),
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

PHOSPHOR_PALETTES = {
    "night": {"green": (0, 255, 135), "amber": (255, 184, 62), "cyan": (79, 224, 202)},
    "day": {"green": (4, 78, 58), "amber": (124, 54, 8), "cyan": (14, 88, 110)},
    "contrast": {"green": (68, 255, 154), "amber": (255, 184, 62), "cyan": (86, 180, 233)},
}

EDITOR_PALETTE_STANDARD = dict(
    background=(11, 15, 25), panel=(17, 24, 39), raised=(26, 35, 51),
    border=(52, 80, 122), text=(229, 231, 235), dim=(139, 149, 167),
    focus=(245, 158, 11), danger=(239, 68, 68), friendly=(96, 165, 250),
    hostile=(248, 113, 113), neutral=(251, 191, 36),
)

EDITOR_PALETTE_DAY = dict(
    background=(243, 244, 246), panel=(255, 255, 255), raised=(249, 250, 251),
    border=(148, 163, 184), text=(31, 41, 55), dim=(75, 85, 99),
    focus=(30, 58, 138), danger=(220, 38, 38), friendly=(29, 78, 216),
    hostile=(220, 38, 38), neutral=(161, 98, 7),
)

EDITOR_PALETTE_HIGH_CONTRAST = dict(
    background=(0, 0, 0), panel=(14, 14, 14), raised=(35, 35, 35),
    border=(160, 160, 160), text=(255, 255, 255), dim=(210, 210, 210),
    focus=(230, 159, 0), danger=(213, 94, 0), friendly=(0, 114, 178),
    hostile=(213, 94, 0), neutral=(240, 228, 66),
)

CONFIG_COLORS = {"night": CONFIG_COLORS_STANDARD, "day": CONFIG_COLORS_DAY,
                 "contrast": CONFIG_COLORS_HIGH_CONTRAST}
SONAR_COLORS = {"night": SONAR_COLORS_STANDARD, "day": SONAR_COLORS_DAY,
                "contrast": SONAR_COLORS_HIGH_CONTRAST}
EDITOR_PALETTES = {"night": EDITOR_PALETTE_STANDARD, "day": EDITOR_PALETTE_DAY,
                   "contrast": EDITOR_PALETTE_HIGH_CONTRAST}

_RGB = {name: {key: _rgb(value) for key, value in tokens.items()}
        for name, tokens in TOKENS.items()}

# The active theme and a counter that changes with it, for caches of drawn
# surfaces (``revision()`` belongs in their keys).
_ACTIVE = "night"
_REVISION = 0
_APPLIED = False
# Under the red light (a red multiply over the night theme) every themed
# colour turns to its grey brightness: a multiply keeps only the red channel,
# so a green accent would go almost black while its grey stays readable.
_RED = False


def _grey(value):
    """``value``'s colours as greys that keep brightness under a red multiply."""
    if isinstance(value, dict):
        return {key: _grey(item) for key, item in value.items()}
    if (isinstance(value, tuple) and len(value) in (3, 4)
            and all(isinstance(part, int) for part in value)):
        r, g, b = value[:3]
        level = max(r, round(0.2126 * r + 0.7152 * g + 0.0722 * b))
        return (level, level, level) + tuple(value[3:])
    if isinstance(value, tuple):
        return tuple(_grey(item) for item in value)
    return value


def red_light() -> bool:
    return _RED


def active() -> str:
    return _ACTIVE


def revision() -> int:
    return _REVISION


def is_light() -> bool:
    return _ACTIVE == "day"


def high_contrast() -> bool:
    return _ACTIVE == "contrast"


def c(token: str) -> tuple:
    """An RGB colour of the active theme."""
    value = _RGB[_ACTIVE][token]
    return _grey(value) if _RED else value


def mix(a, b, amount: float) -> tuple:
    """Blend two colours (tokens or RGB tuples) by ``amount`` (0 = a)."""
    first = c(a) if isinstance(a, str) else a
    second = c(b) if isinstance(b, str) else b
    return tuple(round(x + (y - x) * amount) for x, y in zip(first, second))


def pick(night, day, contrast=None) -> tuple:
    """A literal colour per theme (for a drawing's own accent colours)."""
    if _ACTIVE == "day":
        return day
    if _ACTIVE == "contrast" and contrast is not None:
        return contrast
    return _grey(night) if _RED else night


def phosphor(palette: str) -> tuple:
    """The waterfall trace colour of a sonar phosphor choice."""
    ramps = PHOSPHOR_PALETTES[_ACTIVE]
    value = ramps.get(palette, ramps["cyan"])
    return _grey(value) if _RED else value


# Chart water tint by the clock's light (multiplies the water tokens; the
# grid, land and symbols keep their colours so the picture stays readable).
# The day theme's light water only dims a little at night.
WATER_TINT = {"day": 1.0, "dusk": 0.8, "night": 0.6}
WATER_TINT_LIGHT = {"day": 1.0, "dusk": 0.97, "night": 0.93}


def water_color(color, stage: str):
    """A water token darkened for a daylight stage."""
    factor = (WATER_TINT_LIGHT if is_light() else WATER_TINT).get(stage, 1.0)
    return tuple(int(channel * factor) for channel in color)


def theme_for(game) -> str:
    """The theme a game draws with now.

    High contrast wins; the red light forces the night theme (a red
    multiply over a light screen would glare); otherwise the player's
    ``Preferences.theme``."""
    preferences = getattr(game, "preferences", None)
    if bool(getattr(preferences, "high_contrast", False)):
        return "contrast"
    if getattr(game, "red_light_lit", False):
        return "night"
    chosen = getattr(preferences, "theme", "night")
    return chosen if chosen in SWITCH_THEMES else "night"


def set_theme(name: str, red: bool = False) -> str:
    """Make ``name`` the active theme and reassign every colour global.

    Every consumer (config.COLOR_*, sonar_view's module colors,
    editor_widgets.PALETTE) reads these as live module attributes, so
    reassigning them here covers all existing call sites. Imports are local
    to avoid a cycle: sonar_view/editor_widgets import layout, and layout
    calls this function.
    """
    global _ACTIVE, _REVISION, _APPLIED, _RED
    if name not in THEMES:
        name = "night"
    red = bool(red) and name == "night"
    tone = _grey if red else (lambda value: value)
    from src.core import config
    from src.ui import editor_widgets, sonar_view
    if (name == _ACTIVE and _APPLIED and red == _RED
            and config.COLOR_TEXT == tone(CONFIG_COLORS[name]["COLOR_TEXT"])):
        return name
    _ACTIVE = name
    _RED = red
    _APPLIED = True
    _REVISION += 1
    for key, value in CONFIG_COLORS[name].items():
        setattr(config, key, tone(value))
    for key, value in SONAR_COLORS[name].items():
        setattr(sonar_view, key, tone(value))
    sonar_view.PHOSPHOR_PALETTES = tone(dict(PHOSPHOR_PALETTES[name]))
    editor_widgets.PALETTE = editor_widgets.EditorPalette(**tone(EDITOR_PALETTES[name]))
    _apply_globals()
    return name


# Colour constants other modules keep at module level, reassigned with the
# theme: module -> {name: token, or (night, day) / (night, day, contrast)
# literals}. Scenes seen through optics (sky, sea, ship models) and the
# damage cutaways keep their own colours in every theme.
THEMED_GLOBALS = {
    "src.ui.layout": {"BRACKET_COLOR": "line_strong", "METER_TRACK": "well",
                      "COMMAND_KEY_COLOR": "accent", "COMMAND_DESCRIPTION_COLOR": "text"},
    "src.ui.console": {"LED_OFF": ((44, 56, 76), (203, 210, 220), (60, 60, 60)),
                       "WATER": ((40, 110, 160), (59, 130, 200)),
                       "AIR": ((30, 38, 52), (238, 241, 245), (0, 0, 0))},
    "src.ui.overlay_style": {
        "PANEL_FILL": ((11, 15, 25, 232), (255, 255, 255, 240), (0, 0, 0, 255)),
        "PANEL_RIM": "line_strong", "HIGHLIGHT": "select",
        "PHOSPHOR": ((0, 255, 135), (30, 58, 138)),
        "PHOSPHOR_DIM": ((16, 185, 129), (30, 58, 138)),
        "GOLD": ((245, 158, 11), (180, 83, 9)),
        "BACKDROP_VEIL": ((2, 6, 10, 110), (243, 244, 246, 150))},
    # The start-screen hunt behind the main menu and every overlay: a day
    # scene under a light veil in the light theme, the night hunt otherwise.
    # The damage-control pictures (section, profile, boat cutaway): a light
    # drawing board by day; floodwater, fire and teams keep their colours.
    "src.ui.damage_section": {
        "HULL_FILL": ((40, 50, 56), (203, 213, 223)), "ROOM_FILL": ((22, 44, 48), (232, 237, 243)),
        "STEEL": ((150, 168, 172), (51, 65, 85)), "STEEL_DIM": ((84, 100, 106), (148, 163, 184)),
        "SEA": ((6, 30, 52), (219, 234, 254)), "SEA_LINE": ((90, 160, 200), (37, 99, 235)),
        "WATER_TOP": ((132, 194, 223), (29, 78, 216)), "SPRAY": ((160, 214, 240), (59, 130, 246)),
        "GAS": ((150, 190, 60), (101, 163, 13)), "MARK": ((210, 222, 220), (71, 85, 105)),
        "KEEL": ((22, 40, 48), (148, 163, 184)), "INK": ((170, 186, 186), (71, 85, 105)),
        "DOOR_FILL": ((10, 20, 24), (232, 237, 243)),
        "BOAT_TINTS": ({"stern": (92, 86, 40), "engine": (96, 70, 36), "battery": (90, 46, 44),
                        "quarters": (46, 84, 52), "control": (64, 66, 104), "bow": (96, 54, 48)},
                       {"stern": (231, 223, 176), "engine": (236, 210, 173),
                        "battery": (240, 200, 196), "quarters": (201, 227, 204),
                        "control": (207, 210, 238), "bow": (239, 201, 193)})},
    "src.ui.splash_view": {
        "SKY_TOP": ((3, 7, 16), (126, 170, 208)),
        "SKY_HORIZON": ((20, 44, 62), (206, 224, 236)),
        "SEA_TOP": ((10, 44, 58), (84, 134, 160)),
        "SEA_DEEP": ((2, 9, 15), (30, 66, 90)),
        "STEEL": ((19, 36, 46), (78, 90, 100)),
        "STEEL_RIM": ((84, 150, 158), (38, 48, 58)),
        "HULL_UNDERWATER": ((8, 26, 34), (44, 78, 98)),
        "SUB_STEEL": ((7, 24, 30), (24, 44, 56)),
        "SUB_RIM": ((46, 110, 116), (60, 100, 116)),
        "PING": ((70, 190, 190), (200, 235, 240)),
        "PHOSPHOR": ((150, 255, 205), (30, 58, 138)),
        "PHOSPHOR_DIM": ((62, 140, 128), (55, 65, 81)),
        "GOLD": ((236, 204, 128), (180, 83, 9)),
        "MENU_VEIL": ((2, 6, 10, 170), (243, 244, 246, 185))},
    "src.ui.stations.helicopter": {"DECK_STEEL": ((70, 110, 118), (120, 140, 150)),
                                   "DECK_SEA": ((18, 60, 74), (170, 200, 222))},
    "src.ui.uboot_pilot": {
        "_CAUTION_TINT": ((120, 96, 30), (250, 226, 170)),
        "_DANGER_TINT": ((128, 44, 40), (248, 200, 196)),
        "_CONTOUR": ((44, 86, 110), (120, 150, 180)),
        "_LAND": ((36, 56, 64), (231, 225, 210)),
        "_BAND_SHADES": (
            ((46, 96, 128), (36, 82, 114), (28, 70, 102), (22, 58, 90), (16, 46, 78),
             (11, 36, 66), (8, 28, 56), (5, 21, 46)),
            ((184, 208, 232), (194, 215, 236), (203, 222, 240), (211, 228, 243),
             (218, 233, 246), (224, 237, 248), (230, 241, 250), (236, 244, 252)))},
    "src.ui.nato_symbols": {
        "SELECT_RING": ((235, 235, 220), (31, 41, 55)),
        "AFFILIATION_COLORS": (
            {"UNKNOWN": (251, 191, 36), "FRIEND": (96, 165, 250),
             "NEUTRAL": (52, 211, 153), "HOSTILE": (248, 113, 113)},
            {"UNKNOWN": (161, 98, 7), "FRIEND": (29, 78, 216),
             "NEUTRAL": (4, 120, 87), "HOSTILE": (220, 38, 38)},
            {"UNKNOWN": (240, 228, 66), "FRIEND": (0, 114, 178),
             "NEUTRAL": (0, 158, 115), "HOSTILE": (213, 94, 0)})},
    "src.ui.map_fx_view": {"PING": ((110, 190, 255), (29, 78, 216)),
                           "ECHO": ((255, 236, 150), (161, 98, 7)),
                           "SPLASH": ((255, 214, 120), (180, 83, 9)),
                           "FOC": ((240, 190, 90), (180, 83, 9)),
                           "GLOW": ((70, 190, 130), (4, 120, 87))},
    "src.ui.mic_meter": {"QUIET": ((70, 200, 140), (5, 150, 105)),
                         "NEAR": ((230, 180, 60), (180, 83, 9)),
                         "FAR": ((235, 70, 60), (220, 38, 38)),
                         "DARK": ((30, 44, 52), (226, 232, 240))},
    "src.ui.hit_inset": {"BACK": ((6, 18, 26), (238, 241, 245)),
                         "TRACE": ((110, 232, 200), (4, 120, 87))},
    "src.ui.menu_list": {"TRACK_COLOR": "well", "THUMB_COLOR": "line_strong",
                         "ARROW_COLOR": "text"},
    "src.ui.weather_station": {"SHADOW_COLOR": ((70, 30, 30), (248, 215, 215)),
                               "RAY_COLOR": ((90, 220, 150), (4, 120, 87)),
                               "SOFAR_COLOR": ((110, 170, 230), (29, 78, 216))},
    "src.ui.chart_symbols": {"WRECK_COLOR": ((150, 180, 200), (71, 85, 105)),
                             "ROCK_COLOR": ((220, 190, 120), (146, 64, 14))},
    "src.ui.stations.radio_chart": {"_BACKGROUND": ((6, 16, 28), (222, 232, 244)),
                                    "_LAND": ((30, 48, 58), (231, 225, 210))},
    "src.ui.profile_cursor": {"CURSOR_COLOR": ((150, 235, 255), (29, 78, 216))},
    "src.ui.debrief_view": {"OWN_COLOR": ((90, 160, 255), (29, 78, 216))},
    "src.ui.sferics": {"CRACKLE": ((170, 176, 230), (67, 56, 202))},
}


def _apply_globals() -> None:
    import importlib
    for module_name, names in THEMED_GLOBALS.items():
        module = importlib.import_module(module_name)
        for name, spec in names.items():
            if isinstance(spec, str):
                value = c(spec)
            else:
                index = THEMES.index(_ACTIVE)
                value = spec[index] if index < len(spec) else spec[0]
                if _RED:
                    value = _grey(value)
            setattr(module, name, value)


def configure_for(game=None) -> bool:
    """Apply the game's theme; True when it is the high-contrast one."""
    red = bool(getattr(game, "red_light_lit", False))
    return set_theme(theme_for(game), red=red) == "contrast"


def next_theme(current: str) -> str:
    """The options row's order: night -> day -> high contrast -> night."""
    return THEMES[(THEMES.index(current) + 1) % len(THEMES)] if current in THEMES else "night"


def css_tokens() -> str:
    """The browser's token block: one rule per theme (``--t-<name>``)."""
    blocks = []
    selectors = {"night": ':root, :root[data-theme="night"]',
                 "day": ':root[data-theme="day"]',
                 "contrast": ':root[data-theme="contrast"]'}
    for name in THEMES:
        lines = [f"{selectors[name]} {{",
                 f"  color-scheme: {'light' if name == 'day' else 'dark'};"]
        lines += [f"  --t-{key.replace('_', '-')}: {value};"
                  for key, value in TOKENS[name].items()]
        lines.append("}")
        blocks.append("\n".join(lines))
    # The red light greys the night tokens (see _grey), last so it wins.
    lines = [':root[data-theme="night"][data-red-light] {']
    lines += ["  --t-{}: #{:02X}{:02X}{:02X};".format(key.replace("_", "-"),
                                                      *_grey(_RGB["night"][key]))
              for key in TOKENS["night"]]
    lines.append("}")
    blocks.append("\n".join(lines))
    return "\n".join(blocks) + "\n"
