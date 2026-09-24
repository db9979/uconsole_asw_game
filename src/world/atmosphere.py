"""Derived atmosphere for the weather station (pure functions).

Everything here is a deterministic function of state the world already
keeps (sea state, the current weather epoch and its target, wind, rain,
visibility, clock, season, sea-surface temperature), so nothing new has to
be saved.  The values are a game model of real processes, compressed to the
game's hourly weather epochs; they are not a real forecast.

* Pressure: a seeded synoptic offset plus an equilibrium that falls with
  sea state.  The barometer leads the sea: over each weather epoch it moves
  from the current state's equilibrium towards the coming one, so a front
  announces itself by a falling glass before the sea builds.
* Air temperature: sea-surface temperature minus a seasonal air-sea
  difference, a diurnal swing (damped by cloud and rain) and a cold-air
  outbreak with strong northerly wind; sub-zero air is possible in winter.
* Precipitation type, gusts, cloud ceiling, icing, Beaufort force.
* Sun elevation and twilight from latitude, day of year and local time.
* Lunar phase names from the lunar age.
"""

from __future__ import annotations

import math

from src.core import config, detrand

# --- pressure -----------------------------------------------------------
PRESSURE_CALM_HPA = 1022.0
PRESSURE_PER_SEA_STATE_HPA = 6.0
PRESSURE_OFFSET_RANGE_HPA = (-4.0, 4.0)
TREND_WINDOW_S = 3.0 * 3600.0            # WMO pressure tendency window
TREND_STEADY_HPA = 1.0
TREND_RAPID_HPA = 3.5
STORM_PRESSURE_HPA = 990.0
STORM_WARNING_PRESSURE_HPA = 1004.0

# --- air temperature ---------------------------------------------------
AIR_SEA_WINTER_DIFFERENCE_C = 6.0
AIR_DIURNAL_AMPLITUDE_C = 3.0
AIR_DIURNAL_PEAK_HOUR = 14.0
COLD_OUTBREAK_MAX_C = 6.0
COLD_OUTBREAK_WIND_KN = 40.0
SNOW_TEMPERATURE_C = 0.5

# --- wind / cloud / icing ----------------------------------------------
GUST_FACTOR_CALM = 1.3
GUST_FACTOR_PER_SEA_STATE = 0.035
SPRAY_ICING_WIND_KN = 20.0
BEAUFORT_UPPER_KN = (1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63)
CEILING_NONE_FT = None

# --- sun / moon ----------------------------------------------------------
DEFAULT_LATITUDE_DEG = 55.0
CIVIL_TWILIGHT_DEG = -6.0
NAUTICAL_TWILIGHT_DEG = -12.0
SYNODIC_MONTH_D = 29.530588


def pressure_equilibrium_hpa(sea_state: float, offset_hpa: float) -> float:
    return PRESSURE_CALM_HPA + offset_hpa - PRESSURE_PER_SEA_STATE_HPA * sea_state


def pressure_offset_hpa(seed: int) -> float:
    return detrand.uniform(*PRESSURE_OFFSET_RANGE_HPA, seed, "pressure-offset")


def barometer(seed: int, source_sea: int, target_sea: int,
              epoch_elapsed_s: float) -> tuple[float, float]:
    """Pressure (hPa) and its 3-hour tendency (hPa / 3 h).

    Over one weather epoch the glass moves linearly from the equilibrium of
    the current sea state to that of the coming one."""
    offset = pressure_offset_hpa(seed)
    start = pressure_equilibrium_hpa(source_sea, offset)
    end = pressure_equilibrium_hpa(target_sea, offset)
    lead = max(0.0, min(1.0, epoch_elapsed_s / config.WEATHER_SHIFT_PERIOD_S))
    pressure = start + (end - start) * lead
    tendency = (end - start) * TREND_WINDOW_S / config.WEATHER_SHIFT_PERIOD_S
    return pressure, tendency


def pressure_trend(tendency_hpa_3h: float) -> str:
    if tendency_hpa_3h <= -TREND_RAPID_HPA:
        return "falling_rapidly"
    if tendency_hpa_3h <= -TREND_STEADY_HPA:
        return "falling"
    if tendency_hpa_3h >= TREND_STEADY_HPA:
        return "rising"
    return "steady"


def storm_warning(pressure_hpa: float, trend: str) -> bool:
    return (pressure_hpa < STORM_PRESSURE_HPA
            or (trend == "falling_rapidly" and pressure_hpa <= STORM_WARNING_PRESSURE_HPA))


