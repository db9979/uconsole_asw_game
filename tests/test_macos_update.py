"""macOS app: release asset per processor, safe unpacking of the zipped
bundle, the swap script, and "Update now" in the frozen app (no network)."""

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import zipfile

import pygame
import pytest

from src.core import game_update
from src.core.game import Game
from src.launcher import entry, update

ROOT = Path(__file__).resolve().parents[1]
ZIP_URL = ("https://github.com/db9979/uconsole_asw_game/releases/download/"
           "v9.9.9/U-Jagd-macOS-arm64.zip")

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX shell and links")


def _bundle_dir(tmp_path, name="U-Jagd.app", marker=b"old"):
    app = tmp_path / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(b"<plist/>")
    exe = app / "Contents" / "MacOS" / "U-Jagd"
    exe.write_bytes(marker)
    exe.chmod(0o755)
    return app, exe


def _add(zipped, name, data=b"", mode=0o644, kind=stat.S_IFREG):
    info = zipfile.ZipInfo(name)
    info.create_system = 3  # Unix, as ditto writes it
    info.external_attr = (kind | mode) << 16
    if kind == stat.S_IFDIR:
        info.external_attr |= 0x10
    zipped.writestr(info, data)


def _release_zip(path, extra=(), executable=True):
    with zipfile.ZipFile(path, "w") as zipped:
        _add(zipped, "U-Jagd.app/", kind=stat.S_IFDIR, mode=0o755)
        _add(zipped, "U-Jagd.app/Contents/", kind=stat.S_IFDIR, mode=0o755)
        _add(zipped, "U-Jagd.app/Contents/Info.plist", b"<plist>new</plist>")
        if executable:
            _add(zipped, "U-Jagd.app/Contents/MacOS/U-Jagd", b"new", mode=0o4777)
        _add(zipped, "U-Jagd.app/Contents/Resources/data/x.json", b"{}", mode=0o666)
        _add(zipped, "U-Jagd.app/Contents/Frameworks/data", b"../Resources/data",
             mode=0o755, kind=stat.S_IFLNK)
        _add(zipped, "__MACOSX/U-Jagd.app/._Info.plist", b"meta")
        for name, data, mode, kind in extra:
            _add(zipped, name, data, mode, kind)
    return path


def test_each_processor_has_its_own_release_zip():
    assert update.mac_asset_name("arm64") == "U-Jagd-macOS-arm64.zip"
    assert update.mac_asset_name("x86_64") is None  # no Intel build
    assert update.mac_asset_name("ppc") is None
    payload = {"tag_name": "v9.9.9", "draft": False, "prerelease": False,
               "assets": [{"name": update.ASSET_NAME, "size": 4,
                           "browser_download_url": ZIP_URL.replace(".zip", ".exe")},
                          {"name": "U-Jagd-macOS-arm64.zip", "size": 9,
                           "browser_download_url": ZIP_URL}]}
    release = update.select_release(payload, "1.3.9", "U-Jagd-macOS-arm64.zip")
    assert release.url == ZIP_URL and release.size == 9
    assert update.select_release(payload, "1.3.9", "U-Jagd-macOS-x86_64.zip") is None
    # The Windows program still finds only its own file.
    assert update.select_release(payload, "1.3.9").size == 4


def test_check_latest_asks_for_the_mac_asset():
    payload = {"tag_name": "v9.9.9", "draft": False, "prerelease": False,
               "assets": [{"name": "U-Jagd-macOS-x86_64.zip", "size": 9,
                           "browser_download_url": ZIP_URL}]}

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    def opener(request, timeout):
        return _Response(json.dumps(payload).encode())

    assert update.check_latest("1.3.9", opener=opener,
                               asset_name="U-Jagd-macOS-x86_64.zip").size == 9
    assert update.check_latest("1.3.9", opener=opener) is None


