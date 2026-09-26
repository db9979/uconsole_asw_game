"""The web-host login and setup shell executes in a real browser."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import shutil
import subprocess
import threading

import pytest

from commander_web import WEB_ROUTES

from src.core.i18n import load_catalog


def test_admin_setup_shell_in_chromium():
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            files = {"/admin": ("admin.html", "text/html"),
                     "/admin.js": ("admin.js", "text/javascript"),
                     "/admin.css": ("admin.css", "text/css")}
            if self.path in files:
                name, content_type = files[self.path]
                payload = resources.files("data.commander").joinpath(name).read_bytes()
            elif self.path.startswith(("/css/", "/fonts/")) and self.path in WEB_ROUTES:
                content_type, payload = WEB_ROUTES[self.path]
            elif self.path in ("/api/v2/ui?lang=en", "/api/v2/ui?lang=de"):
                content_type = "application/json"
                payload = json.dumps({key: value for key, value in load_catalog(self.path[-2:]).items()
                                      if key.startswith("commander.web.")}).encode()
            elif self.path == "/api/v2/web/status":
                content_type, payload = "application/json", b'{"configured":false}'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([
            chromium, "--headless", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--virtual-time-budget=2500", "--dump-dom",
            f"http://127.0.0.1:{server.server_port}/admin",
        ], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr[-1000:]
        assert "Set up host account" in result.stdout or "Host-Konto einrichten" in result.stdout
        assert 'id="setup"' in result.stdout
        assert 'id="setup" hidden' not in result.stdout
        assert 'id="editor-kind"' not in result.stdout
        assert 'id="editor-json"' not in result.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
