import { S } from "../state/store.js";
import { $, opforRoles } from "../core/base.js";
import { on } from "../core/events.js";
import { t } from "../core/format.js";
import { node } from "./dom.js";
import { sendHostActionWhenReady } from "../net/host.js";
import { GENERATE_ATTEMPTS, UPLOAD_MAX_BYTES, fetchCatalog, fetchCoast, fetchLibrary, generatedKey,
  missionBundle, missionRequest } from "../net/missions.js";
import { secureId } from "../net/commands.js";
import { mutateStation } from "./lobby.js";

// Own missions of the solo host: the library (start, edit, download, upload,
// delete) and the Mission Planner, a form editor of the Mission Editor's
// format with a map preview. The host validates and stores every change
// (src/commander/mission_library.py); the page only edits a draft.
const WORLD = 500;
const SIDE_OBJECTIVES = {frigate: ["sink", "survive", "protect", "reach"], uboot: ["sink", "survive", "reach"]};
const TABS = ["overview", "world", "units", "objective", "events"];
let draft = null;          // the mission being edited
let editingKey = null;     // its stored key (null: a new mission)
let tab = "overview";
let pick = "player";       // what a map click places
let selectedUnit = null;   // ["exact" | "random_groups", index]
let pendingOverwrite = null;
let renderedRevision = null;

const lang = () => (S.language === "de" ? "de" : "en");
const clone = (value) => JSON.parse(JSON.stringify(value));
const opt = (value, label) => [value, label];
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function defaultMission() {
  const stamp = Date.now().toString(36);
  return {version: 1, key: `user.web_${stamp}`, name: t("missions_new_name"), description: "", seed: 1,
    side: "frigate", boat_id: "", world: {kind: "fixed", size_nm: WORLD, sectors: []},
    player: {x: 250, y: 250, course_deg: 0, speed_kn: 12},
    environment: {sea_state: 3, time_hour: 12, thermocline_depth_m: 80, weather: "clear"},
    units: {exact: [], random_groups: []},
    objective: {type: "survive", target_ids: [], time_limit_s: 3600, reach: {x: 250, y: 250, radius_nm: 2}},
    events: []};
}

function setStatus(key, values = {}, status = "") {
  $("missions-status").textContent = key ? t(key, values) : "";
  $("missions-status").dataset.status = status;
}
function issueText(issues) {
  return issues.slice(0, 6).map((row) => row[lang()]).join(" · ");
}

// ---- library ----------------------------------------------------------------
const objectiveText = (type) => t(`missions_objective_${type}`) || type;
const sideText = (side) => t(side === "uboot" ? "missions_side_uboot" : "missions_side_frigate");

function libraryBusy() {
  // Never rebuild the list under the pointer or the keyboard focus.
  const list = $("missions-list");
  return list.contains(document.activeElement) || list.matches(":hover");
}
function renderLibrary(force = false) {
  const library = S.missionLibrary;
  if (!library || (!force && library.revision === renderedRevision) || (!force && libraryBusy())) return;
  renderedRevision = library.revision;
  $("missions-empty").hidden = library.missions.length > 0;
  $("missions-truncated").hidden = !library.truncated;
  $("missions-list").replaceChildren(...library.missions.map((row) => {
    const item = node("li", undefined, `missions-row${row.valid ? "" : " invalid"}`);
    const head = node("div", undefined, "missions-row-head");
    head.append(node("strong", row.name || row.key), node("span", `${sideText(row.side)} · ${objectiveText(row.objective)}`, "fine"));
    item.append(head);
    const notes = row.valid ? row.hints.map((hint) => hint[lang()]) : [issueText(row.issues)];
    for (const note of notes) item.append(node("p", note, row.valid ? "missions-hint" : "missions-issue"));
    const actions = node("div", undefined, "missions-row-actions");
    const button = (key, handler, className) => {
      const element = node("button", t(key), className);
      element.type = "button";
      element.addEventListener("click", () => handler(row));
      actions.append(element);
      return element;
    };
    const start = button("missions_start", startMission, "primary");
    start.disabled = !row.valid || S.hostPending !== null;
    button("missions_edit", openEditor);
    button("missions_download", downloadMission);
    button("missions_delete", deleteMission, "danger");
    item.append(actions);
    return item;
  }));
}

async function refreshLibrary(force = false) {
  try {
    await fetchLibrary();
    renderLibrary(force);
  } catch (error) {
    setStatus("missions_result_failed", {}, "rejected");
  }
}

