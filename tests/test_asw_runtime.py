"""R8 contracts for finite ASW launchers, stores, and transit phases."""

import copy
import random
from types import SimpleNamespace

import pygame
import pytest

from src.air.sonobuoy import Sonobuoy
from src.core import config
from src.data.catalog import CATALOG
from src.core.game import Game
from src.core.station import Station
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.sensors.platform import PlatformObservation
from src.sonar.sonar import Contact
from src.weapons.torpedo import EnemyTorpedo, Torpedo
from src.weapons.asw import (
    ASROC,
    ConsumableStore,
    MagazineState,
    TowedAcousticDecoy,
    WeaponBattery,
    ownship_loadout,
    valid_battery_state,
    valid_consumable_state,
)


def ocean(**overrides):
    values = dict(size_nm=500.0, on_land=lambda x, y: False,
                  depth_m=lambda x, y: 1000.0)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ownship_loadout_is_typed_and_matches_legacy_level_inventory():
    definition = ownship_loadout()
    assert definition["launcher"]["weapon_keys"] == [
        definition["magazine"]["weapon_key"]]
    assert definition["weapons"][0]["runtime_profile_key"] == "frigate_torp"
    assert definition["weapons"][0]["kill_dist_nm_by_level"] == {
        "leicht": .2, "normal": .135, "harte": .135}
    assert definition["magazine"]["mission_count_by_level"] == {
        "leicht": 6, "normal": 6, "harte": 4}


def test_tubes_reserve_magazine_rounds_and_reload_deterministically():
    battery = WeaponBattery.ownship("normal")
    assert (battery.capacity_total, battery.remaining_total,
            battery.ready_count) == (6, 6, 2)
    assert battery.fire() == "weapon.ownship.torpedo"
    assert (battery.remaining_total, battery.ready_count,
            battery.loading_count) == (5, 1, 1)
    battery.update(59.9)
    assert battery.ready_count == 1
    battery.update(.1)
    assert (battery.ready_count, battery.loading_count) == (2, 0)


def test_empty_magazine_cannot_overcommit_multiple_tubes():
    battery = WeaponBattery(
        "launcher.test", 2, 2, 60, ("weapon.test",),
        [MagazineState("magazine.test", "weapon.test", 1, 1)])
    assert battery.fire() is not None
    assert battery.fire() is None
    assert battery.remaining_total == battery.ready_count == battery.loading_count == 0


def test_catalog_submarine_battery_uses_typed_pilot_profile():
    battery = WeaponBattery.from_catalog(CATALOG, "sub_03", "torpedo")
    assert battery is not None
    assert battery.capacity_total == 24
    assert battery.ready_count == 4
    assert battery.reload_s == 60


def test_battery_roundtrip_and_strict_rejection():
    battery = WeaponBattery.ownship("normal")
    battery.fire()
    battery.update(17.25)
    state = battery.serialize()
    assert WeaponBattery.restore(state).serialize() == state
    for patch in (
            lambda value: value["tubes"][0].update(index=2),
            lambda value: value["tubes"][0].update(
                loaded_weapon_key="weapon.ownship.torpedo"),
            lambda value: value["magazines"][0].update(stowed=True),
            lambda value: value.update(mount_count=1000)):
        malformed = copy.deepcopy(state)
        patch(malformed)
        assert not valid_battery_state(malformed)


def test_battery_validation_preserves_per_weapon_capacity():
    battery = WeaponBattery(
        "launcher.test", 1, 0, 10, ("weapon.a", "weapon.b"),
        [SimpleNamespace(key="magazine.a", weapon_key="weapon.a",
                         capacity=0, stowed=0),
         SimpleNamespace(key="magazine.b", weapon_key="weapon.b",
                         capacity=1, stowed=1)])
    state = battery.serialize()
    state["tubes"][0]["loaded_weapon_key"] = "weapon.a"
    state["magazines"][1]["stowed"] = 0
    assert not valid_battery_state(state)


def test_finite_countermeasure_store_roundtrips_mid_reload():
    store = ConsumableStore.ownship()
    assert store.fire()
    assert (store.ready, store.stowed, store.loading) == (0, 0, [60.0])
    store.update(12.5)
    state = store.serialize()
    assert valid_consumable_state(state)
    assert ConsumableStore.restore(state).serialize() == state
    store.update(47.5)
    assert store.ready == 1 and not store.loading
    assert store.fire()
    assert not store.fire()


def test_asroc_flies_to_immutable_datum_and_enters_water_once():
    asroc = ASROC(0, 0, 1, 0, 1, "weapon.test.asroc", "helo_torp",
                  speed_kn=3600, range_nm=2, side="friendly")
    hidden = SimpleNamespace(x=100, y=100)
    assert not asroc.update(.5, ocean())
    hidden.x = -100
    assert asroc.update(.5, ocean())
    assert (asroc.x, asroc.y) == pytest.approx((1, 0))
    assert asroc.state == "WATER_ENTRY"
    assert not asroc.update(1, ocean())


