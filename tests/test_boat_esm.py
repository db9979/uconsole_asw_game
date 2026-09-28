"""Stage B: the crewed boat's own ESM (intercepts, emitter list, cross-fix,
mast warning and mast time)."""

import copy
import json
import math
import random
import sys
from pathlib import Path

import pygame

from src.core import boat_esm, config, uboot_local
from src.core.boat_esm import BoatESM, cross_fix, level_trend
from src.sensors.esm import ESMMeasurement
from src.sensors.platform import MAST_DEPTH_M
from src.ui import layout, uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402


def _mast_up_near_frigate(game, boat, distance_nm=8.0, bearing=90.0):
    """Boat at periscope depth with the mast up, the frigate's radars on."""
    sub = boat.sub
    rad = math.radians(bearing)
    sub.x = game.ship.x - distance_nm * math.sin(rad)
    sub.y = game.ship.y + distance_nm * math.cos(rad)
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    assert sub.command_mast(True) is True
    game.surface_radar_on = game.air_radar_on = True
    game.world.land_blocks_line = lambda *args: False


def _samples(emitter_x, emitter_y, *, error_deg, seed, legs=46, step_s=20.0, own_kn=6.0):
    rng = random.Random(seed)
    rows = []
    for index in range(legs):
        t = index * step_s
        x, y = 0.0, -config.kn_to_nm_per_s(own_kn) * t
        bearing = math.degrees(math.atan2(emitter_x - x, -(emitter_y - y)))
        rows.append((t, x, y, (bearing + rng.uniform(-error_deg, error_deg)) % 360.0,
                     max(0.1, error_deg / math.sqrt(3.0))))
    return rows


def test_cross_fix_is_exact_without_noise_and_honest_with_it():
    fix = cross_fix(_samples(10.0, 0.0, error_deg=0.0, seed=1), 900.0)
    assert fix is not None and math.hypot(fix["x"] - 10.0, fix["y"]) < 1e-6
    # With +-4 deg bearings the 95 % ellipse holds the emitter in most runs.
    inside = fixes = 0
    for seed in range(120):
        fix = cross_fix(_samples(8.0, 0.0, error_deg=4.0, seed=seed), 900.0)
        if fix is None:
            continue
        fixes += 1
        axis = math.radians(fix["axis_deg"])
        dx, dy = fix["x"] - 8.0, fix["y"]
        along = dx * math.sin(axis) - dy * math.cos(axis)
        across = dx * math.cos(axis) + dy * math.sin(axis)
        inside += (along / fix["major_nm"]) ** 2 + (across / fix["minor_nm"]) ** 2 <= 1.0
    assert fixes > 100 and inside / fixes > 0.85


def test_cross_fix_needs_a_bearing_swing_and_a_point_ahead():
    # Two lines only, or a baseline that hardly turns the bearing: no fix.
    assert cross_fix(_samples(10.0, 0.0, error_deg=0.0, seed=1, legs=2), 20.0) is None
    far = _samples(80.0, 0.0, error_deg=0.0, seed=1, legs=5)
    assert cross_fix(far, 80.0) is None
    # Parallel lines never cross.
    parallel = [(t, 0.0, -t / 100.0, 0.0, 2.0) for t in (0.0, 10.0, 20.0)]
    assert cross_fix(parallel, 20.0) is None


def test_level_trend_reads_the_slope():
    history = [[t, 0.0, 0.0, 90.0, 2.0, 10.0 + t / 60.0] for t in range(0, 300, 30)]
    slope, trend = level_trend(history, 300.0)
    assert abs(slope - 1.0) < 1e-6 and trend == "rising"
    assert level_trend(history[:2], 300.0) == (None, None)


def test_agile_hops_stay_one_emitter_and_keep_the_fixed_fingerprint():
    esm = BoatESM()
    events = []
    orders = type("Orders", (), {"event": lambda self, key, **values: events.append(key)})()

    def measurement(t, frequency, prf, modulation, bearing=90.0):
        return ESMMeasurement(0.0, 0.0, bearing, 2.3, frequency, prf, modulation, 0.8, t,
                              False, 20.0)

    esm._observe((measurement(0.0, 3.0e9, 600.0, "pulse_doppler"),), 0.0, orders)
    esm._observe((measurement(1.0, 3.6e9, 1100.0, "frequency_agile", 91.0),), 1.0, orders)
    esm._observe((measurement(2.0, 3.0e9, 601.0, "pulse_doppler", 89.0),), 2.0, orders)
    assert len(esm.emitters) == 1 and events == ["esm_intercept"]
    track = next(iter(esm.emitters.values())).track
    assert track.modulation_code == "pulse_doppler" and abs(track.frequency_hz - 3.0e9) < 1.0
    # A different fixed radar on the same bearing is a second emitter.
    esm._observe((measurement(3.0, 9.4e9, 1500.0, "pulse", 90.0),), 3.0, orders)
    assert len(esm.emitters) == 2


