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
    if e.type == pygame.MOUSEWHEEL:
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
    if button == 3:
        if layer == "station":
            return False
        game.handle_event(key_event(pygame.K_ESCAPE))
        return True
    if button != 1:
        return False
    canvas = game._window_to_canvas(getattr(e, "pos", None))
    target = pointer.hit(canvas, layer)
    if target is None:
        return False
    if target.action is not None:
        target.action(canvas)
        return True
    game.handle_event(key_event(target.key, target.mod))
    # Held like the key until the button is let go (steering, telegraph).
    game._pointer_held = (target.key, target.mod)
    return True


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