def cloud_cover(weather_kind: str, rain: float) -> float:
    """Fraction of sky covered (0..1), from the observable weather type."""
    return {"clear": 0.25, "fog": 1.0, "rain": 0.75 + 0.25 * rain,
            "storm": 1.0}.get(weather_kind, 0.5)


def air_temperature_c(sst_c: float, day_of_year: int, hour: float,
                      wind_from_deg: float, wind_kn: float, cloud: float) -> float:
    winter = 0.5 * (1.0 + math.cos(2.0 * math.pi * (day_of_year - 15) / 365.0))
    seasonal = AIR_SEA_WINTER_DIFFERENCE_C * winter - 1.0 * (1.0 - winter)
    diurnal = (AIR_DIURNAL_AMPLITUDE_C * (1.0 - 0.7 * cloud)
               * math.cos(2.0 * math.pi * (hour - AIR_DIURNAL_PEAK_HOUR) / 24.0))
    northerly = max(0.0, math.cos(math.radians(wind_from_deg)))
    outbreak = (COLD_OUTBREAK_MAX_C * northerly * winter
                * min(1.0, max(0.0, wind_kn) / COLD_OUTBREAK_WIND_KN))
    return sst_c - seasonal + diurnal - outbreak


def precipitation(rain: float, air_c: float) -> str:
    if rain < 0.1:
        return "none"
    return "snow" if air_c <= SNOW_TEMPERATURE_C else "rain"


def gust_kn(wind_kn: float, sea_state: float) -> float:
    return max(0.0, wind_kn) * (GUST_FACTOR_CALM + GUST_FACTOR_PER_SEA_STATE * sea_state)


def beaufort(wind_kn: float) -> int:
    for force, upper in enumerate(BEAUFORT_UPPER_KN):
        if wind_kn < upper:
            return force
    return 12


def cloud_ceiling_ft(weather_kind: str, rain: float, visibility_nm: float) -> float | None:
    """Cloud base in feet; None means no significant ceiling."""
    if weather_kind == "fog":
        return max(0.0, min(200.0, visibility_nm * 100.0))
    if weather_kind == "storm":
        return 500.0 + 500.0 * max(0.0, 1.0 - rain)
    if weather_kind == "rain":
        return 1000.0 + 1500.0 * max(0.0, 1.0 - rain)
    return CEILING_NONE_FT


def icing(air_c: float, precipitation_kind: str, wind_kn: float) -> str:
    """Airframe/superstructure icing: none, light or severe."""
    if air_c >= 0.0:
        return "none"
    wet = precipitation_kind != "none"
    spray = wind_kn >= SPRAY_ICING_WIND_KN
    if not wet and not spray:
        return "none"
    if air_c <= -3.0 and (wet and spray):
        return "severe"
    return "light"


def sun_elevation_deg(latitude_deg: float, day_of_year: int, hour: float) -> float:
    declination = -23.44 * math.cos(2.0 * math.pi * (day_of_year + 10) / 365.0)
    hour_angle = 15.0 * (hour - 12.0)
    lat, dec, ha = (math.radians(latitude_deg), math.radians(declination),
                    math.radians(hour_angle))
    return math.degrees(math.asin(max(-1.0, min(1.0, math.sin(lat) * math.sin(dec)
                                                 + math.cos(lat) * math.cos(dec)
                                                 * math.cos(ha)))))


def daylight(sun_elevation: float) -> str:
    if sun_elevation > -0.833:
        return "day"
    if sun_elevation > CIVIL_TWILIGHT_DEG:
        return "civil_twilight"
    if sun_elevation > NAUTICAL_TWILIGHT_DEG:
        return "nautical_twilight"
    return "night"


def moon_phase(lunar_age_days: float) -> str:
    fraction = (lunar_age_days % SYNODIC_MONTH_D) / SYNODIC_MONTH_D
    if fraction < 0.0339 or fraction >= 0.9661:
        return "new"
    if fraction < 0.2161:
        return "waxing_crescent"
    if fraction < 0.2839:
        return "first_quarter"
    if fraction < 0.4661:
        return "waxing_gibbous"
    if fraction < 0.5339:
        return "full"
    if fraction < 0.7161:
        return "waning_gibbous"
    if fraction < 0.7839:
        return "last_quarter"
    return "waning_crescent"
