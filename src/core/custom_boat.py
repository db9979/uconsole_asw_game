"""Custom missions the player sails as the submarine (editor field ``side``).

A mission authored with ``side: "uboot"`` names one placed hostile submarine
(``boat_id``) as the player's boat; the AI hunters crew the frigate. The
objective then belongs to the boat: ``survive`` (stay afloat to the time
limit), ``reach`` (bring the boat inside the point's radius) or ``sink``
(sink every target unit, and every member of a target group). The result is
kept from the frigate's side like every boat mission: the boat winning is a
frigate loss (``_end_mission(False, ...)``). A frigate sunk ends the mission
as a boat victory before this module is asked.

Adjudication reads the boat's and the targets' true state like every other
end check; the boat's objective line reads only own truth and the authored
mission (its own position, the authored point, the targets HQ named).
"""

from __future__ import annotations

import math

from src.core.i18n import message
from src.core.mission_definition import mission_side

# Outcome of ``boat_debrief.outcome`` for a held-out survive mission.
HELD_OUT_REASON = "end.reason.boat_held_out"


def definition(game):
    """The running custom mission when the player sails its submarine, else None."""
    value = getattr(game, "custom_mission_definition", None)
    return value if value is not None and mission_side(value) == "uboot" else None


def boat(game):
    """The mission's own submarine (``boat_id``) while it is in the water."""
    authored = definition(game)
    if authored is None:
        return None
    entity = game.mission_entity(authored.get("boat_id", ""))
    return entity if entity is not None and entity in game.subs else None


def _target_entities(game, authored) -> list:
    """(id, entity or None) of every target: units and placed group members."""
    groups = {group["id"] for group in authored["units"]["random_groups"]}
    rows = []
    for target in authored["objective"]["target_ids"]:
        if target in groups:
            prefix = f"{target}:"
            rows.extend((key, game.mission_entity(key))
                        for key in sorted(game.mission_units) if key.startswith(prefix))
        else:
            rows.append((target, game.mission_entity(target)))
    return rows


def _gone(entity) -> bool:
    return (entity is None or getattr(entity, "sunk", False)
            or getattr(entity, "dead", False)
            or getattr(entity, "state", "") in ("SINKING", "SUNK"))


def targets_sunk(game) -> tuple[int, int]:
    """(sunk, total) of the boat's sink targets placed so far."""
    authored = definition(game)
    if authored is None:
        return 0, 0
    rows = _target_entities(game, authored)
    return sum(1 for _key, entity in rows if _gone(entity)), len(rows)


def check(game) -> bool:
    """End a submarine custom mission when it is decided; True when it owns it."""
    authored = definition(game)
    if authored is None:
        return False
    sub = boat(game)
    if sub is None or sub.sunk or sub.state == "SINKING":
        game._end_mission(True, message("end.reason.targets_sunk"))
        return True
    objective = authored["objective"]
    kind = objective["type"]
    limit = float(objective["time_limit_s"])
    if kind == "reach":
        point = objective["reach"]
        if math.hypot(sub.x - float(point["x"]), sub.y - float(point["y"])) \
                <= float(point["radius_nm"]):
            game._end_mission(False, message("end.reason.boat_point_reached"))
            return True
    elif kind == "sink":
        sunk, total = targets_sunk(game)
        # A target group not spawned yet is still to come.
        pending = any(event["type"] == "spawn" and event["id"] in game.mission_events_pending
                      and event["target_id"] in objective["target_ids"]
                      for event in authored["events"])
        if total and sunk >= total and not pending:
            game._end_mission(False, message("end.reason.boat_targets_sunk"))
            return True
    if game.mission_time >= limit:
        if kind == "survive":
            game._end_mission(False, message(HELD_OUT_REASON))
        else:
            game._end_mission(True, message("end.reason.time_limit"))
    return True


def objective(game, sub):
    """The boat's mission line for a submarine custom mission (own truth only)."""
    authored = definition(game)
    if authored is None:
        return None
    objective_spec = authored["objective"]
    kind = objective_spec["type"]
    left = max(0.0, float(objective_spec["time_limit_s"]) - float(game.mission_time))
    left_text = f"{int(left // 3600)}:{int(left % 3600 // 60):02d}"
    if kind == "reach":
        point = objective_spec["reach"]
        dx, dy = float(point["x"]) - sub.x, float(point["y"]) - sub.y
        return message("uboot.objective.custom_reach",
                       bearing=f"{math.degrees(math.atan2(dx, -dy)) % 360.0:03.0f}",
                       range=f"{math.hypot(dx, dy):.1f}", left=left_text)
    if kind == "sink":
        sunk, total = targets_sunk(game)
        return message("uboot.objective.custom_sink", sunk=sunk, total=total, left=left_text)
    return message("uboot.objective.custom_survive", left=left_text)
