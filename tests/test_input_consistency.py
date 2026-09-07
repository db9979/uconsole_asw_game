"""Canvas geometry, universal guards, and reachable contextual controls."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config
from src.core.commands import station_command_hint
from src.core.game import Game
from src.core.help import get_global_help
from src.core.i18n import Translator, load_catalog, pseudolocale
from src.core.station import Station
from src.ui import layout, map_view
from src.ui.stations_view import damage_regions, opz_ppi_rect


@pytest.fixture
def game():
    return Game(seed=808, start_menu=False, audio_enabled=False)


def event(game, kind, **attrs):
    game.handle_event(pygame.event.Event(kind, **attrs))


def press(game, key, **attrs):
    event(game, pygame.KEYDOWN, key=key, **attrs)


@pytest.mark.parametrize("tooltips", [False, True])
@pytest.mark.parametrize("region_type", ["anchor", "callout"])
def test_damage_click_selects_without_assigning_and_obeys_input_owner(game, monkeypatch,
                                                                    tooltips, region_type):
    game.station = Station.DAMAGE
    game.tooltips_enabled = tooltips
    monkeypatch.setattr(config, "STATION_RECT", config.STATION_PANEL_RECT)
    region = damage_regions(game, config.FULL_STATION_RECT)["compartments"]["engine"]
    pos = region[region_type]
    if region_type == "callout":
        pos = pos.center
    before = dict(game.damage.teams)
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    assert list(game.damage.compartments)[game.dmg_cursor] == "engine"
    assert game.damage.teams == before
    assert (game.pinned_tooltip is not None) == tooltips
    assert config.STATION_RECT == config.STATION_PANEL_RECT
    if tooltips:
        press(game, pygame.K_ESCAPE)
        assert not game.quit_confirm
    game._open_administration("help")
    game.dmg_cursor = 0
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    assert game.dmg_cursor == 0
    game.help_open = False
    game.input_mode = "course"
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    assert game.dmg_cursor == 0


def test_editor_universal_guards_and_canvas_pointer(game, monkeypatch):
    received, fullscreen = [], []
    game.editor = NS(mode="form", handle_event=received.append)
    monkeypatch.setattr(game, "toggle_fullscreen", lambda: fullscreen.append(True))
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1600, 1000))
    monkeypatch.setattr(config, "FILL_SCREEN", False)
    press(game, pygame.K_RETURN, mod=pygame.KMOD_ALT)
    press(game, pygame.K_RETURN, repeat=True)
    press(game, pygame.K_F5, repeat=True)
    game.held.add(pygame.K_LEFT)
    game._joy_turn = 1
    event(game, pygame.WINDOWFOCUSLOST)
    assert not received and fullscreen == [True]
    assert game.paused and not game.held and game._joy_turn == 0
    event(game, pygame.WINDOWFOCUSGAINED)
    assert game.paused
    received.clear()
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 25))
    assert not received
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(800, 500))
    assert received[-1].pos == (640, 360)
    event(game, pygame.MOUSEMOTION, pos=(825, 525), rel=(25, 25))
    assert received[-1].pos == (660, 380)
    assert received[-1].rel == (20, 20)


def test_opz_wheel_uses_full_station_geometry_even_before_draw(game, monkeypatch):
    game.station = Station.OPZ
    monkeypatch.setattr(config, "STATION_RECT", config.STATION_PANEL_RECT)
    pos = opz_ppi_rect(config.FULL_STATION_RECT).center
    assert not opz_ppi_rect().collidepoint(pos)
    game.opz_range_nm = config.RADAR_RANGE_SCALES_NM[1]
    event(game, pygame.MOUSEWHEEL, y=0, x=1, pos=pos)
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[1]
    event(game, pygame.MOUSEWHEEL, y=1, pos=pos)
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[2]
    event(game, pygame.MOUSEWHEEL, y=-1, pos=(1200, 100))
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[2]
    assert config.STATION_RECT == config.STATION_PANEL_RECT


def test_letterbox_rejects_damage_and_opz_clicks(game, monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1600, 1000))
    monkeypatch.setattr(config, "FILL_SCREEN", False)
    game.station = Station.DAMAGE
    game.dmg_cursor = 4
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 25))
    assert game.dmg_cursor == 4 and game.pinned_tooltip is None
    game.station = Station.OPZ
    before = game.opz_range_nm
    event(game, pygame.MOUSEWHEEL, y=-1, pos=(100, 25))
    assert game.opz_range_nm == before


@pytest.mark.parametrize("mod", [0, pygame.KMOD_SHIFT])
def test_tab_clears_pinned_tooltip_and_controls(game, mod):
    game.pinned_tooltip = {"title": "old", "lines": []}
    game._tooltip_anchor = (100, 100)
    game.held.add(pygame.K_LEFT)
    press(game, pygame.K_TAB, mod=mod)
    assert game.pinned_tooltip is None and game._tooltip_anchor is None
    assert not game.held


def test_map_click_preserves_follow_and_small_motions_accumulate(game, monkeypatch):
    game.station = Station.BRIDGE
    game.map_view.scale = 4
    game.draw()
    pinned = []
    monkeypatch.setattr(game, "_pin_tooltip_at", lambda pos: pinned.append(pos))
    center = game.map_view.cx, game.map_view.cy
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(200, 200))
    event(game, pygame.MOUSEMOTION, pos=(201, 200))
    event(game, pygame.MOUSEBUTTONUP, button=1, pos=(201, 200))
    assert game.map_follow and pinned == [(201, 200)]
    assert (game.map_view.cx, game.map_view.cy) == center
    pinned.clear()
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(200, 200))
    for x in (201, 202, 203, 204):
        event(game, pygame.MOUSEMOTION, pos=(x, 200))
    assert not game.map_follow and game._map_drag_moved
    assert game.map_view.cx == pytest.approx(center[0] - 1)
    event(game, pygame.MOUSEBUTTONUP, button=1, pos=(204, 200))
    assert not pinned and game._map_drag is None


def test_map_hit_prefers_the_selected_contact_that_is_drawn(game):
    game.map_follow = False
    game.map_view.set_rect(config.MAP_RECT)
    game.map_view.cx = game.map_view.cy = 250
    game.map_view.scale = 4
    game.radar_tracks = lambda: []
    game.selected_contact = NS(id=71, observed_x=260, observed_y=240, bearing=45,
                               range_est=14, last_seen=game.sim_t)
    game.target = NS(id=72, observed_x=270, observed_y=240, bearing=60,
                     range_est=22, last_seen=game.sim_t)
    pos = game.map_view.world_to_screen(260, 240)
    assert map_view.map_hit_target(game, pos)["id"] == "map:sonar:71"
    pos = game.map_view.world_to_screen(270, 240)
    assert map_view.map_hit_target(game, pos)["id"].startswith("chart:")


def test_map_draws_both_grid_axes_with_offset_rect(game, monkeypatch):
    calls = []
    original = pygame.draw.line

    def record(surface, color, start, end, width=1):
        if color == config.COLOR_GEO_GRID:
            calls.append((start, end))
        return original(surface, color, start, end, width)

    monkeypatch.setattr(pygame.draw, "line", record)
    monkeypatch.setattr(config, "MAP_RECT", (20, 60, 600, 440))
    game.map_follow = False
    game.map_view.cx = game.map_view.cy = 250
    map_view.draw_map_view(game)
    assert any(a[0] == b[0] and a[1] != b[1] for a, b in calls)
    assert any(a[1] == b[1] and a[0] != b[0] for a, b in calls)


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
def test_help_all_wrapped_lines_reachable_in_three_categories(game, language, large):
    game.preferences = replace(game.preferences, large_text=large)
    translator = Translator("en" if language == "pseudo" else language)
    if language == "pseudo":
        translator.catalog = pseudolocale(load_catalog("en"))
    game.tr = translator.t
    game.station = Station.SONAR
    game._open_administration("help")
    for page in range(3):
        assert game.help_page == page and game.help_scroll == 0
        lines, visible = game._help_lines()
        for _ in range(len(lines)):
            press(game, pygame.K_DOWN)
        assert game.help_scroll == max(0, len(lines) - visible)
        with layout.capture_text() as trace:
            game.draw_help_overlay()
        assert lines[-1] in [entry["text"] for entry in trace]
        press(game, pygame.K_PAGEUP)
        assert game.help_scroll == max(0, len(lines) - 2 * visible)
        press(game, pygame.K_PAGEDOWN)
        assert game.help_scroll == max(0, len(lines) - visible)
        press(game, pygame.K_RIGHT)
    assert game.help_page == 0
    assert "F10" in [key for key, _ in get_global_help(game.tr)[1]]


@pytest.mark.parametrize("station,method,legacy", [
    (Station.WEAPONS, "launch_torpedo", pygame.K_t),
    (Station.OPZ, "launch_essm", pygame.K_e),
    (Station.HELICOPTER, "launch_helo_torpedo", pygame.K_d),
])
def test_primary_weapon_alias_retains_legacy_keys_and_guards(game, monkeypatch,
                                                          station, method, legacy):
    calls = []
    game.station = station
    monkeypatch.setattr(game, method, lambda: calls.append(True))
    press(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL)
    press(game, pygame.K_KP_ENTER, mod=pygame.KMOD_CTRL)
    press(game, legacy)
    assert len(calls) == 3
    press(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL, repeat=True)
    game.paused = True
    press(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL)
    game.paused = False
    game._open_administration("help")
    press(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL)
    assert len(calls) == 3


def test_primary_weapon_hints_translate_and_do_not_expose_catalog_keys():
    for station in (Station.WEAPONS, Station.OPZ, Station.HELICOPTER):
        assert "Ctrl+Enter" in station_command_hint(station, Translator("en").t)
        assert "Strg+Enter" in station_command_hint(station, Translator("de").t)
        assert "Strg+Enter" in station_command_hint(station)


def test_font_scale_is_shared_and_draw_restores_current_game_preference(game):
    game.preferences = replace(game.preferences, large_text=True)
    game._apply_text_size()
    assert layout.text_scale() == layout.LARGE_TEXT_SCALE
    assert game.font is layout.font(18)
    layout.set_text_scale(1)
    game.draw()
    assert layout.text_scale() == layout.LARGE_TEXT_SCALE
    assert game.font is layout.font(18)


def test_long_top_bar_and_flash_are_bounded(game):
    game.preferences = replace(game.preferences, large_text=True)
    game.custom_mission_definition = {"objective": {"type": "survive"}}
    game.mission_name_display = lambda: "LONG MISSION " * 80
    game.flash("LONG MESSAGE " * 80)
    with layout.capture_text() as trace:
        game.draw()
    bounded = [entry for entry in trace if "LONG" in entry["text"]]
    assert bounded
    assert all(entry["bounds"].contains(entry["rect"]) for entry in bounded)


def test_joystick_open_hotplug_remove_and_device_failure(game, monkeypatch):
    initial = dict(game._joysticks)
    opened, closed = [], []
    device = NS(init=lambda: opened.append(True), get_instance_id=lambda: 123,
                quit=lambda: closed.append(True))
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda index: device)
    game._open_administration("help")
    event(game, pygame.JOYDEVICEADDED, device_index=0)
    assert opened == [True] and game._joysticks[123] is device
    game._joy_turn = 1
    event(game, pygame.JOYDEVICEREMOVED, instance_id=123)
    assert closed == [True] and 123 not in game._joysticks
    assert game._joy_turn == 0

    def unavailable(index):
        raise pygame.error("device disappeared")

    monkeypatch.setattr(pygame.joystick, "Joystick", unavailable)
    event(game, pygame.JOYDEVICEADDED, device_index=1)
    assert game._joysticks == initial
