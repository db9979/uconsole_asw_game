import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, t } from "../core/format.js";
import { request } from "../net/request.js";
import { boundedArray, exactKeys } from "../state/schema.js";
import { resizeCanvas } from "./chart.js";
import { colors, palette } from "../core/palette.js";
import { node } from "./dom.js";
import { advisorReport } from "./advisor.js";

// ---- Debrief replay (after the mission only) ---------------------------------
// The host publishes each side's finished recording once the mission has
// ended (/api/v2/debrief): the true tracks beside the crew's picture, played
// back at 10x or 60x.  Tracks grow as the cursor runs, positions are
// interpolated between frames and shots, pings, hits and sinkings flash where
// they happened.  Mirrors src/core/debrief_replay.py and src/ui/debrief_view.py.
const FLASH_KINDS = new Set(["own_shot", "enemy_shot", "pinged", "sub_sunk", "ship_sunk", "own_damage", "first_contact"]);
const FLASH_WALL_S = 1.6;
// Event colours by the palette's signal names (they follow the theme).
const EVENT_TONES = {first_contact: "amber", first_fix: "amber", classified: "amber", own_shot: "blue",
  enemy_shot: "red", sub_sunk: "green", own_damage: "red", ship_sunk: "red", missed: "plot",
  pinged: "amber", enemy_commander: "amber", enemy_habits: "amber", mission_end: "text"};
const eventColor = (type) => palette()[EVENT_TONES[type]];
const replay = {doc: null, t: 0, playing: false, speed: 10, wall: null, frame: 0};

function point(value) { return exactKeys(value, ["x", "y"]) && finite(value.x) && finite(value.y); }
function validFrame(frame) {
  return exactKeys(frame, ["t", "ship", "subs", "known", "assets", "own_weapons", "enemy_weapons", "buoys"]) &&
    finite(frame.t) && exactKeys(frame.ship, ["x", "y", "course"]) && finite(frame.ship.x) && finite(frame.ship.y) &&
    finite(frame.ship.course) &&
    boundedArray(frame.subs, 16) && frame.subs.every((row) => exactKeys(row, ["id", "x", "y", "depth", "sunk", "hostile"]) &&
      typeof row.id === "string" && finite(row.x) && finite(row.y) && Number.isInteger(row.depth) &&
      typeof row.sunk === "boolean" && typeof row.hostile === "boolean") &&
    boundedArray(frame.known, 32) && frame.known.every((row) => exactKeys(row, ["label", "bearing", "x", "y"]) &&
      typeof row.label === "string" && finite(row.bearing) &&
      (row.x === null && row.y === null || finite(row.x) && finite(row.y))) &&
    boundedArray(frame.assets, 4) && frame.assets.every((row) => exactKeys(row, ["type", "x", "y"]) &&
      typeof row.type === "string" && finite(row.x) && finite(row.y)) &&
    boundedArray(frame.own_weapons, 16) && frame.own_weapons.every(point) &&
    boundedArray(frame.enemy_weapons, 16) && frame.enemy_weapons.every(point) &&
    boundedArray(frame.buoys, 24) && frame.buoys.every(point);
}
export function validDebrief(value) {
  return exactKeys(value, ["protocol", "available", "session", "epoch", "side", "frames", "events", "speeds"]) &&
    value.protocol === 2 && value.available === true && ["frigate", "uboot"].includes(value.side) &&
    boundedArray(value.frames, 512) && value.frames.every(validFrame) &&
    value.frames.every((frame, index, frames) => index === 0 || frame.t >= frames[index - 1].t) &&
    boundedArray(value.events, 512) && value.events.every((event) => exactKeys(event, ["t", "type", "sub", "en", "de"]) &&
      finite(event.t) && Object.hasOwn(EVENT_TONES, event.type) && (event.sub === null || typeof event.sub === "string") &&
      typeof event.en === "string" && typeof event.de === "string") &&
    Array.isArray(value.speeds) && value.speeds.length === 2 && value.speeds.every((speed) => Number.isInteger(speed) && speed > 0);
}