def test_asroc_rejects_land_or_out_of_range_datum():
    blocked = ASROC(0, 0, 1, 0, 1, "weapon.test.asroc", "helo_torp",
                    speed_kn=3600, range_nm=2, side="friendly")
    assert not blocked.update(1, ocean(on_land=lambda x, y: True))
    assert blocked.state == "SASE"
    short = ASROC(0, 0, 2, 0, 2, "weapon.test.asroc", "helo_torp",
                  speed_kn=3600, range_nm=1, side="friendly")
    assert not short.update(1, ocean())
    assert short.state == "SASE"


def test_towed_acoustic_decoy_is_bounded_to_ownship_and_finite():
    ship = SimpleNamespace(x=10.0, y=10.0, course=90.0)
    decoy = TowedAcousticDecoy(1, ship, life_s=10, tether_nm=.2, depth_m=10)
    assert (decoy.x, decoy.y) == pytest.approx((9.8, 10.0))
    ship.x, ship.course = 20, 0
    decoy.update(5, ship, ocean())
    assert (decoy.x, decoy.y) == pytest.approx((20, 10.2))
    decoy.update(5, ship, ocean())
    assert decoy.dead and decoy.state == "SASE"
    assert TowedAcousticDecoy.restore(decoy.serialize(), ship).serialize() \
        == decoy.serialize()


def test_enemy_torpedo_uses_datum_until_terminal_search():
    first = SimpleNamespace(x=1.0, y=0.0, depth=5.0, sunk=False)
    second = SimpleNamespace(x=-100.0, y=100.0, depth=5.0, sunk=False)
    runs = []
    for hidden in (first, second):
        torpedo = EnemyTorpedo(0, 0, 0, 5, 1, guidance_x=0, guidance_y=-8)
        torpedo.update(.1, hidden, ocean())
        runs.append((torpedo.x, torpedo.y, torpedo.course,
                     torpedo.terminal_active, torpedo.seeker_acquired))
    assert runs[0] == runs[1]
    assert runs[0][-2:] == (False, False)


def test_enemy_terminal_seeker_can_be_seduced_by_towed_decoy():
    ship = SimpleNamespace(x=1.0, y=0.0, course=90.0, depth=5.0, sunk=False)
    decoy = TowedAcousticDecoy(1, ship, life_s=60, tether_nm=.8, depth_m=5)
    torpedo = EnemyTorpedo(0, 0, 90, 5, 1, guidance_x=0, guidance_y=0)
    torpedo.update(.1, ship, ocean(), seeker_candidates=[decoy])
    assert torpedo.seeker_acquired
    assert torpedo._seeker_target is decoy


def test_terminal_seekers_reconsider_reactive_acoustic_decoys():
    ship = SimpleNamespace(x=1.0, y=0.0, course=90.0, depth=5.0, sunk=False)
    enemy = EnemyTorpedo(0, 0, 90, 5, 1, guidance_x=0, guidance_y=0)
    enemy.update(0, ship, ocean())
    assert enemy._seeker_target is ship
    decoy = TowedAcousticDecoy(1, ship, life_s=60, tether_nm=.8, depth_m=5)
    enemy.update(0, ship, ocean(), seeker_candidates=[decoy])
    assert enemy._seeker_target is decoy

    player_decoy = TowedAcousticDecoy(
        2, ship, life_s=60, tether_nm=.4, depth_m=5)
    sub = SimpleNamespace(
        id=4, x=1.0, y=0.0, depth=5.0, sunk=False, dead=False, state="PATROLLE")
    player = Torpedo(0, 0, 90, 5, sub, 1, guidance_x=0, guidance_y=0)
    player.update(0, seeker_candidates=[sub], world=ocean())
    assert player.target is sub
    player.update(0, seeker_candidates=[sub, player_decoy], world=ocean())
    assert player.target is player_decoy


def test_pilot_submarine_uses_finite_catalog_stores():
    sub = Sub(10, 10, 50, 0, "sub_03", random.Random(2),
              runtime_catalog=CATALOG)
    assert sub.weapon_battery.capacity_total == sub.torpedoes_left == 24
    assert sub.weapon_battery.ready_count == 4
    assert sub.countermeasure_store.remaining_total == 12
    sub.torpedo_alerted = True
    sub.asw_rng.random = lambda: 0.0
    sub.update(.1, None, ocean(thermocline_depth_m=lambda x, y: 100))
    assert len(sub.pending_decoys) == 1
    assert sub.countermeasure_store.remaining_total == 11


