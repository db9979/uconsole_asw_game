"""Full mouse control: clicks on the targets of the last frame (src/ui/pointer.py).

A key target hands the click to the normal keyboard path as that key's
press (and its release when the button is let go), so the mouse obeys the
same input ownership, station checks, confirmations and feedback as the
keyboard.  Dials and menu rows use small UI actions that end in the same
orders a typed entry or a selected row would give.  A right click cancels
like ``Esc`` wherever a menu, dialog, numeric entry or the mission end owns
input.  Nothing here touches the simulation directly.
"""

from __future__ import annotations

import pygame

from src.ui import pointer

# Printable keys carry their character, as a real key press would.
_UNICODE = {pygame.K_COMMA: ",", pygame.K_PERIOD: ".", pygame.K_PLUS: "+",
            pygame.K_MINUS: "-", pygame.K_SPACE: " "}


def owner(game) -> str:
    """The pointer layer that owns input now (mirrors ``handle_event``)."""
    if game.administration_open:
        return "overlay"
    if game.in_menu:
        return "menu"
    if game.game_over:
        return "end"
    if game.input_mode is not None:
        return "input"
    if getattr(game, "game_menu_open", False):
        return "popup"      # the top bar's game menu (src/ui/game_menu.py)
    return "station"


def key_event(key: int, mod: int = 0, down: bool = True) -> pygame.event.Event:
    char = _UNICODE.get(key, "")
    if not char and pygame.K_a <= key <= pygame.K_z:
        char = chr(key).upper() if mod & pygame.KMOD_SHIFT else chr(key)
    elif not char and pygame.K_0 <= key <= pygame.K_9:
        char = chr(key)
    return pygame.event.Event(pygame.KEYDOWN if down else pygame.KEYUP,
                              key=key, mod=mod, unicode=char, scancode=0)


def handle(game, e) -> bool:
    """Route a mouse button event to a pointer target; True if consumed."""
    if e.type == pygame.MOUSEBUTTONUP and getattr(e, "button", 0) == 1:
        held = getattr(game, "_pointer_held", None)
        if held is None:
            return False
        game._pointer_held = None
        game.handle_event(key_event(held[0], held[1], down=False))
        return True
    layer = owner(game)
    if layer == "popup":
        return _handle_popup(game, e)
    if e.type == pygame.MOUSEWHEEL:
        if layer == "station" and getattr(e, "y", 0):
            # A station's long list scrolls under the pointer.
            region = pointer.scroll_at(game._window_to_canvas(pygame.mouse.get_pos()),
                                       "station")
            if region is None:
                return False
            keys = pointer.legend_keys(region[0] if e.y > 0 else region[1])
            if not keys:
                return False
            for _ in range(min(3, abs(int(e.y)))):
                game.handle_event(key_event(*keys[0]))
            return True
        # Menus and dialogs: the wheel steps the selection or scrolls.
        if layer not in ("menu", "overlay") or not getattr(e, "y", 0):
            return False
        if layer == "menu" and getattr(game, "editor", None) is not None:
            return False
        key = pygame.K_UP if e.y > 0 else pygame.K_DOWN
        for _ in range(min(3, abs(int(e.y))) * (3 if game.help_open else 1)):
            game.handle_event(key_event(key))
        return True
    if e.type != pygame.MOUSEBUTTONDOWN:
        return False
    button = getattr(e, "button", 0)
    canvas = game._window_to_canvas(getattr(e, "pos", None))
    if button != 1 and pointer.blocked(canvas, layer):
        return True       # a panel over the station (F11 log) keeps every click
    if button == 3:
        if layer == "station":
            return False
        game.handle_event(key_event(pygame.K_ESCAPE))
        return True
    if button != 1:
        return False
    if layer == "station" and _over_crew_message(game, canvas):
        return False      # the crew message box lies above every station target
    target = pointer.hit(canvas, layer)
    if target is None or target.hover_only:
        return False
    if target.action is not None:
        target.action(canvas)
        return True
    game.handle_event(key_event(target.key, target.mod))
    # Held like the key until the button is let go (steering, telegraph).
    game._pointer_held = (target.key, target.mod)
    return True


def _handle_popup(game, e) -> bool:
    """The open game menu owns the pointer: a row runs its action, any other
    click (or a right click) only closes the menu."""
    if e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 0) == 1:
        target = pointer.hit(game._window_to_canvas(getattr(e, "pos", None)), "popup")
        if target is not None and target.action is not None:
            target.action(game._window_to_canvas(e.pos))
            return True
    if e.type == pygame.MOUSEBUTTONDOWN:
        game.game_menu_open = False
    return True


def _over_crew_message(game, canvas) -> bool:
    commander = getattr(game, "commander", None)
    if canvas is None or commander is None or not commander.confirm_visible(game):
        return False
    return bool(commander.confirm_rect().collidepoint(canvas))


def enter_value(game, mode: str, value) -> None:
    """Order ``value`` exactly as if it had been typed into ``mode``'s entry."""
    if value is None:
        return
    text = f"{value:g}" if isinstance(value, float) else str(value)
    from src.core import uboot_local
    if mode in uboot_local.UBOOT_INPUT_MODES:
        uboot_local.begin_input(game, mode)
        game.input_buffer = text
        uboot_local.finish_input(game)
        return
    game._begin_numeric_input(mode)
    game.input_buffer = text
    game._finish_numeric_input()


def press(game, key: int, mod: int = 0, times: int = 1) -> None:
    """Press and release ``key`` ``times`` times through the keyboard path
    (a click that stands for several key steps, such as a telegraph row)."""
    for _ in range(max(0, int(times))):
        game.handle_event(key_event(key, mod))
        game.handle_event(key_event(key, mod, down=False))
