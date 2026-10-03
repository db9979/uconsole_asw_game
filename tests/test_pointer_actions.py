"""Click actions are called with the canvas position: every registered
action must accept it (a bound method without it crashed the game)."""

import inspect
from dataclasses import replace

import pygame
import pytest

from src.core import config, game_draw, pointer_input, uboot_local
from src.core.game import Game
from src.core.station import Station
from src.sonar.contact import Contact
from src.ui import game_menu, layout, pointer, sonar_hit, uboot_view


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


# --- Every key-only function reachable by mouse ---------------------------------
# Each new clickable element: drawn where it is hit, and a click changes the
# state exactly as its key does (a twin game presses the key).


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))


def _game(seed=31, scenario=None, side=None):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    if scenario is not None:
        game.reset(seed, scenario)
    if side == "uboot":
        game.local_side = "uboot"
    game.update(0.1)
    return game


def _key(game, key, mod=0):
    game.handle_event(pointer_input.key_event(key, mod))
    game.handle_event(pointer_input.key_event(key, mod, down=False))


def _targets(layer, key, mod=0):
    return [t for t in pointer.targets(layer) if t.key == key and t.mod == mod]


def _menu_row(game, label):
    rows = game_menu.entries(game)
    index = next(i for i, (_key_label, text, _call) in enumerate(rows) if text == label)
    return game_menu.row_rects(len(rows))[index]


def _admin_state(game):
    return (game.help_open, game.options_open, game.save_ui, game.quit_confirm,
            game.nations_open, game.commander_open, game.advisor_open,
            game.weather_station_open, game.autocrew_overview_open, game.plot_mode,
            game.autocrew.assist, game.autocrew.enabled["bridge"], game.editor is not None)


def test_menu_icon_opens_the_menu_and_rows_are_hit_where_drawn(window):
    game = _game()
    game.draw()
    _click(game, game_menu.button_rect().center)
    assert game.game_menu_open
    with layout.capture_geometry() as drawn:
        game.draw()
    _assert_actions_take_the_position()
    rows = game_menu.row_rects(len(game_menu.entries(game)))
    assert [t.rect for t in pointer.targets("popup")] == rows
    panel = next(item["rect"] for item in drawn
                 if item["kind"] == "panel" and item["title"] == "game_menu")
    assert all(panel.contains(rect) for rect in rows)
    # A click beside the menu only closes it: the station never sees it.
    _click(game, (300, 400))
    assert not game.game_menu_open and game.station is Station.BRIDGE
    game.audio.shutdown()


@pytest.mark.parametrize("label,key,mod", [
    ("gamemenu.help", pygame.K_F1, 0), ("gamemenu.options", pygame.K_F10, 0),
    ("gamemenu.save", pygame.K_s, 0), ("gamemenu.load", pygame.K_l, 0),
    ("gamemenu.weather", pygame.K_0, 0), ("gamemenu.plot", pygame.K_p, 0),
    ("gamemenu.autocrew", pygame.K_F2, 0),
    ("gamemenu.crew_assist", pygame.K_F2, pygame.KMOD_SHIFT),
    ("gamemenu.autocrew_overview", pygame.K_F3, 0), ("gamemenu.advisor", pygame.K_F7, 0),
    ("gamemenu.analyzer", pygame.K_F8, 0), ("gamemenu.commander", pygame.K_F9, 0),
    ("gamemenu.nations", pygame.K_n, 0), ("gamemenu.quit", pygame.K_ESCAPE, 0)])
def test_each_menu_row_does_what_its_key_does(window, label, key, mod):
    keyed, clicked, untouched = _game(), _game(), _game()
    _key(keyed, key, mod)
    clicked.draw()
    _click(clicked, game_menu.button_rect().center)
    clicked.draw()
    _click(clicked, _menu_row(clicked, label).center)
    assert _admin_state(clicked) == _admin_state(keyed) != _admin_state(untouched)
    assert not clicked.game_menu_open
    for game in (keyed, clicked, untouched):
        game.audio.shutdown()


def test_any_key_closes_the_menu_and_still_acts(window):
    game = _game()
    game.game_menu_open = True
    _key(game, pygame.K_2)
    assert not game.game_menu_open and game.station is Station.SONAR
    game.audio.shutdown()


def test_submarine_menu_offers_only_the_boat_keys(window):
    game = _game(side="uboot")
    game.draw()
    _click(game, game_menu.button_rect().center)
    assert game.game_menu_open
    game.draw()
    labels = [text for _k, text, _c in game_menu.entries(game)]
    assert "gamemenu.plot" not in labels and "gamemenu.autocrew" not in labels
    _click(game, _menu_row(game, "gamemenu.weather").center)
    assert game.weather_station_open and not game.game_menu_open
    game.audio.shutdown()


