// Turning 3D model of an analyzer profile on a canvas: the generated meshes
// of src/ui/unit_models.py with the uConsole's view, shading and turn rate.
import {
  AIRCRAFT_LIFT, CLASSES, ELEVATION_RAD, LIGHT, MATERIALS, MODELS, SCENE_CACHE_SIZE, SCENE_CLASSES,
  SCENE_ELEVATION_RAD, SCENE_MIN_PX, TURN_RAD_S, VARIANT_GROUPS, WATER, WATER_RING,
} from "./unit-models.js";
import { buildTree } from "./model-bsp.js";

const FRAME_MS = 1000 / 30;
const prepared = new Map();
// Per-type variants (src/ui/unit_variants.py), loaded by group on first use.
const variants = new Map(), variantNav = new Map(), loading = new Map();
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const GROUP_MODULES = {
  naval: () => import("./unit-variants-naval.js"),
  civil: () => import("./unit-variants-civil.js"),
  subs: () => import("./unit-variants-subs.js"),
};

export function loadVariant(key) {
  if (!own(VARIANT_GROUPS, key)) return Promise.resolve(false);
  if (variants.has(key)) return Promise.resolve(true);
  const group = VARIANT_GROUPS[key];
  if (!loading.has(group) && own(GROUP_MODULES, group)) {
    loading.set(group, GROUP_MODULES[group]().then((module) => {
      for (const [name, mesh] of Object.entries(module.VARIANTS)) variants.set(name, mesh);
      for (const [name, nav] of Object.entries(module.NAV)) variantNav.set(name, nav);
      return true;
    }).catch(() => false));
  }
  return (loading.get(group) || Promise.resolve(false)).then(() => variants.has(key));
}

// The model to draw for catalog type ``key`` of class ``cls``: its own
// variant once loaded (the load starts here), the class model until then.
export function modelKey(key, cls) {
  if (typeof key !== "string" || !own(VARIANT_GROUPS, key)) return cls;
  if (variants.has(key)) return key;
  loadVariant(key);
  return cls;
}

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
  const data = (own(MODELS, cls) && MODELS[cls]) || variants.get(cls) || MODELS.unknown;
  const verts = [];
  for (let i = 0; i < data.v.length; i += 3) verts.push([data.v[i] / 1000, data.v[i + 1] / 1000, data.v[i + 2] / 1000]);
  const sided = new Set(data.s);
  const faces = data.f.map((face, index) => {
    const points = face.map((k) => verts[k]);
    return { normal: newell(points), color: MATERIALS[data.m[index]], sided: sided.has(index) };
  });
  const radius = Math.max(...verts.map((p) => Math.hypot(p[0], p[1], p[2])));
  const horizontal = Math.max(...verts.map((p) => Math.hypot(p[0], p[1])));
  const height = Math.max(...verts.map((p) => Math.abs(p[2])));
  const tree = buildTree(verts, data.f, faces.map((face) => face.normal), data.l);
  mesh = { faces, lines: data.l, tree, floating: data.w, radius, horizontal, height };
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

// Faces in back-to-front order with their light factor (hidden back faces
// left out): [kind, index, shade], kind 0 a tree face, 1 a tree line.
function ordered(mesh, view) {
  const shades = mesh.faces.map((face) => {
    const normal = apply(view, face.normal);
    const facing = normal[2] > 0;
    if (!facing && !face.sided) return null;
    const dot = normal[0] * LIGHT[0] + normal[1] * LIGHT[1] + normal[2] * LIGHT[2];
    return 0.34 + 0.66 * (facing ? Math.max(0, dot) : Math.abs(dot));
  });
  const items = [];
  for (const [kind, index] of mesh.tree.order(view[2])) {
    if (kind) { items.push([1, index, 1]); continue; }
    const shade = shades[mesh.tree.faceSrc[index]];
    if (shade !== null) items.push([0, index, shade]);
  }
  return items;
}

