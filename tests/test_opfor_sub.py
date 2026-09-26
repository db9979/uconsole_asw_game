"""The crewed hostile submarine: orders, weapons, sonar, boundary and sides."""

import json
import math
import sys
from pathlib import Path

import pygame
import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import CommanderServer, OPFOR_ROLES, STATIONS
from src.core import config, uboot_local
from src.core.game import Game
from src.core.station import Station
from src.ui import layout

sys.path.insert(0, str(Path(__file__).parent))
from test_commander_bridge import Server  # noqa: E402


class CrewedServer(Server):
    def __init__(self):
        super().__init__()
        self.crewed = True

    def station_leased(self, role):
        return self.crewed and role in OPFOR_ROLES


def _boat_apply(game, bridge):
    """Apply a boat action from the first boat station that owns it."""
    from src.commander.server import UBOOT_COMMAND_ROLES, V2_ACTION_REGISTRY

    def apply(action, params):
        role = next(role for role in UBOOT_COMMAND_ROLES
                    if role in V2_ACTION_REGISTRY[action].stations)
        return bridge._apply_opfor_action(game, action, params, role)
    return apply


def _game(seed=83):
    return Game(seed=seed, start_menu=False, audio_enabled=False, language="en")


def _crewed(seed=83):
    game = _game(seed)
    server, bridge = CrewedServer(), CommanderBridge()
    bridge.pump(game, server, now=1.0)
    assert game.opfor is not None
    return game, server, bridge


def test_crewed_boat_follows_orders_within_its_limits():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    assert sub.manual
    assert sub.set_orders(course=90.0, speed=5.0, depth=120.0) is True
    assert sub.set_orders(depth=-1.0) == "invalid_value"
    assert sub.set_orders(speed=float("nan")) == "invalid_value"
    for _ in range(20 * 240):
        game._update_sim(0.05)
    assert abs(sub.course - 90.0) < 1.0
    assert abs(sub.speed - 5.0) < 0.2
    assert sub.depth <= sub.safe_depth_m(game.world) + 1e-6
    assert abs(sub.depth - min(120.0, sub.safe_depth_m(game.world))) < 5.0


def test_fire_is_checked_and_becomes_an_enemy_torpedo():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    assert sub.command_fire(float("inf")) == "invalid_value"
    assert sub.command_fire(10.0, 100.0) == "invalid_value"
    launcher = game.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
    outside = (sub.course + launcher.arc_center_deg + launcher.arc_width_deg) % 360.0
    if launcher.arc_width_deg < 360.0:
        assert sub.command_fire(outside) == "out_of_arc"
    bearing = (sub.course + launcher.arc_center_deg) % 360.0
    before = sub.torpedoes_left
    assert sub.command_fire(bearing, 5.0, now=game.sim_t) is True
    assert sub.torpedoes_left == before - 1
    for _ in range(4):
        game._update_sim(0.05)
    assert any(torpedo.launch_platform_id == sub.id for torpedo in game.enemy_torpedoes)
    sub.release_manual()
    assert sub.command_fire(bearing) == "not_ready"


def test_released_boat_returns_to_the_ai():
    game, server, bridge = _crewed()
    sub = game.opfor.sub
    server.crewed = False
    bridge.pump(game, server, now=2.0)
    assert game.opfor is None and not sub.manual


def _scripted_run(seed):
    game, server, bridge = _crewed(seed)
    sub = game.opfor.sub
    sub.set_orders(course=200.0, speed=6.0, depth=90.0)
    for step in range(600):
        game._update_sim(0.1)
        if step == 100:
            with game.sonar_perspective(game.opfor.station):
                game.send_active_ping()
        if step == 300:
            sub.set_orders(course=20.0)
    return game.save_state()


