"""Navigation is a leased proposal, never remote helm authority."""

from copy import deepcopy
from itertools import combinations
import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pygame
import pytest

from src.commander.server import CommanderServer, _command_valid
from src.core import config
from src.core.game import Game
from src.core.i18n import Translator, pseudolocale
from src.ui import layout
from test_commander_bridge import start, contact, command as track_command
from test_commander_server import pair, request
from test_commander_assets import ASSETS, PREFIX, Document, browser_state, catalogs


@pytest.fixture
def game():
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    yield game
    game.audio.shutdown()
    layout.configure_for(large_text=False)


def navigation(state, **fields):
    return dict(id="navigation", session=state["session"], epoch=state["epoch"],
                revision=state["revision"], action="propose_navigation", **fields)


@pytest.mark.parametrize("fields", [
    {}, {"course": True}, {"speed_kn": False}, {"course": None}, {"speed_kn": None},
    {"course": "90"}, {"course": float("nan")}, {"course": float("inf")},
    {"course": -float("inf")}, {"speed_kn": float("nan")}, {"speed_kn": float("inf")},
    {"course": -1}, {"course": 360}, {"speed_kn": -1},
    {"speed_kn": config.SHIP_SPEED_MAX_KN + .01}, {"speed_kn": 10**400},
    {"course": []}, {"speed_kn": {}}, {"course": 90, "track": "any"},
    {"course": 90, "value": None}, {"course": 90, "steer": True},
    {"course": 90, "speed_kn": True},
])
def test_schema_rejected_by_transport_and_bridge(game, fields):
    bridge, server = start(game)
    before = deepcopy(game.ship.__dict__)
    body = navigation(server.state, **fields)
    assert not _command_valid(body)
    server.send(body)
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "invalid_schema"
    assert bridge.navigation_proposal is None
    assert game.ship.__dict__ == before


@pytest.mark.parametrize("key,value", [
    ("id", ""), ("id", True), ("session", ""), ("session", 1),
    ("epoch", True), ("epoch", -1), ("epoch", 2**53),
    ("revision", False), ("revision", 1.2), ("revision", 2**53),
    ("action", "set_course"), ("action", "set_speed"), ("action", "accept_navigation"),
])
def test_strict_base_envelope_and_no_direct_helm_actions(game, key, value):
    bridge, server = start(game)
    body = navigation(server.state, course=90)
    body[key] = value
    assert not _command_valid(body)
    server.send(body)
    bridge.pump(game, server, now=100.1)
    assert server.state["results"][-1]["reasoncode"] == "invalid_schema"
    assert bridge.navigation_proposal is None


@pytest.mark.parametrize("fields", [
    {"course": 0}, {"course": 359.999}, {"speed_kn": 0},
    {"speed_kn": config.SHIP_SPEED_MAX_KN}, {"course": 123.5, "speed_kn": 17.25},
])
def test_remote_only_stages_local_confirmation_sets_orders_atomically(game, fields):
    bridge, server = start(game)
    before = deepcopy(game.ship.__dict__)
    body = navigation(server.state, **fields)
    assert _command_valid(body)
    server.send(body)
    bridge.pump(game, server, now=100.1)
    assert game.ship.__dict__ == before
    assert server.state["navigation_proposal"] == dict(course=fields.get("course"),
        speed_kn=fields.get("speed_kn"), status="pending")
    assert "navigation_proposal" not in json.dumps(game.save_state())
    detached = bridge.navigation_proposal
    detached["course"] = -1
    assert bridge.navigation_proposal["course"] == fields.get("course")
    revision = server.state["revision"]
    sequence = bridge.proposal_sequence
    server.send(body)
    bridge.pump(game, server, now=100.2)
    assert server.state["revision"] == revision and bridge.proposal_sequence == sequence
    game.commander_open = True
    assert bridge.accept_navigation(game)
    assert not bridge.accept_navigation(game)
    expected = dict(before, target_course=fields.get("course", before["target_course"]),
                    target_speed=fields.get("speed_kn", before["target_speed"]))
    if "speed_kn" in fields:
        expected["order_idx"] = min(range(len(config.TELEGRAPH_ORDERS)),
            key=lambda i: abs(config.TELEGRAPH_ORDERS[i][1] - fields["speed_kn"]))
    assert game.ship.__dict__ == expected
    bridge.pump(game, server, now=100.3)
    assert server.state["navigation_proposal"]["status"] == "accepted"


