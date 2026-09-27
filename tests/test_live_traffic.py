import math
import queue
import time
from types import SimpleNamespace

import pytest

import src.core.game as game_module
from src.core import game_events
from src.core.game import Game
from src.core.preferences import Preferences
from src.data.catalog import CATALOG
from src.enemies.surface import SurfaceShip
from src.network import live_traffic as live_traffic_module
from src.network.live_traffic import LiveTrafficManager, _category_for_ais_type
from src.sensors.tracks import TrackPicture
from src.world.projection import lonlat_to_nm, nm_to_lonlat


def _fake_world(center_lat=54.0, center_lon=8.0, size_nm=500.0):
    coast = SimpleNamespace(metadata={
        "center": {"latitude": center_lat, "longitude": center_lon}})
    return SimpleNamespace(coast=coast, size_nm=size_nm)


class _FakeFlightManager:
    """Stand-in for FlightManager: same shared-seq contract as the real one."""

    def __init__(self):
        self._seq = 0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq


def _fake_game(ship_x=250.0, ship_y=250.0):
    return SimpleNamespace(runtime_catalog=CATALOG, civilians=[],
                           flights=_FakeFlightManager(),
                           ship=SimpleNamespace(x=ship_x, y=ship_y))


def esm_revolution(game, steps=12):
    """Rotating search radars reach the ESM mast with their main beam only
    once per revolution (up to 5 s); sample the picture over one."""
    for _ in range(steps):
        game.sim_t += .5
        game._update_esm_picture()


def test_category_for_ais_type_mapping():
    assert _category_for_ais_type(65) == "PASSAGIER"
    assert _category_for_ais_type(70) == "FRACHT"
    assert _category_for_ais_type(89) == "TANKER"
    assert _category_for_ais_type(None) == "SONSTIGES"
    assert _category_for_ais_type(0) == "SONSTIGES"


def test_configure_without_real_geography_disables_traffic():
    manager = LiveTrafficManager()
    world = SimpleNamespace(coast=SimpleNamespace(metadata=None), size_nm=500.0)
    game = _fake_game()
    manager.configure(game, world, Preferences(live_ais_enabled=True,
                                               aisstream_api_key="key"))
    assert manager.ais_client is None
    assert manager._center is None


def test_bounding_box_contains_center():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())  # disabled: no sockets opened
    (lat_min, lon_min), (lat_max, lon_max) = manager._bounding_box_latlon()
    assert lat_min < 54.0 < lat_max
    assert lon_min < 8.0 < lon_max


def test_adsb_query_covers_sensor_range_with_smaller_credit_area():
    manager = LiveTrafficManager()
    manager.configure(_fake_game(), _fake_world(), Preferences())
    area = manager._adsb_bounding_box(250.0, 250.0)
    world = manager._bounding_box_latlon()
    area_sqdeg = (area[1][0] - area[0][0]) * (area[1][1] - area[0][1])
    world_sqdeg = (world[1][0] - world[0][0]) * (world[1][1] - world[0][1])
    assert area_sqdeg <= 100.0 < world_sqdeg
    for x, y in ((100.0, 250.0), (400.0, 250.0),
                 (250.0, 100.0), (250.0, 400.0)):
        lon, lat = nm_to_lonlat(x, y, 8.0, 54.0)
        assert area[0][0] <= lat <= area[1][0]
        assert area[0][1] <= lon <= area[1][1]


def test_adsb_client_starts_with_ownship_area(monkeypatch):
    created = []

    class FakeOpenSky:
        def __init__(self, _credentials, bounding_box):
            self.bounding_box = bounding_box
            created.append(self)

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(live_traffic_module, "OpenSkyClient", FakeOpenSky)
    manager = LiveTrafficManager()
    game = _fake_game(ship_x=100.0, ship_y=200.0)
    manager.configure(game, _fake_world(), Preferences(live_adsb_enabled=True))
    assert created[0].bounding_box == manager._adsb_bounding_box(100.0, 200.0)


def test_adsb_query_moves_only_after_ship_crosses_margin():
    manager = LiveTrafficManager()
    game = _fake_game()
    manager.configure(game, _fake_world(), Preferences())
    changed = []
    manager.adsb_client = SimpleNamespace(
        set_bounding_box=lambda box: changed.append(box))
    manager._adsb_anchor = (250.0, 250.0)
    game.ship.x = 274.0
    manager._refresh_adsb_bounding_box(game)
    assert changed == []
    game.ship.x = 275.0
    manager._refresh_adsb_bounding_box(game)
    assert changed == [manager._adsb_bounding_box(275.0, 250.0)]
    assert manager._adsb_anchor == (275.0, 250.0)


