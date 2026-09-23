"""Bounded client for the optional privileged uConsole hotspot helper."""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import json
import os
import queue
import re
import selectors
import subprocess
import threading
import time


HELPER_PATH = "/usr/libexec/u-jagd-hotspot-helper"
PKEXEC_PATH = "/usr/bin/pkexec"
_DEFAULT_COMMAND = (PKEXEC_PATH, "--disable-internal-agent", HELPER_PATH, "serve")
_MAX_MESSAGE_BYTES = 4096
_INTERFACE = re.compile(r"[a-zA-Z0-9_.:-]{1,32}\Z")
_PRIVATE_NETWORKS = tuple(ipaddress.IPv4Network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_ERROR_CODES = frozenset({
    "authorization", "busy", "dependency", "helper_missing", "no_address",
    "no_wifi", "protocol", "start", "timeout", "unsupported",
})


@dataclass(frozen=True, slots=True)
class HotspotDetails:
    ssid: str
    password: str = field(repr=False)
    address: str
    interface: str


class HotspotController:
    """Run one helper process without blocking the Pygame/main thread."""

    def __init__(self, *, command=None, startup_timeout=20.0, stop_timeout=9.0,
                 popen=subprocess.Popen):
        self._command = tuple(command or _DEFAULT_COMMAND)
        self._startup_timeout = float(startup_timeout)
        self._stop_timeout = float(stop_timeout)
        self._popen = popen
        self._events = queue.Queue(maxsize=4)
        self._stop_requested = threading.Event()
        self._thread = None
        self.state = "off"
        self.details = None
        self.error = None

    @property
    def available(self):
        if self._command != _DEFAULT_COMMAND:
            return True
        return (os.path.isfile(PKEXEC_PATH) and os.access(PKEXEC_PATH, os.X_OK)
                and os.path.isfile(HELPER_PATH) and os.access(HELPER_PATH, os.X_OK))

    @property
    def active(self):
        return self.state in ("starting", "running", "stopping")

    def start(self):
        """Begin activation and return immediately."""
        if self.active or (self._thread is not None and self._thread.is_alive()):
            return False
        self.details = None
        self.error = None
        if not self.available:
            self.state = "error"
            self.error = "helper_missing"
            return False
        self._stop_requested.clear()
        self.state = "starting"
        self._thread = threading.Thread(target=self._run, name="commander-hotspot",
                                        daemon=True)
        self._thread.start()
        return True

    def request_stop(self):
        """Request helper cleanup without waiting for NetworkManager."""
        alive = self._thread is not None and self._thread.is_alive()
        if not alive and self.state in ("off", "error"):
            return False
        self.state = "stopping"
        self._stop_requested.set()
        return True

    def poll(self):
        """Apply detached worker results on the main thread."""
        while True:
            try:
                kind, value = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "running" and not self._stop_requested.is_set():
                self.details = value
                self.error = None
                self.state = "running"
            elif kind == "stopped":
                self.details = None
                self.error = None
                self.state = "off"
            elif kind == "error":
                self.details = None
                self.error = value if value in _ERROR_CODES else "start"
                self.state = "error"
        return self.state

    def close(self):
        """Bound shutdown for the application's final cleanup path."""
        self.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(self._stop_timeout + 1.0)
        self.poll()
        if thread is not None and thread.is_alive():
            self.details = None
            self.error = "timeout"
            self.state = "error"

    def _emit(self, kind, value=None):
        try:
            self._events.put_nowait((kind, value))
        except queue.Full:
            # One worker emits at most running plus a terminal event.
            pass

    def _read_startup(self, process):
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + self._startup_timeout
        try:
            while not self._stop_requested.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, "timeout"
                if selector.select(min(0.1, remaining)):
                    line = process.stdout.readline(_MAX_MESSAGE_BYTES + 1)
                    if not line or len(line) > _MAX_MESSAGE_BYTES or not line.endswith(b"\n"):
                        return None, "protocol"
                    try:
                        payload = json.loads(line.decode("ascii"))
                    except (UnicodeError, json.JSONDecodeError):
                        return None, "protocol"
                    if not isinstance(payload, dict):
                        return None, "protocol"
                    if payload.get("status") == "error" and set(payload) == {"status", "code"}:
                        code = payload.get("code")
                        return None, code if code in _ERROR_CODES else "start"
                    return self._validate_details(payload), None
            return None, None
        finally:
            selector.close()

    @staticmethod
    def _validate_details(payload):
        if not isinstance(payload, dict) or set(payload) != {
                "status", "ssid", "password", "address", "interface"}:
            raise ValueError("invalid helper response")
        ssid, password = payload.get("ssid"), payload.get("password")
        address, interface = payload.get("address"), payload.get("interface")
        if (payload.get("status") != "running" or not isinstance(ssid, str)
                or not 1 <= len(ssid.encode("utf-8")) <= 32
                or not isinstance(password, str) or not 12 <= len(password) <= 64
                or any(ord(char) < 0x20 or ord(char) > 0x7e for char in ssid + password)
                or not isinstance(address, str) or not isinstance(interface, str)
                or _INTERFACE.fullmatch(interface) is None):
            raise ValueError("invalid helper response")
        parsed = ipaddress.IPv4Address(address)
        if not any(parsed in network for network in _PRIVATE_NETWORKS):
            raise ValueError("invalid helper response")
        return HotspotDetails(ssid=ssid, password=password, address=str(parsed),
                              interface=interface)

    @staticmethod
    def _finish_process(process, timeout):
        if process.stdin is not None and not process.stdin.closed:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                return process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                return process.wait(timeout=1.0)

    def _run(self):
        process = None
        expected_stop = False
        try:
            process = self._popen(
                self._command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, bufsize=0, close_fds=True)
            try:
                details, error = self._read_startup(process)
            except (OSError, ValueError):
                details, error = None, "protocol"
            if details is None:
                expected_stop = self._stop_requested.is_set()
                returncode = self._finish_process(process, self._stop_timeout)
                if not expected_stop:
                    if error == "protocol" and returncode in (126, 127):
                        error = "authorization"
                    self._emit("error", error or "start")
                if expected_stop:
                    self._emit("stopped")
                return
            self._emit("running", details)
            while not self._stop_requested.wait(0.1):
                if process.poll() is not None:
                    self._emit("error", "start")
                    return
            expected_stop = True
            returncode = self._finish_process(process, self._stop_timeout)
            self._emit("stopped" if returncode == 0 else "error",
                       None if returncode == 0 else "start")
        except (OSError, subprocess.SubprocessError):
            self._emit("error", "helper_missing" if process is None else "start")
        finally:
            if process is not None:
                if process.poll() is None:
                    self._finish_process(process, self._stop_timeout)
                for stream in (process.stdin, process.stdout):
                    if stream is not None and not stream.closed:
                        stream.close()
