"""Schadensmodell: Abteilungen mit Wassereinbruch, Stabilität, Brand und
Reparaturtrupps.

Physics (phase 10):

* Each compartment has a volume, permeability, centroid and height.  A hole
  (area in m^2) below the waterline floods it with the orifice law
  Q = Cd A sqrt(2 g h), where h is the head between the outside waterline
  (dynamic draft plus heel on that side) and the water already inside, so
  flooding slows and stops as the levels equalize.  Teams first patch holes
  (consuming a patch kit), then pump.
* Floodwater adds displacement; free surfaces reduce GM; the transverse
  moment of off-centre water gives the heel (list).  The ship sinks when the
  floodwater exceeds its reserve buoyancy and capsizes when GM is lost or the
  heel passes the downflooding angle.
* Fire intensity grows with the compartment's fuel load and oxygen, is
  smothered by flooding, spreads deterministically through hot bulkheads,
  can start from flooded switchboards and can cook off the magazine.
* Teams walk the compartment graph (transit time per hop).
* Station capability degrades continuously with flooding and fire.

The legacy percentages (flood 0..70 = destroyed, fire 0..100) and state
names remain the public interface for the UI and saves.
"""

import math
import random
from collections import deque

from src.core import config

COMPARTMENTS = [
    ("bridge", "Brücke"),
    ("sonar", "Sonarzentrale"),
    ("weapons", "Waffenzentrale"),
    ("opz", "OPZ / CIC"),
    ("radio", "Funk / Antennen"),
    ("engine", "Maschinerie"),
    ("flightdeck", "Flugdeck / Hangar"),
    ("hull_left", "Rumpf links"),
    ("hull_right", "Rumpf rechts"),
]

COMPARTMENT_ADJACENCY = {
    "bridge": ("sonar",),
    "sonar": ("bridge", "weapons", "opz", "hull_left", "hull_right"),
    "weapons": ("sonar", "opz", "engine", "hull_left", "hull_right"),
    "opz": ("sonar", "weapons", "radio", "hull_left", "hull_right"),
    "radio": ("opz", "flightdeck", "hull_left", "hull_right"),
    "engine": ("weapons", "flightdeck", "hull_left", "hull_right"),
    "flightdeck": ("radio", "engine", "hull_left", "hull_right"),
    "hull_left": ("sonar", "weapons", "opz", "radio", "engine", "flightdeck"),
    "hull_right": ("sonar", "weapons", "opz", "radio", "engine", "flightdeck"),
}

# Geometry (fictional, consistent): floodable volume (m^3, after
# permeability), centroid x (m forward of midships), y (m to starboard),
# floor height above keel (m), compartment height (m), width b (m),
# fuel/fire load factor, electrical switchboard.
GEOMETRY = {
    "bridge":     dict(volume=140.0, x=40.0, y=0.0, floor=10.0, height=4.0,
                       b=10.0, fuel=0.6, electrical=True),
    "sonar":      dict(volume=180.0, x=50.0, y=0.0, floor=0.5, height=5.0,
                       b=8.0, fuel=0.5, electrical=True),
    "weapons":    dict(volume=260.0, x=22.0, y=0.0, floor=1.5, height=6.0,
                       b=11.0, fuel=1.5, electrical=False),
    "opz":        dict(volume=200.0, x=10.0, y=0.0, floor=4.0, height=4.0,
                       b=12.0, fuel=0.8, electrical=True),
    "radio":      dict(volume=150.0, x=-5.0, y=0.0, floor=6.0, height=4.0,
                       b=10.0, fuel=0.6, electrical=True),
    "engine":     dict(volume=520.0, x=-25.0, y=0.0, floor=0.5, height=7.0,
                       b=13.0, fuel=1.4, electrical=False),
    "flightdeck": dict(volume=300.0, x=-45.0, y=0.0, floor=5.0, height=6.0,
                       b=13.0, fuel=1.2, electrical=False),
    "hull_left":  dict(volume=250.0, x=0.0, y=-5.5, floor=0.5, height=6.0,
                       b=3.0, fuel=0.3, electrical=False),
    "hull_right": dict(volume=250.0, x=0.0, y=5.5, floor=0.5, height=6.0,
                       b=3.0, fuel=0.3, electrical=False),
}

