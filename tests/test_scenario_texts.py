"""Every scenario text the menu shows has a catalog entry in both languages."""

import json
from pathlib import Path

from src.core import config

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
        "s3_abfang": "intercept", "s4_zufall": "random",
        "s5_durchbruch": "breakthrough", "s6_aufklaerung": "recon",
        "s7_geleitzug": "convoy_attack", "s8_meerenge": "strait",
        "s9_kampfschwimmer": "swimmers", "s10_versorger": "escort"}


def test_menu_goal_and_loss_lines_are_translated():
    catalogs = [json.loads((ROOT / f"data/i18n/{lang}.json").read_text(encoding="utf-8"))
                for lang in ("en", "de")]
    assert set(KEYS) == set(config.SCENARIOS) == set(config.SCENARIO_ORDER)
    assert config.SCENARIO_NAMES == KEYS
    for scenario, name in KEYS.items():
        spec = config.SCENARIOS[scenario]
        wanted = ["title", "brief"]
        wanted += ["win"] if spec["win_text"] else []
        wanted += ["lose"] if spec["lose_text"] else []
        for field in wanted:
            for catalog in catalogs:
                assert f"scenario.{name}.{field}" in catalog, (scenario, field)
