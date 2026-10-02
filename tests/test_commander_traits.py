"""Computer commanders have a character: from the seed, hinted, named."""

from collections import Counter

import pytest

from src.core import commander_traits as traits
from src.core.game import Game
from src.core.i18n import localize


class _Sub:
    def __init__(self, seed, ident):
        self.sensor_seed, self.id = seed, ident


def test_characters_come_from_the_seed_and_all_four_occur():
    kinds = Counter(traits.sub_kind(_Sub(seed, 3)) for seed in range(400))
    assert set(kinds) == set(traits.KINDS)
    assert min(kinds.values()) > 60
    assert traits.sub_kind(_Sub(17, 3)) == traits.sub_kind(_Sub(17, 3))
    assert {traits.hunter_kind(seed) for seed in range(100)} == set(traits.KINDS)


def test_the_characters_average_out():
    for table in (traits.SUB, traits.HUNTER):
        for factor in next(iter(table.values())):
            mean = sum(row[factor] for row in table.values()) / len(table)
            assert 0.9 <= mean <= 1.15, factor


def test_the_attack_rate_follows_the_character(monkeypatch):
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    sub = next(sub for sub in game.subs if sub.side == "hostile")
    for kind in traits.KINDS:
        monkeypatch.setattr(traits, "sub_kind", lambda _sub, kind=kind: kind)
        assert traits.sub_factor(sub, "attack") == traits.SUB[kind]["attack"]


def test_hq_hints_once_early_and_the_debrief_names_the_commander(monkeypatch):
    monkeypatch.setattr(traits, "hinted", lambda seed, side: True)
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    sub = min((sub for sub in game.subs if sub.side == "hostile"), key=lambda sub: sub.id)
    kind = traits.sub_kind(sub)
    game.mission_time = traits.HINT_AT_S - 0.05
    before = len(game.messages)
    game._commander_hint(0.0)
    assert len(game.messages) == before
    game.mission_time = traits.HINT_AT_S + 0.05
    game._commander_hint(0.1)
    hint = str(localize(game.messages[-1][1], game.tr))
    assert "rates the enemy submarine's commander" in hint
    count = len(game.messages)
    game.mission_time += 0.1
    game._commander_hint(0.1)
    assert len(game.messages) == count
    game.frigate_debrief.finish(game, game.mission_time)
    event = next(e for e in game.frigate_debrief.events if e["kind"] == "enemy_commander")
    assert event["params"]["character"] == kind
    from src.ui.debrief_view import event_text
    assert str(localize(event_text(event, "debrief."), game.tr)).startswith("The enemy commander was")


@pytest.mark.parametrize("kind", traits.KINDS)
def test_every_character_has_its_texts(kind):
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    for key in (f"commander.kind.{kind}", f"hq.commander_hint.{kind}",
                f"uboot.event.hq_hint_{kind}"):
        assert game.tr(key) != key
