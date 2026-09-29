// The phone lookout (/lookout): pairs with a code typed on the phone, then
// holds the frigate's lookout or the boat's periscope.  The phone's gyroscope
// (or a swipe) trains the eyepiece; the player calls what they see by voice
// or by tapping it.  The host confirms a call only when its own lookout has
// something there.  State and commands use the same v2 routes, checks and
// validators as the desktop client; the session stays in HttpOnly cookies.
import { S } from "../state/store.js";
import { $, lookoutRoles, prefix } from "../core/base.js";
import { finite, t } from "../core/format.js";
import { validateSession } from "../net/session.js";
import { boundedArray, exactKeys, validateV2State } from "../state/schema.js";
import { drawSightView, viewMotion } from "../views/sight-scene.js";
import { normalizePairCode, wirePairCodeInput } from "../core/pairing-code.js";
import { lineOfSight, wrap180, wrap360 } from "./orientation.js";
import { createListener, parseReport, speechAvailable } from "./speech.js";

const CATEGORIES = ["contact", "ship", "warship", "merchant", "aircraft", "submarine", "torpedo"];
// Eyepiece tilt limits (config.LOOKOUT_GLASSES_ELEVATION_DEG, UBOOT_SCOPE_ELEVATION_DEG).
const ELEVATION = {frigate: [-20, 45], boat: [-10, 60]};
const STATE_POLL_MS = 250, SESSION_POLL_MS = 4000, RESULT_POLL_MS = 700, RESULT_WAIT_MS = 10000;
const SCOPE_SEND_MS = 330, TAP_PX = 10, TAP_MS = 400;

const P = {
  session: null, state: null, view: null, seq: 0, lastState: 0, stateFailures: 0,
  relative: 0, elevation: 0, power: 0, gyro: false, offset: null, heading: null,
  drag: null, pick: null, listening: null, commands: Promise.resolve(), waiting: new Map(),
  scopeSent: null, scopeAt: 0, scopeBusy: false, status: null, wakeLock: null, timers: [],
};

// --- text ---------------------------------------------------------------------

async function loadLanguage(language) {
  const response = await fetch(`/api/v2/ui?lang=${language}`, {cache: "no-store", credentials: "same-origin", mode: "same-origin"});
  const catalog = await response.json();
  if (!catalog || typeof catalog[prefix + "phone_title"] !== "string" ||
      Object.entries(catalog).some(([key, value]) => !key.startsWith(prefix) || typeof value !== "string")) throw new Error("catalog");
  S.catalog = catalog;
  S.language = language;
  document.documentElement.lang = language;
  $("phone-language").value = language;
  document.title = t("phone_title");
  for (const element of document.querySelectorAll("[data-i18n]")) element.textContent = t(element.dataset.i18n);
  for (const element of document.querySelectorAll("[data-i18n-aria]")) element.setAttribute("aria-label", t(element.dataset.i18nAria));
  if (!$("phone-name").value) $("phone-name").value = t("phone_name_default").slice(0, 32);
  renderCategories();
}

const three = (value) => String(Math.round(wrap360(value)) % 360).padStart(3, "0");
const rangeText = (value) => finite(value) ? t("phone_range", {range: value.toLocaleString(S.language, {maximumFractionDigits: 1})}) : "";

function setStatus(key, values = {}, tone = "") {
  P.status = {key, values, tone, at: performance.now()};
  const element = $("phone-status");
  element.textContent = key ? t(key, values) : "";
  element.className = `phone-status ${tone}`;
}

// --- network ------------------------------------------------------------------

async function api(path, {method = "GET", body, expected = 200} = {}) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 4000);
  try {
    const headers = {Accept: "application/json"};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET" && P.session) headers["X-U-Jagd-CSRF"] = P.session.csrf;
    const response = await fetch(`/api/v2${path}`, {method, headers, signal: controller.signal, cache: "no-store",
      credentials: "same-origin", redirect: "error", mode: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body)});
    if (response.status !== expected) {
      const error = new Error("http");
      error.status = response.status;
      try { error.reason = (await response.json()).error; } catch (_) { /* no body */ }
      throw error;
    }
    if (expected === 202) { await response.text(); return null; }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function adoptSession(value) {
  validateSession(value);
  P.session = value;
  S.session = value;
  P.seq = Math.max(P.seq, value.next_command_seq);
}

