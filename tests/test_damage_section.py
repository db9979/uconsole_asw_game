"""The damage-control pictures: frigate side profile and cross-section,
submarine cutaway; geometry shared with the browser and display only."""

import json
import random
import re
from pathlib import Path

import pygame
import pytest

from src.ship.damage import COMPARTMENTS, HIT_HOLE_M2, DamageModel
from src.ui import damage_section

ROOT = Path(__file__).resolve().parents[1]


def _convex(polygon) -> bool:
    signs = set()
    for a, b, c in zip(polygon, polygon[1:] + polygon[:1], polygon[2:] + polygon[:2]):
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if cross:
            signs.add(cross > 0)
    return len(signs) == 1


def test_browser_draws_the_same_geometry():
    source = (ROOT / "data/commander/js/stations/damage-section.js").read_text()
    block = re.search(r"/\* geometry:begin \*/\nexport const GEOMETRY = (.*);\n/\* geometry:end \*/",
                      source, re.S).group(1)
    assert json.loads(block) == {"frigate": damage_section.FRIGATE, "boat": damage_section.BOAT}


def test_every_compartment_has_one_convex_room():
    rooms = {**damage_section.FRIGATE["rooms"], **damage_section.FRIGATE["section"]["rooms"]}
    assert sorted(rooms) == sorted(key for key, _ in COMPARTMENTS)
    assert all(_convex(coords) for coords in rooms.values())
    assert damage_section.BOAT["order"] == ["stern", "engine", "battery", "quarters",
                                            "control", "bow"]
    assert sum(damage_section.BOAT["share"]) == pytest.approx(1.0)


@pytest.mark.parametrize("heel", [-20.0, 0.0, 12.0])
def test_room_polygons_stay_in_their_pictures(heel):
    profile, section = pygame.Rect(10, 100, 900, 250), pygame.Rect(920, 100, 250, 250)
    polygons = damage_section.frigate_room_polygons(profile, section, heel)
    for key, polygon in polygons.items():
        area = section if key.startswith("hull_") else profile
        assert all(area.collidepoint(point) for point in polygon), key


def test_profile_draws_holes_patches_and_water_without_touching_the_model():
    pygame.font.init()
    model = DamageModel(random.Random(3))
    engine, sonar, port = (model.compartments[key] for key in ("engine", "sonar", "hull_left"))
    engine.state, engine.flood, engine.fire, engine.hole_m2 = "FLUTEND", 30.0, 50.0, HIT_HOLE_M2
    sonar.state, sonar.flood, sonar.hole_m2 = "BESCHAEDIGT", 20.0, HIT_HOLE_M2 / 4
    port.state, port.flood, port.hole_m2 = "FLUTEND", 40.0, HIT_HOLE_M2
    model.teams[1] = "engine"
    assert model.inflow_pct_s("engine") > 0.0 and model.inflow_pct_s("bridge") == 0.0
    before = {key: (c.flood, c.fire, c.hole_m2, c.state) for key, c in model.compartments.items()}
    rng = model.rng.getstate()
    screen = pygame.Surface((1280, 720))
    profile = damage_section.draw_frigate_profile(screen, (10, 100, 900, 250), model, "engine")
    voids = damage_section.draw_frigate_section(screen, (920, 100, 250, 250), model, "hull_left")
    assert set(profile) | set(voids) == {key for key, _ in COMPARTMENTS}
    assert before == {key: (c.flood, c.fire, c.hole_m2, c.state)
                      for key, c in model.compartments.items()}
    assert model.rng.getstate() == rng


def test_leak_state_in_the_projection():
    from src.commander.projections import _leak_state
    model = DamageModel(random.Random(3))
    room = model.compartments["engine"]
    assert _leak_state(room) == "none"
    room.state, room.hole_m2 = "FLUTEND", HIT_HOLE_M2
    assert _leak_state(room) == "open"
    room.state = "BESCHAEDIGT"
    assert _leak_state(room) == "patched"
    room.state = "ZERSTOERT"
    assert _leak_state(room) == "none"
