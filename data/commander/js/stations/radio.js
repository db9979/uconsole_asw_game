import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { actionButton, node, position, stationRows, yesNo } from "../views/dom.js";

export function renderRadioStation(payload) {
  stationRows($("radio-observations"), payload.observations, (row) => [["reference", row.label],
    ["bearing", unit(row.bearing, "\u00b0", 0)], ["quality", number(row.quality, 2)], ["age", unit(row.age_s, "s", 0)],
    ["bearing_uncertainty", unit(row.bearing_uncertainty_deg, "\u00b0")], ["radio_can_capture", yesNo(row.can_capture)]],
    "station_none", (row) => [actionButton("radio_capture", "radio_capture_hfdf", {ref: row.ref}, row.can_capture)]);
  stationRows($("radio-fixes"), payload.logged_fixes, (row) => [["reference", row.ref], ["position", position(row)],
    ["uncertainty", unit(row.uncertainty_nm, "NM")], ["age", unit(row.age_s, "s", 0)],
    ["covariance", row.covariance_nm2 ? row.covariance_nm2.map((value) => number(value, 2)).join(" / ") : t("unavailable")]]);
  stationRows($("radio-bearings"), payload.logged_bearings, (row) => [["reference", row.ref],
    ["bearing", unit(row.bearing, "\u00b0", 0)], ["observer_position", `${unit(row.observer_x, "NM")} / ${unit(row.observer_y, "NM")}`],
    ["age", unit(row.age_s, "s", 0)]]);
  stationRows($("radio-messages"), payload.messages, (row) => [["reference", row.stamp], ["message", row.text]]);
  if (payload.station_down) $("radio-observations").prepend(node("p", t("station_down_state"), "station-alert"));
}
