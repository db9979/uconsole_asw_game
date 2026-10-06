// Contact names on the charts (the browser twin of the uConsole's Alt+N,
// src/ui/map_view.py contact_labels_shown): the names and speeds of the
// contacts on every chart of this browser shown or hidden. Symbols, vectors
// and the hover details stay. A display choice of this browser tab, kept in
// memory like the OPZ display settings (the theme is the only stored one).
import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { keyLabel } from "../input/station-keys.js";

export const NAMES_SHORTCUT = "Alt+N";
let shown = true;
const listeners = [];

export const contactNamesShown = () => shown;
export function onContactNames(listener) { listeners.push(listener); }

export function toggleContactNames() {
  shown = !shown;
  syncContactNamesButton();
  for (const listener of listeners) listener(shown);
}

// The chart toolbar's button: its text and pressed state follow the choice.
export function syncContactNamesButton() {
  const button = $("role-map-names");
  if (!button) return;
  const text = t(shown ? "contact_names_on" : "contact_names_off");
  if (button.textContent !== text) button.textContent = text;
  if (button.getAttribute("aria-pressed") !== String(shown)) button.setAttribute("aria-pressed", String(shown));
  const cap = keyLabel(NAMES_SHORTCUT);
  if (button.dataset.keycap !== cap) button.dataset.keycap = cap;
  const title = t("contact_names_help");
  if (button.title !== title) button.title = title;
}

// Alt+N anywhere outside a text field, as at every uConsole station.
export function isContactNamesKey(event) {
  const target = event.target;
  const typing = target instanceof Element &&
    (target.closest("input, select, textarea, dialog[open]") || target.isContentEditable);
  return event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey &&
    event.code === "KeyN" && !event.repeat && !event.isComposing && !typing;
}
