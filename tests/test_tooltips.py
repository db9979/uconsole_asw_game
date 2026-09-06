"""Context tooltips use displayed observations and consume pin input safely."""

import json
from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.ui import layout, map_view, sonar_view, stations_view


@pytest.fixture
def game():
    return Game(seed=808, start_menu=False, audio_enabled=False)


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_tooltip_box_wraps_flips_and_stays_on_1280x720():
    pygame.font.init()
    payload = layout.tooltip_payload(
        "LONG OPERATIONAL TITLE " * 8,
        "A long status explanation that must wrap rather than leave the canvas " * 5)
    rect, lines = layout.tooltip_rect(payload, (1279, 719))

    assert pygame.Rect(0, 0, 1280, 720).contains(rect)
    assert rect.right <= 1280 and rect.bottom <= 720
    assert rect.left < 1279 and rect.top < 719
    assert len(lines) > 3
    assert layout.MIN_OPERATIONAL_FONT >= 12


def test_click_pins_and_escape_clears_before_quit(game):
    game.station = Station.BRIDGE
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(700, 150))
    game.handle_event(click)
    assert game.pinned_tooltip is not None
    assert not game.quit_confirm

    press(game, pygame.K_ESCAPE)
    assert game.pinned_tooltip is None
    assert not game.quit_confirm
    press(game, pygame.K_ESCAPE)
    assert game.quit_confirm


def test_disabled_tooltips_suppress_hover_and_pin(game):
    game.station = Station.BRIDGE
    game.tooltips_enabled = False
    assert game.tooltip_at((700, 150)) is None
    game.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(700, 150)))
    assert game.pinned_tooltip is None


def test_pinned_snapshot_is_json_safe_and_restores_without_object_refs(game):
    game.station = Station.BRIDGE
    game.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(700, 150)))
    encoded = json.dumps(game.save_state())
    loaded = Game(seed=809, start_menu=False, audio_enabled=False)
    loaded.load_state(json.loads(encoded))

    assert loaded.pinned_tooltip == game.pinned_tooltip
    assert isinstance(loaded.pinned_tooltip["lines"], list)
    assert all(isinstance(value, str) for value in loaded.pinned_tooltip["lines"])


@pytest.mark.parametrize("station,pos", [
    (Station.BRIDGE, (700, 150)),
    (Station.SONAR, (100, 200)),
    (Station.WEAPONS, (700, 150)),
    (Station.DAMAGE, (30, 100)),
    (Station.OPZ, (1100, 120)),
    (Station.RADIO, (30, 120)),
    (Station.ENGINE, (30, 120)),
    (Station.HELICOPTER, (700, 120)),
])
def test_every_station_has_meaningful_context(game, station, pos):
    game.station = station
    payload = game.tooltip_at(pos)
    assert layout.valid_tooltip(payload) is not None
    assert payload["title"] and payload["lines"]


def test_map_context_never_reads_world_entities(game):
    class ForbiddenEntities:
        def __iter__(self):
            pytest.fail("map tooltip iterated hidden world entities")

    game.subs = game.civilians = game.warships = game.animals = ForbiddenEntities()
    game.radar_tracks = lambda: []
    game.target = game.selected_contact = None
    payload = map_view.map_hit_target(game, (100, 100))
    assert payload is not None
    assert payload["title"] == game.tr("map.position")
    assert any("NM" in line or "Wassertiefe" in line or "Water depth" in line
               or "LAND" in line or "LAND" in line.upper()
               for line in payload["lines"])


def test_sonar_contact_tooltip_does_not_read_truth_attributes(monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", config.FULL_STATION_RECT)

    class ObservedContact:
        id = 7
        bearing = 123.0
        player_class = "U_BOOT"
        snr = 8.0
        confidence = .7
        last_seen = 95.0

        def __getattr__(self, name):
            if name in {"kind", "target", "signature", "x", "y", "depth"}:
                pytest.fail(f"tooltip read hidden contact truth: {name}")
            raise AttributeError(name)

    contact = ObservedContact()
    sonar = NS(active_contacts=lambda: [contact])
    fake = NS(sonar=sonar, sonar_page=0, selected_contact=contact,
              sim_t=100.0, station=Station.SONAR)
    payload = sonar_view.sonar_hit_target(fake, (950, 360))
    assert payload["id"] == "sonar:contact:7"


def test_opz_track_tooltip_uses_observation_fields_only(monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", config.FULL_STATION_RECT)

    class ObservedTrack:
        track_id = "S-4"
        label = "TRACK-4"
        kind = "AIS"
        range_nm = 10.0
        bearing = 90.0
        source = "RADAR-S"

        def age(self, now):
            return 2.0

        def display_quality(self, now, stale):
            return .8

        def __getattr__(self, name):
            if name in {"target_id", "hostile", "target", "entity", "truth"}:
                pytest.fail(f"tooltip read hidden track truth: {name}")
            raise AttributeError(name)

    track = ObservedTrack()
    fake = NS(opz_affiliation=lambda track_id: "NEUTRAL", sim_t=20.0,
              air_picture=NS(stale_s=8.0))
    payload = stations_view._track_tooltip(fake, track)
    assert payload["id"] == "opz:track:S-4"
    assert any("RADAR-S" in line for line in payload["lines"])
