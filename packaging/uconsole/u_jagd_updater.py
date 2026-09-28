#!/usr/bin/env python3
"""Self-updating launcher for U-Jagd on the uConsole.

Runs with the system ``python3`` and only the standard library, so it keeps
working even when the game's virtual environment is broken.  Commands:

``launch [game args]``  update (best effort), then replace this process with
                        the game (``.venv/bin/python main.py``).
``update``              update only; used by the background systemd timer.
``setup``               create/refresh the venv, menu entry, ``~/.local/bin``
                        command and the background timer (the installer).
``uninstall``           remove that desktop integration again (keeps the game
                        directory and ``~/.u-jagd`` saves).

Update source: the newest GitHub release (tag ``vX.Y.Z``, the same source the
Windows starter uses).  Without any release the checkout follows ``origin/main``;
``U_JAGD_UPDATE_CHANNEL=main`` forces that.  Offline, a local modification, a
non-main branch or a running game skips the update and the installed version
starts.  A new version whose ``main.py --version`` fails is rolled back.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = "db9979/uconsole_asw_game"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', re.M)
DEP_FILES = ("pyproject.toml", "requirements.txt")
NET_TIMEOUT_S = 6
GIT_TIMEOUT_S = 180
PIP_TIMEOUT_S = 1200
VERIFY_TIMEOUT_S = 90
LOG_MAX_BYTES = 256 * 1024
APP_ID = "u-jagd"

APP_DIR = Path(__file__).resolve().parents[2]


def state_dir() -> Path:
    return Path.home() / ".u-jagd"


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + message
    print(line, file=sys.stderr)
    try:
        path = state_dir() / "updater.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def notify(message: str) -> None:
    """Desktop notification when available (the menu entry has no terminal)."""
    tool = shutil.which("notify-send")
    if tool and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            subprocess.run([tool, "-a", "U-Jagd", "U-Jagd", message],
                           timeout=5, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def git(app: Path, *args: str, timeout: float = GIT_TIMEOUT_S) -> str:
    result = subprocess.run(["git", "-C", str(app), *args], capture_output=True,
                            text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.search(text)
    return tuple(int(part) for part in match.groups()) if match else None


def parse_tag(tag: object) -> tuple[int, int, int] | None:
    match = TAG_RE.match(tag) if isinstance(tag, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def installed_version(app: Path) -> tuple[int, int, int] | None:
    try:
        return parse_version((app / "src/core/version.py").read_text(encoding="utf-8"))
    except OSError:
        return None


def fetch_latest_release(url: str = LATEST_RELEASE_URL) -> str | None:
    """Tag of the newest release, ``""`` when the repo has none, None offline."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "u-jagd-updater"})
    try:
        with urllib.request.urlopen(request, timeout=NET_TIMEOUT_S) as response:
            data = json.loads(response.read(64 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return "" if exc.code == 404 else None
    except (OSError, ValueError):
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    return tag if parse_tag(tag) else None


def venv_python(app: Path) -> Path:
    return app / ".venv" / "bin" / "python"


def ensure_venv(app: Path, force_install: bool = False) -> None:
    py = venv_python(app)
    if not py.exists():
        log("creating virtual environment")
        subprocess.run([sys.executable, "-m", "venv", str(app / ".venv")],
                       check=True, timeout=PIP_TIMEOUT_S)
        force_install = True
    if force_install:
        log("installing dependencies (pip install -e .)")
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                       check=False, timeout=PIP_TIMEOUT_S, cwd=app)
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", "-e", str(app)],
                       check=True, timeout=PIP_TIMEOUT_S, cwd=app)


def skipped_commit() -> str:
    try:
        return (state_dir() / "updater-failed").read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return ""


def remember_failed(commit: str) -> None:
    try:
        (state_dir() / "updater-failed").write_text(commit + "\n", encoding="ascii")
    except OSError:
        pass


def verify(app: Path) -> str | None:
    """The version the game reports, None when it does not even start."""
    try:
        result = subprocess.run([str(venv_python(app)), "main.py", "--version"],
                                cwd=app, capture_output=True, text=True,
                                timeout=VERIFY_TIMEOUT_S, check=False,
                                env={**os.environ, "SDL_VIDEODRIVER": "dummy",
                                     "SDL_AUDIODRIVER": "dummy"})
    except (OSError, subprocess.SubprocessError):
        return None
    lines = result.stdout.strip().splitlines()
    return lines[-1] if result.returncode == 0 and lines else None


