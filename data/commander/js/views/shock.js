// The own ship shaken by a detonation close by (src/core/shock.py): the
// station picture jolts, the light dips towards the emergency red, dust
// trickles and a heavy one leaves a cracked glass that fades. Display only;
// with reduced motion only the light dips.
import { $ } from "../core/base.js";

const CUES = new Set(["shock_light", "shock_heavy"]);
let context = null;
let highWater = 0;

function crackLayer() {
  let layer = document.getElementById("shock-cracks");
  if (layer) return layer;
  layer = document.createElement("canvas");
  layer.id = "shock-cracks";
  layer.width = layer.height = 300;
  layer.setAttribute("aria-hidden", "true");
  const g = layer.getContext("2d");
  if (g) {
    g.translate(150, 150);
    g.strokeStyle = "rgba(255, 236, 226, .95)";
    g.lineWidth = 1.2;
    // A fixed pattern: eleven jagged lines from one point of impact.
    let seed = 7;
    const next = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    for (let line = 0; line < 11; line += 1) {
      let angle = next() * Math.PI * 2, x = 0, y = 0;
      g.beginPath();
      g.moveTo(0, 0);
      const steps = 4 + Math.floor(next() * 5);
      for (let step = 0; step < steps; step += 1) {
        angle += next() - .5;
        const length = 140 * (.08 + next() * .12);
        x += Math.cos(angle) * length; y += Math.sin(angle) * length;
        g.lineTo(x, y);
      }
      g.stroke();
    }
    g.beginPath();
    g.arc(0, 0, 4, 0, Math.PI * 2);
    g.stroke();
  }
  document.body.append(layer);
  return layer;
}

function replay(element, name) {
  element.classList.remove(name);
  void element.getBoundingClientRect();
  element.classList.add(name);
}

export function shake(kind) {
  const operations = $("operations");
  if (!operations) return;
  operations.classList.remove("shock-light", "shock-heavy");
  replay(operations, kind === "shock_heavy" ? "shock-heavy" : "shock-light");
  replay(document.body, "shock-dust");
  if (kind === "shock_heavy") replay(crackLayer(), "shock-cracked");
}

export function syncShock(state) {
  const events = Array.isArray(state?.audio?.events) ? state.audio.events : [];
  const latest = events.length ? events.at(-1).seq : 0;
  const world = state ? `${state.session}:${state.epoch}:${state.role}` : null;
  if (world !== context || latest < highWater) {
    context = world;
    highWater = latest;
    return;
  }
  for (const event of events) if (event.seq > highWater && CUES.has(event.cue)) shake(event.cue);
  highWater = Math.max(highWater, latest);
}
