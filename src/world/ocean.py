"""Time-varying ocean environment: tides, mixed layer, temperature/sound
speed, wind drift, seabed sediment and charted underwater hazards.

Everything here is a deterministic function of the world seed, the
bathymetry, the saved environment clock and one saved relaxation state (the
wind-mixing deepening of the surface layer).  The values are a game model of
real ocean processes; they are not claims about any real sea area.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.core import detrand

# --- tides -----------------------------------------------------------------
M2_PERIOD_S = 12.4206012 * 3600.0
S2_PERIOD_S = 12.0 * 3600.0
S2_TO_M2_RATIO = 0.46
TIDE_M2_AMPLITUDE_RANGE_M = (0.4, 1.4)
# Green's law shoaling a ~ h^-1/4, relative to the deep reference, bounded.
TIDE_REFERENCE_DEPTH_M = 400.0
TIDE_SHOALING_LIMITS = (0.6, 2.2)
# Spatial phase gradient of the tidal wave across the sector (rad per NM).
TIDE_PHASE_GRADIENT_MAX = 0.004

# --- mixed layer -----------------------------------------------------------
MLD_DIURNAL_AMPLITUDE_M = 8.0     # shallowest in the afternoon
MLD_DIURNAL_PEAK_HOUR = 15.0
MLD_WIND_THRESHOLD_KN = 12.0
MLD_WIND_DEEPENING_M_PER_KN = 1.2
MLD_DEEPEN_TAU_S = 2.0 * 3600.0   # storms mix down quickly
MLD_RESTRATIFY_TAU_S = 12.0 * 3600.0
MLD_WIND_MIX_MAX_M = 60.0
INTERNAL_WAVES = 3
INTERNAL_WAVE_AMPLITUDE_M = 2.0   # per component
MLD_MIN_M = 10.0
MLD_MAX_M = 250.0

# --- temperature / sound speed -----------------------------------------------
SALINITY_PSU = 35.0
DEEP_TEMPERATURE_C = 4.0
THERMOCLINE_SCALE_M = 150.0
SST_MEAN_C = 13.0
SST_SEASONAL_AMPLITUDE_C = 5.0
SST_WARMEST_DAY = 225
SST_DIURNAL_AMPLITUDE_C = 0.5

# --- wind drift --------------------------------------------------------------
WIND_DRIFT_FACTOR = 0.03
WIND_DRIFT_DEFLECTION_DEG = 20.0   # to the right (northern hemisphere)

# --- seabed ------------------------------------------------------------------
SEABED_GRID = 12
# Hamilton-style geoacoustic classes: density ratio, sound-speed ratio,
# attenuation (dB/wavelength), Lambert backscatter coefficient mu (dB).
SEDIMENTS = {
    "rock":   (2.50, 2.50, 0.10, -17.0),
    "gravel": (2.00, 1.35, 0.80, -22.0),
    "sand":   (1.95, 1.15, 0.85, -27.0),
    "silt":   (1.70, 1.05, 1.00, -32.0),
    "mud":    (1.45, 0.99, 0.20, -37.0),
}
SEDIMENT_ORDER = ("rock", "gravel", "sand", "silt", "mud")

# --- hazards -----------------------------------------------------------------
MAX_HAZARDS = 64
ROCK_RADIUS_NM = 0.08
ROCK_MIN_TOP_M = 15.0


@dataclass(frozen=True, slots=True)
class Hazard:
    kind: str          # "wreck" | "rock"
    x_nm: float
    y_nm: float
    top_depth_m: float  # depth of the highest point below the surface
    length_m: float


def mackenzie_sound_speed(temperature_c: float, salinity_psu: float,
                          depth_m: float) -> float:
    """Mackenzie (1981) nine-term sound speed in sea water (m/s)."""
    t, s, d = temperature_c, salinity_psu, depth_m
    return (1448.96 + 4.591 * t - 5.304e-2 * t * t + 2.374e-4 * t ** 3
            + 1.340 * (s - 35.0) + 1.630e-2 * d + 1.675e-7 * d * d
            - 1.025e-2 * t * (s - 35.0) - 7.139e-13 * t * d ** 3)


def rayleigh_bottom_loss_db(sediment: str, grazing_deg: float) -> float:
    """Plane-wave fluid-fluid reflection loss at a sediment interface (dB)."""
    rho, nu, attenuation, _mu = SEDIMENTS[sediment]
    theta = math.radians(max(0.01, min(90.0, grazing_deg)))
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # R = (m sin t - sqrt(n^2 - cos^2 t)) / (m sin t + sqrt(n^2 - cos^2 t))
    # with m = rho2/rho1 and n = c1/c2; below the critical grazing angle
    # (cos t > n) the reflection is total.
    n = 1.0 / nu
    radicand = n * n - cos_t * cos_t
    if radicand <= 0.0:
        loss = 0.0
    else:
        root = math.sqrt(radicand)
        r = abs((rho * sin_t - root) / (rho * sin_t + root))
        loss = -20.0 * math.log10(max(r, 1e-6))
    # Sediment absorption adds a small grazing-dependent loss.
    return loss + 0.35 * attenuation * math.sin(theta)


class OceanEnvironment:
    """Deterministic ocean model attached to one ``World``."""

    def __init__(self, seed: int, size_nm: float, charted_depth):
        self.seed = int(seed)
        self.size_nm = float(size_nm)
        self.clock_s = 0.0
        self.wind_mix_m = 0.0
        low, high = TIDE_M2_AMPLITUDE_RANGE_M
        self.m2_amplitude_m = detrand.uniform(low, high, seed, "tide-m2-amp")
        self.m2_phase = detrand.phase(seed, "tide-m2-phase")
        self.s2_phase = detrand.phase(seed, "tide-s2-phase")
        grad = TIDE_PHASE_GRADIENT_MAX
        self.tide_kx = detrand.uniform(-grad, grad, seed, "tide-kx")
        self.tide_ky = detrand.uniform(-grad, grad, seed, "tide-ky")
        self.day_of_year = 1 + int(detrand.u01(seed, "season") * 365.0)
        self._waves = []
        for index in range(INTERNAL_WAVES):
            period = detrand.uniform(1200.0, 3600.0, seed, "iw-period", index)
            wavelength = detrand.uniform(2.0, 8.0, seed, "iw-length", index)
            heading = detrand.phase(seed, "iw-heading", index)
            k = 2.0 * math.pi / wavelength
            self._waves.append((k * math.sin(heading), -k * math.cos(heading),
                                2.0 * math.pi / period,
                                detrand.phase(seed, "iw-phase", index)))
        self._sediment = self._build_sediment(charted_depth)
        self.hazards = self._build_hazards(charted_depth)
        # Bucket rocks by 1-NM cell so depth queries stay O(1).
        self._rock_cells: dict[tuple[int, int], list[Hazard]] = {}
        for hazard in self.hazards:
            if hazard.kind == "rock":
                cell = (int(hazard.x_nm), int(hazard.y_nm))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        self._rock_cells.setdefault(
                            (cell[0] + dx, cell[1] + dy), []).append(hazard)

    # --- construction -------------------------------------------------------

    def _build_sediment(self, charted_depth) -> list[list[str]]:
        n = SEABED_GRID
        step = self.size_nm / (n - 1)
        grid = []
        for row in range(n):
            line = []
            for col in range(n):
                x, y = col * step, row * step
                depth = max(1.0, charted_depth(x, y))
                slope = 0.0
                for dx, dy in ((step * .5, 0.0), (0.0, step * .5)):
                    a = charted_depth(min(self.size_nm, x + dx),
                                      min(self.size_nm, y + dy))
                    b = charted_depth(max(0.0, x - dx), max(0.0, y - dy))
                    slope = max(slope, abs(a - b) / max(step, 1e-6))
                # Steep and shallow ground is coarse; deep, flat basins
                # collect fine sediment.  A seeded jitter breaks up bands.
                score = (math.log10(depth) * 1.2 - min(2.0, slope / 40.0)
                         + detrand.uniform(-0.5, 0.5, self.seed, "sed", row, col))
                index = int(max(0, min(len(SEDIMENT_ORDER) - 1, score - 1.0)))
                line.append(SEDIMENT_ORDER[index])
            grid.append(line)
        return grid

    def _build_hazards(self, charted_depth) -> tuple[Hazard, ...]:
        hazards = []
        attempts = 0
        while len(hazards) < MAX_HAZARDS and attempts < MAX_HAZARDS * 4:
            attempts += 1
            x = detrand.uniform(0.02, 0.98, self.seed, "hz-x", attempts) * self.size_nm
            y = detrand.uniform(0.02, 0.98, self.seed, "hz-y", attempts) * self.size_nm
            depth = charted_depth(x, y)
            if depth <= 5.0:
                continue
            is_rock = 30.0 < depth < 150.0 and detrand.u01(
                self.seed, "hz-kind", attempts) < 0.35
            if is_rock:
                # Submerged pinnacles: a hazard to submarines and weapons,
                # never shallower than surface-ship keel clearance.
                top = depth * detrand.uniform(0.4, 0.9, self.seed, "hz-top",
                                              attempts)
                hazards.append(Hazard("rock", x, y, max(ROCK_MIN_TOP_M, top),
                                      60.0))
            else:
                length = detrand.uniform(40.0, 180.0, self.seed, "hz-len", attempts)
                hazards.append(Hazard("wreck", x, y, max(1.0, depth - 12.0),
                                      length))
        return tuple(hazards)

    # --- tides ----------------------------------------------------------------

    def tide_m(self, x_nm: float, y_nm: float, charted_depth_m: float) -> float:
        spatial = self.tide_kx * x_nm + self.tide_ky * y_nm
        t = self.clock_s
        base = (self.m2_amplitude_m * math.cos(
                    2.0 * math.pi * t / M2_PERIOD_S + self.m2_phase + spatial)
                + S2_TO_M2_RATIO * self.m2_amplitude_m * math.cos(
                    2.0 * math.pi * t / S2_PERIOD_S + self.s2_phase + spatial))
        depth = max(1.0, charted_depth_m)
        low, high = TIDE_SHOALING_LIMITS
        shoal = min(high, max(low, (TIDE_REFERENCE_DEPTH_M / depth) ** 0.25))
        return base * shoal

    # --- mixed layer ------------------------------------------------------------

    def wind_mix_target_m(self, wind_kn: float) -> float:
        return min(MLD_WIND_MIX_MAX_M, max(
            0.0, (wind_kn - MLD_WIND_THRESHOLD_KN) * MLD_WIND_DEEPENING_M_PER_KN))

    def update(self, dt: float, wind_kn: float) -> None:
        if dt <= 0.0:
            return
        self.clock_s += dt
        target = self.wind_mix_target_m(wind_kn)
        tau = (MLD_DEEPEN_TAU_S if target > self.wind_mix_m
               else MLD_RESTRATIFY_TAU_S)
        # Exact first-order relaxation, independent of step size.
        self.wind_mix_m = target + (self.wind_mix_m - target) * math.exp(-dt / tau)

    def mixed_layer_depth_m(self, base_m: float, hour: float,
                            x_nm: float, y_nm: float) -> float:
        diurnal = -MLD_DIURNAL_AMPLITUDE_M * math.cos(
            2.0 * math.pi * (hour - MLD_DIURNAL_PEAK_HOUR) / 24.0)
        waves = sum(INTERNAL_WAVE_AMPLITUDE_M * math.sin(
            kx * x_nm + ky * y_nm - omega * self.clock_s + phase)
            for kx, ky, omega, phase in self._waves)
        return min(MLD_MAX_M, max(MLD_MIN_M,
                                  base_m + diurnal + self.wind_mix_m + waves))

    # --- temperature / sound speed ------------------------------------------------

    def sea_surface_temperature_c(self, hour: float) -> float:
        seasonal = SST_SEASONAL_AMPLITUDE_C * math.cos(
            2.0 * math.pi * (self.day_of_year - SST_WARMEST_DAY) / 365.0)
        diurnal = SST_DIURNAL_AMPLITUDE_C * math.cos(
            2.0 * math.pi * (hour - MLD_DIURNAL_PEAK_HOUR) / 24.0)
        return SST_MEAN_C + seasonal + diurnal

    def temperature_c(self, depth_m: float, mld_m: float, sst_c: float) -> float:
        if depth_m <= mld_m:
            # Nearly isothermal surface layer.
            return sst_c - 0.002 * depth_m
        surface = sst_c - 0.002 * mld_m
        return DEEP_TEMPERATURE_C + (surface - DEEP_TEMPERATURE_C) * math.exp(
            -(depth_m - mld_m) / THERMOCLINE_SCALE_M)

    def sound_speed_m_s(self, depth_m: float, mld_m: float, hour: float) -> float:
        sst = self.sea_surface_temperature_c(hour)
        return mackenzie_sound_speed(self.temperature_c(depth_m, mld_m, sst),
                                     SALINITY_PSU, depth_m)

    # --- wind drift -------------------------------------------------------------

    @staticmethod
    def wind_drift_kn(wind_from_deg: float, wind_kn: float) -> tuple[float, float]:
        """Surface drift (u east, v north) = 3 % of wind, 20 deg to the right."""
        towards = math.radians((wind_from_deg + 180.0
                                + WIND_DRIFT_DEFLECTION_DEG) % 360.0)
        speed = WIND_DRIFT_FACTOR * max(0.0, wind_kn)
        return speed * math.sin(towards), speed * math.cos(towards)

    # --- seabed ----------------------------------------------------------------

    def sediment_at(self, x_nm: float, y_nm: float) -> str:
        n = SEABED_GRID
        step = self.size_nm / (n - 1)
        col = int(round(min(max(x_nm, 0.0), self.size_nm) / step))
        row = int(round(min(max(y_nm, 0.0), self.size_nm) / step))
        return self._sediment[min(n - 1, row)][min(n - 1, col)]

    def rock_top_depth_m(self, x_nm: float, y_nm: float) -> float | None:
        """Shallowest charted rock top covering this point, if any."""
        best = None
        for hazard in self._rock_cells.get((int(x_nm), int(y_nm)), ()):
            if math.hypot(hazard.x_nm - x_nm, hazard.y_nm - y_nm) <= ROCK_RADIUS_NM:
                if best is None or hazard.top_depth_m < best:
                    best = hazard.top_depth_m
        return best

    # --- persistence -------------------------------------------------------------

    def serialize(self) -> dict:
        return {"clock_s": self.clock_s, "wind_mix_m": self.wind_mix_m}

    @staticmethod
    def valid_state(state) -> bool:
        if not isinstance(state, dict) or set(state) != {"clock_s", "wind_mix_m"}:
            return False
        for key, high in (("clock_s", 1e12), ("wind_mix_m", MLD_WIND_MIX_MAX_M)):
            value = state[key]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not 0.0 <= value <= high):
                return False
        return True

    def restore(self, state: dict) -> None:
        self.clock_s = float(state["clock_s"])
        self.wind_mix_m = float(state["wind_mix_m"])
