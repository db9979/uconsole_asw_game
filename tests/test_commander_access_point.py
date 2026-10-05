"""The hotspot client is bounded and tests never touch the real network."""

import json
import sys
import time

import os

import pytest

from src.commander.access_point import HotspotController, HotspotDetails

if os.name != "posix":
    # The uConsole helpers (fcntl, root checks, executable bits) are Linux-only.
    pytest.skip("uConsole (Linux) only", allow_module_level=True)


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


def wait_renew(controller, state, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        controller.poll()
        if controller.renew_state == state:
            return
        time.sleep(0.01)
    pytest.fail(f"renewal remained {controller.renew_state!r}, wanted {state!r}")


def test_new_password_runs_the_helper_once_and_only_while_the_hotspot_is_off():
    controller = HotspotController(command=command(running_payload()),
                                   renew_command=command({"status": "renewed"}, wait=False),
                                   startup_timeout=1, stop_timeout=1)
    assert controller.can_renew and controller.renew_password()
    assert not controller.renew_password() and not controller.start()
    wait_renew(controller, "done")
    assert controller.renew_error is None
    controller._renew_thread.join(1)
    assert controller.start()
    assert not controller.can_renew and not controller.renew_password()
    wait_for(controller, "running")
    controller.close()


@pytest.mark.parametrize("payload, error", [
    ({"status": "error", "code": "busy"}, "busy"),
    ({"status": "error", "code": "state"}, "state"),
    ({"status": "error", "code": "../../etc"}, "start"),
    ({"status": "renewed", "password": "leak"}, "protocol"),
])
def test_new_password_errors_are_sanitized(payload, error):
    controller = HotspotController(command=command(running_payload()),
                                   renew_command=command(payload, wait=False),
                                   startup_timeout=1, stop_timeout=.5)
    assert controller.renew_password()
    wait_renew(controller, "error")
    assert controller.renew_error == error


def test_a_custom_serve_command_has_no_implicit_renewal():
    controller = HotspotController(command=command(running_payload()))
    assert not controller.can_renew and not controller.renew_password()
