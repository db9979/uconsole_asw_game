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
from src.core.lobby import HOST_ONLY, ROWS, LobbyRoom, player_side, side_stations
from src.core.game_server import SERVER_ENTRY
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
        # A crew-versus-crew lobby round: the frigate's and the boat's crews
        # play each other, every browser stays with its unit. Transient.
        self.versus_round = False

    def _set_versus_round(self, enabled: bool) -> None:
        self.versus_round = bool(enabled)
        server = getattr(self.commander, "server", None)
        if server is not None and hasattr(server, "lock_teams"):
            server.lock_teams(self.versus_round)

    def umpire_view_active(self) -> bool:
        """A host-only uConsole in a crew-versus-crew round, or any round of
        server mode, shows no tactical picture of either unit (both crews
        may see its screen, and nobody works a station on it)."""
        return ((self.versus_round or getattr(self, "server_mode", False))
                and self.host_only and self.running
                and not self.in_menu and not self.main_menu)

    def versus_outcome(self):
        """(frigate won, boat won) of a finished crew-versus-crew round, each
        from its own unit's view, or None."""
        if not (self.versus_round and self.game_over):
            return None
        from src.core import boat_campaign, boat_debrief
        boat = self._opfor
        frigate_won = self.mission_result == "SIEG"
        if boat is None:
            return frigate_won, not frigate_won
        return frigate_won, boat_debrief.outcome(self, boat) in boat_campaign.WINS

    def versus_end_line(self):
        outcome = self.versus_outcome()
        if outcome is None:
            return None
        frigate, submarine = (message("lobby.versus.won" if won else "lobby.versus.lost")
                              for won in outcome)
        return message("lobby.versus.result", frigate=frigate, submarine=submarine)

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
        self._set_versus_round(False)
        self._refresh_lobby_missions()
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

    def _refresh_lobby_missions(self) -> None:
        """Hand the lobby the own missions of both sides (read when it opens)."""
        side = self.local_side
        missions = {}
        for choice in ("frigate", "uboot"):
            self.local_side = choice
            missions[choice] = [(record.key, str(record.data.get("name", record.key))[:80])
                                for record in self.custom_menu_records()]
        self.local_side = side
        self.lobby.set_custom_missions(missions)
        self.lobby.set_extra_missions(self.lobby_extra_missions())

    def close_lobby(self) -> None:
        """Back to the main menu; Remote Crew keeps running."""
        if self.lobby is not None:
            self.lobby.cancel()
        self.lobby_round = False
        self.host_only = False
        self._set_versus_round(False)
        self.main_menu = True
        self.menu_screen = "scenario"
        self.main_menu_sel = self.main_menu_index(
            SERVER_ENTRY if self.server_mode else MULTIPLAYER_ENTRY)
        if self.server_mode:
            self.leave_server_mode()
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
        self.sync_server_mode()
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
        self.start_weather, self.start_time = room.weather, room.time
        self.start_length = room.length
        self.lobby_round = True
        # Against a second crew every browser keeps the unit it crews now.
        self._set_versus_round(room.versus == "crew")
        definition = self._lobby_custom_definition(room)
        if room.daily:
            self._start_lobby_daily(room)
        elif room.hotspot is not None:
            if not self._start_lobby_campaign(room):
                self.lobby_round = False
                self.lobby_notice = "lobby.notice.campaign_failed"
                return
        elif definition is None:
            self._start_menu_mission()
        elif not self.start_custom_mission(definition):
            self.lobby_round = False
            self.lobby_notice = "menu.custom.start_failed"
            return
        # A lobby round with a crew lets the AI man every station nobody holds;
        # alone on the uConsole it is a solo game (Shift+F2 still switches it).
        if self.host_only or room.crew(self.lobby_players()):
            self.autocrew.set_assist(True, self.sim_t)
        self._take_lobby_station(room.station)

    def _lobby_mission_text(self, room):
        """The lobby's mission line: own mission, daily mission, campaign
        hotspot or scenario."""
        if room.custom_name is not None:
            return raw_text(room.custom_name)
        title = message("scenario." + config.SCENARIO_NAMES[room.scenario_key] + ".title")
        if room.daily:
            return message("lobby.choice.daily", mission=title)
        if room.hotspot is not None:
            return message("lobby.choice.campaign", name=raw_text(room.hotspot_name or "?"),
                           mission=title)
        return title

    def _lobby_custom_definition(self, room):
        """The chosen own mission's definition, read now (None: a scenario)."""
        if room.custom_key is None:
            return None
        # The library of the lobby's side (a host-only uConsole sits on the
        # frigate whatever side the crew sails).
        side, self.local_side = self.local_side, room.side
        try:
            records = self.custom_menu_records()
        finally:
            self.local_side = side
        record = next((record for record in records if record.key == room.custom_key), None)
        return None if record is None else record.data

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
            players = self.lobby_players()
            result = room.request_start(players)
            self.lobby_notice = (None if result != "confirm"
                                 else "lobby.notice.confirm" if room.teams_manned(players)
                                 else "lobby.notice.team_empty")
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
        layout.blit_line(s, "lobby.server.title" if room.server else "lobby.title",
                         (panel.x + 20, panel.y + 10, panel.w - 40, 34),
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
            message("lobby.row.mission", mission=self._lobby_mission_text(room)),
            message("lobby.row.side_crew" if room.station == HOST_ONLY else "lobby.row.side",
                    side=message(f"menu.side.{room.side}")),
            message("lobby.row.station", station=_station_name(room.station)),
            message("lobby.row.versus", versus=message(f"lobby.versus.{room.versus}")),
            message("menu.start_weather", value=message(f"menu.start_weather.{room.weather}")),
            message("menu.start_time", value=message(f"menu.start_time.{room.time}")),
            message("menu.start_length", value=message(f"menu.start_length.{room.length}")),
            message("lobby.row.start"),
        )
        row_h = 30
        for index, text in enumerate(values):
            selected = index == room.row
            rect = pygame.Rect(right.x, right.y + index * row_h, right.w, row_h - 3)
            if selected:
                pygame.draw.rect(s, config.COLOR_SELECT_BG, rect)
            layout.blit_line(s, message("menu.choice", marker="► " if selected else "  ",
                                        label=text), rect,
                             config.COLOR_WARN if selected else config.COLOR_TEXT, size=19)
            # A click picks the row: the next value, or the start on the last.
            pointer.add_action(rect, lambda _pos, index=index, last=len(values) - 1:
                               self._click_menu_row(
                                   lambda: setattr(room, "row", index),
                                   pygame.K_RETURN if index == last else pygame.K_RIGHT))
        # Right bottom: who is here.
        players = self.lobby_players()
        top = right.y + len(values) * row_h + 30
        versus = room.versus == "crew"
        layout.blit_line(s, "lobby.crew.teams" if versus else "lobby.crew",
                         (right.x, top, right.w, 24), config.COLOR_TEXT_DIM, size=17)
        # (name, stations, ready, observer, unit or None)
        # A server-mode uConsole crews nothing, so it has no row of its own.
        rows = [] if room.server else [(message("lobby.host_player"),
                 [] if room.station == HOST_ONLY else [room.station], True, False,
                 None if room.station == HOST_ONLY else room.side)]
        rows += [(message("lobby.player.leader", name=raw_text(player["name"]))
                  if player.get("leader") else raw_text(player["name"]),
                  player["stations"], player["ready"],
                  player["observer"], player_side(player["stations"])
                  if player["stations"] and not player["observer"] else None)
                 for player in players]
        if versus:
            # Two teams: the frigate's crew first, then the boat's, then the rest.
            order = {"frigate": 0, "uboot": 1, None: 2}
            rows = sorted(rows, key=lambda row: order[row[4]])
        shown = 5
        for index, (name, stations, ready, observer, unit) in enumerate(rows[:shown]):
            y = top + 26 + index * 24
            if versus and unit is not None:
                # The team stripe: blue for the frigate, red for the boat.
                pygame.draw.rect(s, (40, 110, 160) if unit == "frigate" else (170, 70, 50),
                                 (right.x - 10, y + 3, 5, 18))
            state = ("lobby.player.observer" if observer else "lobby.player.ready" if ready
                     else "lobby.player.no_station" if not stations
                     else "lobby.player.waiting")
            color = (config.COLOR_TEXT if ready or observer else config.COLOR_WARN)
            layout.blit_line(s, name, (right.x, y, 220, 22), config.COLOR_TEXT, size=16)
            layout.blit_line(s, raw_text(", ".join(self.tr(f"station.{station}")
                                                   for station in stations)) if stations
                             else "lobby.player.none",
                             (right.x + 230, y, right.w - 400, 22), config.COLOR_TEXT_DIM,
                             size=15)
            layout.blit_line(s, state, (right.right - 160, y, 160, 22), color, size=15,
                             align="right")
        if len(rows) > shown:
            layout.blit_line(s, message("lobby.more", count=str(len(rows) - shown)),
                             (right.x, top + 26 + shown * 24, right.w, 20),
                             config.COLOR_TEXT_DIM, size=14, align="right")
        if len(rows) == 1:
            layout.blit_line(s, "lobby.nobody", (right.x, top + 54, right.w, 24),
                             config.COLOR_TEXT_DIM, size=16)
        # Countdown or notice.
        if room.countdown_s is not None:
            layout.blit_line(s, message("lobby.countdown",
                                        seconds=str(max(1, int(room.countdown_s + 0.999)))),
                             (right.x, right.y + len(values) * row_h, right.w, 30),
                             config.COLOR_WARN, size=26, align="center")
        elif self.lobby_notice:
            layout.blit_line(s, self.lobby_notice,
                             (right.x, right.y + len(values) * row_h + 2, right.w, 26),
                             config.COLOR_WARN, size=18, align="center")
        if room.server and room.countdown_s is None and not self.lobby_notice:
            # Server mode: the leading browser picks and starts.
            layout.blit_line(s, "lobby.server.leads" if any(
                player.get("leader") for player in players) else "lobby.server.waiting",
                (right.x, right.y + len(values) * row_h + 2, right.w, 26),
                config.COLOR_TEXT_DIM, size=16, align="center")
        layout.blit_line(s, "lobby.hint", (panel.x + 20, panel.bottom - 26, panel.w - 40, 22),
                         config.COLOR_TEXT_DIM, size=15, align="center")
        pointer.add_text_keys(localize("lobby.hint"), layout.font(15), panel.centerx,
                              panel.bottom - 15, (None, None, "Enter", "Esc", "F9"))
