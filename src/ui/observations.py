"""Canonical presentation policy for public sensor observations."""

import math

from src.core import config
from src.core.i18n import localize, message
from src.sensors.tracks import SensorTrack
from src.ui import layout


def value(observation, name, fallback=None):
    if isinstance(observation, dict):
        result = observation.get(name)
        return observation.get(fallback) if result is None and fallback else result
    result = getattr(observation, name, None)
    return getattr(observation, fallback, None) if result is None and fallback else result


def position(observation):
    """Return only an explicitly public observation position."""
    x = value(observation, "observed_x")
    y = value(observation, "observed_y")
    if x is not None and y is not None:
        return float(x), float(y)
    # SensorTrack and its compatibility dictionaries expose x/y as observed
    # state. Sonar Contact uses observed_x/y so similarly named entity fields
    # can never become a UI fallback.
    if isinstance(observation, (dict, SensorTrack)):
        x = value(observation, "x")
        y = value(observation, "y")
        if x is not None and y is not None:
            return float(x), float(y)
    return None, None


def bearing(observation, observer=None) -> float:
    """Return bearing to public position, otherwise the stabilized bearing."""
    x, y = position(observation)
    if x is not None and observer is not None:
        return math.degrees(math.atan2(
            x - float(observer.x), -(y - float(observer.y)))) % 360.0
    result = value(observation, "smoothed_bearing")
    if result is None:
        result = value(observation, "passive_bearing")
    if result is None:
        result = value(observation, "bearing")
    return float(result or 0.0) % 360.0


def range_nm(observation, observer=None):
    x, y = position(observation)
    if x is not None and observer is not None:
        return math.hypot(x - float(observer.x), y - float(observer.y))
    result = value(observation, "range_est")
    if result is None:
        result = value(observation, "range_nm", "dist")
    return None if result is None else float(result)


def bearing_uncertainty(observation):
    result = value(observation, "bearing_uncertainty_deg")
    if result is not None:
        return max(0.0, float(result))
    source = str(value(observation, "source") or "")
    if source in ("ESM", "HOJ"):
        return float(config.ESM_BEARING_ERR_DEG)
    if source == "HFDF":
        return float(config.HFDF_BEARING_ERR_DEG)
    return None


def bearing_decimals(observation, observer=None) -> int:
    if position(observation)[0] is not None and observer is not None:
        return 1
    uncertainty = bearing_uncertainty(observation)
    return 1 if uncertainty is not None and uncertainty < 0.5 else 0


def format_bearing(observation, observer=None) -> str:
    decimals = bearing_decimals(observation, observer)
    width = 5 if decimals else 3
    rounded = round(bearing(observation, observer), decimals) % 360.0
    return f"{rounded:0{width}.{decimals}f}"


def format_bearing_pair(observation, ship, *, compact=False) -> str:
    observed = bearing(observation, ship)
    decimals = bearing_decimals(observation, ship)
    if compact:
        true, relative = layout.bearing_pair(observed, getattr(ship, "course", 0.0))
        width = 5 if decimals else 3
        return localize(message(
            "bearing.compact_pair",
            true=f"{round(true, decimals) % 360:0{width}.{decimals}f}",
            relative=f"{round(relative, decimals) % 360:0{width}.{decimals}f}"))
    return layout.format_bearing_pair(
        observed, getattr(ship, "course", 0.0), decimals=decimals)


def observation_age(observation, now: float):
    seen = value(observation, "last_seen")
    if seen is None:
        age = value(observation, "age")
        return None if age is None else max(0.0, float(age))
    return max(0.0, float(now) - float(seen))


def position_age(observation, now: float):
    seen = value(observation, "position_seen")
    if seen is None:
        seen = value(observation, "range_seen")
    return None if seen is None else max(0.0, float(now) - float(seen))
