"""The nightly soak tool (tools/soak_game.py) runs and reports."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import soak_game  # noqa: E402


def test_short_soak_runs_both_sides_and_writes_a_report(tmp_path):
    report = tmp_path / "soak.md"
    code = soak_game.main(["--scenario", "s1_patrouille", "--minutes", "0.5",
                           "--check-every", "0.25", "--check-s", "5",
                           "--seed", "4242", "--report", str(report)])
    text = report.read_text(encoding="utf-8")
    assert "s1_patrouille / frigate" in text and "s1_patrouille / uboot" in text
    assert "--seed 4242" in text
    assert code == 0, text


def test_operator_is_seeded():
    left, right = soak_game.Operator(5), soak_game.Operator(5)
    for _ in range(200):
        assert [(e.type, getattr(e, "key", None), getattr(e, "pos", None))
                for e in left.events()] == [
            (e.type, getattr(e, "key", None), getattr(e, "pos", None))
            for e in right.events()]
