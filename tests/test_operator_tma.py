"""Operator TMA: hypothesis, residuals and explicit acceptance."""

import math
import random
from dataclasses import replace

import pytest

from src.core import config
from src.core.game import Game
from src.sonar import tma_operator
from src.sonar.sonar import Contact
from src.sonar.tma import BearingTrack


def _track(manoeuvre=True, noise=0.5, seed=3):
    """Own ship on two legs (or one), target on a straight line."""
    rng = random.Random(seed)
    track = BearingTrack()
    own_x, own_y, target = 100.0, 100.0, (106.0, 92.0)
    t_course, t_speed = 250.0, 10.0
    for step in range(120):
        t = step * 5.0
        own_course = 30.0 if (step < 60 or not manoeuvre) else 100.0
        own_x += config.kn_to_nm_per_s(12.0) * 5.0 * math.sin(math.radians(own_course))
        own_y -= config.kn_to_nm_per_s(12.0) * 5.0 * math.cos(math.radians(own_course))
        tx = target[0] + config.kn_to_nm_per_s(t_speed) * t * math.sin(math.radians(t_course))
        ty = target[1] - config.kn_to_nm_per_s(t_speed) * t * math.cos(math.radians(t_course))
        bearing = math.degrees(math.atan2(tx - own_x, -(ty - own_y))) % 360.0
        track.add(t, bearing + rng.gauss(0.0, noise), own_x, own_y, own_course,
                  uncertainty_deg=noise)
    ref = track.pts[-1]
    tx = target[0] + config.kn_to_nm_per_s(t_speed) * ref.t * math.sin(math.radians(t_course))
    ty = target[1] - config.kn_to_nm_per_s(t_speed) * ref.t * math.cos(math.radians(t_course))
    truth = tma_operator.Hypothesis(t_course, t_speed, math.hypot(tx - ref.fx, ty - ref.fy))
    return track, truth


def test_residual_fit_separates_the_true_motion_from_wrong_hypotheses():
    track, truth = _track()
    good = tma_operator.evaluate(track.pts, truth)
    assert good["fit"] > .7 and good["observability"] == 1.0
    for wrong in (replace(truth, course=truth.course + 25.0),
                  replace(truth, range_nm=truth.range_nm * 1.6),
                  replace(truth, speed_kn=truth.speed_kn + 6.0)):
        assert tma_operator.evaluate(track.pts, wrong)["fit"] < .1


def test_without_own_manoeuvre_the_range_is_unobservable():
    track, truth = _track(manoeuvre=False)
    assert tma_operator.evaluate(track.pts, truth)["observability"] < .5


@pytest.fixture
def game():
    value = Game(seed=7070, start_menu=False, audio_enabled=False)
    value.sonar.contacts.clear()
    return value


def _install(game, track):
    contact = Contact(5, 999, "passiv", "sub")
    contact._fx, contact._fy = track.pts[-1].fx, track.pts[-1].fy
    game.sonar.contacts[999] = contact
    game.sonar._tracks[999] = track
    game.selected_contact = contact
    game.sim_t = track.pts[-1].t
    return contact


def test_accept_writes_a_dead_reckoned_fix_only_on_request(game):
    track, truth = _track()
    contact = _install(game, track)
    assert contact.range_source is None
    assert game.set_tma_hypothesis(contact, truth.course, truth.speed_kn,
                                   truth.range_nm) is True
    assert contact.range_source is None          # a hypothesis is not a fix
    assert game.accept_tma(contact) is True
    assert contact.range_source == "tma" and contact.tma_quality > 0
    start = (contact.observed_x, contact.observed_y)
    contact.update_passive(contact.bearing, 1.0, .8, "", game.sim_t + 60.0)
    moved = math.hypot(contact.observed_x - start[0], contact.observed_y - start[1])
    assert moved == pytest.approx(config.kn_to_nm_per_s(truth.speed_kn) * 60.0, rel=1e-6)


def test_accept_rejects_trends_and_unobservable_tracks(game):
    track, truth = _track()
    contact = _install(game, track)
    game.set_tma_hypothesis(contact, truth.course + 40.0, truth.speed_kn, truth.range_nm)
    assert game.accept_tma(contact) == "poor_fit"
    flat, flat_truth = _track(manoeuvre=False)
    contact = _install(game, flat)
    game.set_tma_hypothesis(contact, flat_truth.course, flat_truth.speed_kn,
                            flat_truth.range_nm)
    assert game.accept_tma(contact) == "unobservable"
    assert contact.range_source is None


def test_solver_proposal_is_training_only(game):
    track, truth = _track()
    contact = _install(game, track)
    game.sonar._update_tma(type("T", (), {"id": 999})(), game.sim_t + 1.0)
    assert contact.range_source is None           # solver never writes a fix
    assert game.copy_tma_proposal(contact) == "not_available"
    game.preferences = replace(game.preferences, operator_assist="training")
    if game.sonar.tma_proposals.get(999) is not None:
        assert game.copy_tma_proposal(contact) is True
