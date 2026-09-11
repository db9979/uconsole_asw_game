"""Deterministic fictional battery, AIP, snorkel, and radio endurance model."""

from dataclasses import dataclass
import math

from src.data.catalog import EnduranceProfile


PHASES = ("SUBMERGED", "AIP", "ASCENDING", "SNORKEL", "RADIO", "DESCENDING")
SURFACE_PHASES = frozenset(("ASCENDING", "SNORKEL", "RADIO", "DESCENDING"))
STATE_FIELDS = {
    "version", "phase", "battery_kwh", "aip_energy_kwh", "return_depth_m",
    "radio_left_s",
}


@dataclass(frozen=True, slots=True)
class EnergyFlow:
    load_kwh: float
    served_kwh: float
    generator_kwh: float
    aip_kwh: float
    curtailed_kwh: float


class SubmarineEndurance:
    VERSION = 1
    DEPTH_TOLERANCE_M = 0.05
    MAX_STEP_S = 1.0
    MAX_SUBSTEPS = 1024
    ENERGY_EPSILON_KWH = 1e-12

    def __init__(self, profile: EnduranceProfile):
        self.profile = profile
        self.phase = "SUBMERGED"
        self.battery_kwh = profile.battery_capacity_kwh
        self.aip_energy_kwh = profile.aip_energy_kwh or 0.0
        self.return_depth_m = profile.snorkel_depth_m
        self.radio_left_s = 0.0
        self.last_flow = EnergyFlow(0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def surface_operation(self) -> bool:
        return self.phase in SURFACE_PHASES

    @property
    def transmitting(self) -> bool:
        return self.phase == "RADIO"

    def load_kw(self, speed_kn: float, maximum_speed_kn: float) -> float:
        ratio = min(1.0, max(0.0, speed_kn) / max(maximum_speed_kn, 1e-9))
        return (self.profile.hotel_load_kw
                + self.profile.propulsion_max_kw
                * ratio ** self.profile.propulsion_exponent)

    def _start_reserve_cycle(self, depth_m: float) -> None:
        if self.phase not in ("SUBMERGED", "AIP"):
            return
        start = self.profile.battery_capacity_kwh * self.profile.reserve_start_fraction
        stop = self.profile.battery_capacity_kwh * self.profile.reserve_stop_fraction
        if self.phase == "AIP" and self.battery_kwh >= stop - self.ENERGY_EPSILON_KWH:
            self.battery_kwh = max(self.battery_kwh, stop)
            self.phase = "SUBMERGED"
        if self.phase == "SUBMERGED" and self.battery_kwh <= start + self.ENERGY_EPSILON_KWH:
            self.battery_kwh = min(self.battery_kwh, start)
            if self.profile.aip_power_kw is not None and self.aip_energy_kwh > 0.0:
                self.phase = "AIP"
            else:
                self.return_depth_m = max(depth_m, self.profile.snorkel_depth_m)
                self.phase = "ASCENDING"
        elif (self.phase == "AIP"
              and self.aip_energy_kwh <= self.ENERGY_EPSILON_KWH):
            self.aip_energy_kwh = 0.0
            self.return_depth_m = max(depth_m, self.profile.snorkel_depth_m)
            self.phase = "ASCENDING"

    def _advance_instantaneous(self, depth_m: float) -> None:
        self._start_reserve_cycle(depth_m)
        reached_snorkel = depth_m <= (
            self.profile.snorkel_depth_m + self.DEPTH_TOLERANCE_M)
        if self.phase == "ASCENDING" and reached_snorkel:
            self.phase = "SNORKEL"
        elif (self.phase == "SNORKEL" and self.battery_kwh >=
              self.profile.battery_capacity_kwh * self.profile.reserve_stop_fraction):
            self.phase = "RADIO"
            self.radio_left_s = self.profile.radio_duration_s
        elif (self.phase == "DESCENDING" and depth_m >=
              self.return_depth_m - self.DEPTH_TOLERANCE_M):
            self.phase = "SUBMERGED"
        self._start_reserve_cycle(depth_m)

    def supported_speed(self, dt: float, demanded_speed_kn: float,
                        maximum_speed_kn: float, depth_m: float) -> float:
        """Cap demand to propulsion energy that can be served this interval."""
        self._validate_inputs(dt, demanded_speed_kn, maximum_speed_kn, depth_m)
        if dt == 0.0:
            return demanded_speed_kn
        self._advance_instantaneous(depth_m)
        hours = dt / 3600.0
        source_kwh = self.battery_kwh
        if self.phase == "AIP" and self.profile.aip_power_kw is not None:
            source_kwh += min(self.aip_energy_kwh,
                              self.profile.aip_power_kw * hours)
        if (self.phase in ("SNORKEL", "RADIO")
                and depth_m <= self.profile.snorkel_depth_m + self.DEPTH_TOLERANCE_M):
            generator_s = (min(dt, self.radio_left_s)
                           if self.phase == "RADIO" else dt)
            source_kwh += self.profile.generator_power_kw * generator_s / 3600.0
        supported_load_kw = source_kwh / hours
        propulsion_kw = max(0.0, supported_load_kw - self.profile.hotel_load_kw)
        ratio = min(1.0, propulsion_kw / self.profile.propulsion_max_kw) ** (
            1.0 / self.profile.propulsion_exponent)
        return min(demanded_speed_kn, maximum_speed_kn * ratio)

    def time_until_surface_operation(self, dt: float, speed_kn: float,
                                     maximum_speed_kn: float,
                                     depth_m: float) -> float:
        """Return the submerged part of an interval before ascent begins."""
        self._validate_inputs(dt, speed_kn, maximum_speed_kn, depth_m)
        self._advance_instantaneous(depth_m)
        if self.surface_operation or dt == 0.0:
            return 0.0
        first_event = self._seconds_to_event(
            speed_kn, maximum_speed_kn, depth_m)
        if first_event is None or first_event >= dt:
            return dt

        probe = SubmarineEndurance(self.profile)
        probe.phase = self.phase
        probe.battery_kwh = self.battery_kwh
        probe.aip_energy_kwh = self.aip_energy_kwh
        probe.return_depth_m = self.return_depth_m
        probe.radio_left_s = self.radio_left_s
        elapsed = 0.0
        for _ in range(self.MAX_SUBSTEPS):
            probe._advance_instantaneous(depth_m)
            if probe.surface_operation:
                return elapsed
            event = probe._seconds_to_event(
                speed_kn, maximum_speed_kn, depth_m)
            if event is None or elapsed + event >= dt:
                return dt
            if event <= 0.0:
                return elapsed if probe.surface_operation else dt
            probe._update_step(event, speed_kn, maximum_speed_kn, depth_m)
            elapsed += event
        return dt

    def _seconds_to_event(self, speed_kn: float, maximum_speed_kn: float,
                          depth_m: float) -> float | None:
        load_rate = self.load_kw(speed_kn, maximum_speed_kn) / 3600.0
        if self.phase == "SUBMERGED" and load_rate > 0.0:
            start = (self.profile.battery_capacity_kwh
                     * self.profile.reserve_start_fraction)
            return max(0.0, (self.battery_kwh - start) / load_rate)
        if self.phase == "AIP" and self.profile.aip_power_kw is not None:
            aip_rate = self.profile.aip_power_kw / 3600.0
            times = [self.aip_energy_kwh / aip_rate]
            charge_rate = aip_rate - load_rate
            if charge_rate > 0.0:
                stop = (self.profile.battery_capacity_kwh
                        * self.profile.reserve_stop_fraction)
                times.append(max(0.0, (stop - self.battery_kwh) / charge_rate))
            return min(times)
        if self.phase == "SNORKEL" and depth_m <= (
                self.profile.snorkel_depth_m + self.DEPTH_TOLERANCE_M):
            charge_rate = self.profile.generator_power_kw / 3600.0 - load_rate
            if charge_rate > 0.0:
                stop = (self.profile.battery_capacity_kwh
                        * self.profile.reserve_stop_fraction)
                return max(0.0, (stop - self.battery_kwh) / charge_rate)
        if self.phase == "RADIO":
            return self.radio_left_s
        return None

    @staticmethod
    def _validate_inputs(dt: float, speed_kn: float, maximum_speed_kn: float,
                         depth_m: float) -> None:
        if not math.isfinite(dt) or dt < 0.0:
            raise ValueError("endurance dt must be finite and non-negative")
        if (not all(math.isfinite(value) for value in (
                speed_kn, maximum_speed_kn, depth_m)) or speed_kn < 0.0
                or maximum_speed_kn <= 0.0 or depth_m < 0.0):
            raise ValueError("endurance inputs must be finite and bounded")

    def update(self, dt: float, speed_kn: float, maximum_speed_kn: float,
               depth_m: float) -> EnergyFlow:
        self._validate_inputs(dt, speed_kn, maximum_speed_kn, depth_m)
        totals = [0.0] * 5
        remaining = dt
        max_step = max(self.MAX_STEP_S, dt / self.MAX_SUBSTEPS)
        for index in range(self.MAX_SUBSTEPS):
            if remaining <= 0.0:
                break
            self._advance_instantaneous(depth_m)
            step = (remaining if index == self.MAX_SUBSTEPS - 1
                    else min(max_step, remaining))
            event = self._seconds_to_event(speed_kn, maximum_speed_kn, depth_m)
            if (index < self.MAX_SUBSTEPS - 1
                    and event is not None and event > 0.0):
                step = min(step, event)
            flow = self._update_step(step, speed_kn, maximum_speed_kn, depth_m)
            for index, value in enumerate((
                    flow.load_kwh, flow.served_kwh, flow.generator_kwh,
                    flow.aip_kwh, flow.curtailed_kwh)):
                totals[index] += value
            remaining = max(0.0, remaining - step)
        if dt == 0.0:
            self._advance_instantaneous(depth_m)
        self.last_flow = EnergyFlow(*totals)
        return self.last_flow

    def _update_step(self, dt: float, speed_kn: float, maximum_speed_kn: float,
                     depth_m: float) -> EnergyFlow:
        self._advance_instantaneous(depth_m)
        hours = dt / 3600.0
        load = self.load_kw(speed_kn, maximum_speed_kn) * hours
        aip = 0.0
        if self.phase == "AIP" and self.profile.aip_power_kw is not None:
            aip = min(self.aip_energy_kwh, self.profile.aip_power_kw * hours)
            self.aip_energy_kwh -= aip
        generator = 0.0
        if (self.phase in ("SNORKEL", "RADIO")
                and depth_m <= self.profile.snorkel_depth_m + self.DEPTH_TOLERANCE_M):
            generator = self.profile.generator_power_kw * hours

        available = self.battery_kwh + aip + generator
        served = min(load, available)
        after_load = available - served
        self.battery_kwh = min(self.profile.battery_capacity_kwh, after_load)
        curtailed = after_load - self.battery_kwh
        self.aip_energy_kwh = max(0.0, self.aip_energy_kwh)
        flow = EnergyFlow(load, served, generator, aip, curtailed)
        if self.phase == "RADIO":
            self.radio_left_s = max(0.0, self.radio_left_s - dt)
            if self.radio_left_s == 0.0:
                self.phase = "DESCENDING"
        self._advance_instantaneous(depth_m)
        return flow

    def serialize(self) -> dict:
        return {
            "version": self.VERSION,
            "phase": self.phase,
            "battery_kwh": self.battery_kwh,
            "aip_energy_kwh": self.aip_energy_kwh,
            "return_depth_m": self.return_depth_m,
            "radio_left_s": self.radio_left_s,
        }

    @classmethod
    def restore(cls, profile: EnduranceProfile, state: dict) -> "SubmarineEndurance":
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            raise ValueError("invalid endurance state fields")
        if type(state["version"]) is not int or state["version"] != cls.VERSION:
            raise ValueError("unsupported endurance state version")
        if state["phase"] not in PHASES:
            raise ValueError("invalid endurance phase")
        if state["phase"] == "AIP" and profile.aip_power_kw is None:
            raise ValueError("AIP phase requires an AIP profile")
        limits = {
            "battery_kwh": profile.battery_capacity_kwh,
            "aip_energy_kwh": profile.aip_energy_kwh or 0.0,
            "return_depth_m": 2000.0,
            "radio_left_s": profile.radio_duration_s,
        }
        for field, high in limits.items():
            value = state[field]
            if type(value) not in (int, float) or not math.isfinite(value) \
                    or not 0.0 <= value <= high:
                raise ValueError(f"invalid endurance state {field}")
        if state["phase"] == "RADIO" and state["radio_left_s"] <= 0.0:
            raise ValueError("radio phase requires remaining duration")
        if state["phase"] != "RADIO" and state["radio_left_s"] != 0.0:
            raise ValueError("radio duration outside radio phase")
        result = cls(profile)
        result.phase = state["phase"]
        result.battery_kwh = float(state["battery_kwh"])
        result.aip_energy_kwh = float(state["aip_energy_kwh"])
        result.return_depth_m = float(state["return_depth_m"])
        result.radio_left_s = float(state["radio_left_s"])
        return result
