"""Small, separate voice-radio demo. Run with ``.venv/bin/python server.py``.

Voice traffic never enters the game simulation. ``RadioHub.talker`` is the
thread-safe value a Pygame UI can read once per frame.
"""

import asyncio
import hmac
import os
import secrets
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from websockets.exceptions import ConnectionClosed
from websockets.legacy.server import serve


STATIONS = ("bridge", "sonar", "navigation", "weapons", "radio",
            "esm", "engine", "damage", "helicopter")
FRAME_BYTES = 1920  # 20 ms of mono, signed 16-bit PCM at 48 kHz.
MAX_CLIENTS = len(STATIONS)


class RadioHub:
    def __init__(self, code: str):
        self.code = code
        self.clients = {}  # station -> (socket, bounded outgoing queue)
        self._talker = None
        self._lock = threading.Lock()

    @property
    def talker(self):
        """A detached string or None; safe for the Pygame main thread."""
        with self._lock:
            return self._talker

    def _set_talker(self, station):
        with self._lock:
            self._talker = station

    def _broadcast(self, message, *, except_station=None):
        for station, (_, outgoing) in self.clients.items():
            if station != except_station:
                try:
                    outgoing.put_nowait(message)
                except asyncio.QueueFull:
                    # Drop old voice when a receiver cannot keep up.
                    try:
                        outgoing.get_nowait()
                        outgoing.put_nowait(message)
                    except asyncio.QueueEmpty:
                        pass

    async def _writer(self, ws, outgoing):
        while True:
            await ws.send(await outgoing.get())

    async def handle(self, ws):
        station = None
        writer = None
        try:
            # First frame authenticates; there is no audio or status before it.
            import json
            raw = await asyncio.wait_for(ws.recv(), 5)
            if not isinstance(raw, str) or len(raw) > 256:
                await ws.close(code=1008)
                return
            hello = json.loads(raw)
            if (not isinstance(hello, dict) or set(hello) != {"type", "station", "code"}
                    or hello["type"] != "join" or hello["station"] not in STATIONS
                    or not isinstance(hello["code"], str)
                    or not hmac.compare_digest(hello["code"], self.code)
                    or hello["station"] in self.clients
                    or len(self.clients) >= MAX_CLIENTS):
                await ws.close(code=1008)
                return
            station = hello["station"]
            outgoing = asyncio.Queue(maxsize=8)
            self.clients[station] = (ws, outgoing)
            writer = asyncio.create_task(self._writer(ws, outgoing))
            await ws.send(json.dumps({"type": "ready", "station": station}))
            if self.talker is not None:
                outgoing.put_nowait(json.dumps({"type": "talker", "station": self.talker}))
            async for message in ws:
                if isinstance(message, bytes):
                    if len(message) != FRAME_BYTES:
                        await ws.close(code=1008)
                        break
                    if self.talker == station:
                        self._broadcast(bytes((STATIONS.index(station),)) + message,
                                        except_station=station)
                elif message == '"ptt_down"':
                    if self.talker is None:
                        self._set_talker(station)
                        self._broadcast(json.dumps({"type": "talker", "station": station}))
                elif message == '"ptt_up"':
                    if self.talker == station:
                        self._set_talker(None)
                        self._broadcast(json.dumps({"type": "talker", "station": None}))
                else:
                    await ws.close(code=1008)
                    break
        except (ConnectionClosed, asyncio.TimeoutError, ValueError, TypeError):
            pass
        finally:
            if station is not None:
                self.clients.pop(station, None)
                if self.talker == station:
                    self._set_talker(None)
                    self._broadcast('{"type":"talker","station":null}')
            if writer is not None:
                writer.cancel()


class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


async def main():
    host = os.environ.get("VOICE_HOST", "127.0.0.1")
    http_port = int(os.environ.get("VOICE_HTTP_PORT", "8765"))
    ws_port = int(os.environ.get("VOICE_WS_PORT", "8766"))
    code = os.environ.get("VOICE_CODE") or secrets.token_urlsafe(16)
    origin = os.environ.get("VOICE_ORIGIN", f"http://{host}:{http_port}")
    hub = RadioHub(code)
    http = ThreadingHTTPServer((host, http_port), StaticHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    print(f"Open {origin}/index.html ; radio code: {code}", flush=True)
    try:
        async with serve(hub.handle, host, ws_port, origins=[origin],
                         max_size=2048, max_queue=4, compression=None):
            await asyncio.Future()
    finally:
        http.shutdown()
        http.server_close()


if __name__ == "__main__":
    asyncio.run(main())
