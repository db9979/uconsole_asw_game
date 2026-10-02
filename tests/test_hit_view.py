"""The hit picture: a hit in sight or only heard opens a small window."""

import sys
from pathlib import Path

import pygame

from src.core import hit_view
from src.core.hit_view import HitTracker
from src.ui import hit_inset

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _row(at, kind="blast", size=40.0, bearing=45.0):
    return dict(kind=kind, bearing=bearing, range_nm=3.0, at_s=at, dur_s=20.0, size_m=size, level=1.0)


def test_a_hit_in_sight_shows_for_a_few_seconds():
    tracker = HitTracker()
    assert tracker.update("a", 10.0, [_row(5.0)], []) is None      # a new world: only marks
    view = tracker.update("a", 21.0, [_row(5.0), _row(20.0)], [])
    assert view["mode"] == "sight" and view["bearing"] == 45.0 and view["age_s"] == 1.0
    assert tracker.update("a", 20.0 + hit_view.SHOW_S + 0.1, [_row(20.0)], []) is None


def test_depth_charge_columns_are_not_hits():
    tracker = HitTracker()
    tracker.update("a", 0.0, [], [])
    assert tracker.update("a", 1.0, [_row(0.5, "column", 70.0)], []) is None
    assert tracker.update("a", 2.0, [_row(1.5, "column", 110.0)], [])["mode"] == "sight"


def test_a_heard_hit_shows_the_bearing_unless_the_eye_has_it():
    tracker = HitTracker()
    tracker.update("a", 0.0, [], [dict(seq=1, key="contact", bearing=10)])
    view = tracker.update("a", 3.0, [], [dict(seq=2, key="breakup", bearing=120)])
    assert view == dict(mode="sonar", bearing=120.0, kind="breakup", start=3.0, age_s=0.0)
    seen = HitTracker()
    seen.update("b", 0.0, [], [])
    seen.update("b", 4.0, [_row(3.5)], [])
    assert seen.update("b", 4.5, [_row(3.5)], [dict(seq=1, key="hit", bearing=45)])["mode"] == "sight"


def test_the_window_draws_and_reaches_the_browser():
    game, _server, _bridge = _crewed(seed=71)
    ship = game.ship
    assert hit_view.current(game, "frigate") is None
    game.sight_events.ship_hit(type("Hulk", (), dict(x=ship.x + 2.0, y=ship.y, sunk=False,
                                                     hull_length_m=120.0))(), game.sim_t)
    game.sim_t += 0.5
    surface = pygame.Surface((1280, 720))
    surface.fill((0, 0, 0))
    hit_inset.draw(game, surface, "frigate")
    assert surface.get_at(hit_inset.RECT.center)[:3] != (0, 0, 0)
    from src.commander import projections
    shown = projections._hit_view(game, "frigate")
    assert shown["mode"] == "sight" and round(shown["bearing"]) == 90
    assert shown["sky"] is not None and isinstance(shown["events"], list)
    script = (ROOT / "data/commander/js/app/bindings.js").read_text(encoding="utf-8")
    assert "syncHitView(state)" in script


def test_the_sonar_picture_draws():
    surface = pygame.Surface((320, 170))
    hit_inset.draw_sonar(surface, surface.get_rect(), 90.0, 2.0)
    assert surface.get_at((160, 2))[:3] != hit_inset.BACK
