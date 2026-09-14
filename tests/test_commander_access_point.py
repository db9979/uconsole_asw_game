"""The hotspot client is bounded and tests never touch the real network."""

import json
import sys
import time

import pytest

from src.commander.access_point import HotspotController, HotspotDetails


def command(payload, *, wait=True, delay=0.0):
    body = json.dumps(payload, ensure_ascii=True)
    source = (
        "import sys,time; "
        f"time.sleep({delay!r}); "
        f"print({body!r},flush=True); "
        + ("sys.stdin.buffer.read()" if wait else "None")
    )
    return (sys.executable, "-u", "-c", source)


def wait_for(controller, state, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        controller.poll()
        if controller.state == state:
            return
        time.sleep(0.01)
    pytest.fail(f"hotspot remained {controller.state!r}, wanted {state!r}")


def running_payload(**changes):
    payload = dict(status="running", ssid="U-Jagd-7KPX",
                   password="SecureCrewKey2345", address="10.42.0.1",
                   interface="wlan0")
    payload.update(changes)
    return payload


def test_constructor_is_passive_and_missing_helper_is_local_error(monkeypatch):
    calls = []
    controller = HotspotController(popen=lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr("src.commander.access_point.os.path.isfile", lambda path: False)

    assert controller.state == "off" and not controller.active and not calls
    assert not controller.start()
    assert controller.state == "error" and controller.error == "helper_missing"
    assert not calls


def test_valid_helper_lifecycle_hides_password_and_cleans_thread():
    controller = HotspotController(command=command(running_payload()),
                                   startup_timeout=1, stop_timeout=1)
    assert controller.start()
    assert not controller.start()
    wait_for(controller, "running")

    assert controller.details == HotspotDetails(
        ssid="U-Jagd-7KPX", password="SecureCrewKey2345",
        address="10.42.0.1", interface="wlan0")
    assert "SecureCrewKey2345" not in repr(controller.details)
    assert controller.request_stop()
    wait_for(controller, "off")
    assert controller.details is None and controller.error is None
    assert not controller._thread.is_alive()


@pytest.mark.parametrize("changes", [
    {"address": "8.8.8.8"},
    {"address": "169.254.1.1"},
    {"interface": "wlan0;bad"},
    {"ssid": "x" * 33},
    {"password": "short"},
    {"extra": True},
])
def test_hostile_or_invalid_helper_output_is_rejected(changes):
    controller = HotspotController(command=command(running_payload(**changes), wait=False),
                                   startup_timeout=1, stop_timeout=.2)
    assert controller.start()
    wait_for(controller, "error")
    assert controller.error == "protocol" and controller.details is None


def test_bounded_startup_timeout_and_sanitized_helper_error():
    timeout = HotspotController(command=command(running_payload(), delay=.5),
                                startup_timeout=.05, stop_timeout=.1)
    assert timeout.start()
    wait_for(timeout, "error")
    assert timeout.error == "timeout"

    denied = HotspotController(
        command=command({"status": "error", "code": "authorization"}, wait=False),
        startup_timeout=1, stop_timeout=.2)
    assert denied.start()
    wait_for(denied, "error")
    assert denied.error == "authorization"


def test_close_during_start_is_bounded_and_returns_to_off():
    controller = HotspotController(command=command(running_payload(), delay=.5),
                                   startup_timeout=2, stop_timeout=.1)
    assert controller.start()
    started = time.monotonic()
    controller.close()
    assert time.monotonic() - started < 1
    assert controller.state == "off" and controller.details is None
