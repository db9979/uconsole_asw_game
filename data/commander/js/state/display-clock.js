import { S } from "./store.js";
import { finite } from "../core/format.js";

// The host publishes at most every 0.5 s, so drawing the acoustic plots only
// when data arrived made the waterfalls jump in steps. They are instead drawn
// against a smoothed display clock. The game always runs in real time and
// never pauses, so the clock simply advances 1:1 with wall time from the last
// publication while the world is live, runs a fixed jitter delay behind it
// (rows scroll in over the top edge instead of popping in) and only slews
// gently. Purely presentational: nothing here is sent to the host.
export const DISPLAY_CLOCK_LAG_S = .75;
const displayClock = {context: null, sim: 0, wall: 0, live: false, shown: null, shownWall: 0};
export function sampleDisplayClock(state, sim = state?.clock?.sim) {
  if (!state || !finite(sim)) return;
  const context = `${state.session}:${state.epoch}`;
  const live = state.phase === "live";
  const reset = displayClock.context !== context;
  if (reset) { displayClock.context = context; displayClock.shown = null; }
  // One publication reaches the page twice (stream frame and state poll);
  // its earliest arrival is the better anchor for extrapolation.
  if (reset || sim > displayClock.sim || live !== displayClock.live)
    Object.assign(displayClock, {sim, wall: performance.now(), live});
}
export function displaySimNow(wallNow = performance.now()) {
  if (displayClock.context === null) return S.v2State?.clock?.sim ?? 0;
  const rate = displayClock.live ? 1 : 0;
  const elapsed = Math.min(1.5, Math.max(0, (wallNow - displayClock.wall) / 1000));
  const target = displayClock.sim + elapsed * rate - DISPLAY_CLOCK_LAG_S;
  if (displayClock.shown === null || Math.abs(target - displayClock.shown) > 3) {
    displayClock.shown = target;
  } else {
    const dt = Math.min(.25, Math.max(0, (wallNow - displayClock.shownWall) / 1000));
    displayClock.shown += Math.max(0, dt * (rate + Math.max(-.1, Math.min(.1, target - displayClock.shown))));
  }
  displayClock.shownWall = wallNow;
  return displayClock.shown;
}
