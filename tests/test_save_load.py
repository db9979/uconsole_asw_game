"""Save/load roundtrips and strict save-v10 rejection behavior."""

import json
from pathlib import Path
import pytest

from src.core import config
from src.core.game import Game, SAVE_ROOT_FIELDS
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.air.asm import ASM
from src.air.sonobuoy import Sonobuoy
from src.sonar.sonar import Contact
from src.sonar.tma import BearingTrack
from src.weapons.torpedo import Torpedo

DT = 1.0 / 60.0
def pump(g, frames):
    for _ in range(frames):
        g.update(DT)
        g.draw()


@pytest.fixture
def tmp_saves(isolated_saves):
    return isolated_saves


def test_default_save_paths_are_isolated(tmp_path):
    """No opt-in fixture is needed for either slots or legacy saves."""
    saves = tmp_path / "saves"
    assert config.SAVE_DIR == str(saves)
    assert config.SAVE_PATH == str(saves / "save.json")
    assert list(saves.iterdir()) == []
    g = Game(seed=2024, start_menu=False)
    assert g.load_from_slot(5) is False
    assert g.load_game() is False
    g.save_to_slot(2)
    assert g.save_game() == str(saves / "save.json")
    assert {path.name for path in saves.iterdir()} == {"slot2.json", "save.json"}
    assert g.load_from_slot(2)
    assert g.load_game()


def test_roundtrip_preserves_state(tmp_saves):
    g = Game(seed=2024, start_menu=False)
    pump(g, 240)

    # Zustand, der erhalten bleiben muss:
    g.torpedo_depth = 95.0
    g.sonar_mode = "TOWED"
    g.damage.compartments["sonar"].state = "BESCHAEDIGT"
    g.damage.compartments["sonar"].flood = 12.5
    g.damage.compartments["engine"].fire = 20.0
    tgt = g.subs[0]
    weapon_key = g.player_torpedo_battery.fire()
    weapon = next(row for row in g._ownship_loadout["weapons"]
                  if row["key"] == weapon_key)
    profile = g.runtime_catalog.torpedoes[weapon["runtime_profile_key"]]
    g.torpedo_count = g.player_torpedo_battery.remaining_total
    g.torpedoes.append(Torpedo(
        g.ship.x, g.ship.y, 90.0, 60.0, tgt, 99, profile=profile,
        kill_dist_nm=weapon["kill_dist_nm_by_level"][g.level],
        kill_depth_m=weapon["kill_depth_m_by_level"][g.level],
        guidance_x=tgt.x, guidance_y=tgt.y))
    g.torpedo_seq = 99
    g.asms.append(ASM(g.ship.x + 10.0, g.ship.y, 0.0, 42, g.rng_asm))
    g.buoys.append(Sonobuoy(g.ship.x + 1.0, g.ship.y + 1.0, 7))
    g.buoy_seq = 7
    g.helo.buoys_left -= 1
    g.hq_msg("Testnachricht")

    before = dict(
        mission_type=g.mission.type_key,
        hour=g.world.hour,
        sea=g.world.sea_state,
        ship_x=g.ship.x, ship_y=g.ship.y,
        sub_state=tgt.state, sub_x=tgt.x, sub_depth=tgt.depth,
        sub_torps=tgt.torpedoes_left,
    )
    g.save_to_slot(1)

    # Zustand sabotieren, dann laden:
    g.ship.x += 3.0
    g.sonar_mode = "BOW"
    g.torpedo_depth = 10.0
    g.torpedoes.clear()
    g.asms.clear()
    g.buoys.clear()
    g.damage.compartments["sonar"].state = "OK"

    ok = g.load_from_slot(1)
    assert ok, "Load fehlgeschlagen"

    # Mission/Welt
    assert g.mission.type_key == before["mission_type"]
    assert abs(g.world.hour - before["hour"]) < 0.01
    assert g.world.sea_state == before["sea"]

    # Fregatte + Waffe
    assert abs(g.ship.x - before["ship_x"]) < 1e-6
    assert abs(g.ship.y - before["ship_y"]) < 1e-6
    assert g.sonar_mode == "TOWED"
    assert g.torpedo_depth == 95.0

    # Schaden (inkl. repair_mult + Brand)
    assert g.damage.compartments["sonar"].state == "BESCHAEDIGT"
    assert abs(g.damage.compartments["sonar"].flood - 12.5) < 1e-6
    assert abs(g.damage.compartments["engine"].fire - 20.0) < 1e-6
    lvl = config.LEVELS[g.level]
    assert abs(g.damage.repair_mult - lvl["repair_mult"]) < 1e-9

    # U-Boot-KI-Zustand
    s = g.subs[0]
    assert s.state == before["sub_state"]
    assert abs(s.x - before["sub_x"]) < 1e-6
    assert abs(s.depth - before["sub_depth"]) < 0.01
    assert s.torpedoes_left == before["sub_torps"]

    # Laufende Entitaeten
    assert len(g.torpedoes) == 1
    assert g.torpedoes[0].idx == 99
    assert g.torpedoes[0].target is not None
    assert g.torpedoes[0].target.id == g.subs[0].id
    assert len(g.asms) == 1 and g.asms[0].seq == 42
    assert len(g.buoys) == 1 and g.buoys[0].seq == 7
    assert g.messages and g.messages[-1][1] == "Testnachricht"

    # Simulation laeuft nach dem Laden weiter (kein Crash)
    pump(g, 120)
    assert g.sim_t > 0.0


