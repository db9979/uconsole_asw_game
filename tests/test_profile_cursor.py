"""Pointer readout on the BT profile and the weather sound-path section."""

import pygame
import pytest

from src.core.game import Game
from src.core.i18n import localize
from src.core.station import Station
from src.ui import profile_cursor, weather_station


def labels_during_draw(game, monkeypatch, point):
    shown = []
    original = profile_cursor.draw_label
    monkeypatch.setattr(profile_cursor, "pointer", lambda _game: point)
    monkeypatch.setattr(profile_cursor, "draw_label", lambda screen, text, anchor, bounds, size=13: (
        shown.append(localize(text, game.tr)), original(screen, text, anchor, bounds, size))[1])
    game.draw()
    return shown


def test_speed_interpolates_between_measured_depths():
    assert profile_cursor.speed_at([0, 100], [1500, 1480], 25) == pytest.approx(1495)
    assert profile_cursor.speed_at([0, 100], [1500, 1480], 400) == 1480
    assert profile_cursor.speed_at([], [], 10) is None


def test_sonar_environment_reads_depth_speed_and_layer_side(monkeypatch):
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    assert game.measure_sonar_bt() is True
    game.station, game.sonar_page = Station.SONAR, 4
    assert labels_during_draw(game, monkeypatch, None) == []
    shown = labels_during_draw(game, monkeypatch, (640, 420))
    assert len(shown) == 1 and shown[0].startswith("Depth ")
    assert shown[0].endswith("below the layer")


def test_weather_section_reads_range_and_marks_shadow_and_cz(monkeypatch):
    shown = []
    monkeypatch.setattr(profile_cursor, "draw_label",
                        lambda screen, text, anchor, bounds, size=13: shown.append(text))
    profile = dict(depths_m=[0, 100, 400], speeds_m_s=[1500, 1490, 1480],
                   shadow=[[False, False], [False, True]], depth_edges_m=[0, 200, 400],
                   cz_bands_nm=[[25, 35]], range_nm=40)
    screen = pygame.Surface((400, 200))
    left, section = pygame.Rect(0, 0, 100, 200), pygame.Rect(110, 0, 200, 200)
    # Right half of the section, lower half of the depth: shadow cell and CZ.
    weather_station._profile_cursor(screen, profile, (110 + 150, 150), left, section, 400)
    text = localize(shown[-1], Game(seed=1, start_menu=False, audio_enabled=False,
                                    language="en").tr)
    assert text.startswith("30.0 NM | 300 m")
    assert "shadow zone" in text and "convergence zone" in text
    weather_station._profile_cursor(screen, profile, (50, 50), left, section, 400)
    assert len(shown) == 2
    weather_station._profile_cursor(screen, profile, None, left, section, 400)
    assert len(shown) == 2
