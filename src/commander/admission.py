"""Main-thread station admission dialog; all state is transient."""

import pygame

from src.core import config
from src.core.i18n import message, raw_text, translation_scope
from src.ui import layout


class StationAdmission:
    def __init__(self):
        self.request = None
        self.deferred = set()
        self.identity = None
        self.selection = 5
        self.grants = {}
        self.error = False

    @staticmethod
    def key(row):
        return (row["client_id"], row["requested_station"], row.get("request_generation", 0))

    def close(self, game, defer=False):
        if defer and self.request:
            self.deferred.add(self.key(self.request))
        self.request = None
        game._open_administration("")

    def sync(self, game, console):
        identity = (id(console.server), id(game.world), id(game.sonar))
        if identity != self.identity:
            self.identity = identity
            self.deferred.clear()
            if self.request:
                self.close(game)
        rows = console.server.client_statuses()
        pending = [dict(row, requested_station=station,
                        request_generation=detail["request_generation"])
                   for row in rows for station, detail in row["stations"].items()
                   if detail["requested"]]
        keys = {self.key(row) for row in pending}
        self.deferred.intersection_update(keys)
        if self.request:
            if self.key(self.request) not in keys:
                self.close(game)
            return
        if (game.administration_open or game.input_mode is not None or game.editor is not None
                or game.splash_active or game.in_menu or game.main_menu or game.game_over
                or not game.running or game.pinned_tooltip is not None
                or console.confirm_visible(game)):
            return
        pending = sorted((row for row in pending if self.key(row) not in self.deferred),
                         key=lambda row: row["ordinal"])
        if not pending:
            return
        self.request = pending[0]
        self.grants = dict(command=True, direct_fire=False, sonar_audio=False)
        self.selection = 5  # Enter never silently grants an arriving request.
        self.error = False
        game._open_administration("commander")

    @staticmethod
    def rects():
        return [pygame.Rect(244, 232 + index * 57, 792, 48) for index in range(6)]

    def activate(self, game, console, index):
        if index < 3:
            capability = ("command", "direct_fire", "sonar_audio")[index]
            station = self.request["requested_station"]
            if capability == "direct_fire" and (station not in ("weapons", "opz", "helicopter")
                                                or not self.grants["command"]):
                return
            if capability == "sonar_audio" and station != "sonar":
                return
            self.grants[capability] = not self.grants[capability]
            if not self.grants["command"]:
                self.grants["direct_fire"] = False
        elif index == 5:
            self.close(game, defer=True)
        else:
            row = self.request
            if console.server.resolve_station_request(*self.key(row),
                    grants=dict(self.grants) if index == 3 else None):
                self.close(game)
            else:
                self.error = True

    def handle_key(self, game, console, key):
        if key == pygame.K_ESCAPE:
            self.close(game, defer=True)
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_TAB):
            self.selection = (self.selection + (-1 if key == pygame.K_UP else 1)) % 6
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.activate(game, console, self.selection)

    def handle_click(self, game, console, pos):
        for index, rect in enumerate(self.rects()):
            if rect.collidepoint(pos):
                self.selection = index
                self.activate(game, console, index)
                break

    def draw(self, game):
        with translation_scope(game.tr):
            layout.panel(game.screen, pygame.Rect(220, 96, 840, 544))
            layout.blit_line(game.screen, "commander.admission.title", (244, 116, 792, 36),
                             config.COLOR_WARN, size=28)
            station = self.request["requested_station"]
            key = "station.ew" if station == "eloka" else "station." + station
            layout.blit_block(game.screen, message("commander.admission.player",
                name=raw_text(self.request["name"]), station=message(key)),
                244, 159, 792, 64, config.COLOR_TEXT, size=22)
            labels = [message("commander.admission." + capability,
                              state=message("common.on" if value else "common.off"))
                      for capability, value in self.grants.items()]
            labels += [message("commander.admission.approve"),
                       message("commander.admission.reject"), message("commander.admission.later")]
            for index, (rect, text) in enumerate(zip(self.rects(), labels)):
                layout.blit_line(game.screen, message("menu.choice",
                    marker="> " if index == self.selection else "  ", label=text), rect,
                    config.COLOR_WARN if index == self.selection else config.COLOR_TEXT, size=20)
            layout.blit_line(game.screen, "commander.admission.conflict" if self.error
                             else "commander.admission.hint", (244, 592, 792, 30),
                             config.COLOR_WARN if self.error else config.COLOR_TEXT_DIM, size=16)
