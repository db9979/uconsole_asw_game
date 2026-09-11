import copy
from dataclasses import replace
import json
import math
import random

import pytest

from src.core.game import Game
from src.data import catalog
from src.enemies.endurance import SubmarineEndurance
from src.enemies.sub import Sub


class Ocean:
    size_nm = 500

    @staticmethod
    def depth_m(_x, _y):
        return 1000

    @staticmethod
    def thermocline_depth_m(_x, _y):
        return 80

    @staticmethod
    def on_land(_x, _y):
        return False

    @staticmethod
    def sonar_path_blocked(*_args):
        return False


def small_profile(key="diesel_alt", **changes):
    profile = catalog.CATALOG.endurances[f"endurance.{key}"]
    return replace(profile, **changes)


def test_catalog_endurance_is_strict_fictional_and_excludes_nuclear_profiles():
    expected = {key for key, profile in catalog.CATALOG.subs.items()
                if not profile.is_nuclear}
    assert {key.removeprefix("endurance.")
            for key in catalog.CATALOG.endurances} == expected
    claim_coordinates = {
        (claim.profile_key, path): claim
        for claim in catalog.CATALOG.provenance_claims
        for path in claim.field_paths if path.startswith("/endurances/")
    }
    for key, profile in catalog.CATALOG.endurances.items():
        profile_key = key.removeprefix("endurance.")
        for field in profile.__dataclass_fields__:
            if field == "key":
                continue
            claim = claim_coordinates[(profile_key, f"/endurances/{key}/{field}")]
            if getattr(profile, field) is not None:
                assert claim.status == "game_assumption"
                assert claim.source_ids == ("u-jagd.game-model",)


@pytest.mark.parametrize("field,value", [
    ("battery_capacity_kwh", float("nan")),
    ("hotel_load_kw", True),
    ("reserve_start_fraction", 1.0),
    ("aip_power_kw", 10.0),
])
def test_endurance_catalog_rejects_malformed_values(field, value):
    raw = catalog._v2_to_dict(small_profile())
    raw[field] = value
    with pytest.raises(ValueError):
        catalog._endurance_from_dict(raw, "test.endurance")


def test_runtime_catalog_rejects_missing_and_nuclear_endurance():
    snapshot = catalog.CATALOG.runtime_snapshot()
    missing = copy.deepcopy(snapshot)
    missing["components"]["subs.json"]["endurances"].pop()
    with pytest.raises(ValueError):
        catalog.catalog_from_runtime_snapshot(missing)

    nuclear = copy.deepcopy(snapshot)
    raw = catalog._v2_to_dict(small_profile())
    raw["key"] = "endurance.ssn"
    nuclear["components"]["subs.json"]["endurances"].append(raw)
    with pytest.raises(ValueError):
        catalog.catalog_from_runtime_snapshot(nuclear)


def test_energy_balance_is_closed_across_load_generation_and_aip():
    endurance = SubmarineEndurance(small_profile(
        "aip_modern", battery_capacity_kwh=10, hotel_load_kw=2,
        propulsion_max_kw=8, generator_power_kw=6, aip_power_kw=4,
        aip_energy_kwh=5))
    endurance.battery_kwh = 1
    endurance.phase = "AIP"
    before_battery = endurance.battery_kwh
    before_aip = endurance.aip_energy_kwh
    flow = endurance.update(1800, 13, 13, 50)
    assert before_battery + (before_aip - endurance.aip_energy_kwh) == pytest.approx(
        endurance.battery_kwh + flow.served_kwh + flow.curtailed_kwh)
    assert flow.load_kwh == pytest.approx(5)
    assert flow.aip_kwh == pytest.approx(2)

    endurance.phase = "SNORKEL"
    before = endurance.battery_kwh
    flow = endurance.update(1800, 0, 13, 8)
    assert before + flow.generator_kwh == pytest.approx(
        endurance.battery_kwh + flow.served_kwh + flow.curtailed_kwh)


