// Damage-control pictures drawn like a ship's damage-control board, the
// same drawings as the uConsole (src/ui/damage_section.py): the frigate as a
// side profile (bow right) with sea, waterline, draft marks, compartments at
// their real height, floodwater tilted by the trim, holes with water rushing
// in, fitted patches, pumps discharging over the side and the teams; the
// cross-section that lists with the ship and holds the two hull voids; the
// submarine as a cutaway of its pressure hull with sail, fittings, water,
// fire, chlorine, leaks and the round bulkhead doors. Own-ship truth only.

/* geometry:begin */
export const GEOMETRY = {"frigate":{"x_range":[-76.0,77.0],"z_range":[-2.5,41.0],"hull":[[-74.0,4.0],[-74.0,10.0],[-20.0,10.0],[40.0,10.5],[62.0,12.0],[75.0,14.5],[73.0,9.0],[70.0,4.0],[66.0,0.8],[60.0,0.0],[-55.0,0.0],[-66.0,2.0],[-72.0,3.0]],"dome":[[62.0,0.5],[66.0,-1.0],[72.0,-0.2],[74.0,2.5],[70.0,3.5]],"blocks":[[[-50.0,10.0],[-50.0,17.0],[-30.0,17.0],[-28.0,22.0],[-14.0,22.0],[-12.0,17.0],[-4.0,17.0],[-4.0,10.0]],[[-26.0,22.0],[-24.0,27.0],[-17.0,27.0],[-16.0,22.0]],[[-22.7,27.0],[-23.0,28.8],[-21.8,30.6],[-19.2,30.6],[-18.0,28.8],[-18.3,27.0]],[[10.0,10.3],[10.0,19.0],[14.0,19.0],[14.0,23.0],[33.0,23.0],[36.0,19.0],[40.0,16.0],[41.0,10.5]],[[14.0,23.0],[16.0,33.0],[20.0,36.0],[23.0,33.0],[24.0,23.0]],[[46.0,11.1],[47.0,13.2],[53.0,13.2],[54.0,11.4]],[[36.5,17.6],[36.5,19.4],[39.0,19.4],[39.0,17.6]],[[-44.0,17.0],[-44.0,18.8],[-40.0,18.8],[-40.0,17.0]],[[-2.0,12.4],[-1.0,11.2],[8.0,11.2],[9.0,12.4]],[[-68.0,1.5],[-68.0,-1.8],[-63.0,-1.8],[-63.0,1.2]]],"lines":[[[19.5,36.0],[19.5,40.5]],[[53.0,12.6],[61.0,13.2]],[[4.0,10.3],[4.0,30.0]],[[1.5,26.0],[6.5,26.0]],[[-60.0,0.0],[-60.0,-1.6]],[[-61.2,-0.8],[-58.8,-0.8]],[[25.0,22.0],[32.5,22.0]]],"draft_marks":[[-74.6,4.0],[-74.6,6.0],[-74.6,8.0],[-74.6,10.0],[70.4,4.0],[71.6,6.0],[72.8,8.0],[73.8,10.0]],"decks":[[[-72.0,6.0],[70.0,6.0]],[[-64.0,2.5],[66.0,2.5]],[[-50.0,13.5],[-4.0,13.5]],[[10.0,13.5],[41.0,13.5]],[[10.0,16.5],[38.0,16.5]],[[14.0,19.5],[34.0,19.5]],[[-30.0,0.5],[-30.0,10.0]],[[-14.0,0.5],[-14.0,10.0]],[[-56.0,0.5],[-56.0,10.0]],[[-6.0,0.5],[-6.0,10.0]],[[40.0,0.5],[40.0,10.5]],[[56.0,0.5],[56.0,11.5]]],"rooms":{"sonar":[[56.0,0.5],[64.0,0.5],[68.0,3.0],[68.0,6.0],[56.0,6.0]],"bridge":[[24.0,19.6],[32.0,19.6],[32.0,22.6],[24.0,22.6]],"weapons":[[40.0,1.0],[56.0,1.0],[56.0,7.5],[40.0,7.5]],"opz":[[16.0,4.0],[40.0,4.0],[40.0,8.0],[16.0,8.0]],"radio":[[12.0,10.8],[24.0,10.8],[24.0,16.2],[12.0,16.2]],"engine":[[-38.0,0.5],[-6.0,0.5],[-6.0,7.5],[-38.0,7.5]],"flightdeck":[[-48.0,10.2],[-32.0,10.2],[-32.0,16.6],[-48.0,16.6]]},"section":{"y_range":[-10.5,10.5],"z_range":[-1.0,13.0],"shell":[[-8.3,10.4],[-8.3,3.2],[-6.6,0.9],[-3.6,0.0],[3.6,0.0],[6.6,0.9],[8.3,3.2],[8.3,10.4]],"rooms":{"hull_left":[[-8.3,3.4],[-8.3,6.5],[-5.0,6.5],[-5.0,0.4],[-6.4,1.0]],"hull_right":[[8.3,3.4],[6.4,1.0],[5.0,0.4],[5.0,6.5],[8.3,6.5]]}}},"boat":{"order":["stern","engine","battery","quarters","control","bow"],"share":[0.14,0.2,0.17,0.15,0.18,0.16]}};
/* geometry:end */

