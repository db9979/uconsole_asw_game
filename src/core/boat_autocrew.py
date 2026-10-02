"""Autocrew of the crewed submarine: the AI mans every boat station nobody holds.

With the crew assist on (``Game.crew_assist``, set by a lobby start or
Shift+F2) a crewed boat whose crew holds only some of its seven stations is
not left half-manned: each free station is worked here on a fixed cadence,
through the same crew orders the stations give (``Sub.command_*``,
``set_orders``, ``boat_threat.evade``). A station a browser holds, or the
one the uConsole shows while it plays the boat, is left alone.

- Command (``uboot``): evade a fresh alarm; run the boat mission's leg
  (``boat_ai.orders``) or, in a frigate mission, close a known frigate and
  otherwise patrol quietly below the layer; come to snorkel depth when the
  battery runs low and nothing hunts the boat.
- Weapons: keep the tubes loaded and quietly flooded while a target is
  heard, and fire down the contact's fix at a warship (a merchant of the
  convoy in the convoy attack) inside ``FIRE_NM``, one torpedo at a time.
- Engine: snorkel to charge when shallow enough and unhunted, stop when full
  or hunted; keep the trim automatic, answer foul air, send the two
  damage-control teams where the water or the fire is worst.
- Sonar: keep the focus on the loudest fresh contact.
- Mast/ESM: lower the mast when an alarm comes in.
- Navigation and radio room: watch only.

An order a person gives always wins: a free station never overrides what a
held station also commands (course and depth with a person at navigation,
speed and silent running with one in the engine room, trim and damage
control with one at command, the mast with one at command or in the radio
room, a contact the uConsole selected), and while a person holds the mast up the
command keeps the boat at periscope depth.

Stateless: every decision derives from the simulation time, the seed and
saved boat state, so a loaded game continues identically. Targets come from
the boat's own sonar contacts (bearing, fix, TMA) and signature library,
never from the hidden entities; the mission legs are the AI boat's own.
"""

from __future__ import annotations

import math
from functools import lru_cache

from src.core import boat_ai, boat_missions, boat_threat, config, detrand
from src.core.opfor import depth_presets

CADENCE_S = 2.0
BATTERY_LOW = 0.35            # the command comes up to snorkel below this charge
BATTERY_FULL = 0.95           # the engine stops snorkelling at this charge
FIRE_NM = 4.0                 # fire at a target fix this close
FLOOD_NM = 8.0                # start quiet flooding when a target is this close
CLOSE_NM = 12.0               # a frigate mission: close a frigate known this near
PATROL_KN = 4.0
PATROL_LEG_S = 900.0
FIX_MAX_AGE_S = 120.0
EVADE_AGAIN_S = 60.0
ROLES = ("uboot", "uboot_sonar", "uboot_weapons", "uboot_engine", "uboot_esm",
         "uboot_nav", "uboot_radio")
MAST_ROLES = ("uboot", "uboot_esm", "uboot_radio")   # stations that raise the mast


@lru_cache(maxsize=4)
def _signatures(catalog, categories: frozenset) -> tuple:
    """Signature phrases the library knows only from profiles of ``categories``."""
    owners = {}
    for profile in catalog.acoustic_profiles:
        if profile.signature_text:
            owners.setdefault(profile.signature_text, set()).add(profile.category)
    return tuple(sorted(text for text, kinds in owners.items() if kinds <= categories))


def _local_boat(game) -> bool:
    """The uConsole operator works one of the boat's stations."""
    return (getattr(game, "local_side", "frigate") == "uboot" and not game.in_menu
            and not getattr(game, "host_only", False))


def held(game, role: str) -> bool:
    """A person works ``role``: a browser lease, or the uConsole's boat page."""
    query = getattr(getattr(game.commander, "server", None), "station_leased", None)
    if query is not None and query(role):
        return True
    if _local_boat(game):
        from src.core import uboot_local
        return uboot_local.local_station(game) == role
    return False


def active(game) -> bool:
    boat = game._opfor
    return (game.autocrew.assist and boat is not None
            and not game.game_over and not boat.sub.sunk
            and boat.sub.state not in ("SINKING", "SUNK"))


def _fresh(game, contact, age_s=FIX_MAX_AGE_S) -> bool:
    return 0.0 <= game.sim_t - contact.last_seen <= age_s