def resolve_target(app: Path, channel: str) -> tuple[str, str] | None:
    """(label, commit) to move to, or None when there is nothing to do."""
    if channel != "main":
        tag = fetch_latest_release()
        if tag is None:
            log("no network or no answer from GitHub; starting installed version")
            return None
        if tag:
            new = parse_tag(tag)
            current = installed_version(app)
            if current is not None and new <= current:
                return None
            git(app, "fetch", "--quiet", "--no-tags", "origin",
                f"+refs/tags/{tag}:refs/tags/{tag}")
            return tag, git(app, "rev-parse", f"refs/tags/{tag}^{{commit}}")
        log("no GitHub release yet; following origin/main")
    try:
        git(app, "fetch", "--quiet", "origin", "main")
    except (RuntimeError, subprocess.SubprocessError) as exc:
        log(f"fetch failed ({exc}); starting installed version")
        return None
    return "main", git(app, "rev-parse", "origin/main^{commit}")


def update(app: Path = APP_DIR, channel: str | None = None) -> bool:
    """Bring the checkout to the newest release; True when it changed."""
    channel = channel or os.environ.get("U_JAGD_UPDATE_CHANNEL", "release")
    if os.environ.get("U_JAGD_NO_UPDATE"):
        return False
    try:
        if git(app, "status", "--porcelain", "--untracked-files=no"):
            log("local changes in the checkout; update skipped")
            return False
        branch = git(app, "rev-parse", "--abbrev-ref", "HEAD")
        if branch not in ("main", "HEAD"):
            log(f"branch {branch} checked out; update skipped")
            return False
        target = resolve_target(app, channel)
        old = git(app, "rev-parse", "HEAD")
        if target is None or target[1] == old:
            return False
        label, new = target
        if skipped_commit() == new:
            return False  # already failed once; wait for a newer version
        if subprocess.run(["git", "-C", str(app), "merge-base", "--is-ancestor", old, new],
                          timeout=GIT_TIMEOUT_S, check=False).returncode != 0:
            log(f"{label} is not a descendant of the installed commit; update skipped")
            return False
        deps_changed = bool(git(app, "diff", "--name-only", old, new, "--", *DEP_FILES))
        log(f"updating to {label} ({new[:10]})")
        notify(f"Update auf {label} …")
        if branch == "main":
            git(app, "merge", "--quiet", "--ff-only", new)
        else:
            git(app, "checkout", "--quiet", "--detach", new)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        log(f"update check failed: {exc}")
        return False
    try:
        ensure_venv(app, force_install=deps_changed)
        reported = verify(app)
        if not reported:
            raise RuntimeError("new version does not start")
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        log(f"update to {label} failed ({exc}); rolling back to {old[:10]}")
        notify("Update fehlgeschlagen, alte Version bleibt.")
        remember_failed(new)
        try:
            git(app, "reset", "--quiet", "--keep", old)
            ensure_venv(app, force_install=deps_changed)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc2:
            log(f"rollback failed: {exc2}")
        return False
    log(f"now at {reported}")
    return True


class GameLock:
    """Held by the updater and, inherited through exec, by the running game."""

    def __init__(self) -> None:
        state_dir().mkdir(parents=True, exist_ok=True)
        self.fd = os.open(state_dir() / "updater.lock", os.O_RDWR | os.O_CREAT, 0o600)

    def try_acquire(self) -> bool:
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True


def launch(argv: list[str], app: Path = APP_DIR) -> int:
    lock = GameLock()
    if lock.try_acquire():
        update(app)
        try:
            ensure_venv(app)
        except (OSError, subprocess.SubprocessError) as exc:
            log(f"virtual environment missing and could not be created: {exc}")
            notify("Start fehlgeschlagen, siehe ~/.u-jagd/updater.log")
            return 1
        os.set_inheritable(lock.fd, True)  # the game keeps the lock while it runs
    else:
        log("U-Jagd already running or updating; starting without update")
    os.chdir(app)
    py = str(venv_python(app))
    os.execv(py, [py, "main.py", *argv])
    return 1  # pragma: no cover - execv does not return


