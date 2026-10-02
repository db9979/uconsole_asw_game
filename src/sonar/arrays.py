"""Handling of the towed array (TAS) and the variable-depth sonar (VDS).

``ArrayHandlingMixin`` holds ``SonarSystem``'s streaming, retrieving,
depth and performance methods of both arrays, moved verbatim from
``sonar.py``; ``SonarSystem`` inherits them.
"""

from src.core import config
from src.sonar.contact import TowState


class ArrayHandlingMixin:
    """Tow/VDS handling half of ``SonarSystem`` (state lives on the instance)."""

    def toggle_tow(self, ship_speed: float = 0.0) -> bool:
        """Start/reverse array handling; progress pauses outside its envelope."""
        if self.tow_state == TowState.FAULT:
            return False
        if self.tow_state in (TowState.STOWED, TowState.RETRIEVING):
            self.tow_state = TowState.DEPLOYING
        else:
            self.tow_state = TowState.RETRIEVING
        self._tow_handling_ok = self._tow_speed_ok(ship_speed)
        self._tow_settle_s = 0.0
        return True

    @staticmethod
    def _tow_speed_ok(ship_speed: float) -> bool:
        return (config.SONAR_TOWED_HANDLING_MIN_KN <= ship_speed
                <= config.SONAR_TOWED_HANDLING_MAX_KN)

    def _tow_available(self) -> bool:
        return (self.tow_state == TowState.STREAMED
                and self.tow_payout >= config.SONAR_TOWED_AVAILABLE_PAYOUT)

    @property
    def tow_performance(self) -> float:
        """0..1 TAS benefit; full benefit requires streamed and settled cable."""
        if self.tow_state != TowState.STREAMED:
            return 0.0
        stability = config.clamp(
            self._tow_settle_s / config.SONAR_TOWED_SETTLE_S, 0.0, 1.0)
        return stability * config.clamp(self.tow_payout, 0.0, 1.0)

    def tow_status(self, ship_speed: float = None) -> dict:
        handling_ok = self._tow_handling_ok if ship_speed is None else \
            self._tow_speed_ok(ship_speed)
        return {
            "state": getattr(self.tow_state, "value", self.tow_state),
            "payout": self.tow_payout,
            "payout_percent": round(self.tow_payout * 100.0, 1),
            "available": self._tow_available(),
            "handling_ok": handling_ok,
            "performance": self.tow_performance,
            "depth_m": self.towed_depth_m,
            "depth_target_m": self.towed_depth_target_m,
            "heading_deg": self.tow_heading_deg,
        }

    def adjust_towed_depth(self, delta_m: float, ship_speed: float) -> float:
        if self.tow_state != TowState.STREAMED:
            return self.towed_depth_target_m
        limit = max(config.SONAR_TOWED_DEPTH_MIN_M,
                    config.SONAR_TOWED_DEPTH_MAX_M
                    - ship_speed * config.SONAR_TOWED_SPEED_SHALLOW_M_PER_KN)
        self.towed_depth_target_m = config.clamp(
            self.towed_depth_target_m + delta_m,
            config.SONAR_TOWED_DEPTH_MIN_M, limit)
        return self.towed_depth_target_m

    # --- Variable-depth sonar (VDS) -----------------------------------------

    @staticmethod
    def _vds_envelope_ok(ship_speed: float, sea_state: float) -> bool:
        return (config.SONAR_VDS_HANDLING_MIN_KN <= ship_speed
                <= config.SONAR_VDS_HANDLING_MAX_KN
                and sea_state <= config.SONAR_VDS_MAX_SEA_STATE)

    def toggle_vds(self, ship_speed: float = 0.0, sea_state: float = 0.0) -> bool:
        """Start/reverse lowering; progress pauses outside the handling envelope."""
        if self.vds_state == TowState.FAULT:
            return False
        if self.vds_state in (TowState.STOWED, TowState.RETRIEVING):
            self.vds_state = TowState.DEPLOYING
        else:
            self.vds_state = TowState.RETRIEVING
        self._vds_handling_ok = self._vds_envelope_ok(ship_speed, sea_state)
        self._vds_settle_s = 0.0
        return True

    def _vds_available(self) -> bool:
        return self.vds_state == TowState.STREAMED

    @property
    def vds_performance(self) -> float:
        """0..1 VDS benefit; the body settles after reaching its cable length."""
        if self.vds_state != TowState.STREAMED:
            return 0.0
        return config.clamp(self._vds_settle_s / config.SONAR_VDS_SETTLE_S, 0.0, 1.0)

    def vds_depth_limit_m(self, ship_speed: float) -> float:
        """Cable angle: the faster the ship, the shallower the body can go."""
        return max(config.SONAR_VDS_DEPTH_MIN_M,
                   config.SONAR_VDS_DEPTH_MAX_M
                   - ship_speed * config.SONAR_VDS_SPEED_SHALLOW_M_PER_KN)

    def vds_status(self, ship_speed: float = None, sea_state: float = None) -> dict:
        handling_ok = (self._vds_handling_ok if ship_speed is None or sea_state is None
                       else self._vds_envelope_ok(ship_speed, sea_state))
        return {
            "state": getattr(self.vds_state, "value", self.vds_state),
            "payout": self.vds_payout,
            "payout_percent": round(self.vds_payout * 100.0, 1),
            "available": self._vds_available(),
            "handling_ok": handling_ok,
            "performance": self.vds_performance,
            "depth_m": self.vds_depth_m,
            "depth_target_m": self.vds_depth_target_m,
        }

    def _update_vds(self, dt: float, speed: float, sea_state: float) -> None:
        if self.vds_payout > 0 and speed > config.SONAR_VDS_MAX_SAFE_KN:
            self.vds_state = TowState.FAULT
            self._vds_settle_s = 0.0
            return
        self._vds_handling_ok = self._vds_envelope_ok(speed, sea_state)
        if self.vds_state == TowState.DEPLOYING and self._vds_handling_ok:
            self.vds_payout = min(1.0, self.vds_payout + dt / config.SONAR_VDS_DEPLOY_S)
            if self.vds_payout >= 1.0:
                self.vds_state = TowState.STREAMED
                self._vds_settle_s = 0.0
        elif self.vds_state == TowState.RETRIEVING and self._vds_handling_ok:
            self.vds_payout = max(0.0, self.vds_payout - dt / config.SONAR_VDS_RETRIEVE_S)
            if self.vds_payout <= 0.0:
                self.vds_state = TowState.STOWED
        elif self.vds_state == TowState.STREAMED:
            self._vds_settle_s = min(config.SONAR_VDS_SETTLE_S, self._vds_settle_s + dt)
        if self.vds_state == TowState.STREAMED:
            self.vds_depth_target_m = min(self.vds_depth_target_m,
                                          self.vds_depth_limit_m(speed))
            step = config.SONAR_VDS_DEPTH_RATE_M_S * dt
            self.vds_depth_m += config.clamp(
                self.vds_depth_target_m - self.vds_depth_m, -step, step)

    def _update_tow(self, dt: float, speed: float, course: float) -> None:
        lag_fraction = config.clamp(dt / (config.SONAR_TOWED_HEADING_LAG_S + dt), 0, 1)
        self.tow_heading_deg = (self.tow_heading_deg
                                + config.angle_diff_deg(course, self.tow_heading_deg)
                                * lag_fraction) % 360.0
        if self.tow_payout > 0 and speed > config.SONAR_TOWED_MAX_SAFE_KN:
            self.tow_state = TowState.FAULT
            self._tow_settle_s = 0.0
            return
        self._tow_handling_ok = self._tow_speed_ok(speed)
        if self.tow_state == TowState.DEPLOYING and self._tow_handling_ok:
            self.tow_payout = min(1.0, self.tow_payout + dt / config.SONAR_TOWED_DEPLOY_S)
            if self.tow_payout >= 1.0:
                self.tow_state = TowState.STREAMED
                self._tow_settle_s = 0.0
        elif self.tow_state == TowState.RETRIEVING and self._tow_handling_ok:
            self.tow_payout = max(0.0, self.tow_payout - dt / config.SONAR_TOWED_RETRIEVE_S)
            if self.tow_payout <= 0.0:
                self.tow_state = TowState.STOWED
        elif self.tow_state == TowState.STREAMED:
            self._tow_settle_s = min(config.SONAR_TOWED_SETTLE_S,
                                     self._tow_settle_s + dt)
