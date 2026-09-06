"""Small local map projection used by the offline coastline catalog."""

import math


NM_PER_DEGREE = 60.0


def lonlat_to_nm(lon: float, lat: float, center_lon: float,
                 center_lat: float, size_nm: float = 500.0) -> tuple[float, float]:
    """Project WGS84 degrees to a local equirectangular, north-up square."""
    delta_lon = (float(lon) - center_lon + 180.0) % 360.0 - 180.0
    x = size_nm * 0.5 + delta_lon * math.cos(math.radians(center_lat)) * NM_PER_DEGREE
    y = size_nm * 0.5 - (float(lat) - center_lat) * NM_PER_DEGREE
    return x, y


def nm_to_lonlat(x: float, y: float, center_lon: float,
                 center_lat: float, size_nm: float = 500.0) -> tuple[float, float]:
    """Inverse of :func:`lonlat_to_nm` for catalog metadata and tests."""
    latitude = center_lat + (size_nm * 0.5 - float(y)) / NM_PER_DEGREE
    longitude = center_lon + (float(x) - size_nm * 0.5) / (
        math.cos(math.radians(center_lat)) * NM_PER_DEGREE)
    longitude = (longitude + 180.0) % 360.0 - 180.0
    return longitude, latitude
