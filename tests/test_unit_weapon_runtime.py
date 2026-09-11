"""Regression contracts for unit/weapon runtime and observed launch geometry."""

import math
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.air.asm import ASM, ESSM
from src.air.helicopter import Helicopter
from src.core import config
from src.core.game import Game
from src.core.mission_definition import default_mission
from src.data.catalog import CATALOG
from src.enemies.decoy import Decoy
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from src.sonar.sonar import Contact
from src.weapons.torpedo import EnemyTorpedo, Torpedo, underwater_path_blocked


def ocean(**overrides):
    values = dict(size_nm=500.0, on_land=lambda x, y: False,
                  depth_m=lambda x, y: 1000.0,
                  thermocline_depth_m=lambda x, y: 100.0,
                  sonar_path_blocked=lambda *args: False,
                  land_blocks_line=lambda *args: False)
    values.update(overrides)
    return SimpleNamespace(**values)


def contact_target(x, y, depth=50.0):
    return SimpleNamespace(x=x, y=y, depth=depth, sunk=False, dead=False,
                           state="PATROL", hit=lambda: None)


@pytest.fixture
def game(monkeypatch):
    value = Game(seed=829, start_menu=False, audio_enabled=False)
    monkeypatch.setattr(value.world, "on_land", lambda x, y: False)
    monkeypatch.setattr(value.world, "depth_m", lambda x, y: 1000.0)
    monkeypatch.setattr(value.world, "sonar_path_blocked", lambda *args: False)
    monkeypatch.setattr(value.world, "land_blocks_line", lambda *args: False)
    value.subs = []
    value.animals = value.civilians = value.warships = []
    value.mission.asm_count = 0
    return value


def assign_contact(game, target_id=9001):
    contact = Contact(17, target_id, "ping", "sub")
    contact.update_ping(90.0, 5.0, 50.0, 1.0, game.sim_t)
    contact.observed_x, contact.observed_y = game.ship.x + 5.0, game.ship.y
    contact.player_class = "U_BOOT"
    game.sonar.contacts[target_id] = contact
    game.target = contact
    return contact


def test_sinking_is_monotonic_and_delayed_score_is_awarded_once(game):
    sub = Sub(100, 100, 990, 0, "diesel_alt", random.Random(2))
    game.subs = [sub]
    sub.damage = 100.0
    sub.state, sub.sink_left = "SINKING", 20.0
    score = game.score
    for elapsed in (5.0, 5.0, 10.0):
        previous_depth, previous_time = sub.depth, sub.sink_left
        sub.hit()
        sub.hear_ping()
        sub.alert_torpedo()
        assert sub.state == "SINKING"
        assert sub.sink_left == previous_time
        game._update_underwater_entities(elapsed)
        assert sub.depth > previous_depth
        if not sub.sunk:
            assert game.score == score
    assert sub.sunk and sub.sink_left == 0
    assert game.score == score + config.SCORE_SUNK
    game._update_underwater_entities(30)
    assert game.score == score + config.SCORE_SUNK


def test_simultaneous_surface_hit_reports_cannot_double_score(game):
    ship = SurfaceShip(100, 100, random.Random(2), hostile=True)
    ship.damage = 99
    ship.hit()
    assert ship.sunk
    for seq in (1, 2):
        torpedo = Torpedo(100, 100, 0, 5, ship, seq)
        torpedo.state = "HIT"
        game.torpedoes.append(torpedo)
    score = game.score
    game._update_player_torpedoes(0.1)
    assert game.score == score + config.SCORE_SUNK


