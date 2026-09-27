"""The crewed hostile submarine ("OPFOR"): binding, sonar and event feed.

A player crew may command one hostile submarine - from the browser (Remote
Crew roles ``uboot``/``uboot_sonar``) or on the uConsole itself.  The binding
is transient like a station lease: it is never saved, and a load, reset or
new game drops it (the AI then commands the boat again).

The crew's view is strictly the boat's own: its sonar workstation hears the
frigate, its torpedoes and every other radiating target through the ordinary
``SonarSystem`` measurement chain; nothing here publishes truth.
"""

from collections import deque
import math

from src.core.callouts import CalloutLog
from src.core import config, detrand
from src.core.boat_esm import BoatESM
from src.core.crew import CrewState
from src.core.i18n import message
from src.core.plot import PlotLayer
from src.physics import torpedo_dyn
from src.sensors import lookout_id
from src.sensors import visual as visual_physics
from src.sensors.platform import MAST_DEPTH_M
from src.sonar.platforms import (OWNSHIP_SIGNATURE_KEY, OWNSHIP_TARGET_ID,
                                 OWN_TORPEDO_TARGET_BASE, SCOPE_AIR_TARGET_ID,
                                 OwnShipAcousticSource, OwnTorpedoAcousticSource,
                                 SubSonarPlatform)
from src.sonar.sonar import SonarSystem, hull_length_m
from src.sonar.station import SonarStation

# Periscope sightings: coarse classes the eye makes out, their lookout kind
# (``src/sensors/visual.py``) and the Johnson class of the recognition step.
SIGHTING_CLASSES = ("warship", "merchant", "aircraft", "torpedo", "unknown")
SIGHTING_KINDS = {"warship": "SURFACE", "merchant": "SURFACE", "unknown": "SURFACE",
                  "aircraft": "FLG", "torpedo": "TORP"}
_RECOGNIZE_CLASS = {"warship": "WARSHIP", "merchant": "MERCHANT"}
_SIGHTING_LENGTH_M = {"aircraft": 15.0, "torpedo": 40.0}
_SCOPE_AIR_ALTITUDE_M = 60.0
# The periscope shares the frigate lookout's contrast model (anchored ranges).
_SCOPE_MODEL = visual_physics.LookoutModel(
    {"SURFACE": config.LOOKOUT_SURFACE_RANGE_NM, "SUB": config.LOOKOUT_SUB_RANGE_NM,
     "FLG": config.LOOKOUT_AIR_RANGE_NM, "TORP": config.TORPEDO_WAKE_VISIBLE_NM,
     "LAND": config.LOOKOUT_LAND_RANGE_NM},
    config.WEATHER_VISIBILITY_MAX_NM)
# Bounded crew event feed (newest last) and the SonarSystem seed salt.
OPFOR_FEED_MAX = 64
_SONAR_SEED_SALT = 0x0B0A7
# The boat's sonar room is lost with the boat: damage beyond this disables it.
OPFOR_SONAR_DOWN_DAMAGE = 90.0


