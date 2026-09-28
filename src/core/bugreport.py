"""Bug report: a prefilled GitHub issue with version, platform and crash log.

The game holds no GitHub credentials (a token in the program would be public).
Instead it builds the URL of GitHub's "new issue" form for the repository's
issue template ``.github/ISSUE_TEMPLATE/bug.yml``, whose fields GitHub fills
from the query string; the player reviews the text and submits it with their
own account, so nothing leaves the device without their consent.

* ``issue_url()`` carries the newest lines of ``~/.u-jagd/crash.log`` and is
  opened in a browser (uConsole desktop, Windows starter).
* ``short_issue_url()`` carries only version, platform and context so it fits
  the on-screen QR code a phone scans (the uConsole usually has no browser).
* ``write_report()`` stores the whole report as ``~/.u-jagd/bug-report.txt``
  to attach to the issue.

Home directories and the user name are replaced before anything is shown or
written.  Pure helpers apart from the explicit file reads/writes; nothing here
touches the simulation.
"""

from __future__ import annotations

import getpass
import os
import platform
import re
from urllib.parse import quote, urlencode

from src.core import config
from src.core.crashlog import CRASH_LOG
from src.core.version import APP_VERSION

REPO_URL = "https://github.com/db9979/uconsole_asw_game"
NEW_ISSUE_URL = REPO_URL + "/issues/new"
ISSUE_TEMPLATE = "bug.yml"
REPORT_FILE = "bug-report.txt"
# GitHub refuses very long request lines; stay well below ~8 KB.
URL_MAX_CHARS = 7000
# Byte-mode capacity of the largest QR code ``src.ui.qr`` draws (v10, EC-M).
QR_URL_MAX_CHARS = 213
LOG_TAIL_BYTES = 64 * 1024
LOG_TAIL_LINES = 150
FIELD_MAX_CHARS = 120

_GENERIC_USERS = {"root", "user", "admin", "Administrator", "runner"}
_EXCEPTION_LINE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)\b.*)$")


def _user_names() -> list[str]:
    names = []
    for getter in (getpass.getuser, lambda: os.path.basename(os.path.expanduser("~"))):
        try:
            name = getter()
        except (KeyError, OSError, ImportError):
            continue
        # Short or generic names would also hit ordinary words of the log.
        if name and len(name) >= 4 and name not in _GENERIC_USERS and name not in names:
            names.append(name)
    return names


def anonymize(text: str, home: str | None = None, users: list[str] | None = None) -> str:
    """Replace the home directory with ``~`` and the user name with ``<user>``."""
    home = os.path.expanduser("~") if home is None else home
    users = _user_names() if users is None else users
    variants = {home, home.replace("\\", "/"), home.replace("/", "\\")}
    for variant in sorted((v for v in variants if len(v) > 1), key=len, reverse=True):
        text = text.replace(variant, "~")
    # Other users' or differently spelled home paths (/home/x, C:\Users\x).
    text = re.sub(r"(/home/|/Users/|[A-Za-z]:[\\/]+Users[\\/]+)[^/\\\s\"']+",
                  lambda match: match.group(1) + "<user>", text)
    for name in sorted(users, key=len, reverse=True):
        text = re.sub(rf"(?<![\w]){re.escape(name)}(?![\w])", "<user>", text)
    return text


def read_log_tail(root: str | None = None, max_lines: int = LOG_TAIL_LINES) -> str:
    """The newest lines of the crash log (empty if missing or a symlink)."""
    root = os.path.abspath(os.path.expanduser(root or config.SAVE_DIR))
    if os.path.islink(root):
        return ""
    return read_text_tail(os.path.join(root, CRASH_LOG), max_lines)


def read_text_tail(path: str, max_lines: int = LOG_TAIL_LINES) -> str:
    """The newest lines of a text file (empty if missing or a symlink)."""
    try:
        if os.path.islink(path):
            return ""
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - LOG_TAIL_BYTES))
            data = handle.read()
    except OSError:
        return ""
    lines = data.decode("utf-8", "replace").splitlines()
    if len(data) >= LOG_TAIL_BYTES and lines:
        lines = lines[1:]  # the first line was cut in the middle
    return "\n".join(lines[-max_lines:])


