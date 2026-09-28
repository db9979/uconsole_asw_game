"""Windows starter: update rules, game command line, status file, autostart."""

import hashlib
import io
import json
import sys
import urllib.error

import pytest

from src.launcher import app, update

ASSET_URL = ("https://github.com/db9979/uconsole_asw_game/releases/download/"
             "v9.9.9/U-Jagd-Windows.exe")


def _payload(tag="v9.9.9", **asset):
    entry = {"name": update.ASSET_NAME, "browser_download_url": ASSET_URL, "size": 4}
    entry.update(asset)
    return {"tag_name": tag, "draft": False, "prerelease": False,
            "html_url": "https://github.com/db9979/uconsole_asw_game/releases/tag/v9.9.9",
            "assets": [{"name": "other.zip"}, entry]}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_versions_parse_strictly_and_compare_numerically():
    assert update.parse_version("v1.3.10") == (1, 3, 10)
    assert update.parse_version("1.3.9") == (1, 3, 9)
    assert update.parse_version("1.3.10") > update.parse_version("1.3.9")
    for bad in ("1.3", "v1.3.9-rc1", "latest", "", None, 139):
        assert update.parse_version(bad) is None


def test_only_a_newer_published_windows_asset_is_offered():
    release = update.select_release(_payload(digest="sha256:" + "a" * 64), "1.3.9")
    assert release.version == "9.9.9" and release.url == ASSET_URL
    assert release.sha256 == "a" * 64 and release.size == 4
    assert update.select_release(_payload(tag="v1.3.9"), "1.3.9") is None
    assert update.select_release(_payload(tag="v1.3.8"), "1.3.9") is None
    assert update.select_release({**_payload(), "draft": True}, "1.3.9") is None
    assert update.select_release({**_payload(), "prerelease": True}, "1.3.9") is None
    assert update.select_release({**_payload(), "assets": []}, "1.3.9") is None
    for hostile in ({"browser_download_url": "http://github.com/x.exe"},
                    {"browser_download_url": "https://evil.example/x.exe"},
                    {"browser_download_url": "https://user@github.com/x.exe"},
                    {"size": 0}, {"size": update.MAX_ASSET_BYTES + 1}, {"size": "4"},
                    {"digest": "md5:abc"}, {"digest": "sha256:XYZ"}):
        assert update.select_release(_payload(**hostile), "1.3.9") is None
    assert update.select_release([], "1.3.9") is None


def test_check_latest_reads_github_and_treats_no_release_as_current():
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, timeout))
        return _Response(json.dumps(_payload()).encode())

    assert update.check_latest("1.3.9", opener=opener).version == "9.9.9"
    assert seen[0][0] == update.LATEST_RELEASE_API

    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    assert update.check_latest("1.3.9", opener=missing) is None

    def offline(request, timeout):
        raise urllib.error.URLError("offline")

    with pytest.raises(update.UpdateError):
        update.check_latest("1.3.9", opener=offline)
    with pytest.raises(update.UpdateError):
        update.check_latest("1.3.9", opener=lambda r, timeout: _Response(b"{"))
    huge = b" " * (update.MAX_METADATA_BYTES + 1)
    with pytest.raises(update.UpdateError):
        update.check_latest("1.3.9", opener=lambda r, timeout: _Response(huge))


def test_download_is_verified_and_atomic(tmp_path):
    body = b"MZ\x90\x00"
    target = tmp_path / "U-Jagd-Windows.exe.new"
    good = update.Release("9.9.9", ASSET_URL, len(body),
                          hashlib.sha256(body).hexdigest(), update.RELEASES_PAGE)
    progress = []
    update.download(good, str(target), opener=lambda r, timeout: _Response(body),
                    progress=lambda done, total: progress.append((done, total)))
    assert target.read_bytes() == body and progress[-1] == (4, 4)
    target.unlink()
    for release, data in ((update.Release("9.9.9", ASSET_URL, 4, "0" * 64, ""), body),
                          (good, body + b"x"), (good, body[:2])):
        with pytest.raises(update.UpdateError):
            update.download(release, str(target), opener=lambda r, timeout, d=data: _Response(d))
        assert not target.exists()
        assert not (tmp_path / "U-Jagd-Windows.exe.new.part").exists()


