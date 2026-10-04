import { S } from "../state/store.js";
import { stopSonarAudio } from "../audio/audio.js";
import { $, heloStates } from "../core/base.js";
import { finite, heloStateText, number, t, unit } from "../core/format.js";
import { fillFireTargets, metrics, position, setControlValue, setOptions, stationRows, yesNo } from "../views/dom.js";
import { palette, paletteAlpha } from "../core/palette.js";
import { lampTip, noteLamp, renderLamps } from "../views/console-kit.js";
import { visualContext } from "../views/visual-common.js";

// The flight deck's motion (src/ui/stations/helicopter.py _draw_deck_gauge):
// the stern seen from aft rolling against the horizon, the pitch bar with its
// limits and the quiet-period bar that fills while the deck stays inside.
function drawDeckMotion(deck) {
  const canvas = $("helicopter-deck-canvas"), g = canvas.getContext("2d"), p = palette();
  const w = canvas.width, h = canvas.height, cx = (w - 30) / 2, cy = h * .45, half = Math.min(w - 30, h * 2) * .3;
  const inside = Math.abs(deck.roll_deg) <= deck.roll_limit_deg && Math.abs(deck.pitch_deg) <= deck.pitch_limit_deg;
  const color = deck.window_open ? p.accent : inside ? p.amber : p.red;
  g.fillStyle = p.scopeBg; g.fillRect(0, 0, w, h);
  g.fillStyle = p.panel; g.fillRect(0, cy, w - 30, h - 24 - cy);
  g.strokeStyle = p.line; g.lineWidth = 1; g.beginPath(); g.moveTo(0, cy); g.lineTo(w - 30, cy); g.stroke();
  const roll = deck.roll_deg * Math.PI / 180, ux = Math.cos(roll), uy = Math.sin(roll);
  const turned = (shape) => shape.map(([px, py]) => [cx + px * ux - py * uy, cy + px * uy + py * ux]);
  const poly = (points, fill) => { g.fillStyle = fill; g.beginPath(); points.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.closePath(); g.fill(); };
  const hull = turned([[-half, 0], [half, 0], [half * .8, half * .45], [-half * .8, half * .45]]);
  poly(hull, p.muted); poly(turned([[-half * .55, 0], [half * .55, 0], [half * .5, -half * .5], [-half * .5, -half * .5]]), p.muted);
  g.strokeStyle = color; g.lineWidth = 3; g.beginPath(); g.moveTo(...hull[0]); g.lineTo(...hull[1]); g.stroke();
  const barX = w - 20, barTop = 6, barH = h - 36, scale = barH / 2 / (deck.pitch_limit_deg * 2);
  g.lineWidth = 1; g.strokeStyle = p.line; g.strokeRect(barX, barTop, 8, barH);
  for (const limit of [-deck.pitch_limit_deg, deck.pitch_limit_deg]) {
    const y = barTop + barH / 2 - limit * scale; g.strokeStyle = p.text; g.beginPath(); g.moveTo(barX - 3, y); g.lineTo(barX + 11, y); g.stroke();
  }
  const pitch = Math.max(-2 * deck.pitch_limit_deg, Math.min(2 * deck.pitch_limit_deg, deck.pitch_deg));
  g.fillStyle = color; g.fillRect(barX + 1, barTop + barH / 2 - pitch * scale - 2, 6, 4);
  const fill = Math.min(1, deck.quiet_s / Math.max(deck.window_s, .1));
  g.strokeStyle = p.line; g.strokeRect(4, h - 16, w - 8, 10); g.fillStyle = color; g.fillRect(5, h - 15, (w - 10) * fill, 8);
  $("helicopter-deck-text").textContent = `${t("helo_deck_values", {roll: number(Math.abs(deck.roll_deg), 1), pitch: number(Math.abs(deck.pitch_deg), 1)})} \u00b7 ${t(deck.window_open ? "helo_deck_open" : "helo_deck_wait")}`;
}

// The dipping sonar's annunciator lamps: dome, ping, weather and hover.
function renderHelicopterLamps(asset, ready) {
  const lamp = (key, ...rest) => [key, ...rest];
  const dome = {DEPLOYED: "on", DEPLOYING: "caution", RETRIEVING: "caution"}[asset.dip_state] || "off";
  renderLamps($("helicopter-lamps"), [
    lamp("dome", t("helicopter_lamp_dome"), dome, unit(asset.dip_depth_m, "m", 0), "helicopter-dip-toggle", lampTip("dome")),
    lamp("ping", t("sonar_lamp_ping"), ready.can_dipping_ping ? "on" : dome === "on" ? "caution" : "off",
      ready.can_dipping_ping ? t("sonar_lamp_ready") : t("sonar_lamp_cooldown", {seconds: number(asset.dip_ping_cooldown_s, 0)}),
      "helicopter-dip-ping", lampTip("ping")),
    lamp("weather", t("helicopter_lamp_weather"), ready.weather_dipping_safe ? "on" : "alarm",
      t(ready.weather_dipping_safe ? "sonar_lamp_ok" : "helicopter_lamp_unsafe"), undefined, lampTip("dip")),
    lamp("hover", t("helicopter_lamp_hover"), asset.hovering ? "on" : "off", t(asset.hovering ? "sonar_lamp_on" : "sonar_lamp_off"),
      undefined, lampTip("state_dipping")),
  ]);
}

