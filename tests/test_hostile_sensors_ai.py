"""Phase 7: submarines sense through their own suite, run their own TMA,
react with a crew delay, use ESM only at mast depth and a mast-limited
datalink."""

import math
import random
from types import SimpleNamespace

import pytest

from src.core import config
from src.data.catalog import CATALOG
from src.enemies.sub import Sub
from src.sensors.platform import (MAST_DEPTH_M, PlatformObservation,
                                  PlatformSensorSuite, exchange_friendly_datalink)


class Ocean:
    size_nm = 500.0
    sea_state = 1
    effective_sea_state = 1.0
    depth_m = staticmethod(lambda *a: 3000.0)
    thermocline_depth_m = staticmethod(lambda *a: 60.0)
    on_land = staticmethod(lambda *a: False)
    land_blocks_line = staticmethod(lambda *a: False)
    sonar_path_blocked = staticmethod(lambda *a: False)
    current_vec = staticmethod(lambda *a: (0.0, 0.0))


def test_every_catalog_submarine_uses_its_sensor_suite():
    for key in CATALOG.subs:
        sub = Sub(0.0, 0.0, 100.0, 0.0, key, random.Random(1))
        assert sub.legacy_observation_model is False


def _bearing_observation(sub, target, t):
    bearing = math.degrees(math.atan2(target[0] - sub.x, -(target[1] - sub.y))) % 360.0
    return PlatformObservation(
        track_id="Lcontact", domain="sonar", source="SONAR", observer_x=sub.x,
        observer_y=sub.y, bearing=bearing, range_nm=None, x=None, y=None,
        course=None, speed_kn=None, depth_m=None, quality=0.8, signal=0.6,
        last_seen=t, bearing_uncertainty_deg=0.5, range_uncertainty_nm=None,
        depth_uncertainty_m=None, label=None)


def test_submarine_solves_its_own_tma_from_bearings():
    sub = Sub(100.0, 100.0, 80.0, 0.0, "aip_modern", random.Random(2))
    sub.endurance = None
    sub.speed = 6.0
    world = Ocean()
    target = [106.0, 96.0]
    vx = config.kn_to_nm_per_s(12.0)
    t = 0.0
    for _ in range(420):
        t += 1.0
        target[0] += vx
        sub.update(1.0, _bearing_observation(sub, target, t), world)
        if sub.memory["contact"] is not None:
            break
    contact = sub.memory["contact"]
    assert contact is not None
    assert math.hypot(contact["x"] - target[0], contact["y"] - target[1]) < 2.0


def test_torpedo_alarm_waits_for_the_crew_reaction_time():
    sub = Sub(100.0, 100.0, 80.0, 0.0, "aip_modern", random.Random(3))
    sub.endurance = None
    delay = sub.reaction_delay_s()
    assert 2.0 <= delay <= 15.0
    sub.alert_torpedo()
    assert sub.state == "PATROLLE" and sub.torpedo_alarm_left == pytest.approx(delay)
    elapsed = 0.0
    while sub.state != "EVADE" and elapsed < 20.0:
        sub.update(0.5, None, Ocean())
        elapsed += 0.5
    assert sub.state == "EVADE"
    assert elapsed == pytest.approx(delay, abs=0.5)
    sub.alert_torpedo()          # already evading: immediate
    assert sub.torpedo_alarm_left == -1.0


def test_esm_only_works_with_the_mast_up():
    suite = PlatformSensorSuite(CATALOG, "aip_modern", 7, side="hostile",
                                doctrine="submarine")
    profile = next(CATALOG.sensors[key] for key in suite.controllers
                   if CATALOG.sensors[key].domain == "esm")
    emitter = SimpleNamespace(id=9, x=110.0, y=100.0, depth=0.0, course=0.0,
                              speed=10.0, active=True, sunk=False,
                              radar_emitting=True, sensor_domain="surface",
                              noise_level=lambda: 0.5)
    for depth, expected in ((60.0, False), (MAST_DEPTH_M - 2.0, True)):
        suite = PlatformSensorSuite(CATALOG, "aip_modern", 7, side="hostile",
                                    doctrine="submarine")
        owner = SimpleNamespace(id=1, x=100.0, y=100.0, depth=depth, course=0.0,
                                speed=4.0, sensor_domain="subsurface",
                                noise_level=lambda: 0.1)
        suite._observe_candidate(1.0, owner, emitter, Ocean(), profile, 0, 1.0)
        assert bool(suite.local_picture.tracks(1.0)) is expected


def test_datalink_skips_a_boat_without_antenna():
    sender = PlatformSensorSuite(CATALOG, "warship_01", 1, side="hostile",
                                 doctrine="surface_combatant", datalink_group="red")
    boat = PlatformSensorSuite(CATALOG, "aip_modern", 2, side="hostile",
                               doctrine="submarine", datalink_group="red")
    sender.local_picture.observe(PlatformObservation(
        track_id="Lx", domain="radar", source="RADAR", observer_x=0.0,
        observer_y=0.0, bearing=90.0, range_nm=5.0, x=5.0, y=0.0, course=None,
        speed_kn=None, depth_m=None, quality=0.8, signal=0.8, last_seen=1.0,
        bearing_uncertainty_deg=1.0, range_uncertainty_nm=0.1,
        depth_uncertainty_m=None, label=None))
    boat.datalink_reachable = False
    exchange_friendly_datalink([sender, boat], 1.0)
    assert not boat.datalink_picture.tracks(1.0)
    boat.datalink_reachable = True
    exchange_friendly_datalink([sender, boat], 1.0)
    assert boat.datalink_picture.tracks(1.0)
