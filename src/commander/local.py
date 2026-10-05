"""Local-only Commander lifecycle and crew administration, never persisted.

Construction opens nothing. prepare() performs bounded interface discovery once;
activate(game) is the only start path. pump(game) belongs to the main wall loop,
including menu frames, and stop() uses the transport's bounded shutdown.
"""

import ipaddress
from itertools import islice
import os
import socket
import ssl
import struct
import sys
import time

import pygame

from src.commander.access_point import HotspotController
from src.commander.bridge import CommanderBridge
from src.commander.admission import StationAdmission
from src.commander.server import (CommanderServer, web_catalog, DIRECT_FIRE_ROLES, ROLES,
                                  SONAR_AUDIO_ROLES, STATIONS)
from src.core import config, manual
from src.core.i18n import load_catalog, message, raw_text, translation_scope
from src.data.contact_analysis import load_contact_analysis_assets
from src.ui import layout, overlay_style, qr


# Seconds between an accepted admin "end game" and the process quitting.
WEB_SHUTDOWN_GRACE_S = 2.0
# F9 rows: one switch, the crew list and the advanced network rows, which only
# show when opened (network mode, address, port and, while multiplayer is off
# and the hotspot helper is installed, a new hotspot password).
BASIC_ROWS = ("service", "roster", "advanced")
ADVANCED_ROWS = ("mode", "host", "port")
RENEW_ROW = "renew"

