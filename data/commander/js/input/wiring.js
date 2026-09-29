import { S } from "../state/store.js";
import { renderSound } from "../audio/alerts.js";
import { openSonarAudioSocket, renderSonarAudio, scheduleSonarAudioPoll, sonarAudioAuthorized, sonarFilterValues, sonarGainValue, stopSonarAudio, stopSpeech, syncGameAudio } from "../audio/audio.js";
import { $, audioRoles, isSonar } from "../core/base.js";
import { authenticated, finite, hasPosition, number, selectedTrack, t } from "../core/format.js";
import { loadLanguage } from "../core/i18n.js";
import { retryPendingCommand, sendStationAction } from "../net/commands.js";
import { submitBridgeOrder } from "../views/bridge-orders.js";
import { poll } from "../net/poll.js";
import { request } from "../net/request.js";
import { forgetSession, setConnection } from "../net/session.js";
import { stopSonarStream, syncSonarStream } from "../net/sonar-stream.js";
import { plotArea } from "../plot/axes.js";
import { syncPlotAnimation } from "../plot/clock.js";
import { buildDisplayModel } from "../state/display-model.js";
import { elokaFilters, lookoutView, mapRoles, roleMapViews, sonarDisplay, sonarScopeNames, tabNames, view, visualCanvasIds, wideScreen } from "../state/shared.js";
import { syncWeatherAnimation } from "../stations/bridge.js";
import { drawUbootGraphics, renderUbootStation } from "../stations/uboot.js";
import { broadbandVisible, drawSonarVisuals } from "../stations/sonar-visuals.js";
import { analysisProfile, renderContactAnalysis } from "../views/analyzer.js";
import { chartGeometry, fitChart, plotClick, plotTrackBearing, queueDraw, releaseCanvas } from "../views/chart.js";
import { activateDirectFire, confirmFireDialog, renderActionState, renderDirectFireControls, renderSonarControlPage } from "../views/controls.js";
import { clearFireConfirmation } from "../views/dom.js";
import { acceptSession, activateTab, chooseSide, chooseStation, mutateStation, renderLobby } from "../views/lobby.js";
import { changeLookoutRange, queueLookoutDraw, renderLookoutStatus, zoom } from "../views/lookout.js";
import { renderSnapshot } from "../views/render.js";
import { hideMapTooltip, mapTooltipLines, nearestMapInfo, roleMapGeometry, showMapTooltip, stopOpzSweepAnimation, syncOpzSweepAnimation } from "../views/role-map.js";
import { queueVisualDraw, renderRoleVisuals } from "../views/role-visuals.js";
import { applySimlogView, closeSimlogMap, exportSimlog, loadSimlog, queueSimlogMapDraw } from "../views/simlog.js";
import { renderTracks, selectTrack } from "../views/tracks.js";
import { drawWeatherProfile, profileSpeedAt, toggleWeatherStation } from "../views/weather.js";
import { schedule } from "../core/scheduler.js";
import { stationActionAvailable } from "../state/availability.js";
import { renderConnection } from "../views/status.js";
import { canvas, lookoutCanvas, simlogMapCanvas } from "../views/canvases.js";
import { normalizePairCode, wirePairCodeInput } from "../core/pairing-code.js";

const sonarFrequencyAt = (canvas, event, maximum) => {
  const bounds = canvas.getBoundingClientRect();
  const area = plotArea(canvas.clientWidth, canvas.clientHeight);
  const x = (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width);
  return x < area.left || x > area.left + area.width ? null : (x - area.left) / area.width * maximum;
};
// Environment (BT): the cursor depth reads the measured profile.
const btReadout = (event) => {
  const canvas = $("sonar-environment"), bt = S.v2State?.sonar?.visualization?.bt;
  if (!bt || !bt.depths_m.length) return null;
  const bounds = canvas.getBoundingClientRect();
  const area = plotArea(canvas.clientWidth, canvas.clientHeight);
  const y = (event.clientY - bounds.top) * canvas.clientHeight / Math.max(1, bounds.height);
  if (y < area.top || y > area.top + area.height) return null;
  const maximum = Math.max(1, ...bt.depths_m);
  const depth = (y - area.top) / area.height * maximum;
  const speed = profileSpeedAt(bt.depths_m, bt.speeds_m_s, depth);
  const key = !finite(bt.thermocline_m) ? "sonar_cursor_depth"
    : depth < bt.thermocline_m ? "sonar_cursor_depth_above" : "sonar_cursor_depth_below";
  return {depth, text: t(key, {depth: number(depth, 0), speed: number(speed, 1)})};
};
const redrawBt = () => schedule("sonar-bt", () => { if (S.v2State?.sonar) drawSonarVisuals(); });
const redrawWeatherProfile = () => schedule("weather-profile", () => {
  const profile = S.v2State?.weather_station?.profile;
  if ($("weather-dialog").open && profile !== undefined) drawWeatherProfile(profile);
});
const releaseActiveStation = () => S.session?.station && mutateStation("/stations/release", {
  station: S.session.station, station_generation: S.session.station_generation,
  active_generation: S.session.active_generation,
});
const openStationPicker = () => {
  if (!S.session?.station || S.session.requested_station !== null || S.stationMutation) return;
  S.stationPickerOpen = true;
  renderLobby();
};
const numberAction = (formId, inputId, action, field, minimum, maximum) => {
  const form = $(formId);
  if (!form.reportValidity()) return;
  const value = $(inputId).valueAsNumber;
  if (!finite(value) || value < minimum || value > maximum) return;
  sendStationAction(action, {[field]: value});
};
const updateSonarAudioFilters = () => {
  for (const prefix of ["sonar", "helicopter"]) {
    $(`${prefix}-audio-highpass-value`).value = `${number(Number($(`${prefix}-audio-highpass`).value), 0)} Hz`;
    $(`${prefix}-audio-lowpass-value`).value = `${number(Number($(`${prefix}-audio-lowpass`).value), 0)} Hz`;
  }
  const [high, low] = sonarFilterValues();
  if (S.sonarAudioHighpass && S.audio) S.sonarAudioHighpass.frequency.setTargetAtTime(high, S.audio.currentTime, .02);
  if (S.sonarAudioLowpass && S.audio) S.sonarAudioLowpass.frequency.setTargetAtTime(low, S.audio.currentTime, .02);
};
const changeRoleMapZoom = (factor) => {
  const role = S.v2State?.role;
  if (!mapRoles.has(role)) return;
  roleMapViews[role].zoom = Math.max(.5, Math.min(32, roleMapViews[role].zoom * factor));
  queueVisualDraw();
};

