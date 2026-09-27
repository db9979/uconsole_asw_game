"""The audio soak tool runs headless, isolates user data and reports continuity."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


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
    assert "local mixer: underruns 0" in out
    assert "epoch steps" in out
    # The tool never writes into the caller's ~/.u-jagd.
    assert sorted(path.name for path in (fake_home / ".u-jagd").iterdir()) == ["settings.json"]
    assert marker.read_text(encoding="utf-8") == "{}"