async function startMission(row) {
  closeDialog();
  // The side is the solo session's: switch it first, the new world keeps it.
  const boat = opforRoles.has(S.session?.station);
  if ((row.side === "uboot") !== boat) {
    await mutateStation("/stations/request", {station: boat ? "bridge" : "uboot"});
    if (opforRoles.has(S.session?.station) === boat) return;
  }
  // The dialog is already closed: a link that is briefly stale or still
  // resyncing must delay the start order, not drop it without a word.
  sendHostActionWhenReady("host_start_mission", {key: row.key});
}

function download(name, value) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {type: "application/json"});
  const link = node("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
function downloadMission(row) {
  download(`${row.key}.json`, missionBundle(row, S.missionLibrary));
  setStatus("missions_downloaded", {name: row.name}, "applied");
}

async function runRequest(op, fields, okKey, values = {}) {
  setStatus("missions_result_pending", {}, "pending");
  try {
    const outcome = await missionRequest(op, fields);
    if (outcome.status === "applied") {
      setStatus(okKey, values, "applied");
      pendingOverwrite = null;
      renderLibrary(true);
      return outcome;
    }
    if (outcome.reason === "exists") {
      pendingOverwrite = {op, fields, okKey, values};
      setStatus("missions_result_exists", {}, "rejected");
      $("missions-overwrite").hidden = false;
      return outcome;
    }
    setStatus(outcome.issues.length ? "missions_result_issues" : "missions_result_failed",
      {issues: issueText(outcome.issues)}, "rejected");
    return outcome;
  } catch (error) {
    setStatus(error.reason === "too_large" ? "missions_too_large" : "missions_result_failed", {}, "rejected");
    return null;
  }
}

// A mission from a few words (optional language model on the host): stored
// under a fresh key, then opened in the planner for checking.
async function generateMission() {
  const text = $("missions-generate-text").value.trim();
  if (!text) return;
  const button = $("missions-generate");
  button.disabled = true;
  setStatus("missions_generate_pending", {}, "pending");
  try {
    const id = secureId();
    const outcome = await missionRequest("generate", {id, request: text, side: $("missions-generate-side").value},
      GENERATE_ATTEMPTS);
    if (outcome.status === "applied") {
      $("missions-generate-text").value = "";
      renderLibrary(true);
      const row = S.missionLibrary?.missions.find((item) => item.key === generatedKey(id));
      setStatus("missions_generate_done", {}, "applied");
      if (row) openEditor(row);
    } else {
      const reason = t(`missions_generate_reason_${outcome.reason}`) || t("missions_generate_failed");
      setStatus("missions_generate_rejected", {reason, issues: issueText(outcome.issues)}, "rejected");
    }
  } catch (_) {
    setStatus("missions_generate_failed", {}, "rejected");
  } finally {
    button.disabled = false;
  }
}

async function deleteMission(row) {
  if (!window.confirm(t("missions_delete_confirm", {name: row.name}))) return;
  await runRequest("delete", {key: row.key}, "missions_deleted", {name: row.name});
}

function uploadFile(file) {
  if (!file) return;
  if (file.size > UPLOAD_MAX_BYTES) { setStatus("missions_too_large", {}, "rejected"); return; }
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    let value;
    try { value = JSON.parse(String(reader.result)); } catch (_) {
      setStatus("missions_upload_invalid", {}, "rejected");
      return;
    }
    // A bare mission file is wrapped into the shared bundle format.
    const bundle = value && value.format === "u-jagd.editor-bundle" ? value
      : {format: "u-jagd.editor-bundle", version: 1, missions: [value], units: []};
    runRequest("import", {bundle, overwrite: false}, "missions_uploaded", {name: file.name});
  });
  reader.addEventListener("error", () => setStatus("missions_upload_invalid", {}, "rejected"));
  reader.readAsText(file);
}

// ---- dialog -----------------------------------------------------------------
export async function openMissions() {
  if (!S.session?.host) return;
  const dialog = $("missions-dialog");
  showLibrary();
  setStatus("");
  dialog.hidden = false;
  if (!dialog.open) dialog.showModal();
  $("missions-new").focus();
  await refreshLibrary(true);
}
function closeDialog() {
  const dialog = $("missions-dialog");
  if (dialog.open) dialog.close();
}
function showLibrary() {
  $("missions-library").hidden = false;
  $("missions-editor").hidden = true;
  $("missions-head-actions").hidden = false;
  $("missions-overwrite").hidden = true;
  draft = null;
}

