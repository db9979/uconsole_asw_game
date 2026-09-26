"""Physics upgrades must keep the recorded 1.0.0 gameplay calibration."""

import importlib.util
import json
import os
import pytest

pytestmark = pytest.mark.slow  # generation/calibration runs above 20 s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tool():
    spec = importlib.util.spec_from_file_location(
        "calibrate", os.path.join(ROOT, "tools", "calibrate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_calibration_holds_within_tolerance():
    tool = _tool()
    golden = tool.load_json(tool.GOLDEN_PATH, None)
    assert golden is not None and golden["metrics"]
    problems = tool.compare(tool.measure_all(), golden,
                            tool.load_json(tool.DEVIATIONS_PATH, {}))
    assert problems == []


def test_every_deviation_is_justified_and_known():
    tool = _tool()
    golden = tool.load_json(tool.GOLDEN_PATH, None)
    with open(tool.DEVIATIONS_PATH, encoding="utf-8") as handle:
        deviations = json.load(handle)
    for key, entry in deviations.items():
        assert key in golden["metrics"], key
        assert isinstance(entry.get("reason"), str) and len(entry["reason"]) > 20
        assert set(entry) <= {"reason", "value", "tolerance", "phase"}
