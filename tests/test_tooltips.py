"""Context tooltips use displayed observations and consume pin input safely."""

import json
from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator, message
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
    assert layout.MIN_OPERATIONAL_FONT >= 14


def test_tooltip_truncation_is_explicit_and_title_uses_distinct_size():
    pygame.font.init()
    layout.configure_for(large_text=False)
    payload = layout.tooltip_payload("TITLE " * 20, *("body " * 30 for _ in range(12)))
    rect, lines = layout.tooltip_rect(payload, (50, 50), bounds=(0, 0, 260, 120))
    assert pygame.Rect(0, 0, 260, 120).contains(rect)
    assert lines[-1].endswith("...")
    assert layout.font(layout.TOOLTIP_TITLE_SIZE, bold=True).get_height() > \
        layout.font(layout.TOOLTIP_BODY_SIZE).get_height()


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


@pytest.mark.parametrize("station,pos,english", [
    (Station.BRIDGE, (700, 150), "COURSE / RUDDER"),
    (Station.SONAR, (100, 200), "BROADBAND BIN"),
    (Station.WEAPONS, (700, 150), "FIRE-CONTROL SOLUTION"),
    (Station.DAMAGE, (30, 100), "Flooding"),
    (Station.OPZ, (1100, 120), "OPERATIONS / CIC CONTROLS"),
    (Station.RADIO, (30, 120), "HFDF BEARINGS"),
    (Station.ENGINE, (30, 120), "ENGINE ORDER"),
    (Station.HELICOPTER, (700, 120), "FLIGHT STATUS HSP-5"),
])
def test_every_station_tooltip_is_composed_in_english(game, station, pos, english):
    game.tr = Translator("en").translate
    game.station = station
    payload = game.tooltip_at(pos)
    assert english in "\n".join((payload["title"], *payload["lines"]))


def test_radio_tooltip_localizes_structured_feed_message(game):
    game.tr = Translator("en").translate
    game.station = Station.RADIO
    game.messages[:] = [("12:34", message("runtime.helo.return"))]
    payload = game.tooltip_at((1100, 120))
    assert payload["lines"][0] == "12:34 HSP-5: return ordered"
    assert "__u_jagd_i18n__" not in payload["lines"][0]


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


def test_map_contact_position_uses_observation_datum_without_truth_fallback():
    class ObservationOnly:
        observed_x = 12.0
        observed_y = 34.0
        range_est = 8.0

        def __getattr__(self, name):
            if name in {"x", "y", "target", "entity", "truth"}:
                pytest.fail(f"UI read hidden truth: {name}")
            raise AttributeError(name)

    assert map_view.contact_position(
        ObservationOnly(), NS(x=1.0, y=2.0)) == (12.0, 34.0)


def test_map_marker_hit_and_tooltip_recompute_bearing_from_observed_position(game):
    game.tr = Translator("en").translate
    game.map_view.set_rect(config.MAP_RECT)
    observed = (game.ship.x + 10.0, game.ship.y)
    track = {"track_id": "S-9", "label": "FIX", "kind": "AIS",
             "observed_x": observed[0], "observed_y": observed[1],
             "bearing": 270.0, "source": "RADAR-S", "quality": .8, "age": 2.0}
    game.radar_tracks = lambda: [track]
    marker = game.map_view.world_to_screen(*observed)
    first = map_view.map_hit_target(game, marker)
    assert "090.0" in first["lines"][1]

    game.ship.x += 5.0
    game.ship.y += 5.0
    second = map_view.map_hit_target(game, marker)
    assert "045.0" in second["lines"][1]
    assert second["id"] == "map-track:S-9"


def test_opz_marker_hit_and_tooltip_share_position_bearing_after_ownship_move(monkeypatch):
    monkeypatch.setattr(config, "STATION_RECT", config.FULL_STATION_RECT)

    class Track:
        track_id, label, kind, source = "S-9", "FIX", "AIS", "RADAR-S"
        observed_x, observed_y, bearing, range_nm = 10.0, 0.0, 270.0, 10.0

        def age(self, now): return 2.0
        def display_quality(self, now, stale): return .8

    track = Track()
    fake = NS(ship=NS(x=0.0, y=0.0, course=0.0), opz_tracks=lambda: [track],
              opz_affiliation=lambda _: "NEUTRAL", radar_range_nm=20.0,
              sim_t=10.0, air_picture=NS(stale_s=8.0), helo=None,
              tr=Translator("en").translate)
    ppi = stations_view.opz_ppi_rect()
    radius = ppi.w // 2
    first_pos = (ppi.centerx + 10.0 / 20.0 * radius, ppi.centery)
    first = stations_view.opz_hit_target(fake, first_pos)
    assert "090.0" in first["lines"][1]

    fake.ship.x, fake.ship.y = 5.0, 5.0
    second_pos = (ppi.centerx + 5.0 / 20.0 * radius,
                  ppi.centery - 5.0 / 20.0 * radius)
    second = stations_view.opz_hit_target(fake, second_pos)
    assert "045.0" in second["lines"][1]


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
