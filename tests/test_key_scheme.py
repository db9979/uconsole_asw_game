"""The unified key scheme (1.3.114): the same function has the same key at
every station, on the frigate and on the submarine."""

import sys
from pathlib import Path

import pygame
import pytest

from src.core import opfor, opz_display, uboot_local
from src.core.commands import STATION_PAGES
from src.core.game import Game
from src.core.game_bugreport import BUG_REPORT_ENTRY
from src.core.game_logbook import LOGBOOK_HINT_TOKENS
from src.core.help import STATION_HELP, _UBOOT_GLOBAL_HELP, _UBOOT_HELP
from src.core.i18n import Translator
from src.core.station import Station
from src.ui import pointer

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _game as _boat_game  # noqa: E402


def _key(game, key, mod=0):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))


def _frigate():
    return Game(seed=4711, start_menu=False, audio_enabled=False)


def _local_boat():
    game = _boat_game()
    game.local_side = "uboot"
    game._update(0.05)
    return game, game.opfor


def test_weapons_t_enters_the_torpedo_depth_and_never_fires(monkeypatch):
    game = _frigate()
    game.station = Station.WEAPONS
    fired = []
    monkeypatch.setattr(game, "launch_torpedo", lambda: fired.append(True))
    _key(game, pygame.K_t)
    assert game.input_mode == "torpedo_depth" and not fired
    for key in (pygame.K_1, pygame.K_2, pygame.K_0, pygame.K_RETURN):
        _key(game, key)
    assert game.input_mode is None and game.torpedo_depth == 120.0
    _key(game, pygame.K_t)
    for key in (pygame.K_5, pygame.K_RETURN):     # 5 m is out of range: stays open
        _key(game, key)
    assert game.input_mode == "torpedo_depth" and game.torpedo_depth == 120.0
    _key(game, pygame.K_RETURN, pygame.KMOD_CTRL)
    assert game.input_mode == "torpedo_depth" and not fired
    _key(game, pygame.K_ESCAPE)
    _key(game, pygame.K_RETURN, pygame.KMOD_CTRL)
    assert fired == [True]


def test_page_keys_page_every_station_with_several_pages():
    game = _frigate()
    for station in (Station.BRIDGE, Station.WEAPONS, Station.DAMAGE, Station.OPZ,
                    Station.RADIO):
        game.station, game.station_page = station, 0
        count = len(STATION_PAGES[station])
        assert count > 1
        _key(game, pygame.K_PAGEDOWN)
        assert game.station_page == 1
        _key(game, pygame.K_PAGEUP)
        _key(game, pygame.K_PAGEUP)
        assert game.station_page == count - 1


def test_eloka_e_jams_and_ctrl_f_filters_the_band(monkeypatch):
    game = _frigate()
    game.station = Station.ELOKA
    calls = []
    monkeypatch.setattr(game, "deploy_jamming", lambda track: calls.append("jam") or True)
    monkeypatch.setattr(game, "_cycle_jamming_technique",
                        lambda track: calls.append("technique") or "noise")
    _key(game, pygame.K_e)
    _key(game, pygame.K_e, pygame.KMOD_SHIFT)
    _key(game, pygame.K_j)                         # J is the sound, never the jammer
    assert calls == ["jam", "technique"]
    assert game.eloka_audio_enabled is False


def test_submarine_uses_the_frigate_keys_for_shared_functions():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot")
    _key(game, pygame.K_g)                         # G: action stations
    assert boat.watch.action_stations
    _key(game, pygame.K_g)
    assert not boat.watch.action_stations
    _key(game, pygame.K_b)                         # B no longer does it
    assert not boat.watch.action_stations
    _key(game, pygame.K_a)                         # A: silent running
    assert boat.orders.silent


def test_submarine_decoy_is_v_at_weapons_and_speed_stays_v_at_command(monkeypatch):
    game, boat = _local_boat()
    decoys = []
    monkeypatch.setattr(boat.sub, "command_decoy", lambda: decoys.append(True) or True)
    uboot_local.set_local_station(game, "uboot_weapons")
    _key(game, pygame.K_x)
    assert not decoys
    _key(game, pygame.K_v)
    assert decoys == [True] and game.input_mode is None
    uboot_local.set_local_station(game, "uboot")
    _key(game, pygame.K_v)
    assert game.input_mode == "uboot_speed" and decoys == [True]


