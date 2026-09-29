"""Mission runtime = editor scope (plan 1.3, phase 13): reference worlds,
protect/reach objectives, random groups and events, placed aircraft,
animals and decoys.  Other world sizes stay rejected; user unit profiles
and placed torpedoes are covered by tests/test_user_profiles_runtime.py."""

import copy
import json

import pytest

from src.core import config
from src.core.game import Game
from src.core.mission_definition import (default_mission, reference_sector_index,
                                         validate_mission)


def _game(seed=901):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language="en")


def _sub(unit_id="target", x=300.0, y=250.0, side="hostile", profile="sub_03"):
    return {"id": unit_id, "profile": profile, "side": side,
            "placement": {"kind": "fixed", "x": x, "y": y},
            "course_deg": 90.0, "speed_kn": 4.0, "depth_m": 60.0}


def _definition(key="user.runtime", objective="sink", **world):
    definition = default_mission(key)
    definition["seed"] = 4242
    definition["units"]["exact"] = [_sub()]
    definition["objective"].update(type=objective, time_limit_s=1800.0,
                                   target_ids=["target"] if objective == "sink" else [])
    definition["world"].update(world)
    return definition


def _run(game, seconds, dt=0.25):
    for _ in range(int(seconds / dt)):
        game._update_sim(dt)


def _poses(game):
    return [(round(game.ship.x, 6), round(game.ship.y, 6), round(game.ship.course, 6))] + [
        (round(sub.x, 6), round(sub.y, 6), round(sub.depth, 6)) for sub in game.subs]


# --- step 1: reference worlds ------------------------------------------------

def test_reference_sector_names_are_strict():
    assert reference_sector_index("sector:0") == 0
    assert reference_sector_index("sector:127") == 127
    for bad in ("sector:128", "sector:-1", "sector:01", "sector:", "north_sea", "sector:12a", 7):
        assert reference_sector_index(bad) is None
    definition = _definition(kind="reference", reference="north_sea")
    assert "reference" in {problem.code for problem in validate_mission(definition)}
    assert not validate_mission(_definition(kind="reference", reference="sector:5"))


def test_reference_world_starts_on_its_packaged_sector_and_survives_a_save(tmp_path):
    game = _game()
    definition = _definition(kind="reference", reference="sector:17")
    assert game.start_custom_mission(definition)
    assert game.world_mode == "real_fixed"
    assert game.world.coast.metadata["sector_id"] == "real-017"
    assert game.world.size_nm == config.WORLD_SIZE_NM
    _run(game, 5.0)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["world"]["mode"] == "real_fixed"
    other = _game(seed=1)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.world.coast.metadata["sector_id"] == "real-017"
    assert other.custom_mission_definition["world"]["reference"] == "sector:17"
    assert _poses(other) == _poses(game)


def test_reference_world_rejections_stay():
    game = _game()
    for world in ({"kind": "reference", "reference": "sector:999"},
                  {"kind": "reference", "reference": "sector:3", "size_nm": 300.0},
                  {"kind": "fixed", "size_nm": 250.0}):
        assert not game.start_custom_mission(_definition(**world))
    profile = _definition()
    profile["units"]["exact"][0]["profile"] = "user.my_boat"
    assert not game.start_custom_mission(profile)


def test_two_reference_world_runs_are_identical():
    runs = []
    for _ in range(2):
        game = _game()
        assert game.start_custom_mission(_definition(kind="reference", reference="sector:40"))
        _run(game, 30.0)
        runs.append((_poses(game), game.world.coast.metadata["sector_id"],
                     round(game.world.weather_values()["wind_speed_kn"], 6)))
    assert runs[0] == runs[1]


# --- step 2: protect and reach --------------------------------------------------

def _civilian(unit_id="tanker", x=260.0, y=250.0, side="neutral"):
    return {"id": unit_id, "profile": "civ_01", "side": side,
            "placement": {"kind": "fixed", "x": x, "y": y}, "course_deg": 0.0, "speed_kn": 0.0}


def test_reach_objective_needs_its_point_and_protect_its_units():
    game = _game()
    reach = _definition(objective="reach")
    del reach["objective"]["reach"]
    assert {problem.code for problem in validate_mission(reach)} >= {"required"}
    assert not game.start_custom_mission(reach)
    reach["objective"]["reach"] = {"x": 250.0, "y": 250.0, "radius_nm": 60.0}
    assert validate_mission(reach)
    protect = _definition(objective="protect")
    assert "required" in {problem.code for problem in validate_mission(protect)}
    protect["objective"]["target_ids"] = ["target"]           # a hostile boat: refused
    assert not validate_mission(protect) and not game.start_custom_mission(protect)


