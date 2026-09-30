"""Water columns, fire and sinkings in the eyepieces (display only)."""

import math

import pygame

from src.core import sight_events
from src.core.sight_events import SightEvents
from src.ui import sight_events_view, sight_scene


class _Ship:
    def __init__(self, x, y, length=120.0):
        self.x, self.y, self.hull_length_m, self.sunk = x, y, length, False


def test_detonation_column_is_seen_within_visibility_and_horizon():
    events = SightEvents()
    events.detonation(0.0, -2.0, 10.0, "depth_charge", depth_m=30.0)
    rows = events.visible(0.0, 0.0, 18.0, 12.0, visibility_nm=10.0)
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "column" and abs(row["bearing"]) < 1e-6 and row["range_nm"] == 2.0
    assert set(row) == {"kind", "bearing", "range_nm", "at_s", "dur_s", "size_m", "level"}
    # Fog hides it; so does the horizon of a low eye far off.
    assert events.visible(0.0, 0.0, 18.0, 12.0, visibility_nm=1.0) == []
    far = SightEvents()
    far.detonation(0.0, -30.0, 10.0, "rbu")
    assert far.visible(0.0, 0.0, 2.5, 12.0, visibility_nm=30.0) == []


def test_deep_detonation_throws_no_column_and_list_is_bounded():
    events = SightEvents()
    events.detonation(0.0, 1.0, 0.0, "torpedo", depth_m=sight_events.COLUMN_DEPTH_MAX_M + 1)
    assert events.events == []
    for index in range(sight_events.EVENTS_MAX + 5):
        events.detonation(0.0, 1.0 + index * 0.01, float(index), "rbu")
    assert len(events.events) == sight_events.EVENTS_MAX
    assert len(events.visible(0.0, 0.0, 18.0, 30.0, visibility_nm=30.0)) <= sight_events.ROWS_MAX


def test_fire_follows_ship_and_turns_into_sinking():
    events = SightEvents()
    ship = _Ship(0.0, -3.0)
    events.ship_hit(ship, 0.0)
    assert [event.kind for event in events.events] == ["column", "fire"]
    ship.x = 0.5
    events.refresh(10.0)
    fire = next(event for event in events.events if event.kind == "fire")
    assert fire.x == 0.5 and 0.0 < fire.level < 1.0
    ship.sunk = True
    events.refresh(20.0)
    assert any(event.kind == "sinking" for event in events.events)
    events.refresh(20.0 + sight_events.FIRE_S + sight_events.SINKING_S)
    assert events.events == []


def test_own_hull_is_not_in_own_picture_and_own_fire_follows_damage():
    events = SightEvents()
    own = _Ship(0.0, 0.0)
    events.ship_hit(own, 0.0, blast=True)
    assert events.visible(0.0, 0.0, 18.0, 1.0, visibility_nm=30.0, exclude=own) == []
    events.refresh(400.0, lambda ship: 0.6 if ship is own else None)
    fire = next(event for event in events.events if event.kind == "fire")
    assert fire.level == 0.6
    events.refresh(2000.0, lambda ship: 0.6 if ship is own else None)
    assert any(event.kind == "fire" for event in events.events)


def test_events_draw_without_error_day_and_night():
    surface = pygame.Surface((400, 200))
    for light in (1.0, 0.0):
        sky = dict(sight_scene.plain_sky(light < 0.5))
        view = sight_scene.View((0, 0, 400, 200), 0.0, 30.0, 100, 0.0)
        colors = sight_scene.draw_scene(surface, view, sky, visibility_nm=20.0, sea_state=2.0, t=5.0)
        rows = [dict(kind=kind, bearing=bearing, range_nm=1.5, at_s=0.0, dur_s=100.0,
                     size_m=100.0, level=0.8)
                for kind, bearing in (("column", -8.0), ("blast", -3.0), ("fire", 3.0),
                                      ("sinking", 8.0))]
        before = pygame.image.tobytes(surface, "RGB")
        sight_events_view.draw_events(surface, view, colors, sky, rows, 4.0)
        assert pygame.image.tobytes(surface, "RGB") != before


def test_game_publishes_frigate_rows_after_a_depth_charge():
    from src.core.game import Game
    game = Game(seed=5, start_menu=False, show_splash=False, fullscreen=False,
                audio_enabled=False)
    try:
        bearing = math.radians(game.ship.course)
        x = game.ship.x + 1.0 * math.sin(bearing)
        y = game.ship.y - 1.0 * math.cos(bearing)
        game.sight_events.detonation(x, y, game.sim_t, "depth_charge", 20.0)
        rows = sight_events.frigate_rows(game)
        assert rows and rows[0]["kind"] == "column"
        from src.commander import projections
        published = projections._sight_events(rows, game.sim_t)
        assert set(published[0]) == {"type", "bearing", "range_nm", "age_s", "dur_s",
                                     "size_m", "level"}
    finally:
        game.commander.stop()
        game.audio.shutdown()
