"""Capture deterministic protocol-v2 Remote Crew workstation screenshots.

Requires an installed Chromium, not Node, Playwright or a browser download.
The production Game, CommanderBridge, CommanderServer, packaged browser assets,
v2 session endpoint, HttpOnly cookie, and host station APIs are used throughout.
The seeded simulation is advanced by a fixed amount and then frozen, so browser
startup and polling timing cannot change the projected tactical state.

Only an unguessable, capture-only in-memory page and script are augmented with
capture checks. The pairing code is never added to a production asset, DOM, URL,
browser profile output, screenshot name, or tool log, and is rotated immediately
after the expected client pairs. Temporary HOME and Chromium profiles isolate
preferences, saves, cookies, and caches. All
captures are validated and the server is stopped before any image is copied to
the requested output directory.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
ROLES = ("bridge", "sonar", "weapons", "damage", "opz", "radio",
         "engine", "helicopter", "eloka")
DESKTOP = (1920, 1080)
MOBILE = (500, 844)


@dataclass(frozen=True)
class Capture:
    name: str
    language: str
    width: int
    height: int
    role: str | None
    scene: str = "role"
    extra_roles: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


def capture_specs() -> tuple[Capture, ...]:
    captures = []
    for language in ("en", "de"):
        for role in ROLES:
            aliases = ("commander-overview.png",) if (language, role) == ("en", "opz") else ()
            captures.append(Capture(
                f"commander-v2-{language}-{role}-desktop.png", language,
                *DESKTOP, role, aliases=aliases))
    captures.extend((
        Capture("commander-v2-en-lobby-mobile.png", "en", *MOBILE, None,
                scene="lobby"),
        Capture("commander-v2-en-sonar-mobile.png", "en", *MOBILE, "sonar",
                scene="sonar"),
        Capture("commander-v2-de-radio-mobile.png", "de", *MOBILE, "radio",
                scene="radio"),
        Capture("commander-v2-de-multi-station-mobile.png", "de", *MOBILE,
                "bridge", scene="multi", extra_roles=("sonar", "radio")),
        Capture("commander-wide.png", "en", 2560, 1440, "sonar"),
    ))
    return tuple(captures)


AUTOMATION = r"""
(() => {
  "use strict";
  let credential = __PAIRING_CODE__;
  const captureName = __CAPTURE_NAME__;
  const expectedLanguage = __LANGUAGE__;
  const expectedRole = __ROLE__;
  const scene = __SCENE__;
  let pairing = false;
  let errors = 0;
  let positioned = false;
  const $ = (id) => document.getElementById(id);
  console.error = () => { errors++; };
  addEventListener("error", () => { errors++; });
  addEventListener("unhandledrejection", () => { errors++; });

  async function pairWithoutDom() {
    pairing = true;
    const code = credential;
    credential = "";
    try {
      const response = await fetch("/api/v2/pair", {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({code, name: captureName}),
      });
      if (!response.ok) throw new Error("capture_pairing_failed");
      await response.text();
      location.reload();
    } catch (_) {
      errors++;
    }
  }

  function painted(canvas) {
    if (!canvas || canvas.closest("[hidden]") || canvas.width < 300 || canvas.height < 100) return false;
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    for (let index = 0; index < data.length; index += 52) {
      if (data[index + 3] && (data[index] !== 7 || data[index + 1] !== 21 || data[index + 2] !== 28)) return true;
    }
    return false;
  }

  function instrumentFor(role) {
    if (["bridge", "weapons", "opz", "radio", "helicopter"].includes(role)) return $("role-map");
    return $({sonar: "sonar-broadband", damage: "damage-schematic",
      engine: "engine-instruments", eloka: "eloka-scope"}[role]);
  }

  function positionMobileScene() {
    if (positioned) return;
    let target = null;
    if (scene === "sonar") target = $("sonar-audition-mode");
    if (scene === "radio") target = $("radio-messages").lastElementChild || $("radio-messages");
    if (scene === "multi") target = $("workstation-station");
    if (target) target.scrollIntoView({block: scene === "multi" ? "start" : "center"});
    else scrollTo(0, 0);
    positioned = true;
  }

  const timer = setInterval(() => {
    const report = document.documentElement.dataset;
    report.captureReady = "false";
    if ($("shell").hidden) return;
    if (document.documentElement.lang !== expectedLanguage) {
      if (!$('language').disabled) {
        $("language").value = expectedLanguage;
        $("language").dispatchEvent(new Event("change"));
      }
      return;
    }
    if (!pairing && !$('pairing').hidden) {
      void pairWithoutDom();
      return;
    }

    const connection = $("connection").dataset.state;
    const overflow = document.documentElement.scrollWidth > innerWidth;
    report.captureLanguage = document.documentElement.lang;
    report.captureConnection = connection;
    report.captureWidth = String(innerWidth);
    report.captureHeight = String(innerHeight);
    report.captureOverflow = String(overflow);
    report.captureErrors = String(errors);
    report.captureCredentialDom = String($("code").value !== "");
    report.captureCookieHidden = String(!document.cookie.includes("ujagd_remote_v2"));

    if (scene === "lobby") {
      const cards = [...$("station-cards").children];
      report.captureRole = "lobby";
      report.capturePainted = String(cards.length === 9 && cards.every((card) => card.querySelector("button")));
      report.captureSelector = "true";
      report.captureMessage = "true";
      report.captureReady = String(connection === "lobby" && !$("lobby").hidden &&
        cards.length === 9 && !overflow && !errors && !$("code").value);
      positionMobileScene();
      return;
    }

    const section = $(`station-${expectedRole}`);
    const selectedRole = $("workstation-station").value;
    const selectorCount = $("workstation-station").options.length;
    const canvas = instrumentFor(expectedRole);
    const isPainted = painted(canvas);
    const sonarControls = scene !== "sonar" || ["sonar-audition-mode", "sonar-listen-band", "sonar-listen-notch"]
      .every((id) => $(id).getClientRects().length) && $("sonar-audition-mode").value === "FILTERED";
    const radioMessage = scene !== "radio" || $("radio-messages").children.length >= 3;
    const selector = scene !== "multi" || selectorCount >= 3;
    report.captureRole = selectedRole;
    report.capturePainted = String(isPainted);
    report.captureSelector = String(selector);
    report.captureMessage = String(radioMessage);
    if (connection !== "connected" || $("operations").hidden || section.hidden ||
        selectedRole !== expectedRole || !isPainted || !sonarControls || !radioMessage || !selector) return;
    positionMobileScene();
    report.captureReady = String(!overflow && !errors && !$("code").value);
  }, 50);
  addEventListener("pagehide", () => { credential = ""; clearInterval(timer); });
})();
"""


class CaptureReport(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.values = {
                key.removeprefix("data-capture-"): value
                for key, value in attrs if key.startswith("data-capture-")
            }


def _grant_capture(server, client_id: str, spec: Capture) -> None:
    if spec.role is None:
        return
    for station in (spec.role, *spec.extra_roles):
        if not server.grant_station(client_id, station):
            raise RuntimeError("host station grant failed")
        if not server.set_client_grant(client_id, station, "command", True):
            raise RuntimeError("host command grant failed")
    status = next(row for row in server.client_statuses()
                  if row["client_id"] == client_id)
    generation = status["stations"][spec.role]["station_generation"]
    if not server.activate_station(client_id, spec.role, generation):
        raise RuntimeError("host station activation failed")


def _capture_one(spec: Capture, temporary: Path, chromium: str, server,
                  game, bridge, pygame, production_asset, production_index,
                  capture_clock,
                  budget_ms: int):
    content_type, production_script = production_asset
    index_type, production_html = production_index
    nonce = secrets.token_urlsafe(24)
    capture_name = f"Screenshot {nonce[:12]}"
    script_path = f"/.capture-{nonce}.js"
    page_path = f"/.capture-{nonce}.html"
    automation = (AUTOMATION
                  .replace("__PAIRING_CODE__", json.dumps(server.pairing_code))
                  .replace("__CAPTURE_NAME__", json.dumps(capture_name))
                  .replace("__LANGUAGE__", json.dumps(spec.language))
                  .replace("__ROLE__", json.dumps(spec.role))
                  .replace("__SCENE__", json.dumps(spec.scene)))
    server._http.assets[script_path] = (
        content_type, production_script + automation.encode("ascii"))
    server._http.assets[page_path] = (
        index_type, production_html.replace(b"./app.js", script_path.encode("ascii")))
    del automation

    image = temporary / spec.name
    profile = temporary / f"profile-{spec.name}"
    host, port = server.address
    process = subprocess.Popen(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--incognito",
         "--disable-background-networking", "--disable-sync", "--no-first-run",
         "--no-default-browser-check", "--disable-dev-shm-usage", "--no-proxy-server",
         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
         f"--lang={'de-DE' if spec.language == 'de' else 'en-US'}",
         "--force-device-scale-factor=1", f"--user-data-dir={profile}",
         f"--window-size={spec.width},{spec.height}",
         f"--virtual-time-budget={budget_ms}", f"--screenshot={image}",
         "--dump-dom", f"http://{host}:{port}{page_path}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    client_id = None
    code_rotated = False
    try:
        with ThreadPoolExecutor(max_workers=1) as reader:
            result = reader.submit(process.communicate, timeout=40)
            while not result.done():
                # Chromium advances performance.now() using virtual time. Advance
                # publication time too so a frozen simulation does not look stale.
                capture_clock[0] += 0.5
                bridge.pump(game, server, now=capture_clock[0])
                roster = server.client_statuses()
                expected = next((row for row in roster if row["name"] == capture_name), None)
                if expected is not None and client_id is None:
                    client_id = expected["client_id"]
                    _grant_capture(server, client_id, spec)
                if client_id is not None and not code_rotated:
                    with server._lock:
                        server._rotate_code_locked()
                    code_rotated = True
                pygame.event.pump()
                time.sleep(.005)
            stdout, _ = result.result()
        report = CaptureReport(stdout.decode("utf-8", errors="replace")).values
        expected_role = spec.role or "lobby"
        expected = {
            "ready": "true", "language": spec.language,
            "connection": "lobby" if spec.role is None else "connected",
            "role": expected_role, "painted": "true", "selector": "true",
            "message": "true", "overflow": "false", "errors": "0",
            "credential-dom": "false", "cookie-hidden": "true",
            "width": str(spec.width),
        }
        failed = [key for key, value in expected.items() if report.get(key) != value]
        if (process.returncode != 0 or not image.is_file() or failed or client_id is None):
            print(f"{spec.name}: failed checks={','.join(failed)}, exit={process.returncode}, "
                  f"image={image.is_file()}, paired={client_id is not None}, "
                  f"connection={report.get('connection', 'missing')}, "
                  f"role={report.get('role', 'missing')}, "
                  f"painted={report.get('painted', 'missing')}, "
                  f"selector={report.get('selector', 'missing')}, "
                  f"message={report.get('message', 'missing')}, "
                  f"overflow={report.get('overflow', 'missing')}, "
                  f"errors={report.get('errors', 'missing')}, "
                  f"viewport_width={int(report.get('width', 0))}, "
                  f"viewport_height={int(report.get('height', 0))}", file=sys.stderr)
            raise RuntimeError(f"{spec.name}: browser did not reach a healthy v2 capture state")
        if pygame.image.load(image).get_size() != (spec.width, spec.height):
            raise RuntimeError(f"{spec.name}: unexpected screenshot dimensions")
        return image, report
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        if client_id is not None:
            server.revoke_client(client_id)
        server._http.assets.pop(script_path, None)
        server._http.assets.pop(page_path, None)


def capture_all(output: Path, seed: int, chromium: str, budget_ms: int = 8000) -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    previous_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory(prefix="u-jagd-commander-v2-capture-") as directory:
        temporary = Path(directory)
        os.environ["HOME"] = str(temporary)
        sys.path.insert(0, str(ROOT))
        staged = []
        try:
            import pygame
            from src.commander.bridge import CommanderBridge
            from src.commander.server import CommanderServer
            from src.core.game import Game
            from src.core.i18n import load_catalog
            from src.core.preferences import Preferences

            translations = {lang: load_catalog(lang) for lang in ("en", "de")}
            for language in ("en", "de"):
                game = Game(seed=seed, start_menu=False, show_splash=False,
                            preferences=Preferences(language=language, fullscreen=False,
                                                    audio=False))
                server = CommanderServer(translations)
                bridge = CommanderBridge()
                try:
                    game.set_sonar_audition_mode("FILTERED")
                    game.set_sonar_band_preset("SHAFT")
                    game.set_sonar_notch(True)
                    for _ in range(360):
                        game.update(1 / 60)
                    # Keep browser rendering independent of performance.now();
                    # the OPZ sweep is otherwise the only continuously animated
                    # workstation instrument after the simulation is frozen.
                    game.surface_radar_on = False
                    game.air_radar_on = False
                    # Authored own-ship damage demonstrates the real damage UI;
                    # contacts and mission intelligence still come from Game.
                    for key, flood, fire in (("sonar", 12.0, 0.0),
                                             ("engine", 7.0, 9.0)):
                        compartment = game.damage.compartments[key]
                        compartment.state = "BESCHAEDIGT"
                        compartment.flood, compartment.fire = flood, fire
                    game.damage.teams = {1: "sonar", 2: "engine", 3: "engine"}
                    capture_clock = [time.monotonic()]
                    bridge.pump(game, server, now=capture_clock[0])
                    server.start("127.0.0.1", 0)
                    production_asset = server._http.assets["/app.js"]
                    production_index = server._http.assets["/"]
                    css_type, css = server._http.assets["/style.css"]
                    server._http.assets["/style.css"] = (css_type, css + (
                        b"\n*,*::before,*::after{animation:none!important;"
                        b"transition:none!important;caret-color:transparent!important}\n"))
                    for spec in (item for item in capture_specs()
                                 if item.language == language):
                        image, report = _capture_one(
                            spec, temporary, chromium, server, game, bridge, pygame,
                            production_asset, production_index, capture_clock, budget_ms)
                        staged.append((image, (spec.name, *spec.aliases), report))
                finally:
                    http, listener = server._http, server._thread
                    workers = []
                    if http is not None:
                        with http.work_lock:
                            workers = list(http.workers)
                    server.stop()
                    if http is not None:
                        http.assets.clear()
                    if (server.connected or server.client_statuses()
                            or server._thread is not None or server._http is not None
                            or (listener is not None and listener.is_alive())
                            or any(worker.is_alive() for worker in workers)):
                        raise RuntimeError("Commander capture service did not stop")
                    game.commander.stop()
                    game.audio.shutdown()
                    pygame.quit()
            output.mkdir(parents=True, exist_ok=True)
            for image, names, report in staged:
                for name in names:
                    destination = output / name
                    shutil.copyfile(image, destination)
                    print(f"{destination}: protocol=v2, language={report['language']}, "
                          f"role={report['role']}, connected={report['connection']}, "
                          "painted=true, overflow=false, js_errors=0, server_stopped=true")
        finally:
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "screenshots")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--budget-ms", type=int, default=8000,
                        help="Chromium virtual-time budget per capture (2000..15000; default: 8000)")
    args = parser.parse_args()
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        parser.error("An installed Chromium is required; no browser will be downloaded")
    if not 2000 <= args.budget_ms <= 15000:
        parser.error("--budget-ms must be between 2000 and 15000")
    try:
        capture_all(args.output.resolve(), args.seed, chromium, args.budget_ms)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        # Never print browser output, injected JavaScript, request bodies, or credentials.
        print(f"Commander capture failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
