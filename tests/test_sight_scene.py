"""The eyepieces in the start screen's look (src/ui/sight_scene.py)."""

import json

import pygame
import pytest

from src.commander import projections
from src.commander.v2 import schema as web_schema
from src.core import config
from src.core.game import Game
from src.ui import horizon, layout, sight_scene, theme


@pytest.fixture(autouse=True)
def _pygame():
    pygame.init()
    yield


def _sky(hour, **kwargs):
    values = dict(lunar_age_days=14.8, moon_illumination=1.0, cloud_cover=0.25,
                  precipitation="none", rain_intensity=0.0, wind_from_deg=270.0)
    values.update(kwargs)
    return sight_scene.sky_values(hour, **values)


def test_light_follows_the_clock_with_a_dusk_ramp():
    noon, midnight = sight_scene.daylight(12.0), sight_scene.daylight(0.0)
    assert noon == (1.0, 0.0) and midnight[0] == 0.0 and midnight[1] == 0.0
    light, dusk = sight_scene.daylight(config.DAYLIGHT_END_H)
    assert 0.3 < light < 0.7 and dusk > 0.5
    # The sun rises in the east at the start of the day and sets in the west.
    assert _sky(config.DAYLIGHT_START_H)["sun_bearing"] == pytest.approx(90.0)
    assert _sky(config.DAYLIGHT_END_H)["sun_bearing"] == pytest.approx(270.0)
    assert _sky(12.5)["sun_alt_deg"] > 40.0 and _sky(0.0)["sun_alt_deg"] < 0.0


def test_sky_values_are_detached_and_match_the_web_allowlist():
    sky = _sky(23.0, precipitation="snow", rain_intensity=0.6)
    assert tuple(sky) == web_schema.SKY_FIELDS
    assert sky["precipitation"] == "snow" and sky["intensity"] == 0.6
    json.dumps(sky, allow_nan=False)
    # A full moon stands opposite the sun: up at night.
    assert sky["moon_alt_deg"] > 0.0 and sky["moon_waxing"] is False
    assert _sky(12.0, precipitation="none", rain_intensity=0.4)["intensity"] == 0.0


def _picture(sky, **kwargs):
    surface = pygame.Surface((400, 200))
    args = dict(line_of_sight=sky["moon_bearing"], fov_deg=32.0, night=False,
                visibility_nm=30.0, motion=(0.0, 0.0),
                outlines=[(sky["moon_bearing"] + 5.0, 8.0, "warship", False)],
                crosshair_deg=1.5, anim_t=2.0, sky=sky, sea_state=3.0)
    args.update(kwargs)
    horizon.draw_horizon(surface, (0, 0, 400, 200), **args)
    return surface


def test_day_night_and_weather_change_the_picture():
    night = _sky(23.0)
    day = dict(night, light=1.0, dusk=0.0)
    assert (pygame.image.tobytes(_picture(night), "RGB")
            != pygame.image.tobytes(_picture(day), "RGB"))
    rain = dict(night, precipitation="rain", intensity=0.8)
    assert (pygame.image.tobytes(_picture(rain), "RGB")
            != pygame.image.tobytes(_picture(night), "RGB"))
    # The night sky is the start screen's: darker than the day sky at the top.
    top_night = _picture(night).get_at((100, 40))
    top_day = _picture(day).get_at((100, 40))
    assert sum(top_night[:3]) < sum(top_day[:3])


def test_the_picture_is_deterministic_and_its_caches_bounded():
    sky = _sky(21.0, cloud_cover=0.8)
    first = pygame.image.tobytes(_picture(sky), "RGB")
    assert first == pygame.image.tobytes(_picture(sky), "RGB")
    for width in range(100, 140, 3):
        horizon.draw_horizon(pygame.Surface((width, 90)), (0, 0, width, 90),
                             line_of_sight=0.0, fov_deg=16.0, night=True,
                             visibility_nm=2.0, motion=(0.0, 0.0), outlines=[], sky=sky)
    assert len(sight_scene._SKY_CACHE) <= sight_scene._CACHE_MAX
    assert len(sight_scene._SHADE_CACHE) <= sight_scene._CACHE_MAX


def test_bridge_projection_carries_only_the_lookouts_outlines():
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.update(0.1)
    block = projections._lookout_glasses(game)
    assert tuple(block) == web_schema.LOOKOUT_GLASSES_FIELDS
    assert tuple(block["sky"]) == web_schema.SKY_FIELDS
    assert block["fov_deg"] == config.LOOKOUT_GLASSES_FOV_DEG
    for row in block["outlines"]:
        assert tuple(row) == web_schema.LOOKOUT_OUTLINE_FIELDS
        assert row["cls"] in web_schema.SIGHT_CLASSES
    json.dumps(block, allow_nan=False)


def test_panels_carry_corner_brackets_except_in_high_contrast():
    surface = pygame.Surface((200, 120))
    try:
        theme.configure_for(None)
        surface.fill((0, 0, 0))
        layout.box(surface, (10, 10, 180, 100))
        assert surface.get_at((11, 11))[:3] == layout.BRACKET_COLOR
        game = type("G", (), {"preferences": type("P", (), {"high_contrast": True})()})()
        theme.configure_for(game)
        surface.fill((0, 0, 0))
        layout.box(surface, (10, 10, 180, 100))
        assert surface.get_at((11, 11))[:3] != layout.BRACKET_COLOR
    finally:
        theme.configure_for(None)


