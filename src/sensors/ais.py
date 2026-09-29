"""Simulated AIS VHF receiver for the own ship.

Civilian ships that transmit AIS broadcast their own name, position, course
and speed.
Those broadcasts are legitimate observations: the receiver only learns what a
report contained, only when a report was actually sent (ITU-R M.1371 class-A
reporting cadence) and only inside VHF line-of-sight.  Radar observations of
civilian ships therefore no longer carry the ship's true name or course; the
label/course come from the latest received AIS report instead.

The transmission phase of each ship is a stateless function of its sensor
seed, so the schedule needs no saved clock.  What the receiver has decoded is
saved and restored exactly.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.core import config, detrand

AIS_MAX_REPORTS = 128
AIS_STATIC_INTERVAL_S = 360.0
# Own VHF antenna mast and a typical merchant VHF antenna height.
AIS_RX_ANTENNA_HEIGHT_M = 25.0
AIS_TX_ANTENNA_HEIGHT_M = 15.0
AIS_NAME_MAX = 40
# A dynamic report older than this many nominal intervals is not used.
AIS_DYNAMIC_STALE_INTERVALS = 3.0


def reporting_interval_s(speed_kn: float) -> float:
    """ITU-R M.1371 class-A dynamic report interval (not changing course)."""
    if speed_kn <= 3.0:
        return 180.0       # at anchor / moored
    if speed_kn <= 14.0:
        return 10.0
    if speed_kn <= 23.0:
        return 6.0
    return 2.0


def vhf_range_nm() -> float:
    """VHF radio line-of-sight between the two antennas (4/3-Earth)."""
    return config.radar_horizon_nm(AIS_RX_ANTENNA_HEIGHT_M,
                                   AIS_TX_ANTENNA_HEIGHT_M)


@dataclass
class AISReport:
    target_id: int
    name: str | None
    cog: float
    sog: float
    t_dynamic: float
    t_static: float | None
    dynamic_epoch: int
    static_epoch: int
    x: float = 0.0          # reported position (NM) at ``t_dynamic``
    y: float = 0.0


class AISReceiver:
    """Own-ship AIS decoder state; holds received reports only."""

    def __init__(self, seed: int = 0):
        self.seed = int(seed)
        self.reports: dict[int, AISReport] = {}

    def _epoch(self, sensor_seed: int, tag: str, now: float,
               interval: float) -> int:
        offset = detrand.u01(self.seed, tag, sensor_seed) * interval
        return math.floor((now - offset) / interval)

    def update(self, now: float, ships, own_ship, world) -> None:
        """Decode every report that was broadcast inside VHF range."""
        reach = vhf_range_nm()
        present = {ship.id for ship in ships}
        for target_id in [key for key in self.reports if key not in present]:
            del self.reports[target_id]
        for ship in sorted(ships, key=lambda item: item.id):
            if not getattr(ship, "ais_transmitting", False):
                continue
            distance = math.hypot(ship.x - own_ship.x, ship.y - own_ship.y)
            if distance > reach or world.land_blocks_line(
                    own_ship.x, own_ship.y, ship.x, ship.y):
                continue
            interval = reporting_interval_s(ship.speed)
            dynamic_epoch = self._epoch(ship.sensor_seed, "ais-dynamic",
                                        now, interval)
            static_epoch = self._epoch(ship.sensor_seed, "ais-static", now,
                                       AIS_STATIC_INTERVAL_S)
            report = self.reports.get(ship.id)
            if report is None:
                if len(self.reports) >= AIS_MAX_REPORTS:
                    oldest = min(self.reports.values(),
                                 key=lambda item: (item.t_dynamic, item.target_id))
                    del self.reports[oldest.target_id]
                # First decoded message is a position report; the name only
                # arrives with the next static/voyage message.
                report = AISReport(ship.id, None, ship.course % 360.0,
                                   max(0.0, ship.speed), now, None,
                                   dynamic_epoch, static_epoch,
                                   round(ship.x, 4), round(ship.y, 4))
                self.reports[ship.id] = report
                continue
            if dynamic_epoch != report.dynamic_epoch:
                report.dynamic_epoch = dynamic_epoch
                report.cog = ship.course % 360.0
                report.sog = max(0.0, ship.speed)
                report.x, report.y = round(ship.x, 4), round(ship.y, 4)
                report.t_dynamic = now
            if static_epoch != report.static_epoch:
                report.static_epoch = static_epoch
                report.name = str(ship.name)[:AIS_NAME_MAX]
                report.t_static = now

    def forget(self, target_ids) -> None:
        for target_id in list(target_ids):
            self.reports.pop(target_id, None)

    def label_for(self, target_id: int) -> str | None:
        report = self.reports.get(target_id)
        return None if report is None else report.name

    def fresh(self, report: AISReport, now: float) -> bool:
        """The report's dynamic data is recent enough to use."""
        limit = AIS_DYNAMIC_STALE_INTERVALS * reporting_interval_s(report.sog)
        return 0.0 <= now - report.t_dynamic <= limit

    def position_for(self, report: AISReport, now: float) -> tuple[float, float]:
        """The reported position dead-reckoned to ``now`` by reported COG/SOG."""
        run = max(0.0, now - report.t_dynamic) * report.sog / 3600.0
        rad = math.radians(report.cog)
        return report.x + run * math.sin(rad), report.y - run * math.cos(rad)

    def course_for(self, target_id: int, now: float) -> float | None:
        report = self.reports.get(target_id)
        if report is None:
            return None
        limit = AIS_DYNAMIC_STALE_INTERVALS * reporting_interval_s(report.sog)
        if now - report.t_dynamic > limit:
            return None
        return report.cog

    # --- persistence -------------------------------------------------------

    def serialize(self) -> list[dict]:
        return [asdict(self.reports[key]) for key in sorted(self.reports)]

    @staticmethod
    def valid_state(rows, now: float, known_ids) -> bool:
        fields = set(AISReport.__dataclass_fields__)
        if not isinstance(rows, list) or len(rows) > AIS_MAX_REPORTS:
            return False
        previous = None

        def finite(value) -> bool:
            return (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value))

        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                return False
            target_id = row["target_id"]
            if (type(target_id) is not int or target_id not in known_ids
                    or (previous is not None and target_id <= previous)):
                return False
            previous = target_id
            name = row["name"]
            if name is not None and (not isinstance(name, str)
                                     or len(name) > AIS_NAME_MAX):
                return False
            if (not finite(row["cog"]) or not 0.0 <= row["cog"] < 360.0
                    or not finite(row["sog"]) or not 0.0 <= row["sog"] <= 100.0
                    or not finite(row["x"]) or not finite(row["y"])
                    or not -10000.0 <= row["x"] <= 10000.0
                    or not -10000.0 <= row["y"] <= 10000.0
                    or not finite(row["t_dynamic"])
                    or not 0.0 <= row["t_dynamic"] <= now):
                return False
            t_static = row["t_static"]
            if (t_static is None) != (name is None):
                return False
            if t_static is not None and (not finite(t_static)
                                         or not 0.0 <= t_static <= now):
                return False
            if any(type(row[key]) is not int or abs(row[key]) > 2**53
                   for key in ("dynamic_epoch", "static_epoch")):
                return False
        return True

    def restore(self, rows) -> None:
        self.reports = {row["target_id"]: AISReport(**row) for row in rows}
