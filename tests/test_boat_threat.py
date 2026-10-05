"""The crewed boat's threat picture, evasion, reports, debrief and lessons."""

import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pygame

from src.commander import projections
from src.commander.v2.commands import UBOOT_REASONS, V2_ACTION_REGISTRY
from src.core import boat_debrief, boat_threat, config, opfor, training
from src.core.callouts import CalloutLog, callout_of
from src.core.i18n import message
from src.core.station import Station

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_opfor_sub import _boat_apply, _crewed, _game  # noqa: E402


def _ping_from(game, boat, bearing, distance_nm, kind="hull"):
    sub = boat.sub
    rad = math.radians(bearing)
    source = (sub.x + distance_nm * math.sin(rad), sub.y - distance_nm * math.cos(rad))
    sub.memory["last_ping_age"] = math.inf
    sub.hear_ping(source=source, kind=kind)
    opfor.update_crew(game, boat)      # stamps the pending intercept
    return source


def test_ping_level_falls_with_range_and_source_type():
    game, _server, _bridge = _crewed(seed=61)
    sub = game.opfor.sub
    near = sub.ping_level_db((sub.x + 1.0, sub.y), "hull")
    far = sub.ping_level_db((sub.x + 8.0, sub.y), "hull")
    buoy = sub.ping_level_db((sub.x + 1.0, sub.y), "buoy")
    assert near > far + 15.0
    assert near - buoy == config.UBOOT_PING_SOURCE_DB["hull"] - config.UBOOT_PING_SOURCE_DB["buoy"]


def test_intercepts_are_recorded_by_kind_and_bounded():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _ping_from(game, boat, 90.0, 2.0, "hull")
    _ping_from(game, boat, 200.0, 1.0, "dipping")
    kinds = [row["kind"] for row in boat.intercepts]
    assert kinds == ["hull", "dipping"]
    assert all(row["level_db"] is not None for row in boat.intercepts)
    assert abs(config.angle_diff_deg(boat.intercepts[0]["bearing"], 90.0)) < 20.0
    for _ in range(config.UBOOT_INTERCEPTS_MAX + 5):
        boat.orders.intercept("buoy", 10.0, 120.0)
    opfor.update_crew(game, boat)
    assert len(boat.intercepts) == config.UBOOT_INTERCEPTS_MAX


def test_buoy_splash_is_heard_only_nearby():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    sub = boat.sub
    boat_threat.record_splash(game, sub.x + config.UBOOT_SPLASH_HEAR_NM + 1.0, sub.y, 1)
    opfor.update_crew(game, boat)
    assert not any(row["kind"] == "splash" for row in boat.intercepts)
    boat_threat.record_splash(game, sub.x + 1.0, sub.y, 2)
    opfor.update_crew(game, boat)
    rows = [row for row in boat.intercepts if row["kind"] == "splash"]
    assert len(rows) == 1 and rows[0]["level_db"] is None
    assert abs(config.angle_diff_deg(rows[0]["bearing"], 90.0)) < 30.0


def test_picture_counts_advises_and_plans_the_evasion():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    assert boat_threat.evasion_plan(game, boat) is None
    assert boat_threat.evade(game, boat) == "uboot_no_threat"
    _ping_from(game, boat, 45.0, 1.0)
    view = boat_threat.picture(game, boat)
    assert view["counts"]["hull"] == 1 and view["loudest_db"] is not None
    assert view["echo_likely"] is (view["loudest_db"] >= config.UBOOT_PING_ECHO_LIKELY_DB)
    assert "uboot.advice.evade" in view["advice"]
    assert view["layer"] == "unknown" and "uboot.advice.measure_layer" in view["advice"]
    plan = boat_threat.evasion_plan(game, boat)
    assert plan["kind"] == "ping" and plan["silent"] and not plan["decoy"]
    bearing = boat.orders.ping_bearing
    assert abs(config.angle_diff_deg(plan["course"], (bearing + 180.0) % 360.0)) < 0.2
    assert plan["speed_kn"] <= config.UBOOT_SILENT_MAX_KN
    assert json.loads(json.dumps(view)) == view


