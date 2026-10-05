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
// A drawing's own accent colour in the high-contrast theme: dark tones go
// nearly black, light ones nearly white, the hue saturated so the few
// remaining colours stay apart (src/ui/theme._contrast).
export function contrastRgb(rgb) {
  const mean = (rgb[0] + rgb[1] + rgb[2]) / 3;
  const spread = rgb.map((part) => Math.max(0, Math.min(255, Math.round(mean + (part - mean) * 1.6))));
  const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  const scale = luminance < 0.3 ? 0.5 : 235 / Math.max(1, Math.max(...spread));
  return spread.map((part) => Math.max(0, Math.min(255, Math.round(part * scale))));
}
// The same for a "#rrggbb" string.
export function contrastHex(hex) {
  const value = hex.replace("#", "");
  const rgb = [0, 2, 4].map((index) => parseInt(value.slice(index, index + 2), 16));
  return `#${contrastRgb(rgb).map((part) => part.toString(16).padStart(2, "0")).join("")}`;
}
