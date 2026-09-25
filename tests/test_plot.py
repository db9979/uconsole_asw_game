"""Shared operator plot layer: geometry, strict schema, save v14, controls, web."""

import copy
import hashlib
import json
import math

import pygame
import pytest

from src.commander import bridge, server
from src.commander.projections import _plot as plot_projection
from src.core import config, plot
from src.core.game import Game
from src.core.station import Station
from src.ui import layout


@pytest.fixture
def game():
    return Game(seed=4242, start_menu=False, audio_enabled=False)


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))


def test_geometry_bearing_distance_dr_and_cpa():
    brg, dist = plot.bearing_distance(10.0, 10.0, 13.0, 6.0)
    assert brg == pytest.approx(math.degrees(math.atan2(3, 4)))
    assert dist == pytest.approx(5.0)
    item = {"kind": "dr", "t": 100.0, "x": 0.0, "y": 0.0, "course": 90.0, "speed_kn": 36.0}
    assert plot.dr_position(item, 200.0) == pytest.approx((1.0, 0.0))
    # Target runs east along y=0 from x=0; own ship sits still 2 NM south of x=3.
    distance, seconds = plot.cpa(item, 100.0, 3.0, 2.0, 0.0, 0.0)
    assert distance == pytest.approx(2.0) and seconds == pytest.approx(300.0)
    # Opening geometry: the CPA is now.
    distance, seconds = plot.cpa(item, 100.0, -3.0, 0.0, 0.0, 0.0)
    assert seconds == 0.0 and distance == pytest.approx(3.0)


def test_layer_is_strict_bounded_and_labels_default():
    layer = plot.PlotLayer()
    assert layer.add({"kind": "mark", "t": 0.0, "x": 1, "y": 2}) == 1
    assert layer.objects[0]["label"] == "M1" and type(layer.objects[0]["x"]) is float
    for bad in ({"kind": "mark", "t": 0.0, "x": math.nan, "y": 2},
                {"kind": "mark", "t": 0.0, "x": 1, "y": 2, "extra": 1},
                {"kind": "circle", "t": 0.0, "x": 1, "y": 2, "radius_nm": 0},
                {"kind": "dr", "t": 0.0, "x": 1, "y": 2, "course": 360, "speed_kn": 5},
                {"kind": "mark", "t": 0.0, "x": 1, "y": 2, "label": "x" * 25},
                {"kind": "mark", "t": 0.0, "x": 1, "y": 2, "label": "a\nb"},
                {"kind": "bogus", "t": 0.0, "x": 1, "y": 2}):
        assert layer.add(bad) == "invalid_value"
    for _ in range(plot.MAX_OBJECTS - 1):
        layer.add({"kind": "mark", "t": 0.0, "x": 1, "y": 2})
    assert layer.add({"kind": "mark", "t": 0.0, "x": 1, "y": 2}) == "full"
    assert layer.relabel(1, "DATUM") and layer.objects[0]["label"] == "DATUM"
    assert layer.relabel(1, "") and layer.objects[0]["label"] == "M1"
    assert layer.remove(1) and not layer.remove(1)
    assert plot.PlotLayer.valid_save(layer.to_save())


def test_save_round_trip_and_invalid_plot_is_rejected(game):
    game.plot_add("ruler", 100.0, 100.0, "R", x2=104.0, y2=97.0)
    game.plot_add("dr", 90.0, 90.0, course=45.0, speed_kn=12.0)
    state = json.loads(json.dumps(game.save_state()))
    assert state["plot"]["next_id"] == 3
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.plot.objects == game.plot.objects and restored.plot.next_id == 3
    for mutate in (lambda s: s["plot"]["objects"][0].update(x=math.inf),
                   lambda s: s["plot"].update(next_id=2),
                   lambda s: s["plot"]["objects"].append(dict(s["plot"]["objects"][0])),
                   lambda s: s["plot"].pop("objects"),
                   lambda s: s.pop("plot")):
        broken = copy.deepcopy(state)
        mutate(broken)
        assert not restored._load_save_data(broken)
    assert restored.plot.objects == game.plot.objects


def test_plot_never_changes_the_simulation():
    from src.enemies.animal import Animal
    from src.enemies.decoy import Decoy
    from src.enemies.sub import Sub
    from src.enemies.surface import SurfaceShip
    from src.weapons.torpedo import EnemyTorpedo
    counters = {cls: cls._next_id for cls in (Sub, Animal, SurfaceShip, Decoy,
                                              EnemyTorpedo)}
    digests = []
    for drawn in (False, True):
        for cls, value in counters.items():   # entity IDs are process-global
            cls._next_id = value
        game = Game(seed=909, start_menu=False, audio_enabled=False)
        if drawn:
            game.plot_add("mark", game.ship.x + 3.0, game.ship.y)
            game.plot_add("dr", game.ship.x, game.ship.y - 5.0, course=180.0,
                          speed_kn=10.0)
        for _ in range(40):
            game.update(.25)
        state = game.save_state()
        state.pop("plot")
        text = json.dumps(state, sort_keys=True, default=str)
        # Compare digests: a failing diff of two 1 MB strings takes minutes.
        digests.append(hashlib.sha256(text.encode()).hexdigest())
    assert digests[0] == digests[1]


