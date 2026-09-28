// Tilt, zoom and stabilizer of an eyepiece in this browser only
// (presentation, like the uConsole's src/core/optics.py; never sent).
import { number, t } from "../core/format.js";

export function createOptics(powers, elevation) {
  return {powers, min: elevation[0], max: elevation[1], elevation: 0, power: 0, stabilized: false};
}

export const opticsFov = (optics, baseFov) => baseFov / optics.powers[optics.power];

export function opticsText(optics, baseFov) {
  return t("optics_status", {elevation: `${optics.elevation >= 0 ? "+" : ""}${number(optics.elevation, 0)}`,
    fov: number(opticsFov(optics, baseFov), 0)});
}

// Buttons inside ``group``: data-optics-tilt (degrees), data-optics-zoom
// (-1/1) and data-optics-stabilizer (aria-pressed).
export function wireOptics(group, optics, changed) {
  if (!group || group.dataset.wired) return;
  group.dataset.wired = "true";
  const stabilizer = group.querySelector("[data-optics-stabilizer]");
  for (const button of group.querySelectorAll("[data-optics-tilt]"))
    button.addEventListener("click", () => {
      optics.elevation = Math.max(optics.min, Math.min(optics.max, optics.elevation + Number(button.dataset.opticsTilt)));
      changed();
    });
  for (const button of group.querySelectorAll("[data-optics-zoom]"))
    button.addEventListener("click", () => {
      optics.power = Math.max(0, Math.min(optics.powers.length - 1, optics.power + Number(button.dataset.opticsZoom)));
      changed();
    });
  stabilizer?.setAttribute("aria-pressed", "false");
  stabilizer?.addEventListener("click", () => {
    optics.stabilized = !optics.stabilized;
    stabilizer.setAttribute("aria-pressed", String(optics.stabilized));
    changed();
  });
}
