"""The uConsole playing the hostile submarine (new game or lobby side).

The frigate then belongs to the Remote Crew browsers (or to its autocrew);
the local screen, keys and sound serve only the crewed boat.  The boat has the
seven stations of its Remote Crew roles (keys 1-7 or Tab): command, sonar,
weapons, engine room, mast & ESM, navigation and the radio room.  The sonar room uses the
``Station.SONAR`` slot (the ordinary sonar workstation drawn and operated
inside ``Game.sonar_perspective``), every other station the ``Station.BRIDGE``
slot.  Each order key works only at the station that owns the order, exactly
as the browser's action allowlist; a station a browser holds is not operated
from the uConsole.

Nothing here reads frigate truth for display: the boat, the known chart and
the boat's own sonar contacts only.  Frigate flashes, its event feed and its
local sound cues are withheld while this side is played.
"""

import math

import pygame

from src.commander.server import OPFOR_ROLES, V2_ACTION_REGISTRY
from src.core import attack_computer, boat_esm, config, opfor
from src.core.i18n import display_value, message
from src.core.station import Station
from src.enemies import damage_control

LOCAL_SIDES = ("frigate", "uboot")
# Sonar-room keys the boat's operator may use.  Everything that would reach
# the frigate (telegraph, plot, OPZ release) or does not exist aboard the boat
# (towed array handling) is withheld.
_SONAR_BLOCKED = frozenset({
    pygame.K_y, pygame.K_u, pygame.K_v, pygame.K_g, pygame.K_p,
    pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS,
    pygame.K_MINUS, pygame.K_KP_MINUS,
    pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_F8, pygame.K_F11,
    pygame.K_0, pygame.K_KP0,
})
UBOOT_INPUT_MODES = ("uboot_course", "uboot_speed", "uboot_depth", "uboot_bearing",
                     "uboot_range", "uboot_torpedo_depth", "uboot_wire_bearing",
                     "uboot_wire_range")
# Rejections of the tube orders (``Sub.command_load_tube``/``command_flood_tube``).
TUBE_REASONS = ("not_ready", "no_torpedoes", "uboot_compartment_down", "uboot_tubes_full",
                "uboot_no_dry_tube")
# Rejections of boat-mode orders that have their own local text.
UBOOT_LOCAL_REASONS = ("not_ready", "uboot_too_deep", "uboot_no_snorkel", "uboot_mast_depth",
                       "uboot_no_absorbers", "uboot_no_candles", "uboot_candle_burning",
                       "uboot_no_air_stores", "uboot_no_hp_air", "uboot_compartment_down")


def playing(game) -> bool:
    return getattr(game, "local_side", "frigate") == "uboot"


def local_station(game) -> str:
    """The boat station the uConsole shows (a Remote Crew boat role)."""
    if game.station is Station.SONAR:
        return "uboot_sonar"
    station = getattr(game, "uboot_station", "uboot")
    # The sonar slot decides the sonar room (a reset returns to Station.BRIDGE).
    return station if station in OPFOR_ROLES and station != "uboot_sonar" else "uboot"


def set_local_station(game, station) -> None:
    if station not in OPFOR_ROLES:
        return
    game._clear_controls()
    game.uboot_station = station
    game.station = Station.SONAR if station == "uboot_sonar" else Station.BRIDGE


def station_remote(game) -> bool:
    """A browser holds the station the uConsole shows: it is not operated here."""
    query = getattr(getattr(game.commander, "server", None), "station_leased", None)
    return bool(query and query(local_station(game)))


def order_allowed(game, action) -> bool:
    """Order keys follow the Remote Crew allowlist of the shown station."""
    spec = V2_ACTION_REGISTRY.get(action)
    if spec is not None and local_station(game) in spec.stations:
        return True
    owner = next((role for role in OPFOR_ROLES if spec is not None and role in spec.stations),
                 None)
    game.flash(message("uboot.local.wrong_station", station=message(
        f"station.{owner}" if owner else "station.uboot")), 2.0)
    return False


def toggle_side(game) -> str:
    game.local_side = "frigate" if playing(game) else "uboot"
    return game.local_side


def boat(game):
    return game.opfor if playing(game) else None


def selected_contact(game):
    current = boat(game)
    if current is None:
        return None
    contact = current.station.selected_contact
    if contact is None or current.station.sonar.contacts.get(contact.target_id) is not contact:
        return None
    return contact


def _contacts(current):
    return [contact for contact in current.station.sonar.active_contacts()]


