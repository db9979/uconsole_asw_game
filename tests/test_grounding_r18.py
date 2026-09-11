"""R18 physical grounding, recovery, persistence, and API boundaries."""

import copy
from dataclasses import replace
import inspect
import json
import random

import pygame
import pytest

from src.core import config
from src.core.game import Game
from src.core.i18n import Translator
from src.core.station import Station
from src.ship.damage import DamageModel
from src.ship.ship import Ship
from src.world.coastline import Coastline
from src.world.grounding import (DEFAULT_HULL_SPEC, HullSpec,
                                 grounding_contact_is_consistent,
                                 swept_grounding)
from src.world.world import World


def _world(*, size=2.0, landmasses=(), depths=None):
    data = {"world_nm": size, "landmasses": list(landmasses), "airbases": []}
    if depths is not None:
        data["bathymetry"] = {"size": len(depths), "values": depths}
    return World(seed=1, size_nm=size, coast=Coastline(data, size))


def test_new_only_synthetic_shallows_are_deterministic_and_start_is_safe():
    first = Coastline.generate(1818)
    second = Coastline.generate(1818)
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["bathymetry"]["synthetic_shallows"] == 1
    assert min(map(min, first.to_dict()["bathymetry"]["values"])) < 9.0

    restored_data = copy.deepcopy(first.to_dict())
    restored_data["bathymetry"].pop("synthetic_shallows")
    restored = Coastline.from_dict(restored_data)
    assert restored.to_dict() == restored_data

    game = Game(seed=1818, start_menu=False, audio_enabled=False)
    assert game.world.hull_is_safe(game.ship.x, game.ship.y, game.ship.course,
                                   game.ship.hull_spec)


def test_hull_dimensions_materially_affect_boundary_and_shallow_queries():
    world = _world(depths=[[100.0, 100.0], [100.0, 100.0]])
    small = HullSpec(length_m=20.0, beam_m=5.0)
    long = HullSpec(length_m=700.0, beam_m=5.0)
    assert world.hull_is_safe(.15, 1.0, 270.0, small)
    assert not world.hull_is_safe(.15, 1.0, 270.0, long)

    shallow = _world(depths=[[8.0, 8.0], [8.0, 8.0]])
    assert shallow.hull_is_safe(1.0, 1.0, 0.0,
                                HullSpec(draft_m=5.0, keel_reserve_m=1.0))
    assert not shallow.hull_is_safe(1.0, 1.0, 0.0,
                                    HullSpec(draft_m=7.0, keel_reserve_m=1.5))


def test_swept_first_contact_land_boundary_shallow_and_partition_invariance():
    land = {"name": "hazard", "points": [[1.0, .4], [1.1, .4],
                                             [1.1, 1.6], [1.0, 1.6]]}
    world = _world(landmasses=[land])
    hull = HullSpec(length_m=40.0, beam_m=10.0)
    whole = swept_grounding(world, (.5, 1.0, 90.0), (1.5, 1.0, 90.0), hull)
    first = swept_grounding(world, (.5, 1.0, 90.0), (.8, 1.0, 90.0), hull)
    second = swept_grounding(world, (first.safe_x_nm, first.safe_y_nm, 90.0),
                             (1.5, 1.0, 90.0), hull)
    assert whole.contacted and whole.contact.kind == "land"
    assert not first.contacted and second.contacted
    assert second.safe_x_nm == pytest.approx(whole.safe_x_nm, abs=1e-9)
    assert whole.query_count <= 2100

    boundary = swept_grounding(world, (1.5, .2, 0.0), (1.5, -.2, 0.0), hull)
    assert boundary.contact.kind == "boundary"
    shallow = _world(depths=[[100.0, 100.0, 100.0],
                             [100.0, 5.0, 100.0],
                             [100.0, 100.0, 100.0]])
    bottom = swept_grounding(shallow, (.2, 1.0, 90.0), (1.0, 1.0, 90.0), hull)
    assert bottom.contact.kind == "shallow"


def test_499_nm_sweep_cannot_tunnel_through_one_thousandth_nm_land():
    strip = {"name": "strip", "nation": "ZIVIL",
             "points": [[250.0, 249.0], [250.001, 249.0],
                         [250.001, 251.0], [250.0, 251.0]]}
    world = _world(size=500.0, landmasses=[strip])
    hull = HullSpec(length_m=100.0, beam_m=100.0)
    result = swept_grounding(
        world, (.25, 250.0, 90.0), (499.25, 250.0, 90.0),
        hull)

    assert result.contacted and result.contact.kind == "land"
    assert result.fraction == pytest.approx(
        (250.0 - .25 - 50.0 / 1852.0) / 499.0, abs=1e-12)
    assert result.query_count <= 2049

    pose = (result.safe_x_nm, result.safe_y_nm, result.safe_course_deg)
    assert grounding_contact_is_consistent(world, pose, hull,
                                            contact=result.contact)
    assert not grounding_contact_is_consistent(
        world, pose, hull,
        replace(result.contact, normal_x=-result.contact.normal_x,
                normal_y=-result.contact.normal_y))
    assert not grounding_contact_is_consistent(
        world, pose, hull,
        replace(result.contact, normal_x=-result.contact.normal_y,
                normal_y=result.contact.normal_x))


