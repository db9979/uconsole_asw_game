"""Navigation lights of neutral traffic in the periscope and the lookout's
binoculars (COLREG rules 21-23): which lights show from where, only at night
or in restricted visibility, only on neutral vessels, and drawn in colour."""

import math
import sys
from pathlib import Path

import pygame
import pytest

from src.commander import projections
from src.core import opfor
from src.sensors import nav_lights
from src.ui import horizon, sight_scene, uboot_scope
from src.ui.silhouettes import NAV_LIGHT
from src.ui.stations import bridge as bridge_view

sys.path.insert(0, str(Path(__file__).parent))
from test_uboot_scope import _clear, _crewed, _environment, _place_frigate, _scope_up  # noqa: E402


@pytest.mark.parametrize("course, expected", [
    (180.0, "R2rg-"),    # head on: both side lights and both masthead lights
    (90.0, "R2-g-"),     # crossing left to right: starboard side, bow right
    (270.0, "L2r--"),    # crossing right to left: port side, bow left
    (0.0, "R0--s"),      # going away: the stern light only
    (225.0, "L2r--"),    # fine on the port bow
])
def test_lights_follow_the_arcs_of_the_rules(course, expected):
    # The vessel is due north of the observer, 2 NM off, 120 m long.
    assert nav_lights.code(course, 0.0, 2.0, 120.0, 10.0) == expected
    assert nav_lights.valid(expected)


def test_ranges_length_and_visibility_limit_what_shows():
    assert nav_lights.code(180.0, 0.0, 4.0, 120.0, 10.0) == "R2---"   # side lights 3 NM
    assert nav_lights.code(180.0, 0.0, 7.0, 120.0, 10.0) is None      # masthead 6 NM
    assert nav_lights.code(180.0, 0.0, 2.0, 30.0, 10.0) == "R1rg-"    # one masthead light
    assert nav_lights.code(180.0, 0.0, 2.0, 120.0, 1.5) is None       # hidden in the haze
    assert nav_lights.code(180.0, 0.0, 1.0, 120.0, 1.5) == "R2rg-"
    assert nav_lights.lit("night", 10.0) and nav_lights.lit("dusk", 10.0)
    assert nav_lights.lit("day", 1.0) and not nav_lights.lit("day", 10.0)
    assert not nav_lights.valid("X2rg-") and not nav_lights.valid(3)
    assert nav_lights.facing("L1r--") == -1 and nav_lights.facing("R1-g-") == 1
    assert nav_lights.facing(None) == -1


@pytest.mark.parametrize("work, length, expected", [
    ("GW", 40.0, "R0-g-GW"),      # trawling: green over white, no masthead light < 50 m
    ("GW", 80.0, "R1-g-GW"),      # from 50 m one masthead light abaft and above
    ("WR", 20.0, "R0-g-WR"),      # pilot on duty: white over red instead of masthead
    ("RWR", 90.0, "R2-g-RWR"),    # restricted in her ability to manoeuvre
    ("GGG", 55.0, "R2-g-GGG"),    # mine clearance
    (None, 90.0, "R2-g-"),        # a tug without a tow: an ordinary power-driven vessel
])
def test_vessels_at_work_add_their_all_round_lights(work, length, expected):
    assert nav_lights.code(90.0, 0.0, 1.5, length, 10.0, work) == expected
    assert nav_lights.valid(expected)


def test_catalog_duties_and_all_round_range():
    from types import SimpleNamespace
    assert nav_lights.duty(SimpleNamespace(key="aux_07")) == "GW"
    assert nav_lights.duty(SimpleNamespace(key="aux_10")) == "WR"
    assert nav_lights.duty(SimpleNamespace(key="aux_02")) is None       # tug, no tow
    assert nav_lights.duty(SimpleNamespace(key="tanker_01")) is None
    assert nav_lights.duty(None) is None
    # A 40 m trawler from astern: stern and all-round lights carry 2 NM.
    assert nav_lights.code(0.0, 0.0, 2.5, 40.0, 10.0, "GW") is None
    assert nav_lights.code(0.0, 0.0, 1.8, 40.0, 10.0, "GW") == "R0--sGW"