class CrewOrders:
    """Crew settings of the crewed boat (save v15 ``crew.orders``).

    The ``Sub`` reads them only while ``manual``; they vanish with the crew
    binding (release, reset), after which the AI commands the boat again.  A
    save keeps them, so a loaded boat resumes under its crew's last orders.
    """

    # Crew notices raised by the boat itself (key -> feed category).
    EVENTS = {"obstacle": "navigation", "snorkel_stopped": "navigation",
              "battery_low": "navigation", "battery_empty": "navigation",
              "shallow_water": "navigation", "wire_broken": "waffen",
              "ping_heard": "sonar", "torpedo_heard": "sonar",
              "ping_dipping_heard": "sonar", "ping_buoy_heard": "sonar",
              "buoy_splash": "sonar", "evade": "navigation",
              "evade_decoy": "navigation",
              "mast_lowered": "navigation", "esm_intercept": "sonar",
              "obstacle_ahead": "navigation",
              "sighting_warship": "sonar", "sighting_merchant": "sonar",
              "sighting_aircraft": "sonar", "sighting_torpedo": "sonar",
              "sighting_unknown": "sonar",
              "air_caution": "navigation", "air_danger": "navigation",
              "absorber_spent": "navigation", "fuel_low": "navigation",
              "fuel_empty": "navigation", "esm_mast_threat": "navigation",
              "mast_overtime": "navigation", "tanks_venting": "navigation",
              "tanks_flooded": "navigation", "boat_heavy": "navigation",
              "boat_light": "navigation", "trim_angle": "navigation",
              "hp_air_low": "navigation", "dc_leak": "schaden", "dc_fire": "schaden",
              "dc_fire_out": "schaden", "dc_leak_sealed": "schaden",
              "dc_flooded": "schaden", "dc_chlorine": "schaden",
              "dc_power_lost": "schaden", "dc_power_restored": "schaden"}

    def __init__(self):
        self.silent = False
        self.bottomed = False
        self.mast = False
        # Measured alarm bearings (the boat's own intercepts) and ESM picture.
        self.alarm_seq = 0
        self.ping_bearing = None
        self.torpedo_bearing = None
        self.esm = []
        # Periscope: line of sight relative to the bow, and what it sees.
        self.scope_rel_deg = 0.0
        self.sightings = []
        self._sightings_seen = set()
        # Wire-guided crew torpedoes: EnemyTorpedo id -> CrewWire.
        self.wires = {}
        self._known_torpedoes = set()
        self._last_course = None
        # Local fire-control presets (the web sends them with each shot).
        self.torpedo_depth = None
        self.salvo = 1
        self.pending_bearing = None
        self.steer_torpedo = None
        self._events = []
        self._battery_state = "ok"
        self._keel_warned = False
        self._obstacle_warned = False
        # Chart check along the ordered course (0.25 s cadence), for the displays.
        self.obstacle_ahead_nm = None
        # Intercepts not yet stamped by the crew update (never saved; see
        # CrewedBoat.intercepts).
        self._pending_intercepts = []

    def event(self, key: str, **values) -> None:
        if key in self.EVENTS and (values or all(k != key for k, _ in self._events)):
            self._events.append((key, values))

    def intercept(self, kind: str, bearing: float, level_db) -> None:
        """An acoustic intercept for the counter-detection picture."""
        if len(self._pending_intercepts) < config.UBOOT_INTERCEPTS_MAX:
            self._pending_intercepts.append((kind, float(bearing),
                                             None if level_db is None else float(level_db)))

    def drain_events(self) -> list:
        events, self._events = self._events, []
        return events

    def quiet_active(self, sub) -> bool:
        """Silent running within its speed ceiling, or lying on the bottom."""
        if sub.snorkeling or sub.pinged_this_tick:
            return False
        if self.bottomed:
            return True
        return self.silent and sub.speed <= config.UBOOT_SILENT_MAX_KN + 1e-6

    def to_save(self) -> dict:
        """Exact save v15 ``crew.orders`` block (JSON-safe lists, sorted)."""
        return dict(
            silent=self.silent, bottomed=self.bottomed, mast=self.mast,
            alarm_seq=self.alarm_seq, ping_bearing=self.ping_bearing,
            torpedo_bearing=self.torpedo_bearing,
            esm=[[bearing, quality, age] for bearing, quality, age in self.esm],
            scope_rel_deg=self.scope_rel_deg,
            sightings=[dict(row) for row in self.sightings],
            sightings_seen=sorted(self._sightings_seen),
            wires={str(torpedo_id): wire.to_save()
                   for torpedo_id, wire in sorted(self.wires.items())},
            known_torpedoes=sorted(self._known_torpedoes),
            last_course=self._last_course, torpedo_depth=self.torpedo_depth,
            salvo=self.salvo, pending_bearing=self.pending_bearing,
            steer_torpedo=self.steer_torpedo,
            events=[[key, dict(values)] for key, values in self._events],
            battery_state=self._battery_state, keel_warned=self._keel_warned,
            obstacle_warned=self._obstacle_warned,
            obstacle_ahead_nm=self.obstacle_ahead_nm)

    def restore(self, data: dict) -> None:
        """Restore a validated ``crew.orders`` block in place."""
        self.silent = data["silent"]
        self.bottomed = data["bottomed"]
        self.mast = data["mast"]
        self.alarm_seq = data["alarm_seq"]
        self.ping_bearing = data["ping_bearing"]
        self.torpedo_bearing = data["torpedo_bearing"]
        self.esm = [tuple(row) for row in data["esm"]]
        self.scope_rel_deg = data["scope_rel_deg"]
        self.sightings = [dict(row) for row in data["sightings"]]
        self._sightings_seen = set(data["sightings_seen"])
        self.wires = {int(torpedo_id): CrewWire.from_save(int(torpedo_id), wire)
                      for torpedo_id, wire in data["wires"].items()}
        self._known_torpedoes = set(data["known_torpedoes"])
        self._last_course = data["last_course"]
        self.torpedo_depth = data["torpedo_depth"]
        self.salvo = data["salvo"]
        self.pending_bearing = data["pending_bearing"]
        self.steer_torpedo = data["steer_torpedo"]
        self._events = [(key, dict(values)) for key, values in data["events"]]
        self._battery_state = data["battery_state"]
        self._keel_warned = data["keel_warned"]
        self._obstacle_warned = data["obstacle_warned"]
        self.obstacle_ahead_nm = data["obstacle_ahead_nm"]


