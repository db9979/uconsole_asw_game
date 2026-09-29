"""The crewed boat's radio room: HQ broadcast and situation reports
(save ``crew.radio``).

Fleet headquarters sends its submarine broadcast on a fixed schedule: a new
broadcast every ``UBOOT_RADIO_BROADCAST_S``, repeated until the next one.
The boat copies the broadcast on the air once its antenna (the raised mast
at periscope depth) has been up for ``UBOOT_RADIO_COPY_S`` without a break;
a boat that stays deep misses broadcasts and only ever gets the latest.

A broadcast may carry HQ's contact report on the frigate: a position that is
some minutes old (a reconnaissance fix, dead-reckoned back from the frigate's
motion when it is copied), with an error circle, rounded course and speed.
This is modelled intelligence with deterministic noise keyed by seed and
broadcast number, never the frigate's live position.

Below the mast the VLF loop antenna still copies the broadcast down to
``UBOOT_RADIO_VLF_DEPTH_M``; the slow VLF signal needs
``UBOOT_RADIO_VLF_COPY_S`` of continuous reception instead.

From broadcast ``UBOOT_ORDER_FIRST`` on, a broadcast may carry a new HQ
order while none is open (deterministic per seed and broadcast number, so a
missed broadcast is a missed order): proceed to an area, send a situation
report, or keep radio silence, each with a deadline. The radio room tracks
them; they do not decide the mission.

A situation report goes out on HF: ``UBOOT_RADIO_TX_S`` of transmission with
the antenna up, during which the frigate's HF direction finder can take a
bearing on the boat (``Sub.transmitting``).  Lowering the mast aborts it.
HQ acknowledges a report in its next broadcast and then always adds a
sharper contact report.
"""

from __future__ import annotations

import math

from src.core import config, detrand
from src.sensors.platform import MAST_DEPTH_M

VERSION = 2
LOG_KINDS = ("broadcast", "sent", "aborted")
STATE_FIELDS = frozenset({"version", "seq", "copied", "copy_since", "tx_until",
                          "tx_since", "sitreps", "ack_due", "log", "orders",
                          "order_seq"})
LOG_FIELDS = frozenset({"seq", "t", "kind", "number", "ack", "report", "order"})
ORDER_KINDS = ("area", "report", "silence")
ORDER_STATES = ("active", "done", "failed")
ORDER_FIELDS = frozenset({"id", "kind", "number", "issued_t", "deadline_t", "x", "y",
                          "radius_nm", "state", "ended_t"})
ORDERS_KEPT = 6
REPORT_FIELDS = frozenset({"x", "y", "radius_nm", "course", "speed_kn", "as_of"})


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def broadcast_number(sim_t: float) -> int:
    return int(math.floor(max(0.0, sim_t) / config.UBOOT_RADIO_BROADCAST_S))


def antenna_up(boat) -> bool:
    """The radio antenna is above the water: mast raised at periscope depth."""
    sub = boat.sub
    return bool(boat.orders.mast and not sub.sunk and sub.depth <= MAST_DEPTH_M + 1.0)


def reception(boat):
    """How the boat hears the broadcast now: "hf" (mast up), "vlf" (loop
    antenna at shallow depth) or None."""
    if antenna_up(boat):
        return "hf"
    sub = boat.sub
    if not sub.sunk and sub.depth <= config.UBOOT_RADIO_VLF_DEPTH_M:
        return "vlf"
    return None


def copy_seconds(mode) -> float:
    return config.UBOOT_RADIO_COPY_S if mode == "hf" else config.UBOOT_RADIO_VLF_COPY_S


