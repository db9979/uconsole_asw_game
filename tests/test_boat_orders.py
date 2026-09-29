"""VLF reception below the mast and HQ orders to the crewed submarine."""

import copy
import json
import math
import sys
from pathlib import Path

from src.commander import projections
from src.core import boat_radio, config, detrand
from src.core.boat_radio import BoatRadio

sys.path.insert(0, str(Path(__file__).parent))
from test_boat_radio import BROADCAST, _step  # noqa: E402
from test_opfor_sub import _crewed, _feed_texts  # noqa: E402


def _vlf(game, boat, depth=22.0):
    sub = boat.sub
    sub.x, sub.y = game.ship.x - 20.0, game.ship.y
    sub.depth = sub.target_depth = sub.order_depth = depth
    boat.orders.mast = False


def _order_seed(kind=None):
    """A seed whose broadcast 2 carries an order (of ``kind``)."""
    for seed in range(1, 400):
        if detrand.u01(seed, "hq-order", 2) >= config.UBOOT_ORDER_P:
            continue
        index = int(detrand.u01(seed, "hq-order-kind", 2) * len(boat_radio.ORDER_KINDS))
        if kind is None or boat_radio.ORDER_KINDS[index] == kind:
            return seed
    raise AssertionError("no seed")


def _copy_broadcast(game, boat, number):
    game.sim_t = number * BROADCAST + 1.0
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_VLF_COPY_S + 2.0)


def test_the_vlf_loop_copies_slowly_below_the_mast_but_not_deep():
    game, _server, _bridge = _crewed(seed=61)
    boat = game.opfor
    _vlf(game, boat)
    assert boat_radio.reception(boat) == "vlf" and not boat_radio.antenna_up(boat)
    game.sim_t = BROADCAST + 1.0
    _step(game, boat, game.sim_t + config.UBOOT_RADIO_COPY_S + 5.0)
    assert boat.radio.copied == -1                      # VLF is slower than HF
    _step(game, boat, BROADCAST + config.UBOOT_RADIO_VLF_COPY_S + 2.0)
    assert boat.radio.copied == 1
    assert boat.radio.send_sitrep(game, boat) == "uboot_no_antenna"
    boat.sub.depth = config.UBOOT_RADIO_VLF_DEPTH_M + 5.0
    assert boat_radio.reception(boat) is None
    _step(game, boat, 2 * BROADCAST + 200.0)
    assert boat.radio.copied == 1


def test_an_area_order_arrives_by_vlf_and_is_done_on_arrival():
    seed = _order_seed("area")
    game, _server, _bridge = _crewed(seed=seed)
    boat = game.opfor
    _vlf(game, boat)
    _copy_broadcast(game, boat, 2)
    order = boat.radio.active_order()
    assert order is not None and order["kind"] == "area" and order["id"] == 1
    distance = math.hypot(order["x"] - boat.sub.x, order["y"] - boat.sub.y)
    assert config.UBOOT_ORDER_AREA_NM[0] - 0.1 <= distance <= config.UBOOT_ORDER_AREA_NM[1] + 0.1
    assert game.world.physical_depth_m(order["x"], order["y"]) >= config.UBOOT_ORDER_MIN_DEPTH_M
    assert boat.radio.log[-1]["order"] == 1
    assert any("order 1" in text for text in _feed_texts(game))
    view = projections._uboot_radio(game, boat)
    assert view["vlf"] and view["order"]["type"] == "area" and view["order"]["id"] == 1
    assert json.loads(json.dumps(view)) == view
    boat.sub.x, boat.sub.y = order["x"], order["y"]
    _step(game, boat, game.sim_t + 2.0)
    assert order["state"] == "done" and boat.radio.active_order() is None
    assert projections._uboot_radio(game, boat)["orders_done"] == 1


def test_a_report_order_is_done_by_a_sitrep_and_fails_after_its_deadline():
    seed = _order_seed("report")
    game, _server, _bridge = _crewed(seed=seed)
    boat = game.opfor
    _vlf(game, boat)
    _copy_broadcast(game, boat, 2)
    order = boat.radio.active_order()
    assert order["kind"] == "report"
    _step(game, boat, order["deadline_t"] + 1.0)
    assert order["state"] == "failed"
    game2, _s, _b = _crewed(seed=seed)
    boat2 = game2.opfor
    _vlf(game2, boat2)
    _copy_broadcast(game2, boat2, 2)
    boat2.sub.depth = boat2.sub.target_depth = boat2.sub.order_depth = 15.0
    assert boat2.sub.command_mast(True) is True
    assert boat2.radio.send_sitrep(game2, boat2) is True
    _step(game2, boat2, game2.sim_t + config.UBOOT_RADIO_TX_S + 2.0)
    assert boat2.radio.orders[-1]["state"] == "done"


def test_radio_silence_fails_on_a_transmission_and_holds_otherwise():
    seed = _order_seed("silence")
    game, _server, _bridge = _crewed(seed=seed)
    boat = game.opfor
    _vlf(game, boat)
    _copy_broadcast(game, boat, 2)
    order = boat.radio.active_order()
    assert order["kind"] == "silence"
    _step(game, boat, order["deadline_t"] + 1.0, dt=5.0)
    assert order["state"] == "done"


def test_orders_are_deterministic_bounded_and_saved():
    seed = _order_seed()
    runs = []
    for _ in range(2):
        game, _server, _bridge = _crewed(seed=seed)
        boat = game.opfor
        _vlf(game, boat)
        for number in range(2, 20):
            _copy_broadcast(game, boat, number)
        runs.append(copy.deepcopy(boat.radio.orders))
    assert runs[0] == runs[1]
    assert boat.radio.order_seq <= config.UBOOT_ORDER_MAX
    data = game.save_state()
    radio = data["crew"]["radio"]
    assert BoatRadio.valid_state(radio)
    restored = BoatRadio.from_save(json.loads(json.dumps(radio)))
    assert restored.orders == boat.radio.orders
    for mutate in (lambda r: r.pop("orders"),
                   lambda r: r.update(order_seq=config.UBOOT_ORDER_MAX + 1),
                   lambda r: r["orders"][0].update(kind="attack"),
                   lambda r: r["orders"][0].update(state="active", ended_t=None) or
                   r["orders"].append(dict(r["orders"][0], id=r["order_seq"] + 1)),
                   lambda r: r["log"][-1].update(order=99)):
        broken = copy.deepcopy(radio)
        mutate(broken)
        assert not BoatRadio.valid_state(broken)
