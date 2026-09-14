import copy
import json
import random
from types import SimpleNamespace

import pytest

from src.air.flights import Flight
from src.air.raid import Raider
from src.commander.bridge import CommanderBridge
from src.core import config
from src.core.game import Game
from src.enemies.sub import Sub
from src.enemies.surface import SurfaceShip
from test_commander_bridge import Server


def clean_game(seed=1201):
    game = Game(seed=seed, start_menu=False, audio_enabled=False, language="en")
    game.subs = []
    game.civilians = []
    game.warships = []
    game.flights.flights = []
    game.raiders = []
    game.asms = []
    game.surface_radar_on = False
    game.air_radar_on = False
    game.air_picture._tracks.clear()
    game.world.hour = 12.0
    game.world.sea_state = 0
    game.world.refresh_weather()
    for endpoint in (game.world._weather_start, game.world._weather_target):
        endpoint["rain_intensity"] = 0.0
        endpoint["visibility_nm"] = config.WEATHER_VISIBILITY_MAX_NM
    return game


def surface(game, distance):
    actor = SurfaceShip(
        game.ship.x + distance, game.ship.y, random.Random(41),
        profile=game.runtime_catalog.surfaces["warship_01"],
        runtime_catalog=game.runtime_catalog)
    game.warships = [actor]
    return actor


def lookout(game):
    game._update_air_picture()
    return [track for track in game.opz_tracks() if track.source == "LOOKOUT"]


def esm_game(monkeypatch):
    game = clean_game(1202)
    actor = surface(game, 4.0)
    actor.emitter = True
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game.sim_t = .5
    game._update_esm_picture()
    return game


def test_eloka_annotation_is_explicit_bearing_only_release(monkeypatch):
    game = esm_game(monkeypatch)
    intercept = game.eloka_tracks()[0]
    assert not [track for track in game.opz_tracks() if track.source == "ESM"]

    emitter_key = "emitter.warship_01.radar"
    game.eloka_annotations[intercept.track_key] = emitter_key
    game._publish_released_esm()
    released = [track for track in game.opz_tracks() if track.source == "ESM"]

    assert len(released) == 1
    track = released[0]
    assert track.track_id.startswith("O-") and len(track.track_id) == 18
    assert not hasattr(track, "target_id") and track.kind == "UNKNOWN"
    assert track.range_nm is track.x is track.y is track.course is None
    assert track.label != game.runtime_catalog.emitter_name(emitter_key)
    assert track.classification == game.runtime_catalog.emitter_name(emitter_key)
    assert track.bearing == pytest.approx(intercept.bearing)
    assert track.bearing_uncertainty_deg == intercept.bearing_uncertainty_deg


def test_eloka_clear_and_annotation_change_stop_old_release(monkeypatch):
    game = esm_game(monkeypatch)
    intercept = game.eloka_tracks()[0]
    choices = [item.emitter_key for item in game.eloka_candidates(intercept)]
    assert len(choices) >= 2
    game.eloka_annotations[intercept.track_key] = choices[0]
    game._publish_released_esm()
    first = next(track for track in game.opz_tracks() if track.source == "ESM")

    game.eloka_annotations[intercept.track_key] = choices[1]
    game._publish_released_esm()
    released = [track for track in game.opz_tracks() if track.source == "ESM"]
    assert len(released) == 2
    assert first.last_seen == .5
    game.eloka_annotations.pop(intercept.track_key)
    game.sim_t += game.air_picture.stale_s + .1
    game.air_picture.expire(game.sim_t)
    assert not [track for track in game.opz_tracks() if track.source == "ESM"]


@pytest.mark.parametrize(("hour", "sea_state", "distance", "blocked", "visible"), [
    (12.0, 0, 11.9, False, True),
    (12.0, 0, 12.1, False, False),
    (0.0, 0, 5.0, False, False),
    (12.0, 6, 7.0, False, False),
    (12.0, 0, 5.0, True, False),
])
def test_lookout_surface_day_night_weather_land_and_range(
        monkeypatch, hour, sea_state, distance, blocked, visible):
    game = clean_game()
    surface(game, distance)
    game.world.hour = hour
    game.world.sea_state = sea_state
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: blocked)
    assert bool(lookout(game)) is visible


def test_lookout_submarine_depth_gate_and_aircraft_domains(monkeypatch):
    game = clean_game()
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    sub = Sub(game.ship.x + 3.0, game.ship.y,
              config.LOOKOUT_SUB_SURFACED_MAX_DEPTH_M, 0.0, "diesel_alt",
              random.Random(52), runtime_catalog=game.runtime_catalog)
    game.subs = [sub]
    assert [track.kind for track in lookout(game)] == ["SUB"]
    game.air_picture._tracks.clear()
    sub.depth = config.LOOKOUT_SUB_SURFACED_MAX_DEPTH_M + .01
    assert not lookout(game)

    base = game.world.coast.airbases[0]
    flight = Flight("military", base, rng=random.Random(53), seq=91,
                    catalog=game.runtime_catalog)
    flight.x, flight.y = game.ship.x + 15.0, game.ship.y
    game.flights.flights = [flight]
    raider = Raider(game.ship.x - 15.0, game.ship.y, 0.0, 92,
                    random.Random(54), game._air_defense_loadout["raider"])
    game.raiders = [raider]
    assert [track.kind for track in lookout(game)] == ["FLG", "FLG"]


