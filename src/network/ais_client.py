"""AIS Stream (wss://stream.aisstream.io) Client.

Läuft in einem eigenen Daemon-Thread mit einer eigenen asyncio-Event-Loop
(``asyncio.run``); der Rest des Spiels bleibt synchron. Empfangene
Positions- und statische Schiffsnachrichten werden zu flachen dicts
normalisiert und über eine thread-sichere ``queue.Queue`` an den
Pygame-Hauptthread übergeben (siehe ``LiveTrafficManager.pump``).

Robust gegen Verbindungsabbrüche: automatischer Reconnect mit exponentiellem
Backoff (1s..30s). Alle Ausnahmen werden im Thread abgefangen; ein
Netzwerkfehler bringt niemals das Spiel zum Absturz.
"""

from __future__ import annotations

import asyncio
import json
import math
import queue
import threading
import time

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
_MAX_BACKOFF_S = 30.0
_MIN_BACKOFF_S = 1.0

_POSITION_MESSAGE_TYPES = frozenset({
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "LongRangeAisBroadcastMessage",
})
_SUBSCRIPTION_MESSAGE_TYPES = tuple(sorted(
    (*_POSITION_MESSAGE_TYPES, "ShipStaticData", "StaticDataReport")))


def _number(value, minimum: float, maximum: float) -> float | None:
    """Return a finite number inside the AIS field's useful range."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and minimum <= value <= maximum else None


def _integer(value, minimum: int, maximum: int) -> int | None:
    """Strict integer normalizer; JSON booleans are not integer values here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if converted != value or not minimum <= converted <= maximum:
        return None
    return converted


def _text(value, maximum: int) -> str | None:
    """Normalize bounded AIS six-bit text, including its ``@`` padding."""
    if not isinstance(value, str):
        return None
    value = value.strip(" @\x00")
    return value[:maximum] or None


def _dimensions(value) -> tuple[float | None, float | None]:
    if not isinstance(value, dict):
        return None, None
    a = _number(value.get("A"), 0.0, 1000.0)
    b = _number(value.get("B"), 0.0, 1000.0)
    c = _number(value.get("C"), 0.0, 200.0)
    d = _number(value.get("D"), 0.0, 200.0)
    length = a + b if a is not None and b is not None and a + b > 0.0 else None
    width = c + d if c is not None and d is not None and c + d > 0.0 else None
    return length, width