def _cycle_contact(game, current, delta: int) -> None:
    contacts = sorted(_contacts(current), key=lambda item: item.id)
    if not contacts:
        current.station.selected_contact = None
        game.flash(message("uboot.local.no_contact"), 1.5)
        return
    selected = current.station.selected_contact
    index = next((i for i, item in enumerate(contacts) if item is selected), -1)
    current.station.selected_contact = contacts[(index + delta) % len(contacts)]


def fire_at_contact(game, current, contact):
    """The shot the Remote Crew ``uboot_fire`` makes, for a local contact."""
    sub = current.sub
    if contact is None or current.station.sonar.contacts.get(contact.target_id) is not contact:
        return "unknown_ref"
    if not 0 <= game.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S:
        return "stale_ref"
    solution = attack_computer.solution_for_target(current, contact.target_id, game.sim_t)
    if solution is not None:
        # The periscope's attack computer has a course and speed on it.
        return attack_computer.fire_on_solution(game, current, solution)
    bearing = (contact.passive_bearing if contact.passive_bearing is not None
               else contact.bearing)
    range_nm = course = speed = None
    if (contact.observed_x is not None and contact.observed_y is not None
            and contact.range_source in ("ping", "tma", "visual")
            and 0 <= game.sim_t - contact.range_seen < config.SONAR_CONTACT_LOST_S):
        dx, dy = contact.observed_x - sub.x, contact.observed_y - sub.y
        bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
        range_nm = min(40.0, max(0.05, math.hypot(dx, dy)))
        if (contact.range_source == "tma" and contact.tma_course is not None
                and contact.tma_speed is not None
                and contact.tma_quality >= config.TMA_RANGE_MIN_QUALITY):
            course = contact.tma_course % 360.0
            speed = min(60.0, max(0.0, contact.tma_speed))
    if bearing is None or not math.isfinite(bearing):
        return "stale_ref"
    return sub.command_fire(bearing % 360.0, range_nm, course, speed, now=game.sim_t,
                            depth_m=current.orders.torpedo_depth, salvo=current.orders.salvo)


def _announce(game, category: str, text, seconds: float = 2.0) -> None:
    """Banner plus boat log for a completed order (as ``Game.announce``)."""
    game.flash(text, seconds)
    current = boat(game)
    if current is not None:
        current.notice(game.sim_t, category, text, stamp=game.world.format_time())


def _mode_notice(game, mode: str, on: bool, result) -> None:
    """Banner and boat log for a boat-mode toggle (silent/snorkel/bottom)."""
    if result is True:
        _announce(game, "navigation", message(f"uboot.local.{mode}_{'on' if on else 'off'}"))
    else:
        game.flash(message("uboot.local.mode_rejected", reason=message(
            f"uboot.reason.{result}" if result in UBOOT_LOCAL_REASONS
            else "uboot.reason.not_ready")), 2.5)


def _fire_bearing(game, current, range_nm):
    orders = current.orders
    bearing, orders.pending_bearing = orders.pending_bearing, None
    if bearing is None:
        return "not_ready"
    return current.sub.command_fire(bearing, range_nm, now=game.sim_t,
                                    depth_m=orders.torpedo_depth, salvo=orders.salvo)


def _latest_wire(game, current):
    running = {item.id: item for item in game.enemy_torpedoes if item.state == "RUN"}
    active = [key for key, wire in current.orders.wires.items()
              if wire.active and key in running]
    return running[max(active)] if active else None


def _fire_notice(game, result) -> None:
    if result is True:
        # The boat's log gets the torpedo room's own report (tube and all).
        game.flash(message("uboot.local.fired"), 2.0)
    else:
        game.flash(message("uboot.local.fire_rejected",
                           reason=message(f"uboot.reason.{result}")
                           if result in ("not_ready", "no_torpedoes", "reloading",
                                         "out_of_arc", "stale_ref", "unknown_ref",
                                         "uboot_tube_dry",
                                         "uboot_no_wire", "invalid_value",
                                         "uboot_compartment_down", "uboot_no_solution",
                                         "uboot_mast_down", "uboot_no_sighting")
                           else message("uboot.reason.not_ready")), 2.5)


