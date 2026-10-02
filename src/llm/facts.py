"""What the language model may know: the picture one side's crew has.

Every line here comes from the same observations the stations show: own
ship or own boat (legitimate truth), published tracks and contacts with
their age, the crew's own annotations, the event feed, HQ traffic and the
mission order.  Never a hidden entity, a true class or a true position.
The text is plain and compact so a small local model copes with it.
"""

from __future__ import annotations

import math

from src.core import config
from src.core.i18n import localize

MAX_TRACKS = 14
MAX_FEED = 10
MAX_LINES = 60


def _bearing_range(ox, oy, x, y):
    dx, dy = x - ox, y - oy
    return math.degrees(math.atan2(dx, -dy)) % 360.0, math.hypot(dx, dy)


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:d}:{seconds % 3600 // 60:02d}"


def _text(game, value) -> str:
    try:
        return " ".join(localize(value, game.tr).split())
    except Exception:  # noqa: BLE001 - a fact line must never break the game
        return ""


def side_of(game) -> str:
    return "uboot" if getattr(game, "local_side", "frigate") == "uboot" else "frigate"


def mission_lines(game, side: str = "frigate") -> list:
    objective = game.mission_objective_display()
    boat = getattr(game, "opfor", None)
    if side == "uboot" and boat is not None:
        from src.core import boat_missions
        objective = boat_missions.objective(game, boat)
    lines = [f"Mission: {_text(game, game.mission_name_display())}",
             f"Objective: {_text(game, objective)}"]
    mission = getattr(game, "mission", None)
    if mission is not None and not getattr(mission, "open_ended", False):
        try:
            lines.append("Time left: " + _clock(mission.remaining_s(game.mission_time)))
        except Exception:  # noqa: BLE001
            pass
    lines.append("Time of day: " + str(game.world.format_time()))
    weather = game.world.weather_values()
    lines.append(f"Weather: {game.world.weather_kind()}, sea state "
                 f"{weather['sea_state']:.0f}, visibility {weather['visibility_nm']:.0f} NM, "
                 f"{'night' if game.world.is_night() else 'day'}")
    return lines


def frigate_lines(game) -> list:
    ship = game.ship
    lines = ["Own ship: frigate, course {:03.0f}, speed {:.0f} kn (ordered {:03.0f} / {:.0f} kn)"
             .format(ship.course, ship.speed, ship.target_course, ship.target_speed)]
    lines.append(f"Weapons: torpedoes {getattr(game, 'torpedo_count', 0)}")
    tracks = []
    try:
        tracks = list(game.opz_tracks())
    except Exception:  # noqa: BLE001
        tracks = []
    now = game.sim_t
    tracks.sort(key=lambda item: -item.last_seen)
    lines.append(f"Tactical picture (OPZ), {len(tracks)} tracks:")
    for track in tracks[:MAX_TRACKS]:
        parts = [str(track.label), str(track.source), f"brg {track.bearing:03.0f}"]
        if track.range_nm is not None:
            parts.append(f"rng {track.range_nm:.1f} NM")
        if track.course is not None:
            parts.append(f"crs {track.course:03.0f}")
        if track.speed_kn is not None:
            parts.append(f"{track.speed_kn:.0f} kn")
        if track.depth_m is not None:
            parts.append(f"depth {track.depth_m:.0f} m")
        if track.classification:
            parts.append(f"class {track.classification}")
        parts.append(f"age {max(0.0, now - track.last_seen):.0f} s")
        lines.append("- " + ", ".join(parts))
    tasks = []
    try:
        tasks = [task for task in game.task_view() if task.get("state") in ("offered", "active")]
    except Exception:  # noqa: BLE001
        tasks = []
    for task in tasks[:4]:
        lines.append(f"HQ task: {task.get('kind')} ({task.get('state')})")
    return lines


def boat_lines(game) -> list:
    boat = getattr(game, "opfor", None)
    if boat is None:
        return ["Own boat: not crewed"]
    sub = boat.sub
    lines = ["Own boat: submarine, course {:03.0f}, speed {:.0f} kn, depth {:.0f} m"
             .format(sub.course, sub.speed, sub.depth)]
    lines.append(f"Torpedoes left: {getattr(sub, 'torpedoes_left', 0)}")
    endurance = getattr(sub, "endurance", None)
    if endurance is not None:
        capacity = max(1e-6, endurance.profile.battery_capacity_kwh)
        lines.append(f"Battery {100.0 * endurance.battery_kwh / capacity:.0f} %, "
                     f"plant {str(endurance.phase).lower()}")
    observer = boat.station.observer
    now = game.sim_t
    contacts = []
    for _key, contact in sorted(boat.station.sonar.contacts.items()):
        if now - contact.last_seen > config.SONAR_CONTACT_LOST_S:
            continue
        contacts.append(contact)
    contacts.sort(key=lambda item: -item.last_seen)
    lines.append(f"Sonar picture, {len(contacts)} contacts:")
    for contact in contacts[:MAX_TRACKS]:
        bearing = (contact.passive_bearing if contact.passive_bearing is not None
                   else contact.bearing)
        parts = [f"K{contact.id:02d}", f"brg {bearing:03.0f}"]
        if (contact.range_source in ("ping", "tma") and contact.observed_x is not None
                and now - (contact.range_seen or -1e9) <= config.SONAR_CONTACT_LOST_S):
            _brg, rng = _bearing_range(observer.x, observer.y,
                                       contact.observed_x, contact.observed_y)
            parts.append(f"rng {rng:.1f} NM ({contact.range_source})")
        if contact.player_class in config.PLAYER_CLASSES:
            parts.append(f"class {contact.player_class}")
        parts.append(f"age {max(0.0, now - contact.last_seen):.0f} s")
        lines.append("- " + ", ".join(parts))
    radio = getattr(boat, "radio", None)
    order = radio.active_order() if radio is not None else None
    if order is not None:
        lines.append(f"HQ order {order['id']}: {order['kind']}")
    return lines


def feed_lines(game, side: str) -> list:
    if side == "uboot":
        boat = getattr(game, "opfor", None)
        rows = list(boat.feed)[-MAX_FEED:] if boat is not None else []
        out = []
        for row in rows:
            text = row.get("text") if isinstance(row, dict) else None
            if text is not None:
                out.append("- " + _text(game, text))
        return out
    return [f"- {entry.stamp} {_text(game, entry.text)}"
            for entry in game.feed.recent(MAX_FEED)]


def situation(game, side: str | None = None) -> str:
    """The whole picture of one side (default: the uConsole's) as plain lines."""
    side = side or side_of(game)
    lines = mission_lines(game, side)
    lines += boat_lines(game) if side == "uboot" else frigate_lines(game)
    feed = feed_lines(game, side)
    if feed:
        lines.append("Recent reports:")
        lines += feed
    return "\n".join(lines[:MAX_LINES])
