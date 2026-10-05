"""Key footers show every key of a page: what does not fit goes behind a
"more" chip that pages through the rest; each chip presses its key."""

import sys
from pathlib import Path

import pygame

from src.core import uboot_local
from src.core.game import Game
from src.core.station import Station
from src.ui import pointer, uboot_view
from src.ui.stations import common
from src.ui.stations.helicopter import HELICOPTER_FOOTER
from src.ui.weapons_view import WEAPONS_FOOTER

sys.path.insert(0, str(Path(__file__).parent))
from test_opfor_sub import _game as _boat_game  # noqa: E402


SPECS = tuple((key, "bridge.footer.course") for key in "ABCDEFGHIJKLMNOP")


def _legends(surface, rect):
    pointer.reset()
    common._shortcut_footer(surface, rect, SPECS)
    keys = [(t.key, t.mod) for t in pointer.targets("station") if t.key is not None]
    more = [target for target in pointer.targets("station") if target.action]
    return keys, more


def test_footer_page_fits_whole_segments_and_flags_overflow():
    shown, more = common.footer_page(SPECS[:3], [50, 50, 50], 400, 40, 0)
    assert shown == [0, 1, 2] and not more
    shown, more = common.footer_page(SPECS, [50] * 16, 240, 40, 0)
    assert shown == [0, 1, 2, 3] and more
    shown, _more = common.footer_page(SPECS, [50] * 16, 240, 40, 12)
    assert shown == [12, 13, 14, 15]


def test_more_chip_pages_through_every_key_and_wraps():
    pygame.init()
    surface = pygame.Surface((1280, 720))
    rect = (20, 600, 600, 20)
    seen, first = set(), None
    common._FOOTER_OFFSET.clear()
    for _ in range(40):
        keys, more = _legends(surface, rect)
        assert more, "an overflowing footer has a more chip"
        assert keys
        first = first or keys
        seen.update(str(spec) for spec in keys)
        more[0].action((0, 0))
        if _legends(surface, rect)[0] == first:
            break
    assert len(seen) == len(SPECS)


def test_frigate_pages_without_a_key_row_have_one_now():
    assert len(WEAPONS_FOOTER) == 2 and len(HELICOPTER_FOOTER) == 3
    assert ("M", "weapons.footer.target") in WEAPONS_FOOTER[0]
    # Ctrl+Enter is not a chip there: fire by click only at the weapons station.
    assert all(key != "Ctrl+Enter" for page in HELICOPTER_FOOTER for key, _ in page)


def test_submarine_footer_extras_are_allowed_at_their_station(monkeypatch):
    game = _boat_game()
    game.local_side = "uboot"
    game._update(0.05)
    boat = game.opfor
    flashes = []
    monkeypatch.setattr(game, "flash", lambda text, *a, **k: flashes.append(repr(text)))
    for (station, page_name), specs in uboot_view._FOOTER_MORE.items():
        uboot_local.set_local_station(game, station)
        boat.command_page = uboot_view.station_pages(station).index(page_name)
        for key, _label in specs:
            for code, mod in pointer.legend_keys(key):
                flashes.clear()
                game.input_mode = None
                game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code, mod=mod,
                                                     unicode=""))
                assert not any("wrong_station" in text for text in flashes), (station, key)
                game.input_mode = None


def test_station_footers_register_clickable_keys():
    game = Game(seed=4711, start_menu=False, audio_enabled=False)
    for station in (Station.BRIDGE, Station.WEAPONS, Station.HELICOPTER, Station.ELOKA):
        game.station = station
        game.station_page = 0
        game.draw()
        legends = {t.key for t in pointer.targets("station") if t.key is not None}
        assert legends, station
