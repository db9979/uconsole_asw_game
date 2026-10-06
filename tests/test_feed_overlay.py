"""The F11 event log: readable in every colour scheme and closed by mouse,
and a click on it never reaches the station behind."""

import ast
from pathlib import Path

import pygame
import pytest

from src.core import config, uboot_local
from src.core.game import Game
from src.core.station import Station
from src.ui import pointer, theme
from src.ui.feedback import FeedEntry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_theme():
    yield
    theme.set_theme("night")
    # The log's click blocker belongs to the last drawn frame; later tests
    # that click without drawing must not inherit it.
    pointer.reset()


def _game(monkeypatch, side=None):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    if side:
        game.local_side = side
        game.update(0.1)          # the crewed boat comes aboard
        assert uboot_local.boat(game) is not None
    return game


def _click(game, pos, button=1):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=pos))


def _contrast(a, b):
    def lum(rgb):
        parts = [c / 255 for c in rgb[:3]]
        parts = [p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4 for p in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("name", theme.THEMES)
def test_every_log_colour_is_the_chosen_schemes_and_readable(name):
    theme.set_theme(name)
    for category, (color_name, _tag) in config.FEED_CATEGORIES.items():
        color = FeedEntry("18:00", category, "x").color()
        assert color == getattr(config, color_name)
        # Readable on the log's own ground (WCAG large-text ratio at least).
        assert _contrast(color, config.COLOR_FEED_BG) >= 3.0, (name, category, color)


def test_no_module_keeps_a_scheme_colour_from_import_time():
    """A ``config.COLOR_*`` read into a module constant keeps the night
    colour when the scheme changes (the bug of the light F11 log)."""
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Module and class bodies run once at import, and so do the
        # defaults of their functions (nested functions are made per call).
        scopes = [tree.body] + [node.body for node in tree.body
                                if isinstance(node, ast.ClassDef)]
        for body in scopes:
            values = []
            for node in body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    values.append(node)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    values.extend(d for d in node.args.defaults + node.args.kw_defaults if d)
            for value in values:
                if any(isinstance(sub, ast.Attribute) and sub.attr.startswith("COLOR_")
                       and isinstance(sub.value, ast.Name) and sub.value.id == "config"
                       for sub in ast.walk(value)):
                    offenders.append(f"{path.relative_to(ROOT)}:{value.lineno}")
    assert offenders == []


@pytest.mark.parametrize("side", [None, "uboot"])
def test_log_is_opaque_and_closes_with_its_cross(monkeypatch, side):
    game = _game(monkeypatch, side)
    game.station = Station.SONAR
    game.feed_overlay_open = True
    game.draw()
    rect = game.feed_overlay_rect()
    # No station drawing shows through the panel's ground.
    assert game.screen.get_at((rect.x + 2, rect.y + 2))[:3] == config.COLOR_FEED_BG
    close = next(t for t in pointer.targets("station")
                 if t.key == pygame.K_F11 and t.rect.w <= 40 and rect.contains(t.rect))
    _click(game, close.rect.center)
    assert game.feed_overlay_open is False


@pytest.mark.parametrize("side", [None, "uboot"])
def test_clicks_on_the_log_never_reach_the_station_behind(monkeypatch, side):
    game = _game(monkeypatch, side)
    game.station = Station.SONAR
    game.draw()
    rect = game.feed_overlay_rect()
    under = [t for t in pointer.targets("station")
             if rect.contains(t.rect) and not t.hover_only and t.key != pygame.K_F11]
    assert under, "the test needs a station control under the log"
    game.feed_overlay_open = True
    game.draw()
    before = (game.station, game.station_page, game.input_mode, set(game.held))
    for target in under:
        _click(game, target.rect.center)
        _click(game, target.rect.center, button=3)
        assert game.feed_overlay_open is True
        assert (game.station, game.station_page, game.input_mode, set(game.held)) == before
    # No hover frame or lamp note of the station under the panel.
    assert pointer.hover_rect(under[0].rect.center, "station") is None
    assert pointer.tip_at(under[0].rect.center) is None


def test_right_click_on_the_log_sets_no_bridge_waypoint(monkeypatch):
    game = _game(monkeypatch)
    game.station = Station.BRIDGE
    game.draw()
    spot = pygame.Rect(config.MAP_RECT).clip(game.feed_overlay_rect()).center
    _click(game, spot, button=3)
    assert len(game.route.points) == 1, "the test needs the chart under the log"
    game.feed_overlay_open = True
    game.draw()
    _click(game, spot, button=3)
    assert len(game.route.points) == 1
    assert game.feed_overlay_open is True
