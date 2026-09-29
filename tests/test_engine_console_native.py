"""The uConsole engine rooms draw a machinery control console."""

import pygame

from src.core import uboot_local
from src.core.game import Game
from src.core.station import Station
from src.ui import layout


def _geometry(game):
    with layout.capture_geometry() as shapes:
        game.draw()
    return shapes


def _lamp(shapes, title):
    return next(shape for shape in shapes if shape["kind"] == "lamp" and shape["title"] == title)


def test_frigate_engine_pages_show_dials_lamps_tank_and_sections():
    pygame.font.init()
    game = Game(seed=1234, start_menu=False, show_splash=False, fullscreen=False,
                audio_enabled=False, language="en")
    game.station = Station.ENGINE
    game.station_page = 0
    shapes = _geometry(game)
    dials = [shape for shape in shapes if shape["kind"] == "instrument"]
    assert {shape["title"] for shape in dials} >= {
        "engine.dial.speed", "engine.label.rpm", "engine.label.noise"}
    assert len([shape for shape in shapes if shape["kind"] == "lamp"]) >= 12  # 6 steps + 6 lamps

    game.damage.compartments["engine"].fire = 30.0
    game.damage.compartments["hull_left"].flood = 20.0
    game.damage.teams = {1: None, 2: "engine", 3: None}
    game.station_page = 1
    shapes = _geometry(game)
    rooms = [shape for shape in shapes if shape["kind"] == "room"]
    assert [shape["title"] for shape in rooms] == [
        f"engine.room.{key}" for key in
        ("sonar", "bridge", "weapons", "opz", "radio", "engine", "flightdeck")]
    # Bow on the left, stern on the right, the hull sides above and below.
    assert all(a["rect"].right <= b["rect"].left for a, b in zip(rooms, rooms[1:]))
    starboard = _lamp(shapes, "engine.room.hull_right")["rect"]
    port = _lamp(shapes, "engine.room.hull_left")["rect"]
    assert starboard.bottom <= rooms[0]["rect"].top and port.top >= rooms[0]["rect"].bottom
    assert any(shape["kind"] == "tank" and shape["title"] == "engine.tank.bunker" for shape in shapes)
    assert _lamp(shapes, "engine.lamp.fire") and _lamp(shapes, "engine.lamp.flooded")
    screen = pygame.Rect(0, 0, 1280, 720)
    assert all(screen.contains(shape["rect"]) for shape in shapes)


def test_submarine_plant_and_stores_pages_are_consoles():
    pygame.font.init()
    game = Game(seed=1234, start_menu=False, show_splash=False, fullscreen=False,
                audio_enabled=False, language="en")
    game.local_side = "uboot"
    game.reset(1234, "s7_geleitzug")        # a diesel-electric boat
    game.local_side = "uboot"
    game.update(.1)
    uboot_local.set_local_station(game, "uboot_engine")
    boat = game.opfor
    boat.command_page = 0
    shapes = _geometry(game)
    dials = {shape["title"] for shape in shapes if shape["kind"] == "instrument"}
    assert {"uboot.dial.speed", "uboot.label.battery", "uboot.dial.noise"} <= dials
    assert {"uboot.mode.silent", "uboot.mode.snorkel", "engine.lamp.cavitation"} <= {
        shape["title"] for shape in shapes if shape["kind"] == "lamp"}
    boat.command_page = 1
    shapes = _geometry(game)
    tanks = [shape["title"] for shape in shapes if shape["kind"] == "tank"]
    assert tanks[:2] == ["uboot.label.battery", "uboot.label.fuel"] or \
        tanks[:3] == ["uboot.label.battery", "uboot.label.aip", "uboot.label.fuel"]
    assert "uboot.label.absorber" in tanks
