import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { request } from "../net/request.js";
import { sendStationAction } from "../net/commands.js";
import { stationActionAvailable } from "../state/availability.js";
import { boundedArray, exactKeys } from "../state/schema.js";
import { node } from "./dom.js";
import { keyLabel } from "../input/station-keys.js";

// ---- Executive officer (optional language model) -----------------------------
// Mirrors src/core/game_advisor.py: situation report, question, typed order,
// classification help and station briefing, asked at /api/v2/advisor and
// answered by the host from this side's own picture.  A typed order comes
// back as ordinary station commands; they are sent only after the player
// confirms, one after the other, through the normal command pipeline and
// only from a station allowed to give them.  Without the model the button
// stays hidden and nothing here runs.
const MODES = ["situation", "question", "order", "classify", "briefing"];
const TEXT_MODES = new Set(["question", "order"]);
const STATUSES = new Set(["pending", "done", "failed"]);
const TEXT_MAX = 300;
const POLL_MS = 1500;
const advisor = {mode: "situation", doc: null, timer: null, applied: new Set(), discarded: new Set(), message: null};

function validCommand(row) {
  return exactKeys(row, ["type", "value", "action", "params", "stations"]) && typeof row.type === "string" &&
    ["number", "boolean"].includes(typeof row.value) && typeof row.action === "string" &&
    row.params !== null && typeof row.params === "object" && !Array.isArray(row.params) &&
    boundedArray(row.stations, 32) && row.stations.every((name) => typeof name === "string");
}
function validEntry(row) {
  return exactKeys(row, ["seq", "kind", "question", "answer", "status", "error", "proposal"]) &&
    Number.isInteger(row.seq) && typeof row.kind === "string" && typeof row.question === "string" &&
    typeof row.answer === "string" && STATUSES.has(row.status) && (row.error === null || typeof row.error === "string") &&
    (row.proposal === null || boundedArray(row.proposal, 4) && row.proposal.every(validCommand));
}
function validReport(value) {
  return value === null || value === undefined ||
    exactKeys(value, ["status", "text", "error"]) && STATUSES.has(value.status) && typeof value.text === "string" &&
    (value.error === null || typeof value.error === "string");
}
export function validAdvisor(value) {
  return exactKeys(value, ["protocol", "available", "talk", "pending", "reason", "log", "report"]) && value.protocol === 2 &&
    typeof value.available === "boolean" && typeof value.talk === "boolean" && typeof value.pending === "boolean" &&
    (value.reason === null || typeof value.reason === "string") &&
    boundedArray(value.log, 12) && value.log.every(validEntry) && validReport(value.report);
}

function errorText(code) {
  return t("advisor_failed", {reason: t(`advisor_error_${code}`) || code});
}
function valueText(value) {
  if (value === true) return t("advisor_on");
  if (value === false) return t("advisor_off_value");
  return String(value);
}
function stationName(name) { return t(`station_${name}`) || name; }

function entryNode(entry) {
  const item = node("li", undefined, "advisor-entry");
  const kind = t(`advisor_mode_${entry.kind}`) || entry.kind;
  item.append(node("p", entry.question ? `${kind}: ${entry.question}` : `${kind}:`, "advisor-question"));
  if (entry.status === "pending") { item.append(node("p", t("advisor_pending"), "advisor-state")); return item; }
  if (entry.status === "failed") item.append(node("p", errorText(entry.error || "network"), "advisor-state"));
  if (entry.answer) item.append(node("p", entry.answer, "advisor-answer"));
  if (entry.status !== "done" || !entry.proposal) return item;
  const list = node("ul", undefined, "advisor-commands");
  for (const command of entry.proposal) {
    const row = node("li", t(`advisor_command_${command.type}`, {value: valueText(command.value)}));
    if (!command.stations.includes(S.session?.station)) {
      row.append(node("span", ` ${t("advisor_other_station", {stations: command.stations.map(stationName).join(", ")})}`, "fine"));
    }
    list.append(row);
  }
  item.append(list);
  if (advisor.applied.has(entry.seq)) { item.append(node("p", t("advisor_order_applied"), "advisor-state")); return item; }
  if (advisor.discarded.has(entry.seq)) { item.append(node("p", t("advisor_order_discarded"), "advisor-state")); return item; }
  const actions = node("div", undefined, "host-dialog-actions");
  const give = node("button", t("advisor_give"));
  give.type = "button";
  give.disabled = !entry.proposal.some((command) => command.stations.includes(S.session?.station));
  give.addEventListener("click", () => giveOrder(entry));
  const drop = node("button", t("advisor_discard"));
  drop.type = "button";
  drop.addEventListener("click", () => { advisor.discarded.add(entry.seq); render(); });
  actions.append(give, drop);
  item.append(actions);
  return item;
}

