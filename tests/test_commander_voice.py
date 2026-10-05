"""Live voice relay, PTT gate, and lease authorization on the Commander port."""

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import shutil
import subprocess
import threading

import pytest

from websockets.legacy.client import connect

from src.commander.server import CommanderServer
from src.commander.web_auth import WebHostAuth
from src.core.i18n import load_catalog

pytestmark = pytest.mark.browser  # drives headless Chromium (CI browser job)


def test_voice_relay_requires_host_option_and_active_station(tmp_path):
    translations = {language: {key: value for key, value in load_catalog(language).items()
                               if key.startswith("commander.web.")}
                    for language in ("en", "de")}
    server = CommanderServer(translations=translations,
                             web_auth=WebHostAuth(tmp_path / "web-host.json"),
                             public_origin="https://game.test")
    server.start("127.0.0.1", 0)
    try:
        with server._lock:
            first_token, first = server._new_session_locked("Sonar")
            second_token, second = server._new_session_locked("Bridge")
        assert server.grant_station(first["client_id"], "sonar")
        assert server.grant_station(second["client_id"], "bridge")

        async def scenario():
            url = f"ws://127.0.0.1:{server.address[1]}/ws/v2/voice"
            def join(token):
                csrf = first["csrf"] if token == first_token else second["csrf"]
                return connect(url, origin="https://game.test",
                               subprotocols=["u-jagd-voice-v2", f"ujagd-csrf.{csrf}"],
                               extra_headers={"Cookie": f"ujagd_remote_v2={token}"})

            # Voice starts enabled; the host switched it off: no upgrade or
            # microphone path.
            server.set_voice_enabled(False)
            try:
                async with join(first_token):
                    assert False, "disabled voice accepted a connection"
            except Exception as error:
                assert "403" in str(error)
            server.set_voice_enabled(True)
            try:
                async with connect(url, origin="https://game.test",
                                   subprotocols=["u-jagd-voice-v2", "ujagd-csrf.invalid"],
                                   extra_headers={"Cookie": f"ujagd_remote_v2={first_token}"}):
                    assert False, "invalid voice CSRF accepted"
            except Exception as error:
                assert "403" in str(error)
            async with join(first_token) as sender, join(second_token) as receiver:
                assert json.loads(await sender.recv())["station"] == "sonar"
                assert json.loads(await receiver.recv())["station"] == "bridge"
                silence = bytes(1920)
                await sender.send(silence)
                try:
                    await asyncio.wait_for(receiver.recv(), .05)
                    assert False, "idle audio was relayed"
                except asyncio.TimeoutError:
                    pass
                await sender.send("down")
                assert json.loads(await receiver.recv()) == {
                    "type": "talker", "station": "sonar"}
                assert server.voice_talker == "sonar"
                assert json.loads(await sender.recv())["station"] == "sonar"
                await sender.send(silence)
                assert await receiver.recv() == bytes((1,)) + silence
                await sender.send("up")
                assert json.loads(await receiver.recv())["station"] is None
                assert server.voice_talker is None
                assert json.loads(await sender.recv())["station"] is None
                await sender.send(silence)
                try:
                    await asyncio.wait_for(receiver.recv(), .05)
                    assert False, "released audio was relayed"
                except asyncio.TimeoutError:
                    pass
                server.set_voice_enabled(False)
                await asyncio.wait_for(sender.wait_closed(), 2)
                await asyncio.wait_for(receiver.wait_closed(), 2)
            server.set_voice_enabled(True)
            async with join(first_token) as sender:
                assert json.loads(await sender.recv())["type"] == "ready"
                await sender.send("down")
                assert json.loads(await sender.recv())["station"] == "sonar"
                for _ in range(100):
                    await sender.send(bytes(1920))
                await sender.send("up")
                assert json.loads(await asyncio.wait_for(sender.recv(), 3))["station"] is None
                assert not sender.closed
                await sender.send("down")
                assert json.loads(await sender.recv())["station"] == "sonar"
                assert server.revoke_station("sonar")
                assert server.voice_talker is None
                await asyncio.wait_for(sender.wait_closed(), 2)

        asyncio.run(scenario())
    finally:
        server.stop()


