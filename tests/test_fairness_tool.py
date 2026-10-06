"""tools/fairness.py: argument parsing and one short game in a fresh process."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "fairness.py"


def _tool():
    spec = importlib.util.spec_from_file_location("fairness_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_lists_and_defaults():
    tool = _tool()
    assert tool.parse_seeds("7") == [7]
    assert tool.parse_seeds("1-3,5,3") == [1, 2, 3, 5]
    for bad in ("", "3-1", "x", "-2", "1,,2"):
        with pytest.raises(ValueError):
            tool.parse_seeds(bad)
    args = tool.build_parser().parse_args([])
    assert args.seeds == list(range(1, 21)) and args.jobs == 2
    assert args.scenarios == list(tool.KEYS) and not args.crewed and not args.short
    args = tool.build_parser().parse_args(["--crewed", "--short", "--scenarios", "s7",
                                           "--seeds", "4-5", "--max-sim-s", "30"])
    assert (args.crewed, args.short, args.scenarios, args.seeds, args.max_sim_s) == (
        True, True, ["s7"], [4, 5], 30.0)


def test_summary_counts_each_side():
    rows = [dict(scenario="s7", seed=1, result="SIEG"), dict(scenario="s7", seed=2, result=None),
            dict(scenario="s7", seed=3, result="VERLOREN")]
    assert _tool().summarise(rows) == {"s7": {"frigate": 1, "boat": 1, "open": 1, "runs": 3}}


def test_one_short_run_writes_its_row(tmp_path):
    out = tmp_path / "run.json"
    # Its own home: the game in the child never sees the real ~/.u-jagd.
    env = dict(os.environ, HOME=str(tmp_path), PYTHONPATH=str(ROOT))
    subprocess.run([sys.executable, str(TOOL), "--scenarios", "s1", "--seeds", "3",
                    "--jobs", "1", "--max-sim-s", "20", "--out", str(out)],
                   check=True, cwd=tmp_path, env=env, capture_output=True, timeout=300)
    data = json.loads(out.read_text(encoding="utf-8"))
    row = data["rows"][0]
    assert (row["scenario"], row["seed"], row["result"]) == ("s1", 3, None)
    assert 20 <= row["t"] <= 21 and data["summary"]["s1"]["open"] == 1
