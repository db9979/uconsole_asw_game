"""Fingerprint: instanzweiser akustischer Charakter, deterministisch & savbar."""

import random

from src.data import fingerprint as fp
from src.data.catalog import CATALOG
from src.enemies.sub import Sub


def _sig():
    return CATALOG.subs["diesel_alt"].acoustic


def test_roll_from_seed_is_deterministic():
    sig = _sig()
    a = fp.roll_from_seed(1234, sig)
    b = fp.roll_from_seed(1234, sig)
    c = fp.roll_from_seed(4321, sig)
    assert a == b
    assert a != c


def test_fingerprint_ranges_and_dict_roundtrip():
    sig = _sig()
    for seed in (1, 7, 99, 424242):
        f = fp.roll_from_seed(seed, sig)
        assert f.blades in sig.blade_counts
        assert 0.85 <= f.rate_scale <= 1.15
        assert all(abs(o) <= 0.5 + 1e-9 for o in f.offsets)
        assert sig.cavitation_tendency * 0.5 - 1e-9 <= f.cavitation \
            <= sig.cavitation_tendency * 1.5 + 1e-9
        assert sig.broadband[0] * 0.5 - 1e-9 <= f.bb_level \
            <= sig.broadband[0] * 1.4 + 1e-9
        assert f.bb_low_hz > 0 and f.bb_high_hz > f.bb_low_hz
        assert fp.Fingerprint.from_dict(f.to_dict()) == f


def test_sub_fingerprint_derived_from_sensor_seed_only():
    s1 = Sub(10.0, 10.0, 60.0, 0.0, "diesel_alt", random.Random(4))
    s2 = Sub(11.0, 11.0, 60.0, 0.0, "diesel_alt", random.Random(4))
    assert s1.sensor_seed == s2.sensor_seed
    assert s1.fingerprint == s2.fingerprint
    assert s1.fingerprint == fp.roll_from_seed(
        s1.sensor_seed, s1.stype.acoustic)


def test_surface_ship_fingerprint_derived_from_sensor_seed_only():
    from src.enemies.surface import SurfaceShip
    a = SurfaceShip(10.0, 10.0, random.Random(9), hostile=True)
    b = SurfaceShip(12.0, 12.0, random.Random(9), hostile=True)
    assert a.sensor_seed == b.sensor_seed
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint == fp.roll_from_seed(a.sensor_seed, a.profile.acoustic)