def test_reserve_hysteresis_has_no_flutter_and_stores_never_go_negative():
    endurance = SubmarineEndurance(small_profile(
        "aip_modern", battery_capacity_kwh=10, hotel_load_kw=1,
        propulsion_max_kw=1, aip_power_kw=1, aip_energy_kwh=0.01,
        reserve_start_fraction=.2, reserve_stop_fraction=.8))
    endurance.battery_kwh = 2
    endurance.update(1, 0, 13, 60)
    assert endurance.phase == "AIP"
    endurance.battery_kwh = 2.0001
    endurance.update(1, 0, 13, 60)
    assert endurance.phase == "AIP"
    endurance.update(100000, 13, 13, 60)
    assert endurance.phase == "ASCENDING"
    assert endurance.battery_kwh >= 0
    assert endurance.aip_energy_kwh >= 0
    with pytest.raises(ValueError):
        endurance.update(1, float("nan"), 13, 60)


def test_generator_waits_for_actual_snorkel_depth_and_radio_is_separate():
    endurance = SubmarineEndurance(small_profile(
        battery_capacity_kwh=10, hotel_load_kw=1, propulsion_max_kw=1,
        generator_power_kw=10, reserve_start_fraction=.2,
        reserve_stop_fraction=.21, radio_duration_s=2))
    endurance.battery_kwh = 1
    endurance.phase = "ASCENDING"
    endurance.return_depth_m = 60
    assert endurance.update(60, 0, 11, 8.2).generator_kwh == 0
    assert endurance.phase == "ASCENDING"
    assert endurance.update(1, 0, 11, 8).generator_kwh > 0
    assert endurance.phase == "SNORKEL"
    generated = 0.0
    for _ in range(1000):
        generated += endurance.update(1, 0, 11, 8).generator_kwh
        if endurance.phase == "RADIO":
            break
    assert generated > 0
    assert endurance.phase == "RADIO"
    assert endurance.transmitting
    endurance.update(2, 0, 11, 8)
    assert endurance.phase == "DESCENDING"
    assert not endurance.transmitting


def test_endurance_preserves_the_legacy_patrol_snorkel_rng_draw():
    sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1601))
    sub.turn_left = 1000
    sub.endurance.battery_kwh = 0
    before = sub.rng.getstate()
    legacy = random.Random()
    legacy.setstate(before)
    legacy.random()
    sub.update(.1, None, Ocean())
    assert sub.endurance.phase == "ASCENDING"
    assert sub.rng.getstate() == legacy.getstate()


@pytest.mark.parametrize("state,depth", [("PATROLLE", 55), ("LAUER", 60)])
def test_legacy_snorkel_rng_draw_is_not_added_outside_old_conditions(state, depth):
    sub = Sub(100, 100, depth, 0, "diesel_alt", random.Random(1602))
    sub.state = state
    sub.turn_left = 1000
    sub.evac_left = 1000
    before = sub.rng.getstate()
    sub.update(.1, None, Ocean())
    assert sub.rng.getstate() == before


def test_depleted_diesel_and_underpowered_aip_cap_motion_without_negative_stores():
    diesel = Sub(100, 100, 50, 90, "diesel_alt", random.Random(1603))
    diesel.state = "LAUER"
    diesel.evac_left = 1000
    diesel.speed = 10
    diesel.endurance.battery_kwh = 0
    before = (diesel.x, diesel.y)
    diesel.update(1, None, Ocean())
    assert diesel.speed == 0
    assert (diesel.x, diesel.y) == before
    assert diesel.endurance.battery_kwh == 0

    aip = Sub(100, 100, 50, 90, "aip_modern", random.Random(1604))
    aip.state = "LAUER"
    aip.evac_left = 1000
    aip.speed = 10
    aip.endurance = SubmarineEndurance(small_profile(
        "aip_modern", battery_capacity_kwh=10, hotel_load_kw=1,
        propulsion_max_kw=9, propulsion_exponent=1, aip_power_kw=2,
        aip_energy_kwh=1))
    aip.endurance.battery_kwh = 0
    aip.endurance.phase = "AIP"
    aip.update(1, None, Ocean())
    assert aip.speed == pytest.approx(aip.motion.maximum_speed_kn / 9)
    assert math.hypot(aip.x - 100, aip.y - 100) == pytest.approx(
        aip.speed / 3600)
    assert aip.endurance.battery_kwh >= 0
    assert aip.endurance.aip_energy_kwh >= 0