// One command at a time: the pipeline holds one pending command per client.
async function waitFor(check, limitMs) {
  const until = performance.now() + limitMs;
  while (!check() && performance.now() < until) await new Promise((resolve) => setTimeout(resolve, 150));
  return check();
}
// A command counts as given only once the host applied it; one the host
// dropped (the world stepped on while it waited) is sent again.
async function sendApplied(command) {
  for (let attempt = 0; attempt < 3; attempt++) {
    if (!(await waitFor(stationActionAvailable, 8000))) return false;
    await sendStationAction(command.action, {...command.params});
    if (!(await waitFor(() => !S.pending, 8000))) return false;
    if (S.commandMessage?.status === "applied") return true;
  }
  return false;
}
async function giveOrder(entry) {
  advisor.applied.add(entry.seq);
  render();
  let given = 0, skipped = 0;
  for (const command of entry.proposal) {
    if (command.stations.includes(S.session?.station) && await sendApplied(command)) given += 1;
    else skipped += 1;
  }
  advisor.message = t(skipped ? "advisor_order_partial" : "advisor_order_done", {count: given});
  render();
}

function render() {
  const dialog = $("advisor-dialog");
  if (!dialog?.open) return;
  const doc = advisor.doc;
  for (const button of dialog.querySelectorAll("[data-advisor-mode]")) {
    const active = button.dataset.advisorMode === advisor.mode;
    button.setAttribute("aria-pressed", String(active));
    const label = `${MODES.indexOf(button.dataset.advisorMode) + 1} ${t(`advisor_mode_${button.dataset.advisorMode}`)}`;
    if (button.textContent !== label) button.textContent = label;
  }
  $("advisor-help").textContent = t(`advisor_help_${advisor.mode}`);
  const field = $("advisor-text");
  const textMode = TEXT_MODES.has(advisor.mode);
  // The field keeps focus and what was typed; only its visibility changes.
  field.hidden = !textMode;
  $("advisor-send").textContent = t(textMode ? "advisor_send" : `advisor_send_${advisor.mode}`);
  const off = doc !== null && !doc.available;
  $("advisor-send").disabled = off || doc?.pending === true;
  const talkButton = $("advisor-talk");
  talkButton.hidden = !(doc?.talk === true);
  talkButton.textContent = t(talk.recording ? "advisor_talk_send" : "advisor_talk");
  talkButton.setAttribute("aria-pressed", String(talk.recording));
  talkButton.title = t("advisor_talk_hint");
  const cap = keyLabel("Shift+Space");
  if (talkButton.dataset.keycap !== cap) talkButton.dataset.keycap = cap;
  let status = advisor.message || "";
  if (talk.recording) status = t("advisor_listening", {seconds: Math.round((performance.now() - talk.started) / 1000)});
  else if (off) status = t("advisor_unavailable");
  else if (doc?.reason) status = t(`advisor_reason_${doc.reason}`) || doc.reason;
  else if (doc?.pending) status = t("advisor_pending");
  $("advisor-status").textContent = status;
  const log = $("advisor-log");
  const key = JSON.stringify([doc?.log ?? [], [...advisor.applied], [...advisor.discarded], S.language, S.session?.station]);
  if (log.dataset.key !== key) {
    log.replaceChildren(...(doc?.log ?? []).map(entryNode));
    log.dataset.key = key;
    log.scrollTop = log.scrollHeight;
  }
}