@pytest.mark.parametrize("opener,closed", [
    (lambda g: g._open_administration("help"), lambda g: not g.help_open),
    (lambda g: g._open_administration("options"), lambda g: not g.options_open),
    (lambda g: g._open_administration("save"), lambda g: g.save_ui is None),
    (lambda g: g._open_administration("quit"), lambda g: not g.quit_confirm),
    (lambda g: g._open_administration("nations"), lambda g: not g.nations_open),
    (lambda g: g._open_administration("live_traffic"), lambda g: not g.live_traffic_open),
    (lambda g: g.open_weather_station(), lambda g: not g.weather_station_open),
    (lambda g: g.open_autocrew_overview(), lambda g: not g.autocrew_overview_open),
    (lambda g: (setattr(g, "preferences", replace(g.preferences, simlog=True)),
                g._open_simlog_view()),
     lambda g: not g.simlog_view_open)])
def test_overlays_close_with_their_visible_close_box(window, opener, closed):
    game = _game()
    opener(game)
    with layout.capture_geometry() as drawn:
        game.draw()
    box = next(item["rect"] for item in drawn if item["title"] == "close")
    assert box in [t.rect for t in _targets(pointer_input.owner(game), pygame.K_ESCAPE)]
    _click(game, box.center)
    assert closed(game)
    game.audio.shutdown()


def _sonar_game(side=None):
    game = _game(side=side)
    if side == "uboot":
        uboot_local.set_local_station(game, "uboot_sonar")
        sonar, station = game.opfor.station.sonar, game.opfor.station
    else:
        game.station, game.sonar_page = Station.SONAR, 0
        sonar, station = game.sonar, game
    contact = Contact(7, 9001, "passive", "SURFACE")
    contact.bearing = 40.0
    contact.last_seen = game.sim_t
    sonar.contacts[contact.target_id] = contact
    station.selected_contact = contact
    return game, contact


def _sonar_geometry(game):
    """The sonar's geometry as the frame draws it."""
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        previous = config.STATION_RECT
        config.STATION_RECT = config.FULL_STATION_RECT
        try:
            return sonar_hit.sonar_geometry(game)
        finally:
            config.STATION_RECT = previous


def _sonar_state(game, contact):
    sonar = game.sonar
    return (game.msg, contact.player_class, contact.released_to_opz,
            getattr(game.target, "id", None), sonar.tma_enabled,
            str(sonar.tow_state), str(sonar.vds_state))


@pytest.mark.parametrize("label,key,mod", [
    ("C", pygame.K_c, 0), ("T", pygame.K_t, 0), ("G", pygame.K_g, 0), ("M", pygame.K_m, 0),
    ("Y", pygame.K_y, 0), ("Shift+Y", pygame.K_y, pygame.KMOD_SHIFT)])
def test_sonar_contact_chips_act_like_their_keys(window, label, key, mod):
    (keyed, contact_k), (clicked, contact_c) = _sonar_game(), _sonar_game()
    clicked.draw()
    rows = _sonar_geometry(clicked)["contact_keys"]
    assert any(spec[0] == label for _rect, specs in rows for spec in specs)
    # The chip is hit exactly in its drawn row (the key bar's two-pixel lift).
    chips = [t for t in _targets("station", key, mod)
             if any(rect.move(0, -2).contains(t.rect) for rect, _specs in rows)]
    assert len(chips) == 1
    before = _sonar_state(clicked, contact_c)
    _key(keyed, key, mod)
    _click(clicked, chips[0].rect.center)
    assert _sonar_state(clicked, contact_c) == _sonar_state(keyed, contact_k) != before
    for game in (keyed, clicked):
        game.audio.shutdown()


def test_sonar_chips_leave_room_for_the_contact_cards(window):
    game, _contact = _sonar_game()
    with layout.capture_geometry() as drawn:
        game.draw()
    card = next(item["rect"] for item in drawn if item["kind"] == "sonar-contact")
    regions = _sonar_geometry(game)
    assert regions["contacts"].contains(card)
    for rect, _specs in regions["contact_keys"]:
        assert not rect.colliderect(regions["contacts"])
        assert rect.bottom <= regions["main"].bottom
    game.audio.shutdown()


def test_boat_sonar_chips_offer_only_the_boat_keys(window):
    game, _contact = _sonar_game("uboot")
    game.draw()
    assert _targets("station", pygame.K_c) and _targets("station", pygame.K_t)
    assert _targets("station", pygame.K_m)
    assert not _targets("station", pygame.K_g) and not _targets("station", pygame.K_y)
    game.audio.shutdown()


def _opz_state(game):
    return (game.msg, game.asm_sel, game.chaff_cd, getattr(game.target, "id", None))