def test_protect_is_lost_with_the_unit_and_won_at_the_time_limit(tmp_path):
    civ_key = next(iter(_game().runtime_catalog.surfaces))
    for outcome in ("lost", "won"):
        game = _game()
        definition = _definition(objective="protect")
        definition["units"]["exact"].append(dict(_civilian(), profile=civ_key))
        definition["objective"]["target_ids"] = ["tanker"]
        definition["objective"]["time_limit_s"] = 60.0
        assert game.start_custom_mission(definition), validate_mission(definition)
        assert game.mission.win_mode == "protect"
        assert set(game.mission_units) == {"target", "tanker"}
        tanker = game.mission_entity("tanker")
        assert tanker is not None and tanker in game.civilians + game.warships
        # The bookkeeping survives a save; the objective text names the mode.
        state = json.loads(json.dumps(game.save_state(), allow_nan=False))
        assert state["mission_runtime"]["units"] == game.mission_units
        other = _game(seed=2)
        assert other._load_save_data(copy.deepcopy(state))
        assert other.mission_units == game.mission_units
        assert other.mission_entity("tanker") is not None
        from src.core.i18n import Translator, localize
        assert "Protect" in localize(game.mission_objective_display(), Translator("en").t)
        if outcome == "lost":
            tanker.sunk = True
            _run(game, 1.0)
            assert game.mission_result == "VERLOREN"
            assert localize(game.result_reason, Translator("en").t) == "Protected unit tanker was lost"
        else:
            _run(game, 61.0)
            assert game.mission_result == "SIEG"
            assert localize(game.result_reason, Translator("de").t).startswith("Die geschützten")


def test_reach_is_won_at_the_point_and_lost_at_the_deadline():
    for outcome in ("won", "lost"):
        game = _game()
        definition = _definition(objective="reach")
        definition["objective"]["time_limit_s"] = 30.0
        definition["player"].update(x=250.0, y=250.0, speed_kn=0.0)
        point = {"x": 251.0, "y": 250.0, "radius_nm": 2.0} if outcome == "won" else \
            {"x": 400.0, "y": 400.0, "radius_nm": 2.0}
        definition["objective"]["reach"] = point
        assert game.start_custom_mission(definition), validate_mission(definition)
        _run(game, 31.0)
        assert game.mission_result == ("SIEG" if outcome == "won" else "VERLOREN")
        from src.core.i18n import Translator, localize
        reason = localize(game.result_reason, Translator("en").t)
        assert reason == ("Objective point reached" if outcome == "won" else "Time limit exceeded")


# --- step 3: random groups, events, weather -----------------------------------

def _events_definition():
    definition = _definition(objective="survive")
    definition["objective"]["time_limit_s"] = 600.0
    definition["world"]["sectors"] = [
        {"id": "east", "x": 300.0, "y": 200.0, "width": 60.0, "height": 60.0}]
    definition["units"]["random_groups"] = [
        {"id": "pack", "profiles": ["sub_03"], "count": [2, 2], "side": "hostile",
         "placement": {"kind": "sector", "sector": "east"}},
        {"id": "late", "profiles": ["sub_03"], "count": [1, 1], "side": "hostile",
         "placement": {"kind": "sector", "sector": "east"}},
    ]
    definition["events"] = [
        {"id": "brief", "at_s": 0.0, "type": "message", "message": "Patrol {the} east."},
        {"id": "squall", "at_s": 10.0, "type": "weather", "weather": "storm"},
        {"id": "reinforce", "at_s": 20.0, "type": "spawn", "target_id": "late"},
        {"id": "done", "at_s": 40.0, "type": "objective", "action": "complete",
         "message": "Area secured"},
    ]
    return definition


def test_authored_weather_is_held_and_saved():
    game = _game()
    definition = _definition(objective="survive")
    definition["environment"]["weather"] = "fog"
    assert game.start_custom_mission(definition)
    assert game.world.weather_override == "fog" and game.world.weather_kind() == "fog"
    values = game.world.weather_values()
    assert values["visibility_nm"] == 1.0 and values["sea_state"] == definition["environment"]["sea_state"]
    _run(game, 5.0)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["world"]["weather_override"] == "fog"
    other = _game(seed=3)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.world.weather_kind() == "fog"
    other.world.set_weather_override("clear")
    assert other.world.weather_override is None
    with pytest.raises(ValueError):
        other.world.set_weather_override("hail")
    bad = copy.deepcopy(state)
    bad["world"]["weather_override"] = "hail"
    assert not _game(seed=4)._load_save_data(bad)


