"""Sonar-audio soak test: continuity of the local mixer and Remote Crew streams.

Offline diagnostics tool, not a runtime resource. Two modes:

``host`` runs the real game loop (``Game.run``) headless on this machine with
``--clients`` simulated Remote Crew browsers: every audio role (frigate sonar,
boat sonar, helicopter) consumes its WebSocket PCM stream, the other roles poll
state at 2 Hz, and the host's own input advances the world epoch every
``--bump-every`` seconds (the case that used to silence browsers). The local
mixer plays the frigate's sonar room at the same time (``--dummy-audio`` for
CI). The summary reports frame time, catch-up, local underruns, mixer idle
events, and per-stream gaps and arrival jitter; the exit code is non-zero on
any audible defect.

``client`` pairs with a running game from another machine (a PC on the Wi-Fi
the browsers use), waits until the host grants an audio station in F9, and
measures that stream's continuity over the real network.

Everything the host mode writes (settings, saves, debug logs) goes to a
temporary directory; the user's ``~/.u-jagd`` is never touched.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import socket
import statistics
import struct
import sys
import threading
import time
from contextlib import closing
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

AUDIO_ROLES = ("sonar", "uboot_sonar", "helicopter")
AUDIO_ROUTES = {"sonar": "sonar", "helicopter": "helicopter", "uboot_sonar": "uboot"}
BLOCK_S = 0.25
# A missing block longer than the browser's standing lead is an audible gap.
GAP_S = 2.0
SILENCE_S = 0.75


class Session:
    """One paired protocol-v2 client (cookie, CSRF token, client id)."""

    def __init__(self, host: str, port: int, name: str, code: str):
        self.host, self.port, self.name = host, port, name
        status, headers, body = self.request("/api/v2/pair", "POST",
                                             {"code": code, "name": name})
        if status != 200:
            raise RuntimeError(f"pairing failed for {name}: {status} {body}")
        token = headers["Set-Cookie"].split(";", 1)[0]
        self.cookie = token
        self.csrf = body["csrf"]
        self.client_id = body["client_id"]
        self.station = None
        self.poll_errors = 0
        self.polls = 0
        self.poll_latency_ms: list[float] = []

    def request(self, path, method="GET", body=None, cookie=None):
        headers = {}
        if method == "POST":
            headers.update({"Origin": f"http://{self.host}:{self.port}",
                            "Content-Type": "application/json"})
        cookie = getattr(self, "cookie", None) if cookie is None else cookie
        if cookie:
            headers["Cookie"] = cookie
        if getattr(self, "csrf", None) and method == "POST":
            headers["X-U-Jagd-CSRF"] = self.csrf
        payload = None if body is None else json.dumps(body).encode("utf-8")
        with closing(http.client.HTTPConnection(self.host, self.port, timeout=5)) as connection:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            data = response.read()
            response_headers = dict(response.getheaders())
            if response_headers.get("Content-Type", "").startswith("application/json"):
                data = json.loads(data)
            return response.status, response_headers, data

    def poll_state(self):
        started = time.monotonic()
        try:
            status, _, body = self.request("/api/v2/state")
        except (OSError, http.client.HTTPException, ValueError):
            self.poll_errors += 1
            return None
        self.poll_latency_ms.append((time.monotonic() - started) * 1000.0)
        self.polls += 1
        if status != 200:
            self.poll_errors += 1
            return None
        return body

    def poll_session(self):
        try:
            status, _, body = self.request("/api/v2/session")
        except (OSError, http.client.HTTPException, ValueError):
            return None
        if status == 200 and isinstance(body, dict):
            self.station = body.get("station")
            return body
        return None


class AudioStream(threading.Thread):
    """Browser-like consumer of one role's audio WebSocket (with resume cursor)."""

    def __init__(self, session: Session, role: str, stop: threading.Event):
        super().__init__(name=f"soak-audio-{role}", daemon=True)
        self.session, self.role, self.stop = session, role, stop
        self.arrivals: list[float] = []
        self.sequences: list[int] = []
        self.gaps = 0            # sequence jumps (epoch step, retune, skip)
        self.backwards = 0       # numbering went backwards: the old worklet-drop bug
        self.reconnects = 0
        self.refusals = 0        # 4xx handshakes (not yet granted, revoked)
        self.silences: list[float] = []   # intervals without a block > SILENCE_S
        self.first_block_at = None
        self.last_block_at = None
        self.connected_since = None
        self.last_sequence = None

    def run(self):
        while not self.stop.is_set():
            try:
                self._stream_once()
            except (OSError, ValueError, struct.error):
                pass
            if self.stop.is_set():
                break
            self.reconnects += 1
            # The browser reconnects at once after an epoch step, 0.5 s otherwise.
            self.stop.wait(0.1)

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        query = f"?after={self.last_sequence}" if self.last_sequence is not None else ""
        host, port = self.session.host, self.session.port
        return (f"GET /ws/v2/{AUDIO_ROUTES[self.role]}/audio{query} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\nOrigin: http://{host}:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                "Sec-WebSocket-Protocol: u-jagd-audio-v2\r\n"
                f"Cookie: {self.session.cookie}\r\n\r\n").encode("ascii")

    def _stream_once(self):
        with socket.create_connection((self.session.host, self.session.port), timeout=5) as connection:
            connection.sendall(self._handshake())
            received = bytearray()
            while b"\r\n\r\n" not in received:
                chunk = connection.recv(4096)
                if not chunk:
                    return
                received.extend(chunk)
            headers, buffer = bytes(received).split(b"\r\n\r\n", 1)
            if not headers.startswith(b"HTTP/1.1 101"):
                self.refusals += 1
                self.stop.wait(1.0)
                return
            self.connected_since = time.monotonic()
            buffer = bytearray(buffer)
            connection.settimeout(0.5)
            while not self.stop.is_set():
                while True:
                    frame = self._parse_frame(buffer)
                    if frame is None:
                        break
                    opcode, payload = frame
                    if opcode == 8:
                        return
                    if opcode == 2 and len(payload) == 2060 and payload[:4] == b"UJA2":
                        self._accept(struct.unpack("<Q", payload[4:12])[0])
                try:
                    chunk = connection.recv(65536)
                except TimeoutError:
                    continue
                if not chunk:
                    return
                buffer.extend(chunk)

    @staticmethod
    def _parse_frame(buffer: bytearray):
        if len(buffer) < 2:
            return None
        opcode = buffer[0] & 0x0F
        length = buffer[1] & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                return None
            length = struct.unpack("!H", buffer[2:4])[0]
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                return None
            length = struct.unpack("!Q", buffer[2:10])[0]
            offset = 10
        if len(buffer) < offset + length:
            return None
        payload = bytes(buffer[offset:offset + length])
        del buffer[:offset + length]
        return opcode, payload

    def _accept(self, sequence: int):
        now = time.monotonic()
        if self.last_sequence is not None:
            if sequence <= self.last_sequence:
                self.backwards += 1
                return
            if sequence != self.last_sequence + 1:
                self.gaps += 1
        if self.last_block_at is not None and now - self.last_block_at > SILENCE_S:
            self.silences.append(now - self.last_block_at)
        if self.first_block_at is None:
            self.first_block_at = now
        self.last_block_at = now
        self.last_sequence = sequence
        self.arrivals.append(now)
        self.sequences.append(sequence)

    def summary(self) -> dict:
        deltas = [b - a for a, b in zip(self.arrivals, self.arrivals[1:])]
        def percentile(values, fraction):
            if not values:
                return 0.0
            ordered = sorted(values)
            return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]
        return {
            "role": self.role,
            "blocks": len(self.arrivals),
            "seconds": round(len(self.arrivals) * BLOCK_S, 2),
            "gaps": self.gaps,
            "backwards": self.backwards,
            "reconnects": self.reconnects,
            "refusals": self.refusals,
            "silences_over_%.2fs" % SILENCE_S: len(self.silences),
            "silences_over_%.1fs" % GAP_S: sum(1 for value in self.silences if value > GAP_S),
            "longest_silence_s": round(max(self.silences, default=0.0), 2),
            "interarrival_p50_ms": round(1000 * percentile(deltas, .5), 1),
            "interarrival_p99_ms": round(1000 * percentile(deltas, .99), 1),
            "interarrival_max_ms": round(1000 * max(deltas, default=0.0), 1),
        }