class CrewWire:
    """The guidance wire of one crew torpedo (save v15 ``crew.orders.wires``).

    Same spool and tension rules as the frigate's wire (``torpedo_dyn``),
    with the submarine's own speed and turn limits.
    """

    def __init__(self, torpedo_id: int):
        self.torpedo_id = torpedo_id
        self.state = "ACTIVE"          # ACTIVE | BROKEN | CUT
        self.ship_out_nm = 0.0
        self.stress_s = 0.0

    @property
    def active(self) -> bool:
        return self.state == "ACTIVE"

    def to_save(self) -> dict:
        return dict(state=self.state, ship_out_nm=self.ship_out_nm,
                    stress_s=self.stress_s)

    @classmethod
    def from_save(cls, torpedo_id: int, data: dict) -> "CrewWire":
        wire = cls(torpedo_id)
        wire.state = data["state"]
        wire.ship_out_nm = data["ship_out_nm"]
        wire.stress_s = data["stress_s"]
        return wire


class CrewedBoat:
    """One crewed submarine: the boat, its sonar workstation and its feed."""

    def __init__(self, sub, runtime_catalog):
        self.sub = sub
        self.sub_id = sub.id
        self.orders = CrewOrders()
        sub.crew = self.orders
        # Watches, fatigue and morale of the boat's crew (saved; the game
        # replaces it with one that knows the current sim time on claim).
        self.watch = CrewState()
        platform = SubSonarPlatform(sub)
        sonar = SonarSystem(seed=(int(sub.sensor_seed) ^ _SONAR_SEED_SALT) & 0x7FFFFFFF,
                            acoustic_profiles=runtime_catalog.acoustic_profiles)
        self.station = SonarStation(sonar, kind="sub", observer=platform)
        self.station.down = self.sonar_down
        self.feed = deque(maxlen=OPFOR_FEED_MAX)
        self.feed_seq = 0
        # The boat's own grease-pencil plot (transient, never the frigate's).
        self.plot = PlotLayer()
        # The crew's ESM picture (saved) and the emitter the uConsole
        # operator has selected on the ESM page (display only).
        self.esm = BoatESM()
        self.esm_selected = None
        # Damage-control page: the compartment and task picked (display only).
        self.dc_selected = 0
        self.dc_task = "seal"
        # Local command-station UI (display only): chart camera and page.
        self.chart_view = None
        self.chart_follow = True
        self.command_page = 0
        # Counter-detection picture: timestamped intercepts (pings by source,
        # buoy splashes).  Display only and never saved; a loaded boat
        # starts with an empty picture.
        self.intercepts = deque(maxlen=config.UBOOT_INTERCEPTS_MAX)
        # Spoken crew reports from this feed (transient, like the frigate's).
        self.callouts = CalloutLog("boat")
        self.evaded_t = None             # last evasion order (sim s, transient)
        # Cached radiating adapters (identity stays stable between updates).
        self._ownship_source = None
        self._torpedo_sources = {}

    def sonar_down(self) -> bool:
        sub = self.sub
        return bool(sub.sunk or sub.state in ("SINKING", "SUNK")
                    or sub.damage >= OPFOR_SONAR_DOWN_DAMAGE)

    def notice(self, sim_t: float, category: str, text, stamp: str = "") -> None:
        self.feed_seq += 1
        self.feed.append(dict(seq=self.feed_seq, t=float(sim_t), stamp=str(stamp),
                              category=category, text=text))
        self.callouts.add(text)

    def to_save(self) -> dict:
        """The boat-level part of the save v15 ``crew`` block (the game adds
        ``sub_id``, ``hold_s`` and the sonar ``station``)."""
        return dict(orders=self.orders.to_save(),
                    command_page=int(self.command_page),
                    chart_follow=bool(self.chart_follow),
                    plot=self.plot.to_save(),
                    esm=self.esm.to_save(),
                    feed=[dict(row) for row in self.feed],
                    feed_seq=int(self.feed_seq),
                    watch=self.watch.serialize())

    def restore(self, data: dict) -> None:
        self.orders.restore(data["orders"])
        self.command_page = data["command_page"]
        self.chart_follow = data["chart_follow"]
        self.plot = PlotLayer.from_save(data["plot"])
        self.esm = BoatESM.from_save(data["esm"])
        self.feed = deque((dict(row) for row in data["feed"]), maxlen=OPFOR_FEED_MAX)
        self.feed_seq = data["feed_seq"]
        self.watch = CrewState.restore(data["watch"])

    def sonar_targets(self, game) -> list:
        """Everything this boat's sonar can hear (never the boat itself)."""
        sub = self.sub
        if self._ownship_source is None or self._ownship_source._ship is not game.ship:
            self._ownship_source = OwnShipAcousticSource(
                game.ship, game.damage, game.runtime_catalog)
        live = {}
        for torpedo in game.torpedoes:
            if torpedo.state != "RUN":
                continue
            source = self._torpedo_sources.get(id(torpedo))
            if source is None or source._torpedo is not torpedo:
                source = OwnTorpedoAcousticSource(torpedo)
            live[id(torpedo)] = source
        self._torpedo_sources = live
        others = [target for target in game._sonar_targets() if target is not sub]
        own = [] if game.damage.ship_sunk else [self._ownship_source]
        return others + own + [live[key] for key in sorted(
            live, key=lambda item: live[item].id)]


