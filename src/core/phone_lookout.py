"""Phone lookouts: the bridge lookout and the boat's periscope played on a
phone (Remote Crew roles ``lookout`` and ``uboot_lookout``).

While a phone holds the frigate's ``lookout`` role the automatic lookout
stops reporting: what the eye makes out stays in ``game.lookout_eye``, the
phone draws it in its binoculars, and only a sighting the player calls
(by voice or by tapping it) is published to the bridge as a ``LOOKOUT``
track, entered in the lookout log and said aloud.  A called track keeps
being followed by the lookout as before.  On the boat the periscope's
sightings stay the optics picture (attack computer, stadimeter); only the
crew's automatic "sighting" notices give way to the player's calls.

A call is confirmed only when a current sighting of a matching category
lies within ``LOOKOUT_CALL_BEARING_TOL_DEG`` (and, when a range was given,
within ``LOOKOUT_CALL_RANGE_TOL_FRAC``) of it: a report of what is not
there is refused.  Everything here is transient (never saved); after a load
the tracks already published count as called.
"""

from __future__ import annotations

from collections import deque

from src.core import config
from src.core.i18n import message
from src.sensors import lookout_id

ROLE = "lookout"
BOAT_ROLE = "uboot_lookout"
# What a player may call, and what each fits (lookout kinds, periscope classes).
CATEGORIES = ("contact", "ship", "warship", "merchant", "aircraft", "submarine",
              "torpedo")
_KIND_CATEGORIES = {
    "SURFACE": frozenset({"contact", "ship", "warship", "merchant"}),
    "SUB": frozenset({"contact", "ship", "submarine"}),
    "FLG": frozenset({"contact", "aircraft"}),
    "TORP": frozenset({"contact", "torpedo"}),
    "UNKNOWN": frozenset({"contact", "ship"}),
}
_SCOPE_CATEGORIES = {
    "warship": frozenset({"contact", "ship", "warship"}),
    "merchant": frozenset({"contact", "ship", "merchant"}),
    "unknown": frozenset({"contact", "ship", "warship", "merchant"}),
    "aircraft": frozenset({"contact", "aircraft"}),
    "torpedo": frozenset({"contact", "torpedo"}),
}
_WARSHIP_CODES = frozenset(("WARSHIP", "CARRIER", "CRUISER", "DESTROYER", "FRIGATE",
                            "CORVETTE", "NAVAL_AUXILIARY", "MINE_WARFARE"))
_MERCHANT_CODES = frozenset(("MERCHANT", "TANKER", "CARGO", "PASSENGER"))
# The eye keeps a sighting this long after it last had it (like the outlines).
EYE_HOLD_S = config.LOOKOUT_EPOCH_S * 6
CALLS_MAX = 12


class EyeSighting:
    """What the lookout sees but has not called (a track-shaped record)."""

    __slots__ = ("track_id", "kind", "label", "level", "bearing", "range_nm", "quality",
                 "last_seen")

    def __init__(self, track_id, kind, label, level, bearing, range_nm, quality, now):
        self.track_id = track_id
        self.kind = kind
        self.label = label
        self.level = level
        self.bearing = bearing
        self.range_nm = range_nm
        self.quality = quality
        self.last_seen = now


def reset(game) -> None:
    """Transient state of both phone lookouts (new world, load, reset)."""
    game.lookout_eye = {}
    game.lookout_phone = False
    game.lookout_calls = deque(maxlen=CALLS_MAX)
    game._lookout_call_seq = 0


def manned(game, role: str) -> bool:
    """A phone currently holds ``role`` (a Remote Crew lease)."""
    commander = getattr(game, "commander", None)
    query = getattr(commander, "station_leased", None)
    if query is None:
        return False
    try:
        return bool(query(role))
    except (ValueError, TypeError, AttributeError):
        return False


def refresh(game) -> None:
    """Once per lookout pass: is the phone on watch, and forget old sightings."""
    game.lookout_phone = manned(game, ROLE)
    if not game.lookout_phone:
        game.lookout_eye.clear()
        return
    now = game.sim_t
    for track_id in [key for key, eye in game.lookout_eye.items()
                     if not 0.0 <= now - eye.last_seen <= EYE_HOLD_S]:
        del game.lookout_eye[track_id]


def see(game, track_id, kind, label, level, bearing, range_nm, quality) -> None:
    """The eye has a sighting the player has not called yet."""
    eye = game.lookout_eye.get(track_id)
    if eye is None:
        game.lookout_eye[track_id] = EyeSighting(track_id, kind, label, level, bearing,
                                                 range_nm, quality, game.sim_t)
        return
    eye.kind, eye.label, eye.level = kind, label, level
    eye.bearing, eye.range_nm, eye.quality, eye.last_seen = (bearing, range_nm, quality,
                                                            game.sim_t)


def eye_class(kind: str, label) -> str:
    """Sight-scene class of an eye sighting (as the outlines draw it)."""
    _level, code, _identified = lookout_id.decode(label)
    if code in _WARSHIP_CODES:
        return "warship"
    if code in _MERCHANT_CODES:
        return "merchant"
    return {"FLG": "aircraft", "TORP": "torpedo"}.get(kind, "unknown")