def test_install_script_waits_for_the_starter_and_swaps_the_file():
    script = update.install_script(r"C:\Games\U-Jagd-Windows.exe",
                                   r"C:\Games\U-Jagd-Windows.exe.new", 4242)
    assert 'PID eq 4242' in script
    assert r'move /Y "C:\Games\U-Jagd-Windows.exe.new" "C:\Games\U-Jagd-Windows.exe"' in script
    assert r'start "" "C:\Games\U-Jagd-Windows.exe"' in script
    assert script.endswith("\r\n")
    for bad in (r'C:\a"b.exe', r"C:\%PATH%.exe", "C:\\a\nb.exe"):
        with pytest.raises(update.UpdateError):
            update.install_script(bad, r"C:\x.new", 1)
    with pytest.raises(update.UpdateError):
        update.install_script(r"C:\x.exe", r"C:\x.new", 0)


def test_game_command_maps_starter_options(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Games\U-Jagd-Windows.exe")
    assert app.game_command({"port": 8765}, "s.json") == [
        r"C:\Games\U-Jagd-Windows.exe", "--game", "--remote-crew",
        "--web-port", "8765", "--status-file", "s.json"]
    assert app.game_command({"solo": True, "play_sub": True, "windowed": True,
                             "no_audio": True, "port": 9000}, "s.json")[2:] == [
        "--solo-crew", "--play-sub", "--windowed", "--no-audio",
        "--web-port", "9000", "--status-file", "s.json"]
    with pytest.raises(ValueError):
        app.game_command({"port": 80}, "s.json")
    monkeypatch.setattr(sys, "frozen", False)
    command = app.game_command({}, "s.json")
    assert command[1].endswith("main.py") and command[2] == "--remote-crew"


def test_read_status_tolerates_missing_and_broken_files(tmp_path):
    path = tmp_path / "status.json"
    assert app.read_status(str(path)) is None
    path.write_text("{", encoding="utf-8")
    assert app.read_status(str(path)) is None
    path.write_text("[]", encoding="utf-8")
    assert app.read_status(str(path)) is None
    path.write_text('{"state": "running"}', encoding="utf-8")
    assert app.read_status(str(path)) == {"state": "running"}


def test_console_publishes_status_only_on_change(tmp_path):
    from src.commander.local import CommanderConsole

    console = CommanderConsole()
    console.publish_status()  # no path: nothing happens
    path = tmp_path / "status.json"
    console.status_path = str(path)
    console.publish_status()
    assert json.loads(path.read_text()) == {"state": "stopped", "url": None,
                                            "code": None, "solo": False}
    path.unlink()
    console.publish_status()
    assert not path.exists()  # unchanged status is not rewritten
    console.address, console.pairing_code = ("192.168.1.20", 8765), "123ABC"
    console.publish_status()
    assert json.loads(path.read_text()) == {
        "state": "running", "url": "http://192.168.1.20:8765/", "code": "123ABC",
        "solo": False}
    console.address, console.error = None, "commander.local.error.start"
    console.publish_status()
    assert json.loads(path.read_text())["state"] == "error"
    assert not (tmp_path / "status.json.tmp").exists()


def test_prepare_uses_the_routed_private_address_without_linux_ioctls(monkeypatch):
    import ipaddress

    from src.commander.local import CommanderConsole

    monkeypatch.setitem(sys.modules, "fcntl", None)  # as on Windows
    monkeypatch.setattr(CommanderConsole, "_route_address",
                        staticmethod(lambda: ipaddress.IPv4Address("192.168.1.20")))
    console = CommanderConsole()
    console.prepare()
    assert console.hosts == ("127.0.0.1", "192.168.1.20")
    monkeypatch.setattr(CommanderConsole, "_route_address",
                        staticmethod(lambda: ipaddress.IPv4Address("203.0.113.5")))
    public = CommanderConsole()
    public.prepare()
    assert public.hosts == ("127.0.0.1",)  # never a public address
    monkeypatch.setattr(CommanderConsole, "_route_address", staticmethod(lambda: None))
    offline = CommanderConsole()
    offline.prepare()
    assert offline.hosts == ("127.0.0.1",)


def test_remote_crew_flag_autostarts_crew_mode_with_status_file(monkeypatch, tmp_path):
    import main as entry

    calls = []

    class FakeConsole:
        port = 8765
        status_path = None

        def autostart(self):
            calls.append(("crew", self.port, self.status_path))

        def autostart_solo(self):
            calls.append(("solo", self.port, self.status_path))

    class FakeGame:
        def __init__(self, **_kwargs):
            self.commander = FakeConsole()

        def run(self):
            calls.append("run")

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "P", (), {"fullscreen": False, "audio": False})())
    status = str(tmp_path / "s.json")
    assert entry.main(["--remote-crew", "--web-port", "9000",
                       "--status-file", status, "5"]) == 0
    assert calls == [("crew", 9000, status), "run"]
    calls.clear()
    assert entry.main(["--solo-crew", "5"]) == 0
    assert calls == [("solo", 8765, None), "run"]
    for bad in (["--remote-crew", "--solo-crew"], ["--remote-crew", "--web-port", "80"],
                ["--remote-crew", "--web-host", "--public-origin", "https://a.test"]):
        with pytest.raises(SystemExit):
            entry.main(bad)


