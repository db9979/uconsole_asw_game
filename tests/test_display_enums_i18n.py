"""Engine orders and the boat's battery phase are shown translated, never as
their internal enum names (uConsole and web client)."""

from src.core import config
from src.core.i18n import DISPLAY_KEYS, get_translator, load_catalog
from src.enemies.endurance import PHASES


def test_every_telegraph_order_and_phase_has_a_label():
    orders = ["ASTERN", *(name for name, _speed in config.TELEGRAPH_ORDERS)]
    assert set(DISPLAY_KEYS["telegraph"]) == set(orders)
    assert set(DISPLAY_KEYS["endurance_phase"]) == set(PHASES)
    german = get_translator("de")
    assert german.t(DISPLAY_KEYS["telegraph"]["HALF"]) != "HALF"
    catalog = load_catalog("en")
    for order in orders:
        assert f"commander.web.telegraph_{order.lower()}" in catalog
    for phase in PHASES:
        assert f"commander.web.uboot_phase_{phase.lower()}" in catalog


def test_every_sonar_fusion_state_has_a_label():
    for status in ("KEINE DATEN", "BESTAETIGT", "DIVERGENT / GEISTERKONTAKT?", "UNSICHER",
                   "NUR BOW", "NUR TOWED", "TAS L/R?", "TAS L/R? WENDE"):
        assert status in DISPLAY_KEYS["fusion"], status
    for geometry in ("KEINE", "BRAUCHBAR", "SCHWACH"):
        assert geometry in DISPLAY_KEYS["tma"], geometry
