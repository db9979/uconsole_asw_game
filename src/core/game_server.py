"""Server mode in the game: the uConsole only serves, a browser leads.

"Server" in the main menu (or ``--server`` at launch) opens the multiplayer
lobby with the uConsole as host only and switches Remote Crew into server
mode (``src/commander/server_mode.py``): the oldest crew browser leads. The
leader picks side, mission (a scenario, the daily mission, a hotspot of the
side's campaign or an own mission), opponent, weather, time and length in
its browser lobby and starts the countdown; it saves, loads and ends the
mission from its host bar. Every other browser takes its stations as in any
lobby round, the AI mans the free ones, and every mission returns to the
lobby. The uConsole shows the lobby page and, during a mission, the umpire
screen with the join code: no station, no tactical picture.

The leader's commands arrive as closed host actions (``src/commander/
actions.py``) and run here on the main thread. Nothing of server mode is
saved; a load only keeps the round in the lobby's hands.
"""

from __future__ import annotations

from src.core import boat_campaign, campaign as campaign_model, daily, theatre
from src.core.lobby import HOST_ONLY, SIDES

SERVER_ENTRY = "server"
# Campaign actions the leader may send (the campaign screen's N, 1 and 2).
CAMPAIGN_ACTIONS = ("new", "refit", "quick")


