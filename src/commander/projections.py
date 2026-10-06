"""Detached, role-scoped Remote Crew protocol-v2 projections.

The caller owns main-thread access to ``game``.  Every value returned here is a
JSON scalar or a newly allocated container; transport threads never receive a
simulation object.
"""

from copy import deepcopy
import math
import weakref

from src.core import attack_computer, boat_esm, chart_history, boat_missions, boat_threat, config, opfor, plot
from src.core import boat_nav, buoy_antenna, sight_events, station_alarms, status_tips
from src.commander.v2 import schema as web_schema
from src.core.autocrew import AUTOCREW_STATIONS
from src.enemies.damage_control import COMPARTMENTS, capacity_kg
from src.sonar import analysis_tools
from src.ship.ship import NOISE_LEVEL_MAX
from src.core.i18n import localize
from src.core.version import APP_VERSION
from src.commander.server import OPFOR_ROLES, STATE_MAX_BYTES, STATIONS
from src.sensors.esm import (
    ESMCorrelationEvidence,
    ESM_BROADBAND_SENSOR_COUNT,
    ESM_DF_SENSOR_COUNT,
    ESM_FREQUENCY_MAX_HZ,
    ESM_FREQUENCY_MIN_HZ,
    correlate_observations,
    signal_state,
    track_is_operational,
    spectrum_band,
)
from src.sensors.fusion import live_members
from src.physics import ship_dynamics


ROLE_NAMES = STATIONS


def _number(value):
    return (value if type(value) in (int, float) and math.isfinite(value)
            else None)


def _pan(value):
    """A sound cue's left/right position (-1..+1, 1/8 steps), or None centred."""
    value = _number(value)
    return None if value is None else round(max(-1.0, min(1.0, value)) * 8.0) / 8.0


def _age(now, stamp):
    stamp = _number(stamp)
    return now - stamp if stamp is not None and 0 <= stamp <= now else None


_SIGHTINGS_MAX = config.LOOKOUT_REPORTS_MAX


def _sightings(game):
    """Bridge-lookout reports, newest first; codes are localized in the browser."""
    return [dict(time=str(row["stamp"])[:8],
                 sighted=row["kind"] if row["code"] is None else None,
                 code=row["code"],
                 type=None if row["type_name"] is None else str(row["type_name"])[:80],
                 bearing=_number(row["bearing"]), range_nm=_number(row["range_nm"]),
                 lights=_nav_lights(row.get("lights")))
            for row in reversed(getattr(game, "lookout_reports", [])[-_SIGHTINGS_MAX:])]


def _own_navigation(game):
    ship = game.ship
    return {key: _number(getattr(ship, key)) for key in (
        "x", "y", "course", "speed", "target_course", "target_speed",
        "rudder_angle", "yaw_rate", "turn_radius_nm")}


_ATOMIC = (type(None), bool, int, float, str)


def _detach(value):
    """Detached copy of a projection value; scalars need no deepcopy call."""
    return value if type(value) in _ATOMIC else deepcopy(value)


def _observation(row, fields):
    observation = {key: _detach(row[key]) for key in fields}
    if "label" in observation and "_display_id" in row:
        observation["label"] = row["_display_id"]
    return observation


# Row field allowlists: one source for Python and the generated browser schema.
_TACTICAL_FIELDS = web_schema.TACTICAL_FIELDS
_SONAR_FIELDS = web_schema.SONAR_FIELDS
_RADIO_FIELDS = web_schema.RADIO_FIELDS
_HELICOPTER_TACTICAL_FIELDS = web_schema.HELICOPTER_TACTICAL_FIELDS
RADIO_TASK_FIELDS = web_schema.RADIO_TASK_FIELDS
RADIO_REPORT_REASONS = web_schema.RADIO_REPORT_REASONS

_HISTORY_ROWS_MAX = config.LOFAR_HISTORY_COLS
_BROADBAND_BINS_MAX = 180
_BROADBAND_LONG_ROWS_MAX = config.SONAR_BROADBAND_LONG_ROWS
_BROADBAND_LONG_BINS_MAX = 90
_DEMON_HISTORY_ROWS_MAX = config.SONAR_DEMON_HISTORY_ROWS
_TMA_CONTACTS_MAX = 32
_TMA_POINTS_MAX = 24
_ECHOES_MAX = 40
_MAP_ROWS_MAX = 128


def _waterfall_row(values, maximum):
    """One waterfall row rounded to 1/1000: the browser paints at most 256
    shades, and full floats would push the helicopter state past its limit."""
    return [round(value, 3) for value in _series(values, maximum)]


def _series(values, maximum, stride=1):
    """Return a detached finite numeric series or an empty invalid sentinel."""
    if not isinstance(values, (list, tuple)):
        return []
    result = []
    for value in values[::stride][:maximum]:
        number = _number(value)
        if number is None:
            return []
        result.append(number)
    return result


def _mean_binned_series(values, maximum):
    """Downsample a circular power scan without dropping bearing sectors."""
    source = _series(values, len(values)) if isinstance(values, (list, tuple)) else []
    if not source or maximum < 1:
        return []
    if len(source) <= maximum:
        return source
    result = []
    for index in range(maximum):
        start = index * len(source) // maximum
        stop = (index + 1) * len(source) // maximum
        group = source[start:max(start + 1, stop)]
        result.append(sum(group) / len(group))
    return result


def _map_rows(rows, *, include_hfdf=False):
    return [_observation(row, _TACTICAL_FIELDS) for row in rows
            if row.get("_opz") or (include_hfdf and row["source"] == "HFDF")][
                :_MAP_ROWS_MAX]


def _weapon_observation(row):
    return _observation(row, ("ref", "label", "domain", "source", "affiliation",
                              "classification", "bearing", "range_nm", "x", "y",
                              "depth_m", "course", "speed_kn", "quality", "age_s",
                              "fix_age_s", "bearing_uncertainty_deg",
                              "range_uncertainty_nm"))


def _direct_fire_observations(rows, refs):
    result = []
    for row in rows:
        ref = refs.get(row["ref"])
        if ref is None:
            continue
        observation = _weapon_observation(row)
        observation["ref"] = ref
        result.append(observation)
    return result[:_MAP_ROWS_MAX]


def _weather_station(game):
    """Observation-safe weather & sonar analysis block for every role.

    Own-ship atmosphere and flight weather; the ocean profile only after a
    sonar bathythermograph measurement (``profile`` is null before)."""
    data = game.weather_station_data()
    a, p = data["atmosphere"], data["profile"]
    boat = data.get("boat")
    # Exact allowlists shared with the browser validator (v2/schema.py).
    atmosphere = {key: (_number(a[key]) if isinstance(a[key], float) else a[key])
                  for key in (web_schema.WEATHER_ATMOSPHERE_FIELDS if boat is None
                              else web_schema.WEATHER_BOAT_ATMOSPHERE_FIELDS)}
    if boat is None:
        f = data["flight"]
        flight = {key: (_number(value) if isinstance(value, float) else value)
                  for key, value in f.items() if key != "limits"}
        flight["limits"] = {key: _number(float(value)) for key, value in f["limits"].items()}
    profile = None
    if p is not None:
        profile = dict(
            age_s=_number(p["age_s"]), offset_nm=_number(p["offset_nm"]),
            stale=bool(p["stale"]), thermocline_m=_number(p["thermocline_m"]),
            water_depth_m=_number(p["water_depth_m"]),
            depths_m=[_number(float(value)) for value in p["depths_m"]][:64],
            speeds_m_s=[_number(float(value)) for value in p["speeds_m_s"]][:64],
            sofar_axis_m=(None if p["sofar_axis_m"] is None
                          else _number(float(p["sofar_axis_m"]))),
            cz_bands_nm=[[_number(float(a_)), _number(float(b_))]
                         for a_, b_ in p["cz_bands_nm"]][:8],
            range_nm=_number(p["range_nm"]),
            rays=[[[_number(float(r)), _number(float(z))] for r, z in ray][:64]
                  for ray in p["rays"]][:9],
            depth_edges_m=[_number(float(value)) for value in p["depth_edges_m"]][:32],
            shadow=[[bool(cell) for cell in row][:32] for row in p["shadow"]][:32],
            dip_relative_to_layer=p["dip_relative_to_layer"])
    effects = {key: bool(value) for key, value in data["effects"].items()}
    if boat is not None:
        return dict(atmosphere=atmosphere, effects=effects,
                    boat=_weather_boat(boat), profile=profile)
    return dict(atmosphere=atmosphere, effects=effects, flight=flight, profile=profile)


def _weather_boat(boat):
    """The crewed boat's weather block: environment and own boat only."""
    numbers = ("mast_radar_nm", "mast_radar_calm_nm", "sighting_nm", "sighting_ref_nm",
               "snorkel_max_kn", "snorkel_noise_db")
    row = {key: _number(float(boat[key])) for key in numbers}
    row.update(
        ambient_bands_hz=[_number(float(value)) for value in boat["ambient_bands_hz"]][:8],
        ambient_excess_db=[_number(float(value)) for value in boat["ambient_excess_db"]][:8],
        snorkel_available=bool(boat["snorkel_available"]),
        snorkeling=bool(boat["snorkeling"]),
        snorkel_lines_hz=[_number(float(value)) for value in boat["snorkel_lines_hz"]][:4])
    return {key: row[key] for key in web_schema.WEATHER_BOAT_FIELDS}


def _plot(game, layer=None, own=None):
    """The shared crew plot: detached copies plus the DR line's CPA to own ship.

    ``layer``/``own`` give another crew's plot and platform (the crewed boat)."""
    objects = []
    own = game.ship if own is None else own
    for item in (game.plot if layer is None else layer).objects:
        # "shape", not "kind": the browser rejects any "kind" key as a
        # possible entity-type leak.
        row = {("shape" if key == "kind" else key):
               (_number(value) if type(value) is float else value)
               for key, value in item.items()}
        if item["kind"] == "dr":
            now_x, now_y = plot.dr_position(item, game.sim_t)
            distance, seconds = plot.cpa(item, game.sim_t, own.x, own.y,
                                         own.course, own.speed)
            row.update(now_x=_number(now_x), now_y=_number(now_y),
                       cpa_nm=_number(distance), cpa_s=_number(seconds))
        objects.append(row)
    side = "frigate" if layer is None else ("boat", own.id)
    return dict(objects=objects, max_objects=plot.MAX_OBJECTS, max_label=plot.MAX_LABEL,
                trail=_own_trail(game, side), fx=_map_fx(game, side))


def _map_fx(game, side):
    """Own pings, the echoes they brought back and own charges going off
    (age, x, y), for the charts' moving marks (own-side knowledge only)."""
    fx = getattr(game, "map_fx", None)
    rows = fx.rows(side, game.sim_t) if fx is not None else {}
    return {key: [[_number(age), _number(x), _number(y)] for age, x, y in rows.get(key, ())]
            for key in ("pings", "echoes", "splashes")}


def _opz_trails(game, refs, ref_by_track):
    """Earlier OPZ positions of the published picture reports (display aid
    from the chart history: published positions only), newest last."""
    history = getattr(game, "chart_history", None)
    side = history.sides.get("frigate") if history is not None else None
    if side is None:
        return []
    wanted = set(refs)
    trails = []
    for key, rows in side.opz.items():
        ref = ref_by_track.get(key)
        if ref is None or ref not in wanted or not rows:
            continue
        trails.append(dict(ref=ref, points=[
            [_number(round(x, 3)), _number(round(y, 3)),
             _number(round(max(0.0, game.sim_t - t), 1))]
            for t, x, y in list(rows)[-web_schema.OPZ_TRAIL_POINTS:]]))
        if len(trails) >= web_schema.OPZ_TRAIL_MAX:
            break
    return trails


def _own_trail(game, side_key):
    """The own ship's (or boat's) recent track: own-platform truth only."""
    history = getattr(game, "chart_history", None)
    side = history.sides.get(side_key) if history is not None else None
    if side is None:
        return []
    return [[_number(x), _number(y)] for x, y in list(side.own)[-chart_history.OWN_POINTS:]]


def _common(game, status, role):
    weather = game.world.weather_values()
    return dict(protocol=2, version=APP_VERSION, session=status["session"],
                epoch=status["epoch"], revision=status["revision"],
                seq=status["seq"], phase=status["phase"], role=role,
                chart_revision=status["session"],
                clock=dict(sim=_number(game.sim_t), mission=_number(game.mission_time),
                           world=_number(game.world.hour)),
                 environment=dict(
                     sea_state=game.world.sea_state,
                     effective_sea_state=_number(weather["sea_state"]),
                     is_night=bool(game.world.is_night()),
                     weather=game.world.weather_kind(),
                     wind_from_deg=_number(weather["wind_from_deg"]),
                     wind_speed_kn=_number(weather["wind_speed_kn"]),
                     rain_intensity=_number(weather["rain_intensity"]),
                     visibility_nm=_number(weather["visibility_nm"]),
                     # Thunderstorm activity 0..1: sferics on ESM and HF/DF.
                     storm=_number(game.world.thunderstorm())),
                weather_station=_weather_station(game),
                plot=_plot(game),
                alarms=_alarm_rows(station_alarms.frigate(game)),
                mission=dict(name=localize(game.mission_name_display(), game.tr),
                             objective=localize(game.mission_objective_display(), game.tr),
                             # A free patrol has no time limit to count down.
                             remaining_s=(None if game.mission.open_ended else _number(
                                 game.mission.remaining_s(game.mission_time)))),
                audio=dict(
                    events=[dict(seq=int(row["seq"]), cue=str(row["kind"]),
                                 pan=_pan(row.get("pan")))
                            for row in list(game._sound_events)[-16:]],
                    # Spoken crew reports: the feed lines' key and bearing
                    # only; each browser words them in its own language.
                    callouts=game.callouts.detached()),
                hit_view=_hit_view(game, "frigate"),
                crew_noise=_crew_noise(game, "frigate"))