def test_tiny_translated_turn_keeps_exact_strip_handling_and_partition_stability():
    strip = {"name": "strip", "nation": "ZIVIL",
             "points": [[250.0, 249.0], [250.001, 249.0],
                        [250.001, 251.0], [250.0, 251.0]]}
    world = _world(size=500.0, landmasses=[strip])
    hull = HullSpec(length_m=100.0, beam_m=100.0)
    start = (.25, 250.0, 90.0)
    split = (100.0, 250.0, 90.0001998997996)
    end = (499.25, 250.0, 90.001)

    whole = swept_grounding(world, start, end, hull)
    first = swept_grounding(world, start, split, hull)
    second = swept_grounding(
        world, (first.safe_x_nm, first.safe_y_nm, first.safe_course_deg), end, hull)

    assert whole.contacted and whole.contact.kind == "land"
    assert not first.contacted and second.contacted
    assert second.safe_x_nm == pytest.approx(whole.safe_x_nm, abs=1e-9)
    assert second.safe_course_deg == pytest.approx(whole.safe_course_deg, abs=1e-12)


def test_two_degree_stationary_turn_sweeps_thin_land_strip():
    # The narrow radial strip is clear at 0 degrees and crossed by the bow while
    # rotating; there is no centre translation to provide a fallback path.
    strip = {"name": "turn-strip", "nation": "ZIVIL",
             "points": [[250.0004, 249.9677], [250.0014, 249.9677],
                        [250.0014, 249.9687], [250.0004, 249.9687]]}
    world = _world(size=500.0, landmasses=[strip])
    hull = HullSpec(length_m=118.0, beam_m=1.0)

    result = swept_grounding(
        world, (250.0, 250.0, 0.0), (250.0, 250.0, 2.0), hull)

    assert result.contacted and result.contact.kind == "land"


def test_exact_land_sweep_covers_hull_interior_between_nine_sample_paths():
    # This island sits between the centre and starboard edge trajectories.
    strip = {"name": "offset", "nation": "ZIVIL",
             "points": [[250.0, 250.020], [250.001, 250.020],
                        [250.001, 250.021], [250.0, 250.021]]}
    world = _world(size=500.0, landmasses=[strip])
    result = swept_grounding(
        world, (.25, 250.0, 90.0), (499.25, 250.0, 90.0),
        HullSpec(length_m=100.0, beam_m=100.0))

    assert result.contacted and result.contact.kind == "land"
    assert abs(result.contact.hull_lateral) < 1.0


def test_shallow_query_detects_one_metre_cell_inside_100_metre_hull():
    size_nm = 100.0 / 1852.0
    grid_size = 101
    depths = [[100.0] * grid_size for _ in range(grid_size)]
    for row in (50, 51):
        for column in (50, 51):
            depths[row][column] = 1.0
    world = _world(size=size_nm, depths=depths)
    hull = HullSpec(length_m=100.0, beam_m=100.0)

    contact = world.grounding_contact(size_nm / 2.0, size_nm / 2.0, 0.0, hull)
    assert contact is not None and contact.kind == "shallow"


def test_length_and_beam_expand_the_exact_shallow_footprint():
    depths = [[100.0] * 11 for _ in range(11)]
    depths[5][8] = 1.0
    beam_hazard = _world(size=.1, depths=depths)
    depths = [[100.0] * 11 for _ in range(11)]
    depths[2][5] = 1.0
    length_hazard = _world(size=.1, depths=depths)
    small = HullSpec(length_m=10.0, beam_m=10.0)

    assert beam_hazard.hull_is_safe(.05, .05, 0.0, small)
    assert not beam_hazard.hull_is_safe(
        .05, .05, 0.0, HullSpec(length_m=10.0, beam_m=120.0))
    assert length_hazard.hull_is_safe(.05, .05, 0.0, small)
    assert not length_hazard.hull_is_safe(
        .05, .05, 0.0, HullSpec(length_m=120.0, beam_m=10.0))