// ---- editor -----------------------------------------------------------------
async function openEditor(row) {
  try { await fetchCatalog(); } catch (_) { setStatus("missions_result_failed", {}, "rejected"); return; }
  draft = row ? clone(row.data) : defaultMission();
  draft.side ??= "frigate";
  draft.boat_id ??= "";
  draft.objective.reach ??= {x: 250, y: 250, radius_nm: 2};
  editingKey = row ? row.key : null;
  tab = "overview";
  pick = "player";
  selectedUnit = null;
  $("missions-library").hidden = true;
  $("missions-head-actions").hidden = true;
  $("missions-editor").hidden = false;
  $("missions-overwrite").hidden = true;
  setStatus("");
  renderEditor();
  $("missions-tab-overview").focus();
}

function profiles() {
  const own = (S.missionLibrary?.user_profiles ?? []).map((row) => ({...row, own: true}));
  return [...S.missionCatalog.profiles, ...own];
}
function profileOptions(select, value, filter = () => true) {
  const groups = new Map();
  for (const profile of profiles().filter(filter)) {
    const label = t(`missions_kind_${profile.kind}`) || profile.kind;
    if (!groups.has(label)) groups.set(label, node("optgroup"));
    groups.get(label).label = label;
    const option = node("option", profile.own ? `${profile.name} (${t("missions_own_unit")})` : profile.name);
    option.value = profile.key;
    groups.get(label).append(option);
  }
  select.replaceChildren(...groups.values());
  select.value = value;
}

function field(labelKey, input) {
  const wrapper = node("label", undefined, "missions-field");
  wrapper.append(node("span", t(labelKey)), input);
  return wrapper;
}
function numberInput(get, set, {min, max, step = "any"} = {}) {
  const input = node("input");
  input.type = "number";
  if (min !== undefined) input.min = String(min);
  if (max !== undefined) input.max = String(max);
  input.step = String(step);
  input.value = String(get());
  input.addEventListener("change", () => {
    const value = Number(input.value);
    if (input.value.trim() === "" || !Number.isFinite(value)) { input.value = String(get()); return; }
    set(min !== undefined || max !== undefined ? clamp(value, min ?? -Infinity, max ?? Infinity) : value);
    input.value = String(get());
    drawMap();
  });
  return input;
}
function textInput(get, set, maximum, multiline = false) {
  const input = node(multiline ? "textarea" : "input");
  if (!multiline) input.type = "text";
  input.maxLength = maximum;
  input.value = get();
  input.addEventListener("change", () => { set(input.value); drawMap(); });
  return input;
}
function selectInput(options, get, set, rerender = false) {
  const select = node("select");
  for (const [value, label] of options) {
    const option = node("option", label);
    option.value = value;
    select.append(option);
  }
  select.value = get();
  select.addEventListener("change", () => {
    set(select.value);
    if (rerender) renderEditor();
    else drawMap();
  });
  return select;
}
function addButton(key, handler, className = "") {
  const button = node("button", t(key), className);
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}
function nextId(prefix) {
  const used = new Set([...draft.units.exact, ...draft.units.random_groups, ...draft.events,
    ...draft.world.sectors].map((item) => item.id));
  let number = 1;
  while (used.has(`${prefix}${number}`)) number += 1;
  return `${prefix}${number}`;
}
function placementFields(target) {
  const box = node("div", undefined, "missions-grid");
  const sectorIds = draft.world.sectors.map((sector) => sector.id);
  box.append(field("missions_placement", selectInput(
    [opt("fixed", t("missions_placement_fixed")), ...(sectorIds.length ? [opt("sector", t("missions_placement_sector"))] : [])],
    () => target.placement.kind,
    (value) => {
      target.placement = value === "sector" ? {kind: "sector", sector: sectorIds[0]}
        : {kind: "fixed", x: 250, y: 250};
    }, true)));
  if (target.placement.kind === "sector") {
    box.append(field("missions_sector", selectInput(sectorIds.map((id) => [id, id]),
      () => target.placement.sector, (value) => { target.placement.sector = value; })));
  } else {
    box.append(field("missions_x", numberInput(() => target.placement.x, (v) => { target.placement.x = v; }, {min: 0, max: WORLD})),
      field("missions_y", numberInput(() => target.placement.y, (v) => { target.placement.y = v; }, {min: 0, max: WORLD})));
  }
  return box;
}