@pytest.mark.parametrize("blocked", [False, True])
def test_torpedo_warning_is_local_and_not_selected_target_telepathy(game, monkeypatch, blocked):
    near = Sub(100, 100, 50, 0, "diesel_alt", random.Random(3))
    far = Sub(120, 100, 50, 0, "diesel_alt", random.Random(4))
    game.subs = [near, far]
    monkeypatch.setattr(game.world, "sonar_path_blocked", lambda *args: blocked)
    game.torpedoes = [Torpedo(100.5, 100, 90, 50, far, 1,
                              speed_kn=0, guidance_x=120, guidance_y=100)]
    game._update_player_torpedoes(0.1)
    assert near.torpedo_alerted is not blocked
    assert far.torpedo_alerted is False


def test_terminal_depth_tracking_loss_and_reacquisition():
    first = contact_target(100.5, 100, 100)
    torpedo = Torpedo(100, 100, 90, 40, first, 1, speed_kn=0,
                      guidance_x=100.5, guidance_y=100)
    torpedo.update(1.0, [first])
    assert torpedo.seeker_acquired
    assert torpedo.target_depth == 100
    assert torpedo.depth == 15.0
    first.depth = 200
    torpedo.update(1.0, [first])
    assert torpedo.target_depth == 200
    assert torpedo.depth == 25.0
    first.x = 200
    torpedo.update(0.1, [first])
    assert not torpedo.seeker_acquired
    assert torpedo.terminal_active
    # Search remains active even after leaving the original datum.
    torpedo.x = 110
    second = contact_target(110.5, 100, 40)
    torpedo.update(0.1, [first, second])
    assert torpedo.target is second and torpedo.seeker_acquired
    second.dead = True
    torpedo.update(0.1, [second])
    assert not torpedo.seeker_acquired


@pytest.mark.parametrize("enemy", [False, True])
def test_underwater_weapons_stop_at_terrain_before_target(enemy):
    world = ocean(sonar_path_blocked=lambda x0, y0, d0, x1, y1, d1:
                  min(x0, x1) <= 100.4 <= max(x0, x1))
    target = contact_target(100.8, 100, 5)
    if enemy:
        torpedo = EnemyTorpedo(100, 100, 90, 5, 1)
        torpedo.speed_kn = 3600
        torpedo.update(1.0, target, world)
    else:
        torpedo = Torpedo(100, 100, 90, 5, target, 1, speed_kn=3600,
                          guidance_x=100.8, guidance_y=100)
        torpedo.update(1.0, [target], world)
    assert torpedo.state == "SASE"


def test_fallback_terrain_sampling_has_fixed_work_bound():
    calls = []
    world = SimpleNamespace(size_nm=2000,
                            on_land=lambda x, y: calls.append((x, y)) or False)
    assert not underwater_path_blocked(world, 0, 0, 5, 1000, 0, 5)
    assert len(calls) == 65


def test_enemy_torpedo_uses_catalog_hit_speed_and_swept_collision(monkeypatch):
    profile = replace(CATALOG.torpedoes["enemy_torp"],
                      speed_kn=3600.0, hit_dist_nm=0.3, range_nm=5.0)
    monkeypatch.setitem(CATALOG.torpedoes, "enemy_torp", profile)
    torpedo = EnemyTorpedo(100, 100, 90, 5, 1)
    assert (torpedo.speed_kn, torpedo.kill_dist_nm, torpedo.range_nm) == (3600, 0.3, 5)
    target = contact_target(100.5, 100, 5)
    torpedo.update(1.0, target)
    assert torpedo.state == "HIT"
    torpedo = EnemyTorpedo(100, 100, 90, 5, 2)
    torpedo.update(0, contact_target(100.25, 100, 5))
    assert torpedo.state == "HIT"


def test_enemy_launch_lead_uses_catalog_speed_not_legacy_constant(monkeypatch):
    sub = Sub(100, 100, 50, 0, "diesel_alt", random.Random(5))
    ship = SimpleNamespace(x=110, y=100, course=0, speed=10)
    state = sub.rng.getstate()
    expected = sub._launch_data(ship)
    sub.rng.setstate(state)
    monkeypatch.setattr(config, "ENEMY_TORP_SPEED_KN", 99999)
    assert sub._launch_data(ship) == expected


