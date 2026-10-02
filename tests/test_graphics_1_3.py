"""Plan 1.3, phase 10: anti-aliased chart lines, the chart's light of the
hour, the rain/storm hatch and the shared horizon on the lookout page."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.preferences import Preferences, load_preferences, save_preferences
from src.core.station import Station
from src.sensors import lookout_id
from src.ui import horizon, layout, lines, quality, theme
from src.ui.stations import bridge as bridge_view
from src.world import atmosphere


def _game(seed=31, start_menu=False):
    return Game(seed=seed, start_menu=start_menu, audio_enabled=False, language="en")


def _mean_brightness(surface, rect) -> float:
    rect = pygame.Rect(rect)
    total = 0
    count = 0
    for x in range(rect.x + 4, rect.right - 4, 16):
        for y in range(rect.y + 4, rect.bottom - 4, 16):
            total += sum(surface.get_at((x, y))[:3])
            count += 1
    return total / max(1, count)


def test_graphics_preference_round_trips_and_reads_the_old_line_switch(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps({"language": "de", "audio": False}), encoding="utf-8")
    loaded = load_preferences(path)
    assert loaded.graphics == "normal" and loaded.aa_lines is False   # Linux default
    expected = Preferences(graphics="full", aa_lines=True)
    assert save_preferences(expected, path) == path
    assert load_preferences(path) == expected
    path.write_text(json.dumps({"aa_lines": "yes", "graphics": "ultra"}), encoding="utf-8")
    assert load_preferences(path).graphics == "normal"
    # A settings file from before the levels: the line switch meant "full".
    path.write_text(json.dumps({"aa_lines": True}), encoding="utf-8")
    assert load_preferences(path).graphics == "full"
    path.write_text(json.dumps({"graphics": "low", "aa_lines": True}), encoding="utf-8")
    low = load_preferences(path)
    assert low.graphics == "low" and low.aa_lines is False


def test_daylight_stage_boundaries():
    assert [atmosphere.daylight_stage(hour) for hour in (0.0, 5.49, 5.5, 6.49, 6.5, 12.0,
                                                          18.49, 18.5, 19.49, 19.5, 23.9)] == [
        "night", "night", "dusk", "dusk", "day", "day", "day", "dusk", "dusk", "night", "night"]
    assert atmosphere.daylight_stage(30.0) == atmosphere.daylight_stage(6.0)
    assert theme.water_color((100, 200, 50), "night") == (60, 120, 30)
    assert theme.water_color((100, 200, 50), "day") == (100, 200, 50)
    assert set(theme.WATER_TINT) == set(atmosphere.DAYLIGHT_STAGES)


def test_chart_water_darkens_with_the_clock():
    game = _game()
    game.station = Station.BRIDGE
    brightness = {}
    for stage, hour in (("day", 12.0), ("dusk", 19.0), ("night", 23.0)):
        game.world.hour = hour
        assert game.world.daylight_stage() == stage
        game.draw()
        brightness[stage] = _mean_brightness(game.screen, config.MAP_RECT)
    assert brightness["day"] > brightness["dusk"] > brightness["night"]
    # The boat's chart follows the same light.
    game.local_side = "uboot"
    game._update(0.05)
    game.world.hour = 12.0
    game.draw()
    day = _mean_brightness(game.screen, config.MAP_RECT)
    game.world.hour = 23.0
    game.draw()
    assert day > _mean_brightness(game.screen, config.MAP_RECT)


def test_weather_band_hatches_the_chart_and_a_storm_frames_it(monkeypatch):
    game = _game()
    game.station = Station.BRIDGE
    game.world.hour = 12.0
    calm = dict(game.world.weather_values())
    calm.update(rain_intensity=0.0, wind_speed_kn=5.0, visibility_nm=20.0)
    monkeypatch.setattr(game.world, "weather_values", lambda: dict(calm))
    monkeypatch.setattr(game.world, "weather_kind", lambda: "clear")
    game.draw()
    dry = _mean_brightness(game.screen, config.MAP_RECT)
    rain = dict(calm, rain_intensity=0.9, wind_speed_kn=20.0)
    monkeypatch.setattr(game.world, "weather_values", lambda: dict(rain))
    game.draw()
    wet = _mean_brightness(game.screen, config.MAP_RECT)
    assert wet > dry
    monkeypatch.setattr(game.world, "weather_kind", lambda: "storm")
    game.draw()
    rect = pygame.Rect(config.MAP_RECT)
    assert game.screen.get_at((rect.x + 1, rect.centery))[:3] == config.COLOR_WARN
    # Light rain below the threshold draws nothing.
    monkeypatch.setattr(game.world, "weather_values", lambda: dict(calm, rain_intensity=0.1))
    monkeypatch.setattr(game.world, "weather_kind", lambda: "rain")
    game.draw()
    assert _mean_brightness(game.screen, config.MAP_RECT) == pytest.approx(dry)


def test_line_helper_switches_between_plain_and_anti_aliased_paths():
    surfaces = {}
    for enabled in (False, True):
        lines.ENABLED = enabled
        surface = pygame.Surface((64, 64))
        surface.fill((0, 0, 0))
        lines.line(surface, (255, 255, 255), (2, 3), (60, 41))
        lines.lines(surface, (200, 200, 200), True, [(5, 50), (30, 58), (55, 45)])
        lines.polygon(surface, (120, 200, 120), [(10, 10), (40, 12), (30, 30)])
        lines.polygon(surface, (120, 200, 120), [(45, 5), (60, 8), (50, 25)], 1)
        lines.line(surface, (255, 0, 0), (0, 63), (63, 0), 3)   # thick: plain in both
        colours = {surface.get_at((x, y))[:3] for x in range(64) for y in range(64)}
        surfaces[enabled] = colours
    lines.ENABLED = False
    # gfxdraw blends edge pixels: more distinct colours than the plain path.
    assert len(surfaces[True]) > len(surfaces[False])
    game = _game()
    game.preferences = replace(game.preferences, graphics="full")
    layout.configure_for(game)
    assert lines.ENABLED is True
    game.preferences = replace(game.preferences, graphics="normal")
    layout.configure_for(game)
    assert lines.ENABLED is False
    # The chart draws with the anti-aliased path on both sides.
    game.preferences = replace(game.preferences, graphics="full")
    layout.configure_for(game)
    game.station = Station.BRIDGE
    game.draw()
    game.local_side = "uboot"
    game._update(0.05)
    game.draw()
    layout.configure_for(large_text=False)
    lines.ENABLED = False


def test_options_setup_page_carries_the_graphics_level(monkeypatch):
    from src.core import game_draw
    monkeypatch.setattr(game_draw, "save_preferences", lambda *_a, **_k: None)
    game = _game(start_menu=True)
    assert Game._OPTION_ROWS_SETUP == ("local_side", "graphics", "speech", "microphone", "llm")
    assert len(Game._OPTION_ROWS) == 13          # page 1 stays within its footer
    game._open_administration("options")
    game._set_options_page(1)
    assert game._option_rows() is Game._OPTION_ROWS_SETUP
    game.draw()
    assert game.preferences.graphics == "normal"
    game._handle_administration_key(pygame.K_DOWN)
    assert game.options_sel == 1
    game._handle_administration_key(pygame.K_RETURN)
    assert game.preferences.graphics == "full" and game.preferences.aa_lines is True
    assert lines.ENABLED is True
    game.draw()
    game._handle_administration_key(pygame.K_RETURN)
    assert game.preferences.graphics == "low" and lines.ENABLED is False
    assert quality.LEVEL == "low"
    game.draw()
    game._handle_administration_key(pygame.K_LEFT)
    assert game.preferences.graphics == "full"
    # The mouse hits the drawn row, not the side's help text under row 0.
    rects = Game._option_row_hit_rects(Game._OPTION_ROWS_SETUP)
    assert rects[1] == Game._options_row_rects()[6]
    game._window_to_canvas = lambda pos: pos
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rects[1].center))
    assert game.options_sel == 1
    game._set_preference("graphics", "normal")
    assert lines.ENABLED is False and quality.LEVEL == "normal"
    layout.configure_for(large_text=False)


def _track(**values):
    base = dict(bearing=30.0, range_nm=4.0, kind="SURFACE", last_seen=100.0,
                label=lookout_id.encode(lookout_id.RECOGNIZED, "WARSHIP", "FRIGATE", None))
    base.update(values)
    return SimpleNamespace(**base)


def test_lookout_outlines_follow_the_lookout_report():
    game = SimpleNamespace(sim_t=100.5)
    rows = bridge_view.lookout_outlines(game, [
        _track(),
        _track(bearing=90.0, range_nm=8.0, label=lookout_id.encode(
            lookout_id.RECOGNIZED, "MERCHANT", "TANKER", None)),
        _track(bearing=200.0, kind="FLG", label=lookout_id.encode(0, None, None, None),
               last_seen=90.0),
        _track(bearing=250.0, kind="TORP", label=lookout_id.encode(0, None, None, None)),
        _track(bearing=10.0, range_nm=None),
    ])
    assert [(row[0], row[2], row[3]) for row in rows] == [
        (30.0, "warship", False), (90.0, "merchant", False), (200.0, "aircraft", True),
        (250.0, "torpedo", False)]
    # Apparent length: 120 m at 4 NM is about 0.93 degrees; twice the range halves it.
    assert rows[0][1] == pytest.approx(0.928, abs=0.01)
    assert rows[1][1] < rows[0][1]


@pytest.mark.parametrize("language", ["en", "de"])
def test_lookout_page_draws_the_shared_horizon(language):
    game = Game(seed=7, start_menu=False, audio_enabled=False, language=language)
    game.station = Station.BRIDGE
    game.station_page = 2
    game.world.hour = 12.0
    game.air_picture.observe(
        track_id="L-test", kind="SURFACE", target_id=0, source="LOOKOUT",
        bearing=(game.ship.course + 15.0) % 360.0, range_nm=3.0,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None, quality=0.8,
        now=game.sim_t, label=lookout_id.encode(lookout_id.RECOGNIZED, "WARSHIP", "FRIGATE",
                                                None))
    assert len(bridge_view.lookout_outlines(game, game.lookout_sightings())) == 1
    game.draw()
    game.world.hour = 23.0
    game.draw()
    # The strip sits inside the station panel and paints the horizon colours.
    rect = pygame.Rect(config.STATION_RECT)
    colours = {game.screen.get_at((x, y))[:3]
               for x in range(rect.x + 8, rect.right - 8, 24)
               for y in range(rect.y + 40, rect.y + 260, 12)}
    assert len(colours) > 12
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        assert horizon.relative_offset(350.0, 10.0) == -20.0
