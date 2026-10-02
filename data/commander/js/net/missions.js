import { S } from "../state/store.js";
import { secureId } from "./commands.js";
import { request } from "./request.js";
import { boundedArray, exactKeys } from "../state/schema.js";

// Own-mission library of the solo host (src/commander/missions.py): the
// published library, the static editor catalog, sector coasts and the
// queued save/import/delete requests. Content is validated on the host;
// these checks only bound what the page reads.
export const UPLOAD_MAX_BYTES = 1024 * 1024;
const text = (value, maximum) => typeof value === "string" && value.length <= maximum;
const issueOk = (row) => exactKeys(row, ["path", "code", "en", "de"]) &&
  text(row.path, 120) && text(row.code, 32) && text(row.en, 300) && text(row.de, 300);

function validLibrary(value) {
  return exactKeys(value, ["protocol", "revision", "missions", "units", "user_profiles", "results", "truncated"]) &&
    value.protocol === 2 && Number.isSafeInteger(value.revision) && typeof value.truncated === "boolean" &&
    boundedArray(value.missions, 64) && value.missions.every((row) =>
      exactKeys(row, ["key", "name", "side", "objective", "valid", "issues", "hints", "units", "data"]) &&
      text(row.key, 80) && text(row.name, 80) && ["frigate", "uboot"].includes(row.side) &&
      text(row.objective, 16) && typeof row.valid === "boolean" &&
      boundedArray(row.issues, 20) && row.issues.every(issueOk) &&
      boundedArray(row.hints, 8) && row.hints.every((hint) => exactKeys(hint, ["key", "en", "de"]) &&
        text(hint.key, 64) && text(hint.en, 300) && text(hint.de, 300)) &&
      boundedArray(row.units, 64) && row.units.every((key) => text(key, 80)) &&
      row.data && typeof row.data === "object" && !Array.isArray(row.data)) &&
    boundedArray(value.units, 256) && value.units.every((unit) => unit && typeof unit === "object" && text(unit.key, 80)) &&
    boundedArray(value.user_profiles, 256) && value.user_profiles.every((row) =>
      exactKeys(row, ["key", "kind", "name", "warship"]) && text(row.key, 80) && text(row.kind, 16) &&
      text(row.name, 80) && typeof row.warship === "boolean") &&
    boundedArray(value.results, 8) && value.results.every((row) =>
      exactKeys(row, ["id", "status", "reason", "issues"]) && text(row.id, 64) &&
      ["applied", "rejected"].includes(row.status) && text(row.reason, 16) &&
      boundedArray(row.issues, 20) && row.issues.every(issueOk));
}

function validCatalog(value) {
  return exactKeys(value, ["protocol", "world_size_nm", "profiles", "sectors", "sides", "player_sides",
    "objectives", "events", "weathers"]) && value.protocol === 2 && Number.isFinite(value.world_size_nm) &&
    boundedArray(value.profiles, 512) && value.profiles.every((row) =>
      exactKeys(row, ["key", "kind", "name", "warship"]) && text(row.key, 80) && text(row.kind, 16) &&
      text(row.name, 80) && typeof row.warship === "boolean") &&
    boundedArray(value.sectors, 128) && value.sectors.every((row) =>
      exactKeys(row, ["index", "countries"]) && Number.isSafeInteger(row.index) &&
      boundedArray(row.countries, 4) && row.countries.every((name) => text(name, 80))) &&
    ["sides", "player_sides", "objectives", "events", "weathers"].every((field) =>
      boundedArray(value[field], 8) && value[field].every((item) => text(item, 16)));
}

export async function fetchLibrary() {
  const library = await request("/missions");
  if (!validLibrary(library)) throw new Error("protocol");
  S.missionLibrary = library;
  return library;
}

export async function fetchCatalog() {
  if (S.missionCatalog) return S.missionCatalog;
  const catalog = await request("/editor/catalog");
  if (!validCatalog(catalog)) throw new Error("protocol");
  S.missionCatalog = catalog;
  return catalog;
}

const coasts = new Map();
export async function fetchCoast(index) {
  if (coasts.has(index)) return coasts.get(index);
  const coast = await request(`/editor/sector?i=${index}`);
  if (!exactKeys(coast, ["index", "outlines"]) || coast.index !== index ||
      !boundedArray(coast.outlines, 4096) || !coast.outlines.every((outline) =>
        Array.isArray(outline) && outline.every((point) =>
          Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)))) throw new Error("protocol");
  if (coasts.size >= 16) coasts.delete(coasts.keys().next().value);
  coasts.set(index, coast);
  return coast;
}

// Queue one library request, then read the library until its result arrives.
export async function missionRequest(op, fields, attempts = 24) {
  if (!S.session?.host) throw new Error("forbidden");
  const id = fields.id ?? secureId();
  const body = {protocol: 2, op, ...fields, id};
  if (JSON.stringify(body).length > UPLOAD_MAX_BYTES + 4000) {
    const error = new Error("too_large");
    error.reason = "too_large";
    throw error;
  }
  await request("/missions", {method: "POST", body, expected: 202, csrf: S.session.csrf});
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, attempt ? 400 : 150));
    const library = await fetchLibrary();
    const result = library.results.find((row) => row.id === id);
    if (result) return result;
  }
  const error = new Error("timeout");
  error.reason = "timeout";
  throw error;
}

// A shareable file of one mission with the user units it references; the
// same format as the uConsole's exchange folder (u-jagd.editor-bundle).
export function missionBundle(row, library) {
  return {format: "u-jagd.editor-bundle", version: 1, missions: [row.data],
    units: library.units.filter((unit) => row.units.includes(unit.key))};
}

// The key the host stores a generated mission under (mission_library.generated_key).
export function generatedKey(id) {
  return `user.llm_${id.toLowerCase().replace(/[^0-9a-f]/g, "").slice(0, 12)}`;
}
// Language model answers take long: wait up to about three minutes.
export const GENERATE_ATTEMPTS = 450;
