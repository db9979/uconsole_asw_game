"""The periscope attack computer: marks, solution, lead and the shot on it."""

import copy
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pygame
import pytest

from src.core import attack_computer, config, opfor
from src.core.save_schema import CREW_ORDERS_FIELDS
from src.ui import layout, uboot_scope

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _boat_apply, _crewed  # noqa: E402
from test_uboot_scope import _clear, _key, _scope_up  # noqa: E402


def _track(course, speed_kn, times, start=(100.0, 100.0)):
    rad = math.radians(course)
    v = config.kn_to_nm_per_s(speed_kn)
    return [[t, start[0] + v * t * math.sin(rad), start[1] - v * t * math.cos(rad)]
            for t in times]


def test_the_fit_needs_a_base_and_gives_course_and_speed():
    assert attack_computer.solve(_track(90.0, 10.0, [0.0]), 0.0) is None
    assert attack_computer.solve(_track(90.0, 10.0, [0.0, 30.0]), 30.0) is None
    solution = attack_computer.solve(_track(135.0, 12.0, [0.0, 90.0, 180.0]), 240.0)
    assert solution["course"] == pytest.approx(135.0, abs=1e-6)
    assert solution["speed_kn"] == pytest.approx(12.0, abs=1e-6)
    expected = _track(135.0, 12.0, [240.0])[0]
    assert (solution["x"], solution["y"]) == pytest.approx((expected[1], expected[2]))
    assert solution["marks"] == 3 and 0.0 < solution["quality"] <= 1.0
    # An impossible fit (a bad mark) is refused.
    assert attack_computer.solve(_track(0.0, 90.0, [0.0, 120.0]), 120.0) is None
    # Marks out of the window no longer count.
    assert attack_computer.solve(_track(90.0, 10.0, [0.0, 90.0]),
                                 config.UBOOT_TDC_WINDOW_S + 1.0) is None


def test_the_intercept_meets_the_target():
    solution = dict(x=0.0, y=-3.0, course=90.0, speed_kn=15.0)
    lead = attack_computer.intercept(solution, 0.0, 0.0, 40.0)
    assert lead["bearing"] == pytest.approx(0.0)
    assert 0.0 < lead["lead_deg"] < 30.0                   # aim ahead, to the right
    torpedo = config.kn_to_nm_per_s(40.0) * lead["run_s"]
    target = (config.kn_to_nm_per_s(15.0) * lead["run_s"], -3.0)
    aim = (torpedo * math.sin(math.radians(lead["course"])),
           -torpedo * math.cos(math.radians(lead["course"])))
    assert aim == pytest.approx(target, abs=1e-6)
    still = attack_computer.intercept(dict(x=2.0, y=0.0, course=0.0, speed_kn=0.0),
                                      0.0, 0.0, 40.0)
    assert still["lead_deg"] == pytest.approx(0.0) and still["range_nm"] == pytest.approx(2.0)
    # A target running away faster than the torpedo cannot be caught.
    assert attack_computer.intercept(dict(x=0.0, y=-3.0, course=0.0, speed_kn=50.0),
                                     0.0, 0.0, 40.0) is None


def _aim_at_frigate(game, boat):
    sub = boat.sub
    bearing = math.degrees(math.atan2(game.ship.x - sub.x, -(game.ship.y - sub.y)))
    opfor.set_scope_relative(boat, (bearing - sub.course) % 360.0)


def _marked(seed=71):
    """A crewed boat with two stadimeter marks, two minutes apart, on the
    frigate crossing its bow at 12 kn."""
    game, server, bridge = _crewed(seed=seed)
    boat = game.opfor
    _clear(game)
    _scope_up(boat)
    sub = boat.sub
    game.ship.x, game.ship.y = sub.x + 3.0, sub.y - 3.0
    game.ship.course, game.ship.speed = 180.0, 12.0
    for step in range(2):
        if step:
            game.sim_t += 120.0
            game.ship.y += config.kn_to_nm_per_s(12.0) * 120.0
        _aim_at_frigate(game, boat)
        opfor.update_sightings(game, boat)
        assert opfor.stadimeter(game, boat) is True
    return game, bridge, boat


