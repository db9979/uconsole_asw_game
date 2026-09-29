"""Phase 0 of the physics upgrade: save v12, persisted AI timers, strict
damage block, the simulated AIS receiver and stateless randomness."""

import copy
import json
import math

import pytest

from src.core import config, detrand
from src.core.game import Game
from src.core.save_schema import SAVE_ROOT_FIELDS
from src.core.version import SAVE_SCHEMA, SAVE_VERSION
from src.enemies.surface import SurfaceShip
from src.sensors import ais


def _game(seed=1201):
    return Game(seed=seed, start_menu=False, audio_enabled=False)


def test_save_is_v33_and_older_documents_are_rejected():
    game = _game()
    state = json.loads(json.dumps(game.save_state()))
    assert (state["version"], state["save_schema"]) == (33, "u-jagd-save-v33")
    assert (SAVE_VERSION, SAVE_SCHEMA) == (33, "u-jagd-save-v33")
    assert set(state) == SAVE_ROOT_FIELDS
    before = game.save_state()
    legacy = copy.deepcopy(state)
    legacy["version"] = 11
    legacy["save_schema"] = "u-jagd-save-v11"
    del legacy["ais"]
    for row in legacy["subs"]:
        del row["active_ping_cd"]
    assert not game._load_save_data(legacy)
    # v13 differs only by the operator plot layer.
    v13 = copy.deepcopy(state)
    v13["version"] = 13
    v13["save_schema"] = "u-jagd-save-v13"
    del v13["plot"]
    assert not game._load_save_data(v13)
    # v14 differs only by the crew block and the boat orders.
    v14 = copy.deepcopy(state)
    v14["version"] = 14
    v14["save_schema"] = "u-jagd-save-v14"
    del v14["crew"]
    for row in v14["subs"]:
        for key in ("manual", "order_course", "order_speed", "order_depth",
                    "last_bottom_m", "manual_ping_pending"):
            del row[key]
    del v14["ui"]["local_side"]
    assert not game._load_save_data(v14)
    # v15 differs only by the foreign pings still travelling to the frigate.
    v15 = copy.deepcopy(state)
    v15["version"] = 15
    v15["save_schema"] = "u-jagd-save-v15"
    del v15["ping_intercepts"]
    assert not game._load_save_data(v15)
    # v16 differs by the boats' plant state (diesel fuel, charge rate, air).
    v16 = copy.deepcopy(state)
    v16["version"] = 16
    v16["save_schema"] = "u-jagd-save-v16"
    for row in v16["subs"]:
        if row["endurance"] is not None:
            row["endurance"]["version"] = 1
            for key in ("fuel_kwh", "charge_rate", "air"):
                del row["endurance"][key]
    assert not game._load_save_data(v16)
    # v17 differs only by the crewed boat's ESM picture (crew.esm).
    v17 = copy.deepcopy(state)
    v17["version"] = 17
    v17["save_schema"] = "u-jagd-save-v17"
    assert not game._load_save_data(v17)
    # v18 differs only by the submarines' tanks, trim and air (ballast).
    v18 = copy.deepcopy(state)
    v18["version"] = 18
    v18["save_schema"] = "u-jagd-save-v18"
    for row in v18["subs"]:
        del row["ballast"]
        del row["damage_control"]
    assert not game._load_save_data(v18)
    # v19 differs only by the submarines' compartments (damage_control).
    v19 = copy.deepcopy(state)
    v19["version"] = 19
    v19["save_schema"] = "u-jagd-save-v19"
    for row in v19["subs"]:
        del row["damage_control"]
    assert not game._load_save_data(v19)
    # v20 differs by HQ tasking, the crew's watch bill, the patrol aircraft
    # and the buoy owner.
    v20 = copy.deepcopy(state)
    v20["version"] = 20
    v20["save_schema"] = "u-jagd-save-v20"
    del v20["tasking"]
    del v20["watch"]
    del v20["mpa"]
    for buoy in v20["buoys"]:
        del buoy["owner"]
    assert not game._load_save_data(v20)
    # v22 differs only by the variable-depth sonar's state.
    v22 = copy.deepcopy(state)
    v22["version"] = 22
    v22["save_schema"] = "u-jagd-save-v22"
    for key in ("vds_state", "vds_payout", "vds_depth_m", "vds_depth_target_m",
                "vds_settle_s", "vds_handling_ok"):
        del v22["sonar"][key]
    assert not game._load_save_data(v22)
    # v23 differs only by the crewed boat's attack computer (crew.orders.tdc);
    # this game has no crewed boat, so the version alone must reject it.
    v23 = copy.deepcopy(state)
    v23["version"] = 23
    v23["save_schema"] = "u-jagd-save-v23"
    assert not game._load_save_data(v23)
    # v24 differs only by the radar's mast echoes and marks (radar_marks).
    v24 = copy.deepcopy(state)
    v24["version"] = 24
    v24["save_schema"] = "u-jagd-save-v24"
    del v24["radar_marks"]
    assert not game._load_save_data(v24)
    # v25 differs only by the crewed boat's tube flood states (crew.orders.tubes).
    v25 = copy.deepcopy(state)
    v25["version"] = 25
    v25["save_schema"] = "u-jagd-save-v25"
    assert not game._load_save_data(v25)
    # v26 differs only by the boat ESM's main-beam reference (crew.esm version 2).
    v26 = copy.deepcopy(state)
    v26["version"] = 26
    v26["save_schema"] = "u-jagd-save-v26"
    assert not game._load_save_data(v26)
    # v27 differs only by the Bridge's autopilot route (root ``route``).
    v27 = copy.deepcopy(state)
    v27["version"] = 27
    v27["save_schema"] = "u-jagd-save-v27"
    del v27["route"]
    assert not game._load_save_data(v27)
    # v28 differs only by the frigate's depth charges and own ASROC stores.
    v28 = copy.deepcopy(state)
    v28["version"] = 28
    v28["save_schema"] = "u-jagd-save-v28"
    for key in ("depth_charges", "depth_charge_seq", "own_stores"):
        del v28["asw"][key]
    assert not game._load_save_data(v28)
    # v29 differs only by the boat radio's HQ orders (crew.radio version 2).
    v29 = copy.deepcopy(state)
    v29["version"] = 29
    v29["save_schema"] = "u-jagd-save-v29"
    assert not game._load_save_data(v29)
    # v30 differs only by the AIS reports' reported position.
    v30 = copy.deepcopy(state)
    v30["version"] = 30
    v30["save_schema"] = "u-jagd-save-v30"
    for row in v30["ais"]:
        del row["x"], row["y"]
    assert not game._load_save_data(v30)
    # v31 differs only by the helicopter's radar switch, the patrol
    # aircraft's MAD passes and the AI boats' radar hold.
    v31 = copy.deepcopy(state)
    v31["version"] = 31
    v31["save_schema"] = "u-jagd-save-v31"
    del v31["helo"]["radar_on"], v31["mpa"]["mad_mode"]
    for row in v31["subs"]:
        del row["radar_hold_s"]
    assert not game._load_save_data(v31)
    # v32 differs only by the submarines' tube flooding and flood transients.
    v32 = copy.deepcopy(state)
    v32["version"] = 32
    v32["save_schema"] = "u-jagd-save-v32"
    for row in v32["subs"]:
        for key in ("flood_noise_left", "flood_quiet", "flood_seq",
                    "ai_tube_left", "ai_fire_pending"):
            del row[key]
    assert not game._load_save_data(v32)
    assert game.save_state() == before


