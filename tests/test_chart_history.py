"""Own track and contact history on the charts: sampled, bounded, display-only."""

from types import SimpleNamespace

import pytest

from src.core import chart_history
from src.core.chart_history import ChartHistory


def _game(t, x=100.0, y=100.0, tracks=(), contacts=()):
    return SimpleNamespace(
        sim_t=t, world=WORLD, ship=SimpleNamespace(x=x, y=y),
        radar_tracks=lambda: list(tracks),
        sonar=SimpleNamespace(active_contacts=lambda: list(contacts)))


WORLD = object()


def test_own_track_is_sampled_on_simulation_time_and_bounded():
    history = ChartHistory()
    for step in range(0, 3 * chart_history.OWN_POINTS):
        history.record(_game(step * 15.0, x=100.0 + step * 0.01))
    own = history.sides["frigate"].own
    assert len(own) == chart_history.OWN_POINTS
    # One point per 30 s step, never one per frame.
    assert own[-1][0] - own[-2][0] == pytest.approx(0.02)


def test_positioned_track_and_bearings_are_kept_per_minute():
    history = ChartHistory()
    track = dict(track_id="R1", x=110.0, y=105.0)
    contact = SimpleNamespace(id=3, passive_bearing=45.0, bearing=45.0,
                              observed_x=None, observed_y=None, x=None, y=None)
    for second in range(0, 600, 5):
        history.record(_game(float(second), tracks=[track], contacts=[contact]))
    side = history.sides["frigate"]
    assert len(side.positions(("track", "R1"))) == 10
    assert len(side.bearing_history(3)) == chart_history.BEARING_POINTS


def test_load_or_new_world_starts_the_history_anew():
    history = ChartHistory()
    for second in range(0, 300, 10):
        history.record(_game(float(second)))
    assert history.sides["frigate"].own
    history.record(_game(10.0))                 # time went back: a load
    assert len(history.sides["frigate"].own) == 1


def test_old_tracks_are_forgotten():
    history = ChartHistory()
    history.record(_game(0.0, tracks=[dict(track_id="R1", x=1.0, y=1.0)]))
    history.record(_game(chart_history.FORGET_S + 120.0))
    assert ("track", "R1") not in history.sides["frigate"].tracks


def test_game_records_history_without_touching_the_simulation(tmp_path, monkeypatch):
    from src.core.game import Game
    monkeypatch.setenv("HOME", str(tmp_path))
    a = Game(seed=77, start_menu=False, show_splash=False, fullscreen=False,
             audio_enabled=False)
    b = Game(seed=77, start_menu=False, show_splash=False, fullscreen=False,
             audio_enabled=False)
    b.chart_history = SimpleNamespace(record=lambda game: None)
    for _ in range(40):
        a.update(0.5)
        b.update(0.5)
    assert (a.ship.x, a.ship.y, a.sim_t) == (b.ship.x, b.ship.y, b.sim_t)
    assert len(a.chart_history.sides["frigate"].own) >= 1
