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

from src.core import config
from src.core.i18n import message
from src.core.plot import PlotLayer
from src.physics import torpedo_dyn
from src.sonar.platforms import (OwnShipAcousticSource, OwnTorpedoAcousticSource,
                                 SubSonarPlatform)
from src.sonar.sonar import SonarSystem
from src.sonar.station import SonarStation

# Bounded crew event feed (newest last) and the SonarSystem seed salt.
OPFOR_FEED_MAX = 64
_SONAR_SEED_SALT = 0x0B0A7
# The boat's sonar room is lost with the boat: damage beyond this disables it.
OPFOR_SONAR_DOWN_DAMAGE = 90.0


class CrewOrders:
    """Transient crew settings of the crewed boat (never saved).

    The ``Sub`` reads them only while ``manual``; they vanish with the crew
    binding (release, reset, load), after which the AI commands the boat again.
    """

    # Crew notices raised by the boat itself (key -> feed category).
    EVENTS = {"obstacle": "navigation", "snorkel_stopped": "navigation",
              "battery_low": "navigation", "battery_empty": "navigation",
              "shallow_water": "navigation", "wire_broken": "waffen",
              "ping_heard": "sonar", "torpedo_heard": "sonar",
              "mast_lowered": "navigation", "esm_intercept": "sonar",
              "obstacle_ahead": "navigation"}

    def __init__(self):
        self.silent = False
        self.bottomed = False
        self.mast = False
        # Measured alarm bearings (the boat's own intercepts) and ESM picture.
        self.alarm_seq = 0
        self.ping_bearing = None
        self.torpedo_bearing = None
        self.esm = []
        self._esm_seen = set()
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

    def event(self, key: str, **values) -> None:
        if key in self.EVENTS and (values or all(k != key for k, _ in self._events)):
            self._events.append((key, values))

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


class CrewWire:
    """The guidance wire of one crew torpedo (transient; cut by a load).

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


class CrewedBoat:
    """One crewed submarine: the boat, its sonar workstation and its feed."""

    def __init__(self, sub, runtime_catalog):
        self.sub = sub
        self.sub_id = sub.id
        self.orders = CrewOrders()
        sub.crew = self.orders
        platform = SubSonarPlatform(sub)
        sonar = SonarSystem(seed=(int(sub.sensor_seed) ^ _SONAR_SEED_SALT) & 0x7FFFFFFF,
                            acoustic_profiles=runtime_catalog.acoustic_profiles)
        self.station = SonarStation(sonar, kind="sub", observer=platform)
        self.station.down = self.sonar_down
        self.feed = deque(maxlen=OPFOR_FEED_MAX)
        self.feed_seq = 0
        # The boat's own grease-pencil plot (transient, never the frigate's).
        self.plot = PlotLayer()
        # Local command-station UI (display only): chart camera and page.
        self.chart_view = None
        self.chart_follow = True
        self.command_page = 0
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
    # ESM with the mast up: the boat's own intercepts of radar emitters.
    esm = []
    if orders.mast:
        for observation in sub.sensor_suite.local_picture.tracks(game.sim_t, ("esm",)):
            age = max(0.0, game.sim_t - observation.last_seen)
            esm.append((observation.bearing % 360.0, observation.quality, age))
            if observation.track_id not in orders._esm_seen:
                orders._esm_seen.add(observation.track_id)
                orders.event("esm_intercept", bearing=f"{observation.bearing % 360.0:03.0f}")
    else:
        orders._esm_seen.clear()
    orders.esm = sorted(esm)[:16]
    for key, values in orders.drain_events():
        boat.notice(game.sim_t, CrewOrders.EVENTS[key], message(f"uboot.event.{key}", **values),
                    stamp=game.world.format_time())


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
