"""Physics and weapon regressions from the code review of 1.3.204 (package B)."""

import math
import random
from types import SimpleNamespace

import pytest

from src.core import autocrew, opfor
from src.core.game_sim import SimMixin
from src.enemies.sub import Sub
from src.physics import ship_dynamics as dyn
from src.sensors import mad
from src.ship.ship import Ship
from src.weapons.asw import NIXIE_MAX_TOW_KN
from src.weapons.torpedo import EnemyTorpedo, seeker_level_db


@pytest.mark.parametrize("sea", [5, 6])
def test_the_frigate_gets_under_way_from_rest_in_heavy_seas(sea):
    hull = dyn.HULL
    resistance = hull.added_resistance_n(sea)
    v = 0.0
    for _ in range(int(300 / 0.05)):
        v, _, _ = dyn.surge_step(hull, v, 31 * dyn.KN, hull.mass_design_kg, 0.05,
                                 extra_resistance=resistance)
    # It used to stay at 0 kn for ever: the shaft never beat the sea.
    assert v / dyn.KN > 10.0


def test_one_step_from_rest_in_heavy_seas_does_not_jump():
    hull = dyn.HULL
    v, _, _ = dyn.surge_step(hull, 0.0, 6 * dyn.KN, hull.mass_design_kg, 0.05,
                             extra_resistance=hull.added_resistance_n(6))
    assert 0.0 <= v / dyn.KN < 0.5


def _sub(depth):
    sub = Sub(100.0, 100.0, depth, 90.0, "aip_modern", random.Random(1))
    sub.endurance = None
    sub.speed = 8.0
    return sub


@pytest.mark.parametrize("start,first,second", [(100.0, 200.0, 50.0), (150.0, 30.0, 300.0)])
def test_a_reversed_depth_order_does_not_teleport_the_submarine(start, first, second):
    sub = _sub(start)
    for _ in range(100):
        sub._advance_depth(first, sub.motion.depth_rate_m_s, 0.05)
    before = sub.depth
    sub._advance_depth(second, sub.motion.depth_rate_m_s, 0.05)
    assert abs(sub.depth - before) < 1.0


def _mad_draws(fps, seconds=20.0, monkeypatch=None):
    draws = []
    monkeypatch.setattr(mad, "detects", lambda seed, tid, tick, slant: draws.append(tick) or False)
    fake = SimpleNamespace(
        helo=SimpleNamespace(mad_mode=True, airborne=True, hovering=False, x=0.0, y=0.0),
        seed=1, sim_t=0.0,
        _mad_wreck_anomalies=lambda *a, **k: None)
    target = SimpleNamespace(id=7, x=0.0, y=0.0, depth=50.0,
                             sensor_domain="subsurface", sunk=False)
    dt = 1.0 / fps
    for _ in range(int(round(seconds * fps))):
        fake.sim_t += dt
        SimMixin._update_mad(fake, [target], dt)
    return draws


def test_helicopter_mad_looks_do_not_depend_on_the_frame_rate(monkeypatch):
    slow = _mad_draws(30, monkeypatch=monkeypatch)
    fast = _mad_draws(60, monkeypatch=monkeypatch)
    assert len(slow) == len(fast) == pytest.approx(20 / mad.MAD_LOOK_S, abs=1)
    assert len(set(slow)) == len(slow)


def _evade_game(nixies=(), aboard=0):
    return SimpleNamespace(nixies=list(nixies),
                           nixie_store=SimpleNamespace(remaining_total=aboard))


def test_the_bridge_crew_runs_from_a_torpedo_below_nixie_tow_speed():
    assert autocrew.evade_speed_kn(_evade_game(aboard=2)) < NIXIE_MAX_TOW_KN
    assert autocrew.evade_speed_kn(_evade_game(nixies=[object()])) < NIXIE_MAX_TOW_KN
    flank = autocrew.config.SHIP_SPEED_MAX_KN
    assert autocrew.evade_speed_kn(_evade_game()) == flank
    assert autocrew.evade_speed_kn(_evade_game(aboard=2), "asm") == flank


def test_a_hostile_torpedo_drops_a_lock_on_a_target_far_out_of_reach():
    ship = SimpleNamespace(x=0.0, y=0.0, depth=5.0, wake=[], course=0.0)
    torpedo = EnemyTorpedo(0.0, 2.0, 0.0, 10.0, 1, guidance_x=0.0, guidance_y=0.0)
    torpedo.update(0.1, ship)
    assert torpedo.seeker_acquired
    ship.x = 10.0
    for _ in range(50):
        torpedo.update(0.1, ship)
    assert not torpedo.seeker_acquired


def test_the_frigate_sounds_louder_to_a_seeker_at_speed():
    ship = Ship(0.0, 0.0, 0.0)
    weapon = SimpleNamespace(x=0.0, y=1.0, depth=6.0)
    levels = []
    for speed in (0.0, 15.0, 30.0):
        ship.speed = speed
        levels.append(seeker_level_db(weapon, ship))
    assert levels[0] < levels[1] < levels[2]


def _pattern_run(wired, pattern):
    orders = opfor.CrewOrders()
    sub = SimpleNamespace(x=0.0, y=20.0, speed=3.0, course=0.0, sunk=False)
    boat = SimpleNamespace(sub=sub, orders=orders, sub_id=7)
    torpedo = EnemyTorpedo(0.0, 2.0, 0.0, 30.0, 1, guidance_x=0.0, guidance_y=0.0,
                           launch_platform_id=7, pattern=pattern, enable_nm=3.0)
    game = SimpleNamespace(enemy_torpedoes=[torpedo])
    ship = SimpleNamespace(x=200.0, y=200.0, depth=5.0, wake=[])
    if not wired:
        opfor.update_wires(game, boat, 0.25)
        orders.wires[torpedo.id].state = "CUT"
    acc = 0.0
    farthest = 0.0
    for i in range(int(300 / 0.05)):
        torpedo.update(0.05, ship)
        acc += 0.05
        if acc >= 0.25:
            opfor.update_wires(game, boat, acc)
            acc = 0.0
        if i * 0.05 > 120:
            farthest = max(farthest, math.hypot(torpedo.x, torpedo.y))
    return farthest


@pytest.mark.parametrize("pattern", ["circle", "helix"])
def test_a_held_wire_keeps_the_search_pattern(pattern):
    # The wire used to steer the torpedo back to the datum, flattening its
    # circle or helix into a straight run through the point.
    assert _pattern_run(True, pattern) == pytest.approx(_pattern_run(False, pattern), abs=0.2)
