"""tools/hw_report.py: the hardware run summary for the uConsole checklist."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "hw_report", Path(__file__).resolve().parents[1] / "tools" / "hw_report.py")
hw_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw_report)


def _perf(path, start, seconds, fps=30, frame_max=40.0, dropped=0.0):
    lines = [f"t={start + i:.1f} fps={fps} sim_ms=2.00 commander_max_ms=5.0 "
             f"frame_max_ms={frame_max:.1f} sim_lag_ms=0.0 sim_dropped_ms={dropped * i:.1f}"
             for i in range(seconds)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_clean_run_passes_and_only_the_newest_run_counts(tmp_path, capsys):
    perf, audio = tmp_path / "perf.log", tmp_path / "audio.log"
    _perf(perf, 1000.0, 60, fps=12, frame_max=400.0)          # an older, bad run
    old = perf.read_text()
    _perf(perf, 5000.0, 120)
    perf.write_text(old + perf.read_text(), encoding="utf-8")
    audio.write_text("".join(f"t={5000 + i}.0 channel_idle=3 sonar_underruns=1\n"
                             for i in range(120)), encoding="utf-8")
    assert hw_report.main(["--perf", str(perf), "--audio", str(audio)]) == 0
    out = capsys.readouterr().out
    assert "| Frame-Zeit Mittel (30 FPS) | 33.3 ms | ok |" in out
    assert "channel_idle im Lauf | 0 | ok" in out


def test_a_slow_run_is_flagged_and_missing_logs_say_how(tmp_path, capsys):
    perf = tmp_path / "perf.log"
    _perf(perf, 10.0, 90, fps=20, frame_max=180.0, dropped=5.0)
    assert hw_report.main(["--perf", str(perf), "--audio", str(tmp_path / "none")]) == 1
    out = capsys.readouterr().out
    assert "Frame-Zeit Mittel (30 FPS) | 50.0 ms | abweichung" in out
    assert "sim_dropped_ms im Lauf" in out and "abweichung" in out
    assert hw_report.main(["--perf", str(tmp_path / "x"), "--audio", str(tmp_path / "y")]) == 2
