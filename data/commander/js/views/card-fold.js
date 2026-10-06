import { $ } from "../core/base.js";

// Read tables (the station docks' card-readout cards) fold under their
// heading so the controls above them stay in view. Which cards are folded is
// kept for this page only (the client stores nothing but its theme).
const folded = new Set();

function apply(button) {
  const shut = folded.has(button.dataset.fold);
  button.setAttribute("aria-expanded", String(!shut));
  const card = button.closest(".card-readout");
  if (card) card.dataset.folded = String(shut);
}

export function init() {
  for (const button of document.querySelectorAll(".card-fold")) apply(button);
  $("station-view").addEventListener("click", (event) => {
    const button = event.target.closest?.(".card-fold");
    if (!button) return;
    const key = button.dataset.fold;
    if (folded.has(key)) folded.delete(key); else folded.add(key);
    for (const other of document.querySelectorAll(`.card-fold[data-fold="${CSS.escape(key)}"]`)) apply(other);
  });
}
