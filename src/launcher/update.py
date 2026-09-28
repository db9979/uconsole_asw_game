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


def install_script(executable: str, downloaded: str, pid: int) -> str:
    """A ``cmd`` script that swaps the executable once ``pid`` has exited.

    It waits for the running starter to end, retries the move while Windows
    still holds the file, starts the new version and deletes itself.
    """
    for path in (executable, downloaded):
        if '"' in path or "%" in path or "\n" in path or "\r" in path:
            raise UpdateError("unsupported path")
    if type(pid) is not int or pid <= 0:
        raise UpdateError("invalid process id")
    return "\r\n".join((
        "@echo off",
        "setlocal",
        ":wait",
        f'tasklist /FI "PID eq {pid}" /NH 2>NUL | find " {pid} " >NUL',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)",
        "set tries=0",
        ":move",
        f'move /Y "{downloaded}" "{executable}" >NUL 2>NUL',
        "if errorlevel 1 (",
        "  set /a tries+=1",
        "  if %tries% LSS 30 (timeout /t 1 /nobreak >NUL & goto move)",
        ")",
        f'start "" "{executable}"',
        '(goto) 2>NUL & del "%~f0"',
        ""))