def test_adsb_query_handles_antimeridian_with_single_complete_box():
    manager = LiveTrafficManager()
    manager.configure(_fake_game(), _fake_world(center_lon=179.5), Preferences())
    box = manager._adsb_bounding_box(350.0, 250.0)
    assert box[0][1] == -180.0 and box[1][1] == 180.0


def test_first_ais_contact_spawns_neutral_ship_and_applies_kinematics():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    lon, lat = 8.2, 54.1
    report = {"mmsi": 123456789, "lat": lat, "lon": lon, "cog": 90.0,
             "sog": 12.0, "name": "MV TESTSHIP"}
    manager._apply_ais_report(game, 123456789, report)
    assert len(game.civilians) == 1
    ship = game.civilians[0]
    assert isinstance(ship, SurfaceShip)
    assert ship.live_mmsi == 123456789
    assert ship.course == 90.0
    assert ship.speed == 12.0
    expected_x, expected_y = lonlat_to_nm(lon, lat, 8.0, 54.0, 500.0)
    assert ship.x == expected_x
    assert ship.y == expected_y


def test_ais_updates_are_throttled_between_120_and_300_seconds():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    mmsi = 111
    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 5.0})
    ship = manager._ships[mmsi]
    # Immediate follow-up report must not move the throttle-gated target.
    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 55.0, "lon": 9.0, "cog": 270.0, "sog": 20.0})
    assert ship.target_course == 0.0
    assert ship.target_speed == 5.0
    # Simulate that the throttle window has elapsed.
    manager._next_apply_at[mmsi] = time.time() - 1.0
    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 55.0, "lon": 9.0, "cog": 270.0, "sog": 20.0})
    assert ship.target_course == 270.0
    assert ship.target_speed == 20.0


def test_destroyed_mmsi_is_ignored_by_future_reports():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    mmsi = 222
    manager.ais_client = SimpleNamespace(reports=queue.Queue())
    manager.ais_client.reports.put({
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 5.0})
    manager._drain_ais(game)
    assert len(game.civilians) == 1
    manager.mark_ship_destroyed(mmsi)
    manager.ais_client.reports.put({
        "mmsi": mmsi, "lat": 54.1, "lon": 8.1, "cog": 45.0, "sog": 9.0})
    manager._drain_ais(game)
    assert len(game.civilians) == 1  # no second ship spawned for the same mmsi


def test_static_ais_details_are_cached_and_applied_to_live_ship():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.ais_client = SimpleNamespace(reports=queue.Queue())
    manager.ais_client.reports.put({
        "mmsi": 211123456, "lat": None, "lon": None,
        "name": "NORDSTERN", "callsign": "DABC", "imo": 9876543,
        "ship_type": 70, "destination": "HAMBURG", "draught_m": 7.4,
        "length_m": 100.0, "width_m": 15.0,
    })
    manager.ais_client.reports.put({
        "mmsi": 211123456, "lat": 54.0, "lon": 8.0,
        "cog": 45.0, "sog": 12.0, "nav_status": 0,
        "heading": 44, "position_accuracy": True,
    })

    manager._drain_ais(game)

    ship = manager._ships[211123456]
    assert ship.name == "NORDSTERN"
    assert ship.callsign == "DABC"
    assert ship.live_ais_details == {
        "imo": 9876543, "ship_type": 70, "destination": "HAMBURG",
        "draught_m": 7.4, "length_m": 100.0, "width_m": 15.0,
        "nav_status": 0, "heading": 44, "position_accuracy": True,
    }