def _fits(category: str, kind: str, label) -> bool:
    if category not in _KIND_CATEGORIES.get(kind, _KIND_CATEGORIES["UNKNOWN"]):
        return False
    cls = eye_class(kind, label)
    if category == "warship":
        return cls != "merchant"
    if category == "merchant":
        return cls != "warship"
    return True


def _off(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _range_fits(called, measured) -> bool:
    if called is None:
        return True
    if measured is None:
        return False
    return abs(called - measured) <= max(config.LOOKOUT_CALL_RANGE_MIN_NM,
                                         config.LOOKOUT_CALL_RANGE_TOL_FRAC * measured)


def _log(game, side, category, bearing, range_nm, confirmed) -> None:
    game._lookout_call_seq += 1
    game.lookout_calls.append(dict(seq=game._lookout_call_seq, t=game.sim_t, side=side,
                                   category=category, bearing=bearing % 360.0,
                                   range_nm=range_nm, confirmed=confirmed))


def call(game, category: str, bearing: float, range_nm=None):
    """The frigate's phone lookout calls a sighting; True or a reason."""
    if category not in CATEGORIES:
        return "invalid_value"
    if game.damage.station_down("bridge"):
        return "bridge_down"
    now = game.sim_t
    best = None
    for eye in game.lookout_eye.values():
        off = _off(eye.bearing, bearing)
        if (now - eye.last_seen <= config.LOOKOUT_EPOCH_S * 2
                and off <= config.LOOKOUT_CALL_BEARING_TOL_DEG
                and _fits(category, eye.kind, eye.label)
                and _range_fits(range_nm, eye.range_nm)
                and (best is None or off < best[0])):
            best = (off, eye)
    if best is None:
        # A sighting already on the bridge (called before, or reported before
        # the phone took the watch) may be called again: a repeated report.
        for track in game.lookout_sightings():
            off = _off(track.bearing, bearing)
            if (now - track.last_seen <= config.LOOKOUT_EPOCH_S * 2
                    and off <= config.LOOKOUT_CALL_BEARING_TOL_DEG
                    and _fits(category, track.kind, track.label)
                    and _range_fits(range_nm, track.range_nm)
                    and (best is None or off < best[0])):
                best = (off, track)
        if best is None:
            _log(game, "frigate", category, bearing, range_nm, False)
            return "lookout_not_confirmed"
        track = best[1]
        game._lookout_report(track.kind, track.label, track.bearing, track.range_nm,
                             called=category)
        _log(game, "frigate", category, track.bearing, track.range_nm, True)
        return True
    eye = best[1]
    del game.lookout_eye[eye.track_id]
    game.air_picture.observe(
        track_id=eye.track_id, kind=eye.kind, target_id=0, source="LOOKOUT",
        bearing=eye.bearing, range_nm=eye.range_nm, observer_x=game.ship.x,
        observer_y=game.ship.y, course=None, quality=eye.quality, now=now,
        label=eye.label, bearing_uncertainty_deg=config.LOOKOUT_BEARING_ERR_DEG / 3 ** .5)
    game._lookout_report(eye.kind, eye.label, eye.bearing, eye.range_nm, called=category)
    _log(game, "frigate", category, eye.bearing, eye.range_nm, True)
    return True


def called_text(category: str, bearing: float, range_nm):
    """The feed line (and spoken callout) of a confirmed call."""
    return message(f"lookout.called.{category}", bearing=f"{bearing % 360.0:03.0f}",
                   range="?" if range_nm is None else f"{range_nm:.1f}")


def boat_manned(game) -> bool:
    return manned(game, BOAT_ROLE)


def boat_call(game, boat, category: str, bearing: float, range_nm=None):
    """The boat's phone periscope calls a sighting; True or a reason."""
    from src.core import opfor
    if category not in CATEGORIES:
        return "invalid_value"
    if not opfor.scope_available(boat):
        return "uboot_mast_down"
    now = game.sim_t
    best = None
    for row in boat.orders.sightings:
        off = _off(row["bearing"], bearing)
        if (0.0 <= now - row["t"] <= 2.0 and off <= config.LOOKOUT_CALL_BEARING_TOL_DEG
                and category in _SCOPE_CATEGORIES.get(row["cls"], frozenset())
                and (range_nm is None or row["range_nm"] is None
                     or _range_fits(range_nm, row["range_nm"]))
                and (best is None or off < best[0])):
            best = (off, row)
    if best is None:
        _log(game, "boat", category, bearing, range_nm, False)
        return "lookout_not_confirmed"
    row = best[1]
    boat.notice(now, "sonar", message(f"uboot.event.scope_called.{category}",
                                      bearing=f"{row['bearing'] % 360.0:03.0f}"),
                stamp=game.world.format_time())
    _log(game, "boat", category, row["bearing"], range_nm, True)
    return True


def calls(game, side: str) -> list:
    """The phone's own recent calls of one side, newest first (for its view)."""
    return [dict(row) for row in reversed(game.lookout_calls) if row["side"] == side]