class BoatRadio:
    """The radio room's schedule, transmissions and message log."""

    def __init__(self):
        self.seq = 0
        self.copied = -1              # number of the last broadcast copied
        self.copy_since = None        # antenna up since (sim s), for copying
        self.tx_since = None          # situation report on the air since
        self.tx_until = None          # ... and until (sim s)
        self.sitreps = 0
        self.ack_due = False          # HQ acknowledges in its next broadcast
        self.log: list[dict] = []
        self.orders: list[dict] = []  # HQ orders, newest last
        self.order_seq = 0

    # -- state ---------------------------------------------------------------

    @property
    def transmitting(self) -> bool:
        return self.tx_until is not None

    def latest_report(self):
        return next((row for row in reversed(self.log) if row["report"] is not None), None)

    def active_order(self):
        return next((order for order in self.orders if order["state"] == "active"), None)

    def _add(self, sim_t: float, kind: str, number=None, ack=False, report=None,
             order=None) -> dict:
        self.seq += 1
        row = dict(seq=self.seq, t=float(sim_t), kind=kind, number=number, ack=bool(ack),
                   report=report, order=order)
        self.log.append(row)
        del self.log[:-config.UBOOT_RADIO_LOG_MAX]
        return row

    # -- orders ----------------------------------------------------------------

    def send_sitrep(self, game, boat):
        """Start a situation report; True or the reason it cannot go out."""
        if boat.sub.sunk or not boat.sub._crew_ready():
            return "not_ready"
        if not antenna_up(boat):
            return "uboot_no_antenna"
        if self.transmitting:
            return "uboot_transmitting"
        self.tx_since = float(game.sim_t)
        self.tx_until = float(game.sim_t) + config.UBOOT_RADIO_TX_S
        boat.orders.event("radio_sending")
        order = self.active_order()
        if order is not None and order["kind"] == "silence":
            self._close_order(boat, order, "failed", game.sim_t)
        return True

    # -- the schedule (crew cadence) -------------------------------------------

    def update(self, game, boat) -> None:
        now = float(game.sim_t)
        up = antenna_up(boat)
        if self.transmitting:
            if not up:
                self.tx_since = self.tx_until = None
                self._add(now, "aborted")
                boat.orders.event("radio_aborted")
            elif now >= self.tx_until:
                self.tx_since = self.tx_until = None
                self.sitreps += 1
                self.ack_due = True
                self._add(now, "sent", number=self.sitreps)
                boat.orders.event("radio_sent", number=str(self.sitreps))
                order = self.active_order()
                if order is not None and order["kind"] == "report":
                    self._close_order(boat, order, "done", now)
                from src.core import boat_missions
                boat_missions.report_sent(game, boat)
        self._update_orders(boat, now)
        mode = reception(boat)
        if mode is None:
            self.copy_since = None
            return
        if self.copy_since is None:
            self.copy_since = now
        need = copy_seconds(mode)
        number = broadcast_number(now)
        if number <= self.copied or now - self.copy_since < need:
            return
        # The whole copy must fall inside this broadcast's time on the air.
        if self.copy_since < number * config.UBOOT_RADIO_BROADCAST_S \
                and now - number * config.UBOOT_RADIO_BROADCAST_S < need:
            return
        self.copied = number
        ack = self.ack_due
        self.ack_due = False
        report = hq_report(game, number, sharp=ack)
        order = self._issue_order(game, boat, number, now)
        self._add(now, "broadcast", number=number, ack=ack, report=report,
                  order=None if order is None else order["id"])
        boat.orders.event("radio_copied_report" if report is not None else "radio_copied",
                          number=str(number))
        if order is not None:
            boat.orders.event("radio_order_" + order["kind"], number=str(order["id"]))
        tell = getattr(game, "incidents_to_boat", None)
        if tell is not None:
            tell(boat, number * config.UBOOT_RADIO_BROADCAST_S)

    # -- HQ orders ---------------------------------------------------------------

    def _issue_order(self, game, boat, number: int, now: float):
        """The order broadcast ``number`` carries for this boat, or None."""
        seed = int(game.seed)
        if (number < config.UBOOT_ORDER_FIRST or self.active_order() is not None
                or self.order_seq >= config.UBOOT_ORDER_MAX
                or detrand.u01(seed, "hq-order", number) >= config.UBOOT_ORDER_P):
            return None
        kind = ORDER_KINDS[min(len(ORDER_KINDS) - 1, int(
            detrand.u01(seed, "hq-order-kind", number) * len(ORDER_KINDS)))]
        x = y = radius = None
        duration = {"report": config.UBOOT_ORDER_REPORT_S,
                    "silence": config.UBOOT_ORDER_SILENCE_S}.get(kind, config.UBOOT_ORDER_AREA_S)
        if kind == "area":
            point = _order_area(game, boat.sub, seed, number)
            if point is None:
                kind, duration = "report", config.UBOOT_ORDER_REPORT_S
            else:
                (x, y), radius = point, config.UBOOT_ORDER_RADIUS_NM
        self.order_seq += 1
        order = dict(id=self.order_seq, kind=kind, number=int(number), issued_t=float(now),
                     deadline_t=float(now) + duration, x=x, y=y, radius_nm=radius,
                     state="active", ended_t=None)
        self.orders.append(order)
        del self.orders[:-ORDERS_KEPT]
        return order

    def _close_order(self, boat, order, state: str, now: float) -> None:
        order["state"] = state
        order["ended_t"] = float(now)
        boat.orders.event("order_" + state, number=str(order["id"]))

    def _update_orders(self, boat, now: float) -> None:
        order = self.active_order()
        if order is None:
            return
        sub = boat.sub
        if order["kind"] == "area" and not sub.sunk and math.hypot(
                sub.x - order["x"], sub.y - order["y"]) <= order["radius_nm"]:
            self._close_order(boat, order, "done", now)
        elif now >= order["deadline_t"]:
            self._close_order(boat, order, "done" if order["kind"] == "silence"
                              else "failed", now)

    def progress(self, game, boat) -> dict:
        """Copy and transmission progress (0..1, or None) and the schedule."""
        now = float(game.sim_t)
        number = broadcast_number(now)
        copy = None
        if self.copy_since is not None and number > self.copied:
            start = max(self.copy_since, number * config.UBOOT_RADIO_BROADCAST_S)
            copy = min(1.0, max(0.0, (now - start) / copy_seconds(reception(boat))))
        send = None
        if self.transmitting:
            send = min(1.0, max(0.0, (now - self.tx_since) / config.UBOOT_RADIO_TX_S))
        return dict(antenna=antenna_up(boat), reception=reception(boat), broadcast=number,
                    copied=self.copied == number,
                    next_s=(number + 1) * config.UBOOT_RADIO_BROADCAST_S - now,
                    copy=copy, send=send, sitreps=self.sitreps, ack_due=self.ack_due)

    # -- saves -------------------------------------------------------------------

    def to_save(self) -> dict:
        return dict(version=VERSION, seq=self.seq, copied=self.copied,
                    copy_since=self.copy_since, tx_since=self.tx_since,
                    tx_until=self.tx_until, sitreps=self.sitreps, ack_due=self.ack_due,
                    log=[dict(row, report=None if row["report"] is None
                              else dict(row["report"])) for row in self.log],
                    orders=[dict(order) for order in self.orders], order_seq=self.order_seq)

    @staticmethod
    def valid_state(data) -> bool:
        if not isinstance(data, dict) or set(data) != STATE_FIELDS:
            return False
        if data["version"] != VERSION or type(data["version"]) is not int:
            return False
        for key, low in (("seq", 0), ("copied", -1), ("sitreps", 0), ("order_seq", 0)):
            if type(data[key]) is not int or not low <= data[key] <= 2**31:
                return False
        if type(data["ack_due"]) is not bool:
            return False
        for key in ("copy_since", "tx_since", "tx_until"):
            if data[key] is not None and (not _finite(data[key]) or data[key] < 0.0):
                return False
        if (data["tx_since"] is None) != (data["tx_until"] is None):
            return False
        if data["tx_until"] is not None and data["tx_until"] < data["tx_since"]:
            return False
        log = data["log"]
        if not isinstance(log, list) or len(log) > config.UBOOT_RADIO_LOG_MAX:
            return False
        previous = 0
        for row in log:
            if not isinstance(row, dict) or set(row) != LOG_FIELDS:
                return False
            if (type(row["seq"]) is not int or not previous < row["seq"] <= data["seq"]
                    or not _finite(row["t"]) or row["t"] < 0.0
                    or row["kind"] not in LOG_KINDS or type(row["ack"]) is not bool):
                return False
            previous = row["seq"]
            if row["order"] is not None and (
                    type(row["order"]) is not int or row["kind"] != "broadcast"
                    or not 1 <= row["order"] <= data["order_seq"]):
                return False
            if row["number"] is not None and (type(row["number"]) is not int
                                              or not 0 <= row["number"] <= 2**31):
                return False
            report = row["report"]
            if report is not None and (
                    row["kind"] != "broadcast" or not isinstance(report, dict)
                    or set(report) != REPORT_FIELDS
                    or not all(_finite(report[key]) for key in REPORT_FIELDS)
                    or report["radius_nm"] <= 0.0 or not 0.0 <= report["course"] < 360.0
                    or report["speed_kn"] < 0.0):
                return False
        return _valid_orders(data["orders"], data["order_seq"])

    @classmethod
    def from_save(cls, data) -> "BoatRadio":
        if not cls.valid_state(data):
            raise ValueError("invalid radio state")
        radio = cls()
        radio.seq = data["seq"]
        radio.copied = data["copied"]
        radio.copy_since = data["copy_since"]
        radio.tx_since = data["tx_since"]
        radio.tx_until = data["tx_until"]
        radio.sitreps = data["sitreps"]
        radio.ack_due = data["ack_due"]
        radio.log = [dict(row, report=None if row["report"] is None else
                          {key: float(value) for key, value in row["report"].items()})
                     for row in data["log"]]
        radio.orders = [dict(order) for order in data["orders"]]
        radio.order_seq = data["order_seq"]
        return radio