def test_random_groups_and_events_run_in_order_and_survive_a_save():
    game = _game()
    definition = _events_definition()
    assert not validate_mission(definition), validate_mission(definition)
    assert game.start_custom_mission(definition)
    # The exact boat and the two-boat pack are placed; the late group waits.
    assert len(game.subs) == 3 and set(game.mission_units) == {"target", "pack:1", "pack:2"}
    assert all(sub.side == "hostile" for sub in game.subs)
    assert game.mission_events_pending == ["brief", "squall", "reinforce", "done"]
    _run(game, 1.0)
    assert game.mission_events_pending == ["squall", "reinforce", "done"]
    from src.core.i18n import Translator, localize
    texts = [localize(entry.text, Translator("de").t) for entry in game.feed.entries
             if entry.category == "mission"]
    assert "Patrol {the} east." in texts                     # verbatim, never formatted
    assert game.world.weather_kind() != "storm"
    # Save mid-way: pending ids round-trip, unknown ids are rejected.
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert state["mission_events"] == ["squall", "reinforce", "done"]
    bad = copy.deepcopy(state)
    bad["mission_events"] = ["squall", "ghost"]
    assert not _game(seed=5)._load_save_data(bad)
    other = _game(seed=6)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.mission_events_pending == ["squall", "reinforce", "done"]
    for candidate in (game, other):
        _run(candidate, 21.0)
        assert candidate.world.weather_kind() == "storm"
        assert len(candidate.subs) == 4 and "late:1" in candidate.mission_units
        assert candidate.mission_result is None
        _run(candidate, 20.0)
        assert candidate.mission_result == "SIEG"
        assert localize(candidate.result_reason, Translator("en").t) == "Area secured"
    assert _poses(game) == _poses(other)


def test_group_placement_is_seeded_and_bounded_to_its_sector():
    runs = []
    for _ in range(2):
        game = _game()
        definition = _events_definition()
        definition["events"] = []
        assert game.start_custom_mission(definition)
        runs.append(sorted((round(sub.x, 6), round(sub.y, 6), round(sub.course, 3))
                           for sub in game.subs))
    assert runs[0] == runs[1] and len(runs[0]) == 4
    for x, y, _course in runs[0][1:]:
        assert 290.0 <= x <= 370.0 and 190.0 <= y <= 270.0     # sector plus nearest water


# --- step 4: aircraft, animals and decoys -------------------------------------

def _placed(unit_id, profile, x, y, side="neutral", **extra):
    return dict({"id": unit_id, "profile": profile, "side": side,
                 "placement": {"kind": "fixed", "x": x, "y": y},
                 "course_deg": 45.0, "speed_kn": 0.0}, **extra)


def test_aircraft_animals_and_decoys_are_placed_and_saved():
    game = _game()
    catalog = game.runtime_catalog
    aircraft = next(key for key, profile in catalog.aircraft.items() if profile.kind == "military")
    animal = next(iter(catalog.animals))
    decoy = next(iter(catalog.decoys))
    definition = _definition(objective="survive")
    definition["units"]["exact"] += [
        _placed("patrol", aircraft, 200.0, 200.0, side="hostile", speed_kn=180.0),
        _placed("whale", animal, 230.0, 260.0, depth_m=40.0, speed_kn=3.0),
        _placed("lure", decoy, 240.0, 240.0, depth_m=50.0, speed_kn=2.0),
    ]
    assert not validate_mission(definition), validate_mission(definition)
    assert game.start_custom_mission(definition)
    assert set(game.mission_units) == {"target", "patrol", "whale", "lure"}
    flight = game.mission_entity("patrol")
    assert flight in game.flights.flights and flight.akey == aircraft and flight.side == "hostile"
    assert (round(flight.x), round(flight.y)) == (200, 200)
    assert flight.speed == catalog.aircraft[aircraft].speed_kn     # profile speed, not 180
    assert flight.base_id in {base["id"] for base in game.world.coast.airbases}
    whale = game.mission_entity("whale")
    assert whale in game.animals and whale.depth == 40.0 and whale.speed == 3.0
    lure = game.mission_entity("lure")
    assert lure in game.decoys and lure.depth == 50.0 and lure.speed == 0.0 and lure.source_id is None
    _run(game, 10.0)
    assert flight.active and not whale.dead and not lure.dead
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    other = _game(seed=7)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.mission_units == game.mission_units
    restored = other.mission_entity("patrol")
    assert restored is not None and restored.akey == aircraft and restored.waypoints == flight.waypoints
    assert other.mission_entity("whale") is not None and other.mission_entity("lure") is not None
    _run(game, 10.0)
    _run(other, 10.0)
    assert (round(other.mission_entity("patrol").x, 6), round(other.mission_entity("patrol").y, 6)) == \
        (round(flight.x, 6), round(flight.y, 6))


def test_friendly_torpedoes_and_missing_user_profiles_stay_rejected():
    game = _game()
    torpedo = next(key for key, profile in game.runtime_catalog.torpedoes.items()
                   if profile.used_by == "frigate")
    definition = _definition(objective="survive")
    definition["units"]["exact"].append(_placed("fish", torpedo, 220.0, 220.0, depth_m=20.0))
    assert not game.start_custom_mission(definition)
    definition["units"]["exact"][-1]["profile"] = "user.stealth_boat"
    assert validate_mission(definition, {"sub_03"}) and not game.start_custom_mission(definition)