function overviewPanel() {
  const panel = node("div", undefined, "missions-grid");
  panel.append(
    field("missions_key", textInput(() => draft.key, (v) => { draft.key = v.trim(); }, 69)),
    field("missions_name", textInput(() => draft.name, (v) => { draft.name = v; }, 80)),
    field("missions_seed", numberInput(() => draft.seed, (v) => { draft.seed = Math.round(v); }, {min: 0, max: 2147483647, step: 1})),
    field("missions_player_side", selectInput([opt("frigate", t("missions_side_frigate")), opt("uboot", t("missions_side_uboot_long"))],
      () => draft.side, (value) => {
        draft.side = value;
        if (!SIDE_OBJECTIVES[value].includes(draft.objective.type)) draft.objective.type = "survive";
      }, true)));
  if (draft.side === "uboot") {
    const boats = draft.units.exact.filter((unit) => unit.side === "hostile" &&
      profiles().some((profile) => profile.key === unit.profile && profile.kind === "sub"));
    panel.append(field("missions_boat", selectInput([["", t("missions_boat_none")], ...boats.map((unit) => [unit.id, unit.id])],
      () => draft.boat_id, (value) => { draft.boat_id = value; })));
    panel.append(node("p", t("missions_boat_note"), "fine missions-wide"));
  }
  const description = field("missions_description", textInput(() => draft.description ?? "", (v) => { draft.description = v; }, 2000, true));
  description.classList.add("missions-wide");
  panel.append(description);
  return panel;
}

function worldPanel(catalog) {
  const panel = node("div", undefined, "missions-stack");
  const world = node("div", undefined, "missions-grid");
  world.append(field("missions_world", selectInput(
    [opt("fixed", t("missions_world_fixed")), ...catalog.sectors.map((row) =>
      [`sector:${row.index}`, `${t("missions_world_sector", {index: row.index})} ${row.countries.join(" / ")}`])],
    () => (draft.world.kind === "reference" ? draft.world.reference : "fixed"),
    (value) => {
      if (value === "fixed") { draft.world = {kind: "fixed", size_nm: WORLD, sectors: draft.world.sectors}; }
      else { draft.world = {kind: "reference", reference: value, size_nm: WORLD, sectors: draft.world.sectors}; }
    }, true)));
  world.append(
    field("missions_frigate_x", numberInput(() => draft.player.x, (v) => { draft.player.x = v; }, {min: 0, max: WORLD})),
    field("missions_frigate_y", numberInput(() => draft.player.y, (v) => { draft.player.y = v; }, {min: 0, max: WORLD})),
    field("missions_course", numberInput(() => draft.player.course_deg, (v) => { draft.player.course_deg = v; }, {min: 0, max: 359.999})),
    field("missions_speed", numberInput(() => draft.player.speed_kn, (v) => { draft.player.speed_kn = v; }, {min: 0, max: 31})),
    field("missions_sea_state", numberInput(() => draft.environment.sea_state, (v) => { draft.environment.sea_state = Math.round(v); }, {min: 0, max: 9, step: 1})),
    field("missions_time_hour", numberInput(() => draft.environment.time_hour, (v) => { draft.environment.time_hour = v; }, {min: 0, max: 23.999, step: 0.25})),
    field("missions_thermocline", numberInput(() => draft.environment.thermocline_depth_m, (v) => { draft.environment.thermocline_depth_m = v; }, {min: 0, max: 2000})),
    field("missions_weather", selectInput(catalog.weathers.map((w) => [w, t(`missions_weather_${w}`)]),
      () => draft.environment.weather, (value) => { draft.environment.weather = value; })));
  panel.append(world, node("h3", t("missions_sectors")));
  draft.world.sectors.forEach((sector, index) => {
    const row = node("div", undefined, "missions-grid missions-item");
    row.append(
      field("missions_id", textInput(() => sector.id, (v) => { sector.id = v.trim(); }, 64)),
      field("missions_x", numberInput(() => sector.x, (v) => { sector.x = v; }, {min: 0, max: WORLD})),
      field("missions_y", numberInput(() => sector.y, (v) => { sector.y = v; }, {min: 0, max: WORLD})),
      field("missions_width", numberInput(() => sector.width, (v) => { sector.width = v; }, {min: 0.01, max: WORLD})),
      field("missions_height", numberInput(() => sector.height, (v) => { sector.height = v; }, {min: 0.01, max: WORLD})),
      addButton("missions_remove", () => { draft.world.sectors.splice(index, 1); renderEditor(); }, "danger"));
    panel.append(row);
  });
  panel.append(addButton("missions_add_sector", () => {
    draft.world.sectors.push({id: nextId("sector"), x: 200, y: 200, width: 100, height: 100});
    renderEditor();
  }));
  return panel;
}

