"""Save validation of a sonar station block (frigate or crewed boat).

``valid_sonar_block`` is the body of ``valid_save_document``'s ``valid_sonar``
check, moved verbatim from ``save_validate.py``; the closure values it read
(the document, its catalog, save time, buoy ids and the number checks) are
passed in explicitly by the thin ``valid_sonar`` wrapper there.
"""

from src.core import config
from src.sonar import equation as sonar_equation
from src.sonar.sonar import FIX_SOURCES, SONAR_ARRAY_MODES, SonarSystem, TowState


def valid_sonar_block(sonar, allowed_ids, *, data, runtime_catalog,
                      default_catalog, save_sim_t, buoy_ids, finite_number,
                      bounded, identity) -> bool:
    if not isinstance(sonar, dict):
        return False
    for key in ("lofar", "lofar_times", "lofar_bearings",
                "broadband", "history_times", "echo_history",
                "pending_pings"):
        if key in sonar and not isinstance(sonar[key], list):
            return False
    for key in ("lofar", "broadband"):
        if any(not isinstance(row, list)
               or any(not finite_number(value) for value in row)
               for row in sonar.get(key, [])):
            return False
    for key in ("lofar_times", "lofar_bearings", "history_times"):
        if any(not finite_number(value) for value in sonar.get(key, [])):
            return False
    if not bounded(sonar.get("bt_cooldown"), 0,
                   config.SONAR_BT_COOLDOWN_S):
        return False
    # Variable-depth sonar (save v23): exact, typed and inside its envelope.
    if (sonar.get("vds_state") not in {state.value for state in TowState}
            or not bounded(sonar.get("vds_payout"), 0.0, 1.0)
            or not bounded(sonar.get("vds_depth_m"), config.SONAR_VDS_DEPTH_MIN_M,
                           config.SONAR_VDS_DEPTH_MAX_M)
            or not bounded(sonar.get("vds_depth_target_m"), config.SONAR_VDS_DEPTH_MIN_M,
                           config.SONAR_VDS_DEPTH_MAX_M)
            or not bounded(sonar.get("vds_settle_s"), 0.0, config.SONAR_VDS_SETTLE_S)
            or type(sonar.get("vds_handling_ok")) is not bool):
        return False
    bt_profile = sonar.get("bt_profile")
    if bt_profile is not None:
        bt_fields = {"t", "x", "y", "thermocline_m", "water_depth_m",
                     "sea_state", "depths_m", "speeds_m_s", "cz_bands_nm"}
        if not isinstance(bt_profile, dict) or set(bt_profile) != bt_fields:
            return False
        water_depth = bt_profile["water_depth_m"]
        thermocline = bt_profile["thermocline_m"]
        depths = bt_profile["depths_m"]
        speeds = bt_profile["speeds_m_s"]
        if (not bounded(bt_profile["t"], 0, save_sim_t)
                or not bounded(bt_profile["x"], -1_000_000, 1_000_000)
                or not bounded(bt_profile["y"], -1_000_000, 1_000_000)
                or not bounded(water_depth, 1, 10_000)
                or not bounded(thermocline, 0, water_depth)
                or not isinstance(bt_profile["sea_state"], int)
                or isinstance(bt_profile["sea_state"], bool)
                or not 0 <= bt_profile["sea_state"] <= 6
                or not isinstance(depths, list) or len(depths) != 21
                or not isinstance(speeds, list) or len(speeds) != 21
                or any(not finite_number(depth) for depth in depths)
                or any(not finite_number(speed) for speed in speeds)
                or not isinstance(bt_profile["cz_bands_nm"], list)
                or len(bt_profile["cz_bands_nm"]) > 4
                or any(not isinstance(band, list) or len(band) != 2
                       or not bounded(band[0], 0.0, 200.0)
                       or not bounded(band[1], 0.0, 200.0)
                       or not band[0] < band[1]
                       for band in bt_profile["cz_bands_nm"])):
            return False
        maximum = min(water_depth, config.SONAR_BT_MAX_DEPTH_M)
        expected_depths = [maximum * index / 20 for index in range(21)]
        if (any(abs(depth - expected) > 1e-9
                for depth, expected in zip(depths, expected_depths))
                or any(not 1400.0 <= speed <= 1600.0 for speed in speeds)):
            return False
    contacts = sonar.get("contacts", {})
    if not isinstance(contacts, dict):
        return False
    contact_ids = [contact.get("contact_id")
                   for contact in contacts.values()
                   if isinstance(contact, dict)]
    next_contact_id = sonar.get("next_id")
    if (not identity(next_contact_id)
            or any(not identity(contact_id) for contact_id in contact_ids)
            or next_contact_id <= max(contact_ids, default=0)):
        return False
    for contact in contacts.values():
        if not isinstance(contact, dict):
            return False
        if (type(contact.get("released_to_opz")) is not bool
                or type(contact.get("dip_released_to_opz", False)) is not bool
                or type(contact.get("helo_qualified", False)) is not bool
                or type(contact.get("buoy_released_to_opz", False)) is not bool
                or ((contact.get("ship_observer_x") is None)
                    != (contact.get("ship_observer_y") is None))
                or (contact.get("ship_observer_x") is not None
                    and (not bounded(contact["ship_observer_x"], -1_000_000, 1_000_000)
                         or not bounded(contact["ship_observer_y"], -1_000_000, 1_000_000)))
                or contact.get("passive_source") not in (
                    "SONAR-BRG", "SONAR-DIP-BRG")
                or not bounded(contact.get("observer_x"), -1_000_000, 1_000_000)
                or not bounded(contact.get("observer_y"), -1_000_000, 1_000_000)):
            return False
        buoy_reports = contact.get("buoy_reports", {})
        report_fields = {"mode", "bearing", "bearing_uncertainty_deg",
                         "quality", "measured_at", "observer_x", "observer_y",
                         "range_nm", "x", "y"}
        if (not isinstance(buoy_reports, dict)
                or len(buoy_reports) > config.BUOY_COUNT
                or any(type(key) is not str or not key.isdecimal()
                       or int(key) not in buoy_ids
                       or not isinstance(row, dict) or set(row) != report_fields
                       or row["mode"] not in ("PASSIVE", "ACTIVE")
                       or not bounded(row["bearing"], 0, 360)
                       or row["bearing"] == 360
                       or not bounded(row["bearing_uncertainty_deg"], 0, 180)
                       or not bounded(row["quality"], 0, 1)
                       or not bounded(row["measured_at"], 0, save_sim_t)
                       or not bounded(row["observer_x"], -1_000_000, 1_000_000)
                       or not bounded(row["observer_y"], -1_000_000, 1_000_000)
                       or (row["mode"] == "PASSIVE" and any(
                           row[field] is not None for field in ("range_nm", "x", "y")))
                       or (row["mode"] == "ACTIVE" and any(
                           not bounded(row[field], -1_000_000, 1_000_000)
                           for field in ("x", "y")))
                       or (row["mode"] == "ACTIVE" and not bounded(
                           row["range_nm"], 0, config.BUOY_RANGE_NM + .25))
                       for key, row in buoy_reports.items())):
            return False
        reports = contact.get("array_observations", {})
        if not isinstance(reports, dict) or not set(reports) <= set(SONAR_ARRAY_MODES):
            return False
        for report in reports.values():
            if (not isinstance(report, dict)
                    or not {"bearing", "quality", "snr", "last_seen"} <= set(report)
                    or not set(report) <= {"bearing", "quality", "snr", "last_seen", "uncertainty_deg"}
                    or not bounded(report["bearing"], 0, 360) or report["bearing"] == 360
                    or not bounded(report["quality"], 0, 1)
                    or not bounded(report["snr"], -200, 200)
                    or not bounded(report["last_seen"], 0, 1e12)
                    or ("uncertainty_deg" in report
                        and not bounded(report["uncertainty_deg"], .05, 180))):
                return False
        tma_seen = contact.get("tma_seen")
        if tma_seen is not None and not bounded(tma_seen, 0, 1e12):
            return False
        published_fixes = contact.get("fixes")
        if (not isinstance(published_fixes, list) or len(published_fixes) > len(FIX_SOURCES)
                or len({fix.get("source") for fix in published_fixes
                        if isinstance(fix, dict)}) != len(published_fixes)):
            return False
        for fix in published_fixes:
            fields = {"source", "measured_at", "fixed_at", "x", "y",
                      "uncertainty_nm", "depth_m", "depth_uncertainty_m",
                      "quality"}
            if (not isinstance(fix, dict) or set(fix) != fields
                    or fix["source"] not in FIX_SOURCES
                    or not bounded(fix["measured_at"], 0, save_sim_t)
                    or not bounded(fix["fixed_at"], fix["measured_at"], save_sim_t)
                    or not bounded(fix["x"], -1_000_000, 1_000_000)
                    or not bounded(fix["y"], -1_000_000, 1_000_000)
                    or not bounded(fix["uncertainty_nm"], 1e-9, 100)
                    or not bounded(fix["quality"], 0, 1)
                    or ((fix["depth_m"] is None)
                        != (fix["depth_uncertainty_m"] is None))
                    or (fix["depth_m"] is not None
                        and (not bounded(fix["depth_m"], 0, 10_000)
                             or not bounded(fix["depth_uncertainty_m"],
                                            1e-9, 10_000)))):
                return False
        fixes = contact.get("buoy_fixes", [])
        if (not isinstance(fixes, list) or len(fixes) > 80
                or any(not isinstance(row, (list, tuple)) or len(row) != 4
                       or not bounded(row[0], 0, 1e12)
                       or any(not bounded(v, -1_000_000, 1_000_000) for v in row[1:3])
                       or not bounded(row[3], 0, 1) for row in fixes)):
            return False
        history = contact.get("raw_bearings", [])
        if (not isinstance(history, list)
                or len(history) > config.BEARING_TRACK_MAX_PTS
                or any(not isinstance(row, (list, tuple)) or len(row) != 3
                       or any(not finite_number(value) for value in row)
                       or not 0.0 <= row[1] < 360.0
                       or not 0.0 <= row[2] <= 180.0
                       for row in history)):
            return False
        uncertainty = contact.get("bearing_uncertainty_deg")
        if (uncertainty is not None
                and (not finite_number(uncertainty)
                     or not 0.0 <= uncertainty <= 180.0)):
            return False
        # v13: the operator's catalog assignment is required (None = none).
        if "player_profile" not in contact:
            return False
        profile = contact["player_profile"]
        if profile is not None and (
                type(profile) is not str or profile not in (
                    runtime_catalog or default_catalog).profile_systems):
            return False
        passive_bearing = contact.get("passive_bearing")
        if (passive_bearing is not None
                and (not finite_number(passive_bearing)
                     or not 0.0 <= passive_bearing < 360.0)):
            return False
        epoch = contact.get("passive_epoch")
        if epoch is not None and (not isinstance(epoch, int)
                                  or isinstance(epoch, bool) or epoch < 0):
            return False
        filter_t = contact.get("bearing_filter_t")
        if (filter_t is not None
                and (not finite_number(filter_t) or filter_t < 0.0)):
            return False
        filter_rate = contact.get("bearing_filter_rate_deg_s", 0.0)
        if (not finite_number(filter_rate)
                or abs(filter_rate) > config.SONAR_BEARING_RATE_MAX_DEG_S):
            return False
        filter_uncertainty = contact.get("bearing_filter_uncertainty_deg")
        if (filter_uncertainty is not None
                and (not finite_number(filter_uncertainty)
                     or not 0.05 <= filter_uncertainty <= 180.0)):
            return False
        if (filter_t is None and filter_rate != 0.0) \
                or (filter_t is not None
                    and (passive_bearing is None
                         or filter_uncertainty is None)):
            return False
        # W2: the helicopter's own independent dip-passive bearing track.
        dip_bearing = contact.get("dip_bearing")
        if (dip_bearing is not None
                and (not finite_number(dip_bearing)
                     or not 0.0 <= dip_bearing < 360.0)):
            return False
        dip_uncertainty = contact.get("dip_bearing_uncertainty_deg")
        if (dip_uncertainty is not None
                and (not finite_number(dip_uncertainty)
                     or not 0.05 <= dip_uncertainty <= 180.0)):
            return False
        dip_last_seen = contact.get("dip_last_seen")
        if dip_last_seen is not None and not bounded(
                dip_last_seen, 0, save_sim_t):
            return False
        if any(contact.get(name) is not None
               and not bounded(contact.get(name), -1_000_000, 1_000_000)
               for name in ("dip_observer_x", "dip_observer_y")):
            return False
        if dip_bearing is not None and (
                dip_uncertainty is None or dip_last_seen is None
                or contact.get("dip_observer_x") is None
                or contact.get("dip_observer_y") is None):
            return False
        ellipse = contact.get("tma_ellipse")
        if ellipse is not None and (
                not isinstance(ellipse, list) or len(ellipse) != 3
                or not bounded(ellipse[0], 0.0, 1e6)
                or not bounded(ellipse[1], 0.0, ellipse[0] + 1e-9)
                or not bounded(ellipse[2], 0.0, 180.0)):
            return False
        if (contact.get("towed_side") not in ("STBD", "PORT")
                or type(contact.get("towed_ambiguous")) is not bool
                or type(contact.get("towed_resolved")) is not bool
                or (contact["towed_ambiguous"] and contact["towed_resolved"])
                or (contact["towed_ambiguous"] and (
                    not bounded(contact.get("ambiguity_axis"), 0.0, 360.0)
                    or not bounded(contact.get("mirror_bearing"), 0.0, 360.0)))
                or (contact.get("tonal_hz") is not None
                    and not bounded(contact["tonal_hz"], 0.1, 20000.0))):
            return False
    echoes = sonar.get("echo_history", [])
    if any(not isinstance(item, dict)
           or not finite_number(item.get("t"))
           or not finite_number(item.get("contact_id"))
           or any(name in item and not finite_number(item[name])
                  for name in ("bearing", "range_nm", "range_sigma_nm",
                               "depth_m", "depth_sigma_m", "snr_db"))
           for item in echoes):
        return False
    tracks = sonar.get("tracks", {})
    if not isinstance(tracks, dict):
        return False
    if any(not isinstance(points, list)
           or len(points) > config.BEARING_TRACK_MAX_PTS
           or any(not isinstance(point, dict)
                   or any(not finite_number(point.get(name))
                          for name in ("t", "bearing", "fx", "fy",
                                       "fcourse"))
                   or ("uncertainty_deg" in point
                       and (not finite_number(point["uncertainty_deg"])
                            or not 0.05 <= point["uncertainty_deg"] <= 180.0))
                   or (point.get("freq_hz") is not None
                       and not bounded(point["freq_hz"], 0.1, 20000.0))
                   or not bounded(point.get("fspeed"), 0.0, 60.0)
                   for point in points)
           for points in tracks.values()):
        return False
    track_versions = sonar.get("track_versions", {})
    tma_versions = sonar.get("tma_versions", {})
    tma_next = sonar.get("tma_next", {})
    if any(not isinstance(values, dict)
           for values in (track_versions, tma_versions, tma_next)):
        return False
    if any(not isinstance(value, int) or isinstance(value, bool)
           or not 0 <= value <= 1_000_000_000
           for values in (track_versions, tma_versions)
           for value in values.values()):
        return False
    if any(not finite_number(value) or value < 0.0
           for value in tma_next.values()):
        return False
    try:
        all_keys = (set(tracks) | set(track_versions)
                    | set(tma_versions) | set(tma_next))
        if any(not isinstance(key, str) or str(int(key)) != key
               for key in all_keys):
            return False
        gate_keys = ({int(key) for key in track_versions}
                     | {int(key) for key in tma_versions}
                     | {int(key) for key in tma_next})
        track_keys = {int(key) for key in tracks}
    except (TypeError, ValueError):
        return False
    if any(key < 0 for key in gate_keys | track_keys) \
            or not gate_keys <= track_keys:
        return False
    if any(track_versions.get(key, len(points)) < len(points)
           for key, points in tracks.items()):
        return False
    if any(value > track_versions.get(key, len(tracks[key]))
           for key, value in tma_versions.items()):
        return False
    sim_t = data.get("sim_t", 0.0)
    if (not finite_number(sim_t) or sim_t < 0.0
            or any(value > sim_t + config.TMA_RESOLVE_EVERY_S
                   for value in tma_next.values())
            or any(contact.get("bearing_filter_t") is not None
                   and contact["bearing_filter_t"] > sim_t
                   for contact in contacts.values())):
        return False
    if sonar.get("ping_pulse") not in sonar_equation.PULSES:
        return False
    clutter = sonar.get("pending_clutter")
    if (not isinstance(clutter, list)
            or len(clutter) > SonarSystem.MAX_PENDING_CLUTTER
            or any(not isinstance(item, dict)
                   or set(item) != {"ready_at", "mode", "snapshot"}
                   or item["mode"] not in SONAR_ARRAY_MODES + ("DIPPING",)
                   or not SonarSystem.valid_ping_snapshot(item["snapshot"])
                   or not bounded(item["ready_at"], 0, 1e12)
                   or not item["snapshot"]["t"] <= sim_t
                   or not 0 <= item["ready_at"] - item["snapshot"]["t"] <= 25000
                   for item in clutter)):
        return False
    pending_pings = sonar.get("pending_pings", [])
    # 25000 s covers two-way propagation across the 10000 NM snapshot bound.
    if len(pending_pings) > SonarSystem.MAX_PENDING_PINGS or any(not isinstance(item, dict)
           or set(item) != {"target_id", "sent_at", "ready_at", "range_factor", "mode", "snapshot"}
           or not identity(item.get("target_id"))
           or item["target_id"] not in allowed_ids
           or any(not bounded(item.get(key, 0), 0, 1e12)
                  for key in ("sent_at", "ready_at"))
           or not bounded(item.get("range_factor", 1), 0, 100)
            or item.get("mode", "BOW") not in SONAR_ARRAY_MODES + ("DIPPING",)
           or item.get("sent_at", sim_t) > sim_t
           or not 0 <= item.get("ready_at", sim_t) - item.get("sent_at", sim_t) <= 25000
           or not SonarSystem.valid_ping_snapshot(item["snapshot"])
           or not item["sent_at"] <= item["snapshot"]["t"] <= sim_t
           for item in pending_pings):
        return False
    return True