@pytest.mark.parametrize("parts", [
    [720], [360, 360], [17, 43, 60, 200, 400], [1] * 720,
    [.37, .13, .41, .09] * 720,
])
def test_endurance_phase_and_stores_are_stable_under_partitioning(parts):
    profile = small_profile(
        battery_capacity_kwh=10, hotel_load_kw=1, propulsion_max_kw=1,
        generator_power_kw=10, reserve_start_fraction=.2,
        reserve_stop_fraction=.21, radio_duration_s=30)
    endurance = SubmarineEndurance(profile)
    endurance.battery_kwh = 1
    endurance.phase = "ASCENDING"
    endurance.return_depth_m = 60
    for dt in parts:
        endurance.update(dt, 0, 11, 8)
    reference = SubmarineEndurance(profile)
    reference.battery_kwh = 1
    reference.phase = "ASCENDING"
    reference.return_depth_m = 60
    reference.update(720, 0, 11, 8)
    assert endurance.phase == reference.phase
    assert endurance.radio_left_s == pytest.approx(reference.radio_left_s, abs=1e-12)
    assert endurance.battery_kwh == pytest.approx(reference.battery_kwh, abs=1e-12)
    assert endurance.aip_energy_kwh == pytest.approx(
        reference.aip_energy_kwh, abs=1e-12)


@pytest.mark.parametrize("phase", ["SUBMERGED", "AIP", "SNORKEL", "RADIO"])
@pytest.mark.parametrize("parts", [[1.0], [.5, .5], [.17, .29, .54]])
def test_subsecond_energy_transition_partitioning(phase, parts):
    profile = small_profile(
        "aip_modern", battery_capacity_kwh=10, hotel_load_kw=1,
        propulsion_max_kw=1, propulsion_exponent=1, generator_power_kw=10,
        aip_power_kw=2, aip_energy_kwh=1, reserve_start_fraction=.2,
        reserve_stop_fraction=.8, radio_duration_s=30)

    def run(intervals):
        endurance = SubmarineEndurance(profile)
        endurance.phase = phase
        load_rate = endurance.load_kw(0, 11) / 3600
        if phase == "SUBMERGED":
            endurance.battery_kwh = 2 + load_rate * .63
        elif phase == "AIP":
            endurance.battery_kwh = 1
            endurance.aip_energy_kwh = profile.aip_power_kw / 3600 * .63
        elif phase == "SNORKEL":
            net_rate = profile.generator_power_kw / 3600 - load_rate
            endurance.battery_kwh = 8 - net_rate * .63
        else:
            endurance.battery_kwh = 5
            endurance.radio_left_s = .63
        totals = [0.0] * 5
        for interval in intervals:
            flow = endurance.update(interval, 0, 11, 8)
            for index, value in enumerate((
                    flow.load_kwh, flow.served_kwh, flow.generator_kwh,
                    flow.aip_kwh, flow.curtailed_kwh)):
                totals[index] += value
        return endurance, totals

    reference, reference_flow = run([1.0])
    actual, actual_flow = run(parts)
    assert actual.phase == reference.phase
    assert actual.radio_left_s == pytest.approx(reference.radio_left_s, abs=1e-12)
    assert actual.battery_kwh == pytest.approx(reference.battery_kwh, abs=1e-12)
    assert actual.aip_energy_kwh == pytest.approx(
        reference.aip_energy_kwh, abs=1e-12)
    assert actual_flow == pytest.approx(reference_flow, abs=1e-12)


def test_surface_cycle_depth_gate_is_stable_under_runtime_partitioning():
    def run(parts):
        sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1605))
        sub.endurance.battery_kwh = 0
        sub.endurance.phase = "ASCENDING"
        sub.endurance.return_depth_m = 60
        for dt in parts:
            sub.update(dt, None, Ocean())
        return (sub.depth, sub.target_depth, sub.endurance.serialize())

    whole = run([720])
    split = run([360, 360])
    assert split[0] == pytest.approx(whole[0], abs=1e-12)
    assert split[1] == pytest.approx(whole[1], abs=1e-12)
    assert split[2]["phase"] == whole[2]["phase"]
    for field in ("battery_kwh", "aip_energy_kwh", "return_depth_m",
                  "radio_left_s"):
        assert split[2][field] == pytest.approx(whole[2][field], abs=1e-12)


