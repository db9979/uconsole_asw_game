"""OPZ display settings: what the operations room draws on its chart.

Pure presentation choices (track trails, vector length, labels, the bearing
scale, range rings, the selected track's closest point of approach and the
chart layers).  They never change the simulation, observations or the
score; they live in ``settings.json`` (``Preferences.opz_display``), never
in a save.  The uConsole sets them on the OPZ's "Display" page, the browser
OPZ with its own buttons above the chart (kept in the browser's storage).

``cpa`` is the plotting-table closest point of approach between the own
ship (own truth) and an observed track's position and motion: it uses only
what the observation reports.
"""

from __future__ import annotations

import math

# (key, choices, default).  Order is the order of the rows on the page.
OPTIONS = (
    ("trails", ("off", "3", "6", "12"), "6"),
    ("vectors", ("3", "6", "12", "30"), "3"),
    ("labels", ("full", "brief", "off"), "full"),
    ("compass", ("on", "off"), "on"),
    ("rings", ("on", "off"), "on"),
    ("cpa", ("on", "off"), "on"),
    ("bearings", ("on", "off"), "on"),
    ("uncertainty", ("on", "off"), "on"),
    ("chart", ("on", "off"), "on"),
    ("afterglow", ("on", "off"), "on"),
)
KEYS = tuple(key for key, _choices, _default in OPTIONS)
CHOICES = {key: choices for key, choices, _default in OPTIONS}
DEFAULTS = {key: default for key, _choices, default in OPTIONS}
# The chips under the chart: short names of the switchable layers.
CHIP_KEYS = ("trails", "vectors", "labels", "compass", "rings", "cpa",
             "bearings", "uncertainty", "chart", "afterglow")
# A CPA further ahead than this is not drawn (minutes).
CPA_HORIZON_MIN = 120.0
# Below this relative speed the two keep their distance: no CPA.
CPA_MIN_RELATIVE_KN = 0.5


def normalize(pairs) -> dict:
    """Settings from stored ``(key, value)`` pairs; unknown keys and values
    fall back to the defaults (a hostile or older settings file)."""
    values = dict(DEFAULTS)
    if isinstance(pairs, dict):
        pairs = pairs.items()
    try:
        items = list(pairs or ())[:64]
    except TypeError:
        return values
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        key, value = item
        if key in CHOICES and value in CHOICES[key]:
            values[key] = value
    return values


def to_pairs(values: dict) -> tuple:
    """Stored form: only the settings that differ from the default."""
    clean = normalize(values)
    return tuple((key, clean[key]) for key in KEYS if clean[key] != DEFAULTS[key])


def step(values: dict, key: str, delta: int) -> dict:
    """``values`` with ``key`` moved ``delta`` choices on (wrapping)."""
    clean = normalize(values)
    if key not in CHOICES:
        return clean
    choices = CHOICES[key]
    clean[key] = choices[(choices.index(clean[key]) + int(delta)) % len(choices)]
    return clean


def enabled(values: dict, key: str) -> bool:
    """A layer is drawn unless it is switched to ``off``."""
    return normalize(values).get(key, "on") != "off"


def trail_minutes(values: dict) -> float:
    value = normalize(values)["trails"]
    return 0.0 if value == "off" else float(value)


def vector_minutes(values: dict) -> float:
    return float(normalize(values)["vectors"])


def cpa(own_x, own_y, own_course, own_speed_kn, x, y, course, speed_kn):
    """Closest point of approach of an observed track and the own ship.

    Returns ``(distance_nm, minutes, own_point, track_point)`` or None when
    the track has no position or motion, the two do not close, or the CPA
    lies beyond ``CPA_HORIZON_MIN``.  Nautical frame: x east, y south.
    """
    values = (own_x, own_y, own_course, own_speed_kn, x, y, course, speed_kn)
    if any(value is None or not math.isfinite(float(value)) for value in values):
        return None
    own_vx = own_speed_kn * math.sin(math.radians(own_course)) / 60.0
    own_vy = -own_speed_kn * math.cos(math.radians(own_course)) / 60.0
    vx = speed_kn * math.sin(math.radians(course)) / 60.0
    vy = -speed_kn * math.cos(math.radians(course)) / 60.0
    rx, ry = x - own_x, y - own_y
    dvx, dvy = vx - own_vx, vy - own_vy
    rel2 = dvx * dvx + dvy * dvy
    if rel2 * 3600.0 < CPA_MIN_RELATIVE_KN * CPA_MIN_RELATIVE_KN:
        return None
    minutes = -(rx * dvx + ry * dvy) / rel2
    if minutes <= 0.0 or minutes > CPA_HORIZON_MIN:
        return None
    distance = math.hypot(rx + dvx * minutes, ry + dvy * minutes)
    own_point = (own_x + own_vx * minutes, own_y + own_vy * minutes)
    track_point = (x + vx * minutes, y + vy * minutes)
    return distance, minutes, own_point, track_point
