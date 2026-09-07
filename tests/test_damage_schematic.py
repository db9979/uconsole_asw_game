"""Fictional deck-plan geometry and truthful damage-control trends."""

import random
from types import SimpleNamespace as NS

import pygame
import pytest

from src.core import config
from src.core.i18n import Translator
from src.core.station import Station
from src.ship.damage import COMPARTMENTS, DamageModel
from src.ui import layout, stations_view


@pytest.mark.parametrize("large", [False, True])
@pytest.mark.parametrize("width", [640, 1280])
def test_polygons_and_callouts_share_selection_and_tooltip(monkeypatch, large, width):
    monkeypatch.setattr(config, "STATION_RECT", (1280 - width, 30, width, 510))
    game = NS(damage=DamageModel(random.Random(7)), preferences=NS(large_text=large),
              station=Station.DAMAGE, dmg_cursor=0, dmg_team=1)
    geometry = stations_view.damage_regions(game)
    assert list(geometry["compartments"]) == [key for key, _ in COMPARTMENTS]
    assert not geometry["schematic"].colliderect(geometry["detail"])
    for key, region in geometry["compartments"].items():
        assert geometry["schematic"].contains(region["callout"])
        assert all(geometry["schematic"].collidepoint(p) for p in region["polygon"])
        for point in (region["anchor"], region["callout"].center):
            assert stations_view.damage_compartment_at(game, point) == key
            assert stations_view.station_hit_target(game, point)["id"] == f"damage:{key}"
    for point in (None, (-1, -1), (1280, 100), geometry["detail"].center,
                  geometry["footer"].center, geometry["schematic"].topleft):
        assert stations_view.damage_compartment_at(game, point) is None
    assert game.dmg_cursor == 0 and game.damage.teams == {1: None, 2: None, 3: None}


@pytest.mark.parametrize("mult", [.5, 1.0, 1.5])
@pytest.mark.parametrize("teams", [0, 1, 2, 3])
@pytest.mark.parametrize("state", ["FLUTEND", "BESCHAEDIGT"])
def test_net_trends_match_simulation_and_diminishing_teams(monkeypatch, mult, teams, state):
    monkeypatch.setattr(config, "DMG_FIRE_SPREAD_PPS", 0.0)
    model = DamageModel(random.Random(7), repair_mult=mult)
    room = model.compartments["engine"]
    room.state, room.flood, room.fire = state, 60.0, 40.0
    for team in range(1, teams + 1):
        model.assign_team(team, "engine")
    before_rng = model.rng.getstate()
    trend = model.compartment_trend("engine")
    assert trend["repairable"]
    assert model.rng.getstate() == before_rng
    assert (room.state, room.flood, room.fire) == (state, 60.0, 40.0)
    removal = config.DMG_REPAIR_RATE * mult * (1 + .6 * (teams - 1)) if teams else 0
    assert model.repair_rates("engine")[0] == pytest.approx(removal)
    model.update(.01)
    assert (room.flood - 60.0) / .01 == pytest.approx(trend["flood_rate"])
    assert (room.fire - 40.0) / .01 == pytest.approx(trend["fire_rate"])


def test_destroyed_empty_and_sunk_compartments_do_not_claim_falling():
    model = DamageModel(random.Random(7))
    room = model.compartments["engine"]
    model.teams = {1: "engine", 2: "engine", 3: "engine"}
    assert model.compartment_trend("engine")["flood_rate"] == 0
    assert model.compartment_trend("engine")["fire_rate"] == 0
    room.state, room.flood, room.fire = "ZERSTOERT", 100.0, 100.0
    assert model.compartment_trend("engine") == {
        "flood_rate": 0.0, "fire_rate": 0.0, "repairable": False}
    room.state = "FLUTEND"
    model.ship_sunk = True
    assert not model.compartment_trend("engine")["repairable"]
    assert model.compartment_trend("engine")["flood_rate"] == 0


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("large", [False, True])
def test_schematic_readable_markers_detail_and_localized_destination(monkeypatch, language, large):
    monkeypatch.setattr(config, "STATION_RECT", (0, 30, 1280, 510))
    model = DamageModel(random.Random(7))
    room = model.compartments["engine"]
    room.state, room.flood, room.fire = "ZERSTOERT", 100.0, 70.0
    model.teams[1] = "engine"
    game = NS(screen=pygame.Surface((1280, 720)), damage=model,
              preferences=NS(large_text=large), station=Station.DAMAGE,
              dmg_cursor=list(model.compartments).index("engine"), dmg_team=1)
    translator = Translator(language)
    with layout.capture_text() as text:
        stations_view.draw_damage_view(game, tr=translator.t)
    geometry = stations_view.damage_regions(game)
    rendered = "\n".join(item["text"] for item in text)
    assert "X ~ ^ T1" in rendered
    assert translator.t("damage.unrepairable") in rendered
    assert translator.t("damage.falling") not in rendered
    assert "Team 1: " + translator.t("compartment.engine") in rendered
    assert "..." not in rendered
    assert all(item["bounds"].contains(item["rect"]) for item in text), text
    assert all(geometry["station"].contains(item["rect"]) for item in text)
    game.tr = translator.t
    payload = stations_view.station_hit_target(game, geometry["detail"].center)
    assert translator.t("compartment.engine") in "\n".join(payload["lines"])
