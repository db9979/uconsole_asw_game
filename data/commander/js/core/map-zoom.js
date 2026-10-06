// Zoom range of the browser charts, as on the uConsole (config.MAP_ZOOM_*):
// out to the whole sea area and in until the shorter side of the chart shows
// half a sea mile, the uConsole's detail zoom.
export const MAP_ZOOM_MIN = .5;
export const MAP_DETAIL_NM = .5;

// `fit` is the share of the shorter side the whole sea area takes at zoom 1.
export const mapZoomMax = (sizeNm, fit = 1) => Math.max(MAP_ZOOM_MIN, sizeNm / (MAP_DETAIL_NM * fit));
export const clampMapZoom = (zoom, sizeNm, fit = 1) =>
  Math.max(MAP_ZOOM_MIN, Math.min(mapZoomMax(sizeNm, fit), zoom));

// A round grid step in sea miles at least `minPx` pixels apart (1, 2, 5 x 10^n).
export function mapGridStep(pxPerNm, minPx = 110) {
  const rough = minPx / pxPerNm;
  const power = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 5, 10].find((n) => n * power >= rough) * power;
}

// Decimals that show a distance or grid value at this step without noise.
export const stepDecimals = (step) => (step >= 1 ? 0 : step >= .1 ? 1 : 2);

// Two-finger pinch on a canvas: calls onZoom(factor, x, y) with the change of
// finger spread around the midpoint (canvas pixels). Returns `active()`, true
// while two fingers are down, so one-finger drags can stand aside.
export function wirePinch(element, onZoom) {
  const touches = new Map();
  let spread = 0;
  const geometry = () => {
    const [a, b] = [...touches.values()];
    const rect = element.getBoundingClientRect();
    return {spread: Math.hypot(a.x - b.x, a.y - b.y),
      x: (a.x + b.x) / 2 - rect.left, y: (a.y + b.y) / 2 - rect.top};
  };
  element.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "touch") return;
    touches.set(event.pointerId, {x: event.clientX, y: event.clientY});
    if (touches.size === 2) spread = geometry().spread;
  });
  element.addEventListener("pointermove", (event) => {
    if (!touches.has(event.pointerId)) return;
    touches.set(event.pointerId, {x: event.clientX, y: event.clientY});
    if (touches.size !== 2) return;
    const now = geometry();
    if (spread > 0 && now.spread > 0 && Math.abs(now.spread - spread) > 2) {
      onZoom(now.spread / spread, now.x, now.y);
      spread = now.spread;
    }
  });
  const lift = (event) => { touches.delete(event.pointerId); spread = touches.size === 2 ? geometry().spread : 0; };
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) element.addEventListener(type, lift);
  return () => touches.size >= 2;
}
