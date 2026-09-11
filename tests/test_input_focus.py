"""First delivery gate: exclusive input, safe dialogs and keyboard navigation."""

import json
from pathlib import Path

import pygame
import pytest

from src.core import config
from src.core.commands import MAP_STATIONS, event_feed_heading
from src.core.game import Game
from src.core.station import Station


def press(game, key, **attrs):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, **attrs))


@pytest.fixture
def game():
    return Game(seed=31415, start_menu=False)


@pytest.mark.parametrize("dialog", ["help", "nations", "save", "load", "quit"])
def test_administration_blocks_time_and_all_background_devices(game, dialog):
    press(game, pygame.K_UP)
    game._joy_turn = 1
    game._map_drag = (100, 100)
    game._open_administration(dialog)
    before = game.sim_t, game.ship.target_speed, game.ship.target_course, game.station
    for key in (pygame.K_a, pygame.K_t, pygame.K_PLUS, pygame.K_u, pygame.K_v):
        press(game, key)
    for event in (
        pygame.event.Event(pygame.JOYAXISMOTION, axis=0, value=1.0),
        pygame.event.Event(pygame.JOYBUTTONDOWN, button=0),
        pygame.event.Event(pygame.MOUSEWHEEL, y=1, pos=(200, 200)),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(200, 200)),
    ):
        game.handle_event(event)
    game.update(1.0)
    assert (game.sim_t, game.ship.target_speed, game.ship.target_course, game.station) == before
    assert game.held == set()
    assert game._joy_turn == 0
    assert game._map_drag is None
    game.draw()
    press(game, pygame.K_ESCAPE)
    assert not game.administration_open


def test_help_preserves_manual_pause_and_does_not_open_quit(game):
    press(game, pygame.K_p)
    press(game, pygame.K_F1)
    press(game, pygame.K_ESCAPE)
    assert game.paused and not game.quit_confirm
    press(game, pygame.K_v)
    press(game, pygame.K_PLUS)
    assert game.input_mode is None
    assert game.ship.target_speed == config.SHIP_SPEED_START_KN


def test_focus_loss_clears_controls_and_does_not_auto_resume(game):
    press(game, pygame.K_UP)
    game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSLOST))
    game.handle_event(pygame.event.Event(pygame.WINDOWFOCUSGAINED))
    assert game.paused and not game.held
    press(game, pygame.K_p)
    assert not game.paused
    assert game.steering_input() == (0, 0)


@pytest.mark.parametrize("in_menu", [True, False])
def test_window_close_defaults_to_return_and_ignores_key_repeat(game, in_menu):
    game.in_menu = in_menu
    game.handle_event(pygame.event.Event(pygame.QUIT))
    press(game, pygame.K_DOWN)
    press(game, pygame.K_DOWN, repeat=True)
    assert game.quit_selection == 1
    game.handle_event(pygame.event.Event(pygame.QUIT))
    assert game.running
    press(game, pygame.K_ESCAPE)
    game.handle_event(pygame.event.Event(pygame.QUIT))
    press(game, pygame.K_RETURN)
    assert game.running and not game.quit_confirm


def test_every_station_reachable_from_every_station(game):
    for origin in Station:
        for index, destination in enumerate(Station):
            game.station = origin
            press(game, pygame.K_1 + index)
            assert game.station is destination
    game.station = Station.BRIDGE
    press(game, pygame.K_TAB, mod=pygame.KMOD_SHIFT)
    assert game.station is Station.ELOKA


def test_active_station_number_cycles_only_its_real_pages(game):
    game.station = Station.BRIDGE
    game.sonar_page = 4
    press(game, pygame.K_2)
    assert game.station is Station.SONAR and game.sonar_page == 4

    game.held.add(pygame.K_LEFT)
    game.pinned_tooltip = {"title": "old", "lines": []}
    press(game, pygame.K_2)
    assert game.sonar_page == 5
    assert not game.held and game.pinned_tooltip is None
    press(game, pygame.K_2)
    assert game.sonar_page == 0

    press(game, pygame.K_1)
    press(game, pygame.K_1)
    assert game.station is Station.BRIDGE and game.sonar_page == 0


def test_numeric_entry_owns_station_digits(game):
    game.station = Station.BRIDGE
    press(game, pygame.K_u)
    press(game, pygame.K_2)
    assert game.station is Station.BRIDGE
    assert game.input_mode == "course" and game.input_buffer == "2"

    press(game, pygame.K_9)
    assert game.station is Station.BRIDGE
    assert game.input_buffer == "29"


