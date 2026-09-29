"""Tube flooding is a short transient: the frigate hears it as a warning
(loud flooding far, slow and quiet flooding only close), the AI floods before
it shoots, and the crewed boat may flood quietly."""

import copy
import json
import math
import sys
from pathlib import Path

from src.core import config
from src.core.game import Game

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _run  # noqa: E402


def _game(seed=4411):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def _reach(game, quiet):
    own = game.ship.passive_sonar_range_nm(
        1.0, int(getattr(game.world, "effective_sea_state", game.world.sea_state)))
    own = own / config.SONAR_PASSIVE_BASE_NM * game._sonar_range_factor()
    return own * (config.TORP_FLOOD_QUIET_HEAR_NM if quiet else config.TORP_FLOOD_HEAR_NM)


def _place(game, sub, distance_nm, bearing=None):
    """Put the boat at a distance along a bearing the sonar can hear through."""
    for step in range(36):
        angle = math.radians(step * 10.0 if bearing is None else bearing)
        x = game.ship.x + distance_nm * math.sin(angle)
        y = game.ship.y - distance_nm * math.cos(angle)
        if not game.world.sonar_path_blocked(x, y, 80.0, game.ship.x, game.ship.y, 5.0):
            sub.x, sub.y, sub.depth = x, y, 80.0
            return
    raise AssertionError("no open water around the frigate")


def _flood_cues(game):
    return [cue for cue in game.current_torpedo_cues() if cue["kind"] == "flood"]


def test_loud_flooding_is_heard_far_and_quiet_flooding_only_close():
    game = _game()
    sub = game.subs[0]
    for other in game.subs[1:]:
        other.flood_noise_left = 0.0
    loud, quiet = _reach(game, False), _reach(game, True)
    assert quiet < loud
    _place(game, sub, 0.8 * loud)
    sub.flood_transient(quiet=False)
    (cue,) = _flood_cues(game)
    true = math.degrees(math.atan2(sub.x - game.ship.x, -(sub.y - game.ship.y))) % 360.0
    assert abs(config.angle_diff_deg(cue["bearing"], true)) < 5 * config.TORP_CUE_BEARING_SIGMA_DEG
    # The measurement names no platform.
    assert set(cue) == {"kind", "t", "owner", "report", "serial", "bearing"}
    sub.flood_transient(quiet=True)
    assert _flood_cues(game) == []
    _place(game, sub, 0.8 * quiet)
    assert len(_flood_cues(game)) == 1
    # The transient is short.
    sub.flood_noise_left = 0.0
    assert _flood_cues(game) == []


def test_the_flood_cue_is_announced_once_but_does_not_trigger_autocrew_countermeasures():
    game = _game()
    sub = game.subs[0]
    _place(game, sub, 0.5 * _reach(game, False))
    sub.flood_transient(quiet=False)
    game._update_torpedo_cues()
    warnings = [row for row in game.torpedo_warnings() if row["source"] == "flood"]
    assert len(warnings) == 1
    game._update_torpedo_cues()
    assert len([row for row in game.torpedo_warnings() if row["source"] == "flood"]) == 1
    # A warning, not a torpedo: the automatic crews neither evade nor stream Nixie.
    from src.core import autocrew, hunter
    assert autocrew._nearest_threat(game) is None
    stores = game.nixie_store.ready
    hunter.weapons(game, None)
    assert game.nixie_store.ready == stores and not game.nixies


def test_ai_boat_floods_quietly_on_a_fix_and_loudly_when_it_must_shoot_dry():
    game = _game(seed=4412)
    sub = game.subs[0]
    assert not sub.manual and sub.ai_tube_left == -1.0
    sub.ai_flood_tubes(quiet=True)
    assert sub.ai_tube_left == config.UBOOT_TUBE_FLOOD_QUIET_S and sub.flood_quiet
    assert sub.flood_noise_left == config.UBOOT_TUBE_FLOOD_NOISE_S
    before = sub.transient_left
    # Flooding counts down with the boat's own clock; a second order changes nothing.
    sub.ai_flood_tubes(quiet=False)
    assert sub.flood_quiet and sub.transient_left == before
    sub.ai_tube_left = -1.0
    sub.ai_flood_tubes(quiet=False)
    assert sub.ai_tube_left == config.UBOOT_TUBE_FLOOD_S and not sub.flood_quiet
    assert sub.transient_left >= config.UBOOT_TUBE_FLOOD_NOISE_S - 1e-9


def test_ai_shot_on_dry_tubes_waits_for_the_flooding():
    game = _game(seed=4413)
    sub = game.subs[0]
    from src.sensors.platform import PlatformObservation
    observation = PlatformObservation(
        track_id="T", domain="sonar", source="SONAR", observer_x=sub.x, observer_y=sub.y,
        bearing=sub.course, range_nm=None, x=None, y=None, course=None, speed_kn=None,
        depth_m=None, quality=1.0, signal=1.0, last_seen=0.0,
        bearing_uncertainty_deg=None, range_uncertainty_nm=None,
        depth_uncertainty_m=None, label=None)
    sub.state, sub.heard_ping = "EVADE", True
    sub.memory["last_ping_age"] = 0.0
    sub.attack_left = 0.0
    sub.attack_mult = 1e6          # the roll always succeeds
    left = sub.torpedoes_left
    sub._maybe_attack(0.1, observation)
    assert sub.ai_fire_pending and sub.ai_tube_left == config.UBOOT_TUBE_FLOOD_S
    assert not sub.pending_torpedoes and sub.torpedoes_left == left
    sub.ai_tube_left = 0.0
    sub.memory["last_ping_age"] = 0.0
    sub._maybe_attack(0.1, observation)
    assert sub.pending_torpedoes and not sub.ai_fire_pending
    assert sub.ai_tube_left == -1.0


def test_crewed_boat_can_flood_quietly():
    game, _server, _bridge = _crewed(seed=73)
    sub = game.opfor.sub
    battery = sub.weapon_battery
    tube = next(item.index for item in battery.tubes if item.loaded_weapon_key is not None)
    game.opfor.orders.tubes[tube] = ["dry", 0.0]
    before = sub.transient_left
    assert sub.command_flood_tube(tube, quiet=True) is True
    assert game.opfor.orders.tubes[tube] == ["flooding", config.UBOOT_TUBE_FLOOD_QUIET_S]
    assert sub.flood_quiet and sub.transient_left == before
    _run(game, config.UBOOT_TUBE_FLOOD_S + 2.0)
    assert game.opfor.orders.tubes[tube][0] == "flooding"


def test_flood_state_round_trips_and_is_validated():
    game = _game(seed=4414)
    sub = game.subs[0]
    sub.ai_flood_tubes(quiet=True)
    sub.ai_fire_pending = True
    state = json.loads(json.dumps(game.save_state()))
    twin = _game(seed=1)
    assert twin._load_save_data(copy.deepcopy(state))
    loaded = twin.subs[0]
    assert (loaded.ai_tube_left, loaded.ai_fire_pending, loaded.flood_quiet,
            loaded.flood_seq, loaded.flood_noise_left) == (
        sub.ai_tube_left, True, True, sub.flood_seq, sub.flood_noise_left)
    for field, value in (("ai_tube_left", -0.5), ("ai_tube_left", 1e9),
                         ("flood_quiet", 1), ("flood_seq", -1), ("flood_seq", 1.5),
                         ("ai_fire_pending", None), ("flood_noise_left", 99.0)):
        bad = copy.deepcopy(state)
        bad["subs"][0][field] = value
        assert not twin._load_save_data(bad), field
