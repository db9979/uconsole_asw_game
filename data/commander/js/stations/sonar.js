import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { enumText, finite, number, stateText, t, unit } from "../core/format.js";
import { metrics, node, sonarEntries, stationRows, yesNo } from "../views/dom.js";

export function renderSonarStation(payload) {
  const settings = payload.settings;
  // The submarine's sonar room: hull array only, no OPZ to release to.
  const submarine = S.session?.station === "uboot_sonar";
  for (const id of ["sonar-array-mode", "sonar-array-apply", "sonar-tas", "sonar-depth-form", "sonar-vds", "sonar-vds-depth-form",
    "sonar-tas-flip", "sonar-tas-confirm"])
    $(id).hidden = submarine;
  $("station-sonar-title").textContent = t(submarine ? "station_uboot_sonar" : "station_sonar");
  const auditionMode = payload.visualization.receiver.listen_mode;
  metrics($("sonar-settings"), [["sonar_mode", stateText("sonar_array", settings.mode)], ["sonar_page", number(settings.page, 0)],
    ["sonar_listen_bearing", unit(settings.listen_bearing, "\u00b0", 0)], ["sonar_focus", settings.focus_ref || t("station_none")],
    ["sonar_target", settings.target_ref || t("station_none")], ["station_down", yesNo(settings.station_down)],
    ["sonar_tow_state", stateText("tow_state", settings.tow.state)], ["sonar_tow_payout", unit(settings.tow.payout * 100, "%", 0)],
    ["sonar_tow_speed_window", `${unit(settings.tow.speed_min_kn, "kn", 0)} - ${unit(settings.tow.speed_max_kn, "kn", 0)}`],
    ["sonar_tow_depth", unit(settings.tow.depth_m, "m", 0)],
    ["sonar_vds_state", stateText("tow_state", settings.vds.state)], ["sonar_vds_payout", unit(settings.vds.payout * 100, "%", 0)],
    ["sonar_vds_depth", unit(settings.vds.depth_m, "m", 0)],
    ["sonar_bt_ready", yesNo(settings.bt.ready)], ["sonar_ping_ready", yesNo(settings.ping.ready)],
    ["sonar_tma", yesNo(settings.tma_enabled)], ["sonar_audition_mode", enumText({BROADBAND: "sonar_audition_broadband", FILTERED: "sonar_audition_filtered", HETERODYNE: "sonar_audition_heterodyne"}, auditionMode)], ["sonar_gain", unit(settings.gain_db, "dB")],
    ["sonar_band", settings.band_preset || settings.band_hz.map((value) => number(value, 0)).join("-")],
    ["sonar_notch", yesNo(settings.notch)], ["sonar_peak_hold", yesNo(settings.peak_hold)],
    ["sonar_harmonic", unit(settings.harmonic_hz, "Hz")], ["sonar_audio", yesNo(settings.audio_enabled)],
    ["sonar_volume", number(settings.volume, 2)], ["quiet_mode", yesNo(settings.quiet_mode)],
    ["sonar_integration", `${settings.tools.integration_s} s`], ["sonar_vernier", yesNo(settings.tools.vernier)],
    ["sonar_operator_notch", unit(settings.tools.operator_notch_hz, "Hz")],
    ["sonar_demon_marks", t("sonar_demon_marks_value", {shaft: finite(settings.tools.shaft_hz) ? number(settings.tools.shaft_hz, 1) : "--",
      blade: finite(settings.tools.blade_hz) ? number(settings.tools.blade_hz, 1) : "--",
      blades: finite(settings.tools.shaft_hz) && finite(settings.tools.blade_hz) && settings.tools.shaft_hz > 0
        ? number(Math.round(settings.tools.blade_hz / settings.tools.shaft_hz), 0) : "--",
      rpm: finite(settings.tools.shaft_hz) ? number(settings.tools.shaft_hz * 60, 0) : "--"})],
    ["sonar_assist", yesNo(settings.tools.assist)]]);
  if (!S.stationDrafts.has("sonar-integration")) $("sonar-integration").value = String(settings.tools.integration_s);
  if (!S.stationDrafts.has("sonar-demon-band")) $("sonar-demon-band").value = settings.tools.demon_band_hz.map((value) => number(value, 0).replace(/\D/g, "")).join("-");
  if (!S.stationDrafts.has("sonar-heterodyne")) $("sonar-heterodyne").value = String(Math.round(settings.tools.heterodyne_hz));
  $("sonar-vernier").checked = settings.tools.vernier;
  const live = !settings.station_down;
  if (!S.stationDrafts.has("sonar-array-mode")) $("sonar-array-mode").value = settings.mode;
  const tasDeployed = ["DEPLOYING", "STREAMED"].includes(settings.tow.state);
  $("sonar-tas").textContent = t(tasDeployed ? "sonar_tas_retrieve" : "sonar_tas_deploy");
  $("sonar-tas").dataset.deployed = String(tasDeployed);
  const vdsDeployed = ["DEPLOYING", "STREAMED"].includes(settings.vds.state);
  $("sonar-vds").textContent = t(vdsDeployed ? "sonar_vds_retrieve" : "sonar_vds_deploy");
  $("sonar-vds").dataset.deployed = String(vdsDeployed);
  $("sonar-tma").checked = settings.tma_enabled;
  $("sonar-notch").checked = settings.notch;
  $("sonar-listen-notch").checked = settings.notch;
  $("sonar-peak").checked = settings.peak_hold;
  if (!S.stationDrafts.has("sonar-audition-mode")) $("sonar-audition-mode").value = auditionMode;
  if (settings.band_preset && !S.stationDrafts.has("sonar-band")) $("sonar-band").value = settings.band_preset;
  if (settings.band_preset && !S.stationDrafts.has("sonar-listen-band")) $("sonar-listen-band").value = settings.band_preset;
  $("sonar-harmonic-candidates").replaceChildren(...settings.harmonic_candidates_hz.map((value) => {
    const option = node("option"); option.value = String(value); return option;
  }));
  $("sonar-ping").dataset.ready = String(live && settings.ping.ready &&
    (settings.mode !== "TOWED" || settings.tow.available) && (settings.mode !== "VDS" || settings.vds.available));
  $("sonar-bt").dataset.ready = String(live && settings.bt.ready);
  $("sonar-tas").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state !== "FAULT");
  $("sonar-depth-submit").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
  $("sonar-depth").dataset.ready = String(live && settings.tow.handling_ok && settings.tow.state === "STREAMED");
  $("sonar-vds").dataset.ready = String(live && settings.vds.handling_ok && settings.vds.state !== "FAULT");
  $("sonar-vds-depth-submit").dataset.ready = String(live && settings.vds.state === "STREAMED");
  $("sonar-vds-depth").dataset.ready = String(live && settings.vds.state === "STREAMED");
  stationRows($("sonar-observations"), payload.observations, (row) => submarine ? sonarEntries(row) : [...sonarEntries(row),
    ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]]);
}
