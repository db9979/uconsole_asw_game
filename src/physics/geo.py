"""Plane geometry shared by the simulation: range and nautical bearing.

World units are nautical miles with y growing south, so a nautical bearing
(0 north, clockwise) is ``atan2(dx, -dy)``.  These are the exact expressions
the entity classes and helper modules used to repeat; keeping one copy keeps
every result bit-identical.
"""

import math


def bearing_deg(x0: float, y0: float, x1: float, y1: float) -> float:
    """Nautical bearing in degrees [0, 360) from ``(x0, y0)`` to ``(x1, y1)``."""
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


class FrigateRelativeMixin:
    """``distance_nm``/``bearing_from_frigate`` of an entity with ``x``/``y``
    as seen from an observer (the frigate or another platform)."""

    __slots__ = ()

    def distance_nm(self, frigate) -> float:
        return math.hypot(self.x - frigate.x, self.y - frigate.y)

    def bearing_from_frigate(self, frigate) -> float:
        """Nautische Peilung: 0° = Nord (nach oben), 90° = Ost, im Uhrzeigersinn."""
        dx = self.x - frigate.x
        dy = self.y - frigate.y
        return math.degrees(math.atan2(dx, -dy)) % 360.0
