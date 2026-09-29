"""Remote Crew server language: the starter's switch, the host language the
pages open in, and the visible switch on the crew page."""

import shutil
import subprocess
import urllib.request

import pytest
from commander_web import copy_assets, index_html, inject_probe

from src.commander import server as commander_transport
from src.core import config, manual
from src.core.game import Game
from src.core.preferences import load_preferences, save_preferences, Preferences
from src.launcher import app
from test_commander_assets import PREFIX, Document, catalogs


def _translations():
    en, de = catalogs()
    return {"en": {key: value for key, value in en.items() if key.startswith(PREFIX)},
            "de": {key: value for key, value in de.items() if key.startswith(PREFIX)}}


def _get(server, path):
    host, port = server.address
    with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=10) as response:
        return response.read().decode("utf-8")


def test_pages_name_the_host_language_and_ignore_unknown_ones():
    server = commander_transport.CommanderServer(translations=_translations(),
                                                 contact_analysis_assets={})
    server.start("127.0.0.1", 0)
    try:
        assert '<meta name="u-jagd-host-language" content="en">' in _get(server, "/")
        server.set_host_language("de")
        for path in ("/", "/lookout"):
            page = _get(server, path)
            assert page.count('<meta name="u-jagd-host-language" content="de">') == 1, path
        server.set_host_language("fr")
        server.set_host_language(None)
        assert '<meta name="u-jagd-host-language" content="de">' in _get(server, "/")
        # Scripts are never rewritten.
        assert "<meta" not in _get(server, "/js/core/i18n.js")
    finally:
        server.stop()


def test_the_game_tells_its_listener_the_saved_language(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DIR", str(tmp_path / "saves"))
    game = Game(seed=5, start_menu=False, audio_enabled=False, language="de")
    console = game.commander
    console.solo, console.port = False, 0
    console._translations = _translations()
    console._contact_analysis_assets = {}
    console._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
    try:
        console.activate(game)
        console.pump(game)
        assert console.server._host_language == "de"
        game._set_preference("language", "en")
        console.pump(game)
        assert console.server._host_language == "en"
    finally:
        console.stop()
        game.audio.shutdown()


class _Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def test_starter_language_switch_relabels_and_is_saved_for_the_game(tmp_path):
    path = tmp_path / "settings.json"
    save_preferences(Preferences(language="en", fullscreen=False, onboarded=False), path)
    starter = object.__new__(app.Starter)
    starter.preferences_path = path
    starter.tr = app.Translator("en")
    starter.language = _Var("English")
    starter.texts = {}
    starter.state_text, starter.update_text = _Var(), _Var()
    rebuilt = []
    starter._build = lambda: rebuilt.append(starter.tr.language)
    starter._say(starter.state_text, "launcher.state.stopped")
    starter._say(starter.update_text, "launcher.update.current", version="9.9.9")

    starter.choose_language("de")
    _en, de = catalogs()
    assert rebuilt == ["de"] and starter.language.get() == "Deutsch"
    assert starter.state_text.get() == de["launcher.state.stopped"]
    assert starter.update_text.get() == de["launcher.update.current"].format(version="9.9.9")
    saved = load_preferences(path)
    # Only the language changes; a first launch keeps its welcome page.
    assert saved.language == "de" and saved.fullscreen is False and saved.onboarded is False
    starter.choose_language("de")
    starter.choose_language("fr")
    assert rebuilt == ["de"]
    assert set(app.LANGUAGE_NAMES) == {"en", "de"}


SWITCH_SCRIPT = r"""
(() => {
"use strict";
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check, message) {
  for (let index = 0; index < 1500; index++) { if (check()) return; await sleep(20); }
  throw new Error(message);
}
async function run() {
  await until(() => !$("shell").hidden, "translations missing");
  const root = document.documentElement;
  root.dataset.firstLang = root.lang;
  root.dataset.firstTitle = document.querySelector("#pairing h1").textContent;
  root.dataset.firstSwitch = $("language-switch").textContent;
  $("language-switch").click();
  await until(() => root.lang === "en", "switch did not change the language");
  root.dataset.secondTitle = document.querySelector("#pairing h1").textContent;
  root.dataset.secondSwitch = $("language-switch").textContent;
  root.dataset.selectValue = $("language").value;
  root.dataset.switchTest = "passed";
}
addEventListener("load", () => {
  run().catch((error) => { document.documentElement.dataset.failure = String(error?.stack || error); });
});
})();
"""


def test_crew_page_opens_in_the_host_language_and_switches_visibly(tmp_path, monkeypatch):
    chromium = (shutil.which("chromium") or shutil.which("chromium-browser")
                or shutil.which("google-chrome"))
    if not chromium:
        pytest.skip("Optional language browser contract: no installed Chromium")
    copy_assets(tmp_path, inject_probe(index_html(), "switch-test.js"))
    monkeypatch.setattr(commander_transport.resources, "files", lambda _package: tmp_path)
    server = commander_transport.CommanderServer(translations=_translations(),
                                                 contact_analysis_assets={})
    server.set_host_language("de")
    server.start("127.0.0.1", 0)
    server._http.assets["/switch-test.js"] = ("text/javascript; charset=utf-8",
                                              SWITCH_SCRIPT.encode("utf-8"))
    try:
        host, port = server.address
        result = subprocess.run(
            [chromium, "--headless", "--no-sandbox", "--disable-gpu",
             "--disable-background-networking", "--no-first-run",
             "--no-default-browser-check", "--disable-dev-shm-usage",
             f"--user-data-dir={tmp_path / 'browser'}", "--lang=en-US",
             "--virtual-time-budget=20000", "--window-size=1600,900", "--dump-dom",
             f"http://{host}:{port}/"],
            capture_output=True, text=True, timeout=90)
    finally:
        server.stop()
    root = next((attrs for tag, attrs in Document(result.stdout).elements if tag == "html"), {})
    assert root.get("data-switch-test") == "passed", root.get(
        "data-failure", result.stdout[-3000:] + result.stderr[-1500:])
    en, de = catalogs()
    assert root["data-first-lang"] == "de"
    assert root["data-first-title"] == de[PREFIX + "pair_title"]
    assert root["data-first-switch"] == en[PREFIX + "english"]
    assert root["data-second-title"] == en[PREFIX + "pair_title"]
    assert root["data-second-switch"] == de[PREFIX + "german"]
    assert root["data-select-value"] == "en"


def test_language_switch_prose_is_in_both_catalogs():
    en, de = catalogs()
    for key in (PREFIX + "language_switch", "launcher.language"):
        assert en[key] and de[key] and en[key] != de[key]
    assert 'id="language-switch"' in index_html()
