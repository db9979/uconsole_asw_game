"""The built-in opponent picks a plan by itself (no language model needed).

The plan lists of the experimental opponent (``src/llm/opponent.py``) are
also the built-in AI's own tactics: every free AI submarine and the AI
hunter frigate pick one from rules over their own picture, their
commander's character (``commander_traits``) and the player's habits the
enemy learnt from the service record (``src/core/habits.py``).  A plan only biases the AI
where it is free to choose, exactly like the model's plan: an AI boat's
patrol leg (evasion, lying in wait and attacks keep priority) and the
hunters' search speed.  A plan the language model chose wins over the rules.

Stateless apart from the habits decided once per mission (save ``habits``):
each choice derives from the boat's saved memory (ping, torpedo
and contact ages, last heard bearing), its damage and torpedoes, the seed
and the simulation time, so nothing is saved and a loaded game continues
identically.  Observation boundary: an AI boat decides from what it heard
itself, the hunter from the frigate's own picture, never from truth.
"""

from __future__ import annotations

from src.core import commander_traits

# A ping this recent (s) still drives the boat deep.
PINGED_S = 600.0
# From this damage (%) a boat that hears the frigate opens the range.
DAMAGED_PCT = 40.0
# A daring or stubborn hunter that has searched this long (s) without a
# datum changes to sprint and drift.
LONG_SEARCH_S = 1200.0

# The patrol plan of each submarine commander while the frigate is heard
# (and the boat was not pinged lately).
HEARD_PLAN = {"daring": "close_in", "hunter": "close_in", "fox": "lie_still",
              "cautious": "default"}
# After a ping: the cautious and the fox go deep and creep; the daring and the
# stubborn hover under the layer and listen for the frigate's next move.
PINGED_PLAN = {"daring": "lie_still", "hunter": "lie_still", "fox": "deep_hide",
               "cautious": "deep_hide"}
# The hunter captain's search plan without a datum.
SEARCH_PLAN = {"daring": "fast_search", "hunter": "sprint_drift", "fox": "quiet_search",
               "cautious": "default"}


def sub_plan(sub, habits: tuple = ()) -> str:
    """The plan of one free AI submarine (a key of ``opponent.SUB_PLANS``);
    ``habits`` are the frigate player's habits the enemy knows."""
    memory = sub.memory
    kind = commander_traits.sub_kind(sub)
    # The frigate is heard while the boat keeps a bearing: it drops the bearing
    # once its contact is SUB_EVADE_DURATION_S old (the age never gets older).
    heard = memory.get("contact_bearing") is not None and "contact_age" in memory
    if heard and sub.damage >= DAMAGED_PCT:
        return "slip_away"
    if memory.get("last_ping_age", float("inf")) <= PINGED_S:
        # An early pinger pings again: every commander goes deep.
        return "deep_hide" if "early_ping" in habits else PINGED_PLAN[kind]
    if not heard:
        return "default"
    plan = HEARD_PLAN[kind]
    if plan == "close_in" and sub.torpedoes_left <= 0:
        return "slip_away"
    if plan == "close_in" and "long_shots" in habits:
        # Closing only brings it into the frigate's long shots: creep deep.
        return "deep_hide"
    if plan != "lie_still" and ("early_ping" in habits
                                or ("fast_search" in habits and kind != "daring")):
        # Under the layer before the ping comes, or in wait for the loud frigate.
        return "lie_still"
    return plan


def hunter_plan(game, habits: tuple = ()) -> str:
    """The AI hunter frigate's search plan while it has no datum;
    ``habits`` are the submarine player's habits the enemy knows."""
    if "fast_transit" in habits:
        return "quiet_search"
    if "mast_up" in habits or "shallow" in habits:
        return "sprint_drift"
    plan = SEARCH_PLAN[commander_traits.hunter_kind(game.seed)]
    if plan == "fast_search" and game.sim_t >= LONG_SEARCH_S:
        return "sprint_drift"
    return plan


def known_habits(game, side: str) -> tuple:
    """The habits of ``side`` the enemy knows in this mission (``game_habits``)."""
    known = getattr(game, "enemy_known_habits", None)
    return known(side) if known is not None else ()
