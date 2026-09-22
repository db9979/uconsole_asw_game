from types import SimpleNamespace

from src.air.live_aircraft import LiveAircraft


def test_hit_despawns_after_one_round():
    aircraft = LiveAircraft("abc123", "TEST1", 1, x=10.0, y=10.0,
                            altitude_m=3000.0, course=90.0, speed_kn=250.0, t=0.0)
    assert aircraft.despawned is False
    aircraft.hit()
    assert aircraft.despawned is True


def test_distance_and_bearing_from_frigate():
    aircraft = LiveAircraft("abc123", None, 1, x=10.0, y=0.0,
                            altitude_m=1000.0, course=0.0, speed_kn=100.0, t=0.0)
    frigate = SimpleNamespace(x=0.0, y=0.0)
    assert aircraft.distance_nm(frigate) == 10.0
    assert round(aircraft.bearing_from_frigate(frigate)) == 90


def test_extrapolates_past_the_latest_fix_using_last_course_speed():
    aircraft = LiveAircraft("abc123", None, 1, x=0.0, y=0.0,
                            altitude_m=1000.0, course=0.0, speed_kn=0.0, t=0.0)
    aircraft.push_fix(x=0.0, y=0.0, altitude_m=1000.0, course=0.0,
                      speed_kn=600.0, t=10.0)
    aircraft.advance(40.0)  # 30s past the latest fix at 600kn due north
    assert aircraft.y < 0.0  # course 0 = north = -y
    assert abs(aircraft.x) < 1e-6