def test_decoy_broadband_consumes_catalog(monkeypatch):
    signature = replace(CATALOG.acoustic_for("decoy"), broadband=(0.12, 13, 140))
    monkeypatch.setitem(CATALOG.acoustic_by_key, "decoy", signature)
    decoy = Decoy(100, 100, 50, random.Random(6))
    assert decoy.broadband() == dict(level=0.12, low_hz=13, high_hz=140)
    decoy.dead = True
    assert decoy.broadband() == {}


@pytest.mark.parametrize("key", list(CATALOG.subs))
def test_endurance_eligibility_uses_explicit_propulsion(key):
    sub = Sub(100, 100, 100, 0, key, random.Random(7))
    eligible = CATALOG.subs[key].acoustic.propulsion in (
        "Diesel-elektrisch", "elektrisch/AIP")
    assert (sub.endurance is not None) is eligible


def test_sub_observed_memory_does_not_follow_silent_hidden_ship_and_expires():
    sub = Sub(100, 100, 50, 0, "diesel_alt", random.Random(8))
    ship = SimpleNamespace(x=110, y=100, course=90, speed=1, noise_level=lambda: 0.1)
    sub.hear_ping()
    sub.update(0.1, ship, ocean())
    snapshot = dict(sub.memory["contact"])
    ship.x, ship.y = 90, 95
    sub.update(1.0, ship, ocean())
    assert sub.memory["contact"] == snapshot
    assert sub.memory["contact_bearing"] == 90
    sub.update(config.SUB_EVADE_DURATION_S, ship, ocean())
    assert sub.memory["contact"] is None
    assert sub.memory["contact_bearing"] is None


def test_enemy_counterfire_uses_remembered_observation_not_hidden_motion():
    sub = Sub(100, 100, 50, 0, "diesel_alt", random.Random(8))
    ship = SimpleNamespace(x=110, y=100, course=90, speed=1, noise_level=lambda: 0.1)
    sub.hear_ping()
    sub.update(0.1, ship, ocean())
    ship.x, ship.y = 90, 95
    sub.attack_left = 0
    sub.rng.random = lambda: 0.0
    sub.update(1.0, ship, ocean())
    assert sub.pending_torpedoes
    assert 85 < sub.pending_torpedoes[0][2] < 95


def test_terrain_occluded_ping_does_not_create_enemy_memory():
    sub = Sub(100, 100, 50, 0, "diesel_alt", random.Random(9))
    ship = SimpleNamespace(x=110, y=100, course=90, speed=1, noise_level=lambda: 0.1)
    sub.hear_ping()
    sub.update(0.1, ship, ocean(sonar_path_blocked=lambda *args: True))
    assert sub.memory["contact"] is None


def test_helo_canonical_datum_wire_and_water_entry(game):
    contact = assign_contact(game)
    game.helo.launch(game.ship)
    contact.observed_x, contact.observed_y = game.ship.x + 7, game.ship.y + 2
    # Deliberately inconsistent polar cache must not replace the canonical fix.
    contact.bearing, contact.range_est = 0, 1
    game.launch_helo_torpedo()
    torpedo = game.torpedoes[-1]
    assert (torpedo.guidance_x, torpedo.guidance_y) == (contact.observed_x, contact.observed_y)
    assert torpedo.wire_state == "BROKEN"
    assert not torpedo.wire_update(0, 0)
    before = game.helo.torps
    assert game.helo.drop_torpedo(None, 50, 2, guidance_x=100,
                                  guidance_y=100, world=ocean(on_land=lambda x, y: True)) is None
    assert game.helo.torps == before
    assert game.helo.deploy_buoy(1, world=ocean(on_land=lambda x, y: True)) is None