export function init() {
  wirePairCodeInput($("code"));
  $("pair-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if ($("pair-submit").disabled || !$("pair-form").reportValidity()) return;
    if (!S.pairingAvailable) {
      $("pair-error").textContent = t("pair_failed");
      return;
    }
    $("pair-submit").disabled = true;
    $("pair-error").textContent = "";
    const code = normalizePairCode($("code").value);
    const name = $("name").value.trim();
    $("code").value = "";
    try {
      const result = await request("/pair", { method: "POST", body: {code, name}, auth: false });
      acceptSession(result);
      S.generation += 1;
      S.failures = 0;
      $("pairing").hidden = true;
      $("disconnect").hidden = false;
      setConnection(S.session.station === null ? "lobby" : "syncing");
      clearTimeout(S.pollTimer);
      poll();
    } catch (error) {
      // Only the pairing route's own answer means a wrong code; a bare 403
      // is the listener refusing this address (Host/Origin).
      $("pair-error").textContent = t(error?.status === 403 ?
        (error.reason === "invalid_code" ? "pair_invalid_code" : "pair_address") : "pair_failed");
      $("code").focus();
    } finally { $("pair-submit").disabled = false; }
  });
  $("language").addEventListener("change", () => loadLanguage($("language").value === "de" ? "de" : "en"));
  for (const [id, key] of [["eloka-status-filter", "status"], ["eloka-threat-filter", "threat"], ["eloka-band-filter", "band"]]) {
    $(id).addEventListener("change", () => {
      elokaFilters[key] = $(id).value;
      if (S.v2State?.role === "eloka") {
        S.snapshot = buildDisplayModel(S.v2State);
        if (!selectedTrack()) S.selected = null;
        renderSnapshot();
      }
    });
  }
  $("volume").addEventListener("input", () => {
    if (S.sonarAudioGain) S.sonarAudioGain.gain.value = sonarGainValue();
    syncGameAudio();
  });
  $("analysis-filter").addEventListener("input", renderContactAnalysis);
  $("contact-filter").addEventListener("input", renderTracks);
  $("analysis-category").addEventListener("change", renderContactAnalysis);
  // Pointer Events (not "click") so this canvas matches #chart/#role-map's
  // tap-vs-drag disambiguation: a touch that starts a scroll/pan gesture
  // must not also silently set the listen bearing.
  $("sonar-broadband").addEventListener("pointerdown", (event) => {
    if (!isSonar(S.session?.station) || !stationActionAvailable() || !broadbandVisible()
        || !event.isPrimary || event.button !== 0) return;
    const canvas = $("sonar-broadband");
    canvas.setPointerCapture(event.pointerId);
    S.sonarBroadbandDrag = {id: event.pointerId, x: event.clientX, y: event.clientY, moved: false};
  });
  $("sonar-broadband").addEventListener("pointermove", (event) => {
    const canvas = $("sonar-broadband");
    const bounds = canvas.getBoundingClientRect();
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const x = (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width);
    if (x >= area.left && x <= area.left + area.width) {
      const bearing = (x - area.left) / area.width * 360;
      $("sonar-cursor-readout").value = t("sonar_cursor_bearing", {bearing: number(bearing, 1)});
    }
    if (!S.sonarBroadbandDrag || S.sonarBroadbandDrag.id !== event.pointerId) return;
    const dx = event.clientX - S.sonarBroadbandDrag.x;
    const dy = event.clientY - S.sonarBroadbandDrag.y;
    if (Math.hypot(dx, dy) > 5) S.sonarBroadbandDrag.moved = true;
  });
  $("sonar-broadband").addEventListener("pointerup", (event) => {
    if (!S.sonarBroadbandDrag || S.sonarBroadbandDrag.id !== event.pointerId) return;
    const gesture = S.sonarBroadbandDrag;
    S.sonarBroadbandDrag = null;
    $("sonar-broadband").releasePointerCapture(event.pointerId);
    if (gesture.moved || !isSonar(S.session?.station) || !stationActionAvailable()
        || !broadbandVisible()) return;
    const canvas = $("sonar-broadband");
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = (event.clientX - bounds.left) * canvas.clientWidth / bounds.width;
    const y = (event.clientY - bounds.top) * canvas.clientHeight / bounds.height;
    const area = plotArea(canvas.clientWidth, canvas.clientHeight);
    if (x < area.left || x >= area.left + area.width ||
        y < area.top || y >= area.top + area.height) return;
    const bearing = (x - area.left) / area.width * 360;
    const observations = S.v2State?.sonar?.observations ?? [];
    const nearest = observations.map((row) => ({row, delta: Math.abs(((row.bearing - bearing + 540) % 360) - 180)}))
      .sort((a, b) => a.delta - b.delta)[0];
    // Selecting an observed bearing locks its passive S-track and routes that
    // beam to live audio. Empty-water clicks remain free beam steering.
    if (nearest && nearest.delta <= Math.max(3, S.v2State.sonar.visualization.receiver.beam_width_deg / 2)) {
      S.selected = nearest.row.ref;
      sendStationAction("sonar_set_focus", {ref: nearest.row.ref});
    } else sendStationAction("sonar_set_listen_bearing", {bearing});
  });
  $("sonar-broadband").addEventListener("pointercancel", (event) => {
    if (S.sonarBroadbandDrag?.id === event.pointerId) S.sonarBroadbandDrag = null;
  });
  $("sonar-broadband").addEventListener("lostpointercapture", () => { S.sonarBroadbandDrag = null; });
  $("sonar-environment").addEventListener("pointermove", (event) => {
    const reading = btReadout(event);
    sonarDisplay.btCursorDepth = reading ? reading.depth : null;
    sonarDisplay.btCursorText = reading ? reading.text : "";
    if (reading) $("sonar-cursor-readout").value = reading.text;
    redrawBt();
  });
  $("sonar-environment").addEventListener("pointerleave", () => {
    sonarDisplay.btCursorDepth = null;
    redrawBt();
  });
  $("weather-profile").addEventListener("pointermove", (event) => {
    const canvas = $("weather-profile"), bounds = canvas.getBoundingClientRect();
    S.weatherCursor = {x: (event.clientX - bounds.left) * canvas.clientWidth / Math.max(1, bounds.width),
                     y: (event.clientY - bounds.top) * canvas.clientHeight / Math.max(1, bounds.height)};
    redrawWeatherProfile();
  });
  $("weather-profile").addEventListener("pointerleave", () => { S.weatherCursor = null; redrawWeatherProfile(); });
  $("sonar-lofar").addEventListener("pointermove", (event) => {
    const hz = sonarFrequencyAt($("sonar-lofar"), event, 300);
    const visual = S.v2State?.sonar?.visualization?.lofar;
    if (hz === null || !visual?.spectrum?.length) return;
    let bin = 0;
    for (let index = 1; index < visual.bin_frequencies_hz.length; index++)
      if (Math.abs(visual.bin_frequencies_hz[index] - hz) < Math.abs(visual.bin_frequencies_hz[bin] - hz)) bin = index;
    const level = visual.spectrum[bin] || 0;
    const db = 20 * Math.log10(Math.max(1e-6, level));
    const fundamental = S.v2State.sonar.settings.harmonic_hz;
    const order = finite(fundamental) && fundamental > 0 ? Math.max(1, Math.round(hz / fundamental)) : 1;
    $("sonar-cursor-readout").value = t("sonar_cursor_frequency", {frequency: number(hz, 1), strength: number(db, 1), harmonic: order});
  });
  $("sonar-lofar").addEventListener("click", (event) => {
    const hz = sonarFrequencyAt($("sonar-lofar"), event, 300);
    if (hz !== null && isSonar(S.session?.station) && stationActionAvailable()) sendStationAction("sonar_set_harmonic", {frequency_hz: hz});
  });
  $("sonar-demon-spectrum").addEventListener("click", (event) => {
    const hz = sonarFrequencyAt($("sonar-demon-spectrum"), event, 50);
    if (hz === null) return;
    if (isSonar(S.session?.station) && stationActionAvailable())
      sendStationAction("sonar_set_cursor", {page: "demon", frequency_hz: Math.round(hz * 2) / 2});
    if (sonarDisplay.demonCursor === null) {
      sonarDisplay.demonCursor = hz;
      $("sonar-cursor-readout").value = t("sonar_demon_cursor_first", {frequency: number(hz, 1)});
    } else {
      const spacing = Math.abs(hz - sonarDisplay.demonCursor);
      sonarDisplay.demonCursor = spacing > .05 ? spacing : hz;
      $("sonar-cursor-readout").value = t("sonar_demon_spacing", {spacing: number(spacing, 2), rpm: number(spacing * 60, 1)});
    }
    queueVisualDraw();
  });
  for (const id of ["sonar-palette", "sonar-black-level", "sonar-contrast", "sonar-history"]) {
    $(id).addEventListener("input", () => {
      sonarDisplay.palette = $("sonar-palette").value;
      sonarDisplay.black = Number($("sonar-black-level").value);
      sonarDisplay.contrast = Number($("sonar-contrast").value);
      sonarDisplay.history = Number($("sonar-history").value);
      queueVisualDraw();
    });
  }
  $("sonar-detach").addEventListener("click", () => {
    const scope = S.sonarVisualPage === "overview" ? "broadband" : S.sonarVisualPage;
    if (!sonarScopeNames.has(scope)) return;
    window.open(`${location.pathname}?scope=${encodeURIComponent(scope)}`, `ujagd-sonar-${scope}`, "popup,width=1280,height=800,noopener");
  });
  // The dialog's own toolbar (close/fit-to-world/fit-to-units) was never
  // wired to the click handlers and view-fit modes it was built to control.
  $("simlog-map-close").addEventListener("click", closeSimlogMap);
  // Fires for every dismissal path (this button, Escape, a future .close()
  // call) - the single place that resets the dialog's transient state.
  $("simlog-map-dialog").addEventListener("close", () => {
    S.simlogMapData = null;
    S.simlogMapSeq = null;
    S.simlogMapLatest = false;
    $("simlog-map-dialog").hidden = true;
    $("simlog-map-units").replaceChildren();
    releaseCanvas(simlogMapCanvas);
  });
  $("simlog-map-world").addEventListener("click", () => {
    S.simlogMapFit = "world";
    $("simlog-map-world").setAttribute("aria-pressed", "true");
    $("simlog-map-units-fit").setAttribute("aria-pressed", "false");
    queueSimlogMapDraw();
  });
  $("simlog-map-units-fit").addEventListener("click", () => {
    S.simlogMapFit = "units";
    $("simlog-map-world").setAttribute("aria-pressed", "false");
    $("simlog-map-units-fit").setAttribute("aria-pressed", "true");
    queueSimlogMapDraw();
  });
  $("disconnect").addEventListener("click", async () => {
    const csrf = S.session?.csrf;
    try {
      if (csrf) await request("/logout", {method: "POST", csrf});
    } catch (_) {
      // Local tactical data is cleared even when the host cannot confirm logout.
    } finally {
      forgetSession();
      $("code").focus();
    }
  });
  $("release-station").addEventListener("click", releaseActiveStation);
  $("mobile-release-station").addEventListener("click", releaseActiveStation);
  for (const id of ["add-station", "mobile-add-station", "workstation-add-station"]) {
    $(id).addEventListener("click", openStationPicker);
  }
  for (const button of $("side-choice").querySelectorAll("button"))
    button.addEventListener("click", () => chooseSide(button.dataset.side));
  $("lobby-back").addEventListener("click", () => {
    S.stationPickerOpen = false;
    renderLobby();
  });
  wideScreen.addEventListener("change", () => { if (S.v2State?.role) renderRoleVisuals(S.v2State.role); });
  $("mobile-station").addEventListener("change", () => chooseStation($("mobile-station").value));
  $("classification-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const classification = $("classification").value || null;
    if (isSonar(S.session?.station) || S.session?.station === "helicopter")
      sendStationAction("sonar_classify", {ref: S.selected, classification});
    else if (S.session?.station === "opz") sendStationAction("opz_classify", {ref: S.selected, classification});
  });
  $("classification").addEventListener("change", renderActionState);
  $("sonar-release").addEventListener("click", () => {
    const track = selectedTrack();
    if (track) sendStationAction("sonar_set_release", {
      ref: track.ref, released: !track.released_to_opz,
    });
  });
  $("helicopter-qualify").addEventListener("click", () => {
    const rows = [...(S.v2State?.helicopter?.buoy_observations || []),
      ...(S.v2State?.helicopter?.dip_observations || [])];
    const row = rows.find((item) => item.ref === S.selected);
    if (row) sendStationAction("helicopter_qualify", {ref: S.selected, enabled: !row.qualified});
  });
  $("helicopter-buoy-release").addEventListener("click", () => {
    const row = S.v2State?.helicopter?.buoy_observations.find((item) => item.ref === S.selected);
    if (row) sendStationAction("helicopter_buoy_release", {ref: S.selected,
      released: !row.released_to_opz});
  });
  $("affiliation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (S.session?.station === "opz") sendStationAction("opz_affiliate", {ref: S.selected, affiliation: $("affiliation").value});
  });
  $("track-id-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!S.selected || !$("track-id-form").reportValidity()) return;
    sendStationAction("opz_set_track_id", {
      ref: S.selected, label: $("track-id").value.toUpperCase(),
    });
  });
  $("opz-radar-surface").addEventListener("change", () => sendStationAction("opz_set_radar", {domain: "surface", enabled: $("opz-radar-surface").checked}));
  $("opz-ciws").addEventListener("change", () => sendStationAction("opz_set_ciws", {enabled: $("opz-ciws").checked}));
  $("opz-radar-air").addEventListener("change", () => sendStationAction("opz_set_radar", {domain: "air", enabled: $("opz-radar-air").checked}));
  $("opz-range").addEventListener("change", () => sendStationAction("opz_set_range", {range_nm: Number($("opz-range").value)}));
  $("opz-create-fusion").addEventListener("click", () => sendStationAction("opz_create_fusion", {refs: [...S.opzMarked]}));
  $("opz-mark").addEventListener("click", () => {
    const track = selectedTrack();
    if (!track || track.source === "FUSION") return;
    if (S.opzMarked.has(track.ref)) S.opzMarked.delete(track.ref); else if (S.opzMarked.size < 8) S.opzMarked.add(track.ref);
    renderActionState(); renderTracks(); queueDraw();
  });
  $("opz-dissolve").addEventListener("click", () => sendStationAction("opz_dissolve_fusion", {ref: S.selected}));
  $("opz-designate").addEventListener("click", () => {
    if (S.selected) sendStationAction("opz_designate_target", {ref: S.selected});
  });
  $("opz-suppress").addEventListener("click", () => {
    const track = selectedTrack();
    if (!track) return;
    if (S.opzSuppressed.has(track.ref)) S.opzSuppressed.delete(track.ref); else S.opzSuppressed.add(track.ref);
    const raw = S.v2State; if (raw) { S.snapshot = buildDisplayModel(raw); if (!selectedTrack()) S.selected = null; renderSnapshot(); }
  });
  $("opz-manage").addEventListener("change", () => {
    S.opzManage = $("opz-manage").checked;
    if (S.v2State) { S.snapshot = buildDisplayModel(S.v2State); renderSnapshot(); }
  });
  for (const id of ["sonar-array-mode", "sonar-audition-mode", "sonar-band", "sonar-listen-band", "sonar-bearing", "sonar-depth", "sonar-vds-depth", "sonar-gain",
    "sonar-harmonic-input", "engine-telegraph", "engine-course", "engine-speed", "helicopter-x", "helicopter-y",
    "helicopter-dip-depth", "uboot-course", "uboot-speed", "uboot-depth", "uboot-scope-relative",
    "weapons-fire-target", "weapons-fire-depth", "helicopter-fire-target", "helicopter-fire-depth", "opz-fire-target",
    "uboot-fire-target", "uboot-fire-bearing", "uboot-fire-range", "uboot-fire-depth",
    "uboot-fire-salvo", "uboot-wire-weapon", "uboot-wire-bearing", "uboot-wire-range",
    "weapons-torpedo-type", "weapons-pattern", "weapons-enable", "weapons-salvo", "engine-plant", "helicopter-pattern"]) {
    $(id).addEventListener("input", () => S.stationDrafts.add(id));
    $(id).addEventListener("change", () => S.stationDrafts.add(id));
    if (id.includes("fire")) for (const eventName of ["input", "change"]) $(id).addEventListener(eventName, () => {
      clearFireConfirmation(); renderDirectFireControls();
    });
  }
  for (const button of document.querySelectorAll("[data-fire-action]")) button.addEventListener("click", () => activateDirectFire(button));
  $("fire-confirm-cancel").addEventListener("click", clearFireConfirmation);
  $("fire-confirm-confirm").addEventListener("click", confirmFireDialog);
  // Converges every dismissal path (Cancel, the 5s timeout, and the
  // browser's own Escape handling) on the same state reset, mirroring
  // closeSimlogMap()'s use of the dialog's native close event.
  $("fire-confirm-dialog").addEventListener("close", () => {
    clearFireConfirmation();
    renderDirectFireControls();
  });
  $("sonar-control-page").addEventListener("change", renderSonarControlPage);
  for (const button of $("sonar-page-tabs").querySelectorAll("button")) {
    button.addEventListener("click", () => {
      S.sonarVisualPage = button.dataset.sonarVisual;
      $("sonar-control-page").value = ({environment: "array", active: "listen", broadband: "listen", overview: "listen"}[S.sonarVisualPage] || "analysis");
      renderSonarControlPage();
      renderRoleVisuals(S.v2State?.role);
    });
    button.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...$("sonar-page-tabs").querySelectorAll("button")];
      let index = buttons.indexOf(button);
      if (event.key === 'ArrowLeft') index = (index - 1 + buttons.length) % buttons.length;
      if (event.key === 'ArrowRight') index = (index + 1) % buttons.length;
      if (event.key === 'Home') index = 0;
      if (event.key === 'End') index = buttons.length - 1;
      buttons[index].click(); buttons[index].focus();
    });
  }
  $("sonar-bearing-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-bearing-form", "sonar-bearing", "sonar_set_listen_bearing", "bearing", 0, 359.99999999999994);
  });
  $("sonar-clear-focus").addEventListener("click", () => sendStationAction("sonar_clear_focus", {}));
  $("sonar-array-apply").addEventListener("click", () => sendStationAction("sonar_set_array_mode", {mode: $("sonar-array-mode").value}));
  $("weapons-settings-apply").addEventListener("click", () => {
    for (const id of ["weapons-torpedo-type", "weapons-pattern", "weapons-enable", "weapons-salvo"]) S.stationDrafts.delete(id);
    sendStationAction("weapons_set_torpedo_settings", {torpedo_type: $("weapons-torpedo-type").value,
      pattern: $("weapons-pattern").value, enable_nm: $("weapons-enable").valueAsNumber,
      salvo: Number($("weapons-salvo").value)});
  });
  $("sonar-tas").addEventListener("click", () => sendStationAction("sonar_set_tas", {deployed: $("sonar-tas").dataset.deployed !== "true"}));
  $("sonar-depth-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-depth-form", "sonar-depth", "sonar_set_tow_depth", "depth_m", 20, 260);
  });
  $("sonar-vds").addEventListener("click", () => sendStationAction("sonar_set_vds", {deployed: $("sonar-vds").dataset.deployed !== "true"}));
  $("sonar-vds-depth-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-vds-depth-form", "sonar-vds-depth", "sonar_set_vds_depth", "depth_m", 20, 300);
  });
  $("sonar-bt").addEventListener("click", () => sendStationAction("sonar_measure_bt", {}));
  $("sonar-ping").addEventListener("click", () => sendStationAction("sonar_active_ping", {}));
  $("sonar-tma").addEventListener("change", () => sendStationAction("sonar_set_tma_enabled", {enabled: $("sonar-tma").checked}));
  $("sonar-audition-mode").addEventListener("change", () => sendStationAction("sonar_set_audition_mode", {mode: $("sonar-audition-mode").value}));
  $("sonar-gain-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-gain-form", "sonar-gain", "sonar_set_gain", "gain_db", -12, 24);
  });
  $("sonar-band-apply").addEventListener("click", () => sendStationAction("sonar_set_band_preset", {preset: $("sonar-band").value}));
  $("sonar-notch").addEventListener("change", () => sendStationAction("sonar_set_notch", {enabled: $("sonar-notch").checked}));
  $("sonar-listen-band").addEventListener("change", () => sendStationAction("sonar_set_band_preset", {preset: $("sonar-listen-band").value}));
  $("sonar-listen-notch").addEventListener("change", () => sendStationAction("sonar_set_notch", {enabled: $("sonar-listen-notch").checked}));
  $("sonar-peak").addEventListener("change", () => sendStationAction("sonar_set_peak_hold", {enabled: $("sonar-peak").checked}));
  $("sonar-tma-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const course = Number($("sonar-tma-course").value), speed = Number($("sonar-tma-speed").value), range = Number($("sonar-tma-range").value);
    if (S.selected && [course, speed, range].every(finite) && course >= 0 && course < 360 && speed >= 0 && speed <= 45 && range >= .2 && range <= 60)
      sendStationAction("sonar_tma_set", {ref: S.selected, course, speed_kn: speed, range_nm: range});
  });
  $("analysis-assign").addEventListener("click", () => {
    const profile = analysisProfile();
    if (profile && S.selected) sendStationAction("sonar_assign_profile", {ref: S.selected, profile_key: profile.key});
  });
  $("analysis-assign-clear").addEventListener("click", () => { if (S.selected) sendStationAction("sonar_assign_profile", {ref: S.selected, profile_key: null}); });
  $("sonar-tma-accept").addEventListener("click", () => { if (S.selected) sendStationAction("sonar_tma_accept", {ref: S.selected}); });
  $("sonar-tma-copy").addEventListener("click", () => { if (S.selected) sendStationAction("sonar_tma_copy_proposal", {ref: S.selected}); });
  $("sonar-demon-band").addEventListener("change", () => {
    const [low, high] = $("sonar-demon-band").value.split("-").map(Number);
    sendStationAction("sonar_set_demon_band", {low_hz: low, high_hz: high});
  });
  $("sonar-heterodyne").addEventListener("change", () => sendStationAction("sonar_set_heterodyne", {frequency_hz: Number($("sonar-heterodyne").value)}));
  $("sonar-integration").addEventListener("change", () => sendStationAction("sonar_set_integration", {seconds: Number($("sonar-integration").value)}));
  $("sonar-vernier").addEventListener("change", () => sendStationAction("sonar_set_vernier", {enabled: $("sonar-vernier").checked}));
  $("sonar-tas-flip").addEventListener("click", () => { if (S.selected) sendStationAction("sonar_tas_side", {ref: S.selected, action: "flip"}); });
  $("sonar-tas-confirm").addEventListener("click", () => { if (S.selected) sendStationAction("sonar_tas_side", {ref: S.selected, action: "confirm"}); });
  $("sonar-demon-mark").addEventListener("click", () => sendStationAction("sonar_mark_line", {page: "demon"}));
  $("sonar-band-edges-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const low = Number($("sonar-band-low-hz").value), high = Number($("sonar-band-high-hz").value);
    if (finite(low) && finite(high) && low >= 0 && low < high && high <= 300) sendStationAction("sonar_set_band", {low_hz: low, high_hz: high});
  });
  $("sonar-operator-notch-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-operator-notch-form", "sonar-operator-notch", "sonar_set_operator_notch", "frequency_hz", 0.000001, 300);
  });
  $("sonar-operator-notch-clear").addEventListener("click", () => sendStationAction("sonar_set_operator_notch", {frequency_hz: null}));
  $("sonar-harmonic-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("sonar-harmonic-form", "sonar-harmonic-input", "sonar_set_harmonic", "frequency_hz", 0.000001, 300);
  });
  $("sonar-harmonic-clear").addEventListener("click", () => sendStationAction("sonar_set_harmonic", {frequency_hz: null}));
  $("engine-telegraph-submit").addEventListener("click", () => sendStationAction("engine_set_telegraph", {order: $("engine-telegraph").value}));
  $("engine-course-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("engine-course-form", "engine-course", "engine_set_course", "course", 0, 359.99999999999994);
  });
  $("engine-speed-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("engine-speed-form", "engine-speed", "engine_set_speed", "speed_kn", 0, 25);
  });
  $("engine-quiet").addEventListener("click", () => sendStationAction("engine_set_quiet_mode", {enabled: !S.v2State.engine.propulsion.quiet_mode}));
  $("engine-plant-apply").addEventListener("click", () => {
    S.stationDrafts.delete("engine-plant");
    sendStationAction("engine_set_plant", {mode: $("engine-plant").value});
  });
  $("damage-counterflood").addEventListener("click", () => sendStationAction("damage_counterflood",
    {enabled: !S.v2State?.damage?.stability.counterflood_room}));
  $("uboot-course-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("uboot-course-form", "uboot-course", "uboot_set_course", "course", 0, 359.99999999999994);
  });
  $("uboot-speed-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("uboot-speed-form", "uboot-speed", "uboot_set_speed", "speed_kn", 0, 40);
  });
  $("uboot-depth-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("uboot-depth-form", "uboot-depth", "uboot_set_depth", "depth_m", 0, 1000);
  });
  $("uboot-decoy").addEventListener("click", () => sendStationAction("uboot_decoy", {}));
  $("uboot-evade").addEventListener("click", () => sendStationAction("uboot_evade", {}));
  $("uboot-radio-send").addEventListener("click", () => sendStationAction("uboot_radio_send", {}));
  $("uboot-blow").addEventListener("click", () => sendStationAction("uboot_blow", {}));
  // Wire guidance of a running crew torpedo: new datum from the boat, or cut.
  $("uboot-wire-steer").addEventListener("click", () => {
    const ref = $("uboot-wire-weapon").value, bearing = $("uboot-wire-bearing").valueAsNumber, range = $("uboot-wire-range").valueAsNumber;
    if (!ref || !finite(bearing) || bearing < 0 || bearing >= 360 || !finite(range) || range < .05 || range > 40) return;
    sendStationAction("uboot_wire_steer", {ref, bearing, range_nm: range});
  });
  $("uboot-wire-cut").addEventListener("click", () => {
    if ($("uboot-wire-weapon").value) sendStationAction("uboot_wire_cut", {ref: $("uboot-wire-weapon").value});
  });
  // Boat modes: explicit on/off buttons (mast up / down, snorkel up / down, ...).
  for (const button of document.querySelectorAll("[data-uboot-mode]"))
    button.addEventListener("click", () => sendStationAction(button.dataset.ubootMode,
      {enabled: button.dataset.enabled === "true"}));
  // One-step depth orders (periscope, snorkel, above / below the measured layer, deep).
  for (const button of document.querySelectorAll("[data-uboot-depth-preset]"))
    button.addEventListener("click", () => {
      const depth = Number(button.dataset.depth);
      if (button.dataset.depth && finite(depth) && depth >= 0 && depth <= 1000)
        sendStationAction("uboot_set_depth", {depth_m: depth});
    });
  for (const button of document.querySelectorAll("[data-uboot-speed-step]"))
    button.addEventListener("click", () => {
      const speed = Number(button.dataset.speed);
      if (finite(speed) && speed >= 0 && speed <= 40) sendStationAction("uboot_set_speed", {speed_kn: speed});
    });
  // The periscope: train it in steps or to an entered relative bearing, read the stadimeter.
  for (const button of document.querySelectorAll("[data-uboot-scope-turn]"))
    button.addEventListener("click", () => {
      const scope = S.v2State?.[S.v2State?.role]?.scope;
      if (!scope || !finite(scope.relative_deg)) return;
      const relative = ((scope.relative_deg + Number(button.dataset.ubootScopeTurn)) % 360 + 360) % 360;
      sendStationAction("uboot_scope_bearing", {relative_deg: relative});
    });
  $("uboot-scope-form").addEventListener("submit", (event) => {
    event.preventDefault(); numberAction("uboot-scope-form", "uboot-scope-relative", "uboot_scope_bearing", "relative_deg", 0, 359.99999999999994);
  });
  $("uboot-scope-mark").addEventListener("click", () => sendStationAction("uboot_scope_mark", {}));
  $("uboot-scope-fire").addEventListener("click", () => sendStationAction("uboot_scope_fire", {}));
  // Engine room stores: snorkel charge rate, absorber change, oxygen candle.
  for (const button of document.querySelectorAll("[data-uboot-charge-rate]"))
    button.addEventListener("click", () => sendStationAction("uboot_charge_rate", {rate: button.dataset.ubootChargeRate}));
  // Engine room tanks: one step of the regulating or trim tank set point.
  for (const button of document.querySelectorAll("[data-uboot-ballast]"))
    button.addEventListener("click", () => sendStationAction("uboot_ballast",
      {tank: button.dataset.ubootBallast, direction: Number(button.dataset.direction)}));
  // Engine room damage control: send a team, shut or open a compartment.
  $("uboot-dc-form").addEventListener("submit", (event) => {
    event.preventDefault();
    sendStationAction("uboot_dc_team", {team: Number($("uboot-dc-team").value),
      compartment: $("uboot-dc-compartment").value, task: $("uboot-dc-task").value});
  });
  $("uboot-dc-rows").addEventListener("click", (event) => {
    const button = event.target.closest("[data-uboot-bulkhead]");
    if (button) sendStationAction("uboot_bulkhead", {compartment: button.dataset.ubootBulkhead, closed: button.dataset.closed === "true"});
  });
  // Mast station ESM: pick an emitter, classify it, transfer it to the plot.
  $("uboot-esm-emitters").addEventListener("click", (event) => {
    const button = event.target.closest("[data-uboot-esm-emitter]");
    if (!button) return;
    S.ubootEsmSelected = Number(button.dataset.ubootEsmEmitter);
    S.stationDrafts.delete("uboot-esm-class");
    const payload = S.v2State?.[S.v2State?.role];
    if (payload?.esm) renderUbootStation(payload);
  });
  $("uboot-esm-class").addEventListener("change", () => S.stationDrafts.add("uboot-esm-class"));
  $("uboot-esm-class-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const candidate = Number($("uboot-esm-class").value);
    S.stationDrafts.delete("uboot-esm-class");
    if (Number.isSafeInteger(S.ubootEsmSelected) && Number.isInteger(candidate))
      sendStationAction("uboot_esm_classify", {emitter: S.ubootEsmSelected, candidate});
  });
  $("uboot-esm-plot").addEventListener("click", () => {
    if (Number.isSafeInteger(S.ubootEsmSelected)) sendStationAction("uboot_esm_plot", {emitter: S.ubootEsmSelected});
  });
  $("uboot-absorber").addEventListener("click", () => sendStationAction("uboot_absorber", {}));
  $("uboot-o2-candle").addEventListener("click", () => sendStationAction("uboot_o2_candle", {}));
  $("simlog-export").addEventListener("click", () => exportSimlog());
  $("uboot-ping").addEventListener("click", () => sendStationAction("sonar_active_ping", {}));
  $("uboot-bt").addEventListener("click", () => sendStationAction("sonar_measure_bt", {}));
  $("bridge-route-mode").addEventListener("click", () => {
    S.bridgeRouteMode = !S.bridgeRouteMode;
    $("bridge-route-mode").setAttribute("aria-pressed", String(S.bridgeRouteMode));
  });
  $("bridge-route-zigzag").addEventListener("click", () => sendStationAction("bridge_route_pattern", {pattern: "zigzag"}));
  $("bridge-route-square").addEventListener("click", () => sendStationAction("bridge_route_pattern", {pattern: "square"}));
  $("bridge-route-clear").addEventListener("click", () => sendStationAction("bridge_route_clear", {}));
  $("helicopter-launch").addEventListener("click", () => sendStationAction("helicopter_launch", {}));
  $("helicopter-return").addEventListener("click", () => sendStationAction("helicopter_return", {}));
  $("helicopter-waypoint-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const x = $("helicopter-x").valueAsNumber, y = $("helicopter-y").valueAsNumber;
    if (finite(x) && finite(y) && x >= 0 && x <= 1000 && y >= 0 && y <= 1000) sendStationAction("helicopter_set_waypoint", {x, y});
  });
  $("helicopter-buoy").addEventListener("click", () => sendStationAction("helicopter_deploy_buoy", {}));
  $("opz-mpa-waypoint-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const x = $("opz-mpa-x").valueAsNumber, y = $("opz-mpa-y").valueAsNumber;
    if (finite(x) && finite(y) && x >= 0 && x <= 1000 && y >= 0 && y <= 1000) sendStationAction("mpa_set_waypoint", {x, y});
  });
  $("opz-mpa-pattern-apply").addEventListener("click", () => sendStationAction("mpa_set_pattern", {kind: $("opz-mpa-pattern").value}));
  $("helicopter-pattern-apply").addEventListener("click", () => {
    S.stationDrafts.delete("helicopter-pattern");
    sendStationAction("helicopter_set_pattern", {kind: $("helicopter-pattern").value});
  });
  $("helicopter-mad").addEventListener("click", () => sendStationAction("helicopter_set_mad",
    {enabled: !S.v2State?.helicopter?.asset.mad_mode}));
  for (const mode of ["acoustic", "map"]) $(
    `helicopter-visual-${mode}`).addEventListener("click", () => {
      S.helicopterVisualPage = mode;
      renderRoleVisuals("helicopter");
    });
  for (const button of $("helicopter-acoustic-plot-tabs").querySelectorAll("button"))
    button.addEventListener("click", () => {
      S.helicopterPlot = button.dataset.helicopterPlotTab;
      renderRoleVisuals("helicopter");
    });
  $("helicopter-broadband-canvas").addEventListener("click", (event) => {
    if (S.session?.station !== "helicopter" || !stationActionAvailable()) return;
    const canvas = event.currentTarget, area = plotArea(canvas.clientWidth, canvas.clientHeight);
    const x = event.clientX - canvas.getBoundingClientRect().left - area.left;
    if (x >= 0 && x < area.width) sendStationAction("helicopter_set_listen_bearing",
      {bearing: Math.max(0, Math.min(359.9, x / area.width * 360))});
  });
  $("helicopter-buoy-mode").addEventListener("change", () => sendStationAction(
    "helicopter_set_buoy_mode", {mode: $("helicopter-buoy-mode").value}));
  $("helicopter-listen-source").addEventListener("change", () => sendStationAction(
    "helicopter_set_listen_source", {source: $("helicopter-listen-source").value}));
  $("helicopter-listen-bearing-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const bearing = $("helicopter-listen-bearing").valueAsNumber;
    if (finite(bearing) && bearing >= 0 && bearing < 360)
      sendStationAction("helicopter_set_listen_bearing", {bearing});
  });
  $("helicopter-listen-auto").addEventListener("click", () => sendStationAction(
    "helicopter_clear_listen_bearing", {}));
  $("helicopter-audition-mode").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_mode", {mode: $("helicopter-audition-mode").value}));
  $("helicopter-audio-band").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_band", {preset: $("helicopter-audio-band").value}));
  $("helicopter-audio-notch").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_notch", {enabled: $("helicopter-audio-notch").checked}));
  $("helicopter-audio-gain").addEventListener("input", () => {
    $("helicopter-audio-gain-value").value = `${$("helicopter-audio-gain").value} dB`;
  });
  $("helicopter-audio-gain").addEventListener("change", () => sendStationAction(
    "helicopter_set_audio_gain", {gain_db: Number($("helicopter-audio-gain").value)}));
  $("helicopter-dip-toggle").addEventListener("click", () => sendStationAction("helicopter_set_dipping", {
    deployed: $("helicopter-dip-toggle").dataset.deployed !== "true",
  }));
  $("helicopter-dip-ping").addEventListener("click", () => sendStationAction("helicopter_dipping_ping", {}));
  $("helicopter-dip-depth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const depth_m = $("helicopter-dip-depth").valueAsNumber;
    if (finite(depth_m)) sendStationAction("helicopter_set_dip_depth", {depth_m});
  });
  $("propose").addEventListener("click", () => {
    const track = selectedTrack();
    if (track?.can_propose) sendStationAction("propose_target", {ref: track.ref});
  });
  $("clear-proposal").addEventListener("click", () => sendStationAction("clear_target_proposal", {}));
  $("navigation-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const params = {};
    const course = $("navigation-course").value.trim() ? $("navigation-course").valueAsNumber : null;
    const speed = $("navigation-speed").value.trim() ? $("navigation-speed").valueAsNumber : null;
    if (course !== null) params.course = course;
    if (speed !== null) params.speed_kn = speed;
    if (!Object.keys(params).length || (course !== null && (!finite(course) || course < 0 || course >= 360)) ||
        (speed !== null && (!finite(speed) || speed < 0 || speed > 31))) {
      S.commandMessage = {key: "navigation_invalid", status: "rejected"};
      renderActionState();
      return;
    }
    sendStationAction("propose_navigation", params);
  });
  $("bridge-course-form").addEventListener("submit", (event) => { event.preventDefault(); submitBridgeOrder("course"); });
  $("bridge-speed-form").addEventListener("submit", (event) => { event.preventDefault(); submitBridgeOrder("speed"); });
  $("retry-command").addEventListener("click", retryPendingCommand);
  for (const [id, name] of [["workstation-help", "guide"], ["workstation-library", "contacts"], ["workstation-lookout", "lookout"]]) {
    $(id).addEventListener("click", () => { $("workstation-tools").open = false; activateTab(name); });
  }
  $("workstation-release").addEventListener("click", releaseActiveStation);
  $("workstation-weather").addEventListener("click", () => { $("workstation-tools").open = false; toggleWeatherStation(true); });
  $("weather-close").addEventListener("click", () => toggleWeatherStation(false));
  $("weather-dialog").addEventListener("close", (event) => {
    // Only the dialog's own dismissal hides it (not a close from inside).
    if (event.target !== $("weather-dialog") || $("weather-dialog").open) return;
    $("weather-dialog").hidden = true;
    releaseCanvas($("weather-profile"));
  });
  for (const name of tabNames) {
    const tab = $(`tab-${name}`);
    tab.addEventListener("click", () => activateTab(name));
    tab.addEventListener("keydown", (event) => {
      const visible = tabNames.filter((candidate) => !$(`tab-${candidate}`).hidden);
      let index = visible.indexOf(name);
      if (event.key === "ArrowRight") index = (index + 1) % visible.length;
      else if (event.key === "ArrowLeft") index = (index - 1 + visible.length) % visible.length;
      else if (event.key === "Home") index = 0;
      else if (event.key === "End") index = visible.length - 1;
      else return;
      event.preventDefault();
      activateTab(visible[index]);
    });
  }
  for (const link of document.querySelectorAll("#guide-nav a")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = $(link.hash.slice(1));
      const panel = $("panel-guide");
      if (!target || panel.hidden) return;
      panel.scrollTop += target.getBoundingClientRect().top - panel.getBoundingClientRect().top - 12;
      target.focus({ preventScroll: true });
    });
  }
  $("track-list").addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = [...$("track-list").querySelectorAll("button")];
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
    buttons[next]?.focus();
  });
  $("sound").addEventListener("click", async () => {
    try {
      if (S.soundEnabled) {
        S.soundEnabled = false;
        if (!S.sonarAudioEnabled) await S.audio?.suspend();
      } else {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) throw new Error("audio");
        if (!S.audio) S.audio = new Audio();
        await S.audio.resume();
        S.soundEnabled = S.audio.state === "running";
      }
      renderSound();
      syncGameAudio();
    } catch (_) { S.soundEnabled = false; renderSound(); $("sound").textContent = t("sound_unavailable"); }
  });
  $("speech").disabled = !("speechSynthesis" in window);
  $("speech").addEventListener("change", () => {
    S.speechEnabled = $("speech").checked && "speechSynthesis" in window;
    if (!S.speechEnabled) stopSpeech();
  });
  $("sonar-live-toggle").addEventListener("click", async () => {
    if (S.sonarAudioEnabled) { stopSonarAudio(); return; }
    if (!(audioRoles.has(S.session?.station) && S.session.grants.sonar_audio === true)) return;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error("audio");
      if (!S.audio) S.audio = new Audio();
      await S.audio.resume();
      if (S.audio.state !== "running" || !sonarAudioAuthorized()) throw new Error("audio");
      S.sonarAudioGain = S.audio.createGain();
      S.sonarAudioGain.gain.value = sonarGainValue();
      S.sonarAudioHighpass = S.audio.createBiquadFilter();
      S.sonarAudioHighpass.type = "highpass";
      S.sonarAudioHighpass.frequency.value = sonarFilterValues()[0];
      S.sonarAudioLowpass = S.audio.createBiquadFilter();
      S.sonarAudioLowpass.type = "lowpass";
      S.sonarAudioLowpass.frequency.value = sonarFilterValues()[1];
      S.sonarAudioGain.connect(S.sonarAudioHighpass);
      S.sonarAudioHighpass.connect(S.sonarAudioLowpass);
      S.sonarAudioLowpass.connect(S.audio.destination);
      if (S.audio.audioWorklet && window.AudioWorkletNode) {
        try {
          await S.audio.audioWorklet.addModule("/sonar-audio-worklet.js");
          S.sonarAudioWorklet = new AudioWorkletNode(S.audio, "sonar-audio-v2", {outputChannelCount: [1]});
          S.sonarAudioWorklet.connect(S.sonarAudioGain);
          S.sonarAudioWorklet.port.onmessage = ({data}) => {
            if (!S.sonarAudioEnabled) return;
            if (data?.type === "metrics") {
              S.sonarAudioMetrics = data;
              window.uJagdAudioDiagnostics = Object.freeze({
                bufferedSeconds: Math.max(0, Math.min(8, data.buffered * .25)),
                sequenceGaps: data.gaps, droppedBlocks: data.dropped, evictedBlocks: data.evictions,
                concealedBlocks: data.concealed, playbackRate: data.rate,
                stale: data.stale, transport: S.sonarAudioSocket ? "websocket" : "http"});
            }
            if (data?.type === "stale") {
              S.sonarAudioMetrics.stale = data.value;
              renderSonarAudio(data.value ? "sonar_live_stale" : "sonar_live_playing");
            }
          };
        } catch (_) { S.sonarAudioWorklet?.disconnect(); S.sonarAudioWorklet = null; }
      }
      S.sonarAudioEnabled = true;
      S.sonarAudioNextTime = S.audio.currentTime;
      renderSonarAudio("sonar_live_waiting");
      if (S.sonarAudioWorklet) openSonarAudioSocket();
      else scheduleSonarAudioPoll();
    } catch (_) { stopSonarAudio("sonar_live_unavailable"); }
  });
  $("sonar-audio-highpass").addEventListener("input", updateSonarAudioFilters);
  $("sonar-audio-lowpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-highpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-lowpass").addEventListener("input", updateSonarAudioFilters);
  $("helicopter-audio-volume").addEventListener("input", () => {
    $("helicopter-audio-volume-value").value = `${$("helicopter-audio-volume").value} %`;
    if (S.sonarAudioGain) S.sonarAudioGain.gain.value = sonarGainValue();
  });
  updateSonarAudioFilters();
  $("zoom-in").addEventListener("click", () => zoom(1.4));
  $("zoom-out").addEventListener("click", () => zoom(1 / 1.4));
  $("fit").addEventListener("click", fitChart);
  $("role-map-zoom-in").addEventListener("click", () => changeRoleMapZoom(1.4));
  $("role-map-zoom-out").addEventListener("click", () => changeRoleMapZoom(1 / 1.4));
  $("role-map-fit").addEventListener("click", () => {
    const role = S.v2State?.role;
    if (!mapRoles.has(role)) return;
    Object.assign(roleMapViews[role], {x: S.chart?.size_nm / 2 || 250, y: S.chart?.size_nm / 2 || 250, zoom: 1, follow: false});
    queueVisualDraw();
  });
  $("plot-tool").addEventListener("change", () => { S.plotAnchor = null; queueVisualDraw(); });
  $("plot-clear").addEventListener("click", () => sendStationAction("plot_clear", {}));
  $("plot-track-bearing").addEventListener("click", plotTrackBearing);
  $("role-map-follow").addEventListener("click", () => {
    const state = roleMapViews[S.v2State?.role]; if (!state) return;
    state.follow = !state.follow; queueVisualDraw();
  });
  $("role-map").addEventListener("wheel", (event) => { event.preventDefault(); changeRoleMapZoom(event.deltaY < 0 ? 1.15 : 1 / 1.15); }, {passive: false});
  $("role-map").addEventListener("pointerdown", (event) => {
    const role = S.v2State?.role;
    if (!mapRoles.has(role) || !event.isPrimary || event.button !== 0) return;
    $("role-map").setPointerCapture(event.pointerId);
    S.roleMapDrag = {id: event.pointerId, x: event.clientX, y: event.clientY, role,
      worldX: roleMapViews[role].x, worldY: roleMapViews[role].y, moved: false};
  });
  $("role-map").addEventListener("pointermove", (event) => {
    if (!S.roleMapDrag || S.roleMapDrag.id !== event.pointerId || S.roleMapDrag.role !== S.v2State?.role) return;
    const dx = event.clientX - S.roleMapDrag.x, dy = event.clientY - S.roleMapDrag.y;
    if (Math.hypot(dx, dy) > 5) S.roleMapDrag.moved = true;
    if (!S.roleMapDrag.moved) return;
    const state = roleMapViews[S.roleMapDrag.role];
    state.follow = false;
    const scale = Math.min($("role-map").clientWidth, $("role-map").clientHeight) / S.chart.size_nm * state.zoom;
    state.x = S.roleMapDrag.worldX - dx / scale;
    state.y = S.roleMapDrag.worldY - dy / scale;
    queueVisualDraw();
  });
  $("role-map").addEventListener("pointerup", (event) => {
    if (!S.roleMapDrag || S.roleMapDrag.id !== event.pointerId) return;
    const gesture = S.roleMapDrag;
    S.roleMapDrag = null;
    if (!gesture.moved && gesture.role === S.v2State?.role) {
      const rect = $("role-map").getBoundingClientRect();
      const x = event.clientX - rect.left, y = event.clientY - rect.top;
      const hits = S.roleMapHits.filter((hit) => Math.hypot(hit.x - x, hit.y - y) < 26)
        .sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y));
      const contact = hits.find((hit) => hit.ref !== null);
      if ($("plot-tools").open && $("plot-tool").value !== "off") {
        const geometry = roleMapGeometry(gesture.role), state = roleMapViews[gesture.role];
        if (geometry) plotClick(gesture.role, state.x + (x - rect.width / 2) / geometry.scale,
          state.y + (y - rect.height / 2) / geometry.scale);
      } else if (contact && contact.ref.startsWith("blip-")) {
        sendStationAction("opz_mark_blip", {ref: contact.ref});
      } else if (contact) {
        selectTrack(contact.ref);
      } else if (!contact && gesture.role === "bridge" && S.bridgeRouteMode && stationActionAvailable()) {
        // Route mode on the bridge: a click on open chart adds a waypoint.
        const geometry = roleMapGeometry(gesture.role), state = roleMapViews[gesture.role];
        const worldX = state.x + (x - rect.width / 2) / geometry.scale;
        const worldY = state.y + (y - rect.height / 2) / geometry.scale;
        if (finite(worldX) && finite(worldY) && worldX >= 0 && worldX <= 1000 && worldY >= 0 && worldY <= 1000)
          sendStationAction("bridge_route_add", {x: worldX, y: worldY});
      } else if (!hits.length && gesture.role === "helicopter" && stationActionAvailable() &&
                 S.v2State.helicopter.readiness.can_set_waypoint) {
        const geometry = roleMapGeometry(gesture.role);
        const state = roleMapViews[gesture.role];
        const worldX = state.x + (x - rect.width / 2) / geometry.scale;
        const worldY = state.y + (y - rect.height / 2) / geometry.scale;
        if (finite(worldX) && finite(worldY) && worldX >= 0 && worldX <= 1000 && worldY >= 0 && worldY <= 1000) {
          sendStationAction("helicopter_set_waypoint", {x: worldX, y: worldY});
        }
      }
    }
    $("role-map").releasePointerCapture(event.pointerId);
  });
  $("role-map").addEventListener("pointercancel", (event) => { if (S.roleMapDrag?.id === event.pointerId) S.roleMapDrag = null; });
  // Mouse-over: describe the nearest map item, or the chart position.
  $("role-map").addEventListener("pointermove", (event) => {
    const role = S.v2State?.role;
    if (S.roleMapDrag?.moved || event.pointerType === "touch" || !mapRoles.has(role)) { hideMapTooltip(); return; }
    const rect = $("role-map").getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const geometry = roleMapGeometry(role);
    const view = roleMapViews[role];
    const worldX = geometry ? view.x + (x - rect.width / 2) / geometry.scale : null;
    const worldY = geometry ? view.y + (y - rect.height / 2) / geometry.scale : null;
    const own = S.roleMapInfo.find((hit) => hit.kind === "own")?.item || null;
    showMapTooltip(event, mapTooltipLines(nearestMapInfo(S.roleMapInfo, x, y), worldX, worldY, own));
  });
  $("role-map").addEventListener("pointerleave", hideMapTooltip);
  $("role-map").addEventListener("lostpointercapture", () => { S.roleMapDrag = null; });
  $("role-map").addEventListener("keydown", (event) => {
    const role = S.v2State?.role;
    if (!mapRoles.has(role) || !["+", "=", "-", "Home", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    if (["+", "="].includes(event.key)) changeRoleMapZoom(1.4);
    else if (event.key === "-") changeRoleMapZoom(1 / 1.4);
    else if (event.key === "Home") $("role-map-fit").click();
    else { const amount = S.chart.size_nm / roleMapViews[role].zoom / 10; if (event.key === "ArrowLeft") roleMapViews[role].x -= amount; if (event.key === "ArrowRight") roleMapViews[role].x += amount; if (event.key === "ArrowUp") roleMapViews[role].y -= amount; if (event.key === "ArrowDown") roleMapViews[role].y += amount; queueVisualDraw(); }
  });
  $("damage-team").addEventListener("change", queueVisualDraw);
  $("disabled-control-explain").addEventListener("click", () => {
    const reasons = JSON.parse($("disabled-control-explain").dataset.reasons || "[]");
    $("disabled-control-help").textContent = reasons.join(" ");
    $("disabled-control-help").hidden = !$("disabled-control-help").hidden || reasons.length === 0;
    $("disabled-control-explain").setAttribute("aria-expanded", String(!$("disabled-control-help").hidden));
  });
  $("damage-schematic").addEventListener("click", (event) => {
    if (S.v2State?.role !== "damage" || !stationActionAvailable()) return;
    const rect = $("damage-schematic").getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const roomHit = S.damageHits.find((hit) => x >= hit.x && x <= hit.x + hit.width && y >= hit.y && y <= hit.y + hit.height);
    const teamNumber = Number($("damage-team").value);
    const team = S.v2State.damage.teams.find((row) => row.team === teamNumber);
    const room = S.v2State.damage.compartments.find((row) => row.key === roomHit?.key);
    if (!team || !room || team.compartment !== room.key && !room.repairable) return;
    const action = team.compartment === room.key ? "damage_unassign_team" : "damage_assign_team";
    sendStationAction(action, {team: team.team, compartment: room.key});
  });
  $("follow").addEventListener("click", () => {
    if (!hasPosition(S.snapshot?.ownship)) return;
    view.follow = !view.follow;
    $("follow").setAttribute("aria-pressed", String(view.follow));
    queueDraw();
  });
  $("lookout-zoom-in").addEventListener("click", () => changeLookoutRange(-1));
  $("lookout-zoom-out").addEventListener("click", () => changeLookoutRange(1));
  $("lookout-reset").addEventListener("click", () => {
    lookoutView.rangeNm = 100;
    renderLookoutStatus();
    queueLookoutDraw();
  });
  lookoutCanvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    changeLookoutRange(event.deltaY < 0 ? -1 : 1);
  }, { passive: false });
  lookoutCanvas.addEventListener("keydown", (event) => {
    if (!["+", "=", "-", "Home"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "+" || event.key === "=") changeLookoutRange(-1);
    else if (event.key === "-") changeLookoutRange(1);
    else {
      lookoutView.rangeNm = 100;
      renderLookoutStatus();
      queueLookoutDraw();
    }
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    zoom(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  canvas.addEventListener("pointerdown", (event) => {
    if (!S.snapshot || !S.chart || !event.isPrimary || event.button !== 0) return;
    canvas.focus();
    canvas.setPointerCapture(event.pointerId);
    S.drag = { id: event.pointerId, x: event.clientX, y: event.clientY, worldX: view.x, worldY: view.y, moved: false };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!S.drag || S.drag.id !== event.pointerId) return;
    const dx = event.clientX - S.drag.x;
    const dy = event.clientY - S.drag.y;
    if (Math.hypot(dx, dy) > 5) S.drag.moved = true;
    if (!S.drag.moved) return;
    const { scale } = chartGeometry();
    view.follow = false;
    $("follow").setAttribute("aria-pressed", "false");
    view.x = S.drag.worldX - dx / scale;
    view.y = S.drag.worldY - dy / scale;
    queueDraw();
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!S.drag || S.drag.id !== event.pointerId) return;
    if (!S.drag.moved) {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const hits = S.chartHits.filter((hit) => Math.hypot(hit.x - x, hit.y - y) < 26).sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y));
      if (hits.length) selectTrack(hits[0].ref);
    }
    S.drag = null;
    canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener("lostpointercapture", () => { S.drag = null; });
  canvas.addEventListener("pointermove", (event) => {
    if (S.drag?.moved || event.pointerType === "touch" || !S.chart) { hideMapTooltip(); return; }
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const { width, height, scale } = chartGeometry();
    const worldX = view.x + (x - width / 2) / scale, worldY = view.y + (y - height / 2) / scale;
    const own = S.chartInfo.find((hit) => hit.kind === "own")?.item || null;
    showMapTooltip(event, mapTooltipLines(nearestMapInfo(S.chartInfo, x, y), worldX, worldY, own));
  });
  canvas.addEventListener("pointerleave", hideMapTooltip);
  canvas.addEventListener("pointercancel", () => { S.drag = null; });
  canvas.addEventListener("keydown", (event) => {
    if (!S.snapshot || !S.chart) return;
    if (["+", "=", "-", "Home", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) event.preventDefault();
    if (event.key === "+" || event.key === "=") zoom(1.4);
    else if (event.key === "-") zoom(1 / 1.4);
    else if (event.key === "Home") fitChart();
    else if (event.key.startsWith("Arrow")) {
      const distance = 65 / chartGeometry().scale;
      view.follow = false;
      $("follow").setAttribute("aria-pressed", "false");
      if (event.key === "ArrowLeft") view.x -= distance;
      if (event.key === "ArrowRight") view.x += distance;
      if (event.key === "ArrowUp") view.y -= distance;
      if (event.key === "ArrowDown") view.y += distance;
      queueDraw();
    }
  });
  new ResizeObserver(queueDraw).observe(canvas);
  new ResizeObserver(queueLookoutDraw).observe(lookoutCanvas);
  for (const id of visualCanvasIds) new ResizeObserver(() => { queueVisualDraw(); syncOpzSweepAnimation(); }).observe($(id));
  let boatFrame = 0;
  const boatRedraw = () => {
    if (boatFrame) return;
    boatFrame = requestAnimationFrame(() => { boatFrame = 0; drawUbootGraphics(S.v2State?.[S.v2State?.role]); });
  };
  for (const id of ["uboot-depth-canvas", "uboot-esm-canvas", "uboot-scope-canvas", "uboot-ballast-canvas",
    "uboot-dc-canvas"])
    new ResizeObserver(boatRedraw).observe($(id));
  window.addEventListener("resize", () => { queueDraw(); queueLookoutDraw(); queueVisualDraw(); });
  window.addEventListener("hashchange", () => { applySimlogView(); loadSimlog(); });
  document.addEventListener("visibilitychange", () => {
    // A background tab's event batch is not a new audible alarm on return.
    if (document.hidden) S.eventBaselinePending = true;
    if (document.hidden) stopSonarAudio("sonar_live_unavailable");
    if (document.hidden) stopSonarStream(); else syncSonarStream();
    if (document.hidden && authenticated()) setConnection("stale");
    syncOpzSweepAnimation();
    syncWeatherAnimation();
    syncPlotAnimation();
  });
  window.addEventListener("offline", () => { S.eventBaselinePending = true; stopSonarStream(); stopOpzSweepAnimation(); if (authenticated()) setConnection("stale"); });
  window.addEventListener("online", () => { syncOpzSweepAnimation(); syncSonarStream(); if (authenticated() && !S.polling) { clearTimeout(S.pollTimer); poll(); } });
  setInterval(() => {
    if (authenticated() && S.lastSuccess && performance.now() - S.lastSuccess > 4500) setConnection("stale");
    else if (S.linkState === "stale") renderConnection();
    if (S.pending) {
      if (!S.pending.inFlight && performance.now() >= S.pending.retryAt) S.pending.uncertain = true;
      renderActionState();
    }
  }, 1000);
}