def test_submarine_crew_page_uses_w_m_u_and_shift_o_fits_an_absorber(monkeypatch):
    game, boat = _local_boat()
    calls = []
    monkeypatch.setattr(game, "boat_change_watch", lambda: calls.append("watch") or True)
    monkeypatch.setattr(game, "boat_casualty_medic", lambda: calls.append("medic"))
    monkeypatch.setattr(game, "boat_casualty_reassign", lambda: calls.append("reassign"))
    monkeypatch.setattr(boat.sub, "command_absorber", lambda: calls.append("absorber") or True)
    monkeypatch.setattr(boat.sub, "command_o2_candle", lambda: calls.append("candle") or True)
    uboot_local.set_local_station(game, "uboot_engine")
    boat.command_page = 3                          # damage page
    for key in (pygame.K_w, pygame.K_m, pygame.K_u):
        _key(game, key)
    assert calls == ["watch", "medic", "reassign"]
    boat.command_page = 1                          # stores page
    _key(game, pygame.K_a)                         # A is silent running now
    _key(game, pygame.K_o, pygame.KMOD_SHIFT)
    _key(game, pygame.K_o)
    assert calls[3:] == ["absorber", "candle"]
    assert boat.orders.silent


def test_help_tables_name_the_unified_keys():
    def keys(table):
        return {action: key for key, action in table}
    weapons = keys(STATION_HELP[Station.WEAPONS][1])
    assert weapons["help.control.fire"] == "Ctrl+Enter"
    opz = keys(STATION_HELP[Station.OPZ][1])
    assert opz["help.control.essm"] == "Ctrl+Enter"
    assert opz["help.control.radar_range"] == "Q / E"
    helo = keys(STATION_HELP[Station.HELICOPTER][1])
    assert helo["help.control.helo_radar"] == opz["help.control.mpa_radar"] == "Ctrl+R"
    assert helo["help.control.mad"] == opz["help.control.mpa_mad"] == "Shift+M"
    assert helo["help.control.dip_ping"] == "Shift+A"
    for station in (Station.BRIDGE, Station.ENGINE):
        assert keys(STATION_HELP[station][1])["help.control.course_input"] == "C"
    boat = keys(_UBOOT_HELP[1])
    assert boat["help.uboot.action_stations"] == "G"
    assert boat["help.uboot.silent"] == "A"
    assert boat["help.uboot.decoy"] == keys(STATION_HELP[Station.WEAPONS][1])[
        "help.control.nixie"] == "V"


def test_shift_a_and_ctrl_r_at_weapons_never_fire(monkeypatch):
    # Shift+A is the ping key and Ctrl+R the aircraft radar key everywhere.
    game = _frigate()
    game.station = Station.WEAPONS
    fired = []
    for name in ("fire_own_asroc", "fire_rbu", "fire_rbu_defence", "drop_depth_charges"):
        monkeypatch.setattr(game, name, lambda name=name: fired.append(name))
    _key(game, pygame.K_a, pygame.KMOD_SHIFT)
    _key(game, pygame.K_a, pygame.KMOD_CTRL)
    _key(game, pygame.K_r, pygame.KMOD_CTRL)
    _key(game, pygame.K_z, pygame.KMOD_CTRL)
    assert fired == []
    _key(game, pygame.K_a)
    _key(game, pygame.K_r)
    _key(game, pygame.K_r, pygame.KMOD_SHIFT)
    _key(game, pygame.K_z)
    assert fired == ["fire_own_asroc", "fire_rbu", "fire_rbu_defence", "drop_depth_charges"]


def test_submarine_shift_a_never_toggles_silent_running():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot")
    before = boat.orders.silent
    _key(game, pygame.K_a, pygame.KMOD_SHIFT)
    assert boat.orders.silent == before
    _key(game, pygame.K_a)
    assert boat.orders.silent != before


# --- 2026-10-03 audit (P-02 … P-11): one key, one meaning ----------------------


def _type(game, text):
    for char in text:
        _key(game, pygame.K_0 + int(char))