function secureId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// Commands go out one after another (the host wants rising sequence numbers).
function send(action, params, onResult = null) {
  const run = async () => {
    const session = P.session, state = P.state;
    if (!session?.station || !state || state.role !== session.station) return false;
    const id = secureId();
    const body = {protocol: 2, id, seq: P.seq, station: session.station,
      station_generation: session.station_generation, active_generation: session.active_generation,
      world_session: state.session, world_epoch: state.epoch, resource_revision: state.revision,
      action, params};
    try {
      await api("/commands", {method: "POST", body, expected: 202});
      P.seq += 1;
    } catch (error) {
      if (error.status === 401) return unpaired("phone_link_expired");
      onResult?.({status: "rejected", reasoncode: error.reason || "http"});
      return false;
    }
    if (onResult) P.waiting.set(id, {seq: body.seq, onResult, until: performance.now() + RESULT_WAIT_MS});
    return true;
  };
  P.commands = P.commands.then(run, run);
  return P.commands;
}

async function pollResults() {
  if (!P.waiting.size) return;
  try {
    const payload = await api("/results");
    if (!exactKeys(payload, ["protocol", "results"]) || payload.protocol !== 2 || !boundedArray(payload.results, 64)) return;
    for (const result of payload.results) {
      const pending = P.waiting.get(result?.id);
      if (!pending || !exactKeys(result, ["id", "seq", "status", "reasoncode"]) || result.seq !== pending.seq ||
          !["applied", "rejected"].includes(result.status)) continue;
      P.waiting.delete(result.id);
      pending.onResult(result);
    }
  } catch (_) { /* next round */ }
  const now = performance.now();
  for (const [id, pending] of P.waiting) if (now > pending.until) P.waiting.delete(id);
}

async function pollSession() {
  if (!P.session) return;
  try {
    adoptSession(await api("/session"));
    // A phone whose role another phone holds asks for it; the host grants it
    // when it is free.
    const wanted = P.session.station ?? preferredRole();
    if (P.session.station === null && !P.session.stations[wanted].requested)
      adoptSession(await api("/stations/request", {method: "POST", body: {station: wanted}}));
  } catch (error) {
    if (error.status === 401) unpaired("phone_link_expired");
  }
}

async function pollState() {
  if (!P.session) return;
  try {
    const state = await api("/state");
    validateV2State(state);
    P.state = state;
    P.view = state.role && lookoutRoles.includes(state.role) ? state[state.role] : null;
    // The periscope starts where the boat has it trained.
    if (P.view?.side === "boat" && P.scopeSent === null && finite(P.view.relative_deg)) {
      P.relative = P.view.relative_deg;
      P.scopeSent = P.view.relative_deg;
    }
    P.lastState = performance.now();
    P.stateFailures = 0;
    renderWatch();
  } catch (error) {
    if (error.status === 401) return unpaired("phone_link_expired");
    if (error.status === 403) { P.state = null; P.view = null; renderWatch(); return; }
    P.stateFailures += 1;
    if (P.stateFailures >= 8) renderBlocked("phone_link_lost");
  }
}

function every(ms, task) {
  let busy = false;
  P.timers.push(setInterval(async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { await task(); } finally { busy = false; }
  }, ms));
}

// --- screens ------------------------------------------------------------------

const preferredRole = () => document.querySelector("input[name=role]:checked")?.value || "lookout";

function showPairing(message = null) {
  $("phone-watch").hidden = true;
  $("phone-pair").hidden = false;
  $("phone-pair-error").textContent = message ? t(message) : "";
}

function unpaired(message) {
  P.session = null;
  S.session = null;
  P.state = null;
  P.view = null;
  P.waiting.clear();
  stopGyro();
  P.wakeLock?.release?.().catch(() => {});
  P.wakeLock = null;
  showPairing(message);
  return false;
}

async function startWatch() {
  $("phone-pair").hidden = true;
  $("phone-watch").hidden = false;
  $("phone-mark").hidden = P.session.station !== "uboot_lookout";
  if (!speechAvailable()) {
    $("phone-speak").disabled = true;
    $("phone-heard").textContent = t("phone_speech_unavailable");
  }
  if (!("DeviceOrientationEvent" in window)) $("phone-gyro").disabled = true;
  keepAwake();
  renderWatch();
}

async function keepAwake() {
  try { if (!P.wakeLock && navigator.wakeLock) P.wakeLock = await navigator.wakeLock.request("screen"); } catch (_) { /* optional */ }
}

function renderBlocked(key) {
  $("phone-blocked").hidden = !key;
  if (key) $("phone-blocked-text").textContent = t(key);
}