function unitPanel() {
  const panel = node("div", undefined, "missions-stack");
  const sides = [opt("hostile", t("missions_unit_hostile")), opt("neutral", t("missions_unit_neutral")), opt("friendly", t("missions_unit_friendly"))];
  panel.append(node("h3", t("missions_exact_units")));
  draft.units.exact.forEach((unit, index) => {
    const row = node("div", undefined, "missions-grid missions-item");
    const profile = node("select");
    profileOptions(profile, unit.profile);
    profile.addEventListener("change", () => { unit.profile = profile.value; drawMap(); });
    row.append(
      field("missions_id", textInput(() => unit.id, (v) => { unit.id = v.trim(); }, 64)),
      field("missions_profile", profile),
      field("missions_unit_side", selectInput(sides, () => unit.side, (v) => { unit.side = v; })),
      field("missions_course", numberInput(() => unit.course_deg ?? 0, (v) => { unit.course_deg = v; }, {min: 0, max: 359.999})),
      field("missions_speed", numberInput(() => unit.speed_kn ?? 0, (v) => { unit.speed_kn = v; }, {min: 0, max: 60})),
      field("missions_depth", numberInput(() => unit.depth_m ?? 60, (v) => { unit.depth_m = v; }, {min: 0, max: 2000})),
      placementFields(unit));
    const actions = node("div", undefined, "missions-item-actions");
    const place = addButton("missions_pick_unit", () => { pick = "unit"; selectedUnit = ["exact", index]; renderPickHint(); });
    place.setAttribute("aria-pressed", String(pick === "unit" && selectedUnit?.[0] === "exact" && selectedUnit[1] === index));
    actions.append(place, addButton("missions_remove", () => {
      draft.units.exact.splice(index, 1);
      draft.objective.target_ids = draft.objective.target_ids.filter((id) => id !== unit.id);
      if (draft.boat_id === unit.id) draft.boat_id = "";
      selectedUnit = null;
      renderEditor();
    }, "danger"));
    row.append(actions);
    panel.append(row);
  });
  panel.append(addButton("missions_add_unit", () => {
    const sub = profiles().find((row) => row.kind === "sub");
    draft.units.exact.push({id: nextId("unit"), profile: sub?.key ?? profiles()[0].key, side: "hostile",
      placement: {kind: "fixed", x: clamp(draft.player.x + 20, 0, WORLD), y: draft.player.y},
      course_deg: 0, speed_kn: 4, depth_m: 60});
    selectedUnit = ["exact", draft.units.exact.length - 1];
    pick = "unit";
    renderEditor();
  }));
  panel.append(node("h3", t("missions_groups")));
  draft.units.random_groups.forEach((group, index) => {
    const row = node("div", undefined, "missions-grid missions-item");
    const choices = node("select");
    choices.multiple = true;
    choices.size = 5;
    profileOptions(choices, null, (profile) => profile.kind !== "torpedo");
    for (const option of choices.querySelectorAll("option")) option.selected = group.profiles.includes(option.value);
    choices.addEventListener("change", () => {
      const picked = [...choices.selectedOptions].map((option) => option.value);
      if (picked.length) group.profiles = picked;
    });
    row.append(
      field("missions_id", textInput(() => group.id, (v) => { group.id = v.trim(); }, 64)),
      field("missions_group_profiles", choices),
      field("missions_unit_side", selectInput(sides, () => group.side, (v) => { group.side = v; })),
      field("missions_count_min", numberInput(() => group.count[0], (v) => { group.count[0] = Math.round(v); }, {min: 0, max: 100, step: 1})),
      field("missions_count_max", numberInput(() => group.count[1], (v) => { group.count[1] = Math.round(v); }, {min: 0, max: 100, step: 1})),
      placementFields(group));
    const actions = node("div", undefined, "missions-item-actions");
    actions.append(addButton("missions_pick_unit", () => { pick = "unit"; selectedUnit = ["random_groups", index]; renderPickHint(); }),
      addButton("missions_remove", () => {
        draft.units.random_groups.splice(index, 1);
        draft.objective.target_ids = draft.objective.target_ids.filter((id) => id !== group.id);
        draft.events = draft.events.filter((event) => event.target_id !== group.id || event.type !== "spawn");
        selectedUnit = null;
        renderEditor();
      }, "danger"));
    row.append(actions);
    panel.append(row);
  });
  panel.append(addButton("missions_add_group", () => {
    const sub = profiles().find((row) => row.kind === "sub");
    draft.units.random_groups.push({id: nextId("group"), profiles: [sub?.key ?? profiles()[0].key], side: "hostile",
      count: [1, 2], placement: {kind: "fixed", x: clamp(draft.player.x + 40, 0, WORLD), y: draft.player.y}});
    renderEditor();
  }));
  return panel;
}

