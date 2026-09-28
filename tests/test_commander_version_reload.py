"""A browser page that outlived a host update reloads itself once."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.commander.assets import static_assets
from src.core.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
VERSION_JS = ROOT / "data" / "commander" / "js" / "net" / "version.js"


@pytest.mark.parametrize("web_host", [False, True])
def test_served_page_names_its_version(web_host):
    page = static_assets(web_host)["/"][1].decode("utf-8")
    assert page.count('<meta name="u-jagd-version"') == 1
    assert f'<meta name="u-jagd-version" content="{APP_VERSION}">' in page


def test_the_page_hands_its_version_to_the_transport():
    main_js = (ROOT / "data" / "commander" / "js" / "main.js").read_text()
    assert ('setPageVersion(document.querySelector(\'meta[name="u-jagd-version"]\')'
            in main_js)


def test_every_api_request_checks_the_host_version():
    request_js = (ROOT / "data" / "commander" / "js" / "net" / "request.js").read_text()
    assert 'checkHostVersion(response.headers.get("X-U-Jagd-Version"))' in request_js


def _run(page_version, host_versions):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    meta = "null" if page_version is None else json.dumps(page_version)
    script = f"""
let reloads = 0;
globalThis.location = {{ reload() {{ reloads += 1; }} }};
const m = await import({json.dumps(VERSION_JS.as_uri())});
m.setPageVersion({meta});
const results = {json.dumps(host_versions)}.map((v) => m.checkHostVersion(v));
console.log(JSON.stringify({{ reloads, results }}));
"""
    out = subprocess.run([node, "--input-type=module", "-e", script], check=True,
                         capture_output=True, text=True, timeout=30).stdout
    return json.loads(out)


def test_mismatch_reloads_exactly_once():
    assert _run("1.3.45", ["1.3.45", None, "", "1.3.46", "1.3.46"]) == {
        "reloads": 1, "results": [False, False, False, True, False]}


def test_page_without_version_never_reloads():
    assert _run(None, ["1.3.46"]) == {"reloads": 0, "results": [False]}
