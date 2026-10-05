"""Windows program: update rules, straight start into the game, exit codes."""

import hashlib
import io
import json
import sys
import urllib.error

import pytest

from src.launcher import entry, update

ASSET_URL = ("https://github.com/db9979/uconsole_asw_game/releases/download/"
             "v9.9.9/U-Jagd-Windows.exe")


def _payload(tag="v9.9.9", **asset):
    entry = {"name": update.ASSET_NAME, "browser_download_url": ASSET_URL, "size": 4,
             "digest": "sha256:" + "a" * 64}
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
                    {"digest": "md5:abc"}, {"digest": "sha256:XYZ"},
                    {"digest": None}):
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


def test_install_script_retries_the_swap_with_a_real_pause():
    script = update.install_script(r"C:\Games\U-Jagd-Windows.exe",
                                   r"C:\Games\U-Jagd-Windows.exe.new",
                                   ("--self-test", r"C:\Temp\r.json"), log=r"C:\Logs\u.log")
    lines = script.split("\r\n")
    assert r'move /Y "C:\Games\U-Jagd-Windows.exe.new" "C:\Games\U-Jagd-Windows.exe" >NUL 2>NUL' in lines
    # "timeout" returns at once with redirected stdin; the pause must be ping.
    assert "timeout" not in script and "ping -n 2 127.0.0.1 >NUL" in lines
    assert f"if %tries% GEQ {update.INSTALL_TRIES} goto failed" in lines
    assert lines.index(":failed") < lines.index(":start")
    assert any(line.startswith("echo update failed") and r"C:\Logs\u.log" in line
               for line in lines)
    assert r'start "" "C:\Games\U-Jagd-Windows.exe" "--self-test" "C:\Temp\r.json"' in lines
    assert script.endswith("\r\n")
    for bad in (r'C:\a"b.exe', r"C:\%PATH%.exe", "C:\\a\nb.exe", r"C:\a!b.exe", ""):
        with pytest.raises(update.UpdateError):
            update.install_script(bad, r"C:\x.new")


def test_launch_install_starts_the_script_with_a_clean_environment(monkeypatch, tmp_path):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "gone")
    calls = []
    script = update.launch_install(r"C:\Games\U.exe", r"C:\Games\U.exe.new",
                                   popen=lambda cmd, **kw: calls.append((cmd, kw)))
    assert calls[0][0] == ["cmd", "/c", script]
    env = calls[0][1]["env"]
    assert "_PYI_APPLICATION_HOME_DIR" not in env and env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "move /Y" in open(script, encoding="utf-8").read()


def _fake_game_main(monkeypatch, code):
    import main as game_main

    calls = []

    def fake(argv):
        calls.append(list(argv))
        return code

    monkeypatch.setattr(game_main, "main", fake)
    return calls


def test_the_program_starts_straight_into_the_game(monkeypatch):
    calls = _fake_game_main(monkeypatch, 0)
    assert entry.main([]) == 0
    assert entry.main(["--windowed", "--multiplayer", "7"]) == 0
    # The old starter's "--game" prefix is accepted and dropped.
    assert entry.main(["--game", "--no-audio"]) == 0
    assert calls == [[], ["--windowed", "--multiplayer", "7"], ["--no-audio"]]
    monkeypatch.setattr(sys, "argv", ["U-Jagd-Windows.exe", "--windowed"])
    assert entry.main() == 0 and calls[-1] == ["--windowed"]


def test_the_program_passes_the_game_exit_code_through(monkeypatch):
    calls = _fake_game_main(monkeypatch, 3)
    assert entry.main(["5"]) == 3 and calls == [["5"]]


def test_the_update_exit_code_installs_the_downloaded_program(monkeypatch, tmp_path):
    exe = tmp_path / "U-Jagd-Windows.exe"
    exe.write_bytes(b"old")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    installs = []
    monkeypatch.setattr(update, "launch_install",
                        lambda executable, downloaded, args=(), log=None:
                        installs.append((executable, downloaded, args, log)))
    monkeypatch.setattr(update, "check_latest",
                        lambda current: pytest.fail("already downloaded"))
    import main as game_main

    def game_downloads(argv):
        (tmp_path / "U-Jagd-Windows.exe.new").write_bytes(b"new")
        return update.UPDATE_EXIT_CODE

    monkeypatch.setattr(game_main, "main", game_downloads)
    assert entry.main([]) == 0
    assert installs == [(str(exe), f"{exe}.new", (), str(entry.log_path()))]
    # A failed install script keeps the code.

    def broken(*_args, **_kwargs):
        raise update.UpdateError("no temp dir")

    monkeypatch.setattr(update, "launch_install", broken)
    assert entry.main([]) == update.UPDATE_EXIT_CODE


