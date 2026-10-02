"""The enemy learns the player's habits from the logbook (src/core/habits.py)
and the built-in AI picks its own plans (src/core/opfor_plans.py)."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pygame

from src.core import commander_traits, habits, opfor_plans
from src.core import logbook as model
from src.core.game import Game
from src.core.i18n import Translator, translation_scope
from src.ui.debrief_view import event_text

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=7301, scenario="s1_patrouille"):
    game = Game(seed=seed, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")
    assert game.start_new_game(scenario, "fixed", seed=seed)
    return game


def _file(side, shown, count=3):
    book = model.load_logbook()
    for _ in range(count):
        book.record(date="2026-10-02", side=side, scenario="s1_patrouille",
                    level="standard", won=False, score=0, minutes=40, shots=1, sunk=0,
                    earned=[], habits=shown)
    assert model.save_logbook(book)


def _run(game, seconds):
    for _ in range(int(seconds / 0.1)):
        game.update(0.1)


# --- what is known -------------------------------------------------------------

def test_a_habit_is_known_from_more_than_half_of_the_last_missions():
    def rows(*shown):
        return [dict(side="frigate", habits=list(item)) for item in shown]

    assert habits.known(rows(["early_ping"], ["early_ping"]), "frigate") == []   # too few
    assert habits.known(rows(["early_ping"], ["early_ping"], []), "frigate") == ["early_ping"]
    assert habits.known(rows(["early_ping"], [], []), "frigate") == []
    # Only the last WINDOW missions count; entries without habits are skipped.
    old = rows(*[["fast_search"]] * 6)
    recent = rows([], [], [], ["long_shots"], ["long_shots"])
    assert habits.known(old + recent, "frigate") == []
    assert habits.known(old + recent + [dict(side="frigate")] + rows(["long_shots"]),
                        "frigate") == ["long_shots"]
    # The other side's missions never count.
    assert habits.known(rows(["early_ping"], ["early_ping"], ["early_ping"]), "boat") == []


def test_the_logbook_keeps_only_known_habits():
    book = model.Logbook()
    entry = book.record(date="2026-10-02", side="boat", scenario="s5_durchbruch",
                        level="standard", won=True, score=900, minutes=50, shots=0,
                        sunk=0, earned=[], habits=["fast_transit", "mast_up"])["entry"]
    assert entry["habits"] == ["mast_up", "fast_transit"]
    assert model.valid_entry(entry)
    assert not model.valid_entry(dict(entry, habits=["teleport"]))
    assert not model.valid_entry(dict(entry, habits=["mast_up", "mast_up"]))
    assert model.Logbook.valid_state(book.serialize())


def test_a_mission_shows_an_early_ping():
    game = _game()
    _run(game, 20)
    assert game.send_active_ping() is True
    tracker = game.habit_tracker
    _run(game, 40)
    assert tracker.first_ping_t is not None
    shown = tracker.result("frigate", habits.MIN_MISSION_S)
    assert "early_ping" in shown
    # A short mission is not filed with habits.
    assert tracker.result("frigate", habits.MIN_MISSION_S - 1) is None


# --- the decision in a mission ---------------------------------------------------

def test_the_enemy_decides_once_from_the_logbook_and_the_save_keeps_it():
    _file("frigate", ["early_ping", "fast_search"])
    game = _game()
    assert game.enemy_habits is None
    _run(game, 2)
    assert game.enemy_habits == {"side": "frigate", "known": ["early_ping", "fast_search"]}
    assert game.enemy_known_habits("frigate") == ("early_ping", "fast_search")
    assert game.enemy_known_habits("boat") == ()
    # The logbook changing during the mission changes nothing.
    _file("frigate", [], count=5)
    _run(game, 1)
    assert game.enemy_habits["known"] == ["early_ping", "fast_search"]
    document = json.loads(json.dumps(game.save_state(), allow_nan=False))
    assert document["habits"] == {"side": "frigate", "known": ["early_ping", "fast_search"]}
    twin = Game(seed=1, start_menu=True, show_splash=False, audio_enabled=False)
    assert twin._load_save_data(document)
    assert twin.enemy_habits == game.enemy_habits
    for bad in ({"side": "frigate", "known": ["mast_up"]}, {"side": "x", "known": []},
                {"side": "frigate"}, {"side": "boat", "known": ["shallow", "shallow"]}):
        assert not twin._load_save_data(dict(document, habits=bad))


def test_switched_off_or_in_the_daily_mission_the_enemy_knows_nothing(monkeypatch):
    _file("frigate", ["early_ping"])
    game = _game()
    game.preferences = replace(game.preferences, enemy_learns=False)
    _run(game, 2)
    assert game.enemy_habits == {"side": "frigate", "known": []}
    game = _game()
    monkeypatch.setattr(type(game), "_llm_daily_running", lambda self: True)
    _run(game, 2)
    assert game.enemy_habits["known"] == []


def test_the_crewed_boat_side_is_read_for_the_hunter():
    _file("boat", ["shallow", "fast_transit"])
    game, _server, _bridge = _crewed(seed=77)
    game.local_side = "uboot"
    game.enemy_habits = None
    game.mission_time = max(game.mission_time, habits.DECIDE_AFTER_S)
    assert game.enemy_known_habits("boat") == ("shallow", "fast_transit")
    assert opfor_plans.hunter_plan(game, ("shallow", "fast_transit")) == "quiet_search"


# --- the plans ------------------------------------------------------------------

def _free_boat(game):
    return next(sub for sub in game.subs if sub.side == "hostile" and not sub.sunk)


def test_a_free_boat_plans_from_what_it_heard_and_its_character():
    game = _game()
    sub = _free_boat(game)
    kind = commander_traits.sub_kind(sub)
    assert opfor_plans.sub_plan(sub) == "default"            # hears nothing
    sub.memory["contact_bearing"] = 90.0
    sub.memory["contact_age"] = 10.0
    assert opfor_plans.sub_plan(sub) == opfor_plans.HEARD_PLAN[kind]
    sub.memory["last_ping_age"] = 30.0
    assert opfor_plans.sub_plan(sub) == opfor_plans.PINGED_PLAN[kind]
    assert opfor_plans.sub_plan(sub, ("early_ping",)) == "deep_hide"
    sub.damage = 60.0
    assert opfor_plans.sub_plan(sub) == "slip_away"


def test_known_habits_change_a_heard_boat_s_plan(monkeypatch):
    game = _game()
    sub = _free_boat(game)
    sub.memory["contact_bearing"] = 90.0
    sub.memory["contact_age"] = 10.0
    sub.memory["last_ping_age"] = float("inf")
    for kind in commander_traits.KINDS:
        monkeypatch.setattr(commander_traits, "sub_kind", lambda _sub, kind=kind: kind)
        assert opfor_plans.sub_plan(sub, ("early_ping",)) == "lie_still"
        expected = "deep_hide" if opfor_plans.HEARD_PLAN[kind] == "close_in" else (
            opfor_plans.HEARD_PLAN[kind])
        assert opfor_plans.sub_plan(sub, ("long_shots",)) == expected


def test_the_boat_s_patrol_leg_follows_its_plan():
    game = _game()
    _run(game, 2)
    sub = _free_boat(game)
    sub.memory["contact_bearing"] = 90.0
    sub.memory["contact_age"] = 10.0
    sub.memory["last_ping_age"] = 30.0
    game.enemy_habits = {"side": "frigate", "known": ["early_ping"]}
    _run(game, 0.2)
    course, speed, depth = sub.plan_orders
    thermo = game.world.thermocline_depth_m(sub.x, sub.y)
    assert speed == 3.0 and abs(depth - min(sub.stype.max_depth_m * 0.8, thermo + 40.0)) < 0.5


def test_the_hunter_search_plan_follows_its_captain_and_the_habits():
    game = _game()
    kind = commander_traits.hunter_kind(game.seed)
    plan = opfor_plans.hunter_plan(game)
    assert plan == opfor_plans.SEARCH_PLAN[kind] or (plan == "sprint_drift"
                                                     and kind == "daring")
    assert opfor_plans.hunter_plan(game, ("mast_up",)) == "sprint_drift"
    assert opfor_plans.hunter_plan(game, ("fast_transit", "mast_up")) == "quiet_search"


def test_the_plans_keep_a_game_deterministic():
    def run():
        game = _game(seed=7333, scenario="s2_doppeljagd")
        _run(game, 120)
        return ([(sub.x, sub.y, sub.depth, sub.course, sub.speed, sub.plan_orders)
                 for sub in game.subs], (game.ship.x, game.ship.y, game.ship.course))
    assert run() == run()


# --- the debrief and the logbook page -------------------------------------------

def test_the_debrief_names_the_known_habits():
    game = _game()
    _run(game, 2)
    game.enemy_habits = {"side": "frigate", "known": ["early_ping", "long_shots"]}
    game._end_mission(False, "test")
    event = next(event for event in game.frigate_debrief.events
                 if event["kind"] == "enemy_habits")
    with translation_scope(Translator("en").t):
        assert event_text(event) == ("The enemy expected your habits: early pings, "
                                     "long shots")
    with translation_scope(Translator("de").t):
        assert "frühes Pingen" in event_text(event)


def test_the_logbook_page_switches_learning_and_shows_what_is_known():
    _file("frigate", ["fast_search"])
    game = Game(seed=7302, start_menu=True, show_splash=False, audio_enabled=False,
                language="de")
    game.open_logbook()
    game.logbook_side = "frigate"
    game.draw()
    assert game.preferences.enemy_learns
    game._handle_logbook_key(pygame.K_l)
    assert not game.preferences.enemy_learns
    game.draw()
    game._handle_logbook_key(pygame.K_l)
    assert game.preferences.enemy_learns
