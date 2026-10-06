"""The logbook: finished missions, best scores and awards for both sides,
in its own strictly validated file beside the save slots."""

import json
import os
import sys
from pathlib import Path

import pygame

from src.core import config
from src.core import logbook as model
from src.core.game import Game

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=7101):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def test_awards_are_the_same_for_both_sides():
    assert model.awards_for(won=False, shots=1, sunk=1, damage=0.0, fired_at=False,
                            level="realistic") == []
    assert model.awards_for(won=True, shots=1, sunk=1, damage=0.0, fired_at=False,
                            level="realistic") == list(model.AWARDS)
    assert model.awards_for(won=True, shots=3, sunk=1, damage=12.0, fired_at=True,
                            level="standard") == ["first"]


def test_boat_score_follows_outcome_damage_torpedoes_and_level():
    assert model.boat_score("lost", 0.0, 6, "standard") == 0
    assert model.boat_score("over", 0.0, 6, "standard") == 0
    base = model.boat_score("won", 0.0, 0, "standard")
    assert base == 1500 + model.BOAT_UNDAMAGED_BONUS
    assert model.boat_score("won", 50.0, 0, "standard") == base - 250
    assert model.boat_score("won", 0.0, 2, "standard") == base + 200
    assert model.boat_score("won", 0.0, 0, "realistic") == round(base * 1.25)
    assert model.boat_score("survived", 100.0, 0, "beginner") == round(600 * 0.75)


def test_record_keeps_bests_and_awards_once_and_stays_bounded():
    book = model.Logbook()
    first = book.record(date="2026-09-29", side="frigate", scenario="s1_patrouille",
                        level="standard", won=True, score=1200, minutes=40, shots=2,
                        sunk=1, earned=["first", "unscathed"])
    assert first["new_best"] and first["awards"] == ["first", "unscathed"]
    again = book.record(date="2026-09-30", side="frigate", scenario="s1_patrouille",
                        level="standard", won=True, score=900, minutes=40, shots=2,
                        sunk=1, earned=["first", "unscathed", "untouched"])
    assert not again["new_best"] and again["awards"] == ["untouched"]
    assert book.best == {"frigate:s1_patrouille": 1200}
    assert book.awards["frigate:first"] == "2026-09-29"
    # The submarine's record is its own.
    boat = book.record(date="2026-09-30", side="boat", scenario="s1_patrouille",
                       level="beginner", won=True, score=500, minutes=10, shots=4,
                       sunk=1, earned=["first"])
    assert boat["new_best"] and boat["awards"] == ["first"]
    assert book.totals("frigate") == (2, 2) and book.totals("boat") == (1, 1)
    for _ in range(model.MAX_ENTRIES + 5):
        book.record(date="2026-10-01", side="boat", scenario="custom", level="standard",
                    won=False, score=0, minutes=1, shots=0, sunk=0, earned=[])
    assert len(book.entries) == model.MAX_ENTRIES
    assert model.Logbook.valid_state(book.serialize())


def test_file_round_trip_and_hostile_files_start_a_new_book():
    book = model.Logbook()
    book.record(date="2026-09-29", side="frigate", scenario="s7_geleitzug",
                level="realistic", won=True, score=2500, minutes=90, shots=1, sunk=1,
                earned=["first", "one_shot", "realist"])
    assert model.save_logbook(book)
    loaded = model.load_logbook()
    assert loaded.serialize() == book.serialize()
    path = Path(model.logbook_path())
    good = json.loads(path.read_text(encoding="utf-8"))
    for broken in (
            dict(good, version=2),
            dict(good, extra=1),
            dict(good, best={"frigate:s1_patrouille": 1.5}),
            dict(good, best={"../x:s1": 5}),
            dict(good, awards={"frigate:medal": "2026-09-29"}),
            dict(good, entries=[dict(good["entries"][0], score=float("nan"))]),
            dict(good, entries=[dict(good["entries"][0], scenario="../etc")]),
            dict(good, entries=[dict(good["entries"][0], awards=["first", "first"])])):
        text = json.dumps(broken)
        path.write_text(text, encoding="utf-8")
        assert model.load_logbook().entries == []
    path.write_text("[1, 2", encoding="utf-8")
    assert model.load_logbook().entries == []
    path.unlink()
    target = path.with_name("elsewhere.json")
    target.write_text(json.dumps(good), encoding="utf-8")
    os.symlink(target, path)
    assert model.load_logbook().entries == []