def _first_difference(left, right, path=""):
    if type(left) is not type(right):
        return path
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right), key=str):
            found = _first_difference(left.get(key), right.get(key), f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path} (length)"
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_difference(a, b, f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return None if left == right else path


def test_same_seed_and_orders_give_the_same_state(monkeypatch):
    from src.core.game import Animal, Decoy
    from src.enemies.sub import Sub
    from src.enemies.surface import SurfaceShip
    from src.weapons.torpedo import EnemyTorpedo
    # Entity IDs come from process-wide counters; both runs start equal.
    start = {cls: cls._next_id for cls in (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo)}
    runs = []
    for _ in range(2):
        for cls, value in start.items():
            monkeypatch.setattr(cls, "_next_id", value)
        runs.append(_scripted_run(91))
    # A plain comparison: pytest's text diff of two whole saves takes minutes.
    assert _first_difference(*runs) is None, _first_difference(*runs)


def test_crew_binding_survives_save_and_load(tmp_path):
    """Save v15: a crewed boat stays crewed after a load (no object leaks)."""
    game, _server, _bridge = _crewed()
    sub_id = game.opfor.sub_id
    for _ in range(50):
        game._update_sim(0.1)
    data = game.save_state()
    assert "opfor" not in json.dumps(sorted(data))
    assert data["crew"]["sub_id"] == sub_id
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    restored = _game()
    assert restored.load_game(str(path))
    assert restored.opfor is not None and restored.opfor.sub_id == sub_id
    assert restored.opfor.sub.manual and restored.opfor.sub.crew is restored.opfor.orders
    # Loading over a crewed game rebinds the saved boat, not the old object.
    old_boat = game.opfor
    assert game.load_game(str(path)) and game.opfor is not None
    assert game.opfor is not old_boat and game.opfor.sub in game.subs
    assert [sub.manual for sub in restored.subs].count(True) == 1


def test_submarine_views_never_carry_frigate_truth():
    game, server, bridge = _crewed()
    game.ship.target_speed = 20.0
    now = 1.0
    for step in range(20 * 60):
        game._update_sim(0.05)
        if step % 20 == 0:
            now += 0.5
            bridge.pump(game, server, now=now)
    game._emit_sound("sonar_ping")
    bridge.pump(game, server, now=now + 1.0)
    for role in OPFOR_ROLES:
        state = server.v2_states[role]
        assert state["role"] == role
        blob = json.dumps(state)
        for value in (game.ship.x, game.ship.y):
            assert json.dumps(value) not in blob
        assert state["plot"]["objects"] == []
        assert state["audio"]["events"] == []
    assert all(not rows for role, rows in server.events["events_by_role"].items()
               if role in OPFOR_ROLES)


def test_submarine_sonar_commands_never_touch_the_frigate_sonar():
    game, _server, bridge = _crewed()
    frigate_gain = game.sonar.gain_db
    assert bridge._apply_opfor_action(game, "sonar_set_gain", {"gain_db": 9},
                                      "uboot_sonar") is True
    assert game.opfor.station.sonar.gain_db == 9 and game.sonar.gain_db == frigate_gain
    # Frigate-only actions never run for the submarine roles.
    assert bridge._apply_opfor_action(game, "sonar_set_tas", {"deployed": True},
                                      "uboot_sonar") is False
    assert bridge._apply_opfor_action(game, "bridge_set_course", {"course": 10.0},
                                      "uboot") is False


def test_solo_starts_on_the_frigate_and_one_session_never_mixes_sides():
    server = CommanderServer()
    with server._lock:
        _token, crew = server._new_session_locked("crew", web_host=False)
    assert server.grant_station(crew["client_id"], "sonar")
    assert server.grant_station(crew["client_id"], "uboot") is False
    server.revoke_station("sonar")
    assert server.grant_station(crew["client_id"], "uboot")
    assert server.grant_station(crew["client_id"], "bridge") is False
    server.set_solo_mode(True)
    with server._lock:
        _token, solo = server._new_session_locked("solo", web_host=False)
    assert set(solo["leases"]) == set(STATIONS)


def test_local_submarine_side_keeps_frigate_controls_and_banners_away():
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    assert boat is not None and boat.sub.manual and not game.audio.local_effects

    def key(value, mod=0):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod,
                                             unicode=""))

    target_speed = game.ship.target_speed
    key(pygame.K_PLUS)
    key(pygame.K_3)
    assert game.ship.target_speed == target_speed and game.station is Station.BRIDGE
    assert uboot_local.local_station(game) == "uboot_weapons"
    key(pygame.K_1)
    key(pygame.K_d)
    for value in (pygame.K_1, pygame.K_5, pygame.K_0, pygame.K_RETURN):
        key(value)
    assert boat.sub.order_depth == 150.0
    game.msg = ""
    game.flash("frigate banner")
    assert game.msg == ""
    key(pygame.K_2)
    assert game.station is Station.SONAR
    key(pygame.K_y)
    assert boat.station.sonar.tow_state == game.sonar.tow_state
    key(pygame.K_o)
    assert boat.station.sonar.gain_db > game.sonar.gain_db
    game.draw()
    key(pygame.K_1)
    game.draw()


@pytest.mark.parametrize("language", ["en", "de"])
def test_local_submarine_screen_renders_in_both_languages(language):
    game = Game(seed=5, start_menu=False, audio_enabled=False, language=language)
    game.local_side = "uboot"
    game._update(0.05)
    for station in (Station.BRIDGE, Station.SONAR):
        game.station = station
        game.draw()


