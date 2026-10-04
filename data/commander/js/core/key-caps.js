const KEY_EDGE_BEFORE = /[\s(]/, KEY_EDGE_AFTER = /[\s,;.:)]/;

// Key names inside a help text become key caps (<kbd>), like the uConsole's
// blue keys; built from text nodes only, never from markup.
export function markKeys(element, tokens) {
  const text = element.textContent;
  const parts = [];
  let cursor = 0;
  while (cursor < text.length) {
    let best = null;
    for (const token of tokens) {
      if (!token) continue;
      let at = text.indexOf(token, cursor);
      while (at >= 0) {
        const before = at === 0 || KEY_EDGE_BEFORE.test(text[at - 1]);
        const end = at + token.length;
        const after = end === text.length || KEY_EDGE_AFTER.test(text[end]);
        if (before && after) break;
        at = text.indexOf(token, at + 1);
      }
      if (at >= 0 && (best === null || at < best.at)) best = {at, token};
    }
    if (best === null) break;
    if (best.at > cursor) parts.push(document.createTextNode(text.slice(cursor, best.at)));
    const cap = document.createElement("kbd");
    cap.className = "key-cap";
    cap.textContent = best.token;
    parts.push(cap);
    cursor = best.at + best.token.length;
  }
  if (!parts.length) return;
  if (cursor < text.length) parts.push(document.createTextNode(text.slice(cursor)));
  element.replaceChildren(...parts);
}
