import { S } from "../state/store.js";
import { $, phases } from "../core/base.js";
import { enumText, finite, number, t, unit } from "../core/format.js";
import { renderBridgeOrders } from "./bridge-orders.js";
import { queueDraw } from "./chart.js";
import { metrics } from "./dom.js";
import { queueLookoutDraw, renderLookoutStatus } from "./lookout.js";
import { renderStationView } from "./station-view.js";
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
  metrics($("mission-metrics"), [
    ["remaining", unit(S.snapshot.mission.remaining_s, "s", 0)],
    ["mission_clock", unit(S.snapshot.clock.mission, "s", 0)],
    ["world_clock", finite(S.snapshot.clock.world) ? `${String(Math.floor(S.snapshot.clock.world) % 24).padStart(2, "0")}:${String(Math.floor(S.snapshot.clock.world * 60) % 60).padStart(2, "0")}` : t("unavailable")],
  ]);
  renderStationView();
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