def test_simlog_publication_accepts_uncrewed_and_crewed_submarine_roles():
    from dataclasses import replace
    game = _game()
    game.preferences = replace(game.preferences, simlog=True)
    server, bridge = CommanderServer(), CommanderBridge()
    now = 1.0
    for index in range(120):
        game._update(0.05)
        now += 0.1
        bridge.pump(game, server, now=now)   # uncrewed: roles stay redacted
        if index == 60:
            with server._lock:
                _token, session = server._new_session_locked("sub")
            assert server.grant_station(session["client_id"], "uboot_sonar")
    assert game.opfor is not None
    assert all(entry["state"]["role"] == "uboot_sonar"
               for entry in bridge._v2_simlog["uboot_sonar"])


def test_options_page_two_chooses_the_local_side_outside_a_mission_only():
    game = _game()

    def key(value):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=0,
                                             unicode=""))

    assert game.local_side == "frigate"
    # During a mission the row is shown but locked.
    game._open_administration("options")
    key(pygame.K_PAGEDOWN)
    assert game.options_page == 1 and game._option_rows() == ("local_side",)
    key(pygame.K_RETURN)
    assert game.local_side == "frigate"
    game.draw()
    key(pygame.K_ESCAPE)

    game._return_to_main_menu()
    game._open_administration("options")
    assert game.options_page == 1
    key(pygame.K_TAB)
    assert game.options_page == 0 and game.options_sel == 0
    key(pygame.K_TAB)
    key(pygame.K_RIGHT)
    assert game.local_side == "uboot"
    assert not hasattr(game.preferences, "local_side")
    game.draw()
    # Page tabs and the row are clickable (canvas coordinates for this check).
    game._window_to_canvas = lambda pos: pos
    tab = game._options_page_rects()[0]
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                         pos=(tab.center)))
    assert game.options_page == 0
    tab = game._options_page_rects()[1]
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                         pos=(tab.center)))
    row = game._options_row_rects()[0]
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                         pos=(row.center)))
    assert game.options_page == 1 and game.local_side == "frigate"
    # Rows beyond the setup page's one row never act.
    game.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1,
        pos=(game._options_row_rects()[5].center)))
    assert game.options_sel == 0 and game.local_side == "frigate"