async function poll() {
  clearTimeout(advisor.timer);
  advisor.timer = null;
  if (!$("advisor-dialog").open) return;
  try {
    const value = await request("/advisor");
    if (validAdvisor(value)) advisor.doc = value;
  } catch (_) { /* keep the last view; the next poll retries */ }
  render();
  if ($("advisor-dialog").open) advisor.timer = setTimeout(poll, POLL_MS);
}

async function send() {
  const text = TEXT_MODES.has(advisor.mode) ? $("advisor-text").value.trim() : "";
  if (TEXT_MODES.has(advisor.mode) && (!text || text.length > TEXT_MAX)) {
    advisor.message = t("advisor_reason_invalid_value");
    render();
    return;
  }
  advisor.message = null;
  try {
    await request("/advisor", {method: "POST", body: {kind: advisor.mode, text}, expected: 202, csrf: S.session?.csrf});
    if (TEXT_MODES.has(advisor.mode)) $("advisor-text").value = "";
  } catch (error) {
    advisor.message = t(error.status === 429 ? "advisor_reason_llm_busy" : "advisor_rejected");
  }
  poll();
}

// ---- The talk key (Shift+Space, as on the uConsole) ------------------------------
// Held: the question is recorded in /noise-mic.js (the one place that opens the
// microphone) and posted to /api/v2/advisor/speech; the host's speech input
// turns it into text and the executive officer answers it like a typed
// question. A short tap starts the recording and the next press sends it.
const TAP_MS = 350;
const talk = {recording: false, started: 0, pressedAt: null, timer: null};

function talkReady() {
  return advisor.doc?.available === true && advisor.doc?.talk === true && isEligible();
}
function talkPress() {
  if (talk.recording) {
    if (talk.pressedAt === null) talkStop();
    return;
  }
  if (!talkReady()) return;
  if (!$("advisor-dialog").open) { advisor.mode = "question"; open(); }
  talk.recording = true;
  talk.started = performance.now();
  talk.pressedAt = talk.started;
  advisor.message = null;
  window.dispatchEvent(new CustomEvent("u-jagd-talk-start"));
  clearInterval(talk.timer);
  talk.timer = setInterval(render, 500);
  render();
}
function talkRelease() {
  if (talk.pressedAt === null) return;
  const held = performance.now() - talk.pressedAt;
  talk.pressedAt = null;
  if (held >= TAP_MS) talkStop();
}
function talkStop() {
  talk.recording = false;
  talk.pressedAt = null;
  clearInterval(talk.timer);
  talk.timer = null;
  window.dispatchEvent(new CustomEvent("u-jagd-talk-stop"));
  render();
}
function talkCancel() {
  if (!talk.recording) return;
  talk.recording = false;
  talk.pressedAt = null;
  clearInterval(talk.timer);
  talk.timer = null;
  window.dispatchEvent(new CustomEvent("u-jagd-talk-cancel"));
}
async function talkSend(audio) {
  if (!audio) { advisor.message = t("advisor_reason_stt_too_short"); render(); return; }
  try {
    await request("/advisor/speech", {method: "POST", body: {audio}, expected: 202, csrf: S.session?.csrf});
  } catch (error) {
    advisor.message = t(error.status === 429 ? "advisor_reason_llm_busy" : "advisor_rejected");
  }
  poll();
}
function onTalkEvent(event) {
  const detail = event.detail;
  if (!detail || typeof detail.state !== "string") return;
  if (detail.state === "done" && typeof detail.audio === "string") talkSend(detail.audio);
  else if (detail.state === "failed" && typeof detail.failure === "string" && /^mic_[a-z_]+$/.test(detail.failure)) {
    talk.recording = false;
    talk.pressedAt = null;
    clearInterval(talk.timer);
    advisor.message = t("advisor_mic_failed", {reason: t(detail.failure)});
    render();
  }
}
function isTalkKey(event) {
  return event.code === "Space" && event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey;
}

