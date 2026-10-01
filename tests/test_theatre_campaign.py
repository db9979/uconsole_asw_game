"""The theatre campaign ("Feldzug"): situation, hotspots, outcomes and its files."""

import json
from dataclasses import replace

import pygame
import pytest

from src.core import boat_campaign, campaign as campaign_model, config, theatre
from src.core.boat_campaign import BoatCampaignState
from src.core.campaign import CampaignState
from src.core.game import Game
from src.core.i18n import localize
from src.core.theatre import Theatre
from src.ui import layout, pointer


def _menu_game(seed=11, language="en"):
    return Game(seed=seed, start_menu=True, audio_enabled=False, language=language)


def _key(game, key):
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _theatre_at(side, lage, seed=4242):
    front = Theatre(side, seed)
    front.lage = lage
    front.hotspots = []
    front.refill()
    return front


def _play(front, role=None, won=True, enemy_sunk=0, sunk=False, relieved=False):
    spot = next(spot for spot in front.ordered()
                if role is None or front.role(spot) == role)
    assert front.resolve(spot["id"], won=won, enemy_sunk=enemy_sunk, sunk=sunk,
                         relieved=relieved)
    return spot


# --- hotspots ---------------------------------------------------------------------

def test_every_built_in_scenario_of_a_side_is_a_hotspot_but_the_free_hunt():
    # The free patrol has no victory, so it is never a hotspot.
    frigate = set(config.scenarios_for_side("frigate")) - {"s4_zufall", "frei_fregatte"}
    assert set(theatre.SCENARIO_ROLES["frigate"]) == frigate
    assert (set(theatre.SCENARIO_ROLES["boat"])
            == set(config.scenarios_for_side("uboot")) - {"frei_uboot"})
    for roles in theatre.SCENARIO_ROLES.values():
        assert set(roles.values()) == set(theatre.ROLES)
        assert list(roles.values()).count("decisive") == 1


@pytest.mark.parametrize("side", theatre.SIDES)
def test_hotspots_are_deterministic_on_water_and_apart(side):
    for seed in (7, 1234, 99_999):
        first, again = Theatre(side, seed), Theatre(side, seed)
        assert first.serialize() == again.serialize()
        spots = first.ordered()
        assert len(spots) == theatre.OPEN_REGULAR
        assert sorted(first.role(spot) for spot in spots) == sorted(theatre.BANDS[1])
        assert len({spot["scenario"] for spot in spots}) == len(spots)
        lands = theatre._landmasses(seed % 128)
        for spot in spots:
            assert theatre.MAP_MARGIN_NM <= spot["x"] <= theatre.MAP_NM - theatre.MAP_MARGIN_NM
            assert theatre.MAP_MARGIN_NM <= spot["y"] <= theatre.MAP_NM - theatre.MAP_MARGIN_NM
            assert not theatre._on_land(lands, spot["x"], spot["y"])
        assert len({first.name(spot) for spot in spots}) == len(spots)
    assert Theatre(side, 7).serialize() != Theatre(side, 8).serialize()


def test_the_situation_band_decides_which_hotspots_open():
    assert sorted(_theatre_at("frigate", 20).role(s) for s in
                  _theatre_at("frigate", 20).hotspots) == ["defence", "defence", "patrol"]
    high = _theatre_at("frigate", 70)
    assert sorted(high.role(s) for s in high.hotspots) == ["patrol", "strike", "strike"]
    assert not any(high.role(s) == "decisive" for s in high.hotspots)
    top = _theatre_at("boat", theatre.DECISIVE_LAGE)
    decisive = [s for s in top.hotspots if top.role(s) == "decisive"]
    assert [s["scenario"] for s in decisive] == ["s17_duell"]
    # A defeat below the threshold closes the decisive hotspot again.
    _play(top, role="patrol", won=False)
    assert top.lage < theatre.DECISIVE_LAGE
    assert not any(top.role(s) == "decisive" for s in top.hotspots)