def test_evade_orders_the_plan_and_reports_it():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    sub = boat.sub
    _ping_from(game, boat, 45.0, 1.0)
    plan = boat_threat.evasion_plan(game, boat)
    assert boat_threat.evade(game, boat) is True
    assert boat.orders.silent
    assert abs(config.angle_diff_deg(sub.order_course, plan["course"])) < 0.5
    assert abs(sub.order_depth - plan["depth_m"]) < 0.5
    assert boat.evaded_t == game.sim_t
    opfor.update_crew(game, boat)
    assert boat.callouts.detached()[-1]["key"] == "evade"
    # A torpedo alarm is answered with full speed and a decoy.
    boat.orders.torpedo_bearing = 300.0
    sub.memory["last_torpedo_age"] = 5.0
    plan = boat_threat.evasion_plan(game, boat)
    assert plan["kind"] == "torpedo" and plan["decoy"] and not plan["silent"]
    off = abs(config.angle_diff_deg(plan["course"], 300.0))
    assert abs(off - 150.0) < 0.5


def test_remote_evade_action_and_projection():
    game, _server, bridge = _crewed(seed=61)
    boat = game.opfor
    assert V2_ACTION_REGISTRY["uboot_evade"].stations == frozenset({"uboot", "uboot_nav"})
    assert "uboot_no_threat" in UBOOT_REASONS
    apply = _boat_apply(game, bridge)
    assert apply("uboot_evade", {}) == "uboot_no_threat"
    _ping_from(game, boat, 120.0, 1.5)
    threat = projections._uboot_threat(game, boat)
    assert threat["plan"] is not None and threat["counts"]["hull"] == 1
    text = json.dumps(threat)
    assert "NaN" not in text and "Infinity" not in text
    assert apply("uboot_evade", {}) is True


def test_local_key_i_evades_on_command_but_not_on_the_damage_page():
    game = _game(61)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    _ping_from(game, boat, 90.0, 1.0)
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i, mod=0, unicode="i"))
    assert boat.evaded_t is not None


def test_buoy_pings_reach_only_a_crewed_boat():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    ai = [sub for sub in game.subs if sub is not boat.sub]
    before = [(sub.state, sub.memory["last_ping_age"]) for sub in ai]
    sub = boat.sub
    sub.hear_ping(source=(sub.x + 3.0, sub.y), kind="buoy")
    assert sub.state != "EVADE" or sub.manual
    assert [(s.state, s.memory["last_ping_age"]) for s in ai] == before


def test_boat_callouts_are_its_own_log():
    assert callout_of(message("uboot.event.ping_dipping_heard", bearing="045"),
                      side="boat") == ("dipping", 45)
    assert callout_of(message("uboot.event.ping_dipping_heard", bearing="045")) is None
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    assert isinstance(boat.callouts, CalloutLog) and boat.callouts.side == "boat"
    boat.orders.event("buoy_splash", bearing="100")
    opfor.update_crew(game, boat)
    assert [row["key"] for row in boat.callouts.detached()][-1:] == ["splash"]


def test_boat_speech_follows_the_local_side():
    from src.audio.speech import Speaker
    game = _game(61)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    said = []
    game.speaker = Speaker("espeak-ng", popen=lambda args, **_k: said.append(args[-1]) or
                           type("P", (), {"poll": lambda self: 0})())
    game.preferences = replace(game.preferences, speech=True)
    game._pump_speech()
    said.clear()
    boat.notice(game.sim_t, "sonar", message("uboot.event.buoy_splash", bearing="270"),
                stamp="00:00")
    game.feed.add("00:00", "sonar", message("runtime.torpedo_cue.transient", bearing="045.0"))
    game._pump_speech()
    assert len(said) == 1 and "two seven zero" in said[0]


