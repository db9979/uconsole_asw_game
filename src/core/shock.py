"""The own ship shaken by a detonation close by (a display cue only).

A detonation inside ``LIGHT_NM`` of the own frigate or the crewed boat adds a
``shock_light`` or (inside ``HEAVY_NM``) ``shock_heavy`` cue to that side's
bounded sound-event list.  The uConsole (``src/ui/shock_fx.py``) and the
browser shake the picture, dim the light and, after a heavy one, show a
cracked instrument glass.  The cue plays no sound of its own (the detonation
has one) and never touches the simulation; like every sound event it is
transient and never saved.  Only the own ship's position is used.
"""

from __future__ import annotations

HEAVY_NM = 0.15
LIGHT_NM = 0.6
CUES = ("shock_light", "shock_heavy")


def cue(distance_nm: float) -> str | None:
    """The shock cue of a detonation ``distance_nm`` from the own ship."""
    if distance_nm <= HEAVY_NM:
        return "shock_heavy"
    if distance_nm <= LIGHT_NM:
        return "shock_light"
    return None