class _NoTruth:
    """Stands in for frigate truth: any attribute read fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"submarine screen read frigate truth: {name}")


@pytest.mark.parametrize("mode", ["docked", "ticker"])
@pytest.mark.parametrize("language", ["en", "de"])
def test_local_submarine_command_station_is_drawn_without_frigate_truth(mode, language):
    import dataclasses
    from src.ui import uboot_view
    game = Game(seed=5, start_menu=False, audio_enabled=False, language=language)
    game.preferences = dataclasses.replace(game.preferences, bottom_panel=mode)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    boat.sub.set_orders(course=200.0, speed=6.0, depth=120.0)
    for _ in range(50):
        game._update(0.1)
    ship, sonar_targets = game.ship, game._sonar_targets
    game.ship = _NoTruth()
    game._sonar_targets = _NoTruth()
    try:
        for station, page in ((Station.BRIDGE, 0), (Station.BRIDGE, 1), (Station.SONAR, 0)):
            game.station, boat.command_page = station, page
            game.draw()
    finally:
        game.ship, game._sonar_targets = ship, sonar_targets
    # The chart shows land/sea in the map rect and the boat's own symbol.
    game.station, boat.command_page = Station.BRIDGE, 0
    game.draw()
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        view = uboot_view.chart_view(game, boat)
        point = tuple(int(value) for value in view.world_to_screen(boat.sub.x, boat.sub.y))
    friend = uboot_view.nato_symbols.AFFILIATION_COLORS["FRIEND"]
    near = [game.screen.get_at((point[0] + dx, point[1] + dy))[:3]
            for dx in range(-12, 13) for dy in range(-12, 13)]
    assert friend in near


def test_submarine_chart_and_pages_are_the_boats_own_controls():
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    frigate_view = (game.map_view.scale, game.map_view.cx, game.map_view.cy)

    def key(value):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=0, unicode=""))

    game.draw()
    scale = boat.chart_view.scale
    key(pygame.K_q)
    assert boat.chart_view.scale < scale
    key(pygame.K_e)
    key(pygame.K_e)
    assert boat.chart_view.scale > scale
    key(pygame.K_k)
    assert boat.chart_follow is False
    key(pygame.K_PAGEDOWN)
    assert boat.command_page == 1
    key(pygame.K_PAGEUP)
    assert boat.command_page == 0
    # Mouse: the wheel zooms only over the boat's chart; tabs switch pages.
    game._window_to_canvas = lambda pos: pos
    scale = boat.chart_view.scale
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1, pos=(900, 300)))
    assert boat.chart_view.scale == scale
    game.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1, pos=(300, 300)))
    assert boat.chart_view.scale > scale
    from src.ui import stations_view
    with layout.bottom_panel_regions(game.bottom_panel_mode()):
        tab = stations_view._station_page_tab_rects(
            pygame.Rect(config.STATION_PANEL_RECT), 2)[1]
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tab.center))
    assert boat.command_page == 1
    center = boat.chart_view.cx
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(300, 300)))
    game.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(340, 300), rel=(40, 0),
                                         buttons=(1, 0, 0)))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(340, 300)))
    assert boat.chart_view.cx != center
    assert (game.map_view.scale, game.map_view.cx, game.map_view.cy) == frigate_view
    # Orders land in the boat log with the world time.
    key(pygame.K_d)
    for value in (pygame.K_8, pygame.K_0, pygame.K_RETURN):
        key(value)
    row = list(boat.feed)[-1]
    assert row["category"] == "navigation" and row["stamp"] == game.world.format_time()


# --- Crew control of the boat: plant, silent running, bottom, telegraph -----

def _run(game, seconds, dt=0.1):
    for _ in range(int(seconds / dt)):
        game._update_sim(dt)


def _feed_texts(game):
    from src.core.i18n import localize
    return [str(localize(row["text"], game.tr)) for row in game.opfor.feed]


def test_crewed_plant_never_ascends_or_calls_by_itself():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    if sub.endurance is None:
        pytest.skip("nuclear boat: no battery cycle")
    endurance = sub.endurance
    endurance.battery_kwh = endurance.profile.battery_capacity_kwh * .02
    endurance.aip_energy_kwh = 0.0
    sub.set_orders(depth=120.0, speed=6.0)
    _run(game, 60)
    assert endurance.phase == "SUBMERGED"
    assert not sub.transmitting and sub.depth > 60.0
    # An empty battery limits the way the plant can serve instead.
    endurance.battery_kwh = 0.0
    _run(game, 10)
    assert sub.speed < 6.0


def test_snorkel_charges_only_at_snorkel_depth_and_stops_below():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    if sub.endurance is None:
        assert sub.command_snorkel(True) == "uboot_no_snorkel"
        return
    endurance = sub.endurance
    snorkel_depth = endurance.profile.snorkel_depth_m
    sub.depth = sub.target_depth = sub.order_depth = 80.0
    assert sub.command_snorkel(True) == "uboot_too_deep"
    sub.depth = sub.target_depth = snorkel_depth
    endurance.battery_kwh = endurance.profile.battery_capacity_kwh * .3
    assert sub.command_snorkel(True) is True and sub.snorkeling
    sub.set_orders(speed=12.0)
    before = endurance.battery_kwh
    _run(game, 120)
    assert sub.snorkeling and endurance.battery_kwh > before
    assert sub.speed <= config.UBOOT_SNORKEL_MAX_KN + 1e-6
    sub.set_orders(depth=60.0)
    _run(game, 30)
    assert not sub.snorkeling
    assert any("snorkel depth" in text for text in _feed_texts(game))


def test_silent_running_caps_speed_and_gives_the_lurker_quiet():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.set_orders(speed=12.0, depth=100.0)
    _run(game, 60)
    loud = sub.quiet_factor()
    assert sub.command_silent(True) is True
    _run(game, 60)
    assert sub.speed <= config.UBOOT_SILENT_MAX_KN + 1e-6
    assert sub.quiet_factor() >= 0.97 > loud
    assert sub.command_silent("yes") == "invalid_value"
    assert sub.command_silent(False) is True
    sub.release_manual()
    assert sub.command_silent(True) == "not_ready"


def test_lying_on_the_bottom_is_quiet_and_lifts_off_with_way():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    game.world.depth_m = lambda x, y: 150.0
    sub.depth = sub.target_depth = sub.order_depth = 120.0
    _run(game, 1)
    assert sub.command_bottom(True) is True
    _run(game, 240)
    assert abs(sub.depth - (150.0 - config.UBOOT_BOTTOM_CLEARANCE_M)) < 1.0
    assert sub.speed <= 0.05 and sub.bottomed and sub.quiet_factor() >= 0.97
    assert sub.set_orders(speed=4.0) is True
    assert not game.opfor.orders.bottomed
    game.world.depth_m = lambda x, y: sub.stype.max_depth_m + 200.0
    _run(game, 1)
    assert sub.command_bottom(True) == "uboot_too_deep"


def test_crewed_boat_stops_before_land_instead_of_veering():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.set_orders(speed=8.0)
    _run(game, 30)
    course = sub.course
    game.world.on_land = lambda x, y: True
    _run(game, 2)
    assert sub.order_speed == 0.0 and abs(config.angle_diff_deg(sub.course, course)) < 5.0
    assert any("Obstacle ahead" in text for text in _feed_texts(game))


def test_telegraph_steps_run_from_stop_to_the_maximum():
    from src.core import opfor
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    steps = opfor.speed_steps(sub)
    assert steps[0] == 0.0 and steps[-1] == sub.motion.maximum_speed_kn
    sub.set_orders(speed=0.0)
    for expected in steps[1:]:
        assert opfor.step_speed(sub, 1) is True and sub.order_speed == expected
    assert opfor.step_speed(sub, 1) is True and sub.order_speed == steps[-1]
    assert opfor.step_speed(sub, -1) is True and sub.order_speed == steps[-2]


def test_web_crew_modes_and_boat_reasons():
    game, _server, bridge = _crewed()
    apply = _boat_apply(game, bridge)
    assert apply("uboot_silent", {"enabled": True}) is True
    assert game.opfor.orders.silent
    sub = game.opfor.sub
    sub.depth = sub.target_depth = sub.order_depth = 200.0
    expected = "uboot_no_snorkel" if sub.endurance is None else "uboot_too_deep"
    assert apply("uboot_snorkel", {"enabled": True}) == expected
    sub.fire_readiness = lambda bearing=None, salvo=1: "no_torpedoes"
    assert apply("uboot_fire", {"ref": None, "bearing": sub.course, "range_nm": None,
                                "depth_m": None, "salvo": 1}) == "uboot_no_torpedoes"


def test_local_boat_mode_keys():
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor

    def key(value, mod=0):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod, unicode=""))

    key(pygame.K_g)
    assert boat.orders.silent
    key(pygame.K_g)
    assert not boat.orders.silent
    speed = boat.sub.order_speed
    key(pygame.K_PLUS)
    assert boat.sub.order_speed > speed
    key(pygame.K_MINUS)
    game.draw()


# --- Torpedo employment: depth, spread, wire -------------------------------

def _arc_bearing(game, sub):
    launcher = game.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
    return (sub.course + launcher.arc_center_deg) % 360.0


def _crew_torpedoes(game, sub):
    return sorted((item for item in game.enemy_torpedoes
                   if item.launch_platform_id == sub.id), key=lambda item: item.id)


def test_crew_sets_run_depth_and_fires_a_two_torpedo_spread():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    bearing = _arc_bearing(game, sub)
    assert sub.command_fire(bearing, 6.0, depth_m=2.0) == "invalid_value"
    assert sub.command_fire(bearing, 6.0, salvo=3) == "invalid_value"
    if sub.weapon_battery.ready_count < 2:
        pytest.skip("boat has a single tube")
    assert sub.command_fire(bearing, 6.0, now=game.sim_t, depth_m=80.0, salvo=2) is True
    for _ in range(4):
        game._update_sim(0.05)
    fired = _crew_torpedoes(game, sub)
    assert len(fired) == 2
    assert all(item.target_depth == 80.0 for item in fired)
    # Each torpedo has its own datum, turned by the spread about the boat.
    datums = [math.degrees(math.atan2(item.guidance_x - sub.x, -(item.guidance_y - sub.y)))
              for item in fired]
    spread = abs(config.angle_diff_deg(datums[0] % 360.0, datums[1] % 360.0))
    assert abs(spread - 2 * config.UBOOT_SALVO_SPREAD_DEG) < 0.5


def test_wire_steers_the_datum_breaks_on_strain_and_can_be_cut():
    from src.core import opfor
    game, _server, _bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    sub.set_orders(speed=4.0)
    assert sub.command_fire(_arc_bearing(game, sub), 8.0, now=game.sim_t) is True
    _run(game, 1)
    torpedo = _crew_torpedoes(game, sub)[0]
    assert opfor.wire_state(boat, torpedo) == "ACTIVE"
    new_bearing = (_arc_bearing(game, sub) + 40.0) % 360.0
    assert opfor.wire_steer(boat, torpedo, new_bearing, 6.0) is True
    _run(game, 15)
    desired = math.degrees(math.atan2(torpedo.guidance_x - torpedo.x,
                                      -(torpedo.guidance_y - torpedo.y))) % 360.0
    assert abs(config.angle_diff_deg(torpedo.course, desired)) < 5.0
    # Too fast for the wire: it breaks and the log says so.
    sub.set_orders(speed=sub.motion.maximum_speed_kn)
    _run(game, 150)
    assert opfor.wire_state(boat, torpedo) == "BROKEN"
    assert opfor.wire_steer(boat, torpedo, 10.0, 5.0) == "uboot_no_wire"
    assert any("Wire broken" in text for text in _feed_texts(game))
    # A second shot is cut on order.
    sub.set_orders(speed=3.0)
    _run(game, 30)
    if sub.fire_readiness(_arc_bearing(game, sub)) is None:
        assert sub.command_fire(_arc_bearing(game, sub), 8.0, now=game.sim_t) is True
        _run(game, 1)
        second = _crew_torpedoes(game, sub)[-1]
        assert opfor.wire_cut(boat, second) is True
        assert opfor.wire_state(boat, second) == "CUT"


def test_web_fire_parameters_and_wire_actions():
    game, server, bridge = _crewed()
    sub = game.opfor.sub
    apply = _boat_apply(game, bridge)
    assert apply("uboot_fire", {"ref": None, "bearing": _arc_bearing(game, sub), "range_nm": 6.0,
                                "depth_m": 60.0, "salvo": 1}) is True
    _run(game, 1)
    bridge.pump(game, server, now=5.0)
    weapons = server.v2_states["uboot"]["uboot"]["own_weapons"]
    assert weapons and weapons[0]["wire"] == "ACTIVE" and weapons[0]["datum_range_nm"] is not None
    ref = weapons[0]["ref"]
    assert apply("uboot_wire_steer", {"ref": ref, "bearing": 10.0, "range_nm": 4.0}) is True
    assert apply("uboot_wire_cut", {"ref": ref}) is True
    assert apply("uboot_wire_cut", {"ref": ref}) == "uboot_no_wire"
    assert apply("uboot_wire_cut", {"ref": "unknown-reference-000"}) == "unknown_ref"


def test_local_fire_asks_bearing_then_range_with_presets():
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor

    def key(value, mod=0):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod, unicode=""))

    def type_number(text):
        for char in text:
            key(pygame.K_0 + int(char))
        key(pygame.K_RETURN)

    key(pygame.K_3)  # The weapons station owns the shot.
    key(pygame.K_t)
    type_number("90")
    assert boat.orders.torpedo_depth == 90.0
    bearing = int(round(_arc_bearing(game, boat.sub))) % 360
    key(pygame.K_f)
    type_number(f"{bearing:03d}")
    assert game.input_mode == "uboot_range"
    type_number("6")
    for _ in range(4):
        game._update_sim(0.05)
    fired = _crew_torpedoes(game, boat.sub)
    assert fired and fired[0].target_depth == 90.0


# --- Situation picture: alarm bearings, mast/ESM, commander sensors --------

def test_alarm_bearings_are_measured_noisy_and_deterministic():
    bearings = []
    for _ in range(2):
        game, _server, _bridge = _crewed()
        sub = game.opfor.sub
        source = (sub.x + 3.0, sub.y)  # due east of the boat
        sub.hear_ping(source=source)
        sub.alert_torpedo(source=(sub.x, sub.y + 2.0))  # due south
        orders = game.opfor.orders
        assert abs(config.angle_diff_deg(orders.ping_bearing, 90.0)) < 10.0
        assert orders.ping_bearing != 90.0
        assert abs(config.angle_diff_deg(orders.torpedo_bearing, 180.0)) < 20.0
        _run(game, 0.5)
        texts = _feed_texts(game)
        assert any("Active ping intercepted" in text for text in texts)
        assert any("Torpedo screws" in text for text in texts)
        bearings.append((orders.ping_bearing, orders.torpedo_bearing))
    assert bearings[0] == bearings[1]


def test_mast_only_at_periscope_depth_lowers_itself_and_reports_esm():
    from types import SimpleNamespace
    from src.sensors.platform import MAST_DEPTH_M
    game, _server, _bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = 100.0
    assert sub.command_mast(True) == "uboot_mast_depth"
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    assert sub.command_mast(True) is True and boat.orders.mast
    # A radar intercept from the boat's own ESM picture reaches the crew.
    fake = SimpleNamespace(track_id="esm-1", bearing=47.0, quality=0.8, last_seen=game.sim_t)
    picture = sub.sensor_suite.local_picture
    original = picture.tracks
    picture.tracks = lambda now, domains=None: [fake] if domains == ("esm",) else original(now, domains)
    _run(game, 0.5)
    assert [row[0] for row in boat.orders.esm] == [47.0]
    assert any("radar searching, bearing 047" in text for text in _feed_texts(game))
    # Diving lowers the mast by itself; the ESM picture clears.
    sub.set_orders(depth=80.0)
    _run(game, 60)
    assert not boat.orders.mast and boat.orders.esm == []
    assert any("mast lowered" in text for text in _feed_texts(game))


def test_web_mast_alarms_and_commander_sensors():
    game, server, bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    apply = _boat_apply(game, bridge)
    sub.depth = sub.target_depth = sub.order_depth = 12.0
    assert apply("uboot_mast", {"enabled": True}) is True
    sub.hear_ping(source=(sub.x + 3.0, sub.y))
    frigate_bt = game.sonar.bt_profile
    assert apply("sonar_measure_bt", {}) is True
    assert boat.station.sonar.bt_profile is not None and game.sonar.bt_profile is frigate_bt
    bridge.pump(game, server, now=5.0)
    state = server.v2_states["uboot"]["uboot"]
    assert state["status"]["mast"] is True
    assert set(state["alarms"]) == {"ping_age_s", "torpedo_age_s", "ping_bearing",
                                    "torpedo_bearing", "esm"}
    assert state["alarms"]["ping_bearing"] is not None
    assert state["alarms"]["torpedo_bearing"] is None
    json.dumps(state, allow_nan=False)


def test_local_mast_key_and_threat_bar_bearing():
    from src.ui import uboot_view
    from src.core.i18n import localize
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    sub = boat.sub
    sub.depth = sub.target_depth = sub.order_depth = 12.0
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_5, mod=0, unicode=""))
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, mod=0, unicode=""))
    assert boat.orders.mast
    sub.alert_torpedo(source=(sub.x + 2.0, sub.y))
    text, level = uboot_view.threats(game, boat)[0]
    assert level == "danger" and "TORPEDO 0" in str(localize(text, game.tr))
    game.draw()


# --- Navigation and plot ----------------------------------------------------

def test_boat_plot_is_separate_from_the_frigate_plot():
    game, server, bridge = _crewed()
    boat = game.opfor
    apply = lambda action, params, role="uboot": bridge._apply_opfor_action(game, action, params, role)
    frigate_before = list(game.plot.objects)
    sub = boat.sub
    assert apply("plot_add", {"shape": "mark", "x": sub.x + 1.0, "y": sub.y, "label": "Z"}) is True
    assert apply("plot_add", {"shape": "dr", "x": sub.x, "y": sub.y - 2.0, "course": 90.0,
                              "speed_kn": 8.0, "label": "F"}) is True
    assert len(boat.plot.objects) == 2 and game.plot.objects == frigate_before
    # The sonar room has no plot; the frigate's projections never carry the boat's.
    assert apply("plot_add", {"shape": "mark", "x": 1.0, "y": 1.0, "label": ""},
                 "uboot_sonar") is False
    bridge.pump(game, server, now=5.0)
    state = server.v2_states["uboot"]
    assert [row["label"] for row in state["plot"]["objects"]] == ["Z", "F"]
    assert state["plot"]["objects"][1]["cpa_nm"] is not None
    assert server.v2_states["uboot_sonar"]["plot"]["objects"] == []
    ident = state["plot"]["objects"][0]["id"]
    assert apply("plot_relabel", {"id": ident, "label": "Y"}) is True
    assert apply("plot_remove", {"id": ident}) is True
    assert apply("plot_clear", {}) is True and boat.plot.objects == []
    assert game.plot.objects == frigate_before


def test_chart_check_reports_an_obstacle_on_the_ordered_course():
    from src.core import opfor
    game, server, bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    assert sub.set_orders(course=90.0, speed=6.0) is True
    east = sub.x + 2.0
    game.world.on_land = lambda x, y: x >= east
    _run(game, 0.5)
    ahead = opfor.obstacle_ahead_nm(game.world, sub)
    assert ahead is not None and abs(ahead - 2.0) <= 0.3
    assert boat.orders.obstacle_ahead_nm == ahead
    assert any("obstacle" in text and "ahead on the ordered course" in text
               for text in _feed_texts(game))
    bridge.pump(game, server, now=5.0)
    nav = server.v2_states["uboot"]["uboot"]["navigation"]
    assert nav["obstacle_ahead_nm"] == ahead and nav["under_keel_m"] is not None
    # Turning away clears the warning.
    sub.set_orders(course=270.0)
    _run(game, 0.5)
    assert boat.orders.obstacle_ahead_nm is None


def test_local_nav_page_shows_keel_and_obstacle():
    from src.ui import uboot_view
    from src.core.i18n import localize
    game = _game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    boat.sub.set_orders(course=0.0, speed=6.0)
    north = boat.sub.y - 1.0
    game.world.on_land = lambda x, y: y <= north
    _run(game, 0.5)
    texts = [str(localize(text, game.tr)) for text, _level in uboot_view.threats(game, boat)]
    assert any("OBSTACLE AHEAD" in text for text in texts)
    boat.command_page = 0
    game.draw()


def test_each_boat_station_owns_its_own_orders():
    from src.commander.server import DIRECT_FIRE_ROLES, V2_ACTION_REGISTRY
    game, _server, bridge = _crewed()
    sub = game.opfor.sub
    owners = {action: spec.stations for action, spec in V2_ACTION_REGISTRY.items()
              if action.startswith("uboot_")}
    assert owners["uboot_fire"] == {"uboot_weapons"} and "uboot_weapons" in DIRECT_FIRE_ROLES
    assert owners["uboot_mast"] == {"uboot_esm"}
    assert owners["uboot_snorkel"] == {"uboot_engine"}
    assert "uboot_nav" in owners["uboot_set_course"]
    # The commander no longer fires; the weapons station does.
    params = {"ref": None, "bearing": sub.course, "range_nm": None, "depth_m": None, "salvo": 1}
    assert bridge._apply_opfor_action(game, "uboot_fire", params, "uboot") is False
    assert bridge._apply_opfor_action(game, "uboot_mast", {"enabled": False}, "uboot_weapons") is False
    assert bridge._apply_opfor_action(game, "uboot_set_course", {"course": 45.0}, "uboot_nav") is True
    assert sub.order_course == 45.0


def test_new_game_asks_which_unit_the_uconsole_plays():
    game = Game(seed=83, start_menu=True, audio_enabled=False, language="de")
    assert game.main_menu
    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "side" and game.menu_sel == 0
    game.draw()
    game._handle_menu_key(pygame.K_2)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.local_side == "uboot" and game.menu_screen == "scenario"
    game._handle_menu_key(pygame.K_ESCAPE)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "side" and game.menu_sel == 1  # Last choice preselected.
    game._handle_menu_key(pygame.K_UP)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.local_side == "frigate"
    game.audio.shutdown()


@pytest.mark.parametrize("language", ["en", "de"])
def test_local_boat_has_six_stations_and_orders_stay_at_their_station(language):
    from src.ui import uboot_view
    game = Game(seed=83, start_menu=False, audio_enabled=False, language=language)
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    sub = boat.sub

    def key(value, mod=0):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod, unicode=""))

    for number, role in enumerate(("uboot", "uboot_sonar", "uboot_weapons", "uboot_engine",
                                   "uboot_esm", "uboot_nav"), start=1):
        key(pygame.K_0 + number)
        assert uboot_local.local_station(game) == role
        assert (game.station is Station.SONAR) == (role == "uboot_sonar")
        game.draw()
    # Navigation may not raise the mast; the ESM station may.
    sub.depth = sub.target_depth = sub.order_depth = 12.0
    game.msg = ""
    key(pygame.K_p)
    assert not boat.orders.mast
    key(pygame.K_5)
    key(pygame.K_p)
    assert boat.orders.mast
    # The engine room runs the telegraph; the weapons station does not.
    key(pygame.K_3)
    speed = sub.order_speed
    key(pygame.K_PLUS)
    assert sub.order_speed == speed
    key(pygame.K_4)
    key(pygame.K_PLUS)
    assert sub.order_speed > speed
    # Tab cycles, and the top-bar tabs are clickable.
    key(pygame.K_TAB)
    assert uboot_local.local_station(game) == "uboot_esm"
    rect = uboot_view.station_tab_rects()[5]
    if game._window_to_canvas(rect.center) == rect.center:
        game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
        assert uboot_local.local_station(game) == "uboot_nav"
    game.draw()
    game.audio.shutdown()


def test_browser_held_boat_station_is_not_operated_from_the_uconsole():
    game = Game(seed=83, start_menu=False, audio_enabled=False, language="en")
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor

    class Held:
        def station_leased(self, role):
            return role == "uboot_engine"

    game.commander.server = Held()
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=0, unicode=""))
    speed = boat.sub.order_speed
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PLUS, mod=0, unicode=""))
    assert boat.sub.order_speed == speed
    game.draw()
    game.audio.shutdown()


def test_depth_presets_need_their_basis_and_follow_the_local_keys():
    from src.core import opfor
    game = Game(seed=83, start_menu=False, audio_enabled=False, language="en")
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    sub = boat.sub
    presets = opfor.depth_presets(game, boat)
    # No layer presets before the boat's own BT measurement.
    assert presets["layer"] is None and presets["below_layer"] is None
    assert presets["above_layer"] is None and presets["periscope"] <= 18.0
    assert presets["deep"] == sub.safe_depth_m(game.world)

    def key(value, mod=0):
        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=value, mod=mod, unicode=""))

    key(pygame.K_u)
    assert sub.order_depth == round(presets["periscope"])
    key(pygame.K_j)  # Not offered without a BT.
    assert sub.order_depth == round(presets["periscope"])
    with game.sonar_perspective(boat.station):
        assert game.measure_sonar_bt() is True
    measured = opfor.depth_presets(game, boat)
    assert measured["layer"] is not None
    if measured["below_layer"] is not None:
        key(pygame.K_j)
        assert sub.order_depth == round(measured["below_layer"])
    key(pygame.K_h)
    assert sub.order_depth == round(measured["deep"])
    # The weapons station does not order depth.
    key(pygame.K_3)
    key(pygame.K_u)
    assert sub.order_depth == round(measured["deep"])
    game.draw()
    game.audio.shutdown()
