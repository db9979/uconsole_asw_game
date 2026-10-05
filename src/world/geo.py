"""Geographic chart display: latitude/longitude of the sea area's chart.

A real sector (``Coastline.generate``) is projected around its centre
(``src/world/projection.py``: local equirectangular, 60 NM per degree of
latitude). This module only reads that public chart reference to draw a
graticule and to write positions as degrees and minutes; it never changes
positions, ranges or anything the simulation uses. The stylized legacy
map (world mode ``fixed``) has no real place and keeps the NM grid.
"""

import math

from src.core.i18n import message
from src.world.projection import NM_PER_DEGREE, nm_to_lonlat

# Graticule spacings in arc minutes, smallest first.
GRATICULE_STEPS_MIN = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0,
                       60.0, 120.0, 300.0)


def chart_center(world):
    """The (longitude, latitude) the chart is projected around, or None."""
    coast = getattr(world, "coast", None)
    metadata = getattr(coast, "metadata", None) or {}
    center = metadata.get("center")
    if isinstance(center, dict):
        lat, lon = center.get("latitude"), center.get("longitude")
    elif isinstance(center, (list, tuple)) and len(center) == 2:
        lon, lat = center
    else:
        return None
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat)
            and -180.0 <= lon <= 180.0 and -89.0 <= lat <= 89.0):
        return None
    return lon, lat


def to_lonlat(world, x_nm, y_nm):
    """A chart position as (longitude, latitude), or None without a reference."""
    center = chart_center(world)
    if center is None:
        return None
    return nm_to_lonlat(x_nm, y_nm, center[0], center[1], world.size_nm)


def decimal_sep(game_or_translator):
    """Decimal mark of the display language: comma in German, else point."""
    translator = getattr(game_or_translator, "translator", game_or_translator)
    return "," if getattr(translator, "language", "en") == "de" else "."


def nm_per_lon_minute(center_lat):
    return math.cos(math.radians(center_lat)) * NM_PER_DEGREE / 60.0


def graticule_step_min(px_per_minute, min_px=80.0):
    """The smallest spacing in arc minutes that is at least ``min_px`` apart."""
    for step in GRATICULE_STEPS_MIN:
        if step * px_per_minute >= min_px:
            return step
    return GRATICULE_STEPS_MIN[-1]


def graticule(world, x0, x1, y0, y1, scale_px_per_nm, lat_min_px=80.0,
              lon_min_px=120.0):
    """Meridians and parallels inside the chart box ``x0..x1``/``y0..y1`` NM.

    Returns ``(meridians, parallels, lon_step, lat_step)``: lists of
    ``(x_nm, longitude)`` and ``(y_nm, latitude)``. The projection is
    equirectangular, so meridians are vertical and parallels horizontal."""
    center = chart_center(world)
    if center is None:
        return None
    lon0, lat0 = center
    half = world.size_nm * 0.5
    lon_nm = nm_per_lon_minute(lat0)
    lat_step = graticule_step_min(scale_px_per_nm, lat_min_px)
    lon_step = graticule_step_min(scale_px_per_nm * lon_nm, lon_min_px)
    parallels = []
    # y grows south: latitude = lat0 + (half - y) / 60.
    lat_top = (lat0 * 60.0 + (half - y0))
    lat_bottom = (lat0 * 60.0 + (half - y1))
    k0 = math.ceil(min(lat_top, lat_bottom) / lat_step - 1e-9)
    k1 = math.floor(max(lat_top, lat_bottom) / lat_step + 1e-9)
    for k in range(k0, min(k1, k0 + 400) + 1):
        minutes = k * lat_step
        parallels.append((half - (minutes - lat0 * 60.0), minutes / 60.0))
    meridians = []
    lon_left = lon0 * 60.0 + (x0 - half) / lon_nm
    lon_right = lon0 * 60.0 + (x1 - half) / lon_nm
    k0 = math.ceil(min(lon_left, lon_right) / lon_step - 1e-9)
    k1 = math.floor(max(lon_left, lon_right) / lon_step + 1e-9)
    for k in range(k0, min(k1, k0 + 400) + 1):
        minutes = k * lon_step
        meridians.append((half + (minutes - lon0 * 60.0) * lon_nm,
                          (minutes / 60.0 + 180.0) % 360.0 - 180.0))
    return meridians, parallels, lon_step, lat_step