def test_the_mast_hears_the_frigate_radar_and_keeps_the_list():
    game, _server, _bridge = _crewed()
    boat = game.opfor
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    _run(game, 30.0)
    esm = boat.esm
    assert esm.emitters and esm.mast_since is not None
    for emitter in esm.ordered():
        assert abs(config.angle_diff_deg(emitter.track.bearing, 90.0)) < 6.0
        assert emitter.history and emitter.track.track_key.startswith("E")
    assert any("new emitter E1" in text for text in _feed_texts(game))
    count = len(esm.emitters)
    # Diving lowers the mast: no new intercepts, the list stays.
    boat.sub.set_orders(depth=60.0)
    _run(game, 60.0)
    assert not boat.orders.mast and esm.mast_since is None and len(esm.emitters) == count


def test_boat_esm_is_deterministic_and_round_trips_in_saves(tmp_path, monkeypatch):
    from src.core.game import Animal, Decoy
    from src.enemies.sub import Sub
    from src.enemies.surface import SurfaceShip
    from src.weapons.torpedo import EnemyTorpedo
    # Entity IDs come from process-wide counters; both runs start equal.
    start = {cls: cls._next_id for cls in (Sub, Animal, SurfaceShip, Decoy, EnemyTorpedo)}
    states = []
    for _ in range(2):
        for cls, value in start.items():
            monkeypatch.setattr(cls, "_next_id", value)
        game, _server, _bridge = _crewed()
        _mast_up_near_frigate(game, game.opfor, 8.0, bearing=45.0)
        _run(game, 20.0)
        states.append(game.opfor.esm.to_save())
    assert states[0] == states[1] and states[0]["emitters"]
    data = game.save_state()
    assert data["crew"]["esm"] == json.loads(json.dumps(data["crew"]["esm"]))
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert game.load_game(str(path))
    assert game.opfor.esm.to_save() == data["crew"]["esm"]
    # A malformed ESM block rejects the whole save without touching the game.
    before = game.save_state()
    for mutate in (lambda esm: esm.update(version=2),
                   lambda esm: esm["emitters"][0].update(label="emitter.no_such.radar"),
                   lambda esm: esm["emitters"][0]["history"].append([1e12, 0, 0, 0, 1, 0]),
                   lambda esm: esm["emitters"][0]["track"].update(bearing=float("nan")),
                   lambda esm: esm.update(track_seq=0)):
        broken = copy.deepcopy(data)
        mutate(broken["crew"]["esm"])
        assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_classify_and_plot_over_remote_crew():
    game, _server, bridge = _crewed()
    boat = game.opfor
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    _run(game, 10.0)
    apply = bridge._apply_opfor_action
    emitter = boat.esm.ordered()[0]
    number = boat_esm.emitter_number(emitter.track.track_key)
    library = boat.esm.library(game, emitter)
    assert library
    assert apply(game, "uboot_esm_classify", {"emitter": number, "candidate": 0},
                 "uboot_esm") is True
    assert emitter.label == library[0]
    assert apply(game, "uboot_esm_classify", {"emitter": number, "candidate": 15},
                 "uboot_esm") in ("stale_ref", True)
    assert apply(game, "uboot_esm_classify", {"emitter": 999, "candidate": 0},
                 "uboot_esm") == "stale_ref"
    assert apply(game, "uboot_esm_classify", {"emitter": number, "candidate": -1},
                 "uboot_esm") is True and emitter.label is None
    # Only Command and the mast station own it.
    assert apply(game, "uboot_esm_classify", {"emitter": number, "candidate": 0},
                 "uboot_nav") is False
    # Without a cross-fix yet the plot gets the latest bearing line.
    objects = len(boat.plot.objects)
    assert apply(game, "uboot_esm_plot", {"emitter": number}, "uboot_esm") is True
    assert boat.plot.objects[objects]["kind"] in ("bearing", "mark")
    assert game.plot.objects == []


def test_projection_carries_measurements_and_no_emitter_truth():
    from src.commander.projections import _uboot_esm
    game, _server, _bridge = _crewed()
    boat = game.opfor
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    _run(game, 10.0)
    payload = _uboot_esm(game, boat)
    assert payload["mast_up"] and payload["emitters"]
    blob = json.dumps(payload)
    for forbidden in ("emitter_key", "signal_id", "target_id", "track_key", "sensor_seed"):
        assert forbidden not in blob
    for value in (game.ship.x, game.ship.y):
        assert json.dumps(value) not in blob
    row = payload["emitters"][0]
    assert row["label"].startswith("E") and row["band"] and row["history"]


