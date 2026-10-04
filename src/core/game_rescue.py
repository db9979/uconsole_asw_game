"""The helicopter's rescue hoist and the life rafts on radar.

A raft of an accepted distress task (``tasking`` kind ``sar``) is a small
radar target: own surface radar, the helicopter's and the patrol aircraft's
search radar can paint it (canopy and radar reflector, lost in the sea
clutter early), which puts the radio operator's search circle on the echo.

The helicopter recovers survivors only on order: within
``TASK_SAR_HOIST_ORDER_NM`` of a raft the hoist is ordered, the winchman
then cons the pilot over the raft and the winch lifts one survivor per
``TASK_SAR_HELO_S_PER_PERSON`` into a cabin of ``TASK_SAR_HELO_CAPACITY``.
The survivors count as rescued once the helicopter is back on deck; each
task row keeps its own survivors in the cabin as ``aboard`` (saved).
"""

import math

from src.core import config, detrand
from src.core.i18n import message
from src.sensors import radar as radar_physics

# Radar fix: the search circle shrinks to this radius on the echo.
RADAR_FIX_RADIUS_NM = 0.3
# A new radar fix moves the plotted circle only beyond this distance.
REPLOT_NM = 0.1


def persons_left(task) -> int:
    """Survivors still in the raft (the ship alongside takes them in one go,
    the helicopter one per lift)."""
    return max(0, math.ceil(task["persons"] * (1.0 - task["progress"]) - 1e-6))


