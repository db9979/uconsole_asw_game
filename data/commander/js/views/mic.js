// Noise discipline (src/core/noise_discipline.py): the meter of the
// player's own microphone. The capture lives apart in /noise-mic.js (opt-in,
// like voice.js); this module only shows the level against the host's
// thresholds (quiet, heard close by, heard far off), marks the crew's loudest
// level from the state and, while the voice is above "quiet", sends that one
// number to the host, where the enemy may hear it.
import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";

const SEND_MS = 500;
let on = false, level = 0, failure = "", lastSent = 0;
let limits = {safe: 5, loud: 11, max: 20};
let crew = 0, quiet = false, shown = false;

function band(value) {
  return value <= limits.safe ? "quiet" : value <= limits.loud ? "near" : "far";
}

function cells() {
  const meter = $("mic-meter");
  if (meter.childElementCount === limits.max) return meter.children;
  meter.replaceChildren(...Array.from({length: limits.max}, (_, index) => {
    const cell = document.createElement("i");
    cell.dataset.band = band(index + 1);
    return cell;
  }));
  return meter.children;
}

function render() {
  const group = $("mic-discipline");
  if (!group) return;
  group.hidden = !shown;
  if (!shown) return;
  $("mic-toggle").setAttribute("aria-pressed", String(on));
  $("mic-toggle").textContent = t(on ? "mic_off" : "mic_on");
  const list = cells();
  for (let index = 0; index < list.length; index += 1) {
    list[index].classList.toggle("lit", on && index < level);
    list[index].classList.toggle("crew", index === crew - 1);
  }
  const meter = $("mic-meter");
  const loudest = Math.max(on ? level : 0, crew);
  meter.setAttribute("aria-valuemax", String(limits.max));
  meter.setAttribute("aria-valuenow", String(loudest));
  meter.dataset.band = band(loudest);
  const status = failure ? t(failure) : !on && crew === 0 ? t("mic_hint")
    : t(`mic_band_${band(loudest)}`);
  const text = quiet ? `${status} · ${t("mic_quiet_ordered")}` : status;
  $("mic-status").textContent = text;
  meter.title = text;
}

function send(now) {
  const session = S.session;
  if (!session?.csrf || now - lastSent < SEND_MS) return;
  lastSent = now;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1500);
  // Outside the command lane: one small number that nothing waits on.
  fetch("/api/v2/mic", {
    method: "POST", signal: controller.signal, cache: "no-store", credentials: "same-origin",
    redirect: "error", mode: "same-origin",
    headers: {Accept: "application/json", "Content-Type": "application/json", "X-U-Jagd-CSRF": session.csrf},
    body: JSON.stringify({protocol: 2, level}),
  }).catch(() => {}).finally(() => clearTimeout(timeout));
}

export function wireMic() {
  window.addEventListener("u-jagd-mic", (event) => {
    const detail = event.detail;
    if (!detail || typeof detail.on !== "boolean" || !Number.isSafeInteger(detail.level)) return;
    on = detail.on && shown;
    level = Math.max(0, Math.min(limits.max, detail.level));
    failure = typeof detail.failure === "string" && /^mic_[a-z_]+$/.test(detail.failure) ? detail.failure : "";
    if (on && level > limits.safe) send(performance.now());
    render();
  });
}

export function syncMic(state) {
  const noise = state?.crew_noise;
  const live = Boolean(noise) && state.phase === "live" && Boolean(state.role)
    && !["lookout", "uboot_lookout"].includes(state.role);
  if (!live) {
    if (on) window.dispatchEvent(new CustomEvent("u-jagd-mic-stop"));
    shown = false; on = false; crew = 0; quiet = false;
    render();
    return;
  }
  shown = true;
  if (noise.max !== limits.max) $("mic-meter")?.replaceChildren();
  limits = {safe: noise.safe, loud: noise.loud, max: noise.max};
  crew = noise.voice; quiet = noise.quiet;
  render();
}
