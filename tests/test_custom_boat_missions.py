"""Custom missions sailed as the submarine (editor field ``side``): the
player's boat is the placed hostile submarine ``boat_id``, the AI hunts it,
and survive/reach/sink belong to the boat."""

import copy
import json

from src.core import boat_debrief, custom_boat
from src.core.game import Game
from src.core.i18n import Translator, localize
from src.core.mission_definition import default_mission, validate_mission


def _game(seed=903):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language="en")


def _unit(unit_id, profile, side, x, y, speed=4.0):
    return {"id": unit_id, "profile": profile, "side": side,
            "placement": {"kind": "fixed", "x": x, "y": y},
            "course_deg": 90.0, "speed_kn": speed, "depth_m": 60.0}


def _boat_mission(objective="survive", limit=60.0):
    definition = default_mission("user.boat_side")
    definition["seed"] = 777
    definition["side"] = "uboot"
    definition["boat_id"] = "own"
    definition["player"].update(x=250.0, y=250.0, speed_kn=0.0)
    definition["units"]["exact"] = [_unit("own", "diesel_alt", "hostile", 280.0, 250.0, 0.0),
                                    _unit("tanker", "tanker_01", "neutral", 290.0, 250.0, 0.0)]
    definition["objective"].update(type=objective, time_limit_s=limit,
                                   target_ids=["tanker"] if objective == "sink" else [])
    return definition


def _run(game, seconds, dt=0.25):
    for _ in range(int(seconds / dt)):
        game._update_sim(dt)


def test_side_is_optional_and_a_boat_mission_names_its_hostile_submarine():
    plain = default_mission("user.plain")
    del plain["side"], plain["boat_id"]
    assert not validate_mission(plain)
    assert not validate_mission(_boat_mission())
    missing = _boat_mission()
    missing["boat_id"] = "nobody"
    assert "required" in {problem.code for problem in validate_mission(missing)}
    friendly = _boat_mission()
    friendly["units"]["exact"][0]["side"] = "friendly"
    assert "side" in {problem.code for problem in validate_mission(friendly)}
    protect = _boat_mission()
    protect["objective"].update(type="protect", target_ids=["tanker"])
    assert any(problem.path == "objective.type" for problem in validate_mission(protect))
    bad = _boat_mission()
    bad["side"] = "helicopter"
    assert any(problem.path == "side" for problem in validate_mission(bad))


def test_a_boat_mission_binds_its_boat_and_is_won_by_holding_out():
    game = _game()
    game.local_side = "uboot"
    assert game.start_custom_mission(_boat_mission())
    boat = game.claim_opfor_sub()
    assert boat is not None and boat.sub is game.mission_entity("own")
    text = localize(custom_boat.objective(game, boat.sub), Translator("en").t)
    assert text.startswith("Stay afloat")
    _run(game, 61.0)
    # Kept from the frigate's side: the boat holding out is a frigate loss.
    assert game.mission_result == "VERLOREN"
    assert boat_debrief.outcome(game, boat) == "survived"


def test_a_boat_mission_is_lost_with_the_boat():
    game = _game()
    game.local_side = "uboot"
    assert game.start_custom_mission(_boat_mission())
    boat = game.claim_opfor_sub()
    boat.sub.sunk = True
    _run(game, 1.0)
    assert game.mission_result == "SIEG"
    assert boat_debrief.outcome(game, boat) == "lost"


def test_sink_targets_must_be_merchants_and_win_when_sunk():
    escort = _boat_mission("sink")
    escort["units"]["exact"][1]["profile"] = "warship_22"
    assert not _game().start_custom_mission(escort)
    game = _game()
    game.local_side = "uboot"
    assert game.start_custom_mission(_boat_mission("sink", 600.0))
    boat = game.claim_opfor_sub()
    assert custom_boat.targets_sunk(game) == (0, 1)
    game.mission_entity("tanker").sunk = True
    _run(game, 1.0)
    assert game.mission_result == "VERLOREN"
    assert boat_debrief.outcome(game, boat) == "objective"
    assert localize(game.result_reason, Translator("de").t) == "Das U-Boot hat alle Ziele versenkt"


def test_reach_belongs_to_the_boat_and_a_frigate_mission_is_unchanged():
    game = _game()
    game.local_side = "uboot"
    definition = _boat_mission("reach")
    definition["objective"]["reach"] = {"x": 280.5, "y": 250.0, "radius_nm": 2.0}
    assert game.start_custom_mission(definition)
    game.claim_opfor_sub()
    _run(game, 1.0)
    assert game.mission_result == "VERLOREN"
    assert localize(game.result_reason, Translator("en").t) == \
        "The submarine reached its objective point"
    frigate = _boat_mission("reach")
    frigate["side"] = "frigate"
    frigate["objective"]["reach"] = {"x": 250.5, "y": 250.0, "radius_nm": 2.0}
    frigate["objective"]["type"] = "reach"
    other = _game()
    assert other.start_custom_mission(frigate)
    _run(other, 1.0)
    assert other.mission_result == "SIEG"


def test_a_boat_objective_event_counts_for_the_boat():
    game = _game()
    game.local_side = "uboot"
    definition = _boat_mission(limit=600.0)
    definition["events"] = [{"id": "done", "at_s": 2.0, "type": "objective",
                             "action": "complete"}]
    assert game.start_custom_mission(definition)
    boat = game.claim_opfor_sub()
    _run(game, 3.0)
    assert game.mission_result == "VERLOREN"
    assert boat_debrief.outcome(game, boat) == "objective"


def test_a_boat_mission_survives_a_save_with_its_boat():
    game = _game()
    game.local_side = "uboot"
    assert game.start_custom_mission(_boat_mission(limit=600.0))
    boat = game.claim_opfor_sub()
    _run(game, 5.0)
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    other = _game(seed=1)
    assert other._load_save_data(copy.deepcopy(state))
    assert other.custom_mission_definition["side"] == "uboot"
    assert other.local_side == "uboot"
    assert other.claim_opfor_sub().sub.id == boat.sub.id