import { contrastHex, themeName } from "../core/palette.js";

// Night board and the light day board; floodwater, fire and teams keep their colours.
const BOARDS = {
  night: {HULL: "#283238", ROOM: "#162c30", STEEL: "#96a8ac", STEEL_DIM: "#54646a", SEA: "#061e34",
    SEA_LINE: "#5aa0c8", WATER_TOP: "#84c2df", SPRAY: "#a0d6f0", GAS: "rgba(150, 190, 60, .32)",
    MARK: "#d2dedc", INK: "#aabaaa", DOOR: "#0a1418",
    TINTS: {stern: "#5c5628", engine: "#604624", battery: "#5a2e2c", quarters: "#2e5434", control: "#404268", bow: "#603630"}},
  day: {HULL: "#cbd5df", ROOM: "#e8edf3", STEEL: "#334155", STEEL_DIM: "#94a3b8", SEA: "#dbeafe",
    SEA_LINE: "#2563eb", WATER_TOP: "#1d4ed8", SPRAY: "#3b82f6", GAS: "rgba(101, 163, 13, .35)",
    MARK: "#475569", INK: "#475569", DOOR: "#e8edf3",
    TINTS: {stern: "#e7dfb0", engine: "#ecd2ad", battery: "#f0c8c4", quarters: "#c9e3cc", control: "#cfd2ee", bow: "#efc9c1"}},
};
const WATER = "rgba(40, 110, 160, .72)";
let HULL, ROOM, STEEL, STEEL_DIM, SEA, SEA_LINE, WATER_TOP, SPRAY, GAS, MARK, INK, DOOR, TINTS;

// High contrast derives from the night board (the same rule as the console).
BOARDS.contrast = Object.fromEntries(Object.entries(BOARDS.night).map(([key, value]) =>
  [key, key === "TINTS" ? Object.fromEntries(Object.entries(value).map(([name, tint]) =>
    [name, contrastHex(tint)])) : value.startsWith("#") ? contrastHex(value) : value]));

function usePalette() {
  ({HULL, ROOM, STEEL, STEEL_DIM, SEA, SEA_LINE, WATER_TOP, SPRAY, GAS, MARK, INK, DOOR, TINTS} =
    BOARDS[themeName()]);
}

const phase = () => (typeof performance !== "undefined" ? performance.now() : Date.now()) / 1000;

function path(g, pts, close = true) {
  g.beginPath();
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
  if (close) g.closePath();
}

function profileView(box) {
  const [x0, x1] = GEOMETRY.frigate.x_range, [z0, z1] = GEOMETRY.frigate.z_range;
  const scale = Math.max(.5, Math.min(box.width / (x1 - x0), box.height / (z1 - z0)));
  const ox = box.x + box.width / 2 - (x0 + x1) / 2 * scale, oy = box.y + box.height / 2 + (z0 + z1) / 2 * scale;
  const point = (x, z) => [ox + x * scale, oy - z * scale];
  return {scale, point, points: (coords) => coords.map(([x, z]) => point(x, z))};
}

