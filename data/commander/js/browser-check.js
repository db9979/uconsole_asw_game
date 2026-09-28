// Browser check of the pairing page. A classic script, independent of the
// ES module client: it still runs when a browser cannot load or evaluate the
// modules, so the page never stays silently on its loading screen.
(() => {
  const agent = navigator.userAgent || "";
  // Chrome, Chromium, Edge, Opera and other Blink browsers name "Chrome/";
  // Firefox and Safari (also Chrome on iOS, which is WebKit) do not.
  const chromium = /(?:Chrome|Chromium)\/\d/.test(agent) && !/\b(?:CriOS|FxiOS|EdgiOS)\//.test(agent);
  const root = document.documentElement;
  root.dataset.browser = chromium ? "chromium" : "other";
  const hint = document.getElementById("browser-hint");
  if (hint) hint.hidden = chromium;
  // The module client hides #bootstrap once its language catalog is loaded.
  setTimeout(async () => {
    const bootstrap = document.getElementById("bootstrap");
    const note = document.getElementById("bootstrap-hint");
    if (!bootstrap || bootstrap.hidden || !note) return;
    root.dataset.startup = "stalled";
    const language = /^de\b/i.test(navigator.language || "") ? "de" : "en";
    try {
      const response = await fetch(`/api/v2/ui?lang=${language}`, {cache: "no-store", credentials: "omit"});
      const catalog = response.ok ? await response.json() : null;
      const text = catalog && catalog["commander.web.browser_stalled"];
      if (typeof text !== "string" || bootstrap.hidden) return;
      note.textContent = text;
      note.hidden = false;
    } catch (_) {
      // The host is unreachable: the loading screen stays as it is.
    }
  }, 8000);
})();
