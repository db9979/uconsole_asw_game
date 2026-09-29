"""The crewed boat's radio room: HQ broadcast, situation reports, HF-DF, saves."""

import copy
import json
import math
import sys
from pathlib import Path

import pygame

from src.commander import projections
from src.commander.server import OPFOR_ROLES, V2_ACTION_REGISTRY
from src.commander.v2.commands import UBOOT_REASONS
from src.core import boat_radio, config, opfor, uboot_local
from src.core.boat_radio import BoatRadio, broadcast_number, hq_report
from src.sensors.platform import MAST_DEPTH_M
from src.ui import layout, uboot_view

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_opfor_sub import _crewed, _feed_texts  # noqa: E402
from test_uboot_scope import _key, _local_boat  # noqa: E402

BROADCAST = config.UBOOT_RADIO_BROADCAST_S


def _antenna_up(game, boat, distance_nm=20.0, bearing=90.0):
    sub = boat.sub
    rad = math.radians(bearing)
    sub.x = game.ship.x - distance_nm * math.sin(rad)
    sub.y = game.ship.y + distance_nm * math.cos(rad)
    sub.depth = sub.target_depth = sub.order_depth = MAST_DEPTH_M - 3.0
    assert sub.command_mast(True) is True


def _step(game, boat, until, dt=1.0):
    """Advance the radio room's clock (crew cadence) to ``until``."""
    while game.sim_t < until:
        game.sim_t = min(until, game.sim_t + dt)
        opfor.update_crew(game, boat)


def test_the_radio_room_is_the_seventh_boat_station():
    assert OPFOR_ROLES[-1] == "uboot_radio" and len(OPFOR_ROLES) == 7
    assert V2_ACTION_REGISTRY["uboot_radio_send"].stations == frozenset({"uboot_radio"})
    assert "uboot_radio" in V2_ACTION_REGISTRY["uboot_mast"].stations
    assert {"uboot_no_antenna", "uboot_transmitting"} <= UBOOT_REASONS
    assert uboot_view.station_pages("uboot_radio") == ("UBOOT_RADIO",)


def test_a_deep_boat_copies_nothing_and_cannot_send():
    game, _server, bridge = _crewed(seed=61)
    boat = game.opfor
    boat.sub.depth = 80.0
    game.sim_t = BROADCAST + 1.0
    _step(game, boat, game.sim_t + 120.0)
    assert boat.radio.copied == -1 and boat.radio.log == []
    assert bridge._apply_opfor_action(game, "uboot_radio_send", {}, "uboot_radio") \
        == "uboot_no_antenna"
    assert not boat.radio.transmitting and not boat.sub.transmitting


def test_the_antenna_copies_each_broadcast_once_after_the_copy_time():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = BROADCAST + 5.0
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S - 2.0)
    assert boat.radio.copied == -1
    assert boat.radio.progress(game, boat)["copy"] > 0.8
    _step(game, boat, game.sim_t + 3.0)
    assert boat.radio.copied == broadcast_number(game.sim_t) == 1
    rows = [row for row in boat.radio.log if row["kind"] == "broadcast"]
    assert len(rows) == 1 and rows[0]["number"] == 1
    assert any("broadcast 1 copied" in text for text in _feed_texts(game))
    assert boat.feed[-1]["category"] == "funk"
    _step(game, boat, game.sim_t + 200.0)
    assert len(boat.radio.log) == 1                    # the same broadcast only once
    # A copy begun inside the previous broadcast does not count for the next.
    boat.orders.mast = False
    _step(game, boat, 2 * BROADCAST - 5.0)
    boat.orders.mast = True
    _step(game, boat, 2 * BROADCAST + config.UBOOT_RADIO_COPY_S - 1.0)
    assert boat.radio.copied == 1
    _step(game, boat, 2 * BROADCAST + config.UBOOT_RADIO_COPY_S + 1.0)
    assert boat.radio.copied == 2


def test_a_situation_report_is_bearable_and_answered_with_a_sharp_report():
    game, _server, bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.world.land_blocks_line = lambda *args: False
    game.sim_t = 50.0
    _step(game, boat, 50.0 + config.UBOOT_RADIO_COPY_S + 1.0)   # broadcast 0 copied
    assert boat.radio.copied == 0
    assert bridge._apply_opfor_action(game, "uboot_radio_send", {}, "uboot_radio") is True
    assert boat.radio.transmitting and boat.sub.transmitting
    assert bridge._apply_opfor_action(game, "uboot_radio_send", {}, "uboot_radio") \
        == "uboot_transmitting"
    # The frigate's HF direction finder bears the transmission.
    game.radio_picture._tracks.clear()
    game._update_radio_picture()
    assert f"H-{boat.sub.id}" in game.radio_picture._tracks
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_TX_S + 1.0)
    assert not boat.sub.transmitting and boat.radio.sitreps == 1 and boat.radio.ack_due
    assert boat.radio.log[-1]["kind"] == "sent"
    game.radio_picture._tracks.clear()
    game._update_radio_picture()
    assert f"H-{boat.sub.id}" not in game.radio_picture._tracks
    _step(game, boat, BROADCAST + config.UBOOT_RADIO_COPY_S + 1.0)
    row = boat.radio.log[-1]
    assert row["kind"] == "broadcast" and row["ack"] and not boat.radio.ack_due
    assert row["report"]["radius_nm"] == config.UBOOT_RADIO_REPORT_SHARP_NM