def test_the_update_exit_code_fetches_the_release_first(monkeypatch, tmp_path):
    exe = tmp_path / "U-Jagd-Windows.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    release = update.Release("9.9.9", ASSET_URL, 4, "0" * 64, update.RELEASES_PAGE)
    steps = []
    monkeypatch.setattr(update, "check_latest", lambda current: steps.append("check") or release)
    monkeypatch.setattr(update, "download",
                        lambda found, target, **_kw: steps.append(("download", found, target)))
    monkeypatch.setattr(update, "launch_install",
                        lambda executable, downloaded, args=(), log=None:
                        steps.append(("install", downloaded)))
    _fake_game_main(monkeypatch, update.UPDATE_EXIT_CODE)
    assert entry.main([]) == 0
    assert steps == ["check", ("download", release, f"{exe}.new"),
                     ("install", f"{exe}.new")]
    # No newer release or offline: nothing is installed, the code stays.
    steps.clear()
    monkeypatch.setattr(update, "check_latest", lambda current: None)
    assert entry.main([]) == update.UPDATE_EXIT_CODE and steps == []

    def offline(current):
        raise update.UpdateError("offline")

    monkeypatch.setattr(update, "check_latest", offline)
    assert entry.main([]) == update.UPDATE_EXIT_CODE and steps == []


def test_from_source_the_update_exit_code_is_passed_through(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(update, "launch_install",
                        lambda *a, **k: pytest.fail("only the frozen program replaces itself"))
    _fake_game_main(monkeypatch, update.UPDATE_EXIT_CODE)
    assert entry.main([]) == update.UPDATE_EXIT_CODE


def test_the_windows_program_has_no_starter_window():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert not (root / "src" / "launcher" / "app.py").exists()
    source = (root / "src" / "launcher" / "entry.py").read_text(encoding="utf-8")
    assert "tkinter" not in source
    spec = (root / "packaging" / "windows" / "u-jagd-windows.spec").read_text(encoding="utf-8")
    assert '"tkinter"' in spec.split("excludes=", 1)[1].split("\n", 1)[0]
    from src.core.i18n import load_catalog

    for lang in ("en", "de"):
        assert not [key for key in load_catalog(lang) if key.startswith("launcher.")]


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


def test_game_main_checks_for_updates_and_returns_the_update_exit_code(monkeypatch):
    import main as entry

    calls = []

    class FakeConsole:
        port = 8765

        def autostart_solo(self):
            calls.append(("solo", self.port))

    class FakeGame:
        update_exit_code = 0

        def __init__(self, **_kwargs):
            self.commander = FakeConsole()

        def start_update_check(self, mode=None, args=()):
            calls.append(("update_check", mode, tuple(args)))

        def run(self):
            calls.append("run")
            self.update_exit_code = exit_code

    monkeypatch.setattr(entry, "Game", FakeGame)
    monkeypatch.setattr(entry, "load_preferences", lambda: type(
        "P", (), {"fullscreen": False, "audio": False})())
    exit_code = 0
    assert entry.main(["--solo-crew", "--web-port", "9000", "5"]) == 0
    assert calls == [("solo", 9000),
                     ("update_check", None, ("--solo-crew", "--web-port", "9000", "5")),
                     "run"]
    exit_code = update.UPDATE_EXIT_CODE
    assert entry.main(["5"]) == update.UPDATE_EXIT_CODE
def test_frozen_self_test_runs_a_mission_and_serves_remote_crew(tmp_path):
    from src.launcher import entry

    report = tmp_path / "report.json"
    assert entry.self_test(str(report)) == 0, report.read_text()
    result = json.loads(report.read_text())
    assert result["ok"] and result["/"] == 200 and result["/manual-en"] == 200
    assert result["sim_t"] > 0 and result["code"] is True


def test_update_restart_drops_the_old_extraction_directory():
    env = update.clean_environment({
        "PATH": r"C:\Windows", "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI123",
        "_PYI_ARCHIVE_FILE": r"C:\Games\U-Jagd-Windows.exe",
        "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": r"C:\Temp\_MEI123"})
    assert env == {"PATH": r"C:\Windows", "PYINSTALLER_RESET_ENVIRONMENT": "1"}


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


def test_release_pruning_prints_bare_tags(tmp_path):
    import subprocess
    from pathlib import Path

    tool = Path(__file__).resolve().parents[1] / "tools" / "prune_releases.py"
    out = subprocess.run([sys.executable, str(tool), "1.3.42"], input=b"v1.3.41\r\nv1.3.43\r\n",
                         capture_output=True, check=True).stdout
    assert out == b"v1.3.41\n"


def test_workflow_removes_older_releases_and_their_tags():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "windows.yml").read_text(encoding="utf-8")
    publish = workflow.split("\n  publish:\n", 1)[1]
    # A red main is never published: the job waits for this commit's tests.
    wait = publish.split("- name: Wait for the tests of this commit", 1)[1]
    assert "actions/workflows/tests.yml/runs?head_sha=$GITHUB_SHA" in wait
    assert '"completed success") exit 0' in wait
    assert publish.index("Wait for the tests") < publish.index("gh release create")
    step = workflow.split("- name: Remove older releases and tags", 1)[1]
    assert "releases?per_page=100" in step and 'gh release delete "$old"' in step
    assert "tags?per_page=100" in step
    assert 'git/refs/tags/$old' in step
    # Releases go first, so no release is left pointing at a deleted tag.
    assert step.index("gh release delete") < step.index("git/refs/tags/")


def test_tag_pruning_keeps_backup_tags():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "tools" / "prune_releases.py"
    spec = importlib.util.spec_from_file_location("prune_releases", path)
    prune = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prune)
    tags = ["pre-v1-rewrite-main", "pre-v1-rewrite-wip", "v1.3.72", "v1.3.73", "v1.3.74"]
    assert prune.older_tags("1.3.73", tags) == ["v1.3.72"]