def test_load_empty_slot(tmp_saves):
    g = Game(seed=1, start_menu=False)
    assert g.load_from_slot(5) is False


@pytest.mark.parametrize("version", range(1, SAVE_VERSION))
def test_obsolete_save_versions_are_rejected(tmp_saves, version):
    g = Game(seed=99, start_menu=False)
    before = g.save_state()
    data = json.loads(json.dumps(before))
    data["version"] = version
    (tmp_saves / "slot1.json").write_text(json.dumps(data))

    assert not g.load_from_slot(1)
    assert g.save_state() == before


def test_v10_requires_exact_schema_and_every_root_field():
    game = Game(seed=100, start_menu=False)
    state = game.save_state()

    for key in SAVE_ROOT_FIELDS:
        malformed = json.loads(json.dumps(state))
        del malformed[key]
        assert not game._load_save_data(malformed), key

    malformed = json.loads(json.dumps(state))
    malformed["save_schema"] = "u-jagd-save-v9"
    assert not game._load_save_data(malformed)

    malformed = json.loads(json.dumps(state))
    malformed["unknown"] = None
    assert not game._load_save_data(malformed)


@pytest.mark.parametrize("mutation", [
    lambda state: state["ship"].pop("quiet_mode"),
    lambda state: state["sonar"].pop("next_id"),
    lambda state: state["subs"][0].pop("decision_reason"),
    lambda state: state["sonar"].update(unknown=None),
    lambda state: state["civilians"][0].pop("id"),
])
def test_v10_rejects_noncanonical_nested_shapes(mutation):
    game = Game(seed=101, start_menu=False)
    before = game.save_state()
    malformed = json.loads(json.dumps(before))
    mutation(malformed)

    assert not game._load_save_data(malformed)
    assert game.save_state() == before


def test_v10_sonar_contact_sequence_must_exceed_existing_contacts():
    game = Game(seed=102, start_menu=False)
    target = game.subs[0]
    game.sonar.contacts[target.id] = Contact(7, target.id, "passiv", "sub")
    game.sonar._next_contact_id = 8
    state = game.save_state()
    state["sonar"]["next_id"] = 7

    assert not game._load_save_data(state)


def test_malformed_supported_save_does_not_replace_live_game(tmp_saves):
    import json
    import os

    game = Game(seed=101, start_menu=False)
    before = (game.seed, game.ship.x, game.ship.y, game.mission.type_key)
    path = os.path.join(config.SAVE_DIR, "slot2.json")
    with open(path, "w") as handle:
        json.dump({"version": 6, "seed": 999, "ship": None}, handle)

    assert game.load_from_slot(2) is False
    assert (game.seed, game.ship.x, game.ship.y,
            game.mission.type_key) == before


def test_invalid_world_mode_is_rejected_without_replacing_live_game(tmp_saves):
    game = Game(seed=102, start_menu=False)
    before = (game.seed, game.world_mode, game.ship.x, game.ship.y)
    data = game.save_state()
    data["world"]["mode"] = "unknown"
    path = tmp_saves / "slot2.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert game.load_from_slot(2) is False
    assert (game.seed, game.world_mode, game.ship.x, game.ship.y) == before


