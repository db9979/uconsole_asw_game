// Canvas drawing cannot use CSS custom properties directly, so it reads the
// stylesheet tokens (css/tokens.css) through one hidden probe element, which
// resolves var() and color-mix() to plain rgb(). The colours depend on the
// colour theme (<html data-theme>), so the cache is dropped by
// invalidatePalette() whenever core/theme.js switches it.
let probe = null;
function resolveColor(name, fallback) {
  try {
    if (!probe) {
      probe = document.createElement("span");
      probe.hidden = true;
      probe.setAttribute("aria-hidden", "true");
      document.documentElement.append(probe);
    }
    probe.style.color = "";
    probe.style.color = `var(${name}, ${fallback})`;
    return getComputedStyle(probe).color || fallback;
  } catch { return fallback; }
}
// Affiliation colours: one palette for lists, badges and map symbols. The
// object is kept and refilled, so modules holding it see a theme switch.
const affiliationTokens = {UNKNOWN: ["--aff-unknown", "#fbbf24"], FRIEND: ["--aff-friend", "#60a5fa"],
  NEUTRAL: ["--aff-neutral", "#34d399"], HOSTILE: ["--aff-hostile", "#f87171"]};
export const colors = {};
function readAffiliations() {
  for (const [key, [name, fallback]] of Object.entries(affiliationTokens)) colors[key] = resolveColor(name, fallback);
}
readAffiliations();

const paletteTokens = {
  bg: "--bg", panel: "--panel", line: "--line", lineStrong: "--line-strong", lineFaint: "--line-faint",
  text: "--text", muted: "--muted", faint: "--text-faint", accent: "--accent", live: "--live",
  liveStrong: "--live-strong", amber: "--amber", red: "--red", blue: "--blue", green: "--green",
  scopeBg: "--scope-bg", plot: "--plot", raised: "--bg-3", well: "--scope",
  water: "--chart-water", shallow: "--chart-shallow", deep: "--chart-deep", grid: "--chart-grid",
  land: "--chart-land", landEdge: "--chart-land-edge", label: "--chart-label", halo: "--chart-halo",
  sweep: "--chart-sweep", rain: "--chart-rain",
};
let paletteCache = null;
export function palette() {
  if (!paletteCache) {
    paletteCache = {};
    for (const [key, name] of Object.entries(paletteTokens)) paletteCache[key] = resolveColor(name, "#808080");
  }
  return paletteCache;
}
// A palette colour as [r, g, b] (for blends and tints).
export function paletteRgb(key) {
  const match = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/.exec(palette()[key] || "");
  return match ? [1, 2, 3].map((index) => Math.round(Number(match[index]))) : [128, 128, 128];
}
// The same colour with an alpha, for translucent fills.
export function paletteAlpha(key, alpha) {
  return `rgba(${paletteRgb(key).join(", ")}, ${alpha})`;
}
export function invalidatePalette() {
  paletteCache = null;
  readAffiliations();
}
// The theme in force (night unless <html data-theme> names another).
export function themeName() {
  const name = document.documentElement.dataset.theme;
  return name === "day" || name === "contrast" ? name : "night";
}
export const isLightTheme = () => themeName() === "day";