def choose_boat(game):
    """The living hostile submarine with the smallest ID, or None."""
    candidates = [sub for sub in game.subs
                  if getattr(sub, "side", "hostile") == "hostile"
                  and not sub.sunk and sub.state not in ("SINKING", "SUNK")]
    return min(candidates, key=lambda sub: sub.id, default=None)


def update_sonar(game, boat: CrewedBoat, dt: float) -> None:
    """Passive listening, TMA and echoes for the crewed boat (0.25 s cadence)."""
    station = boat.station
    sonar = station.sonar
    if station.target is not None and station.target.target_id not in sonar.contacts:
        station.target = None
    if (station.selected_contact is not None
            and station.selected_contact.target_id not in sonar.contacts):
        station.selected_contact = None
    if boat.sonar_down():
        return
    previous = {contact.id for contact in sonar.contacts.values()}
    targets = boat.sonar_targets(game)
    focus = None
    if station.selected_contact is not None:
        focus = next((target for target in targets
                      if target.id == station.selected_contact.target_id), None)
    sonar.shipping_contacts = sum(
        1 for ship in game.civilians
        if not ship.sunk and ship.distance_nm(station.observer) <= 50.0)
    sonar.update(dt, game.sim_t, station.observer, targets, game.world,
                 range_factor=1.0, mode="BOW", focus_tgt=focus,
                 own_cavitation=1.0 if boat.sub.cavitating else 0.0,
                 advance_mechanics=False)
    while sonar.echo_events:
        echo = sonar.echo_events.pop(0)
        if echo["contact_id"] == 0:
            boat.notice(game.sim_t, "sonar", stamp=game.world.format_time(), text=message(
                "runtime.echo.unassociated", bearing=f"{echo['bearing']:05.1f}",
                range=f"{echo['range_nm']:.1f}"))
            continue
        boat.notice(game.sim_t, "sonar", stamp=game.world.format_time(), text=message(
            "runtime.echo.feed", contact=echo["contact_id"],
            bearing=f"{echo['bearing']:05.1f}", range=f"{echo['range_nm']:.1f}",
            depth=f"{echo['depth_m']:.0f}"))
    for contact in sonar.active_contacts():
        if contact.id not in previous:
            key = ("runtime.contact.new_range" if contact.range_est
                   else "runtime.contact.new_bearing")
            boat.notice(game.sim_t, "sonar", stamp=game.world.format_time(), text=message(
                key, contact=contact.id, bearing=f"{contact.bearing:4.0f}",
                range=f"{contact.range_est:.1f}" if contact.range_est else "",
                origin=contact.origin))


def _crew_torpedoes(game, boat) -> dict:
    return {torpedo.id: torpedo for torpedo in game.enemy_torpedoes
            if torpedo.launch_platform_id == boat.sub_id and torpedo.state == "RUN"}