def test_adsb_snapshot_creates_and_updates_aircraft():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    state = ["abc123", "TEST123", "DE", None, None, 8.1, 54.1, 5000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((time.time(), [state]))
    manager._drain_adsb(game)
    assert "abc123" in manager.aircraft
    aircraft = manager.aircraft["abc123"]
    assert aircraft.altitude_m == 5000.0

    manager.mark_aircraft_destroyed("abc123")
    assert "abc123" not in manager.aircraft
    manager.adsb_client.snapshots.put((time.time(), [state]))
    manager._drain_adsb(game)
    assert "abc123" not in manager.aircraft  # destroyed icao24 stays ignored


def test_live_aircraft_interpolates_between_fixes():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    now = time.time()
    state_a = ["dead01", "AB1", "DE", None, None, 8.0, 54.0, 1000.0,
              False, 100.0, 0.0, 0.0]
    manager.adsb_client.snapshots.put((now, [state_a]))
    manager._drain_adsb(game)
    aircraft = manager.aircraft["dead01"]
    x0, y0 = aircraft.x, aircraft.y

    later = now + 20.0
    state_b = ["dead01", "AB1", "DE", None, None, 8.2, 54.2, 2000.0,
              False, 100.0, 0.0, 0.0]
    manager.adsb_client.snapshots.put((later, [state_b]))
    manager._drain_adsb(game)
    # Halfway between the two fixes: position/altitude should sit in between.
    aircraft.advance(now + 10.0)
    assert x0 != aircraft.x or y0 != aircraft.y
    assert 1000.0 < aircraft.altitude_m < 2000.0


def _lonlat_at_offset_nm(dx_nm, dy_nm, center_lon=8.0, center_lat=54.0,
                         size_nm=500.0):
    x = size_nm * 0.5 + dx_nm
    y = size_nm * 0.5 + dy_nm
    return nm_to_lonlat(x, y, center_lon, center_lat, size_nm)


def test_far_ais_contact_is_never_spawned():
    """Performance guard: contacts far beyond every sensor's max range
    (ESM, the widest at 150 NM) must never be simulated at all."""
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()  # ship sits at the world center, (250, 250)
    manager.configure(game, world, Preferences())
    lon, lat = _lonlat_at_offset_nm(
        live_traffic_module._SHIP_RELEVANCE_NM + 10.0, 0.0)
    manager._apply_ais_report(game, 999, {
        "mmsi": 999, "lat": lat, "lon": lon, "cog": 0.0, "sog": 10.0})
    assert game.civilians == []
    assert 999 not in manager._ships


def test_ais_contact_on_mapped_land_is_not_simulated_and_removes_existing_ship():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    game.world = SimpleNamespace(on_land=lambda x, y: x >= 251.0)
    manager.configure(game, world, Preferences())

    land_lon, land_lat = _lonlat_at_offset_nm(2.0, 0.0)
    manager._apply_ais_report(game, 211123456, {
        "mmsi": 211123456, "lat": land_lat, "lon": land_lon,
        "cog": 0.0, "sog": 5.0, "name": "PORT CONTACT"})
    assert game.civilians == []
    assert 211123456 not in manager._ships

    manager._apply_ais_report(game, 211123456, {
        "mmsi": 211123456, "lat": 54.0, "lon": 8.0,
        "cog": 0.0, "sog": 5.0, "name": "PORT CONTACT"})
    ship = manager._ships[211123456]
    stable_id = ship.id
    assert ship in game.civilians

    manager._apply_ais_report(game, 211123456, {
        "mmsi": 211123456, "lat": land_lat, "lon": land_lon,
        "cog": 0.0, "sog": 5.0})
    assert ship not in game.civilians
    assert 211123456 not in manager._ships

    manager._apply_ais_report(game, 211123456, {
        "mmsi": 211123456, "lat": 54.0, "lon": 8.0,
        "cog": 0.0, "sog": 5.0})
    assert manager._ships[211123456].id == stable_id


def test_stationary_ais_contact_is_not_simulated_until_it_is_moving():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    mmsi = 211987654

    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0,
        "cog": 0.0, "sog": 0.0, "name": "ANCHORED"})
    assert game.civilians == []
    assert mmsi not in manager._ships

    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0,
        "cog": 90.0, "sog": 0.1, "name": "ANCHORED"})
    ship = manager._ships[mmsi]
    stable_id = ship.id
    assert ship in game.civilians

    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0,
        "cog": 90.0, "sog": 0.0})
    assert ship not in game.civilians
    assert mmsi not in manager._ships

    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0,
        "cog": 90.0, "sog": 5.0})
    assert manager._ships[mmsi].id == stable_id