def test_atomic_local_revalidation_and_speed_only_with_bridge_destroyed(game, monkeypatch):
    bridge, server = start(game)
    server.send(navigation(server.state, course=123, speed_kn=19))
    bridge.pump(game, server, now=100.1)
    before = deepcopy(game.ship.__dict__)
    monkeypatch.setattr(game.damage, "station_down", lambda station: station == "bridge")
    assert not bridge.accept_navigation(game)
    assert bridge.navigation_error == "commander.local.navigation.bridge_down"
    assert game.ship.__dict__ == before
    bridge._navigation_proposal["course"] = None
    bridge._navigation_proposal["speed_kn"] = config.SHIP_SPEED_MAX_KN + 1
    assert not bridge.accept_navigation(game)
    assert game.ship.__dict__ == before
    bridge._navigation_proposal["speed_kn"] = 19
    assert bridge.accept_navigation(game)
    assert game.ship.target_course == before["target_course"]
    assert game.ship.target_speed == 19


@pytest.mark.parametrize("cap,quiet,expected", [(8, False, 8), (25, True, 12)])
def test_acceptance_preserves_engine_cap_and_quiet_mode_physics(game, cap, quiet, expected):
    bridge, server = start(game)
    game.ship.speed_cap, game.ship.quiet_mode = cap, quiet
    server.send(navigation(server.state, speed_kn=25))
    bridge.pump(game, server, now=100.1)
    assert bridge.accept_navigation(game)
    assert (game.ship.speed_cap, game.ship.quiet_mode) == (cap, quiet)
    for _ in range(1000):
        game.ship.update(.1)
    assert game.ship.target_speed == 25 and game.ship.speed == expected


@pytest.mark.parametrize("change", ["grant", "regrant", "lease", "disconnect", "world", "menu"])
def test_pending_expires_or_redacts_without_inheriting_authority(game, change):
    bridge, server = start(game)
    server.send(navigation(server.state, course=123, speed_kn=19))
    bridge.pump(game, server, now=100.1)
    if change in ("grant", "regrant"):
        bridge.allowed = False
        if change == "regrant":
            bridge.allowed = True
    elif change == "lease":
        server.lease += 1
        bridge.allowed = True
    elif change == "disconnect":
        server.connected = False
    elif change == "world":
        game.reset(32)
    else:
        game.in_menu = True
    before = deepcopy(game.ship.__dict__)
    assert not bridge.accept_navigation(game)
    bridge.pump(game, server, now=100.2)
    proposal = bridge.navigation_proposal
    assert proposal is None or proposal["status"] == "expired"
    assert game.ship.__dict__ == before
    if change in ("world", "menu"):
        assert "navigation_proposal" not in server.state


@pytest.mark.parametrize("owner", ["paused", "help_open", "game_over", "commander_open"])
def test_remote_owner_epoch_gate_and_local_acceptance_gate(game, owner):
    bridge, server = start(game)
    server.send(navigation(server.state, course=123))
    bridge.pump(game, server, now=100.1)
    body = navigation(server.state, speed_kn=19)
    body["id"] = "second"
    server.send(body)
    setattr(game, owner, True)
    bridge.pump(game, server, now=100.2)
    assert server.state["results"][-1]["reasoncode"] == "stale_epoch"
    assert bridge.accept_navigation(game) is (owner == "commander_open")


def test_target_proposal_separate_reject_and_revision_conflict(game):
    target = contact(game)
    bridge, server = start(game)
    old = navigation(server.state, course=123)
    server.send(track_command(server, "propose"))
    bridge.pump(game, server, now=100.1)
    server.send(old)
    bridge.pump(game, server, now=100.2)
    assert server.state["results"][-1]["reasoncode"] == "revision_conflict"
    body = navigation(server.state, course=123, speed_kn=19)
    body["id"] = "fresh"
    server.send(body)
    bridge.pump(game, server, now=100.3)
    before = deepcopy(game.ship.__dict__)
    server.send(dict(body, course=124))
    bridge.pump(game, server, now=100.4)
    assert server.state["results"][-1]["reasoncode"] == "duplicate_id"
    assert bridge.reject_navigation(game)
    assert bridge.navigation_proposal["status"] == "rejected"
    assert bridge.proposal["status"] == "pending"
    assert bridge.accept_proposal(game) and game.target is target
    assert game.ship.__dict__ == before