def _outline_dicts(rows) -> list:
    """Eyepiece outline rows (``lookout_outlines``/``scope_outlines``) as
    published outlines (``LOOKOUT_OUTLINE_FIELDS``)."""
    return [dict(bearing=_number(bearing), span_deg=_number(span), cls=str(cls),
                 stale=bool(stale), lights=_nav_lights(lights),
                 elevation_deg=_number(elevation), aob_deg=_number(aob),
                 model=None if model is None else str(model), way=_number(way),
                 range_nm=_number(range_nm))
            for bearing, span, cls, stale, lights, elevation, aob, model, way, range_nm in rows]


def _crew_noise(game, side):
    """Noise discipline of one side (``src/core/noise_discipline.py``): the
    crew's held microphone level, its thresholds and whether "Ruhe im Boot"
    (silent running / quiet mode) is ordered."""
    from src.core import noise_discipline as nd
    if side == "uboot":
        quiet = game.opfor is not None and nd.sub_quiet(game.opfor.sub)
    else:
        quiet = bool(game.ship.quiet_mode)
    return dict(voice=int(game.crew_voice_level(side)), safe=nd.VOICE_SAFE,
                loud=nd.VOICE_LOUD, max=nd.VOICE_LEVEL_MAX, quiet=bool(quiet))


def _hit_view(game, side):
    """The hit picture (``src/core/hit_view.py``) of one side, or None: in
    sight the side's own eyepiece outlines and sight events toward the hit,
    heard only its bearing."""
    from src.core import hit_view
    view = hit_view.current(game, side)
    if view is None:
        return None
    result = dict(mode=view["mode"], kind=view["kind"],
                  bearing=_number(view["bearing"] % 360.0), age_s=_number(view["age_s"]),
                  fov_deg=_number(hit_view.FOV_DEG), visibility_nm=None, sea_state=None,
                  sky=None, outlines=[], events=[], eye_m=None)
    if view["mode"] == "sight":
        weather = game.world.weather_values()
        if side == "uboot":
            from src.ui.uboot_scope import scope_outlines
            boat = game.opfor
            outlines = scope_outlines(game, boat) if opfor.scope_available(boat) else []
            rows = sight_events.boat_rows(game, boat)
            eye = opfor.eye_height_m(boat)
        else:
            from src.ui.stations.bridge import eye_outlines
            outlines = eye_outlines(game, game.lookout_sightings())
            rows = sight_events.frigate_rows(game)
            from src.sensors.visual import LOOKOUT_EYE_HEIGHT_M as eye
        result.update(eye_m=_number(eye), visibility_nm=_number(weather["visibility_nm"]),
                      sea_state=_number(weather["sea_state"]), sky=_sky(game),
                      outlines=_outline_dicts(outlines[:12]),
                      events=_sight_events(rows, game.sim_t))
    return result


def _deck_motion(game) -> dict:
    """Own ship's roll and pitch against the flight-deck limits and how long
    the deck has been quiet (own ship: legitimate truth)."""
    from src.air import helicopter as helicopter_physics
    quiet = float(game.ship.deck_quiet_s)
    return dict(roll_deg=_number(game.ship.roll), pitch_deg=_number(game.ship.pitch),
                roll_limit_deg=_number(helicopter_physics.DECK_ROLL_LIMIT_DEG),
                pitch_limit_deg=_number(helicopter_physics.DECK_PITCH_LIMIT_DEG),
                quiet_s=_number(min(quiet, helicopter_physics.DECK_QUIET_MAX_S)),
                window_s=_number(helicopter_physics.DECK_WINDOW_S),
                window_open=bool(helicopter_physics.deck_window_open(
                    quiet, game.ship.roll, game.ship.pitch)))


def _alarm_rows(levels: dict) -> list:
    """The station tabs' alarm lamps, in station order (display only)."""
    return [dict(station=station, level=level) for station, level in sorted(levels.items())]


def redacted_state(status):
    """Return the exact unassigned/status-only v2 envelope."""
    return dict(protocol=2, version=APP_VERSION, session=status["session"],
                epoch=status["epoch"], revision=status["revision"],
                seq=status["seq"], phase=status["phase"], role=None,
                chart_revision=status["session"])


def redacted_chart(status):
    return dict(protocol=2, revision=status["session"], size_nm=500,
                landmasses=[], disclaimer="")


def known_chart(status, chart):
    return dict(protocol=2, revision=status["session"],
                size_nm=_number(chart["size_nm"]),
                landmasses=deepcopy(chart["landmasses"]),
                disclaimer=str(chart["disclaimer"])[:512])


def _tma_summary(track, now):
    """Bearing rate and own-ship legs, as on the uConsole TMA page."""
    from src.ui.sonar_view import tma_observation_summary
    summary = tma_observation_summary(track, now)
    return dict(rate_deg_min=_number(summary["rate"]), legs=int(summary["legs"]))


def _sonar_observer(game):
    """The active sonar workstation's listening platform (frigate or boat)."""
    observer = getattr(game, "sonar_observer", None)
    return game.ship if observer is None else observer


def _sonar_station_down(game):
    down = getattr(game, "_sonar_down", None)
    return bool(down()) if down is not None else game.damage.station_down("sonar")


# Quantized history rows per sonar workstation. A history row is appended once
# and never changes, so its projected bins depend only on the row and the
# operator settings; recomputing 600 s of rows on every 2 Hz publication was
# the largest main-thread cost of Remote Crew. Keyed weakly by the workstation
# (no aliasing after a world reset); rows are keyed by identity and stamp and
# pruned to the rows still shown, so the cache is bounded by the histories.
_ROW_CACHE = weakref.WeakKeyDictionary()


def _cached_rows(sonar, name, settings, stamps, rows, compute):
    """Return ``[(stamp, bins)]`` for the rows, computing only unseen ones."""
    caches = _ROW_CACHE.get(sonar)
    if caches is None:
        caches = _ROW_CACHE[sonar] = {}
    cache = caches.get(name)
    if cache is None or cache[0] != settings:
        cache = caches[name] = (settings, {})
    previous = cache[1]
    current = {}
    result = []
    for stamp, values in zip(stamps, rows):
        key = (id(values), stamp)
        bins = previous.get(key)
        if bins is None:
            bins = compute(values)
        current[key] = bins
        result.append((stamp, bins))
    caches[name] = (settings, current)
    return result


def _sonar_visualization(game, rows, sonar_refs):
    sonar = game.sonar
    receiver = sonar.receiver
    observer = _sonar_observer(game)
    broadband = []
    long_available = bool(getattr(sonar, "broadband_long_history", ()))
    bb_source = (sonar.broadband_long_history if long_available
                 else sonar.broadband_history)
    bb_time_source = (sonar.broadband_long_times if long_available
                      else sonar.history_times)
    bb_limit = _BROADBAND_LONG_ROWS_MAX if long_available else _HISTORY_ROWS_MAX
    bb_bins = _BROADBAND_LONG_BINS_MAX if long_available else _BROADBAND_BINS_MAX
    bb_rows = list(bb_source)[-bb_limit:]
    bb_times = list(bb_time_source)[-len(bb_rows):]
    bb_gain = 10 ** (sonar.gain_db / 20)

    def broadband_bins(values):
        source_bins = (_mean_binned_series(values, bb_bins) if long_available
                       else _series(values, bb_bins))
        return [round(min(1.0, max(0.0, value * bb_gain)), 5) for value in source_bins]

    for stamp, bins in _cached_rows(sonar, "broadband", (long_available, sonar.gain_db),
                                    bb_times, bb_rows, broadband_bins):
        age = _age(game.sim_t, stamp)
        if age is not None and bins:
            broadband.append(dict(age_s=age, bins=bins))

    lofar = []
    lf_rows = list(sonar.lofar_history)[-_HISTORY_ROWS_MAX:]
    lf_times = list(sonar.lofar_times)[-len(lf_rows):]
    lf_bearings = list(sonar.lofar_bearings)[-len(lf_rows):]
    # Everything process_lofar_column reads besides the column itself. The
    # own-shaft notch follows the observer's speed continuously, so the key
    # holds the set of notched bins, which only changes when a bin enters or
    # leaves the window: exact results, no recompute while accelerating.
    shaft = ship_dynamics.own_blade_line_hz(observer.speed)
    notched = (tuple(index for index in range(config.LOFAR_BINS)
                     if abs(config.lofar_bin_freq(index) - shaft) < 5.0)
               if sonar.notch_enabled else ())
    lofar_settings = (sonar.gain_db, sonar.band_low_hz, sonar.band_high_hz,
                      bool(sonar.notch_enabled), getattr(sonar, "operator_notch_hz", None),
                      notched)

    def lofar_bins(values):
        return [round(value, 5) for value in sonar.process_lofar_column(
            _series(values, config.LOFAR_BINS), observer)]

    for (stamp, bins), bearing in zip(
            _cached_rows(sonar, "lofar", lofar_settings, lf_times, lf_rows, lofar_bins),
            lf_bearings):
        age = _age(game.sim_t, stamp)
        if age is not None and _number(bearing) is not None and bins:
            lofar.append(dict(age_s=age, bearing=_number(bearing), bins=bins))
    held = bool(sonar.peak_hold and sonar.peak_spectrum)
    tools = game.sonar_tools
    columns = list(getattr(sonar, "integration_columns", ()))
    live = (analysis_tools.integrate([column[0] for column in columns],
                                     tools.integration_s)
            if columns else receiver.spectrum)
    spectrum = [round(value, 5) for value in sonar.process_lofar_column(
        _series(sonar.peak_spectrum if held else list(live),
                config.LOFAR_BINS), observer)]
    demon_spectrum = (analysis_tools.integrate([column[2] for column in columns],
                                               tools.integration_s)
                      if columns else receiver.demon_spectrum)
    vernier = None
    if tools.vernier and columns:
        low, high = analysis_tools.vernier_window(tools.lofar_cursor_hz)
        native = analysis_tools.integrate([column[1] for column in columns],
                                          tools.integration_s)
        first, last = int(round(low * 2)), int(round(high * 2))
        vernier = dict(low_hz=_number(low), high_hz=_number(high), step_hz=0.5,
                       bins=[round(float(value), 5) for value in native[first:last + 1]])

    analysis = None
    # Automatic modulation analysis is a training aid only.
    if isinstance(sonar.demon_analysis, dict) and game.operator_assist():
        data = sonar.demon_analysis
        hypotheses = []
        for item in list(data.get("harmonic_rpm_hypotheses", ()))[:20]:
            blades = getattr(item, "blade_count", None)
            order = getattr(item, "harmonic_order", None)
            rpm = _number(getattr(item, "rpm", None))
            if type(blades) is int and type(order) is int and rpm is not None:
                hypotheses.append(dict(blades=blades, order=order, rpm=rpm))
        analysis = dict(
            modulation_peak_hz=_number(data.get("modulation_peak_hz")),
            detection_confidence=_number(data.get("detection_confidence")),
            cavitation=_number(data.get("cavitation")),
            tonal_hz=_number(data.get("tonal_hz")), hypotheses=hypotheses)

    demon_history = []
    dm_rows = list(getattr(sonar, "demon_history", ()))[-_DEMON_HISTORY_ROWS_MAX:]
    dm_times = list(getattr(sonar, "demon_times", ()))[-len(dm_rows):]
    for stamp, bins in _cached_rows(
            sonar, "demon", (), dm_times, dm_rows,
            lambda values: [round(value, 5) for value in _series(values, 80)]):
        age = _age(game.sim_t, stamp)
        if age is not None and bins:
            demon_history.append(dict(age_s=age, bins=bins))

    tma = []
    for row in (row for row in rows if row["source"].startswith("SONAR")
                and not row["source"].startswith("SONAR-BUOY-")
                and row["source"] not in ("SONAR-DIP-BRG", "SONAR-DIPPING")):
        contact = sonar_refs.get(row["ref"])
        if contact is None:
            continue
        track = sonar._tracks.get(contact.target_id)
        points = []
        for point in ([] if track is None else track.pts[-_TMA_POINTS_MAX:]):
            values = (_age(game.sim_t, point.t), _number(point.bearing),
                      _number(point.uncertainty_deg), _number(point.fx),
                      _number(point.fy), _number(point.fcourse))
            if all(value is not None for value in values):
                points.append(dict(age_s=values[0], bearing=values[1],
                    uncertainty_deg=values[2], own_x=values[3], own_y=values[4],
                    own_course=values[5]))
        solution = None
        if (row["x"] is not None and row["y"] is not None
                and contact.range_source == "tma"):
            solution = dict(x=row["x"], y=row["y"], course=row["course"],
                            speed_kn=row["speed_kn"], quality=_number(
                                contact.tma_quality), age_s=_age(
                                    game.sim_t, contact.tma_seen),
                            uncertainty_nm=row["range_uncertainty_nm"])
        # Operator hypothesis with its residuals (aligned with the newest
        # bearings sent above); the solver proposal only as a training aid.
        hypothesis = game.tma_hypothesis(contact)
        evaluation = game.tma_evaluation(contact)
        all_points = [] if track is None else list(track.pts)
        residual_rows = ([] if evaluation is None else
                         [round(float(value), 3) for value in
                          evaluation["residuals"][-len(points):]]) if points else []
        proposal = None
        if game.operator_assist():
            candidate = sonar.tma_proposals.get(contact.target_id)
            if candidate is not None and all_points:
                ref = all_points[-1]
                proposal = dict(course=_number(candidate.course),
                                speed_kn=_number(candidate.speed),
                                range_nm=_number(math.hypot(candidate.pos[0] - ref.fx,
                                                            candidate.pos[1] - ref.fy)))
        tma.append(dict(
            ref=row["ref"], bearings=points, solution=solution,
            hypothesis=dict(course=_number(hypothesis.course),
                            speed_kn=_number(hypothesis.speed_kn),
                            range_nm=_number(hypothesis.range_nm)),
            summary=_tma_summary(track, game.sim_t),
            evaluation=None if evaluation is None else dict(
                rms_deg=_number(evaluation["rms_deg"]),
                systematic_deg=_number(evaluation["systematic_deg"]),
                fit=_number(evaluation["fit"]),
                observability=_number(evaluation["observability"])),
            residuals_deg=residual_rows if len(residual_rows) == len(points) else [],
            proposal=proposal))
        if len(tma) == _TMA_CONTACTS_MAX:
            break

    bt = sonar.bt_profile
    bt_data = None
    if isinstance(bt, dict):
        depths = _series(bt.get("depths_m"), 64)
        speeds = _series(bt.get("speeds_m_s"), 64)
        cz = []
        for band in list(bt.get("cz_bands_nm", ()))[:8]:
            values = _series(band, 2)
            if len(values) == 2:
                cz.append(values)
        age = _age(game.sim_t, bt.get("t"))
        if age is not None and depths and len(depths) == len(speeds):
            bt_data = dict(age_s=age, thermocline_m=_number(bt.get("thermocline_m")),
                           water_depth_m=_number(bt.get("water_depth_m")),
                           sea_state=bt.get("sea_state") if type(
                               bt.get("sea_state")) is int else None,
                           depths_m=depths, speeds_m_s=speeds, cz_bands_nm=cz)

    echoes = []
    for echo in list(sonar.echo_history)[-_ECHOES_MAX:]:
        values = (_age(game.sim_t, echo.get("t")), _number(echo.get("bearing")),
                  _number(echo.get("range_nm")), _number(echo.get("depth_m")),
                  _number(echo.get("range_sigma_nm")),
                  _number(echo.get("depth_sigma_m")), _number(echo.get("snr_db")))
        if all(value is not None for value in values):
            echoes.append(dict(age_s=values[0], bearing=values[1],
                range_nm=values[2], depth_m=values[3], range_uncertainty_nm=values[4],
                depth_uncertainty_m=values[5], snr_db=values[6],
                array=str(echo.get("mode", ""))[:16]))

    return dict(
        broadband=dict(bearing_start_deg=0.0,
                       bearing_step_deg=360.0 / bb_bins,
                       history=broadband),
        lofar=dict(frequency_min_hz=0.0, frequency_max_hz=config.LOFAR_FMAX_HZ,
                   bin_frequencies_hz=[config.lofar_bin_freq(i)
                                       for i in range(config.LOFAR_BINS)],
                   history=lofar, spectrum=spectrum, held=held, vernier=vernier),
        demon=dict(frequency_min_hz=1.0, frequency_max_hz=80.0,
                   bin_step_hz=1.0, spectrum=_series(list(demon_spectrum), 80),
                   history=demon_history, analysis=analysis),
        tma=tma, bt=bt_data, active_echoes=echoes,
        receiver=dict(array=str(sonar._receiver_mode)[:16],
                      listen_bearing=_number(sonar.listen_bearing),
                      beam_width_deg=_number(sonar.beam_width_deg),
                      listen_mode=str(sonar.audition_mode)[:16],
                      focus_locked=bool(sonar.focus_locked),
                      audio_enabled=bool(game.sonar_audio_enabled),
                      # Own course (own-ship truth) for the bearing rose's baffles.
                      own_course=_number(_sonar_observer(game).course),
                      baffle_half_deg=_number(config.SONAR_BAFFLE_HALF_DEG)))


