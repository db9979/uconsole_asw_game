"""Bridge lookout: visual class/type recognition and 'Bridge lookout' reports."""

import copy
import json
import math
import random

import pytest

from src.air.flights import Flight
from src.air.live_aircraft import LiveAircraft
from src.core import config
from src.core.game import Game
from src.core.i18n import localize
from src.enemies.surface import SurfaceShip
from src.sensors import lookout_id
from src.ui.stations_view import _track_tooltip
from test_opz_picture_inputs import clean_game


def ship(game, key, distance):
    actor = SurfaceShip(
        game.ship.x + distance, game.ship.y, random.Random(41),
        profile=game.runtime_catalog.surfaces[key],
        runtime_catalog=game.runtime_catalog)
    actor.speed = actor.target_speed = 0.0
    return actor


def visual_labels(game):
    game._update_air_picture(full_scan=True)
    return [track.label for track in game.air_picture.tracks(game.sim_t)
            if track.source == "LOOKOUT"]


def approach(game, actor, start, stop, step=0.1):
    distance = start
    while distance >= stop:
        actor.x = game.ship.x + distance
        game._update_air_picture(full_scan=True)
        game.sim_t += 1.0
        distance -= step


@pytest.fixture
def game(monkeypatch):
    current = clean_game()
    monkeypatch.setattr(current.world, "land_blocks_line", lambda *args: False)
    monkeypatch.setattr(current, "_update_lookout_land", lambda: None)
    yield current
    current.audio.shutdown()


def test_every_catalog_profile_has_a_visual_class():
    from src.data.catalog import CATALOG
    for profile in CATALOG.surfaces.values():
        recognized, identified, type_key = lookout_id.surface_classes(profile)
        assert recognized in lookout_id.CLASS_SIZE and identified in lookout_id.CLASS_SIZE
        assert type_key is None or type_key in lookout_id.type_keys(CATALOG)
    classes = {key: lookout_id.surface_classes(CATALOG.surfaces[key])
               for key in ("warship_24", "warship_23", "warship_28", "cargo_01",
                           "tanker_11", "passenger_05", "aux_10", "aux_07")}
    assert classes["warship_24"] == ("WARSHIP", "FRIGATE", "warship_24")
    assert classes["warship_23"][1] == "DESTROYER"
    assert classes["warship_28"][:2] == ("CARRIER", "CARRIER")
    assert classes["cargo_01"] == ("MERCHANT", "CARGO", None)
    assert classes["tanker_11"] == ("MERCHANT", "TANKER", None)
    assert classes["passenger_05"] == ("MERCHANT", "PASSENGER", None)
    assert classes["aux_10"][0] == "SMALL_CRAFT"
    assert classes["aux_07"][0] == "FISHING"


def test_label_round_trip_and_validation():
    keys = {"warship_24"}
    for label in ("VISUAL", "VISUAL:R:WARSHIP", "VISUAL:I:FRIGATE",
                  "VISUAL:I:FRIGATE:warship_24"):
        assert lookout_id.valid_label(label, keys)
        level, code, key = lookout_id.decode(label)
        assert lookout_id.encode(level, code, code, key) == label
    for label in ("VISUAL:X", "VISUAL:R:BATTLESHIP", "VISUAL:I:FRIGATE:nope",
                  "VISUAL:R:WARSHIP:warship_24", "RADAR", None, 7):
        assert not lookout_id.valid_label(label, keys)


def test_closing_warship_is_sighted_then_classed_then_identified(game):
    actor = ship(game, "warship_24", 12.0)
    game.warships = [actor]
    approach(game, actor, 12.0, 1.5)
    reports = [row for row in game.lookout_reports if row["kind"] == "SURFACE"]
    assert [row["level"] for row in reports] == [0, 1, 2]
    assert [row["code"] for row in reports] == [None, "WARSHIP", "FRIGATE"]
    assert reports[2]["type_name"] == actor.profile.name
    # Each finer level needs a closer range (Johnson criteria).
    assert reports[0]["range_nm"] > reports[1]["range_nm"] > reports[2]["range_nm"]
    feed = [localize(entry.text, game.tr) for entry in game.feed.entries
            if entry.category == "ausguck"]
    assert len(feed) == 3 and all(line.startswith("Bridge lookout:") for line in feed)
    assert "frigate" in feed[-1] and actor.profile.name in feed[-1]
    assert visual_labels(game) == ["VISUAL:I:FRIGATE:warship_24"]


