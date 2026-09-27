// The crew's watch bill, fatigue and morale (frigate bridge/damage, boat
// damage control): metrics plus the two orders the role may give.
import { number, t, unit } from "../core/format.js";
import { actionButton, metrics } from "./dom.js";

export function renderCrew(list, actions, crew, orders) {
  const relief = crew.action_stations ? t("crew_no_relief") : crew.turnover ? t("crew_turnover")
    : t("crew_relief_in", {minutes: number(Math.floor(crew.watch_left_s / 60), 0)});
  metrics(list, [
    ["crew_state", crew.action_stations ? t("crew_action_stations_on") : t("crew_watch_on", {watch: number(crew.on_watch, 0)})],
    ["crew_relief", relief],
    ["crew_performance", unit(crew.effectiveness * 100, "%", 0)],
    ["crew_morale", unit(crew.morale * 100, "%", 0)],
    ...crew.watches.map((row) => [`crew_watch_${row.index}`,
      t(row.on_duty ? "crew_fatigue_on_duty" : "crew_fatigue_resting", {fatigue: number(row.fatigue * 100, 0)})])]);
  const buttons = [actionButton(crew.action_stations ? "crew_stand_down" : "crew_action_stations",
    orders.actionStations, {enabled: !crew.action_stations})];
  if (orders.watchChange) buttons.push(actionButton("crew_relieve", orders.watchChange, {}, !crew.action_stations));
  actions.replaceChildren(...buttons);
}
