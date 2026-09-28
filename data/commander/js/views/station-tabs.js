import { S } from "../state/store.js";
import { $, sideStations, stationKey, stationNames } from "../core/base.js";
import { t } from "../core/format.js";
import { node } from "./dom.js";
import { activateTab, chooseStation } from "./lobby.js";
import { toggleWeatherStation } from "./weather.js";

// ---- Station tabs -----------------------------------------------------
// One tab per station this client holds, in fixed station order. The digit on
// a tab is its station number (1-9), also usable as a hotkey.
const stationTabText = {bridge: "tab_bridge", sonar: "tab_sonar", weapons: "tab_weapons", damage: "tab_damage",
  opz: "tab_opz", radio: "tab_radio", engine: "tab_engine", helicopter: "tab_helicopter", eloka: "tab_eloka",
  uboot: "tab_uboot", uboot_sonar: "tab_uboot_sonar", uboot_weapons: "tab_uboot_weapons",
  uboot_engine: "tab_uboot_engine", uboot_esm: "tab_uboot_esm", uboot_nav: "tab_uboot_nav",
  uboot_radio: "tab_uboot_radio"};
export function renderStationTabs(leased, shown) {
  const bar = $("station-tabs");
  const signature = leased.map((station) => `${station}:${t(stationTabText[station])}`).join("|");
  if (bar.dataset.signature !== signature) {
    bar.replaceChildren(...leased.map((station) => {
      const tab = node("button", undefined, "station-tab");
      tab.type = "button";
      tab.id = `station-tab-${station}`;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", "panel-operations");
      tab.dataset.station = station;
      tab.setAttribute("aria-label", t(`station_${station}`));
      tab.append(node("span", String(stationKey(station)), "station-key"),
        node("span", t(stationTabText[station]), "station-name"));
      tab.addEventListener("click", () => chooseStation(station));
      tab.addEventListener("keydown", (event) => {
        const tabs = [...bar.children];
        let index = tabs.indexOf(tab);
        if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft") index = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") index = 0;
        else if (event.key === "End") index = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[index].focus();
        chooseStation(tabs[index].dataset.station);
      });
      return tab;
    }));
    bar.dataset.signature = signature;
  }
  for (const tab of bar.children) {
    const on = tab.dataset.station === shown;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
    tab.title = `${t(`station_${tab.dataset.station}`)} \u00b7 ${t("station_tab_hint", {key: stationKey(tab.dataset.station)})}`;
  }
}
function stepStation(delta) {
  const held = stationNames.filter((station) => S.session?.stations[station].status === "mine");
  if (held.length < 2) return;
  const index = held.indexOf(S.activatingStation ?? S.session.station);
  chooseStation(held[(index + delta + held.length) % held.length]);
}

export function init() {
  document.addEventListener("keydown", (event) => {
    if (!S.session?.station || event.ctrlKey || event.altKey || event.metaKey || event.isComposing ||
        event.repeat || $("operations").hidden) return;
    const target = event.target;
    if (event.key === "0" && !(target instanceof Element && (target.closest("input, select, textarea") || target.isContentEditable)) &&
        !document.querySelector("dialog[open]:not(#weather-dialog)")) {
      event.preventDefault();
      toggleWeatherStation();
      return;
    }
    if (target instanceof Element && (target.closest("input, select, textarea, dialog[open]") ||
        target.isContentEditable)) return;
    if (/^[1-9]$/.test(event.key)) {
      const held = stationNames.find((name) => S.session.stations[name].status === "mine");
      const station = sideStations(held ?? "bridge")[Number(event.key) - 1];
      if (station && S.session.stations[station].status === "mine") { event.preventDefault(); chooseStation(station); }
    } else if (event.key === "[" || event.key === "]") {
      event.preventDefault();
      stepStation(event.key === "]" ? 1 : -1);
    } else if (event.key === "?") {
      event.preventDefault();
      activateTab("guide");
    }
  });
}
