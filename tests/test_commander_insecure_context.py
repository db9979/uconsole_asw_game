"""The LAN host serves plain HTTP, where crypto.randomUUID does not exist.

Every request-ID generator in the browser clients must fall back to
crypto.getRandomValues instead of throwing ("crypto.randomUUID is not a
function" at pairing/login).
"""

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path("data/commander")


def _function_source(text: str, name: str) -> str:
    start = re.search(rf"^\s*function {name}\(\) {{", text, re.M).start()
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(name)


def test_request_ids_never_call_random_uuid_unguarded():
    for path in ASSETS.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"crypto\.randomUUID\(\)", text):
            line = text[text.rfind("\n", 0, match.start()) + 1:text.find("\n", match.end())]
            assert 'typeof crypto.randomUUID === "function"' in line, (path, line)


def test_request_id_fallback_works_without_random_uuid(tmp_path):
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chromium is None:
        pytest.skip("Chromium is not installed")
    admin = _function_source((ASSETS / "admin.js").read_text(encoding="utf-8"), "requestId")
    app = _function_source((ASSETS / "app.js").read_text(encoding="utf-8"), "secureId")
    script = "\n".join([
        # Emulate a non-secure context: the method is absent.
        "Object.defineProperty(Crypto.prototype, 'randomUUID', {value: undefined});",
        admin, app,
        "const pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;",
        "const ids = [requestId(), requestId(), secureId(), secureId()];",
        "document.documentElement.dataset.result = JSON.stringify({",
        "  valid: ids.every((id) => pattern.test(id)), unique: new Set(ids).size});",
    ])
    page = tmp_path / "ids.html"
    page.write_text(f"<!doctype html><html><body><script>{script}</script></body></html>",
                    encoding="utf-8")
    result = subprocess.run(
        [chromium, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run",
         f"--user-data-dir={tmp_path / 'profile'}", "--virtual-time-budget=5000",
         "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=60)
    match = re.search(r'data-result="([^"]*)"', result.stdout)
    assert match, result.stdout[-2000:] + result.stderr[-2000:]
    assert json.loads(html.unescape(match.group(1))) == {"valid": True, "unique": 4}