def test_sub_ping_cooldown_and_surface_evasion_survive_save_load():
    game = _game(1202)
    sub = game.subs[0]
    sub._active_ping_cd = 37.5
    ship = next(iter(game.warships or game.civilians), None)
    if ship is None:
        ship = SurfaceShip(game.ship.x + 8.0, game.ship.y, game.rng_world,
                           profile=game.runtime_catalog.surfaces["warship_01"],
                           side="hostile", doctrine="surface_combatant",
                           runtime_catalog=game.runtime_catalog)
        game.warships.append(ship)
    ship.alert_torpedo(123.0)
    state = json.loads(json.dumps(game.save_state()))
    restored = _game(1)
    assert restored._load_save_data(copy.deepcopy(state))
    again = next(item for item in restored.subs if item.id == sub.id)
    assert again._active_ping_cd == 37.5
    twin = next(item for item in restored.warships + restored.civilians
                if item.id == ship.id)
    assert twin._torpedo_evade_left == ship._torpedo_evade_left > 0.0
    assert twin._torpedo_threat_bearing == pytest.approx(123.0)
    for _ in range(40):
        game._update_sim(.25)
        restored._update_sim(.25)
    assert restored.save_state()["subs"] == game.save_state()["subs"]
    assert (restored.save_state()["warships"], restored.save_state()["civilians"]) \
        == (game.save_state()["warships"], game.save_state()["civilians"])


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(extra=1),
    lambda d: d.pop("teams"),
    lambda d: d.update(repair_mult=-1.0),
    lambda d: d["teams"].pop("3"),
    lambda d: d["teams"].update({"1": "nowhere"}),
    lambda d: d["compartments"].pop("bridge"),
    lambda d: d["compartments"]["bridge"].update(extra=0),
    lambda d: d["compartments"]["bridge"].pop("fire"),
    lambda d: d["compartments"]["bridge"].update(flood=config.DMG_DESTROY_FLOOD + 1),
    lambda d: d["compartments"]["bridge"].update(state="SUNK"),
])
def test_damage_block_is_validated_exactly(mutation):
    game = _game(1203)
    state = json.loads(json.dumps(game.save_state()))
    mutation(state["damage"])
    before = game.save_state()
    assert not game._load_save_data(state)
    assert game.save_state() == before


