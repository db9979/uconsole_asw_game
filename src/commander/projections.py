"""Detached, role-scoped Remote Crew protocol-v2 projections.

The caller owns main-thread access to ``game``.  Every value returned here is a
JSON scalar or a newly allocated container; transport threads never receive a
simulation object.
"""

from copy import deepcopy
import math

from src.core import config
from src.core.i18n import localize
from src.core.version import APP_VERSION
from src.commander.server import CHART_MAX_BYTES, STATE_MAX_BYTES, STATIONS
from src.sensors.esm import ESMCorrelationEvidence, correlate_observations


ROLE_NAMES = STATIONS


def _number(value):
    return (value if type(value) in (int, float) and math.isfinite(value)
            else None)


def _age(now, stamp):
    stamp = _number(stamp)
    return now - stamp if stamp is not None and 0 <= stamp <= now else None


def _own_navigation(game):
    ship = game.ship
    return {key: _number(getattr(ship, key)) for key in (
        "x", "y", "course", "speed", "target_course", "target_speed",
        "rudder_angle", "yaw_rate")}


def _observation(row, fields):
    observation = {key: deepcopy(row[key]) for key in fields}
    if "label" in observation and "_display_id" in row:
        observation["label"] = row["_display_id"]
    return observation


_TACTICAL_FIELDS = ("ref", "label", "domain", "source", "affiliation",
                    "bearing", "range_nm", "x", "y", "course", "speed_kn",
                    "observer_x", "observer_y", "quality",
                    "age_s", "bearing_uncertainty_deg", "range_uncertainty_nm")
_SONAR_FIELDS = ("ref", "label", "source", "classification", "bearing",
                 "range_nm", "x", "y", "depth_m", "course", "speed_kn",
                 "quality", "age_s", "fix_age_s", "bearing_uncertainty_deg",
                 "range_uncertainty_nm", "observer_x", "observer_y",
                 "released_to_opz", "fixes")
_RADIO_FIELDS = ("ref", "label", "bearing", "quality", "age_s",
                  "bearing_uncertainty_deg")

_HISTORY_ROWS_MAX = config.LOFAR_HISTORY_COLS
_BROADBAND_BINS_MAX = 180
_TMA_CONTACTS_MAX = 32
_TMA_POINTS_MAX = 24
_ECHOES_MAX = 40
_MAP_ROWS_MAX = 128


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


def _common(game, status, role):
    return dict(protocol=2, version=APP_VERSION, session=status["session"],
                epoch=status["epoch"], revision=status["revision"],
                seq=status["seq"], phase=status["phase"], role=role,
                chart_revision=status["session"],
                clock=dict(sim=_number(game.sim_t), mission=_number(game.mission_time),
                           time_scale=game.time_scale, world=_number(game.world.hour)),
                environment=dict(sea_state=game.world.sea_state,
                                 is_night=bool(game.world.is_night())),
                mission=dict(name=localize(game.mission_name_display(), game.tr),
                             objective=localize(game.mission_objective_display(), game.tr),
                             remaining_s=_number(game.mission.remaining_s(game.mission_time))))


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


def _sonar_visualization(game, rows, sonar_refs):
    sonar = game.sonar
    receiver = sonar.receiver
    broadband = []
    bb_rows = list(sonar.broadband_history)[-_HISTORY_ROWS_MAX:]
    bb_times = list(sonar.history_times)[-len(bb_rows):]
    for stamp, values in zip(bb_times, bb_rows):
        bins = [round(min(1.0, max(0.0, value * 10 ** (sonar.gain_db / 20))), 5)
                for value in _series(values, _BROADBAND_BINS_MAX)]
        age = _age(game.sim_t, stamp)
        if age is not None and bins:
            broadband.append(dict(age_s=age, bins=bins))

    lofar = []
    lf_rows = list(sonar.lofar_history)[-_HISTORY_ROWS_MAX:]
    lf_times = list(sonar.lofar_times)[-len(lf_rows):]
    lf_bearings = list(sonar.lofar_bearings)[-len(lf_rows):]
    for stamp, bearing, values in zip(lf_times, lf_bearings, lf_rows):
        bins = [round(value, 5) for value in sonar.process_lofar_column(
            _series(values, config.LOFAR_BINS), game.ship)]
        age = _age(game.sim_t, stamp)
        if age is not None and _number(bearing) is not None and bins:
            lofar.append(dict(age_s=age, bearing=_number(bearing), bins=bins))
    held = bool(sonar.peak_hold and sonar.peak_spectrum)
    spectrum = [round(value, 5) for value in sonar.process_lofar_column(
        _series(sonar.peak_spectrum if held else receiver.spectrum,
                config.LOFAR_BINS), game.ship)]

    analysis = None
    if isinstance(sonar.demon_analysis, dict):
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

    tma = []
    for row in (row for row in rows if row["source"].startswith("SONAR")):
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
        tma.append(dict(ref=row["ref"], bearings=points, solution=solution))
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
        broadband=dict(bearing_start_deg=0.0, bearing_step_deg=2.0,
                       history=broadband),
        lofar=dict(frequency_min_hz=0.0, frequency_max_hz=config.LOFAR_FMAX_HZ,
                   bin_frequencies_hz=[config.lofar_bin_freq(i)
                                       for i in range(config.LOFAR_BINS)],
                   history=lofar, spectrum=spectrum, held=held),
        demon=dict(frequency_min_hz=1.0, frequency_max_hz=80.0,
                   bin_step_hz=1.0, spectrum=_series(receiver.demon_spectrum, 80),
                   analysis=analysis),
        tma=tma, bt=bt_data, active_echoes=echoes,
        receiver=dict(array=str(sonar._receiver_mode)[:16],
                      listen_bearing=_number(sonar.listen_bearing),
                      beam_width_deg=_number(sonar.beam_width_deg),
                      listen_mode=str(sonar.audition_mode)[:16],
                      focus_locked=bool(sonar.focus_locked),
                      audio_enabled=bool(game.sonar_audio_enabled)))


