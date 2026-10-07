"""The frame canvas stays opaque on every system (Mac menu blinking).

On macOS the window's pixel format carries an alpha channel and a plain
``pygame.Surface`` copies it.  The translucent veils and panels of every
menu then left most canvas pixels partly transparent, and the Mac window
blinked behind an open menu.  The canvas is created without alpha.
"""

import pygame

from src.core.game import Game, make_canvas
from src.ui import quality

ARGB = (0xFF0000, 0xFF00, 0xFF, 0xFF000000)


def _mac_window(size):
    """A window surface in the macOS format (32 bit with alpha)."""
    window = pygame.Surface(size, 0, 32, ARGB)
    window.set_alpha(None)
    window.fill((0, 0, 0, 255))
    return window


def _min_alpha(surface) -> int:
    alpha = pygame.surfarray.pixels_alpha(surface)
    try:
        return int(alpha.min())
    finally:
        del alpha


def test_canvas_has_no_alpha_channel():
    canvas = make_canvas(1280, 720)
    assert canvas.get_bitsize() == 32
    assert canvas.get_masks()[3] == 0


def test_game_draws_on_an_opaque_canvas():
    game = Game(seed=3, start_menu=False, show_splash=False, audio_enabled=False)
    assert game.screen.get_masks()[3] == 0


def test_a_mac_like_canvas_turns_translucent_behind_a_veil():
    # The cause: a translucent veil blitted onto a canvas that has alpha.
    canvas = _mac_window((64, 64))
    veil = pygame.Surface((64, 64), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 110))
    canvas.blit(veil, (0, 0))
    assert _min_alpha(canvas) < 255
    # The fix: the opaque canvas blitted onto the same window stays opaque.
    opaque = make_canvas(64, 64)
    opaque.fill((40, 40, 40))
    opaque.blit(veil, (0, 0))
    window = _mac_window((64, 64))
    window.blit(opaque, (0, 0))
    assert _min_alpha(window) == 255


def test_open_menu_frame_reaches_a_mac_window_opaque():
    game = Game(seed=3, start_menu=False, show_splash=False, audio_enabled=False)
    game.options_open = True
    for _ in range(3):
        game._t += 1 / 30
        game.draw()
    for level in ("normal", "low"):
        for size in ((1280, 720), (1512, 850), (2560, 1440)):
            window = _mac_window(size)
            window.blit(quality.scale_canvas(game.screen, size, level), (0, 0))
            assert _min_alpha(window) == 255, (level, size)
