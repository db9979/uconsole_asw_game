"""Leichter Internet-Erreichbarkeits-Check, threaded und nicht blockierend.

Das Optionsmenü fragt ``ConnectivityMonitor.online`` jeden Frame ab; der
eigentliche Socket-Connect läuft in einem Daemon-Thread, damit ein
hängendes Netzwerk niemals die Spiel-Loop blockiert.
"""

from __future__ import annotations

import socket
import threading
import time

_PROBE_HOST = "1.1.1.1"
_PROBE_PORT = 443
_RECHECK_INTERVAL_S = 15.0


def check_internet_sync(timeout: float = 1.0) -> bool:
    """Ein einzelner, kurzer TCP-Connect-Versuch ohne DNS-Abhängigkeit."""
    try:
        with socket.create_connection((_PROBE_HOST, _PROBE_PORT), timeout=timeout):
            return True
    except OSError:
        return False


class ConnectivityMonitor:
    """Wiederholt ``check_internet_sync`` in einem Hintergrund-Thread.

    ``online`` ist ``None`` bis der erste Check durchgelaufen ist, danach
    ``True``/``False``. Nur der Worker-Thread schreibt ``online``, nur der
    Hauptthread liest es - kein Lock notwendig fuer diese einzelne Zuweisung.
    """

    def __init__(self, recheck_interval_s: float = _RECHECK_INTERVAL_S) -> None:
        self.online: bool | None = None
        self._recheck_interval_s = recheck_interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="connectivity-monitor", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self.online = check_internet_sync()
            self._stop.wait(self._recheck_interval_s)