def test_results_move_the_situation_and_branch_the_next_hotspots():
    front = Theatre("frigate", 4242)
    played = _play(front, role="strike", won=True, enemy_sunk=2)
    assert front.lage == 50 + 12 and front.enemy == theatre.ENEMY_START - 2
    assert front.missions == 1 and front.hotspot(played["id"]) is None
    assert len(front.hotspots) == theatre.OPEN_REGULAR
    assert played["scenario"] not in {s["scenario"] for s in front.hotspots}
    lost = Theatre("frigate", 4242)
    _play(lost, role="defence", won=False)
    assert lost.lage == 50 - 12 and lost.losses == 1
    # Different results, different open hotspots.
    assert ({s["scenario"] for s in front.hotspots}
            != {s["scenario"] for s in lost.hotspots})


def test_an_ignored_defence_hotspot_closes_as_a_loss():
    front = _theatre_at("frigate", 20)
    waiting = next(s for s in front.ordered() if front.role(s) == "defence")
    for _ in range(theatre.EXPIRE_AFTER):
        spot = next(s for s in front.ordered() if s["id"] != waiting["id"])
        front.resolve(spot["id"], won=True, enemy_sunk=0, sunk=False)
    assert front.hotspot(waiting["id"]) is None
    assert front.losses == 1
    assert front.lage == 20 + 3 * 8 + theatre.EXPIRED_DEFENCE_LAGE


@pytest.mark.parametrize("setup,play,outcome", [
    (dict(lage=80), dict(role="decisive", won=True), "victory"),
    (dict(enemy=1), dict(won=True, enemy_sunk=1), "cleared"),
    (dict(lage=95), dict(role="strike", won=True), "supremacy"),
    (dict(lage=5), dict(role="defence", won=False), "defeat"),
    (dict(lage=50, losses=3), dict(role="defence", won=False), "overrun"),
    (dict(), dict(won=False, relieved=True), "relieved"),
    (dict(missions=theatre.MISSIONS_MAX - 1), dict(won=True), "stalemate"),
    (dict(lage=80), dict(role="decisive", won=True, sunk=True), "sunk"),
])
def test_the_campaign_ends_by_the_situation(setup, play, outcome):
    front = _theatre_at("frigate", setup.get("lage", 50) if "lage" in setup else 30)
    for key, value in setup.items():
        setattr(front, key, value)
    front.hotspots = []
    front.refill()
    _play(front, **play)
    assert front.outcome == outcome and front.hotspots == []
    assert not front.resolve(0, won=True, enemy_sunk=0, sunk=False)
    expected = ("won" if outcome in ("victory", "cleared", "supremacy") else
                "draw" if outcome == "stalemate" else "lost")
    assert theatre.status_of(outcome) == expected


def test_a_whole_campaign_is_deterministic():
    def run():
        state = CampaignState(31337)
        step = 0
        while state.status == "active":
            spot = state.theatre.ordered()[step % len(state.theatre.hotspots)]
            won = step % 3 != 2
            state.record(spot["id"], won=won, ship_sunk=False, score=step,
                         torpedoes_left=4, damaged=[], helo_lost=False, incident=False,
                         tasks_done=0, tasks_failed=0, enemy_sunk=int(won))
            state.call_at_port("refit" if step % 2 else "quick")
            step += 1
        return state.serialize()

    first = run()
    assert first == run() and first["status"] in ("won", "lost", "draw")
    assert len(first["history"]) <= theatre.MISSIONS_MAX


# --- files ------------------------------------------------------------------------

def test_both_files_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    frigate, boat = CampaignState(500), BoatCampaignState(501)
    frigate.record(frigate.theatre.ordered()[1]["id"], won=True, ship_sunk=False, score=7,
                   torpedoes_left=5, damaged=["sonar"], helo_lost=True, incident=False,
                   tasks_done=0, tasks_failed=0, enemy_sunk=1)
    boat.record(boat.theatre.ordered()[2]["id"], won=False, boat_sunk=False,
                torpedoes_left=2, damage=12.0)
    assert campaign_model.save_campaign(frigate) and boat_campaign.save_campaign(boat)
    assert campaign_model.load_campaign().serialize() == frigate.serialize()
    assert boat_campaign.load_campaign().serialize() == boat.serialize()
    assert json.loads((tmp_path / campaign_model.FILE_NAME).read_text())["version"] == 2