def test_v10_preserves_tas_ping_echo_and_operator_state(tmp_saves):
    game = Game(seed=188, start_menu=False)
    game.sonar.toggle_tow(6.0)
    game.sonar.tow_payout = .42
    game.sonar.ping_cooldown = 7.5
    game.sonar.echo_history = [{"t": 1.0, "contact_id": 2}]
    game.radar_range_nm = 80.0
    game.sonar_page = 5
    game.tooltips_enabled = False
    state = game.save_state()
    assert state["version"] == SAVE_VERSION
    assert state["save_schema"] == SAVE_SCHEMA

    restored = Game(seed=1, start_menu=False)
    restored.load_state(state)
    assert restored.sonar.tow_state.value == "DEPLOYING"
    assert restored.sonar.tow_payout == pytest.approx(.42)
    assert restored.sonar.ping_cooldown == pytest.approx(7.5)
    assert restored.sonar.echo_history == [{"t": 1.0, "contact_id": 2}]
    assert restored.radar_range_nm == 80.0
    assert restored.sonar_page == 5
    assert restored.tooltips_enabled is False


def test_v10_split_run_preserves_scheduler_phase():
    uninterrupted = Game(seed=189, start_menu=False, audio_enabled=False)
    uninterrupted._sensor_acc = .13
    uninterrupted._radio_acc = .31
    uninterrupted._slow_acc = .41
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(json.loads(json.dumps(uninterrupted.save_state())))

    def isolate_scheduler(game, events):
        game._update_navigation = lambda dt: None
        game.sonar.advance_mechanics = lambda *args: None
        game._update_underwater_entities = lambda dt: None
        game._update_aviation = lambda dt: None
        game._update_air_defense = lambda dt, publish_picture: None
        game._update_enemy_torpedoes = lambda dt: None
        game._update_player_torpedoes = lambda dt: None
        game._update_sensors = lambda dt: events.append(
            ("sensor", game.sim_t, dt))
        game._update_radio_picture = lambda: events.append(
            ("radio", game.sim_t, None))
        game._update_damage_and_mission = lambda dt: events.append(
            ("slow", game.sim_t, dt))

    uninterrupted_events = []
    restored_events = []
    isolate_scheduler(uninterrupted, uninterrupted_events)
    isolate_scheduler(restored, restored_events)
    for dt in (.06, .10, .10, .20, .10):
        uninterrupted._update_sim(dt)
        restored._update_sim(dt)

    assert restored_events == uninterrupted_events
    assert (restored._sensor_acc, restored._radio_acc, restored._slow_acc) == \
        pytest.approx((uninterrupted._sensor_acc, uninterrupted._radio_acc,
                       uninterrupted._slow_acc))