@posix_only
def test_bundle_is_found_from_the_executable_only_where_it_can_be_replaced(tmp_path):
    app, exe = _bundle_dir(tmp_path)
    bundle = update.mac_bundle(str(exe))
    assert bundle == update.MacBundle(str(app))
    assert bundle.archive == f"{app}.update.zip" and bundle.old == f"{app}.old"
    assert bundle.staged_app == os.path.join(f"{app}.update", "U-Jagd.app")
    assert update.mac_bundle(str(tmp_path / "U-Jagd")) is None
    assert update.mac_bundle(str(tmp_path / "x" / "Contents" / "MacOS" / "U-Jagd")) is None
    assert update.mac_bundle("/private/var/folders/x/AppTranslocation/1/d/U-Jagd.app/"
                             "Contents/MacOS/U-Jagd") is None
    assert update.mac_bundle("") is None and update.mac_bundle(None) is None
    if os.geteuid() != 0:  # root may write anywhere
        tmp_path.chmod(0o555)
        try:
            assert update.mac_bundle(str(exe)) is None
        finally:
            tmp_path.chmod(0o755)


@posix_only
def test_unpack_keeps_links_and_executable_bits_and_drops_metadata(tmp_path):
    app, _exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    archive = _release_zip(tmp_path / "release.zip")
    staged = Path(update.unpack_app(str(archive), bundle))
    assert staged == Path(bundle.staged_app)
    executable = staged / "Contents" / "MacOS" / "U-Jagd"
    assert executable.read_bytes() == b"new"
    assert stat.S_IMODE(executable.stat().st_mode) == 0o755  # setuid dropped
    data = staged / "Contents" / "Resources" / "data" / "x.json"
    assert stat.S_IMODE(data.stat().st_mode) == 0o644
    link = staged / "Contents" / "Frameworks" / "data"
    assert link.is_symlink() and os.readlink(link) == "../Resources/data"
    assert (link / "x.json").read_bytes() == b"{}"
    assert not (Path(bundle.staging) / "__MACOSX").exists()
    assert not Path(f"{bundle.staging}.part").exists()
    # The running bundle is untouched until the swap.
    assert (app / "Contents" / "MacOS" / "U-Jagd").read_bytes() == b"old"


@posix_only
@pytest.mark.parametrize("extra", [
    [("U-Jagd.app/../evil", b"x", 0o644, stat.S_IFREG)],
    [("/etc/evil", b"x", 0o644, stat.S_IFREG)],
    [("Other.app/Contents/x", b"x", 0o644, stat.S_IFREG)],
    [("U-Jagd.app/Contents/out", b"../../..", 0o755, stat.S_IFLNK)],
    [("U-Jagd.app/Contents/abs", b"/Applications", 0o755, stat.S_IFLNK)],
    [("U-Jagd.app/Contents/Info.plist", b"again", 0o644, stat.S_IFREG)],
    [("U-Jagd.app/up", b"..", 0o755, stat.S_IFLNK)],
    [("U-Jagd.app/Contents/fifo", b"", 0o644, stat.S_IFIFO)],
])
def test_hostile_zips_are_refused_and_leave_nothing(tmp_path, extra):
    app, _exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    archive = _release_zip(tmp_path / "release.zip", extra)
    with pytest.raises(update.UpdateError):
        update.unpack_app(str(archive), bundle)
    assert not Path(bundle.staging).exists()
    assert not Path(f"{bundle.staging}.part").exists()
    assert not (tmp_path / "evil").exists()


@posix_only
def test_a_zip_without_the_app_or_not_a_zip_is_refused(tmp_path):
    app, _exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    with pytest.raises(update.UpdateError):
        update.unpack_app(str(_release_zip(tmp_path / "r.zip", executable=False)), bundle)
    (tmp_path / "junk.zip").write_bytes(b"not a zip")
    with pytest.raises(update.UpdateError):
        update.unpack_app(str(tmp_path / "junk.zip"), bundle)
    assert not Path(bundle.staging).exists()


def _fake_open(tmp_path):
    """An ``open`` on PATH that records how the bundle was opened."""
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "open-calls.txt"
    tool = tools / "open"
    tool.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{calls}"\n')
    tool.chmod(0o755)
    return tools, calls