def _valid_orders(orders, order_seq) -> bool:
    if (not isinstance(orders, list) or len(orders) > ORDERS_KEPT
            or order_seq > config.UBOOT_ORDER_MAX):
        return False
    previous, active = 0, 0
    for order in orders:
        if not isinstance(order, dict) or set(order) != ORDER_FIELDS:
            return False
        if (type(order["id"]) is not int or not previous < order["id"] <= order_seq
                or order["kind"] not in ORDER_KINDS or order["state"] not in ORDER_STATES
                or type(order["number"]) is not int or not 0 <= order["number"] <= 2**31
                or not _finite(order["issued_t"]) or order["issued_t"] < 0.0
                or not _finite(order["deadline_t"])
                or order["deadline_t"] < order["issued_t"]):
            return False
        previous = order["id"]
        area = order["kind"] == "area"
        for key in ("x", "y", "radius_nm"):
            if (order[key] is None) == area or (area and not _finite(order[key])):
                return False
        if area and order["radius_nm"] <= 0.0:
            return False
        if order["state"] == "active":
            active += 1
            if order["ended_t"] is not None:
                return False
        elif not _finite(order["ended_t"]) or order["ended_t"] < order["issued_t"]:
            return False
    return active <= 1


def _order_area(game, sub, seed: int, number: int):
    """An area in open water some miles from the boat, or None."""
    low, high = config.UBOOT_ORDER_AREA_NM
    distance = low + (high - low) * detrand.u01(seed, "hq-order-range", number)
    start = 360.0 * detrand.u01(seed, "hq-order-bearing", number)
    size = float(game.world.size_nm)
    margin = config.UBOOT_ORDER_RADIUS_NM
    for step in range(8):
        rad = math.radians(start + 45.0 * step)
        x = sub.x + distance * math.sin(rad)
        y = sub.y - distance * math.cos(rad)
        if not (margin <= x <= size - margin and margin <= y <= size - margin):
            continue
        if game.world.physical_depth_m(x, y) >= config.UBOOT_ORDER_MIN_DEPTH_M:
            return round(x, 2), round(y, 2)
    return None