def last_exception(log: str) -> str:
    """The last ``SomeError: message`` line of a traceback in the log, or ''."""
    for line in reversed(log.splitlines()):
        match = _EXCEPTION_LINE.match(line.strip())
        if match:
            return match.group(1)[:FIELD_MAX_CHARS]
    return ""


def platform_line() -> str:
    try:
        import pygame
        pygame_version = pygame.version.ver
    except ImportError:
        pygame_version = "-"
    system = platform.system() or "?"
    machine = platform.machine() or "?"
    return (f"{system} {platform.release()} {machine}, Python "
            f"{platform.python_version()}, pygame {pygame_version}")[:FIELD_MAX_CHARS]


def _field(text: str) -> str:
    return " ".join(anonymize(str(text)).split())[:FIELD_MAX_CHARS]


def _title(exception: str) -> str:
    title = f"U-Jagd {APP_VERSION}: "
    return title + (exception[:80] if exception else "Fehlerbericht / bug report")


def _url(fields: dict[str, str]) -> str:
    return NEW_ISSUE_URL + "?" + urlencode(fields, quote_via=quote)


def issue_url(context: str = "", log: str | None = None,
              max_chars: int = URL_MAX_CHARS) -> str:
    """New-issue URL with the newest log lines that fit ``max_chars``."""
    log = anonymize(read_log_tail() if log is None else log)
    fields = {"template": ISSUE_TEMPLATE, "title": _field(_title(last_exception(log))),
              "version": APP_VERSION, "platform": _field(platform_line()),
              "context": _field(context)}
    lines = log.splitlines()
    while True:
        url = _url({**fields, "log": "\n".join(lines)} if lines else fields)
        if len(url) <= max_chars or not lines:
            return url
        # Drop the oldest lines first; the newest hold the crash.
        lines = lines[max(1, len(lines) // 8):]


def short_issue_url(context: str = "", max_chars: int = QR_URL_MAX_CHARS) -> str:
    """New-issue URL without the log, short enough for the QR code."""
    fields = {"template": ISSUE_TEMPLATE, "version": APP_VERSION,
              "platform": _field(f"{platform.system()} {platform.machine()}"),
              "context": _field(context)}
    while len(_url(fields)) > max_chars and fields["context"]:
        fields["context"] = fields["context"][:-4]
    if not fields["context"]:
        del fields["context"]
    return _url(fields)


def report_text(context: str = "", log: str | None = None) -> str:
    """The whole report as plain text, for ``bug-report.txt``."""
    log = anonymize(read_log_tail() if log is None else log)
    return (f"U-Jagd bug report\n"
            f"Version: {APP_VERSION}\n"
            f"Platform: {_field(platform_line())}\n"
            f"Context: {_field(context) or '-'}\n"
            f"Issue: {NEW_ISSUE_URL}?template={ISSUE_TEMPLATE}\n"
            f"\n--- {CRASH_LOG} (newest lines, user paths removed) ---\n"
            f"{log or '(empty)'}\n")


def write_report(text: str, root: str | None = None) -> str | None:
    """Atomically write ``bug-report.txt``; its path, or None on failure."""
    root = os.path.abspath(os.path.expanduser(root or config.SAVE_DIR))
    path = os.path.join(root, REPORT_FILE)
    staging = path + ".tmp"
    try:
        if os.path.lexists(root) and os.path.islink(root):
            return None
        os.makedirs(root, mode=0o700, exist_ok=True)
        if os.path.islink(path) or os.path.islink(staging):
            return None
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(staging, flags, 0o600), "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    except OSError:
        try:
            os.unlink(staging)
        except OSError:
            pass
        return None
    return path


def display_path(path: str) -> str:
    """``path`` as shown on screen, with the home directory as ``~``."""
    return anonymize(path)