// The after-action report of the own side, for the debrief dialog.
export async function advisorReport() {
  try {
    const value = await request("/advisor");
    if (!validAdvisor(value) || !value.report) return null;
    if (value.report.status === "pending") return t("advisor_report_pending");
    if (value.report.status === "failed") return errorText(value.report.error || "network");
    return value.report.text;
  } catch (_) {
    return null;
  }
}

// The button shows during a mission on a station of either side, and only
// when the host has the language model switched on (checked now and then).
// The check shares the one request lane with commands: it runs once per
// world and then rarely, and never while a command or host action waits.
const CHECK_MS = 60000;
let lastCheck = -Infinity;
let checkedWorld = null;
async function checkAvailable() {
  lastCheck = performance.now();
  checkedWorld = `${S.v2State?.session}:${S.v2State?.epoch}`;
  try {
    const value = await request("/advisor");
    if (validAdvisor(value)) { advisor.doc = value; renderAdvisorButton(); }
  } catch (_) { /* stays as it was */ }
}
function isEligible() {
  const role = S.v2State?.role;
  return Boolean(role) && S.v2State?.phase === "live" && S.session?.grants?.command === true &&
    !["lookout", "uboot_lookout"].includes(role);
}
export function renderAdvisorButton() {
  const eligible = isEligible();
  const world = `${S.v2State?.session}:${S.v2State?.epoch}`;
  if (eligible && !$("advisor-dialog").open && !S.pending && S.hostPending == null &&
      (world !== checkedWorld || performance.now() - lastCheck > CHECK_MS)) checkAvailable();
  const show = eligible && advisor.doc?.available === true;
  $("advisor-open").hidden = !show;
  if (!eligible) talkCancel();
  if (!eligible && $("advisor-dialog").open) $("advisor-dialog").close();
}
function open() {
  const dialog = $("advisor-dialog");
  if (!dialog.open) { dialog.hidden = false; dialog.showModal(); }
  advisor.message = null;
  render();
  poll();
}
export function init() {
  const tabs = $("advisor-modes");
  tabs.replaceChildren(...MODES.map((mode) => {
    const button = node("button");
    button.type = "button";
    button.dataset.advisorMode = mode;
    button.addEventListener("click", () => { advisor.mode = mode; advisor.message = null; render(); });
    return button;
  }));
  $("advisor-text").maxLength = TEXT_MAX;
  $("advisor-open").addEventListener("click", open);
  $("advisor-close").addEventListener("click", () => $("advisor-dialog").close());
  $("advisor-send").addEventListener("click", send);
  $("advisor-text").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); send(); }
  });
  // The talk button: held like the key; Enter or Space on it toggles.
  const talkButton = $("advisor-talk");
  talkButton.addEventListener("pointerdown", (event) => { event.preventDefault(); talkPress(); });
  talkButton.addEventListener("pointerup", talkRelease);
  talkButton.addEventListener("pointercancel", talkRelease);
  talkButton.addEventListener("click", (event) => {
    if (event.detail !== 0) return;     // a pointer press was handled above
    if (talk.recording) talkStop(); else { talkPress(); talk.pressedAt = null; }
  });
  window.addEventListener("u-jagd-talk", onTalkEvent);
  // Before the station keys (capture): Shift+Space never reaches a station.
  window.addEventListener("keydown", (event) => {
    if (!isTalkKey(event)) return;
    if (!talkReady() && !talk.recording) return;
    event.preventDefault();
    event.stopPropagation();
    if (!event.repeat) talkPress();
  }, true);
  window.addEventListener("keyup", (event) => {
    if (talk.pressedAt === null || !(event.code === "Space" || event.key === "Shift")) return;
    event.preventDefault();
    talkRelease();
  }, true);
  window.addEventListener("blur", talkCancel);
  $("advisor-dialog").addEventListener("close", () => {
    clearTimeout(advisor.timer);
    advisor.timer = null;
    $("advisor-dialog").hidden = true;
  });
}
