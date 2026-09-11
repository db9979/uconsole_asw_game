import json
import hashlib
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
CONTACT_NAMES = {
    "acoustics.json", "aircraft.json", "animals.json", "civilians.json",
    "decoys.json", "sources.json", "subs.json", "torpedoes.json", "warships.json",
}
LOADOUT_NAMES = {"air_defense.json", "ownship.json"}
CONTACT_ANALYSIS_MANIFEST = json.loads(
    (ROOT / "data/contact_analysis/manifest.json").read_text(encoding="utf-8"))
CONTACT_ANALYSIS_NAMES = {
    "manifest.json", *(item["filename"] for item in CONTACT_ANALYSIS_MANIFEST["assets"]),
}
CONTACT_ANALYSIS_HASHES = {
    item["filename"]: item["sha256"] for item in CONTACT_ANALYSIS_MANIFEST["assets"]
}


def test_editor_templates_are_importlib_resources():
    package = resources.files("data.editor_templates")
    assert {item.name for item in package.iterdir() if item.name.endswith(".json")} == TEMPLATE_NAMES
    assert json.loads(package.joinpath("mission.json").read_text(encoding="utf-8"))["version"] == 1
    contacts = resources.files("data.contacts")
    assert {item.name for item in contacts.iterdir() if item.name.endswith(".json")} == CONTACT_NAMES
    loadouts = resources.files("data.loadouts")
    assert {item.name for item in loadouts.iterdir() if item.name.endswith(".json")} == LOADOUT_NAMES
    analysis = resources.files("data.contact_analysis")
    analysis_names = {item.name for item in analysis.iterdir()
                      if item.name != "__init__.py" and item.is_file()}
    assert analysis_names == CONTACT_ANALYSIS_NAMES
    for name, digest in CONTACT_ANALYSIS_HASHES.items():
        assert hashlib.sha256(analysis.joinpath(name).read_bytes()).hexdigest() == digest


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
    for name in CONTACT_NAMES:
        assert f"data/contacts/{name}" in wheel_names
    for name in LOADOUT_NAMES:
        assert f"data/loadouts/{name}" in wheel_names
    wheel_analysis = {name.removeprefix("data/contact_analysis/")
                      for name in wheel_names
                      if name.startswith("data/contact_analysis/")
                      and name != "data/contact_analysis/__init__.py"}
    assert wheel_analysis == CONTACT_ANALYSIS_NAMES
    with zipfile.ZipFile(wheel) as archive:
        for name in CONTACT_ANALYSIS_NAMES:
            assert archive.read(f"data/contact_analysis/{name}") == \
                (ROOT / "data/contact_analysis" / name).read_bytes()
    assert any(name.endswith(".dist-info/licenses/THIRD_PARTY_NOTICES.md")
               for name in wheel_names)
    assert any(name.endswith("-0.1.7.dist-info/METADATA") for name in wheel_names)

    source = next(tmp_path.glob("u_jagd-*.tar.gz"))
    with tarfile.open(source) as archive:
        source_names = set(archive.getnames())
    for name in TEMPLATE_NAMES:
        assert any(path.endswith(f"/data/editor_templates/{name}") for path in source_names)
    for name in ("index.html", "app.js", "style.css"):
        assert any(path.endswith(f"/data/commander/{name}") for path in source_names)
    for name in CONTACT_NAMES:
        assert any(path.endswith(f"/data/contacts/{name}") for path in source_names)
    for name in LOADOUT_NAMES:
        assert any(path.endswith(f"/data/loadouts/{name}") for path in source_names)
    source_analysis = {Path(name).name for name in source_names
                       if "/data/contact_analysis/" in name
                       and not name.endswith("/__init__.py")}
    assert source_analysis == CONTACT_ANALYSIS_NAMES
    with tarfile.open(source) as archive:
        for name in CONTACT_ANALYSIS_NAMES:
            member = next(item for item in archive.getmembers()
                          if item.name.endswith(f"/data/contact_analysis/{name}"))
            assert archive.extractfile(member).read() == \
                (ROOT / "data/contact_analysis" / name).read_bytes()
    assert any(path.endswith("/THIRD_PARTY_NOTICES.md") for path in source_names)

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
         "from src.core.version import APP_VERSION; assert APP_VERSION == '0.1.7'; "
          "from src.commander.server import CommanderServer; "
          "server=CommanderServer(); server.start('127.0.0.1',0); server.stop(); "
          "assert resources.files('data.commander').joinpath('app.js').is_file(); "
           "assert resources.files('data.contacts').joinpath('sources.json').is_file(); "
            "assert resources.files('data.loadouts').joinpath('ownship.json').is_file(); "
            "from src.data.contact_analysis import load_contact_analysis_assets; "
            "routes=load_contact_analysis_assets(); "
            f"assert len(routes) == {len(CONTACT_ANALYSIS_NAMES)}"],
        cwd=tmp_path, env=environment, check=True, capture_output=True, text=True)
