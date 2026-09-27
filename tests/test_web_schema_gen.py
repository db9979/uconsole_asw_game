"""The browser schema's allowlists are rendered from the Python source."""

import subprocess
import sys
from pathlib import Path

import pytest

from src.commander.v2 import schema
from src.commander.v2.wire import ROLES

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _crewed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "gen_web_schema.py"
SCHEMA_JS = ROOT / "data" / "commander" / "js" / "state" / "schema.js"


def _run(*args, cwd=ROOT):
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd,
                          capture_output=True, text=True)


def test_generated_block_is_deterministic_and_checked(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import gen_web_schema
    first = gen_web_schema.render_block()
    second = gen_web_schema.render_block()
    assert first == second
    current = SCHEMA_JS.read_text(encoding="utf-8")
    assert first in current
    assert gen_web_schema.render(current) == current
    # A hand edit inside the block fails the check and is rewritten.
    copy = tmp_path / "schema.js"
    line = '    sonar: ["observations", "settings", "visualization"],\n'
    assert current.count(line) == 1
    copy.write_text(current.replace(line, line.replace('"visualization"', '"visualization", "secret"')),
                    encoding="utf-8")
    monkeypatch.setattr(gen_web_schema, "SCHEMA_JS", copy)
    assert gen_web_schema.main(["--check"]) == 1
    assert gen_web_schema.main([]) == 0
    assert copy.read_text(encoding="utf-8") == current
    assert gen_web_schema.main(["--check"]) == 0
    assert _run("--check").returncode == 0


def test_role_shapes_match_the_published_projections():
    game, server, _bridge = _crewed(seed=101)
    assert set(schema.ROLE_SHAPES) == set(ROLES)
    for role in ROLES:
        state = server.v2_states[role]
        assert state["role"] == role, role
        assert set(state[role]) == set(schema.ROLE_SHAPES[role]), role
    assert schema.HELICOPTER_TACTICAL_FIELDS[:len(schema.TACTICAL_FIELDS)] == schema.TACTICAL_FIELDS


@pytest.mark.parametrize("name", ["TACTICAL_FIELDS", "SONAR_FIELDS", "RADIO_FIELDS"])
def test_field_tuples_are_unique_and_shared_with_the_projections(name):
    from src.commander import projections
    values = getattr(schema, name)
    assert len(set(values)) == len(values)
    assert getattr(projections, "_" + name) is values
