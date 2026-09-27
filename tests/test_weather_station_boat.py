"""The crewed boat's weather page: no flight weather, a boat block instead.

The frigate's page stays exactly as before; the submarine roles get what the
weather does to the boat (mast radar, optics, ambient noise, snorkel), all
from the environment and the boat's own plant, never another platform."""

import json
import math

import pytest

from src.commander.bridge import CommanderBridge
from src.commander.server import OPFOR_ROLES
from src.commander.v2 import schema as web_schema
from src.core import config
from src.core.game import Game
from src.sensors import radar as radar_physics
from src.sonar import equation as sonar_equation
from test_commander_bridge import Server

FRIGATE_KEYS = {"atmosphere", "effects", "flight", "profile"}
BOAT_KEYS = {"atmosphere", "effects", "boat", "profile"}


@pytest.fixture
def game():
    current = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    assert current.claim_opfor_sub() is not None
    yield current
    current.audio.shutdown()


def _boat_data(game):
    with game.sonar_perspective(game.opfor.station):
        return game.weather_station_data()


def test_boat_side_has_no_flight_block_but_a_boat_block(game):
    data = _boat_data(game)
    assert set(data) == BOAT_KEYS
    assert "ceiling_ft" not in data["atmosphere"] and "icing" not in data["atmosphere"]
    assert set(data["atmosphere"]) == set(web_schema.WEATHER_BOAT_ATMOSPHERE_FIELDS)
    boat = data["boat"]
    assert set(boat) == set(web_schema.WEATHER_BOAT_FIELDS)
    # Real game constants, not display inventions.
    assert boat["snorkel_max_kn"] == config.UBOOT_SNORKEL_MAX_KN == 6.0
    assert boat["snorkel_noise_db"] == config.UBOOT_SNORKEL_NOISE_DB
    assert boat["snorkel_lines_hz"] == [50.0, 100.0]
    assert boat["snorkel_available"] is (game.opfor.sub.endurance is not None)
    assert boat["sighting_ref_nm"] == config.LOOKOUT_SUB_RANGE_NM
    assert boat["ambient_bands_hz"] == list(sonar_equation.BANDS_HZ)
    horizon = config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M, config.SUB_MAST_HEIGHT_M)
    assert 0.0 < boat["mast_radar_nm"] <= boat["mast_radar_calm_nm"] <= horizon
    json.dumps(data, allow_nan=False)


def test_frigate_side_is_unchanged_by_a_crewed_boat():
    plain = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    crewed = Game(seed=4242, start_menu=False, audio_enabled=False, language="en")
    try:
        crewed.claim_opfor_sub()
        before, after = plain.weather_station_data(), crewed.weather_station_data()
        assert set(after) == FRIGATE_KEYS
        assert {"ceiling_ft", "icing"} <= set(after["atmosphere"])
        assert set(after["atmosphere"]) == set(web_schema.WEATHER_ATMOSPHERE_FIELDS)
        assert after == before
    finally:
        plain.audio.shutdown()
        crewed.audio.shutdown()


def test_boat_block_follows_sea_rain_and_light(game, monkeypatch):
    world = type(game.world)
    calm = dict(wind_from_deg=200.0, wind_speed_kn=4.0, rain_intensity=0.0,
                visibility_nm=30.0, sea_state=1.0)
    monkeypatch.setattr(world, "weather_values", lambda self: dict(calm))
    monkeypatch.setattr(world, "is_night", lambda self: False)
    quiet = _boat_data(game)["boat"]
    # Sea state 1, no rain: the calm reference itself.
    assert quiet["ambient_excess_db"] == pytest.approx([0.0] * 4, abs=1e-9)
    assert quiet["sighting_nm"] > 0.0
    rough = dict(calm, sea_state=5.0, rain_intensity=0.8, wind_speed_kn=30.0)
    monkeypatch.setattr(world, "weather_values", lambda self: dict(rough))
    monkeypatch.setattr(world, "is_night", lambda self: True)
    storm = _boat_data(game)["boat"]
    # Sea clutter hides the mast; wind and rain raise every band.
    assert storm["mast_radar_nm"] < quiet["mast_radar_nm"]
    assert storm["mast_radar_calm_nm"] == pytest.approx(quiet["mast_radar_calm_nm"])
    assert storm["mast_radar_nm"] == pytest.approx(min(
        config.radar_horizon_nm(config.RADAR_ANTENNA_HEIGHT_M, config.SUB_MAST_HEIGHT_M),
        radar_physics.detection_range_nm(
            config.RADAR_SURFACE_RANGE_NM, rcs_factor=config.SUB_MAST_RCS_FACTOR,
            domain="surface", sea_state=5.0, rain_intensity=0.8)), rel=1e-6)
    assert all(value > 0.0 for value in storm["ambient_excess_db"])
    assert storm["sighting_nm"] < quiet["sighting_nm"]


def test_boat_block_reads_no_frigate_or_hostile_state(game):
    before = _boat_data(game)
    # Moving the frigate and the other boats changes nothing aboard the boat.
    game.ship.x += 40.0
    game.ship.roll, game.ship.pitch = 12.0, 5.0
    for sub in game.subs:
        if sub is not game.opfor.sub:
            sub.x += 10.0
    after = _boat_data(game)
    assert after["boat"] == before["boat"]
    assert after["atmosphere"] == before["atmosphere"]


class _CrewedServer(Server):
    def station_leased(self, role):
        return role in OPFOR_ROLES


def test_browser_projection_of_every_boat_role():
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    try:
        bridge, server = CommanderBridge(), _CrewedServer()
        bridge.pump(game, server, now=100.0)
        states = json.loads(json.dumps(server.v2_states, allow_nan=False))
        assert set(OPFOR_ROLES) <= set(states)
        for role in OPFOR_ROLES:
            station = states[role]["weather_station"]
            assert set(station) == BOAT_KEYS, role
            assert list(station["atmosphere"]) == list(web_schema.WEATHER_BOAT_ATMOSPHERE_FIELDS)
            assert list(station["boat"]) == list(web_schema.WEATHER_BOAT_FIELDS)
            assert station["boat"]["snorkel_max_kn"] == config.UBOOT_SNORKEL_MAX_KN
            assert all(math.isfinite(value) for value in station["boat"]["ambient_excess_db"])
        for role in ("bridge", "sonar", "helicopter"):
            station = states[role]["weather_station"]
            assert set(station) == FRIGATE_KEYS
            assert list(station["atmosphere"]) == list(web_schema.WEATHER_ATMOSPHERE_FIELDS)
    finally:
        game.audio.shutdown()


def test_web_schema_carries_the_weather_allowlists():
    from tools import gen_web_schema
    block = gen_web_schema.render_block()
    for fields in (web_schema.WEATHER_ATMOSPHERE_FIELDS,
                   web_schema.WEATHER_BOAT_ATMOSPHERE_FIELDS,
                   web_schema.WEATHER_BOAT_FIELDS):
        assert gen_web_schema._array(fields) in block
    assert not {"ceiling_ft", "icing"} & set(web_schema.WEATHER_BOAT_ATMOSPHERE_FIELDS)
