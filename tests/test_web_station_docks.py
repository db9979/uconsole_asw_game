"""Station docks in the browser (W4): controls before read tables, read tables
fold under their heading, the tubes shown once on the weapons page, damaged
compartments first, and two card columns on 1800 px screens."""

import json
import re

from commander_web import run_module_probe
from test_commander_assets import ASSETS, Document


def _grid_cards(document, station):
    """Classes of the direct cards of a station's grid, in markup order."""
    html = ASSETS.joinpath("index.html").read_text()
    section = html[html.index(f'id="station-{station}"'):]
    grid = section[section.index('<div class="station-grid">'):]
    return re.findall(r'<article(?: id="[^"]*")? class="(station-card-view[^"]*)"', grid.split("</section>", 1)[0])


def test_controls_come_before_read_tables():
    for station in ("opz", "weapons", "engine", "sonar"):
        cards = _grid_cards(None, station)
        readout = [index for index, classes in enumerate(cards) if "card-readout" in classes]
        assert readout, station
        assert all("card-readout" in classes for classes in cards[readout[0]:]), (station, cards)


def test_read_tables_fold_and_tubes_appear_once():
    html = ASSETS.joinpath("index.html").read_text()
    document = Document(html)
    folds = [attrs for _, attrs in document.elements if "card-fold" in attrs.get("class", "")]
    assert len(folds) >= 10
    assert all(attrs.get("type") == "button" and attrs["aria-expanded"] == "true"
               and attrs["data-fold"] == attrs["data-i18n"] for attrs in folds)
    ids = {attrs.get("id") for _, attrs in document.elements}
    assert "weapons-tubes" not in ids and "weapons-tube-lamps" not in ids
    css = ASSETS.joinpath("css/stations.css").read_text()
    assert '.card-readout[data-folded="true"] > :not(h3) { display: none; }' in css
    assert "@media (min-width: 1800px)" in css and '[data-station="weapons"]' in css


def test_folds_toggle_and_damage_sorts_first(tmp_path):
    probe = r"""
import { $ } from "./js/core/base.js";
import { init } from "./js/views/card-fold.js";
import { byDamage } from "./js/stations/damage.js";
const out = {};
init();
const button = document.querySelector('#station-opz .card-fold[data-fold="station_radar"]');
button.click();
out.folded = button.closest(".card-readout").dataset.folded;
out.expanded = button.getAttribute("aria-expanded");
button.click();
out.unfolded = button.closest(".card-readout").dataset.folded;
const room = (key, state, flood = 0, fire = 0) => ({key, state, flood, fire});
out.order = byDamage([room("bow", "OK"), room("ops", "FLUTEND", 40), room("engine", "OK", 0, 10),
  room("hangar", "ZERSTOERT"), room("stern", "OK")]).map((row) => row.key);
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    assert json.loads(root["data-result"]) == {
        "folded": "true", "expanded": "false", "unfolded": "false",
        "order": ["hangar", "ops", "engine", "bow", "stern"]}
