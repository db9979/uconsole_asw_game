"""The uConsole playing the hostile submarine (``--play-sub`` / menu ``U``).

The frigate then belongs to the Remote Crew browsers (or to its autocrew);
the local screen, keys and sound serve only the crewed boat.  Two local
views exist: the submarine command (``Station.BRIDGE`` slot) and the
submarine sonar (``Station.SONAR`` slot, the ordinary sonar workstation
drawn and operated inside ``Game.sonar_perspective``).

Nothing here reads frigate truth for display: the boat, the known chart and
the boat's own sonar contacts only.  Frigate flashes, its event feed and its
local sound cues are withheld while this side is played.
"""

import math

import pygame

from src.core import config, opfor
from src.core.i18n import message
from src.core.station import Station

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
# Rejections of boat-mode orders that have their own local text.
UBOOT_LOCAL_REASONS = ("not_ready", "uboot_too_deep", "uboot_no_snorkel", "uboot_mast_depth")


def playing(game) -> bool:
    return getattr(game, "local_side", "frigate") == "uboot"


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
    bearing = (contact.passive_bearing if contact.passive_bearing is not None
               else contact.bearing)
    range_nm = course = speed = None
    if (contact.observed_x is not None and contact.observed_y is not None
            and contact.range_source in ("ping", "tma")
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
        _announce(game, "waffen", message("uboot.local.fired"))
    else:
        game.flash(message("uboot.local.fire_rejected",
                           reason=message(f"uboot.reason.{result}")
                           if result in ("not_ready", "no_torpedoes", "reloading",
                                         "out_of_arc", "stale_ref", "unknown_ref",
                                         "uboot_no_wire", "invalid_value")
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
        if key in (pygame.K_s, pygame.K_l) and game.station is not Station.SONAR:
            game._open_administration("save" if key == pygame.K_s else "load")
            return
        if key in (pygame.K_1, pygame.K_2, pygame.K_TAB):
            destination = (Station.BRIDGE if key == pygame.K_1 else Station.SONAR
                           if key == pygame.K_2 else
                           Station.SONAR if game.station is not Station.SONAR
                           else Station.BRIDGE)
            game._clear_controls()
            if destination is game.station and destination is Station.SONAR and current:
                _dispatch_sonar(game, current, pygame.event.Event(
                    pygame.KEYDOWN, key=pygame.K_2, mod=0))
            game.station = destination
            return
        if game.game_over:
            if key in (pygame.K_r, pygame.K_m):
                game._uboot_dispatch = True
                try:
                    game._handle_owned_event(event)
                finally:
                    game._uboot_dispatch = False
            return
        if current is None or pygame.K_3 <= key <= pygame.K_9:
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


def _command_key(game, current, key, mods) -> None:
    sub = current.sub
    if key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
        current.command_page = (current.command_page
                                + (-1 if key == pygame.K_PAGEUP else 1)) % 2
    elif key in (pygame.K_q, pygame.K_e):
        _chart_zoom(game, current, (1.0 / config.MAP_ZOOM_WHEEL_FACTOR
                                    if key == pygame.K_q else config.MAP_ZOOM_WHEEL_FACTOR))
    elif key == pygame.K_k:
        current.chart_follow = not current.chart_follow
        game.flash(message("runtime.map_follow.on" if current.chart_follow
                           else "runtime.map_follow.off"), 1.5)
    elif key == pygame.K_c:
        begin_input(game, "uboot_course")
    elif key == pygame.K_v:
        begin_input(game, "uboot_speed")
    elif key == pygame.K_d:
        begin_input(game, "uboot_depth")
    elif key == pygame.K_f:
        begin_input(game, "uboot_bearing")
    elif key in (pygame.K_UP, pygame.K_DOWN):
        _cycle_contact(game, current, 1 if key == pygame.K_DOWN else -1)
    elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and mods & pygame.KMOD_CTRL:
        contact = selected_contact(game)
        _fire_notice(game, fire_at_contact(game, current, contact)
                     if contact is not None else "unknown_ref")
    elif key == pygame.K_x:
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
        bottom = bool(mods & pygame.KMOD_SHIFT)
        orders = current.orders
        on = not (orders.bottomed if bottom else orders.silent)
        result = sub.command_bottom(on) if bottom else sub.command_silent(on)
        _mode_notice(game, ("bottom" if bottom else "silent"), on, result)
    elif key == pygame.K_p:
        on = not current.orders.mast
        _mode_notice(game, "mast", on, sub.command_mast(on))
    elif key == pygame.K_n:
        on = not sub.snorkeling
        _mode_notice(game, "snorkel", on, sub.command_snorkel(on))
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
            game.flash(message("uboot.local.blow_unavailable"), 2.5)
