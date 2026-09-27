"""uConsole bridge page 3: the lookout scope (same picture as the web lookout)."""
import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.station import Station
from src.ui import layout


@pytest.fixture
def game():
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    instance.world.land_blocks_line = lambda *args: False
    for index, actor in enumerate(instance.civilians[:2]):
        actor.x, actor.y = instance.ship.x + (2.0 + index), instance.ship.y - 1.5
    for _ in range(300):
        instance._update_sim(0.1)
    instance.station, instance.station_page = Station.BRIDGE, 2
    yield instance
    instance.audio.shutdown()


def key(instance, code):
    instance.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=""))


def test_scope_shows_only_the_lookouts_own_sightings(game):
    sightings = game.lookout_sightings()
    assert sightings, "the lookout should hold the two close merchant ships"
    assert all(track.source == "LOOKOUT" and track.x is not None for track in sightings)
    game.draw()     # renders without touching world entities for the scope


def test_comma_and_period_step_the_scope_radius_only_on_the_lookout_page(game):
    scales = config.LOOKOUT_DISPLAY_RANGES_NM
    game.lookout_range_nm = 12.0
    key(game, pygame.K_PERIOD)
    assert game.lookout_range_nm == scales[scales.index(12.0) + 1]
    for _ in range(10):
        key(game, pygame.K_PERIOD)
    assert game.lookout_range_nm == scales[-1]
    for _ in range(10):
        key(game, pygame.K_COMMA)
    assert game.lookout_range_nm == scales[0]
    game.station_page = 0
    before = game.lookout_range_nm
    key(game, pygame.K_PERIOD)
    assert game.lookout_range_nm == before


def test_scope_tooltip_explains_the_page(game):
    game.tr = Translator("en").translate
    payload = game.tooltip_at((700, 260))
    assert layout.valid_tooltip(payload) is not None
    assert payload["title"] == "LOOKOUT" and any("NM" in line for line in payload["lines"])