def begin_input(game, mode: str) -> None:
    """Numeric entry for the boat (course, speed, depth, free firing bearing)."""
    current = boat(game)
    game._clear_controls()
    game.input_mode = mode
    game.input_buffer = ""
    sub = current.sub if current is not None else None
    current_value = {
        "uboot_course": f"{sub.order_course:03.0f}" if sub else "---",
        "uboot_speed": f"{sub.order_speed:.1f}" if sub else "---",
        "uboot_depth": f"{sub.order_depth:.0f}" if sub else "---",
        "uboot_bearing": "---",
        "uboot_range": "---",
        "uboot_torpedo_depth": (f"{current.orders.torpedo_depth:.0f}"
                                if current is not None and current.orders.torpedo_depth
                                else "---"),
        "uboot_wire_bearing": "---",
        "uboot_wire_range": "---",
    }[mode]
    prompt = message(f"uboot.input.{mode}", current=current_value)
    game.flash(message("runtime.input.pending", prompt=prompt, value=""), 60.0)


def finish_input(game) -> bool:
    """Apply a pending boat entry; ``False`` keeps the entry open (invalid)."""
    current = boat(game)
    mode = game.input_mode
    if mode == "uboot_range" and not game.input_buffer.strip() and current is not None:
        # No range: the datum goes 10 NM down the bearing (as the web).
        game.input_mode, game.input_buffer = None, ""
        _fire_notice(game, _fire_bearing(game, current, None))
        return True
    try:
        number = float(game.input_buffer.replace(",", "."))
    except ValueError:
        game.flash(message("event.invalid_input"), 2.0)
        return False
    if current is None:
        game.input_mode, game.input_buffer = None, ""
        return True
    sub = current.sub
    orders = current.orders
    if mode in ("uboot_bearing", "uboot_wire_bearing"):
        if not 0.0 <= number < 360.0:
            game.flash(message("runtime.numeric.angle"), 2.0)
            return False
        orders.pending_bearing = number
        begin_input(game, "uboot_range" if mode == "uboot_bearing" else "uboot_wire_range")
        return True
    if mode in ("uboot_range", "uboot_wire_range"):
        if not 0.05 <= number <= 40.0:
            game.flash(message("event.invalid_input"), 2.0)
            return False
        game.input_mode, game.input_buffer = None, ""
        if mode == "uboot_range":
            _fire_notice(game, _fire_bearing(game, current, number))
        else:
            torpedo = next((item for item in game.enemy_torpedoes
                            if item.id == orders.steer_torpedo and item.state == "RUN"), None)
            result = ("uboot_no_wire" if torpedo is None or orders.pending_bearing is None
                      else opfor.wire_steer(current, torpedo, orders.pending_bearing, number))
            if result is True:
                _announce(game, "waffen", message("uboot.local.wire_steered",
                          bearing=f"{orders.pending_bearing:03.0f}", range=f"{number:.1f}"))
            else:
                _fire_notice(game, result)
        return True
    if mode == "uboot_torpedo_depth":
        if not config.UBOOT_TORPEDO_MIN_DEPTH_M <= number <= config.UBOOT_TORPEDO_MAX_DEPTH_M:
            game.flash(message("event.invalid_input"), 2.0)
            return False
        orders.torpedo_depth = number
        game.input_mode, game.input_buffer = None, ""
        _announce(game, "waffen", message("uboot.local.torpedo_depth", depth=f"{number:.0f}"))
        return True
    field = {"uboot_course": "course", "uboot_speed": "speed",
             "uboot_depth": "depth"}[mode]
    result = sub.set_orders(**{field: number})
    if result is not True:
        game.flash(message("event.invalid_input"), 2.0)
        return False
    game.input_mode, game.input_buffer = None, ""
    _announce(game, "navigation",
              message(f"uboot.local.ordered_{field}", value=f"{number:.0f}"))
    return True


def handle_numeric_key(game, key) -> None:
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        finish_input(game)
        return
    if key == pygame.K_ESCAPE:
        game.input_mode, game.input_buffer = None, ""
        game.flash(message("event.input_cancelled"), 1.5)
        return
    if key == pygame.K_BACKSPACE:
        game.input_buffer = game.input_buffer[:-1]
        return
    name = pygame.key.name(key).strip("[]")
    if len(name) == 1 and name.isdigit() and len(game.input_buffer) < 5:
        game.input_buffer += name
    elif (key in (pygame.K_PERIOD, pygame.K_COMMA, pygame.K_KP_PERIOD)
          and game.input_mode == "uboot_speed" and "." not in game.input_buffer):
        game.input_buffer += "."


def _dispatch_sonar(game, current, event) -> None:
    """Run the ordinary sonar key handling on the boat's workstation."""
    with game.sonar_perspective(current.station):
        game._uboot_dispatch = True
        try:
            game._handle_owned_event(event)
        finally:
            game._uboot_dispatch = False