def background_update(app: Path = APP_DIR) -> int:
    lock = GameLock()
    if not lock.try_acquire():
        log("game running; background update postponed")
        return 0
    update(app)
    return 0


# --- desktop integration ---------------------------------------------------

def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def desktop_entry(app: Path) -> str:
    launcher = app / "packaging/uconsole/u-jagd-launch"
    icon = app / "packaging/uconsole/u-jagd.svg"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=U-Jagd\n"
        "GenericName=Anti-Submarine Warfare\n"
        "GenericName[de]=U-Boot-Jagd\n"
        "Comment=Anti Sub Marine Warfare on uConsole (updates itself)\n"
        "Comment[de]=U-Boot-Jagd auf der uConsole (aktualisiert sich selbst)\n"
        f"Exec=\"{launcher}\"\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Game;Simulation;\n"
        "StartupNotify=false\n"
    )


def systemd_units(app: Path) -> dict[str, str]:
    script = app / "packaging/uconsole/u_jagd_updater.py"
    return {
        "u-jagd-update.service": (
            "[Unit]\nDescription=U-Jagd background update\n"
            "After=network-online.target\n\n"
            "[Service]\nType=oneshot\n"
            f"ExecStart=/usr/bin/env python3 \"{script}\" update\n"
            "Nice=10\nIOSchedulingClass=idle\n"),
        "u-jagd-update.timer": (
            "[Unit]\nDescription=Check for U-Jagd updates\n\n"
            "[Timer]\nOnBootSec=3min\nOnUnitActiveSec=6h\nPersistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n"),
    }


def write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(mode)
    os.replace(tmp, path)


def systemctl(*args: str) -> bool:
    if not shutil.which("systemctl"):
        return False
    try:
        return subprocess.run(["systemctl", "--user", *args], timeout=30, check=False,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def desktop_dir() -> Path | None:
    try:
        name = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True,
                              timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    path = Path(name) if name else Path.home() / "Desktop"
    return path if path.is_dir() and path != Path.home() else None


def setup(app: Path = APP_DIR) -> int:
    ensure_venv(app, force_install=True)
    entry = desktop_entry(app)
    write_text(data_home() / "applications" / f"{APP_ID}.desktop", entry)
    desk = desktop_dir()
    if desk is not None:
        shortcut = desk / f"{APP_ID}.desktop"
        write_text(shortcut, entry, 0o755)
        if shutil.which("gio"):
            subprocess.run(["gio", "set", str(shortcut), "metadata::trusted", "true"],
                           check=False, timeout=5, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    bin_link = Path.home() / ".local/bin" / APP_ID
    bin_link.parent.mkdir(parents=True, exist_ok=True)
    if bin_link.is_symlink() or bin_link.exists():
        bin_link.unlink()
    bin_link.symlink_to(app / "packaging/uconsole/u-jagd-launch")
    for name, text in systemd_units(app).items():
        write_text(config_home() / "systemd/user" / name, text)
    if systemctl("daemon-reload") and systemctl("enable", "--now", "u-jagd-update.timer"):
        log("background update timer enabled")
    else:
        log("systemd user timer unavailable; updates run at every start only")
    log(f"setup complete in {app}")
    return 0


def uninstall() -> int:
    systemctl("disable", "--now", "u-jagd-update.timer")
    paths = [data_home() / "applications" / f"{APP_ID}.desktop",
             Path.home() / ".local/bin" / APP_ID]
    paths += [config_home() / "systemd/user" / name for name in systemd_units(APP_DIR)]
    desk = desktop_dir()
    if desk is not None:
        paths.append(desk / f"{APP_ID}.desktop")
    for path in paths:
        if path.is_symlink() or path.exists():
            path.unlink()
    systemctl("daemon-reload")
    log(f"desktop integration removed; game files stay in {APP_DIR}")
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "launch"
    if command == "launch":
        return launch(argv[1:])
    if command == "update":
        return background_update()
    if command == "setup":
        return setup()
    if command == "uninstall":
        return uninstall()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
