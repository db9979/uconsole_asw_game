"""Every scenario text the menu shows has a catalog entry in both languages."""

import json
from pathlib import Path

from src.core import config

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"s1_patrouille": "patrol", "s2_doppeljagd": "double",
        "s3_abfang": "intercept", "s4_zufall": "random",
        "s5_durchbruch": "breakthrough", "s6_aufklaerung": "recon",
        "s7_geleitzug": "convoy_attack", "s8_meerenge": "strait",
        "s9_kampfschwimmer": "swimmers", "s10_versorger": "escort",
        "s11_geleitschutz": "convoy_escort", "s12_datum": "datum",
        "s13_fuehlung": "trail", "s14_hafenschutz": "harbour",
        "s15_versorgung": "ras", "s16_seenot": "rescue", "s17_duell": "duel",
        "s18_heimkehr": "homecoming", "s19_abholung": "pickup",
        "s20_lauschposten": "elint", "s21_suchgruppe": "search_group",
        "s22_jagdgruppe": "hunter_group",
        "frei_fregatte": "free", "frei_uboot": "free_boat"}


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


def test_patrol_always_brings_the_old_diesel_its_brief_promises():
    from src.core.mission import Mission
    for seed in range(200):
        assert Mission(seed, "patrouille").sub_types == ["diesel_alt"]
    # Free Hunt still draws every type.
    drawn = {kind for seed in range(200)
             for kind in Mission(seed, None, config.DEFAULT_DIFFICULTY).sub_types}
    assert drawn == {"diesel_alt", "aip_modern", "ssn"}
    for language, word in (("en", "anti-ship missiles"), ("de", "Seezielflugkörpern")):
        catalog = json.loads((ROOT / "data" / "i18n" / f"{language}.json")
                             .read_text(encoding="utf-8"))
        assert word in catalog["scenario.patrol.brief"]