function renderWatch() {
  if ($("phone-watch").hidden) return;
  const session = P.session, view = P.view;
  let blocked = null;
  if (!session?.station) blocked = "phone_waiting_role";
  else if (!P.state || P.state.role === null) blocked = session.station === "uboot_lookout" ? "phone_no_boat" : "phone_no_mission";
  else if (!view?.available) blocked = session.station === "uboot_lookout" ? "phone_scope_down" : "phone_unavailable";
  renderBlocked(blocked);
  for (const id of ["phone-speak", "phone-zoom", "phone-center", "phone-mark"])
    if (id !== "phone-speak" || speechAvailable()) $(id).disabled = Boolean(blocked);
  const calls = $("phone-calls");
  const rows = (view?.calls || []).map((row) => {
    const item = document.createElement("li");
    item.className = row.confirmed ? "confirmed" : "";
    item.textContent = `${row.confirmed ? "✓" : "✗"} ${t(`phone_category_${row.category}`)} ${three(row.bearing)}°${rangeText(row.range_nm)}`;
    return item;
  });
  const signature = rows.map((row) => row.textContent).join("|");
  if (calls.dataset.signature !== signature) {
    calls.replaceChildren(...rows);
    calls.dataset.signature = signature;
  }
}

function renderCategories(bearing = null, rangeNm = null) {
  const panel = $("phone-categories");
  if (bearing === null) {
    panel.hidden = true;
    P.pick = null;
    return;
  }
  P.pick = {bearing, rangeNm};
  const title = document.createElement("p");
  title.textContent = t("phone_pick_category", {bearing: three(bearing)}) + rangeText(rangeNm);
  const buttons = CATEGORIES.map((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = t(`phone_category_${category}`);
    button.addEventListener("click", () => {
      renderCategories();
      call(category, bearing, rangeNm);
    });
    return button;
  });
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = t("phone_cancel");
  cancel.addEventListener("click", () => renderCategories());
  panel.replaceChildren(title, ...buttons, cancel);
  panel.hidden = false;
  buttons[0].focus();
}

// --- the eyepiece ---------------------------------------------------------------

const side = () => P.view?.side || (P.session?.station === "uboot_lookout" ? "boat" : "frigate");
const course = () => P.view?.course ?? 0;
const bearing = () => wrap360(course() + P.relative);
const fov = () => P.view ? P.view.fov_deg / P.view.powers[Math.min(P.power, P.view.powers.length - 1)] : 16;

function setRelative(value) {
  P.relative = wrap360(value);
  const [low, high] = ELEVATION[side()];
  P.elevation = Math.max(low, Math.min(high, P.elevation));
  trainScope();
}

// The boat's periscope turns on the host: the phone sends where it looks.
function trainScope(force = false) {
  if (P.session?.station !== "uboot_lookout" || !P.view?.available) return;
  const now = performance.now();
  if (P.scopeBusy || (!force && now - P.scopeAt < SCOPE_SEND_MS)) return;
  const target = Math.round(P.relative * 10) / 10 % 360;
  if (P.scopeSent !== null && Math.abs(wrap180(target - P.scopeSent)) < .5) return;
  P.scopeBusy = true;
  P.scopeAt = now;
  send("uboot_scope_bearing", {relative_deg: target}).then((sent) => {
    if (sent) P.scopeSent = target;
  }).finally(() => { P.scopeBusy = false; });
}

function draw(now) {
  requestAnimationFrame(draw);
  const canvas = $("phone-view");
  if ($("phone-watch").hidden || !P.view) return;
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const g = canvas.getContext("2d");
  g.setTransform(ratio, 0, 0, ratio, 0, 0);
  const view = P.view, fovDeg = fov(), line = bearing();
  const [offset, tilt] = view.side === "frigate" ? viewMotion(view.motion_pitch, view.motion_roll, P.relative)
    : [view.horizon_offset, view.horizon_tilt];
  drawSightView(g, width, height, {...view, bearing: line, fov_deg: fovDeg, horizon_offset: offset, horizon_tilt: tilt,
    elevation_deg: P.elevation, stabilized: false,
    optics_label: t("optics_status", {elevation: `${P.elevation >= 0 ? "+" : ""}${Math.round(P.elevation)}`, fov: Math.round(fovDeg)})},
    now / 1000, "13px ui-monospace, monospace");
  // Called sightings carry a small mark above them.
  g.fillStyle = "rgb(150, 255, 205)";
  for (const row of view.outlines) {
    if (!row.called) continue;
    const off = wrap180(row.bearing - line);
    if (Math.abs(off) > fovDeg / 2) continue;
    const x = width / 2 + off * width / fovDeg;
    g.beginPath(); g.moveTo(x - 6, 30); g.lineTo(x + 6, 30); g.lineTo(x, 38); g.fill();
  }
  const text = `${three(line)}°`;
  if ($("phone-bearing").textContent !== text) $("phone-bearing").textContent = text;
  if (P.status && now - P.status.at > 6000) setStatus(null);
  trainScope();
}