def test_fresh_navigation_proposal_cannot_replace_pending_and_duplicate_replays(game):
    bridge, server = start(game)
    original = navigation(server.state, course=123)
    server.send(original)
    bridge.pump(game, server, now=100.1)
    pending = bridge.navigation_proposal
    revision = server.state["revision"]

    server.send(original)
    bridge.pump(game, server, now=100.2)
    assert server.state["results"][-1] == dict(
        id="navigation", status="applied", reasoncode="ok")
    assert bridge.navigation_proposal == pending and server.state["revision"] == revision

    replacement = navigation(server.state, course=124)
    replacement["id"] = "replacement"
    server.send(replacement)
    bridge.pump(game, server, now=100.3)
    assert server.state["results"][-1] == dict(
        id="replacement", status="rejected", reasoncode="proposal_pending")
    assert bridge.navigation_proposal == pending


def test_same_batch_navigation_replacement_reports_pending_not_revision(game):
    bridge, server = start(game)
    first = navigation(server.state, course=123)
    second = navigation(server.state, speed_kn=19)
    first["id"], second["id"] = "first", "second"
    server.send(first)
    server.send(second)

    bridge.pump(game, server, now=100.1)

    assert [result["reasoncode"] for result in server.state["results"][-2:]] == [
        "ok", "proposal_pending"]
    assert bridge.navigation_proposal == dict(course=123, speed_kn=None,
                                               status="pending")


def test_real_http_only_queues_navigation_and_denies_direct_actions(game):
    server = CommanderServer()
    server.start("127.0.0.1", 0)
    try:
        token = pair(server)
        bridge = game.commander.bridge
        bridge.allowed = True
        bridge.pump(game, server)
        state = request(server, "/api/v1/state", token=token)[2]
        body = navigation(state, course=123, speed_kn=19)
        before = deepcopy(game.ship.__dict__)
        for action in ("set_course", "set_speed", "accept_navigation"):
            assert request(server, "/api/v1/commands", "POST", dict(body, action=action), token)[0] == 400
        for invalid in (dict(body, track="any"), dict(body, course=True), dict(body, speed_kn=float("inf"))):
            assert request(server, "/api/v1/commands", "POST", invalid, token)[0] == 400
        assert request(server, "/api/v1/commands", "POST", body, token)[0] == 202
        assert bridge.navigation_proposal is None and game.ship.__dict__ == before
        bridge.pump(game, server)
        assert bridge.navigation_proposal["status"] == "pending"
        assert game.ship.__dict__ == before
    finally:
        server.stop()


@pytest.mark.parametrize("language", ["en", "de", "pseudo"])
@pytest.mark.parametrize("large", [False, True])
def test_native_nine_rows_nonoverlap_and_local_confirmation(game, monkeypatch, language, large):
    console = game.commander
    bridge, server = start(game)
    console.bridge = bridge
    console.address = ("127.0.0.1", 8765)
    server.send(navigation(server.state, course=359.999, speed_kn=25))
    bridge.pump(game, server, now=100.1)
    game.tr = (Translator("en", pseudolocale()) if language == "pseudo" else Translator(language)).t
    layout.configure_for(large_text=large)
    console.error = "commander.local.navigation.bridge_down"
    with layout.capture_text() as text:
        console.draw(game)
    assert len(console.row_rects()) == 9
    for entry in text:
        assert entry["bounds"].contains(entry["rect"])
        assert pygame.Rect(0, 0, 1280, 720).contains(entry["bounds"])
        assert "commander." not in entry["text"]
    assert all(not a["rect"].colliderect(b["rect"]) for a, b in combinations(text, 2))
    game.commander_open = True
    console.selection = 6
    console.handle_key(game, pygame.K_DOWN)
    assert console.selection == 7
    console.handle_key(game, pygame.K_RETURN)
    assert game.ship.target_course == 359.999 and game.ship.target_speed == 25
    console.handle_key(game, pygame.K_DOWN)
    assert console.selection == 8
    console.handle_key(game, pygame.K_DOWN)
    assert console.selection == 0
    console.handle_key(game, pygame.K_UP)
    assert console.selection == 8
    reject = Mock(return_value=True)
    monkeypatch.setattr(bridge, "reject_navigation", reject)
    console.handle_key(game, pygame.K_RETURN)
    reject.assert_called_once_with(game)