def _split(value_deg, decimals):
    """Whole degrees and minutes, rounded so minutes never read 60."""
    total = round(abs(value_deg) * 60.0, decimals)
    degrees = int(total // 60)
    minutes = total - degrees * 60
    return degrees, round(minutes, decimals)


def _minutes(minutes, decimals, decimal_sep):
    text = f"{minutes:0{3 + decimals if decimals else 2}.{decimals}f}"
    return text.replace(".", decimal_sep)


def format_lat(lat, decimals=1, decimal_sep=","):
    """``54°21,4'N``: two-digit degrees, minutes with ``decimals``."""
    degrees, minutes = _split(lat, decimals)
    hemi = "N" if lat >= 0 else "S"
    return f"{degrees:02d}°{_minutes(minutes, decimals, decimal_sep)}'{hemi}"


def format_lon(lon, decimals=1, decimal_sep=","):
    """``010°08,2'E``: three-digit degrees, minutes with ``decimals``."""
    degrees, minutes = _split(lon, decimals)
    hemi = "E" if lon >= 0 else "W"
    return f"{degrees:03d}°{_minutes(minutes, decimals, decimal_sep)}'{hemi}"


def label_decimals(step_min):
    """Minute decimals a graticule label needs for its spacing."""
    if step_min >= 1.0:
        return 0
    return 1


def axis_label(value_deg, step_min, is_lat, decimal_sep=","):
    """Short graticule label: ``54°N`` on whole degrees, else ``54°20'N``."""
    decimals = label_decimals(step_min)
    degrees, minutes = _split(value_deg, decimals)
    hemi = ("N" if value_deg >= 0 else "S") if is_lat else (
        "E" if value_deg >= 0 else "W")
    if step_min >= 60.0:
        return f"{degrees}°{hemi}"
    return f"{degrees}°{_minutes(minutes, decimals, decimal_sep)}'{hemi}"


def format_position(world, x_nm, y_nm, decimals=1, decimal_sep=","):
    """``54°21,4'N 010°08,2'E`` for a chart position, or None."""
    lonlat = to_lonlat(world, x_nm, y_nm)
    if lonlat is None:
        return None
    lon, lat = lonlat
    return (f"{format_lat(lat, decimals, decimal_sep)} "
            f"{format_lon(lon, decimals, decimal_sep)}")


def position_message(world, x_nm, y_nm):
    """A position as a localizable message (``geo.position``: the decimal
    mark follows the reader's language), or None without a real sea area."""
    lonlat = to_lonlat(world, x_nm, y_nm)
    if lonlat is None:
        return None
    lon, lat = lonlat
    lat_d, lat_m = _split(lat, 1)
    lon_d, lon_m = _split(lon, 1)
    lat_whole, lat_tenth = divmod(int(round(lat_m * 10)), 10)
    lon_whole, lon_tenth = divmod(int(round(lon_m * 10)), 10)
    return message("geo.position",
                   lat_d=f"{lat_d:02d}", lat_m=f"{lat_whole:02d}", lat_t=str(lat_tenth),
                   ns="N" if lat >= 0 else "S",
                   lon_d=f"{lon_d:03d}", lon_m=f"{lon_whole:02d}", lon_t=str(lon_tenth),
                   ew="E" if lon >= 0 else "W")



def position_fields(world, x_nm, y_nm) -> dict:
    """Text fields naming a position: ``position`` in degrees and minutes on
    a real sea area, else ``x``/``y`` in NM (the stylized fixed chart)."""
    position = position_message(world, x_nm, y_nm)
    if position is None:
        return dict(x=f"{x_nm:.1f}", y=f"{y_nm:.1f}")
    return dict(position=position)


def position_key(key, fields) -> str:
    """The catalog key for ``fields``: ``<key>.geo`` takes ``{position}``."""
    return key + ".geo" if "position" in fields else key


def position_text(key, world, x_nm, y_nm, **params):
    """A localizable message naming a position (see ``position_fields``)."""
    fields = position_fields(world, x_nm, y_nm)
    return message(position_key(key, fields), **params, **fields)
