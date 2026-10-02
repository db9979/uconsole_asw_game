"""The crewed boat's seeker settings: search pattern and enable point."""

import json
import math
import sys
from pathlib import Path

import pygame

from src.commander.server import V2_ACTION_REGISTRY
from src.core import uboot_local
from src.physics import torpedo_dyn
from src.weapons.torpedo import EnemyTorpedo

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _boat_apply, _crewed, _run  # noqa: E402


class _Ship:
    def __init__(self, x, y):
        self.x, self.y, self.depth = x, y, 5.0


def _torpedo(pattern="straight", enable_nm=None, datum=(0.0, -5.0)):
    return EnemyTorpedo(0.0, 0.0, 0.0, 30.0, 1, guidance_x=datum[0], guidance_y=datum[1],
                        pattern=pattern, enable_nm=enable_nm)


def test_defaults_keep_the_ai_shot():
    torpedo = _torpedo()
    assert torpedo.pattern == "straight"
    assert torpedo.enable_nm == torpedo_dyn.BOAT_ENABLE_DEFAULT_NM == 3.0
    assert _torpedo(pattern="bogus").pattern == "straight"


def test_a_late_enable_point_keeps_the_seeker_off_longer():
    ship = _Ship(50.0, 50.0)            # far away: nothing to acquire
    early, late = _torpedo(), _torpedo(enable_nm=1.0)
    for _ in range(int(200 / 0.5)):     # 2.5 NM run: 2.5 NM before the datum
        early.update(0.5, ship)
        late.update(0.5, ship)
    assert early.terminal_active and not late.terminal_active


def test_an_enabled_search_pattern_turns_the_torpedo():
    ship = _Ship(50.0, 50.0)
    straight, snake, circle = (_torpedo(pattern=p, datum=(0.0, -1.0))
                               for p in ("straight", "snake", "circle"))
    for _ in range(240):
        for torpedo in (straight, snake, circle):
            torpedo.update(0.5, ship)
    assert straight.course == 0.0
    assert snake.search_course == 0.0 and snake.search_phase > 0.0
    assert circle.turns_done > 0.0


def test_the_weapons_station_sets_the_seeker_for_the_next_shots():
    game, _server, bridge = _crewed(seed=83)
    apply = _boat_apply(game, bridge)
    boat, sub = game.opfor, game.opfor.sub
    assert V2_ACTION_REGISTRY["uboot_torpedo_settings"].stations == {"uboot_weapons"}
    valid = V2_ACTION_REGISTRY["uboot_torpedo_settings"].validate_params
    assert not valid({"pattern": "snake", "enable_nm": 0.4})
    assert not valid({"pattern": "zigzag", "enable_nm": 1.0})
    assert not valid({"pattern": "snake", "enable_nm": float("nan")})
    assert valid({"pattern": "helix", "enable_nm": 1.3})
    assert apply("uboot_torpedo_settings", {"pattern": "helix", "enable_nm": 1.3}) is True
    assert (boat.orders.torpedo_pattern, boat.orders.torpedo_enable_nm) == ("helix", 1.4)
    launcher = game.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
    bearing = (sub.course + launcher.arc_center_deg) % 360.0
    assert sub.command_fire(bearing, 5.0, now=game.sim_t) is True
    _run(game, 0.2, dt=0.05)
    shot = next(t for t in game.enemy_torpedoes if t.launch_platform_id == sub.id)
    assert (shot.pattern, shot.enable_nm) == ("helix", 1.4)
    state = game.save_state()
    entry = next(row for row in state["enemy_torpedoes"] if row["id"] == shot.id)
    assert (entry["pattern"], entry["enable_nm"]) == ("helix", 1.4)
    assert state["crew"]["orders"]["torpedo_pattern"] == "helix"
    json.dumps(state, allow_nan=False)


def test_uconsole_keys_are_the_frigate_weapons_keys(monkeypatch):
    game, _server, _bridge = _crewed(seed=83)
    game.local_side = "uboot"
    uboot_local.set_local_station(game, "uboot_weapons")
    monkeypatch.setattr(uboot_local, "station_remote", lambda _game: False)
    orders = game.opfor.orders

    def key(code):
        uboot_local.handle_key(game, pygame.event.Event(pygame.KEYDOWN, key=code, mod=0))
    key(pygame.K_x)
    assert orders.torpedo_pattern == "snake"
    key(pygame.K_COMMA)
    assert math.isclose(orders.torpedo_enable_nm, 2.8)
    key(pygame.K_PERIOD)
    key(pygame.K_PERIOD)
    assert math.isclose(orders.torpedo_enable_nm, 3.0)
    # At another station the key names the weapons station instead.
    uboot_local.set_local_station(game, "uboot_nav")
    key(pygame.K_x)
    assert orders.torpedo_pattern == "snake"
