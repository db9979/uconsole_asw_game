"""Crash log: start/end lines, tracebacks and thread exceptions reach
``crash.log`` in the save directory; a symlinked log is never written."""

import faulthandler
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from src.core import crashlog
from src.core.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _log(tmp_path) -> str:
    return (tmp_path / crashlog.CRASH_LOG).read_text(encoding="utf-8")


def test_normal_run_logs_start_and_end(tmp_path):
    assert crashlog.run_logged(lambda: 0, root=str(tmp_path)) == 0
    text = _log(tmp_path)
    assert f"U-Jagd {APP_VERSION} started" in text
    assert text.rstrip().endswith("ended: normal")


def test_exception_is_logged_and_reraised(tmp_path):
    def boom():
        raise ZeroDivisionError("sonar says no")

    with pytest.raises(ZeroDivisionError):
        crashlog.run_logged(boom, root=str(tmp_path))
    text = _log(tmp_path)
    assert "crashed (main loop)" in text
    assert "ZeroDivisionError: sonar says no" in text
    assert "in boom" in text
    assert text.rstrip().endswith("ended: crash")


def test_thread_exception_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    session = crashlog.install(str(tmp_path))
    try:
        worker = threading.Thread(target=lambda: [][1], name="audio-worker")
        worker.start()
        worker.join()
    finally:
        crashlog.finish(session, "normal")
    text = _log(tmp_path)
    assert "crashed (thread audio-worker)" in text
    assert "IndexError" in text


def test_finish_restores_hooks(tmp_path):
    hook = threading.excepthook
    enabled = faulthandler.is_enabled()
    crashlog.finish(crashlog.install(str(tmp_path)), "normal")
    assert threading.excepthook is hook
    assert faulthandler.is_enabled() == enabled


def test_symlinked_log_is_not_followed(tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("keep\n", encoding="utf-8")
    os.symlink(target, tmp_path / crashlog.CRASH_LOG)
    crashlog.run_logged(lambda: 0, root=str(tmp_path))
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_log_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(crashlog, "CRASH_LOG_MAX_BYTES", 2048)
    for _ in range(100):
        crashlog.run_logged(lambda: 0, root=str(tmp_path))
    assert (tmp_path / crashlog.CRASH_LOG).stat().st_size < 4096


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX fatal signal")
def test_fatal_fault_is_dumped(tmp_path):
    code = (
        "import faulthandler, sys\n"
        "from src.core import crashlog\n"
        f"crashlog.run_logged(lambda: faulthandler._sigsegv(), root={str(tmp_path)!r})\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, timeout=60)
    assert result.returncode != 0
    text = _log(tmp_path)
    assert "started" in text
    assert "Fatal Python error" in text
    assert "ended" not in text
