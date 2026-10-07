"""Orders by voice (Dominik 2026-10-07: "es werden keine Befehle vom Spieler in
die Tat umgesetzt ... im Multiplayer keine Befehle annehmen").

What the talk key heard goes to the language model, which turns an order into
the fixed order set (carried out at once) and answers anything else as a
question.  A fixed word list no longer decides, so orders with spoken numbers
("Kurs neunzig") or new wording are carried out.  While other people crew the
stations the executive officer takes no orders, typed or spoken."""

import json
import types

import numpy as np
import pytest

from src.commander import server as transport
from src.commander.server import CommanderServer
from src.core.station import Station
from src.llm import advisor as advisor_model, prompts
from tests.llm_fake import FakeLlmServer
from tests.stt_fake import FakeSttServer
from tests.test_talk import _connect, _game, _pump, _say, clock  # noqa: F401


def _reply(commands=(), **extra):
    return json.dumps(dict(commands=[dict(type=kind, value=value)
                                     for kind, value in commands], **extra))


@pytest.mark.parametrize("phrase,commands,check", [
    ("Kurs neunzig.", [("course", 90)], lambda g: g.ship.target_course == 90),
    ("Neuer Kurs null neun null", [("course", 90)], lambda g: g.ship.target_course == 90),
    ("Fahrt 15", [("speed", 15)], lambda g: g.ship.target_speed == 15),
    ("Fahrt zehn Knoten", [("speed", 10)], lambda g: g.ship.target_speed == 10),
    ("Wende auf 180 Grad", [("course", 180)], lambda g: g.ship.target_course == 180),
    ("Maschinen stopp, Gefechtsstationen", [("speed", 0), ("action_stations", True)],
     lambda g: g.ship.target_speed == 0),
])
def test_orders_the_word_list_missed_are_carried_out(clock, phrase, commands, check):
    with FakeLlmServer(_reply(commands, say="Aye.")) as llm, FakeSttServer(phrase) as speech:
        game = _game()
        _connect(game, llm, speech)
        game.station = Station.SONAR
        entry = _say(game, clock)
        assert check(game), entry
        assert entry["kind"] == "order" and entry["applied"]
        assert entry["answer"].startswith(game.tr("advisor.spoken.done", orders="")[:6])
        # The spoken prompt asks for JSON and allows a question at the same time.
        assert llm.requests[0]["response_format"]["type"] == "json_object"
        system = llm.requests[0]["messages"][0]["content"]
        assert "speech recognition" in system and '"answer"' in system
        assert phrase in llm.requests[0]["messages"][1]["content"]


def test_a_spoken_question_is_answered_and_changes_nothing(clock):
    reply = _reply(answer="Der Kontakt peilt 045.")
    with FakeLlmServer(reply) as llm, FakeSttServer("Lagebericht zu K1 bitte") as speech:
        game = _game()
        _connect(game, llm, speech)
        speed, course = game.ship.target_speed, game.ship.target_course
        entry = _say(game, clock)
        assert entry["kind"] == "question" and entry["answer"] == "Der Kontakt peilt 045."
        assert (game.ship.target_speed, game.ship.target_course) == (speed, course)


def test_a_plain_question_goes_straight_to_the_question_prompt(clock):
    with FakeLlmServer("Etwa 18 Knoten.") as llm, \
            FakeSttServer("Wie schnell ist der Kontakt?") as speech:
        game = _game()
        _connect(game, llm, speech)
        entry = _say(game, clock)
        assert entry["kind"] == "question" and entry["answer"] == "Etwa 18 Knoten."
        assert "response_format" not in llm.requests[0]


def test_a_weapon_order_is_refused_with_a_fixed_text(clock):
    with FakeLlmServer(_reply(refused=True)) as llm, FakeSttServer("Rohr eins los.") as speech:
        game = _game()
        _connect(game, llm, speech)
        entry = _say(game, clock)
        assert entry["answer"] == game.tr("advisor.spoken.not_possible")
        assert "Weapons can never be ordered" in llm.requests[0]["messages"][0]["content"]


def test_a_confirming_reply_without_commands_is_never_read_back(clock):
    """The model must not answer an order with 'aye, 30 knots' while nothing
    happens: a reply with neither commands nor an answer is not understood."""
    with FakeLlmServer(_reply(say="Dreißig Knoten, aye!")) as llm, \
            FakeSttServer("Volle Fahrt voraus.") as speech:
        game = _game()
        _connect(game, llm, speech)
        speed = game.ship.target_speed
        entry = _say(game, clock)
        assert entry["answer"] == game.tr("advisor.spoken.not_understood")
        assert game.ship.target_speed == speed


def test_new_frigate_orders_go_through_the_station_handlers(clock):
    commands = [("radar", False), ("ping", True), ("clear_baffles", True)]
    with FakeLlmServer(_reply(commands, say="ok")) as llm, \
            FakeSttServer("Radar aus, ein Ping und Baffles freifahren") as speech:
        game = _game()
        _connect(game, llm, speech)
        called = []
        game.set_opz_radar = lambda domain, enabled: called.append((domain, enabled)) or True
        entry = _say(game, clock)
        assert ("surface", False) in called
        assert game.tr("advisor.command.radar", value=game.tr("common.off")) in entry["answer"]
        assert game.tr("advisor.command.ping") in entry["answer"]