NAVIGATION_BROWSER = r"""
const $ = (id) => document.getElementById(id);
const fixture = __STATE__;
const translations = __CATALOG__;
const commands = [], results = new Map(), errors = [];
let loseAck = false, publishResults = true, effects = 0, active = 0, maxActive = 0;
const assert = (value, message) => { if (!value) throw Error(message); };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message) {
  for (let i = 0; i < 600; i++) { if (check()) return; await sleep(20); }
  throw Error(message);
}
window.addEventListener("error", (e) => errors.push(e.message));
window.addEventListener("unhandledrejection", (e) => errors.push(String(e.reason)));
window.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
window.fetch = async (url, options) => {
  active++; maxActive = Math.max(active, maxActive);
  try {
    await sleep(5);
    if (url.includes("/ui?")) return Response.json(translations);
    if (url.endsWith("/pair")) return Response.json({token: "test-only-token"});
    assert(options.headers.Authorization === "Bearer test-only-token", "authenticated navigation");
    if (url.endsWith("/chart")) return Response.json({revision: fixture.chart_revision, size_nm: 500, landmasses: [], disclaimer: ""});
    if (url.endsWith("/state")) {
      fixture.seq++;
      fixture.results = publishResults ? [...results.values()].map((r) => r.result) : [];
      return Response.json(fixture);
    }
    assert(url.endsWith("/commands"), "fixed command route");
    const body = JSON.parse(options.body);
    commands.push(body);
    assert(body.action === "propose_navigation" && !Object.hasOwn(body, "track") && !Object.hasOwn(body, "value"), "navigation has no track/value");
    assert(["action", "epoch", "id", "revision", "session"].every((key) => key in body) &&
      (Object.hasOwn(body, "course") || Object.hasOwn(body, "speed_kn")), "navigation envelope");
    const prior = results.get(body.id);
    if (prior) assert(prior.body === options.body, "identical idempotent retry");
    else {
      effects++;
      results.set(body.id, {body: options.body, result: {id: body.id, status: "applied", reasoncode: "ok"}});
      fixture.navigation_proposal = {course: body.course ?? null, speed_kn: body.speed_kn ?? null, status: "pending"};
      fixture.revision++;
    }
    if (loseAck) throw TypeError("acknowledgement lost");
    return new Response("", {status: 202});
  } finally { active--; }
};
async function run() {
  await until(() => !$("shell").hidden, "bootstrap");
  $("code").value = "123ABC";
  $("pair-form").requestSubmit();
  await until(() => !$("propose-navigation").disabled, "track-independent form enabled");
  assert(!document.querySelector('#track-list [aria-pressed="true"]'), "no selected track");
  $("navigation-form").requestSubmit();
  assert(commands.length === 0, "empty proposal denied");
  for (const [id, value] of [["navigation-course", "360"], ["navigation-course", "-1"], ["navigation-speed", "26"]]) {
    $(id).value = value;
    assert(!$("navigation-form").checkValidity(), "native range validation");
    $("navigation-form").requestSubmit();
    $(id).value = "";
  }
  assert(commands.length === 0, "invalid proposals never sent");
  $("navigation-course").value = "123.5";
  $("navigation-speed").value = "17.25";
  await sleep(1100);
  assert($("navigation-course").value === "123.5" && $("navigation-speed").value === "17.25", "poll preserves typing");
  const ownship = JSON.stringify(fixture.ownship);
  loseAck = true; publishResults = false;
  $("navigation-form").requestSubmit();
  await until(() => commands.length === 1 && !$("command-reconcile").hidden, "lost acknowledgement offers recovery");
  assert($("propose-navigation").disabled && $("apply-affiliation").disabled, "single pending command lane");
  loseAck = false;
  await until(() => !$("retry-command").disabled, "bounded retry available");
  $("retry-command").click();
  await until(() => commands.length === 2, "navigation retried");
  assert(effects === 1 && JSON.stringify(commands[0]) === JSON.stringify(commands[1]), "retry never creates second proposal");
  publishResults = true;
  await until(() => !$("propose-navigation").disabled, "result reconciled");
  for (const status of ["pending", "accepted", "rejected", "expired"]) {
    fixture.navigation_proposal.status = status;
    const expected = translations["commander.web.proposal_" + status].split("{label}")[1];
    await until(() => $("navigation-status").textContent.includes(expected), "localized decision " + status);
  }
  assert(JSON.stringify(fixture.ownship) === ownship, "browser never changes helm");
  for (const field of ["course", "speed_kn"]) {
    $("navigation-course").value = field === "course" ? "0" : "";
    $("navigation-speed").value = field === "speed_kn" ? "0" : "";
    const count = commands.length;
    $("navigation-form").requestSubmit();
    await until(() => commands.length > count && !$("propose-navigation").disabled, "optional zero accepted");
    const body = commands.at(-1);
    assert(body[field] === 0 && !Object.hasOwn(body, field === "course" ? "speed_kn" : "course"), "blank omitted, zero preserved");
  }
  for (const phase of ["paused", "menu", "blocked", "ended"]) {
    fixture.phase = phase;
    await until(() => $("propose-navigation").disabled, "non-live form disabled");
    $("navigation-form").dispatchEvent(new Event("submit", {cancelable: true}));
    fixture.phase = "live";
    await until(() => !$("propose-navigation").disabled, "live again");
  }
  fixture.commands_allowed = false;
  await until(() => $("propose-navigation").disabled, "no local grant");
  fixture.commands_allowed = true; fixture.ownship.x = null;
  await sleep(600);
  assert($("propose-navigation").disabled, "no active world");
  assert(commands.length === 4 && effects === 3 && maxActive === 1 && !errors.length, "no extra commands or browser errors");
  assert(document.documentElement.scrollWidth <= innerWidth + 1, "mobile/desktop no horizontal overflow");
  parent.postMessage({navigation: "passed"}, location.origin);
}
window.addEventListener("DOMContentLoaded", () => run().catch((e) => parent.postMessage({navigation: String(e.stack || e)}, location.origin)));
"""