def update_wires(game, boat, dt: float) -> None:
    """Pay out, strain and steer the wires of the crew's running torpedoes."""
    sub, orders = boat.sub, boat.orders
    running = _crew_torpedoes(game, boat)
    for torpedo_id in sorted(running):
        if torpedo_id not in orders._known_torpedoes:
            orders._known_torpedoes.add(torpedo_id)
            orders.wires[torpedo_id] = CrewWire(torpedo_id)
    orders._known_torpedoes &= set(running)
    orders.wires = {key: wire for key, wire in orders.wires.items() if key in running}
    yaw = 0.0
    if orders._last_course is not None and dt > 0.0:
        yaw = abs(config.angle_diff_deg(sub.course, orders._last_course)) / dt
    orders._last_course = sub.course
    for torpedo_id, wire in sorted(orders.wires.items()):
        if not wire.active:
            continue
        torpedo = running[torpedo_id]
        wire.ship_out_nm += config.kn_to_nm_per_s(max(0.0, sub.speed)) * dt
        overload = sub.speed > config.UBOOT_WIRE_MAX_KN or yaw > config.UBOOT_WIRE_MAX_YAW_DEG_S
        wire.stress_s = wire.stress_s + dt if overload else 0.0
        if (sub.sunk or wire.stress_s >= torpedo_dyn.WIRE_TENSION_BREAK_S
                or wire.ship_out_nm >= torpedo_dyn.WIRE_SHIP_SPOOL_NM
                or torpedo.travel >= torpedo.range_nm * torpedo_dyn.WIRE_TORPEDO_SPOOL_FACTOR):
            wire.state = "BROKEN"
            orders.event("wire_broken")
            continue
        if (torpedo.seeker_acquired or torpedo.guidance_x is None
                or torpedo.guidance_y is None):
            continue
        # The wire turns the torpedo onto its (possibly updated) datum.
        desired = math.degrees(math.atan2(torpedo.guidance_x - torpedo.x,
                                          -(torpedo.guidance_y - torpedo.y))) % 360.0
        step = config.UBOOT_WIRE_TURN_DEG_S * dt
        torpedo.course = (torpedo.course + config.clamp(
            config.angle_diff_deg(desired, torpedo.course), -step, step)) % 360.0


def wire_steer(boat, torpedo, bearing: float, range_nm: float):
    """Crew: move a wired torpedo's datum to ``bearing``/``range_nm`` from the boat."""
    wire = boat.orders.wires.get(torpedo.id)
    if wire is None or not wire.active:
        return "uboot_no_wire"
    if (type(bearing) not in (int, float) or type(range_nm) not in (int, float)
            or not math.isfinite(bearing) or not math.isfinite(range_nm)
            or not 0.0 <= bearing < 360.0 or not 0.05 <= range_nm <= 40.0):
        return "invalid_value"
    sub = boat.sub
    torpedo.guidance_x = sub.x + range_nm * math.sin(math.radians(bearing))
    torpedo.guidance_y = sub.y - range_nm * math.cos(math.radians(bearing))
    return True


def wire_cut(boat, torpedo):
    wire = boat.orders.wires.get(torpedo.id)
    if wire is None or not wire.active:
        return "uboot_no_wire"
    wire.state = "CUT"
    return True


def wire_state(boat, torpedo) -> str | None:
    wire = boat.orders.wires.get(torpedo.id)
    return None if wire is None else wire.state


def speed_steps(sub) -> tuple:
    """Telegraph steps of the crewed boat (knots), ending at its maximum."""
    maximum = float(sub.motion.maximum_speed_kn)
    return tuple(step for step in config.UBOOT_SPEED_STEPS_KN if step < maximum) + (maximum,)


def step_speed(sub, delta: int):
    """One telegraph step faster (+1) or slower (-1) from the ordered speed."""
    steps = speed_steps(sub)
    index = min(range(len(steps)), key=lambda i: abs(steps[i] - sub.order_speed))
    return sub.set_orders(speed=steps[max(0, min(len(steps) - 1, index + delta))])


def battery_fraction(sub):
    endurance = sub.endurance
    if endurance is None or not endurance.profile.battery_capacity_kwh:
        return None
    return endurance.battery_kwh / endurance.profile.battery_capacity_kwh


def measured_layer_m(boat):
    """The layer the boat's own BT measurement found, else None (no truth)."""
    profile = boat.station.sonar.bt_profile
    return float(profile["thermocline_m"]) if profile else None


def depth_presets(game, boat) -> dict:
    """Ordered depths the crew can pick in one step (metres, None = unavailable).

    Periscope depth keeps the mast usable; snorkel depth needs a snorkel; the
    layer presets exist only after the boat's own BT measurement; "deep" is
    the safe depth over the charted bottom.
    """
    from src.sensors.platform import MAST_DEPTH_M
    sub = boat.sub
    safe = float(sub.safe_depth_m(game.world))
    endurance = sub.endurance
    layer = measured_layer_m(boat)
    above = below = None
    if layer is not None:
        above = max(config.UBOOT_PRESET_MIN_M, layer - config.UBOOT_LAYER_MARGIN_M)
        below = layer + 2.0 * config.UBOOT_LAYER_MARGIN_M
        above = above if above < layer and above <= safe else None
        below = below if below <= safe else None
    return dict(periscope=min(safe, MAST_DEPTH_M - 3.0),
                snorkel=(min(safe, float(endurance.profile.snorkel_depth_m))
                         if endurance is not None else None),
                above_layer=above, below_layer=below, deep=safe, layer=layer)