@pytest.mark.parametrize("distance", ["", "6"])
def test_submarine_fire_by_bearing_fires_only_on_ctrl_enter(monkeypatch, distance):
    game, boat = _local_boat()
    shots = []
    monkeypatch.setattr(uboot_local, "_fire_bearing",
                        lambda _game, _boat, range_nm: shots.append(range_nm) or True)
    uboot_local.set_local_station(game, "uboot_weapons")
    _key(game, pygame.K_f)
    _type(game, "090")
    _key(game, pygame.K_RETURN)
    assert game.input_mode == "uboot_range"
    _type(game, distance)
    _key(game, pygame.K_RETURN)                    # Enter confirms, it never fires
    _key(game, pygame.K_KP_ENTER)
    assert game.input_mode == "uboot_range" and shots == []
    _key(game, pygame.K_RETURN, pygame.KMOD_CTRL)
    assert game.input_mode is None
    assert shots == [float(distance) if distance else None]


def test_submarine_fire_by_bearing_keeps_a_bad_distance_open(monkeypatch):
    game, boat = _local_boat()
    shots = []
    monkeypatch.setattr(uboot_local, "_fire_bearing",
                        lambda *args: shots.append(args) or True)
    uboot_local.set_local_station(game, "uboot_weapons")
    _key(game, pygame.K_f)
    _type(game, "90")
    _key(game, pygame.K_RETURN)
    _type(game, "99")                              # beyond 40 NM
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_RETURN, pygame.KMOD_CTRL)
    assert game.input_mode == "uboot_range" and shots == []
    _key(game, pygame.K_ESCAPE)
    assert game.input_mode is None and shots == []


@pytest.mark.parametrize("side, in_menu, title", [
    ("frigate", False, "help.global.title"),
    ("uboot", False, "help.uboot_global.title"),
    ("frigate", True, "help.menu.title"),
])
def test_help_page_zero_shows_the_keys_of_where_you_are(side, in_menu, title):
    game, _boat = _local_boat()
    game.local_side, game.in_menu, game.help_page = side, in_menu, 0
    lines, _visible = game._help_lines()
    assert lines[0] == Translator(game.preferences.language).t(title)


def test_submarine_global_help_lists_only_keys_that_work_aboard():
    keys = {key for key, _action in _UBOOT_GLOBAL_HELP[1]}
    assert not keys & {"F2", "F3", "F4", "F8", "N", "P", "help.key.plot_keys"}
    assert {"F1 / ?", "F11", "Shift+F2", "0", "Ctrl+Enter", "Shift+A"} <= keys
    game, _boat = _local_boat()
    _key(game, pygame.K_F11)
    assert game.feed_overlay_open
    _key(game, pygame.K_F11)
    for key in (pygame.K_F3, pygame.K_F4, pygame.K_F8):   # frigate-only overlays
        _key(game, key)
    assert not game.autocrew_overview_open and not game.simlog_view_open


@pytest.mark.parametrize("key, mod, step", [
    (pygame.K_c, 0, 1), (pygame.K_c, pygame.KMOD_SHIFT, -1),
    (pygame.K_RIGHT, 0, 1), (pygame.K_LEFT, 0, -1),
])
def test_submarine_esm_c_classifies_like_the_frigate_esm(monkeypatch, key, mod, step):
    game, boat = _local_boat()
    steps = []
    monkeypatch.setattr(boat.esm, "cycle_classification",
                        lambda _game, _number, direction=1: steps.append(direction) or True)
    uboot_local.set_local_station(game, "uboot_esm")
    boat.command_page = 0
    _key(game, key, mod)
    assert steps == [step] and game.input_mode is None


@pytest.mark.parametrize("station, key, mod", [
    ("uboot_weapons", pygame.K_v, pygame.KMOD_SHIFT),
    ("uboot_weapons", pygame.K_v, pygame.KMOD_CTRL),
    ("uboot", pygame.K_c, pygame.KMOD_CTRL),
    ("uboot", pygame.K_d, pygame.KMOD_SHIFT),
    ("uboot", pygame.K_n, pygame.KMOD_CTRL),
    ("uboot_engine", pygame.K_a, pygame.KMOD_CTRL),
])
def test_submarine_plain_keys_ignore_shift_and_ctrl(monkeypatch, station, key, mod):
    game, boat = _local_boat()
    calls = []
    monkeypatch.setattr(boat.sub, "command_decoy", lambda: calls.append("decoy") or True)
    monkeypatch.setattr(boat.sub, "command_snorkel", lambda on: calls.append("snorkel") or True)
    monkeypatch.setattr(boat.sub, "command_silent", lambda on: calls.append("silent") or True)
    uboot_local.set_local_station(game, station)
    _key(game, key, mod)
    assert calls == [] and game.input_mode is None
    assert uboot_local._key_action(key, mod, station) is None


