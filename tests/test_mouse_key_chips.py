"""Every blue key chip a station draws is clickable (full mouse control).

A key cap tells the player "press this"; one that a click cannot press
looks like a dead button.  Each station page of both sides is drawn in
English and German (every "more" footer page too), and each key cap drawn
by ``layout.command_segment``, ``layout.key_button`` or ``layout.key_cap``
must lie on a click target of that frame.
"""

import pygame
import pytest

from src.core import uboot_local
from src.core.commands import STATION_PAGES
from src.core.game import Game
from src.core.station import Station
from src.ui import layout, pointer, sonar_hit
from src.ui.stations import common
from src.ui.uboot_view import station_pages

# Fire keys outside the weapons station stay keys (fire by click only at
# station 3): drawn as a cap in the rules text, never a switch.
FIRE_CAPS = {"Ctrl+Enter", "Strg+Eingabe"}


@pytest.fixture
def caps(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    drawn = []
    segment, button, cap = layout.command_segment, layout.key_button, layout.key_cap

    def record_segment(screen, rect, key, description, *args, **kwargs):
        if key and layout.localize(key) and pygame.Rect(rect).w > 15:
            drawn.append((pygame.Rect(rect), str(layout.localize(key))))
        return segment(screen, rect, key, description, *args, **kwargs)

    def record_button(screen, rect, key, label, *args, **kwargs):
        if key:
            drawn.append((pygame.Rect(rect), str(key)))
        return button(screen, rect, key, label, *args, **kwargs)

    def record_cap(screen, face, text, topleft, pitch, clip=None):
        rect = cap(screen, face, text, topleft, pitch, clip)
        if rect.w > 2 and rect.h > 2:
            drawn.append((pygame.Rect(rect), text))
        return rect

    monkeypatch.setattr(layout, "command_segment", record_segment)
    monkeypatch.setattr(layout, "key_button", record_button)
    monkeypatch.setattr(layout, "key_cap", record_cap)
    common._FOOTER_OFFSET.clear()
    sonar_hit.SONAR_FOOTER_PAGE.clear()
    yield drawn
    common._FOOTER_OFFSET.clear()
    sonar_hit.SONAR_FOOTER_PAGE.clear()


def _dead_caps(game, drawn, name) -> list:
    """Draw every footer page of the screen; the caps without a target."""
    dead = []
    for _ in range(8):
        drawn.clear()
        game.draw()
        targets = [t for t in pointer.targets() if not t.blocker]
        dead += [(name, text) for rect, text in drawn
                 if text not in FIRE_CAPS
                 and not any(t.rect.colliderect(rect) for t in targets)]
        more = [t for t in pointer.targets("station") if t.action is not None
                and getattr(t.action, "__name__", "") in ("page", "next_page")]
        if not more:
            break
        for target in more:
            target.action(target.rect.center)
        if not any(common._FOOTER_OFFSET.values()) and not any(
                sonar_hit.SONAR_FOOTER_PAGE.values()):
            break
    return dead


@pytest.mark.parametrize("language", ("en", "de"))
def test_every_frigate_key_chip_is_clickable(caps, language):
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language=language)
    try:
        game.reset(1234, "s22_jagdgruppe")
        for _ in range(600):
            game.update(0.1)
        contacts = list(game.sonar.active_contacts())
        game.selected_contact = contacts[0] if contacts else None
        game.msg_until = 0.0
        dead = []
        for station in Station:
            game.station = station
            for page in range(len(STATION_PAGES[station])):
                game.station_page = page
                if station is Station.SONAR:
                    game.sonar_page = page
                dead += _dead_caps(game, caps, f"{station.name}/{page}")
        assert game.selected_contact is not None   # the TMA page shows its footer
        assert not dead
    finally:
        game.audio.shutdown()


@pytest.mark.parametrize("language", ("en", "de"))
def test_every_submarine_key_chip_is_clickable(caps, language):
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language=language)
    try:
        game.local_side = "uboot"
        for _ in range(300):
            game.update(0.1)
        game.msg_until = 0.0
        dead = []
        for role in uboot_local.OPFOR_ROLES:
            uboot_local.set_local_station(game, role)
            pages = (station_pages(role) if role != "uboot_sonar" else ("SONAR",))
            for page in range(len(pages)):
                game.opfor.command_page = page
                dead += _dead_caps(game, caps, f"{role}/{page}")
        assert not dead
    finally:
        game.audio.shutdown()


def _click(game, pos):
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def _key_target(key, mod=0):
    return next(t for t in pointer.targets("station") if t.key == key and t.mod == mod)


def test_lofar_cursor_chip_moves_the_cursor_both_ways(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="en")
    try:
        game.station, game.sonar_page = Station.SONAR, 1
        sonar_hit.SONAR_FOOTER_PAGE.clear()
        game.draw()
        start = game.sonar_tools.lofar_cursor_hz
        _click(game, _key_target(pygame.K_x).rect.center)
        assert game.sonar_tools.lofar_cursor_hz > start
        game.draw()
        _click(game, _key_target(pygame.K_z).rect.center)
        game.draw()
        _click(game, _key_target(pygame.K_z).rect.center)
        assert game.sonar_tools.lofar_cursor_hz < start
    finally:
        game.audio.shutdown()


def test_tma_hypothesis_chips_change_course_speed_and_range(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=1234, start_menu=False, audio_enabled=False, language="de")
    try:
        game.reset(1234, "s22_jagdgruppe")
        for _ in range(600):
            game.update(0.1)
        game.selected_contact = list(game.sonar.active_contacts())[0]
        game.station, game.sonar_page = Station.SONAR, 3
        sonar_hit.SONAR_FOOTER_PAGE.clear()
        before = game.tma_hypothesis(game.selected_contact)
        for key, mod in ((pygame.K_x, 0), (pygame.K_x, pygame.KMOD_CTRL), (pygame.K_q, 0)):
            game.draw()
            _click(game, _key_target(key, mod).rect.center)
        after = game.tma_hypothesis(game.selected_contact)
        assert after.course != before.course
        assert after.speed_kn > before.speed_kn
        assert after.range_nm < before.range_nm
    finally:
        game.audio.shutdown()


def test_submarine_status_line_opens_the_log_like_f11(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_window_size", lambda: (1280, 720))
    game = Game(seed=31, start_menu=False, audio_enabled=False, language="de")
    try:
        game.local_side = "uboot"
        game.update(0.1)
        game.draw()
        _click(game, _key_target(pygame.K_F11).rect.center)
        assert game.feed_overlay_open
    finally:
        game.audio.shutdown()