class RescueMixin:
    """Hoist orders, the lift itself, the delivery on deck and raft echoes."""

    # --- the hoist ---------------------------------------------------------------

    def helo_survivors(self) -> int:
        board = getattr(self, "tasking", None)
        return 0 if board is None else sum(task["aboard"] for task in board.tasks)

    def _rescue_rafts(self) -> list:
        board = getattr(self, "tasking", None)
        if board is None:
            return []
        return [task for task in board.active("sar") if persons_left(task) > 0]

    def _hoist_raft(self, reach_nm: float):
        """The nearest raft with survivors within ``reach_nm`` of the
        helicopter (the crew sees it below them), or None."""
        helo = self.helo
        best = None
        for task in self._rescue_rafts():
            gap = math.hypot(task["true_x"] - helo.x, task["true_y"] - helo.y)
            if gap <= reach_nm and (best is None or (gap, task["id"]) < best[0]):
                best = ((gap, task["id"]), task)
        return None if best is None else best[1]

    def order_helicopter_hoist(self, enabled=None):
        """Start (or stop) the rescue hoist over the nearest raft."""
        helo = self.helo
        if enabled is None:
            enabled = not helo.hoist
        if type(enabled) is not bool:
            return "invalid_value"
        if not enabled:
            helo.stop_hoist()
            return True
        if helo.state != "AUF":
            return "not_airborne"
        if helo.dip_state != "STOWED":
            return "dipping"
        if self.helo_survivors() >= config.TASK_SAR_HELO_CAPACITY:
            return "full"
        if self._hoist_raft(config.TASK_SAR_HOIST_ORDER_NM) is None:
            return "no_raft"
        helo.hoist = True
        helo.hoist_s = 0.0
        return True

    def toggle_helicopter_hoist(self):
        """The hoist key at the helicopter station, with its feedback."""
        result = self.order_helicopter_hoist()
        if result is True:
            self.flash(message("runtime.helo.hoist_on" if self.helo.hoist
                               else "runtime.helo.hoist_off"), 2.0)
        elif result == "no_raft":
            self.flash(message("runtime.helo.hoist_no_raft",
                               range=f"{config.TASK_SAR_HOIST_ORDER_NM:.1f}"), 2.5)
        elif result == "full":
            self.flash(message("runtime.helo.hoist_full",
                               capacity=config.TASK_SAR_HELO_CAPACITY), 2.5)
        elif result == "dipping":
            self.flash(message("runtime.helo.hoist_dipping"), 2.0)
        elif result == "not_airborne":
            self.flash(message("runtime.helo.not_airborne"), 2.0)
        return result

    def _update_helo_hoist(self, dt: float) -> None:
        board = getattr(self, "tasking", None)
        if board is None:
            return
        helo = self.helo
        if helo.state == "HANGAR":
            self._deliver_survivors(board)
        elif helo.state == "VERLOREN":
            self._lose_survivors(board)
        if not helo.hoist:
            return
        if helo.state != "AUF" or helo.dip_state != "STOWED":
            helo.stop_hoist()
            return
        raft = self._hoist_raft(2.0 * config.TASK_SAR_HOIST_ORDER_NM)
        if raft is None:
            helo.stop_hoist()
            self.announce(message("runtime.helo.hoist_lost"), "waffen", 3.0)
            return
        # The winchman cons the pilot over the drifting raft.
        helo.set_waypoint(raft["true_x"], raft["true_y"])
        gap = math.hypot(raft["true_x"] - helo.x, raft["true_y"] - helo.y)
        if (gap > config.TASK_SAR_HOIST_OVERHEAD_NM
                or not self.helicopter_weather()["dipping_safe"]):
            return                                  # holds the lift until steady
        helo.hoist_s += dt
        if helo.hoist_s < config.TASK_SAR_HELO_S_PER_PERSON:
            return
        helo.hoist_s = 0.0
        left = persons_left(raft) - 1
        raft["aboard"] += 1
        raft["progress"] = min(1.0, 1.0 - left / raft["persons"])
        aboard = self.helo_survivors()
        label = self._task_label(raft)
        capacity = config.TASK_SAR_HELO_CAPACITY
        if left <= 0:
            helo.stop_hoist()
            self.announce(message("runtime.helo.hoist_raft_empty", task=label,
                                  aboard=aboard, capacity=capacity), "waffen", 5.0)
        elif aboard >= capacity:
            helo.stop_hoist()
            self.announce(message("runtime.helo.hoist_cabin_full", task=label,
                                  aboard=aboard, capacity=capacity, left=left),
                          "waffen", 5.0)
        else:
            self.announce(message("runtime.helo.hoist_person", task=label,
                                  aboard=aboard, capacity=capacity, left=left),
                          "waffen", 2.5)

    def _deliver_survivors(self, board) -> None:
        """Back on deck: the cabin's survivors go below; a raft whose crew
        is all out of the water is then done (``_progress_task_sar``)."""
        delivered = 0
        for task in board.tasks:
            delivered += task["aboard"]
            task["aboard"] = 0
        if delivered:
            self.announce(message("runtime.helo.survivors_delivered", count=delivered),
                          "waffen", 4.0)

    def _lose_survivors(self, board) -> None:
        for task in list(board.tasks):
            if not task["aboard"]:
                continue
            task["aboard"] = 0
            if task["state"] == "active" and persons_left(task) == 0:
                self._close_task(task, "failed")

    def helo_rescue_status(self):
        """What the helicopter station shows about the rescue, or None when
        no raft is waiting and the cabin is empty. Positions are the
        reported ones; only the winch's own steadiness uses the raft."""
        rafts = self._rescue_rafts()
        aboard = self.helo_survivors()
        helo = self.helo
        if not rafts and not aboard:
            return None
        capacity = config.TASK_SAR_HELO_CAPACITY
        near = None
        for task in rafts:
            x, y = self.task_position(task)
            gap = math.hypot(x - helo.x, y - helo.y)
            if near is None or (gap, task["id"]) < (near[0], near[1]["id"]):
                near = (gap, task)
        phase = "search"
        if helo.hoist:
            raft = self._hoist_raft(2.0 * config.TASK_SAR_HOIST_ORDER_NM)
            if raft is not None:
                x, y = self.task_position(raft)
                near = (math.hypot(x - helo.x, y - helo.y), raft)
            if not self.helicopter_weather()["dipping_safe"]:
                phase = "weather"
            elif raft is None or math.hypot(raft["true_x"] - helo.x, raft["true_y"] - helo.y
                                            ) > config.TASK_SAR_HOIST_OVERHEAD_NM:
                phase = "approach"
            else:
                phase = "lifting"
        elif helo.state != "AUF":
            phase = "deck" if helo.state == "HANGAR" else "return"
        elif (near is not None and near[0] <= config.TASK_SAR_HOIST_ORDER_NM
              and aboard < capacity):
            phase = "ready"
        elif aboard:
            phase = "return"
        return dict(
            phase=phase, hoist=helo.hoist, aboard=aboard, capacity=capacity,
            lift=(helo.hoist_s / config.TASK_SAR_HELO_S_PER_PERSON) if helo.hoist else 0.0,
            raft=None if near is None else self._task_label(near[1]),
            left=None if near is None else persons_left(near[1]),
            range_nm=None if near is None else near[0],
            bearing=None if near is None else (math.degrees(math.atan2(
                self.task_position(near[1])[0] - helo.x,
                -(self.task_position(near[1])[1] - helo.y))) % 360.0))

    # --- rafts on radar ----------------------------------------------------------

    def _raft_radar_targets(self, observer_x, observer_y, altitude_m, range_nm):
        """``(task, distance, bearing)`` of the rafts inside range and the
        radar horizon of one antenna (accepted tasks only)."""
        horizon = min(range_nm, config.radar_horizon_nm(
            altitude_m, config.TASK_SAR_RAFT_HEIGHT_M))
        rows = []
        for task in self._rescue_rafts():
            dx, dy = task["true_x"] - observer_x, task["true_y"] - observer_y
            distance = math.hypot(dx, dy)
            if distance <= horizon and not self.world.land_blocks_line(
                    observer_x, observer_y, task["true_x"], task["true_y"]):
                rows.append((task, distance, math.degrees(math.atan2(dx, -dy)) % 360.0))
        return rows

    def _raft_radar_fix(self, task, observer_x, observer_y, bearing, measured) -> None:
        """One echo: the radio operator's circle goes on it (until the raft
        is in sight, when the lookouts follow it)."""
        if task["sighted"]:
            return
        x = observer_x + measured * math.sin(math.radians(bearing))
        y = observer_y - measured * math.cos(math.radians(bearing))
        first = task["radius_nm"] > RADAR_FIX_RADIUS_NM
        moved = math.hypot(x - task["x"], y - task["y"]) > REPLOT_NM
        task["x"], task["y"] = x, y
        task["radius_nm"] = RADAR_FIX_RADIUS_NM
        task["report_t"] = self.sim_t
        if first or moved:
            self._task_plot(task)
        if first:
            brg, distance = self._task_bearing_range(x, y)
            self.announce(message("task.sar.radar", task=self._task_label(task),
                                  bearing=f"{brg:03.0f}", range=f"{distance:.1f}"),
                          "opz", 5.0)

    def _ship_radar_rafts(self, swept_deg: float) -> None:
        """Own surface radar's look at the rafts (rotating antenna)."""
        for task, distance, bearing in self._raft_radar_targets(
                self.ship.x, self.ship.y, config.RADAR_ANTENNA_HEIGHT_M,
                config.RADAR_SURFACE_RANGE_NM):
            if not self._radar_look("surface", 300000 + task["id"], distance, bearing,
                                    swept_deg=swept_deg,
                                    rcs_factor=config.TASK_SAR_RAFT_RCS):
                continue
            tick, key = math.floor(self.sim_t * 4.0 + 1e-6), int(task["id"])
            noisy = (bearing + config.RADAR_BEARING_ERR_DEG
                     * detrand.normal(self.seed, "ship-radar-raft-brg", key, tick)) % 360.0
            measured = max(0.0, distance + config.TASK_SAR_RADAR_ERR_NM
                           * detrand.normal(self.seed, "ship-radar-raft-rng", key, tick))
            self._raft_radar_fix(task, self.ship.x, self.ship.y, noisy, measured)

    def _aircraft_radar_rafts(self, observer_x, observer_y, altitude_m, range_nm,
                              conditions, tag_prefix, tick) -> None:
        """An own aircraft's search radar on the rafts (one look per scan)."""
        for task, distance, bearing in self._raft_radar_targets(
                observer_x, observer_y, altitude_m, range_nm):
            sinr = radar_physics.sinr(distance, range_nm, rcs_factor=config.TASK_SAR_RAFT_RCS,
                                      domain="surface", **conditions)
            tag, key = tag_prefix + "raft", int(task["id"])
            if detrand.u01(self.seed, tag, key, tick) >= radar_physics.pd_from_sinr(sinr):
                continue
            noisy = (bearing + config.MPA_RADAR_BEARING_ERR_DEG
                     * detrand.normal(self.seed, tag + "-brg", key, tick)) % 360.0
            measured = max(0.0, distance + config.TASK_SAR_RADAR_ERR_NM
                           * detrand.normal(self.seed, tag + "-rng", key, tick))
            self._raft_radar_fix(task, observer_x, observer_y, noisy, measured)
