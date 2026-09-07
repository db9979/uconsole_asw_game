"""Capture seeded Commander demos using the production game/bridge/loopback server.

Requires an installed Chromium, not Node, Playwright or a browser download.
Enemy information comes exclusively from normal sensor updates. The two authored
own-ship damage cases are demonstration data, not historical mission evidence.
The simulation continues on the main thread during capture, so these are seeded
examples, not byte-identical image fixtures or two-computer/hardware acceptance.

Only the server's in-memory app.js response is augmented with pairing/selection
automation. No packaged file is rewritten and no credential is logged, placed in
a URL or stored by this tool. A temporary HOME and incognito browser profile
isolate preferences/saves/caches. Pairing is revoked and the server is stopped
before any screenshot is copied to the requested output directory.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SIZES = (("commander-overview.png", 1920, 1080), ("commander-wide.png", 2560, 1440))


AUTOMATION = r"""
(() => {
  let code = __PAIRING_CODE__;
  let submitted = false;
  let errors = 0;
  const $ = (id) => document.getElementById(id);
  window.addEventListener("error", () => { errors++; });
  window.addEventListener("unhandledrejection", () => { errors++; });
  const timer = setInterval(() => {
    const report = document.documentElement.dataset;
    report.captureReady = "false";
    if ($("shell").hidden) return;
    if (document.documentElement.lang !== "en") {
      if (!$("language").disabled) {
        $("language").value = "en";
        $("language").dispatchEvent(new Event("change"));
      }
      return;
    }
    if (!submitted && !$("pairing").hidden) {
      submitted = true;
      $("code").value = code;
      code = "";
      $("pair-form").requestSubmit();
    }
    if ($("operations").hidden || $("connection").dataset.state !== "connected") return;
    const first = $("track-list").querySelector("button");
    if (!first) return;
    if (first.getAttribute("aria-pressed") !== "true") first.click();
    const canvas = $("chart");
    report.captureConnected = $("connection").dataset.state;
    report.captureCommands = String(!$("apply-affiliation").disabled);
    report.captureSelected = String(first.getAttribute("aria-pressed") === "true");
    report.captureTracks = String($("track-list").querySelectorAll("button").length);
    report.captureWidth = String(innerWidth);
    report.captureHeight = String(innerHeight);
    report.captureOverflow = String(document.documentElement.scrollWidth > innerWidth);
    report.captureErrors = String(errors);
    const painted = canvas.width === Math.round(canvas.clientWidth * Math.min(devicePixelRatio, 3)) && canvas.width > 300;
    report.captureReady = String(painted && !$("apply-affiliation").disabled && !errors);
  }, 100);
  window.addEventListener("pagehide", () => { code = ""; clearInterval(timer); });
})();
"""


class CaptureReport(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.values = {key.removeprefix("data-capture-"): value
                           for key, value in attrs if key.startswith("data-capture-")}


def capture_all(output: Path, seed: int, chromium: str, budget_ms: int = 3000) -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    previous_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory(prefix="u-jagd-commander-capture-") as directory:
        temporary = Path(directory)
        os.environ["HOME"] = str(temporary)
        sys.path.insert(0, str(ROOT))
        try:
            import pygame
            from src.commander.bridge import CommanderBridge
            from src.commander.server import CommanderServer
            from src.core.game import Game
            from src.core.i18n import load_catalog
            from src.core.preferences import Preferences

            staged = []
            for name, width, height in SIZES:
                game = Game(seed=seed, start_menu=False, show_splash=False,
                            preferences=Preferences(language="en", fullscreen=False, audio=False))
                server = CommanderServer({lang: load_catalog(lang) for lang in ("en", "de")})
                bridge = CommanderBridge()
                process = None
                try:
                    for _ in range(360):
                        game.update(1 / 60)
                    server.start("127.0.0.1", 0)
                    bridge.pump(game, server)
                    # Own-ship demo only: never add contacts or manufacture fixes.
                    for key, flood, fire in (("sonar", 12.0, 0.0), ("engine", 7.0, 9.0)):
                        compartment = game.damage.compartments[key]
                        compartment.state = "BESCHAEDIGT"
                        compartment.flood, compartment.fire = flood, fire
                    game.damage.teams = {1: "sonar", 2: "engine", 3: "engine"}
                    content_type, script = server._http.assets["/app.js"]
                    automation = AUTOMATION.replace("__PAIRING_CODE__", json.dumps(server.pairing_code))
                    server._http.assets["/app.js"] = (content_type, script + automation.encode("ascii"))
                    del automation
                    image = temporary / name
                    host, port = server.address
                    process = subprocess.Popen(
                        [chromium, "--headless", "--no-sandbox", "--disable-gpu",
                         "--incognito", "--disable-background-networking", "--disable-sync",
                         "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
                         "--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                         "--lang=en-US", "--force-device-scale-factor=1",
                         f"--user-data-dir={temporary / (name + '-profile')}",
                         f"--window-size={width},{height}", f"--virtual-time-budget={budget_ms}",
                         f"--screenshot={image}", "--dump-dom", f"http://{host}:{port}/"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    )
                    # Only this reader thread touches subprocess pipes, never Game.
                    with ThreadPoolExecutor(max_workers=1) as reader:
                        result = reader.submit(process.communicate, timeout=40)
                        granted = False
                        previous = time.monotonic()
                        while not result.done():
                            now = time.monotonic()
                            if server.connected and not granted:
                                bridge.allowed = True
                                granted = True
                            bridge.pump(game, server, now=now)
                            game.update(min(.1, now - previous))
                            previous = now
                            pygame.event.pump()
                            time.sleep(1 / 60)
                        stdout, _ = result.result()
                    report = CaptureReport(stdout.decode("utf-8", errors="replace")).values
                    expected = {"ready": "true", "connected": "connected", "commands": "true",
                                "selected": "true", "overflow": "false", "errors": "0",
                                "width": str(width)}
                    if (process.returncode != 0 or not image.is_file()
                            or any(report.get(key) != value for key, value in expected.items())
                            or not bridge.status["commands_allowed"] or not server.connected):
                        failed = [key for key, value in expected.items() if report.get(key) != value]
                        print(f"{name}: failed checks={','.join(failed)}, exit={process.returncode}, "
                              f"image={image.is_file()}, connected={server.connected}, "
                              f"commands_allowed={bridge.status['commands_allowed']}, "
                              f"viewport_height={int(report.get('height', 0))}, "
                              f"image_size={pygame.image.load(image).get_size() if image.is_file() else None}", file=sys.stderr)
                        raise RuntimeError(f"{name}: browser did not reach a healthy, selected, enabled capture state")
                    if pygame.image.load(image).get_size() != (width, height):
                        raise RuntimeError(f"{name}: unexpected screenshot dimensions")
                    staged.append((image, report["tracks"], bridge.status["phase"]))
                finally:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)
                    bridge.allowed = False
                    http, listener = server._http, server._thread
                    workers = []
                    if http is not None:
                        with http.work_lock:
                            workers = list(http.workers)
                    server.stop()
                    if http is not None:
                        http.assets.clear()
                    if (server.connected or server._thread is not None or server._http is not None
                            or (listener is not None and listener.is_alive())
                            or any(worker.is_alive() for worker in workers)):
                        raise RuntimeError("Commander capture service did not stop")
                    game.commander.stop()
                    game.audio.shutdown()
                    pygame.quit()
            output.mkdir(parents=True, exist_ok=True)
            for image, tracks, phase in staged:
                destination = output / image.name
                shutil.copyfile(image, destination)
                print(f"{destination}: phase={phase}, connected=true, commands_allowed=true, "
                      f"contacts={tracks}, selected=true, server_stopped=true")
        finally:
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--budget-ms", type=int, default=3000,
                        help="Chromium virtual-time budget; increase on a slow host (1000..15000)")
    args = parser.parse_args()
    chromium = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    if not chromium:
        parser.error("An installed Chromium is required; no browser will be downloaded")
    if not 1000 <= args.budget_ms <= 15000:
        parser.error("--budget-ms must be between 1000 and 15000")
    try:
        capture_all(args.output.resolve(), args.seed, chromium, args.budget_ms)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        # Do not print subprocess output, injected JavaScript or request contents.
        print(f"Commander capture failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
