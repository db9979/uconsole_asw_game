// Turning 3D model of an analyzer profile on a canvas: the generated meshes
// of src/ui/unit_models.py with the uConsole's view, shading and turn rate.
import { CLASSES, ELEVATION_RAD, LIGHT, MATERIALS, MODELS, TURN_RAD_S, WATER, WATER_RING } from "./unit-models.js";

const FRAME_MS = 1000 / 30;
const prepared = new Map();

function newell(points) {
  const n = [0, 0, 0];
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    n[0] += (a[1] - b[1]) * (a[2] + b[2]);
    n[1] += (a[2] - b[2]) * (a[0] + b[0]);
    n[2] += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const length = Math.hypot(n[0], n[1], n[2]);
  return length > 1e-12 ? n.map((c) => c / length) : [0, 0, 1];
}

function prepare(cls) {
  let mesh = prepared.get(cls);
  if (mesh) return mesh;
  const data = MODELS[cls] || MODELS.unknown;
  const verts = [];
  for (let i = 0; i < data.v.length; i += 3) verts.push([data.v[i] / 1000, data.v[i + 1] / 1000, data.v[i + 2] / 1000]);
  const sided = new Set(data.s);
  const faces = data.f.map((face, index) => {
    const points = face.map((k) => verts[k]);
    const centroid = [0, 1, 2].map((axis) => points.reduce((sum, p) => sum + p[axis], 0) / points.length);
    return { face, normal: newell(points), centroid, color: MATERIALS[data.m[index]], sided: sided.has(index) };
  });
  const radius = Math.max(...verts.map((p) => Math.hypot(p[0], p[1], p[2])));
  const horizontal = Math.max(...verts.map((p) => Math.hypot(p[0], p[1])));
  const height = Math.max(...verts.map((p) => Math.abs(p[2])));
  mesh = { verts, faces, lines: data.l, floating: data.w, radius, horizontal, height };
  prepared.set(cls, mesh);
  return mesh;
}

export function modelClass(key) {
  return Object.prototype.hasOwnProperty.call(CLASSES, key) ? CLASSES[key] : "unknown";
}

export function turnAngle(seconds) {
  return 0.6 + TURN_RAD_S * seconds;
}

function viewMatrix(yaw, elevation) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), ce = Math.cos(elevation), se = Math.sin(elevation);
  // Rows: screen right, screen up, towards the viewer (tilt after turn).
  return [[cy, -sy, 0], [se * sy, se * cy, ce], [-ce * sy, -ce * cy, se]];
}

const apply = (m, p) => [0, 1, 2].map((row) => m[row][0] * p[0] + m[row][1] * p[1] + m[row][2] * p[2]);
const rgb = (color) => `rgb(${color.map((c) => Math.max(0, Math.min(255, Math.round(c)))).join(",")})`;

export function drawModel(ctx, width, height, cls, yaw, elevation = ELEVATION_RAD) {
  const mesh = prepare(cls);
  const view = viewMatrix(yaw, elevation);
  const verts = mesh.verts.map((p) => apply(view, p));
  const vertical = mesh.horizontal * Math.sin(elevation) + mesh.height * Math.cos(elevation);
  const reach = mesh.floating ? Math.max(mesh.radius, WATER_RING) : mesh.radius;
  const scale = 0.92 * Math.min(width / (2 * reach), height / (2 * vertical));
  const cx = width / 2, cy = height / 2;
  const screen = verts.map((p) => {
    const persp = 1 / (1 - p[2] / (5 * mesh.radius));
    return [cx + p[0] * scale * persp, cy - p[1] * scale * persp];
  });
  const items = [];
  mesh.faces.forEach((face, index) => {
    const normal = apply(view, face.normal);
    const facing = normal[2] > 0;
    if (!facing && !face.sided) return;
    const dot = normal[0] * LIGHT[0] + normal[1] * LIGHT[1] + normal[2] * LIGHT[2];
    const lit = facing ? Math.max(0, dot) : Math.abs(dot);
    items.push([apply(view, face.centroid)[2], 0, index, 0.34 + 0.66 * lit]);
  });
  mesh.lines.forEach(([a, b], index) => items.push([(verts[a][2] + verts[b][2]) / 2, 1, index, 1]));
  items.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2]);
  ctx.clearRect(0, 0, width, height);
  if (mesh.floating) {
    ctx.strokeStyle = rgb(WATER);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(cx, cy, scale * WATER_RING, scale * WATER_RING * Math.sin(elevation), 0, 0, 2 * Math.PI);
    ctx.stroke();
  }
  ctx.lineJoin = "round";
  for (const [, kind, index, shade] of items) {
    if (kind) {
      const [a, b, material] = mesh.lines[index];
      ctx.strokeStyle = rgb(MATERIALS[material]);
      ctx.lineWidth = Math.max(1, scale / 260);
      ctx.beginPath();
      ctx.moveTo(...screen[a]);
      ctx.lineTo(...screen[b]);
      ctx.stroke();
      continue;
    }
    const face = mesh.faces[index];
    const color = rgb(face.color.map((c) => c * shade));
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    face.face.forEach((k, i) => (i ? ctx.lineTo(...screen[k]) : ctx.moveTo(...screen[k])));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  return items.length;
}

// Turns the model while the canvas is in the page; dragging turns it by
// hand, and with reduced motion it stands still until dragged.
export function mountModel(canvas, cls) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = performance.now();
  let offset = 0, dragX = null, last = 0;
  const paint = (now) => {
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    drawModel(ctx, width, height, cls, turnAngle(still ? 0 : (now - start) / 1000) + offset);
  };
  const frame = (now) => {
    if (!canvas.isConnected) return;
    if (!document.hidden && now - last >= FRAME_MS && (!still || dragX !== null || !last)) {
      last = now;
      paint(now);
    }
    requestAnimationFrame(frame);
  };
  canvas.addEventListener("pointerdown", (event) => { dragX = event.clientX; canvas.setPointerCapture?.(event.pointerId); });
  canvas.addEventListener("pointermove", (event) => {
    if (dragX === null) return;
    offset += (event.clientX - dragX) * 0.012;
    dragX = event.clientX;
  });
  const release = () => { dragX = null; paint(performance.now()); };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);
  requestAnimationFrame(frame);
}