// --- calls ------------------------------------------------------------------------

function call(category, callBearing, rangeNm) {
  const params = {category, bearing: Math.round(wrap360(callBearing) * 10) / 10 % 360,
    range_nm: finite(rangeNm) && rangeNm > 0 && rangeNm <= 60 ? rangeNm : null};
  const what = {category: t(`phone_category_${category}`), bearing: three(params.bearing)};
  setStatus("phone_call_sent", what);
  send("lookout_call", params, (result) => {
    if (result.status === "applied") {
      setStatus("phone_call_confirmed", what, "good");
      navigator.vibrate?.(80);
    } else {
      setStatus(result.reasoncode === "lookout_not_confirmed" ? "phone_call_not_confirmed" : "phone_call_rejected", what, "bad");
      navigator.vibrate?.([40, 60, 40]);
    }
  });
}

// The nearest outline to a tapped bearing lends its measured range (boat).
function tapped(x) {
  const canvas = $("phone-view"), fovDeg = fov();
  const at = wrap360(bearing() + (x - canvas.clientWidth / 2) * fovDeg / canvas.clientWidth);
  const near = (P.view?.outlines || []).map((row) => [Math.abs(wrap180(row.bearing - at)) - row.span_deg / 2, row])
    .filter(([gap]) => gap < Math.max(1.5, fovDeg / 20)).sort((a, b) => a[0] - b[0])[0]?.[1];
  renderCategories(near ? near.bearing : at, near?.range_nm ?? null);
}

function heard(alternatives) {
  const context = {course: course(), viewBearing: bearing()};
  const parsed = alternatives.map((text) => [text, parseReport(text, context)]).find(([, report]) => report);
  if (!parsed) {
    $("phone-heard").textContent = t("phone_heard", {text: alternatives[0] || ""});
    setStatus("phone_not_understood", {}, "bad");
    return;
  }
  const [text, report] = parsed;
  $("phone-heard").textContent = t("phone_heard", {text});
  call(report.category, report.bearing, report.range_nm);
}

function toggleListening() {
  if (P.listening) { P.listening.stop(); return; }
  try {
    P.listening = createListener({language: S.language, onHeard: heard,
      onEnd: () => { P.listening = null; $("phone-speak").setAttribute("aria-pressed", "false"); $("phone-speak").textContent = t("phone_speak"); },
      onError: (error) => setStatus(error === "not-allowed" || error === "service-not-allowed" ? "phone_mic_denied" : "phone_speech_failed", {}, "bad")});
    $("phone-speak").setAttribute("aria-pressed", "true");
    $("phone-speak").textContent = t("phone_listening");
  } catch (_) {
    P.listening = null;
    setStatus("phone_speech_failed", {}, "bad");
  }
}

// --- gyroscope and swipe ------------------------------------------------------------

function oriented(event) {
  const sight = lineOfSight(event.alpha, event.beta, event.gamma);
  if (!sight) return;
  P.heading = sight.heading;
  if (P.offset === null) P.offset = P.relative - sight.heading;   // no jump when switched on
  const [low, high] = ELEVATION[side()];
  P.elevation = Math.max(low, Math.min(high, sight.elevation));
  setRelative(sight.heading + P.offset);
}

async function startGyro() {
  try {
    if (typeof DeviceOrientationEvent.requestPermission === "function" &&
        await DeviceOrientationEvent.requestPermission() !== "granted") throw new Error("denied");
  } catch (_) {
    setStatus("phone_gyro_denied", {}, "bad");
    return;
  }
  P.gyro = true;
  P.offset = null;
  window.addEventListener("deviceorientation", oriented);
  $("phone-gyro").setAttribute("aria-pressed", "true");
  // No event within a second: the phone has no gyroscope (or blocks it).
  setTimeout(() => { if (P.gyro && P.heading === null) { stopGyro(); setStatus("phone_gyro_unavailable", {}, "bad"); } }, 1500);
}

function stopGyro() {
  P.gyro = false;
  P.heading = null;
  window.removeEventListener("deviceorientation", oriented);
  $("phone-gyro").setAttribute("aria-pressed", "false");
}

