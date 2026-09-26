import { S } from "../state/store.js";
import { affiliations, classes, domains, prefix } from "./base.js";

export const t = (key, values = {}) => (S.catalog[prefix + key] || "").replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (_, name) => String(values[name] ?? ""));
export const finite = (value) => typeof value === "number" && Number.isFinite(value);
export const hasPosition = (entity) => finite(entity?.x) && finite(entity?.y);
export const number = (value, digits = 1) => finite(value) ? value.toLocaleString(S.language, { minimumFractionDigits: digits, maximumFractionDigits: digits }) : t("unavailable");
export const unit = (value, symbol, digits = 1) => finite(value) ? `${number(value, digits)} ${symbol}` : t("unavailable");
export const enumText = (map, value) => t(map[value] || "unknown");
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
