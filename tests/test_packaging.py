import json
import os
import subprocess
import sys
import tarfile
import zipfile
from importlib import resources
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEMPLATE_NAMES = {
    "mission.json",
    "unit_aircraft.json",
    "unit_animal.json",
    "unit_decoy.json",
    "unit_sub.json",
    "unit_surface.json",
    "unit_torpedo.json",
}


def test_editor_templates_are_importlib_resources():
    package = resources.files("data.editor_templates")
    assert {item.name for item in package.iterdir() if item.name.endswith(".json")} == TEMPLATE_NAMES
    assert json.loads(package.joinpath("mission.json").read_text(encoding="utf-8"))["version"] == 1


def test_source_and_wheel_contain_editor_templates(tmp_path):
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel",
         "--outdir", str(tmp_path), str(ROOT)],
        cwd=tmp_path, check=True, capture_output=True, text=True)
    wheel = next(tmp_path.glob("u_jagd-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    for name in TEMPLATE_NAMES:
        assert f"data/editor_templates/{name}" in wheel_names
    for name in ("index.html", "app.js", "style.css"):
        assert f"data/commander/{name}" in wheel_names
    assert any(name.endswith("-0.1.6.dist-info/METADATA") for name in wheel_names)

    source = next(tmp_path.glob("u_jagd-*.tar.gz"))
    with tarfile.open(source) as archive:
        source_names = set(archive.getnames())
    for name in TEMPLATE_NAMES:
        assert any(path.endswith(f"/data/editor_templates/{name}") for path in source_names)
    for name in ("index.html", "app.js", "style.css"):
        assert any(path.endswith(f"/data/commander/{name}") for path in source_names)

    installed = tmp_path / "installed"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target",
         str(installed), str(wheel)],
        cwd=tmp_path, check=True, capture_output=True, text=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed)
    subprocess.run(
        [sys.executable, "-c",
         "from importlib import resources; "
         "assert resources.files('data.editor_templates').joinpath('mission.json').is_file(); "
         "from src.core.version import APP_VERSION; assert APP_VERSION == '0.1.6'; "
         "from src.commander.server import CommanderServer; "
         "server=CommanderServer(); server.start('127.0.0.1',0); server.stop(); "
         "assert resources.files('data.commander').joinpath('app.js').is_file()"],
        cwd=tmp_path, env=environment, check=True, capture_output=True, text=True)
