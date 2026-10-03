// Colour themes of the browser stations, the same three as the uConsole
// (src/ui/theme.py): night (Tactical Night, default), day (Tactical Day,
// light) and contrast (high contrast / colour-blind). The theme is a display
// preference of this browser only: its name (never a credential) is kept in
// the browser's local storage under one key, and a blocked or private storage simply falls
// back to night. The red light forces night while it is lit (a red multiply
// over a light page would glare); high contrast stays, as on the uConsole.
import { invalidatePalette } from "./palette.js";

export const THEMES = ["night", "day", "contrast"];
const THEME_KEY = "u-jagd-theme";
let chosen = "night", redLight = false;
const listeners = [];

function storedTheme() {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    return THEMES.includes(value) ? value : "night";
  } catch { return "night"; }
}
function storeTheme(name) {
  try { window.localStorage.setItem(THEME_KEY, name); } catch { /* storage blocked: this page only */ }
}
export const chosenTheme = () => chosen;
export const effectiveTheme = () => chosen === "contrast" ? "contrast" : redLight ? "night" : chosen;
function applyTheme() {
  const name = effectiveTheme(), root = document.documentElement;
  // Under the red light the night tokens turn grey (tokens.css), so a green
  // accent keeps its brightness under the red multiply instead of going black.
  const red = redLight && name === "night";
  if (root.dataset.theme === name && root.hasAttribute("data-red-light") === red) return;
  root.toggleAttribute("data-red-light", red);
  root.dataset.theme = name;
  invalidatePalette();
  for (const listener of listeners) {
    try { listener(name); } catch { /* one view must not stop the others */ }
  }
}
// Called with the new theme name after every switch (views re-render).
export function onThemeChange(listener) { listeners.push(listener); }
// The player's choice from the top bar or the settings menu.
export function chooseTheme(name) {
  chosen = THEMES.includes(name) ? name : "night";
  storeTheme(chosen);
  applyTheme();
}
// The top bar's switch: night <-> day (high contrast goes back to night).
export const toggleTheme = () => chooseTheme(chosen === "night" ? "day" : "night");
export function setRedLightTheme(lit) {
  if (redLight === Boolean(lit)) return;
  redLight = Boolean(lit);
  applyTheme();
}
chosen = storedTheme();
applyTheme();
