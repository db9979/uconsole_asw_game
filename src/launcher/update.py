"""Release lookup and self-update for the Windows and macOS programs.

Everything here is pure or takes its network opener as a parameter, so the
update rules are testable without a network, Windows or a Mac. Release metadata from
GitHub is treated as untrusted input: strict types, bounded sizes, HTTPS
download URLs on GitHub only, and the asset's SHA-256 digest when GitHub
publishes one.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import ssl
import stat
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from src.core.https import ssl_context, urlopen  # noqa: F401 - re-exported

REPOSITORY = "db9979/uconsole_asw_game"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
ASSET_NAME = "U-Jagd-Windows.exe"
# macOS: one zipped app bundle per processor (pygame and NumPy publish no
# universal2 wheels), made with ``ditto -c -k --keepParent U-Jagd.app``.
MAC_APP_NAME = "U-Jagd.app"
MAC_EXECUTABLE = "U-Jagd"
# Apple silicon only; an Intel Mac gets no zip and opens the release page.
MAC_ASSETS = {"arm64": "U-Jagd-macOS-arm64.zip"}
MAX_METADATA_BYTES = 1 << 20
MAX_ASSET_BYTES = 400 << 20
_CHUNK = 1 << 16
_VERSION = re.compile(r"v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})")
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
_DOWNLOAD_HOSTS = frozenset({"github.com", "api.github.com",
                             "objects.githubusercontent.com"})


class UpdateError(RuntimeError):
    """A release could not be checked, downloaded or verified."""


FAILURE_REASONS = ("tls", "offline", "http", "other")


def failure_reason(exc: BaseException) -> str:
    """Why a check failed, as a short key: tls, offline, http or other."""
    seen = exc
    for _ in range(6):
        if isinstance(seen, ssl.SSLCertVerificationError) or (
                isinstance(seen, ssl.SSLError) and "CERTIFICATE" in str(seen).upper()):
            return "tls"
        if isinstance(seen, urllib.error.HTTPError):
            return "http"
        if isinstance(seen, urllib.error.URLError):
            seen = seen.reason if isinstance(seen.reason, BaseException) else None
            if seen is None:
                return "offline"
            continue
        if isinstance(seen, (TimeoutError, ConnectionError, OSError)):
            return "offline"
        nxt = seen.__cause__ or seen.__context__
        if nxt is None:
            break
        seen = nxt
    return "other"


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


def select_release(payload: object, current: str,
                   asset_name: str = ASSET_NAME) -> Release | None:
    """The newer published build ``asset_name`` in a ``releases/latest`` payload."""
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
        if not isinstance(asset, dict) or asset.get("name") != asset_name:
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


def check_latest(current: str, opener=urlopen,
                 timeout: float = 10.0, asset_name: str = ASSET_NAME) -> Release | None:
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
    return select_release(payload, current, asset_name)


def download(release: Release, destination: str, opener=urlopen,
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


# --- macOS app bundle -------------------------------------------------------

MAX_UNPACKED_BYTES = 1 << 30
MAX_ZIP_ENTRIES = 20000
MAX_LINK_CHARS = 1024


def mac_asset_name(machine: str | None = None) -> str | None:
    """The release zip for this Mac's processor (``None`` when unknown)."""
    machine = platform.machine() if machine is None else machine
    return MAC_ASSETS.get({"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine))


@dataclass(frozen=True)
class MacBundle:
    """The running ``.app`` and the paths its update uses beside it.

    ``archive`` is the downloaded zip, ``staging`` the folder the new bundle
    is unpacked into, ``old`` where the running bundle is moved during the
    swap. All of them sit next to the bundle (same volume, so each move is
    one atomic ``rename``); none is inside ``~/.u-jagd``.
    """

    app: str

    @property
    def archive(self) -> str:
        return f"{self.app}.update.zip"

    @property
    def staging(self) -> str:
        return f"{self.app}.update"

    @property
    def staged_app(self) -> str:
        return os.path.join(self.staging, MAC_APP_NAME)

    @property
    def old(self) -> str:
        return f"{self.app}.old"


def mac_bundle(executable: str) -> MacBundle | None:
    """The bundle of ``.../Name.app/Contents/MacOS/<exe>``, else ``None``.

    A bundle that macOS runs translocated (started from the quarantined
    download: a read-only random path) cannot be replaced, nor can one in a
    folder this user may not write; both get ``None`` (release page).
    """
    if type(executable) is not str or not executable or "\n" in executable:
        return None
    macos = os.path.dirname(os.path.abspath(executable))
    contents = os.path.dirname(macos)
    app = os.path.dirname(contents)
    if (os.path.basename(macos) != "MacOS" or os.path.basename(contents) != "Contents"
            or not app.endswith(".app") or "/AppTranslocation/" in app
            or os.path.islink(app) or not os.access(os.path.dirname(app), os.W_OK)):
        return None
    return MacBundle(app)


def _remove_tree(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def remove_mac_leftovers(bundle: MacBundle) -> None:
    """Delete what an update that could not swap in left beside the bundle."""
    for path in (bundle.archive, f"{bundle.archive}.part", bundle.staging,
                 f"{bundle.staging}.part", bundle.old):
        try:
            _remove_tree(path)
        except OSError:
            pass


def _member_parts(name: str) -> tuple[str, ...] | None:
    """The parts of a zip member under ``U-Jagd.app``; ``None`` to skip it."""
    parts = tuple(name.rstrip("/").split("/"))
    if parts[0] == "__MACOSX" or parts[-1].startswith("._"):
        return None  # AppleDouble metadata, never part of the bundle
    if (name.startswith("/") or "\\" in name or "\0" in name or parts[0] != MAC_APP_NAME
            or any(part in ("", ".", "..") for part in parts)):
        raise UpdateError(f"unexpected path in the update: {name[:80]!r}")
    return parts


def _extract(archive: str, root: str) -> None:
    import zipfile

    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > MAX_ZIP_ENTRIES:
            raise UpdateError("too many files in the update")
        if sum(info.file_size for info in members) > MAX_UNPACKED_BYTES:
            raise UpdateError("update too large")
        real_root = os.path.realpath(root)
        for info in members:
            parts = _member_parts(info.filename)
            if parts is None:
                continue
            target = os.path.join(root, *parts)
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            is_dir = info.is_dir() or kind == stat.S_IFDIR
            if os.path.lexists(target) and not (
                    is_dir and os.path.isdir(target) and not os.path.islink(target)):
                raise UpdateError(f"duplicate path in the update: {info.filename[:80]!r}")
            parent = os.path.dirname(target)
            os.makedirs(parent, mode=0o755, exist_ok=True)
            if os.path.commonpath([real_root, os.path.realpath(parent)]) != real_root:
                raise UpdateError("the update writes outside its folder")
            if is_dir:
                os.makedirs(target, mode=0o755, exist_ok=True)
            elif kind == stat.S_IFLNK:
                if info.file_size > MAX_LINK_CHARS:
                    raise UpdateError("a link in the update is too long")
                link = zipped.read(info).decode("utf-8")
                lands = os.path.normpath(os.path.join(*parts[:-1], link)).split(os.sep)
                if not link or link.startswith("/") or "\0" in link or lands[0] != MAC_APP_NAME:
                    raise UpdateError("a link in the update points outside the app")
                os.symlink(link, target)
            elif kind in (0, stat.S_IFREG):
                with zipped.open(info) as source, open(target, "xb") as handle:
                    shutil.copyfileobj(source, handle, _CHUNK)
                # Only the executable bits survive: never setuid, sticky or
                # writable by others.
                os.chmod(target, 0o755 if mode & 0o111 else 0o644)
            else:
                raise UpdateError("unsupported file type in the update")


def unpack_app(archive: str, bundle: MacBundle) -> str:
    """Unpack the downloaded zip to ``bundle.staged_app`` and check it.

    The zip is untrusted beyond its checked digest: only members under
    ``U-Jagd.app/``, no ``..`` or absolute paths, links that stay inside the
    bundle, bounded size and count; modes are reduced to ``755``/``644``.
    It is unpacked into ``<staging>.part`` and renamed into place only once
    complete, so an interrupted unpack never looks finished.
    """
    partial = f"{bundle.staging}.part"
    try:
        for path in (partial, bundle.staging):
            _remove_tree(path)
        os.mkdir(partial, 0o755)
        _extract(archive, partial)
        app = os.path.join(partial, MAC_APP_NAME)
        executable = os.path.join(app, "Contents", "MacOS", MAC_EXECUTABLE)
        if (not os.path.isfile(os.path.join(app, "Contents", "Info.plist"))
                or os.path.islink(executable) or not os.path.isfile(executable)
                or not os.access(executable, os.X_OK)):
            raise UpdateError("the update holds no U-Jagd.app")
        os.replace(partial, bundle.staging)
    except BaseException as exc:
        try:
            _remove_tree(partial)
        except OSError:
            pass
        if isinstance(exc, Exception) and not isinstance(exc, UpdateError):
            raise UpdateError(str(exc)) from exc
        raise
    return bundle.staged_app


def mac_install_script(bundle: MacBundle, pid: int, args=(), log=None) -> str:
    """A ``sh`` script that swaps the bundle once the game ``pid`` has quit.

    The running bundle is renamed to ``.old`` first and the staged one into
    its place; if that second rename fails the old bundle is renamed back.
    The old bundle and the staging files are deleted only once the new
    bundle is in place. Then the bundle (the new one, or the old one after a
    failed swap, which is logged) is opened again and the script deletes
    itself. Nothing in ``~/.u-jagd`` is touched.
    """
    if type(pid) is not int or pid <= 0:
        raise UpdateError("invalid process id")
    names = {"app": bundle.app, "staged": bundle.staged_app, "old": bundle.old,
             "staging": bundle.staging, "archive": bundle.archive,
             "log": log if log is not None else os.devnull}
    for value in (*names.values(), *args):
        if type(value) is not str or not value or "\n" in value or "\0" in value:
            raise UpdateError("unsupported path")
    tail = "".join(f" {shlex.quote(arg)}" for arg in args)
    lines = ["#!/bin/sh"]
    lines += [f"{key}={shlex.quote(value)}" for key, value in names.items()]
    lines += [
        "tries=0",
        f"while kill -0 {pid} 2>/dev/null; do",
        "  tries=$((tries + 1))",
        f'  if [ "$tries" -ge {INSTALL_TRIES} ]; then',
        '    echo "update failed: the game did not quit" >> "$log"',
        '    rm -f "$0"',
        "    exit 1",
        "  fi",
        "  sleep 1",
        "done",
        'rm -rf "$old"',
        'if [ -e "$old" ]; then',
        '  echo "update failed: $old could not be removed" >> "$log"',
        'elif mv "$app" "$old"; then',
        '  if mv "$staged" "$app"; then',
        '    rm -rf "$old" "$staging" "$archive"',
        "  else",
        '    mv "$old" "$app" || echo "update failed: $old could not be moved back" >> "$log"',
        '    echo "update failed: $staged could not replace $app" >> "$log"',
        "  fi",
        "else",
        '  echo "update failed: $app could not be moved aside" >> "$log"',
        "fi",
        f'open -n "$app"{" --args" + tail if tail else ""}',
        'rm -f "$0"',
        "",
    ]
    return "\n".join(lines)


def launch_mac_install(bundle: MacBundle, args=(), log=None, popen=None,
                       pid: int | None = None) -> str:
    """Write the swap script and start it detached; the caller then exits."""
    import subprocess
    import tempfile

    pid = os.getpid() if pid is None else pid
    script = os.path.join(tempfile.gettempdir(), f"u-jagd-update-{pid}.sh")
    try:
        with open(script, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(mac_install_script(bundle, pid, args, log))
        (popen or subprocess.Popen)(
            ["/bin/sh", script], env=clean_environment(os.environ),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    except OSError as exc:
        raise UpdateError(str(exc)) from exc
    return script


# --- update notice (game splash, main menu and starter) --------------------

# The game exits with this code after "Update now" when the starter runs it.
UPDATE_EXIT_CODE = 75
RAW_FILE = "https://raw.githubusercontent.com/{repository}/{tag}/{path}"
MAX_TEXT_BYTES = 1 << 21
MAX_NOTES_CHARS = 700
_ENTRY = re.compile(r"^## (\d+\.\d+\.\d+)\s*$", re.MULTILINE)
_SAVE_VERSION = re.compile(r"^SAVE_VERSION\s*=\s*(\d{1,4})\s*$", re.MULTILINE)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_CHANGELOGS = {"en": "CHANGELOG.md", "de": "CHANGELOG.de.md"}


@dataclass(frozen=True)
class Notice:
    """A newer published release: its version, notes per language and saves."""

    version: str
    page: str
    notes: dict
    save_version: int | None

    def notes_for(self, language: str) -> str:
        return self.notes.get(language) or self.notes.get("en") or ""

    def breaks_saves(self, current_save_version: int) -> bool:
        """Saves of this build no longer load in the new release."""
        return self.save_version is not None and self.save_version != current_save_version


def changelog_entry(text: str, version: str) -> str:
    """The text under ``## version`` in a changelog, ``""`` when missing."""
    matches = list(_ENTRY.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1) == version:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            return text[match.end():end].strip()
    return ""


def plain_notes(text: object, limit: int = MAX_NOTES_CHARS) -> str:
    """Release notes as one plain paragraph (no Markdown), at most ``limit``."""
    if type(text) is not str:
        return ""
    text = _LINK.sub(r"\1", text[:limit * 8])
    text = re.sub(r"[`*_#>]", "", text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


def parse_save_version(text: str) -> int | None:
    match = _SAVE_VERSION.search(text)
    return int(match.group(1)) if match else None


def _fetch_text(url: str, opener, timeout: float, agent: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    try:
        with opener(request, timeout=timeout) as response:
            return _read_bounded(response, MAX_TEXT_BYTES).decode("utf-8")
    except (OSError, ValueError, UpdateError):
        return ""


def fetch_notice(current: str, opener=urlopen,
                 timeout: float = 8.0) -> Notice | None:
    """The newer latest release with its changelog entry, ``None`` if current.

    Nothing is downloaded or installed. The English notes are the release
    text (the changelog entry, see ``tools/changelog_notes.py``); the German
    entry and the release's ``SAVE_VERSION`` are read from the tagged files.
    Raises ``UpdateError`` when GitHub cannot be asked (offline).
    """
    agent = f"u-jagd/{current}"
    request = urllib.request.Request(LATEST_RELEASE_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": agent})
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(_read_bounded(response, MAX_METADATA_BYTES))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise UpdateError(str(exc)) from exc
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    tag = payload.get("tag_name")
    version, installed = parse_version(tag), parse_version(current)
    if version is None or installed is None or version <= installed:
        return None
    number = ".".join(map(str, version))
    tag = f"v{number}"

    def raw(path: str) -> str:
        return _fetch_text(RAW_FILE.format(repository=REPOSITORY, tag=tag, path=path),
                           opener, timeout, agent)

    notes = {}
    for language, path in _CHANGELOGS.items():
        notes[language] = plain_notes(changelog_entry(raw(path), number))
    if not notes["en"]:
        notes["en"] = plain_notes(payload.get("body"))
    page = payload.get("html_url")
    return Notice(number, page if _https_github(page) else RELEASES_PAGE,
                  {key: value for key, value in notes.items() if value},
                  parse_save_version(raw("src/core/version.py")))