def _sonar(game, rows, focus_ref, target_ref, sonar_refs):
    observer = _sonar_observer(game)
    tow = game.sonar.tow_status(observer.speed)
    vds = game.sonar.vds_status(observer.speed, float(getattr(
        game.world, "effective_sea_state", game.world.sea_state)))
    band = (game.sonar.band_low_hz, game.sonar.band_high_hz)
    presets = {"FULL": (0.0, 300.0), "LOW": (4.0, 80.0),
               "SHAFT": (8.0, 55.0), "MID": (20.0, 120.0)}
    return dict(observations=[_observation(row, _SONAR_FIELDS) for row in rows
                              if row["source"].startswith("SONAR")
                              and not row["source"].startswith("SONAR-BUOY-")
                              and row["source"] not in ("SONAR-DIP-BRG", "SONAR-DIPPING")],
                settings=dict(mode=game.sonar_mode, page=game.sonar_page,
                              listen_bearing=_number(game.sonar.listen_bearing),
                              focus_ref=focus_ref if game.sonar.focus_locked else None,
                              target_ref=target_ref,
                              station_down=_sonar_station_down(game),
                               tow=dict(state=str(tow["state"])[:32],
                                        payout=_number(tow["payout"]),
                                        available=bool(tow["available"]),
                                        handling_ok=bool(tow["handling_ok"]),
                                        speed_kn=_number(observer.speed),
                                        speed_min_kn=config.SONAR_TOWED_HANDLING_MIN_KN,
                                        speed_max_kn=config.SONAR_TOWED_HANDLING_MAX_KN,
                                        depth_m=_number(tow["depth_m"]),
                                       depth_target_m=_number(
                                           tow["depth_target_m"])),
                              vds=dict(state=str(vds["state"])[:32],
                                       payout=_number(vds["payout"]),
                                       available=bool(vds["available"]),
                                       handling_ok=bool(vds["handling_ok"]),
                                       speed_min_kn=config.SONAR_VDS_HANDLING_MIN_KN,
                                       speed_max_kn=config.SONAR_VDS_HANDLING_MAX_KN,
                                       max_sea_state=config.SONAR_VDS_MAX_SEA_STATE,
                                       depth_m=_number(vds["depth_m"]),
                                       depth_target_m=_number(vds["depth_target_m"])),
                              bt=dict(ready=game.sonar.bt_cooldown <= 0,
                                       cooldown_s=_number(game.sonar.bt_cooldown),
                                       thermocline_m=_number(
                                           game.sonar.bt_profile.get("thermocline_m"))
                                       if game.sonar.bt_profile else None),
                              ping=dict(ready=bool(game.sonar.ping_ready),
                                        cooldown_s=_number(
                                            game.sonar.ping_cooldown_remaining),
                                        pulse=str(game.sonar.ping_pulse)),
                              tma_enabled=bool(game.sonar.tma_enabled),
                              tma_method=str(game.tma_method),
                              gain_db=_number(game.sonar.gain_db),
                              band_preset=next((key for key, value in presets.items()
                                                if value == band), None),
                              band_hz=[_number(band[0]), _number(band[1])],
                              notch=bool(game.sonar.notch_enabled),
                              peak_hold=bool(game.sonar.peak_hold),
                              harmonic_hz=_number(game.sonar_harmonic_hz),
                              harmonic_candidates_hz=([_number(value) for value in
                                                       game.sonar_harmonic_candidates()]
                                                      if game.operator_assist() else []),
                              tools=dict(
                                  assist=bool(game.operator_assist()),
                                  lofar_cursor_hz=_number(game.sonar_tools.lofar_cursor_hz),
                                  demon_cursor_hz=_number(game.sonar_tools.demon_cursor_hz),
                                  integration_s=int(game.sonar_tools.integration_s),
                                  vernier=bool(game.sonar_tools.vernier),
                                  shaft_hz=_number(game.sonar_tools.shaft_hz),
                                  blade_hz=_number(game.sonar_tools.blade_hz),
                                  operator_notch_hz=_number(
                                      getattr(game.sonar, "operator_notch_hz", None)),
                                  demon_band_hz=[_number(value) for value in
                                                 game.sonar.receiver.demon_band_hz],
                                  heterodyne_hz=_number(game.sonar.heterodyne_hz),
                                  library_marks=int(game.sonar_library_marks()),
                                  library=[dict(name=str(getattr(signature, "label",
                                                                 signature.key))[:48],
                                                fit=_number(fit))
                                           for signature, fit in game.sonar_class_library(3)]),
                              audio_enabled=bool(game.sonar_audio_enabled),
                              volume=_number(game.sonar_volume),
                              quiet_mode=bool(getattr(observer, "quiet_mode", False))),
                visualization=_sonar_visualization(game, rows, sonar_refs))


def _own_weapon_assets(game, asset_refs):
    """Commanded own weapons in the water or air (torpedoes, ASROC, Nixie)."""
    torpedoes = [dict(ref=asset_refs[("torpedo", id(item))], x=_number(item.x), y=_number(item.y),
                      depth_m=_number(item.depth), course=_number(item.course),
                      state=str(item.state)[:32])
                 for item in sorted(game.torpedoes, key=lambda weapon: weapon.idx)[:64]]
    asrocs = [dict(ref=asset_refs[("asroc", id(item))], x=_number(item.x), y=_number(item.y),
                   depth_m=None, course=_number(item.course), state=str(item.state)[:32])
               for item in sorted(game.asrocs, key=lambda weapon: weapon.seq)[:32]]
    nixies = [dict(ref=asset_refs[("nixie", id(item))], x=_number(item.x),
                    y=_number(item.y), depth_m=_number(item.depth), course=None,
                    state=str(item.state)[:32])
               for item in sorted(game.nixies, key=lambda decoy: decoy.seq)[:8]]
    return torpedoes, asrocs, nixies


# The fire-control check order of ``torpedo_readiness`` as the steps of the
# firing chain the browser draws (target, release, solution, tube, fire):
# the first failing check names the step that holds the shot.
_FIRE_STAGES = (("KEIN ZIEL", "target"), ("ZUGEHOERIGKEIT", "release"),
                ("WAFFEN GESPERRT", "release"), ("KEINE ENTFERNUNG", "solution"),
                ("NICHT ALS", "solution"), ("KEINE TORPEDOS", "tube"),
                ("KEIN ROHR", "tube"), ("SALVENLIMIT", "tube"),
                ("WAFFENZENTRALE", "station"))


def _fire_stage(interlock) -> str:
    text = str(interlock)
    return next((stage for marker, stage in _FIRE_STAGES if marker in text),
                "fire" if text == "FEUER FREI" else "station")


def _weapons(game, rows, target_ref, asset_refs, direct_refs):
    tactical = [row for row in rows if row.get("_opz")
                and row["ref"] == target_ref][:_MAP_ROWS_MAX]
    designated = next((_weapon_observation(row) for row in tactical
                       if row["ref"] == target_ref), None)
    torpedoes, asrocs, nixies = _own_weapon_assets(game, asset_refs)
    battery = getattr(game, "player_torpedo_battery", None)
    tubes = ([] if battery is None else [dict(
        tube=item.index, state=("ready" if item.loaded_weapon_key is not None else
                                "reloading" if item.loading_weapon_key is not None
                                else "empty"),
        reload_s=_number(item.reload_remaining_s)) for item in battery.tubes[:16]])
    store = getattr(game, "nixie_store", None)
    interlock = game.torpedo_readiness()[0]
    return dict(inventory=dict(torpedoes=game.torpedo_count, vls=game.vls_cells,
                                ciws=game.ciws_ammo, aa=game.aa_ammo,
                                 chaff_ready=game.softkill_store.ready > 0,
                                nixies=None if store is None else store.remaining_total,
                                asroc=int(game.own_asrocs_left),
                                depth_charges=int(game.depth_charges_left),
                                rbu=int(game.rbu_rockets)),
                 readiness=dict(station_down=game.damage.station_down("weapons"),
                                roe=game.roe, ciws_ready=game.ciws_cooldown_s <= 0,
                                rbu_ready=game.rbu_reload_s <= 0.0,
                                torpedo_warning=game.rbu_defence_bearing() is not None,
                                aa_ready=game.aa_cooldown_s <= 0,
                                state="unavailable" if battery is None else "available",
                                interlock=str(localize(interlock, game.tr))[:256],
                                stage=_fire_stage(interlock),
                                reload_s=None if battery is None else _number(
                                    battery.next_reload_s)),
                 designated_target=designated,
                 navigation=_own_navigation(game), tactical=_map_rows(tactical),
                  target_choices=_direct_fire_observations(rows, direct_refs),
                 depth_m=_number(game.torpedo_depth), tubes=tubes,
                 settings=dict(
                     torpedo_type=str(game.torpedo_type)[:64],
                     choices=[dict(key=str(key)[:64], name=str(name)[:80],
                                   stock=int(stock),
                                   loaded=int(battery.loaded_count(key)) if battery else 0)
                              for key, name, stock in game.torpedo_type_choices()[:8]],
                     pattern=str(game.torpedo_pattern),
                     enable_nm=_number(game.torpedo_enable_nm),
                     salvo=int(game.torpedo_salvo)),
                 own_weapons=torpedoes + asrocs,
                 active_assets=torpedoes + asrocs + nixies)