class CommanderConsole:
    def __init__(self, hotspot=None):
        self.admission = StationAdmission()
        self.server = None
        self.bridge = CommanderBridge()
        self.hotspot = hotspot or HotspotController()
        self.network_mode = "lan"
        # Solo is a per-launch host decision, never persisted.
        self.solo = False
        self.web_mode = False
        self.web_auth = None
        self.public_origin = None
        self._eco_present = False
        self._eco_polled = float("-inf")
        self.hosts = ("127.0.0.1",)
        self.host = self.hosts[0]
        self.port = 8765
        self.address = None
        # The phone lookouts' HTTPS address and certificate fingerprint.
        self.tls_address = None
        self.tls_fingerprint = None
        self.tls_error = None
        self.error = None
        # Admin page "end game": the process quits once the result is out.
        self.shutdown_at = None
        self.selection = 0
        # The advanced network rows are hidden until the host opens them; an
        # address picked there is kept instead of the automatic choice.
        self.advanced = False
        self._host_chosen = False
        self.connected = False
        self.active_crew = False
        self._statuses_cache = None
        self.pairing_code = None
        self._prepared = False
        self._translations = None
        self._contact_analysis_assets = None
        self._manual_pages = None
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
        self._renew_seen = None
        self._qr_payload = None
        self._qr_box_px = None
        self._qr_surface = None
        self._url_qr_payload = None
        self._lookout_qr_payload = None
        self._lookout_qr_box_px = None
        self._lookout_qr_surface = None
        self._url_qr_box_px = None
        self._url_qr_surface = None

    def prepare(self):
        """Discover at most 64 Linux interface IPv4s, with no DNS or LAN probe."""
        if self._prepared:
            return
        hosts = {"127.0.0.1"}
        networks = tuple(ipaddress.IPv4Network(net) for net in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
        try:
            if not sys.platform.startswith("linux"):
                raise ImportError("SIOCGIFADDR 0x8915 is Linux's")  # macOS, Windows
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
            pass
        if len(hosts) == 1:
            # Without Linux ioctls (Windows, macOS) or a private interface
            # address, ask the routing table which local address reaches the
            # network: a UDP connect to an IP literal sends nothing and
            # resolves no name. Never fall back to wildcard binding or a
            # potentially blocking hostname resolver.
            address = self._route_address()
            if address is not None and any(address in net for net in networks):
                hosts.add(str(address))
        self.hosts = ("127.0.0.1", *sorted(hosts - {"127.0.0.1"}))
        self._prepared = True

    @staticmethod
    def _route_address():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 9))  # TEST-NET-1, no packet sent
                return ipaddress.IPv4Address(probe.getsockname()[0])
        except (OSError, ValueError):
            return None

    def invalidate_commands(self):
        self.bridge.invalidate_commands()

    def _stop_transport(self):
        self.admission.request = None
        self.admission.deferred.clear()
        if self.server is not None:
            self.server.stop()
        self.address = None
        self.tls_address = None
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
    def _station_row(status, station):
        """One roster row; a server without the role reports it idle."""
        return status["stations"].get(station) or dict(
            leased=False, requested=False, station_generation=None,
            request_generation=0,
            grants=dict(command=False, direct_fire=False, sonar_audio=False))

    @classmethod
    def _requested_station(cls, status):
        return next((station for station in ROLES
                     if cls._station_row(status, station)["requested"]), None)

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
        if station in ROLES:
            self.roster_station = ROLES.index(station)
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
            selected_station = ROLES[self.roster_station]
            station = (selected_station
                       if self._station_row(selected, selected_station)["requested"]
                       else self._requested_station(selected))
            if station is None:
                self.roster_status = "commander.roster.error.no_request"
                return
            detail = self._station_row(selected, station)
            ok = self.server.resolve_station_request(
                client_id, station, detail["request_generation"],
                dict(command=True, direct_fire=station in DIRECT_FIRE_ROLES,
                     sonar_audio=station in SONAR_AUDIO_ROLES), takeover=True)
            if ok:
                self.roster_station = ROLES.index(station)
            success = message("commander.roster.status.assigned", client=name,
                              station=message(self._station_key(station)))
        elif action == "reject":
            selected_station = ROLES[self.roster_station]
            station = (selected_station
                       if self._station_row(selected, selected_station)["requested"]
                       else self._requested_station(selected))
            if station is None:
                self.roster_status = "commander.roster.error.no_request"
                return
            ok = self.server.reject_station_request(
                client_id, station, self._station_row(selected, station)["request_generation"])
            success = message("commander.roster.status.rejected", client=name)
        elif action == "assign":
            station = ROLES[self.roster_station]
            ok = self.server.grant_station(client_id, station)
            success = message("commander.roster.status.assigned", client=name,
                              station=message(self._station_key(station)))
        elif action in ("simlog", "observer"):
            # A station is always held with its full rights; only the
            # session-wide SimLog and observer grants remain host toggles.
            enabled = not selected.get(action, False)
            ok = self.server.set_client_grant(client_id, action, enabled)
            success = message("commander.roster.status.grant", client=name,
                              capability=message(f"commander.roster.capability.{action}"),
                              state=message("common.on" if enabled else "common.off"))
            if not ok:
                self.roster_status = "commander.roster.error.grant"
                return
        elif action == "revoke_station":
            station = ROLES[self.roster_station]
            if not self._station_row(selected, station)["leased"]:
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
        renew_state = getattr(self.hotspot, "renew_state", None)
        if renew_state == "error" and self._renew_seen != "error":
            self.error = f"commander.local.hotspot.error.{self.hotspot.renew_error}"
        self._renew_seen = renew_state
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
        if not self.web_mode and hasattr(self.server, "resolve_station_request"):
            self.admission.sync(game, self)
        self.connected = self.server.connected
        self.active_crew = False
        if hasattr(self.server, "client_statuses"):
            # Building the roster copies every session; 4 Hz is plenty for
            # the two flags read here and saves main-thread time per frame.
            if (self._statuses_cache is None or self._statuses_cache[0] != id(self.server)
                    or now - self._statuses_cache[1] >= .25):
                self._statuses_cache = (id(self.server), now, self.server.client_statuses())
            statuses = self._statuses_cache[2]
            self.connected = self.connected or bool(statuses)
            self.active_crew = self.active_crew or any(
                status["active_station"] in ROLES for status in statuses)
        else:
            self.active_crew = self.connected
        if getattr(game, "local_side", "frigate") != "uboot" and self.station_leased(game.station):
            game._clear_station_input()
            game.input_mode = None
            game.input_buffer = ""
        # Remote proposals remain staging requests; final decisions stay local.
        if self.server.connected and not self.bridge.allowed:
            self.bridge.allowed = True
        self.bridge.pump(game, self.server)
        if self.web_mode:
            if self.shutdown_at is not None and now >= self.shutdown_at:
                game.running = False
            if self.bridge._identity != (id(game.world), id(game.sonar)):
                self.server.reject_web_admin_pending()
            else:
                self._pump_web_admin(game)
            self.server.web_reclaim_available()
            prefs = game.preferences
            traffic = game.live_traffic
            live_world = traffic._center is not None
            self.server.publish_web_options({
                "language": prefs.language, "simlog": prefs.simlog,
                "voice_enabled": self.server.voice_enabled,
                "voice_talker": self.server.voice_talker,
                "live_ais_enabled": prefs.live_ais_enabled,
                "live_adsb_enabled": prefs.live_adsb_enabled,
                "aisstream_api_key_set": bool(prefs.aisstream_api_key),
                "opensky_credentials_set": bool(prefs.opensky_credentials),
                "live_ais_status": self._web_live_status(
                    prefs.live_ais_enabled, live_world, traffic.ais_client,
                    missing_key=not bool(prefs.aisstream_api_key.strip())),
                "live_adsb_status": self._web_live_status(
                    prefs.live_adsb_enabled, live_world, traffic.adsb_client),
            })
            self.server.publish_web_proposals({
                "target": self.bridge.proposal,
                "navigation": self.bridge.navigation_proposal,
            })
        self.pairing_code = self.server.pairing_code
        if not self.web_mode:
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

    @staticmethod
    def _web_live_status(enabled, world_available, client, *, missing_key=False):
        if not enabled:
            return "disabled"
        if not world_available:
            return "no_geography"
        if missing_key:
            return "no_key"
        if client is None:
            return "unavailable"
        if client.connected:
            return "connected"
        error = client.last_error or ""
        if "429" in error:
            return "rate_limited"
        if "401" in error or "403" in error:
            return "auth_error"
        return "error" if error else "connecting"

    def _pump_web_admin(self, game):
        server = self.server
        items = server.drain_web_admin()
        for request_id, digest, body in items:
            with server._lock:
                current = digest == server._web_host_digest
                host = server._sessions_v2.get(digest)
                host_id = host["client_id"] if host is not None else None
            if not current:
                server.finish_web_admin(request_id, False)
                continue
            action = body["action"]
            if action == "option":
                name, value = body["name"], body["value"]
                if name == "voice_enabled":
                    server.set_voice_enabled(value)
                    server.finish_web_admin(request_id, {"ok": True})
                    continue
                if getattr(game.preferences, name) == value:
                    server.finish_web_admin(request_id, {"ok": True})
                    continue
                game._set_preference(name, value)
                if name.startswith("live_") or name in (
                        "aisstream_api_key", "opensky_credentials"):
                    game.live_traffic.configure(game, game.world, game.preferences)
                server.finish_web_admin(request_id, {"ok": True})
                continue
            client_id = body["client_id"]
            station = body["station"]
            value = body["value"]
            if action == "assign":
                # A granted station always carries all of its rights.
                ok = server.grant_station(client_id, station)
            elif action == "revoke":
                ok = server.revoke_station(station)
            elif action == "revoke_client":
                ok = client_id != host_id and server.revoke_client(client_id)
            elif action in ("command", "direct_fire", "sonar_audio"):
                ok = server.set_client_grant(client_id, station, action, value)
            elif action == "simlog":
                ok = server.set_client_grant(client_id, "simlog", value)
            elif action == "observer":
                ok = server.set_client_grant(client_id, "observer", value)
            elif action == "shutdown":
                # Leave the result time to reach the admin page, then quit.
                ok = value is True
                if ok:
                    self.shutdown_at = time.monotonic() + WEB_SHUTDOWN_GRACE_S
            elif action == "rotate_code":
                with server._lock:
                    server._rotate_code_locked()
                ok = True
            elif action == "accept_target":
                ok = self.bridge.accept_proposal(game)
            elif action == "reject_target":
                ok = self.bridge.reject_proposal(game)
            elif action == "accept_navigation":
                ok = self.bridge.accept_navigation(game)
            elif action == "reject_navigation":
                ok = self.bridge.reject_navigation(game)
            else:
                ok = False
            server.finish_web_admin(request_id, ok)

    def cycle_confirmation(self):
        """Cycle pending proposal types in deterministic target/navigation order."""
        _, kinds = self._confirmation_state()
        if len(kinds) < 2:
            return
        self.confirm_kind = kinds[(kinds.index(self.confirm_kind) + 1) % len(kinds)]
        self.confirm_selection = 0
        self._confirm_mouse_selection = None

    def _decide_confirmation(self, game, accepted):
        if not self.confirm_visible(game) or game.input_mode is not None:
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
        if not self.confirm_visible(game) or game.input_mode is not None:
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
            overlay_style.panel(screen, panel)
            overlay_style.title(screen, "commander.confirm.title",
                                (panel.x + 24, panel.y + 16, panel.w - 48, 34), size=24)
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
                lang: web_catalog(load_catalog(lang))
                for lang in ("en", "de")}
        if self._contact_analysis_assets is None:
            self._contact_analysis_assets = load_contact_analysis_assets()
        if self._manual_pages is None:
            self._manual_pages = {lang: manual.html_page(lang) for lang in manual.LANGUAGES}
        if self.server is None:
            self.server = CommanderServer(
                translations=self._translations,
                contact_analysis_assets=self._contact_analysis_assets,
                web_auth=self.web_auth, public_origin=self.public_origin,
                manual_pages=self._manual_pages)
            if self.solo:
                self.server.set_solo_mode(True)

    def eco_display_ready(self, game):
        """Solo browser is live and no host dialog needs the full local screen.

        The presence query is sampled at most every ``ECO_PRESENCE_POLL_S`` of
        wall time; anything that asks for the host's attention wins at once.
        """
        if (not self.solo or self.address is None or self.server is None
                or self.admission.request is not None or self.roster_open
                or self.confirm_visible(game)):
            self._eco_present = False
            return False
        now = time.monotonic()
        if now - self._eco_polled >= config.ECO_PRESENCE_POLL_S:
            self._eco_polled = now
            query = getattr(self.server, "solo_browser_present", None)
            self._eco_present = bool(query and query(config.ECO_PRESENCE_MAX_AGE_S))
        return self._eco_present

    def set_solo(self, enabled):
        """Switch crew/solo; a running server revokes every session and code."""
        enabled = bool(enabled)
        if enabled is self.solo:
            return
        self.solo = enabled
        if self.server is not None:
            self.server.set_solo_mode(enabled)
            self.pairing_code = self.server.pairing_code
            self.invalidate_commands()

    def autostart_solo(self):
        """Launch-time solo start on the first private LAN address, else loopback."""
        self.autostart(solo=True)

    def autostart(self, solo=False):
        """Remote Crew start on the first private LAN address, else the hotspot."""
        self.solo = bool(solo)
        self.error = None
        try:
            self._prepare_transport()
            self._start_service()
        except (ImportError, OSError, ValueError, RuntimeError):
            self.deactivate()
            self.error = "commander.local.error.start"

    def start_web(self, web_auth, public_origin, port, bind_host="127.0.0.1"):
        """Start an opt-in browser-only room behind an HTTPS proxy."""
        self.web_mode = True
        self.web_auth = web_auth
        self.public_origin = public_origin
        self.port = port
        self.host = bind_host
        self._prepare_transport()
        self._start_transport(self.host)

    def _lookout_tls(self, host):
        """TLS context for the phone lookouts' HTTPS listener, or None (the
        crew then plays on plain HTTP; the phone falls back to swiping)."""
        self.tls_error = None
        if self.web_mode:
            return None
        try:
            from src.commander import tls
            cert, key = tls.ensure_certificate(os.path.join(config.SAVE_DIR, "tls"), host)
            self.tls_fingerprint = tls.fingerprint(cert)
            return tls.context(cert, key)
        except (OSError, ValueError, ssl.SSLError):
            self.tls_error = "commander.local.tls_unavailable"
            self.tls_fingerprint = None
            return None

    def _start_transport(self, host):
        self._prepare_transport()
        context = self._lookout_tls(host)
        self.server.start(host, self.port, tls_context=context)
        self.address = self.server.address
        self.tls_address = getattr(self.server, "tls_address", None)
        if context is not None and self.tls_address is None:
            self.tls_error = "commander.local.tls_unavailable"
        self.pairing_code = self.server.pairing_code
        self._notice_seq = None
        self.invalidate_commands()

    def rows(self):
        """Names of the F9 rows on screen, top to bottom."""
        if not self.advanced:
            return BASIC_ROWS
        running = self.address is not None or self.hotspot.active
        renew = (not running and getattr(self.hotspot, "renew_supported", False))
        return BASIC_ROWS + ADVANCED_ROWS + ((RENEW_ROW,) if renew else ())

    def _start_service(self):
        """Switch multiplayer on: the LAN, else the hotspot when no LAN is up.

        Without advanced choices the first private LAN address is used; with
        none (only loopback) and the hotspot helper installed the uConsole
        opens its own hotspot instead.
        """
        if self.network_mode == "lan":
            self.prepare()
            if not self._host_chosen:
                self.host = self.hosts[1] if len(self.hosts) > 1 else self.hosts[0]
            if (not self._host_chosen and len(self.hosts) == 1
                    and self.hotspot.available):
                self.network_mode = "hotspot"
        if self.network_mode == "hotspot":
            self._hotspot_error_seen = None
            self.hotspot.start()
            if self.hotspot.state == "error":
                self._hotspot_error_seen = self.hotspot.error
                self.error = f"commander.local.hotspot.error.{self.hotspot.error}"
        else:
            self._start_transport(self.host)

    def activate(self, game, direction=1):
        """Perform the selected local row's explicit action, never a remote action."""
        self.error = None
        rows = self.rows()
        row = rows[self.selection % len(rows)]
        running = self.address is not None or self.hotspot.active
        if row == "service":
            if running:
                self.deactivate()
                return
            try:
                self._prepare_transport()
                self._start_service()
            except (ImportError, OSError, ValueError, RuntimeError):
                self.deactivate()
                self.error = "commander.local.error.start"
        elif row == "roster":
            self.roster_open = True
            self.roster_status = None
            statuses = self._roster()
            selected = self._selected_client(statuses)
            station = ((self._requested_station(selected) or selected["active_station"])
                       if selected is not None else None)
            self.roster_station = ROLES.index(station) if station in ROLES else 0
        elif row == "advanced":
            self.advanced = not self.advanced
            self.selection = min(self.selection, len(self.rows()) - 1)
        elif row == "mode" and not running:
            self.network_mode = "hotspot" if self.network_mode == "lan" else "lan"
        elif row == "host" and self.network_mode == "lan" and not running:
            self.prepare()
            self.host = self.hosts[(self.hosts.index(self.host) + direction) % len(self.hosts)]
            self._host_chosen = True
        elif row == "port" and not running:
            self.port = max(1024, min(65535, self.port + direction))
        elif row == RENEW_ROW and not running:
            # The helper keeps the Wi-Fi name; phones have to join again.
            self._renew_seen = None
            self.hotspot.renew_password()

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
            self.selection = ((self.selection + (1 if key == pygame.K_DOWN else -1))
                              % len(self.rows()))
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.activate(game)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_MINUS,
                     pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_MINUS, pygame.K_KP_PLUS):
            if self.rows()[self.selection % len(self.rows())] in ("advanced", *ADVANCED_ROWS):
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
            self.roster_station = (self.roster_station + direction) % len(ROLES)
            self.roster_status = None
            self._roster_mouse_confirm = None
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._roster_action("approve")
        elif key == pygame.K_a:
            self._roster_action("assign")
        elif key == pygame.K_r:
            self._roster_action("reject")
        elif key == pygame.K_l:
            self._roster_action("simlog")
        elif key == pygame.K_o:
            self._roster_action("observer")
        elif key == pygame.K_x:
            self._roster_action("revoke_station")
        elif key == pygame.K_DELETE:
            self._roster_action("revoke_client")
        elif key == pygame.K_BACKSPACE:
            self._roster_action("revoke_all")

    @staticmethod
    def row_rects():
        """Shared canvas geometry for rendering and local click ownership."""
        return tuple(pygame.Rect(124, 300 + index * 34, 1032, 32) for index in range(7))

    @staticmethod
    def roster_client_rects():
        return tuple(pygame.Rect(124, 116 + index * 31, 548, 28) for index in range(12))

    @staticmethod
    def roster_action_rects():
        return tuple(pygame.Rect(704, 116 + index * 39, 452, 34) for index in range(8))

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
        for index, rect in enumerate(self.row_rects()[:len(self.rows())]):
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
                if station in ROLES:
                    self.roster_station = ROLES.index(station)
                self.roster_status = None
                self._roster_mouse_confirm = None
                return
        for direction, rect in zip((-1, 1), self.roster_station_cycle_rects()):
            if rect.collidepoint(canvas):
                self.roster_station = (self.roster_station + direction) % len(ROLES)
                self.roster_status = None
                self._roster_mouse_confirm = None
                return
        actions = ("approve", "reject", "assign", "simlog", "observer",
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

    def _hotspot_qr(self, ssid, password, box_px=132):
        """Return the cached QR surface for the current Wi-Fi credentials."""
        payload = qr.wifi_payload(ssid, password)
        if (self._qr_payload != payload or self._qr_box_px != box_px
                or self._qr_surface is None):
            matrix = qr.encode(payload)
            self._qr_payload = payload
            self._qr_box_px = box_px
            self._qr_surface = qr.to_surface(
                matrix, module_px=max(1, box_px // (len(matrix) + 4)))
        return self._qr_surface

    def _lookout_qr(self, box_px=105):
        """The cached QR surface that opens the phone lookout page (HTTPS)."""
        host, port = self.tls_address
        payload = f"https://{host}:{port}/lookout"
        if (self._lookout_qr_payload != payload or self._lookout_qr_box_px != box_px
                or self._lookout_qr_surface is None):
            matrix = qr.encode(payload)
            self._lookout_qr_payload = payload
            self._lookout_qr_box_px = box_px
            self._lookout_qr_surface = qr.to_surface(
                matrix, module_px=max(1, box_px // (len(matrix) + 4)))
        return self._lookout_qr_surface

    def _url_qr(self, host, port, box_px=132):
        """Return the cached QR surface that opens the crew page directly."""
        payload = f"http://{host}:{port}/"
        if (self._url_qr_payload != payload or self._url_qr_box_px != box_px
                or self._url_qr_surface is None):
            matrix = qr.encode(payload)
            self._url_qr_payload = payload
            self._url_qr_box_px = box_px
            self._url_qr_surface = qr.to_surface(
                matrix, module_px=max(1, box_px // (len(matrix) + 4)))
        return self._url_qr_surface

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
            overlay_style.panel(screen, panel)
            overlay_style.title(screen, "commander.local.title", (124, 30, 1032, 36),
                                size=28, align="left")
            url = (f"http://{self.address[0]}:{self.address[1]}/"
                   if self.address is not None else tr("commander.local.unavailable"))
            proxy = self.public_origin if not self.web_mode else None
            layout.blit_line(screen, message("commander.local.url_proxy", url=raw_text(url),
                                             proxy=raw_text(proxy + "/"))
                             if proxy and self.address is not None else
                             message("commander.local.url", url=raw_text(url)),
                             (124, 72, 1032, 34), config.COLOR_TEXT, size=24,
                             align="center")
            layout.blit_line(screen, message("commander.local.connection", state=tr(
                "commander.local.connected" if self.connected else "commander.local.disconnected")),
                (124, 104, 1032, 26), config.COLOR_TEXT, size=20, align="center")
            hotspot = self.network_mode == "hotspot"
            if hotspot:
                self._draw_hotspot_steps(screen, tr)
            else:
                layout.blit_line(screen, "commander.local.url.qr",
                                 (936, 134, 105, 28), config.COLOR_TEXT_DIM, size=12,
                                 align="center")
                if self.address is not None:
                    surface = self._url_qr(self.address[0], self.address[1], box_px=105)
                    screen.blit(surface, (936 + (105 - surface.get_width()) // 2,
                                          166 + (105 - surface.get_height()) // 2))
                layout.blit_line(screen, "commander.local.join_code",
                                 (124, 144, 790, 24), config.COLOR_TEXT_DIM, size=20,
                                 align="center")
                code = self.pairing_code or "------"
                layout.blit_line(screen, raw_text(code[:3] + " " + code[3:]),
                                 (124, 174, 790, 108), config.COLOR_WARN, size=72,
                                 align="center")
            # The phone lookout: its own QR code opens the HTTPS page.
            if self.address is not None and self.tls_address is not None:
                layout.blit_line(screen, "commander.local.lookout.qr",
                                 (1051, 134, 105, 28), config.COLOR_TEXT_DIM, size=12,
                                 align="center")
                surface = self._lookout_qr()
                screen.blit(surface, (1051 + (105 - surface.get_width()) // 2,
                                      166 + (105 - surface.get_height()) // 2))
            service_state = (f"commander.local.hotspot.state.{self.hotspot.state}"
                             if self.network_mode == "hotspot" and self.hotspot.active
                             else "common.on" if self.address is not None else "common.off")
            texts = {
                "service": message("commander.local.service", state=tr(service_state)),
                "roster": "commander.local.roster",
                "advanced": message("commander.local.advanced", state=tr(
                    "commander.local.advanced.open" if self.advanced
                    else "commander.local.advanced.closed")),
                "mode": message("commander.local.mode", mode=tr(
                    f"commander.local.mode.{self.network_mode}")),
                "host": (message("commander.local.host", host=self.host)
                         if self.network_mode == "lan" else "commander.local.hotspot.host_auto"),
                "port": message("commander.local.port", port=self.port),
                RENEW_ROW: message("commander.local.hotspot.renew", state=tr(
                    "commander.local.hotspot.renew."
                    + (getattr(self.hotspot, "renew_state", None) or "idle"))),
            }
            values = tuple(texts[row] for row in self.rows())
            for index, (text, rect) in enumerate(zip(values, self.row_rects())):
                layout.blit_line(screen, message("menu.choice", marker=(
                    "> " if index == self.selection else "  "),
                    label=message(text) if isinstance(text, str) else text), rect,
                    config.COLOR_WARN if index == self.selection else config.COLOR_TEXT, size=20)
            warning = ("commander.local.hotspot.warning" if self.network_mode == "hotspot"
                       else "commander.local.warning")
            layout.blit_block(screen, warning, 124, 542, 1032, 54,
                               config.COLOR_WARN, size=18)
            if self.error or (self.address is not None and self.tls_error):
                layout.blit_line(screen, self.error or self.tls_error, (124, 604, 1032, 34),
                                   config.COLOR_WARN, size=18)
            layout.blit_line(screen, "commander.local.hint", (124, 646, 1032, 30),
                              config.COLOR_TEXT_DIM, size=16)

    def _draw_hotspot_steps(self, screen, tr):
        """Hotspot: step 1 joins the Wi-Fi, step 2 opens the crew page.

        Both steps are on screen at once, each with its QR code; the lookout
        QR keeps the column right of them.
        """
        details = self.hotspot.details
        unavailable = tr("commander.local.unavailable")
        layout.blit_line(screen, "commander.local.hotspot.step1", (124, 134, 400, 24),
                         config.COLOR_TEXT, size=18)
        if details is not None:
            surface = self._hotspot_qr(details.ssid, details.password, box_px=105)
            screen.blit(surface, (124 + (105 - surface.get_width()) // 2,
                                  162 + (105 - surface.get_height()) // 2))
        layout.blit_line(screen, "commander.local.hotspot.ssid_label",
                         (240, 164, 284, 24), config.COLOR_TEXT_DIM, size=15)
        layout.blit_line(screen, raw_text(details.ssid if details is not None
                                          else unavailable),
                         (240, 188, 284, 30), config.COLOR_TEXT, size=22)
        layout.blit_line(screen, "commander.local.hotspot.password_label",
                         (240, 220, 284, 24), config.COLOR_TEXT_DIM, size=15)
        layout.blit_line(screen, raw_text(details.password if details is not None
                                          else unavailable),
                         (240, 246, 284, 36), config.COLOR_WARN, size=26)
        layout.blit_line(screen, "commander.local.hotspot.step2", (544, 134, 492, 24),
                         config.COLOR_TEXT, size=18)
        if self.address is not None:
            surface = self._url_qr(self.address[0], self.address[1], box_px=105)
            screen.blit(surface, (544 + (105 - surface.get_width()) // 2,
                                  162 + (105 - surface.get_height()) // 2))
        layout.blit_line(screen, "commander.local.join_code", (660, 166, 376, 24),
                         config.COLOR_TEXT_DIM, size=18, align="center")
        code = self.pairing_code or "------"
        layout.blit_line(screen, raw_text(code[:3] + " " + code[3:]),
                         (660, 192, 376, 72), config.COLOR_WARN, size=62, align="center")

    def _draw_roster(self, game):
        screen, tr = game.screen, game.tr
        panel = pygame.Rect(100, 20, 1080, 680)
        overlay_style.panel(screen, panel)
        overlay_style.title(screen, "commander.roster.title", (124, 30, 1032, 36), size=28,
                            align="left")
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
        action_texts = (
            "commander.roster.approve", "commander.roster.reject",
            message("commander.roster.assign", station=message(
                self._station_key(ROLES[self.roster_station]))),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.simlog"), state=message(
                    "common.on" if selected and selected["simlog"] else "common.off")),
            message("commander.roster.toggle", capability=message(
                "commander.roster.capability.observer"), state=message(
                    "common.on" if selected and selected.get("observer") else "common.off")),
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
