"""The crewed boat's counter-detection picture and its evasion order.

Everything here is built from what the boat itself measures: intercepted
pings (bearing, received level, source type told apart by frequency),
torpedo and buoy-splash bearings from its sonar room, its ESM picture, its
own BT-measured layer and its own speed and noise.  No hostile position,
identity or sensor state is read.  The picture is display only; the
evasion order is an ordinary set of crew orders (course, speed, depth,
silent running, decoy) sent through the same checks as the single keys.
"""

from __future__ import annotations

import math

from src.core import boat_nav, config, detrand
from src.core.opfor import depth_presets, measured_layer_m

KINDS = ("hull", "dipping", "buoy", "splash", "torpedo")
ALARM_S = 120.0          # an alarm this fresh drives the evasion order


def record_splash(game, x: float, y: float, seq: int) -> None:
    """A buoy entering the water near the crewed boat is heard as a splash."""
    boat = getattr(game, "_opfor", None)
    if boat is None:
        return
    sub = boat.sub
    if sub.sunk or boat.sonar_down():
        return
    if math.hypot(x - sub.x, y - sub.y) > config.UBOOT_SPLASH_HEAR_NM:
        return
    if (hasattr(game.world, "sonar_path_blocked")
            and game.world.sonar_path_blocked(x, y, 1.0, sub.x, sub.y, sub.depth)):
        return
    true = math.degrees(math.atan2(x - sub.x, -(y - sub.y)))
    bearing = (true + config.UBOOT_SPLASH_SIGMA_DEG * detrand.normal(
        sub.sensor_seed, "buoy-splash", int(seq))) % 360.0
    boat.orders.intercept("splash", bearing, None)
    boat.orders.event("buoy_splash", bearing=f"{bearing:03.0f}")


def layer_state(boat):
    layer = measured_layer_m(boat)
    if layer is None:
        return "unknown", None
    depth = boat.sub.depth
    if abs(depth - layer) < 5.0:
        return "in", layer
    return ("below" if depth > layer else "above"), layer


def picture(game, boat) -> dict:
    """Detached counter-detection summary for the displays (no truth)."""
    sub, orders = boat.sub, boat.orders
    now = game.sim_t
    window = config.UBOOT_THREAT_WINDOW_S
    rows = [dict(row, age_s=max(0.0, now - row["t"])) for row in boat.intercepts
            if 0.0 <= now - row["t"] <= window]
    rows.reverse()
    counts = {kind: sum(1 for row in rows if row["kind"] == kind) for kind in KINDS}
    pings = [row for row in rows if row["kind"] in ("hull", "dipping", "buoy")]
    loudest = max((row["level_db"] for row in pings), default=None)
    # Trend of the last two pings of the newest ping's kind: closing in?
    trend = None
    if pings:
        same = [row for row in pings if row["kind"] == pings[0]["kind"]][:2]
        if len(same) == 2:
            delta = same[0]["level_db"] - same[1]["level_db"]
            trend = "rising" if delta > 1.5 else "falling" if delta < -1.5 else "steady"
    layer, layer_m = layer_state(boat)
    quiet = orders.quiet_active(sub)
    noise = ("cavitating" if sub.cavitating else "snorkel" if sub.snorkeling
             else "quiet" if quiet else "loud" if sub.speed > 8.0 else "moderate")
    return dict(
        intercepts=[dict(kind=row["kind"], bearing=round(row["bearing"], 1),
                         level_db=(None if row["level_db"] is None
                                   else round(row["level_db"], 1)),
                         age_s=round(row["age_s"], 1)) for row in rows[:12]],
        counts=counts, loudest_db=None if loudest is None else round(loudest, 1),
        echo_likely=loudest is not None and loudest >= config.UBOOT_PING_ECHO_LIKELY_DB,
        trend=trend, layer=layer, layer_m=None if layer_m is None else round(layer_m, 1),
        depth_m=round(float(sub.depth), 1), noise=noise, mast=bool(orders.mast),
        esm_count=len(orders.esm), advice=advice(game, boat, layer, noise),
        # The crew's rough clock of the nearest seeker locked on (by ear).
        clock=(None if getattr(boat, "seeker_clock", None) is None else dict(
            bearing=round(boat.seeker_clock["bearing"] % 360.0, 1),
            tti_s=round(boat.seeker_clock["tti_s"]))))