def test_helo_recovery_requires_available_deck_and_fuel():
    helo = Helicopter(random.Random(1))
    ship = SimpleNamespace(x=100, y=100, course=0)
    helo.launch(ship)
    helo.order_return()
    helo.update(0.1, ship, ocean(), recovery_available=False)
    assert helo.state == "ZURUECK"
    helo.update(0.1, ship, ocean(), recovery_available=True)
    assert helo.state == "HANGAR"
    helo.launch(ship)
    helo.order_return()
    helo.fuel_s = 0.1
    helo.update(0.1, ship, ocean(), recovery_available=False)
    assert helo.state == "VERLOREN"


@pytest.mark.parametrize("invalid", ["land", "shallow", "outside"])
def test_invalid_helo_release_preserves_loadout_and_sequence(game, monkeypatch, invalid):
    assign_contact(game)
    game.helo.launch(game.ship)
    if invalid == "land":
        monkeypatch.setattr(game.world, "on_land", lambda x, y: True)
    elif invalid == "shallow":
        monkeypatch.setattr(game.world, "depth_m", lambda x, y: 5.0)
    else:
        game.helo.x = -1
    before = game.helo.torps, game.helo.buoys_left, game.torpedo_seq, game.buoy_seq
    game.launch_helo_torpedo()
    game.deploy_buoys()
    assert (game.helo.torps, game.helo.buoys_left, game.torpedo_seq, game.buoy_seq) == before
    assert game.msg["__u_jagd_i18n__"] == "runtime.helo.water_required"


@pytest.mark.parametrize("launcher", ["launch_torpedo", "launch_helo_torpedo"])
def test_launch_and_readiness_do_not_discover_hidden_liveness(game, launcher):
    sub = Sub(game.ship.x + 50, game.ship.y, 100, 0, "diesel_alt", random.Random(1))
    game.subs = [sub]
    assign_contact(game, sub.id)
    sub.sunk = True
    game.helo.launch(game.ship)
    assert game.torpedo_readiness()[0] == "FEUER FREI"
    getattr(game, launcher)()
    assert len(game.torpedoes) == 1
    assert not sub.torpedo_alerted


@pytest.mark.parametrize("launcher", ["launch_torpedo", "launch_helo_torpedo"])
def test_expired_observation_blocks_launch_and_readiness(game, launcher):
    contact = assign_contact(game)
    game.helo.launch(game.ship)
    contact.last_seen = game.sim_t - config.SONAR_CONTACT_LOST_S
    assert game.torpedo_readiness()[0] != "FEUER FREI"
    getattr(game, launcher)()
    assert not game.torpedoes


@pytest.mark.parametrize("affiliation", ["FRIEND", "NEUTRAL"])
@pytest.mark.parametrize("launcher", ["launch_torpedo", "launch_helo_torpedo"])
def test_protected_observed_annotations_block_both_launchers(game, affiliation, launcher):
    contact = assign_contact(game)
    game.helo.launch(game.ship)
    game.air_picture.observe(track_id="U-9001", kind="SUB", target_id=contact.target_id,
                             source="SONAR-PING", bearing=90, range_nm=5,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=game.sim_t, label="K17")
    game.opz_affiliations["U-9001"] = affiliation
    assert affiliation in game.torpedo_readiness()[0]
    before = game.helo.torps, game.torpedo_count
    getattr(game, launcher)()
    assert not game.torpedoes
    assert (game.helo.torps, game.torpedo_count) == before


@pytest.mark.parametrize("prefix", ["U", "S", "W"])
def test_protected_annotation_survives_measurement_expiry(game, prefix):
    assign_contact(game)
    game.opz_affiliations[f"{prefix}-9001"] = "FRIEND"
    game.air_picture._tracks.clear()
    assert game._target_affiliation_interlock() == "FRIEND"
    game.launch_torpedo()
    assert not game.torpedoes


