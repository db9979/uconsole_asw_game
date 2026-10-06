"""Passive and active sonar equations in dB (per canonical band).

Passive:  SE = SL - TL - NL + DI - DT
Active:   SE = SL_a - 2 TL + TS - max(NL - DI, RL) - DT + PG

The terms are physical in shape (spherical spreading, Francois-Garrison
absorption, Wenz/Knudsen ambient noise, power-summed self noise, aspect
dependent target strength, bottom/surface/volume reverberation, pulse
processing gain).  The reference constants are calibrated so that at the
1.0.0 reference conditions the signal excess reproduces the historical
detection ranges (see ``tools/calibrate.py``).

Everything here is a pure function; nothing owns state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.core import config, detrand

BANDS_HZ = (100.0, 400.0, 1600.0, 6400.0)
NM_M = 1852.0

# --- calibration anchors -------------------------------------------------------
# Passive figure of merit: SE = 0 at the 1.0.0 base range (20 NM) for the
# reference target (quiet 1.0 -> target bonus 1) with no own-noise excess, sea
# state 1, reference ambient, bow array, direct path.
PASSIVE_REFERENCE_RANGE_NM = config.SONAR_PASSIVE_BASE_NM
# Active figure of merit: SE = 0 at SONAR_ACTIVE_BASE_NM for the reference
# target strength, sea state 0, bow array, noise limited.
ACTIVE_REFERENCE_RANGE_NM = config.SONAR_ACTIVE_BASE_NM
REFERENCE_SEA_STATE = 1.0
REFERENCE_SHIPPING_CONTACTS = 4
# Reference echo: a 70 m hull at 45 degrees aspect.
REFERENCE_TARGET_LENGTH_M = 70.0
REFERENCE_ASPECT_DEG = 45.0
# CW Doppler processing separates an echo from stationary reverberation once
# the target's radial speed exceeds this.
CW_DOPPLER_MIN_KN = 2.0
CW_DOPPLER_REJECTION_DB = 10.0

# --- ambient noise (spectrum level dB re 1 uPa^2/Hz) -------------------------------
# Knudsen wind noise at 1 kHz by sea state, falling 17 dB/decade.
KNUDSEN_1KHZ_DB = (44.5, 50.0, 55.0, 58.5, 61.5, 63.5, 65.5)
KNUDSEN_SLOPE_DB_PER_DECADE = -17.0
# Distant shipping peaks near 100 Hz and falls 20 dB/decade above.
SHIPPING_100HZ_DB = 60.0
SHIPPING_SLOPE_DB_PER_DECADE = -20.0
# Heavy rain adds a nearly flat 1-10 kHz spectrum.
RAIN_HEAVY_DB = 62.0
WIND_FLAT_BELOW_HZ = 500.0
# Hull-array self-noise floor (flow and machinery noise reaching the dome
# even at low speed); falls with frequency.
SELF_NOISE_FLOOR_100HZ_DB = 68.0
SELF_NOISE_FLOOR_SLOPE_DB_PER_DECADE = -12.0
THERMAL_NOISE_DB_AT_6K4 = 20.0

# --- pulses -------------------------------------------------------------------
PULSES = {
    # key: (duration s, bandwidth Hz)
    "CW": (1.0, 1.0),
    "LFM": (1.0, 100.0),
}
DEFAULT_PULSE = "CW"
# Scattering strengths (dB): Lambert bottom mu per sediment is in ocean.py;
# surface scattering from wind (Chapman-Harris-like), volume column.
VOLUME_SCATTERING_DB = -80.0


def _db_sum(*levels: float) -> float:
    """Incoherent power sum of dB levels."""
    return 10.0 * math.log10(sum(10.0 ** (level / 10.0) for level in levels))


def francois_garrison_db_per_km(frequency_hz: float, temperature_c: float = 10.0,
                                depth_m: float = 100.0, salinity: float = 35.0,
                                ph: float = 8.0) -> float:
    """Francois-Garrison (1982) sea-water absorption (dB/km)."""
    f = frequency_hz / 1000.0
    t = temperature_c
    c = 1412.0 + 3.21 * t + 1.19 * salinity + 0.0167 * depth_m
    # Boric acid
    a1 = 8.86 / c * 10.0 ** (0.78 * ph - 5.0)
    p1 = 1.0
    f1 = 2.8 * math.sqrt(salinity / 35.0) * 10.0 ** (4.0 - 1245.0 / (273.0 + t))
    # Magnesium sulphate
    a2 = 21.44 * salinity / c * (1.0 + 0.025 * t)
    p2 = 1.0 - 1.37e-4 * depth_m + 6.2e-9 * depth_m ** 2
    f2 = 8.17 * 10.0 ** (8.0 - 1990.0 / (273.0 + t)) / (1.0 + 0.0018 * (salinity - 35.0))
    # Pure water
    if t <= 20.0:
        a3 = (4.937e-4 - 2.59e-5 * t + 9.11e-7 * t * t - 1.5e-8 * t ** 3)
    else:
        a3 = (3.964e-4 - 1.146e-5 * t + 1.45e-7 * t * t - 6.5e-10 * t ** 3)
    p3 = 1.0 - 3.83e-5 * depth_m + 4.9e-10 * depth_m ** 2
    return (a1 * p1 * f1 * f * f / (f1 * f1 + f * f)
            + a2 * p2 * f2 * f * f / (f2 * f2 + f * f)
            + a3 * p3 * f * f)


def spreading_loss_db(distance_nm: float) -> float:
    """Spherical spreading 20 log10(r) with r in metres (>= 1 m)."""
    return 20.0 * math.log10(max(1.0, distance_nm * NM_M))


def ambient_noise_db(frequency_hz: float, sea_state: float, rain: float = 0.0,
                     shipping_contacts: int = REFERENCE_SHIPPING_CONTACTS) -> float:
    """Wenz-style ambient spectrum level: wind + shipping + rain + thermal."""
    index = max(0.0, min(6.0, sea_state))
    low = int(index)
    high = min(6, low + 1)
    wind_1k = (KNUDSEN_1KHZ_DB[low]
               + (KNUDSEN_1KHZ_DB[high] - KNUDSEN_1KHZ_DB[low]) * (index - low))
    # Wenz: wind noise is roughly flat below ~500 Hz.
    decades = math.log10(max(frequency_hz, WIND_FLAT_BELOW_HZ) / 1000.0)
    wind = wind_1k + KNUDSEN_SLOPE_DB_PER_DECADE * decades
    traffic = max(0, shipping_contacts)
    shipping = (SHIPPING_100HZ_DB
                + 10.0 * math.log10((1.0 + traffic) / (1.0 + REFERENCE_SHIPPING_CONTACTS))
                + SHIPPING_SLOPE_DB_PER_DECADE * max(0.0, math.log10(frequency_hz / 100.0)))
    levels = [wind, shipping,
              THERMAL_NOISE_DB_AT_6K4 + 20.0 * math.log10(frequency_hz / 6400.0)]
    if rain > 0.0 and frequency_hz >= 500.0:
        levels.append(RAIN_HEAVY_DB + 10.0 * math.log10(max(rain, 1e-3)))
    return _db_sum(*levels)


def self_noise_floor_db(frequency_hz: float) -> float:
    return (SELF_NOISE_FLOOR_100HZ_DB + SELF_NOISE_FLOOR_SLOPE_DB_PER_DECADE
            * math.log10(frequency_hz / 100.0))


def reference_noise_db(frequency_hz: float) -> float:
    """Reference ambient at sea state 1 power-summed with the self floor."""
    return _db_sum(ambient_noise_db(frequency_hz, REFERENCE_SEA_STATE),
                   self_noise_floor_db(frequency_hz))


def self_noise_db(frequency_hz: float, legacy_range_factor: float) -> float:
    """Speed-dependent own-ship self noise above the floor.

    The 1.0.0 model multiplied range by ``legacy_range_factor`` (own noise,
    cavitation, directional lobe).  With power summation over the reference
    noise, a penalty of L dB needs an extra level
    ``N_ref + 10 log10(10^(L/10) - 1)``; it is then a real spectrum level
    that adds to whatever the ambient actually is.
    """
    floor = self_noise_floor_db(frequency_hz)
    loss = -20.0 * math.log10(max(1e-4, min(1.0, legacy_range_factor)))
    if loss <= 1e-6:
        return floor
    extra = reference_noise_db(frequency_hz) + 10.0 * math.log10(
        10.0 ** (loss / 10.0) - 1.0)
    return _db_sum(floor, extra)


@dataclass(frozen=True, slots=True)
class PassiveTerms:
    frequency_hz: float
    source_level_db: float
    transmission_loss_db: float
    noise_level_db: float
    directivity_db: float
    threshold_db: float

    @property
    def signal_excess_db(self) -> float:
        return (self.source_level_db - self.transmission_loss_db
                - self.noise_level_db + self.directivity_db - self.threshold_db)


def passive_figure_of_merit_offset(frequency_hz: float) -> float:
    """SL_ref + DI_ref - DT_ref so that SE = 0 at the reference range."""
    return spreading_loss_db(PASSIVE_REFERENCE_RANGE_NM) + reference_noise_db(
        frequency_hz)


def passive_terms(*, frequency_hz: float, distance_nm: float,
                  target_bonus: float, excess_path_loss_db: float,
                  absorption_db_per_km: float, legacy_absorption_db: float,
                  own_range_factor: float, array_range_factor: float,
                  sea_state: float, rain: float, shipping_contacts: int,
                  sensitivity_db: float = 0.0,
                  hull_self_noise: bool = True,
                  threshold_db: float = 0.0,
                  reference_absorption_db: float = 0.0) -> PassiveTerms:
    """Assemble the passive sonar equation for one band.

    ``target_bonus`` is the 1.0.0 source-level multiplier (louder target),
    expressed here as +20 log10 dB of source level; the array factor becomes
    directivity; path excess (layer, surface/bottom/refraction) and the
    Francois-Garrison absorption replace the legacy fixed absorption.
    ``threshold_db`` is the operator's recognition differential above the
    calibrated 0 dB (a tired watch needs a stronger signal).
    ``reference_absorption_db`` credits the absorption already contained in
    a figure of merit anchored at a shorter reference range; it is applied
    outside the path-excess bound so it is never lost there.
    """
    anchor = passive_figure_of_merit_offset(frequency_hz)
    source = anchor + 20.0 * math.log10(max(target_bonus, 1e-6))
    absorption = absorption_db_per_km * distance_nm * NM_M / 1000.0
    transmission = (spreading_loss_db(distance_nm) + max(
        0.0, excess_path_loss_db - legacy_absorption_db) + absorption
        - reference_absorption_db)
    ambient = ambient_noise_db(frequency_hz, sea_state, rain, shipping_contacts)
    directivity = 20.0 * math.log10(max(array_range_factor, 1e-6)) + sensitivity_db
    if hull_self_noise:
        noise = _db_sum(ambient, self_noise_db(frequency_hz, own_range_factor))
    else:
        # Off-board sensors (dipping sonar, sonobuoys) are ambient limited;
        # their smaller aperture is the directivity difference to the hull
        # array at the reference noise.
        noise = ambient
        directivity -= reference_noise_db(frequency_hz) - ambient_noise_db(
            frequency_hz, REFERENCE_SEA_STATE)
    return PassiveTerms(frequency_hz, source, transmission, noise, directivity,
                        threshold_db)


# --- active ---------------------------------------------------------------------


def target_strength_db(length_m: float, aspect_deg: float) -> float:
    """Aspect-dependent echo strength of an elongated hull.

    Beam aspect returns a specular highlight ~20 log10(L/10) + 8 dB; bow and
    stern aspects are about 15 dB weaker.
    """
    beam = 20.0 * math.log10(max(length_m, 5.0) / 10.0) + 8.0
    weight = abs(math.sin(math.radians(aspect_deg))) ** 2
    return beam - 15.0 * (1.0 - weight)


def surface_scattering_db(wind_kn: float, grazing_deg: float) -> float:
    """Chapman-Harris-like surface backscatter (dB), rising with wind."""
    grazing = max(0.5, min(89.0, grazing_deg))
    return -60.0 + 0.9 * min(40.0, wind_kn) + 10.0 * math.log10(
        math.sin(math.radians(grazing)))


def bottom_scattering_db(lambert_mu_db: float, grazing_deg: float) -> float:
    """Lambert's law: mu + 10 log10(sin^2 theta)."""
    grazing = max(0.5, min(89.0, grazing_deg))
    return lambert_mu_db + 20.0 * math.log10(math.sin(math.radians(grazing)))