def test_mast_warning_and_recommended_mast_time(monkeypatch):
    calm = boat_esm.recommended_mast_time_s(0.0, 0.0, False)
    rough = boat_esm.recommended_mast_time_s(5.0, 0.0, False)
    assert calm == config.UBOOT_MAST_TIME_BASE_S < rough
    assert boat_esm.recommended_mast_time_s(5.0, 0.0, True) == config.UBOOT_MAST_TIME_THREAT_S
    assert boat_esm.wash_fraction(1.0) == 0.0 < boat_esm.wash_fraction(5.0)
    game, _server, _bridge = _crewed()
    boat = game.opfor
    monkeypatch.setattr(boat_esm, "_weather", lambda _world: (0.0, 0.0))
    _mast_up_near_frigate(game, boat, 1.5, bearing=0.0)
    _run(game, 10.0)
    texts = _feed_texts(game)
    assert any("can see the mast" in text for text in texts)
    assert boat.esm.threat_warned
    # Past the (threat) mast time the log says so once.
    _run(game, config.UBOOT_MAST_TIME_THREAT_S + 2.0)
    assert sum("longer than the recommended" in text for text in _feed_texts(game)) == 1


def test_uconsole_esm_page_keys_and_chart():
    game, boat = _local_boat()
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    for _ in range(100):
        game._update(0.1)
    assert boat.esm.emitters
    uboot_local.set_local_station(game, "uboot_esm")
    boat.command_page = 0
    with layout.capture_geometry() as boxes:
        game.draw()
    titles = {row["title"] for row in boxes}
    assert {"uboot.panel.mast", "uboot.panel.esm", "uboot.panel.esm_detail"} <= titles
    first = uboot_view.esm_selection(boat)[1]
    if len(boat.esm.emitters) > 1:
        _key(game, pygame.K_DOWN)
        assert uboot_view.esm_selection(boat)[1] is not first
        _key(game, pygame.K_UP)
    assert uboot_view.esm_selection(boat)[1] is first
    library = boat.esm.library(game, first)
    _key(game, pygame.K_RIGHT)
    assert first.label == (library[0] if library else None)
    _key(game, pygame.K_LEFT)
    assert first.label is None
    objects = len(boat.plot.objects)
    _key(game, pygame.K_RETURN)
    assert len(boat.plot.objects) > objects
    game.draw()


def _heard(game, boat, seconds=30.0):
    """Bearings (deg) of the emitters in the boat's list after ``seconds``."""
    game.surface_radar_on = game.air_radar_on = False
    for _ in range(int(seconds / 0.25)):
        game._update_sim(0.25)
    return [emitter.track.bearing for emitter in boat.esm.emitters.values()]


def test_boat_esm_hears_the_helicopter_and_patrol_aircraft_radars():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _mast_up_near_frigate(game, boat, distance_nm=25.0)
    assert _heard(game, boat, 12.0) == []
    helo = game.helo
    helo.launch(game.ship)
    helo.x, helo.y = boat.sub.x + 6.0, boat.sub.y
    bearings = _heard(game, boat)
    assert len(bearings) == 1 and abs(config.angle_diff_deg(bearings[0], 90.0)) < 10.0
    emitter = next(iter(boat.esm.emitters.values()))
    helo_radar = game.runtime_catalog.emitters[config.HELO_RADAR_EMITTER]
    low, high = helo_radar.frequency_band_hz
    assert low <= emitter.track.frequency_hz <= high
    assert game.eloka_emitter_name(config.HELO_RADAR_EMITTER) == "ASW helicopter search radar"
    # In the dip the helicopter hovers with its radar off.
    helo.dip_state = "DEPLOYED"
    assert list(boat_esm.own_asset_emissions(game)) == []


def test_patrol_aircraft_radar_follows_its_switch():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _mast_up_near_frigate(game, boat, distance_nm=25.0)
    mpa = game.mpa
    mpa.state = "STATION"
    mpa.x, mpa.y = boat.sub.x, boat.sub.y - 20.0
    mpa.radar_on = False
    signals = list(boat_esm.own_asset_emissions(game))
    assert not signals
    mpa.radar_on = True
    signals = [signal for signal, _height in boat_esm.own_asset_emissions(game)]
    assert signals and all(signal.x == mpa.x for signal in signals)
