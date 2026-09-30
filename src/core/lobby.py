"""The multiplayer lobby: where the crew meets before a shared start.

Pure, transient model (never saved, never part of settings). The uConsole
host picks the mission, which unit it plays and its own station, or only
hosts (``HOST_ONLY``: every station belongs to the browsers or the AI); browsers
pick their stations and tick "ready" (``CommanderServer.set_ready_locked``).
The host then starts a short countdown and the mission begins for everyone
at once. After the mission the game returns here, stations kept, ready
ticks cleared.
"""

from __future__ import annotations

from src.commander.server import OPFOR_ROLES, STATIONS
from src.core import config

# Rows of the uConsole lobby page, top to bottom.
ROWS = ("mission", "side", "station", "start")
SIDES = ("frigate", "uboot")
# Wall seconds between "start" and the mission.
COUNTDOWN_S = 5.0
# Station choice of a uConsole that only hosts: every station is played from
# the browsers or by the AI.
HOST_ONLY = "host"


def side_stations(side: str) -> tuple:
    """Stations the uConsole may play on ``side`` (Remote Crew role names)."""
    return STATIONS if side == "frigate" else OPFOR_ROLES


def station_choices(side: str) -> tuple:
    """The uConsole's station choices on ``side``: a station, or host only."""
    return (*side_stations(side), HOST_ONLY)


class LobbyRoom:
    """Lobby selection, countdown and the "start anyway" confirmation."""

    def __init__(self, scenario_key: str = config.SCENARIO_ORDER[0],
                 side: str = "frigate", station: str | None = None):
        self.row = 0
        self.scenario_index = (config.SCENARIO_ORDER.index(scenario_key)
                               if scenario_key in config.SCENARIO_ORDER else 0)
        self.side = side if side in SIDES else "frigate"
        self.station = (station if station in station_choices(self.side)
                        else side_stations(self.side)[0])
        self.countdown_s = None
        # First "start" with players not ready arms this; a second one starts.
        self.force_armed = False

    @property
    def scenario_key(self) -> str:
        return config.SCENARIO_ORDER[self.scenario_index]

    def move(self, step: int) -> None:
        self.row = (self.row + step) % len(ROWS)
        self.force_armed = False

    def change(self, step: int) -> None:
        """Left/Right on the current row; nothing changes during a countdown."""
        if self.countdown_s is not None:
            return
        self.force_armed = False
        row = ROWS[self.row]
        if row == "mission":
            self.scenario_index = (self.scenario_index + step) % len(config.SCENARIO_ORDER)
        elif row == "side":
            self.side = SIDES[(SIDES.index(self.side) + 1) % len(SIDES)]
            if self.station != HOST_ONLY:
                self.station = side_stations(self.side)[0]
        elif row == "station":
            stations = station_choices(self.side)
            self.station = stations[(stations.index(self.station) + step) % len(stations)]

    @staticmethod
    def crew(players) -> list:
        """Players who take part: a browser holding a station, observers aside."""
        return [player for player in players
                if not player["observer"] and player["stations"]]

    def all_ready(self, players) -> bool:
        return all(player["ready"] for player in self.crew(players))

    def request_start(self, players) -> str:
        """Start the countdown: "started", or "confirm" while players are not ready."""
        if self.countdown_s is not None:
            return "running"
        if not self.all_ready(players) and not self.force_armed:
            self.force_armed = True
            return "confirm"
        self.force_armed = False
        self.countdown_s = COUNTDOWN_S
        return "started"

    def cancel(self) -> bool:
        cancelled = self.countdown_s is not None or self.force_armed
        self.countdown_s = None
        self.force_armed = False
        return cancelled

    def tick(self, wall_dt: float) -> bool:
        """Advance the countdown by wall time; True once it reaches zero."""
        if self.countdown_s is None:
            return False
        self.countdown_s = max(0.0, self.countdown_s - max(0.0, float(wall_dt)))
        if self.countdown_s <= 0.0:
            self.countdown_s = None
            return True
        return False

    def publication(self) -> dict:
        """The detached lobby block every crew browser sees."""
        return {
            "mission": self.scenario_key,
            "side": self.side,
            "host_station": None if self.station == HOST_ONLY else self.station,
            "countdown_s": (None if self.countdown_s is None
                            else round(self.countdown_s, 1)),
        }