@pytest.mark.parametrize("parts", [[.075], [.05, .025], [.025, .025, .025]])
def test_snorkel_depth_crossing_does_not_credit_early_generation(parts):
    def run(parts):
        sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1607))
        threshold = (sub.endurance.profile.snorkel_depth_m
                     + sub.endurance.DEPTH_TOLERANCE_M)
        sub.depth = threshold + sub.motion.depth_rate_m_s * .05
        sub.endurance.battery_kwh = 0
        sub.endurance.phase = "ASCENDING"
        sub.endurance.return_depth_m = 60
        for interval in parts:
            sub.update(interval, None, Ocean())
        return sub

    whole = run([.075])
    split = run(parts)
    assert split.endurance.battery_kwh == pytest.approx(
        whole.endurance.battery_kwh, abs=1e-12)
    assert split.depth == pytest.approx(whole.depth, abs=1e-12)


def test_patrol_speed_resumes_when_descent_completes():
    sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1608))
    sub.state = "PATROLLE"
    sub.speed = 0
    sub.endurance.phase = "DESCENDING"
    sub.endurance.return_depth_m = 60
    sub.depth = 60 - sub.motion.depth_rate_m_s * .05

    sub.update(.05, None, Ocean())

    assert sub.endurance.phase == "SUBMERGED"
    assert sub.speed == pytest.approx(min(6.0, sub.speed_for_state()))


@pytest.mark.parametrize("state", ["PATROLLE", "EVADE", "LAUER"])
def test_descent_completion_returns_residual_time_to_state_update(state):
    def run(parts):
        sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1609))
        sub.state = state
        sub.evac_left = 100
        sub.speed = 0
        sub.endurance.phase = "DESCENDING"
        sub.endurance.return_depth_m = 60
        sub.depth = (60 - sub.endurance.DEPTH_TOLERANCE_M
                     - sub.motion.depth_rate_m_s * .05)
        for interval in parts:
            sub.update(interval, None, Ocean())
        return sub

    whole = run([1.0])
    split = run([.05, .95])
    assert whole.endurance.phase == split.endurance.phase
    assert whole.speed == pytest.approx(split.speed, abs=1e-12)
    assert whole.depth == pytest.approx(split.depth, abs=1e-12)
    assert whole.x == pytest.approx(split.x, abs=1e-12)
    assert whole.y == pytest.approx(split.y, abs=1e-12)
    assert whole.endurance.battery_kwh == pytest.approx(
        split.endurance.battery_kwh, abs=1e-12)


@pytest.mark.parametrize("parts", [[1.0], [.5, .5], [.17, .29, .54]])
def test_subsecond_reserve_transition_has_stable_motion_and_stores(parts):
    def run(intervals):
        sub = Sub(100, 100, 60, 90, "diesel_alt", random.Random(1606))
        sub.state = "EVADE"
        sub.evac_left = 1000
        sub.speed = 6
        load_rate = sub.endurance.load_kw(
            sub.speed, sub.motion.maximum_speed_kn) / 3600
        reserve = (sub.endurance.profile.battery_capacity_kwh
                   * sub.endurance.profile.reserve_start_fraction)
        sub.endurance.battery_kwh = reserve + load_rate * .63
        for interval in intervals:
            sub.update(interval, None, Ocean())
        return sub

    reference = run([1.0])
    actual = run(parts)
    assert actual.endurance.phase == reference.endurance.phase
    assert actual.endurance.battery_kwh == pytest.approx(
        reference.endurance.battery_kwh, abs=1e-12)
    assert actual.speed == pytest.approx(reference.speed, abs=1e-12)
    assert actual.x == pytest.approx(reference.x, abs=1e-12)
    assert actual.y == pytest.approx(reference.y, abs=1e-12)


def test_radio_generator_stops_at_exact_event_duration():
    endurance = SubmarineEndurance(small_profile(generator_power_kw=3600))
    endurance.phase = "RADIO"
    endurance.radio_left_s = .35
    endurance.return_depth_m = 60
    endurance.battery_kwh = 0
    flow = endurance.update(1, 0, 11, 8)
    assert flow.generator_kwh == pytest.approx(.35)
    assert endurance.phase == "DESCENDING"