@pytest.mark.parametrize("width,height,language", [(1280, 720, "en"), (390, 844, "de")])
def test_navigation_browser_form_and_idempotent_recovery(tmp_path, width, height, language):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        pytest.skip("Optional navigation browser test: no Chromium")
    catalog = {key: value for key, value in catalogs()[language == "de"].items() if key.startswith(PREFIX)}
    script = NAVIGATION_BROWSER.replace("__STATE__", json.dumps(browser_state())).replace("__CATALOG__", json.dumps(catalog))
    html = ASSETS.joinpath("index.html").read_text().replace('<script src="./app.js" defer>',
        '<script src="./navigation.js" defer></script><script src="./app.js" defer>')
    routes = {
        "/": (html, "text/html"), "/navigation.js": (script, "text/javascript"),
        "/app.js": (ASSETS.joinpath("app.js").read_text(), "text/javascript"),
        "/style.css": (ASSETS.joinpath("style.css").read_text(), "text/css"),
        "/viewport": (f'<!doctype html><html><head><script src="/viewport.js" defer></script></head>'
                      f'<body><iframe src="/" width="{width}" height="{height}"></iframe></body></html>', "text/html"),
        "/viewport.js": ('window.addEventListener("message", (e) => {'
                         'if (e.origin === location.origin && e.data?.navigation) '
                         'document.documentElement.dataset.navigation = e.data.navigation;});', "text/javascript"),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path not in routes:
                self.send_error(404)
                return
            content, mime = routes[self.path]
            body = content.encode()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-background-networking", "--no-first-run", "--disable-dev-shm-usage",
            f"--user-data-dir={tmp_path / 'browser'}", "--virtual-time-budget=30000", "--dump-dom",
            f"http://127.0.0.1:{server.server_port}/viewport"], capture_output=True, text=True, timeout=60)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    assert result.returncode == 0, result.stderr
    root = next((attrs for tag, attrs in Document(result.stdout).elements if tag == "html"), {})
    assert root.get("data-navigation") == "passed", root.get("data-navigation", result.stdout[-3000:])