def obstacle_ahead_nm(world, sub):
    """Distance to the first charted obstacle (land, or a seabed shallower than
    the boat's keel) along the ordered course, within the look-ahead; else None.
    Known geography only: the chart the crew holds, no other vessel."""
    step = 0.25
    keel = max(sub.depth, sub.order_depth) + config.UBOOT_BOTTOM_CLEARANCE_M
    rad = math.radians(sub.order_course)
    distance = step
    while distance <= config.UBOOT_OBSTACLE_LOOKAHEAD_NM + 1e-9:
        x = sub.x + distance * math.sin(rad)
        y = sub.y - distance * math.cos(rad)
        if world.on_land(x, y) or world.charted_depth_m(x, y) < keel:
            return distance
        distance += step
    return None


def update_crew(game, boat: CrewedBoat) -> None:
    """Crew warnings from the boat's own state (0.25 s cadence)."""
    sub, orders = boat.sub, boat.orders
    if sub.sunk:
        return
    battery = battery_fraction(sub)
    if battery is not None:
        state = ("empty" if battery <= config.UBOOT_BATTERY_EMPTY_FRACTION
                 else "low" if battery <= config.UBOOT_BATTERY_WARN_FRACTION else "ok")
        if state != orders._battery_state:
            if state in ("low", "empty"):
                orders.event("battery_" + state)
            orders._battery_state = state
    bottom = sub.last_bottom_m
    shallow = (bottom is not None and not orders.bottomed
               and bottom - sub.depth < config.UBOOT_UNDER_KEEL_WARN_M)
    if shallow and not orders._keel_warned:
        orders.event("shallow_water")
    orders._keel_warned = shallow
    ahead = orders.obstacle_ahead_nm = obstacle_ahead_nm(game.world, sub)
    if ahead is not None and sub.order_speed > 0.0 and not orders._obstacle_warned:
        orders.event("obstacle_ahead", distance=f"{ahead:.1f}")
    orders._obstacle_warned = ahead is not None and sub.order_speed > 0.0
    for kind, bearing, level in orders._pending_intercepts:
        boat.intercepts.append(dict(t=float(game.sim_t), kind=kind, bearing=bearing,
                                    level_db=level))
    orders._pending_intercepts = []
    # ESM with the mast up: the boat's own intercepts of radar emitters.
    boat.esm.update(game, boat)
    orders.esm = boat.esm.bearings(game.sim_t) if orders.mast else []
    update_sightings(game, boat)
    for key, values in orders.drain_events():
        if "compartment" in values:
            values = dict(values, compartment=message(
                f"uboot.compartment.{values['compartment']}"))
        boat.notice(game.sim_t, CrewOrders.EVENTS[key], message(f"uboot.event.{key}", **values),
                    stamp=game.world.format_time())


# --- periscope -------------------------------------------------------------------

def scope_available(boat) -> bool:
    """The optics are above the water: mast raised at periscope depth."""
    sub, orders = boat.sub, boat.orders
    return bool(orders.mast and not sub.sunk and sub.depth <= MAST_DEPTH_M + 1.0)


def scope_bearing(boat) -> float:
    """True bearing of the periscope's line of sight."""
    return (boat.sub.course + boat.orders.scope_rel_deg) % 360.0


def turn_scope(boat, delta_deg: float) -> float:
    """Train the periscope by ``delta_deg`` (relative to the bow); returns the
    new relative bearing."""
    boat.orders.scope_rel_deg = (boat.orders.scope_rel_deg + delta_deg) % 360.0
    return boat.orders.scope_rel_deg


def set_scope_relative(boat, relative_deg: float) -> float:
    boat.orders.scope_rel_deg = relative_deg % 360.0
    return boat.orders.scope_rel_deg


def horizon_motion(game, boat) -> tuple:
    """(vertical offset px, tilt rad) of the horizon seen through the scope,
    from the wave slope at the boat's own seed and the sea state its optics
    see (display only, deterministic in sim time)."""
    from src.ui.horizon import horizon_motion as motion
    sea_state = getattr(game.world, "effective_sea_state", game.world.sea_state)
    return motion(int(boat.sub.id), game.sim_t, sea_state)