@pytest.mark.parametrize("field,value", [
    ("active_ping_cd", -1.0),
    ("active_ping_cd", config.SUB_ACTIVE_PING_COOLDOWN_S + 1.0),
])
def test_sub_ping_cooldown_is_bounded(field, value):
    game = _game(1204)
    state = json.loads(json.dumps(game.save_state()))
    state["subs"][0][field] = value
    assert not game._load_save_data(state)


def test_reporting_interval_follows_class_a_cadence():
    assert ais.reporting_interval_s(0.0) == 180.0
    assert ais.reporting_interval_s(10.0) == 10.0
    assert ais.reporting_interval_s(18.0) == 6.0
    assert ais.reporting_interval_s(25.0) == 2.0
    assert 18.0 < ais.vhf_range_nm() < 22.0


def _civilian_near(game, distance):
    civil = next(c for c in game.civilians if c.ais_transmitting)
    civil.x, civil.y = game.ship.x + distance, game.ship.y
    game.civilians = [civil]
    game.warships = []
    game.world.land_blocks_line = lambda *args: False
    return civil


def test_radar_track_has_no_truth_name_or_course_until_ais_report():
    game = _game(1205)
    civil = _civilian_near(game, 4.0)
    game.ais.reports.clear()
    game.ais.update = lambda *args, **kwargs: None   # receiver silent
    game._update_air_picture(full_scan=True)
    track = game.air_picture._tracks[f"S-{civil.id}"]
    assert track.label == f"S-{civil.id}"
    assert track.course is None
    assert civil.name not in track.label


def test_ais_decodes_dynamic_then_static_reports_in_vhf_range():
    game = _game(1206)
    civil = _civilian_near(game, 4.0)
    receiver = game.ais
    receiver.update(0.0, [civil], game.ship, game.world)
    report = receiver.reports[civil.id]
    assert report.name is None and receiver.label_for(civil.id) is None
    assert receiver.course_for(civil.id, 0.0) == pytest.approx(civil.course % 360.0)
    for step in range(1, 800):
        receiver.update(step * 0.5, [civil], game.ship, game.world)
    assert receiver.label_for(civil.id) == civil.name
    far = _game(1207)
    other = _civilian_near(far, ais.vhf_range_nm() + 1.0)
    far.ais.update(0.0, [other], far.ship, far.world)
    assert far.ais.reports == {}


def test_ais_state_round_trips_and_rejects_malformed_rows():
    game = _game(1208)
    civil = _civilian_near(game, 3.0)
    for step in range(900):
        game.ais.update(step * 0.5, [civil], game.ship, game.world)
    game.sim_t = 450.0
    state = json.loads(json.dumps(game.save_state()))
    assert state["ais"] and state["ais"][0]["name"] == civil.name
    restored = _game(1)
    assert restored._load_save_data(copy.deepcopy(state))
    assert restored.save_state()["ais"] == state["ais"]
    for mutation in (lambda r: r.update(cog=360.0),
                     lambda r: r.update(t_static=None),
                     lambda r: r.update(target_id=99999999),
                     lambda r: r.update(extra=1),
                     lambda r: r.update(t_dynamic=1e9)):
        broken = copy.deepcopy(state)
        mutation(broken["ais"][0])
        assert not restored._load_save_data(broken)


def test_detrand_is_stable_and_uniform():
    assert detrand.bits(1, "x", 2, 3) == detrand.bits(1, "x", 2, 3)
    assert detrand.bits(1, "x", 2, 3) != detrand.bits(1, "y", 2, 3)
    assert detrand.bits(1, "x", 2, 3) != detrand.bits(1, "x", 3, 2)
    values = [detrand.u01(7, "stat", i) for i in range(4000)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert abs(sum(values) / len(values) - 0.5) < 0.02
    normals = [detrand.normal(7, "n", i) for i in range(4000)]
    mean = sum(normals) / len(normals)
    var = sum((n - mean) ** 2 for n in normals) / len(normals)
    assert abs(mean) < 0.06 and abs(math.sqrt(var) - 1.0) < 0.06
    # Frozen reference value: changing the mixer would silently re-seed
    # every stateless draw in saved games.
    assert detrand.bits(0, "", 0) == 0x21FA69A58F3D62F5
    assert detrand.bits(42, "ujagd", 1) == 0xC19DD5FB35331834
