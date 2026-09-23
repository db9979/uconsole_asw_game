"""Phase 9: decoy acoustics, seeker discrimination and countermeasures."""

import copy
import json
import random
from types import SimpleNamespace

import pytest

from src.core import config
from src.core.game import Game
from src.data.catalog import CATALOG
from src.enemies.decoy import Decoy
from src.weapons import torpedo as torpedo_mod
from src.weapons.torpedo import Torpedo


class Ocean:
    size_nm = 500.0

    def on_land(self, *args):
        return False

    def depth_m(self, *args):
        return 3000.0

    def sonar_path_blocked(self, *args):
        return False

    def current_vec(self, *args):
        return (0.0, 0.0)


def _decoy(life=None):
    decoy = Decoy(0.0, 0.0, 50.0, random.Random(1))
    if life is not None:
        decoy.life = life
    return decoy


def test_decoy_battery_fades_its_emission_and_modulates_tonals():
    fresh, tired = _decoy(), _decoy()
    tired.life = 0.1 * tired.profile.life_s
    assert tired.source_level_offset_db() < fresh.source_level_offset_db() - 5.0
    lines_a, lines_b = fresh.lofar_lines(0.0), fresh.lofar_lines(7.5)
    if lines_a:
        assert lines_a[0][0] != lines_b[0][0]


def test_louder_candidate_wins_and_lock_has_hysteresis():
    weapon = SimpleNamespace(x=0.0, y=0.0, depth=50.0)
    quiet = SimpleNamespace(x=1.0, y=0.0, depth=50.0, speed_kn=5.0,
                            quiet_factor=lambda: 0.9)
    loud = SimpleNamespace(x=1.0, y=0.1, depth=50.0, speed_kn=5.0,
                           quiet_factor=lambda: 0.1)
    assert torpedo_mod.choose_seeker_target(weapon, [quiet, loud], None) is loud
    slightly = SimpleNamespace(x=1.0, y=0.0, depth=50.0, speed_kn=5.0,
                               quiet_factor=lambda: 0.85)
    assert torpedo_mod.choose_seeker_target(weapon, [quiet, slightly], quiet) is quiet


def test_doppler_gate_suppresses_a_stationary_echo():
    weapon = SimpleNamespace(x=0.0, y=0.0, depth=50.0)
    moving = SimpleNamespace(x=1.0, y=0.0, depth=50.0, speed_kn=4.0,
                             quiet_factor=lambda: 0.5)
    still = SimpleNamespace(x=0.8, y=0.0, depth=50.0, speed_kn=0.0,
                            quiet_factor=lambda: 0.5)
    assert torpedo_mod.choose_seeker_target(weapon, [moving, still], None) is moving


def test_torpedo_overruns_a_decoy_and_reattacks():
    decoy = _decoy()
    decoy.x, decoy.y, decoy.depth = 100.05, 100.0, 50.0
    torpedo = Torpedo(100.0, 100.0, 90.0, 50.0, None, 1, speed_kn=360.0,
                      guidance_x=100.0, guidance_y=100.0)
    torpedo.depth = 50.0
    for _ in range(10):
        torpedo.update(0.2, seeker_candidates=[decoy], world=Ocean())
    assert torpedo.state == "RUN"
    assert decoy.id in torpedo.rejected_ids
    assert torpedo.evaluate_seeker_candidates([decoy], Ocean()) is None


def test_warship_streams_decoys_on_a_torpedo_launch_and_saves_the_store():
    from src.enemies.surface import SurfaceShip
    game = Game(seed=9901, start_menu=False, audio_enabled=False)
    warship = SurfaceShip(game.ship.x + 5.0, game.ship.y, game.rng_world,
                          profile=game.runtime_catalog.surfaces["warship_01"],
                          side="hostile", doctrine="surface_combatant",
                          runtime_catalog=game.runtime_catalog)
    game.warships = [warship]
    game.world.sonar_path_blocked = lambda *args: False
    assert warship.countermeasures_left == config.WARSHIP_TORPEDO_DECOYS
    from src.sonar.sonar import Contact
    target_id = game.subs[0].id
    contact = Contact(17, target_id, "ping", "sub")
    contact.update_ping(90.0, 5.0, 50.0, 1.0, game.sim_t)
    contact.observed_x, contact.observed_y = game.ship.x + 5.0, game.ship.y
    contact.player_class = "U_BOOT"
    game.sonar.contacts[target_id] = contact
    game.target = contact
    assert game.launch_torpedo_at(contact, 50.0) is True
    assert warship.countermeasures_left == config.WARSHIP_TORPEDO_DECOYS - 1
    assert any(d.source_id == warship.id for d in game.decoys)
    state = json.loads(json.dumps(game.save_state()))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.warships[0].countermeasures_left == warship.countermeasures_left
    broken = copy.deepcopy(state)
    broken["warships"][0]["countermeasures_left"] = config.WARSHIP_TORPEDO_DECOYS
    assert not restored._load_save_data(broken)   # decoy without store spend