def test_lowering_the_mast_aborts_the_transmission():
    game, _server, bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = 50.0
    assert boat.radio.send_sitrep(game, boat) is True
    _step(game, boat, 55.0)
    assert boat.sub.command_mast(False) is True
    _step(game, boat, 57.0)
    assert not boat.radio.transmitting and boat.radio.sitreps == 0
    assert boat.radio.log[-1]["kind"] == "aborted"
    assert any("aborted" in text for text in _feed_texts(game))


def test_hq_report_is_old_noisy_and_deterministic():
    game, _server, _bridge = _crewed(seed=61)
    ship = game.ship
    game.sim_t = 5000.0
    reports = [hq_report(game, number, sharp=True) for number in range(1, 30)]
    assert reports == [hq_report(game, number, sharp=True) for number in range(1, 30)]
    low, high = config.UBOOT_RADIO_REPORT_AGE_S
    for report in reports:
        assert low - 0.1 <= game.sim_t - report["as_of"] <= high + 0.1
        assert report["radius_nm"] == config.UBOOT_RADIO_REPORT_SHARP_NM
        assert report["course"] % 10.0 == 0.0
    assert len({(row["x"], row["y"]) for row in reports}) > 20
    assert all((row["x"], row["y"]) != (ship.x, ship.y) for row in reports)
    plain = [hq_report(game, number) for number in range(1, 200)]
    share = sum(row is not None for row in plain) / len(plain)
    assert abs(share - config.UBOOT_RADIO_INTEL_P) < 0.15
    game.damage.ship_sunk = True
    assert hq_report(game, 3, sharp=True) is None


def test_radio_state_saves_and_rejects_malformed_blocks(tmp_path):
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = BROADCAST + 1.0
    boat.radio.ack_due = True                          # this broadcast has a report
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S + 1.0)
    assert boat.radio.send_sitrep(game, boat) is True
    data = game.save_state()
    assert data["crew"]["radio"] == json.loads(json.dumps(data["crew"]["radio"]))
    assert data["crew"]["radio"]["tx_until"] is not None
    path = tmp_path / "slot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert game.load_game(str(path))
    assert game.opfor.radio.to_save() == data["crew"]["radio"]
    assert game.opfor.sub.transmitting                 # still on the air after loading
    assert game.opfor.orders.radio is game.opfor.radio
    before = game.save_state()
    for mutate in (lambda radio: radio.update(version=1),
                   lambda radio: radio.pop("log"),
                   lambda radio: radio.update(tx_since=None),
                   lambda radio: radio.update(sitreps=-1),
                   lambda radio: radio["log"][0].update(kind="telegram"),
                   lambda radio: radio["log"][0]["report"].update(x=float("nan")),
                   lambda radio: radio.update(log=[radio["log"][0]] * 2)):
        broken = copy.deepcopy(data)
        mutate(broken["crew"]["radio"])
        assert not BoatRadio.valid_state(broken["crew"]["radio"])
        assert not game._load_save_data(broken)
    assert game.save_state() == before


def test_the_projection_shows_the_radio_room_without_frigate_truth():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _antenna_up(game, boat)
    game.sim_t = BROADCAST + 1.0
    boat.radio.ack_due = True                          # the next broadcast reports
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S + 1.0)
    view = projections._uboot_radio(game, boat)
    assert view["antenna"] and view["copied"] and view["broadcast"] == 1
    report = view["report"]
    assert report is not None and report["age_s"] >= config.UBOOT_RADIO_REPORT_AGE_S[0]
    assert (report["x"], report["y"]) != (game.ship.x, game.ship.y)
    assert [row["type"] for row in view["log"]] == ["broadcast"]
    assert json.loads(json.dumps(view)) == view


def test_key_seven_opens_the_radio_room_and_enter_sends(monkeypatch):
    game, boat = _local_boat(seed=61)
    _key(game, pygame.K_7)
    assert uboot_local.local_station(game) == "uboot_radio"
    assert uboot_view.page_name(game, boat) == "UBOOT_RADIO"
    _key(game, pygame.K_RETURN)
    assert not boat.radio.transmitting                 # antenna down
    _antenna_up(game, boat)
    _key(game, pygame.K_RETURN)
    assert boat.radio.transmitting
    # The page draws in both languages inside the station panel.
    for language in ("en", "de"):
        game.set_language(language) if hasattr(game, "set_language") else None
        layout.configure_for(game)
        uboot_view.draw_command_panel(game, boat)
        uboot_view.draw_chart(game, boat)
    assert boat_radio.antenna_up(boat)