def test_voice_browser_f_key_holds_ptt_and_labels_follow_language():
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    prelude = r'''
window.sent = []; window.closed = false;
class FakeNode { connect(next) { return next; } }
window.AudioContext = class {
  constructor() { this.destination = new FakeNode(); this.audioWorklet = {addModule: async () => {}}; }
  async resume() {} async close() {}
  createMediaStreamSource() { return new FakeNode(); }
  createBiquadFilter() { return Object.assign(new FakeNode(), {frequency: {value: 0}}); }
  createWaveShaper() { return new FakeNode(); }
  createGain() { return Object.assign(new FakeNode(), {gain: {value: 1}}); }
};
window.AudioWorkletNode = class extends FakeNode {
  constructor() { super(); this.port = {postMessage() {}, onmessage: null}; }
};
Object.defineProperty(navigator, "mediaDevices", {value: {getUserMedia: async () =>
  ({getTracks: () => [{stop() {}}]})}});
window.WebSocket = class {
  static OPEN = 1; static CLOSING = 2;
  constructor() { this.readyState = 1; this.bufferedAmount = 0;
    queueMicrotask(() => this.onmessage({data: JSON.stringify({type:"ready",station:"sonar",talker:null})})); }
  send(value) { window.sent.push(value); }
  close() { window.closed = true; this.readyState = 3; }
};
'''
    probe = r'''
(async () => {
  const wait = async (test) => { for (let i=0; i<250; i++) {
    if (test()) return; await new Promise((resolve) => setTimeout(resolve, 20));
  } throw new Error("timed out"); };
  try {
    await wait(() => document.getElementById("voice-enable").disabled === false);
    document.getElementById("voice-enable").click();
    await wait(() => document.getElementById("voice-ptt").disabled === false);
    document.body.dispatchEvent(new KeyboardEvent("keydown", {code:"KeyF",key:"f",bubbles:true}));
    await wait(() => window.sent.includes("down"));
    if (window.closed || document.getElementById("voice-ptt").getAttribute("aria-pressed") !== "true")
      throw new Error("F closed voice");
    document.body.dispatchEvent(new KeyboardEvent("keyup", {code:"KeyF",key:"f",bubbles:true}));
    if (window.sent.at(-1) !== "up" || window.closed) throw new Error("PTT release failed");
    document.getElementById("language").value="de";
    document.getElementById("language").dispatchEvent(new Event("change"));
    await wait(() => document.getElementById("voice-ptt").textContent.includes("Sprechen"));
    const translations = await (await fetch("/api/v2/ui?lang=de")).json();
    window.dispatchEvent(new CustomEvent("u-jagd-language", {detail:{language:"de",translations}}));
    if (document.getElementById("voice-stop").textContent !== "Funk beenden")
      throw new Error("voice buttons did not localize");
    await new Promise((resolve) => setTimeout(resolve, 2200));
    if (document.getElementById("voice-ptt").disabled || window.closed ||
        document.getElementById("voice-stop").textContent !== "Funk beenden")
      throw new Error("poll closed voice or reset the language");
    document.documentElement.dataset.voiceTest="passed";
  } catch (error) { document.documentElement.dataset.voiceTest="failed";
    document.documentElement.dataset.voiceError=String(error); }
})();
'''
    page = '''<!doctype html><html><body>
<select id="language"><option value="en">English</option><option value="de">Deutsch</option></select>
<button id="voice-enable" disabled></button><button id="voice-stop" disabled></button>
<button id="voice-ptt" disabled aria-pressed="false"></button><span id="voice-status"></span>
<script src="/prelude.js" defer></script><script src="/voice.js" defer></script>
<script src="/probe.js" defer></script></body></html>'''

    class Handler(BaseHTTPRequestHandler):
        status_calls = 0

        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/":
                body, mime = page.encode(), "text/html"
            elif self.path == "/voice.js":
                body = resources.files("data.commander").joinpath("voice.js").read_bytes()
                mime = "text/javascript"
            elif self.path == "/prelude.js":
                body, mime = prelude.encode(), "text/javascript"
            elif self.path == "/probe.js":
                body, mime = probe.encode(), "text/javascript"
            elif self.path.startswith("/api/v2/ui?lang="):
                language = self.path[-2:]
                body = json.dumps({key: value for key, value in load_catalog(language).items()
                                   if key.startswith("commander.web.")}).encode()
                mime = "application/json"
            elif self.path == "/api/v2/voice/status":
                Handler.status_calls += 1
                if Handler.status_calls > 1:
                    self.send_response(503)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body, mime = b'{"enabled":true,"station":"sonar","talker":null,"csrf":"test"}', "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([
            chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--virtual-time-budget=6000", "--dump-dom",
            f"http://127.0.0.1:{server.server_port}/",
        ], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr[-1000:]
        assert 'data-voice-test="passed"' in result.stdout, result.stdout[-1500:]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_real_chromium_ptt_keeps_authenticated_radio_open(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    translations = {language: {key: value for key, value in load_catalog(language).items()
                               if key.startswith("commander.web.")}
                    for language in ("en", "de")}
    server = CommanderServer(translations=translations,
                             web_auth=WebHostAuth(tmp_path / "web-host.json"),
                             public_origin="https://game.test")
    server.set_solo_mode(True)
    server.start("127.0.0.1", 0)
    # Chromium considers loopback a secure context. Keep this test entirely
    # local; production web-host still requires an exact HTTPS public origin.
    server.public_origin = None
    server.set_voice_enabled(True)
    code = server.pairing_code
    page = '''<!doctype html><html><body>
<select id="language"><option value="en">English</option><option value="de">Deutsch</option></select>
<button id="voice-enable" disabled></button><button id="voice-stop" disabled></button>
<button id="voice-ptt" disabled aria-pressed="false"></button><span id="voice-status"></span>
<script src="/prelude.js" defer></script><script src="/voice.js" defer></script>
<script src="/probe.js" defer></script></body></html>'''
    prelude = r'''
class FakeNode { connect(next) { return next; } }
window.AudioContext = class {
  constructor() { this.destination = new FakeNode(); this.audioWorklet = {addModule: async () => {}}; }
  async resume() {} async close() {}
  createMediaStreamSource() { return new FakeNode(); }
  createBiquadFilter() { return Object.assign(new FakeNode(), {frequency:{value:0}}); }
  createWaveShaper() { return new FakeNode(); }
  createGain() { return Object.assign(new FakeNode(), {gain:{value:1}}); }
};
window.AudioWorkletNode = class extends FakeNode {
  constructor() { super(); this.port = {onmessage:null, timer:null,
    postMessage(value) {
      if (value === "down" && !this.timer) this.timer = setInterval(() =>
        this.onmessage?.({data:new ArrayBuffer(1920)}), 20);
      if (value === "up") { clearInterval(this.timer); this.timer=null; }
    }}; }
};
Object.defineProperty(navigator, "mediaDevices", {value:{getUserMedia: async () =>
  ({getTracks: () => [{stop() {}}]})}});
'''
    probe = r'''
(async () => {
  const wait = async (test) => { for (let i=0; i<200; i++) {
    if (await test()) return; await new Promise((resolve) => setTimeout(resolve, 50));
  } throw new Error("timed out"); };
  try {
    const pair = await fetch("/api/v2/pair", {method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({code:__CODE__,name:"Voice test"})});
    if (!pair.ok) throw new Error(`pair ${pair.status}`);
    await wait(() => !document.getElementById("voice-enable").disabled);
    document.getElementById("voice-enable").click();
    await wait(() => !document.getElementById("voice-ptt").disabled);
    document.body.dispatchEvent(new KeyboardEvent("keydown", {code:"KeyF",key:"f",bubbles:true}));
    const status = async () => (await (await fetch("/api/v2/voice/status")).json());
    await wait(async () => (await status()).talker === "bridge");
    await new Promise((resolve) => setTimeout(resolve, 2500));
    if ((await status()).talker !== "bridge" || document.getElementById("voice-ptt").disabled)
      throw new Error("long PTT hold closed radio");
    if (document.getElementById("voice-ptt").getAttribute("aria-pressed") !== "true")
      throw new Error("PTT was released while F was held");
    document.body.dispatchEvent(new KeyboardEvent("keyup", {code:"KeyF",key:"f",bubbles:true}));
    await wait(async () => (await status()).talker === null);
    if (document.getElementById("voice-ptt").disabled) throw new Error("radio closed after PTT");
    document.documentElement.dataset.voiceTest="passed";
  } catch (error) { document.documentElement.dataset.voiceTest="failed";
    document.documentElement.dataset.voiceError=String(error); }
})();
'''.replace("__CODE__", json.dumps(code))
    server._http.assets["/"] = ("text/html; charset=utf-8", page.encode())
    server._http.assets["/prelude.js"] = ("text/javascript; charset=utf-8", prelude.encode())
    server._http.assets["/probe.js"] = ("text/javascript; charset=utf-8", probe.encode())
    try:
        result = subprocess.run([
            chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            "--virtual-time-budget=20000", "--dump-dom",
            f"http://127.0.0.1:{server.address[1]}/",
        ], capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr[-1000:]
        assert 'data-voice-test="passed"' in result.stdout, result.stdout[-1800:]
    finally:
        server.stop()