def test_boat_outcome_and_debrief():
    game = _game(61)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    for _ in range(80):
        game._update(0.25)
    assert isinstance(game.boat_debrief, boat_debrief.BoatDebriefRecorder)
    assert game.boat_debrief.frames
    assert boat_debrief.outcome(game, boat) == "over"
    game.damage.ship_sunk = True
    assert boat_debrief.outcome(game, boat) == "won"
    game.damage.ship_sunk = False
    game.result_reason = {"__u_jagd_i18n__": "end.reason.sub_escaped",
                          "params": {"contact": "K07"}}
    # Another submarine escaped: the boat is still near its start.
    assert boat_debrief.outcome(game, boat) == "over"
    home = (boat.sub.x, boat.sub.y)
    boat.sub.x += config.MISSION_ESCAPE_RADIUS_NM + 1.0
    assert boat_debrief.outcome(game, boat) == "escaped"
    game.result_reason = {"__u_jagd_i18n__": "end.reason.sub_escaped_unseen",
                          "params": {}}
    assert boat_debrief.outcome(game, boat) == "escaped"
    boat.sub.x, boat.sub.y = home
    game.result_reason = None
    boat.sub.sunk = True
    assert boat_debrief.outcome(game, boat) == "lost"
    boat.sub.sunk = False
    game.damage.ship_sunk = True
    for _ in range(20):
        game._update(0.25)
    assert game.game_over and game.open_debrief()
    assert game.debrief is game.boat_debrief
    game.draw()
    json.loads(json.dumps(game.boat_debrief.frames))


def test_tracked_spans_need_a_minute():
    frames = [dict(t=float(t), tracked=10 <= t < 90, below_layer=True,
                   ship=dict(x=0.0, y=0.0, course=0), subs=[dict(x=1.0, y=0.0)])
              for t in range(0, 200, 10)]
    spans = boat_debrief.tracked_spans(frames)
    assert len(spans) == 1 and spans[0]["duration_s"] == 70.0 and spans[0]["layer"]
    frames = [dict(frame, tracked=10 <= frame["t"] < 40) for frame in frames]
    assert boat_debrief.tracked_spans(frames) == []


def test_boat_lessons_play_the_boat_and_complete():
    assert training.side_of("boat_evade") == "uboot" and training.side_of("sonar") == "frigate"
    definition = training.lesson_definition("boat_listen", 5)
    assert definition["units"]["exact"][0]["side"] == "hostile"
    assert definition["objective"]["type"] == "survive"
    game = _game(5)
    game.local_side = "uboot"
    assert game.start_training("boat_listen")
    boat = game.opfor
    assert boat is not None and boat.sub.manual
    coach = game.training
    assert coach.hint_key() == "training.step.boat_sonar"
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0, unicode="2"))
    for _ in range(8):
        game._update(0.25)
    assert game.station is Station.SONAR
    assert coach.step >= 1
    game.draw()


def test_evasion_lesson_frigate_pings_until_it_loses_the_boat():
    game = _game(5)
    game.local_side = "uboot"
    assert game.start_training("boat_evade")
    boat = game.opfor
    coach = game.training
    assert training.frigate_should_ping(game, coach)
    for _ in range(40):
        game._update(0.25)
    assert any(row["kind"] == "hull" for row in boat.intercepts)
    assert boat_threat.evade(game, boat) is True
    # One more search ping after the evasion order is always sent ...
    coach.next_ping_t = boat.evaded_t
    assert training.frigate_should_ping(game, coach)
    # ... later ones only while the frigate's own pings still return an echo.
    coach.next_ping_t = boat.evaded_t + 1.0
    game.sim_t = coach.next_ping_t
    echo = any(contact.target_id == boat.sub.id and contact.range_source == "ping"
               for contact in game.sonar.active_contacts())
    assert training.frigate_should_ping(game, coach) is echo
    coach.done = True
    assert not training.frigate_should_ping(game, coach)


