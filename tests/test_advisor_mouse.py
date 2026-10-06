"""The executive officer (F7) and the language model's settings page are
fully mouse-operable: tabs, key buttons, rows and the close box take a click,
the wheel scrolls, and no click reaches the station behind."""

import dataclasses
import json
import time

import pygame

from src.core import pointer_input
from src.core.game import Game
from src.core.game_advisor import LLM_ROWS
from src.core.station import Station
from src.ui import advisor_view, game_menu, pointer
from tests.llm_fake import FakeLlmServer


def _game():
    return Game(seed=4411, start_menu=False, audio_enabled=False)


def _click(game, pos):
    game.draw()
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def _button(game, key):
    game.draw()
    found = [t for t in pointer.targets("overlay") if t.key == key]
    assert found, key
    return found[-1].rect.center


def _connect(game, server):
    game.preferences = dataclasses.replace(
        game.preferences, llm_enabled=True, llm_url=server.url, llm_model="m")
    game.configure_llm()


def test_close_box_and_esc_button_close_the_executive_officer():
    for close in (lambda g: game_menu.close_button(g.screen, advisor_view.PANEL).center,
                  lambda g: _button(g, pygame.K_ESCAPE)):
        game = _game()
        game._open_administration("advisor")
        game.draw()
        _click(game, close(game))
        assert not game.advisor_open
        game.audio.shutdown()


def test_tab_click_picks_the_mode_also_while_typing():
    game = _game()
    game._open_administration("advisor")
    game.advisor_mode = 1
    game.advisor_field.value = "wie"
    for index, rect in enumerate(advisor_view.tab_rects(5)):
        _click(game, rect.center)
        assert game.advisor_mode == index
    assert game.advisor_field.value == "wie"
    game.audio.shutdown()


def test_clicks_inside_the_overlay_never_reach_the_station():
    game = _game()
    game.draw()
    station_targets = [t for t in pointer.targets("station") if t.key is not None]
    assert station_targets
    game._open_administration("advisor")
    before = (game.station, game.ship.target_course, game.ship.target_speed)
    for target in station_targets[:40]:
        _click(game, target.rect.center)
        if not game.advisor_open:
            game._open_administration("advisor")
    assert (game.station, game.ship.target_course, game.ship.target_speed) == before
    assert game.station is Station.BRIDGE
    game.audio.shutdown()


def test_setup_button_opens_the_settings_while_the_model_is_off():
    game = _game()
    game._open_administration("advisor")
    game.draw()
    actions = [t for t in pointer.targets("overlay") if t.action is not None
               and t.rect.y >= advisor_view.BUTTONS_Y]
    assert len(actions) == 1
    _click(game, actions[0].rect.center)
    assert game.llm_open and not game.advisor_open
    game.audio.shutdown()


def test_settings_row_click_changes_it_and_buttons_save_or_cancel():
    game = _game()
    game._open_administration("llm")
    radio = LLM_ROWS.index("llm_radio")
    before = game.preferences.llm_radio
    _click(game, advisor_view.settings_row_rects()[radio].center)
    assert game.llm_sel == radio and game.preferences.llm_radio != before
    # A text row opens its field; the Esc button cancels it, the next Esc closes.
    _click(game, advisor_view.settings_row_rects()[LLM_ROWS.index("llm_model")].center)
    assert game.llm_field_name == "llm_model"
    _click(game, _button(game, pygame.K_ESCAPE))
    assert game.llm_field is None and game.llm_open
    _click(game, _button(game, pygame.K_DOWN))
    assert game.llm_sel == LLM_ROWS.index("llm_model") + 1
    _click(game, _button(game, pygame.K_ESCAPE))
    assert not game.llm_open
    game.audio.shutdown()


def _wait(game, entry):
    end = time.monotonic() + 8
    while entry["status"] == "pending" and time.monotonic() < end:
        game.llm_tick()
        time.sleep(0.02)


def test_order_is_sent_confirmed_and_scrolled_by_mouse():
    reply = json.dumps({"commands": [{"type": "course", "value": 120}], "say": "Course 120. " * 120})
    with FakeLlmServer(reply) as server:
        game = _game()
        _connect(game, server)
        game._open_administration("advisor")
        for _ in range(4):      # a log longer than the page
            asked = game.advisor_ask("situation")
            _wait(game, asked)
        _click(game, advisor_view.tab_rects(5)[2].center)
        game.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="come to 120"))
        _click(game, _button(game, pygame.K_RETURN))
        entry = game.advisor.log("local")[-1]
        _wait(game, entry)
        assert game.advisor_open_proposal() is entry
        assert pointer_input.owner(game) == "overlay"
        _click(game, _button(game, pygame.K_UP))
        # One step back moves at once, the wheel back down follows the newest.
        assert game.advisor_scroll == game.advisor_scroll_max - 1
        game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
        assert game.advisor_scroll is None
        _click(game, _button(game, pygame.K_RETURN))
        assert entry["applied"], (entry, game.msg)
        assert round(game.ship.target_course) == 120
        game.audio.shutdown()


def test_clicks_on_the_overlay_never_switch_the_page_of_the_station_behind():
    """Page tabs are hit-tested by the station itself (no pointer target):
    a click over the open overlay must not reach that hit test either."""
    game = _game()
    for station in (Station.RADIO, Station.OPZ, Station.DAMAGE, Station.ENGINE):
        game.station, game.station_page = station, 0
        for name in ("advisor", "llm"):
            game._open_administration(name)
            game.draw()
            for x in range(20, 1280, 40):
                for y in (60, 80, 100, 400, 650):
                    _click(game, (x, y))
                    if not (game.advisor_open or game.llm_open):
                        game._open_administration(name)
            assert (game.station, game.station_page) == (station, 0), (station, name)
            game._open_administration("")
    game.audio.shutdown()
