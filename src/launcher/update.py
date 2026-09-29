"""Release lookup and self-update for the Windows starter.

Everything here is pure or takes its network opener as a parameter, so the
update rules are testable without a network or Windows. Release metadata from
GitHub is treated as untrusted input: strict types, bounded sizes, HTTPS
download URLs on GitHub only, and the asset's SHA-256 digest when GitHub
publishes one.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

REPOSITORY = "db9979/uconsole_asw_game"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
ASSET_NAME = "U-Jagd-Windows.exe"
MAX_METADATA_BYTES = 1 << 20
MAX_ASSET_BYTES = 400 << 20
_CHUNK = 1 << 16
_VERSION = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
_DOWNLOAD_HOSTS = frozenset({"github.com", "api.github.com",
                             "objects.githubusercontent.com"})


class UpdateError(RuntimeError):
    """A release could not be checked, downloaded or verified."""


def parse_version(text: object) -> tuple[int, int, int] | None:
    """``"v1.3.8"`` or ``"1.3.8"`` as a comparable tuple, else ``None``."""
    if type(text) is not str:
        return None
    match = _VERSION.fullmatch(text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    size: int
    sha256: str | None
    page: str


def _https_github(url: object) -> bool:
    if type(url) is not str or len(url) > 2048:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname in _DOWNLOAD_HOSTS
            and parts.port is None and not parts.username and not parts.password)


def select_release(payload: object, current: str) -> Release | None:
    """The newer published Windows build in a ``releases/latest`` payload."""
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    version = parse_version(payload.get("tag_name"))
    installed = parse_version(current)
    if version is None or installed is None or version <= installed:
        return None
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets[:64]:
        if not isinstance(asset, dict) or asset.get("name") != ASSET_NAME:
            continue
        url, size = asset.get("browser_download_url"), asset.get("size")
        if not _https_github(url) or type(size) is not int or not 0 < size <= MAX_ASSET_BYTES:
            return None
        digest = asset.get("digest")
        match = _DIGEST.fullmatch(digest) if type(digest) is str else None
        if digest is not None and match is None:
            return None
        page = payload.get("html_url")
        return Release(".".join(map(str, version)), url, size,
                       match.group(1) if match else None,
                       page if _https_github(page) else RELEASES_PAGE)
    return None


def _read_bounded(response, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("response too large")
    return data


def check_latest(current: str, opener=urllib.request.urlopen,
                 timeout: float = 10.0) -> Release | None:
    """Ask GitHub for the latest release; ``None`` when nothing newer exists."""
    request = urllib.request.Request(LATEST_RELEASE_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"u-jagd-windows/{current}"})
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(_read_bounded(response, MAX_METADATA_BYTES))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # nothing published yet
            return None
        raise UpdateError(str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise UpdateError(str(exc)) from exc
    return select_release(payload, current)


def download(release: Release, destination: str, opener=urllib.request.urlopen,
             progress=None, timeout: float = 30.0) -> str:
    """Download and verify ``release`` to ``destination`` atomically."""
    staging = f"{destination}.part"
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(release.url, headers={
        "User-Agent": "u-jagd-windows"})
    try:
        with opener(request, timeout=timeout) as response, open(staging, "wb") as handle:
            while True:
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                received += len(chunk)
                if received > release.size:
                    raise UpdateError("download larger than announced")
                digest.update(chunk)
                handle.write(chunk)
                if progress is not None:
                    progress(received, release.size)
            handle.flush()
            os.fsync(handle.fileno())
        if received != release.size:
            raise UpdateError("download incomplete")
        if release.sha256 is not None and digest.hexdigest() != release.sha256:
            raise UpdateError("checksum mismatch")
        os.replace(staging, destination)
    except BaseException as exc:
        try:
            os.remove(staging)
        except OSError:
            pass
        if isinstance(exc, OSError):
            raise UpdateError(str(exc)) from exc
        raise
    return destination


def clean_environment(environ) -> dict:
    """The environment for a fresh start of the (new) one-file executable.

    A PyInstaller one-file program passes its extraction directory to child
    processes (``_PYI_*``) so a child of the same executable reuses it. The
    swapped-in update has the same path but must not: the old process has
    already deleted that directory ("Failed to load Python DLL"). Dropping the
    variables and setting ``PYINSTALLER_RESET_ENVIRONMENT`` makes it unpack
    itself afresh.
    """
    env = {key: value for key, value in environ.items()
           if not key.upper().startswith(("_PYI_", "_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


INSTALL_TRIES = 120  # about two minutes of one-second retries


def _checked_path(path: str) -> str:
    if (type(path) is not str or not path or '"' in path or "%" in path
            or "\n" in path or "\r" in path or "!" in path):
        raise UpdateError("unsupported path")
    return path


def install_script(executable: str, downloaded: str, args=(), log=None) -> str:
    """A ``cmd`` script that swaps the executable once nothing holds it.

    Replacing a running ``.exe`` fails, so the move is retried once a second
    until the starter (a one-file build is two processes: the bootloader and
    Python) has exited. The pause uses ``ping``: ``timeout`` exits at once
    when stdin is redirected, which used up every retry in milliseconds and
    left the update as ``.new`` beside the old program (1.3.73 fix). Then it
    starts the executable (the new one, or the old one if the swap failed,
    which is logged) and deletes itself.
    """
    executable, downloaded = _checked_path(executable), _checked_path(downloaded)
    for arg in args:
        _checked_path(arg)
    tail = "".join(f' "{arg}"' for arg in args)
    lines = [
        "@echo off",
        "setlocal",
        "set tries=0",
        ":move",
        f'move /Y "{downloaded}" "{executable}" >NUL 2>NUL',
        "if not errorlevel 1 goto start",
        "set /a tries+=1",
        f"if %tries% GEQ {INSTALL_TRIES} goto failed",
        "ping -n 2 127.0.0.1 >NUL",
        "goto move",
        ":failed",
    ]
    if log is not None:
        lines.append(f'echo update failed: "{downloaded}" could not replace '
                     f'"{executable}" >> "{_checked_path(log)}"')
    lines += [
        ":start",
        f'start "" "{executable}"{tail}',
        '(goto) 2>NUL & del "%~f0"',
        "",
    ]
    return "\r\n".join(lines)


def launch_install(executable: str, downloaded: str, args=(), log=None,
                   popen=None) -> str:
    """Write the install script and start it detached; the caller then exits."""
    import subprocess
    import tempfile

    script = os.path.join(tempfile.gettempdir(), f"u-jagd-update-{os.getpid()}.cmd")
    try:
        with open(script, "w", encoding="utf-8", newline="") as handle:
            handle.write(install_script(executable, downloaded, args, log))
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    (popen or subprocess.Popen)(
        ["cmd", "/c", script], creationflags=flags,
        env=clean_environment(os.environ), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return script
