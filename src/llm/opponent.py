"""Experimental opponent advisor: the model picks the AI side's plan.

Off by default and never scored.  Every few minutes of mission time the
model gets the AI side's own picture (what the AI boats or the AI hunters
know, never the player's hidden state) and picks one plan from a fixed list.
The plan only biases the built-in AI where it is free to choose: an AI
boat's patrol leg (its evasion, lying in wait and attacks keep priority), or
the hunters' speed.  The model never steers, aims or fires.

Because the answer arrives on wall time, a mission with this mode is not
reproducible from its seed alone.  The chosen plan is part of the save, so a
loaded mission continues with it.  Such a mission is marked "experimental" in
the logbook and earns no best score or award.  It never runs in the
campaign, lessons, the daily mission or two-crew (PvP) play.
"""

from __future__ import annotations

import math

from src.llm import facts, prompts
from src.llm.client import clean_text, parse_json_object

INTERVAL_S = 180.0                 # mission time between two plan requests
SUB_PLANS = {
    "default": "keep the built-in behaviour",
    "deep_hide": "go deep below the layer and creep at 3 kn, holding course",
    "close_in": "close the frigate's last heard bearing below the layer at 6 kn",
    "slip_away": "turn away from the frigate's bearing and open the range deep at 7 kn",
    "lie_still": "hover just below the layer at bare steerage way and listen",
}
HUNTER_PLANS = {
    "default": "keep the built-in behaviour",
    "sprint_drift": "alternate 4 minutes at 22 kn with 4 minutes at 6 kn listening",
    "quiet_search": "search at no more than 8 kn to hear better",
    "fast_search": "search at least at 16 kn to cover ground",
}
SPRINT_KN, DRIFT_KN, SPRINT_LEG_S = 22.0, 6.0, 240.0
QUIET_KN, FAST_KN = 8.0, 16.0
WHY_MAX = 200


def plans_for(side: str) -> dict:
    """The plan list of the AI side ("subs" or "hunter")."""
    return SUB_PLANS if side == "subs" else HUNTER_PLANS


def valid_plan(side: str, plan) -> bool:
    return type(plan) is str and plan in plans_for(side)


def parse(side: str, text: str):
    """(plan, why) from the model's answer, or None."""
    payload = parse_json_object(text)
    if payload is None or not valid_plan(side, payload.get("plan")):
        return None
    return payload["plan"], clean_text(payload.get("why", ""), WHY_MAX)


def sub_facts(game) -> str:
    """What the AI boats themselves know (their own memory, never truth)."""
    lines = [f"Mission time: {int(game.sim_t // 60)} min"]
    for sub in game.subs:
        if sub.sunk or sub.manual or getattr(sub, "side", "hostile") != "hostile":
            continue
        thermo = game.world.thermocline_depth_m(sub.x, sub.y)
        memory = sub.memory
        heard = memory.get("contact_bearing")
        ping = memory.get("last_ping_age", math.inf)
        torpedo = memory.get("last_torpedo_age", math.inf)
        lines.append(
            f"Boat {int(sub.id)}: depth {sub.depth:.0f} m (layer {thermo:.0f} m), "
            f"{sub.speed:.0f} kn, damage {sub.damage:.0f} %, torpedoes {sub.torpedoes_left}, "
            + (f"frigate heard on bearing {heard:03.0f}" if heard is not None
               else "frigate not heard")
            + (f", pinged {ping:.0f} s ago" if ping < 900 else "")
            + (f", torpedo heard {torpedo:.0f} s ago" if torpedo < 900 else ""))
    return "\n".join(lines)


def hunter_facts(game) -> str:
    """The frigate's own picture, which the AI hunters work from."""
    return facts.situation(game, "frigate")


def request(service, side: str, game):
    """Submit one plan request; None when the link is off or busy."""
    plans = plans_for(side)
    listing = "\n".join(f"- {name}: {text}" for name, text in plans.items())
    picture = sub_facts(game) if side == "subs" else hunter_facts(game)
    who = "uboot" if side == "subs" else "frigate"
    return service.submit("opfor", prompts.opfor(who, picture, listing), max_tokens=120,
                          temperature=0.4, json_mode=True)


def sub_orders(game, sub, plan: str):
    """(course, speed, depth) of an AI boat's patrol leg under the plan, or None."""
    if plan == "default" or sub.manual or sub.sunk:
        return None
    thermo = game.world.thermocline_depth_m(sub.x, sub.y)
    deepest = sub.stype.max_depth_m * 0.8
    bearing = sub.memory.get("contact_bearing")
    if plan == "deep_hide":
        return sub.target_course, 3.0, min(deepest, thermo + 40.0)
    if plan == "lie_still":
        return sub.course, 1.5, min(deepest, thermo + 15.0)
    if bearing is None:
        return None
    if plan == "close_in":
        return _clear(game, sub, bearing), 6.0, min(deepest, thermo + 20.0)
    if plan == "slip_away":
        return _clear(game, sub, (bearing + 180.0) % 360.0), 7.0, min(deepest, thermo + 40.0)
    return None


def _clear(game, sub, course: float) -> float:
    from src.core import boat_ai
    return boat_ai._course(game, sub, course)


def hunter_speed(game, plan: str, speed: float) -> float:
    """The hunters' ordered speed under the plan."""
    if plan == "sprint_drift":
        return SPRINT_KN if math.floor(game.sim_t / SPRINT_LEG_S) % 2 == 0 else DRIFT_KN
    if plan == "quiet_search":
        return min(speed, QUIET_KN)
    if plan == "fast_search":
        return max(speed, FAST_KN)
    return speed


def valid_state(value) -> bool:
    """The saved ``llm_opfor`` block: None, or the plan in force."""
    if value is None:
        return True
    return (isinstance(value, dict) and set(value) == {"side", "plan", "since"}
            and value["side"] in ("subs", "hunter") and valid_plan(value["side"], value["plan"])
            and type(value["since"]) in (int, float) and math.isfinite(value["since"])
            and value["since"] >= 0.0)

