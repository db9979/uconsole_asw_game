"""Noise discipline: the own microphone opens on every platform and says why
when it cannot (uConsole, Windows, macOS and the crew browser)."""

import http.client
import json
import ssl
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.audio import microphone
from src.audio.microphone import Microphone
from src.commander import CommanderServer, tls
from src.commander import server as transport
from src.core import game_noise
from src.core.game import Game
from src.core.i18n import localize

sys.path.insert(0, str(Path(__file__).parent))
from test_commander_sessions_v2 import request, server  # noqa: E402,F401
from commander_web import top_level_files  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class FakeDevice:
    def __init__(self, devicename, **kwargs):
        # pygame 2.6 refuses devicename=None with a TypeError: the cause of
        # the microphone that never opened (1.3.168 and before).
        if not isinstance(devicename, str):
            raise TypeError("devicename must be a string")
        self.devicename = devicename
        self.callback = kwargs["callback"]
        self.paused = None
        self.closed = False

    def pause(self, value):
        self.paused = value

    def close(self):
        self.closed = True


def fake_sdl(monkeypatch, names=("Built-in Microphone",), error=None):
    module = SimpleNamespace(AUDIO_F32=0x8120, opened=[])

    def device(**kwargs):
        if error is not None:
            raise error
        opened = FakeDevice(**kwargs)
        module.opened.append(opened)
        return opened
    module.AudioDevice = device
    module.get_audio_device_names = lambda capture: list(names)
    import pygame._sdl2 as package
    monkeypatch.setattr(package, "audio", module, raising=False)
    monkeypatch.setitem(sys.modules, "pygame._sdl2.audio", module)
    return module


def block(value):
    return memoryview(np.full(512, value, dtype=np.float32).tobytes())


def test_the_capture_opens_the_first_named_device(monkeypatch):
    sdl = fake_sdl(monkeypatch)
    now = [0.0]
    mic = Microphone(clock=lambda: now[0])
    assert mic.start() and mic.available and mic.failure == ""
    device = sdl.opened[0]
    assert device.devicename == "Built-in Microphone" and device.paused == 0
    device.callback(device, block(0.1))
    assert mic.blocks == 1 and mic.level() > 0
    now[0] = 10.0
    assert mic.check() == ""
    mic.stop()
    assert device.closed and mic.level() == 0


def test_sdl_dummy_input_delivers_blocks_like_the_build_self_test(monkeypatch):
    import time
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    mic = Microphone()
    try:
        assert mic.start(), mic.detail
        deadline = time.monotonic() + 3.0
        while mic.blocks == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert mic.blocks > 0
    finally:
        mic.stop()


_STOP_MID_CALLBACK = r"""
import os, sys, threading, time
os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, sys.argv[1])
from src.audio.microphone import Microphone
for _round in range(2):
    mic = Microphone()
    inside = threading.Event()
    plain = mic._callback
    def slow(device, data, mic=mic, plain=plain, inside=inside):
        plain(device, data)
        if not inside.is_set():
            inside.set()
            time.sleep(0.4)  # SDL holds the device lock, the GIL is free
    mic._callback = slow
    assert mic.start(), mic.detail
    assert inside.wait(5.0)
    mic.stop()
    assert mic.released == "sdl", mic.released
print("stopped")
"""


