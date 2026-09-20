"""OpenSky Network REST-Client (https://opensky-network.org/api/states/all).

Stdlib-only (``urllib``), passend zur bestehenden Projekt-Konvention
(siehe ``src/data/wiki_import.py``). Läuft in einem normalen
``threading.Thread``-Polling-Loop; kein asyncio notwendig, da REST/Polling.

Ohne Zugangsdaten wird anonym (stark ratenlimitiert) abgefragt. Mit
``client_id:client_secret`` wird zunächst ein OAuth2-Client-Credentials-Token
geholt (neues OpenSky-Auth-Schema seit 2024) und als Bearer-Token verwendet.
"""

from __future__ import annotations

import json
import queue
import random
import threading
import time
import urllib.parse
import urllib.request

STATES_URL = "https://opensky-network.org/api/states/all"
TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/opensky-network/"
             "protocol/openid-connect/token")
_MAX_BACKOFF_S = 60.0
_MIN_BACKOFF_S = 5.0
_REQUEST_TIMEOUT_S = 10.0


class OpenSkyClient:
    """Pollt Zustandsvektoren fuer eine Bounding Box in festem Intervall.

    ``bounding_box`` ist ``((lat_min, lon_min), (lat_max, lon_max))``.
    ``credentials`` ist ``"client_id:client_secret"`` oder leer (anonym).
    Jeder erfolgreiche Poll legt ``(timestamp, states)`` in ``self.snapshots``
    ab (queue_size klein, nur der neueste Snapshot ist relevant).
    """

    def __init__(self, credentials: str, bounding_box, *,
                 interval_s: float = 20.0, jitter_s: float = 5.0) -> None:
        self.credentials = (credentials or "").strip()
        self.bounding_box = bounding_box
        self.interval_s = interval_s
        self.jitter_s = jitter_s
        self.snapshots: "queue.Queue[tuple[float, list]]" = queue.Queue(maxsize=4)
        self.connected = False
        self.last_error: str | None = None
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="opensky-adsb", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self.connected = False

    def _run(self) -> None:
        backoff = _MIN_BACKOFF_S
        while not self._stop.is_set():
            try:
                states = self._fetch_states()
                self.connected = True
                self.last_error = None
                backoff = _MIN_BACKOFF_S
                self._publish(states)
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                self._stop.wait(backoff)
                backoff = min(_MAX_BACKOFF_S, backoff * 2.0)
                continue
            sleep_s = self.interval_s + random.uniform(-self.jitter_s, self.jitter_s)
            self._stop.wait(max(1.0, sleep_s))

    def _publish(self, states: list) -> None:
        snapshot = (time.time(), states)
        try:
            self.snapshots.put_nowait(snapshot)
        except queue.Full:
            try:
                self.snapshots.get_nowait()
            except queue.Empty:
                pass
            try:
                self.snapshots.put_nowait(snapshot)
            except queue.Full:
                pass

    def _fetch_states(self) -> list:
        (lat_min, lon_min), (lat_max, lon_max) = self.bounding_box
        params = urllib.parse.urlencode({
            "lamin": lat_min, "lomin": lon_min,
            "lamax": lat_max, "lomax": lon_max,
        })
        request = urllib.request.Request(f"{STATES_URL}?{params}")
        token = self._ensure_token()
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("states") or []

    def _ensure_token(self) -> str | None:
        if not self.credentials or ":" not in self.credentials:
            return None
        if self._token is not None and time.time() < self._token_expires_at - 30.0:
            return self._token
        client_id, _, client_secret = self.credentials.partition(":")
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("ascii")
        request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload.get("expires_in", 1800))
        return self._token


def test_connection(credentials: str, bounding_box) -> tuple[bool, str | None]:
    """Einmaliger, blockierender Verbindungstest fuer den Optionen-Dialog.

    Fragt einmal ``STATES_URL`` fuer die Bounding Box ab (inkl. OAuth2-Token-
    Beschaffung, falls Zugangsdaten hinterlegt sind) und liefert
    ``(erfolgreich, fehlertext)``.
    """
    probe = OpenSkyClient(credentials, bounding_box)
    try:
        probe._fetch_states()
        return True, None
    except Exception as exc:
        return False, str(exc)
