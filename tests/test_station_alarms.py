"""Alarm lamps of the station tabs and the automatic red light (display only)."""

import pygame
import pytest

from src.core import station_alarms
from src.core.game import Game
from src.ui.red_light import RedLight


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield instance
    instance.audio.shutdown()


def test_quiet_frigate_has_no_lamps(game):
    assert station_alarms.frigate(game) == {}


def test_torpedo_alarm_lights_bridge_sonar_and_weapons(game):
    game.torpedo_cues = [dict(kind="HYDROPHONE", bearing=40.0, t=game.sim_t)]
    levels = station_alarms.frigate(game)
    assert {key: levels[key] for key in ("bridge", "sonar", "weapons")} == dict.fromkeys(
        ("bridge", "sonar", "weapons"), "danger")
    assert station_alarms.red_light_target(game, levels) == 1.0
    game.torpedo_cues = [dict(kind="HYDROPHONE", bearing=40.0,
                              t=game.sim_t - station_alarms.TORPEDO_FRESH_S - 1)]
    assert station_alarms.frigate(game) == {}


def test_fire_blinks_the_damage_lamp_and_flooding_warns(game):
    room = next(iter(game.damage.compartments.values()))
    room.fire = 0.4
    assert station_alarms.frigate(game)["damage"] == "danger"
    room.fire = 0.0
    room.state = "FLUTEND"
    assert station_alarms.frigate(game)["damage"] == "warn"


def test_danger_blinks_warning_is_steady():
    phases = {station_alarms.lamp_on("danger", t / 10.0) for t in range(10)}
    assert phases == {True, False}
    assert all(station_alarms.lamp_on("warn", t / 10.0) for t in range(10))
    assert not station_alarms.lamp_on(None, 0.0)


def test_red_light_follows_the_night(game):
    game.world.hour = 2.0
    assert game.world.is_night()
    assert station_alarms.red_light_target(game, {}) == 1.0
    game.world.hour = 12.0
    assert station_alarms.red_light_target(game, {}) == 0.0


def test_red_light_fades_on_wall_time():
    light = RedLight()
    assert light.step(0.0, 0.0) == 0.0
    halfway = light.step(1.0, station_alarms.FADE_S / 2)
    assert 0.4 < halfway < 0.6
    assert light.step(1.0, station_alarms.FADE_S * 2) == 1.0
    surface = light.overlay((8, 8))
    assert surface.get_at((0, 0))[:3] == (255, 60, 60)


def test_option_cycles_automatic_on_off(game):
    assert game.red_light_mode() == "auto"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F10))
    for _ in range(game._OPTION_ROWS.index("night_mode")):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    seen = []
    for _ in range(3):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        seen.append(game.red_light_mode())
    assert seen == ["on", "off", "auto"]


def test_alarms_reach_the_web_projection(game):
    from src.commander import projections
    game.torpedo_cues = [dict(kind="HYDROPHONE", bearing=40.0, t=game.sim_t)]
    rows = projections._alarm_rows(station_alarms.frigate(game))
    assert dict(station="bridge", level="danger") in rows
    assert all(set(row) == {"station", "level"} for row in rows)
