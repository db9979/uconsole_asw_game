"""OPZ correlation compares course, speed and class, and takes AIS reports."""

import dataclasses
import math

from src.core import config
from src.core.game import Game
from src.enemies.surface import SurfaceShip
from src.sensors.ais import AISReceiver
from src.sensors.fusion import (ManualFusion, OPZFusionPicture, OPZObservation,
                                suggest_correlations)


def report(key, source, bearing, rng, *, course=None, speed=None, cls=None,
           kind="SURFACE", seen=100.0):
    rad = math.radians(bearing)
    x, y = rng * math.sin(rad), -rng * math.cos(rad)
    return OPZObservation(key, source, kind, bearing, rng, x, y, course, .8, seen, key,
                          classification=cls, bearing_uncertainty_deg=1.0,
                          speed_kn=speed)


def suggest(reports):
    return suggest_correlations(reports, 0.0, 0.0, 100.0)


def test_agreeing_motion_is_suggested_with_its_deltas():
    (only,) = suggest([report("A", "RADAR-S", 90, 10, course=45, speed=12),
                       report("B", "ESM", 90.5, 10.2, course=55, speed=14)])
    assert only.course_delta_deg == 10.0 and only.speed_delta_kn == 2.0
    assert only.class_match is None


def test_crossing_courses_or_speeds_rule_a_pairing_out():
    assert not suggest([report("A", "RADAR-S", 90, 10, course=45, speed=12),
                        report("B", "ESM", 90.5, 10.2, course=180, speed=12)])
    assert not suggest([report("A", "RADAR-S", 90, 10, course=45, speed=4),
                        report("B", "ESM", 90.5, 10.2, course=45, speed=25)])
    # A (nearly) stopped contact has no meaningful course to compare.
    assert suggest([report("A", "RADAR-S", 90, 10, course=45, speed=1),
                    report("B", "ESM", 90.5, 10.2, course=225, speed=1.5)])


def test_classes_must_agree_and_agreement_ranks_first():
    assert not suggest([report("A", "RADAR-S", 90, 10, cls="KAMPFSCHIFF"),
                        report("B", "ESM", 90.5, 10.2, cls="FAHRZEUG")])
    same = suggest([report("A", "RADAR-S", 90, 10, cls="FAHRZEUG"),
                    report("B", "ESM", 90.8, 10.2, cls="FAHRZEUG")])
    unknown = suggest([report("A", "RADAR-S", 90, 10),
                       report("B", "ESM", 90.8, 10.2)])
    assert same[0].class_match is True and same[0].score < unknown[0].score


def test_ais_pairs_with_radar_but_never_with_a_classified_submarine():
    ais = report("Z", "AIS", 90.1, 10.0, course=45, speed=12)
    (pair,) = suggest([report("A", "RADAR-S", 90, 10, course=None, speed=12), ais])
    assert set(pair.members) == {"A", "Z"}
    assert not suggest([report("S", "SONAR", 90, 10, cls="U_BOOT", kind="UNKNOWN"), ais])
    stale = dataclasses.replace(ais, last_seen=100.0 - config.OPZ_SUGGEST_AIS_MAX_AGE_S - 1)
    assert not suggest([report("A", "RADAR-S", 90, 10), stale])


def test_a_fusion_carries_the_members_motion():
    picture = OPZFusionPicture()
    members = (report("A", "RADAR-S", 90, 10, course=40, speed=10),
               report("B", "LOOKOUT", 90, 10, course=50, speed=14))
    fused = picture.computed(ManualFusion("F-1", ("A", "B")), members, 100.0, 300.0)
    assert abs(fused.course - 45.0) < 1e-6 and abs(fused.speed_kn - 12.0) < 1e-6


def test_an_ais_member_lends_the_fusion_its_motion():
    """A ship's own AIS course and speed over ground stand alone: a young
    lookout estimate (here 186 kn) never swings the fused motion around
    (bug report 2026-10-06: labels jumping on the chart)."""
    picture = OPZFusionPicture()
    members = (report("A", "LOOKOUT", 90, 10, course=245, speed=186),
               report("B", "AIS", 90, 10, course=90, speed=8))
    fused = picture.computed(ManualFusion("F-1", ("A", "B")), members, 100.0, 300.0)
    assert abs(fused.course - 90.0) < 1e-6 and abs(fused.speed_kn - 8.0) < 1e-6


def test_the_game_publishes_ais_reports_to_the_opz():
    game = Game(seed=4401, start_menu=False, audio_enabled=False)
    ship = SurfaceShip(game.ship.x + 4.0, game.ship.y, game.rng_world)
    ship.course, ship.speed = 90.0, 12.0
    ship.doctrine = "surface_transit"
    game.civilians = [ship]
    game.warships = []
    game.ais = AISReceiver(game.seed)
    game.world.land_blocks_line = lambda *args: False
    game.ais.update(game.sim_t, [ship], game.ship, game.world)
    reports = [item for item in game.opz_source_observations() if item.source == "AIS"]
    assert len(reports) == 1
    item = reports[0]
    assert item.course == 90.0 and item.speed_kn == 12.0
    assert str(ship.id) not in item.observation_id
    assert abs(item.x - ship.x) < 0.01 and abs(item.y - ship.y) < 0.01
    # The saved receiver keeps the reported position.
    rows = game.ais.serialize()
    assert rows[0]["x"] == round(ship.x, 4)
    assert AISReceiver.valid_state(rows, game.sim_t, {ship.id})
    bad = [dict(rows[0], x=float("nan"))]
    assert not AISReceiver.valid_state(bad, game.sim_t, {ship.id})
