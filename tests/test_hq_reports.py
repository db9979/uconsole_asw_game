"""The radio room's own calls to HQ: contact reports and support requests
go out on HF, can be DF'd by the boat, and only count at the mission's end."""

import copy
import json
import math
import sys
from pathlib import Path

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core import config
from src.core.game import Game
from src.core.hq_reports import HqReports, valid_row
from src.core.station import Station

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402


def _game(seed=9101):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _locate(game, x, y):
    """Give the frigate a fresh located sonar contact at (x, y)."""
    contact = next(iter(game.sonar.contacts.values()), None)
    if contact is None:
        game.sonar.update(0.5, game.sim_t, game.ship, [game.subs[0]], game.world)
        contact = game.sonar._get_contact(game.subs[0])
    contact.observed_x, contact.observed_y = x, y
    contact.range_est = math.hypot(x - game.ship.x, y - game.ship.y)
    contact.range_seen = contact.last_seen = game.sim_t
    return contact


def test_contact_report_needs_a_fix_and_scores_only_at_the_end():
    game = _game()
    assert game.send_contact_report() == "report_no_fix"
    sub = game.subs[0]
    _locate(game, sub.x + 1.0, sub.y)
    assert game.send_contact_report() is True
    assert game.hq_reports.transmitting
    assert game.send_contact_report() == "report_transmitting"
    assert game.hq_reports.log[-1]["accurate"] is True
    score = game.score
    game.sim_t = game.hq_reports.tx_until
    game._update_hq_reports()
    assert not game.hq_reports.transmitting
    assert game.score == score                     # nothing during the mission
    assert game.request_support() == "report_cooldown"
    assert game._score_hq_reports() == config.SCORE_CONTACT_REPORT
    # A wrong fix is logged as such and never scores.
    game.sim_t = game.hq_reports.next_t
    _locate(game, sub.x + 20.0, sub.y)
    assert game.send_contact_report() is True
    assert game.hq_reports.log[-1]["accurate"] is False
    assert game._score_hq_reports() == config.SCORE_CONTACT_REPORT


def test_support_request_launches_the_patrol_aircraft():
    game = _game()
    assert not game.mpa.airborne
    assert game.request_support() is True
    game.sim_t = game.hq_reports.tx_until
    game._update_hq_reports()
    assert game.mpa.airborne


def test_calls_need_the_radio_room():
    game = _game()
    game.damage.station_down = lambda station: station == "radio"
    assert game.request_support() == "radio_down"


def test_reports_round_trip_and_bad_state_is_rejected():
    game = _game()
    _locate(game, game.subs[0].x, game.subs[0].y)
    assert game.send_contact_report() is True
    state = json.loads(json.dumps(game.save_state()))
    assert HqReports.valid_state(state["hq_reports"])
    twin = _game(1)
    assert twin._load_save_data(copy.deepcopy(state))
    assert twin.hq_reports.serialize() == game.hq_reports.serialize()
    for field, value in (("tx_kind", "chat"), ("next_t", float("inf")), ("version", 2)):
        broken = copy.deepcopy(state)
        broken["hq_reports"][field] = value
        assert not twin._load_save_data(broken)
    broken = copy.deepcopy(state)
    broken["hq_reports"]["log"][0]["accurate"] = None
    assert not twin._load_save_data(broken)
    assert not valid_row(dict(t=1.0, kind="support", x=1.0, y=None, accurate=None))


def test_the_crewed_boat_takes_a_bearing_on_the_call():
    game, _server, _bridge = _crewed(seed=79)
    boat = game.opfor
    sub = boat.sub
    sub.depth = 10.0
    boat.orders.mast = True
    before = len(boat.plot.items) if hasattr(boat.plot, "items") else None
    assert game.request_support() is True
    events = [key for key, _values in boat.orders._events]
    assert "hf_frigate" in events
    values = next(values for key, values in boat.orders._events if key == "hf_frigate")
    truth = math.degrees(math.atan2(game.ship.x - sub.x, -(game.ship.y - sub.y))) % 360.0
    assert abs(config.angle_diff_deg(float(values["bearing"]), truth)) <= 2 * config.HFDF_BEARING_ERR_DEG + 1
    if before is not None:
        assert len(boat.plot.items) == before + 1


def test_a_deep_boat_hears_nothing_and_an_ai_boat_at_periscope_depth_remembers():
    game = _game()
    sub = game.subs[0]
    sub.x, sub.y = game.ship.x + 10.0, game.ship.y
    sub.depth = 120.0
    sub.memory["contact"] = None
    sub.memory["contact_bearing"] = None
    assert game.request_support() is True
    assert sub.memory["contact_bearing"] is None
    game.sim_t = game.hq_reports.next_t
    game._update_hq_reports()
    sub.depth = 10.0
    assert game.request_support() is True
    assert abs(config.angle_diff_deg(sub.memory["contact_bearing"], 270.0)) <= 20.0


def test_the_ai_boat_keeps_the_call_bearing_and_acts_on_it():
    game = _game()
    sub = game.subs[0]
    # Too far to hear the frigate itself, close enough for the HF ground wave.
    sub.x, sub.y = game.ship.x + 30.0, game.ship.y
    sub.depth = 10.0
    sub.memory["contact"] = None
    sub.memory["contact_bearing"] = None
    sub.memory["contact_age"] = config.SUB_EVADE_DURATION_S
    assert game.request_support() is True
    heard = sub.memory["contact_bearing"]
    assert heard is not None
    # The next step does not wipe it as an old contact.
    game._update_sim(0.25)
    assert sub.memory["contact_bearing"] == heard
    assert sub.memory["contact_age"] < config.SUB_EVADE_DURATION_S


def test_a_call_cut_off_never_scores_and_later_calls_keep_the_points():
    game = _game()
    sub = game.subs[0]
    _locate(game, sub.x, sub.y)
    assert game.send_contact_report() is True
    game.damage.station_down = lambda station: station == "radio"
    game.sim_t = game.hq_reports.tx_until
    game._update_hq_reports()
    assert not game.hq_reports.transmitting
    assert game._score_hq_reports() == 0
    # Right reports are never pushed out of the log by later calls.
    reports = HqReports()
    t = 0.0
    for _ in range(config.CONTACT_REPORT_SCORED):
        reports.start("contact", t, 1.0, 1.0, x=1.0, y=1.0, accurate=True)
        reports.finish()
        t += 10.0
    for _ in range(20):
        reports.start("support", t, 1.0, 1.0)
        reports.finish()
        t += 10.0
    assert reports.accurate_reports() == config.CONTACT_REPORT_SCORED
    assert HqReports.valid_state(reports.serialize())


def test_keys_and_remote_actions():
    game = _game()
    game.station = Station.RADIO
    game.station_page = 2
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, mod=0, unicode="h"))
    assert game.hq_reports.transmitting
    for name in ("radio_contact_report", "radio_request_support"):
        assert V2_ACTION_REGISTRY[name].stations == frozenset({"radio"})
        assert V2_ACTION_REGISTRY[name].validate_params({})
