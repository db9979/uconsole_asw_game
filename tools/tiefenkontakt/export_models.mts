/**
 * Exports the low-poly ship models of Tiefenkontakt (github.com/db9979/tiefenkontakt,
 * apps/client/src/widgets/sea3d) as plain triangles for tools/build_tk_models.py.
 *
 * Run from a Tiefenkontakt checkout after `npm install` there:
 *   npx tsx /path/to/u-jagd/tools/tiefenkontakt/export_models.mts <tiefenkontakt dir> <out.json>
 *
 * Every opaque, visible mesh is written in world coordinates (metres, bow +z, waterline y = 0,
 * port +x) with one colour per triangle (material colour times the mean vertex colour) and the
 * size of the part it belongs to (so small fittings can be left out as a whole).
 * Wake, foam, smoke, glows and decals are left out; the navigation lamps are written apart.
 */
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

// The models paint hull numbers on canvases: a stub canvas keeps them headless.
const noop: any = new Proxy(function () {}, {
  get: (_t, p) => (p === 'measureText' ? () => ({ width: 10 }) : noop), apply: () => noop, set: () => true,
});
(globalThis as any).document = { createElement: () => ({ width: 0, height: 0, getContext: () => noop, style: {} }) };
(globalThis as any).window = globalThis;

const [root, outPath] = process.argv.slice(2).map((p) => resolve(p));
if (!root || !outPath) throw new Error('usage: export_models.mts <tiefenkontakt dir> <out.json>');
const url = (rel: string) => pathToFileURL(join(root, rel)).href;
const THREE = await import(pathToFileURL(join(root, 'node_modules/three/build/three.module.js')).href);
const { CLASSES } = await import(url('packages/shared/src/index.ts'));
const { shipModel, convoyModel } = await import(url('apps/client/src/widgets/sea3d/models.ts'));
const SKIP = /^(wake|bow|feather|smoke)$/;

function exportModel(g: any) {
  g.updateMatrixWorld(true);
  const t: number[] = [];
  const c: number[] = [];
  const nav: number[][] = [];
  const parts: number[] = [];   // per triangle: the size (m, box diagonal) of the part it belongs to
  const sides: number[] = [];   // per triangle: 1 when its material shows both sides
  const box = new THREE.Box3();
  const size = new THREE.Vector3();
  const v = new THREE.Vector3();
  g.traverse((o: any) => {
    if (o.isSprite && o.parent?.name === 'navlights') {
      o.getWorldPosition(v);
      const col = o.material.color;
      nav.push([+v.x.toFixed(3), +v.y.toFixed(3), +v.z.toFixed(3), col.r > col.g ? (col.g > 0.5 ? 'W' : 'R') : 'G'].map((x) => x) as any);
      return;
    }
    if (!o.isMesh) return;
    for (let p = o; p; p = p.parent) if (!p.visible || SKIP.test(p.name)) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const geo = o.geometry.index ? o.geometry.toNonIndexed() : o.geometry;
    const pos = geo.attributes.position;
    const vc = geo.attributes.color;
    const flip = o.matrixWorld.determinant() < 0;   // mirrored parts turn their winding
    const part = +box.setFromObject(o).getSize(size).length().toFixed(2);
    const groups = geo.groups.length ? geo.groups : [{ start: 0, count: pos.count, materialIndex: 0 }];
    for (const gr of groups) {
      const mt = Array.isArray(o.material) ? mats[gr.materialIndex ?? 0] : o.material;
      if (!mt || mt.transparent || mt.visible === false || !mt.color || mt.isMeshBasicMaterial || mt.isShaderMaterial) continue;
      const end = Math.min(pos.count, gr.start + gr.count);
      for (let i = gr.start; i + 2 < end; i += 3) {
        let r = 0, gg = 0, b = 0;
        for (const k of flip ? [0, 2, 1] : [0, 1, 2]) {
          v.fromBufferAttribute(pos, i + k).applyMatrix4(o.matrixWorld);
          t.push(+v.x.toFixed(3), +v.y.toFixed(3), +v.z.toFixed(3));
          if (mt.vertexColors && vc) { r += vc.getX(i + k); gg += vc.getY(i + k); b += vc.getZ(i + k); }
        }
        const col = mt.vertexColors && vc ? new THREE.Color(r / 3, gg / 3, b / 3).multiply(mt.color) : mt.color;
        parts.push(part);
        sides.push(mt.side === THREE.FrontSide ? 0 : 1);
        c.push(Math.round(col.r * 255), Math.round(col.g * 255), Math.round(col.b * 255));
      }
    }
  });
  return { t, c, p: parts, s: sides, nav };
}

const models: Record<string, unknown> = {};
for (const cls of Object.keys(CLASSES)) models[cls] = exportModel(shipModel(cls, 1));
for (const type of ['cargo', 'feeder', 'bulk', 'reefer', 'roro', 'tanker']) models[`convoy_${type}`] = exportModel(convoyModel(type));
const commit = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD']).toString().trim();
writeFileSync(outPath, JSON.stringify({ source: 'https://github.com/db9979/tiefenkontakt', commit, models }));
console.log(`${Object.keys(models).length} models from ${commit.slice(0, 10)} -> ${outPath}`);