def test_ship_that_drifts_out_of_release_range_is_pruned():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager._apply_ais_report(game, 555, {
        "mmsi": 555, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    assert len(game.civilians) == 1
    ship = manager._ships[555]
    ship.x = 250.0 + live_traffic_module._SHIP_RELEASE_NM + 10.0
    ship.y = 250.0
    manager._prune_ships(game, time.time())
    assert game.civilians == []
    assert 555 not in manager._ships


def test_stale_ship_without_recent_reports_is_pruned():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager._apply_ais_report(game, 777, {
        "mmsi": 777, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    assert len(game.civilians) == 1
    future = time.time() + live_traffic_module._SHIP_STALE_S + 1.0
    manager._prune_ships(game, future)
    assert game.civilians == []
    assert 777 not in manager._ships


def test_sunk_live_ship_is_never_pruned_as_a_wreck():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager._apply_ais_report(game, 888, {
        "mmsi": 888, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    ship = manager._ships[888]
    ship.sunk = True
    ship.x = 250.0 + live_traffic_module._SHIP_RELEASE_NM + 50.0
    future = time.time() + live_traffic_module._SHIP_STALE_S + 1.0
    manager._prune_ships(game, future)
    assert ship in game.civilians  # Wrack bleibt, unabhaengig von Alter/Distanz


def test_ship_spawn_cap_is_enforced():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager._ships = {i: object()
                      for i in range(live_traffic_module._MAX_LIVE_SHIPS)}
    manager._apply_ais_report(game, 12345, {
        "mmsi": 12345, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    assert 12345 not in manager._ships
    assert game.civilians == []


def test_far_adsb_contact_is_never_spawned():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    lon, lat = _lonlat_at_offset_nm(
        live_traffic_module._AIRCRAFT_RELEVANCE_NM + 20.0, 0.0)
    state = ["far01", "FAR1", "DE", None, None, lon, lat, 3000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((time.time(), [state]))
    manager._drain_adsb(game)
    assert "far01" not in manager.aircraft


def test_aircraft_that_drifts_out_of_release_range_is_pruned():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    state = ["near01", "NEAR1", "DE", None, None, 8.0, 54.0, 3000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((time.time(), [state]))
    manager._drain_adsb(game)
    assert "near01" in manager.aircraft
    aircraft = manager.aircraft["near01"]
    aircraft.x = 250.0 + live_traffic_module._AIRCRAFT_RELEASE_NM + 10.0
    manager._prune_aircraft(game, time.time())
    assert "near01" not in manager.aircraft


def test_stale_aircraft_without_recent_fixes_is_pruned():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    now = time.time()
    state = ["stale01", "STALE1", "DE", None, None, 8.0, 54.0, 3000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((now, [state]))
    manager._drain_adsb(game)
    assert "stale01" in manager.aircraft
    manager._prune_aircraft(
        game, now + live_traffic_module._AIRCRAFT_STALE_S + 1.0)
    assert "stale01" not in manager.aircraft


def test_aircraft_spawn_cap_is_enforced():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    manager.aircraft = {f"x{i}": object()
                        for i in range(live_traffic_module._MAX_LIVE_AIRCRAFT)}
    state = ["cap01", "CAP1", "DE", None, None, 8.0, 54.0, 3000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((time.time(), [state]))
    manager._drain_adsb(game)
    assert "cap01" not in manager.aircraft


def test_aircraft_reappearing_after_feed_gap_keeps_its_track_id():
    """A feed gap that briefly prunes a still-relevant contact must not
    mint a second, overlapping track for the same real aircraft: the ICAO24
    keeps its `seq` (and thus its air-picture track_id `A-<seq>`) across the
    prune/respawn cycle."""
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager.adsb_client = SimpleNamespace(snapshots=queue.Queue())
    now = time.time()
    state = ["gap01", "GAP1", "DE", None, None, 8.0, 54.0, 3000.0,
            False, 200.0, 90.0, 0.0]
    manager.adsb_client.snapshots.put((now, [state]))
    manager._drain_adsb(game)
    original_seq = manager.aircraft["gap01"].seq

    manager._prune_aircraft(
        game, now + live_traffic_module._AIRCRAFT_STALE_S + 1.0)
    assert "gap01" not in manager.aircraft

    manager.adsb_client.snapshots.put((now + 200.0, [state]))
    manager._drain_adsb(game)
    assert manager.aircraft["gap01"].seq == original_seq


def test_ship_reappearing_after_feed_gap_keeps_its_civilian_id():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    manager._apply_ais_report(game, 333, {
        "mmsi": 333, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    original_id = manager._ships[333].id

    future = time.time() + live_traffic_module._SHIP_STALE_S + 1.0
    manager._prune_ships(game, future)
    assert game.civilians == []

    manager._apply_ais_report(game, 333, {
        "mmsi": 333, "lat": 54.0, "lon": 8.0, "cog": 0.0, "sog": 10.0})
    assert manager._ships[333].id == original_id


@pytest.fixture
def game():
    game = Game(seed=31, audio_enabled=False, language="en")
    yield game
    game.commander.stop()
    game.audio.shutdown()


def test_live_traffic_api_test_reports_ok_and_error(game, monkeypatch):
    """The options-menu 'API test' row runs both probes in a background
    thread and stores per-side (status, reason) tuples the overlay reads."""
    monkeypatch.setattr(game_events, "ais_test_connection",
                        lambda api_key, bbox: (True, None))
    monkeypatch.setattr(game_events, "adsb_test_connection",
                        lambda credentials, bbox: (False, "boom"))
    game._set_preference("aisstream_api_key", "some-key")

    game._start_live_traffic_test()
    thread = game._live_traffic_test_thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert not thread.is_alive()

    assert game.live_traffic_test_result["ais"] == ("ok", None)
    assert game.live_traffic_test_result["adsb"] == ("error", "boom")


def test_live_traffic_api_test_skips_ais_without_key(game, monkeypatch):
    called = []
    monkeypatch.setattr(
        game_events, "ais_test_connection",
        lambda api_key, bbox: called.append(api_key) or (True, None))
    monkeypatch.setattr(game_events, "adsb_test_connection",
                        lambda credentials, bbox: (True, None))
    assert game.preferences.aisstream_api_key == ""

    game._start_live_traffic_test()
    game._live_traffic_test_thread.join(timeout=5.0)

    assert called == []  # AIS key missing: probe never invoked
    assert game.live_traffic_test_result["ais"] == ("no_key", None)
    assert game.live_traffic_test_result["adsb"] == ("ok", None)


def test_live_traffic_test_row_is_reachable_via_navigation(game, monkeypatch):
    monkeypatch.setattr(game_events, "ais_test_connection",
                        lambda api_key, bbox: (True, None))
    monkeypatch.setattr(game_events, "adsb_test_connection",
                        lambda credentials, bbox: (True, None))
    game._open_administration("live_traffic")
    assert game.live_traffic_open

    import pygame
    for _ in range(4):
        game._handle_live_traffic_key(pygame.K_DOWN)
    assert game.live_traffic_sel == 4  # "test" row, wrapping the 5-row menu

    game._handle_live_traffic_key(pygame.K_RETURN)
    thread = game._live_traffic_test_thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert game.live_traffic_test_result["adsb"] == ("ok", None)


def _spawn_live_ship_near_ownship(game, mmsi=211123456, dx_nm=-1.0):
    center_lon, center_lat = game.live_traffic._center
    lon, lat = nm_to_lonlat(
        game.ship.x + dx_nm, game.ship.y, center_lon, center_lat,
        game.world.size_nm)
    game.live_traffic._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": lat, "lon": lon, "cog": 90.0,
        "sog": 12.0, "name": "MV LIVE TEST",
    })
    return game.live_traffic._ships[mmsi]


def test_live_ship_is_not_published_without_simulated_sensor_detection(game):
    live_ship = _spawn_live_ship_near_ownship(game)
    game.air_picture = TrackPicture(game.air_picture.stale_s)
    game.surface_radar_on = False

    game._update_air_picture(full_scan=True)

    assert not [track for track in game.air_picture.tracks(game.sim_t)
                if track.target_id == live_ship.id]


def test_live_ship_is_radar_observed_and_manually_classifiable(game, monkeypatch):
    live_ship = _spawn_live_ship_near_ownship(game)
    game.air_picture = TrackPicture(game.air_picture.stale_s)
    game.surface_radar_on = True
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)

    game._update_air_picture(full_scan=True)

    track = next(track for track in game.air_picture.tracks(game.sim_t)
                 if track.target_id == live_ship.id)
    assert track.source == "RADAR-S"
    assert track.kind == "SURFACE"
    observation = next(row for row in game.opz_published_observations()
                       if row.source == "RADAR-S"
                       and row.kind == "SURFACE")
    assert observation.classification is None
    assert game.classify_opz_observation(
        observation.observation_id, "FAHRZEUG") is True
    refreshed = next(row for row in game.opz_published_observations()
                     if row.observation_id == observation.observation_id)
    assert refreshed.classification == "FAHRZEUG"


def test_live_ship_participates_in_lookout_and_eloka(game, monkeypatch):
    live_ship = _spawn_live_ship_near_ownship(game)
    monkeypatch.setattr(game.world, "land_blocks_line", lambda *args: False)
    game.air_picture = TrackPicture(game.air_picture.stale_s)

    game._update_lookout_picture()
    assert any(track.source == "LOOKOUT" and track.kind == "SURFACE"
               for track in game.air_picture.tracks(game.sim_t))

    live_ship.emitter = True
    esm_revolution(game)
    assert game.eloka_tracks()


def test_live_ship_is_audible_only_inside_passive_sonar_range(game, monkeypatch):
    live_ship = _spawn_live_ship_near_ownship(game)
    captured_sources = []
    monkeypatch.setattr(
        game.sonar.receiver, "update",
        lambda sources, *args, **kwargs: captured_sources.extend(sources))
    monkeypatch.setattr(
        game.sonar, "_passive_range_nm",
        lambda target, distance, *args, **kwargs: (
            2.0 if target is live_ship else 0.0))

    game.sim_t = game.sonar.receiver.block_s
    game.sonar.update(
        game.sonar.receiver.block_s, game.sim_t,
        game.ship, game._sonar_targets(), game.world)

    assert live_ship.id in game.sonar.contacts
    contact = game.sonar.contacts[live_ship.id]
    assert contact.player_class is None
    assert game.classify_sonar_contact(contact, "FAHRZEUG") is True
    assert contact.player_class == "FAHRZEUG"
    assert any(source["seed"] == live_ship.sensor_seed
               for source in captured_sources)

    live_ship.x = game.ship.x + 3.0
    captured_sources.clear()
    game.sonar.update(
        game.sonar.receiver.block_s, 2 * game.sonar.receiver.block_s,
        game.ship, game._sonar_targets(), game.world)

    assert not any(source["seed"] == live_ship.sensor_seed
                   for source in captured_sources)


def test_ais_not_available_sentinels_are_ignored():
    manager = LiveTrafficManager()
    world = _fake_world()
    game = _fake_game()
    manager.configure(game, world, Preferences())
    mmsi = 333
    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0, "cog": 360.0, "sog": 102.3})
    ship = manager._ships[mmsi]
    # AIS 'not available' (COG 360 / SOG 102.3) keeps the generated kinematics.
    assert 0.0 <= ship.course < 360.0
    assert ship.speed < 102.3 and ship.target_speed < 102.3
    generated = (ship.course, ship.speed)
    manager._next_apply_at[mmsi] = time.time() - 1.0
    manager._apply_ais_report(game, mmsi, {
        "mmsi": mmsi, "lat": 54.0, "lon": 8.0, "cog": 360.0, "sog": 102.3})
    assert (ship.target_course, ship.target_speed) == generated


def test_live_ais_ship_is_heard_by_passive_sonar(game, monkeypatch):
    """A live AIS ship is an ordinary acoustic source: it reaches the passive
    sonar through the same pipeline as simulated merchant traffic."""
    monkeypatch.setattr(game, "_check_mission_end", lambda: None)
    game.splash_active = game.main_menu = game.in_menu = False
    manager = game.live_traffic
    manager.configure(game, game.world, Preferences())
    assert manager._center is not None
    game.civilians, game.warships = [], []
    for sub in game.subs:
        sub.x += 1000.0
    x, y = next((game.ship.x + 4.0 * math.sin(math.radians(bearing)),
                 game.ship.y - 4.0 * math.cos(math.radians(bearing)))
                for bearing in range(0, 360, 15)
                if not game.world.on_land(
                    game.ship.x + 4.0 * math.sin(math.radians(bearing)),
                    game.ship.y - 4.0 * math.cos(math.radians(bearing)))
                and not game.world.land_blocks_line(
                    game.ship.x, game.ship.y,
                    game.ship.x + 4.0 * math.sin(math.radians(bearing)),
                    game.ship.y - 4.0 * math.cos(math.radians(bearing))))
    lon, lat = nm_to_lonlat(x, y, *manager._center, manager._size_nm)
    manager._apply_ais_report(game, 211000001, {
        "mmsi": 211000001, "lat": lat, "lon": lon, "cog": 0.0, "sog": 12.0,
        "ship_type": 70})
    ship = manager._ships[211000001]
    assert ship in game._sonar_targets()
    for _ in range(40):
        game.update(.05)
    assert ship.id in game.sonar.contacts