def _neutral_near(game, boat, distance_nm=1.5, bearing=0.0, course=90.0):
    """One neutral merchant in sight of the boat, every other ship far off."""
    sub = boat.sub
    _place_frigate(game, boat, 40.0)
    for other in game.warships:
        other.x, other.y = sub.x + 60.0, sub.y + 60.0
    ship = game.civilians[0]
    for other in game.civilians[1:]:
        other.x, other.y = sub.x - 60.0, sub.y - 60.0
    rad = math.radians(bearing)
    ship.x = sub.x + distance_nm * math.sin(rad)
    ship.y = sub.y - distance_nm * math.cos(rad)
    ship.course = course
    game.world.land_blocks_line = lambda *args: False
    return ship


def test_the_periscope_sees_the_lights_of_neutral_traffic_at_night_only():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _scope_up(boat)
    _clear(game, night=True)
    game._lookout_environment = lambda: dict(_environment(True), illumination=1.0)
    _neutral_near(game, boat, course=90.0)
    opfor.update_sightings(game, boat)
    rows = [row for row in boat.orders.sightings if row["cls"] in ("merchant", "unknown")]
    assert rows, boat.orders.sightings
    code = boat.orders._lights[rows[0]["ref"]]
    assert code == "R2-g-"                   # starboard side seen, bow to the right
    outlines = [row for row in uboot_scope.scope_outlines(game, boat) if row[4] is not None]
    assert outlines and outlines[0][4] == code
    scope = projections._uboot_scope(game, boat)
    assert [row["lights"] for row in scope["sightings"] if row["lights"]] == [code]
    # The frigate itself runs darkened.
    _place_frigate(game, boat, 1.0, bearing=180.0)
    opfor.update_sightings(game, boat)
    frigate = [row for row in boat.orders.sightings if row["cls"] == "warship"]
    assert frigate and frigate[0]["ref"] not in boat.orders._lights
    # By day in clear weather nobody shows lights.
    _clear(game)
    opfor.update_sightings(game, boat)
    assert boat.orders._lights == {}


def test_the_lookout_sees_the_lights_of_neutral_traffic():
    game, _server, _bridge = _crewed(seed=61)
    game.world.hour = 1.0
    game._lookout_environment = lambda: dict(_environment(True), illumination=1.0)
    game.crew_effect = lambda: 1.0
    ship = game.civilians[0]
    for other in game.civilians[1:] + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    ship.x, ship.y, ship.course = game.ship.x, game.ship.y - 1.0, 270.0
    game.world.land_blocks_line = lambda *args: False
    game._update_lookout_picture()
    rows = bridge_view.lookout_outlines(game, game.lookout_sightings())
    lit = [row for row in rows if row[4] is not None]
    assert [row[4] for row in lit] == ["L2r--"]
    glasses = projections._lookout_glasses(game)
    assert [row["lights"] for row in glasses["outlines"] if row["lights"]] == ["L2r--"]
    # Daylight in clear weather: no lights.
    game.world.hour = 12.0
    game.sim_t += 1.0
    game._update_lookout_picture()
    rows = bridge_view.lookout_outlines(game, game.lookout_sightings())
    assert all(row[4] is None for row in rows)


