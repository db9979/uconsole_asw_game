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
        self._incident_dt = dt
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

    # --- a man overboard ------------------------------------------------------------------

    def _incident_candidate_overboard(self) -> bool:
        return not self.damage.ship_sunk and not self.incidents.active("overboard")

    def _build_incident_overboard(self, index: int):
        # He goes over the side a ship's length off the track.
        side = 1.0 if detrand.u01(self.seed, "incident-mob-side", index) < 0.5 else -1.0
        angle = math.radians(self.ship.course + 90.0 * side)
        return dict(x=self.ship.x + 0.03 * math.sin(angle),
                    y=self.ship.y - 0.03 * math.cos(angle),
                    end_t=self.sim_t + config.INCIDENT_OVERBOARD_S)

    def _announce_incident_overboard(self, item) -> None:
        self.announce(message(
            "runtime.incident.overboard", incident=self._incident_label(item),
            x=f"{item['x']:.1f}", y=f"{item['y']:.1f}",
            minutes=f"{config.INCIDENT_OVERBOARD_S / 60.0:.0f}",
            speed=f"{config.INCIDENT_OVERBOARD_PICKUP_KN:.0f}",
            pickup=f"{config.INCIDENT_OVERBOARD_PICKUP_NM:.1f}"), "bruecke", 6.0)
        result = self.plot_add("mark", item["x"], item["y"], self._incident_label(item))
        item["plot_id"] = result if type(result) is int else None
        self._emit_sound("general_alarm")

    def _progress_incident_overboard(self, item) -> None:
        # The man drifts with the surface current (and the wind drift).
        dt = getattr(self, "_incident_dt", 0.0)
        u, v = self.world.current_vec(item["x"], item["y"])
        item["x"] += config.kn_to_nm_per_s(u) * dt
        item["y"] -= config.kn_to_nm_per_s(v) * dt
        if item["plot_id"] is not None and not self.plot.move(item["plot_id"], item["x"],
                                                              item["y"]):
            item["plot_id"] = None
        pickup = config.INCIDENT_OVERBOARD_PICKUP_NM
        by_ship = (not self.damage.ship_sunk
                   and self.ship.speed <= config.INCIDENT_OVERBOARD_PICKUP_KN + 1e-6
                   and math.hypot(self.ship.x - item["x"], self.ship.y - item["y"]) <= pickup)
        helo = self.helo
        # The helicopter winches him up in the hover: sent onto him (its
        # waypoint on the man) or holding a dip right there.
        by_helo = (helo.state == "AUF"
                   and math.hypot(helo.x - item["x"], helo.y - item["y"]) <= pickup
                   and (helo.hovering or (
                       helo.waypoint_x is not None and helo.waypoint_y is not None
                       and math.hypot(helo.waypoint_x - item["x"],
                                      helo.waypoint_y - item["y"]) <= 2.0 * pickup)))
        if by_ship or by_helo:
            self.score += config.SCORE_OVERBOARD_SAVED
            self._crew_event("task_done_sar")
            item["end_t"] = self.sim_t
            self._end_incident(item)
            self.announce(message(
                "runtime.incident.overboard_saved" if by_ship
                else "runtime.incident.overboard_saved_helo",
                incident=self._incident_label(item),
                points=f"{config.SCORE_OVERBOARD_SAVED:+d}"), "bruecke", 5.0)
        elif self.sim_t >= item["end_t"]:
            self.score -= config.SCORE_OVERBOARD_LOST
            self._crew_event("task_failed")
            self._end_incident(item)
            self.announce(message("runtime.incident.overboard_lost",
                                  incident=self._incident_label(item),
                                  points=f"{-config.SCORE_OVERBOARD_LOST:+d}"),
                          "bruecke", 5.0)

    def overboard_target(self):
        """(x, y) of the man in the water, or None (Bridge autocrew)."""
        board = getattr(self, "incidents", None)
        rows = [] if board is None else board.active("overboard")
        return None if not rows else (rows[0]["x"], rows[0]["y"])

    def overboard_just_recovered(self, window_s: float = 30.0) -> bool:
        """Whether a man was picked up in the last ``window_s`` seconds (the
        Bridge autocrew then brings the speed back up)."""
        board = getattr(self, "incidents", None)
        return board is not None and any(
            item["kind"] == "overboard" and not item["active"]
            and 0.0 <= self.sim_t - item["end_t"] <= window_s for item in board.items)

    # --- steering gear failure ----------------------------------------------------------

    def _incident_candidate_rudder(self) -> bool:
        return not self.damage.ship_sunk and not self.incidents.active("rudder")

    def _build_incident_rudder(self, index: int):
        return dict(x=self.ship.x, y=self.ship.y, end_t=self.sim_t + config.INCIDENT_RUDDER_S)

    def _announce_incident_rudder(self, item) -> None:
        self.announce(message(
            "runtime.incident.rudder", incident=self._incident_label(item),
            jam=f"{config.INCIDENT_RUDDER_JAM_S:.0f}",
            minutes=f"{(item['end_t'] - item['start_t']) / 60.0:.0f}"), "bruecke", 6.0)

    def _progress_incident_rudder(self, item) -> None:
        if self.sim_t >= item["end_t"]:
            self._end_incident(item)
            self.announce(message("runtime.incident.rudder_end",
                                  incident=self._incident_label(item)), "bruecke", 4.0)
        elif (self.sim_t - item["start_t"] >= config.INCIDENT_RUDDER_JAM_S
              and self.sim_t - self._incident_dt - item["start_t"]
              < config.INCIDENT_RUDDER_JAM_S):
            self.announce(message("runtime.incident.rudder_emergency",
                                  incident=self._incident_label(item)), "bruecke", 4.0)

    def rudder_casualty(self) -> tuple[bool, bool]:
        """(rudder jammed, on emergency steering) from a steering failure."""
        board = getattr(self, "incidents", None)
        for item in ([] if board is None else board.active("rudder")):
            if self.sim_t < item["end_t"]:
                return (self.sim_t - item["start_t"] < config.INCIDENT_RUDDER_JAM_S, True)
        return False, False

    # --- a submarine's snorkel valve and battery gas -------------------------------------

    def _incident_boat(self):
        """The submarine an emergency strikes: the crewed boat, otherwise the
        first hostile diesel boat afloat (a boat with a generator)."""
        boats = ([self._opfor.sub] if self._opfor is not None else []) + sorted(
            self.subs, key=lambda item: item.id)
        for sub in boats:
            endurance = getattr(sub, "endurance", None)
            if (not sub.sunk and sub.side == "hostile" and endurance is not None
                    and endurance.profile.generator_power_kw > 0.0):
                return sub
        return None

    def _incident_candidate_valve(self) -> bool:
        return self._incident_boat() is not None and not self.incidents.active("valve")

    def _incident_candidate_gas(self) -> bool:
        return self._incident_boat() is not None and not self.incidents.active("gas")

    def _build_incident_valve(self, index: int):
        sub = self._incident_boat()
        return dict(x=float(sub.x), y=float(sub.y), target_id=int(sub.id),
                    end_t=self.sim_t + config.INCIDENT_BOAT_S)

    _build_incident_gas = _build_incident_valve

    def _announce_incident_valve(self, item) -> None:
        sub = self._incident_target_sub(item)
        endurance = sub.endurance
        if endurance.phase == "SNORKEL":
            endurance.stop_snorkel() if sub.manual else self._ai_leave_snorkel(sub)
        if not sub.manual:
            # The AI boat stays down until the valve is free again.
            sub.radar_hold_s = max(sub.radar_hold_s, item["end_t"] - self.sim_t)
        self._incident_boat_event(sub, "incident_valve", item)

    def _announce_incident_gas(self, item) -> None:
        self._incident_boat_event(self._incident_target_sub(item), "incident_gas", item)

    def _progress_incident_valve(self, item) -> None:
        self._progress_boat_incident(item)

    _progress_incident_gas = _progress_incident_valve

    def _progress_boat_incident(self, item) -> None:
        sub = self._incident_target_sub(item)
        if sub is None or sub.sunk or self.sim_t >= item["end_t"]:
            self._end_incident(item)
            if sub is not None and not sub.sunk:
                self._incident_boat_event(sub, f"incident_{item['kind']}_end", item)

    def _incident_target_sub(self, item):
        return next((sub for sub in self.subs if sub.id == item["target_id"]), None)

    def _incident_boat_event(self, sub, key: str, item) -> None:
        boat = self._opfor
        if boat is not None and boat.sub is sub:
            boat.orders.event(key, minutes=f"{(item['end_t'] - self.sim_t) / 60.0:.0f}")

    @staticmethod
    def _ai_leave_snorkel(sub) -> None:
        endurance = sub.endurance
        endurance.phase = "DESCENDING"
        endurance.return_depth_m = endurance.profile.snorkel_depth_m + config.SUB_RADAR_DIVE_M

    def _apply_incident_effects(self) -> None:
        """Generator power of every submarine this substep: nothing through a
        jammed snorkel valve, half while battery gas is vented (derived from
        the saved board, so a loaded game continues identically)."""
        factors = {}
        board = getattr(self, "incidents", None)
        for item in ([] if board is None else board.items):
            if item["active"] and item["kind"] in ("valve", "gas"):
                factor = 0.0 if item["kind"] == "valve" else 0.5
                factors[item["target_id"]] = min(factors.get(item["target_id"], 1.0), factor)
        for sub in self.subs:
            endurance = getattr(sub, "endurance", None)
            if endurance is not None:
                endurance.generator_factor = factors.get(sub.id, 1.0)

    # --- the submarine's broadcast ----------------------------------------------------

    def incidents_to_boat(self, boat, broadcast_t: float) -> None:
        """HQ passes nets, fronts and whales announced before ``broadcast_t``
        on in the boat's broadcast; the crew plots a net on its own chart."""
        board = getattr(self, "incidents", None)
        if board is None:
            return
        for item in board.items:
            if (not item["active"] or item["boat_told"]
                    or item["kind"] not in ("net", "front", "whales")
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
