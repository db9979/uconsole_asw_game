"""Runtime behavior values are sourced from the packaged contact catalog."""

import json
import random
from importlib import resources
from types import SimpleNamespace

from src.air.helicopter import Helicopter
from src.air.flights import Flight
from src.core import config
from src.data.catalog import CATALOG
from src.enemies.animal import Animal
from src.enemies.decoy import Decoy
from src.enemies.surface import SurfaceShip
from src.enemies.sub import Sub
from src.sensors.platform import machine_acoustics
from src.weapons.torpedo import Torpedo


def _packaged_entry(filename: str, key: str) -> dict:
    path = resources.files("data.contacts") / filename
    with path.open("r", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]
    return next(entry for entry in entries if entry["key"] == key)


def test_torpedo_runtime_values_match_packaged_json():
    frigate_profile = _packaged_entry("torpedoes.json", "frigate_torp")
    torpedo = Torpedo(0.0, 0.0, 0.0, 50.0, None, 1)
    assert torpedo.speed_kn == frigate_profile["speed_kn"]
    assert torpedo.range_nm == frigate_profile["range_nm"]
    assert torpedo.kill_dist_nm == frigate_profile["hit_dist_nm"]


def test_helicopter_torpedo_runtime_values_match_packaged_json():
    profile = _packaged_entry("torpedoes.json", "helo_torp")
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    target = SimpleNamespace(x=1.0, y=0.0)
    torpedo = helicopter.drop_torpedo(
        target, 50.0, 1, kill_depth_m=15.0)
    assert torpedo.speed_kn == profile["speed_kn"]
    assert torpedo.range_nm == profile["range_nm"]
    assert torpedo.kill_dist_nm == profile["hit_dist_nm"]
    assert config.HELO_TORP_SPEED_KN == profile["speed_kn"]


def test_helicopter_torpedo_applies_supplied_difficulty_hit_envelope():
    helicopter = Helicopter(random.Random(1))
    helicopter.state = "AUF"
    target = SimpleNamespace(x=1.0, y=0.0)
    torpedo = helicopter.drop_torpedo(
        target, 50.0, 1, kill_dist_nm=0.2, kill_depth_m=20.0)
    assert torpedo.kill_dist_nm == 0.2


def test_submarine_decoy_behavior_matches_packaged_json():
    profile = _packaged_entry("decoys.json", "decoy")
    submarine = Sub(10.0, 10.0, 50.0, 0.0, "sub_03",
                    random.Random(2))
    submarine.state = "SINKING"
    submarine.sink_left = 10.0
    submarine.torpedo_alerted = True
    submarine.rng.random = lambda: 0.0
    world = SimpleNamespace(
        depth_m=lambda _x, _y: 1000.0,
        thermocline_depth_m=lambda _x, _y: 100.0,
        on_land=lambda _x, _y: False,
        size_nm=500.0,
    )
    submarine.update(0.1, SimpleNamespace(), world)
    assert submarine.pending_decoys == [(10.0, 10.0)]
    assert submarine.countermeasure_store.remaining_total == 11
    assert submarine._decoy_cd == profile["cooldown_s"]
    assert config.SUB_DECOY_CHANCE == profile["chance"]
    assert config.SUB_DECOY_COOLDOWN_S == profile["cooldown_s"]


def test_r10_submarine_components_preserve_draw_order_and_add_finite_decoys():
    migrated = [key for key in CATALOG.subs if key not in ("sub_03", "sub_14")]
    for index, key in enumerate(migrated):
        profile = CATALOG.subs[key]
        rng = random.Random(3100 + index)
        submarine = Sub(10, 10, 50, 0, key, rng, runtime_catalog=CATALOG)

        expected_rng = random.Random(3100 + index)
        expected_rng.randint(0, 2**31 - 1)
        expected_rng.uniform(profile.speed_kn[0], min(profile.speed_kn[1], 8.0))
        expected_rng.uniform(300.0, 900.0)
        expected_rng.uniform(-30.0, 30.0)

        assert rng.getstate() == expected_rng.getstate()
        assert submarine.motion.cruise_speed_kn == min(profile.speed_kn[1], 8.0)
        assert submarine.motion.maximum_speed_kn == profile.speed_kn[1]
        assert submarine.legacy_observation_model
        assert machine_acoustics(CATALOG, key, submarine.speed) is None
        assert set(submarine.sensor_suite.controllers) == {
            f"sensor.{key}.sonar", f"sensor.{key}.esm"}
        assert submarine.weapon_battery.remaining_total == profile.torpedoes
        assert submarine.weapon_battery.ready_count == profile.torpedoes
        assert submarine.weapon_battery.reload_s == 0
        assert submarine.countermeasure_store.remaining_total == 12


def test_r10_submarine_decoy_activation_is_deterministic():
    world = SimpleNamespace(
        depth_m=lambda _x, _y: 1000.0,
        thermocline_depth_m=lambda _x, _y: 100.0,
        on_land=lambda _x, _y: False,
        size_nm=500.0,
    )
    first = Sub(10, 10, 50, 0, "diesel_alt", random.Random(91),
                runtime_catalog=CATALOG, asw_rng=random.Random(92))
    second = Sub(10, 10, 50, 0, "diesel_alt", random.Random(91),
                 runtime_catalog=CATALOG, asw_rng=random.Random(92))
    for submarine in (first, second):
        submarine.alert_torpedo()
        submarine.update(0.1, SimpleNamespace(), world)

    assert first.pending_decoys == second.pending_decoys
    assert first.countermeasure_store.serialize() == second.countermeasure_store.serialize()
    assert first.asw_rng.getstate() == second.asw_rng.getstate()


