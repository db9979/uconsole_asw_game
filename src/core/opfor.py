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

from src.core import config
from src.core.i18n import message
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
              "shallow_water": "navigation"}

    def __init__(self):
        self.silent = False
        self.bottomed = False
        self.mast = False
        self._events = []
        self._battery_state = "ok"
        self._keel_warned = False

    def event(self, key: str) -> None:
        if key in self.EVENTS and key not in self._events:
            self._events.append(key)

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
    for key in orders.drain_events():
        boat.notice(game.sim_t, CrewOrders.EVENTS[key], message(f"uboot.event.{key}"),
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