def test_v10_split_run_preserves_filter_pictures_and_tma_gates(monkeypatch):
    uninterrupted = Game(seed=190, start_menu=False, audio_enabled=False)
    target = uninterrupted.subs[0]
    contact = Contact(41, target.id, "passiv", "sub")
    contact._fx, contact._fy = uninterrupted.ship.x, uninterrupted.ship.y
    for t, bearing, uncertainty in ((0.0, 358.0, 1.0),
                                    (1.0, 1.0, 1.5),
                                    (2.0, 4.0, 2.0)):
        contact.update_passive(
            bearing, 1.0, .8, "", t,
            bearing_uncertainty_deg=uncertainty)
    uninterrupted.sonar.contacts[target.id] = contact
    bearing_track = BearingTrack()
    bearing_track.add(0.0, 358.0, uninterrupted.ship.x,
                      uninterrupted.ship.y, uninterrupted.ship.course, 1.25)
    bearing_track.add(4.0, 1.0, uninterrupted.ship.x,
                      uninterrupted.ship.y, uninterrupted.ship.course, 2.5)
    bearing_track.version = 205
    uninterrupted.sonar._tracks[target.id] = bearing_track
    uninterrupted.sonar._tma_versions[target.id] = bearing_track.version
    uninterrupted.sim_t = 10.0
    uninterrupted.sonar._tma_next[target.id] = 11.0
    uninterrupted.air_picture.observe(
        track_id="R-1", kind="SURFACE", target_id=1, source="RADAR-S",
        bearing=80.0, range_nm=12.0, observer_x=0.0, observer_y=0.0,
        course=20.0, quality=.8, now=8.0, label="R-1")
    uninterrupted.radio_picture.observe(
        track_id="H-1", kind="SUB", target_id=1, source="HFDF",
        bearing=120.0, range_nm=None, observer_x=2.0, observer_y=3.0,
        course=None, quality=.7, now=0.0, label="H-1")

    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(json.loads(json.dumps(uninterrupted.save_state())))
    restored_target = next(sub for sub in restored.subs if sub.id == target.id)
    restored_contact = restored.sonar.contacts[target.id]
    restored_track = restored.sonar._tracks[target.id]

    assert restored_contact.raw_bearings == contact.raw_bearings
    assert restored_contact.passive_bearing == contact.passive_bearing
    assert restored_contact.bearing_uncertainty_deg == \
        contact.bearing_uncertainty_deg
    assert restored_contact._bearing_filter_t == contact._bearing_filter_t
    assert restored_contact._bearing_filter_rate_deg_s == \
        contact._bearing_filter_rate_deg_s
    assert restored_contact._bearing_filter_uncertainty_deg == \
        contact._bearing_filter_uncertainty_deg
    assert [point.uncertainty_deg for point in restored_track.pts] == [1.25, 2.5]
    assert restored_track.version == bearing_track.version
    assert restored.sonar._tma_versions == uninterrupted.sonar._tma_versions
    assert restored.sonar._tma_next == uninterrupted.sonar._tma_next
    assert restored.air_picture.serialize() == uninterrupted.air_picture.serialize()
    assert restored.radio_picture.serialize() == \
        uninterrupted.radio_picture.serialize()

    for item in (contact, restored_contact):
        item.update_passive(7.0, 1.0, .8, "", 3.0,
                            bearing_uncertainty_deg=1.75)
    for picture in (uninterrupted.air_picture, restored.air_picture):
        picture.observe(
            track_id="R-1", kind="SURFACE", target_id=1, source="RADAR-S",
            bearing=84.0, range_nm=12.5, observer_x=.1, observer_y=.2,
            course=22.0, quality=.85, now=10.0, label="R-1")
    for picture in (uninterrupted.radio_picture, restored.radio_picture):
        picture.observe(
            track_id="H-1", kind="SUB", target_id=1, source="HFDF",
            bearing=126.0, range_nm=None, observer_x=3.0, observer_y=3.0,
            course=None, quality=.75, now=10.0, label="H-1")

    calls = []
    monkeypatch.setattr("src.sonar.sonar.solve_tma",
                        lambda track: calls.append(track) or None)
    for game, game_target in ((uninterrupted, target),
                              (restored, restored_target)):
        track = game.sonar._tracks[target.id]
        track.add(10.0, 7.0, game.ship.x, game.ship.y,
                  game.ship.course, 1.75)
        game.sonar._update_tma(game_target, 10.5)
    assert calls == []
    uninterrupted.sonar._update_tma(target, 11.0)
    restored.sonar._update_tma(restored_target, 11.0)
    assert calls == [uninterrupted.sonar._tracks[target.id],
                     restored.sonar._tracks[target.id]]
    uninterrupted.sonar._update_tma(target, 20.0)
    restored.sonar._update_tma(restored_target, 20.0)
    assert len(calls) == 2

    assert restored_contact.passive_bearing == contact.passive_bearing
    assert restored_contact.bearing_uncertainty_deg == \
        contact.bearing_uncertainty_deg
    assert restored_contact._bearing_filter_t == contact._bearing_filter_t
    assert restored_contact._bearing_filter_rate_deg_s == \
        contact._bearing_filter_rate_deg_s
    assert restored_contact._bearing_filter_uncertainty_deg == \
        contact._bearing_filter_uncertainty_deg
    assert restored.air_picture.serialize() == uninterrupted.air_picture.serialize()
    assert restored.radio_picture.serialize() == \
        uninterrupted.radio_picture.serialize()
    assert restored.sonar._tma_versions == uninterrupted.sonar._tma_versions
    assert restored.sonar._tma_next == uninterrupted.sonar._tma_next


@pytest.mark.parametrize("slot", [True, False, 0, 6, -1, 1.0, "1", None])
@pytest.mark.parametrize("method", ["save_to_slot", "load_from_slot"])
def test_public_slot_methods_reject_invalid_slots_before_path_use(
        method, slot, tmp_saves, monkeypatch):
    game = Game(seed=9003, start_menu=False)
    path_used = False
    real_join = __import__("os").path.join

    def observed_join(*parts):
        nonlocal path_used
        path_used = True
        return real_join(*parts)

    monkeypatch.setattr("src.core.game.os.path.join", observed_join)
    with pytest.raises(ValueError, match="integer from 1 to 5"):
        getattr(game, method)(slot)
    assert path_used is False
    assert list(tmp_saves.iterdir()) == []


@pytest.mark.parametrize("version", [None, True, 0, 11, -1, 1.0, "10"])
def test_unsupported_or_non_integer_versions_are_rejected(version, tmp_saves):
    game = Game(seed=9004, start_menu=False)
    before = game.save_state()
    data = json.loads(json.dumps(before))
    data["version"] = version
    (tmp_saves / "slot1.json").write_text(json.dumps(data))

    assert game.load_from_slot(1) is False
    assert game.save_state() == before