function sectionView(box, heelDeg, pivotZ) {
  const geo = GEOMETRY.frigate.section, [y0, y1] = geo.y_range, [z0, z1] = geo.z_range;
  const scale = Math.max(.5, Math.min(box.width / (y1 - y0), box.height / (z1 - z0)));
  const cx = box.x + box.width / 2, py = box.y + box.height / 2 + ((z0 + z1) / 2 - pivotZ) * scale;
  const heel = Math.max(-40, Math.min(40, heelDeg)) * Math.PI / 180, c = Math.cos(heel), s = Math.sin(heel);
  const point = (y, z) => { const dz = z - pivotZ; return [cx + (y * c + dz * s) * scale, py - (dz * c - y * s) * scale]; };
  return {scale, cx, py, point, points: (coords) => coords.map(([y, z]) => point(y, z))};
}

function bounds(pts) {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x = Math.min(...xs), y = Math.min(...ys);
  return {x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y};
}

function jet(g, [sx, sy], [tx, ty], length) {
  const angle = Math.atan2(ty - sy, tx - sx), wobble = Math.sin(phase() * 9) * .12;
  g.save(); g.strokeStyle = SPRAY;
  for (const spread of [-.35, 0, .35]) {
    const a = angle + spread + wobble;
    g.lineWidth = spread === 0 ? 2 : 1; g.beginPath();
    for (let step = 0; step <= 5; step++) {
      const t = step / 5, x = sx + Math.cos(a) * length * t, y = sy + Math.sin(a) * length * t + length * .35 * t * t;
      if (step) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.stroke();
  }
  g.restore();
}

function hole(g, [cx, cy], radius, patched, colors) {
  const r = Math.max(3, radius);
  g.save();
  if (patched) {
    g.fillStyle = "#60686c"; g.strokeStyle = "#a0aaac";
    g.fillRect(cx - r - 2, cy - r - 2, 2 * r + 4, 2 * r + 4); g.strokeRect(cx - r - 2, cy - r - 2, 2 * r + 4, 2 * r + 4);
  } else {
    const pts = [];
    for (let k = 0; k < 8; k++) { const f = k % 2 ? 1 : .55; pts.push([cx + r * Math.cos(k * Math.PI / 4) * f, cy + r * Math.sin(k * Math.PI / 4) * f]); }
    path(g, pts); g.fillStyle = "#04080a"; g.fill(); g.strokeStyle = colors.red; g.lineWidth = 1; g.stroke();
  }
  g.restore();
}

function flames(g, box, fire, seed, colors) {
  const {x, y, width: w, height: h} = box, t = phase();
  const glow = g.createRadialGradient(x + w / 2, y + h * .6, 2, x + w / 2, y + h * .6, Math.max(w, h) * .7);
  glow.addColorStop(0, "rgba(255, 140, 50, .9)"); glow.addColorStop(1, "transparent");
  g.globalAlpha = Math.min(.9, .3 + fire * .6); g.fillStyle = glow; g.fillRect(x, y, w, h); g.globalAlpha = 1;
  const count = 2 + Math.round(5 * fire), base = y + h - 2;
  for (let k = 0; k < count; k++) {
    const fx = x + w * (k + .5) / count, flicker = .65 + .35 * Math.sin(t * 7 + seed * 1.7 + k * 2.3);
    const fh = h * (.25 + .45 * fire) * flicker, fw = Math.max(3, w / count * .4);
    g.fillStyle = `rgba(255, ${140 + (k * 37) % 60}, 40, .7)`;
    path(g, [[fx - fw, base], [fx, base - fh], [fx + fw, base]]); g.fill();
  }
  g.fillStyle = `rgba(70, 72, 76, ${(.35 + .3 * fire).toFixed(2)})`;
  g.fillRect(x, y, w, h * (.15 + .25 * fire));
  void colors;
}

function water(g, box, left, right, seed = 0) {
  const t = phase(), top = [];
  for (let step = 0; step <= 8; step++) top.push([box.x + box.width * step / 8, left + (right - left) * step / 8 + 1.2 * Math.sin(t * 2.2 + step * .9 + seed)]);
  g.fillStyle = WATER; path(g, [...top, [box.x + box.width, box.y + box.height + 2], [box.x, box.y + box.height + 2]]); g.fill();
  g.strokeStyle = WATER_TOP; g.lineWidth = 2; path(g, top, false); g.stroke(); g.lineWidth = 1;
}

function hatching(g, box, colors) {
  g.save(); g.strokeStyle = colors.red; g.globalAlpha = .5; g.lineWidth = 1;
  for (let d = -box.height; d < box.width; d += 9) { g.beginPath(); g.moveTo(box.x + d, box.y + box.height); g.lineTo(box.x + d + box.height, box.y); g.stroke(); }
  g.restore();
}

function badges(g, cx, cy, teams, r, colors, selectedTeam) {
  teams.forEach((team, index) => {
    const x = cx + (index - (teams.length - 1) / 2) * (2 * r + 4);
    g.fillStyle = team === selectedTeam ? colors.amber : colors.accent;
    g.beginPath(); g.arc(x, cy, r, 0, Math.PI * 2); g.fill();
    g.fillStyle = colors.bg; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(team), x, cy + 1);
  });
}

