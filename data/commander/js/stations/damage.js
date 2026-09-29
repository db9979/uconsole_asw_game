import { $, damageStates } from "../core/base.js";
import { enumText, number, t, unit } from "../core/format.js";
import { actionButton, metrics, node, stationRows, yesNo } from "../views/dom.js";
import { renderCrew } from "../views/crew.js";

function compartmentName(payload, key) {
  return payload.compartments.find((room) => room.key === key)?.name || key;
}

export function renderDamageStation(payload) {
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
  const selectedTeam = selector.value;
  selector.replaceChildren(...payload.teams.map((team) => {
    const option = node("option", number(team.team, 0));
    option.value = String(team.team);
    return option;
  }));
  if (payload.teams.some((team) => String(team.team) === selectedTeam)) selector.value = selectedTeam;
  stationRows($("damage-teams"), payload.teams, (team) => [["team", team.team], ["compartment", team.compartment]]);
  stationRows($("damage-compartments"), payload.compartments, (room) => [["compartment", room.name],
    ["reference", room.key], ["state", enumText(damageStates, room.state)], ["flood", unit(room.flood, "%")],
    ["fire", unit(room.fire, "%")], ["flood_trend", number(room.trend.flood_rate, 2)],
    ["fire_trend", number(room.trend.fire_rate, 2)], ["damage_repairable", yesNo(room.repairable)]], "station_none", (room) =>
    payload.teams.map((team) => actionButton(team.compartment === room.key ? "damage_unassign" : "damage_assign",
      team.compartment === room.key ? "damage_unassign_team" : "damage_assign_team",
      {team: team.team, compartment: room.key}, team.compartment === room.key || room.repairable)));
}