function wireView() {
  const canvas = $("phone-view");
  canvas.addEventListener("pointerdown", (event) => {
    try { canvas.setPointerCapture(event.pointerId); } catch (_) { /* a pointer already gone */ }
    P.drag = {id: event.pointerId, x: event.clientX, y: event.clientY, x0: event.clientX, y0: event.clientY, at: performance.now()};
  });
  canvas.addEventListener("pointermove", (event) => {
    const drag = P.drag;
    if (!drag || drag.id !== event.pointerId) return;
    const perPx = fov() / canvas.clientWidth, dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    drag.x = event.clientX;
    drag.y = event.clientY;
    if (Math.hypot(event.clientX - drag.x0, event.clientY - drag.y0) < TAP_PX) return;
    // Drag the scene: right swings the view left.  With the gyroscope on the
    // swipe shifts its calibration.
    if (P.gyro && P.offset !== null) P.offset -= dx * perPx;
    setRelative(P.relative - dx * perPx);
    if (!P.gyro) {
      const [low, high] = ELEVATION[side()];
      P.elevation = Math.max(low, Math.min(high, P.elevation + dy * perPx));
    }
  });
  const end = (event) => {
    const drag = P.drag;
    if (!drag || drag.id !== event.pointerId) return;
    P.drag = null;
    if (event.type === "pointerup" && Math.hypot(event.clientX - drag.x0, event.clientY - drag.y0) < TAP_PX &&
        performance.now() - drag.at < TAP_MS && P.view?.available) tapped(event.clientX - canvas.getBoundingClientRect().left);
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  $("phone-gyro").addEventListener("click", () => (P.gyro ? stopGyro() : startGyro()));
  $("phone-center").addEventListener("click", () => {
    if (P.gyro && P.heading !== null) P.offset = -P.heading;
    P.elevation = 0;
    setRelative(0);
  });
  $("phone-zoom").addEventListener("click", () => {
    P.power = P.view ? (P.power + 1) % P.view.powers.length : 0;
  });
  $("phone-mark").addEventListener("click", () => {
    trainScope(true);
    send("uboot_scope_mark", {}, (result) => setStatus(result.status === "applied" ? "phone_mark_done" : "phone_mark_rejected", {},
      result.status === "applied" ? "good" : "bad"));
  });
  $("phone-speak").addEventListener("click", toggleListening);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") renderCategories(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && P.session) { P.wakeLock = null; keepAwake(); } });
}

// --- start ------------------------------------------------------------------------------

function wirePairing() {
  wirePairCodeInput($("phone-code"));
  $("phone-language").addEventListener("change", () => loadLanguage($("phone-language").value).catch(() => {}));
  $("phone-pair-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("phone-pair-submit").disabled = true;
    $("phone-pair-error").textContent = "";
    const code = normalizePairCode($("phone-code").value);
    try {
      adoptSession(await api("/pair", {method: "POST", body: {code,
        name: $("phone-name").value.trim(), role: preferredRole()}}));
      $("phone-code").value = "";
      await startWatch();
    } catch (error) {
      // Only the pairing route's own answer means a wrong code; a bare 403
      // is the listener refusing this address (Host/Origin).
      $("phone-pair-error").textContent = t(error.status === 403 ? (error.reason === "invalid_code" ? "phone_pair_code" : "pair_address") : error.status === 429 ?
        (error.reason === "session_limit" ? "phone_pair_full" : "phone_pair_rate") : "phone_pair_failed", {code});
    } finally {
      $("phone-pair-submit").disabled = false;
    }
  });
}

async function boot() {
  const language = (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  try { await loadLanguage(language); } catch (_) { /* the page still pairs in plain keys */ }
  // Gyroscope and microphone need a secure context (the HTTPS address).
  $("phone-insecure").hidden = window.isSecureContext;
  wirePairing();
  wireView();
  every(STATE_POLL_MS, pollState);
  every(SESSION_POLL_MS, pollSession);
  every(RESULT_POLL_MS, pollResults);
  requestAnimationFrame(draw);
  try {
    const session = await api("/session");
    adoptSession(session);
    const held = session.station ?? session.requested_station;
    if (held && lookoutRoles.includes(held)) {
      const radio = document.querySelector(`input[name=role][value=${held}]`);
      if (radio) radio.checked = true;
      await startWatch();
      return;
    }
    P.session = null;
    S.session = null;
  } catch (_) { /* not paired yet */ }
  showPairing();
}

boot();
