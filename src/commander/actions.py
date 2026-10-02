"""Station action handlers of the Remote Crew bridge: one small function per
v2 action, applied on the main thread through the closed tables
``_V2_ACTION_HANDLERS``, ``_UBOOT_ACTION_HANDLERS`` and
``_HOST_ACTION_HANDLERS`` (never a dynamic method lookup).

Verbatim move from ``bridge.py`` (1.3.59); ``bridge.py`` re-exports every
name so existing imports keep working."""

import math


from src.core import attack_computer, boat_nav, buoy_antenna, config, opfor
from src.physics import torpedo_dyn
from src.core import phone_lookout


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None

def _acknowledge(game, params, _bindings=None):
    return params == {}


def _bridge_set_course(game, params, _bindings=None):
    return game.order_course(params["course"])


def _bridge_set_speed(game, params, _bindings=None):
    return game.order_speed(params["speed_kn"])


def _bridge_route_add(game, params, _bindings=None):
    return game.add_route_waypoint(params["x"], params["y"])


def _bridge_route_pattern(game, params, _bindings=None):
    return game.start_route_pattern(params["pattern"])


def _bridge_route_clear(game, params, _bindings=None):
    return game.clear_route()


def _bridge_clear_baffles(game, params, _bindings=None):
    return game.clear_baffles()


def _bound(bindings, ref):
    return bindings.get(ref) if type(ref) is str else None


def _sonar_classify(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None or not binding[1].startswith("SONAR") or binding[2] is None:
        return "unknown_ref"
    return game.classify_sonar_contact(binding[2], params["classification"])


def _sonar_set_release(game, params, bindings, role="sonar"):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None else
            game.release_sonar_contact(contact, params["released"], source=role))


def _helicopter_qualify(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None else
            game.qualify_helicopter_contact(contact, params["enabled"]))


def _helicopter_buoy_release(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None else
            game.release_sonar_contact(contact, params["released"], source="buoy"))


def _opz_id(bindings, ref):
    binding = _bound(bindings, ref)
    return (binding[0] if binding is not None and binding[1] != "HFDF"
            and binding[3] else None)


def _opz_classify(game, params, bindings):
    key = _opz_id(bindings, params["ref"])
    return "unknown_ref" if key is None else game.classify_opz_observation(
        key, params["classification"])


def _opz_affiliate(game, params, bindings):
    key = _opz_id(bindings, params["ref"])
    return "unknown_ref" if key is None else game.affiliate_opz_observation(
        key, params["affiliation"])


def _opz_set_track_id(game, params, bindings):
    key = _opz_id(bindings, params["ref"])
    return "unknown_ref" if key is None else game.set_opz_track_label(
        key, params["label"])


def _opz_create_fusion(game, params, bindings):
    keys = [_opz_id(bindings, ref) for ref in params["refs"]]
    if any(key is None for key in keys):
        return "unknown_ref"
    if any(bindings[ref][1] == "FUSION" for ref in params["refs"]):
        return "source_owned"
    return game.create_opz_fusion(keys)


