"""Local-only Commander lifecycle and crew administration, never persisted.

Construction opens nothing. prepare() performs bounded interface discovery once;
activate(game) is the only start path. pump(game) belongs to the main wall loop,
including paused frames, and stop() uses the transport's bounded shutdown.
"""

import ipaddress
from itertools import islice
import socket
import struct
import time

import pygame

from src.commander.bridge import CommanderBridge
from src.commander.server import CommanderServer
from src.core import config
from src.core.i18n import load_catalog, message, raw_text, translation_scope
from src.ui import layout


class CommanderConsole:
    def __init__(self):
        self.server = None
        self.bridge = CommanderBridge()
        self.hosts = ("127.0.0.1",)
        self.host = self.hosts[0]
        self.port = 8765
        self.address = None
        self.error = None
        self.selection = 0
        self.connected = False
        self.pairing_code = None
        self._prepared = False
        self._translations = None
        self._notice_seq = None
        self._last_notice = float("-inf")

    def prepare(self):
        """Discover at most 64 Linux interface IPv4s, with no DNS or LAN probe."""
        if self._prepared:
            return
        hosts = {"127.0.0.1"}
        networks = tuple(ipaddress.IPv4Network(net) for net in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
        try:
            import fcntl

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                for _, name in islice(socket.if_nameindex(), 64):
                    try:
                        request = struct.pack("256s", name.encode()[:15])
                        result = fcntl.ioctl(probe.fileno(), 0x8915, request)  # SIOCGIFADDR
                        address = ipaddress.IPv4Address(result[20:24])
                        if any(address in net for net in networks):
                            hosts.add(str(address))
                    except OSError:
                        continue
        except (ImportError, AttributeError, OSError):
            # Loopback remains usable without Linux ioctls; never fall back to
            # wildcard binding or a potentially blocking hostname resolver.
            pass
        self.hosts = ("127.0.0.1", *sorted(hosts - {"127.0.0.1"}))
        self._prepared = True

    def invalidate_commands(self):
        self.bridge.invalidate_commands()

    def stop(self):
        if self.server is not None:
            self.server.stop()
        self.address = None
        self.connected = False
        self.pairing_code = None
        self.bridge.allowed = False
        self.invalidate_commands()

    def pump(self, game):
        if self.address is None:
            return
        now = time.monotonic()
        self.bridge.pump(game, self.server, now=now)
        self.connected = self.server.connected
        self.pairing_code = self.server.pairing_code
        sequence = self.bridge.proposal_sequence
        proposal = self.bridge.proposal
        navigation = self.bridge.navigation_proposal
        if self._notice_seq is None:
            self._notice_seq = sequence
        elif (sequence > self._notice_seq
              and any(p is not None and p["status"] == "pending" for p in (proposal, navigation))
              and now - self._last_notice >= 2.0):
            self._notice_seq = sequence
            self._last_notice = now
            game.flash(message("commander.local.navigation.notice" if navigation is not None
                               and navigation["status"] == "pending"
                               else "commander.local.notice"), 3.0)
            game.audio.play_alert("danger")

    def activate(self, game, direction=1):
        """Perform the selected local row's explicit action, never a remote action."""
        self.error = None
        if self.selection == 0:
            if self.address is not None:
                self.stop()
                return
            self.prepare()
            try:
                if self._translations is None:
                    self._translations = {
                        lang: {key: value for key, value in load_catalog(lang).items()
                               if key.startswith("commander.web.")}
                        for lang in ("en", "de")}
                if self.server is None:
                    self.server = CommanderServer(translations=self._translations)
                self.server.start(self.host, self.port)
                self.address = self.server.address
                self.pairing_code = self.server.pairing_code
                self._notice_seq = None
                self.invalidate_commands()
            except (ImportError, OSError, ValueError, RuntimeError):
                self.stop()
                self.error = "commander.local.error.start"
        elif self.selection == 1 and self.address is None:
            self.prepare()
            self.host = self.hosts[(self.hosts.index(self.host) + direction) % len(self.hosts)]
        elif self.selection == 2 and self.address is None:
            self.port = max(1, min(65535, self.port + direction))
        elif self.selection == 3 and self.address is not None and self.server.connected:
            self.bridge.allowed = not self.bridge.allowed
            self.invalidate_commands()
        elif self.selection == 4 and self.address is not None:
            self.server.revoke()
            self.bridge.allowed = False
            self.connected = False
            self.pairing_code = self.server.pairing_code
            self.invalidate_commands()
        elif self.selection in (5, 6):
            decide = (self.bridge.accept_proposal if self.selection == 5
                      else self.bridge.reject_proposal)
            if not decide(game):
                self.error = "commander.local.error.proposal"
        elif self.selection in (7, 8):
            decide = (self.bridge.accept_navigation if self.selection == 7
                      else self.bridge.reject_navigation)
            if not decide(game):
                self.error = self.bridge.navigation_error

    def handle_key(self, game, key):
        if key in (pygame.K_ESCAPE, pygame.K_F9):
            game._open_administration("")
        elif key in (pygame.K_UP, pygame.K_DOWN):
            self.selection = (self.selection + (1 if key == pygame.K_DOWN else -1)) % 9
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.activate(game)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_MINUS,
                     pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_MINUS, pygame.K_KP_PLUS):
            if self.selection in (1, 2):
                self.activate(game, -1 if key in (pygame.K_LEFT, pygame.K_MINUS,
                                                pygame.K_KP_MINUS) else 1)

    @staticmethod
    def row_rects():
        """Shared canvas geometry for rendering and local click ownership."""
        return tuple(pygame.Rect(124, 226 + index * 34, 1032, 30) for index in range(9))

    def handle_click(self, game, canvas):
        for index, rect in enumerate(self.row_rects()):
            if rect.collidepoint(canvas):
                # Select first, then confirm. A stray click cannot accept a proposal.
                if self.selection == index:
                    self.activate(game)
                else:
                    self.selection = index
                return

    def draw(self, game):
        with translation_scope(game.tr):
            screen, tr = game.screen, game.tr
            panel = pygame.Rect(100, 20, 1080, 680)
            layout.panel(screen, panel)
            layout.blit_line(screen, "commander.local.title", (124, 32, 1032, 34),
                             config.COLOR_WARN, size=26)
            url = (f"http://{self.address[0]}:{self.address[1]}/"
                   if self.address is not None else tr("commander.local.unavailable"))
            layout.blit_line(screen, message("commander.local.url", url=raw_text(url)),
                             (124, 72, 1032, 26), config.COLOR_TEXT, size=18)
            layout.blit_line(screen, message("commander.local.code", code=raw_text(
                self.pairing_code or tr("commander.local.unavailable"))),
                (124, 100, 1032, 26), config.COLOR_TEXT, size=18)
            layout.blit_line(screen, message("commander.local.connection", state=tr(
                "commander.local.connected" if self.connected else "commander.local.disconnected")),
                (124, 128, 1032, 26), config.COLOR_TEXT, size=18)
            proposal = self.bridge.proposal if self.address is not None else None
            proposal_text = (message("commander.local.proposal", label=raw_text(proposal["label"]),
                                    status=tr("commander.local.proposal." + proposal["status"]))
                             if proposal else "commander.local.proposal.none")
            layout.blit_line(screen, proposal_text, (124, 156, 1032, 30),
                             config.COLOR_WARN, size=18)
            navigation = self.bridge.navigation_proposal if self.address is not None else None
            navigation_text = (message("commander.local.navigation.summary",
                status=tr("commander.local.proposal." + navigation["status"]),
                course=(f"{navigation['course']:.1f}" if navigation["course"] is not None
                        else tr("commander.local.navigation.unchanged")),
                speed=(f"{navigation['speed_kn']:.1f}" if navigation["speed_kn"] is not None
                       else tr("commander.local.navigation.unchanged")))
                if navigation else "commander.local.navigation.none")
            layout.blit_line(screen, navigation_text, (124, 188, 1032, 30),
                             config.COLOR_WARN, size=18)
            values = (
                message("commander.local.service", state=tr(
                    "common.on" if self.address is not None else "common.off")),
                message("commander.local.host", host=self.host),
                message("commander.local.port", port=self.port),
                message("commander.local.grant", state=tr(
                    "common.on" if self.bridge.allowed else "common.off")),
                "commander.local.revoke", "commander.local.accept", "commander.local.reject",
                "commander.local.navigation.accept", "commander.local.navigation.reject",
            )
            for index, (text, rect) in enumerate(zip(values, self.row_rects())):
                layout.blit_line(screen, message("menu.choice", marker=(
                    "> " if index == self.selection else "  "),
                    label=message(text) if isinstance(text, str) else text), rect,
                    config.COLOR_WARN if index == self.selection else config.COLOR_TEXT, size=20)
            layout.blit_block(screen, "commander.local.warning", 124, 538, 1032, 64,
                              config.COLOR_WARN, size=18)
            if self.error:
                layout.blit_line(screen, self.error, (124, 606, 1032, 28),
                                 config.COLOR_WARN, size=18)
            layout.blit_line(screen, "commander.local.hint", (124, 640, 1032, 30),
                             config.COLOR_TEXT_DIM, size=16)
