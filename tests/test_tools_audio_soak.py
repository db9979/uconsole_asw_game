"""The audio soak tool runs headless, isolates user data and reports continuity."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("audio_soak_tool", ROOT / "tools" / "audio_soak.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.timeout(240)
def test_audio_soak_tool_runs_headless_and_reports_ok(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".u-jagd").mkdir()
    marker = fake_home / ".u-jagd" / "settings.json"
    marker.write_text("{}", encoding="utf-8")
    env = dict(os.environ, HOME=str(fake_home), SDL_VIDEODRIVER="dummy",
               SDL_AUDIODRIVER="dummy")
    env.pop("U_JAGD_AUDIO_DEBUG", None)
    env.pop("U_JAGD_PERF_DEBUG", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "audio_soak.py"), "host",
         "--dummy-audio", "--duration", "8", "--clients", "3",
         "--bump-every", "3", "--retune-every", "4"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=200)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "RESULT: OK" in out
    assert "stream sonar:" in out and "stream uboot_sonar:" in out
    assert "backwards 0" in out and "silences_over_2.0s 0" in out
    # Mixer starvation after the warm-up fails the run (RESULT above).
    assert "local mixer:" in out
    assert "epoch steps" in out
    # The tool never writes into the caller's ~/.u-jagd.
    assert sorted(path.name for path in (fake_home / ".u-jagd").iterdir()) == ["settings.json"]
    assert marker.read_text(encoding="utf-8") == "{}"


def test_warmup_baseline_counts_only_starvation_after_the_cold_start():
    audio_soak = _load_tool()
    # main 2026-10-07: an 8 s first frame on a busy runner, then one 638 ms
    # frame, starved the mixer once before the stream ran steadily.
    perf = [{"t": 100.0}, {"t": 101.0}, {"t": 102.0}, {"t": 103.0}]
    audio = [{"t": 100.2, "channel_idle": 0}, {"t": 101.1, "channel_idle": 1},
             {"t": 102.1, "channel_idle": 1}, {"t": 103.1, "channel_idle": 1}]
    assert audio_soak._warmup_baseline(perf, audio, 2.0)["channel_idle"] == 1
    # A later stall still counts.
    audio.append({"t": 104.0, "channel_idle": 2})
    assert audio[-1]["channel_idle"] - audio_soak._warmup_baseline(perf, audio, 2.0)["channel_idle"] == 1
    assert audio_soak._warmup_baseline(perf, audio, 0.0) == {}
    assert audio_soak._warmup_baseline([], audio, 2.0) == {}