@pytest.mark.parametrize("key", [pygame.K_m, pygame.K_g, pygame.K_LEFT, pygame.K_RIGHT])
def test_opz_target_page_chips_act_like_their_keys(window, key):
    keyed, clicked = _game(), _game()
    for game in (keyed, clicked):
        game.station, game.station_page = Station.OPZ, 1
    clicked.draw()
    chips = [t for t in _targets("station", key) if t.rect.x > config.SCREEN_W * 3 // 4]
    assert len(chips) == 1
    _key(keyed, key)
    _click(clicked, chips[0].rect.center)
    assert _opz_state(clicked) == _opz_state(keyed)
    for game in (keyed, clicked):
        game.audio.shutdown()


def _consort_state(game):
    orders = game.consort
    return (game.msg, orders.mode, orders.station, orders.active, orders.weapons_free)


@pytest.mark.parametrize("key,mod", [
    (pygame.K_y, 0), (pygame.K_f, 0), (pygame.K_h, 0), (pygame.K_x, 0), (pygame.K_w, 0),
    (pygame.K_a, pygame.KMOD_SHIFT), (pygame.K_w, pygame.KMOD_SHIFT)])
def test_opz_group_page_order_hints_act_like_their_keys(window, key, mod):
    keyed, clicked = _game(5, "s21_suchgruppe"), _game(5, "s21_suchgruppe")
    for game in (keyed, clicked):
        game.station, game.station_page = Station.OPZ, 3
    clicked.draw()
    chips = _targets("station", key, mod)
    assert len(chips) == 1
    _key(keyed, key, mod)
    _click(clicked, chips[0].rect.center)
    assert _consort_state(clicked) == _consort_state(keyed)
    for game in (keyed, clicked):
        game.audio.shutdown()


def test_no_fire_click_on_the_new_controls(window):
    """ESSM and the consort's ASROC stay keys: fire by click only at station 3."""
    game = _game(5, "s21_suchgruppe")
    for page in (1, 3):
        game.station, game.station_page = Station.OPZ, page
        game.draw()
        assert not _targets("station", pygame.K_RETURN, pygame.KMOD_CTRL)
    game.station, game.station_page = Station.SONAR, 0
    game.game_menu_open = True
    game.draw()
    assert not [t for t in pointer.targets() if t.key == pygame.K_RETURN]
    game.audio.shutdown()


def _boat_weapons():
    game = _game(side="uboot")
    uboot_local.set_local_station(game, "uboot_weapons")
    sub = game.opfor.sub
    sub.crew_tubes[0] = ["dry", 0.0]
    return game, sub


@pytest.mark.parametrize("key,mod", [(pygame.K_m, pygame.KMOD_SHIFT),
                                     (pygame.K_m, pygame.KMOD_CTRL), (pygame.K_v, 0)])
def test_boat_weapons_chips_flood_tubes_and_launch_the_decoy(window, key, mod):
    (keyed, sub_k), (clicked, sub_c) = _boat_weapons(), _boat_weapons()
    clicked.draw()
    chips = [t for t in _targets("station", key, mod) if t.rect.h <= 24]
    assert len(chips) == 1
    _key(keyed, key, mod)
    _click(clicked, chips[0].rect.center)

    def state(sub):
        return list(sub.crew_tubes[0]), len(sub.pending_decoys)
    assert state(sub_c) == state(sub_k)
    if key == pygame.K_v:
        assert sub_c.pending_decoys
    else:
        assert sub_c.crew_tubes[0][0] == "flooding"
    for game in (keyed, clicked):
        game.audio.shutdown()


def test_boat_tube_lamps_load_and_flood(window):
    game, sub = _boat_weapons()
    game.draw()
    lamps = [t for t in pointer.targets("station") if t.key == pygame.K_m
             and t.rect.h > 24]
    assert [t.mod for t in lamps] == [pygame.KMOD_SHIFT]       # tube 1 is dry
    _click(game, lamps[0].rect.center)
    assert sub.crew_tubes[0][0] == "flooding"
    game.audio.shutdown()


def test_boat_tube_and_decoy_chips_only_at_the_weapons_station(window):
    game, _sub = _boat_weapons()
    uboot_local.set_local_station(game, "uboot")
    for page in range(len(uboot_view.station_pages("uboot"))):
        game.opfor.command_page = page
        game.draw()
        assert not _targets("station", pygame.K_m, pygame.KMOD_SHIFT)
        assert not _targets("station", pygame.K_m, pygame.KMOD_CTRL)
        # V there is the speed order of the key bar, never the decoy.
        assert all(t.rect.y > config.SCREEN_H - 60 for t in _targets("station", pygame.K_v))
    game.audio.shutdown()
