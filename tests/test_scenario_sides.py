"""The scenario lists follow the side the uConsole plays."""

import pygame

from src.core import config
from src.core.game import Game
from src.core.lobby import LobbyRoom

BOAT = ("s5_durchbruch", "s6_aufklaerung", "s7_geleitzug", "s8_meerenge",
        "s9_kampfschwimmer", "s10_versorger")


def test_each_scenario_belongs_to_exactly_one_side():
    frigate = config.scenarios_for_side("frigate")
    boat = config.scenarios_for_side("uboot")
    assert frigate == ("s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall")
    assert boat == BOAT
    assert sorted(frigate + boat) == sorted(config.SCENARIO_ORDER)


def test_titles_no_longer_carry_the_side():
    from src.core.i18n import Translator
    for language in ("en", "de"):
        tr = Translator(language)
        for key, name in config.SCENARIO_NAMES.items():
            title = tr("scenario." + name + ".title")
            assert "(U-Boot)" not in title and "(submarine)" not in title


def _menu(side):
    game = Game(seed=83, start_menu=True, audio_enabled=False, language="de")
    game._handle_menu_key(pygame.K_RETURN)                   # new game: side choice
    game._handle_menu_key(pygame.K_1 if side == "frigate" else pygame.K_2)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.menu_screen == "scenario" and game.local_side == side
    return game


def test_frigate_list_cycles_and_numbers_only_frigate_scenarios():
    game = _menu("frigate")
    game.draw()
    seen = []
    for _ in range(5):
        seen.append(config.SCENARIO_ORDER[game.scenario_menu_index()])
        game._handle_menu_key(pygame.K_DOWN)
    assert seen == ["s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall",
                    "s1_patrouille"]
    game._handle_menu_key(pygame.K_5)                         # past the frigate list: ignored
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s2_doppeljagd"
    game._handle_menu_key(pygame.K_3)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.scenario_key == "s3_abfang" and game.menu_screen == "briefing"
    game.audio.shutdown()


def test_boat_list_starts_at_the_first_boat_scenario():
    game = _menu("uboot")
    game.draw()
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s5_durchbruch"
    game._handle_menu_key(pygame.K_UP)                        # wraps within the boat list
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s10_versorger"
    game._handle_menu_key(pygame.K_7)                         # past the boat list: ignored
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s10_versorger"
    game._handle_menu_key(pygame.K_1)                         # the boat list counts from 1
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s5_durchbruch"
    game._handle_menu_key(pygame.K_3)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.scenario_key == "s7_geleitzug" and game.menu_screen == "briefing"
    game._handle_menu_key(pygame.K_ESCAPE)                    # back to the boat list
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s7_geleitzug"
    game.audio.shutdown()


def test_lobby_cycles_the_missions_of_its_side():
    room = LobbyRoom("s1_patrouille", "frigate")
    seen = set()
    for _ in range(8):
        room.change(1)
        seen.add(room.scenario_key)
    assert seen == set(config.scenarios_for_side("frigate"))
    room.row = 1                                               # side row
    room.change(1)
    assert room.side == "uboot" and room.scenario_key == "s5_durchbruch"
    room.row = 0
    room.change(-1)
    assert room.scenario_key == "s10_versorger"
    assert LobbyRoom("s7_geleitzug", "frigate").scenario_key == "s1_patrouille"
