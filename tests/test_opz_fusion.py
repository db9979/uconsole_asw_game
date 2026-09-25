import copy
import json
import math

import pygame

from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sonar.sonar import Contact
from src.ui.stations_view import (_opz_track_point, _opz_view, opz_action_at,
                                  opz_regions)
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


def test_manual_fusion_has_no_automatic_link_and_ambiguous_fusion_cannot_designate():
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
    # Two different sonar contacts: no unique weapon target.
    assert game.designate_opz_observation(fusion.observation_id) == "no_solution"
    assert game.msg["__u_jagd_i18n__"] == "runtime.cic.fusion_ambiguous"


def single_contact_fusion():
    """Fuse the ship's and the helicopter's report of the same contact."""
    game = game_with_contacts()
    del game.sonar.contacts[70002]
    contact = game.sonar.contacts[70001]
    contact.released_to_opz = True
    contact.dip_bearing = 31.0
    contact.dip_last_seen = game.sim_t
    contact.dip_observer_x, contact.dip_observer_y = game.ship.x, game.ship.y
    contact.dip_bearing_uncertainty_deg = 3.0
    contact.helo_qualified = True
    contact.dip_released_to_opz = True
    reports = game.opz_tracks()
    assert len(reports) == 2
    game.opz_fusion.marked.update(item.observation_id for item in reports)
    game._create_opz_fusion()
    fusion = game.selected_opz_track()
    assert fusion.source == "FUSION"
    return game, contact, fusion


def test_single_contact_fusion_designates_its_sonar_contact():
    game, contact, fusion = single_contact_fusion()
    game.target = None
    game.designate_opz_track()
    assert game.target is contact and game.selected_contact is contact
    assert game.msg["__u_jagd_i18n__"] == "runtime.cic.designated"


def test_fusion_affiliation_blocks_and_classification_arms_fire_control():
    game, contact, fusion = single_contact_fusion()
    game.roe = "FREE"
    assert contact.player_class is None
    assert game.weapon_classification(contact) is None
    assert game.classify_opz_observation(fusion.observation_id, "U_BOOT") is True
    assert contact.player_class is None
    assert game.weapon_classification(contact) == "U_BOOT"
    # The sonar station's own class keeps precedence.
    contact.player_class = "BIOLOGISCH"
    assert game.weapon_classification(contact) == "BIOLOGISCH"
    contact.player_class = None

    assert game.affiliate_opz_observation(fusion.observation_id, "HOSTILE") is True
    assert game.contact_affiliation(contact) == "HOSTILE"
    assert game.affiliate_opz_observation(fusion.observation_id, "NEUTRAL") is True
    game.target = contact
    assert game.torpedo_readiness()[0] == "BLOCKIERT: ZUGEHOERIGKEIT NEUTRAL"
    count = game.torpedo_count
    assert game.launch_torpedo_at(contact, 50.0) == "roe_blocked"
    assert game.torpedo_count == count and not game.torpedoes


def test_fusion_lookup_for_fire_control_never_prunes_the_register():
    game, contact, fusion = single_contact_fusion()
    game.affiliate_opz_observation(fusion.observation_id, "FRIEND")
    contact.dip_released_to_opz = False   # one member report disappears
    before = (dict(game.opz_fusion.fusions),
              dict(game.opz_fusion.fusion_affiliations))
    assert game._contact_fusions(contact) == []
    assert game.contact_affiliation(contact) == "UNKNOWN"
    assert (dict(game.opz_fusion.fusions),
            dict(game.opz_fusion.fusion_affiliations)) == before


def test_shared_opz_geometry_and_mouse_select_use_opaque_report_id():
    game = game_with_contacts()
    game.sonar.contacts[70001].player_class = "U_BOOT"
    game.sonar.contacts[70001].released_to_opz = True
    report = game.opz_tracks()[0]
    regions = opz_regions(config.OPZ_STATION_RECT)
    station = pygame.Rect(config.OPZ_STATION_RECT)
    assert .74 <= (regions["sidebar"].x - station.x) / station.w <= .76
    point = _opz_track_point(
        game, report, regions["chart"], _opz_view(game, regions["chart"]))
    assert opz_action_at(game, point, config.OPZ_STATION_RECT) == (
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
    # OPZ may cycle a released sonar contact's classification too - it writes
    # straight through to the shared Contact, not a fusion-only overlay.
    assert contact.player_class == "KAMPFSCHIFF"
    assert game.opz_source_classification(report.observation_id) == "KAMPFSCHIFF"
    contact.player_class = "U_BOOT"

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
    # OPZ may reclassify a released sonar contact too - it writes through to
    # the shared Contact, not a separate fusion-only classification store.
    assert game.classify_opz_observation(report.observation_id,
                                         "KAMPFSCHIFF") is True
    assert contact.player_class == "KAMPFSCHIFF"
    assert game.opz_source_classification(report.observation_id) == "KAMPFSCHIFF"
    assert game.classify_sonar_contact(contact, "U_BOOT") is True
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


def test_subsurface_filter_uses_operator_classification_of_sonar_reports():
    game = game_with_contacts()
    first, second = game.sonar.contacts[70001], game.sonar.contacts[70002]
    first.released_to_opz = second.released_to_opz = True
    first.player_class = "U_BOOT"
    game.opz_contact_filter = "SUBSURFACE"
    shown = game.filtered_opz_tracks()
    assert [item.classification for item in shown] == ["U_BOOT"]
    assert shown[0].kind == "UNKNOWN"
    game.opz_contact_filter = "SURFACE"
    assert not game.filtered_opz_tracks()
