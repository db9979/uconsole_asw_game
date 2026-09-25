"""Canonical presentation policy for public sensor observations."""

import math

from src.core import config
from src.core.i18n import localize, message
from src.sensors.tracks import SensorTrack
from src.sensors.fusion import OPZObservation
from src.ui import layout


def value(observation, name, fallback=None):
    if isinstance(observation, dict):
        result = observation.get(name)
        return observation.get(fallback) if result is None and fallback else result
    result = getattr(observation, name, None)
    return getattr(observation, fallback, None) if result is None and fallback else result


def contact_display_id(game, contact) -> str:
    """Shared track ID with a safe fallback for detached UI test doubles."""
    resolver = getattr(game, "contact_display_id", None)
    if callable(resolver) and hasattr(contact, "target_id"):
        return resolver(contact)
    return f"K{int(contact.id):02d}"


def position(observation):
    """Return only an explicitly public observation position."""
    x = value(observation, "observed_x")
    y = value(observation, "observed_y")
    if x is not None and y is not None:
        return float(x), float(y)
    # SensorTrack and its compatibility dictionaries expose x/y as observed
    # state. Sonar Contact uses observed_x/y so similarly named entity fields
    # can never become a UI fallback.
    if isinstance(observation, (dict, SensorTrack, OPZObservation)):
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


# Shared own-ship telemetry: one source for the docked band, the status
# ticker, the F11 overlay and the Remote Crew projection. Values are
# localizable messages; levels are "ok", "warn" or "danger".
TELEMETRY_KEYS = ("telemetry.course_speed", "telemetry.noise",
                  "telemetry.sea_state", "telemetry.flooding",
                  "telemetry.torpedoes", "telemetry.vls_chaff",
                  "telemetry.helo_roe")
TICKER_KEYS = ("telemetry.course_speed", "telemetry.noise",
               "telemetry.flooding", "telemetry.torpedoes")


def telemetry_rows(game) -> list:
    """Return ``(label_key, value, level, compact)`` for own ship and stores.

    ``value`` is the full reading, ``compact`` the ticker form (same facts,
    fewer digits: the overlay and docked band always show the full value).
    Only own-ship and own-asset truth plus the operator's own BT measurement.
    """
    ship = game.ship
    profile = game.sonar.bt_profile
    flood = float(game.damage.avg_flood())
    capacity = len(game.damage.compartments) * 100
    course_speed = message("telemetry.value.course_speed",
                           course=f"{ship.course % 360.0:03.0f}",
                           speed=f"{ship.speed:.1f}")
    noise = message("telemetry.value.noise_cavitating" if ship.cavitating
                    else "telemetry.value.noise",
                    noise=f"{ship.noise_level() * 100:.0f}")
    sea = message("telemetry.value.sea_layer", sea=f"{game.world.sea_state}",
                  layer=(f"{profile['thermocline_m']:.0f}" if profile else "--"))
    helo_roe = message("telemetry.value.helo_roe",
                       helo=message("telemetry.helo.airborne" if game.helo.airborne
                                    else "telemetry.helo.hangar"),
                       roe=raw_roe(game.roe))
    return [
        ("telemetry.course_speed", course_speed, "ok", course_speed),
        ("telemetry.noise", noise, "warn" if ship.cavitating else "ok", noise),
        ("telemetry.sea_state", sea, "ok", sea),
        ("telemetry.flooding", message(
            "telemetry.value.flooding", total=f"{game.damage.total:.0f}",
            capacity=capacity, mean=f"{flood:.0f}"),
         "danger" if flood >= 25 else "warn" if flood > 0 else "ok",
         message("telemetry.value.percent", value=f"{flood:.0f}")),
        ("telemetry.torpedoes", message(
            "telemetry.value.torpedoes", count=game.torpedo_count,
            total=game.torpedo_total, depth=f"{game.torpedo_depth:.0f}"),
         "warn" if game.torpedo_count == 0 else "ok",
         message("telemetry.value.count", count=game.torpedo_count,
                 total=game.torpedo_total)),
        ("telemetry.vls_chaff", message(
            "telemetry.value.vls_chaff", cells=game.vls_cells,
            total=game.vls_loadout_total, chaff=f"{float(game.chaff_cd):.0f}"),
         "warn" if game.vls_cells == 0 else "ok",
         message("telemetry.value.count", count=game.vls_cells,
                 total=game.vls_loadout_total)),
        ("telemetry.helo_roe", helo_roe, "ok", helo_roe),
    ]


def telemetry_label(key: str, short: bool) -> str:
    """Catalog key of a telemetry label, full or abbreviated."""
    return f"{key}.short" if short else key


def raw_roe(roe) -> str:
    """ROE codes are technical labels shown verbatim."""
    return str(roe)[:8]