function roomEdge(room, selected, colors) {
  if (selected) return colors.text;
  if (room.state === "ZERSTOERT" || room.fire > 0) return colors.red;
  return room.flood > 0 ? colors.amber : "#286e64";
}

// The side profile; returns hit boxes {key, x, y, width, height}.
export function drawFrigateProfile(g, box, payload, colors, selectedTeam) {
  usePalette();
  const frigate = GEOMETRY.frigate, view = profileView(box), stability = payload.stability;
  const draft = stability.draft_m, trim = stability.trim_deg, tan = Math.tan(trim * Math.PI / 180);
  const byKey = new Map(payload.compartments.map((room) => [room.key, room]));
  const [left, right] = frigate.x_range;
  const sea = [view.point(left, draft + left * tan), view.point(right, draft + right * tan)];
  g.save(); g.beginPath(); g.rect(box.x, box.y, box.width, box.height); g.clip();
  g.fillStyle = SEA; path(g, [...sea, [box.x + box.width, box.y + box.height], [box.x, box.y + box.height]]); g.fill();
  g.lineWidth = 1;
  for (const coords of frigate.blocks) { path(g, view.points(coords)); g.fillStyle = HULL; g.fill(); g.strokeStyle = STEEL; g.stroke(); }
  path(g, view.points(frigate.hull)); g.fillStyle = HULL; g.fill();
  path(g, view.points(frigate.dome)); g.fill(); g.strokeStyle = STEEL_DIM; g.stroke();
  for (const [a, b] of frigate.decks) { g.beginPath(); g.moveTo(...view.point(...a)); g.lineTo(...view.point(...b)); g.stroke(); }
  g.strokeStyle = STEEL; g.lineWidth = 2;
  for (const [a, b] of frigate.lines) { g.beginPath(); g.moveTo(...view.point(...a)); g.lineTo(...view.point(...b)); g.stroke(); }
  g.lineWidth = 1; g.strokeStyle = MARK;
  for (const [x, z] of frigate.draft_marks) { const [mx, my] = view.point(x, z); g.beginPath(); g.moveTo(mx - 3, my); g.lineTo(mx + 3, my); g.stroke(); }
  g.strokeStyle = SEA_LINE; g.beginPath(); g.moveTo(...sea[0]); g.lineTo(...sea[1]); g.stroke();
  const hits = [];
  Object.entries(frigate.rooms).forEach(([key, coords], index) => {
    const room = byKey.get(key);
    if (!room) return;
    const pts = view.points(coords), area = bounds(pts), teams = payload.teams.filter((team) => team.compartment === key).map((team) => team.team);
    const xs = coords.map((p) => p[0]), zs = coords.map((p) => p[1]);
    const xLo = Math.min(...xs), xHi = Math.max(...xs), xc = xs.reduce((a, b) => a + b, 0) / xs.length;
    const floor = Math.min(...zs), top = Math.max(...zs);
    const flood = Math.max(0, Math.min(100, room.flood)) / 100, fire = Math.max(0, Math.min(100, room.fire)) / 100;
    g.save(); path(g, pts); g.fillStyle = ROOM; g.fill(); g.clip();
    if (fire) flames(g, area, fire, index, colors);
    if (flood) {
      const level = floor + flood * (top - floor);
      water(g, area, view.point(xLo, level + (xLo - xc) * tan)[1], view.point(xHi, level + (xHi - xc) * tan)[1], index);
    }
    if (room.state === "ZERSTOERT") hatching(g, area, colors);
    g.restore();
    const mine = teams.includes(selectedTeam);
    path(g, pts); g.strokeStyle = roomEdge(room, mine, colors); g.lineWidth = mine ? 3 : room.state === "OK" && !room.flood ? 1 : 2; g.stroke(); g.lineWidth = 1;
    g.fillStyle = colors.muted; g.textAlign = "left"; g.textBaseline = "top";
    const number = payload.compartments.findIndex((row) => row.key === key) + 1;
    g.fillText(String(number).padStart(2, "0"), area.x + 3, area.y + 2, Math.max(8, area.width - 6));
    if (room.leak !== "none") {
      const z = floor + .3 * Math.max(.6, Math.min(top, draft) - floor), centre = view.point(xc, z);
      hole(g, centre, Math.max(3, .9 * view.scale), room.leak === "patched", colors);
      if (room.inflow > 0) { const len = view.scale * Math.min(5, 1.5 + 6 * Math.sqrt(room.inflow / .1)); jet(g, centre, [centre[0] + len, centre[1] - len * .4], len); }
    }
    if (teams.length) {
      const r = Math.max(7, Math.min(11, area.height * .25));
      badges(g, area.x + area.width / 2, area.y + area.height - r - 3, teams, r, colors, selectedTeam);
      if (flood) { const [sx, sy] = view.point(xc, Math.max(top, 10)); jet(g, [sx, sy - 2], [sx + 3 * view.scale, sy - view.scale], 2.5 * view.scale); }
    }
    hits.push({key, ...area});
  });
  g.strokeStyle = STEEL; g.lineWidth = 2; path(g, view.points(frigate.hull)); g.stroke(); g.lineWidth = 1;
  g.restore();
  return hits;
}

