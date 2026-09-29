"""Unit Editor profiles take effect in custom missions: user profiles are
added to the mission's runtime catalog (and its save snapshot), and a
placed enemy torpedo runs from the start."""

import copy
import json

import pytest

from src.core import config
from src.core.game import Game
from src.core.mission_definition import default_mission, validate_mission
from src.data.catalog import CATALOG
from src.data.user_content import default_store
from src.data.user_profiles import extend_catalog, referenced_user_keys, sub_propulsion
from src.ui.unit_editor import default_unit, validate_unit


def _template(kind):
    with open(f"data/editor_templates/unit_{kind}.json", encoding="utf-8") as stream:
        return json.load(stream)


def _game(seed=901):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language="en")


def _placed(unit_id, profile, x, y, side="hostile", **extra):
    return dict({"id": unit_id, "profile": profile, "side": side,
                 "placement": {"kind": "fixed", "x": x, "y": y},
                 "course_deg": 90.0, "speed_kn": 4.0}, **extra)


def _run(game, seconds, dt=0.25):
    for _ in range(int(seconds / dt)):
        game._update_sim(dt)


@pytest.fixture
def store():
    store = default_store(config.SAVE_DIR)
    for kind in ("sub", "surface", "aircraft", "animal", "torpedo", "decoy"):
        store.save("unit", _template(kind))
    return store


def test_every_editor_template_extends_the_packaged_catalog():
    units = [_template(kind) for kind in
             ("sub", "surface", "aircraft", "animal", "torpedo", "decoy")]
    assert all(not validate_unit(unit) for unit in units)
    catalog = extend_catalog(CATALOG, units)
    assert "user.training_sub" in catalog.subs
    assert "user.training_surface" in catalog.surfaces
    assert "user.training_aircraft" in catalog.aircraft
    assert "user.training_animal" in catalog.animals
    assert "user.training_torpedo" in catalog.torpedoes
    assert "user.training_decoy" in catalog.decoys
    # The packaged catalog is untouched and the bindings stay.
    assert not any(key.startswith("user.") for key in CATALOG.subs)
    assert dict(catalog.runtime_bindings) == dict(CATALOG.runtime_bindings)
    # The user submarine gets its own copy of the template's systems with
    # the user's speeds and torpedo load.
    systems = catalog.profile_systems["user.training_sub"]
    machine = catalog.machines[systems.machine_key]
    assert (machine.cruise_speed_kn, machine.maximum_speed_kn) == (6.0, 12.0)
    assert catalog.magazines[systems.magazine_keys[0]].mission_count == 4
    assert "endurance.user.training_sub" in catalog.endurances
    # An enemy torpedo without a signature sounds like the bound one.
    assert catalog.torpedoes["user.training_torpedo"].acoustic is not None


def test_propulsion_keywords_pick_the_catalog_class():
    assert sub_propulsion("diesel-electric") == "Diesel-elektrisch"
    assert sub_propulsion("AIP (fuel cell)") == "elektrisch/AIP"
    assert sub_propulsion("Nuclear") == "elektrisch/Kernantrieb"
    assert sub_propulsion("Kernreaktor") == "elektrisch/Kernantrieb"
    nuclear = default_unit("sub", "user.boomer")
    nuclear["acoustic"]["propulsion"] = "nuclear"
    catalog = extend_catalog(CATALOG, [nuclear])
    assert catalog.subs["user.boomer"].is_nuclear
    assert "endurance.user.boomer" not in catalog.endurances


def test_referenced_keys_cover_units_and_groups():
    definition = default_mission("user.refs")
    definition["units"]["exact"] = [_placed("a", "user.b", 1, 1), _placed("c", "sub_03", 1, 1)]
    definition["units"]["random_groups"] = [{"profiles": ["user.a", "user.b"]}]
    assert referenced_user_keys(definition) == ["user.a", "user.b"]


def _definition():
    definition = default_mission("user.custom_units")
    definition["seed"] = 777
    definition["units"]["exact"] = [
        _placed("boat", "user.training_sub", 300.0, 250.0, depth_m=60.0),
        _placed("escort", "user.training_surface", 230.0, 240.0, side="friendly"),
        _placed("fish", "user.training_torpedo", 256.0, 250.0, depth_m=20.0,
                course_deg=270.0),
    ]
    definition["objective"].update(type="sink", time_limit_s=1800.0, target_ids=["boat"])
    return definition


def test_user_profiles_and_a_running_torpedo_start_and_survive_a_save(store):
    game = _game()
    definition = _definition()
    assert game.start_custom_mission(definition)
    boat = game.mission_entity("boat")
    assert boat in game.subs and boat.stype.key == "user.training_sub"
    escort = game.mission_entity("escort")
    assert escort in game.warships and escort.side == "friendly"
    fish = game.mission_entity("fish")
    assert fish in game.enemy_torpedoes and fish.profile_key == "user.training_torpedo"
    assert fish.speed_kn == 28.0 and fish.state == "RUN"
    start = (fish.x, fish.y)
    _run(game, 10.0)
    assert fish.x < start[0]                    # runs west on its course
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert any(entry["key"] == "user.training_sub"
               for entry in state["catalog_snapshot"]["entries"]["subs.json"])
    other = _game(seed=3)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.mission_units == game.mission_units
    assert "user.training_sub" in other.runtime_catalog.subs
    _run(game, 10.0)
    _run(other, 10.0)
    assert [(round(sub.x, 6), round(sub.y, 6)) for sub in other.subs] == \
        [(round(sub.x, 6), round(sub.y, 6)) for sub in game.subs]
    # A new built-in mission leaves the user profiles behind.
    other.reset(5)
    assert other.runtime_catalog is CATALOG


def test_rejections_for_user_profiles_and_torpedoes(store):
    game = _game()
    definition = _definition()
    # A torpedo is hostile only.
    bad = copy.deepcopy(definition)
    bad["units"]["exact"][2]["side"] = "neutral"
    assert not game.start_custom_mission(bad)
    # A frigate torpedo cannot be placed.
    friendly = default_unit("torpedo", "user.own_fish")
    friendly["used_by"] = "frigate"
    store.save("unit", friendly)
    bad = copy.deepcopy(definition)
    bad["units"]["exact"][2]["profile"] = "user.own_fish"
    assert not game.start_custom_mission(bad)
    # A deleted profile rejects the mission.
    store.delete("unit", "user.training_surface")
    assert not game.start_custom_mission(copy.deepcopy(definition))
    # Faster than the user profile's top speed.
    bad = copy.deepcopy(definition)
    bad["units"]["exact"] = bad["units"]["exact"][:1]
    bad["units"]["exact"][0]["speed_kn"] = 13.0
    assert not game.start_custom_mission(bad)
    bad["units"]["exact"][0]["speed_kn"] = 12.0
    assert game.start_custom_mission(bad)


def test_same_mission_with_user_profiles_is_deterministic(store):
    runs = []
    for _ in range(2):
        game = _game()
        assert game.start_custom_mission(_definition())
        _run(game, 20.0)
        runs.append([(round(sub.x, 6), round(sub.y, 6), round(sub.depth, 6)) for sub in game.subs]
                    + [(round(t.x, 6), round(t.y, 6)) for t in game.enemy_torpedoes])
    assert runs[0] == runs[1]


def test_mission_editor_validation_accepts_stored_user_units(store):
    keys = set(CATALOG.subs) | {record.key for record in store.list("unit")}
    assert not validate_mission(_definition(), keys)
