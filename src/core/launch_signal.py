"""Tells the uConsole launcher's start window that the game is visible.

The launcher (``packaging/uconsole/u_jagd_updater.py``) passes the write end
of the start window's pipe as ``U_JAGD_SPLASH_FD``; closing it after the first
presented frame closes that window.  Without the variable this does nothing.
It never touches simulation state.
"""

from __future__ import annotations

import os

_ENV = "U_JAGD_SPLASH_FD"
_done = False


def game_visible() -> None:
    """Close the launcher's start window once; cheap on every later call."""
    global _done
    if _done:
        return
    _done = True
    value = os.environ.pop(_ENV, "")
    if not value.isdigit():
        return
    try:
        os.close(int(value))
    except OSError:
        pass
