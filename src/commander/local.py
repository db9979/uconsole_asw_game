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
from src.data.contact_analysis import load_contact_analysis_assets
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
        self._contact_analysis_assets = None
        self._notice_seq = None
        self._last_notice = float("-inf")
        self._confirm_signature = None
        self._confirm_suppressed = None
        self._confirm_requested = False
        self._confirm_owned = False
        self._confirm_identity = None
        self.confirm_kind = None
        self.confirm_selection = 0
        self._confirm_mouse_selection = None

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
        self._close_confirmation()

    @staticmethod
    def _pending(proposal):
        return proposal is not None and proposal["status"] == "pending"

    def _confirmation_state(self):
        proposal = self.bridge.proposal
        navigation = self.bridge.navigation_proposal
        signature = (
            self.bridge.proposal_sequence,
            None if proposal is None else (
                proposal["ref"], proposal["label"], proposal["status"]),
            None if navigation is None else (
                navigation["course"], navigation["speed_kn"], navigation["status"]),
        )
        kinds = tuple(kind for kind, value in (
            ("target", proposal), ("navigation", navigation)) if self._pending(value))
        return signature, kinds

    def _close_confirmation(self):
        self._confirm_requested = False
        self._confirm_owned = False
        self.confirm_kind = None
        self._confirm_mouse_selection = None

    def _sync_confirmation(self, game):
        signature, kinds = self._confirmation_state()
        changed = signature != self._confirm_signature
        self._confirm_signature = signature
        self._confirm_identity = (id(game.world), id(game.sonar))
        if not kinds:
            self._confirm_suppressed = None
            self._close_confirmation()
            return
        if changed:
            self._confirm_suppressed = None
            self._confirm_requested = True
            self.confirm_kind = kinds[0]
            self.confirm_selection = 0
            self._confirm_mouse_selection = None
        elif self.confirm_kind not in kinds:
            self.confirm_kind = kinds[0]
            self.confirm_selection = 0
            self._confirm_mouse_selection = None
        if self._confirm_suppressed == signature:
            self._confirm_requested = False
        visible = self.confirm_visible(game)
        if visible and not self._confirm_owned:
            game._clear_controls()
        self._confirm_owned = visible

    def confirm_visible(self, game):
        """Return whether the transient crew confirmation is currently visible."""
        if not self._confirm_requested:
            return False
        if (self.address is None or self.server is None or not self.server.connected
                or not self.bridge.allowed
                or self._confirm_identity != (id(game.world), id(game.sonar))):
            self._close_confirmation()
            return False
        if (not game.running or game.in_menu or game.main_menu
                or game.editor is not None or game.splash_active or game.game_over
                or game.administration_open):
            return False
        _, kinds = self._confirmation_state()
        return self.confirm_kind in kinds

    def pump(self, game):
        if self.address is None:
            self._close_confirmation()
            return
        now = time.monotonic()
        self.bridge.pump(game, self.server, now=now)
        self.connected = self.server.connected
        self.pairing_code = self.server.pairing_code
        self._sync_confirmation(game)
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
            game.flash(message("commander.local.notice" if self._pending(proposal)
                               else "commander.local.navigation.notice"), 3.0)
            game.audio.play_alert("danger")

    def cycle_confirmation(self):
        """Cycle pending proposal types in deterministic target/navigation order."""
        _, kinds = self._confirmation_state()
        if len(kinds) < 2:
            return
        self.confirm_kind = kinds[(kinds.index(self.confirm_kind) + 1) % len(kinds)]
        self.confirm_selection = 0
        self._confirm_mouse_selection = None

    def _decide_confirmation(self, game, accepted):
        if not self.confirm_visible(game) or game.paused or game.input_mode is not None:
            return
        decide = ((self.bridge.accept_proposal if accepted else self.bridge.reject_proposal)
                  if self.confirm_kind == "target" else
                  (self.bridge.accept_navigation if accepted else self.bridge.reject_navigation))
        if not decide(game):
            self.error = (self.bridge.navigation_error if self.confirm_kind == "navigation"
                          else "commander.local.error.proposal")
        self._sync_confirmation(game)

    def handle_confirm_key(self, game, key):
        if key == pygame.K_ESCAPE:
            self._confirm_suppressed = self._confirm_signature
            self._confirm_requested = False
            self._confirm_owned = False
            return True
        elif key == pygame.K_F8:
            self.cycle_confirmation()
            return True
        elif key == pygame.K_F6:
            self._decide_confirmation(game, True)
            return True
        elif key == pygame.K_F7:
            self._decide_confirmation(game, False)
            return True
        return False

    @staticmethod
    def confirm_rect():
        return pygame.Rect(250, 218, 780, 284)

    @classmethod
    def confirm_button_rects(cls):
        panel = cls.confirm_rect()
        return (pygame.Rect(panel.x + 34, panel.bottom - 84, 338, 42),
                pygame.Rect(panel.x + 408, panel.bottom - 84, 338, 42))

    def handle_confirm_click(self, game, canvas):
        if not self.confirm_visible(game) or game.paused or game.input_mode is not None:
            return False
        if not self.confirm_rect().collidepoint(canvas):
            return False
        for index, rect in enumerate(self.confirm_button_rects()):
            if rect.collidepoint(canvas):
                self.confirm_selection = index
                if self._confirm_mouse_selection == index:
                    self._decide_confirmation(game, index == 0)
                else:
                    self._confirm_mouse_selection = index
                return True
        return True

    def draw_confirm(self, game):
        if not self.confirm_visible(game):
            return
        with translation_scope(game.tr):
            screen, tr = game.screen, game.tr
            panel = self.confirm_rect()
            layout.panel(screen, panel)
            layout.blit_line(screen, "commander.confirm.title",
                             (panel.x + 24, panel.y + 16, panel.w - 48, 34),
                             config.COLOR_WARN, size=24, align="center")
            proposal = (self.bridge.proposal if self.confirm_kind == "target"
                        else self.bridge.navigation_proposal)
            if self.confirm_kind == "target":
                detail = message("commander.confirm.target",
                                 label=raw_text(proposal["label"]))
            else:
                unchanged = raw_text(tr("commander.confirm.unchanged"))
                detail = message(
                    "commander.confirm.navigation",
                    course=(raw_text(f"{proposal['course']:.1f}")
                            if proposal["course"] is not None else unchanged),
                    speed=(raw_text(f"{proposal['speed_kn']:.1f}")
                           if proposal["speed_kn"] is not None else unchanged),
                )
            layout.blit_block(screen, detail, panel.x + 34, panel.y + 62,
                              panel.w - 68, 74, config.COLOR_TEXT, size=20,
                              align="center", valign="center")
            _, kinds = self._confirmation_state()
            hint = ("commander.confirm.hint.multiple" if len(kinds) > 1
                    else "commander.confirm.hint.single")
            layout.blit_line(screen, hint,
                             (panel.x + 34, panel.y + 142, panel.w - 68, 28),
                             config.COLOR_TEXT_DIM, size=15, align="center")
            for index, (rect, key) in enumerate(zip(
                    self.confirm_button_rects(),
                    ("commander.confirm.accept", "commander.confirm.reject"))):
                selected = index == self.confirm_selection
                pygame.draw.rect(screen, (10, 22, 16), rect)
                pygame.draw.rect(screen, config.COLOR_WARN if selected
                                 else config.COLOR_SONAR_RING, rect, 2 if selected else 1)
                layout.blit_line(screen, key, rect,
                                 config.COLOR_WARN if selected else config.COLOR_TEXT,
                                 size=18, align="center")

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
                if self._contact_analysis_assets is None:
                    self._contact_analysis_assets = load_contact_analysis_assets()
                if self.server is None:
                    self.server = CommanderServer(
                        translations=self._translations,
                        contact_analysis_assets=self._contact_analysis_assets)
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
            self.port = max(1024, min(65535, self.port + direction))
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
