"""Host side of the 1.3.207 browser layout: chart country names, the fire chain."""
from pathlib import Path

from src.commander.bridge import _polygon_area
from src.commander.projections import _fire_stage
from src.commander.server import web_catalog
from src.core.i18n import country_key, country_name, get_translator, load_catalog, localize


def test_country_names_are_localized_and_served_to_the_browser():
    assert country_key("Hong Kong S.A.R.") == "country.hong_kong_s_a_r"
    assert localize(country_name("Denmark"), get_translator("de").t) == "Dänemark"
    assert localize(country_name("Denmark"), get_translator("en").t) == "Denmark"
    # An invented legacy region keeps its own name.
    assert localize(country_name("Britannia"), get_translator("de").t) == "Britannia"
    web = web_catalog(load_catalog("de"))
    assert web["commander.web.country_germany"] == "Deutschland"
    assert all(key.startswith("commander.web.") for key in web)


def test_every_real_sector_country_has_a_name_in_both_languages():
    import gzip
    import json
    raw = (Path(__file__).resolve().parents[1] / "data" / "coastlines" / "real_sectors.json.gz").read_bytes()
    names = {name for sector in json.loads(gzip.decompress(raw))["sectors"] for name in sector["countries"]}
    for language in ("en", "de"):
        catalog = load_catalog(language)
        assert not [name for name in names if country_key(name) not in catalog], language


def test_fire_stage_follows_the_interlock_order():
    assert _fire_stage("BLOCKIERT: KEIN ZIEL") == "target"
    assert _fire_stage("BLOCKIERT: WAFFEN GESPERRT") == "release"
    assert _fire_stage("BLOCKIERT: KEINE ENTFERNUNG") == "solution"
    assert _fire_stage("BLOCKIERT: KEIN ROHR BEREIT") == "tube"
    assert _fire_stage("BLOCKIERT: WAFFENZENTRALE GESTOERT") == "station"
    assert _fire_stage("FEUER FREI") == "fire"


def test_landmass_area_orders_labels():
    assert _polygon_area([(0, 0), (2, 0), (2, 2), (0, 2)]) == 4.0
    assert _polygon_area([]) == 0.0
