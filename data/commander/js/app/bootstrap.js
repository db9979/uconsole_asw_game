import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { loadLanguage } from "../core/i18n.js";
import { poll } from "../net/poll.js";
import { resumeSession, setConnection } from "../net/session.js";
import { loadContactAnalysis } from "../views/analyzer.js";
import { renderHost } from "../views/host.js";
import { renderLobby } from "../views/lobby.js";

async function bootstrap() {
  if (location.protocol === "https:") {
    fetch("/api/v2/web/status", {cache: "no-store"})
      .then((response) => {
        S.webHostAvailable = response.ok;
        renderHost();
        if (S.session) renderLobby();
      })
      .catch(() => {});
  }
  const resumed = await resumeSession();
  let delay = 1000;
  while (!await loadLanguage(S.language)) {
    await new Promise((resolve) => setTimeout(resolve, delay));
    delay = Math.min(8000, delay * 2);
  }
  loadContactAnalysis();
  if (resumed) {
    $("pairing").hidden = true;
    $("disconnect").hidden = false;
    renderLobby();
    setConnection(S.session.station === null ? "lobby" : "syncing");
    poll();
  }
}

export function init() {
  bootstrap();
}