def _mpa(game):
    """The patrol aircraft: commanded own-force datalink state only."""
    view = game.mpa_view()
    airborne = bool(view["airborne"])
    return dict(
        state=view["state"], airborne=airborne,
        x=_number(view["x"]) if airborne else None,
        y=_number(view["y"]) if airborne else None,
        course=_number(view["course"]) if airborne else None,
        bearing=_number(view["bearing"]) if airborne else None,
        range_nm=_number(view["range_nm"]) if airborne else None,
        waypoint_x=_number(view["waypoint_x"]) if airborne else None,
        waypoint_y=_number(view["waypoint_y"]) if airborne else None,
        station_left_s=(_number(max(0.0, view["fuel_s"] - view["bingo_s"]))
                        if airborne else None),
        ready_in_s=(None if view["ready_in_s"] is None else _number(view["ready_in_s"])),
        sorties_left=int(view["sorties_left"]), buoys=int(view["buoys"]),
        torpedoes=int(view["torpedoes"]), radar=bool(view["radar"]), mad=bool(view["mad"]),
        buoy_mode=view["buoy_mode"], pattern=view["pattern"],
        pattern_points=[dict(x=_number(x), y=_number(y))
                        for x, y in view["pattern_points"]],
        datalink=bool(view["datalink"]), relayed=int(view["relayed"]))


def _consort(game):
    """The consort destroyer: commanded own-force datalink state and its
    sonar's bearing lines (measurements), or None without one."""
    view = game.consort_view()
    if view is None:
        return None
    point = view["point"]
    return dict(
        callsign=view["callsign"], sunk=bool(view["sunk"]), datalink=bool(view["datalink"]),
        x=_number(view["x"]), y=_number(view["y"]), course=_number(view["course"]),
        speed_kn=_number(view["speed_kn"]), bearing=_number(view["bearing"]),
        range_nm=_number(view["range_nm"]), mode=view["mode"], working=view["working"],
        station=view["station"],
        point_x=None if point is None else _number(point[0]),
        point_y=None if point is None else _number(point[1]),
        active=bool(view["active"]), weapons_free=bool(view["weapons_free"]),
        asroc=int(view["asroc"]),
        bearings=[dict(observer_x=_number(row["x"]), observer_y=_number(row["y"]),
                       bearing=_number(row["bearing"]),
                       uncertainty_deg=_number(row["uncertainty_deg"]),
                       age_s=_age(game.sim_t, row["t"]))
                  for row in view["bearings"]][:8])


def _bridge_route(game):
    """The autopilot route: own commanded waypoints still ahead (own truth)."""
    route = game.route
    return dict(pattern=route.kind, index=int(route.index), total=len(route.points),
                points=[dict(number=number, x=_number(x), y=_number(y))
                        for number, (x, y) in enumerate(route.points, 1)
                        if number > route.index])


def _crew(game, watch=None, roster=None):
    """A crew's watch bill, fatigue, morale and wounded (own-ship truth)."""
    view = game.crew_view(watch)
    hurt = game.casualty_view(roster)
    left = view["watch_left_s"]
    return dict(on_watch=int(view["on_watch"]),
                watches=[dict(index=int(row["index"]), fatigue=_number(row["fatigue"]),
                              on_duty=bool(row["on_duty"])) for row in view["watches"]],
                watch_left_s=None if left is None else _number(left),
                turnover=bool(view["turnover"]),
                action_stations=bool(view["action_stations"]),
                morale=_number(view["morale"]),
                effectiveness=_number(view["effectiveness"]),
                casualties=dict(
                    wounded=int(hurt["wounded"]), serious=int(hurt["serious"]),
                    returned=int(hurt["returned"]),
                    stations=[dict(station=row["station"], gaps=int(row["gaps"]),
                                   posts=int(row["posts"])) for row in hurt["stations"]],
                    medic=hurt["medic"], spare=int(hurt["spare"]),
                    reassign_in_s=_number(hurt["reassign_in_s"])))


def _leak_state(room) -> str:
    """An own hull hole as the damage-control plot shows it."""
    if room.hole_m2 <= 0.0 or room.state == "ZERSTOERT":
        return "none"
    return "open" if room.state == "FLUTEND" else "patched"


def _damage(game):
    compartments = [dict(key=room.key, name=game.tr("compartment." + room.key),
                          state=room.state, flood=_number(room.flood),
                          fire=_number(room.fire), leak=_leak_state(room),
                          inflow=_number(game.damage.inflow_pct_s(room.key)),
                           repairable=room.key in game.damage.repair_candidates(),
                           trend={key: _number(value) if key != "repairable" else bool(value)
                                  for key, value in game.damage.compartment_trend(
                                      room.key).items()})
                    for room in game.damage.compartments.values()]
    teams = [dict(team=team, compartment=game.damage.teams[team],
                  transit_s=_number(max(0.0, float(game.damage.team_eta.get(team, 0.0)))
                                    if game.damage.teams[team] is not None else 0.0))
             for team in sorted(game.damage.teams)]
    return dict(compartments=compartments, teams=teams, crew=_crew(game),
                total=_number(game.damage.total), sunk=bool(game.damage.ship_sunk),
                stability=dict(list_deg=_number(game.damage.list_deg()),
                               draft_m=_number(game.damage.draft_m),
                               trim_deg=_number(game.damage.trim_deg()),
                               counterflood_room=game.damage.counterflood_room,
                               can_counterflood=(
                                   abs(game.damage.list_deg()) >= 5.0
                                   and not game.damage.ship_sunk)))


def _radio(game, rows, ref_by_track):
    station_down = game.damage.station_down("radio")
    observations = []
    for row in rows:
        if row["source"] != "HFDF":
            continue
        observation = _observation(row, _RADIO_FIELDS)
        frequency = row.get("_frequency_hz")
        observation["frequency_khz"] = (round(frequency / 1e3, 1)
                                        if frequency is not None and frequency > 0 else None)
        observation["propagation"] = row.get("_propagation")
        observation["can_capture"] = (not station_down
                                      and row["age_s"] is not None
                                      and row["age_s"] <= config.RADAR_TRACK_STALE_S)
        observations.append(observation)
    fixes = []
    for track_id, fix in sorted(game.hfdf_fixes.items()):
        ref, age = ref_by_track.get(track_id), _age(game.sim_t, fix.get("t"))
        if ref is not None and age is not None and age <= 300:
            covariance = _series(fix.get("covariance_nm2"), 3)
            fixes.append(dict(ref=ref, x=_number(fix.get("x")), y=_number(fix.get("y")),
                              uncertainty_nm=_number(fix.get("sigma_nm")), age_s=age,
                              covariance_nm2=covariance if len(covariance) == 3 else None))
    logged = []
    for item in game.hfdf_log[-20:]:
        ref, age = ref_by_track.get(item.get("track_id")), _age(game.sim_t, item.get("t"))
        if ref is not None and age is not None and age <= 300:
            logged.append(dict(ref=ref, bearing=_number(item.get("bearing")),
                               observer_x=_number(item.get("observer_x")),
                               observer_y=_number(item.get("observer_y")), age_s=age))
    # The language model's wording replaces a line once it has arrived.
    worded = getattr(game, "llm_radio_text", None)
    messages = [dict(stamp=str(stamp)[:32],
                     text=str((worded(stamp, text) if worded is not None else None)
                              or localize(text, game.tr))[:512])
                for stamp, text in game.messages[-40:]]
    return dict(observations=observations, logged_fixes=fixes,
                 logged_bearings=logged, messages=messages,
                 station_down=station_down, navigation=_own_navigation(game),
                  tactical=[_observation(row, _TACTICAL_FIELDS) for row in rows
                            if row["source"] == "HFDF"][:_MAP_ROWS_MAX],
                 tasks=_radio_tasks(game, station_down),
                 can_request_ras=bool(not station_down and game.tasking.enabled
                                      and not game.game_over and game.ras_needed()),
                 can_contact_report=bool(game.can_send_report("contact")),
                 can_request_support=bool(game.can_send_report("support")),
                 report=_radio_report(game, station_down))


def _radio_report(game, station_down):
    """The radio room's own calls: on the air, waiting or ready, and why not."""
    view = game.report_view()
    reason = game._report_check()
    if reason is None and not view["has_fix"]:
        reason = "report_no_fix"
    state = ("down" if station_down else "on_air" if view["transmitting"]
             else "waiting" if view["ready_in_s"] > 0.0 else "ready")
    return dict(state=state, tx_left_s=_number(view["tx_left_s"]),
                ready_in_s=_number(view["ready_in_s"]), has_fix=bool(view["has_fix"]),
                reason=reason if reason in RADIO_REPORT_REASONS else None,
                sent=int(min(view["sent"], 999)))


def _radio_tasks(game, station_down):
    """HQ tasks as the radio room knows them (reported positions only)."""
    tasks = []
    for row in game.task_view():
        # The wire calls the task's kind ``type``: the browser rejects any
        # ``kind`` key in a role state (it never carries entity kinds).
        item = {key: row["kind" if key == "type" else key]
                for key in RADIO_TASK_FIELDS if key != "can_answer"}
        for key in ("x", "y", "radius_nm", "bearing", "range_nm", "progress",
                    "course", "speed_kn", "respond_s", "remaining_s"):
            item[key] = _number(item[key])
        item["name"] = None if row["name"] is None else str(row["name"])[:24]
        item["can_answer"] = row["state"] == "offered" and not station_down
        tasks.append(item)
    return tasks


def _helicopter_rescue(game):
    """The rescue hoist panel (reported raft positions, own cabin), or None."""
    status = game.helo_rescue_status()
    if status is None:
        return None
    return dict(phase=status["phase"], hoist=bool(status["hoist"]),
                aboard=int(status["aboard"]), capacity=int(status["capacity"]),
                lift=_number(status["lift"]),
                raft=None if status["raft"] is None else str(status["raft"])[:32],
                left=status["left"], range_nm=_number(status["range_nm"]),
                bearing=_number(status["bearing"]))


