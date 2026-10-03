"""Phase 6: submarine and surface-ship physics."""

import copy
import json
import math
import random
from types import SimpleNamespace

import pytest

from src.core.game import Game
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.physics import submarine as sub_physics


class Ocean:
    size_nm = 500.0
    sea_state = 1
    effective_sea_state = 1.0

    def __init__(self, current=(0.0, 0.0)):
        self._current = current

    def depth_m(self, *args):
        return 3000.0

    def thermocline_depth_m(self, *args):
        return 60.0

    def on_land(self, *args):
        return False

    def land_blocks_line(self, *args):
        return False

    def sonar_path_blocked(self, *args):
        return False

    def current_vec(self, *args):
        return self._current


def _sub(seed=1, depth=100.0):
    sub = Sub(100.0, 100.0, depth, 90.0, "aip_modern", random.Random(seed))
    sub.endurance = None
    return sub


def test_planes_lose_authority_at_low_speed():
    assert sub_physics.plane_authority(1.0) == sub_physics.PLANE_MIN_AUTHORITY
    assert sub_physics.plane_authority(8.0) == 1.0
    slow, fast = _sub(), _sub()
    for sub, speed in ((slow, 1.0), (fast, 8.0)):
        sub.speed = speed
        sub.target_depth = 200.0
        sub.state = "PATROLLE"
        sub.turn_left = 1e6
        for _ in range(100):
            sub._advance_depth(200.0, sub.motion.depth_rate_m_s, 0.2)
    assert fast.depth - 100.0 > 2.0 * (slow.depth - 100.0)


def test_hull_accelerates_toward_the_ordered_speed():
    sub = _sub()
    sub.speed = 0.0
    sub.state = "EVADE"
    sub.evac_left = 1000.0
    sub.update(1.0, None, Ocean())
    assert sub.speed_order > 5.0
    assert sub.speed == pytest.approx(sub.motion.acceleration_kn_s * 1.0)


def test_cavitation_onset_rises_with_depth_and_speed_raises_source_level():
    shallow, deep = _sub(depth=20.0), _sub(depth=250.0)
    speed = sub_physics.cavitation_speed_kn(shallow.cavitation_onset_kn(), 20.0) + 0.5
    shallow.speed = deep.speed = speed
    assert shallow.cavitating and not deep.cavitating
    slow = _sub()
    slow.speed = 4.0
    fast = _sub()
    fast.speed = 12.0
    assert fast.source_level_offset_db() - slow.source_level_offset_db() > 15.0
    slow.transient_left = 5.0
    assert slow.source_level_offset_db() > sub_physics.LAUNCH_TRANSIENT_DB - 8.0


def test_emergency_blow_brings_a_flooded_boat_up_once():
    sub = _sub(depth=150.0)
    sub.damage = 70.0
    sub.state = "EVADE"
    sub.evac_left = 1000.0
    sub.update(1.0, None, Ocean())
    assert sub.emergency_ascent and not sub.blow_available
    shallowest = sub.depth
    for _ in range(60):
        sub.update(1.0, None, Ocean())
        shallowest = min(shallowest, sub.depth)
    assert shallowest == pytest.approx(10.0)
    assert not sub.emergency_ascent and not sub.blow_available


def test_pressure_hull_fatigue_and_crush_depth():
    sub = _sub(depth=100.0)
    sub.depth = sub.stype.max_depth_m * 1.05
    sub._update_hull_stress(600.0)
    assert sub.hull_fatigue > 0.0
    sub.depth = sub_physics.crush_depth_m(sub.stype.max_depth_m) + 1.0
    sub._update_hull_stress(0.1)
    assert sub.state == "SINKING"


@pytest.mark.parametrize("current", [(1.0, 0.0), (0.0, 1.0), (-0.7, -0.7)])
def test_lurking_boat_holds_station_against_the_current(current):
    # (east, north) knots: a north set used to be followed, not stemmed.
    world = Ocean(current=current)
    sub = _sub()
    sub.state = "LAUER"
    sub.evac_left = 1e6
    sub.speed = 0.5
    start = (sub.x, sub.y)
    for _ in range(1800):
        sub.update(1.0, None, world)
    drifted = math.hypot(sub.x - start[0], sub.y - start[1])
    assert drifted < 0.2        # pure drift would be 0.5 NM


def test_surface_ship_loses_speed_in_heavy_seas():
    calm_world, rough_world = Ocean(), Ocean()
    rough_world.effective_sea_state = 6.0
    speeds = []
    for world in (calm_world, rough_world):
        ship = SurfaceShip(100.0, 100.0, random.Random(3))
        ship.target_speed = ship.speed_cap_kn
        for _ in range(600):
            ship._steer(1.0, 0.5, world)
        speeds.append(ship.speed)
    assert speeds[1] < 0.95 * speeds[0]


def test_physics_state_round_trips_and_is_validated():
    game = Game(seed=6601, start_menu=False, audio_enabled=False)
    sub = game.subs[0]
    sub.blow_available = False
    sub.emergency_ascent = True
    sub.transient_left = 4.0
    sub.hull_fatigue = 0.3
    sub.speed_order = 7.5
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    twin = next(s for s in restored.subs if s.id == sub.id)
    assert (twin.blow_available, twin.emergency_ascent, twin.transient_left,
            twin.hull_fatigue, twin.speed_order) == (False, True, 4.0, 0.3, 7.5)
    for field, value in (("hull_fatigue", 2.0), ("blow_available", 1),
                         ("transient_left", -1.0)):
        broken = copy.deepcopy(state)
        broken["subs"][0][field] = value
        assert not restored._load_save_data(broken)
