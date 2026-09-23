"""Phase 10: flooding physics, stability, fire, repair logistics."""

import copy
import json
import random

import pytest

from src.core import config
from src.core.game import Game
from src.ship import damage as dmg
from src.ship.damage import DamageModel


def _model(seed=1):
    return DamageModel(random.Random(seed))


def test_orifice_inflow_slows_as_levels_equalize_and_high_rooms_stay_dry():
    model = _model()
    hull = model.compartments["hull_left"]
    hull.state, hull.hole_m2 = "FLUTEND", dmg.HIT_HOLE_M2
    first = model.compartment_trend("hull_left")["flood_rate"]
    hull.flood = 60.0
    later = model.compartment_trend("hull_left")["flood_rate"]
    assert first > later > 0.0
    bridge = model.compartments["bridge"]
    bridge.state, bridge.hole_m2 = "FLUTEND", dmg.HIT_HOLE_M2
    assert model.compartment_trend("bridge")["flood_rate"] == 0.0


def test_patching_consumes_a_kit_and_leaves_a_small_leak():
    model = _model()
    room = model.compartments["engine"]
    room.state, room.hole_m2, room.flood = "FLUTEND", dmg.HIT_HOLE_M2, 20.0
    model.assign_team(1, "engine")
    model.team_eta[1] = 0.0
    model.update(0.1)
    assert model.patch_kits == dmg.PATCH_KITS - 1
    assert room.state == "BESCHAEDIGT"
    assert room.hole_m2 == pytest.approx(dmg.HIT_HOLE_M2 * dmg.PATCH_LEAK_FRACTION)
    empty = _model()
    empty.patch_kits = 0
    other = empty.compartments["engine"]
    other.state, other.hole_m2, other.flood = "FLUTEND", dmg.HIT_HOLE_M2, 20.0
    empty.assign_team(1, "engine")
    empty.team_eta[1] = 0.0
    empty.update(0.1)
    assert other.state == "FLUTEND" and other.hole_m2 == dmg.HIT_HOLE_M2


def test_impact_point_selects_the_compartment():
    assert "engine" in _model().torpedo_hit(impact=(-0.45, 0.0))
    assert "sonar" in _model().torpedo_hit(impact=(0.85, 0.0))
    assert "hull_right" in _model().torpedo_hit(impact=(0.0, 0.9))
    missile = _model()
    keys = missile.missile_hit(0.7, 0.0)
    room = missile.compartments[keys[0]]
    assert room.fire >= 40.0 and room.hole_m2 == 0.0


def test_reserve_buoyancy_and_capsize_decide_sinking():
    sinking = _model()
    for room in sinking.compartments.values():
        room.flood = 65.0
    sinking.update(0.0)
    assert sinking.ship_sunk
    capsize = _model()
    for key in ("engine", "weapons", "flightdeck", "opz", "sonar"):
        capsize.compartments[key].flood = 50.0
    assert capsize.gm_effective_m() < dmg.GM_M
    capsize.update(0.0)
    assert capsize.capsized == (capsize.gm_effective_m() <= dmg.CAPSIZE_GM_M)


def test_fire_spreads_through_hot_bulkheads_and_water_cools_it():
    model = _model()
    engine = model.compartments["engine"]
    engine.fire, engine.state = 70.0, "BESCHAEDIGT"
    for _ in range(40):
        model.update(1.0)
    assert any(model.compartments[key].fire > 0.0
               for key in dmg.COMPARTMENT_ADJACENCY["engine"])
    wet = _model()
    room = wet.compartments["engine"]
    room.fire, room.flood, room.state = 30.0, 55.0, "BESCHAEDIGT"
    assert wet.compartment_trend("engine")["fire_rate"] < 0.0


def test_flooded_switchboard_starts_a_fire_and_the_magazine_can_cook_off():
    model = _model()
    radio = model.compartments["radio"]
    radio.flood, radio.state = dmg.ELECTRICAL_SHORT_FLOOD + 1.0, "BESCHAEDIGT"
    model.update(0.1)
    assert radio.shorted and radio.fire > 0.0
    magazine = _model()
    weapons = magazine.compartments["weapons"]
    weapons.fire, weapons.state = dmg.COOK_OFF_FIRE + 1.0, "BESCHAEDIGT"
    magazine.update(0.1)
    assert magazine.cooked_off and weapons.state == "ZERSTOERT"
    assert all(magazine.compartments[key].hole_m2 > 0.0
               for key in dmg.COMPARTMENT_ADJACENCY["weapons"]
               if magazine.compartments[key].state != "ZERSTOERT")


def test_capability_is_continuous():
    model = _model()
    room = model.compartments["sonar"]
    assert model.capability("sonar") == 1.0
    room.flood, room.state = 35.0, "BESCHAEDIGT"
    assert 0.0 < model.capability("sonar") < 1.0
    room.state = "ZERSTOERT"
    assert model.capability("sonar") == 0.0


def test_hostile_hulls_flood_progressively_and_lose_systems():
    from src.enemies.surface import NPC_RADAR_LOST_DAMAGE, SurfaceShip
    ship = SurfaceShip(100.0, 100.0, random.Random(1),
                       profile=None, side="hostile", doctrine="surface_combatant")
    ship.emitter = True
    ship.damage = 50.0
    ship._progressive_flooding(600.0)
    assert ship.damage > 50.0
    ship.damage = NPC_RADAR_LOST_DAMAGE
    assert not ship.radar_emitting


def test_damage_state_round_trips_and_is_validated():
    game = Game(seed=1010, start_menu=False, audio_enabled=False)
    room = game.damage.compartments["engine"]
    room.state, room.flood, room.hole_m2, room.heat_s = "FLUTEND", 22.0, 0.02, 5.0
    game.damage.assign_team(2, "engine")
    game.damage.patch_kits = 5
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    twin = restored.damage
    assert twin.team_eta == game.damage.team_eta and twin.patch_kits == 5
    assert twin.compartments["engine"].hole_m2 == 0.02
    for mutation in (lambda d: d.update(patch_kits=99),
                     lambda d: d["compartments"]["engine"].update(hole_m2=-1.0),
                     lambda d: d["team_eta"].update({"1": -5.0})):
        broken = copy.deepcopy(state)
        mutation(broken["damage"])
        assert not restored._load_save_data(broken)