def _finished_pid():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def _run_script(tmp_path, bundle, args=(), log=None):
    tools, calls = _fake_open(tmp_path)
    script = tmp_path / "update.sh"
    script.write_text(update.mac_install_script(bundle, _finished_pid(), args, log))
    env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ.get('PATH', '')}"}
    subprocess.run(["/bin/sh", str(script)], env=env, check=False, timeout=60)
    assert not script.exists()  # the script deletes itself
    return calls.read_text().splitlines() if calls.exists() else []


@posix_only
def test_the_swap_script_replaces_the_bundle_and_opens_the_new_one(tmp_path):
    games = tmp_path / "Applications"
    games.mkdir()
    home = tmp_path / "home" / ".u-jagd"
    home.mkdir(parents=True)
    (home / "slot1.json").write_text("{}")
    app, _exe = _bundle_dir(games, "U-Jagd 2.app")  # a renamed bundle keeps its name
    bundle = update.MacBundle(str(app))
    update.unpack_app(str(_release_zip(games / "U-Jagd 2.app.update.zip")), bundle)
    calls = _run_script(tmp_path, bundle, ("--self-test", "/tmp/r p.json"))
    assert (app / "Contents" / "MacOS" / "U-Jagd").read_bytes() == b"new"
    assert sorted(p.name for p in games.iterdir()) == ["U-Jagd 2.app"]
    assert calls == ["-n", str(app), "--args", "--self-test", "/tmp/r p.json"]
    assert (home / "slot1.json").read_text() == "{}"  # user data untouched


@posix_only
def test_a_failed_swap_keeps_and_reopens_the_old_bundle(tmp_path):
    app, _exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    log = tmp_path / "updater.log"
    calls = _run_script(tmp_path, bundle, log=str(log))  # nothing staged
    assert (app / "Contents" / "MacOS" / "U-Jagd").read_bytes() == b"old"
    assert not Path(bundle.old).exists()
    assert "update failed" in log.read_text()
    assert calls == ["-n", str(app)]


def test_the_swap_script_waits_for_the_game_and_quotes_paths(tmp_path):
    bundle = update.MacBundle("/Applications/U-Jagd $(rm -rf ~).app")
    script = update.mac_install_script(bundle, 4242, ("--a b",))
    assert "while kill -0 4242 2>/dev/null; do" in script
    assert f'if [ "$tries" -ge {update.INSTALL_TRIES} ]; then' in script
    assert "app='/Applications/U-Jagd $(rm -rf ~).app'" in script
    assert 'open -n "$app" --args \'--a b\'' in script
    # The old bundle is removed only after the new one is in place.
    assert script.index('mv "$app" "$old"') < script.index('mv "$staged" "$app"')
    assert script.index('mv "$staged" "$app"') < script.index('rm -rf "$old" "$staging"')
    assert ".u-jagd" not in script
    for bad in ((bundle, 0, ()), (bundle, 1, ("a\nb",)),
                (update.MacBundle("/A\n.app"), 1, ())):
        with pytest.raises(update.UpdateError):
            update.mac_install_script(*bad)


def test_launch_mac_install_starts_the_script_detached(monkeypatch, tmp_path):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "gone")
    calls = []
    bundle = update.MacBundle("/Applications/U-Jagd.app")
    script = update.launch_mac_install(bundle, popen=lambda cmd, **kw: calls.append((cmd, kw)),
                                       pid=77)
    assert calls[0][0] == ["/bin/sh", script] and script.endswith("u-jagd-update-77.sh")
    assert calls[0][1]["start_new_session"] is True
    assert "_PYI_APPLICATION_HOME_DIR" not in calls[0][1]["env"]
    assert "kill -0 77" in open(script, encoding="utf-8").read()

    def broken(*_args, **_kwargs):
        raise OSError("no sh")

    with pytest.raises(update.UpdateError):
        update.launch_mac_install(bundle, popen=broken, pid=77)


