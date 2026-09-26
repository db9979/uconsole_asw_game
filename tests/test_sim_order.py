"""The stage order of one simulation substep is a contract (plan 1.3, phase 2)."""

from src.core.game import Game
from src.core.game_sim import SIM_ORDER


def test_update_sim_runs_its_stages_in_the_frozen_order(monkeypatch):
    game = Game(seed=31, start_menu=False, audio_enabled=False)
    for _ in range(3):
        game._update_sim(0.1)
    calls = []
    for name in SIM_ORDER:
        original = getattr(game, name)

        def record(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(game, name, record)
    # Prime every cadence accumulator so each stage fires in this substep.
    game._sensor_acc = game._esm_acc = game._radio_acc = game._slow_acc = 0.5
    game._update_sim(0.1)
    assert [name for name in calls if name in SIM_ORDER] == list(SIM_ORDER)


def test_sim_order_names_are_methods_of_game():
    assert all(callable(getattr(Game, name)) for name in SIM_ORDER)
