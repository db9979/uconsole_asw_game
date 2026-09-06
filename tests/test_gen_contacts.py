import json
import shutil
from importlib import resources

import pytest

from tools.gen_contacts import check, validate


def _copy_catalog(destination):
    source = resources.files("data.contacts")
    for item in source.iterdir():
        if item.name.endswith(".json"):
            shutil.copyfile(item, destination / item.name)


def test_validator_accepts_packaged_catalog():
    with resources.as_file(resources.files("data.contacts")) as contact_dir:
        loaded = validate(contact_dir)
    assert loaded.db_source == "contacts"


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        ("subs.json", lambda data: data["entries"][0].update(quiet=float("nan")),
         "finite number"),
        ("aircraft.json", lambda data: data["entries"][0].update(kind="unknown"),
         "invalid aircraft kind"),
        ("torpedoes.json", lambda data: data["entries"].append(data["entries"][0]),
         "duplicate key"),
        ("acoustics.json", lambda data: data["entries"].pop(),
         "every decoy"),
    ],
)
def test_validator_rejects_invalid_data(tmp_path, filename, mutate, message):
    _copy_catalog(tmp_path)
    path = tmp_path / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, allow_nan=True), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        validate(tmp_path)
    assert check(tmp_path) == 1