def _v1_frigate(**changes):
    state = dict(version=1, base_seed=1234, leg=2, reputation=62, torpedoes=4,
                 damaged=["engine"], helo_lost=True, status="active", port=True,
                 history=[dict(leg=0, result="won", score=900),
                          dict(leg=1, result="won", score=300),
                          dict(leg=2, result="lost", score=-50)])
    state.update(changes)
    return state


def test_a_version_1_campaign_in_progress_is_migrated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    old = _v1_frigate()
    frozen = json.dumps(old, sort_keys=True)
    lifted = campaign_model.migrate_v1(old)
    assert json.dumps(old, sort_keys=True) == frozen          # pure
    assert CampaignState.valid_state(lifted)
    (tmp_path / campaign_model.FILE_NAME).write_text(json.dumps(old))
    state = campaign_model.load_campaign()
    assert state is not None and state.port and state.status == "active"
    assert (state.reputation, state.torpedoes, state.damaged, state.helo_lost) == (
        62, 4, ["engine"], True)
    assert [row["scenario"] for row in state.history] == [
        "s1_patrouille", "s2_doppeljagd", "s1_patrouille"]
    assert state.theatre.lage == 50 + 8 + 8 - 8 and state.theatre.enemy == 4
    assert state.missions == 3 and len(state.theatre.hotspots) == theatre.OPEN_REGULAR
    assert state.mission_seed() % 128 == 1234 % 128
    assert state.call_at_port("refit") and state.can_sail()


def test_finished_version_1_campaigns_keep_their_result():
    won = _v1_frigate(leg=5, port=False, status="won",
                      history=[dict(leg=n, result="won", score=1) for n in range(6)])
    assert CampaignState.restore(won).outcome == "victory"
    lost = _v1_frigate(leg=1, port=False, status="lost",
                       history=[dict(leg=0, result="won", score=1),
                                dict(leg=1, result="sunk", score=0)])
    assert CampaignState.restore(lost).outcome == "sunk"
    boat = dict(version=1, base_seed=77, leg=1, reputation=40, torpedoes=None, damage=20,
                status="active", port=False, history=[dict(leg=0, result="lost")])
    state = BoatCampaignState.restore(boat)
    assert state.can_sail() and state.damage == 20 and state.torpedoes is None
    assert state.history == [dict(scenario="s6_aufklaerung", result="lost")]
    assert state.theatre.lage == 42


@pytest.mark.parametrize("change", [
    lambda s: s.update(version=3),
    lambda s: s.update(reputation=True),
    lambda s: s.update(torpedoes=4.0),
    lambda s: s.update(extra=1),
    lambda s: s["theatre"].update(lage=101),
    lambda s: s["theatre"].update(lage=float("nan")),
    lambda s: s["theatre"].update(outcome="victory"),            # status still active
    lambda s: s["theatre"].update(missions=5),                   # history disagrees
    lambda s: s["theatre"]["hotspots"][0].update(x=900),
    lambda s: s["theatre"]["hotspots"][0].update(y=-1),
    lambda s: s["theatre"]["hotspots"][0].update(scenario="s5_durchbruch"),  # boat's
    lambda s: s["theatre"]["hotspots"][0].update(scenario="../../etc/passwd"),
    lambda s: s["theatre"]["hotspots"][1].update(
        scenario=s["theatre"]["hotspots"][0]["scenario"]),
    lambda s: s["theatre"]["hotspots"][0].update(id=999),
    lambda s: s["theatre"]["hotspots"][0].update(age=theatre.EXPIRE_AFTER),
    lambda s: s["theatre"]["hotspots"].extend([{}] * 5),
    lambda s: s["theatre"].update(hotspots=[]),
    lambda s: s["history"].append(dict(scenario="s1_patrouille", result="won", score=1)),
    lambda s: s.update(history=[[]]),
    lambda s: s.update(status="won"),
])
def test_hostile_campaign_files_are_rejected(change):
    state = json.loads(json.dumps(CampaignState(9).serialize()))
    change(state)
    assert not CampaignState.valid_state(state)
    with pytest.raises(ValueError):
        CampaignState.restore(state)


