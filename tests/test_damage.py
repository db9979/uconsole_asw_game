"""Gezielte Tests fuer das Schadens- und Reparaturmodell."""

import random

import pytest

from src.core import config
from src.ship.damage import CAPSIZE_HEEL_DEG, HIT_HOLE_M2, TEAM_HOP_S, Compartment, DamageModel


class FixedRng:
    def random(self):
        return 0.0

    def uniform(self, low, high):
        return low

    def choice(self, values):
        return values[0]


def test_repeated_hit_never_reduces_existing_damage(monkeypatch):
    monkeypatch.setattr(config, "DMG_FIRE_START_CHANCE", 1.0)
    compartment = Compartment("sonar", "Sonarzentrale")
    compartment.state = "FLUTEND"
    compartment.flood = 55.0
    compartment.fire = 60.0

    compartment.hit(FixedRng())

    assert compartment.flood == 55.0
    assert compartment.fire == 60.0


def test_repeated_hit_does_not_revive_destroyed_compartment():
    compartment = Compartment("engine", "Maschinerie")
    compartment.state = "ZERSTOERT"
    compartment.flood = config.DMG_DESTROY_FLOOD

    compartment.hit(FixedRng())

    assert compartment.state == "ZERSTOERT"
    assert compartment.flood == config.DMG_DESTROY_FLOOD


def _arrive(model):
    for team in model.team_eta:
        model.team_eta[team] = 0.0


def test_repair_is_applied_before_flood_destruction():
    model = DamageModel(random.Random(3))
    compartment = model.compartments["engine"]
    compartment.state = "FLUTEND"
    compartment.flood = config.DMG_DESTROY_FLOOD - 1.0
    compartment.hole_m2 = HIT_HOLE_M2
    model.patch_kits = 0
    model.assign_team(1, "engine")
    _arrive(model)
    trend = model.compartment_trend("engine")["flood_rate"]

    model.update(1.0)

    assert compartment.state == "FLUTEND"
    assert compartment.flood == pytest.approx(
        config.DMG_DESTROY_FLOOD - 1.0 + trend, rel=1e-6)


def test_fire_growth_and_suppression_are_net_before_destruction():
    model = DamageModel(random.Random(3))
    compartment = model.compartments["engine"]
    compartment.fire = config.DMG_FIRE_KILL - 5.0
    compartment.state = "BESCHAEDIGT"
    model.assign_team(1, "engine")
    _arrive(model)
    growth = config.DMG_FIRE_RATE * compartment.geometry["fuel"]

    model.update(1.0)

    assert compartment.state != "ZERSTOERT"
    assert compartment.fire == pytest.approx(
        config.DMG_FIRE_KILL - 5.0 + growth - config.DMG_FIRE_REPAIR_RATE)


def test_fire_only_spreads_to_explicit_neighbors(monkeypatch):
    monkeypatch.setattr(config, "DMG_FIRE_SPREAD_PPS", 1.0)
    model = DamageModel(FixedRng())
    model.compartments["bridge"].fire = 20.0
    model.compartments["sonar"].state = "ZERSTOERT"

    model.update(1.0)

    assert all(c.fire == 0.0 for key, c in model.compartments.items()
               if key not in ("bridge", "sonar"))


def test_multiple_teams_can_share_a_repairable_compartment():
    model = DamageModel(random.Random(1))
    model.compartments["engine"].state = "BESCHAEDIGT"
    model.compartments["engine"].flood = 20.0

    assert model.assign_team(1, "engine") is True
    assert model.assign_team(2, "engine") is True
    # Teams walk from damage control: working only after the transit.
    assert model.teams_on("engine") == []
    assert model.team_eta[1] == pytest.approx(2 * TEAM_HOP_S)
    model.update(2 * TEAM_HOP_S)
    assert model.teams_on("engine") == [1, 2]


def test_fully_repaired_compartment_releases_all_teams():
    model = DamageModel(random.Random(1))
    compartment = model.compartments["engine"]
    compartment.state = "BESCHAEDIGT"
    compartment.flood = 1.0
    model.assign_team(1, "engine")
    model.assign_team(2, "engine")
    _arrive(model)

    model.update(7.0)

    assert compartment.state == "OK"
    assert compartment.flood == 0.0
    assert model.teams[1] is None
    assert model.teams[2] is None


def test_list_deg_reflects_flood_asymmetry_and_is_bounded():
    model = DamageModel(random.Random(1))
    assert model.list_deg() == 0.0

    model.compartments["hull_right"].flood = 20.0
    starboard = model.list_deg()
    # Off-centre floodwater moment over displacement x effective GM.
    assert 1.0 < starboard < 6.0

    model.compartments["hull_left"].flood = 20.0
    assert model.list_deg() == pytest.approx(0.0, abs=1e-9)

    model.compartments["hull_left"].flood = 0.0
    model.compartments["hull_right"].flood = 1000.0
    assert model.list_deg() == CAPSIZE_HEEL_DEG  # clamped at downflooding

    model.compartments["hull_right"].flood = 0.0
    model.compartments["hull_left"].flood = 1000.0
    assert model.list_deg() == -CAPSIZE_HEEL_DEG


