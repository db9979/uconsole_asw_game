import random
from types import SimpleNamespace

import pytest

from src.core import config
from src.enemies.sub import Sub
from src.ship.ship import Ship
from src.sonar.sonar import SonarSystem, TowState, snr_db


def world():
    return SimpleNamespace(sea_state=0, thermocline_depth_m=lambda x, y: 100)


def test_tow_state_timing_handling_envelope_and_depth_gate():
    sonar = SonarSystem(3)
    ship = Ship(0, 0, course_deg=0, speed_kn=6)
    initial_depth = sonar.towed_depth_target_m
    assert sonar.tow_state == TowState.STOWED
    assert sonar.adjust_towed_depth(20, ship.speed) == initial_depth

    assert sonar.toggle_tow(ship.speed)
    sonar.update(config.SONAR_TOWED_DEPLOY_S / 2, 180, ship, [], world())
    assert sonar.tow_state == TowState.DEPLOYING
    assert sonar.tow_payout == pytest.approx(.5)
    assert not sonar.tow_status()["available"]

    ship.speed = 15
    sonar.update(60, 240, ship, [], world())
    assert sonar.tow_payout == pytest.approx(.5)
    assert not sonar.tow_status()["handling_ok"]

    ship.speed = 6
    sonar.update(config.SONAR_TOWED_DEPLOY_S / 2, 420, ship, [], world())
    assert sonar.tow_state == TowState.STREAMED
    assert sonar.tow_payout == 1
    assert sonar.tow_performance == 0
    sonar.update(config.SONAR_TOWED_SETTLE_S, 450, ship, [], world())
    assert sonar.tow_performance == 1
    sonar.adjust_towed_depth(20, ship.speed)
    sonar.update(1, 451, ship, [], world())
    assert sonar.towed_depth_m > initial_depth

    sonar.toggle_tow(ship.speed)
    sonar.update(config.SONAR_TOWED_RETRIEVE_S, 931, ship, [], world())
    assert sonar.tow_state == TowState.STOWED
    assert sonar.tow_payout == 0


def test_tow_overspeed_fault_and_heading_lags_course():
    sonar = SonarSystem()
    ship = Ship(0, 0, course_deg=90, speed_kn=6)
    sonar.toggle_tow(ship.speed)
    sonar.update(10, 10, ship, [], world())
    assert 0 < sonar.tow_heading_deg < ship.course
    ship.speed = config.SONAR_TOWED_MAX_SAFE_KN + 1
    sonar.update(1, 11, ship, [], world())
    assert sonar.tow_state == TowState.FAULT
    assert not sonar.toggle_tow(ship.speed)


def test_hms_and_tas_own_noise_lobes_but_shaft_tonal_stays_frequency_based():
    sonar = SonarSystem()
    ship = Ship(0, 0, course_deg=40, speed_kn=8)
    sonar.update(.25, .25, ship, [], world(), mode="BOW")
    assert sonar.receiver.own_noise_lobe["bearing"] == pytest.approx(220)
    tonal = sonar.receiver.ownship_tonals[0]
    assert tonal["label"] == "OWN SHAFT"
    expected_hz = 10 + 1.9 * ship.speed
    assert tonal["frequency_hz"] == pytest.approx(expected_hz)

    ship.course = 140
    sonar.update(.25, .5, ship, [], world(), mode="TOWED")
    assert sonar.receiver.own_noise_lobe["bearing"] == pytest.approx(
        sonar.tow_heading_deg)
    assert sonar.receiver.ownship_tonals[0]["frequency_hz"] == pytest.approx(expected_hz)


def test_hms_aft_lobe_reduces_detection_range_and_snr_deterministically():
    ship = Ship(0, 0, course_deg=0, speed_kn=12)
    distance = 23.0
    fore = Sub(0, -distance, 40, 0, "diesel_alt", random.Random(7))
    aft = Sub(0, distance, 40, 0, "diesel_alt", random.Random(8))
    sonar = SonarSystem(7)

    fore_range = sonar.passive_range_nm(
        fore, distance, ship, world(), 1.0, "BOW")
    aft_range = sonar.passive_range_nm(
        aft, distance, ship, world(), 1.0, "BOW")
    sonar.update(.25, .25, ship, [fore, aft], world(),
                 advance_mechanics=False)

    assert fore_range > distance > aft_range
    assert snr_db(fore_range, distance) > snr_db(aft_range, distance)
    assert fore.id in sonar.contacts and aft.id not in sonar.contacts
    assert sonar.contacts[fore.id].snr == pytest.approx(
        snr_db(fore_range, distance))


def test_tas_lobe_follows_lagging_heading_after_course_change():
    ship = Ship(0, 0, course_deg=90, speed_kn=6)
    sonar = SonarSystem(9)
    sonar.tow_state = TowState.STREAMED
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    sonar.tow_heading_deg = 0.0
    sonar.advance_mechanics(config.SONAR_TOWED_HEADING_LAG_S, 45, ship)
    assert sonar.tow_heading_deg == pytest.approx(45.0)

    axis = 8 / 2 ** .5
    toward_ship = Sub(axis, -axis, 40, 0, "diesel_alt",
                      random.Random(10))
    away_from_ship = Sub(-axis, axis, 40, 0, "diesel_alt",
                         random.Random(11))
    toward_range = sonar.passive_range_nm(
        toward_ship, 8, ship, world(), 1.0, "TOWED")
    away_range = sonar.passive_range_nm(
        away_from_ship, 8, ship, world(), 1.0, "TOWED")

    assert away_range > toward_range


def test_tas_full_advantage_requires_full_payout_and_stability():
    ship = Ship(0, 0, course_deg=0, speed_kn=6)
    target = Sub(0, 8, 160, 0, "diesel_alt", random.Random(12))
    sonar = SonarSystem(12)
    sonar.tow_state = TowState.STREAMED
    sonar.towed_depth_m = 150.0

    sonar.tow_payout = config.SONAR_TOWED_AVAILABLE_PAYOUT
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S / 2
    partial_performance = sonar.tow_performance
    partial = sonar.passive_range_nm(target, 8, ship, world(), 1.0, "TOWED")
    sonar.tow_payout = 1.0
    sonar._tow_settle_s = config.SONAR_TOWED_SETTLE_S
    full = sonar.passive_range_nm(target, 8, ship, world(), 1.0, "TOWED")

    assert 0 < partial_performance < sonar.tow_performance == 1.0
    assert full > partial


def test_scan_decides_arrays_once_and_rejects_range_before_occlusion(monkeypatch):
    ship = Ship(0, 0, course_deg=0, speed_kn=6)
    far = [Sub(0, -(200 + i), 40, 0, "diesel_alt",
               random.Random(20 + i)) for i in range(12)]
    sonar = SonarSystem(20)
    status_calls = []
    blocked_calls = []
    original_status = sonar.tow_status
    monkeypatch.setattr(sonar, "tow_status", lambda speed=None:
                        status_calls.append(speed) or original_status(speed))
    scan_world = SimpleNamespace(
        sea_state=0, thermocline_depth_m=lambda x, y: 100,
        sonar_path_blocked=lambda *args: blocked_calls.append(args) or False)
    buoy = SimpleNamespace(active=True, x=0, y=0, seq=1)

    sonar.update(.25, .25, ship, far, scan_world, buoys=[buoy],
                 advance_mechanics=True)

    assert len(status_calls) == 1
    assert blocked_calls == []
