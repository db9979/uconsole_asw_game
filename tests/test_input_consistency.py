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
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
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
    assert not game.held and game._joy_turn == 0
    event(game, pygame.WINDOWFOCUSGAINED)
    received.clear()
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 25))
    assert not received
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=(800, 500))
    assert received[-1].pos == (640, 360)
    event(game, pygame.MOUSEMOTION, pos=(825, 525), rel=(25, 25))
    assert received[-1].pos == (660, 380)
    assert received[-1].rel == (20, 20)


def test_opz_wheel_zooms_independent_map_even_before_draw(game, monkeypatch):
    game.station = Station.OPZ
    monkeypatch.setattr(config, "STATION_RECT", config.STATION_PANEL_RECT)
    pos = opz_ppi_rect(config.OPZ_STATION_RECT).center
    assert not opz_ppi_rect().collidepoint(pos)
    game.opz_range_nm = config.RADAR_RANGE_SCALES_NM[1]
    before = game.opz_map_view.scale
    event(game, pygame.MOUSEWHEEL, y=0, x=1, pos=pos)
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[1]
    event(game, pygame.MOUSEWHEEL, y=1, pos=pos)
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[1]
    assert game.opz_map_view.scale > before
    event(game, pygame.MOUSEWHEEL, y=-1, pos=(1200, 100))
    assert game.opz_range_nm == config.RADAR_RANGE_SCALES_NM[1]
    assert config.STATION_RECT == config.STATION_PANEL_RECT


def test_opz_pan_follow_and_radar_range_are_independent(game):
    game.station = Station.OPZ
    chart = opz_ppi_rect(config.OPZ_STATION_RECT)
    start = (chart.centerx + 120, chart.centery + 80)
    end = (start[0] + 30, start[1] + 20)
    before_center = (game.opz_map_view.cx, game.opz_map_view.cy)
    event(game, pygame.MOUSEBUTTONDOWN, button=1, pos=start)
    event(game, pygame.MOUSEMOTION, pos=end, rel=(30, 20))
    event(game, pygame.MOUSEBUTTONUP, button=1, pos=end)
    assert not game.opz_map_follow
    assert (game.opz_map_view.cx, game.opz_map_view.cy) != before_center
    map_state = (game.opz_map_view.cx, game.opz_map_view.cy,
                 game.opz_map_view.scale)
    before_range = game.opz_range_nm
    press(game, pygame.K_PAGEUP)
    assert game.opz_range_nm > before_range
    assert (game.opz_map_view.cx, game.opz_map_view.cy,
            game.opz_map_view.scale) == map_state
    press(game, pygame.K_k)
    assert game.opz_map_follow
    assert (game.opz_map_view.cx, game.opz_map_view.cy) == pytest.approx(
        (game.ship.x, game.ship.y))


def test_opz_zoom_is_cursor_centred_and_limited_to_quarter_mile_radius(game):
    game.station = Station.OPZ
    chart = opz_ppi_rect(config.OPZ_STATION_RECT)
    pivot = (chart.centerx + 100, chart.centery - 70)
    game._configure_opz_map_view(chart)
    world_before = game.opz_map_view.screen_to_world(*pivot)
    for _ in range(30):
        event(game, pygame.MOUSEWHEEL, y=1, pos=pivot)
    assert game.opz_map_view.screen_to_world(*pivot) == pytest.approx(world_before)
    assert min(chart.size) / game.opz_map_view.scale == pytest.approx(
        2.0 * config.OPZ_MAP_MAX_ZOOM_RADIUS_NM)


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
def test_help_all_wrapped_lines_reachable_in_all_categories(game, language, large):
    game.preferences = replace(game.preferences, large_text=large)
    translator = Translator("en" if language == "pseudo" else language)
    if language == "pseudo":
        translator.catalog = pseudolocale(load_catalog("en"))
    game.tr = translator.t
    game.station = Station.SONAR
    game._open_administration("help")
    for page in range(4):
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
    game._open_administration("help")
    press(game, pygame.K_RETURN, mod=pygame.KMOD_CTRL)
    assert len(calls) == 3


def test_primary_weapon_hints_translate_and_do_not_expose_catalog_keys():
    for station in (Station.WEAPONS, Station.OPZ, Station.HELICOPTER):
        assert "Ctrl+Enter" in station_command_hint(station, Translator("en").t)
        assert "Strg+Enter" in station_command_hint(station, Translator("de").t)
        assert "Strg+Enter" in station_command_hint(station)


def test_commander_confirmation_input_precedence_and_station_isolation(game, monkeypatch):
    console = game.commander
    console.address = ("127.0.0.1", 8765)
    console.server = NS(connected=True)
    console.bridge._allowed = True
    console.bridge._proposal = dict(ref="ref", label="C001", status="pending")
    console.bridge._pending_seq = 7
    console._confirm_signature = (7, ("ref", "C001", "pending"), None)
    console._confirm_identity = (id(game.world), id(game.sonar))
    console._confirm_requested = True
    console.confirm_kind = "target"
    decisions = []
    monkeypatch.setattr(console, "_decide_confirmation",
                        lambda current, accepted: decisions.append(accepted))

    game.pinned_tooltip = {"title": "pinned", "lines": []}
    press(game, pygame.K_ESCAPE)
    assert game.pinned_tooltip is None and console.confirm_visible(game)
    press(game, pygame.K_F6, repeat=True)
    assert not decisions
    fullscreen = []
    monkeypatch.setattr(game, "toggle_fullscreen", lambda: fullscreen.append(True))
    press(game, pygame.K_RETURN, mod=pygame.KMOD_ALT)
    assert fullscreen == [True]
    game.input_mode = "course"
    press(game, pygame.K_F6)
    assert not decisions and game.input_mode == "course"
    game.input_mode = None
    press(game, pygame.K_2)
    assert game.station is Station.SONAR
    assert console.confirm_visible(game)
    press(game, pygame.K_F6)
    assert decisions == [True]
    press(game, pygame.K_F9)
    assert game.commander_open


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


def test_compose_frame_survives_replaced_display_surface(game):
    """X11/XWayland can swap pygame's display surface after the first event
    pump; the stale reference becomes 0x0 and blitting to it used to crash
    startup with "Surfaces must not be locked during blit"."""
    game.display = pygame.Surface((0, 0))
    game.screen.fill((10, 200, 30))
    game.compose_frame()
    live = pygame.display.get_surface()
    assert game.display is live
    x, y = live.get_width() // 2, live.get_height() // 2
    assert live.get_at((x, y))[:3] != (0, 0, 0)