@pytest.mark.parametrize("prefix,kind", [("A", "FLG"), ("M", "ASM")])
def test_aircraft_and_missile_sequence_annotations_do_not_alias_sub_id(game, prefix, kind):
    assign_contact(game, target_id=1)
    game.air_picture.observe(track_id=f"{prefix}-1", kind=kind, target_id=1,
                             source="RADAR-L", bearing=0, range_nm=8,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=game.sim_t, label="A1")
    game.opz_affiliations[f"{prefix}-1"] = "FRIEND"
    assert game._target_affiliation_interlock() is None
    game.launch_torpedo()
    assert len(game.torpedoes) == 1


def test_essm_midcourse_uses_only_launch_observation():
    missiles = []
    for hidden_x in (101, 180):
        target = ASM(hidden_x, 100, 0, 1, random.Random(2))
        missile = ESSM(100, 100, 90, target, 1, guidance_x=120, guidance_y=100)
        missile.update(1.0)
        assert not missile.seeker_acquired
        missiles.append(missile)
    assert (missiles[0].x, missiles[0].y, missiles[0].course) == (
        missiles[1].x, missiles[1].y, missiles[1].course)


def test_essm_terminal_acquisition_collision_and_loss():
    target = ASM(100.8, 100, 0, 1, random.Random(2))
    missile = ESSM(100, 100, 90, target, 1, guidance_x=101, guidance_y=100)
    missile.update(2.0)
    assert missile.state == "HIT" and target.state == "ABGEFANGEN"
    target = ASM(100.8, 100, 0, 2, random.Random(2))
    missile = ESSM(100, 100, 90, target, 2, guidance_x=101, guidance_y=100)
    missile.update(0.1)
    assert missile.seeker_acquired
    target.x = 120
    missile.update(0.1)
    assert not missile.seeker_acquired and missile.state == "LAUF"


def test_essm_launch_on_observed_track_does_not_require_live_target(game):
    game.air_picture.observe(track_id="A-10", kind="ASM", target_id=10,
                             source="RADAR-L", bearing=90, range_nm=8,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=game.sim_t, label="ASM")
    game.launch_essm()
    assert len(game.essms) == 1
    assert game.essms[0].target is None
    game.essms[0].update(0.1)
    assert game.essms[0].state == "LAUF"


def test_essm_midcourse_refresh_is_observation_only_and_expires(game):
    track = game.air_picture.observe(
        track_id="A-10", kind="ASM", target_id=10,
        source="RADAR-L", bearing=90, range_nm=20,
        observer_x=game.ship.x, observer_y=game.ship.y,
        course=None, quality=1, now=game.sim_t, label="ASM")
    game.launch_essm()
    missile = game.essms[0]
    track.x, track.y = game.ship.x + 18, game.ship.y + 2
    game._update_air_defense(0.1, publish_picture=False)
    assert (missile.guidance_x, missile.guidance_y) == (track.x, track.y)
    old_datum = missile.guidance_x, missile.guidance_y
    game.sim_t += game.air_picture.stale_s + 1
    track.x = game.ship.x + 25
    game._update_air_defense(0.1, publish_picture=False)
    assert (missile.guidance_x, missile.guidance_y) == old_datum


def test_essm_terminal_acquisition_is_terrain_bounded():
    target = ASM(100.8, 100, 0, 1, random.Random(2))
    missile = ESSM(100, 100, 90, target, 1, guidance_x=101, guidance_y=100)
    missile.update(0.1, world=ocean(land_blocks_line=lambda *args: True))
    assert not missile.seeker_acquired


def test_chaff_does_not_remove_swept_collision():
    ship = SimpleNamespace(x=101, y=100)
    missile = ASM(100, 100, 90, 1, random.Random(1))
    missile.state, missile.chaff_left, missile.broken = "CHAFF", 10.0, True
    missile.update(8.0, ship)
    assert missile.state == "TREFFER"