def test_team_assignment_allows_teams_to_share_selected_room(game):
    game.station = Station.DAMAGE
    rooms = list(game.damage.compartments)
    for room in rooms[:2]:
        game.damage.compartments[room].state = "BESCHAEDIGT"
    game.dmg_cursor = 1
    press(game, pygame.K_RETURN)
    assert game.damage.teams[1] == rooms[1]
    press(game, pygame.K_DOWN)
    press(game, pygame.K_RETURN)
    assert game.damage.teams[1] == rooms[1]
    assert game.damage.teams[2] == rooms[1]
    press(game, pygame.K_LEFT)
    press(game, pygame.K_RETURN)
    assert game.damage.teams[2] == rooms[0]
    press(game, pygame.K_BACKSPACE)
    assert game.damage.teams[2] is None
    assert game.ship.target_course == game.ship.course


def test_numeric_input_stays_live_and_invalid_value_remains_editable(game):
    press(game, pygame.K_UP)
    press(game, pygame.K_u)
    assert not game.held
    for key in (pygame.K_9, pygame.K_9, pygame.K_9, pygame.K_RETURN):
        press(game, key)
    assert game.input_mode == "course" and game.input_buffer == "999"
    game.update(0.05)
    assert game.sim_t > 0.0
    for _ in range(3):
        press(game, pygame.K_BACKSPACE)
    press(game, pygame.K_KP9)
    press(game, pygame.K_KP0)
    press(game, pygame.K_KP_ENTER)
    assert game.input_mode is None and game.ship.target_course == 90.0


def test_save_selection_and_overwrite_require_confirmation(game):
    path = Path(config.SAVE_DIR) / "slot2.json"
    press(game, pygame.K_s)
    press(game, pygame.K_2)
    assert not path.exists()
    press(game, pygame.K_RETURN)
    original = path.read_bytes()
    game.score += 1
    press(game, pygame.K_s)
    press(game, pygame.K_2)
    press(game, pygame.K_RETURN)
    assert game.save_confirm and path.read_bytes() == original
    press(game, pygame.K_RETURN)
    assert json.loads(path.read_text())["score"] == game.score


def test_quit_save_failure_keeps_mission_and_original_file(game, monkeypatch):
    game.save_to_slot(1)
    path = Path(config.SAVE_DIR) / "slot1.json"
    original = path.read_bytes()

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("src.core.game.os.replace", fail_replace)
    press(game, pygame.K_ESCAPE)
    press(game, pygame.K_DOWN)
    press(game, pygame.K_RETURN)
    press(game, pygame.K_1)
    press(game, pygame.K_RETURN)
    press(game, pygame.K_RETURN)
    assert game.running and game.save_ui == "save"
    assert path.read_bytes() == original
    assert list(Path(config.SAVE_DIR).iterdir()) == [path]


def test_save_and_quit_only_after_success(game):
    press(game, pygame.K_ESCAPE)
    press(game, pygame.K_DOWN)
    press(game, pygame.K_RETURN)
    press(game, pygame.K_3)
    assert game.running
    press(game, pygame.K_RETURN)
    assert not game.running
    assert (Path(config.SAVE_DIR) / "slot3.json").exists()


def test_scenario_briefing_starts_selected_mission(game):
    game.in_menu = True
    press(game, pygame.K_3)
    press(game, pygame.K_RETURN)
    assert game.scenario_key == config.SCENARIO_ORDER[2]
    press(game, pygame.K_RETURN)
    assert not game.in_menu and game.scenario_key == config.SCENARIO_ORDER[2]


def test_random_scenario_accepts_default_difficulty(game):
    game.in_menu = True
    press(game, pygame.K_4)
    press(game, pygame.K_RETURN)
    assert 0 <= game.menu_sel < len(config.LEVEL_ORDER)
    press(game, pygame.K_RETURN)
    assert not game.in_menu and game.scenario_key == "s4_zufall"


def test_global_telegraph_reaches_astern_without_wrapping_at_flank(game):
    game.station = Station.SONAR
    for _ in range(10):
        press(game, pygame.K_MINUS)
    assert game.ship.telegraph == "ASTERN"
    assert game.ship.target_speed == config.ASTERN_SPEED_KN
    for _ in range(10):
        press(game, pygame.K_PLUS)
    assert game.ship.target_speed == config.SHIP_SPEED_MAX_KN
    assert game.sonar.gain_db == 0.0


def test_save_draw_does_not_read_disk(game, monkeypatch):
    press(game, pygame.K_s)

    def unexpected_open(*args, **kwargs):
        pytest.fail("Rendering must use cached metadata")

    monkeypatch.setattr("builtins.open", unexpected_open)
    game.draw_save_ui()