def test_class_is_held_while_the_contact_opens_and_nothing_is_repeated(game):
    actor = ship(game, "cargo_05", 2.0)
    game.warships = [actor]
    approach(game, actor, 2.0, 1.9)
    count = len(game.lookout_reports)
    for distance in (3.0, 5.0, 6.5):
        actor.x = game.ship.x + distance
        game._update_air_picture(full_scan=True)
        game.sim_t += 1.0
    assert visual_labels(game) == ["VISUAL:I:CARGO"]
    assert len(game.lookout_reports) == count
    # Several update calls inside one measurement epoch report once only.
    fresh = clean_game(1203)
    try:
        fresh.world.land_blocks_line = lambda *args: False
        fresh._update_lookout_land = lambda: None
        fresh.warships = [ship(fresh, "cargo_05", 1.0)]
        for _ in range(5):
            fresh._update_air_picture(full_scan=True)
        assert len(fresh.lookout_reports) == 1
    finally:
        fresh.audio.shutdown()


def test_small_craft_needs_to_be_much_closer_than_a_tanker(game):
    tanker, boat = ship(game, "tanker_11", 6.0), ship(game, "aux_10", 6.0)
    boat.y += 0.5
    game.warships = [tanker, boat]
    game._update_air_picture(full_scan=True)
    codes = {row["code"] for row in game.lookout_reports}
    assert "MERCHANT" in codes or "TANKER" in codes
    assert "SMALL_CRAFT" not in codes


def test_night_shortens_recognition(game, monkeypatch):
    def identified_at(night):
        current = clean_game(1204)
        try:
            current.world.land_blocks_line = lambda *args: False
            current._update_lookout_land = lambda: None
            current.world.is_night = lambda: night
            actor = ship(current, "warship_24", 8.0)
            current.warships = [actor]
            approach(current, actor, 8.0, 0.2)
            return next(row["range_nm"] for row in current.lookout_reports
                        if row["level"] == lookout_id.IDENTIFIED)
        finally:
            current.audio.shutdown()
    assert identified_at(True) < 0.5 * identified_at(False)


def test_report_is_an_observation_not_an_operator_annotation(game):
    game.warships = [ship(game, "warship_24", 2.0)]
    game._update_air_picture(full_scan=True)
    track = next(item for item in game.opz_tracks() if item.source == "LOOKOUT")
    assert track.visual == "VISUAL:I:FRIGATE:warship_24"
    assert track.classification is None
    assert game.opz_affiliation(track.track_id) not in ("HOSTILE", "FRIEND")
    assert not game.opz_fusion.classifications
    lines = [localize(line, game.tr) for line in _track_tooltip(game, track)["lines"]]
    assert any(line.startswith("Lookout: frigate") for line in lines)


def test_live_aircraft_look_like_simulated_civil_traffic(game):
    base = game.world.coast.airbases[0]
    flight = Flight("civil", base, dest=base, rng=random.Random(5), seq=7,
                    catalog=game.runtime_catalog)
    flight.x, flight.y = game.ship.x + 3.0, game.ship.y
    live = LiveAircraft("abc123", "DLH4", 8, game.ship.x - 3.0, game.ship.y,
                        3000.0, 90.0, 400.0, game.sim_t)
    game.flights.flights = [flight]
    game.live_traffic.aircraft = {"abc123": live}
    labels = visual_labels(game)
    assert len(labels) == 2 and labels[0] == labels[1]
    assert lookout_id.decode(labels[0])[1:] == ("AIRLINER", None)
    assert "DLH4" not in json.dumps(game.lookout_reports)