function objectivePanel() {
  const panel = node("div", undefined, "missions-stack");
  const grid = node("div", undefined, "missions-grid");
  const objective = draft.objective;
  grid.append(
    field("missions_objective", selectInput(SIDE_OBJECTIVES[draft.side].map((type) => [type, objectiveText(type)]),
      () => objective.type, (value) => { objective.type = value; }, true)),
    field("missions_time_limit", numberInput(() => Math.round(objective.time_limit_s / 60),
      (v) => { objective.time_limit_s = Math.max(1, v) * 60; }, {min: 1, max: 10080, step: 1})));
  panel.append(grid, node("p", t(`missions_objective_note_${draft.side}_${objective.type}`), "fine"));
  if (objective.type === "reach") {
    const reach = node("div", undefined, "missions-grid");
    reach.append(
      field("missions_x", numberInput(() => objective.reach.x, (v) => { objective.reach.x = v; }, {min: 0, max: WORLD})),
      field("missions_y", numberInput(() => objective.reach.y, (v) => { objective.reach.y = v; }, {min: 0, max: WORLD})),
      field("missions_radius", numberInput(() => objective.reach.radius_nm, (v) => { objective.reach.radius_nm = v; }, {min: 0.1, max: 50})),
      addButton("missions_pick_reach", () => { pick = "reach"; renderPickHint(); }));
    panel.append(reach);
  }
  if (objective.type === "sink" || objective.type === "protect") {
    const list = node("fieldset", undefined, "missions-targets");
    list.append(node("legend", t("missions_targets")));
    for (const item of [...draft.units.exact, ...draft.units.random_groups]) {
      if (item.id === draft.boat_id) continue;
      const label = node("label");
      const box = node("input");
      box.type = "checkbox";
      box.checked = objective.target_ids.includes(item.id);
      box.addEventListener("change", () => {
        objective.target_ids = box.checked ? [...new Set([...objective.target_ids, item.id])]
          : objective.target_ids.filter((id) => id !== item.id);
      });
      label.append(box, node("span", item.id));
      list.append(label);
    }
    panel.append(list);
  }
  return panel;
}

function eventsPanel(catalog) {
  const panel = node("div", undefined, "missions-stack");
  const groups = draft.units.random_groups.map((group) => [group.id, group.id]);
  draft.events.forEach((event, index) => {
    const row = node("div", undefined, "missions-grid missions-item");
    row.append(
      field("missions_id", textInput(() => event.id, (v) => { event.id = v.trim(); }, 64)),
      field("missions_event_at", numberInput(() => Math.round(event.at_s / 60 * 10) / 10,
        (v) => { event.at_s = Math.max(0, v) * 60; }, {min: 0, max: 10080, step: 0.5})),
      field("missions_event_type", selectInput(catalog.events.filter((type) => type !== "spawn" || groups.length)
        .map((type) => [type, t(`missions_event_${type}`)]), () => event.type, (value) => {
        event.type = value;
        if (value === "spawn") event.target_id = groups[0]?.[0] ?? "";
        if (value === "weather") event.weather ??= "clear";
        if (value === "objective") event.action ??= "complete";
      }, true)));
    const message = field("missions_event_text", textInput(() => event.message ?? "", (v) => { event.message = v; }, 500));
    message.classList.add("missions-wide");
    if (event.type === "spawn") {
      row.append(field("missions_event_group", selectInput(groups, () => event.target_id, (v) => { event.target_id = v; })));
    } else if (event.type === "weather") {
      row.append(field("missions_weather", selectInput(catalog.weathers.map((w) => [w, t(`missions_weather_${w}`)]),
        () => event.weather, (v) => { event.weather = v; })));
    } else if (event.type === "objective") {
      row.append(field("missions_event_action", selectInput([opt("complete", t("missions_event_complete")), opt("fail", t("missions_event_fail"))],
        () => event.action, (v) => { event.action = v; })));
    }
    row.append(message, addButton("missions_remove", () => { draft.events.splice(index, 1); renderEditor(); }, "danger"));
    panel.append(row);
  });
  panel.append(addButton("missions_add_event", () => {
    draft.events.push({id: nextId("event"), at_s: 0, type: "message", message: t("missions_event_default")});
    renderEditor();
  }));
  return panel;
}