def test_stopping_mid_callback_never_deadlocks():
    # pygame's pause()/close() held the GIL while SDL waited for the running
    # capture callback, which waited for the GIL: the macOS build's self-test
    # hung in Microphone.stop() (1.3.234).  A child process, so a regression
    # fails on the timeout instead of hanging the test run; two rounds, as
    # the second device reuses the first one's SDL id.
    import subprocess
    result = subprocess.run([sys.executable, "-c", _STOP_MID_CALLBACK, str(ROOT)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "stopped" in result.stdout, result.stderr


def test_a_device_out_of_reach_of_sdl_closes_the_pygame_way(monkeypatch):
    sdl = fake_sdl(monkeypatch)
    mic = Microphone()
    assert mic.start()
    mic.stop()
    device = sdl.opened[0]
    assert device.paused == 1 and device.closed and mic.released == "pygame"


def test_sdl_library_names():
    from src.audio import sdl_native
    for name in ("/usr/lib/libSDL2-2.0.so.0", "/x/pygame.libs/libSDL2-2-1667c208.0.so.0.2800.4",
                 "SDL2.dll", "/A.app/Contents/Frameworks/pygame/.dylibs/libSDL2-2.0.0.dylib"):
        assert sdl_native._is_sdl(name), name
    for name in ("/x/libSDL2_mixer-2.0.so.0", "SDL2_ttf.dll", "/x/libSDL2main.a", "libsdl.so"):
        assert not sdl_native._is_sdl(name), name


def test_failures_name_their_cause(monkeypatch):
    fake_sdl(monkeypatch, names=())
    mic = Microphone()
    assert not mic.start() and mic.failure == "no_device" and mic.tried
    fake_sdl(monkeypatch, error=RuntimeError("Couldn't open   WASAPI\n device"))
    mic = Microphone()
    assert not mic.start() and mic.failure == "open_failed"
    assert mic.detail == "Couldn't open WASAPI device"
    assert set(microphone.FAILURES) == {"no_capture", "no_device", "open_failed", "silent"}


def test_digital_silence_reads_as_blocked_access_until_sound_arrives(monkeypatch):
    sdl = fake_sdl(monkeypatch)
    now = [0.0]
    mic = Microphone(clock=lambda: now[0])
    assert mic.start()
    device = sdl.opened[0]
    device.callback(device, block(0.0))
    now[0] = microphone.SILENT_AFTER_S - 0.1
    assert mic.check() == ""
    now[0] = microphone.SILENT_AFTER_S
    assert mic.check() == "silent"
    device.callback(device, block(0.002))       # the player allowed access
    assert mic.check() == ""


def test_failure_keys_follow_the_platform():
    assert game_noise.microphone_failure_key("silent", "win32").endswith("silent_windows")
    assert game_noise.microphone_failure_key("silent", "darwin").endswith("silent_macos")
    assert game_noise.microphone_failure_key("silent", "linux").endswith(".silent")
    catalogs = {lang: json.loads((ROOT / f"data/i18n/{lang}.json").read_text(encoding="utf-8"))
                for lang in ("en", "de")}
    for cause in microphone.FAILURES:
        for platform in ("win32", "darwin", "linux"):
            for catalog in catalogs.values():
                assert game_noise.microphone_failure_key(cause, platform) in catalog
                assert game_noise.microphone_state_key(cause) in catalog


def _mission():
    game = Game(seed=7, start_menu=False, audio_enabled=False)
    game.preferences = replace(game.preferences, microphone=True)
    return game


def test_a_failing_microphone_is_said_once_and_retried_next_mission(monkeypatch):
    fake_sdl(monkeypatch, names=())
    game = _mission()
    flashes = []
    monkeypatch.setattr(game, "flash", lambda text, seconds=3.0: flashes.append(text))
    game._pump_microphone(0.1)
    game._pump_microphone(0.1)
    assert len(flashes) == 1
    text = localize(flashes[0], game.tr)
    assert "no microphone found" in text and "F10" in text
    # The mission ends: the next one tries the device again.
    sdl = fake_sdl(monkeypatch)
    game.game_over = True
    game._pump_microphone(0.1)
    game.game_over = False
    game._pump_microphone(0.1)
    assert game.microphone.available and sdl.opened
    assert game.microphone.failure == ""


def test_options_page_two_shows_the_cause(monkeypatch):
    from src.core import game_draw
    monkeypatch.setattr(game_draw, "save_preferences", lambda *_a, **_k: None)
    fake_sdl(monkeypatch, error=RuntimeError("device busy"))
    game = _mission()
    game._pump_microphone(0.1)
    game._open_administration("options")
    game._set_options_page(1)
    texts = []
    original = game_draw.layout.blit_block

    def spy(screen, text, *args, **kwargs):
        texts.append(localize(text, game.tr))
        return original(screen, text, *args, **kwargs)
    monkeypatch.setattr(game_draw.layout, "blit_block", spy)
    game.draw()
    assert any("device busy" in text for text in texts)


def test_the_crew_page_learns_the_https_port(tmp_path, monkeypatch, server):  # noqa: F811
    status, _, body = request(server, "/api/v2/secure")
    assert status == 200 and body == {"protocol": 2, "port": None}
    for name in top_level_files():
        (tmp_path / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(transport.resources, "files", lambda package: tmp_path)
    cert, key = tls.ensure_certificate(str(tmp_path / "tls"), "127.0.0.1")
    secure = CommanderServer()
    secure.start("127.0.0.1", 0, tls_context=tls.context(cert, key), tls_port=0)
    try:
        host, port = secure.tls_address
        assert request(secure, "/api/v2/secure")[2] == {"protocol": 2, "port": port}
        # The crew page itself is served there (the browser grants the mic).
        client = ssl.create_default_context(cafile=cert)
        with closing(http.client.HTTPSConnection(host, port, timeout=5, context=client)) as link:
            link.request("GET", "/")
            assert link.getresponse().status == 200
    finally:
        secure.stop()


def test_packaged_builds_carry_the_capture_and_the_mac_permission():
    windows = (ROOT / "packaging/windows/u-jagd-windows.spec").read_text(encoding="utf-8")
    mac = (ROOT / "packaging/macos/u-jagd-macos.spec").read_text(encoding="utf-8")
    for spec in (windows, mac):
        assert '"pygame._sdl2.audio"' in spec
    assert '"NSMicrophoneUsageDescription"' in mac
    entry = (ROOT / "src/launcher/entry.py").read_text(encoding="utf-8")
    assert "_microphone_self_test()" in entry

