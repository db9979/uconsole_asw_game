import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { number, stateText, unit } from "../core/format.js";
import { fillFireTargets, inUse, metrics, position, stationRows, weaponTargetEntries, yesNo } from "../views/dom.js";
import { noteLamp, renderLamps } from "../views/console-kit.js";

// The interlock chain as lamps, drawn from the host's notes (each says why it
// is lit or blocked, as on the uConsole). The tubes are shown once, on the
// stage (role-visuals.js).
function renderWeaponLamps() {
  renderLamps($("weapons-interlock-lamps"), [noteLamp("target", "target"), noteLamp("fix", "fix"),
    noteLamp("roe", "roe"), noteLamp("weapon", "weapon", "weapons-fire-torpedo"), noteLamp("flak", "flak")].filter(Boolean));
}

function renderTorpedoSettings(settings) {
  const typeSelect = $("weapons-torpedo-type");
  const wanted = settings.choices.map((row) => `${row.key}|${row.name}|${row.stock}|${row.loaded}`).join("\n");
  if (typeSelect.dataset.choices !== wanted && !inUse(typeSelect)) {
    typeSelect.replaceChildren(...settings.choices.map((row) => {
      const option = document.createElement("option");
      option.value = row.key;
      option.textContent = `${row.name} \u00b7 ${number(row.stock, 0)} (${number(row.loaded, 0)})`;
      return option;
    }));
    typeSelect.dataset.choices = wanted;
  }
  if (!S.stationDrafts.has("weapons-torpedo-type")) typeSelect.value = settings.torpedo_type;
  if (!S.stationDrafts.has("weapons-pattern")) $("weapons-pattern").value = settings.pattern;
  if (!S.stationDrafts.has("weapons-enable")) $("weapons-enable").value = String(settings.enable_nm);
  if (!S.stationDrafts.has("weapons-salvo")) $("weapons-salvo").value = String(settings.salvo);
}

export function renderWeaponsStation(payload) {
  const inventory = payload.inventory;
  metrics($("weapons-inventory"), [["torpedoes", number(inventory.torpedoes, 0)], ["vls", number(inventory.vls, 0)],
    ["ciws", number(inventory.ciws, 0)], ["aa", number(inventory.aa, 0)], ["chaff", yesNo(inventory.chaff_ready)],
    ["nixies", number(inventory.nixies, 0)], ["asroc", number(inventory.asroc, 0)],
    ["depth_charges", number(inventory.depth_charges, 0)], ["rbu", number(inventory.rbu, 0)]]);
  const readiness = payload.readiness;
  metrics($("weapons-readiness"), [["station_down", yesNo(readiness.station_down)], ["roe", stateText("roe", readiness.roe)],
    ["ciws_ready", yesNo(readiness.ciws_ready)], ["aa_ready", yesNo(readiness.aa_ready)],
    ["state", stateText("battery_state", readiness.state)], ["interlock", readiness.interlock], ["reload", unit(readiness.reload_s, "s", 0)]]);
  stationRows($("weapons-target"), payload.designated_target ? [payload.designated_target] : [], weaponTargetEntries, "station_no_target");
  renderWeaponLamps();
  fillFireTargets("weapons-fire-target", payload.target_choices);
  if (!S.stationDrafts.has("weapons-fire-depth")) $("weapons-fire-depth").value = String(payload.depth_m);
  renderTorpedoSettings(payload.settings);
  stationRows($("weapons-own"), payload.own_weapons, (row) => [["reference", row.ref], ["position", position(row)],
    ["depth", unit(row.depth_m, "m", 0)], ["course", unit(row.course, "\u00b0", 0)], ["state", stateText("weapon_state", row.state)]]);
}
