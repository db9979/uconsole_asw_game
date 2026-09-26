"""OPZ shows a (noisy, observed) altitude for air tracks; aircraft is a class."""

import pytest
import pygame

from src.air.live_aircraft import LiveAircraft
from src.core import config
from src.core.game import Game
from src.core.i18n import Translator, localize
from src.core.station import Station
from src.ui import layout, stations_view


@pytest.fixture
def game():
    result = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    result.mission.asm_count = 0
    result.sim_t = 10.0
    return result


def _live(game, altitude_m=9000.0, dx=1.0):
    seq = game.flights.next_seq()
    aircraft = LiveAircraft("abc123", "TEST", seq, x=game.ship.x + dx,
                            y=game.ship.y, altitude_m=altitude_m, course=90.0,
                            speed_kn=300.0, t=0.0)
    game.live_traffic.aircraft["abc123"] = aircraft
    return aircraft


def _air_track(game, track_id):
    game._update_air_picture(full_scan=True)
    return next(t for t in game.air_picture.tracks(game.sim_t, ("FLG",))
                if t.track_id == track_id)


def test_measurement_noise_is_bounded_and_deterministic():
    import random
    values = [config.measure_altitude_m(random.Random(seed), 9000.0)
              for seed in range(200)]
    limit = 9000.0 * config.RADAR_ALTITUDE_ERR_FRAC + config.RADAR_ALTITUDE_ERR_M
    assert all(abs(v - 9000.0) <= limit + 1e-9 for v in values)
    assert len(set(values)) > 100
    assert config.measure_altitude_m(random.Random(3), 100.0) == \
        config.measure_altitude_m(random.Random(3), 100.0)
    assert config.measure_altitude_m(random.Random(3), 0.0) >= 0.0


def test_flight_altitude_is_deterministic_and_spread():
    altitudes = {config.flight_altitude_m(seq) for seq in range(1, 60)}
    assert len(altitudes) > 10
    low = config.FLIGHT_RADAR_ALTITUDE_M * (1 - config.FLIGHT_ALTITUDE_SPREAD / 2)
    high = config.FLIGHT_RADAR_ALTITUDE_M * (1 + config.FLIGHT_ALTITUDE_SPREAD / 2)
    assert all(low - 1e-9 <= value <= high + 1e-9 for value in altitudes)
    assert config.flight_altitude_m(7) == config.flight_altitude_m(7)


def test_live_aircraft_radar_track_carries_an_observed_altitude(game):
    aircraft = _live(game, 9000.0)
    track = _air_track(game, f"A-{aircraft.seq}")
    limit = 9000.0 * config.RADAR_ALTITUDE_ERR_FRAC + config.RADAR_ALTITUDE_ERR_M
    assert track.altitude_m is not None
    assert abs(track.altitude_m - 9000.0) <= limit


def test_opz_observation_and_web_row_carry_the_altitude(game):
    aircraft = _live(game, 9000.0)
    track = _air_track(game, f"A-{aircraft.seq}")
    observation = next(o for o in game.opz_tracks()
                       if getattr(o, "altitude_m", None) is not None)
    assert observation.altitude_m == track.altitude_m
    assert observation.speed_kn is None or observation.speed_kn >= 0.0


def test_altitude_is_smoothed_not_replaced_by_each_noisy_fix(game):
    aircraft = _live(game, 9000.0)
    first = _air_track(game, f"A-{aircraft.seq}").altitude_m
    game.sim_t += 1.0
    second = _air_track(game, f"A-{aircraft.seq}").altitude_m
    limit = 9000.0 * config.RADAR_ALTITUDE_ERR_FRAC + config.RADAR_ALTITUDE_ERR_M
    assert abs(second - first) <= 2 * limit * config.OBS_ALTITUDE_SMOOTH + 1e-6


def test_non_air_tracks_have_no_altitude(game):
    game._update_air_picture(full_scan=True)
    assert all(t.altitude_m is None for t in game.air_picture.tracks(
        game.sim_t) if t.kind != "FLG")


def test_opz_panel_and_tooltip_show_altitude_for_air_tracks(game):
    game.translator = Translator("en")
    game.tr = game.translator.t
    aircraft = _live(game, 9000.0)
    track = _air_track(game, f"A-{aircraft.seq}")
    observation = next(o for o in game.opz_tracks() if o.altitude_m is not None)
    payload = stations_view._track_tooltip(game, observation)
    assert any("Altitude" in line and f"{track.altitude_m:.0f}" in line
               for line in payload["lines"])
    game.station = Station.OPZ
    game.station_page = 1  # OPZ_TARGET page carries the selected-track ledger
    game.opz_selected_track_id = observation.track_id
    texts = []
    original = layout.blit_line
    layout.blit_line = lambda s, text, *args, **kwargs: (
        texts.append(localize(text, game.tr)), original(s, text, *args, **kwargs))[1]
    try:
        game.draw()
    finally:
        layout.blit_line = original
    assert any("9" in text and "m / available" in text and "Altitude" in text
               for text in texts), texts


def test_aircraft_is_a_selectable_classification(game):
    assert "FLUGZEUG" in config.PLAYER_CLASSES
    aircraft = _live(game, 9000.0)
    _air_track(game, f"A-{aircraft.seq}")
    observation = next(o for o in game.opz_tracks() if o.altitude_m is not None)
    assert game.classify_opz_observation(observation.observation_id, "FLUGZEUG") is True
    stored = next(o for o in game.opz_tracks()
                  if o.observation_id == observation.observation_id)
    assert stored.classification == "FLUGZEUG"
    from src.core.i18n import display_value
    assert display_value("classification", "FLUGZEUG", Translator("en").t) == "Aircraft"
    assert display_value("classification", "FLUGZEUG", Translator("de").t) == "Flugzeug"


def test_classification_cycle_reaches_aircraft_and_wraps(game):
    aircraft = _live(game, 9000.0)
    _air_track(game, f"A-{aircraft.seq}")
    observation = next(o for o in game.opz_tracks() if o.altitude_m is not None)
    game.opz_selected_track_id = observation.track_id
    seen = []
    for _ in range(len(config.PLAYER_CLASSES) + 1):
        game._cycle_opz_classification()
        current = game.opz_fusion.classifications.get(observation.observation_id)
        seen.append(current)
    assert "FLUGZEUG" in seen
    assert seen[len(config.PLAYER_CLASSES)] is None  # wraps back to unclassified
