import copy
import json
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.core.game import Game
from src.core.mission_definition import default_mission
from src.data.catalog import CATALOG
from src.enemies.surface import SurfaceShip
from src.enemies.sub import Sub
from src.sensors.platform import (
    MAX_LOCAL_TRACKS,
    ObservationPicture,
    PlatformObservation,
    PlatformSensorSuite,
    SensorController,
    exchange_friendly_datalink,
    validate_suite_state,
)


class OpenWorld:
    size_nm = 500.0

    @staticmethod
    def depth_m(*args):
        return 1000.0

    @staticmethod
    def thermocline_depth_m(*args):
        return 80.0

    @staticmethod
    def on_land(*args):
        return False

    @staticmethod
    def land_blocks_line(*args):
        return False

    @staticmethod
    def sonar_path_blocked(*args):
        return False


def target(**values):
    defaults = dict(
        id=77, x=5.0, y=0.0, depth=5.0, course=180.0, speed=12.0,
        active=True, sunk=False, radar_emitting=True, ais_transmitting=True,
        name="SELF REPORT", noise_level=lambda: 0.8,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def observation(track_id, seen):
    return PlatformObservation(
        track_id=track_id, domain="radar", source="RADAR",
        observer_x=0.0, observer_y=0.0, bearing=90.0,
        range_nm=5.0, x=5.0, y=0.0, course=180.0, speed_kn=12.0,
        depth_m=None, quality=0.5, signal=0.5, last_seen=seen,
        bearing_uncertainty_deg=1.0, range_uncertainty_nm=0.1,
        depth_uncertainty_m=None, label=None)


@pytest.mark.parametrize("profile_key", [
    "warship_01", "warship_02", "warship_25", "warship_26", "warship_27",
    "warship_28", "cargo_05", "sub_03", "sub_14",
])
def test_all_pilots_use_attached_machine_and_sensor_components(profile_key):
    systems = CATALOG.profile_systems[profile_key]
    machine = CATALOG.machines[systems.machine_key]
    if profile_key.startswith("sub_"):
        actor = Sub(0, 0, 50, 0, profile_key, random.Random(20),
                    profile=CATALOG.subs[profile_key], runtime_catalog=CATALOG)
    else:
        actor = SurfaceShip(
            0, 0, random.Random(20), profile=CATALOG.surfaces[profile_key],
            side="neutral" if profile_key == "cargo_05" else "hostile",
            runtime_catalog=CATALOG)
    assert actor.motion.maximum_speed_kn == machine.maximum_speed_kn
    assert actor.motion.cruise_speed_kn == machine.cruise_speed_kn
    assert set(actor.sensor_suite.controllers) == set(systems.sensor_keys)
    assert all(controller.enabled
               for controller in actor.sensor_suite.controllers.values())


def test_same_profile_has_independent_mission_side_and_identical_capabilities():
    profile = CATALOG.surfaces["warship_01"]
    friendly = SurfaceShip(
        0, 0, random.Random(1), profile=profile, side="friendly",
        doctrine="surface_combatant", runtime_catalog=CATALOG)
    hostile = SurfaceShip(
        0, 0, random.Random(1), profile=profile, side="hostile",
        doctrine="surface_combatant", runtime_catalog=CATALOG)

    assert friendly.signature_key == hostile.signature_key == "warship_01"
    assert not friendly.hostile and hostile.hostile
    assert friendly.motion == hostile.motion
    assert set(friendly.sensor_suite.controllers) == set(
        hostile.sensor_suite.controllers)


def test_radar_esm_sonar_and_ais_controllers_are_independent():
    world = OpenWorld()
    owner = target(id=1, x=0.0, radar_emitting=True, ais_transmitting=True)
    detected = target()
    suites = [
        PlatformSensorSuite(CATALOG, "warship_01", 1, side="hostile",
                            doctrine="surface_combatant"),
        PlatformSensorSuite(CATALOG, "sub_03", 2, side="hostile",
                            doctrine="submarine"),
        PlatformSensorSuite(CATALOG, "cargo_05", 3, side="neutral",
                            doctrine="surface_transit"),
    ]
    for suite in suites:
        for controller in suite.controllers.values():
            controller.next_scan_s = 0.0
        suite.update(1.0, owner, [detected], world, CATALOG,
                     emcon={"radar": False, "ais": True})

    domains = [{track.domain for track in suite.tactical_tracks(1.0)}
               for suite in suites]
    assert domains[0] == {"sonar"}
    assert domains[1] == {"sonar", "esm"}
    assert domains[2] == {"ais"}


def test_sensor_domains_reject_impossible_targets():
    world = OpenWorld()
    owner = target(id=1, x=0.0)
    suite = PlatformSensorSuite(
        CATALOG, "warship_01", 5, side="friendly",
        doctrine="surface_combatant")
    for controller in suite.controllers.values():
        controller.next_scan_s = 0.0
    suite.update(1.0, owner, [target(sensor_domain="subsurface", depth=100.0)],
                 world, CATALOG)
    assert not suite.local_picture.tracks(1.0, ("radar",))

    suite = PlatformSensorSuite(
        CATALOG, "sub_03", 6, side="friendly", doctrine="submarine")
    for controller in suite.controllers.values():
        controller.next_scan_s = 0.0
    suite.update(1.0, owner, [target(sensor_domain="air")], world, CATALOG)
    assert not suite.local_picture.tracks(1.0, ("sonar",))


def test_submarine_esm_requires_surface_deployment():
    sub = Sub(0, 0, 100, 0, "sub_03", random.Random(6),
              profile=CATALOG.subs["sub_03"], runtime_catalog=CATALOG)
    for controller in sub.sensor_suite.controllers.values():
        controller.next_scan_s = 0.0
    sub.sensor_suite.update(
        1.0, sub, [target()], OpenWorld(), CATALOG)
    assert not sub.sensor_suite.local_picture.tracks(1.0, ("esm",))

    sub.depth = 5.0
    for controller in sub.sensor_suite.controllers.values():
        controller.next_scan_s = 2.0
    sub.sensor_suite.update(
        2.0, sub, [target()], OpenWorld(), CATALOG)
    assert sub.sensor_suite.local_picture.tracks(2.0, ("esm",))


def test_radar_does_not_publish_unmeasured_target_kinematics_or_depth():
    suite = PlatformSensorSuite(
        CATALOG, "warship_01", 7, side="friendly",
        doctrine="surface_combatant")
    for controller in suite.controllers.values():
        controller.next_scan_s = 0.0
    suite.update(1.0, target(id=1, x=0.0), [target()], OpenWorld(), CATALOG)

    radar = suite.local_picture.tracks(1.0, ("radar",))[0]
    sonar = suite.local_picture.tracks(1.0, ("sonar",))[0]
    assert radar.course is None and radar.speed_kn is None
    assert sonar.range_nm is None and sonar.depth_m is None
    assert sonar.fix_source is None


def test_local_picture_is_hard_bounded_with_deterministic_eviction():
    picture = ObservationPicture(30.0, MAX_LOCAL_TRACKS)
    for index in range(MAX_LOCAL_TRACKS + 5):
        picture.observe(observation(f"T{index:03d}", float(index)))

    tracks = picture.tracks(100.0)
    assert len(picture.serialize()) == MAX_LOCAL_TRACKS
    assert {track.track_id for track in tracks} == set()
    assert picture.serialize()[0]["track_id"] == "T005"


def test_friendly_datalink_copies_observations_without_entity_truth():
    first = PlatformSensorSuite(
        CATALOG, "warship_01", 10, side="friendly",
        doctrine="surface_combatant", datalink_group="blue")
    second = PlatformSensorSuite(
        CATALOG, "warship_02", 11, side="friendly",
        doctrine="surface_combatant", datalink_group="blue")
    report = observation("LOCAL", 1.0)
    first.local_picture.observe(report)

    exchange_friendly_datalink([second, first], 1.0)

    received = second.datalink_picture.serialize()
    assert len(received) == 1 and received[0]["source"] == "DATALINK"
    encoded = json.dumps(received)
    assert "target_id" not in encoded and "profile" not in encoded
    first.local_picture._tracks["LOCAL"] = observation("LOCAL", 2.0)
    assert second.datalink_picture.serialize()[0]["last_seen"] == 1.0

    first.local_picture.observe(observation("NOT-DESIGNATED", 1.0))
    second.datalink_picture._tracks.clear()
    exchange_friendly_datalink(
        [first, second], 1.0,
        allowed_track_ids={first.datalink_id: {"LOCAL"}, second.datalink_id: set()})
    assert len(second.datalink_picture.serialize()) == 1


def test_platform_sensor_phase_and_picture_roundtrip_transactionally():
    game = Game(seed=2710, start_menu=False)
    ship = SurfaceShip(
        game.ship.x + 5.0, game.ship.y, random.Random(9),
        profile=game.runtime_catalog.surfaces["warship_01"], side="hostile",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    game.warships = [ship]
    for controller in ship.sensor_suite.controllers.values():
        controller.next_scan_s = 0.0
    game._update_platform_sensors(0.1)
    state = game.save_state()
    expected = copy.deepcopy(state["warships"][0]["platform"])

    restored = Game(seed=1, start_menu=False)
    restored.load_state(copy.deepcopy(state))
    assert restored.warships[0].sensor_suite.serialize() == expected

    malformed = copy.deepcopy(state)
    key = next(iter(malformed["warships"][0]["platform"]["controllers"]))
    malformed["warships"][0]["platform"]["controllers"][key][
        "next_scan_s"] = state["sim_t"] + 100.0
    live_ship = restored.ship
    assert not restored._load_save_data(malformed)
    assert restored.ship is live_ship


def test_same_profile_roundtrips_on_opposing_sides():
    game = Game(seed=2713, start_menu=False)
    profile = game.runtime_catalog.surfaces["warship_01"]
    game.civilians = [SurfaceShip(
        game.ship.x + 2, game.ship.y, random.Random(12), profile=profile,
        side="friendly", doctrine="surface_combatant",
        runtime_catalog=game.runtime_catalog)]
    game.warships = [SurfaceShip(
        game.ship.x + 3, game.ship.y, random.Random(13), profile=profile,
        side="hostile", doctrine="surface_combatant",
        runtime_catalog=game.runtime_catalog)]

    state = game.save_state()
    restored = Game(seed=1, start_menu=False)
    restored.load_state(copy.deepcopy(state))

    assert restored.civilians[0].signature_key == restored.warships[0].signature_key
    assert restored.civilians[0].side == "friendly"
    assert restored.warships[0].side == "hostile"


def test_surface_weapon_release_requires_positioned_observation():
    warship = SurfaceShip(
        0, 0, random.Random(3), profile=CATALOG.surfaces["warship_01"],
        side="hostile", doctrine="surface_combatant", runtime_catalog=CATALOG)
    warship.attack_left = 0.0
    warship.update(1.0, None, OpenWorld())
    assert not warship.pending_asm

    warship.attack_left = 0.0
    warship.rng.randint = lambda low, high: low
    warship.update(1.0, observation("FIX", 0.0), OpenWorld())
    assert warship.pending_asm

    friendly = SurfaceShip(
        0, 0, random.Random(3), profile=CATALOG.surfaces["warship_01"],
        side="friendly", doctrine="surface_combatant", runtime_catalog=CATALOG)
    friendly.attack_left = 0.0
    friendly.update(1.0, observation("FIX", 0.0), OpenWorld())
    assert not friendly.pending_asm


def test_stale_measurement_does_not_refresh_surface_contact_age():
    warship = SurfaceShip(
        0, 0, random.Random(3), profile=CATALOG.surfaces["warship_01"],
        side="hostile", doctrine="surface_combatant", runtime_catalog=CATALOG)
    report = observation("FIX", 1.0)
    warship.update(0.1, report, OpenWorld())
    assert warship.sensor_contact_age == 0.0
    warship.update(0.5, report, OpenWorld())
    assert warship.sensor_contact_age == 0.5


def test_component_damage_can_degrade_or_disable_only_due_sensors():
    owner = target(id=1, x=0.0)
    detected = target(x=30.0)
    suite = PlatformSensorSuite(
        CATALOG, "warship_01", 14, side="friendly",
        doctrine="surface_combatant")
    for controller in suite.controllers.values():
        controller.next_scan_s = 0.0
    suite.update(1.0, owner, [detected], OpenWorld(), CATALOG,
                 emcon={"radar": False}, degraded={"sonar"})
    assert not suite.tactical_tracks(1.0)

    for controller in suite.controllers.values():
        controller.next_scan_s = 2.0
    suite.update(2.0, owner, [target(x=5.0)], OpenWorld(), CATALOG,
                 unavailable={"radar", "sonar"})
    assert not suite.tactical_tracks(2.0)


def test_sensor_phases_are_stable_across_update_chunking():
    owner = target(id=1, x=0.0)
    detected = target(x=5.0)
    fine = PlatformSensorSuite(
        CATALOG, "warship_01", 44, side="friendly",
        doctrine="surface_combatant")
    coarse = PlatformSensorSuite(
        CATALOG, "warship_01", 44, side="friendly",
        doctrine="surface_combatant")
    for index in range(1, 21):
        fine.update(index / 10, owner, [detected], OpenWorld(), CATALOG)
    coarse.update(2.0, owner, [detected], OpenWorld(), CATALOG)

    assert fine.serialize() == coarse.serialize()


def test_sensor_due_tolerance_never_publishes_a_future_timestamp():
    controller = SensorController("sensor", "radar", 1.0, True, 1.0 + 5e-10)

    assert controller.consume_due(1.0) == (0, 1.0)


def test_sensor_state_rejects_scan_sequence_overflow():
    suite = PlatformSensorSuite(
        CATALOG, "warship_01", 45, side="friendly",
        doctrine="surface_combatant")
    state = suite.serialize()
    key = next(iter(state["controllers"]))
    state["controllers"][key]["next_scan_s"] = 1.0
    state["controllers"][key]["scan_index"] = 2**63 - 1

    assert not validate_suite_state(state, CATALOG, "warship_01", 1.0)


def test_pilot_submarine_broadband_uses_machine_component():
    game = Game(seed=2711, start_menu=False)
    sub = Sub(
        0, 0, 50, 0, "sub_03", random.Random(4),
        profile=game.runtime_catalog.subs["sub_03"],
        runtime_catalog=game.runtime_catalog)
    broadband = sub.broadband()
    machine = game.runtime_catalog.machines["machine.sub_03"]
    assert (broadband["low_hz"], broadband["high_hz"]) == (
        machine.cruise_broadband[1], machine.cruise_broadband[2])


def test_friendly_submarine_loss_is_incident_not_score():
    game = Game(seed=2712, start_menu=False)
    sub = Sub(
        game.ship.x + 1, game.ship.y, 50, 0, "sub_03", random.Random(5),
        profile=game.runtime_catalog.subs["sub_03"], side="friendly",
        runtime_catalog=game.runtime_catalog)
    sub.state = "SINKING"
    sub.sink_left = 0.01
    game.subs = [sub]
    score = game.score

    game._update_underwater_entities(0.1)

    assert sub.sunk and game.incident and game.score == score


def test_pilot_submarine_can_counterfire_on_fresh_ping_bearing():
    sub = Sub(0, 0, 50, 90, "sub_03", random.Random(7),
              profile=CATALOG.subs["sub_03"], runtime_catalog=CATALOG)
    ship = target(id=0, x=10.0, noise_level=lambda: 0.2)
    for controller in sub.sensor_suite.controllers.values():
        controller.next_scan_s = 0.0
    sub.sensor_suite.update(1.0, sub, [ship], OpenWorld(), CATALOG)
    report = sub.sensor_suite.local_picture.tracks(1.0, ("sonar",))[0]
    assert report.range_nm is None
    sub.hear_ping()
    sub.attack_left = 0.0
    sub.rng.random = lambda: 0.0

    sub.update(0.1, report, OpenWorld())

    assert sub.pending_torpedoes


def test_asw_ai_selects_only_observations_published_to_each_picture(monkeypatch):
    game = Game(seed=2713, start_menu=False)
    sub = Sub(
        110, 100, 50, 0, "sub_03", random.Random(6),
        profile=game.runtime_catalog.subs["sub_03"], side="hostile",
        runtime_catalog=game.runtime_catalog)
    ship = SurfaceShip(
        100, 100, random.Random(7), side="friendly",
        doctrine="surface_combatant",
        profile=game.runtime_catalog.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    ownship_track = replace(
        observation("ownship", 0), domain="sonar", source="SONAR")
    hostile_sub_track = replace(
        observation("hostile-sub", 0), domain="sonar", source="SONAR",
        fix_source="TMA")

    def publish(suite, *args, **kwargs):
        suite.local_picture.observe(
            ownship_track if suite is sub.sensor_suite else hostile_sub_track)

    monkeypatch.setattr(PlatformSensorSuite, "update", publish)
    game.subs, game.warships = [sub], [ship]
    game.civilians, game.animals, game.decoys = [], [], []
    game.flights.flights = []
    game._update_platform_sensors(.1)

    assert sub._tactical_observation is ownship_track
    assert ship._asw_observation is hostile_sub_track


def test_custom_mission_and_v10_save_enforce_profile_maximum_speed():
    game = Game(seed=2714, start_menu=False)
    definition = default_mission("user.r5_speed")
    definition["units"]["exact"] = [{
        "id": "target", "profile": "sub_03", "side": "hostile",
        "placement": {"kind": "fixed", "x": 100.0, "y": 100.0},
        "course_deg": 0.0, "speed_kn": 36.0, "depth_m": 50.0,
    }]
    definition["objective"]["target_ids"] = ["target"]
    assert not game.start_custom_mission(definition)

    sub = Sub(0, 0, 50, 0, "sub_03", random.Random(8),
              profile=game.runtime_catalog.subs["sub_03"],
              runtime_catalog=game.runtime_catalog)
    game.subs = [sub]
    malformed = game.save_state()
    malformed["subs"][0]["speed"] = 36.0
    assert not game._load_save_data(malformed)