def _helicopter(game, rows, asset_refs, buoy_labels, direct_refs=None,
                sonar_refs=None, asset_only=False):
    helo = game.helo
    flight_weather = game.helicopter_weather()
    airborne = bool(helo.airborne)
    asset = dict(state=helo.state, airborne=airborne,
                 x=_number(helo.x) if airborne else None,
                 y=_number(helo.y) if airborne else None,
                 course=_number(helo.course) if airborne else None,
                 fuel_s=_number(helo.fuel_s), torpedoes=helo.torps,
                 buoys=helo.buoys_left, hovering=bool(helo.hovering),
                 dip_state=helo.dip_state, dip_depth_m=_number(helo.dip_depth_m),
                 dip_depth_target_m=_number(helo.dip_depth_target_m),
                 dip_water_depth_m=_number(helo.dip_water_depth_m),
                 dip_ping_ready=bool(helo.dip_ping_ready),
                 dip_ping_cooldown_s=_number(helo.dip_ping_cooldown),
                 buoy_mode=game.helo_buoy_mode,
                 pattern=str(helo.pattern), pattern_remaining=len(helo.pattern_queue),
                 mad_mode=bool(helo.mad_mode), radar=bool(game.helo_radar_active()),
                 radar_switch=bool(helo.radar_on),
                 # Start preparation: seconds left (0: ready, waiting for the
                 # deck window), None without a launch order.
                 prep_s=_number(helo.prep_s) if helo.preparing else None,
                 # Refuelling on deck: seconds to the launch minimum (prepared
                 # launch short of fuel) or to full, None when not refuelling.
                 refuel_s=None if helo.refuel_wait_s() is None else _number(helo.refuel_wait_s()))
    if asset_only:
        for key in ("buoy_mode", "pattern", "pattern_remaining", "mad_mode", "radar",
                    "radar_switch"):
            asset.pop(key)
        return {"asset": asset}
    water_available = airborne and helo.water_entry_clear(game.world)
    water_depth = (float(game.world.depth_m(helo.x, helo.y))
                   if water_available else None)
    # Charted depth is known geography; the layer only once the lowered
    # dome has passed through it.
    layer = (float(game.world.thermocline_depth_m(helo.x, helo.y))
             if water_available and helo.dip_state != "STOWED" else None)
    thermocline = (layer if layer is not None and helo.dip_depth_m >= layer
                   else None)
    dip_environment = dict(
        water_depth_m=_number(water_depth),
        thermocline_m=_number(thermocline),
        depth_limit_m=(None if water_depth is None else _number(min(
            config.HELO_DIP_DEPTH_MAX_M,
            max(0.0, water_depth - config.HELO_DIP_BOTTOM_CLEARANCE_M)))),
        bottom_clearance_m=(None if water_depth is None or helo.dip_state == "STOWED"
                            else _number(max(0.0, water_depth - helo.dip_depth_m))),
        winch_rate_m_s=_number(config.HELO_DIP_DEPTH_RATE_M_S),
        below_thermocline=(None if thermocline is None
                           or helo.dip_state == "STOWED" else
                           bool(helo.dip_depth_m >= thermocline)))
    waypoint = (dict(x=_number(helo.waypoint_x), y=_number(helo.waypoint_y))
                 if helo.waypoint_x is not None
                 and helo.waypoint_y is not None else None)
    buoys = [dict(ref=asset_refs[("buoy", id(buoy))],
                   label=buoy_labels[("buoy", id(buoy))],
                   x=_number(buoy.x), y=_number(buoy.y),
                   battery_s=_number(buoy.battery_s), active=bool(buoy.active),
                   mode=buoy.mode)
             for buoy in sorted(game.buoys, key=lambda item: item.seq)[:64]]
    distance = (math.hypot(helo.x - game.ship.x, helo.y - game.ship.y)
                if airborne else None)
    # The helicopter's own sonar picture is not gated on OPZ release - unlike
    # every other map role, it must be able to see, classify and release what
    # only its own dip has found, the same way the local Helicopter station can.
    # The dip display uses the helicopter's independent measurements. Generic
    # sonar rows may carry a ship bearing even when this contact was dipped.
    dip_observations = []
    buoy_observations = []
    tactical = []
    for row in rows:
        if row["source"].startswith("SONAR-BUOY-"):
            contact = (sonar_refs or {}).get(row["ref"])
            if contact is None:
                continue
            try:
                seq = int(row["source"].split("-")[2])
            except (IndexError, ValueError):
                continue
            report = contact.buoy_reports.get(seq)
            if report is None:
                continue
            buoy_observations.append(dict(
                ref=row["ref"], label=row["label"],
                buoy_label=next((buoy_labels[("buoy", id(b))]
                                 for b in game.buoys if b.seq == seq),
                                f"SB{seq:02d}"), mode=report["mode"],
                bearing=_number(report["bearing"]),
                bearing_uncertainty_deg=_number(report["bearing_uncertainty_deg"]),
                range_nm=_number(report["range_nm"]),
                x=_number(report["x"]), y=_number(report["y"]),
                observer_x=_number(report["observer_x"]),
                observer_y=_number(report["observer_y"]),
                age_s=_age(game.sim_t, report["measured_at"]),
                quality=_number(report["quality"]),
                qualified=bool(contact.helo_qualified),
                released_to_opz=bool(contact.buoy_released_to_opz)))
            tactical.append(dict(row))
            continue
        if row["ref"] not in (direct_refs or {}):
            continue
        contact = (sonar_refs or {}).get(row["ref"])
        if contact is None:
            continue
        fixes = [fix for fix in contact.active_fixes(game.sim_t)
                 if fix["source"] == "DIPPING"]
        fix = max(fixes, key=lambda item: item["fixed_at"]) if fixes else None
        passive = (contact.dip_bearing is not None and contact.dip_last_seen is not None
                   and 0 <= game.sim_t - contact.dip_last_seen
                   < config.SONAR_CONTACT_LOST_S)
        if not passive and fix is None:
            continue
        origin_x = contact.dip_observer_x if passive else contact.observer_x
        origin_y = contact.dip_observer_y if passive else contact.observer_y
        fix_origin_x, fix_origin_y = contact.observer_x, contact.observer_y
        measured_range = (None if fix is None else _number(math.hypot(
            fix["x"] - fix_origin_x, fix["y"] - fix_origin_y)))
        active_bearing = (None if fix is None else _number(math.degrees(
            math.atan2(fix["x"] - fix_origin_x,
                       -(fix["y"] - fix_origin_y))) % 360))
        dip_observations.append(dict(
            ref=row["ref"], label=row["_display_id"],
            bearing=_number(contact.dip_bearing) if passive else None,
            bearing_uncertainty_deg=(_number(contact.dip_bearing_uncertainty_deg)
                                     if passive else None),
            age_s=_age(game.sim_t, contact.dip_last_seen) if passive else None,
            range_nm=measured_range,
            active_bearing=active_bearing,
            range_uncertainty_nm=(None if fix is None else
                                  _number(fix["uncertainty_nm"])),
            depth_m=None if fix is None else _number(fix["depth_m"]),
            depth_uncertainty_m=(None if fix is None else
                                 _number(fix["depth_uncertainty_m"])),
            fix_age_s=None if fix is None else _age(game.sim_t, fix["measured_at"]),
            classification=row["classification"],
            qualified=bool(contact.helo_qualified),
            released_to_opz=bool(contact.dip_released_to_opz)))
        tactical_row = dict(row)
        tactical_row.update(
            source="SONAR-DIP-BRG" if passive else "SONAR-DIPPING",
            bearing=(_number(contact.dip_bearing) if passive else active_bearing),
            range_nm=None if passive else measured_range,
            x=None if passive else _number(fix["x"]),
            y=None if passive else _number(fix["y"]),
            observer_x=_number(origin_x), observer_y=_number(origin_y),
            age_s=(_age(game.sim_t, fix["measured_at"]) if fix is not None
                   else _age(game.sim_t, contact.dip_last_seen)),
            bearing_uncertainty_deg=(_number(contact.dip_bearing_uncertainty_deg)
                                     if passive else None),
            range_uncertainty_nm=(None if fix is None else _number(fix["uncertainty_nm"])))
        tactical_row["released_to_opz"] = bool(contact.dip_released_to_opz)
        tactical.append(tactical_row)
        if len(dip_observations) >= _MAP_ROWS_MAX:
            break
    return dict(asset=asset, waypoint=waypoint, buoys=buoys,
                buoy_observations=buoy_observations[:_MAP_ROWS_MAX],
                acoustic=dict(source=game.helo_listen_source,
                              ready=game.helicopter_audio_ready(),
                              listen_bearing=_number(game.helo_listen_bearing),
                              audition_mode=game.helo_audition.audition_mode,
                              band_preset=game.helo_audio_band,
                              gain_db=_number(game.helo_audition.gain_db),
                              notch=bool(game.helo_audition.notch_enabled),
                              sources=["DIP", *(f"SB{b.seq}" for b in
                                  sorted(game.buoys, key=lambda item: item.seq))],
                              bin_frequencies_hz=[config.lofar_bin_freq(i)
                                                  for i in range(config.LOFAR_BINS)],
                              spectrum=_series(game.helo_receiver.spectrum,
                                               config.LOFAR_BINS),
                              history=[_waterfall_row(row, config.LOFAR_BINS)
                                       for row in game.helo_spectra[-64:]],
                              broadband=_series(game.helo_receiver.broadband, 180),
                              broadband_history=[_waterfall_row(row, 180)
                                                 for row in game.helo_broadband_history[-64:]],
                              demon=_series(game.helo_receiver.demon_spectrum, 80),
                              demon_history=[_waterfall_row(row, 80)
                                             for row in game.helo_demon_history[-64:]]),
                dip_environment=dip_environment,
                dip_observations=dip_observations,
                rescue=_helicopter_rescue(game),
                navigation=_own_navigation(game), tactical=[
                    _observation(row, _HELICOPTER_TACTICAL_FIELDS)
                    for row in tactical[:_MAP_ROWS_MAX]],
                 target_choices=_direct_fire_observations(
                     rows, {} if direct_refs is None else direct_refs),
                 readiness=dict(
                     flightdeck_down=game.damage.station_down("flightdeck"),
                     deck_state=game.damage.station_state("flightdeck"),
                      can_launch=helo.state == "HANGAR" and not helo.preparing
                     and not game.damage.station_down("flightdeck")
                     and flight_weather["status"] != "no_go",
                    can_return=airborne or helo.preparing,
                     can_set_waypoint=helo.state != "VERLOREN",
                     can_deploy_buoy=airborne and helo.buoys_left > 0
                      and helo.water_entry_clear(game.world),
                     can_pattern=helo.state == "AUF" and helo.buoys_left > 0,
                     can_mad=helo.state == "AUF" and helo.dip_state == "STOWED",
                      can_set_dipping=helo.state == "AUF"
                       and (helo.dip_state != "STOWED"
                            or flight_weather["dipping_safe"])
                       and (helo.dip_state != "STOWED"
                           or helo.dip_depth_limit(game.world)
                           >= config.HELO_DIP_DEPTH_MIN_M),
                     can_set_dip_depth=helo.state == "AUF"
                      and helo.dip_state in ("DEPLOYING", "DEPLOYED"),
                      can_dipping_ping=not game.damage.station_down("sonar")
                       and helo.dip_ping_ready,
                      weather_launch_safe=flight_weather["launch_safe"],
                      weather_dipping_safe=flight_weather["dipping_safe"],
                      crosswind_kn=_number(flight_weather["crosswind_kn"]),
                      # The flight deck's motion and its quiet-period window.
                      deck_motion=_deck_motion(game),
                     rtb_margin_s=(None if distance is None else _number(
                         helo.fuel_s - distance / max(.001, config.kn_to_nm_per_s(
                             config.HELO_SPEED_KN)) - config.HELO_FUEL_RESERVE_S))))


def _eloka(game, rows, esm_refs, candidate_refs):
    evidence = []
    evidence_refs = {}
    for row in rows:
        if not row["source"].startswith("RADAR"):
            continue
        age = (row["fix_age_s"] if row["x"] is not None
               and row["fix_age_s"] is not None else row["age_s"])
        if (_number(row["bearing"]) is None or _number(age) is None
                or (row["x"] is None) != (row["y"] is None)):
            continue
        observed_at = game.sim_t - age
        item = ESMCorrelationEvidence(row["ref"], row["source"], row["bearing"],
                                      row["bearing_uncertainty_deg"], row["x"], row["y"],
                                      observed_at)
        evidence.append(item)
        evidence_refs[row["ref"]] = True
    intercepts = []
    # The emitter group of every intercept (display policy shared with the
    # uConsole list): the anchor's public ref; the browser bundles by it.
    groups = game.eloka_group_map()
    for track in game.eloka_tracks():
        age = _age(game.sim_t, track.last_seen)
        if age is None or age > game.esm_picture.stale_s:
            continue
        # Scores and catalog-derived radar type/threat/range are a training
        # aid; with operator assistance off the browser gets the unranked
        # library range lookup and raw parameters only (as the uConsole).
        candidates = [dict(ref=candidate_refs[(track.track_key, item.emitter_key)],
                            name=(game.eloka_emitter_name(item.emitter_key) or "")[:128],
                            score=None if item.score is None else _number(item.score))
                      for item in game.eloka_display_candidates(track)[:32]]
        annotation = game.eloka_annotation_name(track.track_key)
        analysis = game.eloka_display_analysis(track)
        channel = next((item for item in game.ecm_jammer.channels
                        if item.track_key == track.track_key), None)
        threat = "unknown" if analysis is None else analysis.threat_level
        correlations = []
        evidence_by_ref = {item.track_id: item for item in evidence}
        for item in correlate_observations(track, evidence, game.sim_t):
            observed = evidence_by_ref.get(item.track_id)
            if observed is None:
                continue
            correlations.append(dict(
                ref=item.track_id, source=str(item.source)[:64],
                score=_number(item.score), ambiguous=bool(item.ambiguous),
                evidence=dict(bearing=_number(observed.bearing),
                    bearing_uncertainty_deg=_number(
                        observed.bearing_uncertainty_deg),
                    age_s=_age(game.sim_t, observed.observed_at),
                    position_available=observed.x is not None)))
            if len(correlations) == 8:
                break
        anchor = groups.get(track.track_key, track.track_key)
        intercepts.append(dict(ref=esm_refs[track.track_key], label=track.track_key,
            group=esm_refs.get(anchor, esm_refs[track.track_key]),
            bearing=_number(track.bearing),
            bearing_uncertainty_deg=_number(track.bearing_uncertainty_deg),
            frequency_hz=_number(track.frequency_hz), prf_hz=_number(track.prf_hz),
            frequency_band=spectrum_band(track.frequency_hz).value,
            modulation=track.modulation_code, quality=_number(track.display_quality(
                game.sim_t, game.esm_picture.stale_s)), age_s=age,
            radar_type=(None if analysis is None or analysis.radar_type is None
                        else analysis.radar_type.value),
            threat=threat,
            signal_state=signal_state(track, game.sim_t, threat),
            operational=track_is_operational(
                track, game.sim_t, threat,
                annotated=game.eloka_annotation(track.track_key) is not None,
                jamming=channel is not None),
            ambiguous=False if analysis is None else analysis.ambiguous,
            synthetic_assumption=bool(track.synthetic_assumption),
            signal_db=_number(track.signal_db),
            range_estimate_nm=_number(game.eloka_display_range(track)),
            scan_period_s=_number(track.revisit_s) if track.revisit_s > 0.0 else None,
            auto_jamming=bool(game.ecm_jammer.auto_enabled),
            jamming=channel is not None,
            jamming_effectiveness=(None if channel is None else
                                   _number(channel.effectiveness)),
            jamming_technique=(None if channel is None else channel.technique),
            ecm_power_draw=(None if channel is None else
                            _number(channel.power_draw)),
            is_locked_on=False if channel is None else bool(channel.is_locked_on),
            hoj_risk=bool(channel is not None and channel.technique == "noise"),
            annotation=None if annotation is None else str(annotation)[:128],
            candidates=candidates, correlations=correlations))
    down = game.damage.station_down("opz")
    return dict(intercepts=intercepts, station_down=down,
                hardware=dict(df_sensors=ESM_DF_SENSOR_COUNT,
                              broadband_sensors=ESM_BROADBAND_SENSOR_COUNT,
                              ecm_channels=game.ecm_jammer.MAX_CHANNELS,
                              frequency_min_hz=ESM_FREQUENCY_MIN_HZ,
                              frequency_max_hz=ESM_FREQUENCY_MAX_HZ,
                              reaction_s=game.ecm_jammer.REACTION_DELAY_S),
                status="down" if down else "live")


