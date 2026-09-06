"""Kampfschiff (KAMPFSCHIFF): Spawn, ASM, Akustik, Save/Load."""

import random

import pytest

from src.core.game import Game
from src.enemies.surface import SurfaceShip


def _make_game(seed: int, scenario: str):
    g = Game(seed=seed, start_menu=False)
    g.reset(seed, scenario_key=scenario)
    return g


def test_warships_spawn_for_doppeljagd():
    g = _make_game(7, "s2_doppeljagd")
    assert g.mission.warship_count >= 1
    assert len(g.warships) == g.mission.warship_count
    for w in g.warships:
        assert w.hostile is True
        assert w.anchor is not None
        assert w.sunk is False
        assert w.emitter in (True, False)


def test_no_warships_outside_spawn_range():
    g = _make_game(7, "s2_doppeljagd")
    for w in g.warships:
        assert w.anchor is not None
        # Anker liegt in der Nahe der feindlichen Basis (Land erlaubt, Wasser zwingend)
        bx, by = w.anchor
        assert 0 <= bx <= g.world.size_nm
        assert 0 <= by <= g.world.size_nm


def test_warship_asks_asm_when_frigate_close():
    ship = SurfaceShip(10.0, 10.0, random.Random(1), hostile=True)
    ship.anchor = (10.0, 10.0)
    ship.attack_left = 0.0
    frigate = type("F", (), {"x": 15.0, "y": 15.0})()
    world = type("W", (), {"size_nm": 500.0})()
    ship.update(1.0, frigate, world)
    # 7.07 NM < WARSHIP_ASM_RANGE_NM
    assert len(ship.pending_asm) == 1
    x, y, n = ship.pending_asm[0]
    assert n >= 1
    assert ship.attack_left > 0.0  # Cooldown gestartet


def test_warship_no_asm_when_far():
    ship = SurfaceShip(10.0, 10.0, random.Random(2), hostile=True)
    ship.anchor = (10.0, 10.0)
    ship.attack_left = 0.0
    frigate = type("F", (), {"x": 200.0, "y": 200.0})()
    world = type("W", (), {"size_nm": 500.0})()
    ship.update(1.0, frigate, world)
    assert len(ship.pending_asm) == 0


def test_warship_sunk_after_three_hits():
    ship = SurfaceShip(10.0, 10.0, random.Random(3), hostile=True)
    assert ship.sunk is False
    ship.hit()
    ship.hit()
    assert ship.sunk is False
    ship.hit()
    assert ship.sunk is True
    assert ship.lofar_lines(0.0) == []


def test_warship_lofar_lines_and_broadband():
    ship = SurfaceShip(10.0, 10.0, random.Random(4), hostile=True)
    ship.speed = 18.0
    lines = ship.lofar_lines(0.0)
    assert len(lines) >= 1
    for freq, amp, width in lines:
        assert freq > 0.0
        assert 0.0 < amp <= 1.0
    bb = ship.broadband()
    assert 0.0 < bb["low_hz"] < bb["high_hz"]
    assert 0.0 <= bb["level"] <= 1.0


def test_warship_quiet_factor_bounds():
    ship = SurfaceShip(10.0, 10.0, random.Random(5), hostile=True)
    ship.speed = 24.0
    assert 0.05 <= ship.quiet_factor() <= 1.0
    ship.speed = 14.0
    assert ship.quiet_factor() > 0.05


def test_save_load_roundtrip_keeps_warships():
    g = _make_game(11, "s2_doppeljagd")
    assert g.warships
    ws = g.warships[0]
    old_id, old_x, old_y, old_course, old_damage = \
        ws.id, ws.x, ws.y, ws.course, ws.damage
    data = g.save_state()
    assert data["version"] == 8
    g2 = Game(seed=0, start_menu=False)
    g2.load_state(data)
    loaded = {w.id: w for w in g2.warships}
    assert old_id in loaded
    w2 = loaded[old_id]
    assert abs(w2.x - old_x) < 1e-6
    assert abs(w2.y - old_y) < 1e-6
    assert abs(w2.course - old_course) < 1e-6
    assert w2.damage == old_damage
    assert w2.hostile is True
    assert w2.profile.key == ws.profile.key
