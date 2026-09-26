import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { number, t, unit } from "../core/format.js";
import { fillFireTargets, metrics, position, sonarEntries, stationRows, yesNo } from "../views/dom.js";

export function renderUbootStation(payload) {
  const nav = payload.navigation, status = payload.status, weapons = payload.weapons;
  metrics($("uboot-navigation"), [["position", position(nav)], ["course", unit(nav.course, "\u00b0", 0)],
    ["uboot_ordered_course", unit(nav.target_course, "\u00b0", 0)], ["speed", unit(nav.speed, "kn")],
    ["uboot_ordered_speed", unit(nav.target_speed, "kn")], ["depth", unit(nav.depth_m, "m", 0)],
    ["uboot_ordered_depth", unit(nav.target_depth_m, "m", 0)], ["uboot_safe_depth", unit(nav.safe_depth_m, "m", 0)],
    ["uboot_water_depth", unit(nav.water_depth_m, "m", 0)], ["uboot_cavitating", yesNo(nav.cavitating)],
    ["uboot_noise", number(nav.noise, 2)]]);
  const alarms = payload.alarms;
  metrics($("uboot-status"), [["state", t(`uboot_state_${status.state}`)], ["uboot_damage", unit(status.damage, "%", 0)],
    ["uboot_battery", status.battery === null ? t("unavailable") : unit(status.battery * 100, "%", 0)],
    ["uboot_endurance_phase", status.endurance_phase || t("unavailable")], ["uboot_transmitting", yesNo(status.transmitting)],
    ["uboot_quiet", yesNo(status.quiet)], ["uboot_snorkeling", yesNo(status.snorkeling)],
    ["uboot_blow_available", yesNo(status.blow_available)], ["uboot_emergency_ascent", yesNo(status.emergency_ascent)],
    ["torpedoes", number(weapons.torpedoes, 0)], ["uboot_tubes_ready", number(weapons.tubes_ready, 0)],
    ["reload", unit(weapons.reload_s, "s", 0)], ["uboot_decoys", number(weapons.decoys, 0)],
    ["uboot_ping_heard", alarms.ping_age_s === null ? t("station_none") : unit(alarms.ping_age_s, "s", 0)],
    ["uboot_torpedo_alarm", alarms.torpedo_age_s === null ? t("station_none") : unit(alarms.torpedo_age_s, "s", 0)]]);
  document.body.classList.toggle("uboot-torpedo-alarm", alarms.torpedo_age_s !== null && alarms.torpedo_age_s < 60);
  if (!S.stationDrafts.has("uboot-depth")) $("uboot-depth").max = String(nav.max_depth_m);
  if (!S.stationDrafts.has("uboot-speed")) $("uboot-speed").max = String(nav.max_speed_kn);
  $("uboot-decoy").dataset.ready = String(weapons.decoy_ready);
  $("uboot-blow").dataset.ready = String(status.blow_available && !status.emergency_ascent && nav.depth_m > 30);
  for (const [id, pressed] of [["uboot-silent", status.silent], ["uboot-snorkel", status.snorkeling], ["uboot-bottom", status.bottomed]])
    $(id).setAttribute("aria-pressed", String(pressed));
  $("uboot-snorkel").dataset.ready = String(status.snorkel_available);
  $("uboot-battery-warning").hidden = status.battery === null || status.battery > .2;
  $("uboot-battery-warning").textContent = status.battery !== null && status.battery <= .03 ? t("uboot_battery_empty") : t("uboot_battery_low");
  fillFireTargets("uboot-fire-target", payload.contacts);
  const wired = payload.own_weapons.map((row, index) => ({...row, label: `T${index + 1}`}));
  stationRows($("uboot-weapons"), wired, (row) => [["reference", row.label], ["depth", unit(row.depth_m, "m", 0)],
    ["course", unit(row.course, "\u00b0", 0)], ["uboot_wire", t(row.wire === "CUT" ? "uboot_wire_cut_state" : `uboot_wire_${(row.wire || "none").toLowerCase()}`)],
    ["uboot_datum", row.datum_bearing === null ? t("unavailable") : `${unit(row.datum_bearing, "\u00b0", 0)} / ${unit(row.datum_range_nm, "NM")}`]], "uboot_no_weapons");
  const select = $("uboot-wire-weapon"), active = wired.filter((row) => row.wire === "ACTIVE");
  const previous = select.value;
  select.replaceChildren(...active.map((row) => Object.assign(document.createElement("option"), {value: row.ref, textContent: row.label})));
  if (active.some((row) => row.ref === previous)) select.value = previous;
  $("uboot-wire-steer").dataset.ready = $("uboot-wire-cut").dataset.ready = String(active.length > 0);
  stationRows($("uboot-contacts"), payload.contacts, sonarEntries);
  stationRows($("uboot-feed"), [...payload.feed].reverse().map((row) => ({...row, key: row.seq})),
    (row) => [["age", unit(row.age_s, "s", 0)], ["uboot_log_entry", row.message]]);
}
