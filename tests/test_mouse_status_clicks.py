"""Clicks on status lamps, key hints and readings act like their keys."""

import pygame
import pytest

from src.core import config, uboot_local
from src.core.commands import STATION_PAGES
from src.core.game import Game
from src.core.station import Station
from src.ui import pointer, uboot_view


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    instance.station, instance.station_page = Station.BRIDGE, 0
    yield instance
    instance.audio.shutdown()


@pytest.fixture
def boat(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    instance = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    instance.local_side = "uboot"
    instance.update(0.1)
    yield instance
    instance.audio.shutdown()


def click(game, pos):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def key_targets(key, mod=0):
    return [t for t in pointer.targets("station") if t.key == key and t.mod == mod]


def show(game, station, page=0):
    game.station, game.station_page = station, page
    game.draw()


def test_token_spans_find_each_key_in_english_and_german():
    spans = pointer.token_spans("Y lower/retrieve | U/V depth | Shift+A active ping",
                                (("Y", "Y"), ("U/V", "U/V"), ("Shift+A", "Shift+A")))
    text = "Y lower/retrieve | U/V depth | Shift+A active ping"
    assert [text[a:b] for a, b, _ in spans] == ["Y lower/retrieve", "U/V depth",
                                                "Shift+A active ping"]
    # A key letter inside a word or "HF" never counts; missing tokens are skipped.
    text = "Eigene Rufe: K Kontakt · H Unterstützung (KW, anpeilbar)"
    spans = pointer.token_spans(text, (("K", "K"), ("H", "H"), ("Z", "Z")))
    assert [text[a:b] for a, b, _ in spans] == ["K Kontakt", "H Unterstützung (KW, anpeilbar)"]
    text = "Strg+Enter: START"
    spans = pointer.token_spans(text, (("Ctrl+Enter:", 1), ("Strg+Enter:", 2), ("Enter", 3)))
    assert [(text[a:b], spec) for a, b, spec in spans] == [("Strg+Enter: START", 2)]


def test_legend_with_two_arrow_pairs_gives_four_keys():
    assert pointer.legend_keys("↑/↓ ←/→") == [(pygame.K_UP, 0), (pygame.K_DOWN, 0),
                                              (pygame.K_LEFT, 0), (pygame.K_RIGHT, 0)]


def test_eloka_tone_lamp_switches_like_j(game):
    show(game, Station.ELOKA)
    before = game.eloka_audio_enabled
    click(game, key_targets(pygame.K_j)[0].rect.center)
    assert game.eloka_audio_enabled is not before


def test_sonar_peak_lamp_switches_peak_hold(game):
    show(game, Station.SONAR)
    before = game.sonar.peak_hold
    lamp = next(t for t in key_targets(pygame.K_SPACE))
    click(game, lamp.rect.center)
    assert game.sonar.peak_hold is not before


def test_engine_telegraph_row_orders_that_step(game):
    show(game, Station.ENGINE)
    rows = [t for t in pointer.targets("station") if t.action is not None
            and t.rect.x < config.SCREEN_W // 2]
    assert len(rows) == 1 + len(config.TELEGRAPH_ORDERS)
    click(game, rows[2].rect.center)          # ASTERN, STOP, SLOW ...
    assert game.ship.telegraph == config.TELEGRAPH_ORDERS[1][0]
    click(game, rows[0].rect.center)
    assert game.ship.telegraph == "ASTERN"


def test_engine_acoustic_lamp_switches_quiet_running(game):
    show(game, Station.ENGINE)
    before = game.ship.quiet_mode
    lamp = next(t for t in key_targets(pygame.K_a) if t.rect.x > config.SCREEN_W // 2)
    click(game, lamp.rect.center)
    assert game.ship.quiet_mode is not before


def test_opz_radar_state_switches_the_surface_radar(game):
    show(game, Station.OPZ)
    before = game.surface_radar_on
    click(game, key_targets(pygame.K_r)[0].rect.center)
    assert game.surface_radar_on is not before


def test_weapons_flak_hint_and_lamp_toggle_release(game):
    show(game, Station.WEAPONS)
    before = game.flak_authorized
    targets = key_targets(pygame.K_f)
    assert len(targets) == 2                  # the FLAK lamp and the "F:" hint
    click(game, targets[0].rect.center)
    assert game.flak_authorized is not before


def test_helicopter_rules_name_their_keys(game):
    show(game, Station.HELICOPTER, 1)
    for key, mod in ((pygame.K_h, 0), (pygame.K_y, 0), (pygame.K_u, 0), (pygame.K_v, 0),
                     (pygame.K_a, pygame.KMOD_SHIFT), (pygame.K_b, 0), (pygame.K_d, 0)):
        assert key_targets(key, mod), pygame.key.name(key)


def test_ticker_reading_opens_its_station_but_never_pages_it(game):
    game.station = Station.WEAPONS
    game.draw()
    ticker = [t for t in pointer.targets("station") if t.rect.y >= config.SCREEN_H - 30]
    flooding = [t for t in ticker if t.key == pygame.K_4]
    assert flooding and not [t for t in ticker if t.key == pygame.K_3]   # this station
    click(game, flooding[0].rect.center)
    assert game.station is Station.DAMAGE and game.station_page == 0


def test_ticker_log_hint_opens_the_log(game):
    game.draw()
    click(game, key_targets(pygame.K_F11)[0].rect.center)
    assert game.feed_overlay_open


def test_frigate_fire_key_is_clickable_only_at_the_weapons_station(game):
    for station in Station:
        for page in range(len(STATION_PAGES[station])):
            if station is Station.SONAR:
                game.sonar_page = page
            show(game, station, page)
            fire = key_targets(pygame.K_RETURN, pygame.KMOD_CTRL)
            assert not fire or station is Station.WEAPONS, (station, page)


def test_boat_fire_key_is_clickable_only_at_station_three(boat):
    for role in uboot_local.OPFOR_ROLES:
        uboot_local.set_local_station(boat, role)
        for page in range(len(uboot_view.station_pages(role))):
            boat.opfor.command_page = page
            boat.draw()
            fire = key_targets(pygame.K_RETURN, pygame.KMOD_CTRL)
            assert not fire or role == "uboot_weapons", (role, page)


def test_boat_sonar_tab_click_pages_the_boat_sonar(boat):
    uboot_local.set_local_station(boat, "uboot_sonar")
    boat.draw()
    tab = [t for t in pointer.targets("station") if t.hover_only
           and 30 < t.rect.y < 80 and t.rect.x > 300][2]
    click(boat, tab.rect.center)
    assert boat.opfor.station.sonar_page == 2
    assert boat._frigate_sonar.sonar_page == 0


def test_boat_engine_lamps_and_telegraph_steps(boat):
    uboot_local.set_local_station(boat, "uboot_engine")
    boat.opfor.command_page = 0
    boat.draw()
    silent = boat.opfor.orders.silent
    click(boat, key_targets(pygame.K_a)[0].rect.center)
    assert boat.opfor.orders.silent is not silent
    boat.draw()
    steps = [t for t in pointer.targets("station") if t.action is not None
             and t.rect.h == 26]
    click(boat, steps[0].rect.center)
    assert boat.opfor.sub.order_speed == pytest.approx(0.0)


def test_boat_damage_footer_arrows_are_clickable(boat):
    uboot_local.set_local_station(boat, "uboot_engine")
    boat.opfor.command_page = 3
    boat.draw()
    for key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_i):
        assert key_targets(key), pygame.key.name(key)


def test_hover_frames_the_target_under_the_mouse(game, monkeypatch):
    game.draw()
    tab = key_targets(pygame.K_2)[0]
    monkeypatch.setattr(pygame.mouse, "get_focused", lambda: True)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: tab.rect.center)
    monkeypatch.setattr(game, "red_light_mode", lambda: "off")
    game.draw()
    assert tuple(game.screen.get_at(tab.rect.topleft))[:3] == config.COLOR_TEXT[:3]
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (640, 400))
    game.draw()
    assert tuple(game.screen.get_at(tab.rect.topleft))[:3] != config.COLOR_TEXT[:3]


def test_hover_only_targets_leave_the_click_to_the_station(game):
    show(game, Station.RADIO)
    tab = [t for t in pointer.targets("station") if t.hover_only][1]
    click(game, tab.rect.center)
    assert game.station_page == 1
