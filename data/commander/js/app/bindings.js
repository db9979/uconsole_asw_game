import { S } from "../state/store.js";
import { stopStatePush } from "../net/push.js";
import { playAlert } from "../audio/alerts.js";
import { openSonarAudioSocket, scheduleSonarAudioPoll, sonarAudioAuthorized, stopSonarAudio, syncGameAudio } from "../audio/audio.js";
import { $ } from "../core/base.js";
import { on } from "../core/events.js";
import { t } from "../core/format.js";
import { syncPlotAnimation } from "../plot/clock.js";
import { renderBridgeOrders } from "../views/bridge-orders.js";
import { canvas, lookoutCanvas } from "../views/canvases.js";
import { fitChart, releaseCanvas } from "../views/chart.js";
import { renderActionState, renderSonarControlPage } from "../views/controls.js";
import { clearFireDrafts } from "../views/dom.js";
import { renderEvents, renderProposals } from "../views/feeds.js";
import { renderHost } from "../views/host.js";
import { acceptSession, activateTab, renderLobby } from "../views/lobby.js";
import { renderSnapshot } from "../views/render.js";
import { updateOpzSweepSample } from "../views/role-map.js";
import { queueVisualDraw, renderRoleVisuals } from "../views/role-visuals.js";
import { applySimlogView, loadSimlog } from "../views/simlog.js";
import { clearRoleState } from "../views/station-view.js";
import { renderConnection } from "../views/status.js";

// The transport (net/*) never touches the page. It updates the store and emits
// a topic; this module maps every topic to the views, audio and plot loops.
function revalidateAudio() {
  if (S.sonarAudioEnabled && !sonarAudioAuthorized()) stopSonarAudio("sonar_live_unavailable");
}

function forgetPage() {
  $("operations").hidden = true;
  $("lobby").hidden = true;
  $("role-rail").hidden = true;
  $("mobile-role").hidden = true;
  $("simlog-view").hidden = true;
  $("simlog-list").replaceChildren();
  $("simlog-current").replaceChildren();
  $("simlog-count").textContent = "";
  renderEvents();
  $("pairing").hidden = false;
  $("disconnect").hidden = true;
  $("pair-error").textContent = "";
  $("code").value = "";
  $("navigation-form").reset();
  $("navigation-status").textContent = "";
  document.body.dataset.remoteRole = "";
  $("host-screen").hidden = true;
  $("host-bar").hidden = true;
  activateTab("operations", false);
  for (const id of ["track-list", "detail-label", "detail-badges", "detail-metrics", "mission-name", "objective", "mission-metrics", "proposal-status", "command-status", "snapshot-meta", "lookout-sea", "lookout-light", "lookout-own", "lookout-observations"]) $(id).replaceChildren();
  $("lookout-scope").dataset.light = "unknown";
  releaseCanvas(canvas);
  releaseCanvas(lookoutCanvas);
}

function resetContextForms(worldChanged) {
  clearFireDrafts();
  if (!worldChanged) return;
  $("navigation-form").reset();
  $("bridge-course-form").reset();
  $("bridge-speed-form").reset();
  $("opz-manage").checked = false;
  for (const id of ["sonar-bearing-form", "sonar-depth-form", "sonar-vds-depth-form", "sonar-gain-form", "sonar-harmonic-form",
    "engine-course-form", "engine-speed-form", "helicopter-waypoint-form",
    "uboot-course-form", "uboot-speed-form", "uboot-depth-form"]) $(id).reset();
  $("sonar-control-page").value = "listen";
  renderSonarControlPage();
}

function followState(state) {
  updateOpzSweepSample(state);
  syncGameAudio();
  // A new world epoch (the host's local input advances it) closes the live
  // audio socket; resume it once the state for the new epoch has arrived.
  const audioWorld = `${state.session}:${state.epoch}`;
  if (audioWorld !== S.sonarAudioWorld) {
    S.sonarAudioWorld = audioWorld;
    if (S.sonarAudioEnabled && !S.sonarAudioSocket && sonarAudioAuthorized()) {
      if (S.sonarAudioWorklet) openSonarAudioSocket();
      else if (!S.sonarAudioController) scheduleSonarAudioPoll(0);
    }
  }
}

export function init() {
  on("session:metadata", acceptSession);
  on("session:forgetting", () => stopSonarAudio());
  on("session:forgetting", () => stopStatePush("session forgotten"));
  on("push", (value) => { document.body.dataset.push = value; });
  on("session:forgotten", forgetPage);
  on("connection", (message) => {
    renderConnection();
    if (message) $("connection").textContent = $("connection").title = t(message);
    renderActionState();
    renderHost();
    if (S.v2State?.role) renderRoleVisuals(S.v2State.role);
    revalidateAudio();
    syncGameAudio();
    syncPlotAnimation();
  });
  on("lobby", renderLobby);
  on("role:clear", clearRoleState);
  on("role:fresh", () => document.body.removeAttribute("data-role-stale"));
  on("chart:blank", () => { $("operations").hidden = true; });
  on("chart:fit", fitChart);
  on("context:changed", resetContextForms);
  on("state:accepted", followState);
  on("plots:sync", syncPlotAnimation);
  on("sonar:frame", queueVisualDraw);
  on("snapshot", (epochChanged) => {
    $("pairing").hidden = true;
    renderLobby();
    applySimlogView();
    renderSnapshot(epochChanged);
    loadSimlog();
  });
  on("proposals", renderProposals);
  on("events", (warning) => { if (warning) playAlert(); renderEvents(); });
  on("command", (bridge) => (bridge ? renderBridgeOrders() : renderActionState()));
  on("command:settled", clearFireDrafts);
  on("audio:stop", (reason) => stopSonarAudio(reason));
  on("audio:revalidate", revalidateAudio);
  on("host", renderHost);
}
