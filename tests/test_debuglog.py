"""Bounded diagnostic logs (crash, audio, perf) without directory handles."""

import os

from src.core import debuglog


def test_logs_are_written_where_open_takes_no_directory_handle(monkeypatch, tmp_path):
    # Windows has no dir_fd support: the crash log used to be silently lost.
    monkeypatch.setattr(os, "supports_dir_fd", set())
    debuglog.append_bounded_log(tmp_path, "crash.log", "first\n", 1000)
    debuglog.append_bounded_log(tmp_path, "crash.log", "second\n", 1000)
    assert (tmp_path / "crash.log").read_text(encoding="utf-8") == "first\nsecond\n"


def test_the_fallback_stays_bounded_and_refuses_a_symlinked_file(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "supports_dir_fd", set())
    debuglog.append_bounded_log(tmp_path, "perf.log", "x" * 20, 10)
    debuglog.append_bounded_log(tmp_path, "perf.log", "new\n", 10)
    assert (tmp_path / "perf.log").read_text(encoding="utf-8") == "new\n"
    target = tmp_path / "elsewhere.txt"
    target.write_text("keep", encoding="utf-8")
    (tmp_path / "link.log").symlink_to(target)
    debuglog.append_bounded_log(tmp_path, "link.log", "no\n", 1000)
    assert target.read_text(encoding="utf-8") == "keep"