@pytest.mark.parametrize("station, pings", [("uboot", True), ("uboot_sonar", True),
                                            ("uboot_engine", False)])
def test_submarine_shift_a_pings_at_command_and_sonar(monkeypatch, station, pings):
    game, boat = _local_boat()
    calls = []
    monkeypatch.setattr(opfor, "send_ping", lambda _game, crew: calls.append(crew) or True)
    uboot_local.set_local_station(game, station)
    before = boat.orders.silent
    _key(game, pygame.K_a, pygame.KMOD_SHIFT)
    assert calls == ([boat] if pings else [])
    assert boat.orders.silent == before


def test_periscope_q_e_switch_power_and_arrows_train():
    game, boat = _local_boat()
    uboot_local.set_local_station(game, "uboot_esm")
    boat.command_page = 1                          # periscope page
    sight = boat.scope_optics
    sight.power_index = 0
    _key(game, pygame.K_e)
    assert sight.power_index == 1
    _key(game, pygame.K_q)
    assert sight.power_index == 0
    before = opfor.scope_bearing(boat)
    _key(game, pygame.K_RIGHT)
    assert opfor.scope_bearing(boat) != before


def test_bridge_binoculars_arrows_train_and_q_e_zoom():
    game = _frigate()
    game.station, game.station_page = Station.BRIDGE, 2
    game.lookout_glasses = True
    rel = game.lookout_glasses_rel
    _key(game, pygame.K_RIGHT)
    assert game.lookout_glasses_rel != rel
    _key(game, pygame.K_LEFT)
    assert game.lookout_glasses_rel == rel
    assert pygame.K_RIGHT not in game.held and pygame.K_LEFT not in game.held
    power = game.lookout_optics.power_index
    _key(game, pygame.K_e)
    assert game.lookout_optics.power_index == min(power + 1,
                                                  len(game.lookout_optics.powers) - 1)


@pytest.mark.parametrize("key, mod, method", [
    (pygame.K_a, pygame.KMOD_SHIFT, "send_helicopter_dipping_ping"),
    (pygame.K_g, 0, "_toggle_sonar_release"),
    (pygame.K_r, pygame.KMOD_CTRL, "set_helicopter_radar"),
    (pygame.K_w, 0, "helicopter_waypoint_to_selection"),
])
def test_helicopter_keys_follow_the_scheme(monkeypatch, key, mod, method):
    game = _frigate()
    game.station, game.station_page = Station.HELICOPTER, 1
    calls = []
    monkeypatch.setattr(game, method, lambda *args: calls.append(args) or True)
    _key(game, key, mod)
    assert len(calls) == 1


def test_helicopter_w_sets_the_waypoint_on_the_selected_contact():
    from types import SimpleNamespace
    game = _frigate()
    game.station, game.station_page = Station.HELICOPTER, 1
    _key(game, pygame.K_w)                         # nothing selected: no waypoint
    assert game.helicopter_waypoint_to_selection() == "no_contact"
    contact = SimpleNamespace(target_id=987654, observed_x=game.ship.x + 4.0,
                              observed_y=game.ship.y - 3.0)
    game.sonar.contacts[contact.target_id] = contact
    game.selected_contact = contact
    try:
        _key(game, pygame.K_w)
        assert (game.helo.waypoint_x, game.helo.waypoint_y) == pytest.approx(
            (contact.observed_x, contact.observed_y))
        bearing_only = SimpleNamespace(target_id=987655, bearing=45.0)
        game.sonar.contacts[bearing_only.target_id] = bearing_only
        game.selected_contact = bearing_only
        assert game.helicopter_waypoint_to_selection() == "not_located"
    finally:
        game.sonar.contacts.pop(987654, None)
        game.sonar.contacts.pop(987655, None)
        game.selected_contact = None


