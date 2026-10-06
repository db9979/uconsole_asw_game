"""Service record and training lessons on the browser's host surface (W5):
the solo host (and the server-mode leader) reads the logbook; only the solo
host starts a lesson, crew sessions and server mode cannot."""

import time

import pytest

from src.commander import host_records
from src.commander.actions import _HOST_ACTION_HANDLERS
from src.commander.server import web_catalog
from src.commander.v2.commands import V2_ACTION_REGISTRY
from src.core import logbook, training
from src.core.i18n import load_catalog
from test_commander_solo import (game, host, host_view, host_body, pair, request,  # noqa: F401
                                 send, server, solo)


def _book():
    book = logbook.Logbook()
    for index in range(14):
        book.record(date=f"2026-10-{index + 1:02d}", side="frigate", scenario="s1_patrouille",
                    level="standard", won=index % 2 == 0, score=100 + index, minutes=30,
                    shots=1, sunk=1, earned=["first"] if index == 0 else [])
    book.record(date="2026-10-20", side="boat", scenario="custom", level="realistic",
                won=False, score=0, minutes=12, shots=0, sunk=0, earned=[], advisor=True)
    return book


def test_logbook_view_is_bounded_and_carries_both_sides():
    view = host_records.logbook_view(_book(), learns=True)
    assert set(view) == {"learns", "sides"} and set(view["sides"]) == {"frigate", "boat"}
    frigate, boat = view["sides"]["frigate"], view["sides"]["boat"]
    assert (frigate["missions"], frigate["wins"]) == (14, 7)
    assert frigate["best"] == [{"scenario": "s1_patrouille", "score": 112}]
    assert [row["award"] for row in frigate["awards"]] == list(logbook.AWARDS)
    assert frigate["awards"][0]["date"] == "2026-10-01" and frigate["awards"][1]["date"] is None
    assert len(frigate["recent"]) == host_records.LOGBOOK_RECENT_MAX
    assert frigate["recent"][0]["date"] == "2026-10-14"  # newest first
    assert boat["recent"] == [{"date": "2026-10-20", "scenario": "custom", "level": "realistic",
                               "won": False, "score": 0, "minutes": 12, "marks": ["advisor"]}]
    assert host_records.logbook_view(_book(), learns=False)["sides"]["frigate"]["known"] == []


def test_lessons_view_names_each_lessons_side():
    first = training.LESSONS[0]
    assert host_records.lessons_view() == [
        {"key": lesson, "side": training.side_of(lesson), "done": False, "next": lesson == first}
        for lesson in training.LESSONS]
    assert {"key": "boat_listen", "side": "uboot", "done": False,
            "next": False} in host_records.lessons_view()


def test_lessons_view_marks_done_and_next_lessons():
    done = training.LESSONS[:2]
    rows = host_records.lessons_view(done + ("unknown",))
    assert [row["done"] for row in rows[:3]] == [True, True, False]
    assert [row["key"] for row in rows if row["next"]] == [training.next_lesson(done)]


def test_logbook_view_carries_the_ribbon_rack():
    frigate = host_records.logbook_view(_book(), learns=True)["sides"]["frigate"]
    assert {"scenario": "s1_patrouille", "won": True} in frigate["ribbons"]
    assert all(not row["scenario"].startswith("frei_") for row in frigate["ribbons"])
    assert len(frigate["ribbons"]) == len(logbook.ribbon_scenarios("frigate"))


def test_solo_host_view_publishes_the_logbook_and_rereads_a_changed_file(solo):
    view = host_view(solo)
    assert view["lessons"] == host_records.lessons_view()
    assert view["logbook"]["sides"]["frigate"]["missions"] == 0
    assert logbook.save_logbook(_book())
    solo.bridge._slots_at = None  # the 2 s refresh, without waiting
    solo.bridge.pump(solo.game, solo.server, now=time.monotonic())
    assert host_view(solo)["logbook"]["sides"]["frigate"]["missions"] == 14


def test_solo_host_starts_a_training_lesson(solo):
    assert host(solo, "host_start_training", {"lesson": "sonar"}, "t1")["reasoncode"] == "ok"
    assert solo.game.training is not None and solo.game.training.lesson == "sonar"


@pytest.mark.parametrize("params", [{}, {"lesson": "nope"}, {"lesson": "sonar", "x": 1},
                                    {"lesson": 1}])
def test_training_params_are_strict(solo, params):
    assert V2_ACTION_REGISTRY["host_start_training"].validate_params(params) is not True
    assert send(solo, host_body(solo, "host_start_training", params, "bad"))[0] == 400


def test_server_mode_starts_lessons_from_the_lobby_only():
    class Game:
        server_mode = True

        def start_training(self, lesson):  # pragma: no cover - must not run
            raise AssertionError(lesson)
    assert _HOST_ACTION_HANDLERS["host_start_training"](Game(), {"lesson": "sonar"}) == "use_lobby"


def test_crew_sessions_cannot_start_a_lesson(server, game):  # noqa: F811
    game.commander.bridge.pump(game, server, now=time.monotonic())
    status, headers, session = pair(server)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    body = {"protocol": 2, "id": "h", "seq": 0, "station": "host",
            "station_generation": 0, "active_generation": 0, "world_session": "w",
            "world_epoch": 0, "resource_revision": 0, "action": "host_start_training",
            "params": {"lesson": "sonar"}}
    assert request(server, "/api/v2/commands", "POST", body, cookie, session["csrf"])[0] == 403
    assert getattr(game, "training", None) is None


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_browser_catalog_serves_the_game_texts_it_shows(lang):
    catalog = load_catalog(lang)
    web = web_catalog(catalog)
    for key in ("logbook.title.boat", "logbook.award.first", "logbook.award_hint.realist",
                "habit.mast_up", "level.realistic", "training.lesson.boat_evade",
                "training.lesson_note.tma", "training.boat_title", "training.menu_title"):
        assert web["commander.web.game." + key] == catalog[key]
    # Only the listed prefixes: no other game text reaches the browser this way.
    assert not any(key.startswith("commander.web.game.training.step") for key in web)
