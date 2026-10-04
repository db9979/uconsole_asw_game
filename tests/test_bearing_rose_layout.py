"""The bearing rose keeps its cardinal labels ("000", "090", "180", "270")
inside its own rectangle, so text placed beside a rose (the helicopter's
status readouts, the radio and ESM panels) never meets them."""

import os

import pygame
import pytest

from src.ui import console, layout


@pytest.fixture(autouse=True)
def _display():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    yield
    layout.set_text_scale(1.0)


@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("size", [(140, 140), (190, 140), (190, 190), (300, 300), (420, 420)])
def test_rose_draws_nothing_outside_its_rect(large, size):
    layout.configure_for(large_text=large)
    surface = pygame.Surface((size[0] + 200, size[1] + 200))
    background = (1, 2, 3)
    surface.fill(background)
    rect = pygame.Rect(100, 100, *size)
    console.bearing_rose(surface, rect, [(90.0, (255, 0, 0), 3, 5.0, 0.0)],
                         course=270.0, title="test")
    outside = [(x, y) for x in range(surface.get_width()) for y in range(surface.get_height())
               if not rect.collidepoint(x, y) and surface.get_at((x, y))[:3] != background]
    assert outside == []