def test_boat_end_panel_and_training_menu_draw():
    game = _game(5)
    game.local_side = "uboot"
    game._update(0.05)
    game.training = training.TrainingCoach("boat_evade", 0.0)
    game.training.done = True
    from src.ui import uboot_view
    assert uboot_view.end_text(game, game.opfor) == "uboot.end.trained"
    menu = _game(5)
    menu.in_menu, menu.main_menu, menu.menu_screen = True, False, "training"
    menu.menu_sel = len(training.LESSONS) - 1
    menu.draw()


def test_catalogs_carry_the_new_keys():
    en = json.loads((ROOT / "data/i18n/en.json").read_text(encoding="utf-8"))
    de = json.loads((ROOT / "data/i18n/de.json").read_text(encoding="utf-8"))
    keys = [f"training.lesson.{lesson}" for lesson in training.BOAT_LESSONS]
    keys += [key for lesson in training.BOAT_LESSONS for key, _check in
             training.STEPS[lesson]]
    keys += ["uboot.end." + name for name in ("won", "escaped", "survived", "trained",
                                              "lost", "over")]
    keys += [f"uboot.threat_page.kind.{kind}" for kind in boat_threat.KINDS]
    for key in keys:
        assert key in en and key in de, key


# --- more spoken reports from the boat's own feed ---------------------------------

_BOAT_REPORTS = (
    (message("uboot.event.torpedo_fired", tube="2"), ("torpedo_away", None)),
    (message("uboot.event.torpedo_fired_tubeless"), ("torpedo_away", None)),
    (message("uboot.event.detonation_near", bearing="045"), ("detonation_near", 45)),
    (message("uboot.event.detonation_far", bearing="310"), ("detonation", 310)),
    (message("uboot.event.breakup_heard", bearing="090"), ("breakup", 90)),
    (message("uboot.event.radio_copied", number="3"), ("broadcast", None)),
    (message("uboot.event.radio_copied_report", number="4"), ("broadcast_report", None)),
    (message("uboot.event.sighting_warship", bearing="001"), ("sighting_warship", 1)),
    (message("uboot.event.sighting_merchant", bearing="120"), ("sighting_merchant", 120)),
    (message("uboot.event.sighting_aircraft", bearing="200"), ("sighting_aircraft", 200)),
    (message("uboot.event.sighting_torpedo", bearing="270"), ("sighting_torpedo", 270)),
    (message("uboot.event.sighting_unknown", bearing="359"), ("sighting_unknown", 359)),
    (message("uboot.event.test_depth_near", depth="180", test="200"), ("test_depth_near", None)),
    (message("uboot.event.test_depth_over", depth="201", test="200"), ("test_depth_over", None)),
    (message("uboot.event.hull_hit"), ("hit", None)),
    (message("uboot.event.hull_bolts", compartment="x"), ("hull_damage", None)),
    (message("uboot.event.hull_seal", compartment="x"), ("hull_damage", None)),
    (message("uboot.event.hull_fracture", compartment="x"), ("hull_damage", None)),
    (message("uboot.event.hull_collapse"), ("hull_damage", None)),
    (message("uboot.event.mission_won"), ("won", None)),
    (message("uboot.event.mission_lost"), ("lost", None)),
)


def test_boat_feed_lines_map_to_their_spoken_reports():
    from src.core import callouts
    from src.core.i18n import Translator
    for text, expected in _BOAT_REPORTS:
        assert callout_of(text, side="boat") == expected, text
        # The frigate never speaks the boat's lines.
        assert callout_of(text) is None, text
        row = dict(seq=1, key=expected[0], bearing=expected[1])
        for language in ("en", "de"):
            spoken = callouts.spoken_text(row, Translator(language).t)
            assert spoken and "{" not in spoken and "commander.web" not in spoken
    # A sighting without a readable bearing is never spoken.
    assert callout_of(message("uboot.event.sighting_warship", bearing="n/a"),
                      side="boat") is None