def advice(game, boat, layer: str, noise: str) -> list[str]:
    """Short crew recommendations (catalog keys), most urgent first."""
    sub, orders = boat.sub, boat.orders
    keys = []
    source = alarm_source(boat)
    if source is not None and source[0] == "torpedo":
        keys.append("uboot.advice.torpedo")
    if orders.mast and (orders.esm or source is not None):
        keys.append("uboot.advice.mast_down")
    if source is not None and noise in ("cavitating", "loud", "snorkel"):
        keys.append("uboot.advice.slow_down")
    if layer == "unknown":
        keys.append("uboot.advice.measure_layer")
    elif source is not None and layer != "below":
        keys.append("uboot.advice.go_below")
    if source is not None and source[0] != "torpedo":
        keys.append("uboot.advice.evade")
    return keys[:4]


def alarm_source(boat):
    """``(kind, bearing)`` of the freshest alarm that calls for evasion."""
    sub, orders = boat.sub, boat.orders
    torpedo_age = sub.memory["last_torpedo_age"]
    if (orders.torpedo_bearing is not None and math.isfinite(torpedo_age)
            and torpedo_age < ALARM_S):
        return "torpedo", float(orders.torpedo_bearing)
    ping_age = sub.memory["last_ping_age"]
    if (orders.ping_bearing is not None and math.isfinite(ping_age)
            and ping_age < ALARM_S):
        return "ping", float(orders.ping_bearing)
    return None


def evasion_plan(game, boat):
    """The evasion order for the freshest alarm, or ``None`` without one.

    Torpedo: put it on the quarter (bearing +/-150, the smaller turn), run at
    full speed, cross the measured layer (else go deep) and drop a decoy.
    Active sonar: turn the stern to the pinger (smallest echo), slow to
    silent running and cross the layer (else go deep).
    """
    source = alarm_source(boat)
    if source is None:
        return None
    kind, bearing = source
    sub = boat.sub
    if kind == "torpedo":
        options = ((bearing + 150.0) % 360.0, (bearing - 150.0) % 360.0)
        course = min(options, key=lambda value: abs(config.angle_diff_deg(value, sub.course)))
        speed = float(sub.motion.maximum_speed_kn)
    else:
        course = (bearing + 180.0) % 360.0
        speed = min(3.0, float(config.UBOOT_SILENT_MAX_KN), float(sub.motion.maximum_speed_kn))
    presets = depth_presets(game, boat)
    layer, _layer_m = layer_state(boat)
    depth = (presets["below_layer"] if layer in ("above", "in") else
             presets["above_layer"] if layer == "below" else None)
    if depth is None:
        depth = presets["deep"]
    depth = min(float(depth), float(sub.stype.max_depth_m))
    return dict(kind=kind, bearing=bearing, course=round(course % 360.0, 1),
                speed_kn=round(speed, 1), depth_m=round(max(0.0, depth), 1),
                silent=kind != "torpedo", decoy=kind == "torpedo")


def evade(game, boat):
    """Give the evasion order; True, or the reason it cannot be given."""
    sub = boat.sub
    if not sub._crew_ready():
        return "not_ready"
    plan = evasion_plan(game, boat)
    if plan is None:
        return "uboot_no_threat"
    if boat.orders.bottomed:
        sub.command_bottom(False)
    boat_nav.cancel_on_helm(boat)
    sub.command_silent(plan["silent"])
    result = sub.set_orders(course=plan["course"] % 360.0, speed=plan["speed_kn"],
                            depth=plan["depth_m"])
    if result is not True:
        return result
    decoy = sub.command_decoy() is True if plan["decoy"] else False
    boat.evaded_t = game.sim_t
    boat.orders.event("evade_decoy" if decoy else "evade", course=f"{plan['course']:03.0f}",
                      depth=f"{plan['depth_m']:.0f}")
    return True