def test_a_frigate_mission_is_filed_with_its_score():
    game = _game()
    game.score = 800
    game.damage.ship_sunk = False
    game._end_mission(True, "test")
    book = model.load_logbook()
    assert len(book.entries) == 1
    entry = book.entries[0]
    assert entry["side"] == "frigate" and entry["won"]
    assert entry["scenario"] == game.scenario_key and entry["level"] == "standard"
    assert entry["score"] == game.score > 800   # the victory bonuses count
    assert "first" in entry["awards"]
    line = str(game.logbook_end_line())
    assert str(game.score) in line and game.tr("logbook.award.first") in line


def test_lessons_are_not_filed():
    game = _game()
    game.training = object()
    game._end_mission(False, "test")
    assert model.load_logbook().entries == []
    assert game.logbook_end_line() is None


def test_the_crewed_submarine_files_its_own_side():
    game, _server, _bridge = _crewed(seed=77)
    game.local_side = "uboot"
    game._end_mission(False, "test")          # the frigate lost: the boat's time ran
    entry = model.load_logbook().entries[-1]
    assert entry["side"] == "boat"
    assert entry["level"] == game.level


def test_logbook_page_opens_switches_side_and_draws(monkeypatch):
    book = model.Logbook()
    book.record(date="2026-09-29", side="boat", scenario="s3_abfang", level="standard",
                won=True, score=1700, minutes=55, shots=2, sunk=1, earned=["first"])
    model.save_logbook(book)
    game = _game()
    game.in_menu = True
    game.main_menu = True
    game.main_menu_sel = game.main_menu_index("logbook")
    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "logbook" and not game.main_menu
    assert game.logbook_view.totals("boat") == (1, 1)
    game.logbook_side = "frigate"
    game._handle_logbook_key(pygame.K_RIGHT)
    assert game.logbook_side == "boat"
    game.draw_menu()
    game._handle_logbook_key(pygame.K_ESCAPE)
    assert game.main_menu and game.menu_screen == "scenario"
    assert game.main_menu_entries()[game.main_menu_sel] == "logbook"
    assert config.SAVE_DIR in model.logbook_path()


def test_one_ribbon_per_scenario_won_without_help():
    book = model.Logbook()
    frigate = model.ribbon_scenarios("frigate")
    assert frigate and all(not key.startswith("frei_") for key in frigate)
    assert all(config.scenario_side(key) == "frigate" for key in frigate)
    book.record(date="2026-10-02", side="frigate", scenario=frigate[0], level="standard",
                won=True, score=500, minutes=30, shots=1, sunk=1, earned=[])
    book.record(date="2026-10-02", side="frigate", scenario=frigate[1], level="standard",
                won=True, score=0, minutes=30, shots=1, sunk=1, earned=[], advisor=True)
    book.record(date="2026-10-02", side="frigate", scenario=frigate[2], level="standard",
                won=False, score=0, minutes=30, shots=1, sunk=0, earned=[])
    ribbons = dict(book.ribbons("frigate"))
    assert list(ribbons) == list(frigate)
    assert ribbons[frigate[0]] and not ribbons[frigate[1]] and not ribbons[frigate[2]]
    assert not any(won for _, won in book.ribbons("boat"))
    assert len(book.ribbons("boat")) == len(model.ribbon_scenarios("boat"))


def test_the_logbook_page_draws_the_ribbon_rack():
    from src.core import game_logbook
    assert game_logbook.ribbon_number("s7_geleitzug") == "7"
    assert game_logbook.ribbon_number("custom") == "?"
    surface = pygame.Surface((400, 40))
    rects = game_logbook.draw_ribbons(surface, [("s1_patrouille", True), ("s2_x", False)], 390, 4)
    assert len(rects) == 2 and rects[-1].right <= 390 and rects[0].right < rects[1].left