// Launch, deck window, dipping weather and radar as on the uConsole's
// Einsatzmittel panel: drawn from the host's notes, each with its reason.
function renderHelicopterStatusLamps() {
  renderLamps($("helicopter-status-lamps"), [
    noteLamp("launch", "launch", "helicopter-launch"), noteLamp("deck", "deck"),
    noteLamp("dip", "dip"), noteLamp("radar", "radar", "helicopter-radar"),
  ].filter(Boolean));
}

// North-up scope of the dipping sonar: range rings (outer 20 NM), 10 degree
// ticks, passive bearings with their uncertainty wedge, active fixes and the
// sonobuoys' bearings in amber.
function drawDipScope(g, w, h, rows, buoys, colors) {
  const cx = w / 2, cy = h / 2 + 4, radius = Math.max(10, Math.min(w, h) / 2 - 16);
  const at = (r, deg) => [cx + r * Math.sin(deg * Math.PI / 180), cy - r * Math.cos(deg * Math.PI / 180)];
  g.fillStyle = colors.bg; g.beginPath(); g.arc(cx, cy, radius, 0, Math.PI * 2); g.fill();
  g.lineWidth = 1; g.strokeStyle = colors.line;
  for (const scale of [.25, .5, .75, 1]) { g.beginPath(); g.arc(cx, cy, radius * scale, 0, Math.PI * 2); g.stroke(); }
  for (let step = 0; step < 360; step += 10) {
    const major = step % 30 === 0;
    g.strokeStyle = major ? colors.muted : colors.line;
    g.beginPath(); g.moveTo(...at(radius - (major ? 7 : 3), step)); g.lineTo(...at(radius, step)); g.stroke();
  }
  g.fillStyle = colors.muted; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("N", ...at(radius + 9, 0));
  for (const row of rows) {
    if (!finite(row.bearing)) continue;
    if (finite(row.bearing_uncertainty_deg)) {
      const spread = Math.max(1, row.bearing_uncertainty_deg);
      const a = (row.bearing - spread - 90) * Math.PI / 180, b = (row.bearing + spread - 90) * Math.PI / 180;
      g.save(); g.globalAlpha = .28; g.fillStyle = colors.accent;
      g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, radius, a, b); g.closePath(); g.fill(); g.restore();
    }
    g.strokeStyle = row.ref === S.selected ? colors.text : colors.accent; g.lineWidth = row.ref === S.selected ? 3 : 2;
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(...at(radius, row.bearing)); g.stroke();
  }
  g.lineWidth = 1;
  for (const row of buoys) {
    if (!finite(row.bearing)) continue;
    g.strokeStyle = colors.amber; g.beginPath(); g.moveTo(...at(radius * .6, row.bearing)); g.lineTo(...at(radius, row.bearing)); g.stroke();
  }
  for (const row of rows) {
    if (!finite(row.active_bearing) || !finite(row.range_nm)) continue;
    const [x, y] = at(Math.min(radius, radius * row.range_nm / 20), row.active_bearing);
    if (finite(row.range_uncertainty_nm)) {
      g.strokeStyle = colors.amber;
      g.beginPath(); g.arc(x, y, Math.max(3, Math.min(radius, radius * row.range_uncertainty_nm / 20)), 0, Math.PI * 2); g.stroke();
    }
    g.fillStyle = colors.amber; g.beginPath(); g.arc(x, y, 5, 0, Math.PI * 2); g.fill();
  }
  g.fillStyle = colors.accent; g.beginPath(); g.arc(cx, cy, 3, 0, Math.PI * 2); g.fill();
}