def test_grounding_damage_is_local_monotone_immediate_and_does_not_draw_rng():
    rng = random.Random(88)
    model = DamageModel(rng)
    before_rng = rng.getstate()
    low = model.grounding_impact(1_000_000.0, 1.0, -1.0)
    low_total = model.total
    assert rng.getstate() == before_rng
    assert set(low) == {"hull_left", "bridge"}
    assert model.total == sum(room.flood for room in model.compartments.values())
    model.grounding_impact(4_000_000.0, 1.0, -1.0)
    assert model.total > low_total
    assert len(model.compartments) == 9


def test_one_contact_transition_and_deliberate_astern_recovery():
    world = _world()
    ship = Ship(.15, 1.0, course_deg=270.0, speed_kn=10.0)
    ship.target_speed = 10.0
    impact = ship.update(100.0, world)
    assert impact is not None and ship.grounded and ship.speed == 0.0
    assert ship.update(10.0, world) is None
    blocked_x = ship.x

    ship.order_idx = 0
    ship.cycle_telegraph(-1)
    assert ship.telegraph == "ASTERN" and ship.target_speed == config.ASTERN_SPEED_KN
    assert ship.update(1.0, world) is None
    assert not ship.grounded and ship.x > blocked_x and ship.speed >= 0.0
    ship.cycle_telegraph(1)
    assert ship.telegraph == "STOP"


def test_astern_recovery_cannot_cross_a_reverse_obstacle():
    rear = {"name": "rear", "points": [[.24, .5], [.30, .5],
                                          [.30, 1.5], [.24, 1.5]]}
    world = _world(landmasses=[rear])
    ship = Ship(.15, 1.0, course_deg=270.0, speed_kn=10.0)
    ship.target_speed = 10.0
    assert ship.update(100.0, world) is not None
    ship.order_idx = 0
    ship.cycle_telegraph(-1)
    ship.update(1.0, world)
    assert not ship.grounded
    for _ in range(300):
        contact = ship.update(1.0, world)
        if contact is not None:
            break
    assert contact.kind == "land" and ship.grounded
    assert ship.x < .24


def test_contact_save_split_recovery_continuation_is_deterministic():
    game = Game(seed=919, start_menu=False, audio_enabled=False)
    game.world = _world()
    game.flights.flights = []
    game.ship.x, game.ship.y, game.ship.course = .15, 1.0, 270.0
    game.ship.target_course = 270.0
    game.ship.last_safe_pose = (.15, 1.0, 270.0)
    game.ship.speed = game.ship.target_speed = 10.0
    game._update_navigation(100.0)
    assert game.ship.grounded
    saved = game.save_state()

    restored = Game(seed=920, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(saved))
    for current in (game, restored):
        current.ship.order_idx = 0
        current.ship.cycle_telegraph(-1)
        current._update_navigation(2.0)
    assert restored.save_state()["ship"] == game.save_state()["ship"]
    assert restored.save_state()["damage"] == game.save_state()["damage"]
    assert restored.save_state()["rngs"] == game.save_state()["rngs"]


def test_current_roundtrip_and_exact_pre_r18_upgrade_preserve_bathymetry(tmp_path):
    game = Game(seed=818, start_menu=False, audio_enabled=False)
    current = game.save_state()
    clone = Game(seed=1, start_menu=False, audio_enabled=False)
    clone.load_state(copy.deepcopy(current))
    restored = clone.save_state()
    assert restored["ship"] == current["ship"]
    assert restored["rngs"] == current["rngs"]

    old = copy.deepcopy(current)
    for key in ("astern", "hull", "grounding"):
        old["ship"].pop(key)
    bathymetry = copy.deepcopy(old["world"]["coast"]["bathymetry"])
    path = tmp_path / "old.json"
    path.write_text(json.dumps(old))
    assert clone.load_game(str(path))
    assert clone.world.coast.to_dict()["bathymetry"] == bathymetry
    assert not clone.ship.grounded and not clone.ship.astern
    assert clone.ship.last_safe_pose == (clone.ship.x, clone.ship.y, clone.ship.course)

    near_miss = copy.deepcopy(old)
    near_miss["ship"]["almost_grounding"] = None
    path.write_text(json.dumps(near_miss))
    before = clone.save_state()
    assert not clone.load_game(str(path))
    assert clone.save_state() == before


