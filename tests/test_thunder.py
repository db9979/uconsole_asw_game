"""Thunderstorms: stateless lightning, thunder, sferics on HF bearings."""

import pygame
import pytest

from src.core.game import Game
from src.ui import sferics, sight_scene
from src.world import thunder


def test_only_a_storm_has_lightning():
    assert thunder.activity("rain", 0.9) == 0.0
    assert thunder.activity("storm", 0.5) == pytest.approx(0.35)
    assert thunder.activity("storm", 0.95) == 1.0
    assert thunder.sferics_factor(0.0) == 1.0
    assert thunder.sferics_factor(1.0) == pytest.approx(1.75)


def test_strikes_are_stateless_and_seeded():
    rows = [thunder.strike(7, bucket, 1.0) for bucket in range(600)]
    hits = [row for row in rows if row]
    assert 50 < len(hits) < 150          # about one strike every 12 s
    assert rows == [thunder.strike(7, bucket, 1.0) for bucket in range(600)]
    assert rows != [thunder.strike(8, bucket, 1.0) for bucket in range(600)]
    for t, bearing, distance in hits:
        assert 0.0 <= bearing < 360.0
        assert thunder.DISTANCE_NM[0] <= distance <= thunder.DISTANCE_NM[1]


def test_flash_then_thunder_after_the_sound_run():
    bucket = next(b for b in range(600) if (row := thunder.strike(7, b, 1.0))
                  and row[2] < 5.0)
    t, bearing, distance = thunder.strike(7, bucket, 1.0)
    brightness, flash_bearing, _ = thunder.flash(7, t + 0.05, 1.0)
    assert brightness > 0.3 and flash_bearing == bearing
    assert thunder.flash(7, t - 0.01, 1.0) is None or thunder.flash(7, t - 0.01, 1.0)[1] != bearing
    arrive = t + distance * thunder.NM_M / thunder.SOUND_M_S
    heard = thunder.thunder(7, arrive - 0.5, arrive + 0.5, 1.0)
    assert any(abs(row[1] - bearing) < 1e-9 for row in heard)
    assert thunder.thunder(7, arrive - 0.5, arrive + 0.5, 0.0) == []


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()


def test_storm_widens_hf_bearings_and_reaches_the_sky(game):
    game.world.set_weather_override("storm")
    assert game.world.thunderstorm() > 0.0
    sky = sight_scene.sky_state(game)
    assert sky["storm"] == pytest.approx(game.world.thunderstorm(), abs=1e-4)
    assert set(("lightning", "lightning_bearing")) <= set(sky)


def test_lightning_and_sferics_draw(game):
    surface = pygame.Surface((320, 200))
    view = sight_scene.View((0, 0, 320, 200), 90.0, 40.0, 100, 0.0)
    sky = dict(sight_scene.plain_sky(True), lightning=0.9, lightning_bearing=92.0, storm=1.0)
    before = surface.get_at((160, 20))
    sight_scene.draw_lightning(surface, view, sky)
    assert surface.get_at((160, 20)) != before
    assert sferics.ticks(0.0, 1.0) == []
    assert any(sferics.ticks(1.0, k * 0.12) for k in range(20))
    sferics.draw_rose(surface, (160, 100), 80, 1.0, 3.3)


def test_thunder_is_heard_on_the_frigate(game):
    game.world.set_weather_override("storm")
    heard = []
    game._emit_sound = lambda kind, at=None, pan=None: heard.append(kind)
    game._thunder_t = None
    for step in range(1, 1200):
        game.sim_t = step * 0.5
        game._hear_thunder()
    assert heard and set(heard) == {"thunder"}