def reverberation_level_db(*, source_level_db: float, distance_nm: float,
                           pulse: str, beamwidth_deg: float,
                           water_depth_m: float, lambert_mu_db: float,
                           wind_kn: float, sensor_depth_m: float = 7.0) -> float:
    """Boundary + volume reverberation at the target range.

    The surface patch is seen at the grazing angle the sensor's own depth
    gives; the seabed returns only once the range gate (slant range ``r``)
    has reached it, at the grazing angle of the water below the sensor."""
    r = max(1.0, distance_nm * NM_M)
    # Ensonified boundary patch: the pulse's range cell (c*tau/2 for CW,
    # c/2B after pulse compression for LFM) times cross-range r*theta.
    cell = range_resolution_m(pulse)
    beam = math.radians(beamwidth_deg)
    area = cell * r * beam
    two_way = 2.0 * spreading_loss_db(distance_nm)
    surface_graze = math.degrees(math.asin(min(1.0, max(0.5, sensor_depth_m) / r)))
    levels = [source_level_db - two_way + surface_scattering_db(wind_kn, surface_graze)
              + 10.0 * math.log10(area)]
    height = max(1.0, water_depth_m - sensor_depth_m)
    if r > height:
        graze = math.degrees(math.asin(height / r))
        patch = min(cell / max(math.cos(math.radians(graze)), 0.05) * r * beam,
                    math.pi * r * r)
        levels.append(source_level_db - two_way
                      + bottom_scattering_db(lambert_mu_db, graze) + 10.0 * math.log10(patch))
    levels.append(source_level_db - two_way + VOLUME_SCATTERING_DB
                  + 10.0 * math.log10(area * max(1.0, min(water_depth_m, 500.0))))
    return _db_sum(*levels)


