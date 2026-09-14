"""Static/helper-unit coverage; these tests never contact NetworkManager."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import stat
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

    details = hotspot.start()

    assert details["status"] == "running" and details["address"] == "10.42.0.1"
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