def _sonar(game, rows, focus_ref, target_ref, sonar_refs):
    tow = game.sonar.tow_status(game.ship.speed)
    band = (game.sonar.band_low_hz, game.sonar.band_high_hz)
    presets = {"FULL": (0.0, 300.0), "LOW": (4.0, 80.0),
               "SHAFT": (8.0, 55.0), "MID": (20.0, 120.0)}
    return dict(observations=[_observation(row, _SONAR_FIELDS) for row in rows
                              if row["source"].startswith("SONAR")],
                settings=dict(mode=game.sonar_mode, page=game.sonar_page,
                              listen_bearing=_number(game.sonar.listen_bearing),
                              focus_ref=focus_ref if game.sonar.focus_locked else None,
                              target_ref=target_ref,
                              station_down=game.damage.station_down("sonar"),
                               tow=dict(state=str(tow["state"])[:32],
                                        payout=_number(tow["payout"]),
                                        available=bool(tow["available"]),
                                        handling_ok=bool(tow["handling_ok"]),
                                        speed_kn=_number(game.ship.speed),
                                        speed_min_kn=config.SONAR_TOWED_HANDLING_MIN_KN,
                                        speed_max_kn=config.SONAR_TOWED_HANDLING_MAX_KN,
                                        depth_m=_number(tow["depth_m"]),
                                       depth_target_m=_number(
                                           tow["depth_target_m"])),
                              bt=dict(ready=game.sonar.bt_cooldown <= 0,
                                       cooldown_s=_number(game.sonar.bt_cooldown),
                                       thermocline_m=_number(
                                           game.sonar.bt_profile.get("thermocline_m"))
                                       if game.sonar.bt_profile else None),
                              ping=dict(ready=bool(game.sonar.ping_ready),
                                        cooldown_s=_number(
                                            game.sonar.ping_cooldown_remaining)),
                              tma_enabled=bool(game.sonar.tma_enabled),
                              gain_db=_number(game.sonar.gain_db),
                              band_preset=next((key for key, value in presets.items()
                                                if value == band), None),
                              band_hz=[_number(band[0]), _number(band[1])],
                              notch=bool(game.sonar.notch_enabled),
                              peak_hold=bool(game.sonar.peak_hold),
                              harmonic_hz=_number(game.sonar_harmonic_hz),
                              harmonic_candidates_hz=[_number(value) for value in
                                                      game.sonar_harmonic_candidates()],
                              audio_enabled=bool(game.sonar_audio_enabled),
                              volume=_number(game.sonar_volume),
                              quiet_mode=bool(game.ship.quiet_mode)),
                visualization=_sonar_visualization(game, rows, sonar_refs))