function bracket(frames, time) {
  if (time <= frames[0].t) return [0, 0];
  const last = frames.length - 1;
  if (time >= frames[last].t) return [last, 0];
  let lo = 0, hi = last;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (frames[mid].t <= time) lo = mid; else hi = mid; }
  const span = frames[hi].t - frames[lo].t;
  return [lo, span > 0 ? (time - frames[lo].t) / span : 0];
}
const lerp = (a, b, k) => a + (b - a) * k;
export function interpolateFrame(frames, time) {
  const [index, k] = bracket(frames, time);
  const frame = frames[index];
  if (k <= 0 || index + 1 >= frames.length) return frame;
  const after = frames[index + 1];
  const turn = ((after.ship.course - frame.ship.course + 540) % 360) - 180;
  const later = new Map(after.subs.map((row) => [row.id, row]));
  return {...frame, t: time,
    ship: {x: lerp(frame.ship.x, after.ship.x, k), y: lerp(frame.ship.y, after.ship.y, k),
      course: (frame.ship.course + turn * k + 360) % 360},
    subs: frame.subs.map((row) => {
      const other = later.get(row.id);
      return !other || row.sunk ? row : {...row, x: lerp(row.x, other.x, k), y: lerp(row.y, other.y, k)};
    })};
}
function bounds(frames) {
  const xs = [], ys = [];
  for (const frame of frames) {
    xs.push(frame.ship.x); ys.push(frame.ship.y);
    for (const sub of frame.subs) if (sub.hostile) { xs.push(sub.x); ys.push(sub.y); }
    for (const row of frame.known) if (row.x !== null) { xs.push(row.x); ys.push(row.y); }
  }
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(4, Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 1.1;
  return {cx, cy, span};
}
function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function draw() {
  const doc = replay.doc;
  const canvas = $("debrief-map");
  if (!doc || !canvas || !$("debrief-dialog").open) return;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, rect.width), height = Math.max(1, rect.height);
  const g = canvas.getContext("2d");
  resizeCanvas(canvas, g, width, height);
  const p = palette(), OWN = colors.FRIEND, HOSTILE = colors.HOSTILE, KNOWN = p.amber;
  g.fillStyle = p.scopeBg;
  g.fillRect(0, 0, width, height);
  const box = replay.box ??= bounds(doc.frames);
  const scale = Math.min(width, height) / box.span;
  const at = (x, y) => [width / 2 + (x - box.cx) * scale, height / 2 + (y - box.cy) * scale];
  const frame = interpolateFrame(doc.frames, replay.t);
  const past = doc.frames.filter((item) => item.t < frame.t).concat([frame]);
  g.lineWidth = 2;
  g.strokeStyle = OWN;
  g.beginPath();
  past.forEach((item, index) => { const [x, y] = at(item.ship.x, item.ship.y); if (index) g.lineTo(x, y); else g.moveTo(x, y); });
  g.stroke();
  const paths = new Map();
  for (const item of past) for (const sub of item.subs) if (sub.hostile) {
    if (!paths.has(sub.id)) paths.set(sub.id, []);
    paths.get(sub.id).push(at(sub.x, sub.y));
  }
  g.lineWidth = 1;
  g.strokeStyle = HOSTILE;
  for (const points of paths.values()) {
    g.beginPath();
    points.forEach(([x, y], index) => { if (index) g.lineTo(x, y); else g.moveTo(x, y); });
    g.stroke();
  }
  const [sx, sy] = at(frame.ship.x, frame.ship.y);
  g.fillStyle = OWN;
  g.beginPath(); g.arc(sx, sy, 6, 0, Math.PI * 2); g.fill();
  const rad = frame.ship.course * Math.PI / 180;
  g.strokeStyle = OWN; g.lineWidth = 2;
  g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + 16 * Math.sin(rad), sy - 16 * Math.cos(rad)); g.stroke();
  g.font = "12px 'IBM Plex Mono', monospace";
  for (const sub of frame.subs) {
    if (!sub.hostile) continue;
    const [bx, by] = at(sub.x, sub.y);
    g.strokeStyle = g.fillStyle = sub.sunk ? p.faint : HOSTILE;
    g.beginPath(); g.moveTo(bx, by - 8); g.lineTo(bx + 8, by); g.lineTo(bx, by + 8); g.lineTo(bx - 8, by); g.closePath(); g.stroke();
    g.fillText(`${sub.id} ${sub.depth} m`, bx + 10, by - 4);
  }
  g.strokeStyle = g.fillStyle = KNOWN;
  for (const row of frame.known) {
    if (row.x !== null) {
      const [kx, ky] = at(row.x, row.y);
      g.beginPath(); g.moveTo(kx - 6, ky - 6); g.lineTo(kx + 6, ky + 6); g.moveTo(kx - 6, ky + 6); g.lineTo(kx + 6, ky - 6); g.stroke();
      g.fillText(row.label, kx + 8, ky + 12);
    } else {
      const angle = row.bearing * Math.PI / 180, length = .3 * Math.min(width, height);
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + length * Math.sin(angle), sy - length * Math.cos(angle)); g.stroke();
    }
  }
  for (const [rows, color] of [[frame.own_weapons, p.blue], [frame.enemy_weapons, p.red], [frame.buoys, p.green]]) {
    g.fillStyle = color;
    for (const row of rows) { const [x, y] = at(row.x, row.y); g.beginPath(); g.arc(x, y, 3, 0, Math.PI * 2); g.fill(); }
  }
  g.strokeStyle = doc.side === "frigate" ? OWN : p.red;
  for (const row of frame.assets) { const [x, y] = at(row.x, row.y); g.strokeRect(x - 4, y - 4, 8, 8); }
  // Flashes: shots, pings, hits and sinkings where they happened.
  const window = FLASH_WALL_S * replay.speed;
  for (const event of doc.events) {
    const age = frame.t - event.t;
    if (!FLASH_KINDS.has(event.type) || age < 0 || age > window) continue;
    const k = age / window;
    const sub = event.type === "sub_sunk" ? frame.subs.find((row) => row.id === event.sub) : null;
    const [fx, fy] = sub ? at(sub.x, sub.y) : [sx, sy];
    g.globalAlpha = 1 - k;
    g.strokeStyle = g.fillStyle = eventColor(event.type);
    g.lineWidth = 2;
    g.beginPath(); g.arc(fx, fy, 8 + 34 * k, 0, Math.PI * 2); g.stroke();
    if (k < .25) { g.beginPath(); g.arc(fx, fy, 5, 0, Math.PI * 2); g.fill(); }
    g.globalAlpha = 1;
  }
  renderControls(frame);
}

