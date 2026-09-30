import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { renderDisabledReasons, unavailable } from "./controls.js";
import { node } from "./dom.js";
import { simlogActive } from "./simlog.js";
import { sendHostAction } from "../net/host.js";
import { mutateStation, switchSoloSide } from "./lobby.js";
import { opforRoles } from "../core/base.js";

// ---- Solo host surface --------------------------------------------------
export const scenarioText = {s1_patrouille: "scenario_s1_patrouille", s2_doppeljagd: "scenario_s2_doppeljagd",
  s3_abfang: "scenario_s3_abfang", s4_zufall: "scenario_s4_zufall",
  s5_durchbruch: "scenario_s5_durchbruch", s6_aufklaerung: "scenario_s6_aufklaerung",
  s7_geleitzug: "scenario_s7_geleitzug"};
const hostPhaseAllows = (kind) => {
  const phase = S.hostView?.phase;
  return kind === "any" ? phase === "live" :
    phase === "live" || phase === "menu" || phase === "ended";
};
export function hostUnavailableReason(control) {
  if (!S.hostView) return unavailable("connection_syncing");
  if (S.hostPending) return unavailable("host_pending");
  if (!S.connected) return unavailable("connection_stale", {age: 0});
  if (S.hostView.phase === "blocked") return unavailable("host_blocked");
  if (control.dataset.slot && !S.hostView.slots.find((row) => String(row.slot) === control.dataset.slot)?.saved) {
    return unavailable("host_slot_empty");
  }
  return unavailable("host_phase");
}
export function renderHost() {
  const active = S.session?.host !== null && S.session !== null;
  $("host-bar").hidden = !active;
  $("web-admin-link").hidden = !active || !S.webHostAvailable;
  const menu = active && S.hostView?.phase === "menu";
  $("host-screen").hidden = !menu || simlogActive();
  if (!active) {
    for (const id of ["host-save", "host-load", "host-new",
                      "host-instructor", "host-side", "host-screen-new", "host-screen-load",
                      "host-new-start"]) $(id).disabled = true;
    for (const button of $("host-slot-list").querySelectorAll("button"))
      button.disabled = true;
    return;
  }
  const ready = Boolean(S.hostView) && !S.hostPending && S.connected;
  const any = ready && hostPhaseAllows("any");
  const replacing = ready && hostPhaseAllows("replacing");
  $("host-save").disabled = !any;
  $("host-load").disabled = !replacing;
  $("host-new").disabled = !replacing;
  $("host-instructor").disabled = !any;
  const boat = opforRoles.has(S.session.station);
  $("host-side").textContent = t(boat ? "host_play_frigate" : "host_play_opfor");
  $("host-side").disabled = !ready || S.stationMutation;
  $("host-screen-new").disabled = !replacing;
  $("host-screen-load").disabled = !replacing;
  $("host-new-start").disabled = !replacing;
  for (const button of $("host-slot-list").querySelectorAll("button")) {
    button.disabled = !replacing || (button.dataset.mode === "load" &&
      !S.hostView.slots.find((row) => String(row.slot) === button.dataset.slot)?.saved);
  }
  const text = S.hostMessage ? t(S.hostMessage.key, S.hostMessage.values ?? {}) : "";
  for (const id of ["host-status", "host-screen-status"]) {
    $(id).textContent = text;
    $(id).dataset.status = S.hostMessage?.status ?? "";
  }
}
function closeHostDialog(dialog) { if (dialog.open) dialog.close(); }
function openSlotDialog(mode) {
  if (!S.hostView) return;
  const dialog = $("host-slot-dialog");
  $("host-slot-title").textContent = t(mode === "save" ? "host_save_title" : "host_load_title");
  $("host-slot-note").textContent = t(mode === "save" ? "host_save_note" : "host_load_note");
  $("host-slot-list").replaceChildren(...S.hostView.slots.map((row) => {
    const item = node("li");
    const button = node("button", t(row.saved ? "host_slot_saved" : "host_slot_empty_label", {
      slot: row.slot, time: row.modified === null ? "" : new Date(row.modified * 1000).toLocaleString(S.language)}));
    button.type = "button";
    button.dataset.slot = String(row.slot);
    button.dataset.mode = mode;
    button.disabled = mode === "load" && !row.saved;
    button.addEventListener("click", () => {
      closeHostDialog(dialog);
      sendHostAction(mode === "save" ? "host_save" : "host_load", {slot: row.slot});
    });
    item.append(button);
    return item;
  }));
  renderDisabledReasons();
  dialog.hidden = false;
  if (!dialog.open) dialog.showModal();
  dialog.querySelector("button:not(:disabled)")?.focus();
}
function syncNewGameDifficulty() {
  const scenario = S.hostView?.scenarios.find((row) => row.key === $("host-new-scenario").value);
  const free = Boolean(scenario) && !scenario.fixed;
  for (const input of $("host-new-difficulty").querySelectorAll("input")) input.disabled = !free;
  $("host-new-difficulty-note").textContent = scenario
    ? t(free ? "host_new_difficulty_free" : "host_new_difficulty_fixed") : "";
}
function openNewGameDialog() {
  if (!S.hostView) return;
  const dialog = $("host-new-dialog");
  $("host-new-scenario").replaceChildren(...S.hostView.scenarios.map((row) => {
    const option = node("option", t(scenarioText[row.key] ?? "unknown"));
    option.value = row.key;
    return option;
  }));
  $("host-new-difficulty").replaceChildren(...S.hostView.difficulty_fields.map((field) => {
    const wrapper = node("div", undefined, "field");
    const inputId = `host-new-difficulty-${field.name}`;
    const label = node("label", t(`difficulty_${field.name}`));
    label.htmlFor = inputId;
    const input = node("input");
    input.type = "number";
    input.id = inputId;
    input.dataset.field = field.name;
    input.min = String(field.min);
    input.max = String(field.max);
    input.step = String(field.step);
    input.value = String(S.hostView.difficulty[field.name]);
    wrapper.append(label, input);
    return wrapper;
  }));
  $("host-new-scenario").value = S.hostView.scenario;
  $("host-new-world").value = S.hostView.world_mode;
  $("host-new-side").value = opforRoles.has(S.session?.station) ? "uboot" : "frigate";
  $("host-new-seed").value = "";
  syncNewGameDifficulty();
  renderDisabledReasons();
  dialog.hidden = false;
  if (!dialog.open) dialog.showModal();
  $("host-new-scenario").focus();
}

