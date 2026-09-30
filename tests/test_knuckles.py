"""Knuckles: bubble slicks of hard turns at speed (both sides)."""

import json
import math

from src.core.game import Game
from src.sonar import propagation
from src.weapons.torpedo import EnemyTorpedo
from src.world import knuckles
from src.world.knuckles import KnuckleField


def _game(seed=5):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9
    return game


def test_only_a_hard_turn_at_speed_lays_one_spaced_knuckle():
    field = KnuckleField()
    assert field.observe("frigate", 0, 0, 8.0, 2.0, 0.0) is None     # too slow
    assert field.observe("frigate", 0, 0, 25.0, 0.3, 0.0) is None    # no turn
    first = field.observe("frigate", 0, 0, 25.0, 1.9, 0.0)
    assert first is not None and first["strength"] > 0.5
    assert field.observe("frigate", 0, 0, 25.0, 1.9, 5.0) is None    # spacing
    assert field.observe(7, 1, 1, 16.0, 1.5, 5.0) is not None         # any platform
    field.advance(knuckles.LIFE_S + 6.0)
    assert field.items == []


def test_knuckle_masks_a_path_through_it_and_fades():
    field = KnuckleField()
    field.observe("frigate", 1.0, 0.0, 25.0, 1.9, 0.0)
    field.advance(0.0)
    through = field.path_loss_db(0.0, 0.0, 2.0, 0.0)
    assert through > 6.0
    assert field.path_loss_db(0.0, 1.0, 2.0, 1.0) == 0.0
    field.advance(200.0)
    assert field.path_loss_db(0.0, 0.0, 2.0, 0.0) < through / 3.0


def test_ray_excess_adds_the_bubble_loss():
    game = _game()
    ship = game.ship
    far = (ship.x + 3.0, ship.y)
    clear = propagation.ray_excess_db(game.world, ship.x, ship.y, 6.0, *far, 60.0, 400.0)
    game.world.knuckles.observe(3, ship.x + 1.5, ship.y, 20.0, 1.5, game.sim_t)
    game.world.knuckles.advance(game.sim_t)
    masked = propagation.ray_excess_db(game.world, ship.x, ship.y, 6.0, *far, 60.0, 400.0)
    assert clear is not None and masked > clear + 5.0


def test_frigate_hard_turn_lays_a_knuckle_and_it_is_saved():
    game = _game()
    ship = game.ship
    ship.speed = ship.target_speed = 26.0
    ship.target_course = (ship.course + 160.0) % 360.0
    for _ in range(240):
        game.update(0.25)
    assert any(item["owner"] == "frigate" for item in game.world.knuckles.items)
    state = json.loads(json.dumps(game.save_state()))
    assert state["knuckles"]
    other = _game()
    assert other._load_save_data(state)
    assert other.world.knuckles.items == game.world.knuckles.items
    bad = json.loads(json.dumps(state))
    bad["knuckles"][0]["strength"] = 2.0
    assert not other._load_save_data(bad)


def test_ping_hears_the_knuckle_as_a_false_echo():
    game = _game()
    ship = game.ship
    game.world.knuckles.observe(9, ship.x + 1.0, ship.y, 26.0, 1.9, game.sim_t)
    game.world.knuckles.advance(game.sim_t)
    sonar = game.sonar
    sonar._pending_clutter.clear()
    sonar._queue_clutter(ship, game.world, game.sim_t, 1.0, "BOW")
    assert any(abs(echo["snapshot"]["bearing"] - 90.0) < 20.0
               for echo in sonar._pending_clutter)


def test_wake_homing_torpedo_is_drawn_into_a_strong_knuckle():
    game = _game()
    ship = game.ship
    field = game.world.knuckles
    field.items = [dict(owner="frigate", x=ship.x, y=ship.y - 1.0, t=game.sim_t,
                        strength=1.0)]
    field.advance(game.sim_t)
    lured = [key for key in range(40) if field.lure(ship.x + 0.05, ship.y - 1.0, key)]
    assert 0 < len(lured) < 40
    assert field.lure(ship.x + 1.0, ship.y - 1.0, lured[0]) is None
    assert EnemyTorpedo is not None and math.isfinite(field.items[0]["x"])


def test_a_wreck_moves_the_mad_needle_without_a_contact():
    game = _game()
    wreck = next((h for h in game.world.charted_hazards() if h.kind == "wreck"), None)
    if wreck is None:
        return
    before = set(game.sonar.contacts)
    for tick in range(40):
        game._mad_wreck_anomalies(wreck.x_nm, wreck.y_nm, 30.0, "mad", tick,
                                  "runtime.helo.mad_anomaly")
    if wreck.top_depth_m + 30.0 <= 250.0:
        assert game._mad_wreck_heard
    assert set(game.sonar.contacts) == before


def test_rocks_return_clutter_too():
    from src.sonar import sonar as sonar_module
    game = _game()
    rock = next((h for h in game.world.charted_hazards() if h.kind == "rock"), None)
    if rock is None:
        return
    echo = sonar_module._RockEcho(0, rock, game.world.ocean.seed)
    assert echo.extra_ts_db < sonar_module._WreckEcho.extra_ts_db
