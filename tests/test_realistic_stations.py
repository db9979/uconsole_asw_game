"""Regression tests for observation boundaries and workstation realism."""

from types import SimpleNamespace

import pygame

from src.air.asm import ASM
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact, SonarSystem
from src.weapons.torpedo import Torpedo


def press(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_radar_off_does_not_publish_ground_truth_asm():
    game = Game(seed=123, start_menu=False)
    game.asms = [ASM(game.ship.x + 10.0, game.ship.y, 0.0, 7, game.rng_asm)]
    game.air_picture._tracks.clear()
    game.radar_on = False
    game._update_air_picture()
    assert game.asm_tracks() == []

    game.radar_on = True
    game._update_air_picture()
    tracks = game.radar_tracks()
    assert len([track for track in tracks if track["kind"] == "ASM"]) == 1
    assert "obj" not in tracks[0]


def test_essm_requires_sensor_track_not_live_asm_object():
    game = Game(seed=456, start_menu=False)
    game.asms = [ASM(game.ship.x + 8.0, game.ship.y, 0.0, 8, game.rng_asm)]
    game.air_picture._tracks.clear()
    before = game.vls_cells
    game.launch_essm()
    assert game.vls_cells == before and not game.essms

    game._update_air_picture()
    game.launch_essm()
    assert game.vls_cells == before - 1 and len(game.essms) == 1


def test_essm_rejects_track_outside_engagement_envelope():
    game = Game(seed=457, start_menu=False)
    game.asms = [ASM(game.ship.x + game._air_defense_loadout["sam"]["range_nm"] + 5.0,
                     game.ship.y, 0.0, 9, game.rng_asm)]
    game._update_air_picture()
    before = game.vls_cells
    game.launch_essm()
    assert game.vls_cells == before
    assert not game.essms


def test_torpedo_uses_wire_solution_before_own_seeker_acquires():
    target = SimpleNamespace(x=10.0, y=0.0, depth=50.0, sunk=False,
                             state="PATROL", hit=lambda: None)
    torpedo = Torpedo(0.0, 0.0, 0.0, 50.0, target, 1,
                      guidance_x=0.0, guidance_y=-8.0)
    torpedo.update(0.1)
    assert torpedo.seeker_acquired is False
    assert abs(config.angle_diff_deg(torpedo.course, 0.0)) < 5.0

    torpedo.wire_update(-8.0, 0.0)
    assert abs(config.angle_diff_deg(torpedo._midcourse, 270.0)) < 2.0


def test_helicopter_drops_single_buoy_at_its_own_position_and_does_not_reload():
    game = Game(seed=789, start_menu=False)
    game.helo.launch(game.ship)
    game.helo.x, game.helo.y = game.ship.x + 6.0, game.ship.y + 3.0
    game.deploy_buoys()
    assert len(game.buoys) == 1
    assert (game.buoys[0].x, game.buoys[0].y) == (game.helo.x, game.helo.y)
    remaining = game.helo.buoys_left
    game.helo.state = "HANGAR"
    game.helo.launch(game.ship)
    assert game.helo.buoys_left == remaining


def test_hfdf_cross_bearing_uses_only_logged_observer_rays():
    first = dict(observer_x=0.0, observer_y=0.0, bearing=135.0)
    second = dict(observer_x=10.0, observer_y=0.0, bearing=225.0)
    x, y, geometry = Game._bearing_intersection(first, second)
    assert abs(x - 5.0) < 1e-6
    assert abs(y - 5.0) < 1e-6
    assert geometry > 0.9


def test_station_specific_commands_do_not_leak_to_bridge():
    game = Game(seed=321, start_menu=False)
    game.station = Station.BRIDGE
    press(game, pygame.K_h)
    assert not game.helo.airborne
    press(game, pygame.K_g)
    assert game.chaff_cd == 0.0


def test_old_ping_fix_loses_exact_range_and_depth():
    contact = Contact(1, 1, "ping", "sub")
    contact.update_ping(90.0, 8.0, 60.0, 1.0, 0.0)
    contact.update_passive(91.0, 1.0, .8, "", config.SONAR_PING_FIX_MAX_AGE_S + 1)
    assert contact.range_est is None
    assert contact.depth_est is None


def test_fresh_ping_fix_is_not_replaced_by_passive_update():
    contact = Contact(1, 1, "ping", "sub")
    contact.update_ping(90.0, 8.0, 60.0, 1.0, 0.0)
    contact.update_passive(91.0, 1.0, .8, "", 2.0)
    assert contact.range_source == "ping"
    assert contact.range_est == 8.0
    assert contact.depth_est == 60.0


def test_buoy_bearing_intersection_recovers_geometry():
    first = (SimpleNamespace(x=0.0, y=0.0), 135.0, .8)
    second = (SimpleNamespace(x=10.0, y=0.0), 225.0, .8)
    x, y, geometry = SonarSystem._bearing_fix(first, second)
    assert abs(x - 5.0) < 1e-6
    assert abs(y - 5.0) < 1e-6
    assert geometry > .9


def test_all_operational_stations_have_damage_rooms():
    game = Game(seed=654, start_menu=False)
    for key in ("bridge", "sonar", "weapons", "opz", "radio", "engine",
                "flightdeck"):
        assert key in game.damage.compartments


def test_trackball_cannot_steer_outside_bridge():
    game = Game(seed=655, start_menu=False)
    game.station = Station.SONAR
    game.handle_event(pygame.event.Event(
        pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game._joy_turn == 0

    game.station = Station.BRIDGE
    game.handle_event(pygame.event.Event(
        pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game._joy_turn == 1


def test_trackball_axes_match_damage_team_and_compartment():
    game = Game(seed=658, start_menu=False)
    game.station = Station.DAMAGE
    game.dmg_team = 1
    game.dmg_cursor = 0
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=1, value=1.0))
    assert game.dmg_team == 2 and game.dmg_cursor == 0
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game.dmg_cursor == 1 and game.dmg_team == 2


def test_trackball_axes_match_weapon_depth_and_contact_selection():
    game = Game(seed=659, start_menu=False)
    game.station = Station.WEAPONS
    first = Contact(1, 101, "passiv", "sub")
    second = Contact(2, 102, "passiv", "sub")
    game.sonar.contacts = {101: first, 102: second}
    depth = game.torpedo_depth
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game.selected_contact is first
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=1, value=-1.0))
    assert game.torpedo_depth > depth


def test_trackball_axes_match_helicopter_bearing_and_range():
    game = Game(seed=660, start_menu=False)
    game.station = Station.HELICOPTER
    before_bearing, before_range = game._helo_waypoint_polar()
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=0, value=1.0))
    bearing, distance = game._helo_waypoint_polar()
    assert bearing == (before_bearing + 15.0) % 360.0
    assert abs(distance - before_range) < 1e-9
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=1, value=-1.0))
    assert game._helo_waypoint_polar()[1] > distance