class ServerModeMixin:
    """Server-mode switch, the leader's lobby actions and its host view."""

    def _init_server_mode(self) -> None:
        # Transient, per launch: the uConsole only serves Remote Crew.
        self.server_mode = False

    def start_server_mode(self) -> None:
        """Open the lobby as host only and let a browser lead."""
        self.server_mode = True
        self.open_lobby()
        self.lobby.server = True
        self.lobby.station = HOST_ONLY
        self.sync_server_mode()

    def leave_server_mode(self) -> None:
        self.server_mode = False
        if self.lobby is not None:
            self.lobby.server = False
        self.sync_server_mode()

    def sync_server_mode(self) -> None:
        """Keep the Remote Crew server's mode on the game's (cheap per frame)."""
        server = getattr(self.commander, "server", None)
        if server is None or not hasattr(server, "set_server_mode"):
            return
        if server.server_mode is not self.server_mode:
            server.set_server_mode(self.server_mode)

    def server_leader_name(self):
        server = getattr(self.commander, "server", None)
        if not self.server_mode or server is None or not hasattr(server, "leader_name"):
            return None
        return server.leader_name()

    # --- the lobby's mission choices -----------------------------------------------

    def _lobby_campaign_state(self, side: str):
        return self._boat_campaign() if side == "uboot" else self._campaign()

    def lobby_extra_missions(self) -> dict:
        """The daily mission and the campaign's open hotspots per side."""
        day = daily.today()
        extras = {}
        for side in SIDES:
            state = self._lobby_campaign_state(side)
            spots = ()
            if state is not None and state.can_sail():
                spots = tuple((spot["id"], spot["scenario"], state.theatre.name(spot))
                              for spot in state.theatre.ordered())
            extras[side] = {"daily": daily.scenario_for(day, side), "campaign": spots}
        return extras

    def _lobby_campaign_view(self, side: str) -> dict:
        state = self._lobby_campaign_state(side)
        if state is None:
            return dict(status="none", port=False, lage=0, missions=0,
                        missions_max=theatre.MISSIONS_MAX, hotspots=[])
        front = state.theatre
        spots = front.ordered() if state.can_sail() else []
        return dict(status=state.status, port=bool(state.port), lage=int(front.lage),
                    missions=int(state.missions), missions_max=theatre.MISSIONS_MAX,
                    hotspots=[dict(id=int(spot["id"]), name=str(front.name(spot))[:48],
                                   scenario=spot["scenario"], role=front.role(spot))
                              for spot in spots])

    def lobby_host_view(self):
        """The leader's lobby block of the host view (None outside the lobby)."""
        if not (self.server_mode and self.lobby_active):
            return None
        room = self.lobby
        return dict(
            choice=room.choice, side=room.side, versus=room.versus,
            weather=room.weather, time=room.time, length=room.length,
            countdown_s=(None if room.countdown_s is None else round(room.countdown_s, 1)),
            confirm=bool(room.force_armed),
            daily={side: room.extra_missions[side]["daily"] for side in SIDES},
            campaign={side: self._lobby_campaign_view(side) for side in SIDES})

    # --- the leader's actions (host commands, main thread) -------------------------

    def _server_lobby(self):
        return self.lobby if self.server_mode and self.lobby_active else None

    def server_lobby_set(self, params: dict):
        """Side, mission and start choices from the leader's browser."""
        room = self._server_lobby()
        if room is None:
            return "phase_blocked"
        if room.countdown_s is not None:
            return "lobby_counting"
        side = room.side
        if not room.set_side(params["side"]):
            return "lobby_invalid"
        if not room.set_choice(params["choice"]):
            # The library may have grown since the lobby opened.
            self._refresh_lobby_missions()
            if not room.set_choice(params["choice"]):
                room.set_side(side)
                return "lobby_invalid"
        if not room.set_start_choices(params["versus"], params["weather"],
                                      params["time"], params["length"]):
            return "lobby_invalid"
        self.lobby_notice = None
        return True

    def server_lobby_start(self):
        room = self._server_lobby()
        if room is None:
            return "phase_blocked"
        result = room.request_start(self.lobby_players())
        if result == "confirm":
            players = self.lobby_players()
            self.lobby_notice = ("lobby.notice.confirm" if room.teams_manned(players)
                                 else "lobby.notice.team_empty")
            return "lobby_confirm"
        self.lobby_notice = None
        return True

    def server_lobby_cancel(self):
        room = self._server_lobby()
        if room is None:
            return "phase_blocked"
        room.cancel()
        self.lobby_notice = "lobby.notice.cancelled"
        return True

    def server_campaign(self, side: str, action: str):
        """New campaign or a port call of the side's campaign (campaign screen)."""
        room = self._server_lobby()
        if room is None or room.countdown_s is not None:
            return "phase_blocked"
        boat = side == "uboot"
        if action == "new":
            saved = self.new_boat_campaign() if boat else self.new_campaign()
        else:
            state = self._lobby_campaign_state(side)
            if state is None or state.status != "active" or not state.port:
                return "campaign_unavailable"
            state.call_at_port(action)
            saved = (boat_campaign.save_campaign(state) if boat
                     else campaign_model.save_campaign(state))
        self._refresh_lobby_missions()
        return True if saved else "save_failed"

    def server_end_mission(self):
        """Back to the lobby from a running or finished mission."""
        if not self.server_mode or self.in_menu or self.main_menu:
            return "phase_blocked"
        self.lobby_round = True
        self._return_to_main_menu()
        return True

    def server_loaded(self) -> None:
        """A leader's load: the round stays the lobby's, the uConsole hosts."""
        if self.server_mode:
            self.lobby_round = True
            self.host_only = True

    # --- starting the lobby's daily mission or campaign hotspot --------------------

    def _start_lobby_daily(self, room) -> None:
        day = daily.today()
        self.remember_menu_choice()
        self.seed = daily.seed_for(day, room.side)
        self.scenario_key = daily.scenario_for(day, room.side)
        self.world_mode = daily.WORLD_MODE
        # The daily mission is the same for everyone: no start choices.
        self.start_weather = self.start_time = "random"
        self.start_length = "normal"
        self._start_menu_mission()

    def _start_lobby_campaign(self, room) -> bool:
        if room.side == "uboot":
            return self.start_boat_campaign_leg(room.hotspot)
        self.local_side = "frigate"
        return self.start_campaign_leg(room.hotspot)

