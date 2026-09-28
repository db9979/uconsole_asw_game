import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { isSonar } from "../core/base.js";
import { authenticated, chartMatches, sameContext, selectedTrack } from "../core/format.js";
import { pollV2Result } from "./commands.js";
import { request } from "./request.js";
import { forgetSession, setConnection } from "./session.js";
import { useV2State } from "./sonar-stream.js";
import { buildDisplayModel, contextKey, useEvents, validateChart, validateEvents, validateProposals, validateState } from "../state/display-model.js";
import { PROTOCOL_ERROR_MESSAGES, lookoutView, sonarStream, view } from "../state/shared.js";
import { pollHost } from "./host.js";
import { pushHealthy, syncStatePush, takePushedState } from "./push.js";

async function pollRoleFeeds(state, context) {
  const nextProposals = await request("/proposals", {guard: () => context === S.generation});
  validateProposals(nextProposals);
  if (contextKey(nextProposals) !== contextKey(state)) return;
  const nextEvents = await request("/events", {guard: () => context === S.generation});
  validateEvents(nextEvents);
  if (context !== S.generation || contextKey(nextEvents) !== contextKey(state) ||
      contextKey(state) !== contextKey(S.v2State)) return;
  S.proposals = nextProposals;
  emit("proposals");
  useEvents(nextEvents, state);
}
export async function poll() {
  if (!authenticated() || S.polling) return;
  S.polling = true;
  const context = S.generation;
  const started = performance.now();
  let delay = 500;
  try {
    if (started - S.lastSessionFetch >= 1000) {
      const metadata = await request("/session");
      if (context !== S.generation) return;
      emit("session:metadata", metadata);
    }
    if (S.session.station === null) {
      S.failures = 0;
      S.lastSuccess = performance.now();
      setConnection("lobby");
      emit("lobby");
      return;
    }
    if (S.session.host !== null) await pollHost(context);
    if (context !== S.generation) return;
    const stateRoute = sonarStream.connected && isSonar(S.session.station) ? "/state?sonar=stream" : "/state";
    // A pushed state stands in for the /state request while the push is healthy.
    let next = takePushedState() ?? await request(stateRoute);
    if (context !== S.generation) return;
    if (next?.role !== null && next?.role !== S.session.station) {
      const metadata = await request("/session");
      if (context !== S.generation) return;
      emit("session:metadata", metadata);
    }
    validateState(next);
    const previousRole = S.v2State?.role ?? null;
    if (next.role !== null) { useV2State(next); next = buildDisplayModel(next); }
    if (!chartMatches(next)) {
      // Chart has no session field. Sandwich it between matching snapshots;
      // never display a previous session with a new session's geography.
      // Only a first load or a new world blanks the console; a re-fetch after
      // a pause or station switch repaints in place.
      if (!S.chart || S.chartSession !== next.session) emit("chart:blank");
      setConnection("syncing");
      const candidate = await request("/chart");
      if (context !== S.generation) return;
      validateChart(candidate, next);
      let confirmed = await request(stateRoute);
      if (context !== S.generation) return;
      validateState(confirmed);
      if (confirmed.role !== null) { useV2State(confirmed); confirmed = buildDisplayModel(confirmed); }
      if (!sameContext(next, confirmed) || confirmed.role !== next.role ||
          confirmed.chart_revision !== candidate.revision || confirmed.seq < next.seq) {
        // An active-station switch may race the chart sandwich. Discard both
        // snapshots and retry without treating the expected race as a fault.
        return;
      }
      S.chart = candidate;
      S.chartSession = confirmed.session;
      S.chartEpoch = confirmed.epoch;
      S.chartRole = confirmed.role;
      next = confirmed;
    }
    if (next.role === null) {
      const redactedChart = S.chart;
      const redactedChartSession = S.chartSession;
      const redactedChartEpoch = S.chartEpoch;
      emit("role:clear");
      S.chart = redactedChart;
      S.chartSession = redactedChartSession;
      S.chartEpoch = redactedChartEpoch;
      S.chartRole = null;
      useV2State(next);
      S.failures = 0;
      S.lastSuccess = performance.now();
      // A solo host in the menu is not "syncing": the host screen is the view.
      setConnection(S.session.host !== null && S.hostView?.phase === "menu" ? "connected" : "syncing");
      emit("lobby");
      return;
    }
    if (sameContext(S.snapshot, next) && next.seq < S.snapshot.seq) throw new Error("sequence");
    const hadSnapshot = Boolean(S.snapshot);
    const sessionChanged = hadSnapshot && S.snapshot.session !== next.session;
    const epochChanged = hadSnapshot && !sessionChanged && S.snapshot.epoch !== next.epoch;
    const changed = !sameContext(S.snapshot, next);
    const advanced = changed || !S.snapshot || next.seq > S.snapshot.seq;
    if (changed) {
      // A bare epoch step (the host's local input advances it) keeps the
      // same world and role: live listening continues on the new epoch.
      const listeningContinues = epochChanged && previousRole !== null &&
        previousRole === S.v2State?.role;
      if (S.sonarAudioEnabled && !listeningContinues) emit("audio:stop", "sonar_live_unavailable");
      if (S.pending) S.commandMessage = { key: "command_context_changed", status: "rejected" };
      S.pending = null;
      S.requestedSonarFocus = null;
      const worldChanged = epochChanged || sessionChanged;
      if (worldChanged) {
        S.opzMarked.clear();
        S.opzSuppressed.clear();
        S.opzManage = false;
        S.stationDrafts.clear();
      }
      // Drafts and forms of the previous context are dropped by the views.
      emit("context:changed", worldChanged);
      if (sessionChanged || epochChanged) {
        S.selected = null;
        S.eventContext = null;
        S.eventHighWater = 0;
        S.eventHistory = [];
        view.initialized = false;
        lookoutView.rangeNm = 100;
      }
    }
    S.snapshot = next;
    S.roleStale = false;
    emit("role:fresh");
    syncStatePush();
    await pollRoleFeeds(S.v2State, context);
    emit("audio:revalidate");
    if (S.pending) await pollV2Result(context);
    // A station switch that landed while this poll awaited its feeds replaced
    // the snapshot; this result belongs to the old station, drop it.
    if (context !== S.generation || S.snapshot !== next) return;
    if (!view.initialized) emit("chart:fit");
    if (S.selected && !selectedTrack()) S.selected = null;
    S.failures = 0;
    if (advanced) S.lastSuccess = performance.now();
    setConnection(performance.now() - S.lastSuccess > 4500 ? "stale" : "connected");
    emit("snapshot", epochChanged);
  } catch (error) {
    if (context !== S.generation) return;
    console.error("Commander poll failed", error);
    if (error.status === 401 || error.status === 403) {
      forgetSession("connection_expired");
    } else {
      S.failures += 1;
      delay = Math.min(8000, 500 * (2 ** Math.min(S.failures, 4)));
      // Still retried automatically either way (no forced reload) - only
      // the message differs, so the operator can tell "network is rough"
      // from "the host is sending something broken".
      setConnection(PROTOCOL_ERROR_MESSAGES.has(error.message) ? "protocol_error" : "stale");
    }
  } finally {
    S.polling = false;
    if (authenticated()) {
      // With a healthy push the timer only refreshes session presence, chart
      // and feeds; pushed states wake the loop themselves.
      const cadence = S.session?.station === null ? 1000 : pushHealthy() ? 2500 : delay;
      // A push-woken poll replaces the pending timer; an orphaned timer would
      // add a /state request per pushed state.
      clearTimeout(S.pollTimer);
      S.pollTimer = setTimeout(poll, context !== S.generation ? 0 : S.failures ? delay : Math.max(0, cadence - (performance.now() - started)));
    }
  }
}
