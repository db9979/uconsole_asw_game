"""Status lamp notes: why a lamp shows its state and what to do."""

from src.core import config, status_tips
from src.core.game import Game
from src.core.i18n import Translator
from src.ui.stations.helicopter import _clock


def _game(language="en"):
    return Game(seed=1234, start_menu=False, audio_enabled=False, language=language)


def _text(note, translator):
    tip = status_tips.localized(note, translator)
    return tip["title"] + " | " + " / ".join(tip["lines"])


def test_launch_lamps_name_the_launch_preparation_time_left():
    game = _game()
    tr = Translator("en")
    game.helo.fuel_s = 40 * 60
    game.helo.order_prep()
    game.helo.prep_s = 125.0
    notes = status_tips.helicopter(game)
    hangar = _text(notes["state_hangar"], tr)
    assert "2:05" in hangar and "H" in notes["state_hangar"]["keys"]
    assert "2:05" in _text(notes["launch"], tr)
    assert "2:05" in _text(notes["state_deck"], tr)


def test_launch_lamps_name_the_refuelling_still_needed():
    game = _game("de")
    tr = Translator("de")
    game.helo.fuel_s = 2 * 60
    game.helo.order_prep()
    game.helo.prep_s = 0.0
    clock = _clock(game.helo.refuel_left_s(config.HELO_LAUNCH_MIN_FUEL_S))
    text = _text(status_tips.helicopter(game)["state_hangar"], tr)
    assert "TANKEN" in text and clock in text


def test_every_role_gets_bounded_localized_notes():
    game = _game()
    tr = Translator("en")
    for role in ("bridge", "sonar", "weapons", "damage", "opz", "radio",
                 "engine", "helicopter", "eloka"):
        tips = status_tips.for_role(game, role, tr)
        assert len(tips) <= status_tips.LAMP_TIPS_MAX
        for name, tip in tips.items():
            assert set(tip) == {"title", "label", "value", "level", "lines", "keys"}, name
            assert tip["title"] and all(isinstance(line, str) for line in tip["lines"])