def _bridge_tactical(rows, opz_fusions):
    """The Bridge chart's picture: one row per contact. Reports the OPZ fused
    stand behind their fusion (as on the uConsole Bridge chart); a fusion
    appears where it stands for at least one radar or lookout report."""
    charted = {row["ref"] for row in rows if row.get("_opz")
               and row["source"] not in ("ESM", "FUSION")
               and not row["source"].startswith("SONAR")}
    fused = {ref for fusion in opz_fusions for ref in fusion["members"]}
    result = [_observation(row, _TACTICAL_FIELDS) for row in rows
              if row["ref"] in charted and row["ref"] not in fused]
    by_ref = {row["ref"]: row for row in rows}
    for fusion in opz_fusions:
        if not charted & set(fusion["members"]):
            continue
        row = {key: value for key, value in fusion.items() if key != "members"}
        # The lookout's sighting of a fused ship stays with the one row.
        sighted = next((by_ref[ref] for ref in fusion["members"]
                        if by_ref.get(ref, {}).get("visual_class") is not None), None)
        if row.get("visual_class") is None and sighted is not None:
            row.update(visual_class=sighted["visual_class"],
                       visual_type=sighted["visual_type"])
        result.append(row)
    return result


def build_role_states(game, status, rows, target_ref, focus_ref, ref_by_track,
                       esm_refs, asset_refs, buoy_labels, candidate_refs, sonar_refs,
                       direct_fire_refs):
    """Build all canonical assigned views from current published observations."""
    common = _common(game, status, None)
    opz_observations = []
    opz_fusions = []
    source_classifications = []
    asm_refs = {ref_by_track[track.track_id] for track in game.asm_tracks()
                if track.track_id in ref_by_track}
    for row in rows:
        if not row.get("_opz") or row["source"] == "HFDF":
            continue
        observation = _observation(row, _TACTICAL_FIELDS)
        if row["source"] == "FUSION":
            fusion = game.opz_fusion.fusions.get(next(
                (key for key, value in ref_by_track.items() if value == row["ref"]), ""))
            members = None if fusion is None else live_members(fusion, ref_by_track)
            if members is None:
                continue
            observation["members"] = [ref_by_track[item] for item in members]
            opz_fusions.append(observation)
        else:
            opz_observations.append(observation)
        if row["classification"] is not None:
            source_classifications.append(dict(ref=row["ref"], source=row["source"],
                                               classification=row["classification"]))
    raw_refs = {row["ref"] for row in opz_observations}
    opz_suggestions = []
    for suggestion in game.opz_suggestions():
        refs = [ref_by_track.get(key) for key in suggestion.members]
        if any(ref is None or ref not in raw_refs for ref in refs):
            continue
        opz_suggestions.append(dict(
            key="+".join(refs), refs=refs, bearing=_number(round(suggestion.bearing, 1)),
            bearing_delta_deg=_number(round(suggestion.bearing_delta_deg, 1)),
            distance_nm=(None if suggestion.distance_nm is None
                         else _number(round(suggestion.distance_nm, 2))),
            course_delta_deg=(None if suggestion.course_delta_deg is None
                              else _number(round(suggestion.course_delta_deg, 1))),
            speed_delta_kn=(None if suggestion.speed_delta_kn is None
                            else _number(round(suggestion.speed_delta_kn, 1))),
            class_match=suggestion.class_match))
    operational = {
        "bridge": dict(navigation=_own_navigation(game),
                       orders=dict(station_down=game.damage.station_down("bridge"),
                                   speed_max_kn=config.SHIP_SPEED_MAX_KN,
                                   telegraph=str(game.ship.telegraph)[:16],
                                   noise=_number(game.ship.noise_level()),
                                   cavitating=bool(game.ship.cavitating)),
                        threat=dict(observations=[
                            _observation(row, _TACTICAL_FIELDS) for row in rows
                            if row.get("_opz") and (row["ref"] in asm_refs
                                                   or row["affiliation"] == "HOSTILE")],
                                    count=sum(row["ref"] in asm_refs
                                              or row["affiliation"] == "HOSTILE"
                                              for row in rows if row.get("_opz")),
                                    average_flood=_number(game.damage.avg_flood()),
                                    torpedoes=[dict(source=warning["source"],
                                                    bearing=_number(warning["bearing"]),
                                                    age_s=_number(warning["age_s"]),
                                                    tti_s=_number(warning.get("tti_s")))
                                               for warning in game.torpedo_warnings()[:8]]),
                        systems=[dict(key=key, state=game.damage.station_state(key),
                                      down=game.damage.station_down(key))
                                 for key in sorted(game.damage.compartments)],
                         tactical_summary=_bridge_tactical(rows, opz_fusions),
                        sightings=_sightings(game), crew=_crew(game),
                        lookout=_lookout_glasses(game), route=_bridge_route(game)),
        "sonar": _sonar(game, rows, focus_ref, target_ref, sonar_refs),
        "weapons": _weapons(game, rows, target_ref, asset_refs,
                            direct_fire_refs["weapons"]),
        "damage": _damage(game),
        "opz": dict(observations=opz_observations,
                      fusions=opz_fusions, suggestions=opz_suggestions,
                      radar=dict(surface=bool(game.surface_radar_on),
                                 air=bool(game.air_radar_on),
                                 range_nm=_number(game.radar_range_nm),
                                 live=not game.damage.station_down("opz"),
                                  sweep_bearing=_number(game.radar_sweep_bearing()),
                                  sweep_rate_deg_s=config.RADAR_SWEEP_DEG_PER_S,
                                 weather_severity=_number(
                                     game.radar_weather_severity()),
                                 surface_effective_range_nm=_number(
                                     game.radar_effective_range("surface")),
                                 air_effective_range_nm=_number(
                                     game.radar_effective_range("air"))),
                       defense=dict(vls=game.vls_cells, ciws=game.ciws_ammo,
                                    aa=game.aa_ammo,
                                     chaff_ready=game.softkill_store.ready > 0,
                                    ciws_ready=game.ciws_cooldown_s <= 0,
                                    aa_ready=game.aa_cooldown_s <= 0,
                                    ciws_released=bool(game.ciws_authorized)),
                       asm_observations=[dict(
                           _observation(row, _TACTICAL_FIELDS),
                           ref=direct_fire_refs["opz"][row["ref"]])
                           for row in rows if row.get("_opz")
                           and row["ref"] in direct_fire_refs["opz"]],
                      source_classifications=source_classifications,
                      # Bare mast/snorkel echoes: measured position and age only.
                      radar_blips=[dict(ref=f"blip-{blip['seq']}", x=_number(blip["x"]),
                                        y=_number(blip["y"]),
                                        age_s=_age(game.sim_t, blip["t"]))
                                   for blip in game.radar_blip_view()][-16:],
                      designated_target_ref=(target_ref if any(
                          row.get("_opz") and row["ref"] == target_ref
                          for row in rows) else None),
                      own_assets=dict(ship=_own_navigation(game),
                                       helicopter=_helicopter(
                                           game, rows, asset_refs, buoy_labels,
                                           asset_only=True)["asset"],
                                       mpa=_mpa(game),
                                       consort=_consort(game),
                                       weapons=[row for group in _own_weapon_assets(
                                           game, asset_refs) for row in group]),
                      trails=_opz_trails(game, [row["ref"] for row in opz_observations]
                                         + [row["ref"] for row in opz_fusions],
                                         ref_by_track)),
        "radio": _radio(game, rows, ref_by_track),
        "engine": dict(propulsion=dict(course=_number(game.ship.course),
                    target_course=_number(game.ship.target_course),
                    speed=_number(game.ship.speed),
                    target_speed=_number(game.ship.target_speed), telegraph=game.ship.telegraph,
                    rpm=_number(game.ship.rpm()), quiet_mode=bool(game.ship.quiet_mode),
                    plant_mode=str(game.ship.plant_mode),
                    cavitating=bool(game.ship.cavitating),
                    fuel_kg=_number(game.ship.fuel_kg),
                    fuel_capacity_kg=_number(game.ship.fuel_capacity_kg),
                    fuel_burn_kg_h=_number(game.ship.fuel_burn_kg_h()),
                    fuel_endurance_h=_number(game.ship.fuel_endurance_h()),
                    fuel_range_nm=_number(game.ship.fuel_range_nm())),
                     machinery=dict(station_state=game.damage.station_state("engine"),
                                    speed_cap=_number(game.ship.speed_cap),
                                    effective_speed_cap=_number(
                                        game.damage.engine_speed_cap()),
                                    flood=_number(game.damage.compartments[
                                        "engine"].flood),
                                     fire=_number(game.damage.compartments[
                                         "engine"].fire),
                                     repair_teams=game.damage.teams_on("engine"),
                                     repair_trend={key: (_number(value)
                                         if key != "repairable" else bool(value))
                                         for key, value in game.damage.compartment_trend(
                                             "engine").items()},
                                     noise=_number(game.ship.noise_level()),
                                    grounded=bool(game.ship.grounded)),
                    controls=dict(orders=["ASTERN", "STOP", "SLOW", "HALF",
                                          "FULL", "FLANK"],
                                  plants=list(game.ship.PLANT_MODES),
                                  speed_max_kn=_number(config.SHIP_SPEED_MAX_KN),
                                  rpm_max=_number(game.ship.max_rpm()),
                                  noise_max=_number(NOISE_LEVEL_MAX)),
                    # The engine-room console's section mimic: the frigate's
                    # own compartments (own-ship truth, as the damage role).
                    compartments=[dict(key=room.key, state=room.state,
                                       flood=_number(room.flood), fire=_number(room.fire),
                                       teams=game.damage.teams_on(room.key))
                                  for room in game.damage.compartments.values()],
                      environment_effects=dict(sea_state=_number(
                          game.world.effective_sea_state),
                                              roll=_number(game.ship.roll),
                                              pitch=_number(game.ship.pitch),
                                              tas_available=bool(
                                                  game.sonar_mode != "TOWED"
                                                  or game.sonar._tow_available()),
                                              tas_performance=_number(
                                                  game.sonar.tow_performance))),
        "helicopter": _helicopter(game, rows, asset_refs, buoy_labels,
                                   direct_fire_refs["helicopter"], sonar_refs),
        "eloka": _eloka(game, rows, esm_refs, candidate_refs),
    }
    result = {}
    overview = [dict(station=key, enabled=bool(game.autocrew.enabled[key]),
                     status=game.autocrew.status(game, key))
                for key in AUTOCREW_STATIONS]
    for role in ROLE_NAMES:
        # Shallow per-role copies: the common blocks are fresh for this
        # publication, shared read-only between roles, encoded at once and
        # never mutated afterwards (a deep copy per role cost more than the
        # projection itself on the uConsole).
        state = dict(common)
        state["role"] = role
        state["audio"] = dict(common["audio"], events=[
            dict(event) for event in common["audio"]["events"]
            if role == "eloka" or event["cue"] != "esm_contact"
        ])
        state["autocrew"] = dict(enabled=bool(game.autocrew.enabled[role]),
                                 status=game.autocrew.status(game, role))
        # The whole crew's automation state (as the uConsole F3 overview):
        # own-crew configuration only, identical for every role.
        state["autocrew_overview"] = overview
        state[role] = operational[role]
        # Why each of the station's lamps shows what it shows (own state).
        state["lamp_tips"] = status_tips.for_role(game, role, game.tr)
        result[role] = state
    return result


def _opfor_common(game, status, role, boat):
    """Common block of a submarine role: the boat's own instruments only.

    No frigate plot, frigate audio cue, autocrew or mission framing ever reaches the
    opposing side; the weather block is read through the boat's workstation.
    """
    with game.sonar_perspective(boat.station):
        common = _common(game, status, role)
    # The commander sees the boat's own plot; the sonar room has none.
    common["plot"] = (_plot(game, boat.plot, boat.sub) if role in ("uboot", "uboot_nav") else
                      dict(objects=[], max_objects=plot.MAX_OBJECTS,
                           max_label=plot.MAX_LABEL, trail=[],
                           fx=dict(pings=[], echoes=[], splashes=[])))
    common["mission"]["objective"] = localize(boat_missions.objective(game, boat), game.tr)
    # The boat's own atmosphere cues (hull, detonations), never the frigate's.
    common["audio"] = dict(events=[dict(seq=int(row["seq"]), cue=str(row["kind"]),
                                        pan=_pan(row.get("pan")))
                                   for row in list(boat.sound_events)[-16:]],
                           callouts=boat.callouts.detached())
    common["hit_view"] = _hit_view(game, "uboot")
    common["crew_noise"] = _crew_noise(game, "uboot")
    # With the crew assist the boat's autocrew takes the station once released.
    assist = bool(game.autocrew.assist)
    common["autocrew"] = dict(enabled=assist, status="suspended_remote" if assist else "off")
    common["autocrew_overview"] = []
    common["alarms"] = _alarm_rows(station_alarms.boat(game, boat))
    return common


def _uboot_datum(boat, item):
    """Bearing/range from the boat to a torpedo's commanded datum (crew data)."""
    if item.guidance_x is None or item.guidance_y is None:
        return None, None
    dx, dy = item.guidance_x - boat.sub.x, item.guidance_y - boat.sub.y
    return (_number(math.degrees(math.atan2(dx, -dy)) % 360.0),
            _number(math.hypot(dx, dy)))


