"""R20: Luftangriff – Raider-Zustandsmaschine, Flak, Wellen, Save/Load."""

import copy
import json
import random

import pytest

from src.air.asm import ASM
from src.air.raid import RaidPhase, Raider
from src.core import config
from src.core.game import Game
from src.weapons.air_defense import (
    AIR_DEFENSE_STATE_VERSION,
    air_defense_loadout,
    validate_air_defense_loadout,
)


class _Ship:
    x = 300.0
    y = 300.0
    course = 90.0


@pytest.fixture
def game():
    result = Game(seed=4242, start_menu=False, audio_enabled=False)
    result.sim_t = 10.0
    result.mission.asm_count = 0
    return result


# --- Loadout ---

def test_loadout_v2_exposes_raider_and_aa_gun_profiles():
    loadout = air_defense_loadout()
    assert loadout["version"] == 2
    assert loadout["raider"]["key"].startswith("aircraft.")
    assert loadout["aa_gun"]["key"].startswith("weapon.")
    assert loadout["raider"]["salvo"][0] <= loadout["raider"]["salvo"][1]
    assert loadout["aa_gun"]["rounds_per_attempt"] <= loadout["aa_gun"]["ammo"]


def test_loadout_v1_shape_is_rejected():
    loadout = copy.deepcopy(air_defense_loadout())
    del loadout["raider"], loadout["aa_gun"]
    loadout["version"] = 1
    with pytest.raises(ValueError):
        validate_air_defense_loadout(loadout)


# --- Raider-Zustandsmaschine ---

def test_raider_lifecycle_approach_attack_retreat_despawn():
    profile = air_defense_loadout()["raider"]
    ship = _Ship()
    raider = Raider(ship.x + 120.0, ship.y, 0.0, 1, random.Random(7), profile)
    assert raider.phase is RaidPhase.APPROACH
    for _ in range(5000):
        raider.update(1.0, ship)
        if raider.phase is not RaidPhase.APPROACH:
            break
    assert raider.phase is RaidPhase.ATTACK
    assert raider.pending_asm >= profile["salvo"][0]
    for _ in range(5000):
        raider.update(1.0, ship)
        if raider.phase is not RaidPhase.ATTACK:
            break
    assert raider.phase is RaidPhase.RETREAT
    for _ in range(20000):
        raider.update(1.0, ship)
        if raider.despawned:
            break
    assert raider.despawned
    assert RaidPhase.parse("APPROACH") is RaidPhase.APPROACH
    with pytest.raises(ValueError):
        RaidPhase.parse("DIVE")


def test_raider_turn_rate_is_bounded():
    profile = air_defense_loadout()["raider"]
    ship = _Ship()
    raider = Raider(ship.x + 100.0, ship.y, 0.0, 1, random.Random(7), profile)
    for _ in range(50):
        course = raider.course
        raider.update(1.0, ship)
        assert abs(config.angle_diff_deg(raider.course, course)) <= \
            config.RAIDER_TURN_DEG_S + 0.01


def test_shot_down_raider_stops_moving():
    profile = air_defense_loadout()["raider"]
    ship = _Ship()
    raider = Raider(ship.x + 20.0, ship.y, 0.0, 1, random.Random(7), profile)
    raider.hp = 0
    before = (raider.x, raider.y, raider.course, raider.phase)
    raider.update(5.0, ship)
    assert (raider.x, raider.y, raider.course, raider.phase) == before


# --- Flak (AA gun) ---