@dataclass(frozen=True, slots=True)
class ActiveTerms:
    source_level_db: float
    two_way_loss_db: float
    target_strength_db: float
    noise_db: float
    reverberation_db: float
    processing_gain_db: float
    reverberation_rejection_db: float = 0.0

    @property
    def signal_excess_db(self) -> float:
        interference = max(self.noise_db - self.processing_gain_db,
                           self.reverberation_db - self.reverberation_rejection_db)
        return (self.source_level_db - self.two_way_loss_db
                + self.target_strength_db - interference)

    @property
    def reverberation_limited(self) -> bool:
        return (self.reverberation_db - self.reverberation_rejection_db
                > self.noise_db - self.processing_gain_db)


ACTIVE_FREQUENCY_HZ = 3500.0     # medium-frequency hull sonar
ACTIVE_BEAMWIDTH_DEG = 12.0

SOUND_SPEED_M_S = 1500.0
DOPPLER_FREE_KN = 0.5


def echo_merges_with_clutter(target_range_m: float, target_bearing_deg: float,
                             target_radial_kn: float, clutter_range_m: float,
                             clutter_bearing_deg: float, pulse: str,
                             beamwidth_deg: float = ACTIVE_BEAMWIDTH_DEG) -> bool:
    """True when a target echo cannot be separated from a clutter echo: no
    Doppler to tell it apart, inside the same range cell and the same beam."""
    if abs(target_radial_kn) >= DOPPLER_FREE_KN:
        return False
    bearing_gap = abs((target_bearing_deg - clutter_bearing_deg + 180.0) % 360.0 - 180.0)
    return (abs(target_range_m - clutter_range_m) < range_resolution_m(pulse)
            and bearing_gap < beamwidth_deg / 2.0)