def _uboot_weapons(game, boat, asset_refs):
    """The boat's own torpedoes in the water, with their wire and datum."""
    return [dict(ref=asset_refs[("uboot_torpedo", id(item))], x=_number(item.x),
                 y=_number(item.y), depth_m=_number(item.depth),
                 course=_number(item.course), state=str(item.state)[:32],
                 wire=opfor.wire_state(boat, item),
                 datum_bearing=_uboot_datum(boat, item)[0],
                 datum_range_nm=_uboot_datum(boat, item)[1])
            for item in sorted(game.enemy_torpedoes, key=lambda weapon: weapon.id)
            if ("uboot_torpedo", id(item)) in asset_refs][:16]


def _sky(game):
    """The eyepieces' sky (light, cloud, precipitation, sun and moon) from
    the observed atmosphere and the clock; display only."""
    from src.ui import sight_scene
    values = sight_scene.sky_state(game)
    return {key: (values[key] if isinstance(values[key], (bool, str)) else _number(values[key]))
            for key in web_schema.SKY_FIELDS}


def _nav_lights(code):
    """A ``nav_lights`` code as published, or None."""
    from src.sensors import nav_lights
    return code if code is not None and nav_lights.valid(code) else None


def _sight_events(rows, now):
    """What an eye sees happen (``sight_events`` rows): type, measured
    bearing and range, age, lifetime, size and a fire's strength; no entity."""
    return [dict(type=str(row["kind"]), bearing=_number(row["bearing"]),
                 range_nm=_number(row["range_nm"]), age_s=_age(now, row["at_s"]),
                 dur_s=_number(row["dur_s"]), size_m=_number(row["size_m"]),
                 level=_number(row["level"]))
            for row in rows[:8]]


def _lookout_glasses(game):
    """The bridge lookout's binoculars: the horizon in motion and the outlines
    of his own sightings (measured bearing, class he made out, apparent
    length from the measured range); never a target's position."""
    from src.ui import horizon
    from src.ui.stations.bridge import eye_outlines
    weather = game.world.weather_values()
    # Pitch and roll by the heading to the sea; the browser turns them with
    # its own line of sight (``horizon_offset``/``horizon_tilt``: the bow).
    pitch, roll = horizon.hull_motion(0, game.sim_t, weather["sea_state"],
                                      weather["wind_from_deg"] - game.ship.course)
    offset, tilt = horizon.view_motion(pitch, roll)
    return dict(course=_number(game.ship.course % 360.0), speed_kn=_number(game.ship.speed),
                fov_deg=_number(config.LOOKOUT_GLASSES_FOV_DEG),
                visibility_nm=_number(weather["visibility_nm"]),
                sea_state=_number(weather["sea_state"]),
                horizon_offset=_number(offset), horizon_tilt=_number(tilt),
                motion_pitch=_number(pitch), motion_roll=_number(roll),
                sky=_sky(game),
                outlines=[dict(bearing=_number(bearing), span_deg=_number(span), cls=str(cls),
                               stale=bool(stale), lights=_nav_lights(lights),
                               elevation_deg=_number(elevation), aob_deg=_number(aob),
                               model=None if model is None else str(model), way=_number(way),
                               range_nm=_number(range_nm))
                          for bearing, span, cls, stale, lights, elevation, aob, model, way,
                          range_nm in
                          eye_outlines(game, game.lookout_sightings())[:16]],
                events=_sight_events(sight_events.frigate_rows(game), game.sim_t))


def _uboot_scope(game, boat):
    """The periscope: its line of sight, the light its optics see and the
    crew's own sightings (bearing, class, apparent length, stadimeter range);
    never a target's position or identity."""
    offset, tilt = opfor.horizon_motion(game, boat)
    now = game.sim_t
    return dict(
        available=bool(opfor.scope_available(boat)),
        relative_deg=_number(boat.orders.scope_rel_deg),
        bearing=_number(opfor.scope_bearing(boat)),
        course=_number(boat.sub.course % 360.0), speed_kn=_number(boat.sub.speed),
        fov_deg=_number(config.UBOOT_SCOPE_FOV_DEG),
        window_deg=_number(config.UBOOT_STADIMETER_WINDOW_DEG),
        night=bool(game.world.is_night()),
        visibility_nm=_number(getattr(game.world, "visibility_nm",
                                      config.WEATHER_VISIBILITY_MAX_NM)),
        sea_state=_number(getattr(game.world, "effective_sea_state", game.world.sea_state)),
        horizon_offset=_number(offset), horizon_tilt=_number(tilt),
        sky=_sky(game),
        sightings=[dict(ref=str(row["ref"])[:16], category=str(row["kind"]),
                        cls=str(row["cls"]), bearing=_number(row["bearing"]),
                        span_deg=_number(row["span_deg"]), quality=_number(row["quality"]),
                        age_s=_age(now, row["t"]), range_nm=_number(row["range_nm"]),
                        range_sigma_nm=_number(row["range_sigma_nm"]),
                        range_age_s=(_age(now, row["range_t"])
                                     if row["range_t"] is not None else None),
                        solution=_uboot_solution(boat, row["ref"], now),
                        lights=(None if now - row["t"] > 1.0
                                else _nav_lights(boat.orders._lights.get(row["ref"]))),
                        elevation_deg=(_number(boat.orders._elevation.get(row["ref"]))
                                       if row["kind"] == "FLG" else None),
                        aob_deg=(None if now - row["t"] > 1.0
                                 else _number(boat.orders._aspect.get(row["ref"]))),
                        model=(None if now - row["t"] > 1.0
                               else getattr(boat.orders, "_model", {}).get(row["ref"])),
                        way=(None if now - row["t"] > 1.0
                             else _number(getattr(boat.orders, "_way", {}).get(row["ref"]))))
                   for row in boat.orders.sightings[:config.UBOOT_SIGHTINGS_MAX]],
        events=_sight_events(sight_events.boat_rows(game, boat), now))


def _uboot_solution(boat, ref, now):
    """The attack computer's estimate on one sighting (the crew's own marks)."""
    values = attack_computer.summary(boat, ref, now)
    if values is None:
        return None
    return dict(marks=int(values["marks"]), course=_number(values["course"]),
                speed_kn=_number(values["speed_kn"]), lead_deg=_number(values["lead_deg"]),
                run_s=_number(values["run_s"]), quality=_number(values["quality"]))


def _uboot_plant(sub):
    """The boat's own plant and stores (legitimate own-ship truth): energy
    balance, endurance dived by speed, diesel and the boat's air."""
    endurance = sub.endurance
    if endurance is None:
        return dict(propulsion="nuclear", phase=None, battery_kwh=None, battery_capacity_kwh=None,
                    aip_kwh=None, aip_capacity_kwh=None, aip_kw=None, load_kw=None,
                    supply_kw=None, net_kw=None, empty_s=None, full_s=None,
                    generator_kw=None, fuel_l=None, fuel_capacity_l=None,
                    charge_rate=None, snorkel_rate=None, endurance=[], air=None)
    profile = endurance.profile
    maximum = sub.motion.maximum_speed_kn
    balance = endurance.forecast(sub.speed, maximum)
    litres = config.UBOOT_DIESEL_L_PER_KWH
    speeds = sorted({*(step for step in config.UBOOT_SPEED_STEPS_KN if 0.0 < step < maximum),
                     maximum})
    air = endurance.air
    return dict(
        propulsion="aip" if profile.aip_power_kw is not None else "diesel",
        phase=str(endurance.phase)[:16], battery_kwh=_number(endurance.battery_kwh),
        battery_capacity_kwh=_number(profile.battery_capacity_kwh),
        aip_kwh=(_number(endurance.aip_energy_kwh)
                 if profile.aip_power_kw is not None else None),
        aip_capacity_kwh=_number(profile.aip_energy_kwh),
        aip_kw=_number(profile.aip_power_kw),
        load_kw=_number(balance["load_kw"]), supply_kw=_number(balance["supply_kw"]),
        net_kw=_number(balance["net_kw"]), empty_s=_number(balance["empty_s"]),
        full_s=_number(balance["full_s"]),
        generator_kw=_number(profile.generator_power_kw),
        fuel_l=_number(endurance.fuel_kwh * litres),
        fuel_capacity_l=_number(endurance.fuel_capacity_kwh * litres),
        charge_rate=endurance.charge_rate, snorkel_rate=sub.snorkel_rate,
        endurance=[dict(speed_kn=_number(speed),
                        hours=_number(min(9999.0, endurance.submerged_hours(speed, maximum))))
                   for speed in speeds][:8],
        air=dict(o2_pct=_number(air.o2_pct), co2_pct=_number(air.co2_pct),
                 absorber_pct=_number(air.absorber_left * 100.0),
                 absorber_sets=int(air.absorber_sets), candles=int(air.candles),
                 candle_left_s=_number(air.candle_left_s), level=air.level(),
                 efficiency=_number(air.efficiency())))


def _uboot_ballast(sub):
    """The boat's own tanks, trim and air bottles (own-ship truth)."""
    ballast = sub.ballast
    flooding, moment = sub.flooding_kg(), sub.flood_moment_kg()
    return dict(
        blowing=bool(ballast.blowing), venting=bool(ballast.venting),
        auto=bool(ballast.auto), pumping=bool(ballast.pumping),
        compressor=bool(sub.snorkeling and sub.snorkel_rate != "vent"
                        and sub.damage_control.power()
                        and ballast.hp_air_bar < config.UBOOT_HP_AIR_MAX_BAR),
        hp_air_bar=_number(ballast.hp_air_bar),
        hp_air_max_bar=_number(config.UBOOT_HP_AIR_MAX_BAR),
        blows_left=int(ballast.blows_left()), mbt_pct=_number(ballast.mbt * 100.0),
        regulating_kg=_number(ballast.regulating_kg),
        regulating_order_kg=_number(ballast.regulating_order_kg),
        regulating_capacity_kg=_number(config.UBOOT_REGULATING_KG),
        trim_kg=_number(ballast.trim_kg), trim_order_kg=_number(ballast.trim_order_kg),
        trim_capacity_kg=_number(config.UBOOT_TRIM_TANK_KG),
        load_kg=_number(ballast.load_kg), flooding_kg=_number(flooding),
        residual_kg=_number(ballast.residual_kg(flooding)),
        trim_deg=_number(ballast.trim_deg(moment)),
        drift_mps=_number(ballast.vertical_drift_mps(flooding, sub.speed, moment)))


def _uboot_damage(game, boat):
    """The boat's own compartments, damage-control teams and crew (own-ship truth)."""
    sub = boat.sub
    control = sub.damage_control
    return dict(
        crew=_crew(game, boat.watch, game.peek_roster(boat.sub)),
        power=bool(control.power()), pumping=bool(control.pumping),
        compartments=[dict(
            name=name, water_kg=_number(c.water_kg), capacity_kg=_number(capacity_kg(index)),
            leak_pct=_number(c.leak * 100.0), fire_pct=_number(c.fire * 100.0),
            chlorine_pct=_number(c.chlorine * 100.0), closed=bool(c.closed),
            down=bool(control.down(name)))
            for index, (name, c) in enumerate(zip(COMPARTMENTS, control.compartments))],
        teams=[dict(team=index, compartment=str(team["compartment"]), task=str(team["task"]),
                    transit_s=_number(team["transit_s"]))
               for index, team in enumerate(control.teams)])


# Library suggestions per emitter in the browser (the crew picks by index).
UBOOT_ESM_CANDIDATES = 8


def _uboot_esm_candidate(game, esm, emitter, key):
    """A library entry as the crew reads it: name, radar role and fit grade."""
    profile = game.runtime_catalog.emitters.get(key)
    name = game.eloka_emitter_name(key) or key.rsplit(".", 1)[-1]
    return dict(name=str(name)[:64], role=str(getattr(profile, "radar_role", "unknown"))[:32],
                fit=esm.fit(game, emitter, key) or "poor")


