"""Navigation lights an observer makes out on a vessel (COLREG rules 20-29).

Pure sensor generation: the caller passes the vessel's true course and the
geometry, the result is a short detached code the views draw, never the
course itself.  A power-driven vessel shows a white masthead light over
225 degrees ahead (two from 50 m length, the aft one higher), a green
starboard and a red port side light over 112.5 degrees from ahead on either
side, and a white stern light over the remaining 135 degrees astern.
Vessels at work add their all-round lights (``DUTY``): a trawler green over
white (rule 26, a masthead light only from 50 m), a pilot vessel on duty
white over red instead of masthead lights (rule 29), a vessel restricted in
her ability to manoeuvre (survey, cable laying, research) red, white, red
(rule 27b) and a mine clearance vessel three green (rule 27f).

Code ``"<facing><masthead><red><green><stern>[<all-round>]"``: facing
``L``/``R`` (bow to the left or right as seen), masthead ``0``/``1``/``2``,
then ``r``, ``g``, ``s`` or ``-`` each, then the all-round lights top down
(``GW``, ``WR``, ``RWR`` or ``GGG``).  ``None`` when nothing is lit or in range.

An aircraft (``aircraft_code``, civil traffic only; military aircraft fly
dark) uses the same code: red left and green right wingtip lights over
110 degrees, the white tail light over the 140 degrees aft, and ``AC`` for
its anti-collision lights (flashing red beacons, white wingtip strobes),
which carry furthest.
"""

from __future__ import annotations

import re

# Rule 22 ranges (NM): (length from, masthead, side, stern, all-round).
_RANGES = ((50.0, 6.0, 3.0, 3.0, 3.0), (12.0, 5.0, 2.0, 2.0, 2.0),
           (0.0, 2.0, 1.0, 2.0, 2.0))
SIDE_ARC_DEG = 112.5
# Both side lights show within this angle of dead ahead (cut-off tolerance).
HEAD_ON_DEG = 3.0
# Catalog entries at work and the lights their work adds (top down).
DUTY = {
    "aux_07": "GW",     # fishing trawler, trawling
    "aux_10": "WR",     # pilot vessel on duty
    "aux_04": "RWR",    # research vessel: restricted in ability to manoeuvre
    "aux_05": "RWR",    # cable layer
    "aux_08": "RWR",    # survey vessel
    "aux_01": "GGG",    # mine clearance
}
ALL_ROUND = ("GW", "WR", "RWR", "GGG")
CODE_RE = re.compile(r"^[LR][012][r-][g-][s-](GW|WR|RWR|GGG|AC)?$")
# Aircraft position lights (CS/FAR 25.1387): wingtip lights over 110
# degrees either side, the tail light over the rest; ranges (NM) assumed
# for the eye: position lights 3, anti-collision lights 10.
AIRCRAFT_WING_ARC_DEG = 110.0
AIRCRAFT_NAV_NM = 3.0
AIRCRAFT_ANTI_COLLISION_NM = 10.0


def lit(stage: str, visibility_nm: float) -> bool:
    """Lights are shown from sunset to sunrise and in restricted visibility."""
    return stage != "day" or visibility_nm < 2.0


def duty(profile) -> str | None:
    """The all-round lights a catalog vessel's work adds, or ``None``."""
    return DUTY.get(str(getattr(profile, "key", "")))


def code(course_deg: float, bearing_from_observer_deg: float, distance_nm: float,
         length_m: float, visibility_nm: float, work: str | None = None) -> str | None:
    """The lights visible from the observer, or ``None``."""
    masthead_nm, side_nm, stern_nm, round_nm = next(
        row[1:] for row in _RANGES if length_m >= row[0])
    reach = max(0.0, float(visibility_nm))
    # Angle of the observer off the vessel's bow, clockwise (starboard).
    rel = ((bearing_from_observer_deg + 180.0) - course_deg) % 360.0
    off = rel if rel <= 180.0 else rel - 360.0
    masts = 0
    if abs(off) <= SIDE_ARC_DEG and distance_nm <= min(masthead_nm, reach):
        masts = 2 if length_m >= 50.0 else 1
        if work == "WR":
            masts = 0                       # a pilot vessel's white over red instead
        elif work == "GW":
            masts = 1 if length_m >= 50.0 else 0   # abaft and above the green
    side = distance_nm <= min(side_nm, reach)
    green = side and -HEAD_ON_DEG <= off <= SIDE_ARC_DEG
    red = side and -SIDE_ARC_DEG <= off <= HEAD_ON_DEG
    stern = abs(off) >= SIDE_ARC_DEG and distance_nm <= min(stern_nm, reach)
    round_lights = work if work in ALL_ROUND and distance_nm <= min(round_nm, reach) else ""
    if not (masts or red or green or stern or round_lights):
        return None
    # Seen from starboard the bow points to the observer's right.
    facing = "R" if off >= 0.0 else "L"
    return "%s%d%s%s%s%s" % (facing, masts, "r" if red else "-", "g" if green else "-",
                             "s" if stern else "-", round_lights)


def aircraft_code(course_deg: float, bearing_from_observer_deg: float, distance_nm: float,
                  visibility_nm: float) -> str | None:
    """The lights a civil aircraft shows the observer, or ``None``."""
    reach = max(0.0, float(visibility_nm))
    if distance_nm > min(AIRCRAFT_ANTI_COLLISION_NM, reach):
        return None
    rel = ((bearing_from_observer_deg + 180.0) - course_deg) % 360.0
    off = rel if rel <= 180.0 else rel - 360.0
    near = distance_nm <= min(AIRCRAFT_NAV_NM, reach)
    green = near and -HEAD_ON_DEG <= off <= AIRCRAFT_WING_ARC_DEG
    red = near and -AIRCRAFT_WING_ARC_DEG <= off <= HEAD_ON_DEG
    tail = near and abs(off) >= AIRCRAFT_WING_ARC_DEG
    return "%s0%s%s%sAC" % ("R" if off >= 0.0 else "L", "r" if red else "-",
                             "g" if green else "-", "s" if tail else "-")


def valid(value) -> bool:
    return value is None or (isinstance(value, str) and CODE_RE.match(value) is not None)


def facing(value: str | None) -> int:
    """Silhouette facing for a code: +1 bow right, -1 bow left (default)."""
    return 1 if value and value[0] == "R" else -1


def describe(value: str) -> tuple[tuple[str, ...], str | None, str | None]:
    """What a lookout reads from a code: (lights seen, aspect, work).

    ``lights`` are the single lights in the order he calls them
    (``masthead1``/``masthead2``, ``red``, ``green``, ``stern``, then the
    all-round set or ``ac``); ``aspect`` is his reading of the side he sees
    (``head_on``, ``starboard``, ``port``, ``stern``, ``masthead``) and
    ``work`` the all-round lights' meaning, each ``None`` when absent.
    """
    masts, red, green, stern = int(value[1]), value[2] == "r", value[3] == "g", value[4] == "s"
    extra = value[5:] or None
    lights = []
    if masts:
        lights.append("masthead%d" % masts)
    lights += [name for name, on in (("red", red), ("green", green), ("stern", stern)) if on]
    if extra:
        lights.append(extra.lower())
    aspect = ("head_on" if red and green else "starboard" if green else "port" if red
              else "stern" if stern else "masthead" if masts else None)
    return tuple(lights), aspect, None if extra is None else extra.lower()
