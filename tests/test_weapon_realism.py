"""Focused tests for weapon observation boundaries and tactical symbols."""

from types import SimpleNamespace

import pygame
import pytest

from src.air.helicopter import Helicopter
from src.ui import nato_symbols
from src.weapons.torpedo import Torpedo


def target(x, y, depth=50.0, **extra):
    values = dict(x=x, y=y, depth=depth, sunk=False, state="PATROL",
                  hit=lambda: None)
    values.update(extra)
    return SimpleNamespace(**values)


def test_submarine_and_torpedo_have_distinct_underwater_domains_and_symbols():
    assert nato_symbols.domain_for_kind("SUB") == "SUBSURFACE"
    assert nato_symbols.domain_for_kind("torp") == "UNDERWATER_WEAPON"
    images = []
    for domain in ("SUBSURFACE", "UNDERWATER_WEAPON"):
        surface = pygame.Surface((40, 40))
        surface.fill((0, 0, 0))
        nato_symbols.draw_symbol(surface, (20, 20), "FRIEND", domain)
        images.append(pygame.image.tobytes(surface, "RGB"))
    assert images[0] != images[1]


def test_preterminal_guidance_uses_commanded_datum_not_hidden_target():
    hidden = target(0.2, 0.0)
    torpedo = Torpedo(0.0, 0.0, 0.0, 50.0, hidden, 1,
                      guidance_x=0.0, guidance_y=-8.0)
    torpedo.update(0.1)
    assert torpedo.seeker_acquired is False
    assert torpedo.course == pytest.approx(0.0, abs=1.0)


def test_wire_updates_have_cadence_staleness_and_persistable_break_state():
    torpedo = Torpedo(0.0, 0.0, 0.0, 50.0, None, 1,
                      guidance_x=0.0, guidance_y=-8.0)
    assert torpedo.wire_update(-8.0, 0.0) is True
    assert torpedo.wire_update(8.0, 0.0) is False
    torpedo.update(torpedo.WIRE_UPDATE_CADENCE_S)
    assert torpedo.wire_update(8.0, 0.0) is True
    torpedo.update(torpedo.WIRE_STALE_S)
    assert torpedo.wire_state == "STALE"
    torpedo.break_wire()
    assert torpedo.wire_state == "BROKEN"
    assert torpedo.wire_update(0.0, -2.0) is False


def test_seeker_candidate_api_can_select_a_decoy():
    submarine = target(0.9, 0.0)
    decoy = target(0.3, 0.0, kind="decoy", dead=False)
    torpedo = Torpedo(0.0, 0.0, 90.0, 50.0, submarine, 1,
                      guidance_x=0.0, guidance_y=0.0)
    assert torpedo.evaluate_seeker_candidates([submarine, decoy]) is decoy
    torpedo.update(0.1, seeker_candidates=[submarine, decoy])
    assert torpedo.seeker_acquired is True
    assert torpedo._seeker_target is decoy


def test_helicopter_release_datum_uses_ship_observation_origin():
    helicopter = Helicopter(None)
    helicopter.x, helicopter.y = 13.0, 8.0
    ship = SimpleNamespace(x=10.0, y=10.0)
    datum = helicopter.release_datum_from_ship_observation(
        ship, 90.0, 5.0, bearing_uncertainty_deg=2.5,
        range_uncertainty_nm=0.8)
    assert datum.x_nm == pytest.approx(15.0)
    assert datum.y_nm == pytest.approx(10.0)
    assert datum.course_deg == pytest.approx(135.0)
    assert datum.range_nm == pytest.approx(2.0 ** 0.5 * 2.0)
    assert datum.bearing_uncertainty_deg == 2.5
    assert datum.range_uncertainty_nm == 0.8