class Poller(threading.Thread):
    """2 Hz state poll plus a 1 Hz session refresh, like the browser."""

    def __init__(self, session: Session, stop: threading.Event):
        super().__init__(name=f"soak-poll-{session.name}", daemon=True)
        self.session, self.stop = session, stop

    def run(self):
        next_session = 0.0
        while not self.stop.wait(0.5):
            self.session.poll_state()
            if time.monotonic() >= next_session:
                self.session.poll_session()
                next_session = time.monotonic() + 1.0


def _percentile_ms(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))], 1)


def _parse_debug_lines(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            row = {}
            for key, value in re.findall(r"(\w+)=([-+]?[0-9.]+)", line):
                try:
                    row[key] = float(value)
                except ValueError:
                    pass
            if row:
                rows.append(row)
    return rows


def _warmup_baseline(perf: list[dict], audio_rows: list[dict], warmup_s: float) -> dict:
    """The audio counters at the end of the warm-up, or {} without one.

    The warm-up runs from the first perf row (written once the first frame
    has finished) for warmup_s seconds of wall time.
    """
    if warmup_s <= 0 or not perf or not audio_rows:
        return {}
    end = perf[0].get("t", 0) + warmup_s
    base = {}
    for row in audio_rows:
        if row.get("t", 0) <= end:
            base = row
    return base


def run_host(args) -> int:
    with TemporaryDirectory(prefix="u-jagd-audio-soak-") as home:
        # Isolate settings, saves and debug logs before anything reads ~/.u-jagd.
        os.environ["HOME"] = home
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        if args.dummy_audio:
            os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["U_JAGD_AUDIO_DEBUG"] = "1"
        os.environ["U_JAGD_PERF_DEBUG"] = "1"
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import pygame
        from src.core import config
        from src.core.game import Game
        from src.core.station import Station
        from src.commander.server import ROLES

        save_dir = os.path.join(home, ".u-jagd")
        config.SAVE_DIR = save_dir
        config.SAVE_PATH = os.path.join(save_dir, "save.json")
        game = Game(seed=args.seed, start_menu=False, audio_enabled=True, language="en")
        game.station = Station.SONAR
        game.sonar_audio_enabled = True
        console = game.commander
        console.port = args.port
        console.activate(game)
        if console.address is None:
            print(f"host: transport did not start ({console.error})", file=sys.stderr)
            return 2
        console.bridge.allowed = True
        server = console.server
        host, port = console.address
        print(f"host: listening on {host}:{port}, pairing code {console.pairing_code}, "
              f"mixer {'dummy' if args.dummy_audio else pygame.mixer.get_init()}")

        # Pair the simulated browsers and grant every station: audio roles first.
        roles = [role for role in AUDIO_ROLES if role != "helicopter" or args.helicopter]
        roles += [role for role in ROLES if role not in roles]
        sessions = []
        for index in range(min(args.clients, len(roles))):
            session = Session(host, port, f"soak-{index}", console.pairing_code)
            role = roles[index]
            if not server.grant_station(session.client_id, role):
                print(f"host: could not grant {role} to {session.name}", file=sys.stderr)
                return 2
            if role in AUDIO_ROLES:
                server.set_client_grant(session.client_id, role, "sonar_audio", True)
            session.station = role
            sessions.append(session)
        stop = threading.Event()
        streams = [AudioStream(session, session.station, stop)
                   for session in sessions if session.station in AUDIO_ROLES]
        pollers = [Poller(session, stop) for session in sessions]
        for thread in (*streams, *pollers):
            thread.start()

        # Host input from the main thread, exactly where the game reads it.
        counters = {"bumps": 0, "retunes": 0}
        schedule = {"bump": time.monotonic() + args.bump_every if args.bump_every else None,
                    "retune": time.monotonic() + args.retune_every if args.retune_every else None}
        original_pump = console.pump

        def pump(current):
            now = time.monotonic()
            if schedule["bump"] is not None and now >= schedule["bump"]:
                # F1 opens the help overlay; Esc closes it. Each transition is
                # an input-owner change, i.e. a world epoch step for browsers.
                for key in (pygame.K_F1, pygame.K_ESCAPE):
                    current.handle_event(pygame.event.Event(
                        pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))
                counters["bumps"] += 1
                schedule["bump"] = now + args.bump_every
            if schedule["retune"] is not None and now >= schedule["retune"]:
                current.set_sonar_listen_bearing((current.sonar.listen_bearing + 47.0) % 360.0)
                counters["retunes"] += 1
                schedule["retune"] = now + args.retune_every
            original_pump(current)

        profiler = None
        if args.profile:
            import cProfile
            profiler = cProfile.Profile()
            timed_pump = pump

            def pump(current):  # noqa: F811 - profiled wrapper of the same pump
                profiler.enable()
                try:
                    timed_pump(current)
                finally:
                    profiler.disable()

        console.pump = pump
        game.auto_quit = int(args.duration * game.frame_rate())
        epoch_before = console.bridge.status["epoch"]
        started = time.monotonic()
        try:
            game.run()
        finally:
            stop.set()
        elapsed = time.monotonic() - started
        for thread in (*streams, *pollers):
            thread.join(timeout=3.0)
        epochs = console.bridge.status["epoch"] - epoch_before
        stats = server.audio_stream_stats()
        if profiler is not None:
            import pstats
            print("\n=== commander pump profile (main thread) ===")
            report_stats = pstats.Stats(profiler)
            report_stats.sort_stats("tottime").print_stats(25)
            report_stats.sort_stats("cumulative").print_stats(r"src[\\/]commander", 25)
        perf = _parse_debug_lines(os.path.join(save_dir, "perf_debug.log"))
        audio_rows = _parse_debug_lines(os.path.join(save_dir, "audio_debug.log"))
        return report(args, elapsed, epochs, counters, streams, sessions, stats, perf,
                      audio_rows)


def report(args, elapsed, epochs, counters, streams, sessions, stats, perf, audio_rows) -> int:
    failures = []
    print(f"\n=== audio soak: {elapsed:.1f} s wall, {len(sessions)} clients, "
          f"{counters['bumps']} host input bursts ({epochs} epoch steps), "
          f"{counters['retunes']} retunes ===")
    if perf:
        fps = [row.get("fps", 0) for row in perf]
        frame_max = max(row.get("frame_max_ms", 0) for row in perf)
        dropped = max(row.get("sim_dropped_ms", 0) for row in perf)
        commander = statistics.fmean(row.get("commander_ms", 0) for row in perf)
        commander_max = max(row.get("commander_max_ms", 0) for row in perf)
        print(f"frames: fps min/mean {min(fps):.0f}/{statistics.fmean(fps):.1f}, "
              f"frame_max {frame_max:.0f} ms, commander mean {commander:.2f} ms "
              f"(max {commander_max:.0f} ms), sim_dropped {dropped:.0f} ms")
        if dropped > 0:
            failures.append(f"simulation time dropped ({dropped:.0f} ms)")
    else:
        print("frames: no perf_debug.log written")
    if audio_rows:
        last = audio_rows[-1]
        print("local mixer: underruns {:.0f}, concealed {:.0f}, neutral {:.0f}, "
              "channel_idle {:.0f} (+{:.0f} after a late pump), pump_late {:.0f} (max {:.0f} ms), drops {:.0f}, "
              "input_gaps {:.0f}, buffer {:.2f} s".format(
                  last.get("sonar_underruns", 0), last.get("sonar_concealed", 0),
                  last.get("sonar_neutral", 0), last.get("channel_idle", 0),
                  last.get("channel_idle_late", 0),
                  last.get("pump_late", 0),
                  max(row.get("pump_late_max_ms", 0) for row in audio_rows),
                  last.get("sonar_drops", 0), last.get("input_gaps", 0),
                  last.get("buffer_s", 0)))
        # The first frames of a cold process (imports, font and surface
        # caches, a busy CI runner) can stall for seconds and starve the
        # mixer before the stream is running; count starvation only from the
        # end of the warm-up on. A stall later in the run still fails.
        warmup = getattr(args, "warmup", 0.0)
        base = _warmup_baseline(perf, audio_rows, warmup)
        if base:
            print(f"warm-up: first {warmup:.1f} s after the first frame not counted "
                  f"(underruns {base.get('sonar_underruns', 0):.0f}, "
                  f"channel_idle {base.get('channel_idle', 0):.0f}, "
                  f"drops {base.get('sonar_drops', 0):.0f})")
        for key, label in (("sonar_underruns", "local underruns"),
                           ("channel_idle", "mixer channel idle events"),
                           ("sonar_drops", "rejected local blocks")):
            counted = last.get(key, 0) - base.get(key, 0)
            if counted > 0:
                failures.append(f"{label}: {counted:.0f}")
        # Every retune breaks the receiver sequence once; anything beyond that
        # is a block the frame loop never played. (evictions counts ordinary
        # ring rotation of the two-block receiver window, not loss.)
        if last.get("input_gaps", 0) > counters["retunes"]:
            failures.append(f"local input gaps {last['input_gaps']:.0f} for "
                            f"{counters['retunes']} retunes")
        slow = [row for row in perf if row.get("frame_max_ms", 0) > 100]
        if slow:
            first_t = perf[0].get("t", 0)
            print("slow seconds (frame_max > 100 ms):")
            for row in slow[:8]:
                print("  +{:5.1f}s fps {:2.0f} frame_max {:5.0f} ms  sim {:5.1f}  audio {:4.1f}  "
                      "commander {:5.1f} (max {:4.0f})  events {:4.1f}  traffic {:4.1f}  "
                      "draw {:5.1f}  lag {:4.0f}".format(
                          row.get("t", 0) - first_t, row.get("fps", 0), row.get("frame_max_ms", 0),
                          row.get("sim_ms", 0), row.get("audio_ms", 0), row.get("commander_ms", 0),
                          row.get("commander_max_ms", 0), row.get("events_ms", 0),
                          row.get("traffic_ms", 0), row.get("draw_ms", 0), row.get("sim_lag_ms", 0)))
    else:
        print("local mixer: no audio_debug.log written")
    allowed_gaps = counters["bumps"] + counters["retunes"]
    for stream in streams:
        summary = stream.summary()
        role_stats = stats.get(stream.role, {})
        print(f"stream {stream.role}: " + ", ".join(
            f"{key} {value}" for key, value in summary.items() if key != "role")
            + f"; server skipped {role_stats.get('skipped_blocks', 0)}, "
              f"send timeouts {role_stats.get('send_timeouts', 0)}, "
              f"discontinuities {role_stats.get('discontinuities', 0)}, "
              f"connections {role_stats.get('connections', 0)}")
        if summary["blocks"] == 0:
            if stream.role == "helicopter":
                print("  (no helicopter audio: the dipping sonar was not in the water)")
            else:
                failures.append(f"{stream.role}: no audio received")
            continue
        if summary["backwards"]:
            failures.append(f"{stream.role}: sequence went backwards {summary['backwards']}x")
        if summary["gaps"] > allowed_gaps + stream.reconnects:
            failures.append(f"{stream.role}: {summary['gaps']} gaps for "
                            f"{allowed_gaps} host events")
        if summary["silences_over_%.1fs" % GAP_S]:
            failures.append(f"{stream.role}: {summary['silences_over_%.1fs' % GAP_S]} "
                            f"silences over {GAP_S} s")
    latencies = [value for session in sessions for value in session.poll_latency_ms]
    errors = sum(session.poll_errors for session in sessions)
    polls = sum(session.polls for session in sessions)
    print(f"state polls: {polls} ok, {errors} errors, latency p50/p99/max "
          f"{_percentile_ms(latencies, .5)}/{_percentile_ms(latencies, .99)}/"
          f"{_percentile_ms(latencies, 1.0)} ms")
    if failures:
        print("RESULT: FAIL\n  - " + "\n  - ".join(failures))
        return 1
    print("RESULT: OK")
    return 0


def run_client(args) -> int:
    parts = urlsplit(args.connect)
    host, port = parts.hostname, parts.port or 80
    session = Session(host, port, args.name, args.code)
    print(f"client: paired as {session.name}; waiting for an audio station grant (F9 on the host)")
    deadline = time.monotonic() + args.duration
    while time.monotonic() < deadline:
        body = session.poll_session()
        if body and body.get("station") in AUDIO_ROLES and body["grants"].get("sonar_audio"):
            break
        time.sleep(1.0)
    else:
        print("client: no audio station granted in time")
        return 2
    role = session.station
    print(f"client: streaming {role} for {args.duration:.0f} s")
    stop = threading.Event()
    stream = AudioStream(session, role, stop)
    poller = Poller(session, stop)
    stream.start()
    poller.start()
    started = time.monotonic()
    try:
        while time.monotonic() - started < args.duration:
            time.sleep(1.0)
    finally:
        stop.set()
    stream.join(timeout=3.0)
    poller.join(timeout=3.0)
    return report(args, time.monotonic() - started, 0, {"bumps": 0, "retunes": 0},
                  [stream], [session], {}, [], [])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    host = modes.add_parser("host", help="run the game headless with simulated browsers")
    host.add_argument("--duration", type=float, default=60.0, help="seconds of play")
    host.add_argument("--clients", type=int, default=9, help="paired browsers (max 15 roles)")
    host.add_argument("--bump-every", type=float, default=15.0,
                      help="seconds between host input bursts (0 = never)")
    host.add_argument("--retune-every", type=float, default=0.0,
                      help="seconds between listening-bearing changes (0 = never)")
    host.add_argument("--warmup", type=float, default=2.0,
                      help="seconds after the first frame whose mixer starvation is not counted")
    host.add_argument("--seed", type=int, default=1234)
    host.add_argument("--port", type=int, default=0, help="listener port (0 = ephemeral)")
    host.add_argument("--dummy-audio", action="store_true",
                      help="SDL dummy audio driver (CI); default plays through the mixer")
    host.add_argument("--helicopter", action="store_true",
                      help="also lease the helicopter (audio only once its sonar is wet)")
    host.add_argument("--profile", action="store_true",
                      help="cProfile the Remote Crew pump on the main thread")
    client = modes.add_parser("client", help="consume one audio stream from another machine")
    client.add_argument("--connect", required=True, help="http://host:port of the game")
    client.add_argument("--code", required=True, help="pairing code shown in F9")
    client.add_argument("--name", default="soak-client")
    client.add_argument("--duration", type=float, default=120.0)
    args = parser.parse_args(argv)
    return run_host(args) if args.mode == "host" else run_client(args)


if __name__ == "__main__":
    sys.exit(main())