def handle_key(game, event) -> None:
    """Every live-mission key while the uConsole plays the submarine."""
    key = event.key
    mods = getattr(event, "mod", 0)
    current = boat(game)
    game._uboot_ui = True
    try:
        if game.input_mode is not None:
            if game.input_mode in UBOOT_INPUT_MODES:
                handle_numeric_key(game, key)
            elif current is not None:
                with game.sonar_perspective(current.station):
                    game._handle_numeric_input(key)
            else:
                game.input_mode, game.input_buffer = None, ""
            return
        if key == pygame.K_F9:
            game._open_administration("commander")
            return
        if game.commander.confirm_visible(game) and game.commander.handle_confirm_key(game, key):
            return
        if key == pygame.K_ESCAPE:
            game._open_administration("quit")
            return
        if key == pygame.K_F1:
            game._open_administration("help")
            return
        if key == pygame.K_F10:
            game._open_administration("options")
            return
        if key == pygame.K_F2 and mods & pygame.KMOD_SHIFT:
            game.toggle_crew_assist()
            return
        if key in (pygame.K_0, pygame.K_KP0) and current is not None:
            # The boat's weather panel (its own instruments and BT), as on the frigate.
            game._clear_station_input()
            game.pinned_tooltip = None
            game._tooltip_anchor = None
            game.weather_station_open = True
            return
        if key in (pygame.K_s, pygame.K_l) and game.station is not Station.SONAR:
            game._open_administration("save" if key == pygame.K_s else "load")
            return
        if pygame.K_1 <= key <= pygame.K_7 or key == pygame.K_TAB:
            shown = local_station(game)
            if key == pygame.K_TAB:
                step = -1 if mods & pygame.KMOD_SHIFT else 1
                destination = OPFOR_ROLES[(OPFOR_ROLES.index(shown) + step) % len(OPFOR_ROLES)]
            else:
                destination = OPFOR_ROLES[key - pygame.K_1]
            if destination == shown == "uboot_sonar" and current:
                # Its own key again pages the sonar room, as on the frigate.
                _dispatch_sonar(game, current, pygame.event.Event(
                    pygame.KEYDOWN, key=pygame.K_2, mod=0))
                return
            from src.ui import uboot_view
            pages = uboot_view.station_pages(shown)
            if destination == shown and current and len(pages) > 1:
                # A station's own key again pages its panel.
                current.command_page = (current.command_page + 1) % len(pages)
                return
            set_local_station(game, destination)
            return
        if game.game_over:
            if key in (pygame.K_r, pygame.K_m, pygame.K_d):
                game._uboot_dispatch = True
                try:
                    game._handle_owned_event(event)
                finally:
                    game._uboot_dispatch = False
            return
        if current is None or pygame.K_8 <= key <= pygame.K_9:
            return
        if station_remote(game):
            game.flash(message("uboot.local.station_remote",
                               station=message(f"station.{local_station(game)}")), 2.0)
            return
        if game.station is Station.SONAR:
            if key in _SONAR_BLOCKED or (key == pygame.K_b and mods & pygame.KMOD_SHIFT) \
                    or (key == pygame.K_x and current.station.sonar_page in (0, 4)):
                return
            _dispatch_sonar(game, current, event)
            return
        _command_key(game, current, key, mods)
    finally:
        game._uboot_ui = False


def _chart_zoom(game, current, factor, pivot=None) -> None:
    from src.ui import uboot_view
    uboot_view.chart_view(game, current).zoom(factor, pivot=pivot)


def handle_pointer(game, event) -> None:
    """Chart zoom/pan and page tabs of the command page (display only)."""
    current = boat(game)
    if current is None or game.game_over:
        game._uboot_chart_drag = None
        return
    from src.ui import uboot_view
    pos = getattr(event, "pos", None)
    if event.type == pygame.MOUSEWHEEL:
        pointer = uboot_view.chart_pointer(game, pos or pygame.mouse.get_pos())
        if pointer is not None:
            _chart_zoom(game, current, config.MAP_ZOOM_WHEEL_FACTOR ** event.y, pointer)
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        station = uboot_view.station_tab_at(game, pos)
        if station is not None:
            set_local_station(game, station)
            return
        page = uboot_view.page_tab_at(game, pos)
        if page is not None:
            current.command_page = page
            return
        game._uboot_chart_drag = uboot_view.chart_pointer(game, pos)
    elif event.type == pygame.MOUSEMOTION and game._uboot_chart_drag is not None:
        pointer = game._window_to_canvas(pos)
        if pointer is None:
            return
        dx = pointer[0] - game._uboot_chart_drag[0]
        dy = pointer[1] - game._uboot_chart_drag[1]
        if abs(dx) + abs(dy) <= 2:
            return
        current.chart_follow = False
        uboot_view.chart_view(game, current).pan_px(dx, dy)
        game._uboot_chart_drag = pointer
    elif event.type == pygame.MOUSEBUTTONUP:
        game._uboot_chart_drag = None


