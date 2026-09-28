"""Self-updating uConsole launcher: runs against throwaway local git repos."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import os
import stat
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
UPDATER = ROOT / "packaging/uconsole/u_jagd_updater.py"
LAUNCH = ROOT / "packaging/uconsole/u-jagd-launch"
INSTALL = ROOT / "packaging/uconsole/install.sh"


def load_updater():
    loader = SourceFileLoader("u_jagd_updater_test", str(UPDATER))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit_version(work, version, extra=None):
    (work / "src/core").mkdir(parents=True, exist_ok=True)
    (work / "src/core/version.py").write_text(f'APP_VERSION = "{version}"\n')
    (work / "requirements.txt").write_text(extra or "pygame\n")
    run(work, "git", "add", "-A")
    run(work, "git", "commit", "-qm", version)
    return run(work, "git", "rev-parse", "HEAD")


@pytest.fixture
def repos(tmp_path, monkeypatch):
    """(upstream work tree, installed clone) sharing a bare origin."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("U_JAGD_NO_UPDATE", raising=False)
    monkeypatch.delenv("U_JAGD_UPDATE_CHANNEL", raising=False)
    bare = tmp_path / "origin.git"
    run(tmp_path, "git", "init", "-q", "--bare", "-b", "main", str(bare))
    work = tmp_path / "work"
    run(tmp_path, "git", "clone", "-q", str(bare), str(work))
    run(work, "git", "checkout", "-qb", "main")
    commit_version(work, "1.3.8")
    run(work, "git", "push", "-q", "origin", "main")
    app = tmp_path / "app"
    run(tmp_path, "git", "clone", "-q", "-b", "main", str(bare), str(app))
    return work, app


def publish(work, version, extra=None, tag=True):
    head = commit_version(work, version, extra)
    run(work, "git", "push", "-q", "origin", "main")
    if tag:
        run(work, "git", "tag", f"v{version}")
        run(work, "git", "push", "-q", "origin", f"v{version}")
    return head


@pytest.fixture
def updater(monkeypatch):
    module = load_updater()
    calls = {"install": [], "verify": "1.3.9"}
    monkeypatch.setattr(module, "ensure_venv",
                        lambda app, force_install=False: calls["install"].append(force_install))
    monkeypatch.setattr(module, "verify", lambda app: calls["verify"])
    monkeypatch.setattr(module, "notify", lambda message: None)
    module.calls = calls
    return module


def head(app):
    return run(app, "git", "rev-parse", "HEAD")


def test_newer_release_fast_forwards_and_keeps_branch(repos, updater, monkeypatch):
    work, app = repos
    target = publish(work, "1.3.9")
    publish(work, "1.3.10", tag=False)  # unreleased main commit is not taken
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "v1.3.9")
    assert updater.update(app) is True
    assert head(app) == target
    assert run(app, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert updater.calls["install"] == [False]
    assert updater.installed_version(app) == (1, 3, 9)


def test_dependency_change_reinstalls(repos, updater, monkeypatch):
    work, app = repos
    publish(work, "1.3.9", extra="pygame\nnumpy\n")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "v1.3.9")
    assert updater.update(app) is True
    assert updater.calls["install"] == [True]


@pytest.mark.parametrize("answer", [None, "v1.3.8", "v1.3.7"])
def test_offline_or_not_newer_starts_installed_version(repos, updater, monkeypatch, answer):
    work, app = repos
    before = head(app)
    publish(work, "1.3.9")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: answer)
    assert updater.update(app) is False
    assert head(app) == before


def test_without_release_follows_main(repos, updater, monkeypatch):
    work, app = repos
    target = publish(work, "1.3.9", tag=False)
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "")
    assert updater.update(app) is True
    assert head(app) == target


def test_local_changes_and_other_branches_are_never_touched(repos, updater, monkeypatch):
    work, app = repos
    before = head(app)
    publish(work, "1.3.9")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "v1.3.9")
    (app / "requirements.txt").write_text("edited\n")
    assert updater.update(app) is False
    assert head(app) == before
    assert (app / "requirements.txt").read_text() == "edited\n"
    run(app, "git", "checkout", "-q", "--", "requirements.txt")
    run(app, "git", "checkout", "-qb", "feature")
    assert updater.update(app) is False
    assert head(app) == before


