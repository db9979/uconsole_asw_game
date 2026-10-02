"""The optional language model inside the game: off changes nothing, on it
words radio traffic, answers the executive officer's questions, proposes
orders that run only when confirmed, writes missions through the validator
and (experimental, unscored) picks the AI side's plan."""

import copy
import dataclasses
import json
import time

from src.core import boat_ai, logbook as logbook_model
from src.core.game import Game
from src.core.mission_definition import validate_mission
from src.llm import mission_gen, opponent
from src.llm.advisor import parse_order
from tests.llm_fake import FakeLlmServer


def _game(seed=4401):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _connect(game, server, **prefs):
    game.preferences = dataclasses.replace(
        game.preferences, llm_enabled=True, llm_url=server.url, llm_model="m", **prefs)
    game.configure_llm()


def _pump(game, done, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        game.llm_tick()
        if done():
            return True
        time.sleep(0.02)
    return False


def _motion(game):
    """Everything that moves (entity ids differ between two games in one process)."""
    return ([round(v, 9) for v in (game.ship.x, game.ship.y, game.ship.course, game.ship.speed)],
            [[round(v, 9) for v in (sub.x, sub.y, sub.depth, sub.course, sub.speed)]
             for sub in game.subs],
            [[round(v, 9) for v in (ship.x, ship.y, ship.course)] for ship in game.civilians],
            game.sim_t, game.score)


def _run(game, seconds, dt=0.1):
    for _ in range(int(seconds / dt)):
        game.update(dt)


def test_off_by_default_sends_nothing_and_plays_as_before():
    game = _game()
    assert not game.llm_active()
    game.hq_msg("Test")
    assert game.advisor_ask("situation") == "llm_off"
    assert game.mission_gen.start(game.llm, "en", "frigate", "two subs", key="user.x",
                                  owner="editor") == "llm_off"
    assert game.llm_opfor_side() is None
    _run(game, 5)
    assert game.llm.sent == 0
    assert game.save_state()["llm"] == {"advisor_sides": [], "experimental": False,
                                        "opfor": None}


def test_texts_from_the_model_never_change_the_simulation():
    with FakeLlmServer("Lage ruhig.") as server:
        plain, worded = _game(4402), _game(4402)
        _connect(worded, server)
        plain.hq_msg("Contact report")
        worded.hq_msg("Contact report")
        assert worded.advisor_ask("situation") is not None
        for _ in range(40):
            plain.update(0.1)
            worded.update(0.1)
            worded.llm_tick()
        assert worded.llm.sent >= 1
        assert _motion(plain) == _motion(worded)


def test_radio_message_is_worded_beside_the_original():
    with FakeLlmServer("FROM HQ BREAK CONTACT BEARING 090 OUT") as server:
        game = _game()
        _connect(game, server)
        game.hq_msg("Contact bearing 090")
        stamp, text = game.messages[-1]
        assert _pump(game, lambda: game.llm_radio_text(stamp, text) is not None)
        assert game.llm_radio_text(stamp, text).startswith("FROM HQ")
        assert "Contact bearing 090" in server.requests[0]["messages"][1]["content"]


def test_situation_report_marks_the_side_and_survives_a_load():
    with FakeLlmServer("Two tracks, nothing urgent.") as server:
        game = _game()
        _connect(game, server)
        entry = game.advisor_ask("situation")
        assert isinstance(entry, dict)
        assert _pump(game, lambda: entry["status"] == "done")
        assert entry["answer"] == "Two tracks, nothing urgent."
        assert game.llm_advisor_used
        state = json.loads(json.dumps(game.save_state()))
        assert state["llm"]["advisor_sides"] == ["frigate"]
        other = _game(1)
        assert other._load_save_data(copy.deepcopy(state))
        assert other.llm_advisor_sides == {"frigate"}
        # The briefing alone is no help in the fight: no mark.
        fresh = _game(4403)
        _connect(fresh, server)
        assert isinstance(fresh.advisor_ask("briefing"), dict)
        assert not fresh.llm_advisor_sides


def test_typed_order_runs_only_after_confirmation_and_never_weapons():
    reply = json.dumps({"commands": [{"type": "course", "value": 120},
                                     {"type": "speed", "value": 8}],
                        "say": "Course 120, speed 8."})
    with FakeLlmServer(reply) as server:
        game = _game()
        _connect(game, server)
        before = game.ship.target_course
        entry = game.advisor_ask("order", "come to 120, eight knots")
        assert _pump(game, lambda: entry["status"] == "done")
        assert [row["type"] for row in entry["proposal"]] == ["course", "speed"]
        assert game.ship.target_course == before          # nothing given yet
        assert game.advisor_confirm(entry["seq"]) is True
        assert round(game.ship.target_course) == 120
        assert game.advisor_confirm(entry["seq"]) == "stale_ref"
    assert parse_order("frigate", {"commands": [{"type": "fire", "value": 1}]}) is None
    assert parse_order("frigate", {"commands": [{"type": "course", "value": "x"}]}) is None
    assert parse_order("uboot", {"commands": [{"type": "depth", "value": 80}]})[0]["params"] == {
        "depth_m": 80.0}


def test_logbook_marks_assisted_missions_without_best_or_awards():
    book = logbook_model.Logbook()
    plain = book.record(date="2026-10-02", side="frigate", scenario="s1", level="normal",
                        won=True, score=500, minutes=30, shots=2, sunk=1, earned=["first"])
    assert plain["new_best"]
    helped = book.record(date="2026-10-02", side="frigate", scenario="s1", level="normal",
                         won=True, score=900, minutes=30, shots=2, sunk=1,
                         earned=["first"], advisor=True)
    assert not helped["new_best"] and helped["awards"] == []
    assert helped["entry"]["advisor"] is True
    assert book.best["frigate:s1"] == 500


def _mission_reply(key_side="frigate"):
    mission = {
        "name": "Fog patrol", "description": "Two boats in fog.", "seed": 7, "side": key_side,
        "player": {"x": 250, "y": 250, "course_deg": 0, "speed_kn": 12},
        "environment": {"sea_state": 3, "time_hour": 2.0, "thermocline_depth_m": 80,
                        "weather": "fog"},
        "units": {"exact": [{"id": "sub1", "profile": "diesel_alt", "side": "hostile",
                             "placement": {"kind": "fixed", "x": 262, "y": 240},
                             "course_deg": 200, "speed_kn": 4, "depth_m": 80}],
                  "random_groups": []},
        "objective": {"type": "sink", "target_ids": [], "time_limit_s": 3600},
        "events": [],
        "world": {"kind": "reference", "reference": "/etc/passwd"},
        "unknown_field": 1,
    }
    return json.dumps(mission)


def test_mission_generator_merges_and_validates():
    profiles = mission_gen.builtin_profiles()
    assert profiles["diesel_alt"] == "sub"
    with FakeLlmServer(_mission_reply()) as server:
        game = _game()
        _connect(game, server)
        gen = game.mission_gen
        assert gen.start(game.llm, "en", "frigate", "two boats in fog", key="user.llm_test",
                         owner="test") is None
        assert gen.start(game.llm, "en", "frigate", "again", key="user.y",
                         owner="test") == "llm_busy"
        assert _pump(game, lambda: gen.status in ("done", "failed"))
        assert gen.status == "done", gen.issues
        mission = gen.mission
        assert mission["key"] == "user.llm_test" and "unknown_field" not in mission
        assert mission["world"] == {"kind": "fixed", "size_nm": 500.0, "sectors": []}
        assert mission["objective"]["target_ids"] == ["sub1"]
        assert validate_mission(mission, set(profiles)) == []


def test_mission_generator_gets_one_fix_then_gives_up():
    answers = iter(['{"name": 5}', _mission_reply()])
    with FakeLlmServer(lambda body: next(answers)) as server:
        game = _game()
        _connect(game, server)
        gen = game.mission_gen
        assert gen.start(game.llm, "de", "frigate", "U-Boot im Nebel", key="user.llm_fix",
                         owner="test") is None
        assert _pump(game, lambda: gen.status in ("done", "failed"))
        assert gen.status == "done" and len(server.requests) == 2
        assert "rejected by the validator" in server.requests[1]["messages"][-1]["content"]
    with FakeLlmServer("no json at all") as server:
        game = _game()
        _connect(game, server)
        gen = game.mission_gen
        gen.start(game.llm, "en", "uboot", "a raid", key="user.llm_bad", owner="test")
        assert _pump(game, lambda: gen.status in ("done", "failed"))
        assert gen.status == "failed" and gen.error == "bad_reply" and gen.mission is None


def test_experimental_opponent_picks_a_plan_marks_the_mission_and_is_saved():
    with FakeLlmServer('{"plan": "deep_hide", "why": "hide"}') as server:
        game = _game(4404)
        _connect(game, server, llm_opfor=True)
        assert game.llm_opfor_side() == "subs"
        assert _pump(game, lambda: game.llm_opfor is not None)
        assert game.llm_opfor["plan"] == "deep_hide" and game.llm_experimental
        boat_ai.steer(game)
        hostile = [sub for sub in game.subs if sub.side == "hostile" and not sub.sunk]
        assert hostile and all(sub.llm_orders is not None and sub.llm_orders[1] == 3.0
                               for sub in hostile)
        state = json.loads(json.dumps(game.save_state()))
        other = _game(1)
        assert other._load_save_data(copy.deepcopy(state))
        assert other.llm_opfor == game.llm_opfor and other.llm_experimental
        bad = copy.deepcopy(state)
        bad["llm"]["opfor"]["plan"] = "fire_everything"
        assert not _game(1)._load_save_data(bad)
    assert opponent.parse("subs", '{"plan": "nuke"}') is None
    assert opponent.parse("hunter", '{"plan": "sprint_drift"}')[0] == "sprint_drift"


def test_experimental_opponent_never_runs_in_campaign_or_lessons():
    with FakeLlmServer('{"plan": "deep_hide"}') as server:
        game = _game()
        _connect(game, server, llm_opfor=True)
        game.campaign_mission = True
        assert game.llm_opfor_side() is None
        game.campaign_mission = False
        game.preferences = dataclasses.replace(game.preferences, llm_opfor=False)
        assert game.llm_opfor_side() is None
