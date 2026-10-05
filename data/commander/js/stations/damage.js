import { $, damageStates } from "../core/base.js";
import { enumText, number, t, unit } from "../core/format.js";
import { actionButton, metrics, setOptions, stationRows, yesNo } from "../views/dom.js";
import { renderCrew } from "../views/crew.js";
import { renderNoteLamps } from "../views/console-kit.js";

function compartmentName(payload, key) {
  return payload.compartments.find((room) => room.key === key)?.name || key;
}

function teamStatus(team) {
  if (!team.compartment) return t("damage_team_ready");
  return team.transit_s > 0 ? t("damage_team_en_route", {seconds: number(team.transit_s, 0)})
    : t("damage_team_on_scene");
}

// Team cards: the team the selector holds is highlighted, and a click on a
// card picks that team for the next assignment (like the selector).
function markTeams(list, teams, selector) {
  [...list.children].forEach((card) => {
    const team = teams.find((item) => String(item.team) === card.dataset.rowKey);
    if (!team) return;
    card.classList.add("team-card");
    card.dataset.state = !team.compartment ? "ready" : team.transit_s > 0 ? "transit" : "scene";
    card.classList.toggle("selected", selector.value === String(team.team));
    if (!card.dataset.pick) {
      card.dataset.pick = "1";
      card.tabIndex = 0;
      const pick = () => {
        selector.value = card.dataset.rowKey;
        selector.dispatchEvent(new Event("change", {bubbles: true}));
        [...list.children].forEach((other) => other.classList.toggle("selected", other === card));
      };
      card.addEventListener("click", pick);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pick(); }
      });
    }
  });
}

export function renderDamageStation(payload) {
  renderNoteLamps($("damage-note-lamps"));
  metrics($("damage-summary"), [["damage_total", unit(payload.total, "%")], ["sunk", yesNo(payload.sunk)]]);
  renderCrew($("damage-crew"), $("damage-crew-actions"), payload.crew,
    {actionStations: "crew_action_stations", watchChange: "crew_watch_change",
      medic: "crew_casualty_medic", reassign: "crew_casualty_reassign"});
  const stability = payload.stability;
  metrics($("damage-stability"), [["damage_list", unit(stability.list_deg, "\u00b0")],
    ["damage_trim", unit(stability.trim_deg, "\u00b0")],
    ["damage_counterflood", stability.counterflood_room ? compartmentName(payload, stability.counterflood_room) : t("station_none")]]);
  const valve = $("damage-counterflood");
  valve.textContent = t(stability.counterflood_room ? "damage_counterflood_stop" : "damage_counterflood_start");
  valve.disabled = !stability.counterflood_room && !stability.can_counterflood;
  const selector = $("damage-team");
  setOptions(selector, payload.teams.map((team) => [String(team.team), number(team.team, 0)]));
  stationRows($("damage-teams"), payload.teams, (team) => [["team", t("damage_team_title", {team: team.team})],
    ["compartment", team.compartment ? compartmentName(payload, team.compartment) : t("damage_team_free")],
    ["state", teamStatus(team)]]);
  markTeams($("damage-teams"), payload.teams, selector);
  stationRows($("damage-compartments"), payload.compartments, (room) => [["compartment", room.name],
    ["state", enumText(damageStates, room.state)], ["flood", unit(room.flood, "%")],
    ["fire", unit(room.fire, "%")], ["flood_trend", number(room.trend.flood_rate, 2)],
    ["fire_trend", number(room.trend.fire_rate, 2)], ["damage_repairable", yesNo(room.repairable)]], "station_none", (room) =>
    payload.teams.map((team) => actionButton(team.compartment === room.key ? "damage_unassign" : "damage_assign",
      team.compartment === room.key ? "damage_unassign_team" : "damage_assign_team",
      {team: team.team, compartment: room.key}, team.compartment === room.key || room.repairable)));
}
