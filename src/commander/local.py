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

from src.commander.access_point import HotspotController
from src.commander.bridge import CommanderBridge
from src.commander.admission import StationAdmission
from src.commander.server import CommanderServer, STATIONS
from src.core import config
from src.core.i18n import load_catalog, message, raw_text, translation_scope
from src.data.contact_analysis import load_contact_analysis_assets
from src.ui import layout


class CommanderConsole:
    def __init__(self, hotspot=None):
        self.admission = StationAdmission()
        self.server = None
        self.bridge = CommanderBridge()
        self.hotspot = hotspot or HotspotController()
        self.network_mode = "lan"
        self.hosts = ("127.0.0.1",)
        self.host = self.hosts[0]
        self.port = 8765
        self.address = None
        self.error = None
        self.selection = 0
        self.connected = False
        self.active_crew = False
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
        self.roster_open = False
        self.roster_client_id = None
        self.roster_station = 0
        self.roster_status = None
        self._roster_mouse_confirm = None
        self._hotspot_error_seen = None

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

    def _stop_transport(self):
        self.admission.request = None
        self.admission.deferred.clear()
        if self.server is not None:
            self.server.stop()
        self.address = None
        self.connected = False
        self.active_crew = False
        self.pairing_code = None
        self.bridge.allowed = False
        self.invalidate_commands()
        self._close_confirmation()
        self._close_roster()

    def deactivate(self):
        """Stop Remote Crew first, then release a game-owned hotspot."""
        self._stop_transport()
        if self.hotspot.active:
            self.hotspot.request_stop()

    def stop(self):
        self._stop_transport()
        self.hotspot.close()

    def _close_roster(self):
        self.roster_open = False
        self.roster_client_id = None
        self.roster_status = None
        self._roster_mouse_confirm = None

    def _roster(self):
        """Return the server's detached roster and keep selection deterministic."""
        statuses = self.server.client_statuses() if self.server is not None else []
        ids = [status["client_id"] for status in statuses]
        if self.roster_client_id not in ids:
            self.roster_client_id = ids[0] if ids else None
        return statuses

    def _selected_client(self, statuses=None):
        statuses = self._roster() if statuses is None else statuses
        return next((status for status in statuses
                     if status["client_id"] == self.roster_client_id), None)

    @staticmethod
    def _station_key(station):
        return "station.ew" if station == "eloka" else f"station.{station}"

    @staticmethod
    def _requested_station(status):
        return next((station for station in STATIONS
                     if status["stations"][station]["requested"]), None)

    def _select_client(self, direction):
        statuses = self._roster()
        if not statuses:
            self.roster_status = "commander.roster.error.empty"
            return
        ids = [status["client_id"] for status in statuses]
        index = ids.index(self.roster_client_id)
        self.roster_client_id = ids[(index + direction) % len(ids)]
        selected = self._selected_client(statuses)
        station = self._requested_station(selected) or selected["active_station"]
        if station in STATIONS:
            self.roster_station = STATIONS.index(station)
        self.roster_status = None
        self._roster_mouse_confirm = None

    def _roster_result(self, ok, success):
        self.roster_status = success if ok else "commander.roster.error.stale"
        self._roster_mouse_confirm = None

    def _roster_action(self, action):
        """Apply one local-host roster action after refreshing client state."""
        statuses = self._roster()
        selected = self._selected_client(statuses)
        if action == "revoke_all":
            if not statuses:
                self.roster_status = "commander.roster.error.empty"
                return
            self.server.revoke_all()
            self._roster_result(True, "commander.roster.status.all_revoked")
            return
        if selected is None:
            self.roster_status = "commander.roster.error.no_client"
            return
        client_id = selected["client_id"]
        name = raw_text(selected["name"])
        if action == "approve":
            selected_station = STATIONS[self.roster_station]
            station = (selected_station
                       if selected["stations"][selected_station]["requested"]
                       else self._requested_station(selected))
            if station is None:
                self.roster_status = "commander.roster.error.no_request"
                return
            detail = selected["stations"][station]
            ok = self.server.resolve_station_request(
                client_id, station, detail["request_generation"],
                dict(command=True, direct_fire=False, sonar_audio=False))
            if ok:
                self.roster_station = STATIONS.index(station)
            success = message("commander.roster.status.assigned", client=name,
                              station=message(self._station_key(station)))
        elif action == "reject":
            selected_station = STATIONS[self.roster_station]
            station = (selected_station
                       if selected["stations"][selected_station]["requested"]
                       else self._requested_station(selected))
            if station is None:
                self.roster_status = "commander.roster.error.no_request"
                return
            ok = self.server.reject_station_request(
                client_id, station, selected["stations"][station]["request_generation"])
            success = message("commander.roster.status.rejected", client=name)
        elif action == "assign":
            station = STATIONS[self.roster_station]
            ok = self.server.grant_station(client_id, station)
            success = message("commander.roster.status.assigned", client=name,
                              station=message(self._station_key(station)))
        elif action in ("command", "direct_fire", "simlog", "sonar_audio"):
            station = STATIONS[self.roster_station]
            enabled = (not selected["simlog"] if action == "simlog" else
                       not selected["stations"][station]["grants"][action])
            ok = (self.server.set_client_grant(client_id, action, enabled)
                  if action == "simlog" else
                  self.server.set_client_grant(client_id, station, action, enabled))
            success = message("commander.roster.status.grant", client=name,
                              capability=message(f"commander.roster.capability.{action}"),
                              state=message("common.on" if enabled else "common.off"))
            if not ok:
                self.roster_status = "commander.roster.error.grant"
                return
        elif action == "revoke_station":
            station = STATIONS[self.roster_station]
            if not selected["stations"][station]["leased"]:
                self.roster_status = "commander.roster.error.no_station"
                return
            ok = self.server.revoke_station(station)
            success = message("commander.roster.status.station_revoked", client=name)
        elif action == "revoke_client":
            ok = self.server.revoke_client(client_id)
            success = message("commander.roster.status.client_revoked", client=name)
        else:
            return
        self._roster_result(ok, success)

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

    def station_leased(self, station) -> bool:
        query = getattr(self.server, "station_leased", None)
        return bool(query and query(station.name.lower()))

    def pump(self, game):
        hotspot_state = self.hotspot.poll()
        if self.network_mode == "hotspot":
            if hotspot_state == "running" and self.address is None:
                try:
                    self._start_transport(self.hotspot.details.address)
                except (ImportError, OSError, ValueError, RuntimeError):
                    self._stop_transport()
                    self.hotspot.request_stop()
                    self.error = "commander.local.hotspot.error.listener"
            elif hotspot_state == "error" and self.hotspot.error != self._hotspot_error_seen:
                if self.address is not None:
                    self._stop_transport()
                self._hotspot_error_seen = self.hotspot.error
                self.error = f"commander.local.hotspot.error.{self.hotspot.error}"
        if self.address is None:
            self._close_confirmation()
            return
        now = time.monotonic()
        if hasattr(self.server, "resolve_station_request"):
            self.admission.sync(game, self)
        self.connected = self.server.connected
        self.active_crew = bool(self.server.connected)
        if hasattr(self.server, "client_statuses"):
            statuses = self.server.client_statuses()
            self.connected = self.connected or bool(statuses)
            self.active_crew = self.active_crew or any(
                status["active_station"] in STATIONS for status in statuses)
        if self.station_leased(game.station):
            game._clear_station_input()
            game.input_mode = None
            game.input_buffer = ""
        # Protocol v1 can only annotate and stage proposals; final decisions
        # remain local in the confirmation overlay now that its grant row is gone.
        if self.server.connected and not self.bridge.allowed:
            self.bridge.allowed = True
        self.bridge.pump(game, self.server, now=now)
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

    def _prepare_transport(self):
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

    def _start_transport(self, host):
        self._prepare_transport()
        self.server.start(host, self.port)
        self.address = self.server.address
        self.pairing_code = self.server.pairing_code
        self._notice_seq = None
        self.invalidate_commands()

    def activate(self, game, direction=1):
        """Perform the selected local row's explicit action, never a remote action."""
        self.error = None
        if self.selection == 0:
            if self.address is not None or self.hotspot.active:
                self.deactivate()
                return
            try:
                self._prepare_transport()
                if self.network_mode == "hotspot":
                    self._hotspot_error_seen = None
                    self.hotspot.start()
                    if self.hotspot.state == "error":
                        self._hotspot_error_seen = self.hotspot.error
                        self.error = f"commander.local.hotspot.error.{self.hotspot.error}"
                else:
                    self.prepare()
                    self._start_transport(self.host)
            except (ImportError, OSError, ValueError, RuntimeError):
                self.deactivate()
                self.error = "commander.local.error.start"
        elif self.selection == 1 and self.address is None and not self.hotspot.active:
            self.network_mode = "hotspot" if self.network_mode == "lan" else "lan"
        elif (self.selection == 2 and self.network_mode == "lan"
              and self.address is None and not self.hotspot.active):
            self.prepare()
            self.host = self.hosts[(self.hosts.index(self.host) + direction) % len(self.hosts)]
        elif self.selection == 3 and self.address is None and not self.hotspot.active:
            self.port = max(1024, min(65535, self.port + direction))
        elif self.selection == 4:
            self.roster_open = True
            self.roster_status = None
            statuses = self._roster()
            selected = self._selected_client(statuses)
            station = ((self._requested_station(selected) or selected["active_station"])
                       if selected is not None else None)
            self.roster_station = STATIONS.index(station) if station in STATIONS else 0

    def handle_key(self, game, key):
        if self.admission.request is not None:
            self.admission.handle_key(game, self, key)
            return
        if self.roster_open:
            self._handle_roster_key(game, key)
        elif key in (pygame.K_ESCAPE, pygame.K_F9):
            _, kinds = self._confirmation_state()
            if kinds:
                self._confirm_suppressed = None
                self._confirm_requested = True
                if self.confirm_kind not in kinds:
                    self.confirm_kind = kinds[0]
            game._open_administration("")
        elif key in (pygame.K_UP, pygame.K_DOWN):
            self.selection = (self.selection + (1 if key == pygame.K_DOWN else -1)) % 5
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.activate(game)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_MINUS,
                     pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_MINUS, pygame.K_KP_PLUS):
            if self.selection in (1, 2, 3):
                self.activate(game, -1 if key in (pygame.K_LEFT, pygame.K_MINUS,
                                                 pygame.K_KP_MINUS) else 1)

    def _handle_roster_key(self, game, key):
        if key == pygame.K_ESCAPE:
            self.roster_open = False
            self.roster_status = None
            self._roster_mouse_confirm = None
        elif key == pygame.K_F9:
            self._close_roster()
            game._open_administration("")
        elif key in (pygame.K_UP, pygame.K_DOWN):
            self._select_client(1 if key == pygame.K_DOWN else -1)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_MINUS,
                     pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_MINUS, pygame.K_KP_PLUS):
            direction = -1 if key in (pygame.K_LEFT, pygame.K_MINUS,
                                      pygame.K_KP_MINUS) else 1
            self.roster_station = (self.roster_station + direction) % len(STATIONS)
            self.roster_status = None
            self._roster_mouse_confirm = None
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._roster_action("approve")
        elif key == pygame.K_a:
            self._roster_action("assign")
        elif key == pygame.K_r:
            self._roster_action("reject")
        elif key == pygame.K_c:
            self._roster_action("command")
        elif key == pygame.K_d:
            self._roster_action("direct_fire")
        elif key == pygame.K_l:
            self._roster_action("simlog")
        elif key == pygame.K_u:
            self._roster_action("sonar_audio")
        elif key == pygame.K_x:
            self._roster_action("revoke_station")
        elif key == pygame.K_DELETE:
            self._roster_action("revoke_client")
        elif key == pygame.K_BACKSPACE:
            self._roster_action("revoke_all")

    @staticmethod
    def row_rects():
        """Shared canvas geometry for rendering and local click ownership."""
        return tuple(pygame.Rect(124, 300 + index * 48, 1032, 40) for index in range(5))

    @staticmethod
    def roster_client_rects():
        return tuple(pygame.Rect(124, 116 + index * 31, 548, 28) for index in range(12))

    @staticmethod
    def roster_action_rects():
        return tuple(pygame.Rect(704, 116 + index * 39, 452, 34) for index in range(10))

    @classmethod
    def roster_station_cycle_rects(cls):
        assign = cls.roster_action_rects()[2]
        return (pygame.Rect(assign.x, assign.y, 42, assign.h),
                pygame.Rect(assign.right - 42, assign.y, 42, assign.h))

    def handle_click(self, game, canvas):
        if self.admission.request is not None:
            self.admission.handle_click(game, self, canvas)
            return
        if self.roster_open:
            self._handle_roster_click(canvas)
            return
        for index, rect in enumerate(self.row_rects()):
            if rect.collidepoint(canvas):
                # Select first, then confirm. A stray click cannot accept a proposal.
                if self.selection == index:
                    self.activate(game)
                else:
                    self.selection = index
                return

    def _handle_roster_click(self, canvas):
        statuses = self._roster()
        for status, rect in zip(statuses, self.roster_client_rects()):
            if rect.collidepoint(canvas):
                self.roster_client_id = status["client_id"]
                station = self._requested_station(status) or status["active_station"]
                if station in STATIONS:
                    self.roster_station = STATIONS.index(station)
                self.roster_status = None
                self._roster_mouse_confirm = None
                return
        for direction, rect in zip((-1, 1), self.roster_station_cycle_rects()):
            if rect.collidepoint(canvas):
                self.roster_station = (self.roster_station + direction) % len(STATIONS)
                self.roster_status = None
                self._roster_mouse_confirm = None
                return
        actions = ("approve", "reject", "assign", "command", "direct_fire", "simlog",
                   "sonar_audio",
                   "revoke_station", "revoke_client", "revoke_all")
        for action, rect in zip(actions, self.roster_action_rects()):
            if rect.collidepoint(canvas):
                if action in ("revoke_client", "revoke_all"):
                    signature = (action, (self.roster_client_id if action == "revoke_client"
                                          else tuple(status["client_id"] for status in statuses)))
                    if self._roster_mouse_confirm != signature:
                        self._roster_mouse_confirm = signature
                        self.roster_status = f"commander.roster.confirm.{action}"
                        return
                self._roster_action(action)
                return

    def draw(self, game):
        if self.admission.request is not None:
            self.admission.draw(game)
            return
        with translation_scope(game.tr):
            if self.roster_open:
                self._draw_roster(game)
                return
            screen, tr = game.screen, game.tr
            panel = pygame.Rect(100, 20, 1080, 680)
            layout.panel(screen, panel)
            layout.blit_line(screen, "commander.local.title", (124, 32, 1032, 34),
                             config.COLOR_WARN, size=26)
            url = (f"http://{self.address[0]}:{self.address[1]}/"
                   if self.address is not None else tr("commander.local.unavailable"))
            layout.blit_line(screen, message("commander.local.url", url=raw_text(url)),
                             (124, 72, 1032, 34), config.COLOR_TEXT, size=24,
                             align="center")
            layout.blit_line(screen, message("commander.local.connection", state=tr(
                "commander.local.connected" if self.connected else "commander.local.disconnected")),
                (124, 104, 1032, 26), config.COLOR_TEXT, size=20, align="center")
            if self.network_mode == "hotspot":
                details = self.hotspot.details
                ssid = details.ssid if details is not None else tr("commander.local.unavailable")
                password = (details.password if details is not None
                            else tr("commander.local.unavailable"))
                layout.blit_line(screen, message("commander.local.hotspot.ssid",
                                                  ssid=raw_text(ssid)),
                                 (124, 134, 1032, 24), config.COLOR_TEXT, size=18,
                                 align="center")
                layout.blit_line(screen, message("commander.local.hotspot.password",
                                                  password=raw_text(password)),
                                 (124, 160, 1032, 24), config.COLOR_WARN, size=18,
                                 align="center")
            layout.blit_line(screen, "commander.local.join_code",
                              (124, 190 if self.network_mode == "hotspot" else 144,
                               1032, 26), config.COLOR_TEXT_DIM, size=20, align="center")
            code = self.pairing_code or "------"
            grouped_code = raw_text(code[:3] + " " + code[3:])
            layout.blit_line(screen, grouped_code,
                             (124, 216 if self.network_mode == "hotspot" else 174,
                              1032, 76 if self.network_mode == "hotspot" else 108),
                             config.COLOR_WARN, size=64 if self.network_mode == "hotspot" else 72,
                             align="center")
            service_state = (f"commander.local.hotspot.state.{self.hotspot.state}"
                             if self.network_mode == "hotspot" and self.hotspot.active
                             else "common.on" if self.address is not None else "common.off")
            values = (
                message("commander.local.service", state=tr(service_state)),
                message("commander.local.mode", mode=tr(
                    f"commander.local.mode.{self.network_mode}")),
                (message("commander.local.host", host=self.host)
                 if self.network_mode == "lan" else "commander.local.hotspot.host_auto"),
                message("commander.local.port", port=self.port), "commander.local.roster",
            )
            for index, (text, rect) in enumerate(zip(values, self.row_rects())):
                layout.blit_line(screen, message("menu.choice", marker=(
                    "> " if index == self.selection else "  "),
                    label=message(text) if isinstance(text, str) else text), rect,
                    config.COLOR_WARN if index == self.selection else config.COLOR_TEXT, size=20)
            warning = ("commander.local.hotspot.warning" if self.network_mode == "hotspot"
                       else "commander.local.warning")
            layout.blit_block(screen, warning, 124, 542, 1032, 54,
                               config.COLOR_WARN, size=18)
            if self.error:
                layout.blit_line(screen, self.error, (124, 604, 1032, 34),
                                   config.COLOR_WARN, size=18)
            layout.blit_line(screen, "commander.local.hint", (124, 646, 1032, 30),
                              config.COLOR_TEXT_DIM, size=16)

    def _draw_roster(self, game):
        screen, tr = game.screen, game.tr
        panel = pygame.Rect(100, 20, 1080, 680)
        layout.panel(screen, panel)
        layout.blit_line(screen, "commander.roster.title", (124, 32, 1032, 34),
                         config.COLOR_WARN, size=26)
        layout.blit_line(screen, "commander.roster.subtitle", (124, 70, 1032, 28),
                         config.COLOR_TEXT_DIM, size=16)
        statuses = self._roster()
        selected = self._selected_client(statuses)
        if not statuses:
            layout.blit_block(screen, "commander.roster.empty", 124, 116, 548, 80,
                              config.COLOR_TEXT_DIM, size=20, valign="center")
        unavailable = tr("commander.roster.none")
        for status, rect in zip(statuses, self.roster_client_rects()):
            active = status["active_station"]
            requested = self._requested_station(status)
            station = (tr(self._station_key(active)) if active else unavailable)
            request = (tr(self._station_key(requested)) if requested else unavailable)
            text = message("commander.roster.client", name=raw_text(status["name"]),
                           station=raw_text(station), request=raw_text(request))
            chosen = status["client_id"] == self.roster_client_id
            pygame.draw.rect(screen, (10, 22, 16), rect)
            pygame.draw.rect(screen, config.COLOR_WARN if chosen
                             else config.COLOR_SONAR_RING, rect, 2 if chosen else 1)
            layout.blit_line(screen, text, rect.inflate(-10, -2),
                             config.COLOR_WARN if chosen else config.COLOR_TEXT, size=16)
        state = "common.on" if selected is not None else "common.off"
        selected_station = STATIONS[self.roster_station]
        station_grants = (selected["stations"][selected_station]["grants"]
                          if selected else {})
        action_texts = (
            "commander.roster.approve", "commander.roster.reject",
            message("commander.roster.assign", station=message(
                self._station_key(STATIONS[self.roster_station]))),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.command"), state=message(
                    "common.on" if station_grants.get("command") else "common.off")),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.direct_fire"), state=message(
                    "common.on" if station_grants.get("direct_fire") else "common.off")),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.simlog"), state=message(
                    "common.on" if selected and selected["simlog"] else "common.off")),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.sonar_audio"), state=message(
                    "common.on" if station_grants.get("sonar_audio") else "common.off")),
            "commander.roster.revoke_station", "commander.roster.revoke_client",
            "commander.roster.revoke_all",
        )
        for text, rect in zip(action_texts, self.roster_action_rects()):
            pygame.draw.rect(screen, (10, 22, 16), rect)
            pygame.draw.rect(screen, config.COLOR_SONAR_RING, rect, 1)
            content = rect.inflate(-10, -2)
            if rect == self.roster_action_rects()[2]:
                content = pygame.Rect(rect.x + 48, rect.y + 2, rect.w - 96, rect.h - 4)
            layout.blit_line(screen, text, content, config.COLOR_TEXT, size=17)
        for text, rect in zip(("<", ">"), self.roster_station_cycle_rects()):
            pygame.draw.rect(screen, config.COLOR_SONAR_RING, rect, 1)
            layout.blit_line(screen, raw_text(text), rect, config.COLOR_WARN,
                             size=20, align="center")
        layout.blit_line(screen, message("commander.roster.selection_state", state=message(state)),
                         (124, 504, 548, 28), config.COLOR_TEXT_DIM, size=15)
        if self.roster_status:
            layout.blit_block(screen, self.roster_status, 124, 548, 1032, 52,
                              config.COLOR_WARN, size=18, valign="center")
        layout.blit_block(screen, "commander.roster.hint", 124, 620, 1032, 58,
                          config.COLOR_TEXT_DIM, size=16, valign="center")