def _weapons(game, rows, target_ref, asset_refs, direct_refs):
    tactical = [row for row in rows if row.get("_opz")
                and row["ref"] == target_ref][:_MAP_ROWS_MAX]
    designated = next((_weapon_observation(row) for row in tactical
                       if row["ref"] == target_ref), None)
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
                                nixies=None if store is None else store.remaining_total),
                 readiness=dict(station_down=game.damage.station_down("weapons"),
                                roe=game.roe, ciws_ready=game.ciws_cooldown_s <= 0,
                                aa_ready=game.aa_cooldown_s <= 0,
                                state="unavailable" if battery is None else "available",
                                interlock=str(localize(interlock, game.tr))[:256],
                                reload_s=None if battery is None else _number(
                                    battery.next_reload_s)),
                 designated_target=designated,
                 navigation=_own_navigation(game), tactical=_map_rows(tactical),
                  target_choices=_direct_fire_observations(rows, direct_refs),
                 depth_m=_number(game.torpedo_depth), tubes=tubes,
                 own_weapons=torpedoes + asrocs,
                 active_assets=torpedoes + asrocs + nixies)


def _damage(game):
    compartments = [dict(key=room.key, name=game.tr("compartment." + room.key),
                          state=room.state, flood=_number(room.flood),
                          fire=_number(room.fire),
                           repairable=room.key in game.damage.repair_candidates(),
                           trend={key: _number(value) if key != "repairable" else bool(value)
                                  for key, value in game.damage.compartment_trend(
                                      room.key).items()})
                    for room in game.damage.compartments.values()]
    teams = [dict(team=team, compartment=game.damage.teams[team])
             for team in sorted(game.damage.teams)]
    return dict(compartments=compartments, teams=teams,
                total=_number(game.damage.total), sunk=bool(game.damage.ship_sunk))


def _radio(game, rows, ref_by_track):
    station_down = game.damage.station_down("radio")
    observations = []
    for row in rows:
        if row["source"] != "HFDF":
            continue
        observation = _observation(row, _RADIO_FIELDS)
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
    messages = [dict(stamp=str(stamp)[:32], text=str(localize(text, game.tr))[:512])
                for stamp, text in game.messages[-40:]]
    return dict(observations=observations, logged_fixes=fixes,
                 logged_bearings=logged, messages=messages,
                 station_down=station_down, navigation=_own_navigation(game),
                  tactical=[_observation(row, _TACTICAL_FIELDS) for row in rows
                            if row["source"] == "HFDF"][:_MAP_ROWS_MAX])


