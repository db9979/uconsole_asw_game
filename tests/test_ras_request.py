"""Replenishment at sea on request, delivered in loads (1.3.67)."""

from src.commander import actions, projections
from src.core import config
from src.core.game import Game
from src.weapons import depth_charge


def _game(seed=4101):
    game = Game(seed=seed, start_menu=False, audio_enabled=False)
    game.tasking.next_offer_t = 1e9     # no scheduled offers in these tests
    return game


def _alongside(game, tanker, seconds, dt=0.5):
    for _ in range(int(seconds / dt)):
        game.ship.x, game.ship.y = tanker.x + 0.1, tanker.y
        game.ship.speed = tanker.speed
        game.sim_t += dt
        game._update_tasking(dt)


def _spend(game):
    game.ship.fuel_kg = 0.5 * game.ship.fuel_capacity_kg
    for _ in range(3):
        game.player_torpedo_battery.fire()
    game.torpedo_count = game.player_torpedo_battery.remaining_total
    game.own_asrocs_left = 0
    game.depth_charges_left = 3
    game.nixie_store.ready = game.nixie_store.stowed = 0
    game.ciws_ammo = 0


def test_request_needs_a_shortfall_and_offers_an_accepted_task():
    game = _game()
    assert not game.ras_needed()
    assert game.request_ras() == "ras_full"
    assert projections._radio(game, [], {})["can_request_ras"] is False
    game.depth_charges_left -= 1
    assert projections._radio(game, [], {})["can_request_ras"] is True
    assert game.request_ras() is True
    (task,) = game.tasking.tasks
    assert task["kind"] == "ras" and task["state"] == "active"
    assert game.civilians[-1].id == task["target_id"]
    assert game.request_ras() == "ras_open"


def test_stores_come_over_in_loads_and_a_breakaway_keeps_them():
    game = _game()
    _spend(game)
    assert game.request_ras() is True
    task = game.tasking.tasks[-1]
    tanker = game.civilians[-1]
    fuel = game.ship.fuel_kg
    # Two of five loads, then the ship breaks away.
    _alongside(game, tanker, config.TASK_RAS_S * 2 / config.TASK_RAS_LOADS + 1.0)
    assert fuel < game.ship.fuel_kg < game.ship.fuel_capacity_kg
    assert 0 < game.own_asrocs_left < depth_charge.OWN_ASROC_STOCK
    assert 3 < game.depth_charges_left < depth_charge.DEPTH_CHARGE_STOCK
    kept = (game.torpedo_count, game.own_asrocs_left, game.depth_charges_left,
            game.ciws_ammo)
    game.ship.x += 5.0
    game.sim_t += 60.0
    game._update_tasking(60.0)
    assert (game.torpedo_count, game.own_asrocs_left, game.depth_charges_left,
            game.ciws_ammo) == kept
    assert task["state"] == "active"


def test_a_full_transfer_fills_every_store_but_not_the_vls():
    game = _game()
    _spend(game)
    game.vls_cells -= 2
    cells = game.vls_cells
    assert game.request_ras() is True
    task = game.tasking.tasks[-1]
    _alongside(game, game.civilians[-1], config.TASK_RAS_S + 2.0)
    assert task["state"] == "done"
    assert game.ship.fuel_kg == game.ship.fuel_capacity_kg
    assert game.torpedo_count == game.torpedo_total
    assert game.own_asrocs_left == depth_charge.OWN_ASROC_STOCK
    assert game.depth_charges_left == depth_charge.DEPTH_CHARGE_STOCK
    assert game.nixie_store.remaining_total == game.nixie_store.capacity
    assert game.nixie_store.ready + len(game.nixie_store.loading) > 0
    assert game.ciws_ammo == game._air_defense_loadout["ciws"]["ammo"]
    assert game.vls_cells == cells
    # A fresh request waits for the cooldown after the last one ended.
    game.depth_charges_left -= 1
    assert game.request_ras() == "ras_cooldown"
    game.sim_t += config.TASK_RAS_REQUEST_COOLDOWN_S
    assert game.request_ras() is True


def test_radio_down_and_remote_request(monkeypatch):
    game = _game()
    game.depth_charges_left -= 1
    monkeypatch.setattr(game.damage, "station_down", lambda key: key == "radio")
    assert game.request_ras() == "radio_down"
    assert actions._radio_request_ras(game, {}, {}) == "radio_down"
    monkeypatch.undo()
    assert actions._radio_request_ras(game, {}, {}) is True
    assert actions._radio_request_ras(game, {}, {}) == "not_ready"


def test_ras_candidate_counts_spent_asw_stores():
    game = _game()
    assert not game._task_candidate_ras()
    game.own_asrocs_left -= 1
    assert game._task_candidate_ras()
