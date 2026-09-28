"""A crewed boat below its test depth: bolts, seals, cracks and crush depth."""

import copy
import json
import sys
from pathlib import Path

from src.core import config, detrand
from src.core.i18n import localize
from src.physics import submarine as sub_physics
from src.ui import uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402


def _deep(seed=83):
    game, server, bridge = _crewed(seed=seed)
    game.world.depth_m = lambda x, y: 3000.0
    game.world.charted_depth_m = lambda x, y: 3000.0
    return game, game.opfor.sub


def _events(sub):
    return [key for key, _values in sub.crew._events]


def test_the_crew_may_order_the_boat_below_test_depth_but_not_past_crush_depth():
    game, sub = _deep()
    test = sub.stype.max_depth_m
    assert sub.crush_depth_m == sub_physics.crush_depth_m(test)
    assert sub.set_orders(depth=test * 1.2) is True
    assert sub.set_orders(depth=sub.crush_depth_m + 1.0) == "invalid_value"
    sub.depth = sub.target_depth = test - 5.0
    sub.set_orders(speed=4.0, depth=test * 1.2)
    _run(game, 60)
    assert sub.beyond_test_depth() and sub.depth <= test * 1.2 + 1e-6
    rows = uboot_view.threats(game, game.opfor)
    assert rows[0][0]["__u_jagd_i18n__"] == "uboot.threat.overdepth"
    assert "BELOW TEST DEPTH" in str(localize(rows[0][0], game.tr))


def test_below_test_depth_the_hull_fails_far_faster_than_near_it():
    test = 200.0
    assert sub_physics.overdepth_rate_per_s(test, test) == 0.0
    shallow = sub_physics.overdepth_rate_per_s(test * 1.1, test)
    deep = sub_physics.overdepth_rate_per_s(test * 1.4, test)
    assert 1.0 / 600.0 < shallow < 1.0 / 180.0 and deep > 10.0 * shallow
    game, sub = _deep()
    sub.depth = sub.target_depth = sub.order_depth = sub.stype.max_depth_m * 1.25
    sub.set_orders(speed=0.0, depth=sub.depth)
    _run(game, 180)
    assert sub.damage_control.hits >= 1 and sub.damage > 0.0
    assert any(c.leak > 0.0 for c in sub.damage_control.compartments)


def test_hull_failures_are_deterministic_and_a_crack_floods():
    outcomes = []
    for _ in range(2):
        game, sub = _deep(seed=91)
        sub.depth = sub.stype.max_depth_m * 1.45
        row = []
        for _ in range(6):
            sub.crew._events.clear()
            before = sub.damage
            sub._hull_failure(1.45)
            kind = next(key for key in _events(sub) if key.startswith("hull_"))
            row.append((kind, round(sub.damage - before, 6),
                        [round(c.leak, 6) for c in sub.damage_control.compartments]))
            if sub.damage >= 60.0:
                break
        outcomes.append(row)
    assert outcomes[0] == outcomes[1]
    kinds = {kind for kind, _damage, _leaks in outcomes[0]}
    assert kinds <= {"hull_bolts", "hull_seal", "hull_fracture"}
    # A crack holes the struck compartment fully and its neighbour as well.
    game, sub = _deep(seed=91)
    fracture = next((i for i in range(64) if detrand.u01(sub.sensor_seed, "hull-failure", i)
                     < config.UBOOT_HULL_FRACTURE_MAX), None)
    assert fracture is not None
    sub.damage_control.hits = fracture
    sub._hull_failure(1.5)
    leaks = sorted(c.leak for c in sub.damage_control.compartments)
    assert leaks[-1] == 1.0 and leaks[-2] >= 0.6
    assert sub.damage == config.UBOOT_HULL_FRACTURE_DAMAGE
    _run(game, 5)
    assert sub.damage_control.total_water_kg() > 0.0


def test_just_past_test_depth_there_is_no_crack():
    game, sub = _deep(seed=92)
    for _ in range(12):
        sub._hull_failure(1.0)
    assert "hull_fracture" not in _events(sub)
    assert all(c.fire == 0.0 for c in sub.damage_control.compartments)


def test_crush_depth_collapses_the_boat():
    game, sub = _deep()
    sub.depth = sub.target_depth = sub.crush_depth_m + 0.5
    sub._update_hull_stress(0.1)
    assert sub.state == "SINKING" and "hull_collapse" in _events(sub)


def test_the_ai_boat_keeps_its_limits():
    game, sub = _deep()
    sub.release_manual()
    assert sub.set_orders(depth=sub.stype.max_depth_m * 1.2) in ("not_ready", "invalid_value")
    sub.depth = sub.stype.max_depth_m * 1.2
    rate = sub_physics.fatigue_rate_per_s(sub.depth, sub.stype.max_depth_m)
    before = sub.hull_fatigue
    sub._update_hull_stress(1.0)
    assert abs(sub.hull_fatigue - (before + rate)) < 1e-12


def test_the_depth_projection_and_a_save_carry_the_crush_depth_and_the_damage():
    game, sub = _deep(seed=93)
    from src.commander.projections import _uboot
    nav = _uboot(game, game.opfor, [], None, {})["navigation"]
    assert nav["crush_depth_m"] == sub.crush_depth_m > nav["max_depth_m"]
    sub.depth = sub.target_depth = sub.order_depth = sub.stype.max_depth_m * 1.3
    sub._hull_failure(1.3)
    data = json.loads(json.dumps(game.save_state()))
    fatigue, hits = sub.hull_fatigue, sub.damage_control.hits
    leaks = [c.leak for c in sub.damage_control.compartments]
    assert game._load_save_data(copy.deepcopy(data))
    loaded = game.opfor.sub
    assert (loaded.hull_fatigue, loaded.damage_control.hits) == (fatigue, hits)
    assert [c.leak for c in loaded.damage_control.compartments] == leaks
    assert loaded.beyond_test_depth()
