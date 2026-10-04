import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { filteredEloka } from "../state/shared.js";
import { actionButton, metrics, node, stationRows, yesNo } from "../views/dom.js";
import { noteLamp, renderLamps } from "../views/console-kit.js";

const ELOKA_LAMPS = Object.freeze("esm jammer auto tone".split(" "));

export function renderElokaStation(payload) {
  const intercepts = filteredEloka(payload.intercepts);
  // Receiver, jammer, automatic ECM and tone, each with the host's reason.
  renderLamps($("eloka-lamps"), ELOKA_LAMPS.map((name) => noteLamp(name, name)).filter(Boolean));
  metrics($("eloka-hardware"), [["df_sensors", number(payload.hardware.df_sensors, 0)],
    ["broadband_sensors", number(payload.hardware.broadband_sensors, 0)],
    ["ecm_channels", number(payload.hardware.ecm_channels, 0)],
    ["frequency", `${unit(payload.hardware.frequency_min_hz, "Hz", 0)} - ${unit(payload.hardware.frequency_max_hz, "Hz", 0)}`],
    ["reaction_time", unit(payload.hardware.reaction_s * 1000000, "\u00b5s", 1)]]);
  $("eloka-filter-count").textContent = t("eloka_filter_count", {visible: intercepts.length, total: payload.intercepts.length});
  stationRows($("eloka-intercepts"), intercepts, (row) => [["reference", row.label],
    ["bearing", unit(row.bearing, "\u00b0", 0)], ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")],
    ["frequency", unit(row.frequency_hz, "Hz", 0)], ["frequency_band", row.frequency_band.toUpperCase().replace("_", "/")], ["prf", unit(row.prf_hz, "Hz", 0)],
    ["modulation", row.modulation], ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["signal_level", unit(row.signal_db, "dB", 0)], ["range_estimate", row.range_estimate_nm === null ? t("station_none") : unit(row.range_estimate_nm, "NM", 0)],
    ["scan_period", row.scan_period_s === null ? t("station_none") : unit(row.scan_period_s, "s", 1)],
    ["radar_type", row.radar_type || t("station_none")], ["threat", row.threat],
    ["ambiguous", yesNo(row.ambiguous)],
    ["synthetic_assumption", yesNo(row.synthetic_assumption)],
    ["jamming_effectiveness", row.jamming_effectiveness === null ? t("station_none") : number(row.jamming_effectiveness, 2)],
    ["jamming_technique", row.jamming_technique === null ? t("station_none") : t(`ecm_${row.jamming_technique}`)],
    ["ecm_power_draw", row.ecm_power_draw === null ? t("station_none") : number(row.ecm_power_draw, 2)],
    ["ecm_lock", yesNo(row.is_locked_on)], ["hoj_risk", yesNo(row.hoj_risk)],
    ["annotation", row.annotation || t("station_none")],
    ["opz_release_status", t(row.annotation ? "opz_release_annotated" : "opz_release_unannotated")],
    ["candidates", row.candidates.map((item) => item.score === null ? item.name : `${item.name}: ${number(item.score, 2)}`).join(" / ") || t("station_none")],
    ["correlations", row.correlations.map((item) => `${item.ref} / ${item.source}: ${number(item.score, 2)} (${t(item.ambiguous ? "ambiguous" : "unambiguous")}); ${unit(item.evidence.bearing, "\u00b0", 0)} / ${unit(item.evidence.age_s, "s", 0)}`).join(" / ") || t("station_none")]],
    "station_none", (row) => [...row.candidates.map((candidate) => actionButton("eloka_annotate_candidate",
      "eloka_annotate", {ref: row.ref, candidate_ref: candidate.ref}, !payload.station_down, {candidate: candidate.name})),
    actionButton(row.jamming ? "eloka_stop_jam" : "eloka_jam", "eloka_set_jamming",
      {ref: row.ref, enabled: !row.jamming}, !payload.station_down),
    ...["noise", "rgpo", "vgpo", "false_targets"].filter((technique) => technique !== row.jamming_technique)
      .map((technique) => actionButton(`ecm_${technique}`, "eloka_set_technique",
        {ref: row.ref, technique}, !payload.station_down)),
    actionButton(row.auto_jamming ? "eloka_auto_off" : "eloka_auto_on", "eloka_set_auto",
      {enabled: !row.auto_jamming}, !payload.station_down),
    actionButton("eloka_clear", "eloka_clear_annotation", {ref: row.ref}, !payload.station_down && row.annotation !== null)]);
  if (payload.station_down) $("eloka-intercepts").prepend(node("p", t("station_down_state"), "station-alert"));
}
