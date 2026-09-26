"""pyproject.toml contracts: parallel test defaults, markers, dev-only tools."""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def project():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_xdist_is_a_dev_extra_not_a_runtime_dependency(project):
    runtime = project["project"].get("dependencies", [])
    assert not any("xdist" in item for item in runtime)
    assert any(item.startswith("pytest-xdist") for item in
               project["project"]["optional-dependencies"]["dev"])


def test_pytest_runs_in_parallel_by_default_with_registered_markers(project):
    options = project["tool"]["pytest"]["ini_options"]
    assert "-n auto" in options["addopts"]
    names = {marker.split(":")[0] for marker in options["markers"]}
    assert {"browser", "slow", "hardware"} <= names


def test_browser_tests_are_marked_automatically():
    # conftest marks every module that drives Chromium; this module does not.
    from conftest import drives_browser
    tests = Path(__file__).resolve().parent
    assert drives_browser(tests / "test_opfor_web.py") is True
    assert drives_browser(tests / "test_commander_layout.py") is True
    assert drives_browser(__file__) is False
