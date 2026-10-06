"""Frame-cost work (ray tables ahead, cheaper sensors and drawing, saves on
the worker, automatic economy): every shortcut gives the same results as the
direct computation it replaces, and display-only parts never touch the
simulation."""

import math
import os
import random
import time

import numpy as np
import pygame
import pytest

from src.core import config, game_autosave
from src.core.game import Game
from src.core.preferences import load_preferences, save_preferences
from src.sonar import propagation, raytrace
from src.ui import eco_lamp, pointer, quality, sonar_data
from src.world import grounding


@pytest.fixture
def game():
    return Game(seed=11, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")


@pytest.fixture
def no_auto_low():
    quality.set_auto_low(False)
    yield
    quality.set_auto_low(False)


# --- L1: ray tables built ahead are the tables built at once ---------------

def _keys(game, count=3):
    keys = []
    for index in range(count):
        key = propagation.ray_environment_key(
            game.world, 7.0 + 40.0 * index, game.ship.x + 3.0 * index, game.ship.y)
        if key is not None and key not in keys:
            keys.append(key)
    return keys


@pytest.mark.parametrize("worker", [False, True])
def test_prefetched_tables_equal_inline_tables(game, monkeypatch, worker):
    keys = _keys(game)
    assert keys
    raytrace.clear_cache()
    inline = {key: raytrace.cached_table(key, propagation._profile_from_key).copy()
              for key in keys}
    raytrace.clear_cache()
    monkeypatch.setattr(raytrace, "WORKER_ENABLED", worker)
    monkeypatch.setattr(raytrace, "_worker_failed", False)
    assert raytrace.prefetch(keys, propagation._profile_from_key) == len(keys)
    assert raytrace.prefetch_idle(60.0)
    for key in keys:
        assert key in raytrace._cache
        assert np.array_equal(raytrace.cached_table(key, propagation._profile_from_key),
                              inline[key])
    assert raytrace.inline_builds == 0
    raytrace.clear_cache()


def test_a_half_built_table_is_finished_exactly(game, monkeypatch):
    key = _keys(game, 1)[0]
    raytrace.clear_cache()
    expected = raytrace.cached_table(key, propagation._profile_from_key).copy()
    raytrace.clear_cache()
    # No helper process: ``service`` traces in slices on the game thread.
    monkeypatch.setattr(raytrace, "WORKER_ENABLED", False)
    monkeypatch.setattr(raytrace, "_worker", None)
    raytrace.prefetch([key], propagation._profile_from_key)
    raytrace.service(0.0)               # a slice, then the caller needs it now
    assert raytrace._active and raytrace._active[0] == key
    table = raytrace.cached_table(key, propagation._profile_from_key)
    assert np.array_equal(table, expected) and not raytrace._active
    raytrace.clear_cache()


def test_prediction_keys_are_hints_only(game):
    key = _keys(game, 1)[0]
    predicted = propagation.predicted_ray_keys(
        game.world, 7.0, game.ship.x, game.ship.y, key, (20.0, 0.0))
    assert all(len(item) == len(key) for item in predicted)
    assert key not in predicted


# --- L2/L4: cheaper paths give identical results ---------------------------

def test_hull_check_without_detail_decides_like_the_contact():
    world = Game(seed=7, start_menu=True, show_splash=False, audio_enabled=False,
                 language="en").world
    rng = random.Random(3)
    blocked = 0
    for _ in range(300):
        x, y = 290.0 + rng.uniform(-15, 15), 370.0 + rng.uniform(-15, 15)
        course = rng.uniform(0, 360)
        contact = grounding.grounding_contact(world, x, y, course)
        blocked += contact is not None
        assert world.hull_is_safe(x, y, course) is (contact is None)
    assert 0 < blocked < 300
    started = time.perf_counter()
    assert world.nearest_safe_hull(300.0, 380.0, 300.0) == (
        290.7818595057326, 362.25103141509493)
    assert time.perf_counter() - started < 1.0


def test_open_water_shortcut_never_hides_land(game):
    coast = game.world.coast
    rng = random.Random(5)
    clear = 0
    for _ in range(400):
        x, y = rng.uniform(0, coast.world_size_nm), rng.uniform(0, coast.world_size_nm)
        if not coast.open_water_near(x, y, 6.0):
            continue
        clear += 1
        for _ in range(4):
            angle = rng.uniform(0, 2 * math.pi)
            reach = rng.uniform(0.1, 6.0)
            assert not coast.land_blocks_line(x, y, x + reach * math.sin(angle),
                                              y - reach * math.cos(angle))
    assert clear > 0


@pytest.mark.parametrize("width", [300, 512, 777])
def test_vectorised_waterfall_rows_equal_row_by_row(width):
    rng = np.random.default_rng(1)
    raw = rng.random((40, 360))
    assert np.array_equal(sonar_data.circular_broadband_rows(raw, width),
                          np.asarray([sonar_data._circular_broadband(row, width)
                                      for row in raw]))
    lofar = rng.random((40, 257))
    assert np.array_equal(sonar_data.linear_lofar_rows(lofar, width),
                          np.asarray([sonar_data._linear_lofar(row, width)
                                      for row in lofar]))


def test_eloka_group_sizes_match_the_single_query(game):
    for track in game.eloka_visible_tracks():
        assert game.eloka_group_sizes().get(track.track_key, 1) == game.eloka_group_size(track)


def test_desktop_scaling_reuses_surfaces_with_the_same_pixels():
    canvas = pygame.Surface((1280, 720))
    canvas.fill((10, 20, 30))
    pygame.draw.line(canvas, (255, 255, 255), (0, 0), (1279, 719))
    first = quality.scale_canvas(canvas, (1920, 1080), "normal")
    snapshot = pygame.image.tobytes(first, "RGB")
    again = quality.scale_canvas(canvas, (1920, 1080), "normal")
    assert again is first and pygame.image.tobytes(again, "RGB") == snapshot
    assert quality.scale_canvas(canvas, (1280, 720), "normal") is canvas


# --- L3: saves written by the worker ---------------------------------------

def test_menu_save_is_written_by_the_worker_and_then_closes(game):
    game.save_ui = "save"
    sequence = game.begin_save_to_slot(2, quit_after=True)
    assert sequence and game.slot_save_running()
    game.wait_for_autosave()
    assert not game.slot_save_running() and game.save_ui is None
    assert game.running is False
    path = os.path.join(config.SAVE_DIR, "slot2.json")
    restored = Game(seed=11, start_menu=False, show_splash=False, audio_enabled=False)
    assert restored.load_from_slot(2) and restored.sim_t == game.sim_t
    assert os.path.getsize(path) > 0


def test_atomic_write_syncs_the_folder(tmp_path, monkeypatch):
    tmp_path = tmp_path / "folder"
    tmp_path.mkdir()
    synced = []
    monkeypatch.setattr(game_autosave, "_fsync_directory", synced.append)
    target = tmp_path / "slot1.json"
    game_autosave._write_atomically(str(target), b"{}", ".save-")
    assert target.read_bytes() == b"{}" and synced == [str(tmp_path)]
    assert [entry.name for entry in tmp_path.iterdir()] == ["slot1.json"]


def test_stale_staged_files_are_removed_at_start(tmp_path):
    tmp_path = tmp_path / "folder"
    tmp_path.mkdir()
    old = time.time() - 600
    names = (".autosave-abc", ".save-xyz", "tmpab12cd_9", ".settings.json.k2.tmp")
    for name in names:
        (tmp_path / name).write_text("x")
        os.utime(tmp_path / name, (old, old))
    (tmp_path / ".autosave-fresh").write_text("x")              # still being written
    (tmp_path / "slot1.json").write_text("{}")
    os.utime(tmp_path / "slot1.json", (old, old))
    assert game_autosave.remove_stale_temporaries(str(tmp_path)) == len(names)
    assert sorted(entry.name for entry in tmp_path.iterdir()) == [
        ".autosave-fresh", "slot1.json"]


# --- L5: automatic economy --------------------------------------------------

def test_frame_watch_needs_a_held_slow_picture():
    watch = quality.FrameWatch()
    assert not any(watch.feed(1 / 30) for _ in range(30 * 20))
    watch.reset()
    assert not any(watch.feed(0.1) for _ in range(40))          # 4 s at 10 FPS
    watch.reset()
    results = [watch.feed(0.1) for _ in range(60)]
    assert any(results)
    watch.reset()
    for _ in range(40):
        watch.feed(0.1)
    watch.feed(3.0)                                             # a load: start over
    assert not any(watch.feed(0.1) for _ in range(40))


def test_auto_low_draws_low_and_a_picked_level_ends_it(game, no_auto_low, monkeypatch):
    monkeypatch.setattr("src.core.game_draw.save_preferences", lambda prefs: None)
    sim_before = game.sim_t
    quality.configure("normal")
    for _ in range(80):
        game._watch_frame_rate(0.1)
    assert quality.AUTO_LOW and quality.LEVEL == "low" and quality.CHOSEN == "normal"
    quality.configure("normal")                  # layout reconfigures every frame
    assert quality.LEVEL == "low"
    assert game.sim_t == sim_before
    game._set_preference("graphics", "full")
    assert not quality.AUTO_LOW and quality.LEVEL == "full"


def test_auto_economy_can_be_switched_off(game, no_auto_low, tmp_path):
    choices = [game._graphics_choice()]
    for _ in range(len(game.GRAPHICS_CHOICES)):
        game.options_open, game.options_page = True, 1
        game.options_sel = 1
        game._handle_administration_key(pygame.K_RIGHT)
        choices.append(game._graphics_choice())
    assert set(choices) == set(game.GRAPHICS_CHOICES)
    while game._graphics_choice() != ("normal", False):
        game._handle_administration_key(pygame.K_RIGHT)
    for _ in range(80):
        game._watch_frame_rate(0.1)
    assert not quality.AUTO_LOW
    path = tmp_path / "settings.json"
    save_preferences(game.preferences, path)
    assert load_preferences(path).graphics_auto is False


def test_eco_lamp_explains_itself(game, no_auto_low):
    game.draw()
    assert not eco_lamp.shown(game)
    quality.set_auto_low(True)
    game.draw()
    lamp = eco_lamp.rect(game)
    tip = pointer.tip_at(lamp.center)
    assert tip is not None
    text = " ".join(str(part) for part in tip.values())
    assert "F10" in text
    assert game.tooltip_at(lamp.center) is not None
    for language in ("en", "de"):
        note = eco_lamp.note()
        from src.core.status_tips import localized
        from src.core.i18n import Translator
        words = localized(note, Translator(language).t)
        assert words["title"] and len(words["lines"]) == 2
