import { S } from "../state/store.js";
import { $, isSonar, panelRole, reasons } from "../core/base.js";
import { chartMatches, finite, hasPosition, number, sameContext, selectedTrack, t } from "../core/format.js";
import { sendStationAction } from "../net/commands.js";
import { stationActionAvailable } from "../state/availability.js";
import { renderBridgeOrders } from "./bridge-orders.js";
import { contextKey } from "../state/display-model.js";
import { view } from "../state/shared.js";
import { clearFireConfirmation, showToast } from "./dom.js";
import { hostUnavailableReason } from "./host.js";
import { renderProposals } from "./feeds.js";

export function renderActionState() {
  const track = selectedTrack();
  $("follow").disabled = !hasPosition(S.snapshot?.ownship);
  if ($("follow").disabled) view.follow = false;
  $("follow").setAttribute("aria-pressed", String(view.follow));
  const stationEnabled = stationActionAvailable();
  const sonarAction = stationEnabled &&
    (isSonar(S.session.station) || S.session.station === "helicopter") &&
    track?.can_classify === true;
  const opzAction = stationEnabled && S.session.station === "opz";
  $("apply-classification").disabled = !(sonarAction || opzAction && track?.can_classify === true);
  $("classification").disabled = $("apply-classification").disabled;
  $("apply-classification").textContent = t("apply");
  const dipReport = S.v2State?.helicopter?.dip_observations.find((row) => row.ref === track?.ref);
  const buoyReport = S.v2State?.helicopter?.buoy_observations.find((row) => row.ref === track?.ref);
  $("sonar-release").disabled = !(sonarAction && track && S.session.station !== "uboot_sonar" &&
    (S.session.station !== "helicopter" || dipReport && (dipReport.qualified || dipReport.released_to_opz)));
  $("helicopter-qualify").disabled = !(stationEnabled && S.session.station === "helicopter" && track);
  $("helicopter-buoy-release").disabled = !(stationEnabled && S.session.station === "helicopter" &&
    buoyReport && (buoyReport.qualified || buoyReport.released_to_opz));
  $("apply-affiliation").disabled = !(opzAction && track);
  $("affiliation").disabled = $("apply-affiliation").disabled;
  const proposalAvailable = stationEnabled && S.proposals && contextKey(S.proposals) === contextKey(S.v2State);
  $("propose").disabled = !(proposalAvailable && S.session.station === "sonar" && track?.can_propose === true);
  $("clear-proposal").disabled = !(proposalAvailable && S.session.station === "sonar" && S.proposals.target !== null);
  const navigationAvailable = proposalAvailable && S.session.station === "bridge";
  for (const id of ["navigation-course", "navigation-speed", "propose-navigation"]) $(id).disabled = !navigationAvailable;
  const message = S.pending ? { key: S.pending.uncertain ? "command_uncertain" : "command_pending", status: "pending" } : S.commandMessage;
  const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : message?.reasoncode || t("unavailable");
  $("command-status").textContent = message ? t(message.key, { reason }) : "";
  $("command-status").dataset.status = message?.status || "";
  $("station-command-status").textContent = message ? t(message.key, {reason}) : "";
  $("station-command-status").dataset.status = message?.status || "";
  if (message && message !== S.lastToastedMessage && message.status !== "pending") {
    S.lastToastedMessage = message;
    showToast(message.key, { reason }, message.status === "rejected" ? "danger" : "ok");
  }
  $("command-reconcile").hidden = !S.pending?.uncertain;
  $("retry-command").disabled = !S.pending?.uncertain || S.pending.inFlight || performance.now() < S.pending.retryAt ||
    !S.connected || S.session?.grants.command !== true || !sameContext(S.v2State, {
      session: S.pending?.body.world_session, epoch: S.pending?.body.world_epoch,
    });
  renderProposals();
  renderBridgeOrders();
  renderOpzControls();
  renderStationControls();
  renderDirectFireControls();
  renderDisabledReasons();
}
function directFireSpec(action) {
  const role = S.session?.station;
  const payload = S.v2State?.[role];
  if (role === "weapons") {
    const ref = $("weapons-fire-target").value;
    const depth = $("weapons-fire-depth").valueAsNumber;
    const target = payload?.target_choices.some((row) => row.ref === ref);
    const common = Boolean(payload && !payload.readiness.station_down);
    if (action === "weapons_launch_torpedo") return {ref, params: {ref, depth_m: depth},
      ready: common && target && payload.inventory.torpedoes > 0 && payload.readiness.state === "available" &&
        payload.tubes.some((tube) => tube.state === "ready"), readiness: [payload?.inventory.torpedoes, payload?.readiness, payload?.tubes]};
    if (action === "helicopter_launch_torpedo") return {ref, params: {ref, depth_m: depth},
      ready: common && target, readiness: [payload?.readiness, payload?.target_choices.map((row) => row.ref)]};
    if (action === "weapons_deploy_nixie") return {ref: "", params: {},
      ready: common && payload.inventory.nixies > 0, readiness: [payload?.readiness.station_down, payload?.inventory.nixies]};
  }
  if (role === "helicopter" && action === "helicopter_launch_torpedo") {
    const ref = $("helicopter-fire-target").value;
    const depth = $("helicopter-fire-depth").valueAsNumber;
    return {ref, params: {ref, depth_m: depth}, ready: payload?.asset.airborne && payload.asset.torpedoes > 0 &&
      payload.target_choices.some((row) => row.ref === ref),
    readiness: [payload?.asset.state, payload?.asset.airborne, payload?.asset.torpedoes,
      payload?.readiness, payload?.target_choices.map((row) => row.ref)]};
  }
  if (role === "uboot" && action === "uboot_fire") {
    const ref = $("uboot-fire-target").value;
    const bearing = $("uboot-fire-bearing").valueAsNumber;
    const range = $("uboot-fire-range").valueAsNumber;
    const target = Boolean(ref) && Boolean(payload?.contacts.some((row) => row.ref === ref));
    const freeBearing = !ref && finite(bearing) && bearing >= 0 && bearing < 360;
    const rangeValue = finite(range) && range >= 0.05 && range <= 40 ? range : null;
    const depth = $("uboot-fire-depth").valueAsNumber;
    return {ref: target ? ref : freeBearing ? `bearing:${bearing}` : "",
      params: {ref: target ? ref : null, bearing: target || !freeBearing ? null : bearing,
        range_nm: target ? null : rangeValue,
        depth_m: finite(depth) && depth >= 5 && depth <= 300 ? depth : null,
        salvo: $("uboot-fire-salvo").value === "2" ? 2 : 1},
      ready: Boolean(payload?.weapons.ready) && (target || freeBearing),
      readiness: [payload?.weapons, payload?.contacts.map((row) => row.ref)]};
  }
  if (role === "opz" && ["opz_launch_essm", "opz_launch_chaff"].includes(action)) {
    const ref = $("opz-fire-target").value;
    const target = payload?.asm_observations.some((row) => row.ref === ref);
    return {ref, params: {ref}, ready: payload?.radar.live && target && (action === "opz_launch_essm" ?
      payload.defense.vls > 0 && payload.defense.aa_ready : payload.defense.chaff_ready),
    readiness: [payload?.radar.live, payload?.defense, payload?.asm_observations.map((row) => row.ref)]};
  }
  return {ref: "", params: {}, ready: false, readiness: null};
}
function directFireAvailable() {
  return stationActionAvailable() && S.session?.grants.direct_fire === true;
}
function directFireFingerprint(action, spec) {
  return JSON.stringify([S.generation, S.session?.station, S.session?.station_generation, S.session?.grants.command,
    S.session?.grants.direct_fire, S.v2State?.session, S.v2State?.epoch, action, spec.ref,
    action.includes("torpedo") ? spec.params.depth_m : null, spec.ready, spec.readiness]);
}
function fireStatusKey() {
  if (!S.session?.grants.command || !S.session?.grants.direct_fire) return "fire_revoked";
  if (!S.connected || !chartMatches(S.snapshot)) return "fire_stale";
  if (S.v2State?.phase !== "live") return "fire_inactive";
  if (S.pending) return S.pending.uncertain ? "fire_uncertain" : "fire_pending";
  return "fire_ready";
}
export function renderDirectFireControls() {
  const role = S.session?.station;
  const status = role === "weapons" ? $("weapons-fire-status") : role === "opz" ? $("opz-fire-status") :
    role === "helicopter" ? $("helicopter-fire-status") : role === "uboot" ? $("uboot-fire-status") : null;
  if (!status) { clearFireConfirmation(); return; }
  let pendingConfirm = false;
  let anyReady = false;
  for (const button of document.querySelectorAll("[data-fire-action]")) {
    const owned = button.closest("[data-station-role]")?.dataset.stationRole === panelRole(role);
    const spec = directFireSpec(button.dataset.fireAction);
    const fingerprint = directFireFingerprint(button.dataset.fireAction, spec);
    const isTarget = S.fireConfirmation?.action === button.dataset.fireAction;
    // The dialog holds its own fingerprint snapshot; if the underlying
    // spec changed while it was open (target dropped, readiness lost),
    // cancel rather than let a stale confirm silently go through.
    if (isTarget && (S.fireConfirmation.fingerprint !== fingerprint || performance.now() >= S.fireConfirmation.expiresAt)) {
      clearFireConfirmation();
    }
    const stillPending = S.fireConfirmation?.action === button.dataset.fireAction;
    button.disabled = !owned || !directFireAvailable() || !spec.ready ||
      actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
    anyReady ||= owned && spec.ready && !actionIncludesInvalidDepth(button.dataset.fireAction, spec.params.depth_m);
    button.classList.toggle("armed", stillPending);
    button.textContent = t(button.dataset.fireAction);
    pendingConfirm ||= stillPending;
  }
  for (const control of document.querySelectorAll(".direct-fire-controls input, .direct-fire-controls select")) {
    const owned = control.closest("[data-station-role]")?.dataset.stationRole === panelRole(role);
    control.disabled = !owned || !directFireAvailable();
  }
  const stateKey = fireStatusKey();
  const statusKey = stateKey === "fire_ready" && !anyReady ? "fire_not_ready" : stateKey;
  status.textContent = t(pendingConfirm ? "fire_confirmation_active" : statusKey);
  status.dataset.state = pendingConfirm ? "armed" : statusKey;
}
function actionIncludesInvalidDepth(action, depth) {
  return action.includes("torpedo") && (!finite(depth) || depth < 10 || depth > 300);
}
function fireConfirmSummary(action, spec) {
  const parts = [t(action)];
  if (spec.ref) parts.push(t("fire_confirm_dialog_target", { ref: spec.ref }));
  if (action.includes("torpedo") && finite(spec.params.depth_m)) {
    parts.push(t("fire_confirm_dialog_depth", { depth: spec.params.depth_m }));
  }
  return parts.join(" — ");
}
export function activateDirectFire(button) {
  const action = button.dataset.fireAction;
  const spec = directFireSpec(action);
  if (!directFireAvailable() || !spec.ready || actionIncludesInvalidDepth(action, spec.params.depth_m)) return;
  clearFireConfirmation();
  S.fireConfirmation = {action, fingerprint: directFireFingerprint(action, spec),
    expiresAt: performance.now() + 5000};
  S.fireConfirmationTimer = setTimeout(() => { clearFireConfirmation(); renderDirectFireControls(); }, 5000);
  $("fire-confirm-summary").textContent = fireConfirmSummary(action, spec);
  renderDirectFireControls();
  const dialog = $("fire-confirm-dialog");
  if (!dialog.open) dialog.showModal();
}
export function confirmFireDialog() {
  const state = S.fireConfirmation;
  clearFireConfirmation();
  if (!state) return;
  const spec = directFireSpec(state.action);
  const fingerprint = directFireFingerprint(state.action, spec);
  // Re-validate against the current state rather than trusting what was
  // true when the dialog opened - readiness or the target list can move
  // underneath a modal the operator took a few seconds to act on.
  if (!directFireAvailable() || !spec.ready || fingerprint !== state.fingerprint ||
      actionIncludesInvalidDepth(state.action, spec.params.depth_m)) {
    renderDirectFireControls();
    return;
  }
  sendStationAction(state.action, spec.params);
}
function renderStationControls() {
  const available = stationActionAvailable();
  for (const control of document.querySelectorAll("[data-station-action], .station-controls input, .station-controls select, .station-controls button, #helicopter-waypoint-form input, #helicopter-waypoint-form button")) {
    const local = control.id === "sonar-control-page";
    const owned = control.closest("[data-station-role]")?.dataset.stationRole === panelRole(S.session?.station);
    control.disabled = !owned || !local && (!available || control.dataset.ready === "false");
  }
  const sonar = S.v2State?.sonar?.settings;
  if (sonar) {
    const live = available && !sonar.station_down;
    for (const id of ["sonar-bearing", "sonar-bearing-submit", "sonar-clear-focus", "sonar-array-mode", "sonar-array-apply",
      "sonar-tma", "sonar-audition-mode", "sonar-listen-band", "sonar-listen-notch", "sonar-gain", "sonar-gain-submit", "sonar-band", "sonar-band-apply", "sonar-notch", "sonar-peak",
      "sonar-harmonic-input", "sonar-harmonic-submit", "sonar-harmonic-clear"]) $(id).disabled = !live;
    $("sonar-clear-focus").disabled = !live || sonar.focus_ref === null;
  }
  const engine = S.v2State?.engine;
  if (engine) {
    const live = available && engine.machinery.station_state !== "ZERSTOERT";
    for (const id of ["engine-telegraph", "engine-telegraph-submit", "engine-course", "engine-course-submit", "engine-speed", "engine-speed-submit", "engine-quiet"]) $(id).disabled = !live;
  }
  $("damage-team").disabled = !(available && S.session?.station === "damage" && S.v2State?.damage?.teams.length);
  $("opz-designate").disabled = !(available && S.session?.station === "opz" && selectedTrack() && S.v2State?.opz?.radar.live);
}
export function renderSonarControlPage() {
  const page = $("sonar-control-page").value;
  for (const panel of document.querySelectorAll("[data-sonar-page]")) panel.hidden = panel.dataset.sonarPage !== page;
}
export const unavailable = (key, values = {}) => ({key, values});
function stationUnavailableReason() {
  if (!S.session?.station) return unavailable("reason_role_revoked");
  if (!S.connected) return unavailable(S.linkState === "syncing" ? "connection_syncing" : "connection_stale", {age: 0});
  if (!S.v2State || S.roleStale || !chartMatches(S.snapshot)) return unavailable("connection_syncing");
  if (S.session.grants.command !== true) return unavailable("reason_grant_revoked");
  if (S.v2State.phase !== "live") return unavailable("reason_phase_blocked");
  if (S.pending) return unavailable(S.pending.uncertain ? "command_uncertain" : "command_pending");
  return null;
}
function directFireUnavailableReason(control) {
  const shared = stationUnavailableReason();
  if (shared) return shared;
  if (S.session?.grants.direct_fire !== true) return unavailable("reason_direct_fire_grant");
  const action = control.dataset.fireAction;
  const spec = directFireSpec(action);
  if (actionIncludesInvalidDepth(action, spec.params.depth_m)) return unavailable("reason_invalid_depth");
  const payload = S.v2State?.[S.session.station];
  if (!spec.ref && action !== "weapons_deploy_nixie") return unavailable("reason_no_target");
  if (S.session.station === "weapons") {
    if ((action === "weapons_launch_torpedo" && payload.inventory.torpedoes <= 0) ||
        (action === "weapons_deploy_nixie" && payload.inventory.nixies <= 0)) return unavailable("reason_no_inventory");
    if (action === "weapons_launch_torpedo" && !payload.tubes.some((tube) => tube.state === "ready")) return unavailable("reason_no_ready_tube");
  }
  if (S.session.station === "helicopter") {
    if (!payload.asset.airborne) return unavailable("reason_not_airborne");
    if (payload.asset.torpedoes <= 0) return unavailable("reason_no_inventory");
  }
  return unavailable("reason_not_ready");
}
function disabledReason(control) {
  if (!control.disabled) return null;
  if (control.dataset.fireAction) return directFireUnavailableReason(control);
  if (control.closest("#station-cards")) {
    const record = S.session?.stations[control.dataset.station];
    if (S.session?.requested_station) return unavailable("reason_station_request_pending");
    if (record?.status === "occupied") return unavailable("reason_station_occupied");
    if (record?.status === "mine") return unavailable("reason_station_already_leased");
    return unavailable("reason_station_change_pending");
  }
  if (["add-station", "mobile-add-station", "workstation-add-station"].includes(control.id)) {
    return unavailable(S.session?.requested_station ? "reason_station_request_pending" : "reason_station_change_pending");
  }
  if (["release-station", "mobile-release-station", "mobile-station"].includes(control.id)) {
    return unavailable("reason_station_change_pending");
  }
  if (control.closest("#host-bar, #host-screen, #host-slot-dialog, #host-new-dialog")) return hostUnavailableReason(control);
  if (control.id === "follow") return unavailable("reason_position_unavailable");
  if (control.id === "sonar-live-toggle") return unavailable("reason_sonar_audio_grant");
  const shared = stationUnavailableReason();
  if (shared) return shared;
  const sonar = S.v2State?.sonar?.settings;
  if (control.closest('[data-station-role="sonar"]') && sonar) {
    if (sonar.station_down) return unavailable("reason_sonar_down");
    if (control.id === "sonar-clear-focus" && sonar.focus_ref === null) return unavailable("reason_no_focus");
    if (["sonar-tas", "sonar-depth", "sonar-depth-submit"].includes(control.id)) {
      if (sonar.tow.state === "FAULT") return unavailable("reason_tas_fault");
      if (sonar.tow.speed_kn > sonar.tow.speed_max_kn) return unavailable("reason_tas_too_fast", {speed: number(sonar.tow.speed_kn), limit: number(sonar.tow.speed_max_kn)});
      if (sonar.tow.speed_kn < sonar.tow.speed_min_kn) return unavailable("reason_tas_too_slow", {speed: number(sonar.tow.speed_kn), limit: number(sonar.tow.speed_min_kn)});
      if (["sonar-depth", "sonar-depth-submit"].includes(control.id) && sonar.tow.state !== "STREAMED") return unavailable("reason_tas_not_streamed");
    }
    if (control.id === "sonar-ping" && !sonar.ping.ready) return unavailable("reason_cooldown", {seconds: number(sonar.ping.cooldown_s, 0)});
    if (control.id === "sonar-bt" && !sonar.bt.ready) return unavailable("reason_cooldown", {seconds: number(sonar.bt.cooldown_s, 0)});
  }
  if (control.closest('[data-station-role="engine"]') && S.v2State?.engine?.machinery.station_state === "ZERSTOERT") return unavailable("reason_engine_down");
  if (control.closest('[data-station-role="opz"]') && S.v2State?.opz?.radar.live === false) return unavailable("reason_opz_down");
  if (control.closest('[data-station-role="radio"], #radio-visual') && S.v2State?.radio?.station_down) return unavailable("reason_radio_down");
  if (control.closest('[data-station-role="bridge"]') && S.v2State?.bridge?.orders.station_down) return unavailable("reason_bridge_down");
  const helicopter = S.v2State?.helicopter;
  if (control.closest('[data-station-role="helicopter"]') && helicopter) {
    if (helicopter.readiness.flightdeck_down) return unavailable("reason_flightdeck_down");
    if (["helicopter-return", "helicopter-buoy", "helicopter-dip-toggle", "helicopter-dip-depth", "helicopter-dip-depth-submit", "helicopter-dip-ping"].includes(control.id) && !helicopter.asset.airborne) return unavailable("reason_not_airborne");
    if (control.id === "helicopter-buoy" && helicopter.asset.buoys <= 0) return unavailable("reason_no_buoys");
    if (control.id === "helicopter-dip-ping" && helicopter.asset.dip_ping_cooldown_s > 0) return unavailable("reason_cooldown", {seconds: number(helicopter.asset.dip_ping_cooldown_s, 0)});
  }
  return unavailable("reason_not_ready");
}
export function renderDisabledReasons() {
  const visibleReasons = [];
  for (const control of document.querySelectorAll("button, input, select")) {
    const reason = disabledReason(control);
    if (reason) {
      const text = t(reason.key, reason.values);
      control.title = text;
      control.dataset.disabledReason = text;
      control.setAttribute("aria-disabled", "true");
      const stationPanel = control.closest("[data-station-role]");
      const relevant = stationPanel ? stationPanel.dataset.stationRole === panelRole(S.session?.station)
        : !control.closest("[hidden]");
      if (relevant && !visibleReasons.includes(text)) {
        visibleReasons.push(text);
      }
    } else {
      control.removeAttribute("title");
      delete control.dataset.disabledReason;
      control.removeAttribute("aria-disabled");
    }
  }
  $("disabled-control-explain").hidden = visibleReasons.length === 0;
  $("disabled-control-explain").dataset.reasons = JSON.stringify(visibleReasons.slice(0, 24));
  if (!visibleReasons.length) {
    $("disabled-control-help").hidden = true;
    $("disabled-control-explain").setAttribute("aria-expanded", "false");
  }
  else if (!$("disabled-control-help").hidden) {
    $("disabled-control-help").textContent = visibleReasons.slice(0, 24).join(" ");
  }
}
function renderOpzControls() {
  const active = S.session?.station === "opz";
  $("opz-controls").hidden = !active;
  $("opz-track-actions").hidden = !active;
  $("track-id-form").hidden = !active;
  if (!active) return;
  const radar = S.v2State?.opz?.radar;
  const available = stationActionAvailable() && radar?.live === true;
  $("opz-radar-surface").checked = radar?.surface === true;
  $("opz-radar-air").checked = radar?.air === true;
  if (finite(radar?.range_nm)) $("opz-range").value = String(radar.range_nm);
  for (const id of ["opz-radar-surface", "opz-radar-air", "opz-range"]) $(id).disabled = !available;
  $("opz-create-fusion").disabled = !available || S.opzMarked.size < 2 || S.opzMarked.size > 8;
  const track = selectedTrack();
  if (track && document.activeElement !== $("track-id")) $("track-id").value = track.label;
  $("track-id").disabled = !available || !track;
  $("apply-track-id").disabled = !available || !track;
  $("opz-mark").disabled = !track || track.source === "FUSION";
  $("opz-mark").setAttribute("aria-pressed", String(Boolean(track && S.opzMarked.has(track.ref))));
  $("opz-dissolve").disabled = !available || track?.source !== "FUSION";
  $("opz-suppress").disabled = !track;
  $("opz-suppress").textContent = t(track && S.opzSuppressed.has(track.ref) ? "opz_restore" : "opz_suppress");
  $("opz-mark-status").textContent = t("opz_mark_count", {count: S.opzMarked.size});
}
