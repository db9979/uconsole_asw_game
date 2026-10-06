"""Shared access to the Remote Crew web client assets for tests.

Browser tests serve the real asset set (the server's own manifest and MIME
table), inject a probe script before the client entry point, and static
source checks scan every client script and stylesheet rather than one file.
"""
from __future__ import annotations

import shutil
import threading
import time
from importlib import resources
from pathlib import Path

from src.commander.assets import (ASSET_TREES, PUBLIC_FILES, WEB_HOST_FILES,
                                  static_assets)

ASSETS = resources.files("data.commander")
ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "data" / "commander"
# The single client entry tag in index.html; probes are injected right before it.
ENTRY_TAG = '<script type="module" src="./js/main.js"></script>'


def index_html() -> str:
    return ASSETS.joinpath("index.html").read_text(encoding="utf-8")


def inject_probe(html: str, *names: str) -> str:
    """Load ``names`` (classic deferred scripts) before the client entry point."""
    assert ENTRY_TAG in html, "client entry tag missing from index.html"
    probes = "".join(f'<script src="./{name}" defer></script>' for name in names)
    return html.replace(ENTRY_TAG, probes + ENTRY_TAG, 1)


def top_level_files() -> list[str]:
    """Every top-level asset file name the server reads (public and web-host)."""
    return [name for _route, name, _mime in PUBLIC_FILES + WEB_HOST_FILES]


def tree_files() -> list[Path]:
    """Relative paths of every file below the css/, js/ and fonts/ trees."""
    out = []
    for tree in ASSET_TREES:
        base = ASSET_DIR / tree
        if base.is_dir():
            out.extend(sorted(path.relative_to(ASSET_DIR) for path in base.rglob("*")
                              if path.is_file() and "__pycache__" not in path.parts))
    return out


def copy_assets(target: Path, html: str | None = None) -> None:
    """Copy the complete client into ``target`` (for a patched resources.files)."""
    for name in top_level_files():
        shutil.copyfile(ASSET_DIR / name, target / name)
    for relative in tree_files():
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ASSET_DIR / relative, target / relative)
    if html is not None:
        (target / "index.html").write_text(html, encoding="utf-8")


def write_fixture_assets(target: Path) -> None:
    """Placeholder files with every name the server reads, for transport tests."""
    for name in top_level_files():
        (target / name).write_text(f"fixture {name}", encoding="utf-8")


def web_routes() -> dict[str, tuple[str, bytes]]:
    """The full static route table (web-host variant keeps voice.js in the page)."""
    return static_assets(True, ASSETS)


def js_files() -> list[Path]:
    """Every client script (top-level scripts plus the js/ tree), sorted."""
    names = sorted(path for path in ASSET_DIR.glob("*.js"))
    return names + [ASSET_DIR / path for path in tree_files() if path.suffix == ".js"]


def client_js_files() -> list[Path]:
    """The crew client proper in source order (entry-point import order).

    Admin, voice and worklet scripts and the phone lookout (``js/phone/``)
    are separate programs and excluded.
    """
    import re
    main = ASSET_DIR / "js" / "main.js"
    order = re.findall(r'^import (?:\{[^}]*\} from )?"\./([\w/.-]+)";', main.read_text(), re.M)
    files = [ASSET_DIR / "js" / name for name in order]
    rest = [path for path in js_files() if path.parent != ASSET_DIR and path not in files
            and path != main and path.parent != ASSET_DIR / "js" / "phone"]
    return files + sorted(rest) + [main]


def client_js() -> str:
    """Crew client source in original order for static contract checks.

    ``export`` keywords are dropped so declarations read the same in every
    module; import lines are kept (they are part of the checked source).
    """
    import re
    text = "\n".join(path.read_text(encoding="utf-8") for path in client_js_files())
    return re.sub(r"^export (?=(?:async )?function|const |let |class )", "", text, flags=re.M)


def client_css_files() -> list[Path]:
    """The crew stylesheets in the order index.html links them."""
    import re
    links = re.findall(r'<link rel="stylesheet" href="\./(css/[a-z]+\.css)">', index_html())
    return [ASSET_DIR / link for link in links]


def client_css() -> str:
    """Concatenated crew stylesheets in cascade order."""
    return "\n".join(path.read_text(encoding="utf-8") for path in client_css_files())


WEB_ROUTES = web_routes()


MODULE_ENTRY_TAG = '<script type="module" src="./js/main.js"></script>'


