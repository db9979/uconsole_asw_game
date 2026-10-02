"""A tiny OpenAI-compatible chat server for the language-model tests.

It answers on 127.0.0.1 only; ``reply`` decides the answer text from the
request body (a str, or a callable taking the parsed body that returns the
text, a whole message dict, or an int HTTP status to refuse with).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLlmServer:
    def __init__(self, reply="OK", *, status: int = 200, delay_s: float = 0.0):
        self.reply = reply
        self.status = status
        self.delay_s = delay_s
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append(body)
                owner.headers.append(dict(self.headers))
                if owner.delay_s:
                    threading.Event().wait(owner.delay_s)
                if self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                if owner.status != 200:
                    self.send_response(owner.status)
                    self.end_headers()
                    return
                text = owner.reply(body) if callable(owner.reply) else owner.reply
                if isinstance(text, int):
                    self.send_response(text)
                    self.end_headers()
                    return
                message = (text if isinstance(text, dict)
                           else {"role": "assistant", "content": text})
                payload = json.dumps({"choices": [{"message": message}]})
                data = payload.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
