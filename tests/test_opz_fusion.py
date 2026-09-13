import copy
import json
import math

import pygame

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui.stations_view import opz_action_at, opz_regions
from test_commander_bridge import Server, observe


def game_with_contacts():
    game = Game(seed=1901, start_menu=False, audio_enabled=False, language="en")
    game.station = Station.OPZ
    game.air_picture._tracks.clear()
    for number, bearing in ((70001, 30.0), (70002, 60.0)):
        contact = Contact(number - 70000, number, "passiv", "sub")
        contact.update_passive(bearing, .8, .8, "hidden producer label", game.sim_t)
        game.sonar.contacts[number] = contact
    return game


def press(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))


def test_sonar_release_withdraw_and_private_v2_boundary():
    game = game_with_contacts()
    assert not game.opz_tracks()
    first = game.sonar.contacts[70001]
    first.player_class = "U_BOOT"
    assert not game.opz_tracks()
    assert game.release_sonar_contact(first, True) is True
    released = game.opz_tracks()
    assert len(released) == 1
    report = released[0]
    assert report.kind == "UNKNOWN" and report.classification == "U_BOOT"
    assert report.range_nm is report.x is report.y is report.course is None
    assert "70001" not in report.observation_id and not hasattr(report, "target_id")

    bridge, server = CommanderBridge(), Server()
    bridge.pump(game, server, now=10.0)
    sonar = server.v2_states["sonar"]["sonar"]["observations"]
    opz = server.v2_states["opz"]["opz"]["observations"]
    assert len(sonar) == 2 and len(opz) == 1
    assert "70001" not in json.dumps(server.v2_states)
    assert game.release_sonar_contact(first, False) is True
    assert first.player_class == "U_BOOT"
    assert not game.opz_tracks()


def test_current_modeled_fix_is_the_only_source_of_sonar_geometry():
    game = game_with_contacts()
    contact = game.sonar.contacts[70001]
    contact.player_class = "KAMPFSCHIFF"
    contact.released_to_opz = True
    contact._publish_fix("PING", game.sim_t, game.sim_t,
                         game.ship.x + 4, game.ship.y, .2, .9, 40, 2)
    report = game.opz_tracks()[0]
    assert report.source == "SONAR-PING" and report.range_nm == 4
    assert report.x == game.ship.x + 4 and report.kind == "UNKNOWN"


def test_manual_fusion_has_no_automatic_link_and_cannot_designate():
    game = game_with_contacts()
    for contact in game.sonar.contacts.values():
        contact.player_class = "U_BOOT"
        contact.released_to_opz = True
    reports = game.opz_tracks()
    assert not game.opz_fusion.fusions
    game.opz_fusion.marked.update(item.observation_id for item in reports)
    game._create_opz_fusion()
    fusion = game.selected_opz_track()
    assert fusion.source == "FUSION" and set(fusion.members) == {
        item.observation_id for item in reports}
    target = game.target
    game.designate_opz_track()
    assert game.target is target
    assert game.msg["__u_jagd_i18n__"] == "runtime.cic.fusion_display_only"


def test_shared_opz_geometry_and_mouse_select_use_opaque_report_id():
    game = game_with_contacts()
    game.sonar.contacts[70001].player_class = "U_BOOT"
    game.sonar.contacts[70001].released_to_opz = True
    report = game.opz_tracks()[0]
    regions = opz_regions(config.FULL_STATION_RECT)
    station = pygame.Rect(config.FULL_STATION_RECT)
    assert .74 <= (regions["sidebar"].x - station.x) / station.w <= .76
    radius = regions["chart"].w // 2 - 13
    angle = math.radians(report.bearing)
    point = (regions["chart"].centerx + radius * math.sin(angle),
             regions["chart"].centery - radius * math.cos(angle))
    assert opz_action_at(game, point, config.FULL_STATION_RECT) == (
        "select", report.observation_id)
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                         button=1, pos=point))
    assert game.opz_selected_track_id == report.observation_id