def run_module_probe(tmp_path, probe: str, *, routes: dict | None = None,
                     window: tuple[int, int] = (1280, 720), budget_ms: int = 5000,
                     timeout: int = 60) -> dict:
    """Run ``probe`` (an ES module) against the real page markup in Chromium.

    The client entry point is replaced by the probe, so no module initializer
    runs unless the probe imports and calls it. The probe reports by setting
    ``document.documentElement.dataset.result`` (and optionally ``failure``);
    the attributes of <html> are returned.
    """
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from test_commander_assets import Document

    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        import pytest
        pytest.skip("Chromium unavailable")
    table = dict(WEB_ROUTES)
    page = table["/"][1].decode("utf-8")
    assert MODULE_ENTRY_TAG in page, "module entry tag missing from index.html"
    table["/"] = ("text/html; charset=utf-8", page.replace(
        MODULE_ENTRY_TAG, '<script src="./probe-errors.js"></script>'
        '<script type="module" src="./probe.js"></script>', 1).encode())
    table["/probe.js"] = ("text/javascript; charset=utf-8", probe.encode("utf-8"))
    # Module load/link errors never reach the probe itself; report them here.
    table["/probe-errors.js"] = ("text/javascript; charset=utf-8", (
        'addEventListener("error", (event) => { document.documentElement.dataset.failure ='
        ' String(event.error?.stack || event.message); }, true);').encode())
    table.update(routes or {})

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path not in table:
                self.send_error(404)
                return
            mime, body = table[self.path]
            body = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [chromium, "--headless", "--no-sandbox", "--disable-gpu",
                 "--disable-background-networking", "--no-first-run",
                 "--no-default-browser-check", "--disable-dev-shm-usage",
                 f"--user-data-dir={tmp_path / 'module-probe'}",
                 f"--window-size={window[0]},{window[1]}",
                 f"--virtual-time-budget={budget_ms}", "--dump-dom",
                 f"http://127.0.0.1:{server.server_port}/"],
                capture_output=True, text=True, timeout=timeout)
        finally:
            server.shutdown()
            thread.join(timeout=5)
    root = next((attrs for tag, attrs in Document(result.stdout).elements if tag == "html"), {})
    root.setdefault("data-failure", result.stderr[-2000:])
    return root


def page_dataset(profile: Path) -> dict | None:
    """``<html>`` data attributes of a live headless Chromium page, or None.

    For probes that must run in real time next to the simulation: Chromium's
    virtual time races ahead of the host and starves live WebSocket streams.
    Launch with ``--remote-debugging-port=0`` and ``--user-data-dir=profile``.
    """
    import json
    import urllib.request

    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect

    try:
        port = int((profile / "DevToolsActivePort").read_text().split()[0])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as reply:
            page = next(target for target in json.load(reply) if target["type"] == "page")
        with connect(page["webSocketDebuggerUrl"], open_timeout=2, max_size=None) as devtools:
            devtools.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
                "expression": "JSON.stringify({...document.documentElement.dataset})",
                "returnByValue": True}}))
            while True:
                message = json.loads(devtools.recv(timeout=2))
                if message.get("id") == 1:
                    return json.loads(message["result"]["result"]["value"])
    except (OSError, ValueError, KeyError, StopIteration, TimeoutError, WebSocketException):
        # A busy browser may drop the DevTools socket; the next read retries.
        return None


class RealTimeHost:
    """Drive a test host loop at wall-clock speed, like ``Game.run``.

    Browser probes that listen to live audio play it in real time. A loop of
    fixed ``game.update(.02)`` steps plus sleeps and DevTools reads runs the
    simulation (and the audio produced in it) slower than playback, so the
    worklet underruns whenever the machine is loaded. Each step advances the
    game by the elapsed wall time through ``Game._frame_dt`` (bounded frames
    and catch-up debt), and the page's ``<html>`` dataset is read on a
    background thread so a slow DevTools round trip never stalls the host.
    """

    def __init__(self, game, profile: Path, *, period_s: float = .5):
        self.game = game
        self.profile = profile
        self.period_s = period_s
        self.dataset: dict = {}
        self._last = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_page, daemon=True)
        self._thread.start()

    def _read_page(self) -> None:
        while not self._stop.wait(self.period_s):
            root = page_dataset(self.profile)
            if root is not None:
                self.dataset = root

    def step(self) -> None:
        """Advance the game by the wall time since the previous step."""
        now = time.monotonic()
        wall_dt = 0.0 if self._last is None else now - self._last
        self._last = now
        self.game.update(self.game._frame_dt(wall_dt))

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)


def module_source(relative: str, start: str | None = None, end: str | None = None) -> str:
    """Source of ``js/<relative>`` as plain script text for isolated algorithm tests.

    Import lines and ``export`` keywords are dropped, so a probe can supply its
    own deterministic stand-ins (a fake clock, a stub ``S`` store) for whatever
    the sliced code references. ``start``/``end`` cut the text at exact markers.
    """
    import re
    text = (ASSET_DIR / "js" / relative).read_text(encoding="utf-8")
    text = "\n".join(line for line in text.split("\n") if not line.startswith("import "))
    text = re.sub(r"^export (?=(?:async )?function|const |let |class )", "", text, flags=re.M)
    if start is not None:
        text = text[text.index(start):]
    if end is not None:
        text = text[:text.index(end)]
    return text


def function_source(text: str, name: str) -> str:
    """The complete ``function name(...) {...}`` declaration (brace matched)."""
    import re
    start = re.search(rf"^(?:export )?(?:async )?function {re.escape(name)}\(", text, re.M).start()
    depth = 0
    for index in range(text.index("{", text.index(")", start)), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(name)