export function init() {
  for (const id of ["host-slot-dialog", "host-new-dialog", "instructor-dialog"]) {
    $(id).addEventListener("close", () => { $(id).hidden = true; });
  }
  $("host-slot-cancel").addEventListener("click", () => closeHostDialog($("host-slot-dialog")));
  $("host-new-cancel").addEventListener("click", () => closeHostDialog($("host-new-dialog")));
  $("instructor-cancel").addEventListener("click", () => closeHostDialog($("instructor-dialog")));
  $("host-new-scenario").addEventListener("change", syncNewGameDifficulty);
  $("host-new-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!$("host-new-form").reportValidity()) return;
    const params = {scenario: $("host-new-scenario").value, world_mode: $("host-new-world").value};
    const difficultyInputs = $("host-new-difficulty").querySelectorAll("input");
    if (difficultyInputs.length && !difficultyInputs[0].disabled) {
      const difficulty = {};
      for (const input of difficultyInputs) {
        const field = S.hostView.difficulty_fields.find((row) => row.name === input.dataset.field);
        difficulty[input.dataset.field] = field.kind === "int"
          ? parseInt(input.value, 10) : Number(input.value);
      }
      params.difficulty = difficulty;
    }
    if ($("host-new-seed").value.trim()) params.seed = $("host-new-seed").valueAsNumber;
    closeHostDialog($("host-new-dialog"));
    // The side is the solo session's: switch it first, the new world keeps it.
    const boat = opforRoles.has(S.session?.station);
    if (($("host-new-side").value === "uboot") !== boat) {
      await mutateStation("/stations/request", {station: boat ? "bridge" : "uboot"});
      if (opforRoles.has(S.session?.station) === boat) return;
    }
    sendHostAction("host_new_game", params);
  });
  for (const id of ["host-save"]) $(id).addEventListener("click", () => openSlotDialog("save"));
  for (const id of ["host-load", "host-screen-load"]) $(id).addEventListener("click", () => openSlotDialog("load"));
  for (const id of ["host-new", "host-screen-new"]) $(id).addEventListener("click", openNewGameDialog);
  $("host-side").addEventListener("click", switchSoloSide);
  $("host-instructor").addEventListener("click", () => {
    if (!S.hostView) return;
    const dialog = $("instructor-dialog");
    const sea = S.v2State?.environment?.sea_state;
    $("instructor-sea-state").value = String(Number.isSafeInteger(sea) ? sea : 3);
    $("instructor-event").value = "";
    dialog.hidden = false;
    if (!dialog.open) dialog.showModal();
    $("instructor-sea-state").focus();
  });
  $("instructor-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const seaState = Number($("instructor-sea-state").value);
    if (!Number.isSafeInteger(seaState) || seaState < 0 || seaState > 6) return;
    closeHostDialog($("instructor-dialog"));
    sendHostAction("host_instructor_environment", {sea_state: seaState,
      event: $("instructor-event").value || null});
  });
}
