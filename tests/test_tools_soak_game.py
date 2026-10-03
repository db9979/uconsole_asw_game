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


def _mission_save():
    import json

    from src.core.game import Game

    game = Game(seed=3, start_menu=False, show_splash=False, audio_enabled=False,
                language="en")
    assert game.start_new_game("s1_patrouille", "fixed", seed=3)
    for _ in range(20):
        game.update(0.1)
    return json.loads(json.dumps(game.save_state(), allow_nan=False))


def test_a_refused_save_names_the_innermost_check():
    document = _mission_save()
    document["route"] = 5
    reason = soak_game.diagnose_load(document)
    assert reason.startswith("refused by: src/ship/route.py:"), reason
    assert "valid_save_document()" in reason and "_load_save_data()" in reason


def test_first_difference_names_the_field():
    saved = {"a": [1, {"b": 2.0}], "c": True}
    assert soak_game.first_difference(saved, saved) is None
    restored = {"a": [1, {"b": 2.5}], "c": True}
    assert soak_game.first_difference(restored, saved) == "$.a[1].b: saved 2.0, restored 2.5"
    assert "only in saved" in soak_game.first_difference({"a": [1, {"b": 2.0}]}, saved)


def test_refused_save_is_kept_for_analysis(tmp_path):
    import argparse
    import gzip
    import json

    dumps = tmp_path / "refused"
    soak = soak_game.Soak(argparse.Namespace(dump_dir=str(dumps)), "s1_patrouille",
                          "frigate", 7)
    document = _mission_save()

    class _Game:
        sim_t = 12.0

    note = soak.dump(document, _Game())
    files = list(dumps.iterdir())
    assert len(files) == 1 and files[0].name in note
    with gzip.open(files[0], "rt", encoding="utf-8") as stream:
        assert json.load(stream) == document


def test_nightly_workflow_soaks_every_scenario():
    import re

    from src.core import config

    text = (ROOT / ".github" / "workflows" / "soak.yml").read_text(encoding="utf-8")
    block = text[text.index("scenario: ["):]
    block = block[:block.index("]")]
    assert re.findall(r"[a-z0-9_]+", block.split("[", 1)[1]) == list(config.SCENARIO_ORDER)