@pytest.mark.parametrize("key, mod, expected", [
    (pygame.K_e, 0, ["jam"]), (pygame.K_e, pygame.KMOD_SHIFT, ["technique"]),
    (pygame.K_j, 0, []), (pygame.K_c, 0, ["classify"]),
])
def test_eloka_keys_follow_the_scheme(monkeypatch, key, mod, expected):
    game = _frigate()
    game.station = Station.ELOKA
    calls = []
    monkeypatch.setattr(game, "deploy_jamming", lambda track: calls.append("jam") or True)
    monkeypatch.setattr(game, "_cycle_jamming_technique",
                        lambda track: calls.append("technique") or "noise")
    monkeypatch.setattr(game, "_cycle_eloka_annotation", lambda: calls.append("classify"))
    audio = game.eloka_audio_enabled
    _key(game, key, mod)
    assert calls == expected
    assert (game.eloka_audio_enabled != audio) is (key == pygame.K_j)


@pytest.mark.parametrize("screen, live", [
    ("main", True), ("scenario", True), ("difficulty", True), ("briefing", True),
    ("logbook", False), (BUG_REPORT_ENTRY, False), ("side", False), ("training", False),
    ("daily", False), ("campaign", False),
])
def test_world_seed_and_fullscreen_keys_only_on_main_menu_and_scenario_pages(monkeypatch,
                                                                        screen, live):
    game = _frigate()
    game.in_menu = True
    game.main_menu = screen == "main"
    game.menu_screen = "scenario" if screen == "main" else screen
    monkeypatch.setattr(game, "_handle_logbook_key", lambda key: None)
    monkeypatch.setattr(game, "_handle_bug_report_key", lambda key: None)
    monkeypatch.setattr(game, "_handle_daily_key", lambda key: None)
    monkeypatch.setattr(game, "_handle_campaign_menu_key", lambda key: None)
    fullscreen = []
    monkeypatch.setattr(game, "toggle_fullscreen", lambda *args, **kw: fullscreen.append(1))
    world, seed = game.world_mode, game.seed
    for key in (pygame.K_w, pygame.K_r, pygame.K_f):
        game._handle_menu_key(key)
    assert (game.world_mode != world) is live
    assert (game.seed != seed) is live
    assert bool(fullscreen) is live


def test_real_sector_moves_with_brackets_and_page_keys_scroll_the_list():
    game = _frigate()
    game.in_menu, game.main_menu, game.menu_screen = True, False, "scenario"
    game.world_mode = "real_fixed"
    seed = game.seed
    game._handle_menu_key(pygame.K_PAGEDOWN)
    assert game.seed == seed
    game._handle_menu_key(pygame.K_RIGHTBRACKET)
    assert game.seed % 128 == (seed % 128 + 1) % 128
    game._handle_menu_key(pygame.K_LEFTBRACKET)
    assert game.seed == seed


def test_radio_tasks_page_enter_accepts_the_task(monkeypatch):
    game = _frigate()
    game.station = Station.RADIO
    calls = []
    monkeypatch.setattr(game, "_task_accept_selected", lambda: calls.append("accept"))
    monkeypatch.setattr(game, "capture_hfdf", lambda: calls.append("hfdf"))
    game.station_page = 2
    _key(game, pygame.K_RETURN)
    game.station_page = 0
    _key(game, pygame.K_RETURN)
    assert calls == ["accept", "hfdf"]


def test_opz_display_backspace_resets_the_row_and_shift_backspace_all():
    game = _frigate()
    game.station, game.station_page = Station.OPZ, 4
    game.opz_display_sel = 0
    _key(game, pygame.K_RIGHT)                     # row 0 off its default
    _key(game, pygame.K_DOWN)
    _key(game, pygame.K_RIGHT)                     # row 1 off its default
    changed = dict(game.preferences.opz_display)
    assert len(changed) == 2
    _key(game, pygame.K_BACKSPACE)                 # only row 1 goes back
    assert dict(game.preferences.opz_display) == {
        key: value for key, value in changed.items() if key == opz_display.KEYS[0]}
    _key(game, pygame.K_BACKSPACE, pygame.KMOD_SHIFT)
    assert game.preferences.opz_display == ()


def test_logbook_footer_names_and_clicks_every_key():
    for lang in ("en", "de"):
        text = Translator(lang).t("logbook.hint")
        spans = pointer.token_spans(text, LOGBOOK_HINT_TOKENS)
        assert len(spans) == len(LOGBOOK_HINT_TOKENS)
