"""AI hunters: the frigate, its helicopter and the patrol aircraft hunt a crewed
boat when nobody sails the frigate, from the frigate's own observations."""

import math
import sys
from pathlib import Path

from src.core import config, hunter
from src.core.station import Station

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_opfor_sub import _crewed  # noqa: E402
from test_uboot_scope import _local_boat  # noqa: E402


def _place(game, boat, distance_nm, bearing=90.0, depth=60.0):
    rad = math.radians(bearing)
    sub = boat.sub
    sub.x = game.ship.x + distance_nm * math.sin(rad)
    sub.y = game.ship.y - distance_nm * math.cos(rad)
    sub.depth = sub.target_depth = sub.order_depth = depth


def _fix(game, x, y, age_s=60.0):
    game.hfdf_fixes["H-test"] = dict(label="SIG-01", x=x, y=y, sigma_nm=1.0,
                                     covariance_nm2=(1.0, 0.0, 1.0),
                                     t=game.sim_t - age_s)


def _run(game, seconds, dt=0.25):
    end = game.sim_t + seconds
    while game.sim_t < end - 1e-9 and not game.game_over:
        game._update_sim(dt)


def test_the_hunters_take_over_only_when_nobody_sails_the_frigate():
    game, _server, _bridge = _crewed(seed=61)
    assert game.local_side == "frigate" and not hunter.active(game)
    game.commander.solo = True                   # a solo browser plays the boat
    assert hunter.active(game)
    game.commander.solo = False
    game.local_side = "uboot"                    # the uConsole plays the boat
    assert hunter.active(game)
    game.game_over = True
    assert not hunter.active(game)


def test_only_submarine_signatures_classify_a_contact():
    game, _boat = _local_boat(seed=61)
    phrases = hunter.sub_signatures(game)
    assert "Diesel-Propeller, deutlich hörbar" in phrases
    assert "leise, elektrischer Antrieb" in phrases
    # A phrase surface ships share never marks a contact as a submarine.
    assert "kräftige Gasturbinen-Tonals" not in phrases
    assert "stetiger Frachter-Mahl" not in phrases


def test_without_observations_the_frigate_searches_regardless_of_the_boat():
    """The search never looks at the boat: moving it changes nothing."""
    courses = []
    for distance in (40.0, 80.0):
        game, boat = _local_boat(seed=61)
        _place(game, boat, distance, bearing=200.0)
        game.sonar.contacts.clear()
        assert hunter.datum(game) is None
        hunter.bridge(game, None)
        courses.append((round(game.ship.target_course, 6), game.ship.target_speed))
    assert courses[0] == courses[1]
    assert courses[0][1] == hunter.SEARCH_KN


def test_an_hfdf_fix_sends_ship_helicopter_and_patrol_aircraft():
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    x, y = game.ship.x + 12.0, game.ship.y
    _fix(game, x, y)
    found = hunter.datum(game)
    assert found["source"] == "hfdf" and (found["x"], found["y"]) == (x, y)
    assert found["contact"] is None                 # nothing to shoot at yet
    hunter.bridge(game, found)
    assert abs(game.ship.target_course - 90.0) < 1.0
    assert game.ship.target_speed == hunter.TRANSIT_KN
    assert hunter.helicopter(game, found) == "launched" and game.helo.airborne
    assert hunter.helicopter(game, found) == "moving"
    assert (game.helo.waypoint_x, game.helo.waypoint_y) == (x, y)
    assert hunter.mpa(game, found) == "requested"
    # A stale fix is no datum.
    _fix(game, x, y, age_s=hunter.FIX_MAX_AGE_S + 1.0)
    assert hunter.datum(game) is None


def test_manned_stations_are_left_to_their_crew(monkeypatch):
    game, boat = _local_boat(seed=61)
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    _fix(game, game.ship.x + 12.0, game.ship.y)
    monkeypatch.setattr(game.commander, "station_leased", lambda station: True)
    course, speed = game.ship.target_course, game.ship.target_speed
    game.sim_t = 10.0
    hunter.update(game, hunter.CADENCE_S)
    assert (game.ship.target_course, game.ship.target_speed) == (course, speed)
    assert game.helo.state == "HANGAR" and game.mpa.state == "BASE"
    # Only the bridge free: the ship turns, the aircraft stay put.
    monkeypatch.setattr(game.commander, "station_leased",
                        lambda station: station is not Station.BRIDGE)
    game.sim_t = 12.0
    hunter.update(game, hunter.CADENCE_S)
    assert game.ship.target_speed == hunter.TRANSIT_KN
    assert game.helo.state == "HANGAR" and game.mpa.state == "BASE"


def test_a_heard_boat_is_classified_pinged_and_attacked():
    game, boat = _local_boat(seed=61)
    game.world.land_blocks_line = lambda *args: False
    _place(game, boat, 3.0, bearing=90.0, depth=60.0)
    sub = boat.sub
    assert sub.set_orders(course=0.0, speed=8.0, depth=60.0) is True
    stores = (game.torpedo_count, game.helo.torps)
    _run(game, 300.0)
    rows = [contact for contact in game.sonar.contacts.values()
            if contact.target_id == sub.id]
    assert rows and rows[0].player_class == "U_BOOT"
    assert game.torpedo_count < stores[0] or sub.sunk          # the ship fired
    assert game.helo.torps < stores[1] or sub.sunk             # and the helicopter
    # One weapon per launcher in the water at a time.
    for origin, most in (("frigate", game.torpedo_salvo), ("helo", 1), ("mpa", 1)):
        assert sum(torpedo.state == "RUN" and torpedo.launch_origin == origin
                   for torpedo in game.torpedoes) <= most


def test_the_hunt_is_deterministic():
    states = []
    for _ in range(2):
        game, boat = _local_boat(seed=61)
        _place(game, boat, 3.0, bearing=90.0)
        _run(game, 120.0)
        states.append((game.ship.x, game.ship.y, game.ship.target_course,
                       game.ship.target_speed, game.helo.state, len(game.torpedoes),
                       game.sonar_ping_count if hasattr(game, "sonar_ping_count") else 0))
    assert states[0] == states[1]


def test_the_frigate_hunts_without_the_autocrew():
    game, boat = _local_boat(seed=61)
    assert not any(game.autocrew.enabled.values())
    _place(game, boat, 60.0)
    game.sonar.contacts.clear()
    _fix(game, game.ship.x, game.ship.y - 12.0)
    _run(game, 4.0)
    assert abs(((game.ship.target_course + 180.0) % 360.0) - 180.0) < 1.0
    assert game.ship.target_speed == min(hunter.TRANSIT_KN, config.SHIP_SPEED_MAX_KN)