def test_frozen_self_test_runs_a_mission_and_serves_remote_crew(tmp_path):
    from src.launcher import entry

    report = tmp_path / "report.json"
    assert entry.self_test(str(report)) == 0, report.read_text()
    result = json.loads(report.read_text())
    assert result["ok"] and result["/"] == 200 and result["/manual-en"] == 200
    assert result["sim_t"] > 0 and result["code"] is True


def test_launcher_prose_is_in_both_catalogs():
    from src.core.i18n import load_catalog

    source = (app.__file__, update.__file__)
    keys = set()
    import re
    for path in source:
        with open(path, encoding="utf-8") as handle:
            keys.update(re.findall(r'"(launcher\.[a-z_.]+)"', handle.read()))
    en, de = load_catalog("en"), load_catalog("de")
    assert keys and keys <= set(en) and keys <= set(de)


def test_update_restart_drops_the_old_extraction_directory():
    env = update.clean_environment({
        "PATH": r"C:\Windows", "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI123",
        "_PYI_ARCHIVE_FILE": r"C:\Games\U-Jagd-Windows.exe",
        "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": r"C:\Temp\_MEI123"})
    assert env == {"PATH": r"C:\Windows", "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def test_starter_links_the_support_page():
    from src.ui.support import SUPPORT_URL

    source = open(app.__file__, encoding="utf-8").read()
    assert "launcher.support" in source and "SUPPORT_URL" in source
    assert SUPPORT_URL.startswith("https://buymeacoffee.com/")


def test_release_pruning_keeps_the_current_and_newer_releases():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / "prune_releases.py"
    spec = importlib.util.spec_from_file_location("prune_releases", path)
    prune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prune)
    tags = ["v1.3.41\n", "v1.3.40\n", "v1.3.9\n", "v1.3.39\n", "latest\n", "v1.3.40-rc1\n"]
    assert prune.older_tags("1.3.40", tags) == ["v1.3.9", "v1.3.39"]
    assert prune.older_tags("1.3.11", ["v1.3.11"]) == []
    with pytest.raises(ValueError):
        prune.older_tags("1.3", tags)
