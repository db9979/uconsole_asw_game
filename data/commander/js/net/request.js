import { S } from "../state/store.js";
import { checkHostVersion } from "./version.js";

// All requests, including commands and language changes, share one lane. The
// deadline covers JSON consumption as well as headers, including stalled bodies.
export function request(path, { method = "GET", body, auth = true, expected = 200, guard, csrf } = {}) {
  const cookieSession = auth ? S.session : null;
  const requestGeneration = S.generation;
  const run = async () => {
    if (auth && (!cookieSession || requestGeneration !== S.generation)) throw new Error("cancelled");
    if (guard && !guard()) throw new Error("cancelled");
    const controller = new AbortController();
    S.activeRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 4000);
    let response;
    try {
      const headers = { Accept: "application/json" };
      if (csrf) headers["X-U-Jagd-CSRF"] = csrf;
      if (body !== undefined) headers["Content-Type"] = "application/json";
      response = await fetch(`/api/v2${path}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal, cache: "no-store", credentials: "same-origin", redirect: "error", mode: "same-origin",
      });
      // A host update since this page loaded: reload to the matching client.
      if (checkHostVersion(response.headers.get("X-U-Jagd-Version"))) throw new Error("cancelled");
      if (response.status !== expected) {
        const error = new Error("http");
        error.status = response.status;
        try { error.reason = (await response.json())?.error; } catch (_) { /* no JSON body */ }
        throw error;
      }
      // A queued command acknowledgement need not contain a JSON body.
      if (expected === 202) { await response.text(); return null; }
      return await response.json();
    } catch (error) {
      if (response) error.endpointAvailable = true;
      throw error;
    } finally {
      clearTimeout(timeout);
      if (S.activeRequest === controller) S.activeRequest = null;
    }
  };
  const result = S.requestQueue.then(run, run);
  S.requestQueue = result.catch(() => {});
  return result;
}
