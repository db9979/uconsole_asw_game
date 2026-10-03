"""A decoy keeps its speed in NM/s; sonar must read its knots."""

import random
from types import SimpleNamespace

from src.enemies.decoy import Decoy
from src.sonar import sonar


def test_decoy_doppler_uses_knots_not_nm_per_second():
    decoy = Decoy(10.0, 10.0, 50.0, random.Random(4))
    decoy.course = 0.0                      # running north, at the observer
    observer = SimpleNamespace(x=10.0, y=5.0, course=0.0, speed=0.0)
    expected = 1.0 + decoy.speed_kn / sonar.SOUND_SPEED_KN
    assert decoy.speed_kn > 1.0
    assert abs(sonar.doppler_factor(decoy, observer) - expected) < 1e-9
