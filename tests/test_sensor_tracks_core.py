import math
import random
from unittest.mock import Mock

import pytest

from src.air.asm import ASM
from src.core.game import Game
from src.enemies.surface import SurfaceShip
from src.enemies.sub import Sub
from src.sensors.tracks import TrackPicture
from src.sonar.sonar import Contact


def observe(picture, *, source, now, bearing=90.0, range_nm=None,
            observer_x=0.0, observer_y=0.0):
    return picture.observe(
        track_id="T-1", kind="SURFACE", target_id=1, source=source,
        bearing=bearing, range_nm=range_nm, observer_x=observer_x,
        observer_y=observer_y, course=None, quality=.8, now=now,
        label="T-1")


def test_measurement_cadence_is_source_aware_and_refreshes_only_on_samples():
    hfdf = TrackPicture(300.0)
    track = observe(hfdf, source="HFDF", now=0.0, bearing=10.0)
    observe(hfdf, source="HFDF", now=.25, bearing=80.0)
    assert track.last_seen == 0.0
    assert track.raw_bearing == 10.0
    observe(hfdf, source="HFDF", now=.5, bearing=20.0)
    assert track.last_seen == .5

    esm = TrackPicture(30.0)
    track = observe(esm, source="ESM", now=0.0, bearing=10.0)
    observe(esm, source="ESM", now=.5, bearing=20.0)
    assert track.last_seen == .5

    sonar = TrackPicture(30.0)
    track = observe(sonar, source="SONAR-BRG", now=0.0, bearing=10.0)
    observe(sonar, source="SONAR-BRG", now=.25, bearing=20.0)
    assert track.last_seen == .25
    assert len(track.measurement_history) == 2


def test_sonar_picture_uses_canonical_bearing_without_a_second_delay():
    picture = TrackPicture(30.0)
    track = observe(picture, source="SONAR-BRG", now=1.0, bearing=77.0)

    observe(picture, source="SONAR-BRG", now=1.25, bearing=78.0)

    assert track.bearing == 78.0
    assert track.raw_bearing == 78.0


def test_correlated_bearing_sources_have_continuous_displayed_steps(monkeypatch):
    game = Game(seed=908, audio_enabled=False)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game.radar_on = False
    warship = SurfaceShip(game.ship.x + 4.0, game.ship.y,
                          random.Random(908), hostile=True)
    warship.emitter = True
    game.warships = [warship]
    game.civilians = []
    game.flights.flights = []
    asm = ASM(game.ship.x + 4.0, game.ship.y, 0.0, 18, game.rng_asm)
    asm.jamming = Mock(return_value=True)
    game.asms = [asm]
    sub = Sub(game.ship.x + 4.0, game.ship.y, 8.0, 0.0, "diesel_alt",
              random.Random(908), runtime_catalog=game.runtime_catalog)
    sub.endurance.phase = "RADIO"
    sub.endurance.radio_left_s = 10.0
    sub.x, sub.y = game.ship.x + 4.0, game.ship.y
    game.subs = [sub]

    displayed = {"ESM": [], "HOJ": [], "HFDF": []}
    for now in (9.5, 10.0, 10.5):
        game.sim_t = now
        game._update_air_picture()
        game._update_esm_picture()
        game._update_radio_picture()
        displayed["ESM"].append(game.eloka_tracks()[0].bearing)
        displayed["HOJ"].append(game.air_picture._tracks["M-18"].bearing)
        displayed["HFDF"].append(
            game.radio_picture._tracks[f"H-{sub.id}"].bearing)

    for bearings in displayed.values():
        assert max(abs(math.remainder(after - before, 360.0))
                   for before, after in zip(bearings, bearings[1:])) < 1.0


def test_position_is_canonical_and_survives_fresh_bearing_source_handoff():
    picture = TrackPicture(30.0)
    track = observe(picture, source="RADAR-S", now=0.0, range_nm=10.0)

    observe(picture, source="ESM", now=5.0, bearing=180.0,
            observer_x=1.0)

    assert (track.x, track.y) == pytest.approx((10.0, 0.0))
    assert track.range_nm == pytest.approx(9.0)
    assert track.bearing == pytest.approx(90.0)
    assert math.hypot(track.x - 1.0, track.y) == pytest.approx(track.range_nm)

    observe(picture, source="ESM", now=35.0, bearing=180.0,
            observer_x=1.0)
    assert track.x is track.y is track.range_nm is None