def test_keyboard_plot_mode_places_every_tool(game):
    game.station = Station.BRIDGE
    _key(game, pygame.K_p)
    assert game.plot_mode and game.plot_cursor == (game.ship.x, game.ship.y)
    _key(game, pygame.K_UP, pygame.KMOD_SHIFT)
    _key(game, pygame.K_RETURN)                                   # M1
    _key(game, pygame.K_r)
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_RIGHT, pygame.KMOD_SHIFT)
    _key(game, pygame.K_RETURN)                                   # R2
    _key(game, pygame.K_b)
    _key(game, pygame.K_RETURN)                                   # B3 from own ship
    _key(game, pygame.K_c)
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_DOWN)
    _key(game, pygame.K_RETURN)                                   # C4
    _key(game, pygame.K_d)
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_LEFT, pygame.KMOD_SHIFT)
    _key(game, pygame.K_RETURN)
    assert game.input_mode == "plot_speed"
    for key in (pygame.K_8, pygame.K_PERIOD, pygame.K_5, pygame.K_RETURN):
        _key(game, key)
    kinds = [item["kind"] for item in game.plot.objects]
    assert kinds == ["mark", "ruler", "bearing", "circle", "dr"]
    bearing = game.plot.objects[2]
    assert (bearing["x"], bearing["y"]) == (game.ship.x, game.ship.y)
    assert game.plot.objects[4]["speed_kn"] == 8.5 and game.plot.objects[4]["course"] == 270.0
    assert game.plot.objects[1]["x2"] > game.plot.objects[1]["x"]
    # Backspace erases the object nearest the cursor; Shift clears everything.
    _key(game, pygame.K_BACKSPACE)
    assert len(game.plot.objects) == 4
    _key(game, pygame.K_BACKSPACE, pygame.KMOD_SHIFT)
    assert game.plot.objects == []
    # Esc leaves plot mode first; the next Esc is the normal quit prompt.
    _key(game, pygame.K_ESCAPE)
    assert not game.plot_mode and not game.quit_confirm
    _key(game, pygame.K_ESCAPE)
    assert game.quit_confirm


def test_plot_mode_needs_a_chart_and_owns_arrow_keys(game):
    game.station = Station.SONAR
    _key(game, pygame.K_p)
    assert not game.plot_mode
    game.station = Station.OPZ
    _key(game, pygame.K_p)
    assert game.plot_mode
    course = game.ship.target_course
    _key(game, pygame.K_LEFT)
    assert game.ship.target_course == course
    _key(game, pygame.K_2)                                        # station change
    _key(game, pygame.K_RETURN)
    assert not game.plot_mode and game.plot.objects == []


@pytest.mark.parametrize("station", [Station.BRIDGE, Station.OPZ])
def test_plot_draws_inside_the_chart_without_ellipsis(game, station):
    game.station = station
    game.plot_add("ruler", game.ship.x, game.ship.y, x2=game.ship.x + 4, y2=game.ship.y)
    game.plot_add("bearing", game.ship.x, game.ship.y, bearing=45.0)
    game.plot_add("circle", game.ship.x, game.ship.y, radius_nm=3.0)
    game.plot_add("dr", game.ship.x + 5, game.ship.y, course=270.0, speed_kn=10.0)
    game.toggle_plot_mode()
    with layout.capture_text() as texts:
        game.draw()
    plotted = [row for row in texts if row["text"].startswith(("R1", "B2", "C3", "D4"))]
    assert len(plotted) == 4
    assert all(row["bounds"].contains(row["rect"]) for row in plotted)
    assert not any("…" in row["text"] for row in texts)


def test_remote_commands_validate_strictly_and_apply(game):
    actions = server.V2_ACTION_REGISTRY
    assert all(actions[name].stations == frozenset(server.STATIONS)
               for name in ("plot_add", "plot_remove", "plot_relabel", "plot_clear"))
    check = actions["plot_add"].validate_params
    assert check({"shape": "circle", "x": 10, "y": 10, "label": "", "radius_nm": 2.5})
    assert not check({"kind": "circle", "x": 10, "y": 10, "label": "", "radius_nm": 2.5})
    assert not check({"shape": "circle", "x": 10, "y": 10, "label": "", "radius_nm": 2.5, "t": 0})
    assert not check({"shape": "circle", "x": 10, "y": 10, "label": "", "radius_nm": 900})
    assert not check({"shape": "mark", "x": True, "y": 10, "label": ""})
    assert not check({"shape": "mark", "x": 1e9, "y": 10, "label": ""})
    assert actions["plot_relabel"].validate_params({"id": 3, "label": "DATUM"})
    assert not actions["plot_relabel"].validate_params({"id": 0, "label": "DATUM"})
    handlers = bridge._V2_ACTION_HANDLERS
    assert handlers["plot_add"](game, {"shape": "mark", "x": 10.0, "y": 11.0,
                                       "label": "WX"}, None) is True
    assert handlers["plot_relabel"](game, {"id": 1, "label": "DATUM"}, None) is True
    assert handlers["plot_remove"](game, {"id": 99}, None) == "stale_ref"
    projected = plot_projection(game)
    assert projected["objects"] == [{"id": 1, "shape": "mark", "label": "DATUM",
                                     "t": 0.0, "x": 10.0, "y": 11.0}]
    game.plot_add("dr", 10.0, 10.0, course=0.0, speed_kn=10.0)
    row = plot_projection(game)["objects"][1]
    assert {"now_x", "now_y", "cpa_nm", "cpa_s"} <= set(row)
    assert handlers["plot_clear"](game, {}, None) is True and game.plot.objects == []
    for _ in range(plot.MAX_OBJECTS):
        game.plot_add("mark", 1.0, 1.0)
    assert handlers["plot_add"](game, {"shape": "mark", "x": 1.0, "y": 1.0,
                                       "label": ""}, None) == "active_limit"