@posix_only
def test_leftovers_of_a_failed_update_are_removed(tmp_path):
    tmp_path = tmp_path / "Applications"
    tmp_path.mkdir()
    app, _exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    Path(bundle.archive).write_bytes(b"zip")
    Path(f"{bundle.archive}.part").write_bytes(b"zi")
    Path(bundle.staged_app).mkdir(parents=True)
    Path(bundle.old).mkdir()
    update.remove_mac_leftovers(bundle)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["U-Jagd.app"]


# --- the frozen app ---------------------------------------------------------


def _frozen_mac(monkeypatch, exe):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(update.platform, "machine", lambda: "arm64")


@posix_only
def test_frozen_mac_app_updates_itself_else_opens_the_page(monkeypatch, tmp_path):
    _app, exe = _bundle_dir(tmp_path)
    _frozen_mac(monkeypatch, exe)
    assert game_update.default_update_mode() == "macos"
    monkeypatch.setattr(update.platform, "machine", lambda: "ppc")
    assert game_update.default_update_mode() == "browser"
    monkeypatch.setattr(sys, "executable", str(tmp_path / "U-Jagd"))
    assert game_update.default_update_mode() == "browser"
    monkeypatch.setattr(sys, "platform", "win32")
    assert game_update.default_update_mode() == "windows"


def _notice():
    return update.Notice("9.9.9", update.RELEASES_PAGE, {"en": "Adds a lighthouse."}, None)


@posix_only
def test_macos_downloads_unpacks_in_the_game_then_swaps_and_quits(monkeypatch, tmp_path):
    app, exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    Path(bundle.old).mkdir()  # left by an earlier failed swap
    body = _release_zip(tmp_path / "release.zip").read_bytes()
    release = update.Release("9.9.9", ZIP_URL, len(body), hashlib.sha256(body).hexdigest(),
                             update.RELEASES_PAGE)
    asked, installs = [], []

    def check_latest(current, asset_name=update.ASSET_NAME):
        asked.append(asset_name)
        return release

    def download(rel, target, progress=None):
        Path(target).write_bytes(body)
        progress(len(body), len(body))

    monkeypatch.setattr(update, "check_latest", check_latest)
    monkeypatch.setattr(update, "download", download)
    monkeypatch.setattr(update, "launch_mac_install",
                        lambda found, log=None: installs.append((found, log)))
    monkeypatch.setattr(update, "launch_install",
                        lambda *a, **k: pytest.fail("not the Windows swap"))
    monkeypatch.delenv("U_JAGD_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)
    monkeypatch.setattr(update, "fetch_notice", lambda current: None)
    game = Game(seed=7, start_menu=True, audio_enabled=False, show_splash=True)
    _frozen_mac(monkeypatch, exe)
    game.start_update_check("macos")
    assert not Path(bundle.old).exists()  # stale swap removed
    game._update_thread.join(5)
    game.update_notice = _notice()
    game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=0))
    for _ in range(250):
        if game._update_ready is not None or game.update_failed:
            break
        time.sleep(0.02)
    assert asked == ["U-Jagd-macOS-arm64.zip"] and game.update_progress == 100
    assert (Path(bundle.staged_app) / "Contents" / "MacOS" / "U-Jagd").read_bytes() == b"new"
    game.update_tick()
    assert installs and installs[0][0] == bundle and not game.running
    assert installs[0][1].endswith(os.path.join(".u-jagd", "updater.log"))