def targets(game, boat) -> list:
    """Fresh contacts the crew would shoot at, nearest known fix first."""
    kind = boat_missions.mode(game)
    if kind == "free_boat":
        # A free patrol attacks merchants only on HQ's order to sink one.
        from src.core import free_roam
        order = free_roam.active_order(game)
        kind = "convoy_attack" if order is not None and order["kind"] == "attack" else None
    categories = (frozenset({"TANKER", "FRACHT", "PASSAGIER"}) if kind == "convoy_attack"
                  else frozenset({"TANKER"}) if kind in ("escort", "ras")
                  else frozenset({"KAMPFSCHIFF"}))
    phrases = _signatures(game.runtime_catalog, categories)
    rows = [contact for contact in boat.station.sonar.contacts.values()
            if _fresh(game, contact, 10.0)
            and any(phrase in (contact.signature or "") for phrase in phrases)]

    def fix_range(contact):
        solution = _fix(game, boat, contact)
        return float("inf") if solution is None else solution[1]
    return sorted(rows, key=lambda contact: (fix_range(contact), contact.id))


def _fix(game, boat, contact):
    """``(bearing, range, course, speed)`` of a positioned contact, else None."""
    sub = boat.sub
    if (contact.observed_x is None or contact.observed_y is None
            or contact.range_source not in ("ping", "tma", "visual")
            or contact.range_seen is None
            or not 0.0 <= game.sim_t - contact.range_seen < config.SONAR_CONTACT_LOST_S):
        return None
    dx, dy = contact.observed_x - sub.x, contact.observed_y - sub.y
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    distance = min(40.0, max(0.05, math.hypot(dx, dy)))
    course = speed = None
    if (contact.range_source == "tma" and contact.tma_course is not None
            and contact.tma_speed is not None
            and contact.tma_quality >= config.TMA_RANGE_MIN_QUALITY):
        course, speed = contact.tma_course % 360.0, min(60.0, max(0.0, contact.tma_speed))
    return bearing, distance, course, speed


def _alarm(boat):
    return boat_threat.alarm_source(boat)


# --- stations -------------------------------------------------------------

def command(game, boat) -> str:
    """Steer the boat, but never over a person: course, depth and evasion
    belong to a held navigation station, speed and silent running to a held
    engine room, and a mast a person raised keeps the boat at periscope depth."""
    sub = boat.sub
    if held(game, "uboot_nav"):
        return "monitoring"
    engine_free = not held(game, "uboot_engine")
    if _alarm(boat) is not None:
        if boat.evaded_t is None or game.sim_t - boat.evaded_t >= EVADE_AGAIN_S:
            if boat_threat.evade(game, boat) is True:
                return "evading"
        return "monitoring"
    if boat.orders.route.active:
        return "monitoring"              # the navigator's route has the helm
    if boat.orders.silent and engine_free:
        sub.command_silent(False)
    presets = depth_presets(game, boat)
    ceiling = float(presets["deep"])
    if boat.orders.mast and any(held(game, role) for role in MAST_ROLES):
        ceiling = min(ceiling, float(presets["periscope"]))
    endurance = sub.endurance
    if (endurance is not None and presets["snorkel"] is not None
            and endurance.battery_kwh < BATTERY_LOW * endurance.profile.battery_capacity_kwh
            and not boat_ai.hunted(sub)):
        sub.set_orders(speed=(min(PATROL_KN, sub.motion.maximum_speed_kn)
                              if engine_free else None),
                       depth=min(float(presets["snorkel"]), ceiling))
        return "charging"
    leg = boat_ai.orders(game, sub)
    if leg is None:
        leg = _frigate_mission_leg(game, boat)
    course, speed, depth = leg
    depth = min(float(depth), ceiling)
    sub.set_orders(course=float(course) % 360.0,
                   speed=(min(float(speed), float(sub.motion.maximum_speed_kn))
                          if engine_free else None),
                   depth=max(0.0, depth))
    return "steering"


def _frigate_mission_leg(game, boat):
    """No boat mission: close a frigate the boat knows, else patrol quietly."""
    sub = boat.sub
    deep = boat_ai._deep(game, sub)
    found = targets(game, boat)
    solution = _fix(game, boat, found[0]) if found else None
    if solution is not None and solution[1] <= CLOSE_NM:
        bearing, distance = solution[0], solution[1]
        # Close on a slant for bearing motion, straight in when near.
        offset = 0.0 if distance <= FIRE_NM else 30.0
        return (boat_ai._course(game, sub, (bearing + offset) % 360.0),
                boat_ai.pace(sub, config.BOAT_AI_TRANSIT_KN), deep)
    # Patrol: a new waypoint near the boat's start every leg.
    leg = int(math.floor(game.sim_t / PATROL_LEG_S))
    angle = 360.0 * detrand.u01(game.seed, "boat-autocrew.patrol", 0, leg)
    reach = 3.0 + 7.0 * detrand.u01(game.seed, "boat-autocrew.reach", 0, leg)
    x = sub.start_pos[0] + reach * math.sin(math.radians(angle))
    y = sub.start_pos[1] - reach * math.cos(math.radians(angle))
    course = boat_ai._bearing(sub.x, sub.y, x, y)
    return boat_ai._course(game, sub, course), PATROL_KN, deep


