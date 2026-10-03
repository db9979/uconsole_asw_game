"""The unified key scheme (1.3.114): the same function has the same key at
every station, on the frigate and on the submarine."""

import sys
from pathlib import Path

import pygame

from src.core import uboot_local
from src.core.commands import STATION_PAGES
from src.core.game import Game
from src.core.help import STATION_HELP, _UBOOT_HELP
from src.core.station import Station

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