def _frigate_length_m(game) -> float:
    catalog = game.runtime_catalog
    systems = catalog.profile_systems.get(OWNSHIP_SIGNATURE_KEY)
    reference = (catalog.references.get(systems.reference_key)
                 if systems is not None and systems.reference_key else None)
    if reference is not None and reference.length_m:
        return float(reference.length_m)
    return config.UBOOT_STADIMETER_LENGTHS_M["warship"]


def _scope_candidates(game, boat) -> list:
    """``(target_id, actor, class, length_m, altitude_m)`` of everything the
    periscope could make out (sensor generation: internal truth, never
    published)."""
    rows = []
    if not game.damage.ship_sunk:
        rows.append((OWNSHIP_TARGET_ID, game.ship, "warship", _frigate_length_m(game), None))
    for other in game.warships:
        if not other.sunk:
            rows.append((int(other.id), other, "warship", hull_length_m(other), None))
    for other in game.civilians:
        if not other.sunk:
            rows.append((int(other.id), other, "merchant", hull_length_m(other), None))
    helo = game.helo
    if helo is not None and helo.airborne:
        rows.append((SCOPE_AIR_TARGET_ID, helo, "aircraft",
                     _SIGHTING_LENGTH_M["aircraft"], _SCOPE_AIR_ALTITUDE_M))
    for torpedo in game.torpedoes:
        if torpedo.state == "RUN":
            rows.append((OWN_TORPEDO_TARGET_BASE + int(torpedo.idx), torpedo, "torpedo",
                         _SIGHTING_LENGTH_M["torpedo"], None))
    return rows


def update_sightings(game, boat: CrewedBoat) -> None:
    """What the raised periscope sees (0.25 s cadence): bearing-only
    sightings with a coarse class and the apparent length of the target.

    Detection follows the frigate lookout's contrast model with the
    periscope's eye height; the bearing carries a per-target bias plus a
    small jitter, the class needs the finer Johnson resolution.  A sighting
    is held ``UBOOT_SIGHTING_LOST_S`` after the optics last had it.
    """
    sub, orders = boat.sub, boat.orders
    if not scope_available(boat):
        orders.sightings = []
        orders._sightings_seen.clear()
        return
    now = game.sim_t
    seed = int(sub.sensor_seed)
    environment = game._lookout_environment()
    epoch = math.floor((now + 1e-9) / config.LOOKOUT_EPOCH_S)
    previous = {row["ref"]: row for row in orders.sightings}
    rows = []
    # A tired watch on the periscope needs more contrast (1.0 when fresh).
    alert = boat.watch.effectiveness(game.sim_t)
    for target_id, actor, cls, length_m, altitude_m in _scope_candidates(game, boat):
        dx, dy = actor.x - sub.x, actor.y - sub.y
        distance = math.hypot(dx, dy)
        kind = SIGHTING_KINDS[cls]
        margin = alert * _SCOPE_MODEL.margin(kind, distance, altitude_m=altitude_m,
                                             eye_m=config.UBOOT_SCOPE_EYE_HEIGHT_M,
                                             **environment)
        if margin < 1.0 or game.world.land_blocks_line(sub.x, sub.y, actor.x, actor.y):
            continue
        recognized = cls
        if cls in _RECOGNIZE_CLASS and _SCOPE_MODEL.margin(
                kind, distance, altitude_m=altitude_m,
                eye_m=config.UBOOT_SCOPE_EYE_HEIGHT_M,
                detail=lookout_id.RECOGNIZE_CYCLES
                / lookout_id.CLASS_SIZE[_RECOGNIZE_CLASS[cls]],
                **environment) * alert < 1.0:
            recognized = "unknown"
        true_bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
        error = (0.7 * detrand.normal(seed, "scope-bias", target_id)
                 + 0.3 * detrand.normal(seed, "scope-jitter", target_id, epoch))
        bearing = (true_bearing + error * config.UBOOT_SCOPE_BEARING_ERR_DEG) % 360.0
        course = getattr(actor, "course", None)
        aspect = (1.0 if course is None
                  else max(0.2, abs(math.sin(math.radians(course - true_bearing)))))
        span = math.degrees(length_m * aspect / max(distance * 1852.0, length_m))
        span *= 1.0 + 0.05 * detrand.normal(seed, "scope-span", target_id, epoch)
        quality = config.clamp(.5 + .45 * (1.0 - 1.0 / margin), .5, .95)
        ref = "V-%08X" % (detrand.bits(seed, "scope-ref", target_id) & 0xFFFFFFFF)
        old = previous.get(ref)
        if old is not None and recognized == "unknown" and old["cls"] != "unknown":
            recognized = old["cls"]      # a class once made out is held
        rows.append(dict(
            ref=ref, target_id=int(target_id), kind=kind, cls=recognized,
            bearing=bearing, span_deg=max(1e-3, min(180.0, span)), aspect=aspect,
            quality=quality, first_t=old["first_t"] if old is not None else now, t=now,
            range_nm=old["range_nm"] if old is not None else None,
            range_sigma_nm=old["range_sigma_nm"] if old is not None else None,
            range_t=old["range_t"] if old is not None else None))
    fresh = {row["ref"] for row in rows}
    for ref, old in previous.items():
        if ref not in fresh and 0.0 <= now - old["t"] < config.UBOOT_SIGHTING_LOST_S:
            rows.append(dict(old))
    for row in rows:
        if row["range_t"] is not None and not (
                0.0 <= now - row["range_t"] <= config.SONAR_PING_FIX_MAX_AGE_S):
            row["range_nm"] = row["range_sigma_nm"] = row["range_t"] = None
    rows.sort(key=lambda row: (row["bearing"], row["ref"]))
    orders.sightings = rows[:config.UBOOT_SIGHTINGS_MAX]
    for row in orders.sightings:
        if row["ref"] not in orders._sightings_seen and row["t"] == now:
            orders._sightings_seen.add(row["ref"])
            orders.event("sighting_" + row["cls"], bearing=f"{row['bearing']:03.0f}")


