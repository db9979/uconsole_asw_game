"""Remote Crew projections of the phone lookouts (``lookout``, ``uboot_lookout``).

The frigate's phone sees what its lookout's eye has (called or not: measured
bearing, the class he made out, apparent size) and the calls it made; the
boat's phone sees the periscope's own sightings.  Never a target's position,
identity or reference.
"""

from src.commander import projections
from src.core import config, phone_lookout
from src.ui.stations.bridge import lookout_outlines
from src.ui.uboot_scope import full_span


def _number(value):
    return projections._number(value)


def _calls(game, side):
    now = game.sim_t
    return [dict(seq=int(row["seq"]), age_s=projections._age(now, row["t"]),
                 category=str(row["category"]), bearing=_number(row["bearing"]),
                 range_nm=_number(row["range_nm"]), confirmed=bool(row["confirmed"]))
            for row in phone_lookout.calls(game, side)[:8]]


def _outline(bearing, span, cls, stale, lights, elevation, aob, called, range_nm=None):
    return dict(bearing=_number(bearing), span_deg=_number(span), cls=str(cls),
                stale=bool(stale), lights=projections._nav_lights(lights),
                elevation_deg=_number(elevation), aob_deg=_number(aob), called=bool(called),
                range_nm=_number(range_nm))


def _frigate(game):
    from src.ui import horizon
    weather = game.world.weather_values()
    # Pitch and roll by the heading to the sea; the phone turns them with its
    # own line of sight (as the bridge binoculars in the browser).
    pitch, roll = horizon.hull_motion(0, game.sim_t, weather["sea_state"],
                                      weather["wind_from_deg"] - game.ship.course)
    offset, tilt = horizon.view_motion(pitch, roll)
    called = lookout_outlines(game, game.lookout_sightings())
    unseen = lookout_outlines(game, sorted(game.lookout_eye.values(),
                                           key=lambda eye: eye.track_id))
    outlines = ([_outline(*row, True) for row in called]
                + [_outline(*row, False) for row in unseen])[:24]
    return dict(side="frigate", available=not game.damage.station_down("bridge"),
                manned=bool(game.lookout_phone), course=_number(game.ship.course % 360.0),
                relative_deg=None, fov_deg=_number(config.LOOKOUT_GLASSES_FOV_DEG),
                powers=[_number(value) for value in config.LOOKOUT_GLASSES_POWERS],
                window_deg=None, visibility_nm=_number(weather["visibility_nm"]),
                sea_state=_number(weather["sea_state"]), horizon_offset=_number(offset),
                horizon_tilt=_number(tilt), motion_pitch=_number(pitch),
                motion_roll=_number(roll), sky=projections._sky(game), outlines=outlines,
                calls=_calls(game, "frigate"))


def _boat(game, boat):
    scope = projections._uboot_scope(game, boat)
    now = game.sim_t
    elevation = boat.orders._elevation
    outlines = [_outline(row["bearing"], full_span(row["span_deg"], row["aob"]),
                         "aircraft" if row["kind"] == "FLG" and row["ref"] in elevation
                         else row["cls"], row["stale"], row["lights"],
                         elevation.get(row["ref"]) if row["kind"] == "FLG" else None,
                         row["aob"], False, row["range_nm"])
                for row in (dict(sighting, stale=not 0.0 <= now - sighting["t"] <= 1.0,
                                 lights=(None if now - sighting["t"] > 1.0 else
                                         boat.orders._lights.get(sighting["ref"])),
                                 aob=(None if now - sighting["t"] > 1.0 else
                                      boat.orders._aspect.get(sighting["ref"])))
                            for sighting in boat.orders.sightings[:config.UBOOT_SIGHTINGS_MAX])]
    return dict(side="boat", available=scope["available"], manned=phone_lookout.boat_manned(game),
                course=_number(boat.sub.course % 360.0), relative_deg=scope["relative_deg"],
                fov_deg=scope["fov_deg"],
                powers=[_number(value) for value in config.UBOOT_SCOPE_POWERS],
                window_deg=scope["window_deg"],
                visibility_nm=scope["visibility_nm"], sea_state=scope["sea_state"],
                horizon_offset=scope["horizon_offset"], horizon_tilt=scope["horizon_tilt"],
                motion_pitch=None, motion_roll=None, sky=scope["sky"], outlines=outlines,
                calls=_calls(game, "boat"))


def build_lookout_states(game, status, boat, redacted):
    """The two phone roles' states; the periscope's is redacted without a crewed boat."""
    frigate = projections._common(game, status, "lookout")
    frigate["autocrew"] = dict(enabled=False, status="off")
    frigate["autocrew_overview"] = []
    frigate["lookout"] = _frigate(game)
    states = {"lookout": frigate}
    if boat is None:
        states["uboot_lookout"] = dict(redacted)
    else:
        state = projections._opfor_common(game, status, "uboot_lookout", boat)
        state["uboot_lookout"] = _boat(game, boat)
        states["uboot_lookout"] = state
    return states
