"""AIS Stream (wss://stream.aisstream.io) Client.

Läuft in einem eigenen Daemon-Thread mit einer eigenen asyncio-Event-Loop
(``asyncio.run``); der Rest des Spiels bleibt synchron. Empfangene
PositionReport-/ShipStaticData-Nachrichten werden zu flachen dicts
normalisiert und über eine thread-sichere ``queue.Queue`` an den
Pygame-Hauptthread übergeben (siehe ``LiveTrafficManager.pump``).

Robust gegen Verbindungsabbrüche: automatischer Reconnect mit exponentiellem
Backoff (1s..30s). Alle Ausnahmen werden im Thread abgefangen; ein
Netzwerkfehler bringt niemals das Spiel zum Absturz.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
_MAX_BACKOFF_S = 30.0
_MIN_BACKOFF_S = 1.0


class AisStreamClient:
    """Abonniert eine Bounding Box beim AIS-Stream-Dienst.

    ``bounding_box`` ist ``((lat_min, lon_min), (lat_max, lon_max))``.
    Normalisierte Reports landen in ``self.reports`` (queue.Queue), Format:
    ``{"mmsi": int, "lat": float, "lon": float, "cog": float | None,
       "sog": float | None, "heading": float | None, "ship_type": int | None,
       "name": str | None, "ts": float}``.
    """

    def __init__(self, api_key: str, bounding_box, *, queue_size: int = 512) -> None:
        self.api_key = api_key
        self.bounding_box = bounding_box
        self.reports: "queue.Queue[dict]" = queue.Queue(maxsize=queue_size)
        self.connected = False
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="ais-stream", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self.connected = False

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as exc:  # pragma: no cover - defensive last resort
            self.last_error = str(exc)
            self.connected = False

    async def _run(self) -> None:
        import websockets

        backoff = _MIN_BACKOFF_S
        subscribe_message = json.dumps({
            "APIKey": self.api_key,
            "BoundingBoxes": [[list(self.bounding_box[0]), list(self.bounding_box[1])]],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        })
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                        AISSTREAM_URL, open_timeout=10, close_timeout=2) as ws:
                    await ws.send(subscribe_message)
                    self.connected = True
                    self.last_error = None
                    backoff = _MIN_BACKOFF_S
                    while not self._stop.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue
                        self._handle_message(raw)
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(_MAX_BACKOFF_S, backoff * 2.0)

    def _handle_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        msg_type = payload.get("MessageType")
        meta = payload.get("MetaData") or {}
        mmsi = meta.get("MMSI")
        if mmsi is None:
            return
        message = (payload.get("Message") or {}).get(msg_type) or {}
        report: dict = {
            "mmsi": int(mmsi),
            "lat": meta.get("latitude"),
            "lon": meta.get("longitude"),
            "name": (meta.get("ShipName") or "").strip() or None,
            "ts": time.time(),
        }
        if msg_type == "PositionReport":
            report["cog"] = message.get("Cog")
            report["sog"] = message.get("Sog")
            report["heading"] = message.get("TrueHeading")
        elif msg_type == "ShipStaticData":
            report["ship_type"] = message.get("Type")
        else:
            return
        if report.get("lat") is None or report.get("lon") is None:
            if msg_type != "ShipStaticData":
                return
        try:
            self.reports.put_nowait(report)
        except queue.Full:
            try:
                self.reports.get_nowait()
            except queue.Empty:
                pass
            try:
                self.reports.put_nowait(report)
            except queue.Full:
                pass