def test_new_boat_orders_reach_the_boat(clock):
    from tests.test_opfor_sub import _game as boat_game

    with FakeLlmServer(_reply([("mast", True)], say="ok")) as llm, \
            FakeSttServer("Mast ausfahren") as speech:
        game = boat_game()
        _connect(game, llm, speech)
        game.local_side = "uboot"
        game._update(0.05)
        seen = []
        game.opfor.sub.command_mast = lambda on: seen.append(on) or True
        entry = _say(game, clock)
        assert seen == [True] and entry["applied"]
        system = llm.requests[0]["messages"][0]["content"]
        assert "Depths now:" in system and "periscope" in system


def test_parse_order_takes_the_new_types_and_still_never_weapons():
    assert advisor_model.parse_order("frigate", {"commands": [{"type": "ping", "value": True}]}) \
        == [dict(type="ping", value=True, action="sonar_active_ping", params={})]
    assert advisor_model.parse_order(
        "frigate", {"commands": [{"type": "radar", "value": "on"}]})[0]["params"] == {
            "domain": "surface", "enabled": True}
    assert advisor_model.parse_order("frigate", {"commands": [{"type": "ping", "value": False}]}) \
        is None
    assert advisor_model.parse_order("uboot", {"commands": [{"type": "radar", "value": True}]}) \
        is None
    for weapon in ("fire", "torpedo", "launch", "asroc"):
        assert advisor_model.parse_order(
            "frigate", {"commands": [{"type": weapon, "value": True}]}) is None
    for side, orders in advisor_model.ORDER_SET.items():
        for action, *_ in orders.values():
            assert not any(word in action for word in ("fire", "launch", "torpedo", "tube"))


# -- multiplayer: no orders ------------------------------------------------------------


def _crewed(game):
    game.commander.server = types.SimpleNamespace(crew_present=lambda: True)


def test_in_multiplayer_a_spoken_order_is_not_taken(clock):
    with FakeLlmServer(_reply([("speed", 30)], say="ok")) as llm, \
            FakeSttServer("Volle Fahrt voraus.") as speech:
        game = _game()
        _connect(game, llm, speech)
        _crewed(game)
        speed = game.ship.target_speed
        entry = _say(game, clock)
        assert game.ship.target_speed == speed and not entry["applied"]
        assert entry["answer"] == game.tr("advisor.orders_locked")
        assert llm.requests == []


def test_in_multiplayer_questions_are_still_answered_without_orders(clock):
    with FakeLlmServer("Kurs 045.") as llm, FakeSttServer("Wo steht K1?") as speech:
        game = _game()
        _connect(game, llm, speech)
        _crewed(game)
        entry = _say(game, clock)
        assert entry["answer"] == "Kurs 045."
        assert "take no orders" in llm.requests[0]["messages"][0]["content"]


def test_in_multiplayer_typed_orders_are_refused(clock):
    with FakeLlmServer(_reply([("speed", 30)], say="ok")) as llm:
        game = _game()
        _connect(game, llm)
        entry = game.advisor_ask("order", "Volle Fahrt voraus")
        assert _pump(game, lambda: entry["status"] == "done")
        _crewed(game)
        speed = game.ship.target_speed
        assert game.advisor_confirm(entry["seq"]) == "orders_locked"
        assert game.ship.target_speed == speed
        assert game.advisor_ask("order", "Kurs 090") == "orders_locked"
        assert game.tr("advisor.reason.orders_locked") != "advisor.reason.orders_locked"


def test_a_browser_in_multiplayer_gets_no_order_carried_out(clock):
    with FakeLlmServer(_reply([("speed", 30)], say="ok")) as llm, \
            FakeSttServer("Volle Fahrt voraus.") as speech:
        game = _game()
        _connect(game, llm, speech)
        _crewed(game)
        speed = game.ship.target_speed
        samples = np.full(16000, 0.2, dtype=np.float32)
        assert game.talk_submit_web("web:1", samples, "frigate", "bridge") == "transcribing"
        assert _pump(game, lambda: game.advisor.log("web:1")
                     and game.advisor.log("web:1")[-1]["status"] != "pending")
        assert game.ship.target_speed == speed
        assert game.advisor.log("web:1")[-1]["answer"] == game.tr("advisor.orders_locked")


@pytest.fixture
def server(tmp_path, monkeypatch):
    from tests.test_commander_sessions_v2 import top_level_files

    for name in top_level_files():
        (tmp_path / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(transport.resources, "files", lambda package: tmp_path)
    instance = CommanderServer()
    instance.start("127.0.0.1", 0)
    try:
        yield instance
    finally:
        instance.stop()


def test_crew_present_counts_people_at_stations_only(server):
    from tests.test_commander_sessions_v2 import pair_v2

    assert server.crew_present() is False
    _, _, _, paired = pair_v2(server, "Watch")
    assert server.crew_present() is False          # paired, no station yet
    assert server.grant_station(paired["client_id"], "sonar")
    assert server.crew_present() is True
    server.set_solo_mode(True)                       # one person holds every station
    _, _, _, solo = pair_v2(server, "Solo")
    assert server.crew_present() is False


def test_the_spoken_prompt_lists_only_the_sides_orders():
    help_text = advisor_model.command_help("frigate")
    system = prompts.spoken("de", "frigate", "facts", help_text, "Kurs neunzig")[0]["content"]
    assert "ping" in system and "mast" not in system and "Deutsch" in system