def test_v2_fusion_members_are_only_opaque_published_references():
    game = game_with_contacts()
    for contact in game.sonar.contacts.values():
        contact.player_class = "U_BOOT"
        contact.released_to_opz = True
    game.opz_fusion.marked.update(item.observation_id for item in game.opz_tracks())
    game._create_opz_fusion()
    bridge, server = CommanderBridge(), Server()
    bridge.pump(game, server, now=10.0)
    payload = server.v2_states["opz"]["opz"]
    assert len(payload["fusions"]) == 1
    refs = {item["ref"] for item in payload["observations"]}
    assert set(payload["fusions"][0]["members"]) == refs
    assert all("7000" not in ref for ref in refs)


def test_classification_ownership_suppression_scope_and_transience():
    game = game_with_contacts()
    contact = game.sonar.contacts[70001]
    contact.player_class = "U_BOOT"
    contact.released_to_opz = True
    report = game.opz_tracks()[0]
    game.opz_selected_track_id = report.observation_id
    press(game, pygame.K_c)
    assert contact.player_class == "U_BOOT"
    assert game.opz_source_classification(report.observation_id) == "U_BOOT"

    before = copy.deepcopy(game.save_state())
    press(game, pygame.K_DELETE)
    assert not game.opz_tracks()
    assert len(game.opz_published_observations()) == 1
    assert game.save_state() == before
    press(game, pygame.K_h)
    assert game.opz_tracks()[0].observation_id == report.observation_id

    loaded = Game(seed=9, start_menu=False, audio_enabled=False)
    loaded.load_state(before)
    assert not loaded.opz_fusion.suppressed and not loaded.opz_fusion.fusions


def test_fusion_is_bounded_and_not_serialized():
    game = game_with_contacts()
    for contact in game.sonar.contacts.values():
        contact.player_class = "U_BOOT"
        contact.released_to_opz = True
    reports = game.opz_tracks()
    saved = game.save_state()
    for _ in range(32):
        game.opz_fusion.marked.update(item.observation_id for item in reports)
        assert game.opz_fusion.create(reports) is not None
    game.opz_fusion.marked.update(item.observation_id for item in reports)
    assert game.opz_fusion.create(reports) is None
    game.opz_selected_track_id = "F-01"
    assert game.save_state() == saved


def test_result_helpers_enforce_freshness_damage_and_source_ownership():
    game = game_with_contacts()
    contact = game.sonar.contacts[70001]
    assert game.classify_sonar_contact(contact, "U_BOOT") is True
    assert game.release_sonar_contact(contact, True) is True
    report = game.opz_source_observations()[0]
    assert game.classify_opz_observation(report.observation_id,
                                         "KAMPFSCHIFF") == "source_owned"
    assert contact.player_class == "U_BOOT"
    assert game.affiliate_opz_observation(report.observation_id, "HOSTILE") is True
    observe(game, "S-99003", "SURFACE", "RADAR-S")
    radar = next(item for item in game.opz_source_observations()
                 if item.source == "RADAR-S")
    assert game.classify_opz_observation(radar.observation_id,
                                         "KAMPFSCHIFF") is True
    assert game.opz_source_classification(radar.observation_id) == "KAMPFSCHIFF"

    contact.last_seen = game.sim_t - config.SONAR_CONTACT_LOST_S
    assert game.classify_sonar_contact(contact, None) == "stale_ref"
    assert game.affiliate_opz_observation(report.observation_id,
                                          "FRIEND") == "stale_ref"

    game.damage.compartments["sonar"].state = "ZERSTOERT"
    assert game.classify_sonar_contact(contact, "BIOLOGISCH") == "sonar_down"
    game.damage.compartments["opz"].state = "ZERSTOERT"
    assert game.set_opz_radar("surface", False) == "opz_down"
    assert game.set_opz_range(config.RADAR_RANGE_SCALES_NM[0]) == "opz_down"
