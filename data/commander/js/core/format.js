import { S } from "../state/store.js";
import { affiliations, classes, domains, prefix } from "./base.js";

export const t = (key, values = {}) => (S.catalog[prefix + key] || "").replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, name) => String(values[name] ?? ""));
export const finite = (value) => typeof value === "number" && Number.isFinite(value);
export const hasPosition = (entity) => finite(entity?.x) && finite(entity?.y);
export const number = (value, digits = 1) => finite(value) ? value.toLocaleString(S.language, { minimumFractionDigits: digits, maximumFractionDigits: digits }) : t("unavailable");
// Durations as h:mm:ss (m:ss below an hour); world time of day as hh:mm.
export const duration = (seconds) => {
  if (!finite(seconds)) return t("unavailable");
  const total = Math.max(0, Math.round(seconds)), h = Math.floor(total / 3600), m = Math.floor(total / 60) % 60, s = total % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
};
export const timeOfDay = (hours) => finite(hours)
  ? `${String(Math.floor(hours) % 24).padStart(2, "0")}:${String(Math.floor(hours * 60) % 60).padStart(2, "0")}` : t("unavailable");
export const unit = (value, symbol, digits = 1) => finite(value) ? `${number(value, digits)} ${symbol}` : t("unavailable");
// An internal state name as catalog text ("<family>_<value>"), else as sent.
export const stateText = (family, value) => {
  if (value === null || value === undefined || value === "") return t("unavailable");
  const key = `${family}_${String(value).toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;
  return S.catalog[prefix + key] ? t(key) : String(value);
};
export const enumText = (map, value) => t(map[value] || "unknown");
// The helicopter's state: in the hangar with a launch ordered, the start
// preparation with its time left, or ready and waiting for the deck window.
const clockText = (seconds) => {
  const left = Math.ceil(Math.max(0, seconds));
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
};
// The helicopter's state as the uConsole shows it: start preparation, then
// refuelling to the launch minimum, or ready; without an order, refuelling.
export const heloStateText = (map, asset) => {
  const refuel = asset.refuel_s === null || asset.refuel_s === undefined ? null : asset.refuel_s;
  if (asset.prep_s !== null && asset.prep_s !== undefined) {
    if (asset.prep_s > 0) return t("helo_prep", {time: clockText(asset.prep_s)});
    return refuel !== null ? t("helo_refuel", {time: clockText(refuel)}) : t("helo_prep_ready");
  }
  if (refuel !== null) return t("helo_refuel", {time: clockText(refuel)});
  return enumText(map, asset.state);
};
export const classificationText = (value) => Object.hasOwn(classes, value) ? enumText(classes, value) :
  typeof value === "string" && value ? value : t("unknown");
export const affClass = (value) => `aff-${Object.hasOwn(affiliations, value) ? value.toLowerCase() : "unknown"}`;
export const domainClass = (value) => `domain-${Object.hasOwn(domains, value) ? value.toLowerCase() : "unknown"}`;
export const selectedTrack = () => S.snapshot?.tracks.find((track) => track.ref === S.selected);
export const sameContext = (a, b) => a && b && a.session === b.session && a.epoch === b.epoch;
// Every assigned station receives the identical known chart, so a station
// switch keeps it; only the redacted (role-less) chart is a different picture.
export const chartMatches = (state) => Boolean(state && S.chart) && S.chartSession === state.session && S.chartEpoch === state.epoch &&
  (S.chartRole === state.role || (S.chartRole !== null && state.role !== null)) &&
  S.chart.revision === state.chart_revision;
export const authenticated = () => S.session !== null;