def _helicopter(game, rows, asset_refs, buoy_labels, direct_refs=None):
    helo = game.helo
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
                 dip_ping_cooldown_s=_number(helo.dip_ping_cooldown))
    waypoint = (dict(x=_number(helo.waypoint_x), y=_number(helo.waypoint_y))
                 if helo.waypoint_x is not None
                 and helo.waypoint_y is not None else None)
    buoys = [dict(ref=asset_refs[("buoy", id(buoy))],
                   label=buoy_labels[("buoy", id(buoy))],
                   x=_number(buoy.x), y=_number(buoy.y),
                   battery_s=_number(buoy.battery_s), active=bool(buoy.active))
             for buoy in sorted(game.buoys, key=lambda item: item.seq)[:64]]
    distance = (math.hypot(helo.x - game.ship.x, helo.y - game.ship.y)
                if airborne else None)
    tactical = [row for row in rows if row.get("_opz")
                and row["ref"] in (direct_refs or {})]
    return dict(asset=asset, waypoint=waypoint, buoys=buoys,
                navigation=_own_navigation(game), tactical=[
                    _observation(row, _TACTICAL_FIELDS)
                    for row in tactical[:_MAP_ROWS_MAX]],
                 target_choices=_direct_fire_observations(
                     rows, {} if direct_refs is None else direct_refs),
                 readiness=dict(
                     flightdeck_down=game.damage.station_down("flightdeck"),
                     deck_state=game.damage.station_state("flightdeck"),
                     can_launch=helo.state == "HANGAR"
                    and not game.damage.station_down("flightdeck"),
                    can_return=airborne,
                     can_set_waypoint=helo.state != "VERLOREN",
                     can_deploy_buoy=airborne and helo.buoys_left > 0
                      and helo.water_entry_clear(game.world),
                     can_set_dipping=helo.state == "AUF"
                      and (helo.dip_state != "STOWED"
                           or helo.dip_depth_limit(game.world)
                           >= config.HELO_DIP_DEPTH_MIN_M),
                     can_set_dip_depth=helo.state == "AUF"
                      and helo.dip_state in ("DEPLOYING", "DEPLOYED"),
                     can_dipping_ping=not game.damage.station_down("sonar")
                      and helo.dip_ping_ready,
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
    for track in game.eloka_tracks():
        age = _age(game.sim_t, track.last_seen)
        if age is None or age > game.esm_picture.stale_s:
            continue
        candidates = [dict(ref=candidate_refs[(track.track_key, item.emitter_key)],
                            name=(game.eloka_emitter_name(item.emitter_key) or "")[:128],
                            score=_number(item.score))
                      for item in game.eloka_candidates(track)[:5]]
        annotation = game.eloka_annotation_name(track.track_key)
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
        intercepts.append(dict(ref=esm_refs[track.track_key], label=track.track_key,
            bearing=_number(track.bearing),
            bearing_uncertainty_deg=_number(track.bearing_uncertainty_deg),
            frequency_hz=_number(track.frequency_hz), prf_hz=_number(track.prf_hz),
            modulation=track.modulation_code, quality=_number(track.display_quality(
                game.sim_t, game.esm_picture.stale_s)), age_s=age,
            annotation=None if annotation is None else str(annotation)[:128],
            candidates=candidates, correlations=correlations))
    down = game.damage.station_down("opz")
    return dict(intercepts=intercepts, station_down=down,
                status="down" if down else "live")


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
            members = game.opz_fusion.fusions.get(next(
                (key for key, value in ref_by_track.items() if value == row["ref"]), ""))
            if (members is None
                    or any(item not in ref_by_track for item in members.members)):
                continue
            observation["members"] = [ref_by_track[item] for item in members.members]
            opz_fusions.append(observation)
        else:
            opz_observations.append(observation)
        if row["classification"] is not None:
            source_classifications.append(dict(ref=row["ref"], source=row["source"],
                                               classification=row["classification"]))
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
                                    average_flood=_number(game.damage.avg_flood())),
                        systems=[dict(key=key, state=game.damage.station_state(key),
                                      down=game.damage.station_down(key))
                                 for key in sorted(game.damage.compartments)],
                         tactical_summary=[_observation(row, _TACTICAL_FIELDS)
                                           for row in rows
                                          if row["source"] not in ("ESM", "FUSION")
                                          and not row["source"].startswith("SONAR")]),
        "sonar": _sonar(game, rows, focus_ref, target_ref, sonar_refs),
        "weapons": _weapons(game, rows, target_ref, asset_refs,
                            direct_fire_refs["weapons"]),
        "damage": _damage(game),
        "opz": dict(observations=opz_observations,
                      fusions=opz_fusions,
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
                                    aa_ready=game.aa_cooldown_s <= 0),
                       asm_observations=[dict(
                           _observation(row, _TACTICAL_FIELDS),
                           ref=direct_fire_refs["opz"][row["ref"]])
                           for row in rows if row.get("_opz")
                           and row["ref"] in direct_fire_refs["opz"]],
                      source_classifications=source_classifications,
                      designated_target_ref=(target_ref if any(
                          row.get("_opz") and row["ref"] == target_ref
                          for row in rows) else None),
                      own_assets=dict(ship=_own_navigation(game),
                                       helicopter=_helicopter(
                                           game, rows, asset_refs, buoy_labels)["asset"])),
        "radio": _radio(game, rows, ref_by_track),
        "engine": dict(propulsion=dict(speed=_number(game.ship.speed),
                    target_speed=_number(game.ship.target_speed), telegraph=game.ship.telegraph,
                    rpm=_number(game.ship.rpm()), quiet_mode=bool(game.ship.quiet_mode),
                    cavitating=bool(game.ship.cavitating)),
                     machinery=dict(station_state=game.damage.station_state("engine"),
                                    speed_cap=_number(game.ship.speed_cap),
                                    effective_speed_cap=_number(
                                        game.damage.engine_speed_cap()),
                                    flood=_number(game.damage.compartments[
                                        "engine"].flood),
                                    fire=_number(game.damage.compartments[
                                        "engine"].fire),
                                    noise=_number(game.ship.noise_level()),
                                    grounded=bool(game.ship.grounded)),
                    controls=dict(orders=["ASTERN", "STOP", "SLOW", "HALF",
                                          "FULL", "FLANK"],
                                  speed_max_kn=_number(config.SHIP_SPEED_MAX_KN)),
                     environment_effects=dict(sea_state=game.world.sea_state,
                                              roll=_number(game.ship.roll),
                                              pitch=_number(game.ship.pitch),
                                              tas_available=bool(
                                                  game.sonar_mode != "TOWED"
                                                  or game.sonar._tow_available()),
                                              tas_performance=_number(
                                                  game.sonar.tow_performance))),
        "helicopter": _helicopter(game, rows, asset_refs, buoy_labels,
                                   direct_fire_refs["helicopter"]),
        "eloka": _eloka(game, rows, esm_refs, candidate_refs),
    }
    result = {}
    for role in ROLE_NAMES:
        state = deepcopy(common)
        state["role"] = role
        state[role] = operational[role]
        result[role] = state
    return result