def test_endurance_and_surface_loops_are_strictly_bounded(monkeypatch):
    endurance = SubmarineEndurance(small_profile())
    endurance.phase = "RADIO"
    endurance.radio_left_s = .35
    endurance.battery_kwh = 0
    calls = 0
    original_step = SubmarineEndurance._update_step

    def counted_step(self, *args):
        nonlocal calls
        calls += 1
        return original_step(self, *args)

    monkeypatch.setattr(SubmarineEndurance, "_update_step", counted_step)
    endurance.update(1e12, 0, 11, 8)
    assert calls <= SubmarineEndurance.MAX_SUBSTEPS
    assert math.isfinite(endurance.battery_kwh) and endurance.battery_kwh >= 0
    assert math.isfinite(endurance.aip_energy_kwh) and endurance.aip_energy_kwh >= 0
    monkeypatch.setattr(SubmarineEndurance, "_update_step", original_step)

    sub = Sub(100, 100, 60, 0, "diesel_alt", random.Random(1607))
    sub.endurance.phase = "ASCENDING"
    surface_calls = 0
    original_update = SubmarineEndurance.update

    def counted_update(self, *args):
        nonlocal surface_calls
        surface_calls += 1
        return original_update(self, *args)

    monkeypatch.setattr(SubmarineEndurance, "update", counted_update)
    sub.update(1e12, None, Ocean())
    assert surface_calls <= SubmarineEndurance.MAX_SUBSTEPS
    assert math.isfinite(sub.depth) and sub.depth >= 0
    assert math.isfinite(sub.endurance.battery_kwh)


def _prior_r16_save(game):
    prior = copy.deepcopy(game.save_state())
    for component in prior["catalog_snapshot"]["components"].values():
        component.pop("endurances")
    for row in prior["subs"]:
        row.pop("endurance")
    return prior


def test_exact_prior_r16_v10_shape_upgrades_and_canonicalizes(tmp_path):
    source = Game(seed=1612, start_menu=False, audio_enabled=False)
    prior = _prior_r16_save(source)
    frozen_component_fields = {
        "version", "profiles", "references", "machines", "sensors",
        "emitters", "weapons", "launchers", "magazines", "countermeasures",
    }
    assert all(set(component) == frozen_component_fields
               for component in prior["catalog_snapshot"]["components"].values())
    assert all("endurance" not in row for row in prior["subs"])
    assert not source._load_save_data(copy.deepcopy(prior))
    path = tmp_path / "r15-v10.json"
    path.write_text(json.dumps(prior), encoding="utf-8")
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored.load_game(str(path))
    assert restored.save_state()["catalog_snapshot"] == catalog.CATALOG.runtime_snapshot()
    for sub in restored.subs:
        expected = catalog.CATALOG.endurances.get(f"endurance.{sub.stype.key}")
        assert (sub.endurance is None) == (expected is None)
        if expected is not None:
            assert sub.endurance.battery_kwh == expected.battery_capacity_kwh
            assert sub.endurance.aip_energy_kwh == (expected.aip_energy_kwh or 0)


@pytest.mark.parametrize("mutation", [
    lambda value: value["catalog_snapshot"]["components"]["subs.json"].update(
        endurances=[]),
    lambda value: value["catalog_snapshot"]["entries"]["subs.json"][0].update(
        quiet=.123456),
    lambda value: value["subs"][0].update(endurance={}),
    lambda value: value["subs"][0].update(unknown_r15_field=True),
])
def test_prior_r16_near_misses_are_rejected_transactionally(mutation):
    game = Game(seed=1613, start_menu=False, audio_enabled=False)
    prior = _prior_r16_save(game)
    mutation(prior)
    before = game.save_state()
    assert not game._load_save_data(prior, allow_pre_r9=True)
    assert game.save_state() == before


