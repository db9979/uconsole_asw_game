"""The boat's ESM measures each emitter's scan period: search or fire control."""

import copy
import json
import math
import sys
from pathlib import Path

from src.core import config
from src.core.i18n import localize
from src.core.boat_esm import BoatESM, scan_reading
from src.sensors.esm import ESMMeasurement
from src.ui import uboot_view

sys.path.insert(0, str(Path(__file__).parent))
from test_boat_esm import _mast_up_near_frigate  # noqa: E402
from test_opfor_sub import _crewed, _feed_texts, _run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _orders(events):
    return type("Orders", (), {"event": lambda self, key, **values: events.append(key)})()


def _measure(t, bearing=90.0):
    return ESMMeasurement(0.0, 0.0, bearing, 2.3, 9.4e9, 1500.0, "pulse", 0.8, t, False, 20.0)


def _feed(esm, times, orders, wash=0.0):
    for t in times:
        esm._wash = (5, 7, wash)
        esm._observe((_measure(float(t)),), float(t), orders)


def test_a_steady_beam_reads_steady_and_warns_once():
    esm, events = BoatESM(), []
    _feed(esm, range(0, 5), _orders(events))
    track = next(iter(esm.emitters.values())).track
    assert scan_reading(track) is None                     # still measuring
    _feed(esm, range(5, 20), _orders(events))
    assert scan_reading(track) == "steady" and abs(track.revisit_s - 1.0) < 1e-9
    assert events.count("esm_steady") == 1


def test_a_rotating_search_radar_reads_its_period():
    esm, events = BoatESM(), []
    # A 2.5 s antenna seen by one-second scans: gaps of 2 and 3 s.
    times = [math.floor(k * 2.5) for k in range(20)]
    _feed(esm, times, _orders(events))
    track = next(iter(esm.emitters.values())).track
    assert scan_reading(track) == "rotating" and 2.0 <= track.revisit_s <= 3.0
    assert "esm_steady" not in events


def test_washed_scans_and_long_silences_do_not_count():
    esm, events = BoatESM(), []
    # Every scan in between lost to the sea: the gap measures nothing.
    _feed(esm, (0, 4, 8, 12), _orders(events), wash=1.0)
    track = next(iter(esm.emitters.values())).track
    assert track.revisit_s == 0.0
    _feed(esm, (13, 14), _orders(events))
    assert track.revisit_s == 1.0
    _feed(esm, (14 + config.UBOOT_ESM_SCAN_GAP_MAX_S + 1,), _orders(events))
    assert track.revisit_s == 1.0


def test_the_frigate_search_radar_reads_rotating_on_the_mast():
    game, server, bridge = _crewed(seed=93)
    boat = game.opfor
    _mast_up_near_frigate(game, boat, 8.0, bearing=90.0)
    game.world.sea_state = 1
    _run(game, 60.0)
    readings = {scan_reading(item.track) for item in boat.esm.ordered()}
    assert "rotating" in readings and "steady" not in readings
    bridge.pump(game, server, now=5.0)
    rows = server.v2_states["uboot"]["uboot"]["esm"]["emitters"]
    rotating = [row for row in rows if row["scan"] == "rotating"]
    assert rotating and all(1.5 < row["scan_period_s"] <= 12.0 for row in rotating)
    # The reading survives a save exactly.
    state = json.loads(json.dumps(game.save_state()))
    assert game._load_save_data(copy.deepcopy(state))
    assert {scan_reading(item.track) for item in game.opfor.esm.ordered()} == readings
    chosen = next(item for item in boat.esm.ordered() if scan_reading(item.track) == "rotating")
    text = str(localize(uboot_view._esm_scan_text(chosen)))
    assert "sweep" in text and f"{chosen.track.revisit_s:.1f}" in text


def test_a_steady_live_emitter_is_a_mast_threat():
    game, _server, _bridge = _crewed(seed=94)
    boat = game.opfor
    esm = boat.esm
    _feed(esm, range(0, 20), _orders([]))
    emitter = esm.ordered()[0]
    assert esm.mast_threat(game, emitter, 19.0, 0.0) is True
    assert esm.mast_threat(game, emitter, 19.0 + config.UBOOT_ESM_LIVE_S + 1.0, 0.0) is False


def test_the_crew_log_reports_a_steady_beam():
    game, _server, _bridge = _crewed(seed=95)
    boat = game.opfor
    _feed(boat.esm, range(0, 20), boat.orders)
    _run(game, 1.0)
    assert any("steady illumination" in text for text in _feed_texts(game))
    js = (ROOT / "data/commander/js/stations/uboot.js").read_text(encoding="utf-8")
    assert "uboot_esm_scan_${row.scan}" in js
