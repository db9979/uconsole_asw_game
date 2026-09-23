"""Dependency-free local geographic projection tests."""

import pytest

from src.world.projection import lonlat_to_nm, nm_to_lonlat


@pytest.mark.parametrize("center", [(-4.2, 56.0), (139.0, 35.0),
                                     (-73.0, -35.0)])
def test_projection_center_and_round_trip(center):
    lon, lat = center
    assert lonlat_to_nm(lon, lat, lon, lat) == pytest.approx((250.0, 250.0))
    projected = lonlat_to_nm(lon + 1.25, lat - 0.75, lon, lat)
    assert nm_to_lonlat(*projected, lon, lat) == pytest.approx(
        (lon + 1.25, lat - 0.75))


def test_projection_wraps_across_antimeridian():
    x, y = lonlat_to_nm(-179.0, 10.0, 179.0, 10.0)
    assert x > 250.0
    assert y == pytest.approx(250.0)