def _uboot_esm(game, boat):
    """The boat's own ESM picture: mast time and the crew's emitter list
    (measured parameters, own-position bearing history, crew cross-fix and
    library classification; never an emitter's identity or position)."""
    esm, now = boat.esm, game.sim_t
    sea = float(getattr(game.world, "effective_sea_state", game.world.sea_state))
    rain = config.clamp(float(getattr(game.world, "rain_intensity", 0.0)), 0.0, 1.0)
    mast_range = boat_esm.mast_radar_nm(sea, rain)
    emitters = []
    threat = False
    for emitter in esm.ordered()[:config.UBOOT_ESM_EMITTERS_MAX]:
        track = emitter.track
        live = esm.live(emitter, now)
        danger = esm.mast_threat(game, emitter, now, mast_range)
        threat = threat or danger
        slope, trend = boat_esm.level_trend(emitter.history, now)
        fix = emitter.fix(now)
        emitters.append(dict(
            number=boat_esm.emitter_number(track.track_key),
            label=boat_esm.emitter_label(track.track_key),
            bearing=_number(track.bearing % 360.0),
            bearing_uncertainty_deg=_number(track.bearing_uncertainty_deg),
            frequency_hz=_number(track.frequency_hz), band=boat_esm.band(track.frequency_hz),
            prf_hz=_number(track.prf_hz), modulation=track.modulation_code,
            signal_db=_number(track.signal_db), trend=trend, trend_db_min=_number(slope),
            age_s=_age(now, track.last_seen), live=live,
            quality=_number(track.display_quality(now, config.UBOOT_ESM_MEMORY_S)),
            classification=(None if esm.classified(game, emitter) is None
                            else _uboot_esm_candidate(game, esm, emitter, emitter.label)),
            candidates=[_uboot_esm_candidate(game, esm, emitter, key)
                        for key in esm.library(game, emitter)[:UBOOT_ESM_CANDIDATES]],
            range_estimate_nm=_number(esm.range_estimate_nm(game, emitter)),
            mast_threat=danger,
            # The measured scan period: rotating search radar or a steady beam.
            scan=boat_esm.scan_reading(track),
            scan_period_s=(_number(track.revisit_s)
                           if boat_esm.scan_reading(track) is not None else None),
            history=[dict(age_s=_age(now, row[0]), x=_number(row[1]), y=_number(row[2]),
                          bearing=_number(row[3])) for row in emitter.history[-16:]],
            fix=None if fix is None else dict(
                x=_number(fix["x"]), y=_number(fix["y"]), major_nm=_number(fix["major_nm"]),
                minor_nm=_number(fix["minor_nm"]), axis_deg=_number(fix["axis_deg"]),
                lines=int(fix["lines"]), consistent=bool(fix["consistent"]))))
    mast_s = esm.mast_time_s(now)
    return dict(mast_up=esm.mast_since is not None, mast_s=_number(mast_s),
                mast_time_s=_number(boat_esm.recommended_mast_time_s(sea, rain, threat)),
                mast_threat=threat, mast_radar_nm=_number(mast_range),
                wash=_number(boat_esm.wash_fraction(sea)), emitters=emitters)


def _uboot_threat(game, boat):
    """The boat's counter-detection picture and evasion order (own
    intercepts and own state only; see src/core/boat_threat.py)."""
    view = boat_threat.picture(game, boat)
    plan = boat_threat.evasion_plan(game, boat)
    view["intercepts"] = [dict(type=row["kind"], bearing=_number(row["bearing"]),
                               level_db=_number(row["level_db"]), age_s=_number(row["age_s"]))
                          for row in view["intercepts"]]
    view["counts"] = {kind: int(view["counts"][kind]) for kind in boat_threat.KINDS}
    for key in ("loudest_db", "layer_m", "depth_m"):
        view[key] = _number(view[key])
    view["plan"] = None if plan is None else dict(
        {key: value for key, value in plan.items() if key != "kind"}, type=plan["kind"],
        bearing=_number(plan["bearing"]), course=_number(plan["course"]),
        speed_kn=_number(plan["speed_kn"]), depth_m=_number(plan["depth_m"]))
    view["clock"] = None if view["clock"] is None else dict(
        bearing=_number(view["clock"]["bearing"]), tti_s=_number(view["clock"]["tti_s"]))
    return view


def _uboot_radio_report(game, report):
    if report is None:
        return None
    return dict(x=_number(report["x"]), y=_number(report["y"]),
                radius_nm=_number(report["radius_nm"]), course=_number(report["course"]),
                speed_kn=_number(report["speed_kn"]),
                age_s=_number(max(0.0, game.sim_t - report["as_of"])))


def _uboot_radio(game, boat):
    """The radio room: HQ broadcast schedule, the boat's own transmissions and
    the copied messages (HQ's contact report is modelled intelligence, see
    src/core/boat_radio.py)."""
    radio = boat.radio
    progress = radio.progress(game, boat)
    latest = radio.latest_report()
    order = radio.active_order()
    return dict(
        antenna=bool(progress["antenna"]), broadcast=int(progress["broadcast"]),
        copied=bool(progress["copied"]), next_s=_number(progress["next_s"]),
        copy=_number(progress["copy"]), send=_number(progress["send"]),
        transmitting=bool(radio.transmitting), sitreps=int(progress["sitreps"]),
        ack_due=bool(progress["ack_due"]),
        report=_uboot_radio_report(game, None if latest is None else latest["report"]),
        log=[dict(seq=int(row["seq"]), type=row["kind"], age_s=_age(game.sim_t, row["t"]),
                  number=None if row["number"] is None else int(row["number"]),
                  ack=bool(row["ack"]), report=_uboot_radio_report(game, row["report"]),
                  order=None if row["order"] is None else int(row["order"]))
             for row in reversed(radio.log)],
        vlf=progress["reception"] == "vlf",
        order=None if order is None else _uboot_radio_order(game, order),
        # The open order worded by the optional language model (display only).
        worded=_worded_order(game, order),
        orders_done=sum(1 for row in radio.orders if row["state"] == "done"),
        orders_failed=sum(1 for row in radio.orders if row["state"] == "failed"),
        buoy=buoy_antenna.status(boat.orders.buoy),
        buoy_payout=_number(boat.orders.buoy[0]),
        buoy_rx=progress["reception"] == "buoy")


def _worded_order(game, order):
    worded = getattr(game, "llm_boat_order_text", None)
    text = worded(order) if worded is not None else None
    return str(text)[:512] if text else None


def _uboot_radio_order(game, order):
    """The open HQ order; an attack's position is its reported one,
    dead-reckoned (src/core/free_roam.py), never the merchant's truth."""
    x, y = order["x"], order["y"]
    if order["kind"] == "attack":
        from src.core import free_roam
        x, y = free_roam.target_position(order, game.sim_t)
    return dict(id=int(order["id"]), type=order["kind"], x=_number(x), y=_number(y),
                radius_nm=_number(order["radius_nm"]),
                left_s=_number(max(0.0, order["deadline_t"] - game.sim_t)))


def _uboot_sounder(game, boat):
    """The echo-sounder strip as on the uConsole's navigation page: own
    soundings over the window (age, seabed, own depth; every second sample)
    and the charted profile ahead on the ordered course (own chart)."""
    from src.ui import uboot_pilot
    sub, now = boat.sub, game.sim_t
    past = [[_number(now - t), _number(b), _number(d)]
            for t, _x, _y, b, d in boat.sounder.window(now)][::-2][::-1]
    bottom = sub.last_bottom_m
    if bottom is not None and math.isfinite(bottom):
        past.append([0.0, _number(max(0.0, bottom)), _number(sub.depth)])
    ahead = [[_number(distance), _number(depth)]
             for distance, depth in uboot_pilot.ahead_profile(game, sub)]
    scale = uboot_pilot.sounder_scale_m(sub, [row[1] for row in past] + [row[1] for row in ahead])
    return dict(past=past, ahead=ahead, scale_m=_number(scale),
                window_s=_number(uboot_pilot.WINDOW_S),
                ahead_nm=_number(config.UBOOT_OBSTACLE_LOOKAHEAD_NM),
                warn_m=_number(config.UBOOT_UNDER_KEEL_WARN_M),
                caution_m=_number(uboot_pilot.PILOT_CAUTION_M))


def _uboot(game, boat, rows, target_ref, asset_refs):
    """The crewed submarine's commander: own boat (legitimate truth), its
    orders, weapons and the boat's own sonar contacts."""
    sub = boat.sub
    endurance = sub.endurance
    battery = None
    phase = None
    if endurance is not None:
        capacity = endurance.profile.battery_capacity_kwh
        battery = (endurance.battery_kwh / capacity) if capacity else None
        phase = str(endurance.phase)[:16]
    launcher = (game.runtime_catalog.launchers[sub.weapon_battery.launcher_key]
                if sub.weapon_battery is not None else None)
    reason = sub.fire_readiness()
    store = sub.countermeasure_store
    alarms = sub.memory
    state = ("sunk" if sub.sunk else "sinking" if sub.state == "SINKING"
             else "manual" if sub.manual else "ai")
    est_x, est_y = boat_nav.position(boat)
    route = boat.orders.route
    return dict(
        navigation=dict(
            x=_number(sub.x), y=_number(sub.y), course=_number(sub.course),
            target_course=_number(sub.order_course), speed=_number(sub.speed),
            target_speed=_number(sub.order_speed), depth_m=_number(sub.depth),
            target_depth_m=_number(sub.order_depth),
            safe_depth_m=_number(sub.safe_depth_m(game.world)),
            max_depth_m=_number(float(sub.stype.max_depth_m)),
            crush_depth_m=_number(sub.crush_depth_m),
            max_speed_kn=_number(sub.motion.maximum_speed_kn),
            water_depth_m=_number(game.world.depth_m(sub.x, sub.y)),
            under_keel_m=_number(game.world.depth_m(sub.x, sub.y) - sub.depth),
            depth_presets={key: _number(value) for key, value
                           in opfor.depth_presets(game, boat).items()},
            obstacle_ahead_nm=_number(boat.orders.obstacle_ahead_nm),
            cavitating=bool(sub.cavitating), noise=_number(sub.noise_level()),
            # Dead reckoning: where the crew believes the boat is (their chart
            # is drawn about it), the navigator's error estimate and the fix.
            est_x=_number(est_x), est_y=_number(est_y),
            dr_error_nm=_number(boat_nav.uncertainty_nm(boat)),
            fix_age_s=_number(boat.orders.nav[2]),
            fix_progress=_number(boat_nav.fix_progress(boat)),
            route=dict(points=[[_number(x), _number(y)] for x, y in route.points],
                       index=int(route.index), type=str(route.kind),
                       active=bool(route.active)),
            sounder=_uboot_sounder(game, boat)),
        status=dict(
            state=state, damage=_number(sub.damage),
            emergency_ascent=bool(sub.emergency_ascent),
            blow_available=bool(sub.blow_available),
            battery=_number(battery), endurance_phase=phase,
            transmitting=bool(sub.transmitting),
            snorkel_available=sub.endurance is not None,
            snorkeling=bool(sub.snorkeling),
            silent=bool(sub.crew is not None and sub.crew.silent),
            quiet=bool(sub.crew is not None and sub.crew.quiet_active(sub)),
            bottomed=bool(sub.crew is not None and sub.crew.bottomed),
            surfaced=bool(sub.surfaced),
            mast=bool(sub.crew is not None and sub.crew.mast)),
        weapons=dict(
            torpedoes=int(sub.torpedoes_left),
            tubes_ready=opfor.tubes_flooded(sub),
            tubes=[dict(state=state, seconds=_number(seconds))
                   for state, seconds in opfor.tube_states(sub)[:32]],
            reload_s=(_number(sub.weapon_battery.next_reload_s)
                      if sub.weapon_battery is not None else None),
            ready=reason is None, reason=reason,
            arc_center_deg=(_number(launcher.arc_center_deg)
                            if launcher is not None else None),
            arc_width_deg=(_number(launcher.arc_width_deg)
                           if launcher is not None else None),
            pattern=str(boat.orders.torpedo_pattern),
            enable_nm=_number(boat.orders.torpedo_enable_nm),
            decoys=(int(store.remaining_total) if store is not None else 0),
            decoy_ready=bool(store is not None and store.ready > 0
                             and sub._decoy_cd <= 0.0 and not sub.pending_decoys)),
        alarms=dict(
            ping_age_s=(_number(alarms["last_ping_age"])
                        if math.isfinite(alarms["last_ping_age"]) else None),
            torpedo_age_s=(_number(alarms["last_torpedo_age"])
                           if math.isfinite(alarms["last_torpedo_age"]) else None),
            ping_bearing=_number(getattr(sub.crew, "ping_bearing", None)),
            torpedo_bearing=_number(getattr(sub.crew, "torpedo_bearing", None)),
            esm=[dict(bearing=_number(bearing), quality=_number(quality), age_s=_number(age))
                 for bearing, quality, age in (sub.crew.esm if sub.crew is not None else [])]),
        contacts=[_observation(row, _SONAR_FIELDS) for row in rows],
        own_weapons=_uboot_weapons(game, boat, asset_refs),
        designated_target_ref=target_ref,
        scope=_uboot_scope(game, boat),
        plant=_uboot_plant(sub),
        esm=_uboot_esm(game, boat),
        ballast=_uboot_ballast(sub),
        damage_control=_uboot_damage(game, boat),
        threat=_uboot_threat(game, boat),
        radio=_uboot_radio(game, boat),
        feed=[dict(seq=int(row["seq"]), age_s=_age(game.sim_t, row["t"]),
                   message=str(localize(row["text"], game.tr))[:256])
              for row in list(boat.feed)[-16:]])


def build_opfor_states(game, status, boat, rows, target_ref, focus_ref, sonar_refs,
                       asset_refs=None):
    """Canonical views of the submarine roles, or ``{}`` without a boat."""
    if boat is None:
        return {}
    result = {}
    command = None
    boat_tips = None
    for role in OPFOR_ROLES:
        state = _opfor_common(game, status, role, boat)
        if role != "uboot_sonar":
            # The boat's command stations share one picture of their own boat;
            # each browser station shows the part its watch operates.
            if command is None:
                command = _uboot(game, boat, rows, target_ref, asset_refs or {})
            state[role] = deepcopy(command)
        else:
            with game.sonar_perspective(boat.station):
                state[role] = _sonar(game, rows, focus_ref, target_ref, sonar_refs)
        # The command stations share one set of notes on their own boat.
        if role == "uboot_sonar" or boat_tips is None:
            with game.sonar_perspective(boat.station):
                tips = status_tips.for_role(game, role, game.tr, boat)
            if role != "uboot_sonar":
                boat_tips = tips
        state["lamp_tips"] = tips if role == "uboot_sonar" else boat_tips
        result[role] = state
    return result
