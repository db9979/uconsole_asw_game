"""R9 profile-driven missile-defense acceptance regressions."""

import copy
import json

import pytest

from src.air.asm import ASM
from src.core.game import Game
from src.enemies.surface import SurfaceShip
from src.ui.stations_view import draw_opz_view
from src.weapons.air_defense import air_defense_loadout


def observe_asm(game, missile, *, source="RADAR-L", seen=None, distance=1.0):
    seen = game.sim_t if seen is None else seen
    return game.air_picture.observe(
        track_id=f"M-{missile.seq}", kind="ASM", target_id=missile.seq,
        source=source, bearing=90, range_nm=distance,
        observer_x=game.ship.x, observer_y=game.ship.y, course=None,
        quality=1, now=seen, label="ASM")


@pytest.fixture
def game():
    result = Game(seed=909, start_menu=False, audio_enabled=False)
    result.sim_t = 10.0
    result.mission.asm_count = 0
    return result


def test_vls_capacity_loadout_magazine_and_fire_channels_are_separate(game):
    profile = air_defense_loadout()
    assert profile["vls"]["capacity"] > profile["vls"]["sam_loadout"]
    assert game.vls_cells == profile["vls"]["sam_loadout"]

    missile = ASM(game.ship.x + 8, game.ship.y, 270, 1, game.rng_asm,
                  game._air_defense_loadout["asm"])
    game.asms = [missile]
    observe_asm(game, missile, distance=8)
    for _ in range(profile["vls"]["fire_channels"]):
        game.launch_essm()
    assert len(game.essms) == profile["vls"]["fire_channels"]
    remaining = game.vls_cells
    game.launch_essm()
    assert len(game.essms) == profile["vls"]["fire_channels"]
    assert game.vls_cells == remaining

    game.essms.clear()
    launches = 0
    while game.vls_cells:
        game.launch_essm()
        launches += 1
        game.essms.clear()
    game.launch_essm()
    assert launches == remaining and not game.essms


@pytest.mark.parametrize("source", ["RADAR-L", "DATALINK"])
def test_sam_release_requires_fresh_local_or_datalink_position(game, source):
    missile = ASM(game.ship.x + 8, game.ship.y, 270, 1, game.rng_asm)
    game.asms = [missile]
    maximum = game._air_defense_loadout["sam"]["observation_max_age_s"]
    observe_asm(game, missile, source=source, seen=game.sim_t - maximum - .01,
                distance=8)
    game.launch_essm()
    assert not game.essms
    game.air_picture._tracks.clear()
    observe_asm(game, missile, source=source, distance=8)
    game.launch_essm()
    assert len(game.essms) == 1


def test_bearing_only_refresh_does_not_refresh_hardkill_position(game):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    sam = game._air_defense_loadout["sam"]
    ciws = game._air_defense_loadout["ciws"]
    observed = observe_asm(game, missile, seen=game.sim_t - 10.0)
    game.air_picture.observe(
        track_id=observed.track_id, kind="ASM", target_id=missile.seq,
        source="HOJ", bearing=90, range_nm=None, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=.5, now=game.sim_t,
        label="ASM", jamming=True)

    ammo = game.ciws_ammo
    softkill = game.softkill_store.remaining_total
    game.launch_essm()
    game._update_air_defense(.1, publish_picture=False)
    game.launch_chaff()
    assert not game.essms
    assert game.ciws_ammo == ammo
    assert game.softkill_store.remaining_total == softkill
    assert sam["observation_max_age_s"] < 10.0
    assert ciws["observation_max_age_s"] < 10.0