// The listing cross-section with both hull voids; returns their hit boxes.
export function drawFrigateSection(g, box, payload, colors, selectedTeam) {
  usePalette();
  const geo = GEOMETRY.frigate.section, stability = payload.stability;
  const view = sectionView(box, stability.list_deg, stability.draft_m);
  const byKey = new Map(payload.compartments.map((room) => [room.key, room]));
  g.save(); g.beginPath(); g.rect(box.x, box.y, box.width, box.height); g.clip();
  g.fillStyle = SEA; g.fillRect(box.x, view.py, box.width, box.y + box.height - view.py);
  const shell = view.points(geo.shell);
  path(g, shell); g.fillStyle = HULL; g.fill();
  g.strokeStyle = SEA_LINE; g.beginPath(); g.moveTo(box.x, view.py); g.lineTo(box.x + box.width, view.py); g.stroke();
  const hits = [];
  for (const [key, coords] of Object.entries(geo.rooms)) {
    const room = byKey.get(key);
    if (!room) continue;
    const pts = view.points(coords), area = bounds(pts), teams = payload.teams.filter((team) => team.compartment === key).map((team) => team.team);
    const flood = Math.max(0, Math.min(100, room.flood)) / 100;
    g.save(); path(g, pts); g.fillStyle = ROOM; g.fill(); g.clip();
    if (flood) {
      const zs = coords.map((p) => p[1]), floor = Math.min(...zs), top = Math.max(...zs);
      const yc = coords.reduce((a, p) => a + p[0], 0) / coords.length, level = view.point(yc, floor + flood * (top - floor))[1];
      water(g, area, level, level);
    }
    if (room.state === "ZERSTOERT") hatching(g, area, colors);
    g.restore();
    const mine = teams.includes(selectedTeam);
    path(g, pts); g.strokeStyle = roomEdge(room, mine, colors); g.lineWidth = mine ? 3 : 1.5; g.stroke(); g.lineWidth = 1;
    if (room.leak !== "none") {
      const side = key === "hull_left" ? -1 : 1, centre = view.point(8.3 * side, 2.4);
      hole(g, centre, Math.max(3, .5 * view.scale), room.leak === "patched", colors);
      if (room.inflow > 0) { const inner = view.point(5.8 * side, 2.8); jet(g, centre, inner, Math.abs(inner[0] - centre[0])); }
    }
    if (teams.length) badges(g, area.x + area.width / 2, area.y + area.height / 2, teams, 8, colors, selectedTeam);
    hits.push({key, ...area});
  }
  g.strokeStyle = STEEL; g.lineWidth = 2; path(g, shell, false); g.stroke(); g.lineWidth = 1;
  g.strokeStyle = Math.abs(stability.list_deg) >= 5 ? colors.amber : STEEL;
  g.beginPath(); g.moveTo(...view.point(0, 12.5)); g.lineTo(...view.point(0, 0)); g.stroke();
  g.strokeStyle = STEEL_DIM; g.beginPath(); g.moveTo(view.cx, box.y + 4); g.lineTo(view.cx, view.py); g.stroke();
  g.restore();
  return hits;
}

