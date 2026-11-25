"""AI submarines hunting as a pack, and their snap shot down a heard launch
bearing (``src/enemies/wolfpack.py``)."""

from __future__ import annotations

import math

import pytest

from src.core import config, detrand
from src.core.game import Game
from src.enemies import wolfpack


def _pack_game():
    game = Game(seed=11, start_menu=False, audio_enabled=False)
    game.start_new_game("s2_doppeljagd", "fixed", seed=11)
    boats = [sub for sub in game.subs if sub.side == "hostile" and not sub.manual]
    assert len(boats) >= 2
    return game, boats[0], boats[1]


def _hold_contact(sub, x, y, now):
    sub.memory["contact"] = dict(x=x, y=y, speed=12.0, course=90.0, noise=0.6)
    sub.memory["contact_age"] = 10.0
    sub.memory["contact_bearing"] = 0.0
    sub.memory["contact_sigma_nm"] = 0.5
    sub.memory["contact_t"] = float(now)


def _slot(game, sub, after: float) -> float:
    """The start of the shadower's next report slot after ``after``."""
    period = wolfpack.PACK_REPORT_PERIOD_S
    start = wolfpack._slot_start(game, sub, after, period)
    if start < after:
        start = wolfpack._slot_start(game, sub, after + period, period)
    return start


def test_a_pack_reports_more_often_than_a_lone_boat():
    game, first, second = _pack_game()
    assert wolfpack.pack(game) and wolfpack.report_period(game, first) \
        == wolfpack.PACK_REPORT_PERIOD_S
    second.sunk = True
    assert wolfpack.pack(game) == []
    assert wolfpack.report_period(game, first) == config.SUB_REPORT_PERIOD_S


def test_the_shadower_comes_up_before_its_slot_and_the_pack_takes_the_datum():
    game, shadower, mate = _pack_game()
    mate.memory["contact"] = None
    game.sim_t = 1000.0
    _hold_contact(shadower, 100.0, 100.0, game.sim_t)
    start = _slot(game, shadower, game.sim_t + wolfpack.RISE_S + 5.0)
    game.sim_t = start - wolfpack.RISE_S / 2.0
    _hold_contact(shadower, 100.0, 100.0, game.sim_t)
    orders = wolfpack.rising_orders(game, shadower)
    assert orders is not None and orders[2] < 20.0 and orders[1] <= wolfpack.RISE_KN
    # On the air: the frigate's HF/DF can hear it.
    shadower.depth = 12.0
    game.sim_t = start + 1.0
    assert wolfpack.report_on_air(game, shadower, game.sim_t)
    # The call ends: the mate takes a coarse, dead-reckoned datum.
    end = start + config.SUB_REPORT_TX_S
    game.sim_t = end + 0.05
    heard = shadower.memory["contact_t"]
    assert wolfpack.share(game, 0.1) == 1
    datum = mate.memory["contact"]
    run = config.kn_to_nm_per_s(12.0) * (game.sim_t - heard)
    assert datum["x"] == pytest.approx(100.0 + run) and datum["y"] == pytest.approx(100.0)
    assert mate.memory["contact_sigma_nm"] >= wolfpack.PACK_SIGMA_NM
    assert mate.memory["contact_age"] == wolfpack.PACK_MEMORY_AGE_S
    expected = math.degrees(math.atan2(datum["x"] - mate.x, -(datum["y"] - mate.y))) % 360.0
    assert mate.memory["contact_bearing"] == pytest.approx(expected)
    # The next substep hands nothing on again.
    game.sim_t += 0.1
    assert wolfpack.share(game, 0.1) == 0


def test_a_boat_with_its_own_fresh_contact_keeps_it():
    game, shadower, mate = _pack_game()
    game.sim_t = 2000.0
    start = _slot(game, shadower, game.sim_t)
    _hold_contact(shadower, 100.0, 100.0, start)
    shadower.depth = 12.0
    _hold_contact(mate, 50.0, 50.0, start)
    mate.memory["contact_age"] = 5.0
    game.sim_t = start + config.SUB_REPORT_TX_S + 0.05
    assert wolfpack.share(game, 0.1) == 0
    assert mate.memory["contact"]["x"] == 50.0


def test_a_heard_launch_may_draw_a_snap_shot_down_its_bearing():
    game, boat, _mate = _pack_game()
    boat.ai_tube_left = 0.0
    boat.attack_left = 0.0
    if boat.weapon_battery is not None:
        assert boat.weapon_battery.ready_count > 0
    source = (boat.x + 6.0, boat.y)
    chance = wolfpack.SNAP_CHANCE * boat.stype.aggression
    seqs = [seq for seq in range(1, 60)
            if detrand.u01(game.seed, "snap-shot", int(boat.sensor_seed), seq) < chance]
    misses = [seq for seq in range(1, 60) if seq not in seqs]
    assert seqs and misses
    assert not wolfpack.snap_shot(game, boat, source, misses[0])
    before = len(boat.pending_torpedoes)
    assert wolfpack.snap_shot(game, boat, source, seqs[0])
    assert len(boat.pending_torpedoes) == before + 1
    course = boat.pending_torpedoes[-1][2]
    assert abs(config.angle_diff_deg(course, 90.0)) <= 3.0 + 1e-9
    # Its tubes are dry now and it waits out its cooldown: no second shot.
    assert boat.attack_left > 0.0
    assert not wolfpack.snap_shot(game, boat, source, seqs[1] if len(seqs) > 1 else seqs[0])


def test_no_snap_shot_from_dry_tubes_or_in_peacetime():
    game, boat, _mate = _pack_game()
    boat.ai_tube_left = -1.0
    assert not any(wolfpack.snap_shot(game, boat, (boat.x + 5.0, boat.y), seq)
                   for seq in range(1, 40))
    boat.ai_tube_left = 0.0
    boat.mission_peace = True
    assert not any(wolfpack.snap_shot(game, boat, (boat.x + 5.0, boat.y), seq)
                   for seq in range(1, 40))
