import pygame
import pytest

from src.ui import horizon, silhouettes


@pytest.mark.parametrize("cls", sorted(silhouettes.PROFILES))
def test_profiles_stay_in_hull_units(cls):
    profile = silhouettes.PROFILES[cls]
    for poly in [profile["hull"], *profile["blocks"]]:
        assert len(poly) >= 3
        assert all(0.0 <= u <= 1.0 and -0.1 <= v <= 0.7 for u, v in poly)


@pytest.mark.parametrize("cls", ["warship", "merchant", "unknown", "aircraft", "torpedo",
                                 "mystery"])
@pytest.mark.parametrize("width", [3, 24, 180])
def test_outline_draws_every_class_near_its_bearing(cls, width):
    surface = pygame.Surface((400, 300), pygame.SRCALPHA)
    horizon.draw_outline(surface, cls, 200, 200, width, (200, 200, 200, 255), 1.5)
    rect = surface.get_bounding_rect()
    assert rect.w > 0
    # Rotor disc, bow wave and wake may reach past the hull.
    assert rect.left >= 200 - width // 2 - 12 - width * 0.2
    assert rect.right <= 200 + width // 2 + 12 + width * 0.4


@pytest.mark.parametrize("cls", ["warship", "aircraft", "submarine"])
def test_silhouettes_animate_with_the_display_clock(cls):
    frames = []
    for t in (0.0, 0.37):
        surface = pygame.Surface((400, 300))
        silhouettes.draw_profile(surface, cls, 200, 200, 240, (200, 200, 200), t=t,
                                 rim=(90, 160, 160))
        frames.append(pygame.image.tobytes(surface, "RGB"))
    assert frames[0] != frames[1]


def test_facing_mirrors_the_profile():
    left = silhouettes.frame_for("warship", 200, 100, 100, facing=-1).point(0.0, 0.0)
    right = silhouettes.frame_for("warship", 200, 100, 100, facing=1).point(0.0, 0.0)
    assert left[0] < 200 < right[0]
