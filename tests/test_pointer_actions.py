"""Click actions are called with the canvas position: every registered
action must accept it (a bound method without it crashed the game)."""

import inspect

import pygame

from src.core import game_draw, uboot_local
from src.core.game import Game
from src.sonar.contact import Contact
from src.ui import pointer


def _click(game, pos):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def _assert_actions_take_the_position():
    for target in pointer.targets():
        if target.action is not None:
            inspect.signature(target.action).bind((0, 0))


def test_theme_switch_click_flips_the_colour_scheme():
    game = Game(seed=5, start_menu=False, audio_enabled=False)
    game.draw()
    _assert_actions_take_the_position()
    before = game.color_theme()
    _click(game, game_draw.theme_switch_rect().center)
    assert game.color_theme() != before
    game.audio.shutdown()


def test_submarine_weapons_contact_card_click_selects_the_contact():
    game = Game(seed=61, start_menu=False, audio_enabled=False, language="de")
    game.reset(61, "s1_patrouille")
    game.local_side = "uboot"
    game._update(0.05)
    uboot_local.set_local_station(game, "uboot_weapons")
    boat = game.opfor
    contacts = []
    for index, target_id in enumerate((9001, 9002), 1):
        contact = Contact(index, target_id, "passive", "SURFACE")
        boat.station.sonar.contacts[target_id] = contact
        contacts.append(contact)
    boat.station.selected_contact = contacts[0]
    game.draw()
    _assert_actions_take_the_position()
    cards = [target for target in pointer.targets("station") if target.action is not None
             and target.rect.w > 200 and target.rect.h < 60]
    assert len(cards) >= 2
    _click(game, cards[1].rect.center)
    assert boat.station.selected_contact is contacts[1]
    game.audio.shutdown()