def sighting_in_crosshair(boat, now: float):
    """The fresh sighting nearest the crosshair within the stadimeter window."""
    bearing = scope_bearing(boat)
    best = None
    for row in boat.orders.sightings:
        if not 0.0 <= now - row["t"] <= 1.0:
            continue
        off = abs((row["bearing"] - bearing + 180.0) % 360.0 - 180.0)
        if off <= config.UBOOT_STADIMETER_WINDOW_DEG and (best is None or off < best[0]):
            best = (off, row)
    return None if best is None else best[1]


def stadimeter(game, boat: CrewedBoat):
    """Range the sighting under the crosshair from its apparent length and
    the assumed length of its class (a generic frigate when unrecognized).

    The reading becomes a VISUAL fix (±25 %) on the boat's sonar contact of
    the same target, usable for a shot like a ping fix, for 120 s.
    """
    if not scope_available(boat):
        return "uboot_mast_down"
    row = sighting_in_crosshair(boat, game.sim_t)
    if row is None:
        return "uboot_no_sighting"
    length = config.UBOOT_STADIMETER_LENGTHS_M.get(row["cls"])
    if length is None:
        return "uboot_no_stadimeter"
    range_nm = length / math.radians(max(row["span_deg"], 1e-3)) / 1852.0
    range_nm = max(0.05, min(40.0, range_nm))
    sigma = range_nm * config.UBOOT_STADIMETER_ERR_FRAC
    row["range_nm"], row["range_sigma_nm"], row["range_t"] = range_nm, sigma, game.sim_t
    contact = boat.station.sonar.contacts.get(row["target_id"])
    if contact is not None:
        contact.update_visual(row["bearing"], range_nm, game.sim_t, sigma, row["quality"],
                              boat.sub.x, boat.sub.y)
    return True


def advance_mechanics(game, boat: CrewedBoat, dt: float) -> None:
    """Per-substep sonar clocks (ping cooldown, queued echoes)."""
    if boat.sub.sunk:
        return
    boat.station.sonar.advance_mechanics(dt, game.sim_t, boat.station.observer)


def send_ping(game, boat: CrewedBoat):
    """Active transmission from the boat: an echo for the crew, and every ship
    in reach hears the boat (the frigate through its ordinary intercept)."""
    if boat.sonar_down():
        return "sonar_down"
    sonar = boat.station.sonar
    if not sonar.fire_ping():
        return "not_ready"
    result = boat.sub.command_ping()
    if result is not True:
        return result
    sonar.queue_ping(boat.station.observer, boat.sonar_targets(game), game.world,
                     game.sim_t, 1.0, mode="BOW")
    return True


def boat_is_alive(boat) -> bool:
    return boat is not None and not boat.sub.sunk


def contact_lost(game, contact) -> bool:
    return not 0 <= game.sim_t - contact.last_seen < config.SONAR_CONTACT_LOST_S