class AisStreamClient:
    """Abonniert eine Bounding Box beim AIS-Stream-Dienst.

    ``bounding_box`` ist ``((lat_min, lon_min), (lat_max, lon_max))``.
    Normalisierte Reports landen in ``self.reports`` (queue.Queue), Format:
    ``{"mmsi": int, "lat": float, "lon": float, "cog": float | None,
       "sog": float | None, "heading": float | None, "ship_type": int | None,
       "name": str | None, "callsign": str | None, "imo": int | None,
       "destination": str | None, "draught_m": float | None,
       "length_m": float | None, "width_m": float | None, "ts": float}``.
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
            "FilterMessageTypes": list(_SUBSCRIPTION_MESSAGE_TYPES),
        })
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                        AISSTREAM_URL, open_timeout=10, close_timeout=2,
                        compression="deflate") as ws:
                    await ws.send(subscribe_message)
                    # A successful WebSocket handshake does not mean that the
                    # key/subscription was accepted.  AISStream sends an
                    # explicit SubscriptionConfirmation before live data.
                    self.connected = False
                    self.last_error = None
                    backoff = _MIN_BACKOFF_S
                    while not self._stop.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue
                        if self._handle_message(raw):
                            self.connected = True
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(_MAX_BACKOFF_S, backoff * 2.0)

    def _handle_message(self, raw: str) -> bool:
        """Normalize one frame; return whether it proves subscription success."""
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return False
        msg_type = payload.get("MessageType")
        if msg_type == "SubscriptionConfirmation":
            return True
        error = payload.get("error") or payload.get("Error")
        if error:
            self.last_error = str(error)
            return False
        meta = payload.get("MetaData") or {}
        messages = payload.get("Message") or {}
        if not isinstance(meta, dict) or not isinstance(messages, dict):
            return False
        message = messages.get(msg_type) or {}
        if not isinstance(message, dict):
            return False
        mmsi = _integer(meta.get("MMSI", message.get("UserID")), 1, 999999999)
        if mmsi is None:
            return False
        raw_latitude = meta.get("latitude", message.get("Latitude"))
        raw_longitude = meta.get("longitude", message.get("Longitude"))
        latitude = _number(raw_latitude, -90.0, 90.0)
        longitude = _number(raw_longitude, -180.0, 180.0)
        if ((raw_latitude is not None and latitude is None)
                or (raw_longitude is not None and longitude is None)):
            return False
        report: dict = {
            "mmsi": mmsi,
            "lat": latitude,
            "lon": longitude,
            "name": _text(meta.get("ShipName") or message.get("Name"), 128),
            "ts": time.time(),
        }
        if msg_type in _POSITION_MESSAGE_TYPES:
            report["cog"] = _number(message.get("Cog"), 0.0, 360.0)
            report["sog"] = _number(message.get("Sog"), 0.0, 102.3)
            report["heading"] = _integer(message.get("TrueHeading"), 0, 359)
            accuracy = message.get("PositionAccuracy")
            report["position_accuracy"] = accuracy if isinstance(accuracy, bool) else None
            report["nav_status"] = _integer(
                message.get("NavigationalStatus"), 0, 15)
            if msg_type == "ExtendedClassBPositionReport":
                report["ship_type"] = _integer(message.get("Type"), 0, 99)
        elif msg_type == "ShipStaticData":
            report["ship_type"] = _integer(message.get("Type"), 0, 99)
            report["callsign"] = _text(message.get("CallSign"), 32)
            report["imo"] = _integer(message.get("ImoNumber"), 1, 99999999)
            report["destination"] = _text(message.get("Destination"), 128)
            report["draught_m"] = _number(
                message.get("MaximumStaticDraught"), 0.1, 100.0)
            report["length_m"], report["width_m"] = _dimensions(
                message.get("Dimension"))
        elif msg_type == "StaticDataReport":
            part_a = message.get("ReportA") or {}
            part_b = message.get("ReportB") or {}
            if not isinstance(part_a, dict) or not isinstance(part_b, dict):
                return False
            report["name"] = report["name"] or _text(part_a.get("Name"), 128)
            report["callsign"] = _text(part_b.get("CallSign"), 32)
            report["ship_type"] = _integer(part_b.get("ShipType"), 0, 99)
            report["length_m"], report["width_m"] = _dimensions(
                part_b.get("Dimension"))
        else:
            return False
        if report.get("lat") is None or report.get("lon") is None:
            if msg_type not in {"ShipStaticData", "StaticDataReport"}:
                return False
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
        return True


def test_connection(api_key: str, bounding_box, timeout: float = 6.0) -> tuple[bool, str | None]:
    """Einmaliger, blockierender Verbindungstest fuer den Optionen-Dialog.

    Verbindet, abonniert die Bounding Box und wartet kurz auf die erste
    Nachricht oder eine Fehlermeldung vom Dienst. Laeuft im aufrufenden
    Thread synchron (also von der UI in einem eigenen Hintergrund-Thread zu
    starten) und liefert ``(erfolgreich, fehlertext)``.
    """
    import asyncio

    async def _probe() -> tuple[bool, str | None]:
        import websockets

        subscribe_message = json.dumps({
            "APIKey": api_key,
            "BoundingBoxes": [[list(bounding_box[0]), list(bounding_box[1])]],
            "FilterMessageTypes": list(_SUBSCRIPTION_MESSAGE_TYPES),
        })
        async with websockets.connect(
                AISSTREAM_URL, open_timeout=timeout, close_timeout=2,
                compression="deflate") as ws:
            await ws.send(subscribe_message)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                return False, "no subscription confirmation received"
            try:
                payload = json.loads(raw)
            except (ValueError, TypeError):
                return False, "invalid response before subscription confirmation"
            error = payload.get("error") or payload.get("Error")
            if error:
                return False, str(error)
            msg_type = payload.get("MessageType")
            if (msg_type == "SubscriptionConfirmation"
                    or msg_type in _POSITION_MESSAGE_TYPES
                    or msg_type in {"ShipStaticData", "StaticDataReport"}):
                return True, None
            return False, "unexpected response before subscription confirmation"

    try:
        return asyncio.run(_probe())
    except Exception as exc:
        return False, str(exc)
