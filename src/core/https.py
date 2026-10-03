"""HTTPS requests that verify certificates in the packaged programs too (1.3.173).

The Python inside the macOS app looks for root certificates in the folder of
the Python it was built with, which does not exist on a player's Mac: every
HTTPS request (update check, optional language model, live air traffic)
failed certificate verification. ``ssl_context()`` adds certifi's bundle
(packaged with the Windows and macOS programs) and macOS's own
``/etc/ssl/cert.pem`` to the default store, never in place of it, so a
system with its own certificates (a company proxy) keeps working.
"""

from __future__ import annotations

import os
import ssl
import sys
import threading
import urllib.request

_EXTRA_CA_FILES = ("/etc/ssl/cert.pem",) if sys.platform == "darwin" else ()
_lock = threading.Lock()
_context: ssl.SSLContext | None = None


def certifi_file() -> str | None:
    """certifi's bundle when it is installed, else ``None``."""
    try:
        import certifi
    except ImportError:
        return None
    path = certifi.where()
    return path if os.path.isfile(path) else None


def ca_files() -> tuple[str, ...]:
    """The extra root certificate files ``ssl_context()`` loads."""
    return tuple(path for path in (certifi_file(), *_EXTRA_CA_FILES)
                 if path and os.path.isfile(path))


def ssl_context() -> ssl.SSLContext:
    """The default client context plus ``ca_files()``; built once."""
    global _context
    with _lock:
        if _context is None:
            context = ssl.create_default_context()
            for path in ca_files():
                try:
                    context.load_verify_locations(cafile=path)
                except (OSError, ssl.SSLError):
                    pass
            _context = context
        return _context


def urlopen(request, timeout: float):
    """``urllib.request.urlopen`` with ``ssl_context()``."""
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())
