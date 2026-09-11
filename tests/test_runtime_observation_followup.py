"""Observation boundaries, swept civilian impacts, and local unit navigation."""

import copy
import random
from types import SimpleNamespace

import pytest

from src.air.asm import ASM
from src.air.flights import Flight
from src.core import config
from src.core.game import Game
from src.data.catalog import CATALOG
from src.enemies.animal import Animal
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.sonar.sonar import Contact
from src.weapons.torpedo import Torpedo


def water(**overrides):
    values = dict(size_nm=500, on_land=lambda x, y: False,
                  depth_m=lambda x, y: 1000,
                  thermocline_depth_m=lambda x, y: 100,
                  land_blocks_line=lambda *args: False)
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def game(monkeypatch):
    game = Game(seed=733, start_menu=False, audio_enabled=False)
    game.subs, game.animals, game.civilians, game.warships, game.decoys = [], [], [], [], []
    game.asms, game.essms, game.torpedoes = [], [], []
    game.flights.flights = []
    game.air_picture._tracks.clear()
    game.mission.asm_count = 0
    for name in ("on_land", "land_blocks_line", "sonar_path_blocked"):
        monkeypatch.setattr(game.world, name, lambda *args: False)
    monkeypatch.setattr(game.world, "depth_m", lambda *args: 1000)
    game.msg = "unchanged"
    return game


def observed_target(game, target_id):
    contact = Contact(17, target_id, "ping", "sub")
    contact.update_ping(90, 5, 50, 1, game.sim_t)
    contact.player_class = "U_BOOT"
    contact.observed_x, contact.observed_y = game.ship.x + 5, game.ship.y
    game.sonar.contacts[target_id] = contact
    game.target = contact
    return contact


@pytest.mark.parametrize("kind", ["sub", "civilian", "animal", "decoy", "missing"])
@pytest.mark.parametrize("launcher", ["launch_torpedo", "launch_helo_torpedo"])
def test_launch_authorization_is_observation_equivalent_across_hidden_categories(game, kind, launcher):
    rng = random.Random(1)
    entity = None
    if kind == "sub":
        entity = Sub(100, 100, 50, 0, "diesel_alt", rng)
        game.subs.append(entity)
    elif kind == "civilian":
        entity = SurfaceShip(100, 100, rng)
        game.civilians.append(entity)
    elif kind == "animal":
        entity = Animal(100, 100, "whale", rng)
        game.animals.append(entity)
    elif kind == "decoy":
        entity = Decoy(100, 100, 50, rng)
        game.decoys.append(entity)
    contact = observed_target(game, entity.id if entity else 999999)
    game.helo.launch(game.ship)
    assert game.torpedo_readiness()[0] == "FEUER FREI"
    getattr(game, launcher)()
    assert len(game.torpedoes) == 1
    assert (game.torpedoes[0].guidance_x, game.torpedoes[0].guidance_y) == (
        contact.observed_x, contact.observed_y)
    assert not hasattr(game, "_target_ids")


@pytest.mark.parametrize("affiliation", ["FRIEND", "NEUTRAL"])
@pytest.mark.parametrize("launcher", ["launch_torpedo", "launch_helo_torpedo"])
def test_empty_datum_shots_still_respect_protected_annotations(game, affiliation, launcher):
    observed_target(game, 999999)
    game.opz_affiliations["U-999999"] = affiliation
    game.helo.launch(game.ship)
    getattr(game, launcher)()
    assert not game.torpedoes


@pytest.mark.parametrize("depth,incident", [(5, True), (100, False)])
def test_civilian_incident_uses_swept_path_and_depth(game, depth, incident):
    civilian = SurfaceShip(100.5, 100, random.Random(1))
    game.civilians = [civilian]
    torpedo = Torpedo(100, 100, 90, depth, None, 1, speed_kn=3600,
                      guidance_x=130, guidance_y=100)
    torpedo.depth = depth
    game.torpedoes = [torpedo]
    game._update_player_torpedoes(1)
    assert game.incident is incident
    assert civilian.sunk is incident