function renderPickHint() {
  const what = pick === "unit" && selectedUnit
    ? draft.units[selectedUnit[0]][selectedUnit[1]]?.id ?? "" : t(`missions_pick_${pick}_label`);
  $("missions-pick").textContent = t("missions_pick_hint", {what});
}

function renderEditor() {
  const catalog = S.missionCatalog;
  $("missions-editor-title").textContent = t(editingKey ? "missions_edit_title" : "missions_new_title", {name: draft.name});
  for (const name of TABS) {
    const button = $(`missions-tab-${name}`);
    button.setAttribute("aria-selected", String(name === tab));
    button.tabIndex = name === tab ? 0 : -1;
  }
  const panel = {overview: overviewPanel, world: () => worldPanel(catalog), units: unitPanel,
    objective: objectivePanel, events: () => eventsPanel(catalog)}[tab]();
  $("missions-panel").replaceChildren(panel);
  renderPickHint();
  drawMap();
}

function mapPoint(event) {
  const canvas = $("missions-map");
  const rect = canvas.getBoundingClientRect();
  return [clamp((event.clientX - rect.left) / rect.width * WORLD, 0, WORLD),
    clamp((event.clientY - rect.top) / rect.height * WORLD, 0, WORLD)];
}
function placeAt(x, y) {
  const round = (value) => Math.round(value * 10) / 10;
  if (pick === "reach") Object.assign(draft.objective.reach, {x: round(x), y: round(y)});
  else if (pick === "unit" && selectedUnit) {
    const target = draft.units[selectedUnit[0]][selectedUnit[1]];
    if (target) target.placement = {kind: "fixed", x: round(x), y: round(y)};
  } else Object.assign(draft.player, {x: round(x), y: round(y)});
  renderEditor();
}

let mapToken = 0;
async function drawMap() {
  const canvas = $("missions-map");
  if (!draft || canvas.hidden) return;
  const token = ++mapToken;
  const size = canvas.clientWidth || 360;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(size * ratio);
  canvas.height = Math.round(size * ratio);
  const context = canvas.getContext("2d");
  const style = getComputedStyle(document.documentElement);
  const color = (name) => style.getPropertyValue(name).trim();
  const scale = canvas.width / WORLD;
  let coast = null;
  if (draft.world.kind === "reference") {
    const index = Number(String(draft.world.reference).split(":")[1]);
    try { coast = await fetchCoast(index); } catch (_) { coast = null; }
    if (token !== mapToken) return;
  }
  context.fillStyle = color("--scope");
  context.fillRect(0, 0, canvas.width, canvas.height);
  if (coast) {
    context.fillStyle = color("--bg-4");
    context.strokeStyle = color("--text-faint");
    for (const outline of coast.outlines) {
      context.beginPath();
      outline.forEach(([x, y], index) => (index ? context.lineTo(x * scale, y * scale) : context.moveTo(x * scale, y * scale)));
      context.closePath();
      context.fill();
      context.stroke();
    }
  }
  context.strokeStyle = color("--line-strong");
  context.lineWidth = ratio;
  for (const sector of draft.world.sectors) {
    context.strokeRect(sector.x * scale, sector.y * scale, sector.width * scale, sector.height * scale);
  }
  const sideColor = {hostile: color("--aff-hostile"), neutral: color("--aff-neutral"), friendly: color("--aff-friend")};
  const sectors = new Map(draft.world.sectors.map((sector) => [sector.id, sector]));
  const where = (placement) => placement.kind === "sector" && sectors.has(placement.sector)
    ? [sectors.get(placement.sector).x + sectors.get(placement.sector).width / 2,
      sectors.get(placement.sector).y + sectors.get(placement.sector).height / 2] : [placement.x, placement.y];
  const mark = (x, y, fill, radius, own) => {
    context.beginPath();
    context.arc(x * scale, y * scale, radius * ratio, 0, Math.PI * 2);
    context.fillStyle = fill;
    context.fill();
    if (own) { context.strokeStyle = color("--live-strong"); context.lineWidth = 2 * ratio; context.stroke(); }
  };
  if (draft.objective.type === "reach") {
    const reach = draft.objective.reach;
    context.beginPath();
    context.arc(reach.x * scale, reach.y * scale, Math.max(3 * ratio, reach.radius_nm * scale), 0, Math.PI * 2);
    context.strokeStyle = color("--caution");
    context.lineWidth = 2 * ratio;
    context.stroke();
  }
  for (const group of draft.units.random_groups) {
    const [x, y] = where(group.placement);
    context.strokeStyle = sideColor[group.side];
    context.lineWidth = ratio;
    context.strokeRect(x * scale - 6 * ratio, y * scale - 6 * ratio, 12 * ratio, 12 * ratio);
  }
  for (const unit of draft.units.exact) {
    const [x, y] = where(unit.placement);
    mark(x, y, sideColor[unit.side] ?? color("--text"), 4, unit.id === draft.boat_id && draft.side === "uboot");
  }
  mark(draft.player.x, draft.player.y, color("--aff-friend"), 5, draft.side === "frigate");
}

