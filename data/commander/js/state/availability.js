import { S } from "./store.js";
import { chartMatches } from "../core/format.js";

// Command gates evaluated from client state only (no DOM); the host revalidates.
export function bridgeOrderAvailable(kind) {
  const orders = S.v2State?.bridge?.orders;
  return S.session?.station === "bridge" &&
    S.session.grants.command === true && S.connected && !S.roleStale && S.v2State?.phase === "live" &&
    chartMatches(S.snapshot) && !S.pending && orders && (kind !== "course" || !orders.station_down);
}
export function stationActionAvailable() {
  return S.connected && !S.roleStale && S.session?.grants.command === true &&
    S.v2State?.phase === "live" && chartMatches(S.snapshot) && !S.pending;
}
