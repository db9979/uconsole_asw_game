import socket

from src.network.connectivity import ConnectivityMonitor, check_internet_sync


def test_check_internet_sync_true_on_successful_connect(monkeypatch):
    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _FakeSocket())
    assert check_internet_sync() is True


def test_check_internet_sync_false_on_os_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("network unreachable")

    monkeypatch.setattr(socket, "create_connection", _raise)
    assert check_internet_sync() is False


def test_connectivity_monitor_reflects_check_result(monkeypatch):
    monkeypatch.setattr(
        "src.network.connectivity.check_internet_sync", lambda **k: True)
    monitor = ConnectivityMonitor(recheck_interval_s=60.0)
    assert monitor.online is None
    monitor.start()
    try:
        for _ in range(200):
            if monitor.online is not None:
                break
            import time
            time.sleep(0.01)
        assert monitor.online is True
    finally:
        monitor.stop(timeout=2.0)