async function saveDraft(start) {
  const key = draft.key;
  const result = await runRequest("save", {mission: draft, overwrite: editingKey === key},
    "missions_saved", {name: draft.name});
  if (result?.status !== "applied") return;
  editingKey = key;
  if (start) {
    const row = S.missionLibrary?.missions.find((item) => item.key === key);
    if (row?.valid) startMission(row);
  }
}

export function init() {
  const dialog = $("missions-dialog");
  dialog.addEventListener("close", () => { dialog.hidden = true; draft = null; });
  $("host-missions").addEventListener("click", openMissions);
  $("missions-close").addEventListener("click", closeDialog);
  $("missions-new").addEventListener("click", () => openEditor(null));
  $("missions-generate").addEventListener("click", generateMission);
  $("missions-generate-text").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); generateMission(); }
  });
  $("missions-upload").addEventListener("click", () => $("missions-upload-input").click());
  $("missions-upload-input").addEventListener("change", () => {
    uploadFile($("missions-upload-input").files[0]);
    $("missions-upload-input").value = "";
  });
  $("missions-overwrite").addEventListener("click", () => {
    $("missions-overwrite").hidden = true;
    if (!pendingOverwrite) return;
    const {op, fields, okKey, values} = pendingOverwrite;
    runRequest(op, {...fields, overwrite: true}, okKey, values);
  });
  for (const name of TABS) {
    $(`missions-tab-${name}`).addEventListener("click", () => { tab = name; renderEditor(); });
  }
  $("missions-tabs").addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const step = event.key === "ArrowRight" ? 1 : -1;
    tab = TABS[(TABS.indexOf(tab) + step + TABS.length) % TABS.length];
    renderEditor();
    $(`missions-tab-${tab}`).focus();
  });
  $("missions-map").addEventListener("click", (event) => { if (draft) placeAt(...mapPoint(event)); });
  $("missions-pick-player").addEventListener("click", () => { pick = "player"; renderPickHint(); });
  $("missions-save").addEventListener("click", () => saveDraft(false));
  $("missions-save-start").addEventListener("click", () => saveDraft(true));
  $("missions-export-draft").addEventListener("click", () => {
    if (draft) download(`${draft.key}.json`, {format: "u-jagd.editor-bundle", version: 1, missions: [draft],
      units: (S.missionLibrary?.units ?? []).filter((unit) => JSON.stringify(draft.units).includes(`"${unit.key}"`))});
  });
  $("missions-back").addEventListener("click", () => { showLibrary(); renderLibrary(true); });
  on("missions-revision", () => { if (dialog.open && !draft) refreshLibrary(); });
  on("host", () => { if (dialog.open && !draft) renderLibrary(); });
  window.addEventListener("resize", () => { if (draft) drawMap(); });
}