export function renderHelicopterStation(payload) {
  const asset = payload.asset;
  if (S.helicopterAudioSource !== null && S.helicopterAudioSource !== payload.acoustic.source && S.sonarAudioEnabled)
    stopSonarAudio("sonar_live_waiting");
  S.helicopterAudioSource = payload.acoustic.source;
  setControlValue($("helicopter-buoy-mode"), asset.buoy_mode);
  const listen = $("helicopter-listen-source");
  setOptions(listen, payload.acoustic.sources.map((source) => [source, source === "DIP" ? t("helicopter_dip_picture") : source]));
  setControlValue(listen, payload.acoustic.source);
  if (document.activeElement !== $("helicopter-listen-bearing"))
    $("helicopter-listen-bearing").value = payload.acoustic.listen_bearing ?? "";
  setControlValue($("helicopter-audition-mode"), payload.acoustic.audition_mode);
  setControlValue($("helicopter-audio-band"), payload.acoustic.band_preset);
  $("helicopter-audio-notch").checked = payload.acoustic.notch;
  if (document.activeElement !== $("helicopter-audio-gain"))
    $("helicopter-audio-gain").value = payload.acoustic.gain_db;
  $("helicopter-audio-gain-value").value = `${number(payload.acoustic.gain_db, 0)} dB`;
  $("helicopter-acoustic-text").textContent = t("helicopter_acoustic_equivalent", {
    rows: payload.acoustic.history.length, bearings: payload.acoustic.broadband.length,
    bins: payload.acoustic.demon.length});
  metrics($("helicopter-asset"), [["state", heloStateText(heloStates, asset)], ["airborne", yesNo(asset.airborne)],
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
  drawDeckMotion(ready.deck_motion);
  renderHelicopterStatusLamps();
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
  // During the start preparation the launch button shows its time left and
  // the recall button stops it.
  $("helicopter-launch").textContent = asset.prep_s !== null ? heloStateText(heloStates, asset) : t("helicopter_launch");
  $("helicopter-return").textContent = t(asset.prep_s !== null ? "helicopter_prep_cancel" : "helicopter_return");
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
  drawHelicopterDip(payload.dip_observations, asset, payload.dip_environment);
  renderHelicopterLamps(asset, ready);
  const scope = visualContext("helicopter-dip-rose");
  if (scope) drawDipScope(scope.context, scope.width, scope.height, payload.dip_observations, payload.buoy_observations, palette());
}
// The dipping sonar's side view beside the scope (src/ui/stations/helicopter.py
// _draw_dip_column): air with the helicopter on top, the waterline, the water
// darker with depth, the layer in amber and the dome on its cable.
function drawDipColumn(ctx, x, y, w, h, asset, environment, colors) {
  const airH = Math.max(18, Math.round(h / 5)), waterY = y + airH, waterH = h - airH;
  const gaugeMax = Math.max(50, environment.depth_limit_m || 0), cx = x + w / 2;
  ctx.fillStyle = paletteAlpha("muted", .22); ctx.fillRect(x, y, w, airH);
  const gradient = ctx.createLinearGradient(0, waterY, 0, y + h);
  gradient.addColorStop(0, paletteAlpha("blue", .35)); gradient.addColorStop(1, paletteAlpha("blue", .8));
  ctx.fillStyle = gradient; ctx.fillRect(x, waterY, w, waterH);
  ctx.strokeStyle = colors.lineStrong; ctx.lineWidth = 1; ctx.strokeRect(x + .5, y + .5, w - 1, h - 1);
  ctx.strokeStyle = colors.blue; ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(x - 5, waterY); ctx.lineTo(x + w + 5, waterY); ctx.stroke();
  if (asset.airborne) {
    ctx.fillStyle = colors.text;
    ctx.beginPath(); ctx.moveTo(cx - 8, y + 5); ctx.lineTo(cx + 8, y + 5); ctx.lineTo(cx, y + 12); ctx.closePath(); ctx.fill();
  }
  if (finite(environment.thermocline_m) && environment.thermocline_m <= gaugeMax) {
    const layerY = waterY + waterH * environment.thermocline_m / gaugeMax;
    ctx.strokeStyle = colors.amber; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x - 6, layerY); ctx.lineTo(x + w + 6, layerY); ctx.stroke();
  }
  if (asset.airborne && asset.dip_state !== "STOWED") {
    const domeY = waterY + waterH * Math.min(1, asset.dip_depth_m / gaugeMax);
    ctx.strokeStyle = colors.muted; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, y + 12); ctx.lineTo(cx, domeY); ctx.stroke();
    ctx.fillStyle = colors.accent; ctx.beginPath(); ctx.arc(cx, domeY, 5, 0, Math.PI * 2); ctx.fill();
  }
}
function drawHelicopterDip(rows, asset, environment) {
  const canvas = $("helicopter-dip-canvas"), ctx = canvas.getContext("2d");
  if (!ctx) return;
  const {width: w, height: h} = canvas, colors = palette();
  ctx.fillStyle = colors.scopeBg; ctx.fillRect(0, 0, w, h);
  ctx.font = "13px ui-monospace, monospace";
  drawDipScope(ctx, w - 70, h - 16, rows, [], colors);
  drawDipColumn(ctx, w - 52, 14, 26, h - 44, asset, environment, colors);
  ctx.fillStyle = colors.muted; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  ctx.fillText(t("helicopter_dip_scale"), 12, h - 8);
}