def test_the_eyepiece_draws_the_lights_in_colour():
    pygame.init()
    surface = pygame.Surface((480, 270))
    sky = sight_scene.plain_sky(True)

    def draw(code):
        surface.fill((0, 0, 0))
        horizon.draw_horizon(surface, (0, 0, 480, 270), line_of_sight=0.0, fov_deg=20.0,
                             night=True, visibility_nm=10.0, motion=(0.0, 0.0),
                             outlines=[(0.0, 10.0, "merchant", False, code)], sky=sky)
        return {surface.get_at((x, y))[:3] for x in range(120, 360) for y in range(60, 140)}

    port = draw("L2r--")
    starboard = draw("R2-g-")
    plain = draw(None)
    assert NAV_LIGHT["red"] in port and NAV_LIGHT["red"] not in starboard
    assert NAV_LIGHT["green"] in starboard and NAV_LIGHT["green"] not in port
    assert NAV_LIGHT["white"] in port and NAV_LIGHT["white"] not in plain
    trawler = draw("R0-g-GW")
    assert NAV_LIGHT["green"] in trawler and NAV_LIGHT["white"] in trawler
    assert NAV_LIGHT["red"] in draw("R0-g-RWR")


def test_civil_aircraft_show_position_and_anti_collision_lights():
    # Due north of the observer, 2 NM off: crossing to the east shows the
    # right (green) wingtip, flying away the white tail light.
    assert nav_lights.aircraft_code(90.0, 0.0, 2.0, 10.0) == "R0-g-AC"
    assert nav_lights.aircraft_code(270.0, 0.0, 2.0, 10.0) == "L0r--AC"
    assert nav_lights.aircraft_code(0.0, 0.0, 2.0, 10.0) == "R0--sAC"
    assert nav_lights.aircraft_code(180.0, 0.0, 2.0, 10.0) == "R0rg-AC"
    # Further off only the flashing anti-collision lights carry.
    assert nav_lights.aircraft_code(90.0, 0.0, 8.0, 10.0) == "R0---AC"
    assert nav_lights.aircraft_code(90.0, 0.0, 12.0, 20.0) is None
    assert nav_lights.aircraft_code(90.0, 0.0, 5.0, 4.0) is None
    assert nav_lights.valid("R0---AC")


def test_the_lookout_sees_civil_aircraft_lights_and_military_ones_dark():
    game, _server, _bridge = _crewed(seed=61)
    game.world.hour = 1.0
    game._lookout_environment = lambda: dict(_environment(True), illumination=1.0)
    game.crew_effect = lambda: 1.0
    for other in game.civilians + game.warships:
        other.x, other.y = game.ship.x + 60.0, game.ship.y + 60.0
    game.world.land_blocks_line = lambda *args: False
    flights = [flight for flight in game.flights.flights if flight.active]
    if len(flights) < 1:
        pytest.skip("no flight in the air for this seed")
    for flight in game.flights.flights:
        flight.x, flight.y = game.ship.x - 80.0, game.ship.y - 80.0
    flight = flights[0]
    flight.x, flight.y, flight.course = game.ship.x + 2.0, game.ship.y, 0.0
    flight.kind = "civil"
    game._update_lookout_picture()
    rows = [row for row in bridge_view.lookout_outlines(game, game.lookout_sightings())
            if row[2] == "aircraft"]
    assert [row[4] for row in rows] == ["L0r--AC"]     # flying north seen from the west
    flight.kind = "military"
    game.sim_t += 1.0
    game._update_lookout_picture()
    rows = [row for row in bridge_view.lookout_outlines(game, game.lookout_sightings())
            if row[2] == "aircraft"]
    assert all(row[4] is None for row in rows)


def test_anti_collision_lights_flash():
    pygame.init()
    surface = pygame.Surface((480, 270))
    sky = sight_scene.plain_sky(True)

    def reds(t):
        surface.fill((0, 0, 0))
        horizon.draw_horizon(surface, (0, 0, 480, 270), line_of_sight=0.0, fov_deg=20.0,
                             night=True, visibility_nm=10.0, motion=(0.0, 0.0),
                             outlines=[(0.0, 4.0, "aircraft", False, "R0---AC")], sky=sky,
                             anim_t=t)
        return sum(1 for x in range(480) for y in range(270)
                   if surface.get_at((x, y))[:3] == NAV_LIGHT["red"])

    assert reds(0.05) > 0 and reds(0.5) == 0
