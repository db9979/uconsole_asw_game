"""Tilt, zoom and stabilizer of the bridge binoculars and the periscope
eyepiece (presentation only, never saved)."""

import sys
from pathlib import Path

import pygame

from src.core import config, optics
from src.ui import horizon, sight_scene

sys.path.insert(0, str(Path(__file__).parent))
from test_lookout_glasses import _key, _lookout_page  # noqa: E402
from test_opfor_sub import _game  # noqa: E402
from test_uboot_scope import _clear, _local_boat  # noqa: E402


def test_optics_bounds():
    sight = optics.lookout_glasses()
    assert sight.fov_deg == config.LOOKOUT_GLASSES_FOV_DEG and not sight.stabilized
    for _ in range(40):
        sight.tilt(10.0)
        sight.zoom(1)
    assert sight.elevation_deg == config.LOOKOUT_GLASSES_ELEVATION_DEG[1]
    assert sight.fov_deg == config.LOOKOUT_GLASSES_FOV_DEG / config.LOOKOUT_GLASSES_POWERS[-1]
    scope = optics.periscope()
    scope.zoom(1)
    assert scope.fov_deg == config.UBOOT_SCOPE_FOV_DEG / 4.0      # 1.5x to 6x


def test_binocular_keys_take_the_arrows_from_the_telegraph_only_while_raised():
    game = _game(5)
    _lookout_page(game)
    telegraph = game.ship.telegraph
    _key(game, pygame.K_b)
    _key(game, pygame.K_UP)
    _key(game, pygame.K_UP, pygame.KMOD_SHIFT)
    _key(game, pygame.K_e)
    _key(game, pygame.K_SPACE)
    sight = game.lookout_optics
    assert sight.elevation_deg == config.SIGHT_TILT_STEP_DEG + config.SIGHT_TILT_STEP_FAST_DEG
    assert sight.fov_deg == config.LOOKOUT_GLASSES_FOV_DEG / 2.0 and sight.stabilized
    assert game.ship.telegraph == telegraph
    _key(game, pygame.K_b)                       # lowered: the arrows are the telegraph again
    _key(game, pygame.K_UP)
    assert game.ship.telegraph != telegraph


def test_periscope_keys_tilt_power_and_stabilizer():
    game, boat = _local_boat()
    _clear(game)
    _key(game, pygame.K_1)
    _key(game, pygame.K_1)
    sight = boat.scope_optics
    _key(game, pygame.K_UP)
    _key(game, pygame.K_PERIOD)
    _key(game, pygame.K_SPACE)
    assert sight.elevation_deg == config.SIGHT_TILT_STEP_DEG
    assert sight.fov_deg == config.UBOOT_SCOPE_FOV_DEG / 4.0 and sight.stabilized
    _key(game, pygame.K_COMMA)
    assert sight.fov_deg == config.UBOOT_SCOPE_FOV_DEG
    game.draw()


def _picture(**kwargs):
    surface = pygame.Surface((400, 200))
    args = dict(line_of_sight=0.0, fov_deg=20.0, night=False, visibility_nm=30.0,
                motion=(20.0, 0.1), outlines=[], sky=sight_scene.plain_sky(False),
                sea_state=3.0, anim_t=1.0)
    args.update(kwargs)
    horizon.draw_horizon(surface, (0, 0, 400, 200), **args)
    return surface


def _horizon_row(surface):
    """The row of the sharpest change down a clear column (sky to sea)."""
    column = [surface.get_at((200, y))[:3] for y in range(30, 200)]
    jumps = [sum(abs(a - b) for a, b in zip(column[i], column[i + 1]))
             for i in range(len(column) - 1)]
    return 30 + jumps.index(max(jumps))


def test_tilting_up_lowers_the_horizon_and_the_stabilizer_steadies_it():
    level = _horizon_row(_picture(motion=(0.0, 0.0)))
    up = _horizon_row(_picture(motion=(0.0, 0.0), elevation_deg=4.0))
    assert up - level >= 4.0 * 400 / 20.0 - 6          # 4 degrees at 20 px per degree
    rolling = _horizon_row(_picture())
    steady = _horizon_row(_picture(stabilized=True))
    assert abs(steady - level) < abs(rolling - level)
