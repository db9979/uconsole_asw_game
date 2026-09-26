// Affiliation colours come from the stylesheet tokens (one palette for
// lists, badges and map symbols); literals are only the fallback.
const cssToken = (name, fallback) => {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; } catch { return fallback; }
};
export const colors = { UNKNOWN: cssToken("--aff-unknown", "#f3c577"), FRIEND: cssToken("--aff-friend", "#81c5ff"),
  NEUTRAL: cssToken("--aff-neutral", "#8fdfab"), HOSTILE: cssToken("--aff-hostile", "#ff9090") };
// Canvas drawing cannot use CSS custom properties directly, so it used to
// duplicate the palette as hand-copied hex literals - a real drift risk if
// style.css's :root palette is ever retuned. Read it once instead; these
// are static custom properties (no @media override anywhere in style.css),
// so there is nothing to invalidate the cache for.
let paletteCache = null;
export function palette() {
  if (!paletteCache) {
    const style = getComputedStyle(document.documentElement);
    const read = (name) => style.getPropertyValue(name).trim();
    paletteCache = {
      bg: read("--bg"), panel: read("--panel"), line: read("--line"),
      text: read("--text"), muted: read("--muted"), accent: read("--accent"),
      amber: read("--amber"), red: read("--red"), blue: read("--blue"),
      scopeBg: read("--scope-bg"), plot: read("--plot"),
    };
  }
  return paletteCache;
}