def test_aa_gun_engages_only_fresh_raider_observations(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    raider.hp = 1
    game.raiders = [raider]
    game.raid_seq = 1
    game.air_picture.observe(
        track_id="R-1", kind="FLG", target_id=1, source="RADAR-L",
        bearing=90.0, range_nm=20.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=0.9, now=game.sim_t,
        label="A-1")
    game.rng_raid.random = lambda: 0.0
    ammo = game.aa_ammo
    game._update_raiders(0.1, publish_picture=False)
    assert game.aa_ammo == ammo - profile["aa_gun"]["rounds_per_attempt"]
    assert game.aa_cooldown_s == profile["aa_gun"]["cycle_s"]
    assert game.raiders == []  # abgeschossen und entfernt


def test_aa_gun_refuses_stale_or_missing_observations(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    game.raiders = [raider]
    game.raid_seq = 1
    game.air_picture.observe(
        track_id="R-1", kind="FLG", target_id=1, source="RADAR-L",
        bearing=90.0, range_nm=20.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=0.9,
        now=game.sim_t - profile["aa_gun"]["observation_max_age_s"] - 0.5,
        label="A-1")
    ammo = game.aa_ammo
    game._update_raiders(0.1, publish_picture=False)
    assert game.aa_ammo == ammo and game.raiders == [raider]


def test_aa_gun_refuses_raiders_beyond_range(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 70.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    game.raiders = [raider]
    game.raid_seq = 1
    game.air_picture.observe(
        track_id="R-1", kind="FLG", target_id=1, source="RADAR-L",
        bearing=90.0, range_nm=70.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=0.9, now=game.sim_t,
        label="A-1")
    ammo = game.aa_ammo
    game._update_raiders(0.1, publish_picture=False)
    assert game.aa_ammo == ammo and game.aa_cooldown_s == 0.0


def test_aa_gun_hits_reduce_hp_and_stop_when_ammo_is_exhausted(game,
                                                              monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    aa = profile["aa_gun"]
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    raider.evasion = 0.0
    raider.hp = 2
    game.raiders = [raider]
    game.raid_seq = 1
    game.aa_ammo = aa["rounds_per_attempt"]
    game.air_picture.observe(
        track_id="R-1", kind="FLG", target_id=1, source="RADAR-L",
        bearing=90.0, range_nm=20.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=0.9, now=game.sim_t,
        label="A-1")
    game.rng_raid.random = lambda: 0.0
    game._update_raiders(aa["cycle_s"] + 0.1, publish_picture=False)
    assert game.aa_ammo == 0
    assert raider.hp == 1 and game.raiders == [raider]
    game.air_picture.observe(
        track_id="R-1", kind="FLG", target_id=1, source="RADAR-L",
        bearing=90.0, range_nm=20.0, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=0.9, now=game.sim_t,
        label="A-1")
    game._update_raiders(aa["cycle_s"] + 0.1, publish_picture=False)
    assert raider.hp == 1  # ohne Munition kein Treffer


# --- Raid-Wellen ---

def test_no_raid_waves_without_mission_asm_pressure(game):
    game.mission.asm_count = 0
    game.mission_time = config.RAID_FIRST_WAVE_S + 50 * config.RAID_WAVE_INTERVAL_S
    for _ in range(20):
        game._update_raiders(0.1, publish_picture=False)
    assert not game.raiders and game.raid_waves_spawned == 0


def test_raid_waves_spawn_on_schedule_outside_radar_range(game):
    game.mission.asm_count = 2
    # Weltmitte, damit Clampen den Spawn-Ring nicht verkürzt.
    game.ship.x, game.ship.y = 250.0, 250.0
    game.mission_time = config.RAID_FIRST_WAVE_S - 1.0
    game._update_raiders(0.1, publish_picture=False)
    assert not game.raiders  # noch zu früh
    game.mission_time = config.RAID_FIRST_WAVE_S
    game._update_raiders(0.1, publish_picture=False)
    assert 1 <= len(game.raiders) <= config.RAID_WAVE_SIZE[1]
    assert game.raid_waves_spawned == 1
    for raider in game.raiders:
        dist = raider.distance_nm(game.ship)
        assert dist > config.RADAR_AIR_RANGE_NM - 5.0
        assert raider.phase is RaidPhase.APPROACH
        assert 1 <= raider.seq <= game.raid_seq


def test_raid_wave_cap_holds_until_a_slot_frees(game):
    game.mission.asm_count = 2
    profile = game._air_defense_loadout["raider"]
    for i in range(config.RAID_MAX_CONCURRENT):
        game.raid_seq += 1
        game.raiders.append(Raider(game.ship.x + 100.0, game.ship.y + i, 0.0,
                                   game.raid_seq, game.rng_raid, profile))
    game.mission_time = config.RAID_FIRST_WAVE_S + 2 * config.RAID_WAVE_INTERVAL_S
    game._update_raiders(0.1, publish_picture=False)
    assert len(game.raiders) == config.RAID_MAX_CONCURRENT
    assert game.raid_waves_spawned == 0
    game.raiders[0].despawned = True
    game._update_raiders(0.1, publish_picture=False)  # Slot wird frei
    game._update_raiders(0.1, publish_picture=False)  # Welle ersetzt den Slot
    assert len(game.raiders) == config.RAID_MAX_CONCURRENT
    assert game.raid_waves_spawned == 1


def test_raid_wave_is_deterministic_for_the_same_seed():
    games = [Game(seed=777, start_menu=False, audio_enabled=False)
             for _ in range(2)]
    for g in games:
        g.mission.asm_count = 2
        g.mission_time = config.RAID_FIRST_WAVE_S
    for g in games:
        for _ in range(400):
            g._update_raiders(0.1, publish_picture=False)
    assert games[0].save_state()["air_defense"]["raiders"] == \
        games[1].save_state()["air_defense"]["raiders"]
    assert games[0].save_state()["rngs"]["raid"] == games[1].save_state()["rngs"]["raid"]


# --- Salvo-Ablassung (ASM) ---

def test_raider_salvo_drains_into_attack_asms(game):
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    raider.phase = RaidPhase.ATTACK
    raider.salto_cd = 0.0
    game.raiders = [raider]
    game.raid_seq = 1
    game._update_raiders(0.1, publish_picture=False)
    salvo = raider.pending_asm
    assert salvo >= profile["raider"]["salvo"][0]
    before = len(game.asms)
    game._drain_raider_asm()
    assert len(game.asms) == before + salvo
    for asm in game.asms[before:]:
        assert isinstance(asm, ASM)
        assert asm.profile_key == profile["asm"]["key"]
        assert asm.state == "LAUF"
    assert raider.pending_asm == 0


def test_raider_salvo_asms_hit_the_frigate_and_damage_compartments(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 0.1, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    raider.pending_asm = 1
    game.raiders = [raider]
    game.raid_seq = 1
    game._drain_raider_asm()
    asm = game.asms[0]
    asm.speed_kn = 0.0  # Treffer-Zeitpunkt kontrollieren
    game._update_air_defense(0.1, publish_picture=False)
    assert asm.state == "TREFFER"
    assert any(c.flood > 0.0 for c in game.damage.compartments.values())


# --- Air Picture ---

def test_raider_publishes_as_anonymous_flg_track(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 3,
                    game.rng_raid, profile["raider"])
    game.raiders = [raider]
    game.raid_seq = 3
    game._update_air_picture()
    track = game.air_picture._tracks.get("R-3")
    assert track is not None and track.kind == "FLG"
    assert track.source == "RADAR-L" and track.hostile is False
    game.air_radar_on = False
    game.air_picture._tracks.clear()
    game._update_air_picture()
    assert "R-3" not in game.air_picture._tracks


def test_raider_first_contact_flashes_once(game, monkeypatch):
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 20.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    game.raiders = [raider]
    game.raid_seq = 1
    game._update_air_picture()
    flashes = []
    monkeypatch.setattr(game, "flash",
                        lambda text, seconds=3.0: flashes.append(text))
    game._update_raiders(0.1, publish_picture=True)
    assert any("raid.incoming" in str(f) for f in flashes)
    assert game._raider_visible_last is True
    game._update_raiders(0.1, publish_picture=True)
    assert len([f for f in flashes if "raid.incoming" in str(f)]) == 1


# --- Save/Load ---

def test_raid_state_roundtrips_save_load(game):
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 60.0, game.ship.y, 0.0, 7,
                    game.rng_raid, profile["raider"])
    raider.phase = RaidPhase.ATTACK
    raider.hp = 5
    raider.salto_cd = 12.3
    raider.pending_asm = 1
    raider.attack_t = 20.0
    game.raiders = [raider]
    game.raid_seq = 7
    game.raid_waves_spawned = 3
    game.aa_ammo = 100
    game.aa_cooldown_s = 0.4
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(state)
    snapshot = json.loads(json.dumps(restored.save_state(), allow_nan=False))
    for field in ("air_defense", "rngs"):
        assert snapshot[field] == state[field]
    out = restored.raiders[0]
    assert (out.x, out.y, out.course, out.seq, out.phase, out.hp,
            out.salto_cd, out.pending_asm, out.attack_t) == \
        (raider.x, raider.y, raider.course, raider.seq, raider.phase, raider.hp,
         raider.salto_cd, raider.pending_asm, raider.attack_t)
    assert restored.aa_ammo == 100 and restored.aa_cooldown_s == 0.4
    assert restored.raid_seq == 7 and restored.raid_waves_spawned == 3


def test_pre_r20_save_upgrades_to_raid_shape(game):
    state = json.loads(json.dumps(game.save_state(), allow_nan=False))
    ad = state["air_defense"]
    loadout = ad["loadout"]
    del loadout["raider"], loadout["aa_gun"]
    loadout["version"] = 1
    for key in ("aa_ammo", "aa_cooldown_s", "raiders", "raider_seq",
                "waves_spawned"):
        del ad[key]
    ad["version"] = 1
    del state["rngs"]["raid"]
    # ohne Upgrade-Pfad: abgelehnt
    assert not game._load_save_data(copy.deepcopy(state))
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored._load_save_data(copy.deepcopy(state), allow_pre_r9=True)
    out = restored.save_state()["air_defense"]
    assert out["version"] == AIR_DEFENSE_STATE_VERSION == 2
    assert out["loadout"]["version"] == 2
    assert out["loadout"]["raider"] == air_defense_loadout()["raider"]
    assert out["aa_ammo"] == out["loadout"]["aa_gun"]["ammo"]
    assert out["raiders"] == [] and out["raider_seq"] == 0
    assert out["waves_spawned"] == 0
    assert "raid" in restored.save_state()["rngs"]


@pytest.mark.parametrize("mutate", [
    lambda state: state["air_defense"].update(aa_ammo=-1),
    lambda state: state["air_defense"].update(aa_cooldown_s=True),
    lambda state: state["air_defense"].update(aa_ammo=10**6),
    lambda state: state["air_defense"]["raiders"][0].update(hp=0),
    lambda state: state["air_defense"]["raiders"][0].update(phase="DIVE"),
    lambda state: state["air_defense"]["raiders"][0].update(course=360),
    lambda state: state["air_defense"]["raiders"][0].update(seq=0),
    lambda state: state["air_defense"].update(raider_seq=-1),
    lambda state: state["air_defense"].update(waves_spawned=1.5),
    lambda state: state["air_defense"].update(raiders=[
        dict(x=1.0, y=1.0, course=1.0, seq=1, phase="APPROACH", hp=1,
             salvo_cd=0.0, pending_asm=0, attack_t=0.0, extra=1)]),
    lambda state: state["rngs"].pop("raid"),
])
def test_malformed_raid_state_is_rejected_transactionally(game, mutate):
    profile = game._air_defense_loadout
    raider = Raider(game.ship.x + 60.0, game.ship.y, 0.0, 1,
                    game.rng_raid, profile["raider"])
    game.raiders = [raider]
    game.raid_seq = 1
    before = game.save_state()
    malformed = json.loads(json.dumps(before, allow_nan=False))
    mutate(malformed)
    assert not game._load_save_data(malformed)
    assert game.save_state() == before
