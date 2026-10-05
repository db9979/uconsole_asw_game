"""The daily mission: one fixed mission per side and day, its page and its best."""

import datetime

import pygame

from src.core import config, daily
from src.core import logbook as model
from src.core.game import Game

DAY = datetime.date(2026, 10, 2)


def test_the_day_fixes_scenario_and_seed_per_side():
    for side in ("frigate", "uboot"):
        pool = daily.scenarios(side)
        assert pool and all(config.SCENARIOS[key]["difficulty"] is not None for key in pool)
        assert all(not key.startswith("frei_") for key in pool)
        assert daily.scenario_for(DAY, side) in pool
        assert daily.scenario_for(DAY, side) == daily.scenario_for(DAY, side)
        assert 1 <= daily.seed_for(DAY, side) < 1_000_000_000
    assert daily.seed_for(DAY, "frigate") != daily.seed_for(DAY, "uboot")
    days = [DAY + datetime.timedelta(days=n) for n in range(30)]
    assert len({daily.seed_for(day, "frigate") for day in days}) == 30
    assert len({daily.scenario_for(day, "uboot") for day in days}) > 3


def test_a_mission_is_matched_today_or_after_midnight_only():
    seed, scenario = daily.seed_for(DAY, "frigate"), daily.scenario_for(DAY, "frigate")
    assert daily.match(seed, scenario, "frigate", DAY) == DAY
    assert daily.match(seed, scenario, "frigate", DAY + datetime.timedelta(days=1)) == DAY
    assert daily.match(seed, scenario, "frigate", DAY + datetime.timedelta(days=2)) is None
    assert daily.match(seed + 1, scenario, "frigate", DAY) is None
    assert daily.match(seed, scenario, "uboot", DAY) is None
    assert daily.best_key(DAY) == "daily_20261002" and daily.is_daily_key("daily_20261002")


def test_the_logbook_keeps_the_best_of_the_newest_days():
    book = model.Logbook()
    assert book.record_daily("frigate", "daily_20261001", True, 900, 3)
    assert not book.record_daily("frigate", "daily_20261001", True, 800, 3)
    assert not book.record_daily("frigate", "daily_20261001", False, 2000, 3)
    assert book.record_daily("frigate", "daily_20261001", True, 1200, 3)
    for day in range(2, 6):
        book.record_daily("frigate", f"daily_2026100{day}", True, 100, 3)
    book.record_daily("boat", "daily_20261001", True, 50, 3)
    assert sorted(key for key in book.best if key.startswith("frigate:")) == [
        "frigate:daily_20261003", "frigate:daily_20261004", "frigate:daily_20261005"]
    assert book.best["boat:daily_20261001"] == 50
    assert model.Logbook.valid_state(book.serialize())


def test_the_page_starts_the_days_mission_and_files_its_best(monkeypatch):
    monkeypatch.setattr(daily, "today", lambda: DAY)
    game = Game(seed=5, start_menu=True, audio_enabled=False, language="en")
    game.main_menu_sel = game.main_menu_index("daily")
    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "daily" and not game.main_menu
    game.draw_menu()
    game._handle_daily_key(pygame.K_ESCAPE)
    assert game.main_menu and game.main_menu_entries()[game.main_menu_sel] == "daily"
    game.open_daily()
    game._handle_daily_key(pygame.K_RETURN)
    assert not game.in_menu
    assert game.scenario_key == daily.scenario_for(DAY, "frigate")
    assert game.seed == daily.seed_for(DAY, "frigate")
    assert game.world_mode == daily.WORLD_MODE
    game.score = 700
    game._end_mission(True, "test")
    assert game.logbook_result["daily_best"]
    assert model.load_logbook().best["frigate:" + daily.best_key(DAY)] > 0
    assert game.tr("logbook.end.daily_best") in str(game.logbook_end_line())
    # The logbook page still draws with a daily best beside the scenario bests.
    game.in_menu = True
    game.open_logbook()
    game.logbook_side = "frigate"
    game.draw_menu()


def test_the_daily_mission_hands_back_the_players_world_choice(monkeypatch):
    monkeypatch.setattr(daily, "today", lambda: DAY)
    game = Game(seed=5, start_menu=True, audio_enabled=False, language="en")
    game.world_mode = "fixed" if daily.WORLD_MODE != "fixed" else "procedural"
    chosen = game.world_mode
    game.start_weather, game.start_length = "storm", "short"
    game.start_daily("frigate")
    assert game.world_mode == daily.WORLD_MODE and game.start_length == "normal"
    game._return_to_main_menu()
    assert game.world_mode == chosen
    assert (game.start_weather, game.start_length) == ("storm", "short")
    # A later normal return leaves the choice alone.
    game.world_mode = "real_fixed"
    game._return_to_main_menu()
    assert game.world_mode == "real_fixed"


def test_another_seed_is_no_daily_mission(monkeypatch):
    monkeypatch.setattr(daily, "today", lambda: DAY)
    game = Game(seed=5, start_menu=False, audio_enabled=False, language="en")
    game.scenario_key = daily.scenario_for(DAY, "frigate")
    game.score = 700
    game._end_mission(True, "test")
    assert not game.logbook_result["daily_best"]