def test_civilian_depth_must_overlap_at_collision_time_not_frame_end(game):
    civilian = SurfaceShip(100.2, 100, random.Random(1))
    game.civilians = [civilian]
    torpedo = Torpedo(100, 100, 90, 5, None, 1, speed_kn=360,
                      guidance_x=130, guidance_y=100)
    torpedo.depth = 105
    game.torpedoes = [torpedo]
    game._update_player_torpedoes(10)
    assert torpedo.depth < 20
    assert not game.incident and not civilian.sunk


def test_civilian_hit_cannot_cross_intervening_terrain(game, monkeypatch):
    game.civilians = [SurfaceShip(100.8, 100, random.Random(1))]
    monkeypatch.setattr(game.world, "sonar_path_blocked",
                        lambda x0, y0, d0, x1, y1, d1: min(x0, x1) <= 100.5 <= max(x0, x1))
    game.torpedoes = [Torpedo(100, 100, 90, 5, None, 1, speed_kn=3600,
                              guidance_x=130, guidance_y=100)]
    game._update_player_torpedoes(1)
    assert not game.incident and not game.civilians[0].sunk


def test_biological_candidate_can_be_acquired_without_revealing_hidden_identity(game):
    animal = Animal(100.5, 100, "whale", random.Random(1), depth_m=50)
    game.animals = [animal]
    torpedo = Torpedo(100, 100, 90, 50, None, 1, speed_kn=3600,
                      guidance_x=100.5, guidance_y=100)
    torpedo.depth = 50
    game.torpedoes = [torpedo]
    before = len(game.feed.entries)
    game._update_player_torpedoes(1)
    assert animal.dead and torpedo.target is animal
    assert not game.incident
    assert game.msg == "unchanged" and len(game.feed.entries) == before


def test_r10_batch5_profiles_add_no_hidden_observation_or_weapon_capabilities():
    for key in (*CATALOG.animals, *CATALOG.decoys):
        systems = CATALOG.profile_systems[key]
        assert systems.sensor_keys == systems.emitter_keys == ()
        assert systems.launcher_keys == systems.magazine_keys == \
            systems.countermeasure_keys == ()
    animal = Animal(100, 100, "whale", random.Random(81), depth_m=50)
    decoy = Decoy(100, 100, 50, random.Random(82))
    assert not hasattr(animal, "sensor_suite")
    assert not hasattr(decoy, "sensor_suite")


def test_decoy_and_salvo_spawn_callbacks_do_not_publish_hidden_notifications(game):
    sub = Sub(100, 100, 50, 0, "diesel_alt", random.Random(1))
    sub.pending_decoys = [(100, 100)]
    game.subs = [sub]
    warship = SurfaceShip(100, 100, random.Random(2), hostile=True)
    warship.sensor_contact = (120, 100)
    warship.sensor_contact_age = 0
    warship.pending_asm = [(100, 100, 2)]
    game.warships = [warship]
    before = len(game.feed.entries), list(game.messages)
    game._drain_warship_asm()
    assert all(asm.course == 90 for asm in game.asms)
    game._update_underwater_entities(.1)
    game.mission.asm_count = 1
    game.mission_time = config.ASM_SPAWN_FIRST_S
    game._maybe_spawn_asm()
    assert game.decoys and len(game.asms) == 3
    assert game.msg == "unchanged"
    assert (len(game.feed.entries), game.messages) == before