def active_noise_db(sea_state: float, rain: float = 0.0) -> float:
    return _db_sum(ambient_noise_db(ACTIVE_FREQUENCY_HZ, sea_state, rain),
                   self_noise_floor_db(ACTIVE_FREQUENCY_HZ))


def reference_target_strength_db() -> float:
    return target_strength_db(REFERENCE_TARGET_LENGTH_M, REFERENCE_ASPECT_DEG)


REFERENCE_WATER_TEMPERATURE_C = 10.0


def _two_way_absorption_db(distance_nm: float, absorption_db_per_km: float) -> float:
    return 2.0 * absorption_db_per_km * distance_nm * NM_M / 1000.0


def _active_budget_db(distance_nm: float) -> float:
    absorption = francois_garrison_db_per_km(ACTIVE_FREQUENCY_HZ,
                                             REFERENCE_WATER_TEMPERATURE_C)
    return (2.0 * spreading_loss_db(distance_nm)
            + _two_way_absorption_db(distance_nm, absorption))


def active_range_factor_db(factor: float) -> float:
    """Two-way loss (dB) that scales the reference active range by ``factor``
    on the real spreading+absorption curve (negative for factor > 1)."""
    factor = max(factor, 1e-6)
    return (_active_budget_db(ACTIVE_REFERENCE_RANGE_NM)
            - _active_budget_db(ACTIVE_REFERENCE_RANGE_NM * factor))