def test_r10_warship_components_preserve_legacy_runtime_and_draw_order():
    for index, key in enumerate(f"warship_{number:02d}" for number in range(3, 25)):
        profile = CATALOG.surfaces[key]
        rng = random.Random(4100 + index)
        ship = SurfaceShip(
            10, 10, rng, profile=profile, side="hostile",
            doctrine="surface_combatant", runtime_catalog=CATALOG)

        expected_rng = random.Random(4100 + index)
        expected_rng.randint(0, 2**31 - 1)
        expected_rng.uniform(0.0, 360.0)
        expected_rng.uniform(*profile.speed_kn)
        expected_rng.random()
        expected_rng.uniform(600.0, 1800.0)
        expected_rng.choice((-1, 1))

        assert rng.getstate() == expected_rng.getstate()
        assert ship.motion.cruise_speed_kn == profile.speed_kn[1]
        assert ship.motion.maximum_speed_kn == profile.speed_kn[1]
        assert ship.legacy_observation_model
        assert machine_acoustics(CATALOG, key, ship.speed) is None
        assert set(ship.sensor_suite.controllers) == {
            f"sensor.{key}.radar", f"sensor.{key}.sonar"}
        assert ship.asroc_battery is None


def test_r10_civilian_components_preserve_legacy_runtime_and_draw_order():
    for index, profile in enumerate(CATALOG.civilian_surfaces):
        rng = random.Random(5100 + index)
        ship = SurfaceShip(
            10, 10, rng, profile=profile, side="neutral",
            doctrine="surface_transit", runtime_catalog=CATALOG)

        expected_rng = random.Random(5100 + index)
        expected_rng.choice(profile.callsigns)
        expected_rng.randint(0, 2**31 - 1)
        expected_rng.uniform(0.0, 360.0)
        expected_rng.uniform(*profile.speed_kn)
        expected_rng.random()
        expected_rng.uniform(600.0, 1800.0)
        expected_rng.choice((-1, 1))

        assert rng.getstate() == expected_rng.getstate()
        assert set(ship.sensor_suite.controllers) == {
            f"sensor.{profile.key}.radar", f"sensor.{profile.key}.ais"}
        assert ship.asroc_battery is None
        if profile.key != "cargo_05":
            assert ship.motion.cruise_speed_kn == profile.speed_kn[1]
            assert ship.motion.maximum_speed_kn == profile.speed_kn[1]
            assert ship.legacy_observation_model
            assert machine_acoustics(CATALOG, profile.key, ship.speed) is None


def test_r10_aircraft_components_preserve_legacy_runtime_and_draw_order():
    base = {"id": "base", "x": 10.0, "y": 10.0, "nation": "BOREN"}
    destination = {"id": "dest", "x": 20.0, "y": 20.0, "nation": "HANSE"}
    cases = (("military", "mil_patrol", None),
             ("civil", "civil_transit", destination))
    for index, (kind, key, dest) in enumerate(cases):
        rng = random.Random(6100 + index)
        flight = Flight(kind, base, dest=dest, rng=rng, seq=index + 1,
                        catalog=CATALOG)

        expected_rng = random.Random(6100 + index)
        expected_rng.uniform(*CATALOG.aircraft[key].loiter_nm)
        if dest is None:
            expected_rng.uniform(0.0, 360.0)
            expected_rng.uniform(0.0, flight.loiter_nm)
            expected_rng.uniform(0.0, 360.0)
            expected_rng.uniform(0.0, 360.0)

        assert rng.getstate() == expected_rng.getstate()
        assert flight.speed == CATALOG.aircraft[key].speed_kn
        assert flight.legacy_observation_model
        assert set(flight.sensor_suite.controllers) == set(
            CATALOG.profile_systems[key].sensor_keys)
        assert CATALOG.profile_systems[key].launcher_keys == ()


def test_r10_batch5_components_preserve_animal_and_decoy_runtime_draw_order():
    animal_rng = random.Random(7100)
    animal = Animal(10, 10, "whale", animal_rng, profile=CATALOG.animals["whale"])
    expected = random.Random(7100)
    expected.randint(0, 2**31 - 1)
    expected.uniform(80.0, 200.0)
    expected.uniform(0, 360)
    expected_speed = CATALOG.animals["whale"].speed_kn * expected.uniform(0.7, 1.1)
    expected.uniform(300.0, 900.0)
    assert animal_rng.getstate() == expected.getstate()
    assert animal.speed == expected_speed
    assert machine_acoustics(CATALOG, "whale", animal.speed) is None

    decoy_rng = random.Random(7101)
    decoy = Decoy(10, 10, 50, decoy_rng, profile=CATALOG.decoys["decoy"],
                  acoustic=CATALOG.acoustic_for("decoy"))
    expected = random.Random(7101)
    expected.randint(0, 2**31 - 1)
    expected.uniform(0.0, 360.0)
    assert decoy_rng.getstate() == expected.getstate()
    assert decoy.life == CATALOG.decoys["decoy"].life_s
    assert machine_acoustics(CATALOG, "decoy", CATALOG.decoys["decoy"].speed_kn) is None


def test_r10_batch5_torpedo_components_are_behavior_neutral():
    for key, profile in CATALOG.torpedoes.items():
        machine = CATALOG.machines[f"machine.{key}"]
        assert machine.cruise_speed_kn == machine.maximum_speed_kn == profile.speed_kn
        assert machine_acoustics(CATALOG, key, profile.speed_kn) is None
    assert CATALOG.machines["machine.enemy_torp"].cruise_broadband == \
        CATALOG.torpedoes["enemy_torp"].acoustic.broadband
