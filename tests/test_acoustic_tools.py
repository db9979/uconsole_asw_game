"""Manual acoustic analysis tools and the operator-assistance setting."""

import hashlib
import json
from dataclasses import replace

import numpy as np
import pygame
import pytest

from src.core.game import Game
from src.core.i18n import localize
from src.core.station import Station
from src.sensors.esm import ESMTrack, library_emitters
from src.sonar import analysis_tools as tools
from src.ui import layout
from src.ui import sonar_view


def key(game, value, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod))


def test_integration_windows_and_running_mean():
    columns = [[float(i)] * 3 for i in range(300)]
    assert tools.window_columns(2) == 1
    assert tools.window_columns(8) == 32
    assert tools.window_columns(64) == 256
    assert tools.integrate(columns, 2).tolist() == [299.0] * 3
    assert tools.integrate(columns, 8)[0] == pytest.approx(np.mean(range(268, 300)))
    rows = tools.integrate_rows([[1.0], [3.0], [5.0], [7.0]], 8)
    assert rows[-1][0] == pytest.approx(4.0) and rows.shape == (4, 1)


def test_operator_arithmetic_only():
    assert tools.harmonic_comb(50.0, 160.0) == [(1, 50.0), (2, 100.0), (3, 150.0)]
    blades, deviation, rpm = tools.blade_count(2.5, 12.6)
    assert blades == 5 and deviation == pytest.approx(.04) and rpm == 150.0
    assert tools.blade_count(None, 12.0) is None
    assert tools.clamp_cursor(400.0, "lofar") == 300.0
    assert tools.clamp_cursor(12.26, "demon") == 12.5
    assert tools.vernier_window(5.0) == (0.0, 20.0)


@pytest.fixture
def sonar_game():
    game = Game(seed=6060, start_menu=False, audio_enabled=False)
    game.station = Station.SONAR
    return game


def test_cursor_band_edges_notch_and_integration_keys(sonar_game):
    game = sonar_game
    game.sonar_page = 1
    start = game.sonar_tools.lofar_cursor_hz
    key(game, pygame.K_x)
    key(game, pygame.K_x, pygame.KMOD_SHIFT)
    assert game.sonar_tools.lofar_cursor_hz == start + 11.0
    key(game, pygame.K_z, pygame.KMOD_CTRL)
    assert game.sonar.band_low_hz == start + 11.0
    key(game, pygame.K_x)
    key(game, pygame.K_x, pygame.KMOD_CTRL)
    assert game.sonar.band_high_hz == start + 12.0
    key(game, pygame.K_n, pygame.KMOD_SHIFT)
    assert game.sonar.operator_notch_hz == start + 12.0
    column = [1.0] * 110
    processed = game.sonar.process_lofar_column(column, game.ship)
    bins = [index for index in range(110)
            if abs(__import__("src.core.config", fromlist=["x"]).lofar_bin_freq(index)
                   - (start + 12.0)) < 2.5]
    assert bins and all(processed[index] < .2 for index in bins)
    assert [game.sonar_tools.integration_s] == [2]
    for expected in (8, 16, 64, 2):
        key(game, pygame.K_q)
        assert game.sonar_tools.integration_s == expected
    key(game, pygame.K_q, pygame.KMOD_SHIFT)
    assert game.sonar_tools.vernier is True


def test_demon_marks_give_blade_count(sonar_game):
    game = sonar_game
    game.sonar_page = 2
    game.set_sonar_cursor("demon", 3.0)
    key(game, pygame.K_k)
    game.set_sonar_cursor("demon", 15.0)
    key(game, pygame.K_k)
    assert (game.sonar_tools.shaft_hz, game.sonar_tools.blade_hz) == (3.0, 15.0)
    rows = [localize(row[0], game.tr) for row in sonar_view._detail_rows(game, 2)]
    assert any("5 blades" in row and "180 rpm" in row for row in rows)
    key(game, pygame.K_k)
    assert game.sonar_tools.shaft_hz is None and game.sonar_tools.blade_hz is None


def test_assist_off_hides_automatic_analysis_and_training_shows_it(sonar_game):
    game = sonar_game
    for _ in range(40):
        game.update(1.0)
    game.sonar.demon_analysis = dict(blade_rate_hz=12.0, confidence=.9,
                                     modulation_peak_hz=12.0)
    demon = [.01] * 80
    demon[11] = .9
    game.sonar.receiver.demon_spectrum = demon
    game.sonar.integration_columns.clear()
    game.sonar.receiver.peaks = [(40.0, .8)]
    off = [localize(row[0], game.tr) for page in (1, 2)
           for row in sonar_view._detail_rows(game, page)]
    assert not any("40.0 Hz" in row or "rpm" in row.lower() for row in off)
    game.preferences = replace(game.preferences, operator_assist="training")
    training = [localize(row[0], game.tr) for page in (1, 2)
                for row in sonar_view._detail_rows(game, page)]
    assert any("40.0 Hz" in row for row in training)
    assert any("rpm" in row.lower() for row in training)


def test_esm_library_lookup_is_unranked_and_annotation_order_neutral():
    game = Game(seed=6061, start_menu=False, audio_enabled=False)
    emitters = game.runtime_catalog.emitters
    track = ESMTrack("E" + "1" * 16, 0.0, 0.0, 45.0, 1.0, 9.4e9, 1000.0,
                     "pulse", .8, 0.0, 0.0)
    library = library_emitters(track, emitters)
    assert library and all(item.score is None for item in library)
    for item in library:
        low, high = emitters[item.emitter_key].frequency_band_hz
        assert low <= track.frequency_hz <= high
    assert game.eloka_display_analysis(track) is None
    game.preferences = replace(game.preferences, operator_assist="training")
    assert game.eloka_display_analysis(track) is not None
    assert all(item.score is not None for item in game.eloka_display_candidates(track))


def test_assistance_setting_never_changes_the_simulation():
    from src.enemies.animal import Animal
    from src.enemies.decoy import Decoy
    from src.enemies.sub import Sub
    from src.enemies.surface import SurfaceShip
    from src.weapons.torpedo import EnemyTorpedo
    counters = {cls: cls._next_id for cls in (Sub, Animal, SurfaceShip, Decoy,
                                              EnemyTorpedo)}
    states = []
    for assist in ("off", "training"):
        for cls, value in counters.items():   # entity IDs are process-global
            cls._next_id = value
        game = Game(seed=6062, start_menu=False, audio_enabled=False)
        game.preferences = replace(game.preferences, operator_assist=assist)
        game.station = Station.SONAR
        for step in range(90):
            game.update(1.0)
            if step % 15 == 0:
                game.draw()
        states.append(json.dumps(game.save_state(), sort_keys=True, default=str))
    # Compare digests: a failing diff of two 1 MB strings would take minutes.
    assert hashlib.sha256(states[0].encode()).hexdigest() == \
        hashlib.sha256(states[1].encode()).hexdigest()


def test_lofar_and_demon_pages_draw_without_truncation_in_both_modes(sonar_game):
    game = sonar_game
    for _ in range(30):
        game.update(1.0)
    for assist in ("off", "training"):
        game.preferences = replace(game.preferences, operator_assist=assist)
        for page in (1, 2):
            game.sonar_page = page
            with layout.capture_truncations() as cut:
                game.draw()
            assert not cut, (assist, page, cut)