# Order keys -> the Remote Crew action they are (its allowlist names the stations).
_KEY_ACTIONS = {
    pygame.K_c: "uboot_set_course", pygame.K_v: "uboot_set_speed",
    pygame.K_d: "uboot_set_depth", pygame.K_f: "uboot_fire",
    pygame.K_t: "uboot_fire", pygame.K_y: "uboot_fire", pygame.K_w: "uboot_wire_steer",
    pygame.K_p: "uboot_mast", pygame.K_n: "uboot_snorkel",
    pygame.K_r: "uboot_charge_rate",
    pygame.K_o: "uboot_o2_candle", pygame.K_z: "uboot_trim_auto",
    pygame.K_u: "uboot_set_depth", pygame.K_j: "uboot_set_depth", pygame.K_h: "uboot_set_depth",
    pygame.K_PLUS: "uboot_set_speed", pygame.K_EQUALS: "uboot_set_speed",
    pygame.K_KP_PLUS: "uboot_set_speed", pygame.K_MINUS: "uboot_set_speed",
    pygame.K_KP_MINUS: "uboot_set_speed",
}


def _stadimeter_notice(game, current, result) -> None:
    if result is not True:
        game.flash(message(f"uboot.local.{result}"), 2.0)
        return
    row = opfor.sighting_in_crosshair(current, game.sim_t)
    _announce(game, "sonar", message(
        "uboot.local.stadimeter", cls=display_value("sighting_class", row["cls"]),
        bearing=f"{row['bearing']:03.0f}", range=f"{row['range_nm']:.1f}"), 2.5)


def _esm_number(current):
    from src.ui import uboot_view
    _emitters, chosen = uboot_view.esm_selection(current)
    return None if chosen is None else boat_esm.emitter_number(chosen.track.track_key)


def _esm_notice(game, current, result, what: str) -> None:
    number = _esm_number(current)
    if result is not True or number is None:
        game.flash(message("uboot.local.esm_" + ("full" if result == "active_limit"
                                                  else "none")), 2.0)
        return
    emitter = current.esm.by_number(number)
    if what == "classified":
        name = current.esm.classified(game, emitter)
        game.flash(message("uboot.local.esm_classified", emitter=f"E{number}",
                           name=(game.eloka_emitter_name(emitter.label) or emitter.label)
                           if name is not None else message("uboot.esm.unclassified")), 1.5)
    else:
        _announce(game, "sonar", message("uboot.local.esm_plotted", emitter=f"E{number}"), 1.5)


def _ballast_notice(game, sub, tank, result) -> None:
    if result is not True:
        game.flash(message("uboot.local.ballast_unavailable"), 2.0)
        return
    ballast = sub.ballast
    order = ballast.regulating_order_kg if tank == "regulating" else ballast.trim_order_kg
    _announce(game, "navigation", message(f"uboot.local.ballast_{tank}",
                                          order=f"{order / 1000.0:+.1f}"), 1.5)


def _dc_notice(game, key, result, **values) -> None:
    if result is not True:
        game.flash(message("uboot.local.dc_unavailable"), 2.0)
        return
    _announce(game, "schaden", message(key, **values), 1.5)


# The engine room's damage page: the frigate's crew-page keys (W watch,
# M medical team, U men from the resting watches).
_CREW_PAGE_ACTIONS = {pygame.K_w: "uboot_watch_change", pygame.K_m: "uboot_casualty_medic",
                      pygame.K_u: "uboot_casualty_reassign"}


def _key_action(key, mods, station=None, page=None):
    """The Remote Crew action a key is at this station/page (its allowlist
    decides whether the station may give it), or None."""
    if page == "UBOOT_DAMAGE" and key in _CREW_PAGE_ACTIONS:
        return _CREW_PAGE_ACTIONS[key]
    if key == pygame.K_g:
        # G as on the frigate: action stations; Shift+G lies on the bottom.
        return "uboot_bottom" if mods & pygame.KMOD_SHIFT else "uboot_action_stations"
    if key == pygame.K_a:
        return "uboot_silent"            # A: silent running, the frigate's quiet mode
    if key == pygame.K_o and mods & pygame.KMOD_SHIFT:
        return "uboot_absorber"
    if key == pygame.K_v and station == "uboot_weapons":
        return "uboot_decoy"             # V: the decoy, as at the frigate's weapons
    if key == pygame.K_b and mods & pygame.KMOD_SHIFT:
        return "uboot_blow"
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER) and mods & pygame.KMOD_CTRL:
        return "uboot_fire"
    return _KEY_ACTIONS.get(key)