def test_lookout_is_neutral_noisy_separate_and_does_not_mutate_global_rng(monkeypatch):
    game = clean_game()
    actor = surface(game, 5.0)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    global_state = random.getstate()
    game._update_air_picture()
    visual = next(track for track in game.opz_tracks() if track.source == "LOOKOUT")
    radar_key = f"W-{actor.id}"
    assert not hasattr(visual, "target_id")
    assert visual.label != "VISUAL" and visual.course is None
    assert visual.track_id != radar_key and str(actor.id) not in visual.track_id
    assert visual.range_nm != pytest.approx(5.0)
    assert random.getstate() == global_state

    first = copy.deepcopy(visual)
    game.air_picture._tracks.clear()
    game._update_air_picture()
    second = next(track for track in game.opz_tracks() if track.source == "LOOKOUT")
    assert second == first


def test_visual_track_never_overwrites_radar_track(monkeypatch):
    game = clean_game()
    actor = surface(game, 5.0)
    game.surface_radar_on = True
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game._update_air_picture()
    tracks = game.opz_tracks()
    assert {track.source for track in tracks} == {"RADAR-S", "LOOKOUT"}
    assert len({track.track_id for track in tracks}) == 2
    radar = next(track for track in tracks if track.source == "RADAR-S")
    assert not hasattr(radar, "target_id") and radar.quality == .9


def test_lookout_picture_is_stably_ordered_and_hard_bounded(monkeypatch):
    game = clean_game()
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game.civilians = [SimpleNamespace(
        id=index, sensor_seed=index + 1, sunk=False,
        x=game.ship.x + 1.0 + index / 10_000.0, y=game.ship.y)
        for index in reversed(range(600))]
    game._update_lookout_picture()
    tracks = game.opz_tracks()
    assert len(tracks) == game.air_picture.maximum
    assert [track.track_id for track in tracks] == sorted(
        track.track_id for track in tracks)


def test_v2_roles_receive_only_authorized_new_picture_sources(monkeypatch):
    game = esm_game(monkeypatch)
    intercept = game.eloka_tracks()[0]
    game.eloka_annotations[intercept.track_key] = "emitter.warship_01.radar"
    game._publish_released_esm()
    game._update_air_picture()
    bridge, server = CommanderBridge(), Server()
    bridge.pump(game, server, now=10.0)

    bridge_sources = {row["source"] for row in
                      server.v2_states["bridge"]["bridge"]["tactical_summary"]}
    opz_sources = {row["source"] for row in
                   server.v2_states["opz"]["opz"]["observations"]}
    assert "LOOKOUT" in bridge_sources and "ESM" not in bridge_sources
    assert {"LOOKOUT", "ESM"} <= opz_sources
    remote_esm = next(row for row in
                      server.v2_states["opz"]["opz"]["observations"]
                      if row["source"] == "ESM")
    opz_esm = next(row for row in game.opz_tracks() if row.source == "ESM")
    assert remote_esm["label"] == opz_esm.label
    classification = next(row for row in server.v2_states["opz"]["opz"][
        "source_classifications"] if row["ref"] == remote_esm["ref"])
    assert classification["classification"] == game.runtime_catalog.emitter_name(
        "emitter.warship_01.radar")
    assert remote_esm["range_nm"] is remote_esm["x"] is remote_esm["y"] is None
    assert remote_esm["course"] is None and remote_esm["affiliation"] == "UNKNOWN"
    for role in ("sonar", "weapons", "damage", "radio", "engine",
                 "helicopter", "eloka"):
        encoded = json.dumps(server.v2_states[role][role], sort_keys=True)
        assert '"LOOKOUT"' not in encoded and '"ESM"' not in encoded


def test_new_picture_sources_save_round_trip_validate_and_continue(monkeypatch):
    game = esm_game(monkeypatch)
    intercept = game.eloka_tracks()[0]
    game.eloka_annotations[intercept.track_key] = "emitter.warship_01.radar"
    game._publish_released_esm()
    game._update_air_picture()
    state = game.save_state()
    assert Game._valid_save_document(state, game.runtime_catalog)
    restored = Game(seed=1, start_menu=False, audio_enabled=False)
    restored.load_state(state)
    monkeypatch.setattr(restored.world, "land_blocks_line", lambda *args: False)
    assert restored.air_picture.serialize() == game.air_picture.serialize()

    malformed = copy.deepcopy(state)
    row = next(item for item in malformed["air_picture"]
               if item["source"] == "ESM")
    row["x"] = row["y"] = 1.0
    assert not Game._valid_save_document(malformed, game.runtime_catalog)
    malformed = copy.deepcopy(state)
    row = next(item for item in malformed["air_picture"]
               if item["source"] == "ESM")
    row["raw_x"] = 1.0
    assert not Game._valid_save_document(malformed, game.runtime_catalog)

    for _ in range(6):
        game.update(.1)
        restored.update(.1)
    assert restored.air_picture.serialize() == game.air_picture.serialize()