function renderControls(frame) {
  const doc = replay.doc;
  const end = doc.frames.at(-1).t;
  $("debrief-time").textContent = `${clock(frame.t)} / ${clock(end)}`;
  $("debrief-play").textContent = t(replay.playing ? "debrief_pause" : "debrief_play");
  $("debrief-play").setAttribute("aria-pressed", String(replay.playing));
  $("debrief-speed").textContent = t("debrief_speed", {speed: replay.speed});
  const scrub = $("debrief-scrub");
  scrub.max = String(Math.max(1, Math.round(end)));
  if (document.activeElement !== scrub) scrub.value = String(Math.round(frame.t));
  const list = $("debrief-events");
  const past = doc.events.filter((event) => event.t <= frame.t).length;
  if (list.dataset.count !== String(doc.events.length) || list.dataset.lang !== S.language) {
    list.replaceChildren(...doc.events.map((event) => {
      const row = node("li", `${clock(event.t)} ${event[S.language === "de" ? "de" : "en"]}`);
      row.style.setProperty("--event-color", eventColor(event.type));
      return row;
    }));
    list.dataset.count = String(doc.events.length);
    list.dataset.lang = S.language;
  }
  [...list.children].forEach((row, index) => row.classList.toggle("past", index < past));
}

function tick(now) {
  if (!replay.playing || !replay.doc || !$("debrief-dialog").open) { replay.wall = null; return; }
  if (replay.wall !== null) replay.t += Math.min(.25, Math.max(0, (now - replay.wall) / 1000)) * replay.speed;
  replay.wall = now;
  const end = replay.doc.frames.at(-1).t;
  if (replay.t >= end) { replay.t = end; replay.playing = false; replay.wall = null; }
  draw();
  if (replay.playing) requestAnimationFrame(tick);
}
function togglePlay() {
  if (!replay.doc) return;
  if (!replay.playing && replay.t >= replay.doc.frames.at(-1).t - 1e-6) replay.t = replay.doc.frames[0].t;
  replay.playing = !replay.playing;
  replay.wall = null;
  if (replay.playing) requestAnimationFrame(tick);
  draw();
}

export async function openDebrief() {
  try {
    const value = await request("/debrief");
    if (!validDebrief(value)) { $("debrief-status").textContent = t("debrief_unavailable"); return; }
    replay.doc = value;
    replay.box = null;
    replay.speed = value.speeds[0];
    replay.t = value.frames[0].t;
    replay.playing = false;
    const dialog = $("debrief-dialog");
    $("debrief-status").textContent = "";
    if (!dialog.open) { dialog.hidden = false; dialog.showModal(); }
    draw();
    showReport();
  } catch (_) {
    $("debrief-status").textContent = t("debrief_unavailable");
  }
}
// The after-action report of the language model, when one was written.
async function showReport() {
  const text = await advisorReport();
  $("debrief-report-box").hidden = !text;
  $("debrief-report").textContent = text || "";
}
// The button shows only once the mission is over.
export function renderDebriefButton() {
  const ended = S.v2State?.phase === "ended" && Boolean(S.v2State?.role);
  $("debrief-open").hidden = !ended;
  if (!ended && $("debrief-dialog").open) $("debrief-dialog").close();
}
export function init() {
  $("debrief-open").addEventListener("click", openDebrief);
  $("debrief-close").addEventListener("click", () => $("debrief-dialog").close());
  $("debrief-dialog").addEventListener("close", () => { replay.playing = false; $("debrief-dialog").hidden = true; });
  $("debrief-play").addEventListener("click", togglePlay);
  $("debrief-speed").addEventListener("click", () => {
    if (!replay.doc) return;
    const speeds = replay.doc.speeds;
    replay.speed = speeds[(speeds.indexOf(replay.speed) + 1) % speeds.length];
    draw();
  });
  $("debrief-scrub").addEventListener("input", () => {
    replay.t = Number($("debrief-scrub").value);
    replay.playing = false;
    draw();
  });
  $("debrief-dialog").addEventListener("keydown", (event) => {
    if (event.key === " " && !(event.target instanceof HTMLButtonElement)) { event.preventDefault(); togglePlay(); }
  });
  window.addEventListener("resize", () => { if ($("debrief-dialog").open) draw(); });
}
