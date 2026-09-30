"""Moving marks on the tactical charts: the own ping's wavefront, echoes,
splashes of own charges and the furthest-on circle of a stale fix.

Only own-side knowledge goes in: where and when the own sonar (or the
helicopter's dipping sonar, or the crewed boat's bow sonar) transmitted,
where a received echo puts its reflector (measured bearing and range), and
where the own depth charges and rockets went off.  Nothing is saved and
nothing feeds back into the simulation; the rows are drawn by
``src/ui/map_fx_view.py`` and, as the plot's ``fx`` block, by the browser.
"""

from __future__ import annotations

import math
from collections import deque

# Sound speed for the drawn wavefront (m/s) and how long it is drawn.
SOUND_MPS = 1500.0
PING_SHOW_S = 60.0
ECHO_SHOW_S = 4.0
SPLASH_SHOW_S = 20.0
PINGS_MAX, ECHOES_MAX, SPLASHES_MAX = 6, 12, 12
# Furthest-on circle: a fix older than this grows a circle at the class's
# assumed top speed (kn), no larger than the cap.
FOC_MIN_AGE_S = 60.0
FOC_SPEED_KN = {"SUB": 20.0, "SURFACE": 30.0}
FOC_MAX_NM = 25.0


def ping_radius_nm(age_s: float) -> float:
    """Radius (NM) of the outgoing wavefront ``age_s`` after the ping."""
    return max(0.0, age_s) * SOUND_MPS / 1852.0


def furthest_on_nm(kind: str, age_s: float) -> float | None:
    """Radius (NM) a contact of ``kind`` can have gone since a fix
    ``age_s`` old; None for a fresh fix or a kind without a bound."""
    speed = FOC_SPEED_KN.get(str(kind).upper())
    if speed is None or age_s < FOC_MIN_AGE_S:
        return None
    return min(FOC_MAX_NM, age_s * speed / 3600.0)


class MapFx:
    """Bounded recent pings, echoes and splashes per side (display only)."""

    def __init__(self) -> None:
        self.pings = deque(maxlen=PINGS_MAX)
        self.echoes = deque(maxlen=ECHOES_MAX)
        self.splashes = deque(maxlen=SPLASHES_MAX)

    def clear(self) -> None:
        self.pings.clear()
        self.echoes.clear()
        self.splashes.clear()

    def ping(self, side, t: float, x: float, y: float) -> None:
        self.pings.append((side, float(t), float(x), float(y)))

    def echo(self, side, t: float, x: float, y: float, bearing, range_nm) -> None:
        """An echo received at ``t`` on the measured ``bearing``/``range_nm``
        from the receiver at (x, y)."""
        if not isinstance(bearing, (int, float)) or not isinstance(range_nm, (int, float)):
            return
        if not (math.isfinite(bearing) and math.isfinite(range_nm)):
            return
        angle = math.radians(bearing)
        self.echoes.append((side, float(t), x + range_nm * math.sin(angle),
                            y - range_nm * math.cos(angle)))

    def splash(self, side, t: float, x: float, y: float) -> None:
        self.splashes.append((side, float(t), float(x), float(y)))

    def rows(self, side, now: float) -> dict:
        """``{"pings", "echoes", "splashes"}``: lists of (age_s, x, y) of
        ``side`` that are still drawn, newest last."""
        def pick(items, show_s):
            return [(now - t, x, y) for owner, t, x, y in items
                    if owner == side and 0.0 <= now - t <= show_s]
        return dict(pings=pick(self.pings, PING_SHOW_S), echoes=pick(self.echoes, ECHO_SHOW_S),
                    splashes=pick(self.splashes, SPLASH_SHOW_S))
