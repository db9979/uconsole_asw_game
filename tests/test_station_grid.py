"""Stage 3b of the three-column layout: ELOKA, the radio room and the
frigate's Weapons page show cards on the left that a click selects."""

import pygame

from src.core import config
from src.core.game import Game
from src.core.station import Station
from src.sensors.esm import ESMMeasurement
from src.sonar.contact import Contact
from src.ui import layout, pointer
from src.ui.stations import eloka, radio
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
