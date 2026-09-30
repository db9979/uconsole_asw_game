#!/usr/bin/env python3
"""Self-updating launcher for U-Jagd on the uConsole.

Runs with the system ``python3`` and only the standard library, so it keeps
working even when the game's virtual environment is broken.  Commands:

``launch [game args]``  replace this process with the game
                        (``.venv/bin/python main.py``); never updates.
``install [game args]`` "Update now" in the game: wait until the game has
                        closed, update to the newest release, then start it.
``update``              with ``U_JAGD_UPDATE_NOW=1`` (the installer) update
                        only; otherwise (the retired background timer of
                        releases up to 1.3.109) switch that timer off.
``setup``               create/refresh the venv, menu entry and ``~/.local/bin``
                        command (the installer); removes the old timer.
``uninstall``           remove that desktop integration again (keeps the game
                        directory and ``~/.u-jagd`` saves).

Since 1.3.110 nothing is installed automatically: the game shows a newer
release with its changelog on the start screen and installs it only when the
player presses "Update now".

Update source: the newest GitHub release (tag ``vX.Y.Z``, the same source the
Windows program uses).  Without any release the checkout follows ``origin/main``;
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
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "db9979/uconsole_asw_game"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', re.M)
DEP_FILES = ("pyproject.toml", "requirements.txt")
NET_TIMEOUT_S = 6
PROBE_TIMEOUT_S = 2.5
PROBE_HOST = ("github.com", 443)
GIT_TIMEOUT_S = 60
# git gives up on a stalled or unreachable remote instead of hanging the start
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_HTTP_LOW_SPEED_LIMIT": "1000",
           "GIT_HTTP_LOW_SPEED_TIME": "15"}
PIP_TIMEOUT_S = 1200
INSTALL_WAIT_S = 120  # "Update now": the game saves and closes in this time
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
                            text=True, timeout=timeout, check=False,
                            env={**os.environ, **GIT_ENV})
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def probe_address() -> tuple[str, int]:
    """GitHub, or the HTTPS proxy when one is configured."""
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if proxy:
        try:
            parts = urllib.parse.urlsplit(proxy if "://" in proxy else "http://" + proxy)
            if parts.hostname:
                return parts.hostname, parts.port or 80
        except ValueError:
            pass
    return PROBE_HOST


def online(timeout: float = PROBE_TIMEOUT_S) -> bool:
    """Whether GitHub is reachable, decided within ``timeout`` seconds.

    Name resolution ignores socket timeouts, so the probe runs in a daemon
    thread and a hanging DNS lookup simply counts as offline."""
    result: list[bool] = []

    def probe() -> None:
        try:
            socket.create_connection(probe_address(), timeout=timeout).close()
            result.append(True)
        except OSError:
            result.append(False)

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(timeout)
    return bool(result and result[0])


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


MESSAGES = {
    "de": {
        "check": "Suche nach Updates …",
        "download": "Lade Update {label} …",
        "deps": "Installiere Abhängigkeiten …",
        "verify": "Prüfe neue Version …",
        "rollback": "Update fehlgeschlagen, starte bisherige Version …",
        "start": "Starte U-Jagd …",
        "busy": "Hintergrund-Update läuft, bitte warten …",
        "closing": "Warte, bis U-Jagd beendet ist …",
        "running": "U-Jagd läuft bereits.",
        "failed": "Start fehlgeschlagen, siehe ~/.u-jagd/updater.log",
    },
    "en": {
        "check": "Checking for updates …",
        "download": "Downloading update {label} …",
        "deps": "Installing dependencies …",
        "verify": "Checking the new version …",
        "rollback": "Update failed, starting the previous version …",
        "start": "Starting U-Jagd …",
        "busy": "Background update running, please wait …",
        "closing": "Waiting for U-Jagd to close …",
        "running": "U-Jagd is already running.",
        "failed": "Start failed, see ~/.u-jagd/updater.log",
    },
}


def language() -> str:
    """The game's saved language, else the system locale (de or en)."""
    try:
        data = json.loads((state_dir() / "settings.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("language") in MESSAGES:
            return data["language"]
    except (OSError, ValueError):
        pass
    lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "")
    return "de" if lang.startswith("de") else "en"


def message(key: str, **values: str) -> str:
    return MESSAGES[language()][key].format(**values)


def _no_progress(key: str, **values: str) -> None:
    pass


def update(app: Path = APP_DIR, channel: str | None = None, progress=_no_progress) -> bool:
    """Bring the checkout to the newest release; True when it changed.

    ``progress(key, **values)`` reports each step (keys of ``MESSAGES``)."""
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
        progress("check")
        if not online():
            log("offline (GitHub not reachable); update check skipped")
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
        progress("download", label=label)
        if branch == "main":
            git(app, "merge", "--quiet", "--ff-only", new)
        else:
            git(app, "checkout", "--quiet", "--detach", new)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        log(f"update check failed: {exc}")
        return False
    try:
        if deps_changed:
            progress("deps")
        ensure_venv(app, force_install=deps_changed)
        progress("verify")
        reported = verify(app)
        if not reported:
            raise RuntimeError("new version does not start")
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        log(f"update to {label} failed ({exc}); rolling back to {old[:10]}")
        progress("rollback")
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
    """Held by the launcher and, inherited through exec, by the running game.

    The lock file names its holder (``launch``, ``game`` or ``update``) so a
    second start can tell a running game from a background update."""

    def __init__(self) -> None:
        state_dir().mkdir(parents=True, exist_ok=True)
        self.fd = os.open(state_dir() / "updater.lock", os.O_RDWR | os.O_CREAT, 0o600)

    def try_acquire(self) -> bool:
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def acquire(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while not self.try_acquire():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.5)
        return True

    def set_role(self, role: str) -> None:
        os.ftruncate(self.fd, 0)
        os.pwrite(self.fd, f"{role} {os.getpid()}\n".encode("ascii"), 0)

    def holder(self) -> str:
        """Role written by the current holder ("" while it is still starting)."""
        try:
            return os.pread(self.fd, 64, 0).decode("ascii", "replace").split(" ")[0].strip()
        except OSError:
            return ""


class Splash:
    """The start window (``u_jagd_splash.py``), fed through a pipe.

    Without a display or without Pygame in the venv it silently does nothing."""

    def __init__(self, app: Path) -> None:
        self.proc = None
        self.fd = None
        py = venv_python(app)
        script = app / "packaging/uconsole/u_jagd_splash.py"
        if os.environ.get("U_JAGD_NO_SPLASH") or not py.exists() or not script.exists():
            return
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return
        read_fd, write_fd = os.pipe()
        try:
            self.proc = subprocess.Popen([str(py), str(script)], stdin=read_fd,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         start_new_session=True)
        except OSError:
            os.close(write_fd)
            write_fd = None
        finally:
            os.close(read_fd)
        self.fd = write_fd

    def send(self, kind: str, value: str) -> None:
        if self.fd is None:
            return
        try:
            os.write(self.fd, f"{kind}\t{value}\n".encode("utf-8"))
        except OSError:
            self.close()

    def status(self, key: str, **values: str) -> None:
        self.send("status", message(key, **values))

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def hand_to_game(self, env: dict) -> None:
        """The game closes the pipe after its first frame; the window follows."""
        if self.fd is not None:
            os.set_inheritable(self.fd, True)
            env["U_JAGD_SPLASH_FD"] = str(self.fd)


def show_briefly(app: Path, key: str) -> None:
    splash = Splash(app)
    splash.status(key)
    splash.send("close", "3")
    if splash.proc is None:
        notify(message(key))
    splash.close()
    if key == "running" and shutil.which("wmctrl"):
        try:  # bring the running game to the front where a window manager allows it
            subprocess.run(["wmctrl", "-a", "U-Jagd"], timeout=5, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            pass


def launch(argv: list[str], app: Path = APP_DIR, install: bool = False) -> int:
    """Start the game; ``install`` first updates to the newest release."""
    lock = GameLock()
    splash = None
    if not lock.try_acquire():
        if install:
            # "Update now": the game that asked is still closing.
            splash = Splash(app)
            splash.status("closing")
            if not lock.acquire(INSTALL_WAIT_S):
                log("game did not close; update not installed")
                splash.close()
                return 1
        elif lock.holder() != "update":
            log("U-Jagd is already running or starting; second start ignored")
            show_briefly(app, "running")
            return 0
        else:
            splash = Splash(app)
            splash.status("busy")
            if not lock.acquire(PIP_TIMEOUT_S):
                splash.close()
                return 1
    lock.set_role("launch")
    splash = splash or Splash(app)
    if install:
        update(app, progress=splash.status)
    try:
        ensure_venv(app)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"virtual environment missing and could not be created: {exc}")
        splash.status("failed")
        splash.send("close", "5")
        notify(message("failed"))
        return 1
    splash.status("start")
    lock.set_role("game")
    os.set_inheritable(lock.fd, True)  # the game keeps the lock while it runs
    env = dict(os.environ)
    splash.hand_to_game(env)
    os.chdir(app)
    py = str(venv_python(app))
    os.execve(py, [py, "main.py", *argv], env)
    return 1  # pragma: no cover - execve does not return


def background_update(app: Path = APP_DIR) -> int:
    if not os.environ.get("U_JAGD_UPDATE_NOW"):
        # The timer of releases up to 1.3.109 still calls this: turn it off.
        log("automatic updates are off; the game offers new releases itself")
        retire_timer()
        return 0
    lock = GameLock()
    if not lock.try_acquire():
        log("game running; background update postponed")
        return 0
    lock.set_role("update")
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
        "Comment=Anti Sub Marine Warfare on uConsole\n"
        "Comment[de]=U-Boot-Jagd auf der uConsole\n"
        f"Exec=\"{launcher}\"\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Game;Simulation;\n"
        "StartupNotify=false\n"
    )


TIMER_UNITS = ("u-jagd-update.timer", "u-jagd-update.service")


def retire_timer() -> None:
    """Switch off and remove the background update timer of older releases."""
    systemctl("disable", "--now", TIMER_UNITS[0])
    removed = False
    for name in TIMER_UNITS:
        path = config_home() / "systemd/user" / name
        if path.is_symlink() or path.exists():
            try:
                path.unlink()
                removed = True
            except OSError:
                pass
    if removed:
        systemctl("daemon-reload")


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
    retire_timer()
    log(f"setup complete in {app}")
    return 0


def uninstall() -> int:
    retire_timer()
    paths = [data_home() / "applications" / f"{APP_ID}.desktop",
             Path.home() / ".local/bin" / APP_ID]
    desk = desktop_dir()
    if desk is not None:
        paths.append(desk / f"{APP_ID}.desktop")
    for path in paths:
        if path.is_symlink() or path.exists():
            path.unlink()
    log(f"desktop integration removed; game files stay in {APP_DIR}")
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "launch"
    if command == "launch":
        return launch(argv[1:])
    if command == "install":
        return launch(argv[1:], install=True)
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