def active_source_level_db() -> float:
    """Transmit level such that SE = 0 at the reference range, sea state 0,
    reference target strength, reference water temperature, noise limited."""
    absorption = francois_garrison_db_per_km(ACTIVE_FREQUENCY_HZ,
                                             REFERENCE_WATER_TEMPERATURE_C)
    return (2.0 * spreading_loss_db(ACTIVE_REFERENCE_RANGE_NM)
            + _two_way_absorption_db(ACTIVE_REFERENCE_RANGE_NM, absorption)
            - reference_target_strength_db() + active_noise_db(0.0))


def cw_doppler_rejection_db(radial_speed_kn: float) -> float:
    """Reverberation suppression of a CW pulse for a moving echo.

    Stationary scatterers stay near zero Doppler; an echo shifted by a few
    knots of radial speed leaves the reverberation band and the rejection
    grows with the shift (bounded)."""
    speed = abs(radial_speed_kn)
    if speed < CW_DOPPLER_MIN_KN:
        return 0.0
    return min(30.0, CW_DOPPLER_REJECTION_DB
               + 10.0 * math.log10(speed / CW_DOPPLER_MIN_KN))


def active_terms(*, distance_nm: float, target_ts_db: float, legacy_range_factor: float,
                 sea_state: float, rain: float, pulse: str, water_depth_m: float,
                 lambert_mu_db: float, wind_kn: float,
                 absorption_db_per_km: float,
                 radial_speed_kn: float = 0.0,
                 gain_factor: float = 1.0,
                 sensor_depth_m: float = 7.0) -> ActiveTerms:
    """Active sonar equation for one echo.

    ``legacy_range_factor`` is the below-layer transmission loss of the
    1.0.0 model; it attenuates echo and boundary reverberation alike.
    ``gain_factor`` (array ping multiplier, gameplay range factor) is a
    receive/transmit gain against noise only - it cannot beat
    reverberation, which scales with the transmitted level.
    """
    source = active_source_level_db()
    absorption = _two_way_absorption_db(distance_nm, absorption_db_per_km)
    # Layer crossing / array transmission penalty of the 1.0.0 model; it
    # attenuates the reverberating boundary returns as much as the echo.
    path_penalty = active_range_factor_db(legacy_range_factor)
    two_way = 2.0 * spreading_loss_db(distance_nm) + absorption + path_penalty
    noise = active_noise_db(sea_state, rain)
    reverb = reverberation_level_db(
        source_level_db=source, distance_nm=distance_nm, pulse=pulse,
        beamwidth_deg=ACTIVE_BEAMWIDTH_DEG, water_depth_m=water_depth_m,
        lambert_mu_db=lambert_mu_db, wind_kn=wind_kn,
        sensor_depth_m=sensor_depth_m) - absorption - path_penalty
    # CW and LFM carry the same energy (same length and level), so a matched
    # filter gives both the same signal-to-noise ratio; the LFM's
    # time-bandwidth product only shrinks its range cell, and with it the
    # reverberation (above).
    gain = active_range_factor_db(1.0 / max(gain_factor, 1e-6))
    rejection = cw_doppler_rejection_db(radial_speed_kn) if pulse == "CW" else 0.0
    return ActiveTerms(source, two_way, target_ts_db, noise, reverb, gain,
                       rejection)


