"""Separate helper process that traces ray tables ahead of need.

``raytrace.prefetch`` asks for tables the sensors will need soon.  Python
runs one thread of the game at a time, so a thread could only take turns
with the game; this helper is its own process (``python -m
src.sonar.raytrace_worker``) on another core, at a lower scheduling
priority.  It runs exactly ``raytrace.trace_table`` on the same arguments,
so its tables are the ones the game would build itself.

Protocol over the helper's stdin/stdout: each request is a 4-byte
big-endian length and a JSON object (``id``, ``source``, ``depths``,
``speeds``, ``water``, ``sediment``, ``wind``); each answer a 4-byte length,
a JSON header (``id``, ``shape`` or ``error``) and, on success, the table's
float64 bytes.  JSON writes floats exactly (shortest round-trip repr).

Where no helper can be started (a frozen build, no ``sys.executable``, a
platform without processes) ``TraceWorker.start`` returns None and
``raytrace.service`` traces in slices on the game thread instead.
"""

from __future__ import annotations

import json
import os
import queue
import struct
import subprocess
import sys
import threading

import numpy as np

_LENGTH = struct.Struct(">I")
MAX_MESSAGE = 16 * 1024 * 1024
WAIT_TIMEOUT_S = 60.0


def _read_exact(stream, size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            return None
        data += chunk
    return bytes(data)


def _read_message(stream) -> bytes | None:
    head = _read_exact(stream, _LENGTH.size)
    if head is None:
        return None
    (size,) = _LENGTH.unpack(head)
    if size > MAX_MESSAGE:
        return None
    return _read_exact(stream, size)


def _write_message(stream, payload: bytes) -> None:
    stream.write(_LENGTH.pack(len(payload)) + payload)


def serve(stdin=None, stdout=None) -> int:
    """The helper's main loop: trace every request until stdin closes."""
    from src.sonar.raytrace import trace_table

    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    while True:
        raw = _read_message(stdin)
        if raw is None:
            return 0
        try:
            request = json.loads(raw)
            table = np.ascontiguousarray(trace_table(
                request["source"], request["depths"], request["speeds"],
                request["water"], request["sediment"], request["wind"]),
                dtype=np.float64)
            header = {"id": request["id"], "shape": list(table.shape)}
            _write_message(stdout, json.dumps(header).encode("ascii"))
            _write_message(stdout, table.tobytes())
        except Exception as exc:  # noqa: BLE001 - answer, never die silently
            ident = request.get("id") if isinstance(request, dict) else None
            _write_message(stdout, json.dumps({"id": ident, "error": type(exc).__name__})
                           .encode("ascii"))
        stdout.flush()


class TraceWorker:
    """The game's side of the helper: submit, collect, wait."""

    MAX_IN_FLIGHT = 2

    def __init__(self, process: subprocess.Popen):
        self._process = process
        self._results: "queue.Queue" = queue.Queue()
        self._done: dict = {}
        self._next_id = 0
        self.in_flight: dict = {}           # key -> request id
        self.alive = True
        self._reader = threading.Thread(target=self._read, name="u-jagd-raytrace-reader",
                                        daemon=True)
        self._reader.start()

    @classmethod
    def start(cls) -> "TraceWorker | None":
        if getattr(sys, "frozen", False) or not sys.executable:
            return None
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env = dict(os.environ)
        env["PYTHONPATH"] = root + (os.pathsep + env["PYTHONPATH"]
                                    if env.get("PYTHONPATH") else "")
        flags = {}
        if os.name == "nt":
            flags["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                      | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "src.sonar.raytrace_worker"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, cwd=root, env=env, **flags)
        except (OSError, ValueError):
            return None
        return cls(process)

    def _read(self) -> None:
        stream = self._process.stdout
        while True:
            raw = _read_message(stream)
            if raw is None:
                break
            try:
                header = json.loads(raw)
            except ValueError:
                break
            if "error" in header:
                self._results.put((header.get("id"), None))
                continue
            body = _read_message(stream)
            if body is None:
                break
            try:
                table = np.frombuffer(body, dtype=np.float64).reshape(header["shape"])
            except (ValueError, TypeError, KeyError):
                break
            self._results.put((header["id"], table))
        self.alive = False
        self._results.put((None, None))

    def submit(self, key: tuple, source: float, depths, speeds, water: float,
               sediment: str, wind: float) -> bool:
        if not self.alive or key in self.in_flight:
            return False
        self._next_id += 1
        request = {"id": self._next_id, "source": source,
                   "depths": [float(value) for value in depths],
                   "speeds": [float(value) for value in speeds],
                   "water": water, "sediment": sediment, "wind": wind}
        try:
            _write_message(self._process.stdin, json.dumps(request).encode("ascii"))
            self._process.stdin.flush()
        except (OSError, ValueError):
            self.alive = False
            return False
        self.in_flight[key] = self._next_id
        return True

    def _settle(self, ident, table) -> None:
        for key, request in list(self.in_flight.items()):
            if request == ident:
                del self.in_flight[key]
                self._done[key] = table
                return

    def poll(self) -> list:
        """Finished ``(key, table or None)`` pairs, without waiting."""
        while True:
            try:
                ident, table = self._results.get_nowait()
            except queue.Empty:
                break
            if ident is not None:
                self._settle(ident, table)
        if not self.alive:
            for key in list(self.in_flight):
                self._done[key] = None
            self.in_flight.clear()
        done, self._done = list(self._done.items()), {}
        return done

    def wait(self, key: tuple):
        """Block until the table of ``key`` (in flight) arrives; None if the
        helper failed.  Other finished tables wait in ``poll``."""
        while key in self.in_flight and self.alive:
            try:
                ident, table = self._results.get(timeout=WAIT_TIMEOUT_S)
            except queue.Empty:
                self.close()
                break
            if ident is not None:
                self._settle(ident, table)
        if key in self._done:
            return self._done.pop(key)
        self.in_flight.pop(key, None)
        return None

    def close(self) -> None:
        self.alive = False
        try:
            self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            self._process.kill()


def main() -> int:
    if hasattr(os, "nice"):
        try:
            os.nice(5)          # the game keeps its core first
        except OSError:
            pass
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
