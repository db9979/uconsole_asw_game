import { S } from "../state/store.js";
import { $, isSonar } from "../core/base.js";
import { finite, number, selectedTrack, t, unit } from "../core/format.js";
import { request } from "../net/request.js";
import { metrics, node, yesNo } from "./dom.js";
import { stationActionAvailable } from "../state/availability.js";
import { mountModel } from "./model-view.js";

function validateContactAnalysis(data) {
  const scalar = (value) => value === null || typeof value === "string" || typeof value === "boolean" || finite(value);
  const record = (value, fields) => value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).sort().join(",") === [...fields].sort().join(",");
  const textList = (value) => Array.isArray(value) && value.length <= 128 &&
    value.every((item) => typeof item === "string" && item.length <= 128);
  const numberList = (value) => value === null || (Array.isArray(value) && value.length <= 128 && value.every(finite));
  const boundedObject = (value, depth = 0) => {
    if (depth > 5) return false;
    if (scalar(value)) return typeof value !== "string" || value.length <= 512;
    if (Array.isArray(value)) return value.length <= 128 && value.every((item) => boundedObject(item, depth + 1));
    return value && typeof value === "object" && Object.keys(value).length <= 32 &&
      Object.entries(value).every(([key, item]) => key.length <= 64 && boundedObject(item, depth + 1));
  };
  if (!data || typeof data !== "object" || Array.isArray(data) ||
      Object.keys(data).sort().join(",") !== "profiles,version" || data.version !== 1 ||
      !Array.isArray(data.profiles) || data.profiles.length > 4096) throw new Error("analysis_schema");
  const keys = new Set();
  for (const profile of data.profiles) {
    const referenceFields = ["hull_type", "length_m"];
    const machineFields = ["cruise_speed_kn", "maximum_speed_kn", "quiet_speed_kn", "propulsion_codes", "motor_rpm", "shaft_rpm", "propulsor_type", "blade_count", "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband"];
    if (!profile || typeof profile !== "object" || Array.isArray(profile) ||
        Object.keys(profile).sort().join(",") !== "assets,components,key,machine,name,reference,resource" ||
        typeof profile.key !== "string" || !/^[a-z0-9][a-z0-9_.-]{0,95}$/.test(profile.key) || keys.has(profile.key) ||
        typeof profile.name !== "string" || !profile.name || profile.name.length > 256 ||
        typeof profile.resource !== "string" || !["subs.json", "warships.json", "civilians.json", "aircraft.json", "animals.json", "torpedoes.json", "decoys.json"].includes(profile.resource) ||
        !profile.assets || typeof profile.assets !== "object" || Array.isArray(profile.assets) ||
        Object.keys(profile.assets).some((kind) => !["acoustic_cruise", "acoustic_high", "radar"].includes(kind)) ||
        Object.entries(profile.assets).some(([kind, route]) => {
          const suffix = { acoustic_cruise: "cruise", acoustic_high: "high", radar: "radar" }[kind];
          return typeof route !== "string" || route !== `/contact-analysis/${profile.key}-${suffix}.png`;
        }) ||
        !profile.components || typeof profile.components !== "object" || Array.isArray(profile.components) ||
        Object.keys(profile.components).sort().join(",") !== "countermeasures,emitters,launchers,magazines,sensors,weapons" ||
        Object.values(profile.components).some((items) => !Array.isArray(items) || items.length > 128 || items.some((item) => !boundedObject(item))) ||
        !record(profile.reference, referenceFields) || !record(profile.machine, machineFields) ||
        !referenceFields.every((field) => scalar(profile.reference[field])) ||
        !textList(profile.machine.propulsion_codes) || !numberList(profile.machine.motor_rpm) || !numberList(profile.machine.shaft_rpm) ||
        !["cruise_lines", "high_speed_lines"].every((field) => Array.isArray(profile.machine[field]) && profile.machine[field].length <= 128 && profile.machine[field].every((line) => Array.isArray(line) && line.length === 3 && line.every(finite))) ||
        !["cruise_broadband", "high_speed_broadband"].every((field) => profile.machine[field] === null || (Array.isArray(profile.machine[field]) && profile.machine[field].length === 3 && profile.machine[field].every(finite))) ||
        !machineFields.filter((field) => !["propulsion_codes", "motor_rpm", "shaft_rpm", "cruise_lines", "high_speed_lines", "cruise_broadband", "high_speed_broadband"].includes(field)).every((field) => scalar(profile.machine[field])) ||
        !boundedObject(profile.components)) throw new Error("analysis_schema");
    keys.add(profile.key);
  }
}
export async function loadContactAnalysis() {
  try {
    const data = await request("/contacts", { auth: false });
    validateContactAnalysis(data);
    S.contactAnalysis = data;
    S.analysisError = false;
  } catch (_) {
    S.contactAnalysis = null;
    S.analysisError = true;
  }
  renderContactAnalysis();
}
export function analysisProfile() {
  return S.contactAnalysis?.profiles.find((profile) => profile.key === S.analysisSelected) || null;
}
export function renderContactAnalysis() {
  const status = $("analysis-status");
  const detail = $("analysis-profile");
  const list = $("analysis-list");
  if (!S.contactAnalysis) {
    S.analysisImageKey = null;
    list.replaceChildren();
    detail.hidden = true;
    status.hidden = false;
    status.textContent = t(S.analysisError ? "analyzer_error" : "analyzer_loading");
    $("analysis-count").textContent = "";
    return;
  }
  const term = $("analysis-filter").value.trim().toLocaleLowerCase(S.language).slice(0, 96);
  const category = $("analysis-category").value;
  const visible = S.contactAnalysis.profiles.filter((profile) => (!category || profile.resource === category) &&
    (!term || `${profile.name} ${profile.key}`.toLocaleLowerCase(S.language).includes(term)));
  list.replaceChildren(...visible.map((profile) => {
    const button = node("button", undefined, "analysis-item");
    button.type = "button";
    button.dataset.key = profile.key;
    button.setAttribute("aria-pressed", String(profile.key === S.analysisSelected));
    button.append(node("span", profile.name), node("small", `${profile.key} / ${t(`analyzer_${profile.resource.slice(0, -5)}`)}`));
    button.addEventListener("click", () => { S.analysisSelected = profile.key; renderContactAnalysis(); });
    return button;
  }));
  if (!visible.length) list.append(node("p", t("analyzer_no_results"), "empty"));
  $("analysis-count").textContent = t("analyzer_count", { count: number(visible.length, 0), total: number(S.contactAnalysis.profiles.length, 0) });
  const profile = analysisProfile();
  status.hidden = Boolean(profile);
  detail.hidden = !profile;
  if (!profile) { status.textContent = t("analyzer_select"); return; }
  $("analysis-key").textContent = profile.key;
  $("analysis-name").textContent = profile.name;
  $("analysis-resource").textContent = t(`analyzer_${profile.resource.slice(0, -5)}`);
  // Sonar operators assign the compared profile to their selected contact.
  const canAssign = isSonar(S.session?.station) && Boolean(S.selected) && stationActionAvailable();
  $("analysis-assign").hidden = $("analysis-assign-clear").hidden = !canAssign;
  $("analysis-assign-status").value = canAssign ? t("analyzer_assign_target", {contact: selectedTrack()?.label || S.selected}) : "";
  const reference = profile.reference;
  const machine = profile.machine;
  const joined = (items) => Array.isArray(items) && items.length ? items.join(", ") : t("unavailable");
  metrics($("analysis-metrics"), [
    ["analyzer_hull", reference.hull_type || t("unavailable")],
    ["analyzer_length", unit(reference.length_m, "m")],
    ["analyzer_speed_band", `${unit(machine.cruise_speed_kn, "kn")} / ${unit(machine.maximum_speed_kn, "kn")}`],
    ["analyzer_propulsion", joined(machine.propulsion_codes)],
    ["analyzer_propulsor", machine.propulsor_type || t("unavailable")],
  ]);
  metrics($("analysis-systems"), Object.entries(profile.components).map(([kind, items]) =>
    [`analyzer_${kind}`, number(items.length, 0)]));
  const componentRows = (element, rows, titleKey, fields) => {
    element.replaceChildren(...rows.map((row, index) => {
      const article = node("article", undefined, "analysis-component");
      article.append(node("h4", t(titleKey, {number: index + 1})));
      const list = node("dl", undefined, "detail-metrics");
      for (const [field, value] of fields(row)) {
        const group = node("div");
        const labels = {domain: "domain", frequency_band_hz: "frequency", prf_band_hz: "prf",
          synthetic_range_nm: "range", bearing_uncertainty_deg: "bearing_uncertainty",
          range_uncertainty_nm: "range_uncertainty", modulation_codes: "modulation",
          modes: "analyzer_modes", emits: "analyzer_emits", sensitivity_db: "analyzer_sensitivity",
          cadence_s: "analyzer_cadence", depth_uncertainty_m: "analyzer_depth_uncertainty"};
        group.append(node("dt", t(labels[field]) || field), node("dd", value));
        list.append(group);
      }
      article.append(list);
      return article;
    }));
  };
  const band = (values, symbol) => Array.isArray(values) ? values.map((value) => unit(value, symbol, 0)).join(" - ") : t("unavailable");
  componentRows($("analysis-sensors"), profile.components.sensors,
    "analyzer_sensor_title", (sensor) => [
    ["domain", sensor.domain], ["modes", joined(sensor.modes)], ["emits", yesNo(sensor.emits)],
    ["synthetic_range_nm", unit(sensor.synthetic_range_nm, "NM")], ["sensitivity_db", unit(sensor.sensitivity_db, "dB")],
    ["cadence_s", unit(sensor.cadence_s, "s")], ["bearing_uncertainty_deg", unit(sensor.bearing_uncertainty_deg, "\u00b0")],
    ["range_uncertainty_nm", unit(sensor.range_uncertainty_nm, "NM")], ["depth_uncertainty_m", unit(sensor.depth_uncertainty_m, "m")],
  ]);
  componentRows($("analysis-emitters"), profile.components.emitters,
    "analyzer_emitter_title", (emitter) => [
    ["domain", emitter.domain], ["frequency_band_hz", band(emitter.frequency_band_hz, "Hz")],
    ["prf_band_hz", band(emitter.prf_band_hz, "Hz")], ["modulation_codes", joined(emitter.modulation_codes)],
  ]);
  const imageLabels = { acoustic_cruise: "analyzer_acoustic_cruise", acoustic_high: "analyzer_acoustic_high",
    radar: "analyzer_radar" };
  const imageKey = `${S.language}:${profile.key}`;
  if (S.analysisImageKey !== imageKey) {
    const model = node("figure", undefined, "analysis-image analysis-model");
    const canvas = node("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", t("analyzer_model_alt"));
    model.append(canvas, node("figcaption", t("analyzer_model")));
    mountModel(canvas, profile.key);
    $("analysis-images").replaceChildren(model, ...Object.entries(profile.assets).map(([kind, route]) => {
      const figure = node("figure", undefined, "analysis-image");
      const image = node("img");
      const descriptions = [];
      if (kind === "radar") {
        descriptions.push(t("analyzer_image_alt_radar_base", { speed: t(imageLabels[kind]) }));
        descriptions.push(t(profile.components.emitters.some((emitter) => Array.isArray(emitter.prf_band_hz))
          ? "analyzer_image_alt_radar_prf" : "analyzer_image_alt_radar_no_prf"));
      } else {
        const cruise = kind === "acoustic_cruise";
        const lines = cruise ? machine.cruise_lines : machine.high_speed_lines;
        const broadband = cruise ? machine.cruise_broadband : machine.high_speed_broadband;
        descriptions.push(t("analyzer_image_alt_base", { speed: t(imageLabels[kind]) }));
        if (Array.isArray(lines) && lines.length) descriptions.push(t("analyzer_image_alt_tonals"));
        if (Array.isArray(broadband)) descriptions.push(t("analyzer_image_alt_broadband"));
      }
      image.src = route;
      image.alt = descriptions.join(" ");
      image.loading = "lazy";
      image.decoding = "async";
      figure.append(image, node("figcaption", t(imageLabels[kind])));
      return figure;
    }));
    S.analysisImageKey = imageKey;
  }
}