def test_identified_label_survives_save_and_load(game):
    game.warships = [ship(game, "warship_24", 2.0)]
    game._update_air_picture(full_scan=True)
    state = json.loads(json.dumps(game.save_state()))
    assert Game._valid_save_document(state, game.runtime_catalog)
    restored = Game(seed=1, start_menu=False, audio_enabled=False, language="en")
    try:
        assert restored._load_save_data(copy.deepcopy(state))
        assert restored.air_picture.serialize() == game.air_picture.serialize()
        assert restored.lookout_reports == []
    finally:
        restored.audio.shutdown()
    for label in ("VISUAL:I:FRIGATE:not_a_key", "VISUAL:Q"):
        broken = copy.deepcopy(state)
        row = next(item for item in broken["air_picture"] if item["source"] == "LOOKOUT")
        row["label"] = label
        assert not Game._valid_save_document(broken, game.runtime_catalog)


def test_torpedo_wake_is_announced(game):
    torpedo = type("Torpedo", (), {})()
    torpedo.id, torpedo.state, torpedo.depth = 3, "RUN", 3.0
    torpedo.x, torpedo.y = game.ship.x + 0.4, game.ship.y
    game.enemy_torpedoes = [torpedo]
    game._update_air_picture(full_scan=True)
    report = next(row for row in game.lookout_reports if row["kind"] == "TORP")
    assert report["code"] == "TORPEDO_WAKE"
    assert "TORPEDO WAKE" in localize(game.msg, game.tr)


def _coast_offset(game, distance):
    """A sea position about ``distance`` NM off the nearest coast."""
    world = game.world
    for landmass in world.coast.landmasses:
        for px, py in landmass.points[::7]:
            for angle in range(0, 360, 30):
                x = px + distance * math.sin(math.radians(angle))
                y = py - distance * math.cos(math.radians(angle))
                if (not world.on_land(x, y)
                        and abs(world.coast._distance_to_coast(x, y) - distance) < 0.5):
                    return x, y
    pytest.skip("no suitable coast")


def test_land_in_sight_is_reported_once_per_sighting():
    game = clean_game()
    try:
        game.ship.x, game.ship.y = _coast_offset(game, 7.0)
        game._update_lookout_land()
        land = [row for row in game.lookout_reports if row["code"] == "LAND"]
        # One report per landmass in sight (islands each count once).
        sightings = len(land)
        assert sightings >= 1
        assert min(row["range_nm"] for row in land) == pytest.approx(7.0, abs=0.6)
        game.sim_t += config.LOOKOUT_LAND_CHECK_S
        game._update_lookout_land()
        assert len([row for row in game.lookout_reports if row["code"] == "LAND"]) == sightings
        # Fog: the coast drops out of sight, and is reported again when it lifts.
        endpoints = (game.world._weather_start, game.world._weather_target)
        for endpoint in endpoints:
            endpoint["visibility_nm"] = 1.0
        game.sim_t += config.LOOKOUT_LAND_CHECK_S
        game._update_lookout_land()
        for endpoint in endpoints:
            endpoint["visibility_nm"] = config.WEATHER_VISIBILITY_MAX_NM
        game.sim_t += config.LOOKOUT_LAND_CHECK_S
        game._update_lookout_land()
        assert len([row for row in game.lookout_reports if row["code"] == "LAND"]) == 2 * sightings
        assert "land in sight" in localize(game.lookout_report_text(land[0]), game.tr)
    finally:
        game.audio.shutdown()


def test_reports_are_bounded(game):
    for index in range(config.LOOKOUT_REPORTS_MAX + 10):
        game._lookout_report("SURFACE", "VISUAL", float(index), 5.0)
    assert len(game.lookout_reports) == config.LOOKOUT_REPORTS_MAX
    assert game.lookout_reports[-1]["bearing"] == config.LOOKOUT_REPORTS_MAX + 9
