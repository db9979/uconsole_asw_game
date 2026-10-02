"""Surfacing the crewed boat: diesels in the open air, the bridge watch, a
crash dive that first floods the tanks, and who sees a surfaced boat."""

import sys
from pathlib import Path

import pygame

from src.core import config, opfor, uboot_local
from src.core.callouts import callout_of
from src.core.i18n import message

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402


def _surface(game, seconds=120):
    sub = game.opfor.sub
    sub.depth = sub.target_depth = 12.0
    assert sub.command_surface(True) is True and sub.order_depth == 0.0
    _run(game, seconds)
    return sub


def test_surfacing_blows_the_tanks_and_runs_the_diesels_faster():
    game, _server, _bridge = _crewed()
    sub = _surface(game)
    assert sub.surfaced and sub.depth <= config.UBOOT_SURFACED_DEPTH_M
    assert sub.ballast.mbt < 1.0                        # the blower works on the tanks
    assert any("Surfaced" in text for text in _feed_texts(game))
    if sub.endurance is None:
        return
    endurance = sub.endurance
    endurance.battery_kwh = endurance.profile.battery_capacity_kwh * .3
    assert sub.command_snorkel(True) is True and sub.snorkeling
    sub.set_orders(speed=20.0)
    before = endurance.battery_kwh
    _run(game, 60)
    assert sub.surfaced and sub.snorkeling
    assert config.UBOOT_SNORKEL_MAX_KN < sub.speed <= config.UBOOT_SURFACE_MAX_KN + 1e-6
    assert endurance.generator_factor == config.UBOOT_SURFACE_DIESEL_FACTOR
    sub.set_orders(speed=2.0)
    _run(game, 60)
    assert endurance.battery_kwh > before


def test_a_crash_dive_needs_the_vents_before_the_boat_goes_down():
    game, _server, _bridge = _crewed()
    sub = _surface(game, seconds=config.UBOOT_MBT_LP_BLOW_S + 60)
    assert sub.ballast.mbt == 0.0
    game.opfor.orders.mast = True
    sub.depth = 30.0
    assert sub.command_crash_dive() == "uboot_not_surfaced"
    sub.depth = 0.0
    assert sub.command_surface(False) is True
    assert not game.opfor.orders.mast
    assert sub.order_depth == config.UBOOT_CRASH_DIVE_DEPTH_M
    assert sub.order_speed == sub.motion.maximum_speed_kn
    _run(game, config.UBOOT_MBT_VENT_S * .5)
    assert sub.depth <= config.UBOOT_MBT_SURFACE_DEPTH_M + 1e-6    # held up by blown tanks
    _run(game, config.UBOOT_MBT_VENT_S * .6 + 60)
    assert sub.ballast.dived() and sub.depth > config.UBOOT_MBT_SURFACE_DEPTH_M + 5.0
    cues = [row["kind"] for row in game.opfor.sound_events]
    assert "dive_alarm" in cues
    assert any("Crash dive" in text for text in _feed_texts(game))


def test_the_bridge_watch_sees_farther_and_shouts_for_aircraft():
    game, _server, _bridge = _crewed()
    boat = game.opfor
    sub = boat.sub
    assert not opfor.scope_available(boat)
    _surface(game)
    assert opfor.scope_available(boat) and opfor.bridge_watch(boat)
    assert opfor.eye_height_m(boat) == config.UBOOT_BRIDGE_EYE_HEIGHT_M
    assert callout_of(message("uboot.event.bridge_aircraft", bearing="045"), "boat") == (
        "bridge_aircraft", 45)
    assert callout_of(message("uboot.event.crash_dive"), "boat") == ("crash_dive", None)

    class Mpa:
        airborne, altitude_m, course, speed = True, 300.0, 90.0, 200.0
        x, y = sub.x + 3.0, sub.y

    game.mpa = Mpa()
    from src.sonar.platforms import SCOPE_MPA_TARGET_ID
    assert any(row[0] == SCOPE_MPA_TARGET_ID and row[2] == "aircraft"
               for row in opfor._scope_candidates(game, boat))


def test_the_frigate_radar_and_lookouts_see_a_surfaced_boat():
    game, _server, _bridge = _crewed()
    sub = game.opfor.sub
    sub.x, sub.y = game.ship.x + 6.0, game.ship.y
    sub.depth = 40.0
    assert not [row for row in game._surface_heads(10.0) if row[0] is sub]
    sub.depth = 0.0
    rows = [row for row in game._surface_heads(10.0) if row[0] is sub]
    assert rows and rows[0][4] == config.SUB_SURFACED_RCS_FACTOR


def test_shift_h_surfaces_and_h_crash_dives_from_the_surface():
    game, _server, _bridge = _crewed()
    game.local_side = "uboot"
    sub = game.opfor.sub
    sub.depth = sub.target_depth = 14.0
    assert uboot_local._key_action(pygame.K_h, pygame.KMOD_SHIFT) == "uboot_surface"
    uboot_local._command_key(game, game.opfor, pygame.K_h, pygame.KMOD_SHIFT)
    assert sub.order_depth == 0.0
    sub.depth = 0.0
    uboot_local._command_key(game, game.opfor, pygame.K_h, 0)
    assert sub.order_depth == config.UBOOT_CRASH_DIVE_DEPTH_M


def test_the_web_action_is_allowlisted_for_command_and_navigation():
    from src.commander.server import V2_ACTION_REGISTRY
    game, _server, bridge = _crewed()
    assert V2_ACTION_REGISTRY["uboot_surface"].stations == {"uboot", "uboot_nav"}
    sub = game.opfor.sub
    sub.depth = sub.target_depth = 14.0
    assert bridge._apply_opfor_action(game, "uboot_surface", {"enabled": True}, "uboot_nav")
    assert sub.order_depth == 0.0
    assert bridge._apply_opfor_action(game, "uboot_surface", {"enabled": True},
                                      "uboot_weapons") is False