export function drawModel(ctx, width, height, cls, yaw, elevation = ELEVATION_RAD) {
  const mesh = prepare(cls);
  const view = viewMatrix(yaw, elevation);
  const verts = mesh.tree.verts.map((p) => apply(view, p));
  const vertical = mesh.horizontal * Math.sin(elevation) + mesh.height * Math.cos(elevation);
  const reach = mesh.floating ? Math.max(mesh.radius, WATER_RING) : mesh.radius;
  const scale = 0.92 * Math.min(width / (2 * reach), height / (2 * vertical));
  const cx = width / 2, cy = height / 2;
  const screen = verts.map((p) => {
    const persp = 1 / (1 - p[2] / (5 * mesh.radius));
    return [cx + p[0] * scale * persp, cy - p[1] * scale * persp];
  });
  const items = ordered(mesh, view);
  ctx.clearRect(0, 0, width, height);
  if (mesh.floating) {
    ctx.strokeStyle = rgb(WATER);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(cx, cy, scale * WATER_RING, scale * WATER_RING * Math.sin(elevation), 0, 0, 2 * Math.PI);
    ctx.stroke();
  }
  ctx.lineJoin = "round";
  for (const [kind, index, shade] of items) {
    if (kind) {
      const [a, b] = mesh.tree.lines[index];
      ctx.strokeStyle = rgb(MATERIALS[mesh.lines[mesh.tree.lineSrc[index]][2]]);
      ctx.lineWidth = Math.max(1, scale / 260);
      ctx.beginPath();
      ctx.moveTo(...screen[a]);
      ctx.lineTo(...screen[b]);
      ctx.stroke();
      continue;
    }
    const face = mesh.faces[mesh.tree.faceSrc[index]];
    const color = rgb(face.color.map((c) => c * shade));
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    mesh.tree.faces[index].forEach((k, i) => (i ? ctx.lineTo(...screen[k]) : ctx.moveTo(...screen[k])));
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  return items.length;
}

// --- the eyepieces (src/ui/unit_models.py draw_in_scene) --------------------
const sceneCache = new Map();

// Observer ``aob`` degrees off the bow (starboard positive): abeam to
// starboard the bow points right, bow on at 0.
const sceneYaw = (aob) => (aob - 90) * Math.PI / 180;

function renderSceneSprite(cls, length, aob, color, surfaceOnly) {
  const mesh = prepare(cls);
  const view = viewMatrix(sceneYaw(aob), SCENE_ELEVATION_RAD);
  const verts = mesh.tree.verts.map((p) => apply(view, p));
  const sx = verts.map((p) => p[0] * length), sy = verts.map((p) => -p[1] * length);
  const left = Math.floor(Math.min(...sx)) - 2, top = Math.floor(Math.min(...sy)) - 2;
  const width = Math.ceil(Math.max(...sx)) - left + 3, height = Math.ceil(Math.max(...sy)) - top + 3;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, width); canvas.height = Math.max(1, height);
  const g = canvas.getContext("2d");
  const tone = Math.min(1.25, Math.max(.05, (color[0] + color[1] + color[2]) / 3 / 150));
  const items = ordered(mesh, view);
  const px = (k) => [sx[k] - left, sy[k] - top];
  const lineColor = rgb(color.map((c) => Math.floor(c * .6)));
  for (const [kind, index, shade] of items) {
    if (kind) {
      const [a, b] = mesh.tree.lines[index];
      g.strokeStyle = lineColor; g.lineWidth = Math.max(1, Math.floor(length / 260));
      g.beginPath(); g.moveTo(...px(a)); g.lineTo(...px(b)); g.stroke();
      continue;
    }
    const face = mesh.faces[mesh.tree.faceSrc[index]];
    const fill = rgb(face.color.map((c, i) => .5 * c * shade * tone + .5 * color[i] * (.55 + .6 * shade)));
    g.fillStyle = fill; g.strokeStyle = fill; g.lineWidth = .5;
    g.beginPath();
    mesh.tree.faces[index].forEach((k, i) => (i ? g.lineTo(...px(k)) : g.moveTo(...px(k))));
    g.closePath(); g.fill(); g.stroke();
  }
  if (surfaceOnly) {
    // The hull below the waterline stays in the sea.
    const cut = -top + 1 + Math.ceil(.1 * Math.sin(SCENE_ELEVATION_RAD) * length);
    if (cut < height) g.clearRect(0, cut, width, height - cut);
  }
  return {canvas, ox: -left, oy: -top};
}

function sceneSprite(cls, length, aob, color, surfaceOnly) {
  const key = `${cls}|${length}|${aob}|${color.join(",")}|${surfaceOnly}`;
  let sprite = sceneCache.get(key);
  if (sprite) sceneCache.delete(key);
  else {
    sprite = renderSceneSprite(cls, length, aob, color, surfaceOnly);
    while (sceneCache.size >= SCENE_CACHE_SIZE) sceneCache.delete(sceneCache.keys().next().value);
  }
  sceneCache.set(key, sprite);
  return sprite;
}

// Draws ``cls`` in an eyepiece turned by the judged angle on the bow,
// ``width`` px long, afloat on ``base`` (``aloft``: an aircraft centred on
// it).  Returns the frame for its navigation lights, or null when it is too
// small or not turned, so the caller draws the flat silhouette instead;
// ``model`` is the identified type (its own variant and light positions).
export function drawInScene(g, cls, cx, base, width, color, aob, aloft = false, model = null) {
  if (!Number.isFinite(aob) || !SCENE_CLASSES.includes(cls) || width < SCENE_MIN_PX) return null;
  const length = Math.floor(width);
  if (cls === "aircraft" && !aloft) base -= .25 * length;   // hovering over the horizon
  // An identified type is drawn as its own variant.
  const key = model === null ? cls : modelKey(model, cls);
  const {canvas, ox, oy} = sceneSprite(key, length, aob, color.map((c) => Math.floor(c / 4) * 4), cls !== "aircraft");
  g.drawImage(canvas, Math.floor(cx) - ox, Math.floor(base) - oy);
  const view = viewMatrix(sceneYaw(aob), SCENE_ELEVATION_RAD);
  const lift = cls === "aircraft" ? AIRCRAFT_LIFT : 0;
  const point = (u, v) => {
    const p = apply(view, [.5 - u, 0, v - lift]);
    return [cx + p[0] * length, base - p[1] * length];
  };
  return {point, poly: (points) => points.map(([u, v]) => point(u, v)), nav: variantNav.get(key) || null};
}

// Turns the model while the canvas is in the page; dragging turns it by
// hand, and with reduced motion it stands still until dragged.
export function mountModel(canvas, key) {
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
    drawModel(ctx, width, height, modelKey(key, modelClass(key)), turnAngle(still ? 0 : (now - start) / 1000) + offset);
  };
  const frame = (now) => {
    if (!canvas.isConnected) return;
    if (!document.hidden && now - last >= FRAME_MS && (!still || dragX !== null || !last)) {
      last = now;
      paint(now);
    }
    requestAnimationFrame(frame);
  };
  // The type's own variant arrives with its group: draw it once loaded.
  loadVariant(key).then((loaded) => { if (loaded && canvas.isConnected) paint(performance.now()); });
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