@posix_only
def test_macos_failed_unpack_is_reported_and_cleaned(monkeypatch, tmp_path):
    tmp_path = tmp_path / "Applications"
    tmp_path.mkdir()
    app, exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    release = update.Release("9.9.9", ZIP_URL, 3, None, update.RELEASES_PAGE)
    monkeypatch.setattr(update, "check_latest", lambda current, asset_name=None: release)
    monkeypatch.setattr(update, "download",
                        lambda rel, target, progress=None: Path(target).write_bytes(b"bad"))
    game = Game(seed=7, start_menu=True, audio_enabled=False, show_splash=False)
    _frozen_mac(monkeypatch, exe)
    game.update_notice = _notice()
    game.update_mode = "macos"
    game.request_update()
    for _ in range(250):
        if game.update_failed:
            break
        time.sleep(0.02)
    assert game.update_failed and game.update_progress is None and game.running
    assert sorted(p.name for p in tmp_path.iterdir()) == ["U-Jagd.app"]


@posix_only
def test_the_update_exit_code_swaps_the_mac_bundle(monkeypatch, tmp_path):
    app, exe = _bundle_dir(tmp_path)
    bundle = update.MacBundle(str(app))
    body = _release_zip(tmp_path / "release.zip").read_bytes()
    release = update.Release("9.9.9", ZIP_URL, len(body), None, update.RELEASES_PAGE)
    steps = []
    monkeypatch.setattr(update, "check_latest",
                        lambda current, asset_name=None: steps.append(asset_name) or release)
    monkeypatch.setattr(update, "download",
                        lambda rel, target, **_kw: Path(target).write_bytes(body))
    monkeypatch.setattr(update, "launch_mac_install",
                        lambda found, args=(), log=None: steps.append(("install", found)))
    import main as game_main

    monkeypatch.setattr(game_main, "main", lambda argv: update.UPDATE_EXIT_CODE)
    _frozen_mac(monkeypatch, exe)
    assert entry.main([]) == 0
    assert steps == ["U-Jagd-macOS-arm64.zip", ("install", bundle)]
    assert Path(bundle.staged_app).is_dir()


def test_workflow_builds_the_apple_silicon_zip_and_publishes_from_one_job():
    workflow = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    jobs = workflow.split("\njobs:\n", 1)[1]
    mac = jobs.split("\n  macos:\n", 1)[1].split("\n  publish:\n", 1)[0]
    assert "arch: arm64" in mac and "x86_64" not in mac
    assert "pyinstaller --noconfirm packaging/macos/u-jagd-macos.spec" in mac
    assert 'ditto -c -k --norsrc --noextattr --keepParent dist/U-Jagd.app "dist/$ZIP"' in mac
    assert "ZIP: U-Jagd-macOS-${{ matrix.arch }}.zip" in mac
    assert "--update-self-test" in mac and "update.unpack_app" in mac
    publish = jobs.split("\n  publish:\n", 1)[1]
    assert "needs: [build, macos]" in publish
    assert "gh release create" in publish and "gh release create" not in jobs.split(
        "\n  publish:\n", 1)[0]
    for name in (update.ASSET_NAME, *update.MAC_ASSETS.values()):
        assert name in publish
    # Older releases go only after this one is published.
    assert publish.index("gh release upload") < publish.index("gh release delete")


def test_mac_spec_names_match_the_updater():
    spec = (ROOT / "packaging" / "macos" / "u-jagd-macos.spec").read_text(encoding="utf-8")
    assert f'name="{update.MAC_APP_NAME}"' in spec
    assert f'name="{update.MAC_EXECUTABLE}"' in spec
    assert 'bundle_identifier="de.ujagd.game"' in spec and "console=False" in spec


def test_remote_crew_finds_the_lan_address_on_a_mac(monkeypatch):
    """macOS has fcntl but not Linux's SIOCGIFADDR: ask the routing table."""
    import ipaddress

    from src.commander import local
    from src.commander.local import CommanderConsole

    monkeypatch.setattr(local.sys, "platform", "darwin")
    monkeypatch.setattr(local.socket, "if_nameindex",
                        lambda: pytest.fail("no Linux ioctls on macOS"))
    monkeypatch.setattr(CommanderConsole, "_route_address",
                        staticmethod(lambda: ipaddress.IPv4Address("192.168.1.20")))
    console = CommanderConsole()
    console.prepare()
    assert console.hosts == ("127.0.0.1", "192.168.1.20")