def range_resolution_m(pulse: str) -> float:
    """Range resolution of a pulse: c T / 2 for CW, c / 2B for LFM."""
    tau, bandwidth = PULSES[pulse]
    if bandwidth > 1.0 / tau:
        return config.SOUND_SPEED_M_S / (2.0 * bandwidth)
    return config.SOUND_SPEED_M_S * tau / 2.0


def range_sigma_m(pulse: str, snr_db: float) -> float:
    """Cramer-Rao-style range accuracy: resolution / sqrt(2 SNR)."""
    snr = 10.0 ** (max(snr_db, 0.0) / 10.0)
    return range_resolution_m(pulse) / math.sqrt(2.0 * max(snr, 1.0))


def equivalent_range_nm(distance_nm: float, signal_excess_db: float) -> float:
    """Range multiplier form used by the 1.0.0 consumers: snr_db(R, d) = SE."""
    return max(distance_nm, 1e-6) * 10.0 ** (signal_excess_db / 20.0)


# Signal fading (1.3.215): multipath and the moving sea make the received
# level of a distant source wander, log-normal with a spread of a few dB and
# correlated over tens of seconds, so a contact near the detection edge comes
# and goes instead of switching on at a hard range.  Stateless: the fade is
# a pure function of (seed, observer, source, time) via ``detrand``.
FADING_SIGMA_DB = 3.0
FADING_EPOCH_S = 40.0
FADING_LIMIT_DB = 2.5 * FADING_SIGMA_DB


def fading_db(seed: int, observer: int, source: int, t: float) -> float:
    """Slowly varying fade (dB, mean 0) of one observer-source path at ``t``.

    Independent normal draws at every ``FADING_EPOCH_S``, blended with a
    smooth weight that keeps the variance constant between them."""
    scaled = max(0.0, float(t)) / FADING_EPOCH_S
    epoch = math.floor(scaled)
    blend = scaled - epoch
    weight = 0.5 - 0.5 * math.cos(math.pi * blend)
    first = detrand.normal(seed, "passive-fading", observer, source, epoch)
    second = detrand.normal(seed, "passive-fading", observer, source, epoch + 1)
    value = ((1.0 - weight) * first + weight * second) / math.sqrt(
        (1.0 - weight) ** 2 + weight * weight)
    return max(-FADING_LIMIT_DB, min(FADING_LIMIT_DB, FADING_SIGMA_DB * value))
