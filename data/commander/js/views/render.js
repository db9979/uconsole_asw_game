import { S } from "../state/store.js";
import { $, phases } from "../core/base.js";
import { duration, enumText, number, t, timeOfDay } from "../core/format.js";
import { renderBridgeOrders } from "./bridge-orders.js";
import { queueDraw } from "./chart.js";
import { metrics } from "./dom.js";
import { queueLookoutDraw, renderLookoutStatus } from "./lookout.js";
import { renderStationView } from "./station-view.js";
import { renderStationAlarms } from "./station-tabs.js";
import { renderDebriefButton } from "./debrief.js";
import { renderAdvisorButton } from "./advisor.js";
import { flushSonarFocus, renderDetail, renderTracks } from "./tracks.js";
import { renderWeatherStation } from "./weather.js";

export function renderSnapshot(resetDraft = false) {
  renderWeatherStation();
  $("mission-name").textContent = S.snapshot.mission.name;
  $("objective").textContent = S.snapshot.mission.objective;
  $("phase").textContent = enumText(phases, S.snapshot.phase);
  $("command-permission").textContent = t(S.session?.grants.command ? "commands_enabled" : "commands_disabled");
  $("autocrew-status").textContent = S.v2State?.autocrew ? t("autocrew_status", {
    status: t(`autocrew_${S.v2State.autocrew.status}`),
  }) : "";
  $("autocrew-overview").textContent = S.v2State?.autocrew_overview?.some((row) => row.enabled)
    ? t("autocrew_overview", {stations: S.v2State.autocrew_overview.filter((row) => row.enabled)
      .map((row) => `${t(`station_${row.station}`)}: ${t(`autocrew_${row.status}`)}`).join(", ")})
    : t("autocrew_overview_none");
  // With the autocrew on, releasing the station hands it over to the AI.
  const release = t(S.v2State?.autocrew?.enabled ? "role_release_ai" : "role_release");
  for (const id of ["release-station", "mobile-release-station"]) $(id).textContent = release;
  // Compact status-bar clocks; the full names are the tooltips.
  metrics($("mission-metrics"), [
    ["status_remaining", duration(S.snapshot.mission.remaining_s)],
    ["status_elapsed", duration(S.snapshot.clock.mission)],
    ["status_world", timeOfDay(S.snapshot.clock.world)],
  ]);
  for (const [row, key] of [...$("mission-metrics").children].map((row, index) => [row, ["remaining", "mission_clock", "world_clock"][index]])) row.title = t(key);
  renderStationView();
  renderStationAlarms();
  renderDebriefButton();
  renderAdvisorButton();
  renderBridgeOrders();
  $("chart-disclaimer").textContent = S.chart.disclaimer;
  $("snapshot-meta").textContent = t("snapshot_meta", { version: S.snapshot.version, seq: S.snapshot.seq, revision: S.snapshot.revision, sim: number(S.snapshot.clock.sim, 1) });
  renderTracks();
  renderDetail(resetDraft);
  queueDraw();
  renderLookoutStatus();
  queueLookoutDraw();
  flushSonarFocus();
}
