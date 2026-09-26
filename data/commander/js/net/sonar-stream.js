import { S } from "../state/store.js";
import { emit } from "../core/events.js";
import { isSonar } from "../core/base.js";
import { authenticated, finite } from "../core/format.js";
import { sonarHistory, sonarStream } from "../state/shared.js";
import { sampleDisplayClock } from "../state/display-clock.js";

function accumulateSonarHistory(state) {
  if (!isSonar(state.role) || !finite(state.clock?.sim)) return;
  const context = `${state.session}:${state.epoch}`;
  if (sonarHistory.context !== context) {
    sonarHistory.context = context;
    for (const name of ["broadband", "lofar", "demon"]) sonarHistory[name].clear();
  }
  const visual = state.sonar.visualization;
  for (const [name, rows] of [["broadband", visual.broadband.history], ["lofar", visual.lofar.history], ["demon", visual.demon.history]]) {
    const history = sonarHistory[name];
    for (const row of rows) {
      const stamp = state.clock.sim - row.age_s;
      if (!finite(stamp)) continue;
      history.set(Math.round(stamp * 1000), {...row, stamp});
    }
    for (const [key, row] of history) if (row.stamp < state.clock.sim - 605 || row.stamp > state.clock.sim + .001) history.delete(key);
    while (history.size > 3000) history.delete(history.keys().next().value);
  }
}
export function stopSonarStream() {
  sonarStream.generation += 1;
  clearTimeout(sonarStream.retry);
  sonarStream.retry = null;
  const socket = sonarStream.socket;
  sonarStream.socket = null;
  sonarStream.connected = false;
  sonarStream.sequence = -1;
  if (socket) socket.close(1000, "station context changed");
}
function storeSonarStreamRow(name, stamp, bins, bearing = null) {
  if (!finite(stamp) || !Array.isArray(bins) || !bins.length) return;
  const row = {stamp, age_s: 0, bins};
  if (bearing !== null) row.bearing = bearing;
  const history = sonarHistory[name];
  history.set(Math.round(stamp * 1000), row);
  while (history.size > 3000) history.delete(history.keys().next().value);
}
function acceptSonarStreamFrame(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 60 || !S.v2State || !isSonar(S.v2State.role)) throw new Error("sonar_stream_protocol");
  const view = new DataView(buffer);
  if (view.getUint8(0) !== 85 || view.getUint8(1) !== 74 || view.getUint8(2) !== 83 || view.getUint8(3) !== 50 ||
      view.getUint8(4) !== 1 || view.getUint8(5) !== 0 || view.getUint16(6, true) !== 60) throw new Error("sonar_stream_protocol");
  const sequence = Number(view.getBigUint64(8, true));
  const epoch = Number(view.getBigUint64(16, true));
  const simTime = view.getFloat64(24, true);
  const bearing = view.getFloat32(32, true);
  const counts = [36, 38, 40, 42, 44].map((offset) => view.getUint16(offset, true));
  const ages = [48, 52, 56].map((offset) => view.getFloat32(offset, true));
  if (!Number.isSafeInteger(sequence) || sequence <= sonarStream.sequence || !Number.isSafeInteger(epoch) ||
      epoch !== S.v2State.epoch || !finite(simTime) || !finite(bearing) || ages.some((age) => !finite(age) || age < 0) ||
      counts[0] > 180 || counts[1] > 256 || counts[2] > 80 || counts[3] > 256 || counts[4] > 80 ||
      60 + counts.reduce((sum, count) => sum + count, 0) !== buffer.byteLength) throw new Error("sonar_stream_protocol");
  let offset = 60;
  const take = (count) => { const values = Array.from(new Uint8Array(buffer, offset, count), (value) => value / 255); offset += count; return values; };
  const broadband = take(counts[0]), lofar = take(counts[1]), demon = take(counts[2]);
  sonarStream.lofarSpectrum = take(counts[3]);
  sonarStream.demonSpectrum = take(counts[4]);
  sonarStream.sequence = sequence;
  storeSonarStreamRow("broadband", simTime - ages[0], broadband);
  storeSonarStreamRow("lofar", simTime - ages[1], lofar, bearing);
  storeSonarStreamRow("demon", simTime - ages[2], demon);
  sampleDisplayClock(S.v2State, simTime);
  const visual = S.v2State.sonar.visualization;
  visual.lofar.spectrum = sonarStream.lofarSpectrum;
  visual.demon.spectrum = sonarStream.demonSpectrum;
  emit("sonar:frame");
}
export function syncSonarStream() {
  const allowed = authenticated() && S.connected && !document.hidden && isSonar(S.session?.station) &&
    isSonar(S.v2State?.role) && S.v2State.phase === "live";
  if (!allowed) { if (sonarStream.socket) stopSonarStream(); return; }
  if (sonarStream.socket) return;
  const streamGeneration = ++sonarStream.generation;
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new window.WebSocket(`${scheme}//${location.host}/ws/v2/sonar`, "u-jagd-sonar-v2");
  socket.binaryType = "arraybuffer";
  sonarStream.socket = socket;
  socket.addEventListener("open", () => {
    if (streamGeneration !== sonarStream.generation || sonarStream.socket !== socket) { socket.close(); return; }
    sonarStream.connected = true;
  });
  socket.addEventListener("message", (event) => {
    if (streamGeneration !== sonarStream.generation || sonarStream.socket !== socket) return;
    try { acceptSonarStreamFrame(event.data); }
    catch (_) { socket.close(4002, "invalid sonar frame"); }
  });
  socket.addEventListener("close", () => {
    if (sonarStream.socket === socket) sonarStream.socket = null;
    sonarStream.connected = false;
    if (streamGeneration === sonarStream.generation && authenticated()) {
      sonarStream.retry = setTimeout(syncSonarStream, 1000);
    }
  });
  socket.addEventListener("error", () => socket.close());
}
export function useV2State(state) {
  // Both sonar rooms render through one panel reading ``state.sonar``; the
  // alias is non-enumerable so exact-key checks still see the wire shape.
  if (state.role === "uboot_sonar" && !Object.hasOwn(state, "sonar"))
    Object.defineProperty(state, "sonar", {value: state.uboot_sonar, enumerable: false, configurable: true});
  accumulateSonarHistory(state);
  sampleDisplayClock(state);
  S.v2State = state;
  if (isSonar(state.role) && sonarStream.connected) {
    state.sonar.visualization.lofar.spectrum = sonarStream.lofarSpectrum;
    state.sonar.visualization.demon.spectrum = sonarStream.demonSpectrum;
  }
  // Views, game sounds and live audio follow the accepted state.
  emit("state:accepted", state);
  syncSonarStream();
  emit("plots:sync");
}
