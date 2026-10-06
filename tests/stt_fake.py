"""A tiny OpenAI-compatible transcription server for the speech-input tests.

It answers on 127.0.0.1 only.  ``reply`` decides the answer from the parsed
form (a dict of text fields plus ``"file"`` with the uploaded bytes): a
str (sent as ``{"text": ...}``), a dict (sent as JSON), bytes (sent as they
are) or an int HTTP status to refuse with.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_form(content_type: str, body: bytes) -> dict:
    boundary = content_type.split("boundary=", 1)[1].encode("ascii")
    form = {}
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        disposition = head.decode("utf-8").split("\r\n")[0]
        name = disposition.split('name="', 1)[1].split('"', 1)[0]
        form[name] = data if 'filename="' in disposition else data.decode("utf-8")
    return form


class FakeSttServer:
    def __init__(self, reply="Wo ist der Kontakt?", *, delay_s: float = 0.0):
        self.reply = reply
        self.delay_s = delay_s
        self.forms: list[dict] = []
        self.headers: list[dict] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                form = parse_form(self.headers.get("Content-Type", ""), body)
                owner.forms.append(form)
                owner.headers.append(dict(self.headers))
                if owner.delay_s:
                    threading.Event().wait(owner.delay_s)
                if self.path != "/v1/audio/transcriptions":
                    self.send_response(404)
                    self.end_headers()
                    return
                answer = owner.reply(form) if callable(owner.reply) else owner.reply
                if isinstance(answer, int):
                    self.send_response(answer)
                    self.end_headers()
                    return
                if isinstance(answer, bytes):
                    data, kind = answer, "text/plain"
                else:
                    data = json.dumps(answer if isinstance(answer, dict)
                                      else {"text": answer}).encode("utf-8")
                    kind = "application/json"
                self.send_response(200)
                self.send_header("Content-Type", kind)
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
