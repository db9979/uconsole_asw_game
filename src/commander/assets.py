"""Static Remote Crew web assets: one manifest shared by the server and tests.

The browser client is a fixed set of top-level files plus the ``css/``,
``js/`` and ``fonts/`` trees under the ``data.commander`` package. Every file
is read once at listener start into an exact ``route -> (mime, bytes)`` map;
nothing is resolved from request paths at run time.
"""
from __future__ import annotations

import re
from importlib import resources
from importlib.resources.abc import Traversable

from src.core.version import APP_VERSION

_JS = "text/javascript; charset=utf-8"
_CSS = "text/css; charset=utf-8"
_HTML = "text/html; charset=utf-8"
_COLOR_SCHEME_META = b'<meta name="color-scheme" content="dark">'

# Extension allowlist for the asset trees; anything else is never served.
MIME_TYPES = {".js": _JS, ".css": _CSS, ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}
ASSET_TREES = ("css", "js", "fonts")
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}").fullmatch
_FILE = re.compile(r"([a-z0-9][a-z0-9_.-]{0,63})(\.[a-z0-9]+)").fullmatch
_MAX_DEPTH = 3
_MAX_FILES = 256
_MAX_FILE_BYTES = 4 * 1024 * 1024

# Top-level files of the public crew page.
PUBLIC_FILES = (
    ("/", "index.html", _HTML),
    # The phone lookout (binoculars or periscope, gyroscope and voice).
    ("/lookout", "lookout.html", _HTML),
    ("/sonar-audio-worklet.js", "sonar-audio-worklet.js", _JS),
    ("/manual.css", "manual.css", _CSS),
)
# Files only served by the authenticated web-host room (admin page and voice).
WEB_HOST_FILES = (
    ("/admin", "admin.html", _HTML),
    ("/admin.js", "admin.js", _JS),
    ("/admin.css", "admin.css", _CSS),
    ("/voice-worklet.js", "voice-worklet.js", _JS),
    ("/voice.js", "voice.js", _JS),
)


def _walk(node: Traversable, prefix: str, depth: int, out: dict) -> None:
    for child in sorted(node.iterdir(), key=lambda item: item.name):
        name = child.name
        if child.is_dir():
            if name == "__pycache__":
                continue
            if depth >= _MAX_DEPTH or not _SEGMENT(name):
                raise ValueError(f"invalid Commander asset directory {prefix}{name}")
            _walk(child, f"{prefix}{name}/", depth + 1, out)
            continue
        match = _FILE(name)
        if name == "__init__.py" or not match:
            continue
        mime = MIME_TYPES.get(match.group(2))
        if mime is None:
            continue
        body = child.read_bytes()
        if len(body) > _MAX_FILE_BYTES:
            raise ValueError(f"Commander asset too large: {prefix}{name}")
        out[f"/{prefix}{name}"] = (mime, body)
        if len(out) > _MAX_FILES:
            raise ValueError("too many Commander assets")


def tree_assets(root: Traversable | None = None) -> dict[str, tuple[str, bytes]]:
    """Every allowlisted file below the ``css/``, ``js/`` and ``fonts/`` trees."""
    root = resources.files("data.commander") if root is None else root
    out: dict[str, tuple[str, bytes]] = {}
    for tree in ASSET_TREES:
        node = root.joinpath(tree)
        if node.is_dir():
            _walk(node, f"{tree}/", 1, out)
    return out


def static_assets(web_host: bool, root: Traversable | None = None) -> dict[str, tuple[str, bytes]]:
    """The complete static route table for one listener."""
    root = resources.files("data.commander") if root is None else root
    assets = {route: (mime, root.joinpath(name).read_bytes())
              for route, name, mime in PUBLIC_FILES}
    assets.update(tree_assets(root))
    # The page names the version it belongs to; the client compares it with
    # the host's X-U-Jagd-Version header and reloads after a host update.
    mime, page = assets["/"]
    assets["/"] = (mime, page.replace(
        _COLOR_SCHEME_META,
        _COLOR_SCHEME_META + b'\n  <meta name="u-jagd-version" content="'
        + APP_VERSION.encode("ascii") + b'">', 1))
    if web_host:
        assets.update({route: (mime, root.joinpath(name).read_bytes())
                       for route, name, mime in WEB_HOST_FILES})
    else:
        # The local uConsole crew listener has no web-admin voice option.
        mime, page = assets["/"]
        page = page.replace(b'<script src="./voice.js" defer></script>', b'')
        page = re.sub(rb'\s*<div class="voice-controls"[^\n]*</div>', b'', page)
        assets["/"] = (mime, page)
    return assets
