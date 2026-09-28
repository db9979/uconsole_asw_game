"""The support link: a valid QR code, drawn in the main menu only."""

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.ui import support


def _finder(rows, top, left):
    block = [rows[top + y][left:left + 7] for y in range(7)]
    return block == ["1111111", "1000001", "1011101", "1011101",
                     "1011101", "1000001", "1111111"]


def test_qr_rows_form_a_version_3_code_with_three_finder_patterns():
    rows = support.QR_ROWS
    assert len(rows) == 29 and all(len(row) == 29 and set(row) <= {"0", "1"} for row in rows)
    assert _finder(rows, 0, 0) and _finder(rows, 0, 22) and _finder(rows, 22, 0)
    assert support.SUPPORT_URL == "https://" + support.SUPPORT_SHORT


def test_support_corner_stays_on_the_canvas():
    surface = pygame.Surface((config.SCREEN_W, config.SCREEN_H))
    rect = support.draw_support_corner(surface, config.SCREEN_W - 24, 600,
                                       (255, 255, 255), (128, 128, 128))
    assert surface.get_rect().contains(rect)
    assert support.qr_surface(3).get_width() == (29 + 4) * 3


@pytest.fixture
def game():
    return Game(seed=4242, start_menu=False, audio_enabled=False, language="en")


def test_main_menu_draws_the_support_code_and_missions_do_not(game, monkeypatch):
    calls = []
    monkeypatch.setattr("src.core.game_draw.draw_support_corner",
                        lambda *args, **kwargs: calls.append(args))
    game.draw()
    assert calls == []
    game.in_menu = True
    game.main_menu = True
    game.draw()
    assert len(calls) == 1