@pytest.mark.parametrize("pre_r18", [False, True])
@pytest.mark.parametrize("mutation", [
    lambda coast: coast.update(world_nm=500),
    lambda coast: coast.update(world_nm=float("inf")),
    lambda coast: coast["bathymetry"].update(size=16),
    lambda coast: coast["bathymetry"]["values"].pop(),
    lambda coast: coast["bathymetry"]["values"][0].pop(),
    lambda coast: coast["bathymetry"]["values"][0].__setitem__(0, True),
    lambda coast: coast["landmasses"][0]["points"].__setitem__(0, [False, 0]),
    lambda coast: coast.update(metadata={"sector_id": "incomplete"}),
])
def test_world_snapshot_is_strictly_rejected_before_restore(pre_r18, mutation):
    game = Game(seed=818, start_menu=False, audio_enabled=False)
    malformed = copy.deepcopy(game.save_state())
    if pre_r18:
        for key in ("astern", "hull", "grounding"):
            malformed["ship"].pop(key)
    mutation(malformed["world"]["coast"])
    before = game.save_state()

    assert not game._load_save_data(malformed, allow_pre_r9=True)
    assert game.save_state() == before


def test_coastline_snapshot_and_restore_are_detached_both_ways():
    source = Coastline.generate(818).to_dict()
    coast = Coastline.from_dict(source)
    baseline = coast.to_dict()

    source["landmasses"][0]["points"][0][0] = 0.0
    source["airbases"].clear()
    source["bathymetry"]["values"][0][0] = 9999.0
    source["metadata"]["countries"].clear()
    assert coast.to_dict() == baseline

    exported = coast.to_dict()
    exported["landmasses"][0]["points"][0][0] = 0.0
    exported["airbases"].clear()
    exported["bathymetry"]["values"][0][0] = 9999.0
    exported["metadata"]["countries"].clear()
    assert coast.to_dict() == baseline

    game = Game(seed=818, start_menu=False, audio_enabled=False)
    load_input = game.save_state()
    restored = Game(seed=819, start_menu=False, audio_enabled=False)
    restored.load_state(load_input)
    loaded_baseline = restored.world.coast.to_dict()
    load_input["world"]["coast"]["landmasses"][0]["points"][0][0] = 0.0
    load_input["world"]["coast"]["bathymetry"]["values"][0][0] = 9999.0
    load_input["world"]["coast"]["metadata"]["countries"].clear()
    assert restored.world.coast.to_dict() == loaded_baseline


def _grounded_boundary_save():
    game = Game(seed=821, start_menu=False, audio_enabled=False)
    game.world = _world()
    game.flights.flights = []
    game.ship.x, game.ship.y, game.ship.course = .15, 1.0, 270.0
    game.ship.target_course = 270.0
    game.ship.last_safe_pose = (.15, 1.0, 270.0)
    game.ship.speed = game.ship.target_speed = 10.0
    game._update_navigation(100.0)
    assert game.ship.grounded
    return game, game.save_state()


@pytest.mark.parametrize("mutation", [
    lambda ship, contact: contact.update(kind="land"),
    lambda ship, contact: contact.update(normal_x=0.0, normal_y=0.0),
    lambda ship, contact: contact.update(
        kind="shallow", x_nm=ship["x"], y_nm=ship["y"],
        hull_longitudinal=0.0, hull_lateral=0.0, normal_x=1.0, normal_y=0.0),
    lambda ship, contact: contact.update(
        kind="land", x_nm=-1.0, y_nm=ship["y"], normal_x=1.0, normal_y=0.0),
])
def test_impossible_grounding_evidence_is_transactionally_rejected(mutation):
    game, valid = _grounded_boundary_save()
    malformed = copy.deepcopy(valid)
    mutation(malformed["ship"], malformed["ship"]["grounding"]["contact"])
    before = game.save_state()

    assert not game._load_save_data(malformed)
    assert game.save_state() == before


@pytest.mark.parametrize("field", DEFAULT_HULL_SPEC.to_dict())
@pytest.mark.parametrize("kind", ["near", "int", "bool"])
def test_current_hull_requires_exact_canonical_default(field, kind):
    game = Game(seed=819, start_menu=False, audio_enabled=False)
    malformed = copy.deepcopy(game.save_state())
    value = malformed["ship"]["hull"][field]
    malformed["ship"]["hull"][field] = {
        "near": value + .001,
        "int": int(value),
        "bool": True,
    }[kind]
    before = game.save_state()

    assert not game._load_save_data(malformed)
    assert game.save_state() == before


def test_physical_api_is_acoustically_separate_and_controls_are_localized():
    source = inspect.getsource(__import__("src.world.grounding", fromlist=["x"]))
    assert "sonar_path_blocked" not in source
    assert "src.sonar" not in source
    assert "ASTERN" in Translator("en").t("help.control.engine_order")
    assert "ASTERN" in Translator("de").t("help.control.engine_order")

    game = Game(seed=19, start_menu=False, audio_enabled=False)
    game.station = Station.BRIDGE
    game.ship.order_idx = 0
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    assert game.ship.astern
    game.station = Station.ENGINE
    game._joy_step(-1)
    assert not game.ship.astern and game.ship.order_idx == 0