RHO = 1025.0
G = 9.80665
ORIFICE_CD = 0.6
DESIGN_DRAFT_M = 7.5
DISPLACEMENT_KG = 3_600_000.0
GM_M = 1.2
# Reserve buoyancy calibrated to the 1.0.0 sinking rule: 60 % mean flooding.
RESERVE_BUOYANCY_KG = 0.6 * sum(g["volume"] for g in GEOMETRY.values()) * RHO
CAPSIZE_HEEL_DEG = 35.0
CAPSIZE_GM_M = 0.05
# Torpedo hole area calibrated so a fresh hit floods a mid compartment at
# the 1.0.0 rate (DMG_FLOOD_RATE); a patch leaves 25 %.
PATCH_LEAK_FRACTION = config.DMG_LEAK_RATE / config.DMG_FLOOD_RATE
PATCH_KITS = 8
PATCH_TIME_S = 20.0
TEAM_HOP_S = 20.0
TEAM_BASE = "opz"                 # damage-control central
FIRE_SPREAD_LEVEL = 60.0
FIRE_SPREAD_HEAT_S = 30.0
FIRE_SMOTHER_FLOOD = 60.0
FIRE_WATER_COOLING = 0.3          # %/s at the smothering level
ELECTRICAL_SHORT_FLOOD = 40.0
COOK_OFF_FIRE = 90.0


def _reference_hole_m2() -> float:
    geo = GEOMETRY["weapons"]
    head = DESIGN_DRAFT_M - geo["floor"]
    rate = config.DMG_FLOOD_RATE / 100.0 * geo["volume"]      # m^3/s
    return rate / (ORIFICE_CD * math.sqrt(2.0 * G * head))


HIT_HOLE_M2 = _reference_hole_m2()


def orifice_inflow_m3_s(area_m2: float, head_m: float) -> float:
    if area_m2 <= 0.0 or head_m <= 0.0:
        return 0.0
    return ORIFICE_CD * area_m2 * math.sqrt(2.0 * G * head_m)


class Compartment:
    """Zustand: OK -> FLUTEND/BESCHAEDIGT -> ZERSTOERT."""

    def __init__(self, key: str, name: str):
        self.key = key
        self.name = name
        self.state = "OK"
        self.flood = 0.0  # 0..100 % of floodable volume (70 = destroyed)
        self.fire = 0.0   # M14: Brand 0..100 % (>100 = Kompartiment ZERSTOERT)
        self.hole_m2 = 0.0     # open hull area
        self.heat_s = 0.0      # time a strong fire has heated the bulkheads
        self.shorted = False   # switchboard already shorted by flooding

    @property
    def geometry(self) -> dict:
        return GEOMETRY[self.key]

    def water_m3(self) -> float:
        return self.flood / 100.0 * self.geometry["volume"]

    def water_level_m(self) -> float:
        """Height of the free surface above the keel."""
        geo = self.geometry
        return geo["floor"] + min(1.0, self.flood / 100.0) * geo["height"]

    def hit(self, rng: random.Random, hole_scale: float = 1.0) -> None:
        if self.state != "ZERSTOERT":
            self.state = "FLUTEND"
        self.hole_m2 = max(self.hole_m2, HIT_HOLE_M2 * hole_scale)
        self.flood = max(self.flood, rng.uniform(10.0, 30.0)
                         if self.geometry["floor"] < DESIGN_DRAFT_M else self.flood)
        if rng.random() < config.DMG_FIRE_START_CHANCE:
            self.fire = max(self.fire, rng.uniform(*config.DMG_FIRE_START))

    def capability(self) -> float:
        """0..1 remaining function of the station in this room."""
        if self.state == "ZERSTOERT":
            return 0.0
        return max(0.0, 1.0 - self.flood / config.DMG_DESTROY_FLOOD
                   - self.fire / (2.0 * config.DMG_FIRE_KILL))