function boatCells(box) {
  if (box.height > box.width * .3) {                // keep the boat's proportions
    const height = box.width * .3;
    box = {...box, y: box.y + (box.height - height) / 2, height};
  }
  const towerH = Math.max(12, box.height / 4);
  const body = {x: box.x + 2, y: box.y + towerH, width: box.width - 4, height: box.height - towerH};
  const deckY = body.y + Math.max(3, body.height / 9), keelY = body.y + body.height - Math.max(3, body.height / 10);
  const bx = body.x, bw = body.width, br = body.x + body.width;
  const outer = [[bx, deckY + (keelY - deckY) * .4], [bx + bw * .05, deckY], [bx + bw * .84, deckY],
    [br - bw * .03, body.y + 1], [br, body.y + 2], [br - bw * .02, deckY + (keelY - deckY) / 2],
    [br - bw * .07, keelY], [bx + bw * .12, keelY], [bx + bw * .04, deckY + (keelY - deckY) * .75]];
  const hull = {x: bx + bw * .07, y: deckY + Math.max(3, body.height / 12), width: bw * .82};
  hull.height = keelY - Math.max(4, body.height / 7) - hull.y;
  const taper = Math.max(6, hull.width / 14), hb = hull.y + hull.height, hr = hull.x + hull.width;
  const pressure = [[hull.x, hull.y + hull.height * .3], [hull.x + taper, hull.y], [hr - taper, hull.y], [hr, hull.y + hull.height * .3],
    [hr, hb - hull.height * .3], [hr - taper, hb], [hull.x + taper, hb], [hull.x, hb - hull.height * .3]];
  const tx = hull.x + hull.width * .5;
  const tower = [[tx - towerH * 1.6, deckY], [tx - towerH * 1.2, box.y + towerH * .35], [tx + towerH, box.y + towerH * .35], [tx + towerH * 1.5, deckY]];
  const cells = [];
  let x = hull.x;
  for (const share of GEOMETRY.boat.share) { cells.push({x, y: hull.y, width: hull.width * share, height: hull.height}); x += hull.width * share; }
  return {hull, outer, tower, pressure, cells};
}