def test_air_threat_report_requires_a_modeled_track_and_is_not_repeated(game):
    game.radar_on = False
    missile = ASM(game.ship.x + 10, game.ship.y, 270, 1, game.rng_asm)
    missile.jammer = False
    game.asms = [missile]
    game._update_air_defense(.1)
    assert game.msg == "unchanged" and not game.air_threat_reported
    game.air_picture.observe(track_id="M-1", kind="ASM", target_id=1,
                             source="RADAR-L", bearing=90, range_nm=10,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=game.sim_t, label="M1")
    game._update_air_defense(.1)
    assert game.msg["__u_jagd_i18n__"] == "runtime.threat.air"
    count = len(game.feed.entries)
    game._update_air_defense(.1)
    assert len(game.feed.entries) == count


def test_surface_own_radar_contact_freezes_on_loss_then_expires():
    warship = SurfaceShip(100, 100, random.Random(1), hostile=True)
    player = SimpleNamespace(x=110, y=100)
    warship.emitter = False
    warship.attack_left = 0
    warship.update(.1, player, water())
    assert warship.sensor_contact is None and not warship.pending_asm
    warship.emitter = True
    warship.update(.1, player, water())
    assert warship.sensor_contact == (110, 100) and warship.pending_asm
    player.x, player.y = 90, 120
    warship.update(1, player, water(land_blocks_line=lambda *args: True))
    assert warship.sensor_contact == (110, 100)
    warship.emitter = False
    warship.pending_asm.clear()
    warship.attack_left = 0
    warship.update(config.RADAR_TRACK_STALE_S, player, water())
    assert warship.sensor_contact is None and not warship.pending_asm


def test_surface_coast_avoidance_wins_over_tactical_orders():
    warship = SurfaceShip(100, 100, random.Random(1), hostile=True)
    warship.course = warship.target_course = 90
    warship.speed = 6
    warship.orbit_direction = 1
    player = SimpleNamespace(x=90, y=100)  # Tactical evasion orders east, into land.
    coast = water(on_land=lambda x, y: x >= 100.1)
    # Use the endpoint fallback for this deliberately minimal world.
    del coast.land_blocks_line
    warship.update(1, player, coast)
    assert warship.course > 90 and warship.target_course != 90


def patrol():
    flight = Flight("military", dict(id="base", x=100, y=100, nation="BOREN"),
                    rng=random.Random(1))
    flight.x, flight.y = 100, 100
    return flight


def test_aircraft_esm_requires_emission_and_keeps_only_aged_bearing():
    flight = patrol()
    player = SimpleNamespace(x=110, y=100)
    flight.update(.1, player, world=water())
    assert flight.sensor_bearing is None
    flight.update(.1, player, ship_emitting=True, world=water())
    bearing = flight.sensor_bearing
    assert bearing is not None
    player.x, player.y = 90, 130
    flight.update(1, player, ship_emitting=False, world=water())
    assert flight.sensor_bearing == bearing
    flight.update(config.RADAR_TRACK_STALE_S, player, ship_emitting=True,
                  world=water(land_blocks_line=lambda *args: True))
    assert flight.sensor_bearing is None


def test_aircraft_receiver_capability_does_not_make_it_an_emitter(game):
    flight = patrol()
    flight.x, flight.y = game.ship.x + 50, game.ship.y
    game.flights.flights = [flight]
    game.radar_on = False
    flight.radar_emitting = False
    flight.esm = True
    game._update_air_picture()
    game._update_esm_picture()
    assert not game.air_picture.tracks(game.sim_t)
    assert not game.eloka_tracks()
    flight.radar_emitting = True
    flight.esm = False
    flight.esm_range_nm = 1  # Its receiver range is not the player's receiver range.
    game._update_esm_picture()
    assert len(game.eloka_tracks()) == 1
    assert not game.air_picture.tracks(game.sim_t)


@pytest.mark.parametrize("state,rate", [("PATROLLE", .5), ("EVADE", 1.5),
                                         ("LAUER", .5)])
