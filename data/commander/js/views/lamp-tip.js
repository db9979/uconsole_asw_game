import { markKeys } from "../core/key-caps.js";

// Hover note of a status lamp (the role state's ``lamp_tips``): why the lamp
// shows what it shows and what to do, keys as key caps. One shared floating
// box; built from text nodes only.

let box = null, owner = null;

function tipBox() {
  if (!box) {
    box = document.createElement("div");
    box.id = "lamp-tip";
    box.className = "lamp-tip";
    box.setAttribute("role", "tooltip");
    box.hidden = true;
    document.body.append(box);
  }
  return box;
}

function fill(tip) {
  const target = tipBox();
  const title = document.createElement("strong");
  title.textContent = tip.title;
  const lines = tip.lines.map((text) => {
    const line = document.createElement("p");
    line.textContent = text;
    markKeys(line, tip.keys);
    return line;
  });
  target.replaceChildren(title, ...lines);
}

function place(element) {
  const target = tipBox(), rect = element.getBoundingClientRect();
  const width = Math.min(380, window.innerWidth - 16);
  target.style.maxWidth = `${width}px`;
  const height = target.offsetHeight, right = window.innerWidth - 8;
  let left = Math.min(rect.left, right - target.offsetWidth);
  let top = rect.bottom + 6;
  if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
  target.style.left = `${Math.max(8, left) + window.scrollX}px`;
  target.style.top = `${top + window.scrollY}px`;
}

function show(element) {
  const tip = element.lampTip;
  if (!tip) return hide(element);
  owner = element;
  fill(tip);
  tipBox().hidden = false;
  element.setAttribute("aria-describedby", "lamp-tip");
  place(element);
}

function hide(element) {
  if (owner !== element) return;
  owner = null;
  if (box) box.hidden = true;
  element.removeAttribute("aria-describedby");
}

// ``element.lampTip`` holds the current note (or nothing); set it on every
// render, the listeners are attached once.
export function attachLampTip(element) {
  if (element.dataset.lampTip) return;
  element.dataset.lampTip = "1";
  element.addEventListener("mouseenter", () => show(element));
  element.addEventListener("mouseleave", () => hide(element));
  element.addEventListener("focus", () => show(element));
  element.addEventListener("blur", () => hide(element));
}

export function setLampTip(element, tip) {
  attachLampTip(element);
  element.lampTip = tip || null;
  element.setAttribute("aria-description", tip ? [tip.title, ...tip.lines].join(". ") : "");
  if (!tip) element.removeAttribute("aria-description");
  if (owner === element) tip ? (fill(tip), place(element)) : hide(element);
}
