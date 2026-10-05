"""The crewed submarine's winning outcomes agree everywhere (end panel,
campaign, logbook points, PvP)."""

from types import SimpleNamespace

from src.core import boat_campaign, logbook, mission_modes
from src.ui import uboot_view


def test_end_panel_wins_match_campaign_wins():
    panel = {key.removeprefix("uboot.end.") for key in uboot_view._END_WINS}
    # A finished boat lesson is shown green but is no campaign victory.
    assert panel - {"trained"} == set(boat_campaign.WINS)


def test_every_win_scores_points_and_every_loss_none():
    for outcome in boat_campaign.WINS:
        assert logbook.BOAT_OUTCOME_POINTS.get(outcome, 0) > 0, outcome
        assert logbook.boat_score(outcome, 0.0, 0, "standard") > 0
    assert set(logbook.BOAT_OUTCOME_POINTS) == set(boat_campaign.WINS)
    for outcome in ("lost", "over", "trained"):
        assert logbook.boat_score(outcome, 0.0, 0, "standard") == 0


def test_mission_mode_outcomes_are_wins():
    for key in ("end.reason.boat_home", "end.reason.agents_escaped",
                "end.reason.elint_reported", "end.reason.trail_lost",
                "end.reason.trail_short"):
        assert mission_modes.outcome(None, key) in boat_campaign.WINS


def test_scenario_13_and_18_to_20_wins_score():
    assert logbook.boat_score("home", 0.0, 0, "standard") == 1500
    assert logbook.boat_score("picked_up", 0.0, 0, "standard") == 1600
    assert logbook.boat_score("elint", 0.0, 0, "standard") == 1500
    assert logbook.boat_score("shaken", 0.0, 0, "standard") == 1300


def test_versus_outcome_counts_home_as_boat_win(monkeypatch):
    from src.core import boat_debrief, game_lobby
    monkeypatch.setattr(boat_debrief, "outcome", lambda game, boat: "home")
    game = SimpleNamespace(versus_round=True, game_over=True, _opfor=object(),
                           mission_result="VERLOREN")
    mixin = next(cls for cls in vars(game_lobby).values()
                 if isinstance(cls, type) and hasattr(cls, "versus_outcome"))
    assert mixin.versus_outcome(game) == (False, True)