def test_submarine_safe_command_never_teleports_depth(state, rate):
    sub = Sub(100, 100, 70, 0, "diesel_alt", random.Random(1))
    sub.state, sub.evac_left, sub.target_depth = state, 100, 1000
    sub.rng.random = lambda: 1.0
    player = SimpleNamespace(x=400, y=400, noise_level=lambda: 0)
    sub.update(.1, player, water(depth_m=lambda x, y: 80))
    assert sub.target_depth <= 55
    assert sub.depth > 55
    assert abs(sub.depth - 70) <= rate * .1 + 1e-9


def test_submarine_depth_converges_without_overshoot_and_does_not_cross_shoal():
    sub = Sub(100, 100, 50, 90, "diesel_alt", random.Random(1))
    sub.state, sub.evac_left = "EVADE", 100
    player = SimpleNamespace(x=400, y=400, noise_level=lambda: 0)
    sub.update(10, player, water(depth_m=lambda x, y: 80))
    assert sub.depth == sub.target_depth == 55
    sub.course = 90
    before = sub.x
    sub.update(60, player, water(depth_m=lambda x, y: 30 if x > before + .001 else 80))
    assert sub.x == before


def test_animal_target_depth_respects_seabed_and_rate():
    animal = Animal(100, 100, "whale", random.Random(1), depth_m=45)
    animal.target_depth = 200
    world = water(depth_m=lambda x, y: 50)
    animal.update(1, world)
    assert animal.target_depth == 49 and animal.depth == 46
    animal.update(10, world)
    assert animal.depth == 49


def test_decoy_terrain_collision_expires_without_crossing_land():
    decoy = Decoy(100, 100, 50, random.Random(1))
    decoy.course, decoy.speed = 90, 1
    decoy.update(1, water(on_land=lambda x, y: 100.2 <= x <= 100.4))
    assert decoy.dead and (decoy.x, decoy.y) == (100, 100)


def test_new_ai_observations_and_alert_state_roundtrip(game):
    warship = SurfaceShip(100, 100, random.Random(1), hostile=True)
    warship.sensor_contact, warship.sensor_contact_age = (110, 105), 2
    game.warships = [warship]
    flight = patrol()
    flight.base_id = game.world.coast.airbases[0]["id"]
    flight.radar_emitting, flight.sensor_bearing, flight.sensor_age = False, 123, 4
    game.flights.flights = [flight]
    game.air_threat_reported = True
    game.load_state(game.save_state())
    assert game.warships[0].sensor_contact == (110, 105)
    assert game.warships[0].sensor_contact_age == 2
    assert not game.flights.flights[0].radar_emitting
    assert game.flights.flights[0].sensor_bearing == 123
    assert game.flights.flights[0].sensor_age == 4
    assert game.air_threat_reported


@pytest.mark.parametrize("field,value", [("sensor_contact", [1]),
                                         ("sensor_contact", [1, float("nan")]),
                                         ("sensor_contact_age", 31)])
def test_invalid_surface_observations_are_rejected_transactionally(game, field, value):
    game.warships = [SurfaceShip(100, 100, random.Random(1), hostile=True)]
    before = game.save_state()
    data = copy.deepcopy(before)
    data["warships"][0][field] = value
    assert not game._load_save_data(data)
    assert game.save_state() == before


@pytest.mark.parametrize("field,value", [("radar_emitting", "yes"),
                                         ("sensor_age", -1), ("sensor_age", 31),
                                         ("sensor_bearing", 360),
                                         ("sensor_bearing", float("inf"))])
def test_invalid_aircraft_observations_are_rejected_transactionally(game, field, value):
    flight = patrol()
    flight.base_id = game.world.coast.airbases[0]["id"]
    game.flights.flights = [flight]
    before = game.save_state()
    data = copy.deepcopy(before)
    data["flights"]["items"][0][field] = value
    assert not game._load_save_data(data)
    assert game.save_state() == before


def test_invalid_air_threat_notice_state_is_rejected_transactionally(game):
    before = game.save_state()
    data = copy.deepcopy(before)
    data["air_threat_reported"] = 1
    assert not game._load_save_data(data)
    assert game.save_state() == before