class DamageModel:
    """Fregatten-Schäden + Reparaturteams (1–3)."""

    TEAM_COUNT = 3

    def __init__(self, rng: random.Random, repair_mult: float = 1.0):
        self.rng = rng
        self.repair_mult = repair_mult   # M7: Level-Faktor Reparaturrate
        self.compartments = {k: Compartment(k, n) for k, n in COMPARTMENTS}
        self.teams: dict[int, str | None] = {1: None, 2: None, 3: None}
        # Where each team stands and how long until it arrives (saved).
        self.team_position: dict[int, str] = {1: TEAM_BASE, 2: TEAM_BASE,
                                              3: TEAM_BASE}
        self.team_eta: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0}
        self.patch_kits = PATCH_KITS
        self.cooked_off = False
        self.capsized = False
        self.total = 0.0
        self.ship_sunk = False
        self.draft_m = DESIGN_DRAFT_M

    # --- Ereignisse ---

    def torpedo_hit(self, hit_zone: str | None = None,
                    impact: tuple[float, float] | None = None,
                    hole_scale: float = 1.0) -> list[str]:
        """Damage the compartments at the impact point.

        ``impact`` is (longitudinal, lateral) in -1..1 of the hull (bow and
        starboard positive): the nearest compartment floods, and the next one
        within the blast radius too.  Without an impact the legacy zone
        weighting chooses 1-2 compartments at random.
        """
        if impact is not None:
            chosen = self._impact_compartments(*impact)
        else:
            chosen = self._zone_compartments(hit_zone)
        for key in chosen:
            self.compartments[key].hit(self.rng, hole_scale)
        return chosen

    def _impact_compartments(self, longitudinal: float, lateral: float) -> list[str]:
        x = longitudinal * 59.0
        y = lateral * 7.0
        ranked = sorted(
            GEOMETRY, key=lambda key: (math.hypot(GEOMETRY[key]["x"] - x,
                                                  (GEOMETRY[key]["y"] - y) * 3.0),
                                       key))
        first = ranked[0]
        chosen = [first]
        side = "hull_right" if lateral >= 0.0 else "hull_left"
        if side not in chosen and abs(lateral) >= 0.4:
            chosen.append(side)
        elif ranked[1] in COMPARTMENT_ADJACENCY[first]:
            chosen.append(ranked[1])
        return chosen[:2]

    def _zone_compartments(self, hit_zone):
        keys = [k for k in self.compartments]
        n = self.rng.choice((1, 2))
        preferred = {
            "bow": ["bridge", "sonar", "hull_left", "hull_right"],
            "stern": ["engine", "flightdeck", "weapons", "hull_left", "hull_right"],
            "port": ["hull_left", "engine", "weapons"],
            "starboard": ["hull_right", "engine", "weapons"],
            "center": ["weapons", "opz", "radio", "engine", "hull_left", "hull_right"],
        }.get(hit_zone, [])
        chosen = []
        if preferred and self.rng.random() < 0.70:
            chosen.append(self.rng.choice(preferred))
        remaining = [k for k in keys if k not in chosen]
        if len(chosen) < n:
            chosen.extend(self.rng.sample(remaining, n - len(chosen)))
        return chosen

    def missile_hit(self, longitudinal: float, lateral: float) -> list[str]:
        """Above-waterline hit: fire and structural damage, no flooding."""
        key = self._impact_compartments(longitudinal, lateral)[0]
        room = self.compartments[key]
        if room.state == "OK":
            room.state = "BESCHAEDIGT"
        room.fire = max(room.fire, 40.0)
        return [key]

    def grounding_impact(self, energy_j: float, longitudinal: float,
                         lateral: float) -> dict[str, float]:
        """Apply deterministic localized flooding without consuming RNG state."""
        energy = max(0.0, float(energy_j))
        severity = min(100.0, math.sqrt(energy / 1_000_000.0) * 1.8)
        side = "hull_right" if lateral >= 0.0 else "hull_left"
        if longitudinal > 0.35:
            local = "sonar" if abs(lateral) < 0.5 else "bridge"
        elif longitudinal < -0.35:
            local = "engine" if abs(lateral) < 0.5 else "flightdeck"
        else:
            local = "weapons" if abs(lateral) < 0.5 else side
        allocations = {side: severity, local: severity * 0.55}
        applied = {}
        for key, amount in allocations.items():
            compartment = self.compartments[key]
            old = compartment.flood
            compartment.flood = min(config.DMG_DESTROY_FLOOD,
                                    compartment.flood + amount)
            if compartment.state != "ZERSTOERT" and amount > 0.0:
                compartment.state = ("ZERSTOERT"
                                     if compartment.flood >= config.DMG_DESTROY_FLOOD
                                     else "FLUTEND")
                # A grounding tears the shell plating open too.
                compartment.hole_m2 = max(compartment.hole_m2,
                                          HIT_HOLE_M2 * amount / 30.0)
            applied[key] = compartment.flood - old
        self._recompute_totals()
        return applied

    # --- stability -------------------------------------------------------------

    def flood_mass_kg(self) -> float:
        return sum(c.water_m3() for c in self.compartments.values()) * RHO

    def gm_effective_m(self) -> float:
        """GM with the free-surface correction of partly flooded rooms."""
        displacement = DISPLACEMENT_KG + self.flood_mass_kg()
        free = 0.0
        for c in self.compartments.values():
            if 0.0 < c.flood < 95.0:
                geo = c.geometry
                length = geo["volume"] / (geo["b"] * geo["height"])
                free += RHO * length * geo["b"] ** 3 / 12.0
        return GM_M - free / displacement

    def _heel_rad(self) -> float:
        displacement = DISPLACEMENT_KG + self.flood_mass_kg()
        moment = sum(c.water_m3() * RHO * c.geometry["y"]
                     for c in self.compartments.values())
        gm = max(self.gm_effective_m(), CAPSIZE_GM_M)
        return math.atan(moment / (displacement * gm))

    def _recompute_totals(self) -> None:
        self.total = sum(c.flood for c in self.compartments.values())
        if self.flood_mass_kg() >= RESERVE_BUOYANCY_KG:
            self.ship_sunk = True
        if (self.gm_effective_m() <= CAPSIZE_GM_M
                or abs(math.degrees(self._heel_rad())) >= CAPSIZE_HEEL_DEG):
            self.capsized = True
            self.ship_sunk = True

    # --- Steuerung ---

    def repair_candidates(self) -> list[str]:
        return [k for k, c in self.compartments.items()
                if c.state != "ZERSTOERT" and (c.state != "OK" or c.fire > 0.0)]

    def _travel_s(self, start: str, destination: str) -> float:
        """Transit time along the compartment graph (hops x TEAM_HOP_S)."""
        if start == destination:
            return 0.0
        seen = {start}
        queue = deque([(start, 0)])
        while queue:
            key, hops = queue.popleft()
            for neighbour in COMPARTMENT_ADJACENCY[key]:
                if neighbour in seen:
                    continue
                if neighbour == destination:
                    return (hops + 1) * TEAM_HOP_S
                seen.add(neighbour)
                queue.append((neighbour, hops + 1))
        return TEAM_HOP_S * len(COMPARTMENTS)

    def _send(self, team: int, destination: str | None) -> None:
        self.teams[team] = destination
        if destination is None:
            self.team_eta[team] = 0.0
            return
        self.team_eta[team] = self._travel_s(self.team_position[team], destination)

    def assign_team_cycle(self, team: int) -> str | None:
        """Team auf das nächste (oder weitere) betroffene Kompartiment."""
        cands = self.repair_candidates()
        if not cands:
            self._send(team, None)
            return None
        cur = self.teams.get(team)
        if cur in cands:
            nxt = cands[(cands.index(cur) + 1) % len(cands)]
        else:
            nxt = cands[0]
        self._send(team, nxt)
        return nxt

    def assign_team(self, team: int, destination: str) -> bool:
        """Assign explicitly without silently displacing another team."""
        if team not in self.teams or destination not in self.repair_candidates():
            return False
        self._send(team, destination)
        return True

    def unassign_team(self, team: int) -> None:
        self._send(team, None)

    def teams_on(self, key: str) -> list[int]:
        """Teams that have arrived and are working in this room."""
        return [t for t, k in self.teams.items()
                if k == key and self.team_eta.get(t, 0.0) <= 0.0]

    def repair_rates(self, key: str) -> tuple[float, float]:
        """Flood/fire removal per second with the current team assignment."""
        count = len(self.teams_on(key))
        factor = 0.0 if not count else 1.0 + .6 * (count - 1)
        return (config.DMG_REPAIR_RATE * self.repair_mult * factor,
                config.DMG_FIRE_REPAIR_RATE * count)

    def _inflow_pct_s(self, c: Compartment) -> float:
        geo = c.geometry
        if c.hole_m2 <= 0.0 or c.state == "ZERSTOERT":
            return 0.0
        side = geo["y"]
        waterline = self.draft_m + side * math.tan(self._heel_rad())
        head = waterline - max(geo["floor"], c.water_level_m())
        return orifice_inflow_m3_s(c.hole_m2, head) / geo["volume"] * 100.0

    def compartment_trend(self, key: str) -> dict:
        """Pure instantaneous net rates, excluding random spread/transitions.

        Rates are percentage points per simulation second. Destroyed rooms and
        a sunk ship cannot improve; zero-valued hazards cannot fall below zero.
        """
        c = self.compartments[key]
        repairable = not self.ship_sunk and c.state != "ZERSTOERT"
        flood_rate = fire_rate = 0.0
        if repairable:
            flood_repair, fire_repair = self.repair_rates(key)
            flood_rate = self._inflow_pct_s(c) - flood_repair
            if c.flood <= 0.0:
                flood_rate = max(0.0, flood_rate)
            if c.fire > 0.0:
                fire_rate = self._fire_growth(c) - fire_repair
        return {"flood_rate": flood_rate, "fire_rate": fire_rate,
                "repairable": repairable}

    # --- Abfragen ---

    def station_state(self, key: str) -> str:
        return self.compartments[key].state

    def station_down(self, key: str) -> bool:
        return self.compartments[key].state == "ZERSTOERT"

    def station_degraded(self, key: str) -> bool:
        return self.compartments[key].state in ("FLUTEND", "BESCHAEDIGT") \
            or self.compartments[key].fire > 0.0

    def capability(self, key: str) -> float:
        return self.compartments[key].capability()

    def avg_flood(self) -> float:
        return self.total / len(self.compartments)

    def list_deg(self) -> float:
        """Heel from off-centre floodwater (positive = to starboard)."""
        return config.clamp(math.degrees(self._heel_rad()),
                            -CAPSIZE_HEEL_DEG, CAPSIZE_HEEL_DEG)

    def engine_speed_cap(self) -> float:
        if self.station_down("engine"):
            return 8.0
        if self.station_degraded("engine"):
            # Continuous loss of plant power with flooding and fire.
            return max(8.0, 8.0 + (config.SHIP_SPEED_MAX_KN - 8.0)
                       * min(15.0 / config.SHIP_SPEED_MAX_KN,
                             self.capability("engine") + 0.2))
        return config.SHIP_SPEED_MAX_KN

    # --- Update ---

    def _fire_growth(self, c: Compartment) -> float:
        """Net intensity change: fuel-driven growth limited by oxygen, minus
        cooling by floodwater (continuous, so trends stay predictable)."""
        oxygen = max(0.0, 1.0 - c.flood / FIRE_SMOTHER_FLOOD)
        cooling = FIRE_WATER_COOLING * max(0.0, c.flood - 20.0) / FIRE_SMOTHER_FLOOD
        return config.DMG_FIRE_RATE * c.geometry["fuel"] * oxygen - cooling

    def _update_compartment(self, c: Compartment, dt: float) -> None:
        if c.state == "ZERSTOERT":
            return
        teams = self.teams_on(c.key)
        flood_repair, fire_repair = self.repair_rates(c.key)
        # Rates of this step come from the state at its start.
        fire_net = self._fire_growth(c) - fire_repair
        inflow = self._inflow_pct_s(c)
        if teams and c.hole_m2 > 0.0 and c.state == "FLUTEND":
            # Shoring and patching the hole needs a kit.
            if self.patch_kits > 0 and c.flood <= 35.0 + flood_repair * PATCH_TIME_S:
                self.patch_kits -= 1
                c.hole_m2 *= PATCH_LEAK_FRACTION
                c.state = "BESCHAEDIGT"
        c.flood += inflow * dt
        if teams:
            c.flood -= flood_repair * dt
            if c.flood <= 0.0:
                c.flood = 0.0
                c.hole_m2 = 0.0
                c.state = "OK" if c.fire <= 0.0 else "BESCHAEDIGT"
        c.flood = max(0.0, c.flood)
        if c.state in ("FLUTEND", "BESCHAEDIGT") and c.flood >= config.DMG_DESTROY_FLOOD:
            c.state = "ZERSTOERT"
            c.flood = config.DMG_DESTROY_FLOOD
            return
        if (c.geometry["electrical"] and not c.shorted
                and c.flood >= ELECTRICAL_SHORT_FLOOD):
            c.shorted = True
            c.fire = max(c.fire, 10.0)
        if c.fire > 0.0:
            c.fire += fire_net * dt
            c.fire = max(0.0, c.fire)
            c.heat_s = c.heat_s + dt if c.fire >= FIRE_SPREAD_LEVEL else 0.0
            if c.fire >= config.DMG_FIRE_KILL:
                c.state = "ZERSTOERT"
                c.flood = max(c.flood, config.DMG_DESTROY_FLOOD)
        else:
            c.heat_s = 0.0

    def _spread_fire(self) -> None:
        for c in self.compartments.values():
            if c.heat_s < FIRE_SPREAD_HEAT_S:
                continue
            c.heat_s = 0.0
            for key in COMPARTMENT_ADJACENCY[c.key]:
                neighbour = self.compartments[key]
                if neighbour.fire <= 0.0 and neighbour.state != "ZERSTOERT" \
                        and neighbour.flood < FIRE_SMOTHER_FLOOD:
                    neighbour.fire = config.DMG_FIRE_START[0]

    def _cook_off(self) -> None:
        room = self.compartments["weapons"]
        if self.cooked_off or room.fire < COOK_OFF_FIRE:
            return
        self.cooked_off = True
        room.state = "ZERSTOERT"
        room.flood = config.DMG_DESTROY_FLOOD
        for key in COMPARTMENT_ADJACENCY["weapons"]:
            neighbour = self.compartments[key]
            if neighbour.state == "ZERSTOERT":
                continue
            neighbour.state = "FLUTEND"
            neighbour.hole_m2 = max(neighbour.hole_m2, HIT_HOLE_M2)
            neighbour.fire = max(neighbour.fire, 30.0)

    def update(self, dt: float, draft_m: float | None = None) -> None:
        if self.ship_sunk:
            return
        if draft_m is not None:
            self.draft_m = draft_m
        for team, eta in self.team_eta.items():
            if eta > 0.0:
                self.team_eta[team] = max(0.0, eta - dt)
                if self.team_eta[team] <= 0.0 and self.teams[team] is not None:
                    self.team_position[team] = self.teams[team]
        for c in self.compartments.values():
            self._update_compartment(c, dt)
        self._spread_fire()
        self._cook_off()
        for team, key in self.teams.items():
            c = self.compartments[key] if key is not None else None
            if c is not None and c.state == "OK" and c.fire <= 0.0:
                self.teams[team] = None
        self._recompute_totals()