def test_friendly_platform_datalink_publishes_runtime_air_fix(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    sender = SurfaceShip(
        game.ship.x, game.ship.y + .5, game.rng_world,
        profile=game.runtime_catalog.surfaces["warship_01"], side="friendly",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    game.warships = [sender]
    sender.emitter = True
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = game.sim_t
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)

    game._update_platform_sensors(.25)

    track = game.air_picture._tracks[f"M-{missile.seq}"]
    assert track.source == "DATALINK"
    assert track.position_seen == game.sim_t
    ammo = game.ciws_ammo
    game.rng_asm.random = lambda: 1.0
    game._update_air_defense(.1, publish_picture=False)
    assert game.ciws_ammo < ammo


def test_fresh_own_radar_supersedes_retained_stale_datalink(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    sender = SurfaceShip(
        game.ship.x, game.ship.y + .5, game.rng_world,
        profile=game.runtime_catalog.surfaces["warship_01"], side="friendly",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    game.warships = [sender]
    sender.emitter = True
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = 0.0
    game.sim_t = 0.0
    game._update_platform_sensors(.25)
    assert game.air_picture._tracks[f"M-{missile.seq}"].source == "DATALINK"

    game.sim_t = 10.0
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = 11.0
    game._update_platform_sensors(.25)
    game._update_air_picture()

    track = game.air_picture._tracks[f"M-{missile.seq}"]
    assert track.source == "RADAR-L"
    assert track.position_seen == game.sim_t


def test_equal_time_own_radar_supersedes_datalink(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    sender = SurfaceShip(
        game.ship.x, game.ship.y + .5, game.rng_world,
        profile=game.runtime_catalog.surfaces["warship_01"], side="friendly",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    game.warships = [sender]
    sender.emitter = True
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = game.sim_t
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)

    game._update_platform_sensors(.25)
    game._update_air_picture()

    track = game.air_picture._tracks[f"M-{missile.seq}"]
    assert track.source == "RADAR-L"
    assert track.position_seen == game.sim_t


def test_other_friendly_datalink_group_cannot_supply_fire_control(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    game.asms = [missile]
    sender = SurfaceShip(
        game.ship.x, game.ship.y + .5, game.rng_world,
        profile=game.runtime_catalog.surfaces["warship_01"], side="friendly",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    sender.sensor_suite.datalink_group = "other"
    game.warships = [sender]
    sender.emitter = True
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = game.sim_t
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)

    game._update_platform_sensors(.25)

    assert f"M-{missile.seq}" not in game.air_picture._tracks


def test_ciws_requires_fresh_observation_and_uses_profiled_ammunition(game):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    ciws = game._air_defense_loadout["ciws"]
    observe_asm(game, missile, seen=game.sim_t - ciws["observation_max_age_s"] - .01)
    before = game.ciws_ammo
    game._update_air_defense(.1, publish_picture=False)
    assert game.ciws_ammo == before
    game.air_picture._tracks.clear()
    observe_asm(game, missile)
    game.rng_asm.random = lambda: 1.0
    game._update_air_defense(.1, publish_picture=False)
    assert game.ciws_ammo == before - ciws["rounds_per_attempt"]


def test_successful_softkill_precedes_and_suppresses_hardkill(game):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    observe_asm(game, missile)
    game._air_defense_loadout["softkill"]["defeat_probability"] = 1.0
    inventory = game.softkill_store.remaining_total
    ammo = game.ciws_ammo
    game.launch_chaff()
    assert missile.broken and game.softkill_store.remaining_total == inventory - 1
    game._update_air_defense(.1, publish_picture=False)
    assert game.ciws_ammo == ammo


def test_softkill_inventory_and_readiness_are_finite_simulation_state(game):
    store = game.softkill_store
    profile = game._air_defense_loadout["softkill"]
    assert store.remaining_total == profile["mission_count"]
    assert store.fire() and store.ready == 0
    store.update(profile["reload_s"] - .01)
    assert store.ready == 0
    store.update(.01)
    assert store.ready == profile["ready_count"]
    fired = 1
    while store.fire():
        fired += 1
        store.update(profile["reload_s"])
    assert fired == profile["mission_count"] and store.remaining_total == 0


def test_sam_resolution_precedes_ciws_burst(game):
    missile = ASM(game.ship.x + .8, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    observe_asm(game, missile, distance=.8)
    game.launch_essm()
    interceptor = game.essms[0]
    interceptor.x = missile.x - .01
    interceptor.y = missile.y
    interceptor.seeker_acquired = True
    ammo = game.ciws_ammo
    game._update_air_defense(.01, publish_picture=False)
    assert missile.state == "ABGEFANGEN" and game.ciws_ammo == ammo


def test_renderer_and_wall_clock_do_not_mutate_air_defense(game, monkeypatch):
    missile = ASM(game.ship.x + 8, game.ship.y, 270, 1, game.rng_asm)
    game.asms = [missile]
    observe_asm(game, missile, distance=8)
    before = copy.deepcopy(game.save_state()["air_defense"]), copy.deepcopy(
        game.save_state()["asms"]), copy.deepcopy(game.save_state()["air_picture"])
    monkeypatch.setattr("pygame.time.get_ticks", lambda: 2**31 - 1)
    draw_opz_view(game)
    draw_opz_view(game)
    after = (game.save_state()["air_defense"], game.save_state()["asms"],
             game.save_state()["air_picture"])
    assert after == before


def test_profiled_midflight_save_continuation_is_canonical(game):
    missile = ASM(game.ship.x + 12, game.ship.y, 270, 1, game.rng_asm,
                  game._air_defense_loadout["asm"])
    game.asms = [missile]
    observe_asm(game, missile, distance=12)
    game.launch_essm()
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    snapshot = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored.load_state(snapshot)
    roundtrip = restored.save_state()
    for field in ("air_defense", "asms", "essms"):
        assert roundtrip[field] == snapshot[field]
    for current in (game, restored):
        current.ciws_ammo = 0
        for _ in range(20):
            current._update_air_defense(.05, publish_picture=False)
    assert restored.save_state()["asms"] == game.save_state()["asms"]
    assert restored.save_state()["essms"] == game.save_state()["essms"]


@pytest.mark.parametrize("mutate", [
    lambda state: state["air_defense"].update(version=2),
    lambda state: state["air_defense"]["loadout"]["sam"].update(extra=1),
    lambda state: state["air_defense"]["softkill"].update(effect_type="towed_acoustic"),
    lambda state: state["air_defense"].update(sam_remaining=True),
    lambda state: state.update(chaff_cd=False),
    lambda state: state["asms"][0].pop("profile_key"),
])
def test_malformed_air_defense_schema_is_rejected_transactionally(game, mutate):
    missile = ASM(game.ship.x + 8, game.ship.y, 270, 1, game.rng_asm)
    game.asms = [missile]
    before = game.save_state()
    malformed = copy.deepcopy(before)
    mutate(malformed)
    assert not game._load_save_data(malformed)
    assert game.save_state() == before


def test_noncanonical_essm_course_is_rejected_transactionally(game):
    missile = ASM(game.ship.x + 8, game.ship.y, 270, 1, game.rng_asm)
    game.asms = [missile]
    observe_asm(game, missile, distance=8)
    game.launch_essm()
    before = game.save_state()
    malformed = copy.deepcopy(before)
    malformed["essms"][0]["course"] = 360

    assert not game._load_save_data(malformed)
    assert game.save_state() == before


@pytest.mark.parametrize("offset", [-1, 1, 2**63 - 1])
def test_sam_sequence_must_match_consumed_inventory(game, offset):
    before = game.save_state()
    malformed = copy.deepcopy(before)
    malformed["air_defense"]["essm_seq"] += offset

    assert not game._load_save_data(malformed)
    assert game.save_state() == before


def test_exact_pre_r9_v10_file_upgrades_without_mutating_input(game, tmp_path):
    current = game.save_state()
    legacy = copy.deepcopy(current)
    del legacy["air_defense"]
    for row in legacy["asms"]:
        del row["profile_key"]
    for row in legacy["essms"]:
        del row["profile_key"]
    original = copy.deepcopy(legacy)
    path = tmp_path / "pre-r9-v10.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert not game._load_save_data(legacy)
    assert game.load_game(str(path))

    assert legacy == original
    assert game.save_state()["air_defense"]["sam_remaining"] == legacy["vls_cells"]


def test_integrated_softkill_and_datalink_split_run(game, monkeypatch):
    missile = ASM(game.ship.x + 1, game.ship.y, 0, 1, game.rng_asm)
    missile.speed_kn = 0
    game.asms = [missile]
    sender = SurfaceShip(
        game.ship.x, game.ship.y + .5, game.rng_world,
        profile=game.runtime_catalog.surfaces["warship_01"], side="friendly",
        doctrine="surface_combatant", runtime_catalog=game.runtime_catalog)
    game.warships = [sender]
    sender.emitter = True
    for controller in sender.sensor_suite.controllers.values():
        controller.next_scan_s = game.sim_t
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game._update_platform_sensors(.25)
    game._air_defense_loadout["softkill"]["defeat_probability"] = 0.0
    game.launch_chaff()
    snapshot = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(snapshot)
    monkeypatch.setattr(restored.world, "land_blocks_line", lambda *args: False)

    for current in (game, restored):
        for _ in range(10):
            current._update_sim(.05)

    for field in ("air_defense", "asms", "essms", "schedulers"):
        assert restored.save_state()[field] == game.save_state()[field]
    current_track = game.air_picture._tracks[f"M-{missile.seq}"]
    restored_track = restored.air_picture._tracks[f"M-{missile.seq}"]
    assert current_track.source in ("DATALINK", "RADAR-L")
    assert restored_track == current_track
    assert restored.save_state()["rngs"]["asm"] == game.save_state()["rngs"]["asm"]
