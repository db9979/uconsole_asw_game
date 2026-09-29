"""Incidents at sea in the running mission (model in ``incidents.py``).

``Game`` mixin: the schedule, the four kinds (drift net, weather front,
a merchant without AIS, a pod of whales), their effects on the frigate and
the submarines, and what HQ tells the crewed boat in its broadcast.
"""

from __future__ import annotations

import math

from src.core import config, detrand
from src.core.i18n import message
from src.core.incidents import (KINDS, WEATHER, IncidentBoard, segment_distance_nm,
                                 segments_cross)
from src.enemies.animal import Animal
from src.enemies.civilian import CivilianShip
from src.sonar.sonar import TowState

# The frigate's slot in a net's ``fouled`` list (entity IDs start at 1).
FRIGATE_ID = 0


class IncidentsMixin:
    """Unplanned events of a mission; saved as the root field ``incidents``."""

    def _reset_incidents(self) -> None:
        first = detrand.uniform(*config.INCIDENT_FIRST_S, self.seed, "incident-first")
        self.incidents = IncidentBoard(first)

    # --- the schedule ----------------------------------------------------------

    def _update_incidents(self, dt: float) -> None:
        board = getattr(self, "incidents", None)
        if board is None or self.game_over:
            return
        for item in list(board.active()):
            getattr(self, "_progress_incident_" + item["kind"])(item)
        if (board.enabled and self.training is None and self.sim_t >= board.next_t
                and board.count < config.INCIDENT_MAX):
            self._start_incident()
            board.next_t = self.sim_t + detrand.uniform(
                *config.INCIDENT_INTERVAL_S, self.seed, "incident-interval", board.count)

    def _start_incident(self, kind: str | None = None):
        """Start the next incident (``kind`` forces one, for tests)."""
        board = self.incidents
        index = board.count
        board.count += 1
        kinds = [name for name in KINDS if (kind is None or name == kind)
                 and getattr(self, "_incident_candidate_" + name)()]
        if not kinds:
            return None
        kind = kinds[int(detrand.u01(self.seed, "incident-kind", index) * len(kinds))]
        fields = getattr(self, "_build_incident_" + kind)(index)
        if fields is None:
            return None
        base = dict(kind=kind, announced_t=self.sim_t, start_t=self.sim_t,
                    end_t=self.sim_t, active=True, x2=None, y2=None, weather=None,
                    target_id=None, plot_id=None, boat_told=False, fouled=[])
        item = board.add({**base, **fields})
        getattr(self, "_announce_incident_" + kind)(item)
        return item

    def _incident_point(self, index: int, tag: str, low: float, high: float,
                        spread_deg: float):
        """A deterministic point in deep water ``low..high`` NM out, around
        own course (``spread_deg`` either side)."""
        for attempt in range(8):
            offset = spread_deg * (2.0 * detrand.u01(self.seed, tag + "-brg", index,
                                                     attempt) - 1.0)
            angle = math.radians(self.ship.course + offset)
            distance = detrand.uniform(low, high, self.seed, tag + "-rng", index, attempt)
            x = config.clamp(self.ship.x + distance * math.sin(angle),
                             5.0, self.world.size_nm - 5.0)
            y = config.clamp(self.ship.y - distance * math.cos(angle),
                             5.0, self.world.size_nm - 5.0)
            if not self.world.on_land(x, y) and self.world.depth_m(x, y) > 30.0:
                return x, y
        return None

    def _incident_params(self, x: float, y: float) -> dict:
        bearing = math.degrees(math.atan2(x - self.ship.x, -(y - self.ship.y))) % 360.0
        return dict(x=f"{x:.1f}", y=f"{y:.1f}", bearing=f"{bearing:03.0f}",
                    range=f"{math.hypot(x - self.ship.x, y - self.ship.y):.1f}")

    def _end_incident(self, item, key: str | None = None) -> None:
        item["active"] = False
        if item["plot_id"] is not None:
            self.plot.remove(item["plot_id"])
            item["plot_id"] = None
        if key is not None:
            self.hq_msg(message(key, incident=self._incident_label(item)))

    @staticmethod
    def _incident_label(item) -> str:
        return f"{item['kind'].upper()} {item['id']}"

    # --- candidates -------------------------------------------------------------

    def _incident_candidate_net(self) -> bool:
        return len(self.incidents.active("net")) < 2

    def _incident_candidate_front(self) -> bool:
        return self.world.weather_override is None and not self.incidents.active("front")

    def _incident_candidate_dark(self) -> bool:
        return bool(self._dark_profiles())

    def _incident_candidate_whales(self) -> bool:
        return "whale" in self.runtime_catalog.animals

    def _dark_profiles(self) -> list:
        return sorted(key for key, profile in self.runtime_catalog.surfaces.items()
                      if profile.category == "FRACHT")

    # --- drift net ------------------------------------------------------------------

    def _build_incident_net(self, index: int):
        point = self._incident_point(index, "incident-net", *config.INCIDENT_NET_RANGE_NM,
                                     config.INCIDENT_NET_SPREAD_DEG)
        if point is None:
            return None
        cx, cy = point
        # Laid across the track: perpendicular to own course, a little skewed.
        skew = 30.0 * (2.0 * detrand.u01(self.seed, "incident-net-skew", index) - 1.0)
        angle = math.radians(self.ship.course + 90.0 + skew)
        half = config.INCIDENT_NET_LENGTH_NM / 2.0
        x1, y1 = cx - half * math.sin(angle), cy + half * math.cos(angle)
        x2, y2 = cx + half * math.sin(angle), cy - half * math.cos(angle)
        if self.world.on_land(x1, y1) or self.world.on_land(x2, y2):
            return None
        return dict(x=x1, y=y1, x2=x2, y2=y2,
                    end_t=self.sim_t + config.INCIDENT_NET_S)

    def _announce_incident_net(self, item) -> None:
        cx, cy = (item["x"] + item["x2"]) / 2.0, (item["y"] + item["y2"]) / 2.0
        self.hq_msg(message("runtime.incident.net", incident=self._incident_label(item),
                            length=f"{config.INCIDENT_NET_LENGTH_NM:.1f}",
                            depth=f"{config.INCIDENT_NET_DEPTH_M:.0f}",
                            minutes=f"{config.INCIDENT_NET_S / 60.0:.0f}",
                            **self._incident_params(cx, cy)))
        self.announce(message("runtime.incident.net_short",
                              incident=self._incident_label(item)), "funk", 5.0)
        result = self.plot_add("ruler", item["x"], item["y"], self._incident_label(item),
                               x2=item["x2"], y2=item["y2"])
        item["plot_id"] = result if type(result) is int else None

    def _progress_incident_net(self, item) -> None:
        if self.sim_t >= item["end_t"]:
            self._end_incident(item, "runtime.incident.net_end")
            return
        reach = config.INCIDENT_NET_HIT_NM
        line = (item["x"], item["y"], item["x2"], item["y2"])
        if (FRIGATE_ID not in item["fouled"] and not self.damage.ship_sunk
                and segment_distance_nm(self.ship.x, self.ship.y, *line) <= reach):
            self._foul_net(item, FRIGATE_ID)
            self._frigate_crosses_net(item)
        for sub in sorted(self.subs, key=lambda boat: boat.id):
            if (sub.sunk or sub.id in item["fouled"]
                    or sub.depth > config.INCIDENT_NET_DEPTH_M
                    or segment_distance_nm(sub.x, sub.y, *line) > reach):
                continue
            self._foul_net(item, sub.id)
            # Tearing free of the net is loud and short.
            sub.transient_left = max(sub.transient_left, config.INCIDENT_NET_TRANSIENT_S)
            if sub.manual and sub.crew is not None:
                sub.crew.event("net_fouled")

    @staticmethod
    def _foul_net(item, entity_id: int) -> None:
        if len(item["fouled"]) < 16:
            item["fouled"] = sorted(set(item["fouled"]) | {int(entity_id)})

    def _frigate_crosses_net(self, item) -> None:
        self.score -= config.SCORE_NET_TORN
        label = self._incident_label(item)
        fouled = []
        if self.sonar.tow_payout > 0.0 and self.sonar.tow_state != TowState.FAULT:
            self.sonar.tow_state = TowState.RETRIEVING
            fouled.append("TAS")
        if self.sonar.vds_payout > 0.0 and self.sonar.vds_state != TowState.FAULT:
            self.sonar.vds_state = TowState.RETRIEVING
            fouled.append("VDS")
        key = "runtime.incident.net_fouled" if fouled else "runtime.incident.net_torn"
        notice = message(key, incident=label, gear=" + ".join(fouled),
                         points=f"{-config.SCORE_NET_TORN:+d}")
        self.announce(notice, "bruecke", 5.0)

    # --- weather front ------------------------------------------------------------

    def _build_incident_front(self, index: int):
        draw = detrand.u01(self.seed, "incident-front-kind", index)
        weather = WEATHER[0 if draw < 0.5 else 1 if draw < 0.8 else 2]
        start = self.sim_t + config.INCIDENT_FRONT_LEAD_S
        hold = detrand.uniform(*config.INCIDENT_FRONT_S, self.seed, "incident-front-s", index)
        return dict(x=self.ship.x, y=self.ship.y, weather=weather,
                    start_t=start, end_t=start + hold)

    def _announce_incident_front(self, item) -> None:
        self.hq_msg(message(
            "runtime.incident.front", incident=self._incident_label(item),
            weather=message("weather.kind." + item["weather"]),
            lead=f"{(item['start_t'] - self.sim_t) / 60.0:.0f}",
            minutes=f"{(item['end_t'] - item['start_t']) / 60.0:.0f}"))

    def _progress_incident_front(self, item) -> None:
        world = self.world
        if self.sim_t >= item["end_t"]:
            if world.weather_override == item["weather"]:
                world.set_weather_override(None)
            self._end_incident(item, "runtime.incident.front_end")
        elif self.sim_t >= item["start_t"] and world.weather_override is None:
            world.set_weather_override(item["weather"])
            self.hq_msg(message("runtime.incident.front_here",
                                incident=self._incident_label(item),
                                weather=message("weather.kind." + item["weather"])))

    # --- a merchant without AIS ------------------------------------------------------

    def _build_incident_dark(self, index: int):
        point = self._incident_point(index, "incident-dark", *config.INCIDENT_DARK_RANGE_NM,
                                     180.0)
        if point is None:
            return None
        profiles = self._dark_profiles()
        key = profiles[int(detrand.u01(self.seed, "incident-dark-profile", index)
                           * len(profiles))]
        x, y = point
        ship = CivilianShip(x, y, rng=self.rng_world, side="neutral",
                            doctrine="dark_transit",
                            profile=self.runtime_catalog.surfaces[key],
                            runtime_catalog=self.runtime_catalog)
        course = 360.0 * detrand.u01(self.seed, "incident-dark-course", index)
        ship.course = ship.target_course = course
        ship.speed = ship.target_speed = detrand.uniform(
            *config.INCIDENT_DARK_SPEED_KN, self.seed, "incident-dark-speed", index)
        self.civilians.append(ship)
        return dict(x=x, y=y, target_id=int(ship.id),
                    end_t=self.sim_t + config.INCIDENT_DARK_S)

    def _announce_incident_dark(self, item) -> None:
        sigma = config.TASK_IDENTIFY_REPORT_SIGMA_NM
        index = item["id"]
        x = item["x"] + sigma * detrand.normal(self.seed, "incident-dark-ex", index)
        y = item["y"] + sigma * detrand.normal(self.seed, "incident-dark-ey", index)
        self.hq_msg(message("runtime.incident.dark", incident=self._incident_label(item),
                            **self._incident_params(x, y)))
        ship = next((row for row in self.civilians if row.id == item["target_id"]), None)
        if (ship is not None and self.tasking.enabled
                and len(self.tasking.open_tasks()) < config.TASK_MAX_OPEN):
            self._offer_task("identify", target=ship)

    def _progress_incident_dark(self, item) -> None:
        if self.sim_t >= item["end_t"]:
            self._end_incident(item)

    # --- a pod of whales -----------------------------------------------------------------

    def _build_incident_whales(self, index: int):
        point = self._incident_point(index, "incident-whales",
                                     *config.INCIDENT_WHALES_RANGE_NM, 60.0)
        if point is None:
            return None
        cx, cy = point
        profile = self.runtime_catalog.animals["whale"]
        course = 360.0 * detrand.u01(self.seed, "incident-whales-course", index)
        count = config.INCIDENT_WHALES_COUNT[0] + int(
            detrand.u01(self.seed, "incident-whales-n", index)
            * (config.INCIDENT_WHALES_COUNT[1] - config.INCIDENT_WHALES_COUNT[0] + 1))
        for member in range(count):
            angle = math.radians(360.0 * member / count)
            x, y = self.world.nearest_water(cx + 0.3 * math.sin(angle),
                                            cy - 0.3 * math.cos(angle))
            whale = Animal(x, y, "whale", self.rng_world, profile=profile)
            whale.course = whale.target_course = course
            self.animals.append(whale)
        return dict(x=cx, y=cy, end_t=self.sim_t + config.INCIDENT_WHALES_S)

    def _announce_incident_whales(self, item) -> None:
        self.hq_msg(message("runtime.incident.whales", incident=self._incident_label(item),
                            **self._incident_params(item["x"], item["y"])))

    def _progress_incident_whales(self, item) -> None:
        if self.sim_t >= item["end_t"]:
            self._end_incident(item)

    # --- the submarine's broadcast ----------------------------------------------------

    def incidents_to_boat(self, boat, broadcast_t: float) -> None:
        """HQ passes nets, fronts and whales announced before ``broadcast_t``
        on in the boat's broadcast; the crew plots a net on its own chart."""
        board = getattr(self, "incidents", None)
        if board is None:
            return
        for item in board.items:
            if (not item["active"] or item["boat_told"] or item["kind"] == "dark"
                    or item["announced_t"] > broadcast_t):
                continue
            item["boat_told"] = True
            label = self._incident_label(item)
            if item["kind"] == "net":
                cx, cy = (item["x"] + item["x2"]) / 2.0, (item["y"] + item["y2"]) / 2.0
                boat.orders.event("incident_net", incident=label, x=f"{cx:.1f}",
                                  y=f"{cy:.1f}",
                                  depth=f"{config.INCIDENT_NET_DEPTH_M:.0f}")
                self.plot_add("ruler", item["x"], item["y"], label, layer=boat.plot,
                              x2=item["x2"], y2=item["y2"])
            elif item["kind"] == "front":
                boat.orders.event("incident_front", incident=label,
                                  weather=message("weather.kind." + item["weather"]))
            else:
                boat.orders.event("incident_whales", incident=label,
                                  x=f"{item['x']:.1f}", y=f"{item['y']:.1f}")

    def net_ahead(self, x1: float, y1: float, x2: float, y2: float) -> bool:
        """Whether a leg crosses a reported drift net (the chart's knowledge)."""
        board = getattr(self, "incidents", None)
        return board is not None and any(
            segments_cross(x1, y1, x2, y2, item["x"], item["y"], item["x2"], item["y2"])
            for item in board.active("net"))

    def incident_view(self) -> list:
        """Detached rows of the current incidents (the radio room's list)."""
        rows = []
        for item in reversed(self.incidents.items):
            if not item["active"]:
                continue
            row = dict(id=item["id"], kind=item["kind"], label=self._incident_label(item),
                       start_t=item["start_t"], end_t=item["end_t"],
                       weather=item["weather"])
            if item["kind"] == "net":
                row.update(x=item["x"], y=item["y"], x2=item["x2"], y2=item["y2"])
            rows.append(row)
        return rows