def test_two_stadimeter_marks_give_a_solution_on_the_target():
    game, _bridge, boat = _marked()
    (ref, entry), = boat.orders.tdc.items()
    assert len(entry["marks"]) == 2
    solution = attack_computer.solution_for_ref(boat, ref, game.sim_t)
    # The crew's estimate: stadimeter ranges are off by the assumed hull length.
    assert abs(((solution["course"] - 180.0 + 180.0) % 360.0) - 180.0) < 20.0
    assert 6.0 < solution["speed_kn"] < 20.0
    values = attack_computer.summary(boat, ref, game.sim_t)
    assert values["lead_deg"] is not None and values["run_s"] > 0.0
    text, _color = uboot_scope.tdc_line(game, boat)
    assert text["__u_jagd_i18n__"] == "uboot.line.tdc_solution"
    for language in ("en", "de"):
        game.preferences = replace(game.preferences, language=language)
        layout.configure_for(game)
        uboot_scope.draw_scope_page(game.screen, game, boat, 640, 60, 620, 560)


def test_firing_on_the_solution_leads_the_target():
    game, bridge, boat = _marked()
    sub = boat.sub
    ref = next(iter(boat.orders.tdc))
    lead = attack_computer.intercept(attack_computer.solution_for_ref(boat, ref, game.sim_t),
                                     sub.x, sub.y, attack_computer.torpedo_speed_kn(sub))
    sub.course = sub.target_course = lead["course"]     # the target inside the tube arc
    _aim_at_frigate(game, boat)
    apply = _boat_apply(game, bridge)
    before = len(sub.pending_torpedoes)
    assert apply("uboot_scope_fire", {}) is True
    row = sub.pending_torpedoes[-1]
    assert len(sub.pending_torpedoes) == before + 1
    assert abs(((row[2] - lead["course"] + 180.0) % 360.0) - 180.0) <= 3.0 + 1e-6
    # The sonar-contact shot uses the same solution once the target is marked.
    assert attack_computer.solution_for_target(boat, entry_target(boat), game.sim_t)


def entry_target(boat):
    return next(iter(boat.orders.tdc.values()))["target_id"]


def test_no_solution_no_shot_and_the_web_action_is_command_only():
    game, _server, bridge = _crewed(seed=72)
    boat = game.opfor
    apply = _boat_apply(game, bridge)
    assert apply("uboot_scope_fire", {}) == "uboot_mast_down"
    _clear(game)
    _scope_up(boat)
    assert apply("uboot_scope_fire", {}) == "uboot_no_sighting"
    from src.commander.server import V2_ACTION_REGISTRY
    spec = V2_ACTION_REGISTRY["uboot_scope_fire"]
    assert spec.stations == frozenset({"uboot"}) and not spec.validate_params({"x": 1})
    sub = boat.sub
    game.ship.x, game.ship.y = sub.x + 2.0, sub.y - 2.0
    _aim_at_frigate(game, boat)
    opfor.update_sightings(game, boat)
    assert opfor.stadimeter(game, boat) is True
    assert apply("uboot_scope_fire", {}) == "uboot_no_solution"


def test_the_marks_survive_a_save_and_bad_marks_are_rejected():
    game, _bridge, boat = _marked(seed=73)
    assert "tdc" in CREW_ORDERS_FIELDS
    data = json.loads(json.dumps(game.save_state()))
    saved = copy.deepcopy(boat.orders.tdc)
    assert game._load_save_data(copy.deepcopy(data))
    assert game.opfor.orders.tdc == saved
    for mutate in (
            lambda tdc, ref: tdc[ref]["marks"].reverse(),
            lambda tdc, ref: tdc[ref].update(target_id=10**9),
            lambda tdc, ref: tdc[ref].update(marks=[]),
            lambda tdc, ref: tdc[ref]["marks"][0].append(1.0),
            lambda tdc, ref: tdc[ref].update(extra=1)):
        broken = copy.deepcopy(data)
        tdc = broken["crew"]["orders"]["tdc"]
        mutate(tdc, next(iter(tdc)))
        assert not game._load_save_data(broken)
    assert game.opfor.orders.tdc == saved


def test_ctrl_enter_on_the_periscope_fires_on_the_solution():
    game, _bridge, boat = _marked(seed=74)
    game.local_side = "uboot"
    from src.core.station import Station
    game.station = Station.BRIDGE
    from src.ui import uboot_view
    pages = uboot_view.station_pages("uboot")
    boat.command_page = pages.index("UBOOT_SCOPE")
    sub = boat.sub
    ref = next(iter(boat.orders.tdc))
    lead = attack_computer.intercept(attack_computer.solution_for_ref(boat, ref, game.sim_t),
                                     sub.x, sub.y, attack_computer.torpedo_speed_kn(sub))
    sub.course = sub.target_course = lead["course"]
    _aim_at_frigate(game, boat)
    before = len(sub.pending_torpedoes)
    _key(game, pygame.K_RETURN, pygame.KMOD_CTRL)
    assert len(sub.pending_torpedoes) == before + 1