def weapons(game, boat) -> str:
    sub = boat.sub
    found = targets(game, boat)
    if not found:
        return "monitoring"
    solution = _fix(game, boat, found[0])
    close = solution is not None and solution[1] <= FLOOD_NM
    tubes = sub.crew_tubes
    if tubes is not None:
        if any(tube.loaded_weapon_key is None and tube.loading_weapon_key is None
               for tube in sub.weapon_battery.tubes) and sub.command_load_tube() is True:
            return "loading"
        if close and sub.command_flood_tube(quiet=True) is True:
            return "flooding"
    if solution is None or solution[1] > FIRE_NM or boat_ai._torpedo_running(game, sub):
        return "monitoring"
    bearing, distance, course, speed = solution
    if sub.command_fire(bearing, distance, course, speed, now=game.sim_t) is True:
        return "engaged"
    return "monitoring"


def engine(game, boat) -> str:
    sub = boat.sub
    endurance = sub.endurance
    # Command shares the trim and the damage-control teams: a person there decides.
    command_free = not held(game, "uboot")
    if command_free and not sub.ballast.auto:
        sub.command_trim_auto(True)
    action = "monitoring"
    if endurance is not None:
        capacity = endurance.profile.battery_capacity_kwh
        hunted = _alarm(boat) is not None or boat_ai.hunted(sub)
        if sub.snorkeling and (hunted or endurance.battery_kwh >= BATTERY_FULL * capacity):
            sub.command_snorkel(False)
            action = "snorkel_off"
        elif (not sub.snorkeling and not hunted
              and endurance.battery_kwh < BATTERY_FULL * capacity
              and sub.depth <= endurance.profile.snorkel_depth_m + 1.0
              and sub.command_snorkel(True) is True):
            action = "snorkel_on"
        air = endurance.air
        if air.level() != "ok":
            if air.absorber_left <= 0.0 and air.absorber_sets > 0:
                sub.command_absorber()
            elif air.candle_left_s <= 0.0 and air.candles > 0:
                sub.command_o2_candle()
    if command_free:
        _damage_control(sub)
    return action


def _damage_control(sub) -> None:
    from src.enemies.damage_control import COMPARTMENTS
    control = sub.damage_control
    rows = [(c.fire * 3.0 + c.leak * 2.0 + c.water_kg / 1000.0, -index, name, c)
            for index, (name, c) in enumerate(zip(COMPARTMENTS, control.compartments))]
    rows = sorted((row for row in rows if row[0] > 0.0), reverse=True)
    for team, row in enumerate(rows[:2]):
        _, _, name, c = row
        task = "fire" if c.fire > 0.0 else "seal" if c.leak > 0.0 else "pump"
        current = control.teams[team]
        if current["compartment"] != name or current["task"] != task:
            sub.command_dc_team(team, name, task)


def sonar(game, boat) -> str:
    station = boat.station
    contacts = [contact for contact in station.sonar.contacts.values() if _fresh(game, contact, 2.0)]
    if not contacts:
        return "monitoring"
    picked = station.selected_contact
    if (_local_boat(game) and picked is not None
            and station.sonar.contacts.get(picked.target_id) is picked):
        return "monitoring"             # the uConsole's pick (Up/Down) stays picked
    best = max(contacts, key=lambda contact: (contact.snr, -contact.id))
    if station.selected_contact is not best:
        station.selected_contact = best
        return "focused"
    return "monitoring"


def esm(game, boat) -> str:
    # Command and the radio room raise the mast too: a person there decides.
    if (boat.orders.mast and _alarm(boat) is not None
            and not any(held(game, role) for role in MAST_ROLES if role != "uboot_esm")):
        boat.sub.command_mast(False)
        return "mast_down"
    return "monitoring"


_STATIONS = (("uboot_sonar", sonar), ("uboot_engine", engine), ("uboot_esm", esm),
             ("uboot", command), ("uboot_weapons", weapons))


def update(game, dt: float) -> None:
    """Man every free boat station on the cadence (after the boat's sonar)."""
    if math.floor(game.sim_t / CADENCE_S) == math.floor((game.sim_t - dt) / CADENCE_S):
        return
    if not active(game):
        return
    boat = game._opfor
    for role, work in _STATIONS:
        if not held(game, role):
            work(game, boat)