def hq_report(game, number: int, *, sharp: bool = False):
    """HQ's contact report on the frigate for broadcast ``number``, or None.

    Not every broadcast has one; after a situation report it always does,
    with a smaller error.  The position is ``age`` old: the frigate's
    position then, dead-reckoned back from its present course and speed,
    plus a deterministic error inside the stated circle.
    """
    if game.damage.ship_sunk:
        return None
    seed = int(game.seed)
    if not sharp and detrand.u01(seed, "hq-intel", number) >= config.UBOOT_RADIO_INTEL_P:
        return None
    ship = game.ship
    low, high = config.UBOOT_RADIO_REPORT_AGE_S
    age = low + (high - low) * detrand.u01(seed, "hq-age", number)
    speed_nm_s = max(0.0, float(ship.speed)) / 3600.0
    rad = math.radians(ship.course)
    x = ship.x - age * speed_nm_s * math.sin(rad)
    y = ship.y + age * speed_nm_s * math.cos(rad)
    radius = (config.UBOOT_RADIO_REPORT_SHARP_NM if sharp
              else config.UBOOT_RADIO_REPORT_RADIUS_NM)
    x += 0.4 * radius * detrand.normal(seed, "hq-x", number)
    y += 0.4 * radius * detrand.normal(seed, "hq-y", number)
    return dict(x=round(x, 2), y=round(y, 2), radius_nm=float(radius),
                course=float(round(ship.course / 10.0) * 10 % 360),
                speed_kn=float(round(max(0.0, ship.speed))),
                as_of=round(float(game.sim_t) - age, 1))
