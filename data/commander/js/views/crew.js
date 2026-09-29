// The crew's watch bill, fatigue and morale (frigate bridge/damage, boat
// damage control): metrics plus the two orders the role may give.
import { number, t, unit } from "../core/format.js";
import { actionButton, metrics } from "./dom.js";

export function renderCrew(list, actions, crew, orders) {
  const relief = crew.action_stations ? t("crew_no_relief") : crew.turnover ? t("crew_turnover")
    : t("crew_relief_in", {minutes: number(Math.floor(crew.watch_left_s / 60), 0)});
  const hurt = crew.casualties;
  const rows = [
    ["crew_state", crew.action_stations ? t("crew_action_stations_on") : t("crew_watch_on", {watch: number(crew.on_watch, 0)})],
    ["crew_relief", relief],
    ["crew_performance", unit(crew.effectiveness * 100, "%", 0)],
    ["crew_morale", unit(crew.morale * 100, "%", 0)],
    ...crew.watches.map((row) => [`crew_watch_${row.index}`,
      t(row.on_duty ? "crew_fatigue_on_duty" : "crew_fatigue_resting", {fatigue: number(row.fatigue * 100, 0)})])];
  if (orders.medic) {
    // The wounded: empty posts per station, the medical team, spare hands.
    rows.push(["crew_wounded", t("crew_wounded_value", {wounded: number(hurt.wounded, 0),
      serious: number(hurt.serious, 0), returned: number(hurt.returned, 0)})],
    ...hurt.stations.map((row) => [`crew_posts_${row.station}`,
      t("crew_posts_value", {gaps: number(row.gaps, 0), posts: number(row.posts, 0)})]),
    ["crew_medic", hurt.medic ? t(`crew_posts_${hurt.medic}`) : "\u2013"],
    ["crew_spare", number(hurt.spare, 0)]);
  }
  metrics(list, rows);
  const buttons = [actionButton(crew.action_stations ? "crew_stand_down" : "crew_action_stations",
    orders.actionStations, {enabled: !crew.action_stations})];
  if (orders.watchChange) buttons.push(actionButton("crew_relieve", orders.watchChange, {}, !crew.action_stations));
  if (orders.medic) {
    const gaps = hurt.stations.some((row) => row.gaps > 0);
    buttons.push(actionButton("crew_medic_next", orders.medic, {}, gaps));
    buttons.push(actionButton("crew_reassign", orders.reassign, {}, gaps && hurt.spare > 0 && hurt.reassign_in_s <= 0));
  }
  actions.replaceChildren(...buttons);
}
