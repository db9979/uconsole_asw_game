"""Static/helper-unit coverage; these tests never contact NetworkManager."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import json
import os
import stat
import sys

import pytest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).parents[1]
HELPER = ROOT / "packaging/uconsole/u-jagd-hotspot-helper"
INSTALLER = ROOT / "packaging/uconsole/install-hotspot-helper.sh"
POLICY = ROOT / "packaging/uconsole/io.github.db9979.u-jagd.hotspot.policy"


def load_helper():
    loader = SourceFileLoader("u_jagd_hotspot_helper_test", str(HELPER))
    spec = spec_from_loader(loader.name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeDbus:
    String = str
    Boolean = bool
    ByteArray = bytes

    @staticmethod
    def Array(values, signature=None):
        return list(values)

    @staticmethod
    def Dictionary(values, signature=None):
        return dict(values)


def test_helper_builds_only_fixed_ephemeral_wpa2_shared_profile():
    module = load_helper()
    hotspot = object.__new__(module.NetworkManagerHotspot)
    hotspot.dbus = FakeDbus

    settings = hotspot._settings("wlan0", "U-Jagd-TEST", "SecureCrewKey2345")

    assert settings["connection"] == {
        "id": module.CONNECTION_ID,
        "uuid": module.CONNECTION_UUID,
        "type": "802-11-wireless",
        "interface-name": "wlan0",
        "autoconnect": False,
    }
    assert settings["802-11-wireless"] == {
        "ssid": b"U-Jagd-TEST", "mode": "ap", "band": "bg"}
    assert settings["802-11-wireless-security"] == {
        "key-mgmt": "wpa-psk", "psk": "SecureCrewKey2345",
        "proto": ["rsn"], "pairwise": ["ccmp"], "group": ["ccmp"]}
    assert settings["ipv4"] == {"method": "shared"}
    assert settings["ipv6"] == {"method": "disabled"}


def test_start_uses_volatile_dbus_bound_activation(monkeypatch):
    module = load_helper()
    calls = []

    class NetworkManager:
        def AddAndActivateConnection2(self, settings, device, specific, options):
            calls.append((settings, device, specific, options))
            return "/connection", "/active", {}

    hotspot = object.__new__(module.NetworkManagerHotspot)
    hotspot.dbus = FakeDbus
    hotspot.nm = NetworkManager()
    hotspot.device_path = hotspot.previous_connection = None
    hotspot.connection_path = hotspot.active_path = None
    monkeypatch.setattr(hotspot, "_delete_stale_profiles", lambda: None)
    monkeypatch.setattr(hotspot, "_wifi_device", lambda: ("/device", "wlan0"))
    monkeypatch.setattr(hotspot, "_active_for_device",
                        lambda device: ("/old-active", "/old-connection"))
    monkeypatch.setattr(hotspot, "_wait_for_address", lambda: "10.42.0.1")
    monkeypatch.setattr(module, "hotspot_credentials",
                        lambda: ("U-Jagd-7KPX", "abcdefghijkmnopqrs"))

    details = hotspot.start()

    assert details["status"] == "running" and details["address"] == "10.42.0.1"
    assert (details["ssid"], details["password"]) == ("U-Jagd-7KPX", "abcdefghijkmnopqrs")
    assert calls[0][0]["802-11-wireless"]["ssid"] == b"U-Jagd-7KPX"
    assert hotspot.previous_connection == "/old-connection"
    assert calls[0][1:] == (
        "/device", "/", {"persist": "volatile", "bind-activation": "dbus-client"})


def test_cleanup_waits_for_deactivation_and_previous_wifi(monkeypatch):
    module = load_helper()
    calls = []

    class NetworkManager:
        def DeactivateConnection(self, active):
            calls.append(("deactivate", active))

        def ActivateConnection(self, connection, device, specific):
            calls.append(("restore", connection, device, specific))
            return "/restoring"

    hotspot = object.__new__(module.NetworkManagerHotspot)
    hotspot.nm = NetworkManager()
    hotspot.active_path = "/hotspot-active"
    hotspot.connection_path = "/hotspot-profile"
    hotspot.previous_connection = "/previous-profile"
    hotspot.device_path = "/device"
    monkeypatch.setattr(hotspot, "_active_connections", lambda: ("/hotspot-active",))
    monkeypatch.setattr(hotspot, "_wait_inactive", lambda: True)
    monkeypatch.setattr(hotspot, "_active_for_device", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(hotspot, "_wait_activated",
                        lambda active: calls.append(("wait", active)) or True)

    assert hotspot.cleanup()
    assert calls == [
        ("deactivate", "/hotspot-active"),
        ("restore", "/previous-profile", "/device", "/"),
        ("wait", "/restoring"),
    ]


def test_policy_allows_only_the_root_owned_fixed_helper_for_active_user():
    root = ET.parse(POLICY).getroot()
    action = root.find("action")
    defaults = action.find("defaults")
    annotations = {node.attrib["key"]: node.text for node in action.findall("annotate")}

    assert action.attrib["id"] == "io.github.db9979.u-jagd.hotspot"
    assert defaults.findtext("allow_any") == "no"
    assert defaults.findtext("allow_inactive") == "no"
    assert defaults.findtext("allow_active") == "yes"
    assert annotations == {
        "org.freedesktop.policykit.exec.path": "/usr/libexec/u-jagd-hotspot-helper"}


def test_checkout_installers_are_executable_and_helper_has_no_shell_runner():
    helper_text = HELPER.read_text(encoding="utf-8")
    installer_text = INSTALLER.read_text(encoding="utf-8")
    assert HELPER.stat().st_mode & stat.S_IXUSR
    assert INSTALLER.stat().st_mode & stat.S_IXUSR
    assert "subprocess" not in helper_text
    assert "os.system" not in helper_text
    assert "shell=True" not in helper_text
    assert "PATH=/usr/sbin:/usr/bin:/sbin:/bin" in installer_text
    assert "/usr/bin/python3 -I -c 'import dbus'" in installer_text


@pytest.fixture
def stateful(tmp_path, monkeypatch):
    module = load_helper()
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path / "var-lib-u-jagd"))
    monkeypatch.setattr(module, "STATE_OWNER_UID", os.getuid())
    return module, tmp_path / "var-lib-u-jagd" / "hotspot.json"


def test_credentials_are_made_once_privately_and_reused(stateful):
    module, state = stateful
    ssid, password = module.hotspot_credentials()

    assert module.valid_credentials(ssid, password)
    assert stat.S_IMODE(state.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    assert json.loads(state.read_text()) == {
        "version": 1, "ssid": ssid, "password": password}
    assert [path.name for path in state.parent.iterdir()] == ["hotspot.json"]
    for _ in range(3):
        assert module.hotspot_credentials() == (ssid, password)


def test_new_password_keeps_the_network_name(stateful):
    module, state = stateful
    ssid, password = module.hotspot_credentials()
    renewed = module.hotspot_credentials(renew_password=True)

    assert renewed[0] == ssid and renewed[1] != password
    assert module.valid_credentials(*renewed)
    assert module.hotspot_credentials() == renewed


@pytest.mark.parametrize("content", [
    "", "not json", "[]", '{"version": 1, "ssid": "U-Jagd-7KPX"}',
    '{"version": 2, "ssid": "U-Jagd-7KPX", "password": "abcdefghijkmnopqrs"}',
    '{"version": true, "ssid": "U-Jagd-7KPX", "password": "abcdefghijkmnopqrs"}',
    '{"version": 1, "ssid": "U-Jagd-7KPI", "password": "abcdefghijkmnopqrs"}',
    '{"version": 1, "ssid": "Evil-Net", "password": "abcdefghijkmnopqrs"}',
    '{"version": 1, "ssid": "U-Jagd-7KPX", "password": "short"}',
    '{"version": 1, "ssid": "U-Jagd-7KPX", "password": "abcdefghijkmnopqr0"}',
    '{"version": 1, "ssid": "U-Jagd-7KPX", "password": "abcdefghijkmnopqrs", "x": 1}',
    '{"version": 1, "ssid": "U-Jagd-7KPX", "password": "' + "a" * 2000 + '"}',
])
def test_invalid_state_is_replaced_with_new_credentials(stateful, content):
    module, state = stateful
    state.parent.mkdir(mode=0o700)
    state.write_text(content)
    state.chmod(0o600)

    ssid, password = module.hotspot_credentials()

    assert module.valid_credentials(ssid, password)
    assert json.loads(state.read_text())["password"] == password


def test_loose_permissions_are_not_trusted(stateful):
    module, state = stateful
    state.parent.mkdir(mode=0o755)
    state.write_text('{"version": 1, "ssid": "U-Jagd-7KPX", '
                     '"password": "abcdefghijkmnopqrs"}')
    state.chmod(0o644)

    assert module.hotspot_credentials() != ("U-Jagd-7KPX", "abcdefghijkmnopqrs")
    assert stat.S_IMODE(state.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(state.stat().st_mode) == 0o600


def test_symlinked_state_file_is_never_followed(stateful, tmp_path):
    module, state = stateful
    state.parent.mkdir(mode=0o700)
    target = tmp_path / "elsewhere.json"
    target.write_text('{"version": 1, "ssid": "U-Jagd-7KPX", '
                      '"password": "abcdefghijkmnopqrs"}')
    target.chmod(0o600)
    state.symlink_to(target)

    ssid, password = module.hotspot_credentials()

    assert (ssid, password) != ("U-Jagd-7KPX", "abcdefghijkmnopqrs")
    assert not state.is_symlink() and state.is_file()
    assert "abcdefghijkmnopqrs" in target.read_text()     # target untouched


def test_symlinked_or_foreign_state_directory_is_refused(stateful, tmp_path, monkeypatch):
    module, state = stateful
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    state.parent.symlink_to(real)
    with pytest.raises(module.HotspotError) as refused:
        module.hotspot_credentials()
    assert refused.value.code == "state"
    assert not list(real.iterdir())

    state.parent.unlink()
    state.parent.mkdir(mode=0o700)
    monkeypatch.setattr(module, "STATE_OWNER_UID", os.getuid() + 1)
    with pytest.raises(module.HotspotError):
        module.hotspot_credentials()


def test_failed_write_leaves_the_old_state_and_no_temporary(stateful, monkeypatch):
    module, state = stateful
    before = module.hotspot_credentials()

    real_fsync = os.fsync

    def broken_fsync(descriptor):
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "fsync", broken_fsync)
    with pytest.raises(module.HotspotError):
        module.hotspot_credentials(renew_password=True)
    monkeypatch.setattr(module.os, "fsync", real_fsync)
    assert [path.name for path in state.parent.iterdir()] == ["hotspot.json"]
    assert json.loads(state.read_text())["password"] == before[1]


def test_new_password_subcommand_is_the_only_other_entry(stateful, monkeypatch, capsys):
    module, state = stateful
    monkeypatch.setattr(module, "LOCK_PATH", str(state.parent.parent / "lock"))
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "fstat", _root_fstat(module.os.fstat))
    monkeypatch.setattr(sys, "argv", ["helper", "new-password"])
    monkeypatch.setattr(module, "STATE_OWNER_UID", 0)
    first = None
    for _ in range(2):
        assert module.main() == 0
        assert capsys.readouterr().out == '{"status":"renewed"}\n'
        password = json.loads(state.read_text())["password"]
        assert password != first
        first = password
    for argv in (["helper"], ["helper", "serve", "x"], ["helper", "new-password", "x"],
                 ["helper", "reset"]):
        monkeypatch.setattr(sys, "argv", argv)
        assert module.main() == 2
        assert json.loads(capsys.readouterr().out) == {
            "status": "error", "code": "authorization"}


def _root_fstat(real_fstat):
    """Pretend files are root-owned so main() runs unprivileged in tests."""
    def fstat(descriptor):
        result = real_fstat(descriptor)
        return os.stat_result((result.st_mode, result.st_ino, result.st_dev,
                               result.st_nlink, 0, 0, result.st_size,
                               result.st_atime, result.st_mtime, result.st_ctime))
    return fstat


def test_uninstall_also_forgets_the_stored_hotspot_credentials():
    installer_text = INSTALLER.read_text(encoding="utf-8")
    assert "state_dir=/var/lib/u-jagd" in installer_text
    assert '"$state_dir/hotspot.json"' in installer_text
    helper = load_helper()
    assert helper.STATE_DIR == "/var/lib/u-jagd" and helper.STATE_NAME == "hotspot.json"