@pytest.mark.parametrize("mutation", [
    lambda value: value["catalog_snapshot"].update(version=2.0),
    lambda value: value["catalog_snapshot"]["components"]["subs.json"].update(
        version=2.0),
    lambda value: value["catalog_snapshot"]["entries"]["subs.json"][0].update(
        is_nuclear=0),
])
def test_prior_r16_snapshot_numeric_types_are_exact_and_transactional(mutation):
    game = Game(seed=1614, start_menu=False, audio_enabled=False)
    prior = _prior_r16_save(game)
    mutation(prior)
    before = game.save_state()
    assert not game._load_save_data(prior, allow_pre_r9=True)
    assert game.save_state() == before


def test_prior_r16_snockel_resumes_without_patrol_or_rng_draw(tmp_path):
    source = Game(seed=1615, start_menu=False, audio_enabled=False)
    prior = _prior_r16_save(source)
    row = next(item for item in prior["subs"]
               if f"endurance.{item['stype']}" in catalog.CATALOG.endurances)
    row["state"] = "SNOCKEL"
    row["depth"] = 20.0
    row["target_depth"] = 8.0
    row["evac_left"] = 12.5
    path = tmp_path / "r15-snockel-v10.json"
    path.write_text(json.dumps(prior), encoding="utf-8")
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    assert restored.load_game(str(path))
    sub = next(item for item in restored.subs if item.id == row["id"])
    before_rng = sub.rng.getstate()
    before_battery = sub.endurance.battery_kwh
    sub.update(.5, None, Ocean())
    assert sub.state == "PATROLLE"
    assert sub.evac_left == 0.0
    assert sub.endurance.phase == "RADIO"
    assert sub.endurance.radio_left_s == pytest.approx(12.0)
    assert sub.endurance.battery_kwh < before_battery
    assert sub.rng.getstate() == before_rng


@pytest.mark.parametrize("legacy_state", [
    "PATROLLE", "EVADE", "LAUER", "SINKING", "SUNK",
])
def test_prior_r16_other_submarine_states_map_exactly(legacy_state):
    game = Game(seed=1616, start_menu=False, audio_enabled=False)
    prior = _prior_r16_save(game)
    prior["subs"][0]["state"] = legacy_state
    prior["subs"][0]["evac_left"] = 7.25
    upgraded = Game._upgrade_pre_r16_v10(prior)
    assert upgraded["subs"][0]["state"] == legacy_state
    assert upgraded["subs"][0]["evac_left"] == 7.25


def test_v10_endurance_transition_continues_identically_through_save():
    control = Game(seed=1610, start_menu=False, audio_enabled=False)
    sub = Sub(control.ship.x + 10, control.ship.y, 60, 0, "diesel_alt",
              control.rng_world, runtime_catalog=control.runtime_catalog,
              asw_rng=control.rng_asw)
    control.subs.append(sub)
    sub.endurance.phase = "RADIO"
    sub.endurance.radio_left_s = .35
    sub.endurance.battery_kwh *= .6
    sub.endurance.aip_energy_kwh *= .4
    state = control.save_state()
    restored = Game(seed=2, start_menu=False, audio_enabled=False)
    restored.load_state(copy.deepcopy(state))
    for _ in range(10):
        control._update_sim(.1)
        restored._update_sim(.1)
    left = next(item for item in control.subs if item.id == sub.id)
    right = next(item for item in restored.subs if item.id == sub.id)
    assert right.endurance.serialize() == left.endurance.serialize()
    assert (right.depth, right.target_depth, right.rng.getstate()) == (
        left.depth, left.target_depth, left.rng.getstate())


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(battery_kwh=float("nan")),
    lambda value: value.update(extra=1),
    lambda value: value.pop("phase"),
    lambda value: value.update(phase="AIP"),
])
def test_malformed_endurance_save_is_rejected_transactionally(mutation):
    game = Game(seed=1611, start_menu=False, audio_enabled=False)
    game.subs.append(Sub(
        game.ship.x + 10, game.ship.y, 60, 0, "diesel_alt", game.rng_world,
        runtime_catalog=game.runtime_catalog, asw_rng=game.rng_asw))
    state = game.save_state()
    row = next(item for item in state["subs"] if item["stype"] == "diesel_alt")
    mutation(row["endurance"])
    live_ship = game.ship
    live_catalog = game.runtime_catalog
    assert not game._load_save_data(state)
    assert game.ship is live_ship
    assert game.runtime_catalog is live_catalog
