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
  fillFireTargets("uboot-fire-target", payload.contacts);
  stationRows($("uboot-contacts"), payload.contacts, sonarEntries);
  stationRows($("uboot-feed"), [...payload.feed].reverse().map((row) => ({...row, key: row.seq})),
    (row) => [["age", unit(row.age_s, "s", 0)], ["uboot_log_entry", row.message]]);
}
