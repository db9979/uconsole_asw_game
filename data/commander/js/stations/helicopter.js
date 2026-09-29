import { S } from "../state/store.js";
import { stopSonarAudio } from "../audio/audio.js";
import { $, heloStates } from "../core/base.js";
import { enumText, finite, number, t, unit } from "../core/format.js";
import { fillFireTargets, metrics, node, position, stationRows, yesNo } from "../views/dom.js";

export function renderHelicopterStation(payload) {
  const asset = payload.asset;
  if (S.helicopterAudioSource !== null && S.helicopterAudioSource !== payload.acoustic.source && S.sonarAudioEnabled)
    stopSonarAudio("sonar_live_waiting");
  S.helicopterAudioSource = payload.acoustic.source;
  if (!S.stationDrafts.has("helicopter-buoy-mode")) $("helicopter-buoy-mode").value = asset.buoy_mode;
  const listen = $("helicopter-listen-source");
  if (listen.options.length !== payload.acoustic.sources.length ||
      payload.acoustic.sources.some((source, index) => listen.options[index]?.value !== source)) {
    listen.replaceChildren(...payload.acoustic.sources.map((source) => {
      const option = node("option", source === "DIP" ? t("helicopter_dip_picture") : source);
      option.value = source;
      return option;
    }));
  }
  listen.value = payload.acoustic.source;
  if (document.activeElement !== $("helicopter-listen-bearing"))
    $("helicopter-listen-bearing").value = payload.acoustic.listen_bearing ?? "";
  $("helicopter-audition-mode").value = payload.acoustic.audition_mode;
  $("helicopter-audio-band").value = payload.acoustic.band_preset;
  $("helicopter-audio-notch").checked = payload.acoustic.notch;
  if (document.activeElement !== $("helicopter-audio-gain"))
    $("helicopter-audio-gain").value = payload.acoustic.gain_db;
  $("helicopter-audio-gain-value").value = `${number(payload.acoustic.gain_db, 0)} dB`;
  $("helicopter-acoustic-text").textContent = t("helicopter_acoustic_equivalent", {
    rows: payload.acoustic.history.length, bearings: payload.acoustic.broadband.length,
    bins: payload.acoustic.demon.length});
  metrics($("helicopter-asset"), [["state", enumText(heloStates, asset.state)], ["airborne", yesNo(asset.airborne)],
    ["position", position(asset)], ["course", unit(asset.course, "\u00b0", 0)], ["fuel", unit(asset.fuel_s, "s", 0)],
    ["torpedoes", number(asset.torpedoes, 0)], ["buoys", number(asset.buoys, 0)],
    ["helicopter_hovering", yesNo(asset.hovering)], ["helicopter_dip_state", asset.dip_state],
    ["helicopter_dip_depth", unit(asset.dip_depth_m, "m", 0)],
    ["helicopter_dip_water", unit(asset.dip_water_depth_m, "m", 0)],
    ["helicopter_dip_cooldown", unit(asset.dip_ping_cooldown_s, "s", 0)],
    ["helicopter_pattern", t(`buoy_pattern_${asset.pattern}`)],
    ["helicopter_pattern_remaining", number(asset.pattern_remaining, 0)],
    ["helicopter_mad", yesNo(asset.mad_mode)], ["helicopter_radar", yesNo(asset.radar)]]);
  if (!S.stationDrafts.has("helicopter-pattern")) $("helicopter-pattern").value = asset.pattern;
  $("helicopter-mad").textContent = t(asset.mad_mode ? "helicopter_mad_stop" : "helicopter_mad_start");
  $("helicopter-mad").setAttribute("aria-pressed", String(asset.mad_mode));
  $("helicopter-radar").textContent = t(asset.radar_switch ? "helicopter_radar_off" : "helicopter_radar_on");
  $("helicopter-radar").setAttribute("aria-pressed", String(asset.radar_switch));
  metrics($("helicopter-waypoint"), [["position", payload.waypoint ? position(payload.waypoint) : t("station_none")]]);
  const environment = payload.dip_environment;
  metrics($("helicopter-dip-environment"), [
    ["helicopter_dip_water", unit(environment.water_depth_m, "m", 0)],
    ["helicopter_dip_thermocline", unit(environment.thermocline_m, "m", 0)],
    ["helicopter_dip_limit", unit(environment.depth_limit_m, "m", 0)],
    ["helicopter_dip_clearance", unit(environment.bottom_clearance_m, "m", 0)],
    ["helicopter_dip_winch_rate", unit(environment.winch_rate_m_s, "m/s", 1)],
    ["helicopter_dip_below_layer", environment.below_thermocline === null ? t("station_none") : yesNo(environment.below_thermocline)]]);
  const ready = payload.readiness;
  metrics($("helicopter-readiness"), [["flightdeck_down", yesNo(ready.flightdeck_down)],
    ["helicopter_can_launch", yesNo(ready.can_launch)], ["helicopter_can_return", yesNo(ready.can_return)],
    ["deck_state", ready.deck_state], ["helicopter_can_waypoint", yesNo(ready.can_set_waypoint)],
    ["helicopter_can_buoy", yesNo(ready.can_deploy_buoy)],
    ["helicopter_can_pattern", yesNo(ready.can_pattern)], ["helicopter_can_mad", yesNo(ready.can_mad)],
    ["helicopter_can_dipping", yesNo(ready.can_set_dipping)],
    ["helicopter_can_dip_ping", yesNo(ready.can_dipping_ping)],
    ["helicopter_weather_launch", yesNo(ready.weather_launch_safe)],
    ["helicopter_weather_dipping", yesNo(ready.weather_dipping_safe)],
    ["helicopter_crosswind", unit(ready.crosswind_kn, "kn")],
    ["rtb_margin", unit(ready.rtb_margin_s, "s", 0)]]);
  $("helicopter-launch").dataset.ready = String(ready.can_launch);
  $("helicopter-return").dataset.ready = String(ready.can_return);
  $("helicopter-waypoint-submit").dataset.ready = String(ready.can_set_waypoint);
  $("helicopter-x").dataset.ready = String(ready.can_set_waypoint);
  $("helicopter-y").dataset.ready = String(ready.can_set_waypoint);
  $("helicopter-buoy").dataset.ready = String(ready.can_deploy_buoy);
  $("helicopter-pattern-apply").dataset.ready = String(ready.can_pattern);
  $("helicopter-mad").dataset.ready = String(ready.can_mad || asset.mad_mode);
  const dipping = asset.dip_state !== "STOWED";
  $("helicopter-dip-toggle").textContent = t(dipping ? "helicopter_dip_retrieve" : "helicopter_dip_deploy");
  $("helicopter-dip-toggle").dataset.deployed = String(dipping);
  $("helicopter-dip-toggle").dataset.ready = String(ready.can_set_dipping);
  $("helicopter-dip-ping").dataset.ready = String(ready.can_dipping_ping);
  $("helicopter-dip-depth").dataset.ready = String(ready.can_set_dip_depth);
  $("helicopter-dip-depth-submit").dataset.ready = String(ready.can_set_dip_depth);
  if (!S.stationDrafts.has("helicopter-dip-depth")) {
    $("helicopter-dip-depth").value = String(asset.dip_depth_target_m);
  }
  fillFireTargets("helicopter-fire-target", payload.target_choices);
  if (!S.stationDrafts.has("helicopter-fire-depth")) $("helicopter-fire-depth").value = "80";
  stationRows($("helicopter-buoys"), payload.buoys, (row) => [["reference", row.label], ["position", position(row)],
    ["battery", unit(row.battery_s, "s", 0)], ["active", yesNo(row.active)],
    ["helicopter_buoy_mode", t(row.mode === "ACTIVE" ? "helicopter_buoy_active" : "helicopter_buoy_passive")]]);
  stationRows($("helicopter-buoy-observations"), payload.buoy_observations, (row) => [
    ["reference", `${row.buoy_label} / ${row.label}`],
    ["helicopter_buoy_mode", t(row.mode === "ACTIVE" ? "helicopter_buoy_active" : "helicopter_buoy_passive")],
    ["bearing", unit(row.bearing, "°", 1)],
    ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "°", 1)],
    ["range", unit(row.range_nm, "NM", 1)], ["age", unit(row.age_s, "s", 0)],
    ["helicopter_qualified", yesNo(row.qualified)],
    ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]],
    "helicopter_dip_empty");
  stationRows($("helicopter-dip-observations"), payload.dip_observations, (row) => [
    ["reference", row.label], ["helicopter_dip_passive_bearing", unit(row.bearing, "°", 1)],
    ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "°", 1)],
    ["age", unit(row.age_s, "s", 0)],
    ["helicopter_dip_active_range", unit(row.range_nm, "NM", 1)],
    ["range_uncertainty", unit(row.range_uncertainty_nm, "NM", 2)],
    ["depth", unit(row.depth_m, "m", 0)],
    ["helicopter_dip_depth_uncertainty", unit(row.depth_uncertainty_m, "m", 0)],
    ["fix_age", unit(row.fix_age_s, "s", 0)],
    ["opz_release_status", t(row.released_to_opz ? "opz_release_active" : "opz_release_private")]],
    "helicopter_dip_empty");
  drawHelicopterDip(payload.dip_observations);
}
function drawHelicopterDip(rows) {
  const canvas = $("helicopter-dip-canvas"), ctx = canvas.getContext("2d");
  if (!ctx) return;
  const {width: w, height: h} = canvas;
  ctx.fillStyle = "#091b1a"; ctx.fillRect(0, 0, w, h);
  const cx = w / 2, cy = h / 2, radius = Math.min(w, h) * .43;
  ctx.strokeStyle = "#42645e"; ctx.lineWidth = 1;
  for (const scale of [.5, 1]) { ctx.beginPath(); ctx.arc(cx, cy, radius * scale, 0, Math.PI * 2); ctx.stroke(); }
  for (const angle of [0, 90, 180, 270]) {
    const a = angle * Math.PI / 180;
    ctx.beginPath(); ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.sin(a) * radius, cy - Math.cos(a) * radius); ctx.stroke();
  }
  for (const row of rows) {
    if (finite(row.bearing)) {
      const a = row.bearing * Math.PI / 180;
      if (finite(row.bearing_uncertainty_deg)) {
        ctx.strokeStyle = "#4e8f7d"; ctx.lineWidth = 1;
        for (const edge of [-1, 1]) {
          const b = (row.bearing + edge * row.bearing_uncertainty_deg) * Math.PI / 180;
          ctx.beginPath(); ctx.moveTo(cx, cy);
          ctx.lineTo(cx + Math.sin(b) * radius, cy - Math.cos(b) * radius); ctx.stroke();
        }
      }
      ctx.strokeStyle = "#79d8a7"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.sin(a) * radius, cy - Math.cos(a) * radius); ctx.stroke();
    }
    if (finite(row.active_bearing) && finite(row.range_nm)) {
      const a = row.active_bearing * Math.PI / 180;
      const dx = Math.sin(a), dy = -Math.cos(a);
      const r = Math.min(radius, radius * row.range_nm / 20);
      if (finite(row.range_uncertainty_nm)) {
        ctx.strokeStyle = "#ffcc70"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(cx + dx * r, cy + dy * r,
          Math.max(3, Math.min(radius, radius * row.range_uncertainty_nm / 20)), 0, Math.PI * 2); ctx.stroke();
      }
      ctx.fillStyle = "#ffcc70"; ctx.beginPath(); ctx.arc(cx + dx * r, cy + dy * r, 5, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.fillStyle = "#a8c3bc"; ctx.font = "14px sans-serif";
  ctx.fillText(t("helicopter_dip_scale"), 12, h - 12);
}