@pytest.mark.parametrize("dialog,draw_name", [
    ("help", "draw_help_overlay"), ("nations", "draw_nations_overlay"),
    ("save", "draw_save_ui"), ("quit", "draw_quit_overlay"),
])
def test_game_over_dialog_renders_above_end_panel(game, monkeypatch, dialog, draw_name):
    order = []
    game._end_mission(False, "Test")
    game._open_administration(dialog)
    monkeypatch.setattr(game, "draw_end_panel", lambda: order.append("end"))
    monkeypatch.setattr(game, draw_name, lambda: order.append("dialog"))
    game.draw()
    assert order == ["end", "dialog"]


@pytest.mark.parametrize("screen", ["scenario", "level", "briefing"])
def test_help_accessible_and_visible_in_menu(game, monkeypatch, screen):
    game.in_menu = True
    game.menu_screen = screen
    rendered = []
    monkeypatch.setattr(game, "draw_help_overlay", lambda: rendered.append(True))
    press(game, pygame.K_F1)
    game.draw()
    assert rendered and game.help_open
    press(game, pygame.K_ESCAPE)
    assert game.in_menu and not game.administration_open


def test_quit_from_menu_never_saves_unstarted_scenario(game):
    game.in_menu = True
    press(game, pygame.K_3)
    press(game, pygame.K_RETURN)
    game.handle_event(pygame.event.Event(pygame.QUIT))
    press(game, pygame.K_DOWN)
    press(game, pygame.K_RETURN)
    assert not game.running
    assert not list(Path(config.SAVE_DIR).glob("*.json"))


def test_end_mission_cancels_live_entry_and_allows_restart(game):
    press(game, pygame.K_u)
    game._map_drag = (100, 100)
    game._end_mission(False, "Test")
    assert game.input_mode is None and game._map_drag is None
    press(game, pygame.K_r)
    assert not game.game_over
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(200, 200)))
    assert game._map_drag is None


def test_load_from_slot_keeps_camera_and_station(game):
    game.station = Station.RADIO
    game.map_view.cx, game.map_view.cy = 123.0, 234.0
    game.map_view.scale = 4.0
    game.map_follow = False
    game.save_to_slot(1)
    game.reset(game.seed)
    assert game.load_from_slot(1)
    assert game.station is Station.RADIO
    assert (game.map_view.cx, game.map_view.cy, game.map_view.scale) == (123.0, 234.0, 4.0)
    assert not game.map_follow


@pytest.mark.parametrize("context", ["menu", "course", "quit"])
def test_alt_enter_never_confirms_current_action(game, monkeypatch, context):
    toggles = []
    monkeypatch.setattr(game, "toggle_fullscreen", lambda: toggles.append(True))
    if context == "menu":
        game.in_menu = True
    elif context == "course":
        press(game, pygame.K_u)
        game.input_buffer = "180"
    else:
        press(game, pygame.K_ESCAPE)
        game.quit_selection = 2
    press(game, pygame.K_RETURN, mod=pygame.KMOD_ALT)
    assert toggles and game.running
    if context == "menu":
        assert game.menu_screen == "scenario"
    elif context == "course":
        assert game.input_mode == "course"
    else:
        assert game.quit_confirm


def test_escape_quits_but_q_is_station_scoped_map_zoom(game):
    game.station = Station.BRIDGE
    before = game.map_view.scale
    press(game, pygame.K_q)
    assert not game.quit_confirm
    assert game.map_view.scale < before
    press(game, pygame.K_e)
    assert game.map_view.scale == pytest.approx(before)
    press(game, pygame.K_ESCAPE)
    assert game.quit_confirm


@pytest.mark.parametrize("station", list(Station))
def test_map_keyboard_controls_are_limited_to_visible_map_stations(game, station):
    game.station = station
    scale, follow = game.map_view.scale, game.map_follow
    press(game, pygame.K_q)
    press(game, pygame.K_k)
    if station in MAP_STATIONS:
        assert game.map_view.scale < scale
        assert game.map_follow is not follow
    else:
        assert game.map_view.scale == scale
        assert game.map_follow is follow


def test_event_feed_does_not_advertise_station_commands():
    for station in Station:
        assert event_feed_heading(station) == "EREIGNIS-FEED"


def test_stale_held_depth_controls_never_steer_outside_bridge(game):
    game.station = Station.WEAPONS
    game.held.update((pygame.K_UP, pygame.K_DOWN))
    game._joy_turn = 1
    before = game.ship.target_course
    assert game.steering_input() == (0, 0)
    game.update(0.1)
    assert game.ship.target_course == before