// The submarine's cutaway; ``rooms`` in the damage model's order (bow
// first). Returns the cells by room name.
export function drawBoatSection(g, box, rooms, teams, trimDeg, colors) {
  usePalette();
  const {hull, outer, tower, pressure, cells} = boatCells(box), order = GEOMETRY.boat.order;
  const byName = new Map(rooms.map((room) => [room.name, room]));
  const tan = Math.tan(Math.max(-20, Math.min(20, trimDeg)) * Math.PI / 180) * 1.5, t = phase();
  g.save();
  g.lineWidth = 1; g.fillStyle = HULL; g.strokeStyle = STEEL;
  path(g, outer); g.fill(); g.stroke(); path(g, tower, false); g.fill(); g.stroke();
  const span = tower[2][0] - tower[1][0], top = tower[1][1];
  g.lineWidth = 2;
  for (const [share, height] of [[.25, 1], [.45, .8], [.7, .6]]) { const mx = tower[1][0] + span * share; g.beginPath(); g.moveTo(mx, top); g.lineTo(mx, box.y + (top - box.y) * (1 - height)); g.stroke(); }
  g.lineWidth = 1;
  g.save(); path(g, pressure); g.fillStyle = ROOM; g.fill(); g.clip();
  const ink = INK, floor = hull.y + hull.height * 2 / 3, byCell = {};
  order.forEach((name, position) => {
    const cell = cells[position], room = byName.get(name);
    byCell[name] = cell;
    g.fillStyle = TINTS[name]; g.globalAlpha = .6; g.fillRect(cell.x, cell.y, cell.width, cell.height); g.globalAlpha = 1;
    g.strokeStyle = ink;
    if (name === "stern" || name === "bow") {
      g.fillStyle = "#3c608c";
      const th = Math.max(2, cell.height / 9);
      for (const k of [0, 1]) g.fillRect(cell.x + (name === "bow" ? cell.width / 3 : 2), cell.y + cell.height / 2 - th - 1 + k * (th + 2), cell.width * 2 / 3 - 4, th);
    } else if (name === "engine") {
      for (const k of [0, 1]) g.strokeRect(cell.x + 4 + k * cell.width / 2, floor - cell.height / 3, cell.width / 2 - 8, cell.height / 3);
    } else if (name === "control") {
      for (const share of [.35, .6]) { g.beginPath(); g.moveTo(cell.x + cell.width * share, cell.y); g.lineTo(cell.x + cell.width * share, floor); g.stroke(); }
    } else if (name === "quarters") {
      for (const k of [1, 2]) { const y = cell.y + (floor - cell.y) * k / 3; g.beginPath(); g.moveTo(cell.x + 4, y); g.lineTo(cell.x + cell.width - 4, y); g.stroke(); }
    }
    if (name === "battery" || name === "quarters") {
      const w = Math.max(3, (cell.width - 6) / 7);
      g.strokeStyle = "#6e6046";
      for (let k = 0; k < 7; k++) g.strokeRect(cell.x + 3 + k * w, floor + 2, w - 1, Math.max(2, hull.y + hull.height - floor - 5));
    }
    if (!room) return;
    const fill = Math.max(0, Math.min(1, room.water_kg / Math.max(1, room.capacity_kg)));
    if (room.fire_pct > 0) flames(g, cell, Math.min(1, room.fire_pct / 100), position, colors);
    if (room.chlorine_pct > 0) {
      g.fillStyle = GAS;
      for (let k = 0; k < 6; k++) { g.beginPath(); g.arc(cell.x + cell.width * ((k * .37 + t * .03) % 1), cell.y + cell.height * (.2 + .25 * ((k * .61) % 1)), Math.max(4, cell.height / 5), 0, Math.PI * 2); g.fill(); }
    }
    if (fill > 0) {
      const level = cell.y + cell.height * (1 - fill), cx = cell.x + cell.width / 2;
      water(g, cell, level + (cx - cell.x) * tan, level - (cell.x + cell.width - cx) * tan, position);
    }
    if (room.down) hatching(g, cell, colors);
  });
  g.restore();
  g.strokeStyle = STEEL; g.lineWidth = 2; path(g, pressure); g.stroke();
  order.forEach((name, position) => {
    const cell = cells[position], room = byName.get(name);
    if (position) { g.beginPath(); g.moveTo(cell.x, cell.y + 1); g.lineTo(cell.x, cell.y + cell.height - 1); g.stroke(); }
    if (room && room.leak_pct > 0) {
      const centre = [cell.x + cell.width / 2, cell.y + cell.height - 2];
      hole(g, centre, 3 + 3 * Math.min(1, room.leak_pct / 100), false, colors);
      jet(g, centre, [centre[0] + cell.width / 5, centre[1] - cell.height / 2], Math.max(6, cell.height * .4 * Math.min(1.5, .5 + room.leak_pct / 100)));
    }
    const inside = teams.filter((team) => team.compartment === name).map((team) => team.team + 1);
    if (inside.length) badges(g, cell.x + cell.width / 2, cell.y + cell.height / 2, inside, Math.max(6, Math.min(10, cell.height / 5)), colors);
  });
  const radius = Math.max(4, hull.height / 8);
  for (let position = 1; position < cells.length; position++) {
    const a = byName.get(order[position - 1]), b = byName.get(order[position]);
    const shut = Boolean(a?.closed || b?.closed), x = cells[position].x, y = hull.y + hull.height / 2 - hull.height / 8;
    g.fillStyle = DOOR; g.beginPath(); g.arc(x, y, radius, 0, Math.PI * 2); g.fill();
    g.strokeStyle = shut ? colors.accent : STEEL_DIM; g.lineWidth = 2; g.stroke();
    if (shut) { g.beginPath(); g.moveTo(x - radius + 2, y); g.lineTo(x + radius - 2, y); g.moveTo(x, y - radius + 2); g.lineTo(x, y + radius - 2); g.stroke(); }
  }
  g.restore();
  return byCell;
}