def test_trackball_axes_match_sonar_beam_and_contact_selection():
    game = Game(seed=661, start_menu=False)
    game.station = Station.SONAR
    contact = Contact(1, 101, "passiv", "sub")
    game.sonar.contacts = {101: contact}
    bearing = game.sonar.listen_bearing
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game.sonar.listen_bearing == bearing + .5
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=1, value=1.0))
    assert game.selected_contact is contact


def test_trackball_axes_match_opz_asm_and_cic_selection():
    game = Game(seed=662, start_menu=False)
    game.station = Station.OPZ
    game.air_picture._tracks.clear()
    for track_id, kind in (("S-1", "AIS"), ("M-2", "ASM"), ("M-3", "ASM")):
        game.air_picture.observe(
            track_id=track_id, kind=kind, target_id=int(track_id[-1]),
            source="RADAR", bearing=90.0, range_nm=5.0,
            observer_x=game.ship.x, observer_y=game.ship.y, course=0.0,
            quality=.8, now=game.sim_t, label=track_id)
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=0, value=1.0))
    assert game.asm_sel == 1
    for _ in range(2):
        game.handle_event(pygame.event.Event(
            pygame.JOYAXISMOTION, axis=1, value=1.0))
    assert game.opz_selected_track_id == "M-2"


def test_procedural_world_snapshot_survives_save_load():
    game = Game(seed=656, start_menu=False)
    before = game.world.coast.to_dict()
    restored = Game(seed=1, start_menu=False)
    restored.load_state(game.save_state())
    assert restored.world_mode == "procedural"
    assert restored.world.coast.to_dict() == before


def test_opz_designation_hands_sonar_solution_to_weapons():
    game = Game(seed=657, start_menu=False)
    target = game.subs[0]
    contact = Contact(77, target.id, "passiv", "sub")
    contact.update_passive(90.0, 1.0, .8, "", game.sim_t)
    game.sonar.contacts[target.id] = contact
    game.air_picture.observe(
        track_id=f"U-{target.id}", kind="SUB", target_id=target.id,
        source="SONAR-BRG", bearing=90.0, range_nm=None,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=.8, now=game.sim_t, label="K77")
    game.opz_selected_track_id = f"U-{target.id}"

    game.designate_opz_track()

    assert game.target is contact
    assert game.selected_contact is contact
