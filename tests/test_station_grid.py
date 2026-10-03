"""Stage 3b of the three-column layout: ELOKA, the radio room and the
frigate's Weapons page show cards on the left that a click selects."""

import pygame

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sensors.esm import ESMMeasurement
from src.sonar.contact import Contact
from src.ui import layout, pointer
from src.ui.stations import damage, eloka, radio
from src.ui import weapons_view


def _game():
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language="de")
    game._update(0.05)
    return game


def _click(game, pos):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def _draw_checked(game):
    with layout.capture_text() as text, layout.capture_truncations() as cut:
        game.draw()
    bad = [(item["text"], item["bounds"], item["rect"]) for item in text
           if not item["bounds"].contains(item["rect"])]
    assert not bad, bad
    return cut


def test_eloka_has_three_columns_and_a_card_click_selects_the_intercept():
    game = _game()
    game.esm_picture.observe_batch([ESMMeasurement(
        observer_x=game.ship.x, observer_y=game.ship.y, bearing=bearing,
        bearing_uncertainty_deg=2.0, frequency_hz=frequency, prf_hz=900.0,
        modulation_code="pulse", quality=.8, observed_at=game.sim_t)
        for bearing, frequency in ((40.0, 9.375e9), (200.0, 3.05e9), (300.0, 15.5e9))],
        game.sim_t)
    game.eloka_status_filter = "ALL"
    game.station, game.station_page = Station.ELOKA, 0
    regions = eloka.eloka_regions(config.FULL_STATION_RECT, page=0)
    assert regions["cards"].right < regions["picture"].x
    assert regions["picture"].right < regions["details"].x
    assert regions["details"].right <= config.SCREEN_W - 14
    assert not _draw_checked(game)
    cards = eloka.eloka_cards(game, config.FULL_STATION_RECT, page=0)
    assert len(cards) == 3
    track, rect = cards[2]
    _click(game, rect.center)
    assert game.eloka_selected_track_key == track.track_key
    # The evidence page keeps the cards beside the evidence.
    game.station_page = 1
    evidence = eloka.eloka_regions(config.FULL_STATION_RECT, page=1)["evidence"]
    assert evidence.x > regions["cards"].right
    assert not _draw_checked(game)
    game.audio.shutdown()


def test_radio_signal_cards_select_and_the_rose_moves_right():
    game = _game()
    for index, bearing in enumerate((40.0, 210.0, 300.0)):
        game.radio_picture.observe(
            track_id=f"H-90{index}", kind="HF", target_id=9000 + index, source="HFDF",
            bearing=bearing, range_nm=None, observer_x=game.ship.x,
            observer_y=game.ship.y, course=None, quality=.7, now=game.sim_t,
            label=f"x{index}", bearing_uncertainty_deg=4.0)
    game.station, game.station_page = Station.RADIO, 0
    station = pygame.Rect(config.FULL_STATION_RECT)
    from src.core.commands import STATION_PAGES
    from src.ui.stations.common import _station_content_top
    cy = _station_content_top(station, len(STATION_PAGES[Station.RADIO]))
    regions = radio.hfdf_regions(station.x + 14, cy, station.w - 28, station.bottom - cy - 34)
    assert regions["left"].right < regions["right"].x < regions["right"].right < regions["side"].x
    _draw_checked(game)
    cards = radio.hfdf_cards(game, regions["left"])
    assert len(cards) == 3
    index, _report, rect = cards[2]
    _click(game, rect.center)
    assert game.radio_sel == index
    game.audio.shutdown()


def test_frigate_weapons_contact_cards_select_like_left_right():
    game = _game()
    contacts = []
    for index, target_id in enumerate((9101, 9102), 1):
        contact = Contact(index, target_id, "passive", "SURFACE")
        contact.last_seen = game.sim_t
        game.sonar.contacts[target_id] = contact
        contacts.append(contact)
    game.station, game.station_page = Station.WEAPONS, 0
    regions = weapons_view.weapons_regions(game, 0)
    assert regions["contacts"].right < regions["solution"].x
    assert regions["contacts"].bottom < regions["stages"].y
    _draw_checked(game)
    cards = weapons_view.weapons_contact_cards(game)
    assert [contact for contact, _rect in cards] == contacts
    _click(game, cards[1][1].center)
    assert game.selected_contact is contacts[1]
    for target in pointer.targets():
        assert target.rect.right <= config.SCREEN_W
    game.audio.shutdown()


def test_damage_selection_page_has_compartment_and_team_cards():
    game = _game()
    game.station, game.station_page = Station.DAMAGE, 1
    assert not _draw_checked(game)
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        station = pygame.Rect(config.FULL_STATION_RECT)
    regions = damage.damage_regions(game, station, page=1)
    assert regions["cards"].right < regions["detail"].x < regions["detail"].right < regions["teams"].x
    cards = damage.damage_selection_cards(game, station)
    assert [key for key, _rect in cards] == list(game.damage.compartments)
    assigned = dict(game.damage.teams)
    _click(game, cards[5][1].center)
    assert game.dmg_cursor == 5
    teams = damage.damage_team_cards(game, station)
    _click(game, teams[2][1].center)
    assert game.dmg_team == teams[2][0]
    # Selecting never sends a team; Enter does.
    assert game.damage.teams == assigned
    game.audio.shutdown()


def test_submarine_esm_row_click_selects_the_emitter():
    from test_boat_esm import _mast_up_near_frigate
    from test_uboot_scope import _local_boat
    from src.core import uboot_local
    from src.ui import uboot_view
    game, boat = _local_boat()
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    for _ in range(100):
        game._update(0.1)
    uboot_local.set_local_station(game, "uboot_esm")
    boat.command_page = 0
    with layout.capture_geometry() as boxes:
        game.draw()
    listing = next(pygame.Rect(row["rect"]) for row in boxes
                   if row["title"] == "uboot.panel.esm")
    rows = [target for target in pointer.targets("station")
            if target.action is not None and listing.contains(target.rect)
            and target.rect.h == 20]
    assert len(rows) == len(boat.esm.ordered()) >= 1
    last = boat.esm.ordered()[len(rows) - 1]
    _click(game, rows[-1].rect.center)
    assert uboot_view.esm_selection(boat)[1] is last
    game.audio.shutdown()