def test_broken_chaff_run_does_not_fly_past_its_expiry():
    missile = ASM(100, 100, 90, 1, random.Random(1))
    missile.state, missile.chaff_left, missile.broken = "CHAFF", 2, True
    missile.update(8, SimpleNamespace(x=101, y=100))
    assert missile.state == "VERLOREN"
    assert missile.travel == pytest.approx(config.kn_to_nm_per_s(
        missile.profile["speed_kn"]) * 2)


@pytest.mark.parametrize("limit", ["range", "age", "world"])
def test_asm_has_bounded_endurance_and_world_exit(limit):
    missile = ASM(100, 100, 90, 1, random.Random(1))
    missile.jammer = True
    if limit == "range":
        missile.travel = missile.RANGE_NM
    elif limit == "age":
        missile.age_s = missile.LIFE_S
    else:
        missile.x = 500
    missile.update(1.0, SimpleNamespace(x=200, y=200), ocean())
    assert missile.state == "VERLOREN"


def test_scheduled_asm_aim_and_sequence_survive_pruning(game):
    game.mission.asm_count = 2
    game.mission_time = 100000
    game._maybe_spawn_asm()
    first = game.asms[0]
    expected = math.degrees(math.atan2(game.ship.x - first.x,
                                      -(game.ship.y - first.y))) % 360
    assert first.course == pytest.approx(expected)
    game.asms.clear()
    game._maybe_spawn_asm()
    assert game.asms[0].seq > first.seq


def test_scheduled_and_surface_salvos_share_monotonic_asm_sequence(game):
    ship = SurfaceShip(game.ship.x + 20, game.ship.y, random.Random(1), hostile=True)
    ship.pending_asm = [(ship.x, ship.y, 2)]
    game.warships = [ship]
    game._drain_warship_asm()
    sequences = [item.seq for item in game.asms]
    assert len(sequences) == 2 and sequences[1] > sequences[0]
    game.asms.clear()
    game.mission.asm_count = 1
    game.mission_time = config.ASM_SPAWN_FIRST_S
    game._maybe_spawn_asm()
    assert game.asms[0].seq > sequences[-1]


def test_ciws_failure_spends_ammo_with_one_second_cadence(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    game.air_picture.observe(track_id="M-1", kind="ASM", target_id=1,
                             source="RADAR-L", bearing=90, range_nm=1,
                             observer_x=game.ship.x, observer_y=game.ship.y,
                             course=None, quality=1, now=game.sim_t, label="ASM")
    game.rng_asm.random = lambda: 1.0
    ammo = game.ciws_ammo
    game._update_air_defense(0.1, publish_picture=False)
    burst = game._air_defense_loadout["ciws"]["rounds_per_attempt"]
    assert game.ciws_ammo == ammo - burst
    assert missile.state == "LAUF"
    game._update_air_defense(0.5, publish_picture=False)
    assert game.ciws_ammo == ammo - burst
    game._update_air_defense(0.5, publish_picture=False)
    assert game.ciws_ammo == ammo - 2 * burst


@pytest.mark.parametrize("level", list(config.LEVELS))
def test_custom_mission_applies_authored_sub_speed_and_difficulty(level):
    game = Game(seed=829, level=level, start_menu=False, audio_enabled=False)
    # The initial built-in patrol intentionally overrides constructor difficulty.
    game.level = level
    definition = default_mission("user.runtime")
    definition["units"]["exact"] = [dict(id="target", profile="diesel_alt",
                                        side="hostile", placement=dict(kind="fixed", x=100, y=100),
                                        course_deg=123, speed_kn=7, depth_m=65)]
    definition["objective"]["target_ids"] = ["target"]
    assert game.start_custom_mission(definition)
    sub = game.subs[0]
    tuning = config.LEVELS[level]
    assert sub.speed == 7 and sub.course == 123
    assert sub.quiet_mult == tuning["quiet_mult"]
    assert sub.attack_mult == tuning["enemy_attack_mult"]
    assert sub.attack_left == sub.attack_cooldown == tuning["enemy_cooldown_s"]
