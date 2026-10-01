"""The scenario lists follow the side the uConsole plays."""

import pygame

from src.core import config
from src.core.game import Game
from src.core.lobby import LobbyRoom

BOAT = ("s5_durchbruch", "s6_aufklaerung", "s7_geleitzug", "s8_meerenge",
        "s9_kampfschwimmer", "s10_versorger", "s17_duell", "s18_heimkehr",
        "s19_abholung", "s20_lauschposten", "s22_jagdgruppe")
FRIGATE = ("s1_patrouille", "s2_doppeljagd", "s3_abfang", "s4_zufall",
           "s11_geleitschutz", "s12_datum", "s13_fuehlung", "s14_hafenschutz",
           "s15_versorgung", "s16_seenot", "s21_suchgruppe")


def test_each_scenario_belongs_to_exactly_one_side():
    frigate = config.scenarios_for_side("frigate")
    boat = config.scenarios_for_side("uboot")
    assert frigate == FRIGATE
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
    for _ in range(13):
        seen.append("custom" if game.menu_sel == game.custom_row_sel()
                    else config.SCENARIO_ORDER[game.scenario_menu_index()])
        game._handle_menu_key(pygame.K_DOWN)
    # The list ends with the side's own missions, then wraps.
    assert seen == list(FRIGATE) + ["custom", "s1_patrouille"]
    game._handle_menu_key(pygame.K_0)                         # the tenth row
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s16_seenot"
    game._handle_menu_key(pygame.K_2)
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s2_doppeljagd"
    game._handle_menu_key(pygame.K_3)
    game._handle_menu_key(pygame.K_RETURN)
    assert game.scenario_key == "s3_abfang" and game.menu_screen == "briefing"
    game.audio.shutdown()


def test_boat_list_starts_at_the_first_boat_scenario():
    game = _menu("uboot")
    game.draw()
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s5_durchbruch"
    game._handle_menu_key(pygame.K_UP)                        # wraps to the own missions
    assert game.menu_sel == game.custom_row_sel()
    game._handle_menu_key(pygame.K_UP)                        # then the boat list's last
    assert config.SCENARIO_ORDER[game.scenario_menu_index()] == "s22_jagdgruppe"
    game._handle_menu_key(pygame.K_6)
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
    for _ in range(12):
        room.change(1)
        seen.add(room.scenario_key)
    assert seen == set(config.scenarios_for_side("frigate"))
    room.row = 1                                               # side row
    room.change(1)
    assert room.side == "uboot" and room.scenario_key == "s5_durchbruch"
    room.row = 0
    room.change(-1)
    assert room.scenario_key == "s22_jagdgruppe"
    assert LobbyRoom("s7_geleitzug", "frigate").scenario_key == "s1_patrouille"


def test_own_missions_row_lists_only_the_sides_missions(tmp_path):
    from src.core.mission_definition import default_mission
    from src.data.user_content import default_store
    store = default_store(config.SAVE_DIR)
    frigate = default_mission("user.own_frigate")
    frigate.update(name="Own frigate")
    frigate["objective"].update(type="survive")
    store.save("mission", frigate)
    boat = default_mission("user.own_boat")
    boat.update(name="Own boat", side="uboot", boat_id="me")
    boat["units"]["exact"] = [{"id": "me", "profile": "diesel_alt", "side": "hostile",
                               "placement": {"kind": "fixed", "x": 300.0, "y": 250.0},
                               "course_deg": 0.0, "speed_kn": 0.0, "depth_m": 60.0}]
    boat["objective"].update(type="survive")
    store.save("mission", boat)
    game = _menu("uboot")
    game._handle_menu_key(pygame.K_o)
    assert game.menu_screen == "custom"
    assert [record.key for record in game._custom_records] == ["user.own_boat"]
    game.draw()
    game._handle_menu_key(pygame.K_RETURN)
    assert not game.in_menu and game.local_side == "uboot"
    assert game.custom_mission_definition["key"] == "user.own_boat"
    game.audio.shutdown()
    other = _menu("frigate")
    other._handle_menu_key(pygame.K_UP)
    other._handle_menu_key(pygame.K_RETURN)
    assert [record.key for record in other._custom_records] == ["user.own_frigate"]
    other._handle_menu_key(pygame.K_ESCAPE)
    assert other.menu_screen == "scenario" and other.menu_sel == other.custom_row_sel()
    other.audio.shutdown()
