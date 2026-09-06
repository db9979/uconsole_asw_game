"""Gezielte Tests fuer das Schadens- und Reparaturmodell."""

import random

import pytest

from src.core import config
from src.ship.damage import Compartment, DamageModel


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


def test_repair_is_applied_before_flood_destruction():
    compartment = Compartment("engine", "Maschinerie")
    compartment.state = "FLUTEND"
    compartment.flood = config.DMG_DESTROY_FLOOD - 1.0

    compartment.update(1.0, repaired=True)

    assert compartment.state == "FLUTEND"
    assert compartment.flood == pytest.approx(
        config.DMG_DESTROY_FLOOD - 1.0
        + config.DMG_FLOOD_RATE - config.DMG_REPAIR_RATE)


def test_fire_growth_and_suppression_are_net_before_destruction():
    compartment = Compartment("weapons", "Waffenzentrale")
    compartment.fire = config.DMG_FIRE_KILL - 1.0

    compartment.update(1.0, repaired=True, fire_teams=1)

    assert compartment.state == "OK"
    assert compartment.fire == pytest.approx(
        config.DMG_FIRE_KILL - 1.0
        + config.DMG_FIRE_RATE - config.DMG_FIRE_REPAIR_RATE)


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
    assert model.teams_on("engine") == [1, 2]


def test_fully_repaired_compartment_releases_all_teams():
    model = DamageModel(random.Random(1))
    compartment = model.compartments["engine"]
    compartment.state = "BESCHAEDIGT"
    compartment.flood = 1.0
    model.assign_team(1, "engine")
    model.assign_team(2, "engine")

    model.update(7.0)

    assert compartment.state == "OK"
    assert compartment.flood == 0.0
    assert model.teams[1] is None
    assert model.teams[2] is None
