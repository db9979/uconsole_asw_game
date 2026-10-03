"""Station key helpers of the event owner: joystick steps, sonar cursor,
TMA and TAS keys, plot keys and clicks, numeric entry, MPA/consort orders,
ELOKA jamming and track-id entry.  Moved verbatim from ``game_events.py``;
``EventMixin`` inherits ``StationKeysMixin``.
"""

import pygame

from src.core import config
from src.core.i18n import localize, message
from src.core.station import Station
from src.core.limits import MAX_TRACK_DISPLAY_ID_LEN
from src.sonar import tma_operator


class StationKeysMixin:
    """Station-key helper half of ``EventMixin``."""

    def _joy_step(self, delta: int) -> None:
        """uConsole-Trackball Y-Achse: stationsabhängiger Schritt."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            self.dmg_team = (self.dmg_team - 1 + delta) % 3 + 1
        elif self.station is Station.SONAR:
            self._cycle_selected_contact(delta)
        elif self.station is Station.WEAPONS:
            self.torpedo_depth = config.clamp(
                self.torpedo_depth - delta * 10.0, 10.0, 300.0)
        elif self.station is Station.OPZ:
            self._cycle_opz_track(delta)
        elif self.station is Station.ELOKA:
            self._cycle_eloka_track(delta)
        elif self.station is Station.RADIO and self.station_page == 2:
            self._cycle_task(delta)
        elif self.station is Station.RADIO:
            self._cycle_hfdf(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(range_delta=float(-delta))
        elif self.station is Station.BRIDGE:
            self.ship.cycle_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)
        elif self.station is Station.ENGINE:
            self._cycle_engine_telegraph(-delta)
            self.flash(message("runtime.telegraph", order=self.ship.telegraph), 1.5)

    def _joy_horizontal_step(self, delta: int) -> None:
        """uConsole-Trackball X-Achse: selection or bearing step."""
        if self.in_menu or self.game_over:
            return
        if self.station is Station.DAMAGE:
            n = len(self.damage.compartments)
            self.dmg_cursor = (self.dmg_cursor + delta) % n
        elif self.station is Station.SONAR:
            self.sonar.set_listen_bearing(self.sonar.listen_bearing + delta * .5)
        elif self.station is Station.WEAPONS:
            self._cycle_selected_contact(delta)
        elif self.station is Station.OPZ:
            self._cycle_asm_track(delta)
        elif self.station is Station.HELICOPTER:
            self._adjust_helo_waypoint(bearing_delta=float(delta * 15))

    def _sonar_cursor_key(self, e) -> None:
        """Z/X move the frequency cursor; Shift: 10 Hz; Ctrl on LOFAR sets
        the band-pass low (Z) or high (X) edge at the cursor."""
        page = "demon" if self.sonar_page == 2 else "lofar"
        mods = getattr(e, "mod", 0)
        tools = self.sonar_tools
        if page == "lofar" and mods & pygame.KMOD_CTRL:
            cursor = tools.lofar_cursor_hz
            low, high = self.sonar.band_low_hz, self.sonar.band_high_hz
            low, high = ((cursor, high) if e.key == pygame.K_z else (low, cursor))
            if self.set_sonar_band(low, high) is True:
                self.flash(message("runtime.sonar_band", low=f"{low:.1f}",
                                   high=f"{high:.1f}"), 1.5)
            return
        fine = page == "demon" or tools.vernier
        step = 10.0 if mods & pygame.KMOD_SHIFT else (0.5 if fine else 1.0)
        current = tools.demon_cursor_hz if page == "demon" else tools.lofar_cursor_hz
        self.set_sonar_cursor(page, current + (step if e.key == pygame.K_x else -step))

    # --- Operator TMA (sonar page 3) ---

    def _tma_key(self, e) -> None:
        """TMA page: Z/X course -/+ (Shift fine), Ctrl+Z/X speed -/+,
        Q / Shift+Q range -/+, K accept, Shift+K copy the solver proposal."""
        contact = self._tma_contact()
        if contact is None:
            self.flash(message("runtime.tma.no_contact"), 1.5)
            return
        mods = getattr(e, "mod", 0)
        hypothesis = self.tma_hypothesis(contact)
        course, speed, rng = hypothesis.course, hypothesis.speed_kn, hypothesis.range_nm
        if e.key == pygame.K_k:
            if mods & pygame.KMOD_SHIFT:
                if self.tma_method == "ekelund":
                    result = self.copy_tma_ekelund(contact)
                    self.flash(message("runtime.tma.ekelund_copied" if result is True
                                       else "runtime.tma.ekelund_none"), 1.5)
                    return
                result = self.copy_tma_proposal(contact)
                self.flash(message("runtime.tma.copied" if result is True
                                   else "runtime.tma.no_proposal"), 1.5)
                return
            self._accept_tma_with_notice(contact)
            return
        sign = 1.0 if e.key == pygame.K_x else -1.0
        if e.key == pygame.K_q:
            rng += (tma_operator.RANGE_FINE_NM if mods & pygame.KMOD_CTRL
                    else tma_operator.RANGE_STEP_NM) * (1.0 if mods & pygame.KMOD_SHIFT
                                                        else -1.0)
        elif mods & pygame.KMOD_CTRL:
            speed += tma_operator.SPEED_STEP_KN * sign
        else:
            course += (tma_operator.COURSE_FINE_DEG if mods & pygame.KMOD_SHIFT
                       else tma_operator.COURSE_STEP_DEG) * sign
        self.set_tma_hypothesis(contact, course, speed, rng)

    def _tas_side_key(self, e) -> None:
        contact = self.selected_contact
        action = "confirm" if getattr(e, "mod", 0) & pygame.KMOD_SHIFT else "flip"
        result = self.set_tas_side(contact, action)
        if result is True:
            self.flash(message("runtime.tas_side.confirmed" if action == "confirm"
                               else "runtime.tas_side.flipped",
                               contact=self.contact_display_id(contact),
                               side=contact.towed_side), 1.5)
        else:
            self.flash(message("runtime.tas_side.not_ambiguous"), 1.5)

    def _handle_plot_key(self, key: int, mod: int) -> bool:
        """Plot-mode keys; returns True when the key was consumed."""
        view = self._plot_view()
        if view is None or self._local_station_input_locked():
            self._reset_plot_ui()
            return False
        if key == pygame.K_p or (key == pygame.K_ESCAPE and self.plot_anchor is None):
            self.toggle_plot_mode()
            return True
        if key == pygame.K_ESCAPE:
            self.plot_anchor = None
            return True
        steps = {pygame.K_LEFT: (-1, 0), pygame.K_RIGHT: (1, 0),
                 pygame.K_UP: (0, -1), pygame.K_DOWN: (0, 1)}
        if key in steps:
            px = (self.PLOT_CURSOR_STEP_FAST_PX if mod & pygame.KMOD_SHIFT
                  else self.PLOT_CURSOR_STEP_PX)
            step = px / max(view.scale, 1e-6)
            dx, dy = steps[key]
            limit = self.world.size_nm
            self.plot_cursor = (config.clamp(self.plot_cursor[0] + dx * step, 0.0, limit),
                                config.clamp(self.plot_cursor[1] + dy * step, 0.0, limit))
            return True
        if key in self.PLOT_TOOL_KEYS:
            self.plot_tool = self.PLOT_TOOL_KEYS[key]
            self.plot_anchor = None
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._plot_commit_point()
            return True
        if key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if mod & pygame.KMOD_SHIFT:
                self.plot_clear()
                self.flash(message("plot.flash.cleared"), 1.5)
                return True
            item = self.plot.nearest(*self.plot_cursor,
                                     self.PLOT_PICK_PX / max(view.scale, 1e-6))
            if item is not None:
                self.plot_remove(item["id"])
                self.flash(message("plot.flash.removed", label=item["label"]), 1.5)
            return True
        return False

    def _handle_plot_click(self, pos) -> bool:
        """Left click on the chart in plot mode places a point there."""
        view = self._plot_view()
        canvas = self._window_to_canvas(pos) if pos is not None else None
        if view is None or canvas is None:
            return False
        if not pygame.Rect(view.rect).collidepoint(canvas):
            return False
        x, y = view.screen_to_world(*canvas)
        limit = self.world.size_nm
        self._plot_commit_point(config.clamp(x, 0.0, limit), config.clamp(y, 0.0, limit))
        return True

    def _handle_numeric_input(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.input_mode = None
            self.input_buffer = ""
            self.flash(message("event.input_cancelled"), 1.5)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._finish_numeric_input()
        elif key == pygame.K_BACKSPACE:
            self.input_buffer = self.input_buffer[:-1]
        elif self.input_mode == "track_id":
            name = pygame.key.name(key)
            if (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                    and len(name) == 1 and name.isascii()
                    and (name.isalnum() or name == "-")):
                self.input_buffer += name.upper()
            elif (len(self.input_buffer) < MAX_TRACK_DISPLAY_ID_LEN
                  and key in (pygame.K_MINUS, pygame.K_KP_MINUS)):
                self.input_buffer += "-"
        elif len(pygame.key.name(key)) == 1 and pygame.key.name(key).isdigit():
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key)
        elif key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3,
                     pygame.K_KP4, pygame.K_KP5, pygame.K_KP6, pygame.K_KP7,
                     pygame.K_KP8, pygame.K_KP9):
            if len(self.input_buffer) < 5:
                self.input_buffer += pygame.key.name(key).strip("[]")
        elif (self.input_mode in ("speed", "bearing", "plot_speed")
              and key in (pygame.K_PERIOD, pygame.K_COMMA, pygame.K_KP_PERIOD)
              and "." not in self.input_buffer):
            self.input_buffer += "."

    def _finish_numeric_input(self) -> None:
        """Validate and apply a pending course or speed order."""
        mode = self.input_mode
        if mode == "track_id":
            track = self.selected_opz_track()
            result = ("stale_ref" if track is None else
                      self.set_opz_track_label(track.observation_id,
                                               self.input_buffer))
            if result is not True:
                self.flash(message("runtime.cic.track_id_invalid"), 2.0)
                return
            self.flash(message("runtime.cic.track_id_set",
                               track=self.input_buffer.upper()), 2.0)
            self.input_mode = None
            self.input_buffer = ""
            return
        value = self.input_buffer.replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            self.flash(message("event.invalid_input"), 2.0)
            return
        if mode == "plot_speed":
            pending = self._plot_dr_pending
            self.input_mode = None
            self.input_buffer = ""
            self._plot_dr_pending = None
            if pending is not None:
                self._plot_flash_result(self.plot_add(
                    "dr", pending[0], pending[1], course=pending[2],
                    speed_kn=number))
            return
        if mode == "torpedo_depth":
            if not 10.0 <= number <= 300.0:
                self.flash(message("event.invalid_input"), 2.0)
                return
            self.torpedo_depth = number
            self.flash(message("runtime.numeric.torpedo_depth",
                               depth=f"{number:.0f}"), 2.0)
            self.input_mode = None
            self.input_buffer = ""
            return
        if mode in ("course", "bearing"):
            if not 0.0 <= number < 360.0:
                self.flash(message("runtime.numeric.angle"), 2.0)
                return
            if mode == "bearing":
                if self.set_sonar_listen_bearing(number) is not True:
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.true_bearing", bearing=f"{number:05.1f}"), 2.0)
            else:
                result = (self.set_engine_course(number)
                          if self.station is Station.ENGINE else self.order_course(number))
                if result in ("bridge_down", "engine_down"):
                    self.flash(message("event.bridge_down" if result == "bridge_down"
                                       else "engine.limit.down"))
                    self.input_mode = None
                    self.input_buffer = ""
                    return
                if result != "ok":
                    self.flash(message("event.invalid_input"), 2.0)
                    return
                self.flash(message("runtime.numeric.course", course=f"{number:03.0f}"), 2.0)
        else:
            if not 0.0 <= number <= config.SHIP_SPEED_MAX_KN:
                self.flash(message("runtime.numeric.speed",
                                   maximum=f"{config.SHIP_SPEED_MAX_KN:.0f}"), 2.0)
                return
            result = (self.set_engine_speed(number) if self.station is Station.ENGINE
                      else self.order_speed(number))
            if result not in (True, "ok"):
                self.flash(message("event.invalid_input"), 2.0)
                return
            self.flash(message("runtime.numeric.speed_set", speed=f"{number:.1f}"), 2.0)
        self.input_mode = None
        self.input_buffer = ""

    def _begin_numeric_input(self, mode: str) -> None:
        """Open a keyboard-first entry for a navigation order."""
        self._clear_controls()
        self.input_mode = mode
        if mode == "bearing":
            self.input_buffer = ""
            prompt = message("runtime.input.bearing",
                             current=f"{self.sonar.listen_bearing:05.1f}")
        elif mode == "plot_speed":
            self.input_buffer = ""
            prompt = message("plot.input.speed")
        elif mode == "course":
            self.input_buffer = ""
            prompt = message("runtime.input.course",
                             current=f"{self.ship.target_course:03.0f}")
        elif mode == "torpedo_depth":
            self.input_buffer = ""
            prompt = message("runtime.input.torpedo_depth",
                             current=f"{self.torpedo_depth:.0f}")
        else:
            self.input_buffer = ""
            prompt = message("runtime.input.speed",
                             current=f"{self.ship.target_speed:.1f}")
        self.flash(message("runtime.input.pending", prompt=localize(prompt, self.tr),
                            value=self.input_buffer), 60.0)

    def _mpa_key_order(self, e):
        """OPZ page 3: the patrol aircraft's order for a key, on the same keys
        as the helicopter (H, W, X, B, Shift+B, Shift+M, Ctrl+R, D), or None."""
        mods = getattr(e, "mod", 0)
        shift, ctrl = bool(mods & pygame.KMOD_SHIFT), bool(mods & pygame.KMOD_CTRL)
        if e.key == pygame.K_h:
            return self.toggle_mpa
        if e.key == pygame.K_w:
            return self.mpa_waypoint_to_selection
        if e.key == pygame.K_x:
            return ((lambda: self.set_mpa_pattern("single")) if shift
                    else self.cycle_mpa_pattern)
        if e.key == pygame.K_b:
            return self.toggle_mpa_buoy_mode if shift else self.mpa_drop_buoy
        if e.key == pygame.K_m and shift:
            return self.toggle_mpa_mad
        if e.key == pygame.K_r and ctrl:
            return self.toggle_mpa_radar
        if e.key == pygame.K_d:
            return self.mpa_attack
        return None

    def _consort_key_order(self, e):
        """OPZ page 4: the consort destroyer's order for a key, or None:
        F formation station, W prosecute the selected track, X search here,
        H hold, Y auto, Shift+A active sonar, Shift+W weapons free."""
        mods = getattr(e, "mod", 0)
        shift = bool(mods & pygame.KMOD_SHIFT)
        orders = getattr(self, "consort", None)
        if e.key == pygame.K_w and shift:
            return lambda: self.set_consort_weapons(
                not orders.weapons_free if orders is not None else True)
        if e.key == pygame.K_a and shift:
            return lambda: self.set_consort_active(
                not orders.active if orders is not None else True)
        if e.key == pygame.K_f:
            return self.cycle_consort_station
        if e.key == pygame.K_w:
            return self.consort_point_to_selection
        if e.key == pygame.K_x:
            return lambda: self.set_consort_mode("search")
        if e.key == pygame.K_h:
            return lambda: self.set_consort_mode("hold")
        if e.key == pygame.K_y:
            return lambda: self.set_consort_mode("auto")
        return None

    def _eloka_jamming_key(self, e) -> None:
        """ELOKA: E engages/releases the directional jammer on the selected
        intercept, Shift+E cycles the ECM technique."""
        if getattr(e, "mod", 0) & pygame.KMOD_SHIFT:
            technique = self._cycle_jamming_technique(self.selected_eloka_track())
            technique_names = {
                "noise": message("eloka.technique.noise"),
                "rgpo": message("eloka.technique.rgpo"),
                "vgpo": message("eloka.technique.vgpo"),
                "false_targets": message("eloka.technique.false_targets"),
            }
            notice = (message("runtime.eloka.technique",
                              technique=technique_names[technique])
                      if technique in technique_names else
                      message("runtime.eloka.jamming_off"))
            self.flash(notice, 1.5)
        else:
            result = self.deploy_jamming(self.selected_eloka_track())
            self.flash(message("runtime.eloka.jamming_on" if result is True
                               else "runtime.eloka.jamming_off"), 1.5)

    def _begin_track_id_input(self) -> None:
        """Open bounded OPZ entry for the selected track's shared display ID."""
        track = self.selected_opz_track()
        if track is None:
            self.flash(message("runtime.cic.none_select"), 2.0)
            return
        self._clear_controls()
        self.input_mode = "track_id"
        self.input_buffer = ""
        self.flash(message("runtime.input.track_id", current=track.label), 60.0)