@pytest.mark.parametrize("sonar_patch", [
    {"echo_history": "not-a-list"},
    {"echo_history": ["not-an-echo"]},
    {"echo_history": [{"t": "yesterday", "contact_id": 2}]},
    {"lofar": [None]},
    {"lofar": [[float("nan")]]},
    {"broadband": {}},
    {"history_times": [None]},
    {"tracks": {"1": [None]}},
    {"tracks": {"1": [{"t": 1.0}]}},
    {"tracks": {"1": [{"t": 1.0, "bearing": 2.0, "fx": 3.0,
                         "fy": 4.0, "fcourse": 5.0,
                         "uncertainty_deg": float("nan")}]}},
    {"track_versions": {"1": 1}},
    {"tma_next": {"1": 1.0}},
    {"contacts": {"1": {"raw_bearings": [[1.0, 2.0,
                                                 float("nan")]]}}},
    {"contacts": {"1": {"bearing_filter_t": float("nan")}}},
    {"contacts": {"1": {"bearing_filter_rate_deg_s": 999.0}}},
    {"contacts": {"1": {"bearing_filter_uncertainty_deg": -1.0}}},
    {"contacts": {"1": {"passive_bearing": "north"}}},
    {"contacts": {"1": {"bearing_filter_t": 999999.0,
                           "passive_bearing": 2.0,
                           "bearing_filter_uncertainty_deg": 1.0}}},
    {"pending_pings": {}},
    {"pending_pings": [None]},
])
def test_malformed_sonar_history_is_rejected_transactionally(
        sonar_patch, tmp_saves):
    game = Game(seed=9005, start_menu=False)
    before = game.save_state()
    data = json.loads(json.dumps(before))
    data["sonar"].update(sonar_patch)
    (tmp_saves / "slot1.json").write_text(json.dumps(data))

    assert game.load_from_slot(1) is False
    assert game.save_state() == before


@pytest.mark.parametrize("schedulers", [
    None,
    {"sensor": float("nan")},
    {"radio": .5},
    {"slow": -1.0},
])
def test_malformed_scheduler_state_is_rejected_transactionally(
        schedulers, tmp_saves):
    game = Game(seed=9008, start_menu=False)
    before = game.save_state()
    data = json.loads(json.dumps(before))
    data["schedulers"] = schedulers
    (tmp_saves / "slot1.json").write_text(json.dumps(data))

    assert game.load_from_slot(1) is False
    assert game.save_state() == before


def test_malformed_enums_are_rejected_transactionally(tmp_saves):
    game = Game(seed=9006, start_menu=False)
    before = game.save_state()
    data = json.loads(json.dumps(before))
    data["sonar_mode"] = "SIDEWAYS"
    data["sonar"]["tow_state"] = "BROKEN_ENUM"
    data["ui"]["station"] = "NOT_A_STATION"
    (tmp_saves / "slot1.json").write_text(json.dumps(data))

    assert not game.load_from_slot(1)
    assert game.save_state() == before


@pytest.mark.parametrize("entrypoint", ["slot", "legacy"])
@pytest.mark.parametrize("failure", [
    "missing", "invalid-json", "not-object", "unsupported", "early-state",
    "late-state",
])
def test_every_failed_file_load_preserves_live_state(
        entrypoint, failure, tmp_saves):
    game = Game(seed=9007, start_menu=False)
    game.ship.x += 0.125
    game.held.add(12345)
    game.map_view.cx += 1.25
    game.msg = "live transient state"
    before = game.save_state()
    before_transient = (set(game.held), game.map_view.cx, game.msg)
    path = (tmp_saves / "slot1.json" if entrypoint == "slot"
            else Path(config.SAVE_PATH))

    if failure == "invalid-json":
        path.write_text("{")
    elif failure == "not-object":
        path.write_text("[]")
    elif failure == "unsupported":
        data = json.loads(json.dumps(before))
        data["version"] = SAVE_VERSION + 1
        path.write_text(json.dumps(data))
    elif failure == "early-state":
        path.write_text(json.dumps({"version": SAVE_VERSION,
                                    "save_schema": SAVE_SCHEMA,
                                    "seed": 1, "ship": None}))
    elif failure == "late-state":
        data = json.loads(json.dumps(before))
        data["ui"]["map_scale"] = "not-a-number"
        path.write_text(json.dumps(data))

    loaded = (game.load_from_slot(1) if entrypoint == "slot"
              else game.load_game())
    assert loaded is False
    assert game.save_state() == before
    assert (game.held, game.map_view.cx, game.msg) == before_transient