def test_pilot_submarine_salvo_is_deterministic_on_dedicated_asw_stream():
    observation = PlatformObservation(
        track_id="F-1", domain="sonar", source="SONAR",
        observer_x=100, observer_y=100, bearing=0, range_nm=5,
        x=100, y=95, course=0, speed_kn=10, depth_m=5,
        quality=1, signal=1, last_seen=1,
        bearing_uncertainty_deg=1, range_uncertainty_nm=.1,
        depth_uncertainty_m=1, label=None)
    results = []
    for _ in range(2):
        sub = Sub(100, 100, 80, 0, "sub_03", random.Random(6),
                  attack_mult=1000, runtime_catalog=CATALOG,
                  asw_rng=random.Random(7))
        sub.attack_left = 0
        sub.state, sub.heard_ping = "EVADE", True
        sub.update(1, observation, ocean(thermocline_depth_m=lambda x, y: 100))
        results.append((sub.pending_torpedoes,
                        sub.weapon_battery.serialize(), sub.torpedoes_left))
    for left, right in zip(results[0][0], results[1][0]):
        assert left[:7] + left[8:] == right[:7] + right[8:]
    assert results[0][1:] == results[1][1:]
    assert len(results[0][0]) == 2


def test_pilot_submarine_respects_catalog_launcher_arc():
    sub = Sub(100, 100, 80, 0, "sub_03", random.Random(8),
              attack_mult=1000, runtime_catalog=CATALOG,
              asw_rng=random.Random(9))
    sub.attack_left = 0
    sub.state, sub.heard_ping = "EVADE", True
    behind = PlatformObservation(
        track_id="F-2", domain="sonar", source="LOCAL",
        observer_x=100, observer_y=100, bearing=180, range_nm=5,
        x=100, y=105, course=0, speed_kn=10, depth_m=5,
        quality=1, signal=1, last_seen=1,
        bearing_uncertainty_deg=1, range_uncertainty_nm=.1,
        depth_uncertainty_m=1, label=None)
    sub.update(1, behind, ocean(thermocline_depth_m=lambda x, y: 100))
    assert not sub.pending_torpedoes
    assert sub.weapon_battery.remaining_total == 24


def test_friendly_surface_asroc_uses_only_detached_sonar_datum():
    ship = SurfaceShip(100, 100, random.Random(3), side="friendly",
                       doctrine="surface_combatant",
                       profile=CATALOG.surfaces["warship_01"],
                       runtime_catalog=CATALOG)
    observation = PlatformObservation(
        track_id="S-1", domain="sonar", source="SONAR",
        observer_x=ship.x, observer_y=ship.y, bearing=90, range_nm=None,
        x=None, y=None, course=None, speed_kn=None, depth_m=80,
        quality=.7, signal=.6, last_seen=1,
        bearing_uncertainty_deg=2, range_uncertainty_nm=None,
        depth_uncertainty_m=20, label=None)
    ship.update(.1, None, ocean(), asw_observation=observation)
    assert not ship.pending_asroc
    observation = PlatformObservation(
        track_id="S-1", domain="sonar", source="SONAR",
        observer_x=ship.x, observer_y=ship.y, bearing=90, range_nm=10,
        x=None, y=None, course=None, speed_kn=None, depth_m=80,
        quality=.7, signal=.6, last_seen=2,
        bearing_uncertainty_deg=2, range_uncertainty_nm=.5,
        depth_uncertainty_m=20, label=None, fix_source="TMA")
    ship.update(.1, None, ocean(), asw_observation=observation)
    assert len(ship.pending_asroc) == 1
    launch = ship.pending_asroc[0]
    assert launch["datum_x"] == pytest.approx(observation.observer_x + 10)
    assert launch["datum_y"] == pytest.approx(observation.observer_y)
    assert ship.asroc_battery.remaining_total == 7
    ship.update(.1, None, ocean(), asw_observation=observation)
    assert len(ship.pending_asroc) == 1


def test_surface_asroc_preserves_observed_zero_depth():
    ship = SurfaceShip(100, 100, random.Random(30), side="friendly",
                       doctrine="surface_combatant",
                       profile=CATALOG.surfaces["warship_01"],
                       runtime_catalog=CATALOG)
    observation = PlatformObservation(
        track_id="S-zero", domain="sonar", source="SONAR",
        observer_x=ship.x, observer_y=ship.y, bearing=90, range_nm=10,
        x=110, y=100, course=None, speed_kn=None, depth_m=0.0,
        quality=.7, signal=.6, last_seen=1,
        bearing_uncertainty_deg=2, range_uncertainty_nm=.5,
        depth_uncertainty_m=20, label=None, fix_source="TMA")

    ship.update(.1, None, ocean(), asw_observation=observation)

    assert ship.pending_asroc[0]["target_depth_m"] == 0.0


