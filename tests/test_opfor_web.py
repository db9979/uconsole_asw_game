"""The submarine sonar room in real Chromium: filters and continuous audio."""

import json
import shutil
import subprocess
import time

import pygame
import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server
from src.core.game import Game
from test_commander_assets import ASSETS, Document, PREFIX, catalogs


PROBE = r'''
(() => {
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(check, message, limit = 200000) {
    for (let index = 0; index < limit; index++) {
      if (check()) return;
      await sleep(20);
    }
    throw new Error(typeof message === 'function' ? message() : message);
  }
  // Count delivered submarine audio blocks on either transport, and the
  // world epochs the browser sees in its state polls.
  let blocks = 0;
  const sequences = [];
  const epochs = new Set();
  const NativeSocket = window.WebSocket, nativeFetch = window.fetch;
  window.WebSocket = function (url, protocol) {
    const socket = new NativeSocket(url, protocol);
    if (String(url).includes('/ws/v2/uboot/audio')) socket.addEventListener('message', ({data}) => {
      blocks++;
      if (data instanceof ArrayBuffer && data.byteLength === 2060)
        sequences.push(Number(new DataView(data).getBigUint64(4, true)));
    });
    return socket;
  };
  window.WebSocket.prototype = NativeSocket.prototype;
  Object.assign(window.WebSocket, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const url = String(args[0]);
    if (url.endsWith('/api/v2/uboot/audio') && response.status === 200) {
      blocks++;
      sequences.push(Number(response.headers.get('x-u-jagd-audio-sequence')));
    }
    if (url.includes('/api/v2/state') && response.status === 200)
      response.clone().json().then((state) => { if (state.role) epochs.add(state.epoch); }, () => {});
    return response;
  };
  async function run() {
    await until(() => !$('shell').hidden, 'translations');
    $('name').value = 'Submarine'; $('code').value = __CODE__;
    $('pair-form').requestSubmit();
    await until(() => $('station-tab-uboot_sonar'), 'submarine sonar tab');
    $('station-tab-uboot_sonar').click();
    root.dataset.stage = 'panel';
    await until(() => document.body.dataset.remoteRole === 'assigned' &&
      !$('station-sonar').hidden && !$('sonar-visual').hidden, 'sonar panel');
    await until(() => !$('sonar-listen-band').disabled, 'filters enabled');
    if (!$('sonar-tas').hidden) throw new Error('towed array offered aboard the boat');
    $('sonar-listen-band').value = 'LOW';
    $('sonar-listen-band').dispatchEvent(new Event('change'));
    await until(() => !$('sonar-listen-notch').disabled, 'band applied');
    await sleep(600);
    $('sonar-listen-notch').checked = true;
    $('sonar-listen-notch').dispatchEvent(new Event('change'));
    await sleep(600);
    root.dataset.stage = 'listening';
    $('sonar-live-toggle').click();
    await until(() => $('sonar-live-toggle').getAttribute('aria-pressed') === 'true',
      () => `live sonar not started: ${$('sonar-live-status').textContent}`);
    // The host types on the uConsole: two epoch steps later the live stream
    // must still be on (conditions, not wall time).
    root.dataset.stage = 'host input';
    const seen = epochs.size;
    await until(() => epochs.size >= seen + 2, () => `no epoch steps: ${[...epochs]}`);
    if ($('sonar-live-toggle').getAttribute('aria-pressed') !== 'true')
      throw new Error(`live sonar switched off by host input: ${$('sonar-live-status').textContent}`);
    // Audio keeps flowing after the host's input: at least two seconds of new
    // blocks arrive, every sequence is higher than the one before (a restart
    // at 1 would make the worklet drop them all), and nothing went stale.
    root.dataset.stage = 'audio after host input';
    const before = blocks;
    await until(() => blocks >= before + 8, () => `audio stalled after host input: ${blocks - before} blocks`);
    for (let i = 1; i < sequences.length; i++)
      if (!(sequences[i] > sequences[i - 1])) throw new Error(`sequence went backwards: ${sequences[i - 1]} -> ${sequences[i]}`);
    const diagnostics = window.uJagdAudioDiagnostics || {};
    if (diagnostics.stale === true || diagnostics.droppedBlocks > 0)
      throw new Error(`worklet dropped audio: ${JSON.stringify(diagnostics)}`);
    root.dataset.sequences = String(sequences.length);
  }
  run().then(() => { root.dataset.opforTest = 'passed'; }, (error) => {
    root.dataset.opforTest = 'failed';
    root.dataset.failure = String(error.stack || error);
  });
})();
'''


def test_submarine_sonar_filters_and_audio_survive_host_input(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional submarine sonar browser contract: no Chromium")
    en, de = catalogs()
    game = Game(seed=913, start_menu=False, audio_enabled=False, language="en")
    console = game.commander
    console.port = 0
    console._translations = {
        "en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
        "de": {key: value for key, value in de.items() if key.startswith(PREFIX)},
    }
    console._contact_analysis_assets = {}
    console._manual_pages = {}
    html = inject_probe(index_html(), "opfor-test.js")
    copy_assets(tmp_path, html)
    monkeypatch.setattr(server.resources, "files", lambda _package: tmp_path)
    console.activate(game)
    console.server._http.assets["/opfor-test.js"] = (
        "text/javascript; charset=utf-8",
        PROBE.replace("__CODE__", json.dumps(console.pairing_code)).encode("utf-8"))
    console.bridge.allowed = True
    process = subprocess.Popen([
        chromium, "--headless", "--no-sandbox", "--disable-gpu",
        "--disable-background-networking", "--no-first-run",
        "--no-default-browser-check", "--disable-dev-shm-usage",
        "--autoplay-policy=no-user-gesture-required",
        f"--user-data-dir={tmp_path / 'browser'}", "--window-size=1600,1000",
        "--virtual-time-budget=60000", "--dump-dom",
        f"http://{console.address[0]}:{console.address[1]}/",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    granted = False
    epoch = boat = None
    bumped_at = None
    try:
        while process.poll() is None and time.monotonic() - started < 120:
            if not granted:
                clients = console.server.client_statuses()
                if clients:
                    client = clients[0]["client_id"]
                    assert console.server.grant_station(client, "uboot_sonar")
                    assert console.server.set_client_grant(
                        client, "uboot_sonar", "sonar_audio", True)
                    granted = True
            elif (game.opfor is not None and game.opfor.station.sonar.notch_enabled
                  and (bumped_at is None or time.monotonic() - bumped_at > 2.0)):
                if epoch is None:
                    epoch = console.bridge.status["epoch"]
                    boat = game.opfor
                # Local numeric entry on the uConsole advances the world epoch.
                for key in (pygame.K_u, pygame.K_ESCAPE):
                    game.handle_event(pygame.event.Event(
                        pygame.KEYDOWN, key=key, mod=0, unicode=""))
                bumped_at = time.monotonic()
            console.pump(game)
            game.update(.02)
            time.sleep(.02)
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        console.stop()
        game.audio.shutdown()
    root = next((attrs for tag, attrs in Document(stdout).elements if tag == "html"), {})
    assert root.get("data-opfor-test") == "passed", (
        root.get("data-stage"), root.get("data-failure", stderr[-2000:]))
    assert boat is not None
    sonar = boat.station.sonar
    assert (sonar.band_low_hz, sonar.band_high_hz) == (4.0, 80.0)
    assert sonar.notch_enabled and not game.sonar.notch_enabled
    assert console.bridge.status["epoch"] >= epoch + 2