def test_broken_files_load_as_no_campaign(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    path = tmp_path / campaign_model.FILE_NAME
    for text in ('{"version": Infinity}', "[" * 100_000, "{", json.dumps([1, 2]),
                 json.dumps(_v1_frigate(leg=9)), json.dumps(dict(version=1)),
                 " " * (campaign_model.FILE_BYTES_MAX + 1)):
        path.write_text(text)
        assert campaign_model.load_campaign() is None
    path.write_text(json.dumps(_v1_frigate()))
    boat_path = tmp_path / boat_campaign.FILE_NAME
    boat_path.write_text(json.dumps(_v1_frigate()))       # a frigate file as the boat's
    assert boat_campaign.load_campaign() is None
    assert campaign_model.load_campaign() is not None


# --- the screen ---------------------------------------------------------------------

def _texts(game):
    with layout.capture_text() as rendered:
        game.draw()
    return rendered


@pytest.mark.parametrize("language", ("en", "de"))
def test_the_campaign_screen_draws_map_briefing_and_summary(tmp_path, monkeypatch,
                                                           language):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path))
    game = _menu_game(seed=600, language=language)
    game.preferences = replace(game.preferences, language=language)
    layout.configure_for(game)
    game.main_menu_sel = game.main_menu_index("campaign")
    _key(game, pygame.K_RETURN)
    for side_key in (None, pygame.K_TAB):
        if side_key is not None:
            _key(game, side_key)
        _key(game, pygame.K_n)
        state = game._menu_campaign()
        for world in ("procedural", "fixed"):
            game.world_mode = world
            rendered = _texts(game)
            screen = pygame.Rect(0, 0, config.SCREEN_W, config.SCREEN_H)
            assert all(screen.contains(item["rect"]) for item in rendered)
            names = [state.theatre.name(spot) for spot in state.theatre.ordered()]
            assert all(any(name in item["text"] for item in rendered) for name in names)
        # The rows take clicks: one selects, the second opens the briefing.
        game.draw()
        rows = [t for t in pointer.targets() if t.action is not None
                and t.rect.x < 500 and t.rect.w > 600]
        assert len(rows) == theatre.OPEN_REGULAR
        rows[2].action(rows[2].rect.center)
        assert game.campaign_hotspot_sel == 2
        game.draw()
        row = [t for t in pointer.targets() if t.action is not None
               and t.rect.x < 500 and t.rect.w > 600][2]
        row.action(row.rect.center)
        assert game._campaign_briefing == state.theatre.ordered()[2]["id"]
        rendered = _texts(game)
        spot = state.theatre.ordered()[2]
        brief = game.tr("scenario." + config.SCENARIO_NAMES[spot["scenario"]] + ".brief")
        stakes = localize(game._stakes_text(state.theatre, spot), game.tr)
        texts = " ".join(item["text"] for item in rendered)
        assert stakes in texts and brief.split()[1] in texts
        _key(game, pygame.K_ESCAPE)
        assert game._campaign_briefing is None and game.menu_screen == "campaign"
        # A finished campaign shows its outcome.
        state.theatre.outcome, state.theatre.hotspots = "overrun", []
        state.status = "lost"
        rendered = _texts(game)
        outcome = game.tr("campaign.outcome.overrun")
        assert any(outcome in item["text"] for item in rendered)
        _key(game, pygame.K_RETURN)                      # nothing to sail to
        assert not game.campaign_mission