def _opz_dissolve_fusion(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None:
        return "unknown_ref"
    if binding[1] != "FUSION":
        return "source_owned"
    return game.dissolve_opz_fusion(binding[0])


def _opz_dismiss_suggestion(game, params, bindings):
    keys = [_opz_id(bindings, ref) for ref in params["refs"]]
    if any(key is None for key in keys):
        return "unknown_ref"
    return game.dismiss_opz_suggestion(keys)


def _opz_set_ciws(game, params, _bindings):
    return game.set_ciws_authorized(params["enabled"])


def _opz_set_radar(game, params, _bindings):
    return game.set_opz_radar(params["domain"], params["enabled"])


def _opz_set_range(game, params, _bindings):
    return game.set_opz_range(params["range_nm"])


def _opz_designate_target(game, params, bindings):
    key = _opz_id(bindings, params["ref"])
    return "unknown_ref" if key is None else game.designate_opz_observation(key)


def _engine_set_telegraph(game, params, _bindings):
    return game.set_engine_telegraph(params["order"])


def _engine_set_course(game, params, _bindings):
    return game.set_engine_course(params["course"])


def _engine_set_speed(game, params, _bindings):
    return game.set_engine_speed(params["speed_kn"])


def _engine_set_quiet_mode(game, params, _bindings):
    return game.set_quiet_mode(params["enabled"])


def _engine_set_plant(game, params, _bindings):
    return game.set_plant_mode(params["mode"])


def _damage_counterflood(game, params, _bindings):
    return game.set_counterflood(params["enabled"])


def _damage_assign_team(game, params, _bindings):
    return game.assign_damage_team(params["team"], params["compartment"])


def _damage_unassign_team(game, params, _bindings):
    return game.unassign_damage_team(params["team"], params["compartment"])


def _radio_capture_hfdf(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None or binding[1] != "HFDF":
        return "unknown_ref"
    return game.capture_hfdf_report(binding[4])


def _crew_action_stations(game, params, _bindings):
    return game.set_action_stations(params["enabled"])


def _crew_watch_change(game, params, _bindings):
    return game.change_watch()


def _casualty_result(result):
    return result if result is True else "not_ready"


def _crew_casualty_medic(game, _params, _bindings):
    return _casualty_result(game.casualty_medic())


def _crew_casualty_reassign(game, _params, _bindings):
    return _casualty_result(game.casualty_reassign())


def _radio_task_accept(game, params, _bindings):
    return game.accept_task(params["task"])


def _radio_task_decline(game, params, _bindings):
    return game.decline_task(params["task"])


def _radio_request_ras(game, params, _bindings):
    result = game.request_ras()
    # The browser shows the radio room's own refusals as "not ready".
    return result if result is True or result == "radio_down" else "not_ready"


def _radio_contact_report(game, params, _bindings):
    result = game.send_contact_report()
    return result if result is True or result == "radio_down" else "not_ready"


def _radio_request_support(game, params, _bindings):
    result = game.request_support()
    return result if result is True or result == "radio_down" else "not_ready"


def _eloka_annotate(game, params, bindings):
    intercept = _bound(bindings, params["ref"])
    candidate = _bound(bindings, params["candidate_ref"])
    if intercept is None or intercept[1] != "ELOKA":
        return "unknown_ref"
    if candidate is None or candidate[1] != "ELOKA_CANDIDATE":
        return "unknown_ref"
    if candidate[2] is not intercept[2]:
        return "stale_ref"
    return game.annotate_eloka_intercept(intercept[2], candidate[0])


def _eloka_clear_annotation(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None or binding[1] != "ELOKA":
        return "unknown_ref"
    return game.clear_eloka_annotation(binding[2])


def _eloka_set_jamming(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None or binding[1] != "ELOKA":
        return "unknown_ref"
    return game.set_jamming(binding[2], params["enabled"])


def _eloka_set_technique(game, params, bindings):
    binding = _bound(bindings, params["ref"])
    if binding is None or binding[1] != "ELOKA":
        return "unknown_ref"
    return game.set_jamming_technique(binding[2], params["technique"])


def _eloka_set_auto(game, params, _bindings):
    return game.set_ecm_auto(params["enabled"])


def _sonar_contact(bindings, ref):
    binding = _bound(bindings, ref)
    return (binding[2] if binding is not None
            and binding[1].startswith("SONAR") else None)


def _sonar_set_listen_bearing(game, params, _bindings):
    return game.set_sonar_listen_bearing(params["bearing"])


def _sonar_set_focus(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return "unknown_ref" if contact is None else game.set_sonar_focus(contact)


def _sonar_clear_focus(game, params, _bindings):
    return game.clear_sonar_focus()


def _sonar_set_array_mode(game, params, _bindings):
    return game.set_sonar_array_mode(params["mode"])


def _sonar_set_tas(game, params, _bindings):
    return game.set_sonar_tas(params["deployed"])


def _sonar_set_tow_depth(game, params, _bindings):
    return game.set_sonar_tow_depth(params["depth_m"])


def _sonar_set_vds(game, params, _bindings):
    return game.set_sonar_vds(params["deployed"])


def _sonar_set_vds_depth(game, params, _bindings):
    return game.set_sonar_vds_depth(params["depth_m"])


def _opz_mark_blip(game, params, _bindings):
    # Blip refs are "blip-<sequence>": a display counter, never a target identity.
    ref = params["ref"]
    if not ref.startswith("blip-") or not ref[5:].isdigit() or len(ref) > 24:
        return "unknown_ref"
    return game.mark_radar_blip(int(ref[5:]))


def _sonar_measure_bt(game, params, _bindings):
    return game.measure_sonar_bt()


def _sonar_active_ping(game, params, _bindings):
    return game.send_active_ping()


def _sonar_set_tma_enabled(game, params, _bindings):
    return game.set_sonar_tma_enabled(params["enabled"])


def _sonar_set_gain(game, params, _bindings):
    return game.set_sonar_gain(params["gain_db"])


def _sonar_set_audition_mode(game, params, _bindings):
    return game.set_sonar_audition_mode(params["mode"])


def _sonar_set_band_preset(game, params, _bindings):
    return game.set_sonar_band_preset(params["preset"])


def _sonar_set_notch(game, params, _bindings):
    return game.set_sonar_notch(params["enabled"])


def _sonar_set_peak_hold(game, params, _bindings):
    return game.set_sonar_peak_hold(params["enabled"])


def _sonar_set_harmonic(game, params, _bindings):
    return game.set_sonar_harmonic(params["frequency_hz"])


def _sonar_set_cursor(game, params, _bindings):
    return game.set_sonar_cursor(params["page"], params["frequency_hz"])


def _sonar_mark_line(game, params, _bindings):
    return game.mark_sonar_cursor(params["page"])


def _plot_add(game, params, _bindings, layer=None):
    fields = {key: value for key, value in params.items()
              if key not in ("shape", "x", "y", "label")}
    result = game.plot_add(params["shape"], params["x"], params["y"],
                           params["label"], layer=layer, **fields)
    return "active_limit" if result == "full" else (
        True if type(result) is int else result)


def _plot_remove(game, params, _bindings, layer=None):
    return game.plot_remove(params["id"], layer=layer)


def _plot_relabel(game, params, _bindings, layer=None):
    return game.plot_relabel(params["id"], params["label"], layer=layer)


def _plot_clear(game, _params, _bindings, layer=None):
    return game.plot_clear(layer=layer)


def _sonar_set_integration(game, params, _bindings):
    return game.set_sonar_integration(params["seconds"])


def _sonar_set_vernier(game, params, _bindings):
    return game.set_sonar_vernier(params["enabled"])


def _sonar_set_band(game, params, _bindings):
    return game.set_sonar_band(params["low_hz"], params["high_hz"])


def _sonar_set_operator_notch(game, params, _bindings):
    return game.set_sonar_operator_notch(params["frequency_hz"])


def _sonar_tas_side(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None
            else game.set_tas_side(contact, params["action"]))


def _sonar_set_demon_band(game, params, _bindings):
    return game.set_sonar_demon_band(float(params["low_hz"]), float(params["high_hz"]))


def _sonar_set_heterodyne(game, params, _bindings):
    return game.set_sonar_heterodyne(float(params["frequency_hz"]))


def _sonar_assign_profile(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None else
            game.assign_contact_profile(contact, params["profile_key"]))


def _sonar_tma_set(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return ("unknown_ref" if contact is None else game.set_tma_hypothesis(
        contact, params["course"], params["speed_kn"], params["range_nm"]))


def _sonar_tma_accept(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return "unknown_ref" if contact is None else game.accept_tma(contact)


def _sonar_tma_copy_proposal(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return "unknown_ref" if contact is None else game.copy_tma_proposal(contact)


def _sonar_designate_target(game, params, bindings):
    contact = _sonar_contact(bindings, params["ref"])
    return "unknown_ref" if contact is None else game.designate_sonar_target(contact)


def _helicopter_launch(game, params, _bindings):
    return game.launch_helicopter()


def _helicopter_return(game, params, _bindings):
    return game.return_helicopter()


def _helicopter_set_waypoint(game, params, _bindings):
    return game.set_helicopter_waypoint(params["x"], params["y"])


def _helicopter_deploy_buoy(game, params, _bindings):
    return game.deploy_helicopter_buoy()


def _helicopter_set_pattern(game, params, _bindings):
    return game.set_helicopter_pattern(params["kind"])


def _helicopter_set_mad(game, params, _bindings):
    return game.set_helicopter_mad(params["enabled"])


def _helicopter_set_radar(game, params, _bindings):
    return game.set_helicopter_radar(params["enabled"])


def _helicopter_set_buoy_mode(game, params, _bindings):
    return game.set_helicopter_buoy_mode(params["mode"])


def _helicopter_set_listen_source(game, params, _bindings):
    return game.set_helicopter_listen_source(params["source"])


def _helicopter_set_listen_bearing(game, params, _bindings):
    return game.set_helicopter_listen_bearing(params["bearing"])


def _helicopter_clear_listen_bearing(game, _params, _bindings):
    return game.set_helicopter_listen_bearing(None)


def _helicopter_set_audio_mode(game, params, _bindings):
    return game.set_helicopter_audio_mode(params["mode"])


def _helicopter_set_audio_band(game, params, _bindings):
    return game.set_helicopter_audio_band(params["preset"])


def _helicopter_set_audio_gain(game, params, _bindings):
    return game.set_helicopter_audio_gain(params["gain_db"])


def _helicopter_set_audio_notch(game, params, _bindings):
    return game.set_helicopter_audio_notch(params["enabled"])


def _helicopter_set_dipping(game, params, _bindings):
    return game.set_helicopter_dipping(params["deployed"])


def _helicopter_set_dip_depth(game, params, _bindings):
    return game.set_helicopter_dip_depth(params["depth_m"])


def _helicopter_dipping_ping(game, params, _bindings):
    return game.send_helicopter_dipping_ping()


def _direct_observation(bindings, ref, kind):
    binding = _bound(bindings, ref)
    return (binding if binding is not None and len(binding) == 6
            and binding[1] == kind else None)


def _weapons_launch_torpedo(game, params, bindings):
    binding = _direct_observation(bindings, params["ref"], "DIRECT_SONAR")
    if binding is None or binding[5] != "weapons":
        return "unknown_ref"
    contact = binding[2]
    if game.sonar.contacts.get(contact.target_id) is not contact:
        return "stale_ref"
    return game.launch_torpedo_at(contact, params["depth_m"])


def _helicopter_launch_torpedo(game, params, bindings):
    binding = _direct_observation(bindings, params["ref"], "DIRECT_SONAR")
    if binding is None or binding[5] not in ("weapons", "helicopter"):
        return "unknown_ref"
    contact = binding[2]
    if game.sonar.contacts.get(contact.target_id) is not contact:
        return "stale_ref"
    return game.launch_helicopter_torpedo_at(contact, params["depth_m"])


def _mpa_request(game, _params, _bindings):
    return game.request_mpa()


def _mpa_return(game, _params, _bindings):
    return game.mpa_return()


def _mpa_set_waypoint(game, params, _bindings):
    return game.set_mpa_waypoint(params["x"], params["y"])


def _mpa_set_pattern(game, params, _bindings):
    return game.set_mpa_pattern(params["kind"])


def _mpa_drop_buoy(game, _params, _bindings):
    return game.mpa_drop_buoy()


def _mpa_set_buoy_mode(game, params, _bindings):
    return game.set_mpa_buoy_mode(params["mode"])


def _mpa_set_mad(game, params, _bindings):
    return game.set_mpa_mad(params["enabled"])


def _mpa_set_radar(game, params, _bindings):
    return game.set_mpa_radar(params["enabled"])


def _mpa_attack(game, _params, _bindings):
    return game.mpa_attack()


def _consort_set_mode(game, params, _bindings):
    return game.set_consort_mode(params["mode"])


def _consort_set_point(game, params, _bindings):
    return game.set_consort_point(params["x"], params["y"])


def _consort_set_station(game, params, _bindings):
    return game.set_consort_station(params["station"])


def _consort_set_active(game, params, _bindings):
    return game.set_consort_active(params["enabled"])


def _consort_set_weapons(game, params, _bindings):
    return game.set_consort_weapons(params["enabled"])


def _consort_fire(game, _params, _bindings):
    return game.consort_fire_on_prosecution()


def _weapons_set_torpedo_settings(game, params, _bindings):
    """Type, pattern, enable point and salvo in one settings command; the
    first refused value stops the sequence and names the reason."""
    for setter, value in ((game.set_torpedo_type, params["torpedo_type"]),
                          (game.set_torpedo_pattern, params["pattern"]),
                          (game.set_torpedo_enable, float(params["enable_nm"])),
                          (game.set_torpedo_salvo, params["salvo"])):
        result = setter(value)
        if result is not True:
            return result
    return True


def _weapons_deploy_nixie(game, params, _bindings):
    return game.deploy_nixie_result()


# Own-attack refusals the command pipeline reports with its shared codes.
_OWN_ATTACK_REASONS = {"empty_asroc": "empty", "empty_depth_charges": "empty",
                       "reloading": "not_ready", "too_slow": "not_ready",
                       "rbu_empty": "empty", "rbu_reloading": "not_ready",
                       "rbu_no_warning": "not_ready"}


def _weapons_own_attack(game, params, bindings, fire):
    binding = _direct_observation(bindings, params["ref"], "DIRECT_SONAR")
    if binding is None or binding[5] != "weapons":
        return "unknown_ref"
    contact = binding[2]
    if game.sonar.contacts.get(contact.target_id) is not contact:
        return "stale_ref"
    result = fire(contact, params["depth_m"])
    return _OWN_ATTACK_REASONS.get(result, result)


def _weapons_fire_asroc(game, params, bindings):
    return _weapons_own_attack(game, params, bindings, game.fire_own_asroc_at)


def _weapons_drop_depth_charges(game, params, bindings):
    return _weapons_own_attack(game, params, bindings, game.drop_depth_charges_at)


def _weapons_fire_rbu(game, params, bindings):
    return _weapons_own_attack(game, params, bindings, game.fire_rbu_at)


def _weapons_rbu_defence(game, _params, _bindings):
    result = game.fire_rbu_defence()
    return _OWN_ATTACK_REASONS.get(result, result)


def _opz_launch_essm(game, params, bindings):
    binding = _direct_observation(bindings, params["ref"], "DIRECT_ASM")
    if binding is None or binding[5] != "opz":
        return "unknown_ref"
    return game.launch_essm_at(binding[4])


def _opz_launch_chaff(game, params, bindings):
    binding = _direct_observation(bindings, params["ref"], "DIRECT_ASM")
    if binding is None or binding[5] != "opz":
        return "unknown_ref"
    return game.launch_chaff_at(binding[4])


# Crew results in the boat's own rejection vocabulary.
_UBOOT_REASONS = {"no_torpedoes": "uboot_no_torpedoes", "no_decoys": "uboot_no_decoys",
                  "reloading": "uboot_reloading", "out_of_arc": "uboot_out_of_arc"}


def _uboot_result(result):
    return _UBOOT_REASONS.get(result, result) if type(result) is str else result


def _uboot_set_course(game, boat, params, _bindings):
    result = boat.sub.set_orders(course=params["course"])
    if result is True:
        boat_nav.cancel_on_helm(boat)    # a helm order takes the boat off its route
    return result


def _uboot_torpedo_settings(game, boat, params, _bindings):
    """The weapons officer's seeker settings for the next shots."""
    boat.orders.torpedo_pattern = params["pattern"]
    boat.orders.torpedo_enable_nm = torpedo_dyn.quantized_enable_nm(
        float(params["enable_nm"]))
    return True


def _uboot_route_waypoint(game, boat, params, _bindings):
    return boat_nav.add_waypoint(boat, params["x"], params["y"], float(game.world.size_nm))


def _uboot_route_pattern(game, boat, params, _bindings):
    return boat_nav.start_pattern(boat, params["pattern"], float(game.world.size_nm))


def _uboot_route_clear(game, boat, params, _bindings):
    return boat_nav.clear(boat)


def _uboot_clear_baffles(game, boat, params, _bindings):
    return opfor.clear_baffles(game, boat)


def _uboot_set_speed(game, boat, params, _bindings):
    return boat.sub.set_orders(speed=params["speed_kn"])


def _uboot_set_depth(game, boat, params, _bindings):
    return boat.sub.set_orders(depth=params["depth_m"])


def _uboot_fire(game, boat, params, bindings):
    """Shoot down a contact's measured bearing (with its fix/TMA solution when
    one is current) or down a free crew bearing; never at a hidden target."""
    sub = boat.sub
    bearing, range_nm = params["bearing"], params["range_nm"]
    course = speed = None
    if params["ref"] is not None:
        contact = _sonar_contact(bindings, params["ref"])
        if contact is None or boat.station.sonar.contacts.get(
                contact.target_id) is not contact:
            return "unknown_ref"
        if not 0 <= game.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
            return "stale_ref"
        solution = attack_computer.solution_for_target(boat, contact.target_id, game.sim_t)
        if solution is not None:
            # The periscope's attack computer has a course and speed on it.
            aim = attack_computer.shot(boat, solution)
            if aim is not None:
                return _uboot_result(sub.command_fire(
                    aim[0], aim[1], now=game.sim_t, depth_m=params["depth_m"],
                    salvo=params["salvo"]))
        bearing = (contact.passive_bearing if contact.passive_bearing is not None
                   else contact.bearing)
        positioned = (contact.observed_x is not None and contact.observed_y is not None
                      and contact.range_source in ("ping", "tma", "visual")
                      and 0 <= game.sim_t - contact.range_seen
                      < config.SONAR_CONTACT_LOST_S)
        if positioned:
            dx, dy = contact.observed_x - sub.x, contact.observed_y - sub.y
            bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
            range_nm = min(40.0, max(0.05, math.hypot(dx, dy)))
            if (contact.range_source == "tma" and contact.tma_course is not None
                    and contact.tma_speed is not None
                    and contact.tma_quality >= config.TMA_RANGE_MIN_QUALITY):
                course = contact.tma_course % 360.0
                speed = min(60.0, max(0.0, contact.tma_speed))
        if _number(bearing) is None:
            return "stale_ref"
        bearing %= 360.0
    return _uboot_result(sub.command_fire(bearing, range_nm, course, speed,
                                          now=game.sim_t, depth_m=params["depth_m"],
                                          salvo=params["salvo"]))


def _uboot_decoy(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_decoy())


def _uboot_tube_load(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_load_tube(params["tube"]))


def _uboot_tube_flood(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_flood_tube(params["tube"]))


def _uboot_tube_flood_quiet(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_flood_tube(params["tube"], quiet=True))


def _uboot_evade(game, boat, params, _bindings):
    from src.core import boat_threat
    return _uboot_result(boat_threat.evade(game, boat))


def _uboot_blow(game, boat, params, _bindings):
    return boat.sub.command_blow()


def _uboot_snorkel(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_snorkel(params["enabled"]))


def _uboot_charge_rate(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_charge_rate(params["rate"]))


def _uboot_absorber(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_absorber())


def _uboot_o2_candle(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_o2_candle())


def _uboot_trim_auto(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_trim_auto(params["enabled"]))


def _uboot_ballast(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_ballast(params["tank"], params["direction"]))


def _uboot_dc_team(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_dc_team(params["team"], params["compartment"],
                                                  params["task"]))


def _uboot_bulkhead(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_bulkhead(params["compartment"], params["closed"]))


def _uboot_action_stations(game, boat, params, _bindings):
    return game.boat_set_action_stations(params["enabled"])


def _uboot_watch_change(game, boat, params, _bindings):
    return game.boat_change_watch()


def _uboot_casualty_medic(game, boat, _params, _bindings):
    return _casualty_result(game.boat_casualty_medic())


def _uboot_casualty_reassign(game, boat, _params, _bindings):
    return _casualty_result(game.boat_casualty_reassign())


def _uboot_mast(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_mast(params["enabled"]))


def _uboot_radio_send(game, boat, params, _bindings):
    return boat.radio.send_sitrep(game, boat)


def _uboot_buoy(game, boat, params, _bindings):
    return buoy_antenna.order(boat.orders.buoy, params["enabled"])


def _uboot_silent(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_silent(params["enabled"]))


def _uboot_bottom(game, boat, params, _bindings):
    return _uboot_result(boat.sub.command_bottom(params["enabled"]))


def _uboot_scope_bearing(game, boat, params, _bindings):
    if not boat.sub._crew_ready():
        return "not_ready"
    opfor.set_scope_relative(boat, params["relative_deg"])
    return True


def _uboot_scope_mark(game, boat, params, _bindings):
    if not boat.sub._crew_ready():
        return "not_ready"
    return _uboot_result(opfor.stadimeter(game, boat))


def _uboot_scope_fire(game, boat, params, _bindings):
    """Fire on the attack computer's solution of the crosshair sighting."""
    if not boat.sub._crew_ready():
        return "not_ready"
    return _uboot_result(attack_computer.fire_on_crosshair(game, boat))


def _uboot_lookout_call(game, boat, params, _bindings):
    """The phone on the periscope calls a sighting."""
    if not boat.sub._crew_ready():
        return "not_ready"
    return phone_lookout.boat_call(game, boat, params["category"], params["bearing"],
                                   params["range_nm"])


def _lookout_call(game, params, _bindings):
    """The frigate's phone lookout calls a sighting."""
    return phone_lookout.call(game, params["category"], params["bearing"],
                              params["range_nm"])


def _uboot_esm_classify(game, boat, params, _bindings):
    if not boat.sub._crew_ready():
        return "not_ready"
    return boat.esm.classify(game, params["emitter"], params["candidate"])


def _uboot_esm_plot(game, boat, params, _bindings):
    if not boat.sub._crew_ready():
        return "not_ready"
    return boat.esm.to_plot(game, boat, params["emitter"])


_UBOOT_ACTION_HANDLERS = {
    "acknowledge": lambda game, boat, params, _bindings: params == {},
    "uboot_set_course": _uboot_set_course,
    "uboot_torpedo_settings": _uboot_torpedo_settings,
    "uboot_route_waypoint": _uboot_route_waypoint,
    "uboot_route_pattern": _uboot_route_pattern,
    "uboot_route_clear": _uboot_route_clear,
    "uboot_clear_baffles": _uboot_clear_baffles,
    "uboot_set_speed": _uboot_set_speed,
    "uboot_set_depth": _uboot_set_depth,
    "uboot_fire": _uboot_fire,
    "uboot_decoy": _uboot_decoy,
    "uboot_tube_load": _uboot_tube_load,
    "uboot_tube_flood": _uboot_tube_flood,
    "uboot_tube_flood_quiet": _uboot_tube_flood_quiet,
    "uboot_blow": _uboot_blow,
    "uboot_snorkel": _uboot_snorkel,
    "uboot_charge_rate": _uboot_charge_rate,
    "uboot_absorber": _uboot_absorber,
    "uboot_trim_auto": _uboot_trim_auto,
    "uboot_ballast": _uboot_ballast,
    "uboot_dc_team": _uboot_dc_team,
    "uboot_bulkhead": _uboot_bulkhead,
    "uboot_action_stations": _uboot_action_stations,
    "uboot_watch_change": _uboot_watch_change,
    "uboot_casualty_medic": _uboot_casualty_medic,
    "uboot_casualty_reassign": _uboot_casualty_reassign,
    "uboot_o2_candle": _uboot_o2_candle,
    "uboot_mast": _uboot_mast,
    "uboot_radio_send": _uboot_radio_send,
    "uboot_buoy": _uboot_buoy,
    "uboot_silent": _uboot_silent,
    "uboot_evade": _uboot_evade,
    "uboot_bottom": _uboot_bottom,
    "uboot_scope_bearing": _uboot_scope_bearing,
    "uboot_scope_mark": _uboot_scope_mark,
    "uboot_scope_fire": _uboot_scope_fire,
    "uboot_esm_classify": _uboot_esm_classify,
    "uboot_esm_plot": _uboot_esm_plot,
    "lookout_call": _uboot_lookout_call,
}


_V2_ACTION_HANDLERS = {
    "acknowledge": _acknowledge,
    "lookout_call": _lookout_call,
    "plot_add": _plot_add,
    "plot_remove": _plot_remove,
    "plot_relabel": _plot_relabel,
    "plot_clear": _plot_clear,
    "bridge_set_course": _bridge_set_course,
    "bridge_set_speed": _bridge_set_speed,
    "bridge_route_add": _bridge_route_add,
    "bridge_route_pattern": _bridge_route_pattern,
    "bridge_route_clear": _bridge_route_clear,
    "bridge_clear_baffles": _bridge_clear_baffles,
    "sonar_classify": _sonar_classify,
    "sonar_set_release": _sonar_set_release,
    "helicopter_qualify": _helicopter_qualify,
    "helicopter_buoy_release": _helicopter_buoy_release,
    "opz_classify": _opz_classify,
    "opz_affiliate": _opz_affiliate,
    "opz_set_track_id": _opz_set_track_id,
    "opz_create_fusion": _opz_create_fusion,
    "opz_dissolve_fusion": _opz_dissolve_fusion,
    "opz_dismiss_suggestion": _opz_dismiss_suggestion,
    "opz_mark_blip": _opz_mark_blip,
    "opz_set_radar": _opz_set_radar,
    "opz_set_ciws": _opz_set_ciws,
    "opz_set_range": _opz_set_range,
    "opz_designate_target": _opz_designate_target,
    "engine_set_telegraph": _engine_set_telegraph,
    "engine_set_course": _engine_set_course,
    "engine_set_speed": _engine_set_speed,
    "engine_set_quiet_mode": _engine_set_quiet_mode,
    "damage_assign_team": _damage_assign_team,
    "damage_counterflood": _damage_counterflood,
    "crew_action_stations": _crew_action_stations,
    "crew_watch_change": _crew_watch_change,
    "crew_casualty_medic": _crew_casualty_medic,
    "crew_casualty_reassign": _crew_casualty_reassign,
    "engine_set_plant": _engine_set_plant,
    "damage_unassign_team": _damage_unassign_team,
    "radio_capture_hfdf": _radio_capture_hfdf,
    "radio_task_accept": _radio_task_accept,
    "radio_request_ras": _radio_request_ras,
    "radio_contact_report": _radio_contact_report,
    "radio_request_support": _radio_request_support,
    "radio_task_decline": _radio_task_decline,
    "eloka_annotate": _eloka_annotate,
    "eloka_clear_annotation": _eloka_clear_annotation,
    "eloka_set_jamming": _eloka_set_jamming,
    "eloka_set_technique": _eloka_set_technique,
    "eloka_set_auto": _eloka_set_auto,
    "sonar_set_listen_bearing": _sonar_set_listen_bearing,
    "sonar_set_focus": _sonar_set_focus,
    "sonar_clear_focus": _sonar_clear_focus,
    "sonar_set_array_mode": _sonar_set_array_mode,
    "sonar_set_tas": _sonar_set_tas,
    "sonar_set_tow_depth": _sonar_set_tow_depth,
    "sonar_set_vds": _sonar_set_vds,
    "sonar_set_vds_depth": _sonar_set_vds_depth,
    "sonar_measure_bt": _sonar_measure_bt,
    "sonar_active_ping": _sonar_active_ping,
    "sonar_set_tma_enabled": _sonar_set_tma_enabled,
    "sonar_set_gain": _sonar_set_gain,
    "sonar_set_audition_mode": _sonar_set_audition_mode,
    "sonar_set_band_preset": _sonar_set_band_preset,
    "sonar_set_notch": _sonar_set_notch,
    "sonar_set_peak_hold": _sonar_set_peak_hold,
    "sonar_set_harmonic": _sonar_set_harmonic,
    "sonar_set_cursor": _sonar_set_cursor,
    "sonar_tma_set": _sonar_tma_set,
    "sonar_assign_profile": _sonar_assign_profile,
    "sonar_set_demon_band": _sonar_set_demon_band,
    "sonar_tas_side": _sonar_tas_side,
    "sonar_set_heterodyne": _sonar_set_heterodyne,
    "sonar_tma_accept": _sonar_tma_accept,
    "sonar_tma_copy_proposal": _sonar_tma_copy_proposal,
    "sonar_mark_line": _sonar_mark_line,
    "sonar_set_integration": _sonar_set_integration,
    "sonar_set_vernier": _sonar_set_vernier,
    "sonar_set_band": _sonar_set_band,
    "sonar_set_operator_notch": _sonar_set_operator_notch,
    "sonar_designate_target": _sonar_designate_target,
    "helicopter_launch": _helicopter_launch,
    "helicopter_return": _helicopter_return,
    "helicopter_set_waypoint": _helicopter_set_waypoint,
    "helicopter_deploy_buoy": _helicopter_deploy_buoy,
    "helicopter_set_pattern": _helicopter_set_pattern,
    "helicopter_set_mad": _helicopter_set_mad,
    "helicopter_set_radar": _helicopter_set_radar,
    "helicopter_set_buoy_mode": _helicopter_set_buoy_mode,
    "helicopter_set_listen_source": _helicopter_set_listen_source,
    "helicopter_set_listen_bearing": _helicopter_set_listen_bearing,
    "helicopter_clear_listen_bearing": _helicopter_clear_listen_bearing,
    "helicopter_set_audio_mode": _helicopter_set_audio_mode,
    "helicopter_set_audio_band": _helicopter_set_audio_band,
    "helicopter_set_audio_gain": _helicopter_set_audio_gain,
    "helicopter_set_audio_notch": _helicopter_set_audio_notch,
    "helicopter_set_dipping": _helicopter_set_dipping,
    "helicopter_set_dip_depth": _helicopter_set_dip_depth,
    "helicopter_dipping_ping": _helicopter_dipping_ping,
    "weapons_launch_torpedo": _weapons_launch_torpedo,
    "helicopter_launch_torpedo": _helicopter_launch_torpedo,
    "weapons_deploy_nixie": _weapons_deploy_nixie,
    "weapons_fire_asroc": _weapons_fire_asroc,
    "weapons_drop_depth_charges": _weapons_drop_depth_charges,
    "weapons_fire_rbu": _weapons_fire_rbu,
    "weapons_rbu_defence": _weapons_rbu_defence,
    "weapons_set_torpedo_settings": _weapons_set_torpedo_settings,
    "opz_launch_essm": _opz_launch_essm,
    "opz_launch_chaff": _opz_launch_chaff,
    "mpa_request": _mpa_request,
    "mpa_return": _mpa_return,
    "mpa_set_waypoint": _mpa_set_waypoint,
    "mpa_set_pattern": _mpa_set_pattern,
    "mpa_drop_buoy": _mpa_drop_buoy,
    "mpa_set_buoy_mode": _mpa_set_buoy_mode,
    "mpa_set_radar": _mpa_set_radar,
    "mpa_set_mad": _mpa_set_mad,
    "mpa_attack": _mpa_attack,
    "consort_set_mode": _consort_set_mode,
    "consort_set_point": _consort_set_point,
    "consort_set_station": _consort_set_station,
    "consort_set_active": _consort_set_active,
    "consort_set_weapons": _consort_set_weapons,
    "consort_fire": _consort_fire,
}


def _host_save(game, params):
    try:
        game.save_to_slot(params["slot"])
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return "save_failed"
    return True


def _host_load(game, params):
    return True if game.load_from_slot(params["slot"]) else "no_save"


def _host_new_game(game, params):
    if "weather" in params:
        game.start_weather = params["weather"]
    if "time" in params:
        game.start_time = params["time"]
    if "length" in params:
        game.start_length = params["length"]
    return game.start_new_game(params["scenario"], params["world_mode"],
                               params.get("difficulty"), params.get("seed"))


def _host_start_mission(game, params):
    """Start an own mission of the Mission Editor's library (solo host)."""
    from src.core import config
    from src.data.user_content import default_store
    from src.data.validation import ContentValidationError
    try:
        definition = default_store(config.SAVE_DIR).load("mission", params["key"])
    except (OSError, ValueError, ContentValidationError):
        return "no_mission"
    return True if game.start_custom_mission(definition) else "mission_rejected"


def _host_instructor_environment(game, params):
    """Apply a bounded, save-compatible exercise environment change."""
    if params["event"] is not None:
        result = _host_instructor_event(game, {"event": params["event"]})
        if result is not True:
            return result
    game.world.sea_state = params["sea_state"]
    game.world.refresh_weather()
    return True


def _host_instructor_event(game, params):
    """Inject a deterministic exercise cue without exporting target identity."""
    targets = sorted(
        (sub for sub in game.subs
         if sub.side == "hostile" and not sub.sunk and sub.state != "SINKING"),
        key=lambda sub: sub.id)
    if not targets:
        return "no_target"
    event = params["event"]
    if event == "torpedo_transient":
        targets[0].alert_torpedo()
        game._emit_sound("torpedo_launch")
        return True
    fraction = {"targets_quiet": .2, "targets_cruise": .5,
                "targets_flank": 1.0}[event]
    for sub in targets:
        sub.speed = max(0.0, sub.motion.maximum_speed_kn * fraction)
    return True


# Solo-only host surface: a closed table, never a dynamic method lookup. The
# world-replacing actions are listed so the rest of the frame can fail closed.
_HOST_ACTION_HANDLERS = {
    "host_save": _host_save,
    "host_load": _host_load,
    "host_new_game": _host_new_game,
    "host_start_mission": _host_start_mission,
    "host_instructor_environment": _host_instructor_environment,
}