def test_web_silhouettes_are_generated_from_the_uconsole_profiles():
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import gen_web_schema
    assert gen_web_schema.render_profiles() == gen_web_schema.PROFILES_JS.read_text(
        encoding="utf-8")


def test_the_sky_stays_still_while_the_horizon_rolls():
    sky = _sky(22.0, cloud_cover=0.9)
    calm = _picture(sky, motion=(0.0, 0.0), outlines=[], crosshair_deg=None)
    rolling = _picture(sky, motion=(25.0, 0.08), outlines=[], crosshair_deg=None)
    # Clouds, stars and moon in the upper sky are drawn at the same place.
    band = pygame.Rect(20, 30, 360, 30)
    assert (pygame.image.tobytes(calm.subsurface(band), "RGB")
            == pygame.image.tobytes(rolling.subsurface(band), "RGB"))


def test_the_sea_looks_different_into_across_and_down_the_waves():
    head, cross = sight_scene.sea_aspect(0.0, 0.0)
    assert head == pytest.approx(1.0) and cross == pytest.approx(0.0, abs=1e-9)
    head, cross = sight_scene.sea_aspect(0.0, 90.0)      # waves from the left
    assert head == pytest.approx(0.0, abs=1e-9) and cross == pytest.approx(1.0)
    assert sight_scene.sea_aspect(0.0, 180.0)[0] == pytest.approx(-1.0)
    sky = dict(sight_scene.plain_sky(False), wind_from_deg=0.0)
    band = (0, 110, 360, 70)
    into = _picture(sky, motion=(0.0, 0.0), outlines=[], crosshair_deg=None, sea_state=5.0,
                    line_of_sight=0.0)
    across = _picture(sky, motion=(0.0, 0.0), outlines=[], crosshair_deg=None, sea_state=5.0,
                      line_of_sight=90.0)
    assert pygame.image.tobytes(into.subsurface(band), "RGB") != \
        pygame.image.tobytes(across.subsurface(band), "RGB")


def test_heading_to_the_sea_sets_pitch_and_roll():
    from src.ui import horizon
    beam = [horizon.hull_motion(3, t / 4.0, 5.0, 90.0) for t in range(400)]
    head = [horizon.hull_motion(3, t / 4.0, 5.0, 0.0) for t in range(400)]
    peak = lambda rows, index: max(abs(row[index]) for row in rows)  # noqa: E731
    assert peak(beam, 1) > 2.0 * peak(head, 1)       # beam seas: she rolls
    assert peak(head, 0) > 2.0 * peak(beam, 0)       # head seas: she pitches
    # Looking abeam the roll lifts the horizon instead of tilting it.
    offset, tilt = horizon.view_motion(0.0, 0.05, 90.0)
    assert offset > 0 and tilt == pytest.approx(0.0, abs=1e-9)
    offset, tilt = horizon.view_motion(0.0, 0.05, 0.0)
    assert offset == pytest.approx(0.0, abs=1e-9) and tilt > 0


def test_the_bridge_weather_instrument_is_a_small_eyepiece_into_the_wind():
    from src.ui.stations import bridge as bridge_view
    surface = pygame.Surface((200, 100))

    def draw(hour, wind_from, sky=None):
        surface.fill((0, 0, 0))
        weather = dict(wind_from_deg=wind_from, visibility_nm=10.0, sea_state=3.0,
                       rain_intensity=0.0, wind_speed_kn=15.0)
        bridge_view._draw_bridge_weather(surface, (5, 5, 190, 90), weather, hour, 2.0, sky)
        return surface.copy()

    day = draw(12.0, 0.0)
    night = draw(1.0, 0.0)
    # The start screen's brackets and the turquoise wind arrow.
    assert day.get_at((186, 8))[:3] == sight_scene.FRAME
    rose = {day.get_at((x, y))[:3] for x in range(5, 45) for y in range(5, 45)}
    assert sight_scene.WIND_ARROW in rose
    assert day.get_at((100, 20))[:3] != night.get_at((100, 20))[:3]
    # The arrow blows from where the wind comes: its head (the heavier end)
    # sits low for a north wind and high for a south wind.
    def arrow_rows(picture):
        return [y for x in range(5, 45) for y in range(5, 45)
                if picture.get_at((x, y))[:3] == sight_scene.WIND_ARROW]
    north, south = arrow_rows(day), arrow_rows(draw(12.0, 180.0))
    assert sum(north) / len(north) > sum(south) / len(south) + 1.0
    # The game's own sky (clouds, sun) replaces the plain one.
    cloudy = sight_scene.sky_values(12.0, 0.0, 0.0, 0.9, "rain", 0.6, 0.0)
    assert pygame.image.tobytes(draw(12.0, 0.0, cloudy), "RGB") != \
        pygame.image.tobytes(day, "RGB")
