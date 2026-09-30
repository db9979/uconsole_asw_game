"""Multiplayer lobby page of the start menu (model in ``lobby.py``).

"Multiplayer" in the main menu (or ``--multiplayer`` at launch) opens it:
Remote Crew starts by itself in crew mode, the page shows the join QR code
and code, the players with their stations and ready ticks, and the host's
mission, unit and own station. The host starts a short wall-clock
countdown; the mission then begins for all.
A mission started here returns to the lobby when it ends. The page belongs to
the start menu: nothing is simulated while it is open.
"""

from __future__ import annotations

import pygame

from src.core import config
from src.core.i18n import localize, message, raw_text
from src.core.lobby import HOST_ONLY, ROWS, LobbyRoom, side_stations
from src.core.station import Station
from src.ui import layout, pointer
from src.ui.splash_view import draw_menu_panel

LOBBY_SCREEN = "lobby"
MULTIPLAYER_ENTRY = "multiplayer"
_PLAYERS_MAX = 12


def _station_name(station: str) -> str:
    return message("lobby.host_only" if station == HOST_ONLY else f"station.{station}")


class LobbyMixin:
    """State, keys, countdown and drawing of the multiplayer lobby."""

    def _init_lobby(self) -> None:
        self.lobby = None
        # True while the current mission was started from the lobby: its end
        # leads back to the lobby instead of the main menu.
        self.lobby_round = False
        self.lobby_notice = None
        self._lobby_published = None
        # The uConsole only hosts this lobby round: it works no station, so the
        # browsers and the AI crew every one. Transient, like the leases.
        self.host_only = False

    @property
    def crew_assist(self) -> bool:
        """The AI mans every station nobody holds, on both units."""
        return self.autocrew.assist

    def toggle_crew_assist(self) -> bool:
        enabled = self.autocrew.set_assist(not self.autocrew.assist, self.sim_t)
        self._clear_station_input()
        self.flash(message("autocrew.assist.on" if enabled else "autocrew.assist.off"))
        return enabled

    @property
    def lobby_active(self) -> bool:
        return (self.in_menu and not self.main_menu and self.lobby is not None
                and self.menu_screen == LOBBY_SCREEN)

    def open_lobby(self) -> None:
        """Show the lobby and make sure Remote Crew runs in crew mode."""
        if self.lobby is None:
            station = (Station.BRIDGE.name.lower() if self.local_side != "uboot"
                       else "uboot")
            self.lobby = LobbyRoom(self.scenario_key, self.local_side, station)
        self.lobby.cancel()
        self.main_menu = False
        self.menu_screen = LOBBY_SCREEN
        self.lobby_notice = None
        console = self.commander
        if getattr(console, "web_mode", False):
            return
        if console.solo:
            console.set_solo(False)
        if console.address is None and not console.hotspot.active:
            console.autostart()

    def close_lobby(self) -> None:
        """Back to the main menu; Remote Crew keeps running."""
        if self.lobby is not None:
            self.lobby.cancel()
        self.lobby_round = False
        self.host_only = False
        self.main_menu = True
        self.menu_screen = "scenario"
        self.main_menu_sel = self.main_menu_index(MULTIPLAYER_ENTRY)
        self._publish_lobby(None)

    def lobby_players(self) -> list:
        server = getattr(self.commander, "server", None)
        if server is None or getattr(self.commander, "address", None) is None:
            return []
        return server.lobby_players()[:_PLAYERS_MAX]

    def _publish_lobby(self, room) -> None:
        if room == self._lobby_published:
            return
        server = getattr(self.commander, "server", None)
        if server is not None:
            server.publish_lobby(room)
        self._lobby_published = room

    def lobby_tick(self, wall_dt: float) -> None:
        """Publish the lobby to the crew and run the start countdown."""
        if not self.lobby_active:
            self._publish_lobby(None)
            return
        if self.lobby.tick(wall_dt):
            self._start_lobby_mission()
            return
        self._publish_lobby(self.lobby.publication())

    def _start_lobby_mission(self) -> None:
        room = self.lobby
        self._publish_lobby(None)
        self.host_only = room.station == HOST_ONLY
        # A host-only uConsole watches from the frigate; the boat is crewed from
        # the browsers (or runs as the AI boat when nobody takes it).
        self.local_side = "frigate" if self.host_only else room.side
        self.scenario_key = room.scenario_key
        self.lobby_round = True
        self._start_menu_mission()
        # A lobby round with a crew lets the AI man every station nobody holds;
        # alone on the uConsole it is a solo game (Shift+F2 still switches it).
        if self.host_only or room.crew(self.lobby_players()):
            self.autocrew.set_assist(True, self.sim_t)
        self._take_lobby_station(room.station)

    def _take_lobby_station(self, station: str) -> None:
        """Put the uConsole on its lobby station in the new mission."""
        if station not in side_stations(self.local_side):
            return
        if self.local_side == "uboot":
            from src.core import uboot_local
            uboot_local.set_local_station(self, station)
            return
        self._clear_controls()
        self.station = Station.RADAR if station == "opz" else Station[station.upper()]
        self.station_page = 2 if self.station is Station.HELICOPTER else 0

    def _handle_lobby_key(self, key) -> None:
        room = self.lobby
        if key in (pygame.K_UP, pygame.K_DOWN):
            room.move(1 if key == pygame.K_DOWN else -1)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            room.change(1 if key == pygame.K_RIGHT else -1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if ROWS[room.row] != "start":
                room.change(1)
                return
            result = room.request_start(self.lobby_players())
            self.lobby_notice = ("lobby.notice.confirm" if result == "confirm"
                                 else None)
        elif key in (pygame.K_ESCAPE, pygame.K_q):
            if room.cancel():
                self.lobby_notice = "lobby.notice.cancelled"
            else:
                self.close_lobby()

    def _draw_lobby_hotspot_steps(self, left, address, details) -> None:
        """On the uConsole's own hotspot: step 1 joins the Wi-Fi (its QR code,
        name and password), step 2 opens the crew page (its QR code, address
        and join code). Both steps show at once."""
        s, console = self.screen, self.commander
        box = 120
        text_x, text_w = left.x + box + 12, left.w - box - 12
        top = left.y
        layout.blit_line(s, "commander.local.hotspot.step1", (left.x, top, left.w, 22),
                         config.COLOR_TEXT, size=16)
        surface = console._hotspot_qr(details.ssid, details.password, box_px=box)
        s.blit(surface, (left.x + (box - surface.get_width()) // 2,
                         top + 28 + (box - surface.get_height()) // 2))
        layout.blit_line(s, "commander.local.hotspot.ssid_label",
                         (text_x, top + 28, text_w, 20), config.COLOR_TEXT_DIM, size=14)
        layout.blit_line(s, raw_text(details.ssid), (text_x, top + 48, text_w, 26),
                         config.COLOR_TEXT, size=20)
        layout.blit_line(s, "commander.local.hotspot.password_label",
                         (text_x, top + 78, text_w, 20), config.COLOR_TEXT_DIM, size=14)
        layout.blit_line(s, raw_text(details.password), (text_x, top + 98, text_w, 30),
                         config.COLOR_WARN, size=22)
        top += 164
        layout.blit_line(s, "commander.local.hotspot.step2", (left.x, top, left.w, 22),
                         config.COLOR_TEXT, size=16)
        surface = console._url_qr(address[0], address[1], box_px=box)
        s.blit(surface, (left.x + (box - surface.get_width()) // 2,
                         top + 28 + (box - surface.get_height()) // 2))
        layout.blit_line(s, raw_text(f"http://{address[0]}:{address[1]}/"),
                         (text_x, top + 32, text_w, 22), config.COLOR_TEXT, size=14)
        layout.blit_line(s, "commander.local.join_code", (text_x, top + 62, text_w, 20),
                         config.COLOR_TEXT_DIM, size=14, align="center")
        code = console.pairing_code or "------"
        layout.blit_line(s, raw_text(code[:3] + " " + code[3:]),
                         (text_x, top + 84, text_w, 56), config.COLOR_WARN, size=44,
                         align="center")

    def _draw_lobby_page(self) -> None:
        s, room = self.screen, self.lobby
        console = self.commander
        panel = pygame.Rect(40, 116, config.SCREEN_W - 80, 500)
        draw_menu_panel(s, panel, pygame.Rect(0, 0, 0, 0))
        layout.blit_line(s, "lobby.title", (panel.x + 20, panel.y + 10, panel.w - 40, 34),
                         config.COLOR_WARN, size=26, align="center")
        # Left: how to join (address, code, QR codes).
        left = pygame.Rect(panel.x + 20, panel.y + 52, 360, panel.h - 80)
        address = getattr(console, "address", None)
        details = getattr(console.hotspot, "details", None)
        if (address is not None and details is not None
                and console.network_mode == "hotspot"):
            self._draw_lobby_hotspot_steps(left, address, details)
        elif address is not None:
            layout.blit_line(s, "lobby.join", (left.x, left.y, left.w, 24),
                             config.COLOR_TEXT_DIM, size=17, align="center")
            surface = console._url_qr(address[0], address[1], box_px=168)
            s.blit(surface, (left.centerx - surface.get_width() // 2, left.y + 30))
            layout.blit_line(s, raw_text(f"http://{address[0]}:{address[1]}/"),
                             (left.x, left.y + 206, left.w, 24), config.COLOR_TEXT,
                             size=18, align="center")
            code = console.pairing_code or "------"
            layout.blit_line(s, "commander.local.join_code",
                             (left.x, left.y + 240, left.w, 22), config.COLOR_TEXT_DIM,
                             size=16, align="center")
            layout.blit_line(s, raw_text(code[:3] + " " + code[3:]),
                             (left.x, left.y + 262, left.w, 60), config.COLOR_WARN,
                             size=52, align="center")
        else:
            layout.blit_block(s, console.error or "lobby.starting", left.x, left.y + 40,
                              left.w, 120, config.COLOR_WARN, size=18)
        layout.blit_line(s, "lobby.admin_hint", (left.x, left.bottom - 26, left.w, 22),
                         config.COLOR_TEXT_DIM, size=14, align="center")
        # Right top: the host's choices.
        right = pygame.Rect(left.right + 30, left.y, panel.right - left.right - 50, left.h)
        values = (
            message("lobby.row.mission", mission=message(
                "scenario." + config.SCENARIO_NAMES[room.scenario_key] + ".title")),
            message("lobby.row.side", side=message(f"menu.side.{room.side}")),
            message("lobby.row.station", station=_station_name(room.station)),
            message("lobby.row.start"),
        )
        for index, text in enumerate(values):
            selected = index == room.row
            rect = pygame.Rect(right.x, right.y + index * 34, right.w, 30)
            if selected:
                pygame.draw.rect(s, (18, 52, 58), rect)
            layout.blit_line(s, message("menu.choice", marker="► " if selected else "  ",
                                        label=text), rect,
                             config.COLOR_WARN if selected else config.COLOR_TEXT, size=20)
            # A click picks the row: the next value, or the start on the last.
            pointer.add_action(rect, lambda _pos, index=index, last=len(values) - 1:
                               self._click_menu_row(
                                   lambda: setattr(room, "row", index),
                                   pygame.K_RETURN if index == last else pygame.K_RIGHT))
        # Right bottom: who is here.
        players = self.lobby_players()
        top = right.y + len(values) * 34 + 40
        layout.blit_line(s, "lobby.crew", (right.x, top, right.w, 24),
                         config.COLOR_TEXT_DIM, size=17)
        rows = [(message("lobby.host_player"),
                 [] if room.station == HOST_ONLY else [room.station], True, False)]
        rows += [(raw_text(player["name"]), player["stations"], player["ready"],
                  player["observer"]) for player in players]
        for index, (name, stations, ready, observer) in enumerate(rows[:8]):
            y = top + 28 + index * 26
            state = ("lobby.player.observer" if observer else "lobby.player.ready" if ready
                     else "lobby.player.no_station" if not stations
                     else "lobby.player.waiting")
            color = (config.COLOR_TEXT if ready or observer else config.COLOR_WARN)
            layout.blit_line(s, name, (right.x, y, 220, 24), config.COLOR_TEXT, size=17)
            layout.blit_line(s, raw_text(", ".join(self.tr(f"station.{station}")
                                                   for station in stations)) if stations
                             else "lobby.player.none",
                             (right.x + 230, y, right.w - 400, 24), config.COLOR_TEXT_DIM,
                             size=15)
            layout.blit_line(s, state, (right.right - 160, y, 160, 24), color, size=16,
                             align="right")
        if len(rows) == 1:
            layout.blit_line(s, "lobby.nobody", (right.x, top + 56, right.w, 24),
                             config.COLOR_TEXT_DIM, size=16)
        # Countdown or notice.
        if room.countdown_s is not None:
            layout.blit_line(s, message("lobby.countdown",
                                        seconds=str(max(1, int(room.countdown_s + 0.999)))),
                             (right.x, right.y + len(values) * 34, right.w, 34),
                             config.COLOR_WARN, size=26, align="center")
        elif self.lobby_notice:
            layout.blit_line(s, self.lobby_notice,
                             (right.x, right.y + len(values) * 34 + 4, right.w, 26),
                             config.COLOR_WARN, size=18, align="center")
        layout.blit_line(s, "lobby.hint", (panel.x + 20, panel.bottom - 26, panel.w - 40, 22),
                         config.COLOR_TEXT_DIM, size=15, align="center")
        pointer.add_text_keys(localize("lobby.hint"), layout.font(15), panel.centerx,
                              panel.bottom - 15, (None, None, "Enter", "Esc", "F9"))