def test_full_pending_queues_do_not_consume_additional_rounds():
    sub = Sub(100, 100, 80, 0, "sub_03", random.Random(31),
              attack_mult=1000, runtime_catalog=CATALOG,
              asw_rng=random.Random(32))
    sub.pending_torpedoes = [tuple(range(9)), tuple(range(9))]
    sub.attack_left = 0
    sub.state, sub.heard_ping = "EVADE", True
    observation = PlatformObservation(
        track_id="F-full", domain="sonar", source="SONAR",
        observer_x=100, observer_y=100, bearing=0, range_nm=5,
        x=100, y=95, course=0, speed_kn=10, depth_m=5,
        quality=1, signal=1, last_seen=1,
        bearing_uncertainty_deg=1, range_uncertainty_nm=.1,
        depth_uncertainty_m=1, label=None, fix_source="TMA")
    before = sub.weapon_battery.remaining_total

    sub.update(1, observation, ocean(thermocline_depth_m=lambda x, y: 100))

    assert sub.weapon_battery.remaining_total == before


def test_packaged_passive_asroc_sensor_does_not_invent_launchable_range():
    ship = SurfaceShip(100, 100, random.Random(15), side="friendly",
                       doctrine="surface_combatant",
                       profile=CATALOG.surfaces["warship_01"],
                       runtime_catalog=CATALOG)
    sub = Sub(105, 100, 80, 0, "sub_03", random.Random(16),
              runtime_catalog=CATALOG)
    for controller in ship.sensor_suite.controllers.values():
        controller.next_scan_s = 0
    ship.sensor_suite.update(1, ship, [sub], ocean(), CATALOG,
                             emcon={"radar": False})
    observation = ship.sensor_suite.tactical_tracks(1)[0]
    assert observation.domain == "sonar" and observation.range_nm is None
    ship.update(.1, None, ocean(), asw_observation=observation)
    assert not ship.pending_asroc
    assert ship.asroc_battery.remaining_total == 8


def test_game_asw_ai_ignores_unassociated_sonar_observation():
    game = Game(seed=192, start_menu=False, audio_enabled=False)
    ship = SurfaceShip(
        100, 100, random.Random(14), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    observation = PlatformObservation(
        track_id="L-detached", domain="sonar", source="LOCAL",
        observer_x=100, observer_y=100, bearing=0, range_nm=5,
        x=100, y=95, course=None, speed_kn=None, depth_m=70,
        quality=.8, signal=.7, last_seen=game.sim_t,
        bearing_uncertainty_deg=2, range_uncertainty_nm=.5,
        depth_uncertainty_m=20, label=None)
    ship.sensor_suite.local_picture.observe(observation)
    for controller in ship.sensor_suite.controllers.values():
        controller.next_scan_s = game.sim_t + 100
    game.subs, game.civilians, game.warships = [], [], [ship]
    game.flights.flights = []
    game._update_platform_sensors(.1)
    assert ship._asw_observation is None


def _assign_game_contact(game):
    target = game.subs[0]
    contact = Contact(71, target.id, "ping", "sub")
    contact.update_ping(90, 5, target.depth, 1, game.sim_t)
    contact.observed_x, contact.observed_y = game.ship.x + 5, game.ship.y
    contact.player_class = "U_BOOT"
    game.sonar.contacts[target.id] = contact
    game.target = contact


def test_game_launch_consumes_ready_tubes_and_reload_uses_simulation_time():
    game = Game(seed=181, start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    for _ in range(2):
        game.launch_torpedo()
        game.torpedoes.clear()
    assert game.player_torpedo_battery.ready_count == 0
    assert game.torpedo_count == game.torpedo_total - 2
    assert game.torpedo_readiness()[0] == "BLOCKIERT: KEIN ROHR BEREIT"
    game.damage.compartments["weapons"].state = "ZERSTOERT"
    game._update_asw_stores(60)
    assert game.player_torpedo_battery.ready_count == 0
    game.damage.compartments["weapons"].state = "OK"
    game._update_asw_stores(60)
    assert game.player_torpedo_battery.ready_count == 2


def test_nixie_key_is_station_scoped_and_store_is_finite():
    game = Game(seed=180, start_menu=False, audio_enabled=False)
    initial = game.nixie_store.remaining_total
    game.station = Station.SONAR
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v))
    assert game.nixie_store.remaining_total == initial
    game.station = Station.WEAPONS
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v))
    assert game.nixie_store.remaining_total == initial - 1
    assert len(game.nixies) == 1