def test_broken_update_rolls_back(repos, updater, monkeypatch):
    work, app = repos
    before = head(app)
    publish(work, "1.3.9")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "v1.3.9")
    updater.calls["verify"] = None
    assert updater.update(app) is False
    assert head(app) == before
    assert updater.installed_version(app) == (1, 3, 8)
    log = (Path(os.environ["HOME"]) / ".u-jagd/updater.log").read_text()
    assert "rolling back" in log
    updater.calls["verify"] = "1.3.9"
    assert updater.update(app) is False  # the failed commit is not retried
    target = publish(work, "1.3.10")
    monkeypatch.setattr(updater, "fetch_latest_release", lambda url=None: "v1.3.10")
    assert updater.update(app) is True
    assert head(app) == target


def test_no_update_env_skips(repos, updater, monkeypatch):
    work, app = repos
    publish(work, "1.3.9")
    monkeypatch.setenv("U_JAGD_NO_UPDATE", "1")
    monkeypatch.setattr(updater, "fetch_latest_release",
                        lambda url=None: pytest.fail("no network while disabled"))
    assert updater.update(app) is False


def test_tag_and_version_parsing():
    module = load_updater()
    assert module.parse_tag("v1.3.10") == (1, 3, 10)
    assert module.parse_tag("v1.3.10") > module.parse_tag("v1.3.9")
    for bad in ("1.3.9", "v1.3", "v1.3.9-rc1", None, 7):
        assert module.parse_tag(bad) is None
    assert module.parse_version('X = 1\nAPP_VERSION = "1.3.8"\n') == (1, 3, 8)


def test_running_game_blocks_background_update(tmp_path, monkeypatch):
    module = load_updater()
    monkeypatch.setenv("HOME", str(tmp_path))
    held = module.GameLock()
    assert held.try_acquire()
    monkeypatch.setattr(module, "update", lambda app=None: pytest.fail("updated under game"))
    assert module.background_update() == 0
    os.close(held.fd)


def test_setup_and_uninstall_desktop_integration(tmp_path, monkeypatch):
    module = load_updater()
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(module, "ensure_venv", lambda app, force_install=False: None)
    monkeypatch.setattr(module, "systemctl", lambda *args: True)
    monkeypatch.setattr(module, "desktop_dir", lambda: home / "Desktop")
    assert module.setup(ROOT) == 0
    entry = (home / ".local/share/applications/u-jagd.desktop").read_text()
    assert f'Exec="{LAUNCH}"' in entry and "Categories=Game;" in entry
    assert (home / "Desktop/u-jagd.desktop").stat().st_mode & stat.S_IXUSR
    assert (home / ".local/bin/u-jagd").resolve() == LAUNCH
    timer = (home / ".config/systemd/user/u-jagd-update.timer").read_text()
    assert "OnUnitActiveSec=6h" in timer
    service = (home / ".config/systemd/user/u-jagd-update.service").read_text()
    assert f'"{UPDATER}" update' in service
    assert module.uninstall() == 0
    assert not (home / ".local/bin/u-jagd").is_symlink()
    assert not (home / ".local/share/applications/u-jagd.desktop").exists()
    assert not (home / "Desktop/u-jagd.desktop").exists()


def test_scripts_are_executable_posix_shell():
    for script in (LAUNCH, INSTALL, UPDATER):
        assert script.stat().st_mode & stat.S_IXUSR, script
    for script in (LAUNCH, INSTALL):
        subprocess.run(["sh", "-n", str(script)], check=True)
    assert "releases/latest" in UPDATER.read_text()


@pytest.mark.skipif(os.geteuid() == 0, reason="the installer refuses to run as root")
def test_installer_updates_checkout_that_predates_it(repos, tmp_path):
    """An old ~/games/u-jagd without the updater is fast-forwarded first."""
    work, app = repos
    stub = work / "packaging/uconsole/u_jagd_updater.py"
    stub.parent.mkdir(parents=True)
    stub.write_text("import sys\nprint('stub', *sys.argv[1:])\n")
    run(work, "git", "add", "-A")
    run(work, "git", "commit", "-qm", "installer")
    run(work, "git", "push", "-q", "origin", "main")
    result = subprocess.run(["sh", str(INSTALL)], capture_output=True, text=True,
                            env={**os.environ, "U_JAGD_DIR": str(app)}, check=True)
    assert "stub update" in result.stdout and "stub setup" in result.stdout
    assert (app / "packaging/uconsole/u_jagd_updater.py").exists()