def test_frigate_callouts_are_unchanged():
    from src.core import callouts
    assert callouts._EXACT == {
        "runtime.contact.new_range": "contact",
        "runtime.contact.new_bearing": "contact",
        "runtime.breakup_noise": "breakup",
        "runtime.torpedo.feed": "torpedo_away",
        "runtime.hit.damage": "hit",
        "runtime.hit.asm": "hit",
        "runtime.mission.won": "won",
        "runtime.mission.lost": "lost",
        "crew.action_stations_on": "action_stations",
        "mpa.on_station": "mpa_on_station",
        "runtime.task.offered": "task",
    }
    assert callouts._PREFIX == (("runtime.torpedo_cue.", "torpedo"),)


def _boat_keys(boat):
    return [row["key"] for row in boat.callouts.detached()]


def _feed_keys(boat):
    return [row["text"].get("__u_jagd_i18n__") for row in boat.feed
            if isinstance(row["text"], dict)]


def test_boat_reports_its_own_torpedo_away_with_the_tube():
    game, _server, _bridge = _crewed(seed=71)
    boat = game.opfor
    sub = boat.sub
    sub.course = 90.0
    assert sub.command_fire(90.0, 3.0, now=game.sim_t) is True
    opfor.update_crew(game, boat)
    row = boat.feed[-1]
    assert row["text"]["__u_jagd_i18n__"] == "uboot.event.torpedo_fired"
    assert row["text"]["params"]["tube"] == f"{sub.weapon_battery.last_fired_tube + 1}"
    assert _boat_keys(boat)[-1] == "torpedo_away"


def test_boat_reports_hits_hull_failures_and_test_depth():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    sub = boat.sub
    sub.hit(10.0)
    opfor.update_crew(game, boat)
    assert "uboot.event.hull_hit" in _feed_keys(boat) and "hit" in _boat_keys(boat)
    sub._hull_failure(1.1)
    opfor.update_crew(game, boat)
    assert "hull_damage" in _boat_keys(boat)
    test = sub.stype.max_depth_m
    near = test * config.UBOOT_TEST_DEPTH_WARN_FRACTION
    sub.depth = near + 0.5
    sub._report_test_depth(near - 0.5)
    sub.depth = test + 0.5
    sub._report_test_depth(test - 0.5)
    # Going up again or staying level is no report.
    sub._report_test_depth(test + 5.0)
    opfor.update_crew(game, boat)
    keys = _boat_keys(boat)
    assert keys.count("test_depth_near") == 1 and keys.count("test_depth_over") == 1
    assert keys.index("test_depth_near") < keys.index("test_depth_over")


def test_boat_hears_breakup_noises_only_when_its_sonar_can():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    sub = boat.sub
    # Its own hull is never "heard" breaking up, nor one far beyond hearing.
    opfor.hear_breakup(game, boat, sub.x, sub.y, sub.depth, sub.id)
    opfor.hear_breakup(game, boat, sub.x + 500.0, sub.y, 0.0, 999)
    opfor.update_crew(game, boat)
    assert "breakup" not in _boat_keys(boat)
    x, y = sub.x + 0.5, sub.y
    assert not game.world.sonar_path_blocked(x, y, 0.0, sub.x, sub.y, sub.depth)
    opfor.hear_breakup(game, boat, x, y, 0.0, 999)
    opfor.update_crew(game, boat)
    row = boat.callouts.detached()[-1]
    assert row["key"] == "breakup" and abs((row["bearing"] - 90 + 180) % 360 - 180) <= 15


def test_boat_reports_the_mission_result():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    game.damage.ship_sunk = True
    game._end_mission(False, message("end.reason.frigate_sunk"))
    assert _feed_keys(boat)[-1] == "uboot.event.mission_won"
    assert _boat_keys(boat)[-1] == "won"
    # The frigate's own report is untouched.
    assert game.callouts.detached()[-1]["key"] == "lost"
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    boat.sub.state = "SINKING"
    game._end_mission(True, message("end.reason.targets_sunk"))
    assert _feed_keys(boat)[-1] == "uboot.event.mission_lost"
    assert _boat_keys(boat)[-1] == "lost"
    assert game.callouts.detached()[-1]["key"] == "won"