def test_game_asw_midphase_roundtrip_and_strict_validation():
    game = Game(seed=182, start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.launch_torpedo()
    game._update_asw_stores(12.5)
    game.deploy_nixie()
    game.asroc_seq = 4
    game.asrocs = [ASROC(
        game.ship.x, game.ship.y, game.ship.x + 5, game.ship.y, 4,
        "weapon.warship_01.asroc", "helo_torp", 500, 12, "friendly", 80)]
    asroc_ship = SurfaceShip(
        game.ship.x, game.ship.y, random.Random(17), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    assert asroc_ship.asroc_battery.fire() is not None
    game.asrocs[0].launch_platform_id = asroc_ship.id
    game.warships.append(asroc_ship)
    enemy_profile = game.runtime_catalog.torpedoes[
        game.runtime_catalog.runtime_bindings["enemy_torpedo"]]
    source = game.subs[0]
    if source.weapon_battery is not None:
        weapon_key = source.weapon_battery.fire()
        assert weapon_key is not None
        source.torpedoes_left = source.weapon_battery.remaining_total
    else:
        weapon_key = None
        source.torpedoes_left -= 1
    enemy = EnemyTorpedo(
        game.ship.x + 2.5, game.ship.y, 270, 5, 1, profile=enemy_profile,
        guidance_x=game.ship.x + 2.5, guidance_y=game.ship.y,
        launch_platform_id=source.id, launch_weapon_key=weapon_key)
    enemy.update(0, game.ship, ocean(), seeker_candidates=game.nixies)
    game.enemy_torpedoes = [enemy]
    state = game.save_state()
    game.load_state(copy.deepcopy(state))
    assert game.player_torpedo_battery.serialize() == state["asw"]["player_battery"]
    assert game.nixie_store.serialize() == state["asw"]["countermeasure"]
    assert [item.serialize() for item in game.asrocs] == state["asw"]["asrocs"]
    assert game.enemy_torpedoes[0].terminal_active
    assert game.enemy_torpedoes[0]._seeker_target is game.nixies[0]
    assert game.save_state() == state

    malformed = copy.deepcopy(state)
    malformed["asw"]["player_battery"]["tubes"][0]["index"] = 99
    before = game.save_state()
    assert not game._load_save_data(malformed)
    assert game.save_state() == before

    malformed = copy.deepcopy(state)
    malformed["asw"]["player_battery"]["launcher_key"] = "launcher.fake"
    assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["asw"]["asrocs"][0]["weapon_key"] = "weapon.fake"
    assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["rngs"].pop("asw")
    assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["torpedoes_in_flight"][0]["speed_kn"] += 1
    assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["torpedoes_in_flight"][0]["kill_dist_nm"] = 1000
    assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["enemy_torpedoes"][0]["seeker_acquired"] = False
    assert not game._load_save_data(malformed)


def test_embedded_ownship_loadout_remains_authoritative():
    game = Game(seed=188, start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.launch_torpedo()
    state = game.save_state()
    state["asw"]["loadout"]["launcher"]["reload_s"] = 75
    state["asw"]["player_battery"]["reload_s"] = 75
    game.load_state(state)
    assert game._ownship_loadout["launcher"]["reload_s"] == 75
    assert game.player_torpedo_battery.reload_s == 75


def test_v10_without_asw_block_is_rejected_transactionally():
    game = Game(seed=189, start_menu=False, audio_enabled=False)
    state = game.save_state()
    state.pop("asw")
    state["rngs"].pop("asw")
    for sub in state["subs"]:
        sub.pop("asw_battery", None)
        sub.pop("countermeasure_store", None)
    for ship in state["warships"]:
        ship.pop("asroc_battery", None)
        ship.pop("pending_asroc", None)
        ship.pop("asw_last_seen", None)
    before = game.save_state()
    assert not game._load_save_data(state)
    assert game.save_state() == before


def test_dead_nixie_roundtrips_without_resurrection():
    game = Game(seed=193, start_menu=False, audio_enabled=False)
    game.deploy_nixie()
    game.nixies[0].dead, game.nixies[0].state = True, "SASE"
    state = game.save_state()
    game.load_state(state)
    assert game.nixies[0].dead and game.nixies[0].state == "SASE"


def test_asw_rng_split_run_matches_uninterrupted_salvo():
    game = Game(seed=194, start_menu=False, audio_enabled=False)
    game.subs = [Sub(
        100, 100, 80, 0, "sub_03", game.rng_world,
        attack_mult=1000, runtime_catalog=game.runtime_catalog,
        asw_rng=game.rng_asw)]
    game.subs[0].attack_left = 0
    game.subs[0].state, game.subs[0].heard_ping = "EVADE", True
    state = game.save_state()
    observation = PlatformObservation(
        track_id="F-3", domain="sonar", source="SONAR",
        observer_x=100, observer_y=100, bearing=0, range_nm=5,
        x=100, y=95, course=0, speed_kn=10, depth_m=5,
        quality=1, signal=1, last_seen=1,
        bearing_uncertainty_deg=1, range_uncertainty_nm=.1,
        depth_uncertainty_m=1, label=None)
    game.subs[0].update(
        1, observation, ocean(thermocline_depth_m=lambda x, y: 100))
    expected = (game.subs[0].pending_torpedoes,
                game.subs[0].weapon_battery.serialize(), game.rng_asw.getstate())

    restored = Game(seed=999, start_menu=False, audio_enabled=False)
    restored.load_state(state)
    restored.subs[0].update(
        1, observation, ocean(thermocline_depth_m=lambda x, y: 100))
    actual = (restored.subs[0].pending_torpedoes,
              restored.subs[0].weapon_battery.serialize(),
              restored.rng_asw.getstate())
    assert actual == expected


def test_npc_battery_save_is_bound_to_profile_components():
    game = Game(seed=184, start_menu=False, audio_enabled=False)
    game.subs = [Sub(
        100, 100, 80, 90, "sub_03", random.Random(5),
        runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)]
    state = game.save_state()
    assert state["subs"][0]["asw_battery"] is not None
    state["subs"][0]["asw_battery"]["launcher_key"] = "launcher.fake"
    assert not game._load_save_data(state)


def test_r8_save_requires_runtime_stores_for_profiles_that_define_them():
    game = Game(seed=190, start_menu=False, audio_enabled=False)
    game.subs = [Sub(
        100, 100, 80, 90, "sub_03", random.Random(10),
        runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)]
    state = game.save_state()
    state["subs"][0]["asw_battery"] = None
    assert not game._load_save_data(state)

    ship = SurfaceShip(
        100, 100, random.Random(11), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    game.warships = [ship]
    state = game.save_state()
    state["warships"][0]["asroc_battery"] = None
    assert not game._load_save_data(state)


def test_pending_launches_cannot_exceed_spent_inventory():
    game = Game(seed=191, start_menu=False, audio_enabled=False)
    clean = game.save_state()
    _assign_game_contact(game)
    game.launch_torpedo()
    impossible = copy.deepcopy(clean)
    impossible["torpedoes_in_flight"] = game.save_state()["torpedoes_in_flight"]
    assert not game._load_save_data(impossible)

    game.subs = [Sub(
        100, 100, 80, 90, "sub_03", random.Random(12),
        runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)]
    state = game.save_state()
    state["subs"][0]["pending_torpedoes"] = [
        [100, 100, 90, 8, 105, 100, "enemy_torp"]]
    assert not game._load_save_data(state)

    ship = SurfaceShip(
        100, 100, random.Random(13), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    game.warships = [ship]
    state = game.save_state()
    state["warships"][0]["pending_asroc"] = [{
        "x": 100, "y": 100, "datum_x": 105, "datum_y": 100,
        "weapon_key": "weapon.warship_01.asroc", "target_depth_m": 80,
    }]
    assert not game._load_save_data(state)


def test_asroc_queue_retains_reserved_launches_at_global_limit():
    game = Game(seed=185, start_menu=False, audio_enabled=False)
    ship = SurfaceShip(
        game.ship.x, game.ship.y, random.Random(4), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    ship.pending_asroc = [{
        "x": ship.x, "y": ship.y, "datum_x": ship.x + 5,
        "datum_y": ship.y, "weapon_key": "weapon.warship_01.asroc",
        "target_depth_m": 60,
    }]
    game.warships = [ship]
    game.asrocs = [SimpleNamespace() for _ in range(128)]
    game._drain_asrocs()
    assert len(ship.pending_asroc) == 1


def test_newly_queued_asroc_starts_flight_on_next_substep():
    game = Game(seed=203, start_menu=False, audio_enabled=False)
    ship = SurfaceShip(
        game.ship.x, game.ship.y, random.Random(31), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    weapon_key = ship.asroc_battery.fire()
    ship.pending_asroc = [{
        "x": ship.x, "y": ship.y, "datum_x": ship.x + 5,
        "datum_y": ship.y, "weapon_key": weapon_key,
        "target_depth_m": 60,
    }]
    game.warships = [ship]
    game._update_asrocs(.1)
    assert len(game.asrocs) == 1 and game.asrocs[0].travel == 0


def test_game_asroc_water_entry_spawns_one_datum_guided_payload():
    game = Game(seed=183, start_menu=False, audio_enabled=False)
    game.asroc_seq = 1
    game.asrocs = [ASROC(
        game.ship.x, game.ship.y, game.ship.x + .1, game.ship.y, 1,
        "weapon.warship_01.asroc", "helo_torp", 3600, 12, "friendly", 90)]
    game._update_asrocs(.1)
    assert not game.asrocs
    assert len(game.torpedoes) == 1
    payload = game.torpedoes[0]
    assert (payload.guidance_x, payload.guidance_y) == pytest.approx(
        (game.ship.x + .1, game.ship.y))
    assert payload.profile_key == "helo_torp"
    assert payload.launch_origin == "asroc"
    assert payload.wire_state == "BROKEN"


def test_asroc_payload_does_not_reuse_rocket_flight_substep():
    game = Game(seed=186, start_menu=False, audio_enabled=False)
    game.asroc_seq = 1
    game.asrocs = [ASROC(
        game.ship.x, game.ship.y, game.ship.x + .001, game.ship.y, 1,
        "weapon.warship_01.asroc", "helo_torp", 500, 12, "friendly", 90)]
    game._update_sim(.1)
    payload = game.torpedoes[-1]
    assert payload.profile_key == "helo_torp"
    assert payload.travel == 0


def test_submarine_decoy_creation_does_not_consume_air_defense_rng():
    game = Game(seed=187, start_menu=False, audio_enabled=False)
    sub = game.subs[0]
    sub.pending_decoys.append((sub.x, sub.y))
    before = game.rng_asm.getstate()
    game._update_underwater_entities(0)
    assert game.rng_asm.getstate() == before


def test_enemy_torpedo_reaches_moving_contact_lead_datum():
    sub = Sub(100, 100, 80, 90, "sub_03", random.Random(20),
              runtime_catalog=CATALOG, asw_rng=random.Random(21))
    sub.asw_rng.uniform = lambda low, high: 0.0
    observation = PlatformObservation(
        track_id="F-moving", domain="sonar", source="LOCAL",
        observer_x=100, observer_y=100, bearing=90, range_nm=18,
        x=118, y=100, course=0, speed_kn=20, depth_m=5,
        quality=1, signal=1, last_seen=1,
        bearing_uncertainty_deg=1, range_uncertainty_nm=.5,
        depth_uncertainty_m=1, label=None)
    x, y, course, depth, datum_x, datum_y = sub._launch_data(observation)
    assert (datum_x, datum_y) != (observation.x, observation.y)
    weapon = EnemyTorpedo(
        x, y, course, depth, 1, guidance_x=datum_x, guidance_y=datum_y)
    hidden_ship = SimpleNamespace(x=118, y=100, depth=5, sunk=False)
    for _ in range(4000):
        weapon.update(1, hidden_ship, ocean())
        if weapon.terminal_active or weapon.state != "RUN":
            break
    assert weapon.terminal_active and weapon.state == "RUN"


def test_easy_helicopter_torpedo_roundtrips_with_difficulty_envelope():
    game = Game(seed=195, level="leicht", start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.helo.launch(game.ship)
    game.launch_helo_torpedo()
    assert game.torpedoes[-1].launch_origin == "helo"
    state = game.save_state()
    game.load_state(copy.deepcopy(state))
    assert game.save_state() == state


def test_v10_active_helicopter_torpedo_requires_explicit_provenance():
    game = Game(seed=196, level="normal", start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.helo.launch(game.ship)
    game.launch_helo_torpedo()
    state = game.save_state()
    row = state["torpedoes_in_flight"][0]
    for field in ("profile_key", "launch_origin", "launch_platform_id",
                  "launch_weapon_key"):
        row.pop(field)
    before = game.save_state()
    assert not game._load_save_data(state)
    assert game.save_state() == before


def test_current_asw_save_requires_datum_and_numeric_torpedo_phase():
    game = Game(seed=197, start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.launch_torpedo()
    state = game.save_state()
    missing_datum = copy.deepcopy(state)
    missing_datum["torpedoes_in_flight"][0]["guidance_x"] = None
    missing_datum["torpedoes_in_flight"][0]["guidance_y"] = None
    assert not game._load_save_data(missing_datum)
    for field, value in (("search_phase", "bad"), ("midcourse", 360)):
        malformed = copy.deepcopy(state)
        malformed["torpedoes_in_flight"][0][field] = value
        assert not game._load_save_data(malformed)
    malformed = copy.deepcopy(state)
    malformed["torpedo_seq"] = 0
    assert not game._load_save_data(malformed)


def test_current_enemy_torpedo_requires_observed_datum():
    game = Game(seed=201, start_menu=False, audio_enabled=False)
    sub = game.subs[0]
    if sub.weapon_battery is not None:
        weapon_key = sub.weapon_battery.fire()
        assert weapon_key is not None
        sub.torpedoes_left = sub.weapon_battery.remaining_total
    else:
        weapon_key = None
        sub.torpedoes_left -= 1
    game.enemy_torpedoes = [EnemyTorpedo(
        game.ship.x + 2, game.ship.y, 270, 5, 1,
        profile=sub.enemy_torpedo_profile,
        guidance_x=game.ship.x, guidance_y=game.ship.y,
        launch_platform_id=sub.id, launch_weapon_key=weapon_key)]
    state = game.save_state()
    assert Game._valid_save_document(state)
    state["enemy_torpedoes"][0]["guidance_x"] = None
    state["enemy_torpedoes"][0]["guidance_y"] = None
    assert not game._load_save_data(state)


def test_ownship_loadout_capacity_must_match_saved_difficulty():
    game = Game(seed=202, level="normal", start_menu=False, audio_enabled=False)
    state = game.save_state()
    state["level"] = "harte"
    assert not game._load_save_data(state)


def test_buoy_inventory_state_and_high_water_are_strict():
    game = Game(seed=198, start_menu=False, audio_enabled=False)
    game.helo.launch(game.ship)
    game.deploy_buoys()
    state = game.save_state()
    assert Game._valid_save_document(state)
    for patch in (
            lambda value: value["helo"].update(buoys_left=config.BUOY_COUNT),
            lambda value: value["buoys"][0].update(battery_s="forever"),
            lambda value: value.update(buoy_seq=0)):
        malformed = copy.deepcopy(state)
        patch(malformed)
        assert not game._load_save_data(malformed)


def test_active_decoys_cannot_exceed_source_store_spend():
    game = Game(seed=199, start_menu=False, audio_enabled=False)
    sub = Sub(100, 100, 80, 90, "sub_03", random.Random(22),
              runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)
    assert sub.countermeasure_store.fire()
    profile = game.runtime_catalog.decoys[
        game.runtime_catalog.runtime_bindings["submarine_decoy"]]
    game.subs = [sub]
    game.decoys = [Decoy(
        100, 100, 80, game.rng_asw, profile,
        game.runtime_catalog.acoustic_for(profile.key), source_id=sub.id)]
    state = game.save_state()
    duplicate = copy.deepcopy(state["decoys"][0])
    duplicate["id"] = state["next_entity_ids"]["decoy"]
    state["next_entity_ids"]["decoy"] += 1
    state["decoys"].append(duplicate)
    assert not game._load_save_data(state)


def test_decoy_cannot_be_attributed_to_submarine_without_store():
    game = Game(seed=204, start_menu=False, audio_enabled=False)
    sub = Sub(100, 100, 80, 90, "diesel_alt", random.Random(33),
              runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw)
    assert sub.countermeasure_store is None
    profile = game.runtime_catalog.decoys[
        game.runtime_catalog.runtime_bindings["submarine_decoy"]]
    game.subs = [sub]
    game.decoys = [Decoy(
        100, 100, 80, game.rng_asw, profile,
        game.runtime_catalog.acoustic_for(profile.key), source_id=sub.id)]

    assert not game._load_save_data(game.save_state())


def test_helicopter_torpedo_cannot_claim_frigate_provenance():
    game = Game(seed=205, start_menu=False, audio_enabled=False)
    _assign_game_contact(game)
    game.helo.launch(game.ship)
    game.launch_helo_torpedo()
    assert game.player_torpedo_battery.fire() is not None
    game.torpedo_count = game.player_torpedo_battery.remaining_total
    state = game.save_state()
    row = state["torpedoes_in_flight"][0]
    profile = game.runtime_catalog.torpedoes[row["profile_key"]]
    row["launch_origin"] = "frigate"
    row["kill_dist_nm"] = profile.hit_dist_nm
    row["kill_depth_m"] = Torpedo.KILL_DEPTH_M

    assert not game._load_save_data(state)


def test_asroc_inventory_is_bound_to_launch_platform_and_weapon_type():
    game = Game(seed=200, start_menu=False, audio_enabled=False)
    ships = [SurfaceShip(
        100 + index, 100, random.Random(30 + index), side="friendly",
        doctrine="surface_combatant", profile=CATALOG.surfaces[key],
        runtime_catalog=game.runtime_catalog)
        for index, key in enumerate(("warship_01", "warship_02"))]
    weapon_key = ships[0].asroc_battery.fire()
    weapon = game.runtime_catalog.weapons[weapon_key]
    game.asroc_seq = 1
    game.warships = ships
    game.asrocs = [ASROC(
        100, 100, 105, 100, 1, weapon.key, "helo_torp",
        weapon.maximum_speed_kn, weapon.engagement_range_nm[1], "friendly",
        80, ships[0].id)]
    state = game.save_state()
    assert Game._valid_save_document(state)
    wrong_key = ships[1].asroc_battery.weapon_keys[0]
    wrong_weapon = game.runtime_catalog.weapons[wrong_key]
    state["asw"]["asrocs"][0].update(
        weapon_key=wrong_key, speed_kn=wrong_weapon.maximum_speed_kn,
        range_nm=wrong_weapon.engagement_range_nm[1])
    assert not game._load_save_data(state)