def test_radar_source_handoff_is_immediate_and_geometry_consistent():
    picture = TrackPicture(30.0)
    track = observe(picture, source="ESM", now=0.0, bearing=130.0)

    observe(picture, source="RADAR-S", now=.5, bearing=90.0,
            range_nm=12.0)

    assert track.source == "RADAR-S"
    assert (track.bearing, track.range_nm, track.x, track.y) == pytest.approx(
        (90.0, 12.0, 12.0, 0.0))


def test_stale_sonar_republication_keeps_measurement_age(monkeypatch):
    game = Game(seed=905, audio_enabled=False)
    contact = Contact(11, 1100, "passiv", "sub")
    contact.last_seen = 3.0
    contact.confidence = contact.quality = 1.0
    contact.passive_bearing = 90.0
    contact._fx, contact._fy = game.ship.x, game.ship.y
    monkeypatch.setattr(game.sonar, "update", Mock())
    monkeypatch.setattr(game.sonar, "active_contacts", lambda: [contact])

    game.sim_t = 20.0
    game._update_sensors(.25)
    game.sim_t = 21.0
    game._update_sensors(.25)

    track = game.air_picture._tracks["U-1100"]
    assert track.last_seen == 3.0
    assert track.age(game.sim_t) == 18.0
    assert len(track.measurement_history) == 1


def test_hfdf_capture_uses_persisted_measurement_pose_and_time(monkeypatch):
    game = Game(seed=906, audio_enabled=False)
    sub = Sub(game.ship.x + 4.0, game.ship.y, 8.0, 0.0, "diesel_alt",
              random.Random(906), runtime_catalog=game.runtime_catalog)
    sub.endurance.phase = "RADIO"
    sub.endurance.radio_left_s = 10.0
    sub.x, sub.y = game.ship.x + 4.0, game.ship.y
    game.subs = [sub]
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    measured_pose = (game.ship.x, game.ship.y)
    game.sim_t = 10.0
    game._update_radio_picture()

    rows = game.radio_picture.serialize()
    game.radio_picture = TrackPicture(300.0)
    game.radio_picture.restore(rows)
    game.ship.x += 20.0
    game.sim_t = 25.0
    game.capture_hfdf()

    assert game.hfdf_log[-1]["t"] == 10.0
    assert (game.hfdf_log[-1]["observer_x"],
            game.hfdf_log[-1]["observer_y"]) == measured_pose


def test_hoj_noise_uses_simulation_time_not_cosmetic_time():
    game = Game(seed=907, audio_enabled=False)
    asm = ASM(game.ship.x + 4.0, game.ship.y, 0.0, 17, game.rng_asm)
    asm.jamming = Mock(return_value=True)
    game.asms = [asm]
    game.civilians = []
    game.warships = []
    game.flights.flights = []
    game.sim_t, game._t = 7.0, 1.0
    game._update_air_picture()
    first = game.air_picture._tracks["M-17"].raw_bearing

    game.air_picture._tracks.clear()
    game._t = 10000.0
    game._update_air_picture()

    assert game.air_picture._tracks["M-17"].raw_bearing == first


def test_esm_continuation_is_identical_after_save_load(isolated_saves):
    game = Game(seed=909, audio_enabled=False)
    game.radar_on = False
    warship = game.warships[0]
    warship.x, warship.y = game.ship.x + 4.0, game.ship.y
    warship.emitter = True
    game.warships = [warship]
    game.civilians = []
    game.flights.flights = []
    game.asms = []
    game.esm_picture._tracks.clear()
    game.sim_t = 2.0
    game._update_esm_picture()
    game.save_to_slot(1)

    restored = Game(seed=1, audio_enabled=False)
    assert restored.load_from_slot(1)
    game.sim_t = restored.sim_t = 2.5
    game._update_esm_picture()
    restored._update_esm_picture()

    assert restored.esm_picture.serialize() == game.esm_picture.serialize()
    assert restored.esm_picture.track_seq == game.esm_picture.track_seq