def _command_key(game, current, key, mods) -> None:
    from src.core.optics import optics_key
    sub = current.sub
    from src.ui import uboot_view
    page = uboot_view.page_name(game, current)
    action = _key_action(key, mods, local_station(game), page)
    if action == "uboot_fire" and page == "UBOOT_SCOPE" and key in (pygame.K_RETURN,
                                                                     pygame.K_KP_ENTER):
        action = "uboot_scope_fire"       # the periscope fires on its solution
    if action is not None and not order_allowed(game, action):
        return
    if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
        pages = uboot_view.station_pages(local_station(game))
        current.command_page = (current.command_page
                                + (-1 if key == pygame.K_PAGEUP else 1)) % len(pages)
    elif page == "UBOOT_SCOPE" and key in (pygame.K_UP, pygame.K_DOWN, pygame.K_q,
                                           pygame.K_e, pygame.K_SPACE):
        # The eyepiece, as the frigate's binoculars: tilt, Q/E low/high power,
        # Space stabilizer (the wheel still zooms the chart).
        optics_key(game, current.scope_optics, key, mods)
    elif page == "UBOOT_SCOPE" and key in (pygame.K_LEFT, pygame.K_RIGHT):
        if order_allowed(game, "uboot_scope_bearing"):
            step = (config.UBOOT_SCOPE_STEP_FAST_DEG if mods & pygame.KMOD_SHIFT
                    else config.UBOOT_SCOPE_STEP_DEG)
            opfor.turn_scope(current, -step if key == pygame.K_LEFT else step)
    elif page == "UBOOT_SCOPE" and key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
            and not mods & pygame.KMOD_CTRL:
        if order_allowed(game, "uboot_scope_mark"):
            _stadimeter_notice(game, current, opfor.stadimeter(game, current))
    elif page == "UBOOT_SCOPE" and key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        # Ctrl+Enter on the periscope: fire on the attack computer's solution.
        if order_allowed(game, "uboot_scope_fire"):
            _fire_notice(game, attack_computer.fire_on_crosshair(game, current))
    elif page == "UBOOT_ESM" and key in (pygame.K_UP, pygame.K_DOWN):
        uboot_view.step_esm_selection(current, 1 if key == pygame.K_DOWN else -1)
    elif page == "UBOOT_ESM" and key in (pygame.K_LEFT, pygame.K_RIGHT):
        if order_allowed(game, "uboot_esm_classify"):
            _esm_notice(game, current, current.esm.cycle_classification(
                game, _esm_number(current), 1 if key == pygame.K_RIGHT else -1), "classified")
    elif page == "UBOOT_ESM" and key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
            and not mods & pygame.KMOD_CTRL:
        if order_allowed(game, "uboot_esm_plot"):
            _esm_notice(game, current, current.esm.to_plot(game, current, _esm_number(current)),
                        "plotted")
    elif page == "UBOOT_RADIO" and key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
            and not mods & pygame.KMOD_CTRL:
        if order_allowed(game, "uboot_radio_send"):
            result = current.radio.send_sitrep(game, current)
            if result is not True:
                game.flash(message("uboot.local.radio_" + (
                    result if result in ("uboot_no_antenna", "uboot_transmitting")
                    else "not_ready")), 2.0)
    elif page == "UBOOT_BALLAST" and key in (pygame.K_UP, pygame.K_DOWN,
                                             pygame.K_LEFT, pygame.K_RIGHT):
        if order_allowed(game, "uboot_ballast"):
            tank = "regulating" if key in (pygame.K_UP, pygame.K_DOWN) else "trim"
            direction = 1 if key in (pygame.K_DOWN, pygame.K_RIGHT) else -1
            _ballast_notice(game, sub, tank, sub.command_ballast(tank, direction))
    elif page == "UBOOT_DAMAGE" and key in (pygame.K_UP, pygame.K_DOWN):
        current.dc_selected = (current.dc_selected + (1 if key == pygame.K_DOWN else -1)) \
            % len(damage_control.COMPARTMENTS)
    elif page == "UBOOT_DAMAGE" and key in (pygame.K_LEFT, pygame.K_RIGHT):
        tasks = damage_control.TASKS
        index = tasks.index(current.dc_task) if current.dc_task in tasks else 0
        current.dc_task = tasks[(index + (1 if key == pygame.K_RIGHT else -1)) % len(tasks)]
    elif page == "UBOOT_DAMAGE" and key in (pygame.K_RETURN, pygame.K_KP_ENTER) \
            and not mods & pygame.KMOD_CTRL:
        if order_allowed(game, "uboot_dc_team"):
            team = 1 if mods & pygame.KMOD_SHIFT else 0
            compartment = damage_control.COMPARTMENTS[current.dc_selected
                                                      % len(damage_control.COMPARTMENTS)]
            _dc_notice(game, "uboot.local.dc_team", sub.command_dc_team(
                team, compartment, current.dc_task), team=team + 1,
                compartment=message(f"uboot.compartment.{compartment}"),
                task=message(f"uboot.dc.task.{current.dc_task}"))
    elif page == "UBOOT_WEAPONS" and key == pygame.K_m:
        quiet = bool(mods & pygame.KMOD_CTRL)
        flood = quiet or bool(mods & pygame.KMOD_SHIFT)
        if order_allowed(game, "uboot_tube_flood" if flood else "uboot_tube_load"):
            result = (sub.command_flood_tube(quiet=quiet) if flood
                      else sub.command_load_tube())
            if result is True:
                _announce(game, "waffen", message(
                    "uboot.local.tube_flooding_quiet" if quiet
                    else "uboot.local.tube_flooding" if flood
                    else "uboot.local.tube_loading"))
            else:
                game.flash(message("uboot.local.tube_rejected", reason=message(
                    f"uboot.reason.{result}" if result in TUBE_REASONS
                    else "uboot.reason.not_ready")), 2.0)
    elif page == "UBOOT_DAMAGE" and key == pygame.K_w:
        if game.boat_change_watch() is not True:
            game.flash(message("crew.watch_blocked"), 2.0)
    elif page == "UBOOT_DAMAGE" and key == pygame.K_m:
        game.boat_casualty_medic()
    elif page == "UBOOT_DAMAGE" and key == pygame.K_u:
        game.boat_casualty_reassign()
    elif key == pygame.K_b and mods & pygame.KMOD_CTRL:
        if order_allowed(game, "uboot_clear_baffles"):
            result = opfor.clear_baffles(game, current)
            if result is not True:
                game.flash(message("uboot.local.baffles_rejected"), 2.0)
    elif key == pygame.K_g and not mods & pygame.KMOD_SHIFT:
        game.boat_set_action_stations(not current.watch.action_stations)
    elif page == "UBOOT_DAMAGE" and key == pygame.K_i:
        if order_allowed(game, "uboot_bulkhead"):
            compartment = damage_control.COMPARTMENTS[current.dc_selected
                                                      % len(damage_control.COMPARTMENTS)]
            index = damage_control.COMPARTMENTS.index(compartment)
            closed = not sub.damage_control.compartments[index].closed
            _dc_notice(game, "uboot.local.dc_bulkhead_" + ("closed" if closed else "open"),
                       sub.command_bulkhead(compartment, closed),
                       compartment=message(f"uboot.compartment.{compartment}"))
    elif key in (pygame.K_q, pygame.K_e):
        uboot_view.chart_view(game, current).step_zoom(
            -1 if key == pygame.K_q else 1, config.MAP_ZOOM_STEPS_NM)
    elif key == pygame.K_k:
        current.chart_follow = not current.chart_follow
        game.flash(message("runtime.map_follow.on" if current.chart_follow
                           else "runtime.map_follow.off"), 1.5)
    elif key == pygame.K_c:
        begin_input(game, "uboot_course")
    elif key == pygame.K_v and action != "uboot_decoy":
        begin_input(game, "uboot_speed")
    elif key == pygame.K_d:
        begin_input(game, "uboot_depth")
    elif key in (pygame.K_u, pygame.K_j, pygame.K_h):
        # One-step depth orders: U periscope (Shift: snorkel depth), J below the
        # measured layer (Shift: above it), H deep (safe depth).
        shift = bool(mods & pygame.KMOD_SHIFT)
        name = {pygame.K_u: "snorkel" if shift else "periscope",
                pygame.K_j: "above_layer" if shift else "below_layer",
                pygame.K_h: "deep"}[key]
        depth = opfor.depth_presets(game, current).get(name)
        if depth is None:
            game.flash(message("uboot.local.preset_unavailable",
                               preset=message(f"uboot.preset.{name}")), 2.0)
        elif sub.set_orders(depth=round(depth)) is True:
            _announce(game, "navigation", message(
                "uboot.local.depth_preset", preset=message(f"uboot.preset.{name}"),
                depth=f"{round(depth):.0f}"), 1.5)
    elif key == pygame.K_f:
        begin_input(game, "uboot_bearing")
    elif key in (pygame.K_UP, pygame.K_DOWN):
        _cycle_contact(game, current, 1 if key == pygame.K_DOWN else -1)
    elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and mods & pygame.KMOD_CTRL:
        contact = selected_contact(game)
        _fire_notice(game, fire_at_contact(game, current, contact)
                     if contact is not None else "unknown_ref")
    elif key == pygame.K_i and page != "UBOOT_DAMAGE":
        if order_allowed(game, "uboot_evade"):
            from src.core import boat_threat
            result = boat_threat.evade(game, current)
            game.flash(message("uboot.local.evade" if result is True
                               else "uboot.local.evade_" + ("no_threat" if result
                                                            == "uboot_no_threat"
                                                            else "unavailable")), 2.0)
    elif action == "uboot_decoy":
        result = sub.command_decoy()
        if result is True:
            _announce(game, "waffen", message("uboot.local.decoy"))
        else:
            game.flash(message("uboot.local.decoy_unavailable"), 2.0)
    elif key == pygame.K_t:
        begin_input(game, "uboot_torpedo_depth")
    elif key == pygame.K_y:
        current.orders.salvo = 2 if current.orders.salvo == 1 else 1
        game.flash(message("uboot.local.salvo", count=current.orders.salvo), 1.5)
    elif key == pygame.K_w:
        torpedo = _latest_wire(game, current)
        if torpedo is None:
            _fire_notice(game, "uboot_no_wire")
        elif mods & pygame.KMOD_SHIFT:
            if opfor.wire_cut(current, torpedo) is True:
                _announce(game, "waffen", message("uboot.local.wire_cut"))
        else:
            current.orders.steer_torpedo = torpedo.id
            begin_input(game, "uboot_wire_bearing")
    elif key == pygame.K_g:
        on = not current.orders.bottomed
        _mode_notice(game, "bottom", on, sub.command_bottom(on))
    elif key == pygame.K_a:
        on = not current.orders.silent
        _mode_notice(game, "silent", on, sub.command_silent(on))
    elif key == pygame.K_p:
        on = not current.orders.mast
        _mode_notice(game, "mast", on, sub.command_mast(on))
    elif key == pygame.K_n:
        on = not sub.snorkeling
        _mode_notice(game, "snorkel", on, sub.command_snorkel(on))
    elif key == pygame.K_r:
        rates = config.UBOOT_CHARGE_RATES
        current_rate = sub.endurance.charge_rate if sub.endurance is not None else rates[0]
        rate = rates[(rates.index(current_rate) + 1) % len(rates)]
        result = sub.command_charge_rate(rate)
        if result is True:
            _announce(game, "navigation", message(
                "uboot.local.charge_rate", rate=message(f"uboot.charge.{rate}")), 1.5)
        else:
            _mode_notice(game, "charge", True, result)
    elif action == "uboot_absorber":
        result = sub.command_absorber()
        if result is True:
            _announce(game, "navigation", message("uboot.local.absorber"), 2.0)
        else:
            _mode_notice(game, "absorber", True, result)
    elif key == pygame.K_z:
        on = not sub.ballast.auto
        _mode_notice(game, "trim_auto", on, sub.command_trim_auto(on))
    elif key == pygame.K_o:
        # Checked after Shift+O (absorber) above: plain O lights a candle.
        result = sub.command_o2_candle()
        if result is True:
            _announce(game, "navigation", message("uboot.local.o2_candle"), 2.0)
        else:
            _mode_notice(game, "o2_candle", True, result)
    elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS,
                 pygame.K_MINUS, pygame.K_KP_MINUS):
        up = key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS)
        if opfor.step_speed(sub, 1 if up else -1) is True:
            _announce(game, "navigation", message(
                "uboot.local.speed_ordered", speed=f"{sub.order_speed:.1f}"), 1.5)
    elif key == pygame.K_b and mods & pygame.KMOD_SHIFT:
        result = sub.command_blow()
        if result is True:
            _announce(game, "navigation", message("uboot.local.blow"), 2.5)
        else:
            game.flash(message("uboot.local.blow_no_air" if result == "uboot_no_hp_air"
                               else "uboot.local.blow_unavailable"), 2.5)
