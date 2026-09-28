"""Crash log: what ended the game, written to ``~/.u-jagd/crash.log``.

Started from the uConsole menu entry the game has no terminal, so a Python
traceback or a fatal signal would otherwise vanish.  ``install()`` appends a
start line, turns on :mod:`faulthandler` for hard faults (segfaults in SDL or
the mixer, aborts, SIGTERM) and logs exceptions escaping a thread.
``record_exception()`` appends the traceback of an exception that ends the
game, and ``finish()`` appends the end line.  A start line without an end
line therefore means the process was killed outright (for example by the
kernel's out-of-memory killer, see ``dmesg``).

The file is bounded (truncated when it outgrows ``CRASH_LOG_MAX_BYTES``) and,
like the other diagnostic logs, never written through a symlink.  Nothing here
touches the simulation.
"""

from __future__ import annotations

import faulthandler
import os
import platform
import signal
import sys
import threading
import time
import traceback

from src.core import config
from src.core.debuglog import append_bounded_log
from src.core.version import APP_VERSION

CRASH_LOG = "crash.log"
CRASH_LOG_MAX_BYTES = 256 * 1024


class CrashSession:
    """Open crash-log state of one game launch."""

    def __init__(self, root: str, fault_file, previous_thread_hook):
        self.root = root
        self.fault_file = fault_file
        self.previous_thread_hook = previous_thread_hook
        self.fault_was_enabled = False


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append(root: str, text: str) -> None:
    append_bounded_log(root, CRASH_LOG, text, CRASH_LOG_MAX_BYTES)


def _open_fault_file(root: str):
    """Append-only handle for faulthandler, or None (symlink or I/O error)."""
    path = os.path.join(root, CRASH_LOG)
    try:
        if os.path.islink(root) or os.path.islink(path):
            return None
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        return os.fdopen(os.open(path, flags, 0o600), "a", encoding="utf-8")
    except OSError:
        return None


def install(root: str | None = None) -> CrashSession:
    """Start crash logging for this launch (call once, before the game)."""
    root = os.path.abspath(os.path.expanduser(root or config.SAVE_DIR))
    _append(root, f"=== {_stamp()} U-Jagd {APP_VERSION} started (pid {os.getpid()}, "
                  f"Python {platform.python_version()}, {platform.machine()})\n")
    was_enabled = faulthandler.is_enabled()
    fault_file = _open_fault_file(root)
    if fault_file is not None:
        faulthandler.enable(file=fault_file, all_threads=True)
        if hasattr(signal, "SIGTERM") and hasattr(faulthandler, "register"):
            # Dump the stacks, then terminate as SIGTERM would anyway.
            faulthandler.register(signal.SIGTERM, file=fault_file,
                                  all_threads=True, chain=True)
    previous = threading.excepthook

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            name = args.thread.name if args.thread is not None else "?"
            record_exception(args.exc_type, args.exc_value, args.exc_traceback,
                             root=root, where=f"thread {name}")
        previous(args)

    threading.excepthook = thread_hook
    session = CrashSession(root, fault_file, previous)
    session.fault_was_enabled = was_enabled
    return session


def record_exception(exc_type, exc_value, exc_tb, root: str | None = None,
                     where: str = "main loop") -> None:
    """Append the traceback of an exception to the crash log."""
    root = os.path.abspath(os.path.expanduser(root or config.SAVE_DIR))
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _append(root, f"--- {_stamp()} U-Jagd {APP_VERSION} crashed ({where}):\n{text}")


def finish(session: CrashSession, status: str) -> None:
    """Append the end line and undo ``install()``."""
    _append(session.root, f"=== {_stamp()} U-Jagd {APP_VERSION} ended: {status}\n")
    threading.excepthook = session.previous_thread_hook
    if session.fault_file is not None:
        if hasattr(signal, "SIGTERM") and hasattr(faulthandler, "unregister"):
            faulthandler.unregister(signal.SIGTERM)
        faulthandler.disable()
        try:
            session.fault_file.close()
        except OSError:
            pass
        if session.fault_was_enabled and sys.stderr is not None:
            try:
                faulthandler.enable(file=sys.stderr, all_threads=True)
            except (AttributeError, OSError, ValueError, RuntimeError):
                pass


def run_logged(start, root: str | None = None) -> int:
    """Run ``start()`` with crash logging; exceptions are logged and re-raised."""
    session = install(root)
    status = "normal"
    try:
        return start()
    except KeyboardInterrupt:
        status = "interrupted (Ctrl+C)"
        raise
    except SystemExit as exc:
        status = f"exit {exc.code}"
        raise
    except BaseException:
        status = "crash"
        record_exception(*sys.exc_info(), root=session.root)
        raise
    finally:
        finish(session, status)
