import math
from types import SimpleNamespace

import pytest

from src.core import config
from src.sensors.tracks import TrackPicture
from src.sonar.sonar import Contact, SonarSystem
from src.sonar.tma import BearingTrack


def observe(picture, bearing, now, range_nm=10.0, source="RADAR-L"):
    return picture.observe(
        track_id="A-1", kind="FLG", target_id=1, source=source,
        bearing=bearing, range_nm=range_nm, observer_x=0.0,
        observer_y=0.0, course=None, quality=.8, now=now, label="TEST")


def test_track_bearing_smoothing_takes_short_arc_across_north():
    picture = TrackPicture()
    track = observe(picture, 359.0, 0.0)
    observe(picture, 1.0, config.OBS_RADAR_EPOCH_S)
    assert abs(config.angle_diff_deg(track.bearing, 0.0)) < 1.0
    assert track.raw_bearing == 1.0


def test_track_same_epoch_is_not_an_independent_filter_sample():
    picture = TrackPicture()
    track = observe(picture, 10.0, 0.0)
    observe(picture, 80.0, config.OBS_RADAR_EPOCH_S / 2.0)
    assert track.bearing == 10.0
    assert track.raw_bearing == 10.0
    assert len(track.measurement_history) == 1


def test_track_position_is_derived_only_from_measurements_and_is_deterministic():
    first = TrackPicture()
    second = TrackPicture()
    for now, bearing, distance in ((0.0, 90.0, 10.0), (.5, 100.0, 12.0),
                                   (1.0, 95.0, 11.0)):
        a = observe(first, bearing, now, distance)
        b = observe(second, bearing, now, distance)
    assert (a.bearing, a.range_nm, a.x, a.y) == (
        b.bearing, b.range_nm, b.x, b.y)
    assert a.x != pytest.approx(11.0 * math.sin(math.radians(95.0)))


def test_track_restore_requires_canonical_rows_and_stale_track_expires():
    picture = TrackPicture(stale_s=2.0)
    track = observe(picture, 45.0, 1.0)
    legacy = {key: value for key, value in picture.serialize()[0].items()
              if not key.startswith("raw_")
              and key not in ("measurement_epoch", "measurement_history")}
    restored = TrackPicture(stale_s=2.0)
    with pytest.raises(ValueError):
        restored.restore([legacy])
    restored.restore(picture.serialize())
    assert restored.tracks(2.9)[0].bearing == track.bearing
    assert restored.tracks(3.1) == []


def test_passive_update_cannot_rotate_fresh_ping_position():
    contact = Contact(1, 1, "ping", "sub")
    contact._fx, contact._fy = 4.0, 7.0
    contact.update_ping(90.0, 8.0, 60.0, 1.0, 0.0)
    ping_pos = contact.ping_pos
    contact.update_passive(180.0, 1.0, .6, "", 2.0)
    assert contact.passive_bearing == 180.0
    assert contact.bearing == 90.0
    assert contact.ping_pos == ping_pos
    assert (contact.observed_x, contact.observed_y) == ping_pos
    assert contact.bearing_uncertainty_deg is not None

    contact._fx = 5.0
    contact.update_passive(270.0, 1.0, .6, "", 4.0)
    assert (contact.observed_x, contact.observed_y) == ping_pos
    assert contact.bearing != contact.passive_bearing


def test_tma_position_is_separate_and_presentation_does_not_change_raw_bearings():
    contact = Contact(1, 1, "passiv", "sub")
    contact._fx = contact._fy = 0.0
    contact.update_passive(20.0, 1.0, .8, "", 0.0)
    raw = list(contact.raw_bearings)
    solution = SimpleNamespace(pos=(3.0, -4.0), course=40.0, speed=8.0,
                               quality=.8)
    contact.update_tma(solution, 10.0)
    assert contact.tma_pos == (3.0, -4.0)
    assert (contact.observed_x, contact.observed_y) == contact.tma_pos
    assert contact.raw_bearings == raw


def test_sonar_noise_is_smooth_deterministic_and_track_keeps_raw_epochs():
    target = SimpleNamespace(id=5, sensor_seed=123)
    ship = SimpleNamespace(speed=6.0)
    first = SonarSystem(1)
    second = SonarSystem(999)
    values_a = [first._observed_bearing(target, 359.0, ship, .7, "BOW", t)
                for t in (1.99, 2.0, 2.01)]
    values_b = [second._observed_bearing(target, 359.0, ship, .7, "BOW", t)
                for t in (1.99, 2.0, 2.01)]
    assert values_a == values_b
    assert abs(config.angle_diff_deg(values_a[2], values_a[0])) < .1

    track = BearingTrack()
    track.add(1.0, 10.0, 0.0, 0.0, 0.0)
    track.add(1.0, 80.0, 0.0, 0.0, 0.0)
    assert [point.bearing for point in track.pts] == [10.0]
