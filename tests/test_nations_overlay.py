"""The N overlay is a catalog and chart reference, not a live truth view."""

from types import SimpleNamespace

from src.data.catalog import CATALOG
from src.core.game import Game
from src.nations.nations import reference_summary
from src.world.coastline import Coastline


def test_nations_summary_uses_current_chart_and_catalog():
    coast = Coastline({"landmasses": [
        {"name": "A", "nation": "TESTLAND", "points": [[0, 0], [1, 0], [0, 1]]},
    ], "airbases": []})
    summary = reference_summary(coast, CATALOG)
    assert summary["countries"] == ("TESTLAND",)
    assert summary["friendly"] == tuple(sorted(
        p.name for p in CATALOG.surfaces.values()
        if p.default_faction == "FREUND"))
    assert "Improved-Kilo" in summary["hostile_subs"]
    assert "Admiral-Gorshkov-Fregatte" in summary["hostile_surfaces"]

    coast.metadata = {"countries": ["SECOND", "FIRST", "FIRST"]}
    catalog = SimpleNamespace(
        subs={"new": SimpleNamespace(name="New submarine", default_faction="FEIND")},
        surfaces={"new": SimpleNamespace(name="New frigate", category="KAMPFSCHIFF",
                                         default_faction="FREUND")})
    changed = reference_summary(coast, catalog)
    assert changed["countries"] == ("FIRST", "SECOND")
    assert changed["friendly"] == ("New frigate",)
    assert changed["hostile_subs"] == ("New submarine",)
    assert changed["hostile_surfaces"] == ()


def test_opening_nations_refreshes_reference_after_world_change():
    game = Game(seed=12, start_menu=False)
    game._open_administration("nations")
    first = game._nations_summary
    game.world.coast.metadata = {"countries": ["NEW AREA"]}
    game._open_administration("nations")
    assert game._nations_summary is not first
    assert game._nations_summary["countries"] == ("NEW AREA",)
